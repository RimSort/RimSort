"""File-based command queue between MCP subprocess and RimSort GUI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.utils.app_info import AppInfo

GUI_ALIVE_NAME = "mcp_gui_alive"
COMMANDS_NAME = "mcp_commands.jsonl"


def _storage() -> Path:
    return Path(AppInfo().app_storage_folder)


def gui_alive_path() -> Path:
    return _storage() / GUI_ALIVE_NAME


def commands_path() -> Path:
    return _storage() / COMMANDS_NAME


def mark_gui_alive() -> None:
    path = gui_alive_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()), encoding="utf-8")


def clear_gui_alive() -> None:
    try:
        gui_alive_path().unlink(missing_ok=True)
    except OSError:
        pass


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def gui_is_alive() -> bool:
    path = gui_alive_path()
    if not path.exists():
        return False
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return False
    return _pid_is_alive(pid)


def enqueue(command: dict[str, Any]) -> None:
    path = commands_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(command, ensure_ascii=False) + "\n")


def drain() -> list[dict[str, Any]]:
    path = commands_path()
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
        path.unlink(missing_ok=True)
    except OSError:
        return []
    commands: list[dict[str, Any]] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            commands.append(payload)
    return commands


def require_gui_for_mutation() -> dict[str, Any] | None:
    if gui_is_alive():
        return None
    return {"ok": False, "error": "RimSort GUI is not running"}
