"""Tests for MCP server registration, tool schemas and the stdio entrypoint."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from collections.abc import Generator
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import anyio
import pytest
from loguru import logger
from mcp_types import CallToolResult, Tool

from app.mcp.core import RimSortMcpCore
from app.mcp.server import SERVER_NAME, build_server
from app.models.instance import Instance
from app.models.settings import Settings
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from tests.game_layout_fixtures import GameInstall
from tests.mcp.conftest import build_core, write_mod, write_mods_config

EXPECTED_TOOLS = {
    "get_instance_status",
    "search_installed_mods",
    "get_mod_details",
    "get_active_modlist",
    "analyze_and_sort_modlist",
    "apply_active_modlist",
    "refresh_metadata_cache",
}


def _list_tools(core: RimSortMcpCore) -> list[Tool]:
    server = build_server(core)
    return anyio.run(server.list_tools)


def _call(
    core: RimSortMcpCore, name: str, arguments: dict[str, object]
) -> CallToolResult:
    server = build_server(core)
    result = anyio.run(server.call_tool, name, arguments)
    assert isinstance(result, CallToolResult)
    return result


def _payload(result: CallToolResult) -> dict[str, object]:
    """Decode the JSON payload a tool returned as text content."""
    block = result.content[0]
    text = getattr(block, "text", None)
    assert isinstance(text, str), f"expected text content, got {type(block).__name__}"
    payload = json.loads(text)
    assert isinstance(payload, dict)
    return payload


def test_server_registers_exactly_the_documented_tools(
    mcp_core: RimSortMcpCore,
) -> None:
    tools = _list_tools(mcp_core)

    assert {tool.name for tool in tools} == EXPECTED_TOOLS
    assert SERVER_NAME == "RimSort"


def test_every_tool_documents_itself_and_types_its_arguments(
    mcp_core: RimSortMcpCore,
) -> None:
    for tool in _list_tools(mcp_core):
        assert tool.description, f"{tool.name} has no description"
        schema = tool.input_schema
        assert schema["type"] == "object"
        for prop in schema.get("properties", {}).values():
            assert prop.get("type") or prop.get("anyOf"), prop


def test_search_tool_schema_exposes_documented_parameters(
    mcp_core: RimSortMcpCore,
) -> None:
    tools = {tool.name: tool for tool in _list_tools(mcp_core)}

    search = tools["search_installed_mods"].input_schema
    assert set(search["properties"]) == {
        "query",
        "supported_version",
        "active_only",
        "include_description",
    }
    analyze = tools["analyze_and_sort_modlist"].input_schema
    assert analyze["required"] == ["package_ids"]


def test_tool_call_returns_json_payload(mcp_core: RimSortMcpCore) -> None:
    result = _call(mcp_core, "get_instance_status", {})

    assert result.is_error is False
    payload = _payload(result)
    assert payload["instance_name"] == mcp_core.settings.current_instance
    assert "paths" in payload


def test_tool_failures_surface_as_structured_errors(
    mcp_core: RimSortMcpCore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A raised exception must not corrupt the JSON-RPC session."""

    def boom() -> dict[str, object]:
        raise RuntimeError("metadata exploded")

    monkeypatch.setattr(mcp_core, "get_instance_status", boom)
    result = _call(mcp_core, "get_instance_status", {})
    payload = _payload(result)

    assert result.is_error is False
    assert payload["error"] == "RuntimeError: metadata exploded"
    assert payload["tool"] == "get_instance_status"


def test_apply_tool_reports_structured_refusal(
    mcp_core: RimSortMcpCore, game_install: GameInstall
) -> None:
    write_mod(game_install.mods_path, "Harmony", "brrainz.harmony")
    core = build_core(mcp_core.settings)

    result = _call(core, "apply_active_modlist", {"package_ids": ["nope.missing"]})
    payload = _payload(result)

    assert payload["saved"] is False
    errors = payload["errors"]
    assert isinstance(errors, list)
    assert errors[0]["type"] == "unresolved_package_id"


def _dig(frame: dict[str, object], *keys: str) -> object:
    """Walk nested JSON-RPC response dicts in a type-safe way."""
    current: object = frame
    for key in keys:
        assert isinstance(current, dict), f"expected object at {key}"
        current = current[key]
    return current


