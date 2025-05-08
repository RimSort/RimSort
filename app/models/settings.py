import json
from json import JSONDecodeError
from os import path, rename
from pathlib import Path
from shutil import copytree, rmtree
from time import time
from typing import Any, Dict

import msgspec
from loguru import logger
from PySide6.QtCore import QObject

from app.models.instance import Instance
from app.utils.app_info import AppInfo
from app.utils.constants import SortMethod
from app.utils.event_bus import EventBus
from app.utils.generic import handle_remove_read_only


class Settings(QObject):
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

        self.database_expiry: int = 604800  # 7 days

        self.external_no_version_warning_metadata_source: str = "None"
        self.external_no_version_warning_file_path: str = str(
            AppInfo().app_storage_folder / "ModIdsToFix.xml"
        )
        self.external_no_version_warning_repo_path: str = (
            "https://github.com/emipa606/NoVersionWarning"
        )

        self.external_use_this_instead_metadata_source: str = "None"
        self.external_use_this_instead_file_path: str = str(
            AppInfo().app_storage_folder / "UseThisInstead"
        )
        self.external_use_this_instead_repo_path: str = (
            "https://github.com/emipa606/UseThisInstead"
        )

        # Sorting
        self.sorting_algorithm: SortMethod = SortMethod.TOPOLOGICAL
        self.check_dependencies_on_sort: bool = (
            True  # Whether to check for missing dependencies when sorting
        )

        # DB Builder
        self.db_builder_include: str = "all_mods"
        self.build_steam_database_dlc_data: bool = True
        self.build_steam_database_update_toggle: bool = False
        self.steam_apikey: str = ""

        # SteamCMD
        self.steamcmd_validate_downloads: bool = True

        # todds
        self.todds_preset: str = "optimized"
        self.todds_active_mods_target: bool = True
        self.todds_dry_run: bool = False
        self.todds_overwrite: bool = False

        # Theme
        self.enable_themes: bool = True
        self.theme_name: str = "RimPy"

        # Advanced
        self.debug_logging_enabled: bool = False
        self.watchdog_toggle: bool = True
        self.mod_type_filter_toggle: bool = True
        self.hide_invalid_mods_when_filtering_toggle: bool = False
        self.duplicate_mods_warning: bool = False
        self.steam_mods_update_check: bool = False
        self.try_download_missing_mods: bool = False
        self.render_unity_rich_text: bool = True

        self.rentry_auth_code: str = ""

        self.github_username: str = ""
        self.github_token: str = ""

        # Instances
        self.current_instance: str = "Default"
        self.instances: dict[str, Instance] = {"Default": Instance()}

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
                mitigations = (
                    True  # Assume there are mitigations unless we reach else block
                )
                # Mitigate issues when "instances" key is not parsed, but the old path attributes are present
                if not data.get("instances"):
                    logger.debug(
                        "Instances key not found in settings.json. Performing mitigation."
                    )
                    steamcmd_prefix_default_instance_path = str(
                        Path(AppInfo().app_storage_folder / "instances" / "Default")
                    )
                    # Create Default instance
                    data["instances"] = {
                        "Default": Instance(
                            name="Default",
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
                        Path(steamcmd_prefix_to_mitigate) / "steamcmd"
                    )
                    steam_path_to_mitigate = str(
                        Path(steamcmd_prefix_to_mitigate) / "steam"
                    )
                    if steamcmd_prefix_to_mitigate and path.exists(
                        steamcmd_prefix_to_mitigate
                    ):
                        logger.debug(
                            "Configured SteamCMD install path found. Attempting to migrate it to the Default instance path..."
                        )
                        steamcmd_prefix_steamcmd_path = str(
                            Path(steamcmd_prefix_default_instance_path) / "steamcmd"
                        )
                        steamcmd_prefix_steam_path = str(
                            Path(steamcmd_prefix_default_instance_path) / "steam"
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
                    data["current_instance"] = "Default"
                else:
                    # There was nothing to mitigate, so don't save the model to the file
                    mitigations = False
                # Parse data from settings.json into the model
                self._from_dict(data)
                # Save the model to the file if there were mitigations
                if mitigations:
                    self.save()
        except FileNotFoundError:
            self.save()
        except JSONDecodeError:
            raise

    def save(self) -> None:
        if self.debug_logging_enabled:
            self._debug_file.touch(exist_ok=True)
        else:
            self._debug_file.unlink(missing_ok=True)

        with open(str(self._settings_file), "w") as file:
            json.dump(self._to_dict(), file, indent=4)

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

        data["instances"] = {
            name: instance.as_dict() for name, instance in self.instances.items()
        }
        return data
