# tests/views/test_main_content_run.py
from pathlib import Path
from types import SimpleNamespace
from typing import Generator, Iterator, List, Tuple
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


@pytest.fixture(scope="session", autouse=True)
def qapp() -> Iterator[QApplication]:
    """Create QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None or not isinstance(app, QApplication):
        app = QApplication([])
    yield app


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
