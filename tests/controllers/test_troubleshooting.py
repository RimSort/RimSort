import json
from pathlib import Path
from shutil import rmtree
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from app.controllers.troubleshooting_controller import TroubleshootingController
from app.models.instance import Instance
from app.models.settings import Settings
from app.views.troubleshooting_dialog import TroubleshootingDialog


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Qt application instance for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    elif not isinstance(app, QApplication):
        raise RuntimeError("Expected QApplication instance, got QCoreApplication.")
    return app


@pytest.fixture
def setup_test_environment(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Setup temporary directories and minimal files for testing."""
    game_dir = tmp_path / "game"
    config_dir = tmp_path / "config"
    steam_mods_dir = tmp_path / "steam_mods"

    game_dir.mkdir()
    config_dir.mkdir()
    steam_mods_dir.mkdir()

    (game_dir / "Mods").mkdir()
    (config_dir / "ModsConfig.xml").write_text("<ModsConfigData></ModsConfigData>")
    (config_dir / "Prefs.xml").write_text("<PrefsData></PrefsData>")

    return game_dir, config_dir, steam_mods_dir


@pytest.fixture
def troubleshooting_controller(
    qapp: QApplication, setup_test_environment: tuple[Path, Path, Path]
) -> tuple[TroubleshootingController, Path, Path, Path]:
    """Create TroubleshootingController with mock settings and dialog."""
    game_dir, config_dir, steam_mods_dir = setup_test_environment

    settings = Settings()
    mock_instance = Instance()
    mock_instance.game_folder = str(game_dir)
    mock_instance.config_folder = str(config_dir)
    mock_instance.workshop_folder = str(steam_mods_dir)

    settings.instances = {"default": mock_instance}
    settings.current_instance = "default"

    dialog = TroubleshootingDialog()
    controller = TroubleshootingController(settings, dialog)

    return controller, game_dir, config_dir, steam_mods_dir


class TestGameFilesRecovery:
    """Tests for game files recovery operations."""

    def test_preserves_local_mods(
        self,
        troubleshooting_controller: tuple[TroubleshootingController, Path, Path, Path],
    ) -> None:
        """Test that game files deletion preserves Mods folder."""
        controller, game_dir, _, _ = troubleshooting_controller

        mods_dir = game_dir / "Mods"
        test_mod = mods_dir / "TestMod"
        test_mod.mkdir()
        (test_mod / "About.xml").write_text("<ModMetaData></ModMetaData>")

        (game_dir / "test.txt").write_text("test")

        with patch("app.utils.generic.platform_specific_open"):
            controller._delete_game_files()
            assert test_mod.exists()
            assert not (game_dir / "test.txt").exists()


class TestSteamModsRecovery:
    """Tests for Steam Workshop mods recovery operations."""

    def test_deletes_steam_mods(
        self,
        troubleshooting_controller: tuple[TroubleshootingController, Path, Path, Path],
    ) -> None:
        """Test that Steam Workshop mods are deleted."""
        controller, _, _, steam_mods_dir = troubleshooting_controller

        test_mod = steam_mods_dir / "123456789"
        test_mod.mkdir()
        (test_mod / "About.xml").write_text("<ModMetaData></ModMetaData>")

        with patch("app.utils.generic.platform_specific_open"):
            controller._delete_steam_mods()
            assert not test_mod.exists()


class TestConfigRecovery:
    """Tests for mod and game configuration recovery operations."""

    def test_mod_config_deletion_preserves_core_files(
        self,
        troubleshooting_controller: tuple[TroubleshootingController, Path, Path, Path],
    ) -> None:
        """Test mod config deletion preserves ModsConfig.xml and Prefs.xml."""
        controller, _, config_dir, _ = troubleshooting_controller

        (config_dir / "test.xml").write_text("<TestData></TestData>")
        (config_dir / "ModsConfig.xml").write_text("<ModsConfigData></ModsConfigData>")
        (config_dir / "Prefs.xml").write_text("<PrefsData></PrefsData>")

        controller._delete_mod_configs()
        assert (config_dir / "ModsConfig.xml").exists()
        assert (config_dir / "Prefs.xml").exists()
        assert not (config_dir / "test.xml").exists()

    def test_game_config_deletion(
        self,
        troubleshooting_controller: tuple[TroubleshootingController, Path, Path, Path],
    ) -> None:
        """Test game config files deletion."""
        controller, _, config_dir, _ = troubleshooting_controller

        (config_dir / "ModsConfig.xml").write_text("<ModsConfigData></ModsConfigData>")
        (config_dir / "Prefs.xml").write_text("<PrefsData></PrefsData>")
        (config_dir / "KeyPrefs.xml").write_text("<KeyPrefsData></KeyPrefsData>")

        controller._delete_game_configs()
        assert not (config_dir / "ModsConfig.xml").exists()
        assert not (config_dir / "Prefs.xml").exists()
        assert not (config_dir / "KeyPrefs.xml").exists()


class TestUIInteractions:
    def test_cancel_button_clears_checkboxes(
        self,
        troubleshooting_controller: tuple[TroubleshootingController, Path, Path, Path],
    ) -> None:
        """Test that cancel button clears all checkboxes."""
        controller, _, _, _ = troubleshooting_controller

        controller.dialog.integrity_delete_game_files.setChecked(True)
        controller.dialog.integrity_delete_steam_mods.setChecked(True)
        controller.dialog.integrity_delete_mod_configs.setChecked(True)
        controller.dialog.integrity_delete_game_configs.setChecked(True)

        controller._on_integrity_cancel_button_clicked()

        assert not controller.dialog.integrity_delete_game_files.isChecked()
        assert not controller.dialog.integrity_delete_steam_mods.isChecked()
        assert not controller.dialog.integrity_delete_mod_configs.isChecked()
        assert not controller.dialog.integrity_delete_game_configs.isChecked()

    def test_clear_mods_functionality(
        self,
        troubleshooting_controller: tuple[TroubleshootingController, Path, Path, Path],
    ) -> None:
        """Test clear mods button deletes mods and resets config."""
        controller, game_dir, config_dir, _ = troubleshooting_controller

        mods_dir = game_dir / "Mods"
        test_mod = mods_dir / "TestMod"
        test_mod.mkdir()
        (test_mod / "About.xml").write_text("<ModMetaData></ModMetaData>")

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

            assert mods_dir.exists()
            assert not test_mod.exists()

            new_content = mods_config.read_text()
            assert "ludeon.rimworld" in new_content
            assert "test.mod" not in new_content

            mock_event_bus_instance.emit.assert_called_once()

    def test_apply_button_executes_selected_operations(
        self,
        troubleshooting_controller: tuple[TroubleshootingController, Path, Path, Path],
    ) -> None:
        """Test apply button executes only selected operations."""
        controller, game_dir, config_dir, steam_mods_dir = troubleshooting_controller

        (game_dir / "test.txt").write_text("test")
        test_mod = steam_mods_dir / "123456789"
        test_mod.mkdir()
        (config_dir / "test.xml").write_text("<TestData></TestData>")

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

        assert not (game_dir / "test.txt").exists()
        assert test_mod.exists()
        assert not (config_dir / "test.xml").exists()
        assert (config_dir / "ModsConfig.xml").exists()

    def test_apply_button_cancelled(
        self,
        troubleshooting_controller: tuple[TroubleshootingController, Path, Path, Path],
    ) -> None:
        """Test that apply button does nothing if cancelled."""
        controller, game_dir, config_dir, steam_mods_dir = troubleshooting_controller

        (game_dir / "test.txt").write_text("test")
        test_mod = steam_mods_dir / "123456789"
        test_mod.mkdir()

        controller.dialog.integrity_delete_game_files.setChecked(True)
        controller.dialog.integrity_delete_steam_mods.setChecked(True)

        with patch(
            "app.controllers.troubleshooting_controller.show_dialogue_conditional",
            return_value=False,
        ):
            controller._on_integrity_apply_button_clicked()

        assert (game_dir / "test.txt").exists()
        assert test_mod.exists()


class TestSteamUtilities:
    def test_steam_clear_cache(
        self,
        troubleshooting_controller: tuple[TroubleshootingController, Path, Path, Path],
    ) -> None:
        """Test Steam clear cache button behavior."""
        controller, _, _, steam_mods_dir = troubleshooting_controller

        steam_path = Path("C:/Program Files (x86)/Steam")
        with (
            patch("app.utils.generic.platform_specific_open") as mock_open,
            patch(
                "app.controllers.troubleshooting_controller.show_dialogue_conditional",
                return_value=True,
            ),
            patch("shutil.rmtree", side_effect=PermissionError()),
            patch(
                "app.controllers.troubleshooting_controller.TroubleshootingController._get_steam_root_from_workshop",
                return_value=steam_path,
            ),
            patch("pathlib.Path.exists", return_value=True),
        ):
            controller._on_steam_clear_cache_clicked()

        mock_open.reset_mock()
        with (
            patch("app.utils.generic.platform_specific_open") as mock_open,
            patch(
                "app.controllers.troubleshooting_controller.show_dialogue_conditional",
                return_value=True,
            ),
        ):
            controller._on_steam_verify_game_clicked()
            mock_open.assert_called_with("steam://validate/294100")

        with (
            patch(
                "pathlib.Path.exists",
                side_effect=lambda p: False if str(p).endswith("downloading") else True,
            ),
            patch(
                "app.controllers.troubleshooting_controller.show_dialogue_conditional"
            ) as mock_dialog,
        ):
            controller._on_steam_clear_cache_clicked()
            assert mock_dialog.call_args.kwargs["title"] in [
                "Cache Clear",
                "Cache Clear Failed",
            ]

    def test_steam_repair_library_button(
        self,
        troubleshooting_controller: tuple[TroubleshootingController, Path, Path, Path],
    ) -> None:
        """Test Steam repair library button behavior."""
        controller, _, _, _ = troubleshooting_controller

        mock_library_file = Path("mock_libraryfolders.vdf")

        with (
            patch(
                "app.controllers.troubleshooting_controller.TroubleshootingController._get_steam_library_file",
                return_value=mock_library_file,
            ),
            patch(
                "pathlib.Path.read_text",
                return_value='"appid" "294100"\n"appid" "123456"',
            ),
            patch(
                "app.controllers.troubleshooting_controller.show_dialogue_conditional",
                return_value=True,
            ),
            patch("app.utils.generic.platform_specific_open") as mock_open,
        ):
            controller._on_steam_repair_library_clicked()
            assert mock_open.call_count == 2
            mock_open.assert_any_call("steam://validate/294100")
            mock_open.assert_any_call("steam://validate/123456")


class TestEdgeCases:
    def test_missing_directories(
        self,
        troubleshooting_controller: tuple[TroubleshootingController, Path, Path, Path],
    ) -> None:
        """Test that operations handle missing directories gracefully."""
        controller, game_dir, config_dir, steam_mods_dir = troubleshooting_controller

        for path in [game_dir, config_dir, steam_mods_dir]:
            rmtree(path)

        with (
            patch("app.utils.generic.platform_specific_open"),
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.iterdir", return_value=[]),
        ):
            controller._delete_game_files()
            controller._delete_steam_mods()
            controller._delete_mod_configs()
            controller._delete_game_configs()


class TestModListImportExport:
    def test_mod_export_list_button(
        self,
        troubleshooting_controller: tuple[TroubleshootingController, Path, Path, Path],
    ) -> None:
        """Test exporting mod list to file."""
        controller, _, config_dir, _ = troubleshooting_controller

        mods_config = config_dir / "ModsConfig.xml"
        mods_config.write_text(
            """<?xml version="1.0" encoding="utf-8"?>
<ModsConfigData>
  <version>1.4</version>
  <activeMods>
    <li>mod1</li>
    <li>mod2</li>
  </activeMods>
  <knownExpansions>
    <li>expansion1</li>
  </knownExpansions>
</ModsConfigData>"""
        )

        with (
            patch(
                "app.controllers.troubleshooting_controller.show_dialogue_file",
                return_value=str(config_dir / "exported_mods.xml"),
            ),
            patch(
                "app.controllers.troubleshooting_controller.show_dialogue_conditional",
                return_value=True,
            ),
            patch("builtins.open", create=True) as mock_open,
            patch("json.dump") as mock_json_dump,
        ):
            controller._on_mod_export_list_button_clicked()
            mock_open.assert_called()
            mock_json_dump.assert_called()

    def test_mod_import_list_button(
        self,
        troubleshooting_controller: tuple[TroubleshootingController, Path, Path, Path],
    ) -> None:
        """Test importing mod list from file."""
        controller, _, config_dir, _ = troubleshooting_controller

        mods_config = config_dir / "ModsConfig.xml"
        mods_config.write_text("<ModsConfigData></ModsConfigData>")

        import_data = {
            "version": "1.4",
            "activeMods": ["mod1", "mod2"],
            "knownExpansions": ["expansion1"],
        }

        import_path = config_dir / "imported_mods.xml"
        import_path.write_text(json.dumps(import_data))

        with (
            patch(
                "app.controllers.troubleshooting_controller.show_dialogue_file",
                return_value=str(import_path),
            ),
            patch(
                "app.controllers.troubleshooting_controller.show_dialogue_conditional",
                return_value=True,
            ),
            patch("builtins.open", create=True) as mock_open,
            patch("json.load", return_value=import_data),
            patch("app.utils.event_bus.EventBus") as mock_event_bus,
        ):
            controller._on_mod_import_list_button_clicked()
            mock_open.assert_called()
            mock_event_bus.return_value.do_refresh_mods_lists.emit.assert_called()