def _decode_content(frame: dict[str, object]) -> dict[str, object]:
    """Decode the JSON payload from a ``tools/call`` response frame."""
    content = _dig(frame, "result", "content")
    assert isinstance(content, list) and content
    text = content[0]["text"]
    payload = json.loads(text)
    assert isinstance(payload, dict)
    return payload


# ---- stdio entrypoint ----


def _handshake() -> list[dict[str, object]]:
    """The JSON-RPC preamble every client sends before using tools."""
    return [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    ]


def _tools_call(request_id: int, name: str) -> dict[str, object]:
    """A ``tools/call`` request frame."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": {}},
    }


def _run_mcp_session(
    env: dict[str, str], requests: list[dict[str, object]]
) -> tuple[list[dict[str, object]], str, int]:
    """Drive a real stdio MCP session the way a client does.

    The session is kept open until every expected response has been read;
    closing stdin earlier lets the transport shut down before writing a
    response, which is a property of one-shot pipes rather than of the server.

    :param env: Environment for the server process
    :param requests: JSON-RPC requests, including notifications
    :return: ``(responses, stderr, exit code)``
    """
    expected = len([request for request in requests if "id" in request])
    process = subprocess.Popen(
        [sys.executable, "-m", "app", "--mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    responses: list[dict[str, object]] = []
    response_queue: queue.Queue[dict[str, object]] = queue.Queue()

    def pump() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            if line.strip():
                response_queue.put(json.loads(line))

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    try:
        assert process.stdin is not None
        for request in requests:
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
        # Wait for the expected responses rather than for EOF: the process keeps
        # stdout open until it exits, and it only exits once stdin closes.
        for _ in range(expected):
            responses.append(response_queue.get(timeout=240))
    finally:
        if process.stdin is not None:
            process.stdin.close()
        process.wait(timeout=240)
        reader.join(timeout=30)
    stderr = process.stderr.read() if process.stderr is not None else ""
    return responses, stderr, process.returncode


def _write_dev_settings(dev_dir: Path, install: GameInstall, config: Path) -> None:
    data = dev_dir / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "settings.json").write_text(
        json.dumps(
            {
                "current_instance": "Default",
                "instances": {
                    "Default": {
                        "name": "Default",
                        "game_folder": str(install.launch_location),
                        "config_folder": str(config),
                        "local_folder": str(install.mods_path),
                        "workshop_folder": "",
                        "steamcmd_install_path": str(data / "instances" / "Default"),
                    }
                },
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def dev_env(
    tmp_path: Path, game_install: GameInstall, config_folder: Path
) -> dict[str, str]:
    write_mod(game_install.mods_path, "Harmony", "brrainz.harmony")
    write_mods_config(config_folder, ["ludeon.rimworld"])
    dev_dir = tmp_path / "dev"
    _write_dev_settings(dev_dir, game_install, config_folder)
    return dict(
        os.environ,
        RIMSORT_DEV="1",
        RIMSORT_DEV_DIR=str(dev_dir),
        QT_QPA_PLATFORM="offscreen",
    )


def test_mcp_stdio_session_keeps_stdout_json_only(dev_env: dict[str, str]) -> None:
    """Every stdout line must parse as JSON-RPC: logging never leaks there."""
    requests: list[dict[str, object]] = [
        *_handshake(),
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        _tools_call(3, "get_instance_status"),
    ]
    responses, stderr, returncode = _run_mcp_session(dev_env, requests)

    assert returncode == 0, stderr[-4000:]
    assert [frame["id"] for frame in responses] == [1, 2, 3]
    tools_listed = _dig(responses[1], "result", "tools")
    assert isinstance(tools_listed, list)
    assert {tool["name"] for tool in tools_listed} == EXPECTED_TOOLS
    payload = _decode_content(responses[2])
    assert payload["instance_name"] == "Default"
    # Diagnostics must reach stderr so they never interleave with frames.
    assert "Starting RimSort MCP server" in stderr


def test_instance_flag_rejects_unknown_instance(
    tmp_path: Path, game_install: GameInstall, config_folder: Path
) -> None:
    dev_dir = tmp_path / "dev"
    _write_dev_settings(dev_dir, game_install, config_folder)
    env = dict(
        os.environ,
        RIMSORT_DEV="1",
        RIMSORT_DEV_DIR=str(dev_dir),
        QT_QPA_PLATFORM="offscreen",
    )

    completed = subprocess.run(
        [sys.executable, "-m", "app", "--mcp", "--instance", "Nonexistent"],
        input="",
        capture_output=True,
        text=True,
        env=env,
        timeout=240,
        cwd=str(Path(__file__).resolve().parents[2]),
        check=False,
    )

    assert completed.returncode == 2
    assert "Nonexistent" in completed.stderr
    assert completed.stdout == ""


def test_instance_flag_requires_a_value(dev_env: dict[str, str]) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "app", "--mcp", "--instance"],
        input="",
        capture_output=True,
        text=True,
        env=dev_env,
        timeout=240,
        cwd=str(Path(__file__).resolve().parents[2]),
        check=False,
    )

    assert completed.returncode == 2
    assert "--instance requires a name" in completed.stderr
    assert completed.stdout == ""


def test_settings_without_configured_paths_still_serves(
    dev_env: dict[str, str],
) -> None:
    """A fresh install has no game paths; the server must still answer tools."""
    requests: list[dict[str, object]] = [
        *_handshake(),
        _tools_call(2, "get_active_modlist"),
    ]
    env = dict(dev_env, RIMSORT_DEV_DIR=dev_env["RIMSORT_DEV_DIR"] + "-empty")
    responses, stderr, returncode = _run_mcp_session(env, requests)

    assert returncode == 0, stderr[-4000:]
    payload = _decode_content(responses[1])
    assert payload["found"] is False
    assert payload["active_mods"] == []


def test_entrypoint_never_constructs_a_gui_application() -> None:
    """The MCP path must use QCoreApplication, never QApplication/MainWindow."""
    source = (
        Path(__file__).resolve().parents[2] / "app" / "mcp" / "entrypoint.py"
    ).read_text(encoding="utf-8")

    assert "QApplication" not in source
    assert "MainWindow" not in source
    assert source.count("QCoreApplication(") == 1


def test_settings_model_used_by_server_is_plain_settings() -> None:
    settings = Settings()

    assert isinstance(settings.current_instance, str)
    assert settings.current_instance in settings.instances


# ---- in-process entrypoint units ----
#
# The stdio tests above drive ``python -m app --mcp`` as a subprocess, which
# coverage.py cannot observe. These call the same functions in-process so line
# coverage reflects what the entrypoint really executes.


@pytest.fixture
def entrypoint() -> Generator[ModuleType]:
    """Import the entrypoint with the singleton metadata controller reset."""
    from app.controllers.metadata_controller import MetadataController
    from app.mcp import entrypoint as module

    MetadataController._instance = None
    yield module
    MetadataController._instance = None
    # ``_configure_stdio_logging`` replaces every sink; restore a live one so
    # later tests never write to the stream pytest has already closed.
    logger.remove()
    logger.add(sys.stderr)


@pytest.fixture
def configured_settings(game_install: GameInstall, config_folder: Path) -> Settings:
    """Persist a Default instance pointing at the synthetic install.

    ``_bootstrap_core`` constructs its own :class:`Settings`, so the only way to
    make it see a usable instance is to write the file it will load.
    """
    write_mod(game_install.mods_path, "Harmony", "brrainz.harmony")
    write_mods_config(config_folder, ["ludeon.rimworld"])

    settings = Settings()
    settings.instances[settings.current_instance] = Instance(
        name=settings.current_instance,
        game_folder=str(game_install.launch_location),
        config_folder=str(config_folder),
        local_folder=str(game_install.mods_path),
    )
    settings.save()
    return settings


def test_configure_stdio_logging_writes_only_to_stderr_and_file(
    entrypoint: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    log_file = entrypoint._configure_stdio_logging()

    try:
        logger.info("frame-safe diagnostic")
        captured = capsys.readouterr()

        assert log_file.name == "RimSortMCPServer.log"
        assert log_file.is_file()
        assert captured.out == ""
        assert "frame-safe diagnostic" in captured.err
    finally:
        logger.remove()
        logger.add(sys.stderr)


def test_select_instance_keeps_the_active_one_when_unspecified(
    entrypoint: ModuleType, configured_settings: Settings
) -> None:
    entrypoint._select_instance(configured_settings, None)

    assert configured_settings.current_instance == "Default"


def test_select_instance_switches_to_a_configured_instance(
    entrypoint: ModuleType, configured_settings: Settings
) -> None:
    configured_settings.instances["Second"] = Instance(name="Second")

    entrypoint._select_instance(configured_settings, "Second")

    assert configured_settings.current_instance == "Second"


def test_select_instance_rejects_an_unknown_name(
    entrypoint: ModuleType,
    configured_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = MagicMock()
    monkeypatch.setattr(entrypoint.logger, "error", error)

    with pytest.raises(SystemExit) as raised:
        entrypoint._select_instance(configured_settings, "Missing")

    assert raised.value.code == 2
    error.assert_called_once()
    assert "Missing" in error.call_args.args[0]
    # The bound instance is left untouched by a rejected name.
    assert configured_settings.current_instance == "Default"


def test_bootstrap_core_loads_metadata_for_the_bound_instance(
    entrypoint: ModuleType,
    configured_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_steamcmd = MagicMock()
    fake_steamcmd.steamcmd_appworkshop_acf_path = ""
    monkeypatch.setattr(
        SteamcmdInterface, "instance", MagicMock(return_value=fake_steamcmd)
    )

    core = entrypoint._bootstrap_core(None)

    assert core.settings.current_instance == "Default"
    assert "brrainz.harmony" in core.metadata_controller.packageid_to_paths
    assert core.get_instance_status()["active_mods_count"] == 1


def test_bootstrap_core_warns_when_paths_are_unconfigured(
    entrypoint: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh install has no paths; the server must still come up."""
    Settings().save()  # writes an instance with empty folders
    fake_steamcmd = MagicMock()
    fake_steamcmd.steamcmd_appworkshop_acf_path = ""
    monkeypatch.setattr(
        SteamcmdInterface, "instance", MagicMock(return_value=fake_steamcmd)
    )
    warning = MagicMock()
    monkeypatch.setattr(entrypoint.logger, "warning", warning)

    core = entrypoint._bootstrap_core(None)

    assert core.get_instance_status()["paths"]["local_folder"] == ""
    assert core.get_instance_status()["active_mods_count"] == 0
    assert any(
        "missing a game folder" in str(call.args[0]) for call in warning.call_args_list
    )


