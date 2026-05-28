"""JSON-RPC 2.0 protocol layer for companion mod communication.

Handles message creation, parsing, and serialization per the
JSON-RPC 2.0 specification (https://www.jsonrpc.org/specification).
"""

import json
import threading
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROTOCOL_VERSION = 1

# Standard JSON-RPC 2.0 error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601

# Application-specific error codes
ERR_VERSION_MISMATCH = 1001
ERR_MOD_NOT_FOUND = 1002
ERR_ACTION_DECLINED = 1003
ERR_ACTION_FAILED = 1004
ERR_ACTION_BUSY = 1005
ERR_NOT_READY = 1006

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class JsonRpcError(Exception):
    """Raised when a JSON-RPC message is malformed or violates the spec."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Thread-safe auto-incrementing ID generator
# ---------------------------------------------------------------------------

_id_counter = 0
_id_lock = threading.Lock()


def _next_id() -> int:
    global _id_counter
    with _id_lock:
        _id_counter += 1
        return _id_counter


# ---------------------------------------------------------------------------
# Message creation
# ---------------------------------------------------------------------------


def create_request(
    method: str,
    params: dict[str, Any] | list[Any] | None = None,
    id: int | str | None = None,
) -> dict[str, Any]:
    """Create a JSON-RPC 2.0 request message.

    :param method: The RPC method name
    :param params: Optional positional or named parameters
    :param id: Request ID. Auto-generated if not provided.
    :return: A dict representing the JSON-RPC request
    """
    msg: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
    }
    if params is not None:
        msg["params"] = params
    msg["id"] = id if id is not None else _next_id()
    return msg


def create_notification(
    method: str,
    params: dict[str, Any] | list[Any] | None = None,
) -> dict[str, Any]:
    """Create a JSON-RPC 2.0 notification (request with no id).

    :param method: The RPC method name
    :param params: Optional positional or named parameters
    :return: A dict representing the JSON-RPC notification
    """
    msg: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
    }
    if params is not None:
        msg["params"] = params
    return msg


def create_response(id: int | str | None, result: Any) -> dict[str, Any]:
    """Create a JSON-RPC 2.0 success response.

    :param id: The request ID this response corresponds to
    :param result: The result value
    :return: A dict representing the JSON-RPC response
    """
    return {
        "jsonrpc": "2.0",
        "id": id,
        "result": result,
    }


def create_error_response(
    id: int | str | None,
    code: int,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    """Create a JSON-RPC 2.0 error response.

    :param id: The request ID this response corresponds to (None for parse errors)
    :param code: Error code
    :param message: Human-readable error message
    :param data: Optional additional error data
    :return: A dict representing the JSON-RPC error response
    """
    error: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": id,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_message(raw: str | bytes) -> dict[str, Any]:
    """Parse a raw JSON string into a validated JSON-RPC 2.0 message.

    :param raw: Raw JSON string or bytes
    :return: Parsed message dict
    :raises JsonRpcError: If the message is invalid JSON or violates the spec
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    raw = raw.strip()

    try:
        msg = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise JsonRpcError(code=PARSE_ERROR, message=f"Invalid JSON: {exc}") from exc

    if not isinstance(msg, dict):
        raise JsonRpcError(
            code=INVALID_REQUEST, message="Message must be a JSON object"
        )

    if "jsonrpc" not in msg:
        raise JsonRpcError(code=INVALID_REQUEST, message='Missing "jsonrpc" field')

    if msg["jsonrpc"] != "2.0":
        raise JsonRpcError(
            code=INVALID_REQUEST,
            message=f"Unsupported JSON-RPC version: {msg['jsonrpc']}",
        )

    return msg


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_message(msg: dict[str, Any]) -> bytes:
    """Serialize a JSON-RPC message to newline-terminated UTF-8 bytes.

    :param msg: A JSON-RPC message dict
    :return: UTF-8 encoded bytes ending with a newline
    """
    return (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Type helpers
# ---------------------------------------------------------------------------


def is_request(msg: dict[str, Any]) -> bool:
    """Return True if the message is a JSON-RPC request (has method and id)."""
    return "method" in msg and "id" in msg


def is_notification(msg: dict[str, Any]) -> bool:
    """Return True if the message is a JSON-RPC notification (has method, no id)."""
    return "method" in msg and "id" not in msg


def is_response(msg: dict[str, Any]) -> bool:
    """Return True if the message is a JSON-RPC response (has result or error, and id)."""
    return ("result" in msg or "error" in msg) and "id" in msg
