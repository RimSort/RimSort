# tests/views/test_main_content_run.py
from pathlib import Path
from threading import Thread
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QMessageBox

from app.utils.event_bus import EventBus
from app.views import dialogue, main_content_panel
from app.views.main_content_panel import MainContent
from tests.game_layout_fixtures import make_game_install


@pytest.fixture(autouse=True)
def patch_dialogue(mock_dialogue: Mock) -> Mock:
    """Auto-patch dialogue for every test in this module."""
    return mock_dialogue


@pytest.fixture(autouse=True)
def steam_open_mock(monkeypatch: pytest.MonkeyPatch) -> Mock:
    spy = Mock()
    monkeypatch.setattr(main_content_panel, "platform_specific_open", spy)
    return spy


@pytest.fixture(autouse=True)
def patch_launch(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, str]]:
    # Fake launch_game_process in main_content_panel to capture calls
    from app.views import main_content_panel

    monkeypatch.setattr("app.utils.generic.platform.system", lambda: "Linux")
    monkeypatch.setattr(main_content_panel.sys, "platform", "linux")
    calls: list[tuple[Path, str]] = []

    def fake_launch_game_process(game_install_path: str, run_args: str = "") -> None:
        calls.append((Path(game_install_path), run_args))

    monkeypatch.setattr(
        main_content_panel, "launch_game_process", fake_launch_game_process
    )
    monkeypatch.setattr(main_content_panel, "create_backup_in_thread", Mock())
    return calls


@pytest.fixture
def unsaved_main_content(
    main_content: tuple[MainContent, list[bool]],
) -> tuple[MainContent, list[bool]]:
    mc, save_calls = main_content
    # Set unsaved changes
    mc.mods_panel.active_mods_list.paths = ["a", "b"]
    mc.active_mods_uuids_last_save = ["a"]
    return mc, save_calls


@pytest.mark.parametrize(
    "dialogue_return, expected_save_calls, expected_launch",
    [
        (QMessageBox.StandardButton.Cancel, [], []),
        (None, [], []),
        ("Run Anyway", [], [(Path("/fake/path"), "--test")]),
        ("Save and Run", [True], [(Path("/fake/path"), "--test")]),
    ],
)
def test_run_game_with_unsaved_changes(
    patch_dialogue: Mock,
    patch_launch: list[tuple[Path, str]],
    unsaved_main_content: tuple[MainContent, list[bool]],
    dialogue_return: QMessageBox.StandardButton | str | None,
    expected_save_calls: list[bool],
    expected_launch: list[tuple[Path, str]],
) -> None:
    mc, save_calls = unsaved_main_content
    patch_dialogue.return_value = (
        dialogue_return
        if isinstance(dialogue_return, QMessageBox.StandardButton)
        else mc.tr(dialogue_return)
        if dialogue_return is not None
        else None
    )
    mc._do_run_game()
    assert save_calls == expected_save_calls
    assert patch_launch == expected_launch


def test_run_without_unsaved(
    patch_dialogue: Mock,
    patch_launch: list[tuple[Path, str]],
    main_content: tuple[MainContent, list[bool]],
) -> None:
    mc, save_calls = main_content
    # No unsaved changes
    mc.mods_panel.active_mods_list.paths = ["a", "b"]
    mc.active_mods_uuids_last_save = ["a", "b"]
    mc._do_run_game()
    # Dialogue not shown
    assert patch_dialogue.return_value is None
    assert save_calls == []
    assert patch_launch == [(Path("/fake/path"), "--test")]


