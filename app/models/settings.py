import json
import sys
from json import JSONDecodeError
from os import path, rename
from pathlib import Path
from shutil import copy2, copytree, rmtree
from time import time
from typing import Any, Dict

import msgspec
from loguru import logger
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from app.controllers.instance_controller import InstanceController
from app.models.instance import Instance
from app.utils.acf_utils import validate_acf_file_exists
from app.utils.app_info import AppInfo
from app.utils.constants import (
    DEFAULT_INSTANCE_NAME,
    INSTANCE_FOLDER_NAME,
    STEAM_FOLDER_NAME,
    STEAMCMD_FOLDER_NAME,
    SortMethod,
)
from app.utils.event_bus import EventBus
from app.utils.generic import handle_remove_read_only
from app.views.dialogue import BinaryChoiceDialog, InformationBox


class Settings(QObject):
    MIN_SIZE = 400
    MAX_SIZE = 1600
    DEFAULT_WIDTH = 900
    DEFAULT_HEIGHT = 600

    @staticmethod
    def validate_window_custom_size(width: int, height: int) -> tuple[int, int]:
        """Validate custom width and height, resetting to defaults if out of range."""
        if not (Settings.MIN_SIZE <= width <= Settings.MAX_SIZE):
            width = Settings.DEFAULT_WIDTH
        if not (Settings.MIN_SIZE <= height <= Settings.MAX_SIZE):
            height = Settings.DEFAULT_HEIGHT
        return width, height

    def __init__(self) -> None:
        super().__init__()

        self._settings_file = AppInfo().app_settings_file
        self._debug_file = AppInfo().app_storage_folder / "DEBUG"

        # RimSort Update check
        self.check_for_update_startup: bool = True

        # Databases
        self.external_steam_metadata_source: str = "None"
        self.external_steam_metadata_file_path: str = str(
            AppInfo().app_storage_folder / "steamDB.json"
        )
        self.external_steam_metadata_repo: str = (
            "https://github.com/RimSort/Steam-Workshop-Database"
        )

        self.external_community_rules_metadata_source: str = "None"
        self.external_community_rules_file_path: str = str(
            AppInfo().app_storage_folder / "communityRules.json"
        )
        self.external_community_rules_repo: str = (
            "https://github.com/RimSort/Community-Rules-Database"
        )

        # Disable by default previously this was 7 days "604800"
        self.database_expiry: int = 0
        # Default (-1) means do not delete data from Aux Metadata DB
        self.aux_db_time_limit: int = -1

        self.external_no_version_warning_metadata_source: str = "None"
        self.external_no_version_warning_file_path: str = str(
            AppInfo().app_storage_folder / "ModIdsToFix.xml"
        )
        self.external_no_version_warning_repo_path: str = (
            "https://github.com/emipa606/NoVersionWarning"
        )

        self.external_use_this_instead_metadata_source: str = "None"
        self.external_use_this_instead_file_path: str = str(
            AppInfo().app_storage_folder / "UseThisInstead" / "replacements.json.gz"
        )
        self.external_use_this_instead_repo_path: str = (
            "https://github.com/emipa606/UseThisInstead"
        )

        # Sorting
        self.sorting_algorithm: SortMethod = SortMethod.TOPOLOGICAL
        # Whether to use moddependencies as loadTheseBefore rules
        self.use_moddependencies_as_loadTheseBefore: bool = False
        # Whether to use alternativePackageIds as satisfying dependencies
        self.use_alternative_package_ids_as_satisfying_dependencies: bool = True
        # Whether to check for missing dependencies when sorting
        self.check_dependencies_on_sort: bool = True

        # XML parsing behavior
        # If enabled, About.xml *ByVersion tags take precedence over base tags
        # e.g., modDependenciesByVersion, loadAfterByVersion, loadBeforeByVersion, incompatibleWithByVersion, descriptionsByVersion
        self.prefer_versioned_about_tags: bool = True

        # Whether to notify user about missing mods
        self.try_download_missing_mods: bool = True
        # Whether to notify user about duplicate mods
        self.duplicate_mods_warning: bool = True
        # Whether to enable Mod type filter
        self.mod_type_filter: bool = True
        # Whether to hide invalid mods
        self.hide_invalid_mods_when_filtering: bool = False
        # Whether to enable inactive mods sorting options
        self.inactive_mods_sorting: bool = True
        # Inactive mods sort state saving
        self.save_inactive_mods_sort_state: bool = False
        self.inactive_mods_sort_key: str = "FILESYSTEM_MODIFIED_TIME"
        self.inactive_mods_sort_descending: bool = True

        # Data source filter state (0 = All)
        self.active_mods_data_source_filter_index: int = 0
        self.inactive_mods_data_source_filter_index: int = 0

        # DB Builder
        self.db_builder_include: str = "all_mods"
        self.build_steam_database_dlc_data: bool = True
        self.build_steam_database_update_toggle: bool = False
        self.steam_apikey: str = ""

        # SteamCMD
        self.steamcmd_validate_downloads: bool = True
        self.steamcmd_delete_before_update: bool = False

        # todds
        self.todds_preset: str = "optimized"
        self.todds_custom_command: str = ""
        self.todds_active_mods_target: bool = True
        self.todds_dry_run: bool = False
        self.todds_overwrite: bool = False
        self.auto_delete_orphaned_dds: bool = False
        self.auto_run_todds_before_launch: bool = False

        # External Tools
        self.text_editor_location: str = ""
        self.text_editor_folder_arg: str = ""
        self.text_editor_file_arg: str = ""

        # Theme
        self.enable_themes: bool = True
        self.theme_name: str = "RimPy"

        self.font_family: str = QApplication.font().family()
        self.font_size: int = 12

        # Language
        self.language = "en_US"

        # Launch state
        # Dialogue positioning
        self.constrain_dialogues_to_main_window_monitor: bool = False

        # Launch state setting: "maximized", "normal", or "custom"
        # Main Window
        self.main_window_launch_state: str = "maximized"
        self.main_window_custom_width: int = 900
        self.main_window_custom_height: int = 600

        # Browser Window
        self.browser_window_launch_state: str = "maximized"
        self.browser_window_custom_width: int = 900
        self.browser_window_custom_height: int = 600

        # Settings Window
        self.settings_window_launch_state: str = "custom"
        self.settings_window_custom_width: int = 900
        self.settings_window_custom_height: int = 600

        # Advanced
        self.debug_logging_enabled: bool = False
        self.watchdog_toggle: bool = True

        # Backups
        self.backup_saves_on_launch: bool = False
        self.last_backup_date: str = ""
        self.auto_backup_retention_count: int = 10
        self.auto_backup_compression_count: int = 10
        self.steam_mods_update_check: bool = False
        self.render_unity_rich_text: bool = True
        self.update_databases_on_startup: bool = True
        self.include_mod_notes_in_mod_name_filter: bool = False
        # UI: Save-comparison labels and icons
        self.show_save_comparison_indicators: bool = True
        # Clear button behavior
        self.clear_moves_dlc: bool = False

        # Update backup settings
        self.enable_backup_before_update: bool = True
        self.max_backups: int = 3

        # Authentication
        self.rentry_auth_code: str = ""
        self.github_username: str = ""
        self.github_token: str = ""

        # Auxiliary Metadata DB
        self.enable_aux_db_behavior_editing: bool = False

        # Player Log
        self.auto_load_player_log_on_startup: bool = False

        # Instances
        self.current_instance: str = DEFAULT_INSTANCE_NAME
        self.current_instance_path: str = str(
            Path(AppInfo().app_storage_folder)
            / INSTANCE_FOLDER_NAME
            / self.current_instance
        )
        self.instances: dict[str, Instance] = {DEFAULT_INSTANCE_NAME: Instance()}

        # Color Picker Custom Colors (Store as hex)
        self.color_picker_custom_colors: list[str] = []

        # Active mod list dividers: list of {uuid, name, collapsed, index}
        self.active_mods_dividers: list[dict[str, Any]] = []

    @property
    def aux_db_path(self) -> Path:
        """
        Get the path to the auxiliary metadata database for the current instance.
        """

        instance = self.instances[self.current_instance]
        # Default instance never uses override
        override = (
            ""
            if self.current_instance == DEFAULT_INSTANCE_NAME
            else instance.instance_folder_override
        )
        instance_path = InstanceController.get_instance_folder_path(
            self.current_instance, override
        )
        return instance_path / "aux_metadata.db"

    def __setattr__(self, key: str, value: Any) -> None:
        # If private attribute, set it normally
        if key.startswith("_"):
            super().__setattr__(key, value)
            return

        if hasattr(self, key) and getattr(self, key) == value:
            return
        super().__setattr__(key, value)
        EventBus().settings_have_changed.emit()

    def load(self) -> None:
        if self._debug_file.exists() and self._debug_file.is_file():
            self.debug_logging_enabled = True
        else:
            self.debug_logging_enabled = False

        try:
            with open(str(self._settings_file), "r") as file:
                data = json.load(file)
                # Assume there are mitigations unless we reach else block
                mitigations = True
                # Mitigate issues when "instances" key is not parsed, but the old path attributes are present
                if not data.get("instances"):
                    logger.debug(
                        "Instances key not found in settings.json. Performing mitigation."
                    )
                    steamcmd_prefix_default_instance_path = str(
                        Path(
                            AppInfo().app_storage_folder
                            / INSTANCE_FOLDER_NAME
                            / DEFAULT_INSTANCE_NAME
                        )
                    )
                    # Create Default instance
                    data["instances"] = {
                        DEFAULT_INSTANCE_NAME: Instance(
                            name=DEFAULT_INSTANCE_NAME,
                            game_folder=data.get("game_folder", ""),
                            local_folder=data.get("local_folder", ""),
                            workshop_folder=data.get("workshop_folder", ""),
                            config_folder=data.get("config_folder", ""),
                            run_args=data.get("run_args", []),
                            steamcmd_install_path=steamcmd_prefix_default_instance_path,
                            steam_client_integration=False,
                        )
                    }
                    steamcmd_prefix_to_mitigate = data.get("steamcmd_install_path", "")
                    steamcmd_path_to_mitigate = str(
                        Path(steamcmd_prefix_to_mitigate) / STEAMCMD_FOLDER_NAME
                    )
                    steam_path_to_mitigate = str(
                        Path(steamcmd_prefix_to_mitigate) / STEAM_FOLDER_NAME
                    )
                    if steamcmd_prefix_to_mitigate and path.exists(
                        steamcmd_prefix_to_mitigate
                    ):
                        logger.debug(
                            "Configured SteamCMD install path found. Attempting to migrate it to the Default instance path..."
                        )
                        steamcmd_prefix_steamcmd_path = str(
                            Path(steamcmd_prefix_default_instance_path)
                            / STEAMCMD_FOLDER_NAME
                        )
                        steamcmd_prefix_steam_path = str(
                            Path(steamcmd_prefix_default_instance_path)
                            / STEAM_FOLDER_NAME
                        )
                        try:
                            if path.exists(steamcmd_prefix_steamcmd_path):
                                current_timestamp = int(time())
                                rename(
                                    steamcmd_prefix_steamcmd_path,
                                    f"{steamcmd_prefix_steamcmd_path}_{current_timestamp}",
                                )
                            elif path.exists(steamcmd_prefix_steam_path):
                                current_timestamp = int(time())
                                rename(
                                    steamcmd_prefix_steam_path,
                                    f"{steamcmd_prefix_steam_path}_{current_timestamp}",
                                )
                            logger.info(
                                f"Migrated SteamCMD install path from {steamcmd_prefix_to_mitigate} to {steamcmd_prefix_default_instance_path}"
                            )
                            copytree(
                                steamcmd_path_to_mitigate,
                                steamcmd_prefix_steamcmd_path,
                                symlinks=True,
                            )
                            logger.info(
                                f"Deleting old SteamCMD install path at {steamcmd_path_to_mitigate}..."
                            )
                            rmtree(
                                steamcmd_path_to_mitigate,
                                ignore_errors=False,
                                onerror=handle_remove_read_only,
                            )
                            logger.info(
                                f"Migrated SteamCMD data path from {steam_path_to_mitigate} to {steamcmd_prefix_default_instance_path}"
                            )
                            copytree(
                                steam_path_to_mitigate,
                                steamcmd_prefix_steam_path,
                                symlinks=True,
                            )
                            logger.info(
                                f"Deleting old SteamCMD data path at {steam_path_to_mitigate}..."
                            )
                            rmtree(
                                steam_path_to_mitigate,
                                ignore_errors=False,
                                onerror=handle_remove_read_only,
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to migrate SteamCMD install path. Error: {e}"
                            )
                elif (
                    not data.get("current_instance")
                    or data["current_instance"] not in data["instances"]
                ):
                    logger.debug(
                        "Current instance not found in settings.json. Performing mitigation."
                    )
                    data["current_instance"] = DEFAULT_INSTANCE_NAME

                    new_path = str(
                        Path(AppInfo().app_storage_folder)
                        / "instances"
                        / data.get("current_instance")
                    )
                    data["current_instance_path"] = new_path
                elif not data.get("current_instance_path"):
                    new_path = str(
                        Path(AppInfo().app_storage_folder)
                        / "instances"
                        / data.get("current_instance")
                    )
                    data["current_instance_path"] = new_path
                else:
                    # There was nothing to mitigate, so don't save the model to the file
                    mitigations = False
                # Parse data from settings.json into the model
                self._from_dict(data)
                # Validate Steam integration configuration after loading
                config_fixed = self._validate_steam_integration_config()
                # Save the model to the file if there were mitigations or config fixes
                if mitigations or config_fixed:
                    self.save()
                else:
                    # Update .backup only if no mitigations/config fixing took place
                    # This might prevent overwriting a good/better backup
                    self.update_backup()

        except FileNotFoundError:
            self.save()
        except JSONDecodeError:
            self.handle_corrupted_settings()

    def save(self) -> None:
        if self.debug_logging_enabled:
            self._debug_file.touch(exist_ok=True)
        else:
            self._debug_file.unlink(missing_ok=True)

        with open(str(self._settings_file), "w") as file:
            json.dump(self._to_dict(), file, indent=4)

    def handle_corrupted_settings(self) -> None:
        use_old_backup = False
        msg = "Your settings file seems to be corrupted and cannot be loaded. "
        if (AppInfo().settings_backups_folder / "settings.json.backup").exists():
            msg += (
                f"RimSort found a backup at {AppInfo().settings_backups_folder / "settings.json.backup"}. "
                "Do you want to attempt to recover your settings from this backup?"
            )
        elif (AppInfo().settings_backups_folder / "settings.json.backup.old").exists():
            msg += (
                f"RimSort found an old backup at {AppInfo().settings_backups_folder / "settings.json.backup.old"}. "
                "Do you want to attempt to recover your settings from this backup?"
            )
            use_old_backup = True
        else:
            msg += "No backup file was found, RimSort will reset your settings to defaults."

        dlg = BinaryChoiceDialog(
            title=self.tr("Settings Load Error"),
            text=self.tr(msg),
            information=self.tr(f"If you proceed, a backup of the corrupted file will be saved to {AppInfo().settings_backups_folder / "settings.json.corrupted"}."),
            positive_text=self.tr("Proceed"),
            negative_text=self.tr("Exit RimSort"),
        )
        if dlg.exec_is_positive():
            try:
                self.recover_backup(use_old_backup=use_old_backup)
            except Exception as e:
                logger.error(f"Failed to recover settings from backup: {e}")
                InformationBox(
                    title=self.tr("Settings Recovery Failed"),
                    text=self.tr(
                        "RimSort failed to recover your settings from the backup. "
                        f"You may be able to manually recover your settings by restoring \"settings.json.backup\" or \"settings.json.backup.old\" from {AppInfo().settings_backups_folder} to {self._settings_file}."
                        ),
                ).exec()
        else:
            sys.exit(0)

    def update_backup(self) -> bool:
        backups_dir = AppInfo().settings_backups_folder

        backup_path = backups_dir / f"{self._settings_file.name}.backup"
        backup_old_path = backups_dir / f"{self._settings_file.name}.backup.old"
        try:
            if backup_path.exists():
                copy2(backup_path, backup_old_path)
            if self._settings_file.exists():
                copy2(self._settings_file, backup_path)
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to update settings backup: {e}")
            return False
        
    def recover_backup(self, use_old_backup: bool = False) -> bool:
        logger.info("Attempting to recover settings from backup...")
        try:
            backups_dir = AppInfo().settings_backups_folder

            backup_path = backups_dir / f"{self._settings_file.name}.backup"
            backup_old_path = backups_dir / f"{self._settings_file.name}.backup.old"
            corrupted_path = backups_dir / f"{self._settings_file.name}.corrupted"

            if self._settings_file.exists():
                copy2(self._settings_file, corrupted_path)

            if backup_path.exists():
                copy2(backup_path, self._settings_file)
            elif use_old_backup and backup_old_path.exists():
                copy2(backup_old_path, self._settings_file)
            else:
                logger.info("No backup settings file found. Resetting to defaults.")
                self._settings_file.unlink()
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to recover settings from backup: {e}")
            return False

    def _from_dict(self, data: Dict[str, Any]) -> None:
        special_attributes = ["instances"]

        for key, value in data.items():
            if key in special_attributes:
                continue
            if not hasattr(self, key):
                continue
            setattr(self, key, value)

        if "instances" in data:
            # Convert to Instance objects
            instances = {}
            for instance_name, instance_data in data["instances"].items():
                if isinstance(instance_data, Instance):
                    instances[instance_name] = instance_data
                elif isinstance(instance_data, dict):
                    instances[instance_name] = msgspec.convert(instance_data, Instance)
                else:
                    logger.warning(
                        f"Instance data for {instance_name} is not a valid type: {type(instance_data)}"
                    )
            self.instances = instances

    def _to_dict(self, skip_private: bool = True) -> Dict[str, Any]:
        special_attributes = ["instances"]
        skip_attributes = ["destroyed", "objectNameChanged"]

        data = {}

        for key, value in self.__dict__.items():
            if key in special_attributes:
                continue
            if key in skip_attributes:
                continue
            if skip_private and key.startswith("_"):
                continue
            data[key] = value

        # Serialize instances using msgspec
        instances_dict = {}
        for name, instance in self.instances.items():
            instances_dict[name] = msgspec.json.decode(
                msgspec.json.encode(instance), type=dict
            )
        data["instances"] = instances_dict
        return data

    def _validate_steam_integration_config(self) -> bool:
        """
        Validate and fix Steam client integration configuration.

        Ensures that Steam client integration settings are valid:
        - If steam_client_integration is enabled but workshop_folder is not set, disable it.
        - If workshop_folder is set but the appworkshop_294100.acf file is missing,
          disable steam_client_integration and clear workshop_folder.
        - If launch_via_steam_protocol is enabled but steam_client_integration is disabled, disable it.

        Invalid configurations are silently fixed without user interaction.

        :return: True if configuration was fixed, False if no changes were made.
        """
        active_instance = self.instances[self.current_instance]
        steam_client_integration = active_instance.steam_client_integration
        workshop_folder = active_instance.workshop_folder
        launch_via_steam_protocol = active_instance.launch_via_steam_protocol

        # If neither is enabled, no validation needed
        if (
            not steam_client_integration
            and not workshop_folder
            and not launch_via_steam_protocol
        ):
            return False

        # If launch_via_steam_protocol is enabled but steam_client_integration is not, disable it
        if launch_via_steam_protocol and not steam_client_integration:
            logger.warning(
                "Steam protocol launch is enabled but Steam client integration is disabled. Disabling..."
            )
            active_instance.launch_via_steam_protocol = False
            return True

        # If steam_client_integration is enabled but workshop_folder is not set, disable it
        if steam_client_integration and not workshop_folder:
            logger.warning(
                "Steam client integration is enabled but workshop folder is not configured. Disabling..."
            )
            active_instance.steam_client_integration = False
            return True

        # If workshop_folder is set, validate that the ACF file exists
        if workshop_folder and not validate_acf_file_exists(workshop_folder):
            logger.warning(
                f"ACF file not found for workshop folder: {workshop_folder}. "
                "Disabling Steam client integration and clearing workshop folder..."
            )
            active_instance.steam_client_integration = False
            active_instance.workshop_folder = ""
            return True

        return False
