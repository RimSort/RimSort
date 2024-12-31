import json
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from shutil import copy2, rmtree

from app.models.settings import Settings
from app.utils.gui_info import show_dialogue_conditional, show_dialogue_file
from app.views.troubleshooting_dialog import TroubleshootingDialog


class TroubleshootingController:
    def __init__(self, settings: Settings, dialog: TroubleshootingDialog) -> None:
        self.settings = settings
        self.dialog = dialog

        # Connect button signals
        self.dialog.integrity_apply_button.clicked.connect(
            self._on_integrity_apply_button_clicked
        )
        self.dialog.integrity_cancel_button.clicked.connect(
            self._on_integrity_cancel_button_clicked
        )

        # Connect mod configuration buttons
        self.dialog.clear_mods_button.clicked.connect(
            self._on_clear_mods_button_clicked
        )
        self.dialog.mod_export_list_button.clicked.connect(
            self._on_mod_export_list_button_clicked
        )
        self.dialog.mod_import_list_button.clicked.connect(
            self._on_mod_import_list_button_clicked
        )

        # Connect Steam utility buttons
        self.dialog.steam_clear_cache_button.clicked.connect(
            self._on_steam_clear_cache_clicked
        )
        self.dialog.steam_verify_game_button.clicked.connect(
            self._on_steam_verify_game_clicked
        )
        self.dialog.steam_repair_library_button.clicked.connect(
            self._on_steam_repair_library_clicked
        )

    @property
    def game_location(self) -> str:
        return self.settings.instances[self.settings.current_instance].game_folder

    @property
    def config_location(self) -> str:
        return self.settings.instances[self.settings.current_instance].config_folder

    @property
    def steam_mods_location(self) -> str:
        return self.settings.instances[self.settings.current_instance].workshop_folder

    def _delete_game_files(self) -> None:
        """Delete game files while preserving local mods."""
        if not self.game_location:
            return

        game_dir = Path(self.game_location)
        mods_dir = game_dir / "Mods"

        # Temporarily move Mods folder
        if mods_dir.exists():
            temp_mods = game_dir / "Mods_temp"
            mods_dir.rename(temp_mods)

        # Delete all files except Mods
        for item in game_dir.iterdir():
            if item.name != "Mods_temp":
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    rmtree(item)

        # Restore Mods folder
        if (game_dir / "Mods_temp").exists():
            (game_dir / "Mods_temp").rename(mods_dir)

        # Try to trigger Steam installation
        try:
            from app.utils.generic import platform_specific_open

            platform_specific_open("steam://install/294100")  # RimWorld's Steam ID
        except Exception:
            show_dialogue_conditional(
                title="Steam Launch Failed",
                text="Could not automatically start game installation through Steam.\n\nPlease manually verify/install the game through Steam.",
                icon="warning",
            )

    def _delete_steam_mods(self) -> None:
        """Delete all Steam Workshop mods and trigger redownload."""
        if not self.steam_mods_location:
            return

        steam_mods_dir = Path(self.steam_mods_location)
        if not steam_mods_dir.exists():
            return

        # get list of mod IDs before deleting
        mod_ids = []
        for item in steam_mods_dir.iterdir():
            if (
                item.is_dir() and item.name.isdigit()
            ):  # workshop folders are numeric IDs
                mod_ids.append(item.name)

        # delete all files and folders
        for item in steam_mods_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                rmtree(item)

        # try to trigger redownload for each mod
        try:
            from app.utils.generic import platform_specific_open

            # first verify/repair game files
            platform_specific_open("steam://validate/294100")

            # then trigger download for each mod
            for mod_id in mod_ids:
                platform_specific_open(
                    f"steam://workshop_download_item/294100/{mod_id}"
                )
        except Exception:
            show_dialogue_conditional(
                title="Steam Workshop Redownload",
                text="Mods have been deleted. Please restart Steam to trigger automatic redownload of subscribed mods.\n\nIf mods don't download automatically, try:\n1. Restart Steam\n2. Verify game files in Steam\n3. Visit the Workshop page of each mod",
                icon="warning",
            )

    def _delete_mod_configs(self) -> None:
        """Delete mod configuration files while preserving ModsConfig.xml and Prefs.xml."""
        if not self.config_location:
            return

        config_dir = Path(self.config_location)
        if not config_dir.exists():
            return

        protected_files = ["ModsConfig.xml", "Prefs.xml"]
        for item in config_dir.iterdir():
            if item.is_file() and item.name not in protected_files:
                item.unlink()

    def _delete_game_configs(self) -> None:
        """Delete game configuration files."""
        if not self.config_location:
            return

        config_dir = Path(self.config_location)
        if not config_dir.exists():
            return

        config_files = ["ModsConfig.xml", "Prefs.xml", "KeyPrefs.xml"]
        for filename in config_files:
            config_file = config_dir / filename
            if config_file.exists():
                config_file.unlink()

    def _on_integrity_apply_button_clicked(self) -> None:
        """Handle clicking the Apply button in the integrity check section."""
        if not show_dialogue_conditional(
            "Confirm Changes",
            "Are you sure you want to apply these changes? This cannot be undone.",
            "This will delete the selected files. Make sure you have backups if needed.",
        ):
            return

        if self.dialog.integrity_delete_game_files.isChecked():
            self._delete_game_files()

        if self.dialog.integrity_delete_steam_mods.isChecked():
            self._delete_steam_mods()

        if self.dialog.integrity_delete_mod_configs.isChecked():
            self._delete_mod_configs()

        if self.dialog.integrity_delete_game_configs.isChecked():
            self._delete_game_configs()

        # Clear checkboxes after applying
        self._on_integrity_cancel_button_clicked()

    def _on_integrity_cancel_button_clicked(self) -> None:
        """Clear all checkboxes in the integrity check section."""
        self.dialog.integrity_delete_game_files.setChecked(False)
        self.dialog.integrity_delete_steam_mods.setChecked(False)
        self.dialog.integrity_delete_mod_configs.setChecked(False)
        self.dialog.integrity_delete_game_configs.setChecked(False)

    def _on_clear_mods_button_clicked(self) -> None:
        """Clear all mods and reset to vanilla state."""
        if not self.config_location or not self.game_location:
            return

        if not show_dialogue_conditional(
            title="Confirm Clear",
            text="Are you sure you want to delete all mods?\n\nWARNING: This will permanently delete all mods in your Mods folder and reset to vanilla state.",
            icon="warning",
        ):
            return

        # delete mods folder
        game_dir = Path(self.game_location)
        mods_dir = game_dir / "Mods"
        if mods_dir.exists():
            rmtree(mods_dir)
            mods_dir.mkdir()  # recreate empty Mods folder

        # reset ModsConfig.xml to vanilla state
        config_dir = Path(self.config_location)
        mods_config = config_dir / "ModsConfig.xml"
        if mods_config.exists():
            # backup current ModsConfig.xml
            backup_path = mods_config.with_suffix(".xml.backup")
            copy2(mods_config, backup_path)

            # Wwrite vanilla ModsConfig.xml
            vanilla_content = """<?xml version="1.0" encoding="utf-8"?>
<ModsConfigData>
  <version>1.4</version>
  <activeMods>
    <li>ludeon.rimworld</li>
  </activeMods>
  <knownExpansions>
  </knownExpansions>
</ModsConfigData>"""
            mods_config.write_text(vanilla_content)

        # refresh mod list
        from app.utils.event_bus import EventBus

        EventBus().do_refresh_mods_lists.emit()

    def _on_mod_export_list_button_clicked(self) -> None:
        """Backup current mod list to a file."""
        if not self.config_location:
            return

        config_dir = Path(self.config_location)
        mods_config = config_dir / "ModsConfig.xml"
        if not mods_config.exists():
            return

        # let user select save location
        save_path = show_dialogue_file(
            title="Export Mod List",
            directory=str(config_dir),
            file_type="File",
            file_filter="RimSort Mod List (*.rml)",
            is_save=True,
        )
        if not save_path:
            return

        # ensure .rml extension
        save_path = str(save_path)
        if not save_path.lower().endswith(".rml"):
            save_path += ".rml"

        if not show_dialogue_conditional(
            "Confirm Export",
            "Export current mod list to file?",
        ):
            return

        # read current mod list
        content = mods_config.read_text()
        tree = ElementTree.fromstring(content)
        active_mod_list = [mod.text for mod in tree.findall(".//activeMods/li")]
        known_expansions_list = [
            exp.text for exp in tree.findall(".//knownExpansions/li")
        ]

        # create new ModsConfig.xml content
        root = ElementTree.Element("ModsConfigData")
        version_elem = tree.find("version")
        if version_elem is not None and version_elem.text is not None:
            version = ElementTree.SubElement(root, "version")
            version.text = version_elem.text
        else:
            version = ElementTree.SubElement(root, "version")
            version.text = "1.4"  # default version if not found

        active_mods_elem = ElementTree.SubElement(root, "activeMods")
        for mod in active_mod_list:
            if mod is not None:
                mod_elem = ElementTree.SubElement(active_mods_elem, "li")
                mod_elem.text = mod

        known_expansions_elem = ElementTree.SubElement(root, "knownExpansions")
        for exp in known_expansions_list:
            if exp is not None:
                exp_elem = ElementTree.SubElement(known_expansions_elem, "li")
                exp_elem.text = exp

        xml_tree = ElementTree.ElementTree(root)
        xml_tree.write(mods_config, encoding="utf-8", xml_declaration=True)

        # export as JSON
        export_data = {
            "version": version.text,
            "activeMods": active_mod_list,
            "knownExpansions": known_expansions_list,
        }

        with open(save_path, "w") as f:
            json.dump(export_data, f, indent=2)

    def _on_mod_import_list_button_clicked(self) -> None:
        """Import mod list from a file."""
        if not self.config_location:
            return

        config_dir = Path(self.config_location)
        mods_config = config_dir / "ModsConfig.xml"
        if not mods_config.exists():
            return

        # let user select file to import
        import_path = show_dialogue_file(
            title="Import Mod List",
            directory=str(config_dir),
            file_type="File",
            file_filter="RimSort Mod List (*.rml *.rws *.xml)",
        )
        if not import_path:
            return

        if not show_dialogue_conditional(
            "Confirm Import",
            "Import mod list from file?",
            "This will overwrite your current mod list.",
        ):
            return

        try:
            # read and validate import file
            with open(import_path) as f:
                import_data = json.load(f)

            if not all(key in import_data for key in ["version", "activeMods"]):
                raise ValueError("Invalid mod list format")

            # create new ModsConfig.xml content
            root = ElementTree.Element("ModsConfigData")
            version = ElementTree.SubElement(root, "version")
            version.text = import_data["version"]

            active_mods = ElementTree.SubElement(root, "activeMods")
            for mod in import_data["activeMods"]:
                mod_elem = ElementTree.SubElement(active_mods, "li")
                mod_elem.text = mod

            known_expansions = ElementTree.SubElement(root, "knownExpansions")
            for exp in import_data.get("knownExpansions", []):
                exp_elem = ElementTree.SubElement(known_expansions, "li")
                exp_elem.text = exp

            tree = ElementTree.ElementTree(root)
            tree.write(mods_config, encoding="utf-8", xml_declaration=True)

            # refresh mod list so user dont need to click refresh button in main window
            from app.utils.event_bus import EventBus

            EventBus().do_refresh_mods_lists.emit()

        except (json.JSONDecodeError, ValueError, KeyError):
            show_dialogue_conditional(
                "Error",
                "Failed to import mod list",
                "The selected file is not a valid mod list file.",
            )

    def _get_steam_root_from_workshop(self) -> Path | None:
        """Get Steam root directory from configured workshop folder path."""
        if not self.steam_mods_location:
            return None

        # workshop path is typically: Steam/steamapps/workshop/content/294100
        # So we go up 4 levels to get steam root
        try:
            workshop_path = Path(self.steam_mods_location)
            if "steamapps" in str(workshop_path):
                steam_root = workshop_path
                while (
                    steam_root.name.lower() != "steam"
                    and steam_root.parent != steam_root
                ):
                    steam_root = steam_root.parent
                if steam_root.name.lower() == "steam":
                    return steam_root
        except Exception:
            pass
        return None

    def _on_steam_clear_cache_clicked(self) -> None:
        """Clear Steam's download cache by deleting the downloading folder."""
        try:
            # try to get steam path from workshop folder first
            steam_path = self._get_steam_root_from_workshop()

            # if not found, try common installation paths
            if not steam_path:
                steam_paths = [
                    Path("C:/Program Files (x86)/Steam"),
                    Path("C:/Program Files/Steam"),
                    Path(str(Path.home()) + "/Steam"),
                ]
                for path in steam_paths:
                    if path.exists():
                        steam_path = path
                        break

            if not steam_path:
                raise Exception("Steam installation not found")

            # delete downloading folder
            downloading_folder = steam_path / "steamapps" / "downloading"
            if downloading_folder.exists():
                rmtree(downloading_folder)
                show_dialogue_conditional(
                    title="Cache Cleared",
                    text="Successfully deleted Steam's downloading folder.\nRestart Steam for the changes to take effect.",
                    icon="info",
                )
            else:
                show_dialogue_conditional(
                    title="Cache Clear",
                    text="Steam's downloading folder is already empty.",
                    icon="info",
                    buttons=["Ok"],
                )

        except Exception:
            show_dialogue_conditional(
                title="Cache Clear Failed",
                text="Could not delete Steam's downloading folder.\nPlease delete it manually: Steam/steamapps/downloading",
                icon="warning",
                buttons=["Ok"],
            )

    def _on_steam_verify_game_clicked(self) -> None:
        """Verify game files through Steam."""
        try:
            from app.utils.generic import platform_specific_open

            platform_specific_open("steam://validate/294100")  # rim steam app id
        except Exception:
            show_dialogue_conditional(
                title="Steam Action Failed",
                text="Could not open Steam to verify game files.\nPlease verify game files manually through Steam's game properties.",
                icon="warning",
                buttons=["Ok"],
            )

    def _on_steam_repair_library_clicked(self) -> None:
        """Repair Steam library by validating all installed games."""
        try:
            steam_path = self._get_steam_root_from_workshop()

            if not steam_path:
                steam_paths = [
                    Path("C:/Program Files (x86)/Steam"),
                    Path("C:/Program Files/Steam"),
                    Path(str(Path.home()) + "/Steam"),
                ]
                for path in steam_paths:
                    if path.exists():
                        steam_path = path
                        break

            if not steam_path:
                raise Exception("Steam installation not found")

            # read libraryfolders.vdf to get all library paths and installed games
            library_file = steam_path / "steamapps" / "libraryfolders.vdf"
            if not library_file.exists():
                raise Exception("Steam library file not found")

            # parse libraryfolders.vdf to get app IDs
            # libraryfolders.vdf is a (valve structured) key-value pair file
            import re

            content = library_file.read_text(encoding="utf-8")
            app_ids = re.findall(r'"appid"\s+"(\d+)"', content)

            if not app_ids:
                show_dialogue_conditional(
                    title="No Games Found",
                    text="No installed games found in this Steam library folder.\nYou may have games installed in a different Steam library folder or drive.",
                    icon="warning",
                    buttons=["Ok"],
                )
                return

            # ask for confirmation since this will validate all games
            if not show_dialogue_conditional(
                title="Confirm Library Repair",
                text=f"This will verify all {len(app_ids)} games in your Steam library.\nThis may take a while. Continue?",
            ):
                return

            # validate each game
            from app.utils.generic import platform_specific_open

            for app_id in app_ids:
                platform_specific_open(f"steam://validate/{app_id}")

            show_dialogue_conditional(
                title="Library Repair Started",
                text=f"Steam will now verify {len(app_ids)} games.\nYou can monitor progress in the Steam client.",
                icon="info",
            )

        except Exception:
            show_dialogue_conditional(
                title="Steam Action Failed",
                text="Could not repair Steam library.\nPlease verify your games manually through Steam.",
                icon="warning",
            )
