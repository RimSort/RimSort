"""Spawn/stop the local MCP HTTP subprocess from the RimSort GUI."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

from loguru import logger

_proc: subprocess.Popen[Any] | None = None
_running_key: tuple[object, ...] | None = None


def is_compiled() -> bool:
    if getattr(sys, "frozen", False):
        return True
    main = sys.modules.get("__main__")
    return main is not None and hasattr(main, "__compiled__")


def launch_args(port: int) -> list[str]:
    if is_compiled():
        return [sys.executable, "--mcp", "--http", "--port", str(port)]
    return [sys.executable, "-m", "app", "--mcp", "--http", "--port", str(port)]


def stop_mcp_subprocess() -> None:
    global _proc, _running_key
    proc = _proc
    _proc = None
    _running_key = None
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def sync_mcp_subprocess(settings: Any) -> None:
    global _proc, _running_key
    enabled = bool(getattr(settings, "mcp_server_enabled", False))
    port = int(getattr(settings, "mcp_server_port", 17342) or 17342)
    token = str(getattr(settings, "mcp_server_token", "") or "")
    instance = str(getattr(settings, "current_instance", "") or "")
    key = (enabled, port, token, instance)
    if not enabled:
        stop_mcp_subprocess()
        return
    if _proc is not None and _proc.poll() is None and key == _running_key:
        return

    stop_mcp_subprocess()
    env = os.environ.copy()
    env["RIMSORT_MCP_PORT"] = str(port)
    if token:
        env["RIMSORT_MCP_TOKEN"] = token
    else:
        env.pop("RIMSORT_MCP_TOKEN", None)
    if instance:
        env["RIMSORT_INSTANCE"] = instance

    kwargs: dict[str, Any] = {
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    cmd = launch_args(port)
    logger.info("Starting MCP HTTP subprocess: {}", " ".join(cmd))
    _proc = subprocess.Popen(cmd, **kwargs)
    _running_key = key
