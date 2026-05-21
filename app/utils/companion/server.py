"""CompanionServer — TCP connection manager for RimWorld companion mod.

Manages a single TCP client connection using QTcpServer. Handles the
handshake protocol, heartbeat monitoring, newline-delimited JSON-RPC
message framing, and request/response correlation.
"""

from typing import Any

from loguru import logger
from PySide6.QtCore import QObject, QTimer
from PySide6.QtNetwork import QHostAddress, QTcpServer, QTcpSocket

from app.utils.app_info import AppInfo
from app.utils.companion.protocol import (
    ERR_VERSION_MISMATCH,
    PROTOCOL_VERSION,
    JsonRpcError,
    create_error_response,
    create_notification,
    create_request,
    create_response,
    is_notification,
    is_request,
    is_response,
    parse_message,
    serialize_message,
)
from app.utils.event_bus import EventBus

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HANDSHAKE_TIMEOUT_MS = 5000
HEARTBEAT_INTERVAL_MS = 5000
HEARTBEAT_MISS_LIMIT = 3
APPLY_TIMEOUT_MS = 60000
MAX_BUFFER_SIZE = 1_048_576  # 1 MB

# Maps request method names to EventBus signal names for response routing
_RESPONSE_SIGNAL_MAP: dict[str, str] = {
    "get.load_order": "companion_load_order_received",
    "get.mod_errors": "companion_mod_errors_received",
    "get.mod_details": "companion_mod_details_received",
    "get.harmony_patches": "companion_harmony_patches_received",
}


