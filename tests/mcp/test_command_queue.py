from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.mcp import command_queue, tools


@pytest.fixture
def queue_storage(tmp_path: Path):
    storage = tmp_path / "storage"
    storage.mkdir()
    with patch("app.mcp.command_queue.AppInfo") as mock_info:
        mock_info.return_value.app_storage_folder = storage
        yield storage


def test_enqueue_and_drain(queue_storage: Path) -> None:
    command_queue.enqueue({"type": "sort"})
    command_queue.enqueue({"type": "save"})
    drained = command_queue.drain()
    assert drained == [{"type": "sort"}, {"type": "save"}]
    assert command_queue.drain() == []
    assert not (queue_storage / command_queue.COMMANDS_NAME).exists()


def test_gui_not_running_blocks_queue_tools(queue_storage: Path) -> None:
    result = tools.call_tool("queue_sort_mods", {})
    assert result == {"ok": False, "error": "RimSort GUI is not running"}
    assert not (queue_storage / command_queue.COMMANDS_NAME).exists()


def test_queue_download_when_gui_alive(queue_storage: Path) -> None:
    alive = queue_storage / command_queue.GUI_ALIVE_NAME
    alive.write_text(str(__import__("os").getpid()), encoding="utf-8")
    with patch(
        "app.mcp.tools.validate_publishedfileids",
        return_value={
            "valid": ["12345", "67890"],
            "invalid": [],
            "valid_details": [],
        },
    ):
        result = tools.call_tool(
            "queue_download", {"publishedfileids": ["12345", "67890"]}
        )
    assert result["ok"] is True
    assert result["count"] == 2
    lines = (queue_storage / command_queue.COMMANDS_NAME).read_text(encoding="utf-8")
    payload = json.loads(lines.strip())
    assert payload["type"] == "steamcmd_download"
    assert payload["publishedfileids"] == ["12345", "67890"]


def test_drain_app_controller_emits_event_bus() -> None:
    from app.controllers import app_controller

    mock_bus = MagicMock()
    with (
        patch("app.controllers.app_controller.drain") as mock_drain,
        patch("app.controllers.app_controller.EventBus", return_value=mock_bus),
    ):
        mock_drain.return_value = [
            {"type": "steamcmd_download", "publishedfileids": ["1"]},
            {"type": "sort"},
            {"type": "save"},
            {"type": "run_game"},
        ]
        app_controller.AppController._drain_mcp_commands(object())
        mock_bus.do_steamcmd_download.emit.assert_called_once_with(["1"])
        mock_bus.do_sort_active_mods_list.emit.assert_called_once()
        mock_bus.do_save_active_mods_list.emit.assert_called_once()
        mock_bus.do_run_game.emit.assert_called_once()
