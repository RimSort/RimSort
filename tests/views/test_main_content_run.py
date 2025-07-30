
# tests/views/test_main_content_run.py
from pathlib import Path
from types import SimpleNamespace
from typing import List, Tuple
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QMessageBox

import app.utils.steam.steamcmd.wrapper as steamcmd_wrapper
import app.views.dialogue as dialogue
from app.views.main_content_panel import MainContent


# Dummy settings and controller to initialize MainContent
class DummySettings:
    def __init__(self) -> None:
        self.current_instance = "inst1"
        # Toggle filter for mod type filtering
        self.mod_type_filter_toggle = False
        # Instance data with dummy game_folder and run_args
        self.instances = {
            "inst1": SimpleNamespace(
                game_folder="/fake/path", run_args=["--test"], steam_client_integration=False
            )
        }

class DummySettingsController:
    def __init__(self) -> None:
        self.settings = DummySettings()

@pytest.fixture(autouse=True)
def patch_dialogue(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock_dialog = Mock()
    mock_dialog.return_value = None
    monkeypatch.setattr(dialogue, 'show_dialogue_conditional', mock_dialog)
    return mock_dialog

@pytest.fixture(autouse=True)
def patch_launch(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[Path, List[str]]]:
    # Fake launch_game_process in main_content_panel to capture calls
    from app.views import main_content_panel
    calls: List[Tuple[Path, List[str]]] = []
    def fake_launch_game_process(game_install_path: str, args: List[str]) -> None:
        calls.append((Path(game_install_path), args))
    monkeypatch.setattr(main_content_panel, 'launch_game_process', fake_launch_game_process)
    return calls

@pytest.fixture(autouse=True)
def patch_steamcmd(monkeypatch: pytest.MonkeyPatch) -> None:
    # Prevent SteamcmdInterface __init__ requiring args
    monkeypatch.setattr(
        steamcmd_wrapper.SteamcmdInterface,
        'instance',
        classmethod(lambda cls: SimpleNamespace(setup=True, steamcmd_appworkshop_acf_path=""))
    )

@pytest.fixture
def main_content(monkeypatch: pytest.MonkeyPatch) -> Tuple[MainContent, List[bool]]:
    # Initialize MainContent with dummy settings
    sc = DummySettingsController()
    mc = MainContent(sc)  # type: ignore[arg-type]
    # Patch _do_save to capture calls
    save_calls: List[bool] = []
    monkeypatch.setattr(mc, '_do_save', lambda: save_calls.append(True))
    return mc, save_calls


def test_cancel_on_unsaved(patch_dialogue: Mock, patch_launch: List[Tuple[Path, List[str]]], main_content: Tuple[MainContent, List[bool]]) -> None:
    mc, save_calls = main_content
    # Set unsaved changes
    mc.mods_panel.active_mods_list.uuids = ['a', 'b']
    mc.active_mods_uuids_last_save = ['a']
    # Simulate Cancel
    patch_dialogue.return_value = QMessageBox.StandardButton.Cancel
    mc._do_run_game()
    assert save_calls == []
    assert patch_launch == []


def test_run_anyway_on_unsaved(patch_dialogue: Mock, patch_launch: List[Tuple[Path, List[str]]], main_content: Tuple[MainContent, List[bool]]) -> None:
    mc, save_calls = main_content
    mc.mods_panel.active_mods_list.uuids = ['a', 'b']
    mc.active_mods_uuids_last_save = ['a']
    patch_dialogue.return_value = 'Run Anyway'
    mc._do_run_game()
    assert save_calls == []
    # launch_game_process with dummy args
    assert patch_launch == [(Path('/fake/path'), ['--test'])]


def test_save_and_run_on_unsaved(patch_dialogue: Mock, patch_launch: List[Tuple[Path, List[str]]], main_content: Tuple[MainContent, List[bool]]) -> None:
    mc, save_calls = main_content
    mc.mods_panel.active_mods_list.uuids = ['a', 'b']
    mc.active_mods_uuids_last_save = ['a']
    patch_dialogue.return_value = 'Save and Run'
    mc._do_run_game()
    assert save_calls == [True]
    assert patch_launch == [(Path('/fake/path'), ['--test'])]


def test_run_without_unsaved(patch_dialogue: Mock, patch_launch: List[Tuple[Path, List[str]]], main_content: Tuple[MainContent, List[bool]]) -> None:
    mc, save_calls = main_content
    # No unsaved changes
    mc.mods_panel.active_mods_list.uuids = ['a', 'b']
    mc.active_mods_uuids_last_save = ['a', 'b']
    mc._do_run_game()
    # Dialogue not shown
    assert patch_dialogue.return_value is None
    assert save_calls == []
    assert patch_launch == [(Path('/fake/path'), ['--test'])]