def test_run_mcp_server_serves_and_quits_the_core_app(
    entrypoint: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    core = MagicMock(spec=RimSortMcpCore)
    server = MagicMock()
    server.run.return_value = None
    qt_app = MagicMock()

    monkeypatch.setattr(entrypoint, "_configure_stdio_logging", MagicMock())
    monkeypatch.setattr(entrypoint, "_bootstrap_core", MagicMock(return_value=core))
    monkeypatch.setattr(entrypoint, "build_server", MagicMock(return_value=server))
    monkeypatch.setattr(
        entrypoint.QCoreApplication, "instance", MagicMock(return_value=qt_app)
    )

    assert entrypoint.run_mcp_server() == 0
    server.run.assert_called_once_with(transport="stdio")
    qt_app.quit.assert_called_once()


def test_run_mcp_server_creates_a_core_application_when_absent(
    entrypoint: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    core = MagicMock(spec=RimSortMcpCore)
    server = MagicMock()
    created = MagicMock()
    app_class = MagicMock()
    app_class.instance.return_value = None
    app_class.return_value = created

    monkeypatch.setattr(entrypoint, "_configure_stdio_logging", MagicMock())
    monkeypatch.setattr(entrypoint, "_bootstrap_core", MagicMock(return_value=core))
    monkeypatch.setattr(entrypoint, "build_server", MagicMock(return_value=server))
    monkeypatch.setattr(entrypoint, "QCoreApplication", app_class)

    assert entrypoint.run_mcp_server("Second") == 0
    app_class.assert_called_once()
    created.quit.assert_called_once()
    entrypoint._bootstrap_core.assert_called_once_with("Second")


def test_run_mcp_server_handles_keyboard_interrupt(
    entrypoint: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    core = MagicMock(spec=RimSortMcpCore)
    server = MagicMock()
    server.run.side_effect = KeyboardInterrupt
    qt_app = MagicMock()

    monkeypatch.setattr(entrypoint, "_configure_stdio_logging", MagicMock())
    monkeypatch.setattr(entrypoint, "_bootstrap_core", MagicMock(return_value=core))
    monkeypatch.setattr(entrypoint, "build_server", MagicMock(return_value=server))
    monkeypatch.setattr(
        entrypoint.QCoreApplication, "instance", MagicMock(return_value=qt_app)
    )

    assert entrypoint.run_mcp_server() == 0
    qt_app.quit.assert_called_once()
