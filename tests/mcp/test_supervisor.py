from unittest.mock import MagicMock, patch

from app.mcp.server import dispatch
from app.mcp.supervisor import launch_args, stop_mcp_subprocess, sync_mcp_subprocess


def test_launch_args_source() -> None:
    with patch("app.mcp.supervisor.is_compiled", return_value=False):
        args = launch_args(17342)
    assert args[1:4] == ["-m", "app", "--mcp"]
    assert "--http" in args
    assert "17342" in args


def test_launch_args_compiled() -> None:
    with (
        patch("app.mcp.supervisor.is_compiled", return_value=True),
        patch("app.mcp.supervisor.sys") as mock_sys,
    ):
        mock_sys.executable = "C:\\RimSort\\RimSort.exe"
        args = launch_args(19000)
    assert args[0].endswith("RimSort.exe")
    assert args[1:] == ["--mcp", "--http", "--port", "19000"]


def test_dispatch_tools_list() -> None:
    reply = dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert reply is not None
    names = [t["name"] for t in reply["result"]["tools"]]
    assert "list_active_mods" in names
    assert "list_installed_mods" in names
    assert "describe_mod" in names
    assert "search_workshop_mods" in names
    assert "search_steam_workshop" in names
    assert "validate_workshop_ids" in names
    assert "queue_sort_mods" in names
    assert len(names) >= 15


def test_dispatch_notification_has_no_reply() -> None:
    assert dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_sync_disabled_stops_process() -> None:
    settings = MagicMock()
    settings.mcp_server_enabled = False
    settings.mcp_server_port = 17342
    settings.mcp_server_token = ""
    settings.current_instance = "Default"
    with patch("app.mcp.supervisor.subprocess.Popen") as popen:
        sync_mcp_subprocess(settings)
        popen.assert_not_called()
    stop_mcp_subprocess()


def test_sync_enabled_spawns_http_server() -> None:
    settings = MagicMock()
    settings.mcp_server_enabled = True
    settings.mcp_server_port = 17342
    settings.mcp_server_token = "secret"
    settings.current_instance = "Default"
    fake_proc = MagicMock()
    fake_proc.poll.return_value = None
    with (
        patch("app.mcp.supervisor.is_compiled", return_value=False),
        patch("app.mcp.supervisor.subprocess.Popen", return_value=fake_proc) as popen,
    ):
        stop_mcp_subprocess()
        sync_mcp_subprocess(settings)
        sync_mcp_subprocess(settings)
        assert popen.call_count == 1
        cmd = popen.call_args[0][0]
        assert "--http" in cmd
        env = popen.call_args.kwargs["env"]
        assert env["RIMSORT_MCP_TOKEN"] == "secret"
        assert env["RIMSORT_INSTANCE"] == "Default"
    stop_mcp_subprocess()
