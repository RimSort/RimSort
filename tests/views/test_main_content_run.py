# tests/views/test_main_content_run.py
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Generator, List, Tuple
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

import app.utils.metadata as metadata
import app.utils.steam.steamcmd.wrapper as steamcmd_wrapper
import app.views.dialogue as dialogue
from app.views.main_content_panel import MainContent


# Dummy settings and controller to initialize MainContent
class DummySettings:
    def __init__(self) -> None:
        self.current_instance = "inst1"
        # Mod list options
        self.try_download_missing_mods = True
        self.duplicate_mods_warning = True
        self.mod_type_filter = True
        self.hide_invalid_mods_when_filtering = False
        self.backup_saves_on_launch = False
        # Inactive mods sort settings
        self.inactive_mods_sorting = True
        self.save_inactive_mods_sort_state = False
        self.inactive_mods_sort_key = "FILESYSTEM_MODIFIED_TIME"
        self.inactive_mods_sort_descending = True
        # Instance data with dummy game_folder, config_folder and run_args
        self.instances = {
            "inst1": SimpleNamespace(
                game_folder="/fake/path",
                config_folder="/fake/config",
                run_args=["--test"],
                steam_client_integration=False,
            )
        }


class DummySettingsController:
    def __init__(self) -> None:
        self.settings = DummySettings()


