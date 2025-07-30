
# tests/views/test_main_content_run.py
import pytest
from types import SimpleNamespace
from pathlib import Path
from PySide6.QtWidgets import QMessageBox

import app.views.dialogue as dialogue
import app.utils.generic as generic
from app.views.main_content_panel import MainContent
import app.utils.steam.steamcmd.wrapper as steamcmd_wrapper

# Dummy settings and controller to initialize MainContent
class DummySettings:
    def __init__(self):
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
    def __init__(self):
        self.settings = DummySettings()

@pytest.fixture(autouse=True)
def patch_dialogue(monkeypatch):
    # Fake dialogue to return controlled values
    def fake_dialogue_conditional(title=None, text=None, button_text_override=None, **kwargs):
        return fake_dialogue_conditional.return_value
    fake_dialogue_conditional.return_value = None
    monkeypatch.setattr(dialogue, 'show_dialogue_conditional', fake_dialogue_conditional)
    return fake_dialogue_conditional

@pytest.fixture(autouse=True)
def patch_launch(monkeypatch):
    # Fake launch_game_process in main_content_panel to capture calls
    from app.views import main_content_panel
    calls = []
    def fake_launch_game_process(game_install_path, args):
        calls.append((Path(game_install_path), args))
    monkeypatch.setattr(main_content_panel, 'launch_game_process', fake_launch_game_process)
    return calls

@pytest.fixture(autouse=True)
def patch_steamcmd(monkeypatch):
    # Prevent SteamcmdInterface __init__ requiring args
    monkeypatch.setattr(
        steamcmd_wrapper.SteamcmdInterface,
        'instance',
        classmethod(lambda cls: SimpleNamespace(setup=True, steamcmd_appworkshop_acf_path=""))
    )

@pytest.fixture
def main_content(monkeypatch):
    # Initialize MainContent with dummy settings
    sc = DummySettingsController()
    mc = MainContent(sc)
    # Patch _do_save to capture calls
    save_calls = []
    monkeypatch.setattr(mc, '_do_save', lambda: save_calls.append(True))
    return mc, save_calls


def test_cancel_on_unsaved(patch_dialogue, patch_launch, main_content):
    mc, save_calls = main_content
    # Set unsaved changes
    mc.mods_panel.active_mods_list.uuids = ['a', 'b']
    mc.active_mods_uuids_last_save = ['a']
    # Simulate Cancel
    patch_dialogue.return_value = QMessageBox.StandardButton.Cancel
    mc._do_run_game()
    assert save_calls == []
    assert patch_launch == []


def test_run_anyway_on_unsaved(patch_dialogue, patch_launch, main_content):
    mc, save_calls = main_content
    mc.mods_panel.active_mods_list.uuids = ['a', 'b']
    mc.active_mods_uuids_last_save = ['a']
    patch_dialogue.return_value = 'Run Anyway'
    mc._do_run_game()
    assert save_calls == []
    # launch_game_process with dummy args
    assert patch_launch == [(Path('/fake/path'), ['--test'])]


def test_save_and_run_on_unsaved(patch_dialogue, patch_launch, main_content):
    mc, save_calls = main_content
    mc.mods_panel.active_mods_list.uuids = ['a', 'b']
    mc.active_mods_uuids_last_save = ['a']
    patch_dialogue.return_value = 'Save and Run'
    mc._do_run_game()
    assert save_calls == [True]
    assert patch_launch == [(Path('/fake/path'), ['--test'])]


def test_run_without_unsaved(patch_dialogue, patch_launch, main_content):
    mc, save_calls = main_content
    # No unsaved changes
    mc.mods_panel.active_mods_list.uuids = ['a', 'b']
    mc.active_mods_uuids_last_save = ['a', 'b']
    mc._do_run_game()
    # Dialogue not shown
    assert patch_dialogue.return_value is None
    assert save_calls == []
    assert patch_launch == [(Path('/fake/path'), ['--test'])]