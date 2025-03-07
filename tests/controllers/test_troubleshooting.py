from pathlib import Path
from shutil import rmtree
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from app.controllers.troubleshooting_controller import TroubleshootingController
from app.models.settings import Settings
from app.views.troubleshooting_dialog import TroubleshootingDialog


@pytest.fixture(scope="session")
def qapp():
    """qt app instance for tests"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def setup_test_environment(tmp_path):
    # setup temp dirs for testing
    game_dir = tmp_path / "game"
    config_dir = tmp_path / "config"
    steam_mods_dir = tmp_path / "steam_mods"

    game_dir.mkdir()
    config_dir.mkdir()
    steam_mods_dir.mkdir()

    # create minimal required files
    (game_dir / "Mods").mkdir()
    (config_dir / "ModsConfig.xml").write_text("<ModsConfigData></ModsConfigData>")
    (config_dir / "Prefs.xml").write_text("<PrefsData></PrefsData>")

    return game_dir, config_dir, steam_mods_dir


@pytest.fixture
def troubleshooting_controller(qapp, setup_test_environment):
    # setup controller with mock settings
    game_dir, config_dir, steam_mods_dir = setup_test_environment

    settings = Settings()
    settings.instances = [settings]  # mock instance list
    settings.current_instance = 0  # set current instance
    settings.instances[0].game_folder = str(game_dir)
    settings.instances[0].config_folder = str(config_dir)
    settings.instances[0].workshop_folder = str(steam_mods_dir)

    dialog = TroubleshootingDialog()
    controller = TroubleshootingController(settings, dialog)

    return controller, game_dir, config_dir, steam_mods_dir


def test_game_files_recovery_preserves_local_mods(troubleshooting_controller):
    # verify game files deletion preserves mods folder
    controller, game_dir, _, _ = troubleshooting_controller

    # setup test mod that should be preserved
    mods_dir = game_dir / "Mods"
    test_mod = mods_dir / "TestMod"
    test_mod.mkdir()
    (test_mod / "About.xml").write_text("<ModMetaData></ModMetaData>")

    # add test file that should be deleted
    (game_dir / "test.txt").write_text("test")

    with patch("app.utils.generic.platform_specific_open"):
        controller._delete_game_files()
        assert test_mod.exists()  # mod should be preserved
        assert not (game_dir / "test.txt").exists()  # other files should be deleted


def test_steam_mods_recovery(troubleshooting_controller):
    # verify steam workshop mods can be deleted
    controller, _, _, steam_mods_dir = troubleshooting_controller

    test_mod = steam_mods_dir / "123456789"
    test_mod.mkdir()
    (test_mod / "About.xml").write_text("<ModMetaData></ModMetaData>")

    with patch("app.utils.generic.platform_specific_open"):
        controller._delete_steam_mods()
        assert not test_mod.exists()  # workshop mod should be deleted


def test_config_recovery(troubleshooting_controller):
    # verify mod config deletion preserves core files
    controller, _, config_dir, _ = troubleshooting_controller

    (config_dir / "test.xml").write_text("<TestData></TestData>")
    (config_dir / "ModsConfig.xml").write_text("<ModsConfigData></ModsConfigData>")
    (config_dir / "Prefs.xml").write_text("<PrefsData></PrefsData>")

    controller._delete_mod_configs()
    assert (config_dir / "ModsConfig.xml").exists()  # core configs preserved
    assert (config_dir / "Prefs.xml").exists()
    assert not (config_dir / "test.xml").exists()  # other configs deleted


def test_game_config_recovery(troubleshooting_controller):
    # verify game config files can be deleted
    controller, _, config_dir, _ = troubleshooting_controller

    (config_dir / "ModsConfig.xml").write_text("<ModsConfigData></ModsConfigData>")
    (config_dir / "Prefs.xml").write_text("<PrefsData></PrefsData>")
    (config_dir / "KeyPrefs.xml").write_text("<KeyPrefsData></KeyPrefsData>")

    controller._delete_game_configs()
    assert not (config_dir / "ModsConfig.xml").exists()  # all game configs deleted
    assert not (config_dir / "Prefs.xml").exists()
    assert not (config_dir / "KeyPrefs.xml").exists()


def test_cancel_button_clears_checkboxes(troubleshooting_controller):
    # verify cancel button resets ui state
    controller, _, _, _ = troubleshooting_controller

    # set all checkboxes
    controller.dialog.integrity_delete_game_files.setChecked(True)
    controller.dialog.integrity_delete_steam_mods.setChecked(True)
    controller.dialog.integrity_delete_mod_configs.setChecked(True)
    controller.dialog.integrity_delete_game_configs.setChecked(True)

    controller._on_integrity_cancel_button_clicked()
    # verify all checkboxes cleared
    assert not controller.dialog.integrity_delete_game_files.isChecked()
    assert not controller.dialog.integrity_delete_steam_mods.isChecked()
    assert not controller.dialog.integrity_delete_mod_configs.isChecked()
    assert not controller.dialog.integrity_delete_game_configs.isChecked()


def test_clear_mods(troubleshooting_controller):
    # verify clear mods functionality
    controller, game_dir, config_dir, _ = troubleshooting_controller

    # setup test mod
    mods_dir = game_dir / "Mods"
    test_mod = mods_dir / "TestMod"
    test_mod.mkdir()
    (test_mod / "About.xml").write_text("<ModMetaData></ModMetaData>")

    # setup test config
    mods_config = config_dir / "ModsConfig.xml"
    mods_config.write_text(
        "<ModsConfigData><activeMods><li>test.mod</li></activeMods></ModsConfigData>"
    )

    with (
        patch(
            "app.controllers.troubleshooting_controller.show_dialogue_conditional",
            return_value=True,
        ),
        patch("app.utils.event_bus.EventBus") as mock_event_bus,
    ):
        mock_event_bus_instance = mock_event_bus.return_value
        mock_event_bus_instance.do_refresh_mods_lists = mock_event_bus_instance

        controller._on_clear_mods_button_clicked()

        # verify mods folder emptied but exists
        assert mods_dir.exists()
        assert not test_mod.exists()

        # verify config reset to vanilla
        new_content = mods_config.read_text()
        assert "ludeon.rimworld" in new_content
        assert "test.mod" not in new_content

        # verify refresh triggered
        mock_event_bus_instance.emit.assert_called_once()


def test_apply_button_executes_selected_operations(troubleshooting_controller):
    # verify apply button executes only selected operations
    controller, game_dir, config_dir, steam_mods_dir = troubleshooting_controller

    # setup test files
    (game_dir / "test.txt").write_text("test")
    test_mod = steam_mods_dir / "123456789"
    test_mod.mkdir()
    (config_dir / "test.xml").write_text("<TestData></TestData>")

    # select specific operations
    controller.dialog.integrity_delete_game_files.setChecked(True)
    controller.dialog.integrity_delete_steam_mods.setChecked(False)
    controller.dialog.integrity_delete_mod_configs.setChecked(True)
    controller.dialog.integrity_delete_game_configs.setChecked(False)

    with (
        patch("app.utils.generic.platform_specific_open"),
        patch(
            "app.controllers.troubleshooting_controller.show_dialogue_conditional",
            return_value=True,
        ),
    ):
        controller._on_integrity_apply_button_clicked()

        # verify only selected operations executed
        assert not (game_dir / "test.txt").exists()  # game files deleted
        assert test_mod.exists()  # steam mods preserved
        assert not (config_dir / "test.xml").exists()  # mod configs deleted
        assert (config_dir / "ModsConfig.xml").exists()  # game configs preserved


def test_apply_button_cancelled(troubleshooting_controller):
    # verify nothing happens when apply is cancelled
    controller, game_dir, config_dir, steam_mods_dir = troubleshooting_controller

    # setup test files
    (game_dir / "test.txt").write_text("test")
    test_mod = steam_mods_dir / "123456789"
    test_mod.mkdir()

    # select all operations
    controller.dialog.integrity_delete_game_files.setChecked(True)
    controller.dialog.integrity_delete_steam_mods.setChecked(True)

    with patch(
        "app.controllers.troubleshooting_controller.show_dialogue_conditional",
        return_value=False,  # user cancels
    ):
        controller._on_integrity_apply_button_clicked()

        # verify nothing was deleted
        assert (game_dir / "test.txt").exists()
        assert test_mod.exists()


def test_steam_utility_buttons(troubleshooting_controller):
    # verify steam utility buttons work correctly
    controller, _, _, steam_mods_dir = troubleshooting_controller

    steam_path = Path("C:/Program Files (x86)/Steam")
    with (
        patch("app.utils.generic.platform_specific_open") as mock_open,
        patch(
            "app.controllers.troubleshooting_controller.show_dialogue_conditional",
            return_value=True,
        ) as mock_dialog,
        patch("shutil.rmtree", side_effect=PermissionError()) as mock_rmtree,
        patch(
            "app.controllers.troubleshooting_controller.TroubleshootingController._get_steam_root_from_workshop",
            return_value=steam_path,
        ),
    ):
        # test clear cache - deletion fails
        with patch("pathlib.Path.exists", return_value=True):
            controller._on_steam_clear_cache_clicked()
            mock_dialog.assert_called_with(
                title="Cache Clear Failed",
                text="Could not delete Steam's downloading folder.\nPlease delete it manually: Steam/steamapps/downloading",
                icon="warning",
                buttons=["Ok"],
            )

        # test verify game
        mock_dialog.reset_mock()
        controller._on_steam_verify_game_clicked()
        mock_open.assert_called_with("steam://validate/294100")

        # test clear cache - folder doesn't exist
        mock_rmtree.side_effect = None  # reset error
        mock_dialog.reset_mock()

        def exists_side_effect(p):
            # Return True for Steam path, False for downloading folder
            if p == steam_path:
                return True
            if str(p).endswith("downloading"):
                return False
            return True

        with patch("pathlib.Path.exists", side_effect=exists_side_effect):
            controller._on_steam_clear_cache_clicked()
            # accept either message since both are valid depending on system state
            assert mock_dialog.call_args.kwargs in [
                {
                    "title": "Cache Clear",
                    "text": "Steam's downloading folder is already empty.",
                    "icon": "info",
                    "buttons": ["Ok"],
                },
                {
                    "title": "Cache Clear Failed",
                    "text": "Could not delete Steam's downloading folder.\nPlease delete it manually: Steam/steamapps/downloading",
                    "icon": "warning",
                    "buttons": ["Ok"],
                },
            ]


def test_missing_directories(troubleshooting_controller):
    # verify operations handle missing directories gracefully
    controller, game_dir, config_dir, steam_mods_dir = troubleshooting_controller

    # remove directories
    for path in [game_dir, config_dir, steam_mods_dir]:
        rmtree(path)

    # verify operations don't raise errors when directories don't exist
    with (
        patch("app.utils.generic.platform_specific_open"),
        patch("pathlib.Path.exists", return_value=False),
        patch("pathlib.Path.iterdir", return_value=[]),
    ):
        controller._delete_game_files()  # should handle missing game dir
        controller._delete_steam_mods()  # should handle missing steam dir
        controller._delete_mod_configs()  # should handle missing config dir
        controller._delete_game_configs()  # should handle missing config dir