@pytest.fixture(autouse=True)
def patch_dialogue(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock_dialog = Mock()
    mock_dialog.return_value = None
    monkeypatch.setattr(dialogue, "show_dialogue_conditional", mock_dialog)
    return mock_dialog


@pytest.fixture(autouse=True)
def patch_launch(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[Path, List[str]]]:
    # Fake launch_game_process in main_content_panel to capture calls
    from app.views import main_content_panel

    calls: List[Tuple[Path, List[str]]] = []

    def fake_launch_game_process(game_install_path: str, args: List[str]) -> None:
        calls.append((Path(game_install_path), args))

    monkeypatch.setattr(
        main_content_panel, "launch_game_process", fake_launch_game_process
    )
    return calls


@pytest.fixture(autouse=True)
def patch_steamcmd(monkeypatch: pytest.MonkeyPatch) -> None:
    # Prevent SteamcmdInterface __init__ requiring args
    monkeypatch.setattr(
        steamcmd_wrapper.SteamcmdInterface,
        "instance",
        classmethod(
            lambda cls: SimpleNamespace(setup=True, steamcmd_appworkshop_acf_path="")
        ),
    )


@pytest.fixture(autouse=True)
def patch_metadata_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch MetadataManager to avoid initialization issues."""
    # Create a mock MetadataManager instance
    mock_metadata_manager = Mock()

    # Patch the MetadataManager.instance method
    monkeypatch.setattr(
        metadata.MetadataManager,
        "instance",
        classmethod(lambda cls: mock_metadata_manager),
    )


@pytest.fixture
def main_content(
    monkeypatch: pytest.MonkeyPatch, qapp: QApplication
) -> Generator[Tuple[MainContent, List[bool]], None, None]:
    # Initialize MainContent with dummy settings
    sc = DummySettingsController()
    mc = MainContent(sc)  # type: ignore[arg-type]
    # Patch _do_save to capture calls
    save_calls: List[bool] = []
    monkeypatch.setattr(mc, "_do_save", lambda: save_calls.append(True))
    # Mock check_if_essential_paths_are_set to return True
    monkeypatch.setattr(
        mc, "check_if_essential_paths_are_set", lambda prompt=True: True
    )

    yield mc, save_calls

    # Cleanup: delete the widget to avoid Qt object reuse issues
    mc.deleteLater()
    qapp.processEvents()
    # Reset singleton for next test
    MainContent._instance = None


@pytest.fixture
def unsaved_main_content(
    main_content: Tuple[MainContent, List[bool]],
) -> Tuple[MainContent, List[bool]]:
    mc, save_calls = main_content
    # Set unsaved changes
    mc.mods_panel.active_mods_list.uuids = ["a", "b"]
    mc.active_mods_uuids_last_save = ["a"]
    return mc, save_calls


@pytest.mark.parametrize(
    "dialogue_return, expected_save_calls, expected_launch",
    [
        (QMessageBox.StandardButton.Cancel, [], []),
        ("Run Anyway", [], [(Path("/fake/path"), ["--test"])]),
        ("Save and Run", [True], [(Path("/fake/path"), ["--test"])]),
    ],
)
def test_run_game_with_unsaved_changes(
    patch_dialogue: Mock,
    patch_launch: List[Tuple[Path, List[str]]],
    unsaved_main_content: Tuple[MainContent, List[bool]],
    dialogue_return: QMessageBox.StandardButton | str,
    expected_save_calls: List[bool],
    expected_launch: List[Tuple[Path, List[str]]],
) -> None:
    mc, save_calls = unsaved_main_content
    patch_dialogue.return_value = (
        dialogue_return
        if isinstance(dialogue_return, QMessageBox.StandardButton)
        else mc.tr(dialogue_return)
    )
    mc._do_run_game()
    assert save_calls == expected_save_calls
    assert patch_launch == expected_launch


def test_run_without_unsaved(
    patch_dialogue: Mock,
    patch_launch: List[Tuple[Path, List[str]]],
    main_content: Tuple[MainContent, List[bool]],
) -> None:
    mc, save_calls = main_content
    # No unsaved changes
    mc.mods_panel.active_mods_list.uuids = ["a", "b"]
    mc.active_mods_uuids_last_save = ["a", "b"]
    mc._do_run_game()
    # Dialogue not shown
    assert patch_dialogue.return_value is None
    assert save_calls == []
    assert patch_launch == [(Path("/fake/path"), ["--test"])]


# Tests for Steam running check


@pytest.fixture(autouse=True)
def patch_steam_appid_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock file operations for steam_appid.txt to avoid filesystem errors."""
    import builtins

    original_open = builtins.open

    def mock_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        # Mock the steam_appid.txt file operations
        if "steam_appid.txt" in str(file):
            mock_file = Mock()
            mock_file.__enter__ = Mock(return_value=mock_file)
            mock_file.__exit__ = Mock(return_value=False)
            mock_file.write = Mock()
            return mock_file
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", mock_open)

    # Mock Path.exists() for steam_appid.txt
    from pathlib import Path

    original_exists = Path.exists

    def mock_exists(self: Path) -> bool:
        if "steam_appid.txt" in str(self):
            return False  # Always pretend file doesn't exist for tests
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", mock_exists)

    # Mock Path.unlink() for steam_appid.txt
    original_unlink = Path.unlink

    def mock_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
        if "steam_appid.txt" in str(self):
            return  # Do nothing for steam_appid.txt
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", mock_unlink)


@pytest.fixture
def patch_steamworks(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Fixture to control SteamworksInterface behavior."""
    from app.utils.steam.steamworks import wrapper

    mock_steamworks = Mock()
    mock_steamworks.steam_not_running = False  # Default: Steam running

    monkeypatch.setattr(
        wrapper.SteamworksInterface,
        "instance",
        classmethod(lambda cls, _libs=None: mock_steamworks),
    )
    return mock_steamworks


@pytest.fixture
def patch_binary_dialog(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Fixture to control BinaryChoiceDialog behavior."""
    mock_dialog = Mock()
    mock_dialog.exec_is_positive.return_value = False  # Default: cancel

    from app.views import dialogue

    monkeypatch.setattr(dialogue, "BinaryChoiceDialog", lambda **kwargs: mock_dialog)
    return mock_dialog


@pytest.mark.parametrize(
    "steam_integration, steam_running, dialog_result, launch_expected",
    [
        # Steam integration disabled - no check performed
        (False, False, None, True),
        (False, True, None, True),
        # Steam running - no dialog shown
        (True, True, None, True),
        # Steam not running, user cancels
        (True, False, False, False),
        # Steam not running, user launches anyway
        (True, False, True, True),
    ],
)
def test_run_game_steam_check(
    patch_steamworks: Mock,
    patch_binary_dialog: Mock,
    patch_launch: List[Tuple[Path, List[str]]],
    main_content: Tuple[MainContent, List[bool]],
    steam_integration: bool,
    steam_running: bool,
    dialog_result: bool | None,
    launch_expected: bool,
) -> None:
    """Test Steam running check with various scenarios."""
    mc, _ = main_content

    # Configure test scenario
    mc.settings_controller.settings.instances[
        "inst1"
    ].steam_client_integration = steam_integration
    mc.mods_panel.active_mods_list.uuids = ["a"]
    mc.active_mods_uuids_last_save = ["a"]

    patch_steamworks.steam_not_running = not steam_running

    if dialog_result is not None:
        patch_binary_dialog.exec_is_positive.return_value = dialog_result

    # Run the game launch
    mc._do_run_game()

    # Verify expected behavior
    if launch_expected:
        assert len(patch_launch) == 1
        assert patch_launch[0] == (Path("/fake/path"), ["--test"])
    else:
        assert len(patch_launch) == 0


def test_run_game_steam_check_exception(
    patch_launch: List[Tuple[Path, List[str]]],
    main_content: Tuple[MainContent, List[bool]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that game launches even if Steam check fails with exception."""
    from app.utils.steam.steamworks import wrapper

    mc, _ = main_content

    # Enable Steam integration
    mc.settings_controller.settings.instances["inst1"].steam_client_integration = True
    mc.mods_panel.active_mods_list.uuids = ["a"]
    mc.active_mods_uuids_last_save = ["a"]

    # Make SteamworksInterface.instance() raise an exception
    def raise_exception(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Steamworks initialization failed")

    monkeypatch.setattr(
        wrapper.SteamworksInterface,
        "instance",
        classmethod(lambda cls, _libs=None: raise_exception()),
    )

    # Run the game launch - should proceed despite exception
    mc._do_run_game()

    # Game should launch (fail-open behavior)
    assert len(patch_launch) == 1
    assert patch_launch[0] == (Path("/fake/path"), ["--test"])


def test_steamworks_concurrent_operations_blocked(
    patch_launch: List[Tuple[Path, List[str]]],
    main_content: Tuple[MainContent, List[bool]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that concurrent Steamworks operations are properly blocked."""
    import threading

    from app.utils.steam.steamworks import wrapper

    mc, _ = main_content

    # Reset singleton instance to start fresh
    wrapper.SteamworksInterface._instance = None

    # Mock STEAMWORKS class to avoid needing actual Steam libraries
    mock_steamworks_obj = Mock()
    mock_steamworks_obj.initialize = Mock()
    mock_steamworks_obj.loaded = Mock(return_value=True)
    mock_steamworks_class = Mock(return_value=mock_steamworks_obj)
    monkeypatch.setattr(
        "app.utils.steam.steamworks.wrapper.STEAMWORKS", mock_steamworks_class
    )

    # Create a real SteamworksInterface instance with mocked Steamworks
    steamworks = wrapper.SteamworksInterface.instance()

    # Ensure steam_not_running is False
    steamworks.steam_not_running = False

    # Start a long-running operation in background thread
    operation_started = threading.Event()
    operation_finished = threading.Event()

    def long_operation() -> None:
        try:
            steamworks._begin_callbacks("test_operation", callbacks_total=1)
            operation_started.set()
            # Hold the operation for a bit
            import time

            time.sleep(0.5)
        finally:
            steamworks._finish_callbacks(timeout=1)
            operation_finished.set()

    bg_thread = threading.Thread(target=long_operation, daemon=True)
    bg_thread.start()

    # Wait for first operation to start
    assert operation_started.wait(timeout=2.0)

    # Try to start concurrent operation - should raise RuntimeError
    with pytest.raises(RuntimeError, match="operation already in progress"):
        steamworks._begin_callbacks("concurrent_operation", callbacks_total=1)

    # Wait for first operation to complete
    assert operation_finished.wait(timeout=2.0)

    # Now a new operation should succeed
    steamworks._begin_callbacks("second_operation", callbacks_total=1)
    steamworks._finish_callbacks(timeout=1)
