# tests/views/test_main_content_run.py
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QMessageBox

from app.views import dialogue
from app.views.main_content_panel import MainContent


@pytest.fixture(autouse=True)
def patch_dialogue(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock_dialog = Mock()
    mock_dialog.return_value = None
    monkeypatch.setattr(dialogue, "show_dialogue_conditional", mock_dialog)
    return mock_dialog


@pytest.fixture(autouse=True)
def patch_launch(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, str]]:
    # Fake launch_game_process in main_content_panel to capture calls
    from app.views import main_content_panel

    calls: list[tuple[Path, str]] = []

    def fake_launch_game_process(game_install_path: str, run_args: str = "") -> None:
        calls.append((Path(game_install_path), run_args))

    monkeypatch.setattr(
        main_content_panel, "launch_game_process", fake_launch_game_process
    )
    # Also patch platform_specific_open to avoid trying to open Steam protocol
    monkeypatch.setattr(main_content_panel, "platform_specific_open", Mock())
    return calls


@pytest.fixture
def main_content(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    mock_settings_controller: MagicMock,
    mock_metadata_controller: MagicMock,
    mock_steamcmd_interface: MagicMock,
) -> Generator[tuple[MainContent, list[bool]], None, None]:
    # Ensure active_mods_dividers is set on the settings object
    QObject.__setattr__(mock_settings_controller.settings, "active_mods_dividers", [])
    # Set game_folder and run_args on the instance to match test expectations
    instance = mock_settings_controller.settings.instances["Default"]
    instance.game_folder = "/fake/path"
    instance.run_args = "--test"
    # Initialize MainContent with settings from the mock settings controller
    mc = MainContent(
        mock_settings_controller.settings, metadata_controller=mock_metadata_controller
    )
    # Patch _do_save to capture calls
    save_calls: list[bool] = []
    monkeypatch.setattr(mc, "_do_save", lambda: save_calls.append(True))
    # Mock check_if_essential_paths_are_set to return True
    monkeypatch.setattr(
        mc, "check_if_essential_paths_are_set", lambda prompt=True: True
    )
    mc.todds_controller = MagicMock()

    yield mc, save_calls

    # Cleanup: delete the widget to avoid Qt object reuse issues
    mc.deleteLater()
    qapp.processEvents()
    # Reset singleton for next test
    MainContent._instance = None


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
        ("Run Anyway", [], [(Path("/fake/path"), "--test")]),
        ("Save and Run", [True], [(Path("/fake/path"), "--test")]),
    ],
)
def test_run_game_with_unsaved_changes(
    patch_dialogue: Mock,
    patch_launch: list[tuple[Path, str]],
    unsaved_main_content: tuple[MainContent, list[bool]],
    dialogue_return: QMessageBox.StandardButton | str,
    expected_save_calls: list[bool],
    expected_launch: list[tuple[Path, str]],
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
