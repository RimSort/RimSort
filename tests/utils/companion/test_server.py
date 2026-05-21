"""Tests for the CompanionServer TCP connection manager."""

import json
import socket
import time

import pytest
from PySide6.QtCore import QCoreApplication

from app.utils.companion.protocol import (
    PROTOCOL_VERSION,
    create_notification,
    create_request,
    serialize_message,
)
from app.utils.companion.server import (
    CompanionServer,
)
from app.utils.event_bus import EventBus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _process_events() -> None:
    """Process pending Qt events so the server can handle socket I/O."""
    app = QCoreApplication.instance()
    if app is not None:
        app.processEvents()


def _recv_with_events(sock: socket.socket, timeout: float = 2.0) -> bytes:
    """Receive data from a socket while pumping the Qt event loop.

    Reads in non-blocking bursts, processing Qt events between attempts,
    until a newline-delimited message arrives or the timeout expires.
    """
    sock.setblocking(False)
    buf = b""
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            _process_events()
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    raise ConnectionError("Socket closed")
                buf += chunk
                if b"\n" in buf:
                    return buf
            except BlockingIOError:
                pass
            time.sleep(0.01)
    finally:
        sock.setblocking(True)
        sock.settimeout(2)
    raise TimeoutError("Timed out waiting for data from server")


def _read_message(sock: socket.socket) -> dict:
    """Read a single newline-delimited JSON message, pumping Qt events."""
    data = _recv_with_events(sock)
    line = data.split(b"\n", 1)[0]
    return json.loads(line)


