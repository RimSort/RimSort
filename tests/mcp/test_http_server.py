import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread

from app.mcp.server import _McpHttpHandler, dispatch


def test_http_initialize_and_tools_list() -> None:
    _McpHttpHandler.token = "tok"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _McpHttpHandler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    try:
        conn = HTTPConnection(host, port, timeout=5)
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
            }
        )
        conn.request(
            "POST",
            "/mcp",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer tok",
            },
        )
        resp = json.loads(conn.getresponse().read())
        assert resp["result"]["serverInfo"]["name"] == "rimsort-mcp"

        conn.request(
            "POST",
            "/mcp",
            body=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer tok",
            },
        )
        listed = json.loads(conn.getresponse().read())
        names = [t["name"] for t in listed["result"]["tools"]]
        assert "get_mod_info" in names

        conn.request("POST", "/mcp", body="{}", headers={"Content-Type": "application/json"})
        assert conn.getresponse().status == 401
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_dispatch_unknown_method() -> None:
    reply = dispatch({"jsonrpc": "2.0", "id": 9, "method": "nope"})
    assert reply is not None
    assert reply["error"]["code"] == -32601
