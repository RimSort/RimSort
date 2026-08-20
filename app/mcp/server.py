"""Minimal MCP JSON-RPC server (stdio and localhost HTTP)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from loguru import logger

from app.mcp import tools

PROTOCOL_VERSION = "2024-11-05"


def dispatch(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC message. None means a notification with no reply."""
    msg_id = msg.get("id")
    method = msg.get("method", "")
    params = msg.get("params") or {}

    if method == "initialize":
        client_version = ""
        if isinstance(params, dict):
            client_version = str(params.get("protocolVersion") or "")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": client_version or PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                    "serverInfo": {"name": "rimsort-mcp", "version": "1.2.0"},
            },
        }

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": tools.list_tools()},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments") or {}
        try:
            content = tools.call_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {"type": "text", "text": json.dumps(content, ensure_ascii=False)}
                    ],
                    "isError": False,
                },
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            }

    if msg_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return None


def _send_stdio(obj: dict[str, Any]) -> None:
    payload = json.dumps(obj, ensure_ascii=False) + "\n"
    sys.stdout.buffer.write(payload.encode("utf-8"))
    sys.stdout.buffer.flush()


def _read_stdio_message() -> dict[str, Any] | None:
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    decoded = line.decode("utf-8", errors="replace").strip()
    if not decoded:
        return _read_stdio_message()
    if decoded.lower().startswith("content-length:"):
        length = int(decoded.split(":", 1)[1].strip() or "0")
        while True:
            header_line = sys.stdin.buffer.readline()
            if not header_line or header_line in (b"\r\n", b"\n"):
                break
        if length <= 0:
            return None
        raw = sys.stdin.buffer.read(length)
        return json.loads(raw.decode("utf-8"))
    return json.loads(decoded)


def _serve_stdio() -> None:
    while True:
        msg = _read_stdio_message()
        if msg is None:
            break
        reply = dispatch(msg)
        if reply is not None:
            _send_stdio(reply)


def _authorized(handler: BaseHTTPRequestHandler, token: str) -> bool:
    if not token:
        return True
    auth = handler.headers.get("Authorization", "")
    if auth == f"Bearer {token}":
        return True
    return handler.headers.get("X-RimSort-Token", "") == token


class _McpHttpHandler(BaseHTTPRequestHandler):
    token = ""

    def log_message(self, fmt: str, *args: object) -> None:
        logger.debug("mcp-http {}", fmt % args)

    def _send_bytes(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        if not _authorized(self, self.token):
            self._send_bytes(401, b"unauthorized", "text/plain")
            return
        if self.path.rstrip("/") in ("/health", ""):
            self._send_bytes(200, b'{"ok":true}', "application/json")
            return
        body = b"event: ping\ndata: {}\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if not _authorized(self, self.token):
            self._send_bytes(401, b"unauthorized", "text/plain")
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload: Any = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            err = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
            blob = json.dumps(err).encode("utf-8")
            self._send_bytes(400, blob, "application/json")
            return

        if isinstance(payload, list):
            replies = [r for r in (dispatch(m) for m in payload) if r is not None]
            if not replies:
                self.send_response(202)
                self.end_headers()
                return
            blob = json.dumps(replies).encode("utf-8")
        elif isinstance(payload, dict):
            reply = dispatch(payload)
            if reply is None:
                self.send_response(202)
                self.end_headers()
                return
            blob = json.dumps(reply).encode("utf-8")
        else:
            blob = b'{"jsonrpc":"2.0","error":{"code":-32600,"message":"Invalid Request"}}'
        self._send_bytes(200, blob, "application/json")


def serve_http(host: str, port: int, token: str) -> None:
    _McpHttpHandler.token = token
    httpd = ThreadingHTTPServer((host, port), _McpHttpHandler)
    httpd.allow_reuse_address = True
    logger.info("MCP HTTP listening on http://{}:{}/mcp", host, port)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="RimSort MCP server")
    parser.add_argument("--instance", default=None, help="RimSort instance name")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve Streamable HTTP on localhost instead of stdio",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("RIMSORT_MCP_PORT", "17342")),
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("RIMSORT_MCP_TOKEN", ""),
    )
    args = parser.parse_args()
    if args.instance:
        os.environ["RIMSORT_INSTANCE"] = args.instance
    if args.http:
        serve_http(args.host, args.port, args.token)
        return
    _serve_stdio()


if __name__ == "__main__":
    main()