def _connect_and_handshake(port: int) -> socket.socket:
    """Open a TCP socket and complete the handshake, pumping Qt events."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    sock.connect(("127.0.0.1", port))

    # Let the server accept the connection
    _process_events()

    handshake = create_request(
        "handshake",
        params={
            "protocol_version": PROTOCOL_VERSION,
            "mod_version": "1.0.0",
            "game_version": "1.5",
        },
    )
    sock.sendall(serialize_message(handshake))

    # Read and discard the handshake response (pumping Qt events)
    _read_message(sock)

    return sock


def _send_message(sock: socket.socket, msg: dict) -> None:
    """Send a JSON-RPC message to the server."""
    sock.sendall(serialize_message(msg))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def event_bus() -> EventBus:
    """Return the EventBus singleton."""
    return EventBus()


@pytest.fixture()
def server(qtbot, event_bus) -> CompanionServer:  # type: ignore[no-untyped-def]
    """Create a CompanionServer on an OS-assigned port and start it."""
    srv = CompanionServer(port=0)
    assert srv.start()
    yield srv  # type: ignore[misc]
    srv.stop()


# ---------------------------------------------------------------------------
# TestServerLifecycle
# ---------------------------------------------------------------------------


class TestServerLifecycle:
    def test_start_and_stop(self, qtbot, event_bus) -> None:  # type: ignore[no-untyped-def]
        srv = CompanionServer(port=0)
        assert srv.start()
        assert srv.is_listening()
        assert srv.port() > 0
        assert not srv.has_connection()

        srv.stop()
        assert not srv.is_listening()

    def test_port_returns_bound_port(self, server) -> None:  # type: ignore[no-untyped-def]
        port = server.port()
        assert isinstance(port, int)
        assert port > 0

    def test_accepts_tcp_connection(self, qtbot, server) -> None:  # type: ignore[no-untyped-def]
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            sock.connect(("127.0.0.1", server.port()))
        finally:
            sock.close()

    def test_start_failure_emits_error(self, qtbot, event_bus) -> None:  # type: ignore[no-untyped-def]
        """Bind a port, then try to start a server on the same port."""
        blocker_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        blocker_sock.bind(("127.0.0.1", 0))
        blocker_sock.listen(1)
        taken_port = blocker_sock.getsockname()[1]

        try:
            srv = CompanionServer(port=taken_port)
            with qtbot.waitSignal(event_bus.companion_server_error, timeout=2000):
                result = srv.start()
            assert not result
        finally:
            blocker_sock.close()

    def test_stop_is_idempotent(self, qtbot, event_bus) -> None:  # type: ignore[no-untyped-def]
        srv = CompanionServer(port=0)
        srv.start()
        srv.stop()
        srv.stop()  # Should not raise


# ---------------------------------------------------------------------------
# TestHandshake
# ---------------------------------------------------------------------------


class TestHandshake:
    def test_successful_handshake_emits_connected(
        self, qtbot, server, event_bus
    ) -> None:  # type: ignore[no-untyped-def]
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)

        try:
            with qtbot.waitSignal(event_bus.companion_connected, timeout=3000) as sig:
                sock.connect(("127.0.0.1", server.port()))
                _process_events()

                handshake = create_request(
                    "handshake",
                    params={
                        "protocol_version": PROTOCOL_VERSION,
                        "mod_version": "1.0.0",
                        "game_version": "1.5",
                    },
                )
                sock.sendall(serialize_message(handshake))
                # Let the server process and respond
                qtbot.wait(100)

            # Verify the signal carried the handshake params
            params = sig.args[0]
            assert params["protocol_version"] == PROTOCOL_VERSION
            assert params["mod_version"] == "1.0.0"

            assert server.has_connection()

            # Verify we got a success response
            resp = _read_message(sock)
            assert "result" in resp
            assert resp["result"]["protocol_version"] == PROTOCOL_VERSION
        finally:
            sock.close()

    def test_version_mismatch_returns_error_and_disconnects(
        self, qtbot, server, event_bus
    ) -> None:  # type: ignore[no-untyped-def]
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)

        try:
            sock.connect(("127.0.0.1", server.port()))
            _process_events()

            bad_handshake = create_request(
                "handshake",
                params={"protocol_version": 999},
            )
            sock.sendall(serialize_message(bad_handshake))

            # Should get an error response (pump events to let server process)
            resp = _read_message(sock)
            assert "error" in resp
            assert resp["error"]["code"] == 1001

            _process_events()
            assert not server.has_connection()
        finally:
            sock.close()

    def test_second_connection_drops_first(self, qtbot, server, event_bus) -> None:  # type: ignore[no-untyped-def]
        sock1 = _connect_and_handshake(server.port())

        try:
            assert server.has_connection()

            # Second connection should drop the first
            with qtbot.waitSignal(event_bus.companion_disconnected, timeout=3000):
                sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock2.settimeout(2)
                sock2.connect(("127.0.0.1", server.port()))
                _process_events()
                qtbot.wait(50)

            # Complete handshake on second socket
            with qtbot.waitSignal(event_bus.companion_connected, timeout=3000):
                handshake = create_request(
                    "handshake",
                    params={
                        "protocol_version": PROTOCOL_VERSION,
                        "mod_version": "2.0.0",
                        "game_version": "1.5",
                    },
                )
                sock2.sendall(serialize_message(handshake))
                qtbot.wait(100)

            assert server.has_connection()
            sock2.close()
        finally:
            sock1.close()

    def test_non_handshake_first_message_disconnects(self, qtbot, server) -> None:  # type: ignore[no-untyped-def]
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)

        try:
            sock.connect(("127.0.0.1", server.port()))
            _process_events()

            msg = create_request("get.load_order", id=1)
            sock.sendall(serialize_message(msg))

            qtbot.wait(200)
            assert not server.has_connection()
        finally:
            sock.close()


# ---------------------------------------------------------------------------
# TestNotificationRouting
# ---------------------------------------------------------------------------


class TestNotificationRouting:
    def test_heartbeat_notification_emits_signal(
        self, qtbot, server, event_bus
    ) -> None:  # type: ignore[no-untyped-def]
        sock = _connect_and_handshake(server.port())

        try:
            heartbeat = create_notification(
                "heartbeat",
                params={"timestamp": 1234567890},
            )

            with qtbot.waitSignal(event_bus.companion_heartbeat, timeout=3000) as sig:
                _send_message(sock, heartbeat)
                qtbot.wait(100)

            assert sig.args[0]["timestamp"] == 1234567890
        finally:
            sock.close()

    def test_state_changed_notification_emits_signal(
        self, qtbot, server, event_bus
    ) -> None:  # type: ignore[no-untyped-def]
        sock = _connect_and_handshake(server.port())

        try:
            state_change = create_notification(
                "game.state_changed",
                params={"state": "playing"},
            )

            with qtbot.waitSignal(
                event_bus.companion_state_changed, timeout=3000
            ) as sig:
                _send_message(sock, state_change)
                qtbot.wait(100)

            assert sig.args[0] == "playing"
        finally:
            sock.close()

    def test_apply_result_notification_emits_signal(
        self, qtbot, server, event_bus
    ) -> None:  # type: ignore[no-untyped-def]
        sock = _connect_and_handshake(server.port())

        try:
            result = create_notification(
                "apply.mod_list.result",
                params={
                    "request_id": 42,
                    "accepted": True,
                    "message": "Applied successfully",
                },
            )

            with qtbot.waitSignal(
                event_bus.companion_apply_result, timeout=3000
            ) as sig:
                _send_message(sock, result)
                qtbot.wait(100)

            assert sig.args[0]["accepted"] is True
        finally:
            sock.close()


# ---------------------------------------------------------------------------
# TestSendRequest
# ---------------------------------------------------------------------------


class TestSendRequest:
    def test_send_request_returns_id_when_connected(self, qtbot, server) -> None:  # type: ignore[no-untyped-def]
        sock = _connect_and_handshake(server.port())

        try:
            req_id = server.send_request("get.load_order")
            assert req_id is not None
            assert isinstance(req_id, int)

            # The client should receive the request
            msg = _read_message(sock)
            assert msg["method"] == "get.load_order"
            assert msg["id"] == req_id
        finally:
            sock.close()

    def test_send_request_returns_none_when_disconnected(self, qtbot, server) -> None:  # type: ignore[no-untyped-def]
        req_id = server.send_request("get.load_order")
        assert req_id is None

    def test_send_notification_returns_true_when_connected(self, qtbot, server) -> None:  # type: ignore[no-untyped-def]
        sock = _connect_and_handshake(server.port())

        try:
            result = server.send_notification("some.event", {"key": "value"})
            assert result is True

            msg = _read_message(sock)
            assert msg["method"] == "some.event"
            assert "id" not in msg
        finally:
            sock.close()

    def test_send_notification_returns_false_when_disconnected(
        self, qtbot, server
    ) -> None:  # type: ignore[no-untyped-def]
        result = server.send_notification("some.event")
        assert result is False


# ---------------------------------------------------------------------------
# TestResponseRouting
# ---------------------------------------------------------------------------


class TestResponseRouting:
    def test_response_to_pending_request_emits_signal(
        self, qtbot, server, event_bus
    ) -> None:  # type: ignore[no-untyped-def]
        sock = _connect_and_handshake(server.port())

        try:
            req_id = server.send_request("get.load_order")
            assert req_id is not None

            # Read the request on the client side
            _read_message(sock)

            # Send a response back
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"mods": ["Core", "HugsLib"]},
            }

            with qtbot.waitSignal(
                event_bus.companion_load_order_received, timeout=3000
            ) as sig:
                _send_message(sock, response)
                qtbot.wait(100)

            assert sig.args[0]["mods"] == ["Core", "HugsLib"]
        finally:
            sock.close()
