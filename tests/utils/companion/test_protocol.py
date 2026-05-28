"""Tests for the JSON-RPC 2.0 protocol layer."""

import threading

import pytest

from app.utils.companion.protocol import (
    ERR_ACTION_BUSY,
    ERR_ACTION_DECLINED,
    ERR_ACTION_FAILED,
    ERR_MOD_NOT_FOUND,
    ERR_NOT_READY,
    ERR_VERSION_MISMATCH,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_protocol_version(self) -> None:
        assert PROTOCOL_VERSION == 1

    def test_standard_error_codes(self) -> None:
        assert PARSE_ERROR == -32700
        assert INVALID_REQUEST == -32600
        assert METHOD_NOT_FOUND == -32601

    def test_application_error_codes(self) -> None:
        assert ERR_VERSION_MISMATCH == 1001
        assert ERR_MOD_NOT_FOUND == 1002
        assert ERR_ACTION_DECLINED == 1003
        assert ERR_ACTION_FAILED == 1004
        assert ERR_ACTION_BUSY == 1005
        assert ERR_NOT_READY == 1006


# ---------------------------------------------------------------------------
# JsonRpcError
# ---------------------------------------------------------------------------


class TestJsonRpcError:
    def test_has_code_and_message(self) -> None:
        err = JsonRpcError(code=-32700, message="Parse error")
        assert err.code == -32700
        assert err.message == "Parse error"

    def test_is_exception(self) -> None:
        err = JsonRpcError(code=-32600, message="Invalid request")
        assert isinstance(err, Exception)

    def test_str_representation(self) -> None:
        err = JsonRpcError(code=-32700, message="Parse error")
        s = str(err)
        assert "-32700" in s
        assert "Parse error" in s


# ---------------------------------------------------------------------------
# create_request
# ---------------------------------------------------------------------------


class TestCreateRequest:
    def test_basic_request(self) -> None:
        msg = create_request("hello", params={"name": "world"}, id=1)
        assert msg["jsonrpc"] == "2.0"
        assert msg["method"] == "hello"
        assert msg["params"] == {"name": "world"}
        assert msg["id"] == 1

    def test_no_params(self) -> None:
        msg = create_request("ping", id=42)
        assert msg["method"] == "ping"
        assert "params" not in msg
        assert msg["id"] == 42

    def test_auto_increment_id(self) -> None:
        msg1 = create_request("a")
        msg2 = create_request("b")
        assert isinstance(msg1["id"], int)
        assert isinstance(msg2["id"], int)
        assert msg2["id"] > msg1["id"]

    def test_explicit_id_does_not_affect_counter(self) -> None:
        msg1 = create_request("a")
        auto_id = msg1["id"]
        _ = create_request("b", id=99999)
        msg3 = create_request("c")
        assert msg3["id"] == auto_id + 1

    def test_list_params(self) -> None:
        msg = create_request("add", params=[1, 2], id=1)
        assert msg["params"] == [1, 2]


# ---------------------------------------------------------------------------
# create_notification
# ---------------------------------------------------------------------------


class TestCreateNotification:
    def test_basic_notification(self) -> None:
        msg = create_notification("update", params={"status": "ready"})
        assert msg["jsonrpc"] == "2.0"
        assert msg["method"] == "update"
        assert msg["params"] == {"status": "ready"}
        assert "id" not in msg

    def test_no_params(self) -> None:
        msg = create_notification("ping")
        assert msg["method"] == "ping"
        assert "params" not in msg
        assert "id" not in msg


# ---------------------------------------------------------------------------
# create_response
# ---------------------------------------------------------------------------


class TestCreateResponse:
    def test_success_response(self) -> None:
        msg = create_response(id=1, result={"ok": True})
        assert msg["jsonrpc"] == "2.0"
        assert msg["id"] == 1
        assert msg["result"] == {"ok": True}
        assert "error" not in msg

    def test_null_result(self) -> None:
        msg = create_response(id=1, result=None)
        assert msg["result"] is None

    def test_string_id(self) -> None:
        msg = create_response(id="abc", result=42)
        assert msg["id"] == "abc"
        assert msg["result"] == 42


# ---------------------------------------------------------------------------
# create_error_response
# ---------------------------------------------------------------------------


class TestCreateErrorResponse:
    def test_basic_error(self) -> None:
        msg = create_error_response(id=1, code=-32600, message="Invalid request")
        assert msg["jsonrpc"] == "2.0"
        assert msg["id"] == 1
        assert msg["error"]["code"] == -32600
        assert msg["error"]["message"] == "Invalid request"
        assert "result" not in msg

    def test_with_data(self) -> None:
        msg = create_error_response(
            id=2, code=-32700, message="Parse error", data={"detail": "unexpected EOF"}
        )
        assert msg["error"]["data"] == {"detail": "unexpected EOF"}

    def test_without_data(self) -> None:
        msg = create_error_response(id=3, code=-32601, message="Method not found")
        assert "data" not in msg["error"]

    def test_null_id_for_parse_errors(self) -> None:
        msg = create_error_response(id=None, code=-32700, message="Parse error")
        assert msg["id"] is None


# ---------------------------------------------------------------------------
# parse_message
# ---------------------------------------------------------------------------


class TestParseMessage:
    def test_parse_request(self) -> None:
        raw = '{"jsonrpc":"2.0","method":"hello","params":{},"id":1}'
        msg = parse_message(raw)
        assert msg["method"] == "hello"
        assert msg["id"] == 1

    def test_parse_notification(self) -> None:
        raw = '{"jsonrpc":"2.0","method":"update","params":{"x":1}}'
        msg = parse_message(raw)
        assert msg["method"] == "update"
        assert "id" not in msg

    def test_parse_success_response(self) -> None:
        raw = '{"jsonrpc":"2.0","result":42,"id":1}'
        msg = parse_message(raw)
        assert msg["result"] == 42
        assert msg["id"] == 1

    def test_parse_error_response(self) -> None:
        raw = '{"jsonrpc":"2.0","error":{"code":-32600,"message":"bad"},"id":1}'
        msg = parse_message(raw)
        assert msg["error"]["code"] == -32600

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(JsonRpcError) as exc_info:
            parse_message("not json at all")
        assert exc_info.value.code == PARSE_ERROR

    def test_missing_jsonrpc_field_raises(self) -> None:
        with pytest.raises(JsonRpcError) as exc_info:
            parse_message('{"method":"hello","id":1}')
        assert exc_info.value.code == INVALID_REQUEST

    def test_wrong_version_raises(self) -> None:
        with pytest.raises(JsonRpcError) as exc_info:
            parse_message('{"jsonrpc":"1.0","method":"hello","id":1}')
        assert exc_info.value.code == INVALID_REQUEST

    def test_tolerates_unknown_fields(self) -> None:
        raw = '{"jsonrpc":"2.0","method":"hello","id":1,"extra":"ignored"}'
        msg = parse_message(raw)
        assert msg["method"] == "hello"
        assert msg["extra"] == "ignored"

    def test_not_a_dict_raises(self) -> None:
        with pytest.raises(JsonRpcError) as exc_info:
            parse_message("[1, 2, 3]")
        assert exc_info.value.code == INVALID_REQUEST

    def test_strips_whitespace(self) -> None:
        raw = '  {"jsonrpc":"2.0","method":"ping","id":1}  \n'
        msg = parse_message(raw)
        assert msg["method"] == "ping"


# ---------------------------------------------------------------------------
# serialize_message
# ---------------------------------------------------------------------------


class TestSerializeMessage:
    def test_produces_bytes(self) -> None:
        msg = create_request("ping", id=1)
        data = serialize_message(msg)
        assert isinstance(data, bytes)

    def test_newline_terminated(self) -> None:
        msg = create_request("ping", id=1)
        data = serialize_message(msg)
        assert data.endswith(b"\n")

    def test_valid_utf8(self) -> None:
        msg = create_request("ping", params={"emoji": "❤"}, id=1)
        data = serialize_message(msg)
        decoded = data.decode("utf-8")
        assert "❤" in decoded

    def test_roundtrip(self) -> None:
        original = create_request("hello", params={"a": 1}, id=1)
        data = serialize_message(original)
        parsed = parse_message(data.decode("utf-8"))
        assert parsed == original


# ---------------------------------------------------------------------------
# Type helpers
# ---------------------------------------------------------------------------


class TestTypeHelpers:
    def test_is_request(self) -> None:
        assert is_request(create_request("hello", id=1))
        assert not is_request(create_notification("hello"))
        assert not is_request(create_response(id=1, result=None))
        assert not is_request(create_error_response(id=1, code=-1, message="err"))

    def test_is_notification(self) -> None:
        assert is_notification(create_notification("hello"))
        assert not is_notification(create_request("hello", id=1))
        assert not is_notification(create_response(id=1, result=None))

    def test_is_response(self) -> None:
        assert is_response(create_response(id=1, result=None))
        assert is_response(create_error_response(id=1, code=-1, message="err"))
        assert not is_response(create_request("hello", id=1))
        assert not is_response(create_notification("hello"))


# ---------------------------------------------------------------------------
# Thread safety of auto-increment ID
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_id_generation(self) -> None:
        ids: list[int] = []
        lock = threading.Lock()

        def generate_ids(count: int) -> None:
            local_ids = []
            for _ in range(count):
                msg = create_request("test")
                local_ids.append(msg["id"])
            with lock:
                ids.extend(local_ids)

        threads = [
            threading.Thread(target=generate_ids, args=(100,)) for _ in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(ids) == 1000
        assert len(set(ids)) == 1000  # All unique
