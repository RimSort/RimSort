import json
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from shutil import copy2, rmtree
from typing import List, Optional

from loguru import logger
from PySide6.QtCore import QCoreApplication

from app.models.settings import Settings
from app.utils.gui_info import (
    show_dialogue_conditional,
    show_dialogue_file,
)
from app.views.dialogue import show_information, show_warning
from app.views.troubleshooting_dialog import TroubleshootingDialog


class TroubleshootingController:
    def __init__(self, settings: Settings, dialog: TroubleshootingDialog) -> None:
        self.settings = settings
        self.dialog = dialog

        self.translate = QCoreApplication.translate

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
    def game_location(self) -> Optional[str]:
        return self.settings.instances[self.settings.current_instance].game_folder

    @property
    def config_location(self) -> Optional[str]:
        return self.settings.instances[self.settings.current_instance].config_folder

    @property
    def steam_mods_location(self) -> Optional[str]:
        return self.settings.instances[self.settings.current_instance].workshop_folder

    def _delete_files_in_directory(
        self, directory: Path, exclude: Optional[List[str]] = None
    ) -> None:
        """Helper method to delete files and folders in a directory, excluding specified names."""
        if exclude is None:
            exclude = []
        for item in directory.iterdir():
            if item.name in exclude:
                continue
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    rmtree(item)
            except Exception as e:
                logger.error(f"Failed to delete {item}: {e}")
                self.show_failed_warning(item, e)

    def _delete_game_files(self) -> None:
        """Delete game files while preserving local mods."""
        # Avoid Deleteing Game files if not Steam user
        if not self.steam_mods_location:
            logger.warning("Steam user Check failed, skipping deleteing game files.")
            self.show_steam_user_warning()
            return None

        # Check if game location is set
        if not self.game_location:
            logger.warning("Game location not set, skipping delete game files.")
            self.show_steam_user_warning()
            return

        game_dir = Path(self.game_location)
        mods_dir = game_dir / "Mods"

        # Temporarily move Mods folder
        if mods_dir.exists():
            temp_mods = game_dir / "Mods_temp"
            try:
                mods_dir.rename(temp_mods)
            except Exception as e:
                item = temp_mods
                logger.error(f"Failed to rename {item} folder: {e}")
                self.show_failed_warning(item, e)
                return

        # Delete all files except Mods_temp
        self._delete_files_in_directory(game_dir, exclude=["Mods_temp"])

        # Restore Mods folder
        temp_mods = game_dir / "Mods_temp"
        if temp_mods.exists():
            try:
                temp_mods.rename(mods_dir)
            except Exception as e:
                item = temp_mods
                logger.error(f"Failed to restore {item} folder: {e}")
                self.show_failed_warning(item, e)
                return

        # Try to trigger Steam installation
        try:
            from app.utils.generic import platform_specific_open

            platform_specific_open("steam://install/294100")  # RimWorld's Steam
            logger.info("Triggered Steam installation for game ID 294100.")
            show_information(
                title=self.translate("TroubleshootingController", "Process complete"),
                text=self.translate(
                    "TroubleshootingController",
                    "Process complete, wait for steam to complete further process.",
                ),
            )
        except Exception as e:
            logger.error(f"Failed to launch Steam installation: {e}")
            show_dialogue_conditional(
                title=self.translate(
                    "TroubleshootingController", "Steam Launch Failed"
                ),
                text=self.translate(
                    "TroubleshootingController",
                    "Could not automatically start game installation through Steam.\n\nPlease manually verify/install the game through Steam.",
                ),
                icon="warning",
            )

    def _delete_steam_mods(self) -> None:
        """Delete all Steam Workshop mods and trigger redownload."""
        if not self.steam_mods_location:
            logger.warning("Steam mods location not set, skipping deleting steam mods.")
            self.show_steam_user_warning()
            return None

        steam_mods_dir = Path(self.steam_mods_location)
        if not steam_mods_dir.exists():
            logger.warning("Steam mods directory does not exist, skipping.")
            self.show_steam_user_warning()
            return

        # get list of mod IDs before deleting
        mod_ids = []
        for item in steam_mods_dir.iterdir():
            if (
                item.is_dir() and item.name.isdigit()
            ):  # workshop folders are numeric IDs
                mod_ids.append(item.name)

        # delete all files and folders
        self._delete_files_in_directory(steam_mods_dir)
        logger.info("Deleted all files in the Steam mods directory.")
        show_information(
            title=self.translate("TroubleshootingController", "Process complete"),
            text=self.translate(
                "TroubleshootingController",
                "Deleted all files in the Steam mods directory.\n\n Trying to restart Steam to trigger automatic redownload of subscribed mods.",
            ),
        )

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
                logger.info(f"opening: steam://workshop_download_item/294100/{mod_id}")
        except Exception as e:
            logger.error(f"Failed to trigger Steam workshop redownload: {e}")
            show_dialogue_conditional(
                title=self.translate(
                    "TroubleshootingController", "Steam Workshop Redownload"
                ),
                text=self.translate(
                    "TroubleshootingController",
                    "Mods have been deleted. Please restart Steam to trigger automatic redownload of subscribed mods.\n\nIf mods don't download automatically, try:\n1. Restart Steam\n2. Verify game files in Steam\n3. Visit the Workshop page of each mod",
                ),
                icon="warning",
            )

    def _delete_mod_configs(self) -> None:
        """Delete mod configuration files while preserving ModsConfig.xml and Prefs.xml."""
        if not self.config_location:
            logger.warning("Config location not set, skipping delete mod configs.")
            self.show_location_warning()
            return

        config_dir = Path(self.config_location)
        if not config_dir.exists():
            logger.warning("Config directory does not exist, skipping.")
            self.show_location_warning()
            return

        protected_files = ["ModsConfig.xml", "Prefs.xml"]
        deleted_any = False
        for item in config_dir.iterdir():
            if item.is_file() and item.name not in protected_files:
                try:
                    print(f"Deleting {item}...")
                    item.unlink()
                    deleted_any = True
                    logger.info(f"Deleted {item} successfully.")
                except Exception as e:
                    logger.error(f"Failed to delete config file {item}: {e}")
                    self.show_failed_warning(item, e)

        if deleted_any:
            show_information(
                title=self.translate("TroubleshootingController", "Process complete"),
                text=self.translate(
                    "TroubleshootingController",
                    "Deleted all files in the {config_dir} successfully.",
                ).format(config_dir=config_dir),
            )
        else:
            logger.info(f"No files found in {config_dir} for deletion.")
            show_information(
                title=self.translate("TroubleshootingController", "Process complete"),
                text=self.translate(
                    "TroubleshootingController",
                    "No files found in {config_dir} for deletion.",
                ).format(config_dir=config_dir),
            )

    def _delete_game_configs(self) -> None:
        """Delete game configuration files."""
        if not self.config_location:
            logger.warning("Config location not set, skipping delete game configs.")
            self.show_location_warning()
            return

        config_dir = Path(self.config_location)
        if not config_dir.exists():
            logger.warning("Config directory does not exist, skipping.")
            self.show_location_warning()
            return

        config_files = ["ModsConfig.xml", "Prefs.xml", "KeyPrefs.xml"]
        for filename in config_files:
            config_file = config_dir / filename
            item = config_file
            if item.exists():
                try:
                    item.unlink()
                    logger.info(f"Deleted {item} successfully.")
                    show_information(
                        title=self.translate(
                            "TroubleshootingController", "Process complete"
                        ),
                        text=self.translate(
                            "TroubleshootingController", "Deleted {item} successfully."
                        ).format(item=item),
                    )
                except Exception as e:
                    logger.error(f"Failed to delete game config file {item}: {e}")
                    self.show_failed_warning(item, e)

    def _on_integrity_apply_button_clicked(self) -> None:
        """Handle clicking the Apply button in the integrity check section."""
        if not show_dialogue_conditional(
            self.translate("TroubleshootingController", "Confirm Changes"),
            self.translate(
                "TroubleshootingController",
                "Are you sure you want to apply these changes? This cannot be undone.",
            ),
            self.translate(
                "TroubleshootingController",
                "This will delete the selected files. Make sure you have backups if needed.",
            ),
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
            logger.warning("Config or game location not set, skipping clear mods.")
            self.show_location_warning()
            return

        if not show_dialogue_conditional(
            title=self.translate("TroubleshootingController", "Confirm Clear"),
            text=self.translate(
                "TroubleshootingController",
                "Are you sure you want to delete all mods?\n\nWARNING: This will permanently delete all mods in your Mods folder and reset to vanilla state.",
            ),
            icon="warning",
        ):
            return

        # delete mods folder
        game_dir = Path(self.game_location)
        mods_dir = game_dir / "Mods"
        if mods_dir.exists():
            try:
                rmtree(mods_dir)
                mods_dir.mkdir()  # recreate empty Mods folder
            except Exception as e:
                item = mods_dir
                logger.error(f"Failed to clear {item} folder: {e}")
                self.show_failed_warning(item, e)
                return

        # reset ModsConfig.xml to vanilla state
        config_dir = Path(self.config_location)
        mods_config = config_dir / "ModsConfig.xml"
        if mods_config.exists():
            try:
                # backup current ModsConfig.xml
                backup_path = mods_config.with_suffix(".xml.backup")
                copy2(mods_config, backup_path)

                # Write vanilla ModsConfig.xml
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
                logger.info(
                    "Successfully deleted all mods and resetting ModsConfig.xml to vanilla state."
                )
                show_information(
                    title=self.translate(
                        "TroubleshootingController", "Process complete"
                    ),
                    text=self.translate(
                        "TroubleshootingController",
                        "Successfully deleted all mods and resetting ModsConfig.xml to vanilla state.",
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to reset ModsConfig.xml: {e}")
                show_dialogue_conditional(
                    title=self.translate("TroubleshootingController", "Error"),
                    text=self.translate(
                        "TroubleshootingController", "Failed to reset ModsConfig.xml."
                    ),
                    icon="warning",
                )
                return

        # refresh mod list
        from app.utils.event_bus import EventBus

        EventBus().do_refresh_mods_lists.emit()

    def _on_mod_export_list_button_clicked(self) -> None:
        """Backup current mod list to a file."""
        if not self.config_location:
            logger.warning("Config location not set, skipping mod export.")
            self.show_location_warning()
            return

        config_dir = Path(self.config_location)
        mods_config = config_dir / "ModsConfig.xml"
        if not mods_config.exists():
            logger.warning(f"{mods_config} does not exist, skipping mod export.")
            show_warning(
                title=self.translate("TroubleshootingController", "Export failed"),
                text=self.translate(
                    "TroubleshootingController",
                    "{mods_config} does not exist, skipping mod export.",
                ).format(mods_config=mods_config),
            )
            return

        # let user select save location
        save_path = show_dialogue_file(
            title=self.translate("TroubleshootingController", "Export Mod List"),
            directory=str(config_dir),
            file_type="File",
            file_filter="RimSort Mod List (*.xml)",
            is_save=True,
        )
        if not save_path:
            logger.error(f"Failed to save to Location: {save_path}.")
            show_warning(
                title=self.translate("TroubleshootingController", "Location Error"),
                text=self.translate(
                    "TroubleshootingController", "Failed to get Location: {save_path}."
                ),
            )
            return

        # ensure .xml extension
        save_path = str(save_path)
        if not save_path.lower().endswith(".xml"):
            save_path += ".xml"

        if not show_dialogue_conditional(
            self.translate("TroubleshootingController", "Confirm Export"),
            self.translate(
                "TroubleshootingController", "Export current mod list to file?"
            ),
        ):
            return

        try:
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
        except Exception as e:
            logger.error(f"Failed to export mod list: {e}")
            show_dialogue_conditional(
                title=self.translate("TroubleshootingController", "Error"),
                text=self.translate(
                    "TroubleshootingController", "Failed to export mod list."
                ),
                icon="warning",
            )

    def _on_mod_import_list_button_clicked(self) -> None:
        """Import mod list from a file."""
        if not self.config_location:
            logger.warning("Config location not set, skipping mod import.")
            self.show_location_warning()
            return

        config_dir = Path(self.config_location)
        mods_config = config_dir / "ModsConfig.xml"
        if not mods_config.exists():
            logger.warning(f"{mods_config} does not exist, skipping mod import.")
            show_warning(
                title=self.translate("TroubleshootingController", "Import failed"),
                text=self.translate(
                    "TroubleshootingController",
                    "{mods_config} does not exist, skipping mod import.",
                ).format(mods_config=mods_config),
            )
            return

        # let user select file to import
        import_path = show_dialogue_file(
            title=self.translate("TroubleshootingController", "Import Mod List"),
            directory=str(config_dir),
            file_type="File",
            file_filter="RimSort Mod List (*.xml *.rws *.xml)",
        )
        if not import_path:
            return

        if not show_dialogue_conditional(
            self.translate("TroubleshootingController", "Confirm Import"),
            self.translate("TroubleshootingController", "Import mod list from file?"),
            self.translate(
                "TroubleshootingController",
                "This will overwrite your current mod list.",
            ),
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

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(f"Failed to import mod list: {e}")
            show_dialogue_conditional(
                self.translate("TroubleshootingController", "Error"),
                self.translate(
                    "TroubleshootingController", "Failed to import mod list"
                ),
                self.translate(
                    "TroubleshootingController",
                    "The selected file is not a valid mod list file.\nDetails: {e}",
                ).format(e=str(e)),
            )

    def _get_steam_root_from_workshop(self) -> Optional[Path]:
        """Get Steam root directory from configured workshop folder path."""
        if not self.steam_mods_location:
            logger.warning("Steam mods location not set, skipping getting steam root.")
            self.show_steam_user_warning()
            return None

        # workshop path is typically: Steam/steamapps/workshop/content/294100
        # So we go up 4 levels to get steam root
        workshop_path = Path(self.steam_mods_location)
        try:
            if "steamapps" in str(workshop_path):
                steam_root = workshop_path
                while (
                    steam_root.name.lower() != "steam"
                    and steam_root.parent != steam_root
                ):
                    steam_root = steam_root.parent
                if steam_root.name.lower() == "steam":
                    return steam_root
        except Exception as e:
            item = workshop_path
            logger.error(f"Failed to get steam root from {item} : {e}")
            self.show_failed_warning(item, e)
        return None

    def _find_steam_path(self) -> Path:
        """Find Steam installation path"""
        # First try to get from workshop
        steam_path = self._get_steam_root_from_workshop()

        # If not found, try common locations
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
            raise Exception(f"Steam installation not found: {steam_path}")

        return steam_path

    def _on_steam_clear_cache_clicked(self) -> None:
        """Clear Steam download cache."""
        try:
            steam_path = self._find_steam_path()

            # delete downloading folder
            downloading_folder = steam_path / "steamapps" / "downloading"
            if downloading_folder.exists():
                rmtree(downloading_folder)
                show_dialogue_conditional(
                    title=self.translate("TroubleshootingController", "Cache Cleared"),
                    text=self.translate(
                        "TroubleshootingController",
                        "Successfully deleted Steam's downloading folder.\nRestart Steam for the changes to take effect.",
                    ),
                    icon="info",
                )
            else:
                show_dialogue_conditional(
                    title=self.translate("TroubleshootingController", "Cache Clear"),
                    text=self.translate(
                        "TroubleshootingController",
                        "Steam's downloading folder is already empty.",
                    ),
                    icon="info",
                    buttons=["Ok"],
                )

        except Exception as e:
            logger.error(f"Failed to clear Steam cache: {e}")
            show_dialogue_conditional(
                title=self.translate("TroubleshootingController", "Cache Clear Failed"),
                text=self.translate(
                    "TroubleshootingController",
                    "Could not delete Steam's downloading folder.\nPlease delete it manually: Steam/steamapps/downloading\nDetails: {e}",
                ).format(e=str(e)),
                icon="warning",
                buttons=["Ok"],
            )

    def _on_steam_verify_game_clicked(self) -> None:
        """Verify game files through Steam."""
        try:
            from app.utils.generic import platform_specific_open

            platform_specific_open("steam://validate/294100")  # rim steam app id
        except Exception as e:
            logger.error(f"Failed to verify game files: {e}")
            show_dialogue_conditional(
                title=self.translate(
                    "TroubleshootingController", "Steam Action Failed"
                ),
                text=self.translate(
                    "TroubleshootingController",
                    "Could not open Steam to verify game files.\nPlease verify game files manually through Steam's game properties.\nDetails: {e}",
                ).format(e=str(e)),
                icon="warning",
                buttons=["Ok"],
            )

    def _get_steam_library_file(self) -> Path:
        """Get Steam library file path"""
        steam_path = self._find_steam_path()
        library_file = steam_path / "steamapps" / "libraryfolders.vdf"
        if not library_file.exists():
            raise Exception(f"Steam library file not found: {library_file}")
        return library_file

    def _on_steam_repair_library_clicked(self) -> None:
        """Repair Steam library by validating all installed games."""
        try:
            # get library file and parse app IDs
            library_file = self._get_steam_library_file()
            content = library_file.read_text(encoding="utf-8")
            app_ids = re.findall(r'"appid"\s+"(\d+)"', content)

            if not app_ids:
                show_dialogue_conditional(
                    title=self.translate("TroubleshootingController", "No Games Found"),
                    text=self.translate(
                        "TroubleshootingController",
                        "No installed games found in this Steam library folder.\nYou may have games installed in a different Steam library folder or drive.",
                    ),
                    icon="warning",
                    buttons=["Ok"],
                )
                return

            # ask for confirmation since this will validate all games
            if not show_dialogue_conditional(
                title=self.translate(
                    "TroubleshootingController", "Confirm Library Repair"
                ),
                text=self.translate(
                    "TroubleshootingController",
                    "This will verify all {len} games in your Steam library.\nThis may take a while. Continue?",
                ).format(len=len(app_ids)),
            ):
                return

            # validate each game
            from app.utils.generic import platform_specific_open

            for app_id in app_ids:
                platform_specific_open(f"steam://validate/{app_id}")

            show_dialogue_conditional(
                title=self.translate(
                    "TroubleshootingController", "Library Repair Started"
                ),
                text=self.translate(
                    "TroubleshootingController",
                    "Steam will now verify {len} games.\nYou can monitor progress in the Steam client.",
                ).format(len=len(app_ids)),
                icon="info",
            )

        except Exception as e:
            logger.error(f"Failed to repair Steam library: {e}")
            show_dialogue_conditional(
                title=self.translate(
                    "TroubleshootingController", "Steam Action Failed"
                ),
                text=self.translate(
                    "TroubleshootingController",
                    "Could not repair Steam library.\nPlease verify your games manually through Steam.\nDetails: {e}",
                ).format(e=str(e)),
                icon="warning",
            )

    def show_location_warning(self) -> None:
        show_information(
            title=self.translate("TroubleshootingController", "Location Error"),
            text=self.translate(
                "TroubleshootingController",
                "Path not set, Please check your settings and Try again.",
            ),
        )

    def show_failed_warning(self, item: Path | str, e: Exception) -> None:
        show_warning(
            title=self.translate("TroubleshootingController", "Process failed"),
            text=self.translate(
                "TroubleshootingController", "Could not process: {item}"
            ).format(item=item),
            information=self.translate(
                "TroubleshootingController",
                "Failed to process item: {item} due to the following error: {e}",
            ).format(item=item, e=str(e)),
        )

    def show_steam_user_warning(self) -> None:
        show_warning(
            title=self.translate(
                "TroubleshootingController", "Steam user Check failed"
            ),
            text=self.translate(
                "TroubleshootingController",
                "You are not a Steam user, or Path not set, Please check settings and try again.",
            ),
        )