@pytest.mark.parametrize("marker_exists", [True, False])
@pytest.mark.parametrize("steam_protocol", [True, False])
def test_save_failure_stops_all_launch_preparation(
    unsaved_main_content: tuple[MainContent, list[bool]],
    steam_open_mock: Mock,
    patch_dialogue: Mock,
    patch_launch: list[tuple[Path, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    marker_exists: bool,
    steam_protocol: bool,
) -> None:
    mc, _calls = unsaved_main_content
    install = make_game_install(tmp_path / "RimWorld", "linux")
    marker = install.content_root / "steam_appid.txt"
    if marker_exists:
        marker.write_text("keep unchanged")
    instance = mc.settings.instances[mc.settings.current_instance]
    instance.game_folder = str(install.launch_location)
    instance.steam_client_integration = not marker_exists
    instance.launch_via_steam_protocol = steam_protocol
    mc.settings.auto_run_todds_before_launch = True
    save = Mock(return_value=False)
    todds = Mock(return_value=(True, 0))
    monkeypatch.setattr(mc, "_do_save", save)
    monkeypatch.setattr(mc, "_do_optimize_textures", todds)
    patch_dialogue.return_value = "Save and Run"
    mc._do_run_game()
    save.assert_called_once()
    todds.assert_not_called()
    assert marker.exists() is marker_exists
    if marker_exists:
        assert marker.read_text() == "keep unchanged"
    assert patch_launch == []
    steam_open_mock.assert_not_called()


@pytest.mark.parametrize("allow", [True, False])
def test_unresolved_direct_launch_requires_explicit_override_before_mutation(
    main_content: tuple[MainContent, list[bool]],
    patch_launch: list[tuple[Path, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    allow: bool,
) -> None:
    mc, _calls = main_content
    game = tmp_path / "RimWorld"
    game.mkdir()
    executable = game / "RimWorld"
    executable.write_bytes(b"game")
    executable.chmod(0o755)
    instance = mc.settings.instances[mc.settings.current_instance]
    instance.game_folder = str(game)
    instance.steam_client_integration = True
    mc.settings.auto_run_todds_before_launch = True
    todds = Mock(return_value=(True, 0))
    monkeypatch.setattr(mc, "_do_optimize_textures", todds)
    monkeypatch.delattr(mc, "_confirm_direct_launch")
    confirm = Mock(return_value=allow)
    monkeypatch.setattr(dialogue, "confirm_content_discovery_override", confirm)
    mc._do_run_game()
    confirm.assert_called_once()
    assert confirm.call_args.kwargs["action_text"] == "Run anyway"
    assert (game / "steam_appid.txt").exists() is allow
    assert bool(todds.call_count) is allow
    assert patch_launch == ([(game, "--test")] if allow else [])
    assert instance.game_folder == str(game)


@pytest.mark.parametrize("has_executable", [True, False])
def test_resolved_direct_launch_needs_no_content_override(
    main_content: tuple[MainContent, list[bool]],
    patch_launch: list[tuple[Path, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    has_executable: bool,
) -> None:
    mc, _calls = main_content
    install = make_game_install(tmp_path / "RimWorld", "linux")
    marker = install.content_root / "steam_appid.txt"
    if not has_executable:
        (install.launch_location / "RimWorld").unlink()
        marker.write_text("keep")
    mc.settings.instances[mc.settings.current_instance].game_folder = str(
        install.launch_location
    )
    monkeypatch.delattr(mc, "_confirm_direct_launch")
    confirm = Mock()
    monkeypatch.setattr(dialogue, "confirm_content_discovery_override", confirm)
    mc._do_run_game()
    confirm.assert_not_called()
    assert patch_launch == (
        [(install.launch_location, "--test")] if has_executable else []
    )
    if not has_executable:
        assert marker.read_text() == "keep"


def test_steam_protocol_remains_available_without_content_override(
    main_content: tuple[MainContent, list[bool]],
    steam_open_mock: Mock,
    patch_launch: list[tuple[Path, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mc, _calls = main_content
    instance = mc.settings.instances[mc.settings.current_instance]
    instance.game_folder = str(tmp_path)
    instance.steam_client_integration = True
    instance.launch_via_steam_protocol = True
    monkeypatch.delattr(mc, "_confirm_direct_launch")
    confirm = Mock()
    monkeypatch.setattr(dialogue, "confirm_content_discovery_override", confirm)
    mc._do_run_game()
    confirm.assert_not_called()
    assert patch_launch == []
    steam_open_mock.assert_called_once_with("steam://rungameid/294100")


@pytest.mark.parametrize("allow", [True, False])
def test_steamworks_launch_is_confirmed_before_worker_creation(
    main_content: tuple[MainContent, list[bool]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    allow: bool,
) -> None:
    mc, _calls = main_content
    game = tmp_path / "RimWorld"
    game.mkdir()
    (game / "RimWorld").write_bytes(b"game")
    (game / "RimWorld").chmod(0o755)
    monkeypatch.delattr(mc, "_confirm_direct_launch")
    monkeypatch.setattr(
        dialogue, "confirm_content_discovery_override", Mock(return_value=allow)
    )
    monkeypatch.setattr(
        main_content_panel, "check_steam_available", Mock(return_value=True)
    )
    worker = Mock()
    monkeypatch.setattr(main_content_panel, "SteamworksGameLaunch", worker)
    mc.steamworks_in_use = False
    assert (
        mc._do_steamworks_api_call(["launch_game_process", [str(game), "--test"]])
        is allow
    )
    assert bool(worker.call_count) is allow
    assert mc.steamworks_in_use is False
    if allow:
        worker.return_value.start.assert_called_once()
        worker.return_value.join.assert_called_once()


def test_steamworks_subscription_does_not_prompt_for_game_content(
    main_content: tuple[MainContent, list[bool]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mc, _calls = main_content
    confirm = Mock(side_effect=AssertionError("subscription must not preflight launch"))
    monkeypatch.setattr(mc, "_confirm_direct_launch", confirm)
    monkeypatch.setattr(
        main_content_panel, "check_steam_available", Mock(return_value=True)
    )
    worker = Mock()
    monkeypatch.setattr(main_content_panel, "SteamworksSubscriptionHandler", worker)
    mc.steamworks_in_use = False
    assert mc._do_steamworks_api_call(["subscribe", [123]])
    confirm.assert_not_called()
    worker.return_value.start.assert_called_once()


@pytest.mark.parametrize("allow", [True, False])
def test_signal_launch_confirms_on_gui_before_thread_dispatch(
    qapp: QApplication,
    main_content: tuple[MainContent, list[bool]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    allow: bool,
) -> None:
    mc, _calls = main_content
    events: list[tuple[str, bool]] = []
    results: list[bool] = []

    def confirm(_path: Path) -> bool:
        events.append(("confirm", QThread.currentThread() == qapp.thread()))
        return allow

    def dispatch(**kwargs: object) -> bool:
        events.append(("dispatch", QThread.currentThread() == qapp.thread()))
        target = kwargs["target"]
        assert callable(target)
        thread = Thread(target=lambda: results.append(bool(target())))
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive()
        return results[0]

    monkeypatch.setattr(mc, "_confirm_direct_launch", confirm)
    monkeypatch.setattr(mc, "do_threaded_loading_animation", dispatch)
    monkeypatch.setattr(mc, "_do_refresh", Mock())
    monkeypatch.setattr(
        main_content_panel, "check_steam_available", lambda **kwargs: True
    )
    worker = Mock()
    monkeypatch.setattr(main_content_panel, "SteamworksGameLaunch", worker)
    mc.steamworks_in_use = False
    mc.steam_browser = None
    EventBus().do_steamworks_api_call.emit(
        ["launch_game_process", [str(tmp_path), "--test"]]
    )
    assert events == (
        [("confirm", True), ("dispatch", True)] if allow else [("confirm", True)]
    )
    assert bool(worker.call_count) is allow
    assert results == ([True] if allow else [])


def test_upload_file_cancel(
    main_content: tuple[MainContent, list[bool]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mc, _ = main_content
    # Create a temporary file
    temp_file = tmp_path / "test_log.txt"
    temp_file.write_text("dummy log content")

    # Mock do_threaded_loading_animation to return None (cancel)
    monkeypatch.setattr(mc, "do_threaded_loading_animation", Mock(return_value=None))

    # This should return early without errors
    mc._upload_file(temp_file)


def test_upload_file_exception(
    main_content: tuple[MainContent, list[bool]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mc, _ = main_content
    temp_file = tmp_path / "test_log2.txt"
    temp_file.write_text("dummy log content")

    # Mock do_threaded_loading_animation to raise an Exception
    monkeypatch.setattr(
        mc,
        "do_threaded_loading_animation",
        Mock(side_effect=RuntimeError("upload error")),
    )

    # Mock dialogue.show_warning to capture call
    mock_warning = Mock()
    monkeypatch.setattr(dialogue, "show_warning", mock_warning)

    mc._upload_file(temp_file)
    mock_warning.assert_called_once()
    assert "Upload failed" in mock_warning.call_args[1]["title"]


def test_check_for_workshop_updates_exception(
    main_content: tuple[MainContent, list[bool]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mc, _ = main_content
    # Mock do_threaded_loading_animation to raise an Exception
    monkeypatch.setattr(
        mc,
        "do_threaded_loading_animation",
        Mock(side_effect=RuntimeError("workshop error")),
    )

    # Connect status_signal to a mock slot
    mock_slot = Mock()
    mc.status_signal.connect(mock_slot)

    # Mock check_internet_connection to return True
    monkeypatch.setattr(
        "app.views.main_content_panel.check_internet_connection", lambda: True
    )

    mc._do_check_for_workshop_updates()
    mock_slot.assert_called_once_with(mc.tr("Failed to check for Workshop updates"))


def test_check_for_workshop_updates_empty(
    main_content: tuple[MainContent, list[bool]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mc, _ = main_content
    # Mock do_threaded_loading_animation to return a result with status "no_workshop_mods"
    mock_result = Mock()
    mock_result.status = "no_workshop_mods"
    monkeypatch.setattr(
        mc, "do_threaded_loading_animation", Mock(return_value=mock_result)
    )

    # Connect status_signal to a mock slot
    mock_slot = Mock()
    mc.status_signal.connect(mock_slot)

    monkeypatch.setattr(
        "app.views.main_content_panel.check_internet_connection", lambda: True
    )

    mc._do_check_for_workshop_updates()
    mock_slot.assert_called_once_with(mc.tr("No Workshop mods to check for updates"))


def test_append_mod_list_cancel(
    main_content: tuple[MainContent, list[bool]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mc, _ = main_content
    # Mock dialogue.show_dialogue_file to return None (cancel)
    monkeypatch.setattr(dialogue, "show_dialogue_file", Mock(return_value=None))

    # Calling this should log cancellation and return early
    mc._do_append_list_file_xml()