class CompanionServer(QObject):
    """TCP server managing a single companion mod connection.

    The server listens on localhost for a single client (the RimWorld
    companion mod). It enforces a handshake protocol on first message,
    monitors liveness via heartbeat notifications, and routes JSON-RPC
    messages to the appropriate EventBus signals.
    """

    def __init__(self, port: int = 29515, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._requested_port = port
        self._event_bus = EventBus()

        # Networking
        self._server = QTcpServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._client: QTcpSocket | None = None
        self._buffer = b""
        self._handshake_done = False

        # Pending requests: id -> method name
        self._pending_requests: dict[int | str, str] = {}

        # Pending apply state
        self._pending_apply_id: int | str | None = None

        # Timers
        self._handshake_timer = QTimer(self)
        self._handshake_timer.setSingleShot(True)
        self._handshake_timer.setInterval(HANDSHAKE_TIMEOUT_MS)
        self._handshake_timer.timeout.connect(self._on_handshake_timeout)

        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(HEARTBEAT_INTERVAL_MS)
        self._heartbeat_timer.timeout.connect(self._on_heartbeat_tick)
        self._missed_heartbeats = 0

        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(APPLY_TIMEOUT_MS)
        self._apply_timer.timeout.connect(self._on_apply_timeout)

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start listening on ``127.0.0.1:{port}``.

        :return: True if the server started successfully
        """
        address = QHostAddress(QHostAddress.SpecialAddress.LocalHost)
        if not self._server.listen(address, self._requested_port):
            error_msg = (
                f"Failed to bind companion server on port "
                f"{self._requested_port}: {self._server.errorString()}"
            )
            logger.error(error_msg)
            self._event_bus.companion_server_error.emit(error_msg)
            return False

        logger.info(
            "Companion server listening on 127.0.0.1:{}",
            self._server.serverPort(),
        )
        return True

    def stop(self) -> None:
        """Stop the server and disconnect any client."""
        self._disconnect_client(emit_signal=False)
        if self._server.isListening():
            self._server.close()
            logger.info("Companion server stopped")

    def port(self) -> int:
        """Return the actual port the server is bound to."""
        return self._server.serverPort()

    def is_listening(self) -> bool:
        """Return whether the server is currently listening."""
        return self._server.isListening()

    def has_connection(self) -> bool:
        """Return whether a client is connected and has completed the handshake."""
        return (
            self._client is not None
            and self._client.state() == QTcpSocket.SocketState.ConnectedState
            and self._handshake_done
        )

    # ------------------------------------------------------------------
    # Outgoing messages
    # ------------------------------------------------------------------

    def send_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> int | None:
        """Send a JSON-RPC request to the connected client.

        :param method: The RPC method name
        :param params: Optional parameters
        :return: The request id, or None if no client is connected
        """
        if not self.has_connection():
            return None

        msg = create_request(method, params)
        req_id: int = msg["id"]
        self._pending_requests[req_id] = method

        if method == "apply.mod_list":
            self._pending_apply_id = req_id
            self._apply_timer.start()

        self._send_raw(msg)
        logger.debug("Sent request id={} method={}", req_id, method)
        return req_id

    def send_notification(
        self, method: str, params: dict[str, Any] | None = None
    ) -> bool:
        """Send a JSON-RPC notification to the connected client.

        :param method: The notification method name
        :param params: Optional parameters
        :return: True if the notification was sent
        """
        if not self.has_connection():
            return False

        msg = create_notification(method, params)
        self._send_raw(msg)
        return True

    # ------------------------------------------------------------------
    # Connection management (private)
    # ------------------------------------------------------------------

    def _on_new_connection(self) -> None:
        """Accept a new incoming TCP connection."""
        pending = self._server.nextPendingConnection()
        if pending is None:
            return

        # Drop existing client if one is connected
        if self._client is not None:
            logger.info("Dropping existing companion connection for new client")
            self._disconnect_client(emit_signal=True)

        self._client = pending
        self._buffer = b""
        self._handshake_done = False
        self._missed_heartbeats = 0

        self._client.readyRead.connect(self._on_data_ready)
        self._client.disconnected.connect(self._on_client_disconnected)

        self._handshake_timer.start()
        logger.info(
            "New companion connection from {}:{}",
            self._client.peerAddress().toString(),
            self._client.peerPort(),
        )

    def _on_client_disconnected(self) -> None:
        """Handle the client disconnecting."""
        was_handshaked = self._handshake_done
        self._cleanup_client_state()

        if was_handshaked:
            logger.info("Companion mod disconnected")
            self._event_bus.companion_disconnected.emit()
        else:
            logger.debug("Unhandshaked client disconnected")

    def _disconnect_client(self, *, emit_signal: bool) -> None:
        """Forcibly disconnect the current client."""
        if self._client is None:
            return

        was_handshaked = self._handshake_done

        # Disconnect signals before closing to avoid re-entrant slot calls
        try:
            self._client.readyRead.disconnect(self._on_data_ready)
        except RuntimeError:
            pass
        try:
            self._client.disconnected.disconnect(self._on_client_disconnected)
        except RuntimeError:
            pass

        self._client.abort()
        self._cleanup_client_state()

        if emit_signal and was_handshaked:
            self._event_bus.companion_disconnected.emit()

    def _cleanup_client_state(self) -> None:
        """Reset all per-connection state."""
        self._client = None
        self._buffer = b""
        self._handshake_done = False
        self._pending_requests.clear()
        self._pending_apply_id = None
        self._missed_heartbeats = 0

        self._handshake_timer.stop()
        self._heartbeat_timer.stop()
        self._apply_timer.stop()

    # ------------------------------------------------------------------
    # Data handling
    # ------------------------------------------------------------------

    def _on_data_ready(self) -> None:
        """Read available data, split on newlines, and process messages."""
        if self._client is None:
            return

        self._buffer += bytes(self._client.readAll())

        if len(self._buffer) > MAX_BUFFER_SIZE:
            logger.warning("Companion: buffer exceeded max size — disconnecting")
            self._disconnect_client(emit_signal=True)
            return

        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            self._process_line(line)

    def _process_line(self, line: bytes) -> None:
        """Parse and route a single newline-delimited message."""
        try:
            msg = parse_message(line)
        except JsonRpcError as exc:
            logger.warning("Failed to parse message from companion: {}", exc)
            return

        if not self._handshake_done:
            self._handle_handshake(msg)
        elif is_notification(msg):
            self._handle_notification(msg)
        elif is_response(msg):
            self._handle_response(msg)
        elif is_request(msg):
            logger.warning(
                "Unexpected request from companion after handshake: {}",
                msg.get("method"),
            )
        else:
            logger.warning("Unrecognized message structure from companion")

    # ------------------------------------------------------------------
    # Handshake
    # ------------------------------------------------------------------

    def _handle_handshake(self, msg: dict[str, Any]) -> None:
        """Validate the handshake message and respond."""
        self._handshake_timer.stop()

        # Must be a request with method "handshake"
        if not is_request(msg) or msg.get("method") != "handshake":
            logger.warning("First message was not a handshake request, disconnecting")
            self._disconnect_client(emit_signal=False)
            return

        params = msg.get("params", {})
        if not isinstance(params, dict):
            logger.warning("Handshake params is not an object, disconnecting")
            self._disconnect_client(emit_signal=False)
            return

        client_version = params.get("protocol_version")
        if client_version != PROTOCOL_VERSION:
            logger.warning(
                "Protocol version mismatch: client={}, server={}",
                client_version,
                PROTOCOL_VERSION,
            )
            error_resp = create_error_response(
                id=msg["id"],
                code=ERR_VERSION_MISMATCH,
                message=(
                    f"Protocol version mismatch: expected {PROTOCOL_VERSION}, "
                    f"got {client_version}"
                ),
            )
            self._send_raw(error_resp)
            self._disconnect_client(emit_signal=False)
            return

        # Handshake successful
        self._handshake_done = True

        response = create_response(
            id=msg["id"],
            result={
                "rimsort_version": str(AppInfo().app_version),
                "protocol_version": PROTOCOL_VERSION,
            },
        )
        self._send_raw(response)

        self._heartbeat_timer.start()

        logger.info("Companion handshake complete: {}", params)
        self._event_bus.companion_connected.emit(params)

    # ------------------------------------------------------------------
    # Notification routing
    # ------------------------------------------------------------------

    def _handle_notification(self, msg: dict[str, Any]) -> None:
        """Route incoming notifications to the appropriate EventBus signal."""
        method = msg.get("method", "")
        params = msg.get("params", {})
        if not isinstance(params, dict):
            params = {}

        if method == "heartbeat":
            self._missed_heartbeats = 0
            self._event_bus.companion_heartbeat.emit(params)

        elif method == "game.state_changed":
            state = params.get("state", "unknown")
            self._event_bus.companion_state_changed.emit(state)

        elif method == "apply.mod_list.result":
            self._apply_timer.stop()
            self._pending_apply_id = None
            self._event_bus.companion_apply_result.emit(params)

        else:
            logger.debug("Unhandled notification method: {}", method)

    # ------------------------------------------------------------------
    # Response routing
    # ------------------------------------------------------------------

    def _handle_response(self, msg: dict[str, Any]) -> None:
        """Route incoming responses to the appropriate EventBus signal."""
        resp_id = msg.get("id")
        if resp_id not in self._pending_requests:
            logger.warning("Received response for unknown request id={}", resp_id)
            return

        method = self._pending_requests.pop(resp_id)

        if "error" in msg:
            logger.warning(
                "Error response for request id={} method={}: {}",
                resp_id,
                method,
                msg["error"],
            )
            return

        result = msg.get("result", {})
        signal_name = _RESPONSE_SIGNAL_MAP.get(method)
        if signal_name is None:
            logger.debug("No signal mapping for response method={}, ignoring", method)
            return

        signal = getattr(self._event_bus, signal_name, None)
        if signal is not None:
            signal.emit(result)
        else:
            logger.warning("EventBus has no signal named {}", signal_name)

    # ------------------------------------------------------------------
    # Heartbeat monitoring
    # ------------------------------------------------------------------

    def _on_heartbeat_tick(self) -> None:
        """Check heartbeat liveness on each timer tick."""
        self._missed_heartbeats += 1
        if self._missed_heartbeats >= HEARTBEAT_MISS_LIMIT:
            logger.warning(
                "Companion missed {} heartbeats, disconnecting",
                self._missed_heartbeats,
            )
            self._disconnect_client(emit_signal=True)

    # ------------------------------------------------------------------
    # Handshake timeout
    # ------------------------------------------------------------------

    def _on_handshake_timeout(self) -> None:
        """Drop the connection if no handshake within the timeout."""
        logger.warning("Handshake timeout, disconnecting client")
        self._disconnect_client(emit_signal=False)

    # ------------------------------------------------------------------
    # Apply timeout
    # ------------------------------------------------------------------

    def _on_apply_timeout(self) -> None:
        """Handle apply.mod_list timeout."""
        logger.warning("Apply mod list request timed out")
        timed_out_id = self._pending_apply_id
        self._pending_apply_id = None
        self._event_bus.companion_apply_result.emit(
            {
                "request_id": timed_out_id,
                "accepted": False,
                "message": "Timed out waiting for mod list apply confirmation",
            }
        )

    # ------------------------------------------------------------------
    # Low-level send
    # ------------------------------------------------------------------

    def _send_raw(self, msg: dict[str, Any]) -> None:
        """Serialize and send a message to the connected client."""
        if self._client is None:
            return
        data = serialize_message(msg)
        self._client.write(data)
        self._client.flush()
