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
