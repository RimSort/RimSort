import json
from json import JSONDecodeError
from os import path, rename
from pathlib import Path
from shutil import copytree, rmtree
from time import time
from typing import Dict, Any, Optional, List

from PySide6.QtCore import QObject
from loguru import logger

from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus


class Settings(QObject):
    def __init__(self) -> None:
        super().__init__()

        self._settings_file = AppInfo().app_storage_folder / "settings.json"
        self._debug_file = AppInfo().app_storage_folder / "DEBUG"

        self._debug_logging_enabled: bool = False
        self._check_for_update_startup: bool = False
        self._show_folder_rows: bool = False
        self._sorting_algorithm: str = ""
        self._external_steam_metadata_file_path: str = ""
        self._external_steam_metadata_repo: str = ""
        self._external_steam_metadata_source: str = ""
        self._external_community_rules_file_path: str = ""
        self._external_community_rules_repo: str = ""
        self._external_community_rules_metadata_source: str = ""
        self._db_builder_include: str = ""
        self._database_expiry: int = 0
        self._build_steam_database_dlc_data: bool = False
        self._build_steam_database_update_toggle: bool = False
        self._watchdog_toggle: bool = False
        self._mod_type_filter_toggle: bool = False
        self._duplicate_mods_warning: bool = False
        self._steam_mods_update_check: bool = False
        self._try_download_missing_mods: bool = False
        self._steamcmd_validate_downloads: bool = False
        self._todds_preset: str = ""
        self._todds_active_mods_target: bool = False
        self._todds_dry_run: bool = False
        self._todds_overwrite: bool = False
        self._current_instance: Optional[str] = None
        self._instances: dict[str, dict[str, Any]] = {}
        self._stylesheet_enabled: bool = False
        self._github_username: str = ""
        self._github_token: str = ""
        self._steam_apikey: str = ""
        self.apply_default_settings()

    def apply_default_settings(self) -> None:
        self._debug_logging_enabled = False
        self._check_for_update_startup = False
        self._show_folder_rows = True
        self._sorting_algorithm = "Alphabetical"
        self._external_steam_metadata_file_path = str(
            AppInfo().app_storage_folder / "steamDB.json"
        )
        self._external_steam_metadata_repo = (
            "https://github.com/RimSort/Steam-Workshop-Database"
        )
        self._external_steam_metadata_source = "None"
        self._external_community_rules_file_path = str(
            AppInfo().app_storage_folder / "communityRules.json"
        )
        self._external_community_rules_repo = (
            "https://github.com/RimSort/Community-Rules-Database"
        )
        self._external_community_rules_metadata_source = "None"
        self._db_builder_include = "all_mods"
        self._database_expiry = 604800
        self._build_steam_database_dlc_data = True
        self._build_steam_database_update_toggle = False
        self._watchdog_toggle = True
        self._mod_type_filter_toggle = True
        self._duplicate_mods_warning = False
        self._steam_mods_update_check = False
        self._try_download_missing_mods = False
        self._steamcmd_validate_downloads = True
        self._todds_preset = "optimized"
        self._todds_active_mods_target = True
        self._todds_dry_run = False
        self._todds_overwrite = False
        self._current_instance = "Default"
        self._instances: Dict[str, Dict[str, str]] = {
            "Default": {
                "game_folder": "",
                "config_folder": "",
                "local_folder": "",
                "workshop_folder": "",
                "run_args": [],
                "steamcmd_install_path": str(
                    Path(AppInfo().app_storage_folder / "instances" / "Default")
                ),
            }
        }
        self._stylesheet_enabled = True
        self._github_username = ""
        self._github_token = ""
        self._steam_apikey = ""

    @property
    def debug_logging_enabled(self) -> bool:
        return self._debug_logging_enabled

    @debug_logging_enabled.setter
    def debug_logging_enabled(self, value: bool) -> None:
        if value == self._debug_logging_enabled:
            return
        self._debug_logging_enabled = value
        EventBus().settings_have_changed.emit()

    @property
    def check_for_update_startup(self) -> bool:
        return self._check_for_update_startup

    @check_for_update_startup.setter
    def check_for_update_startup(self, value: bool) -> None:
        if value == self._check_for_update_startup:
            return
        self._check_for_update_startup = value
        EventBus().settings_have_changed.emit()

    @property
    def show_folder_rows(self) -> bool:
        return self._show_folder_rows

    @show_folder_rows.setter
    def show_folder_rows(self, value: bool) -> None:
        if value == self._show_folder_rows:
            return
        self._show_folder_rows = value
        EventBus().settings_have_changed.emit()

    @property
    def sorting_algorithm(self) -> str:
        return self._sorting_algorithm

    @sorting_algorithm.setter
    def sorting_algorithm(self, value: str) -> None:
        if value == self._sorting_algorithm:
            return
        self._sorting_algorithm = value
        EventBus().settings_have_changed.emit()

    @property
    def external_steam_metadata_file_path(self) -> str:
        return self._external_steam_metadata_file_path

    @external_steam_metadata_file_path.setter
    def external_steam_metadata_file_path(self, value: str) -> None:
        if value == self._external_steam_metadata_file_path:
            return
        self._external_steam_metadata_file_path = value
        EventBus().settings_have_changed.emit()

    @property
    def external_steam_metadata_repo(self) -> str:
        return self._external_steam_metadata_repo

    @external_steam_metadata_repo.setter
    def external_steam_metadata_repo(self, value: str) -> None:
        if value == self._external_steam_metadata_repo:
            return
        self._external_steam_metadata_repo = value
        EventBus().settings_have_changed.emit()

    @property
    def external_steam_metadata_source(self) -> str:
        return self._external_steam_metadata_source

    @external_steam_metadata_source.setter
    def external_steam_metadata_source(self, value: str) -> None:
        if value == self._external_steam_metadata_source:
            return
        self._external_steam_metadata_source = value
        EventBus().settings_have_changed.emit()

    @property
    def external_community_rules_file_path(self) -> str:
        return self._external_community_rules_file_path

    @external_community_rules_file_path.setter
    def external_community_rules_file_path(self, value: str) -> None:
        if value == self._external_community_rules_file_path:
            return
        self._external_community_rules_file_path = value
        EventBus().settings_have_changed.emit()

    @property
    def external_community_rules_repo(self) -> str:
        return self._external_community_rules_repo

    @external_community_rules_repo.setter
    def external_community_rules_repo(self, value: str) -> None:
        if value == self._external_community_rules_repo:
            return
        self._external_community_rules_repo = value
        EventBus().settings_have_changed.emit()

    @property
    def external_community_rules_metadata_source(self) -> str:
        return self._external_community_rules_metadata_source

    @external_community_rules_metadata_source.setter
    def external_community_rules_metadata_source(self, value: str) -> None:
        if value == self._external_community_rules_metadata_source:
            return
        self._external_community_rules_metadata_source = value
        EventBus().settings_have_changed.emit()

    @property
    def db_builder_include(self) -> str:
        return self._db_builder_include

    @db_builder_include.setter
    def db_builder_include(self, value: str) -> None:
        if value == self._db_builder_include:
            return
        self._db_builder_include = value
        EventBus().settings_have_changed.emit()

    @property
    def database_expiry(self) -> int:
        return self._database_expiry

    @database_expiry.setter
    def database_expiry(self, value: int) -> None:
        if value == self._database_expiry:
            return
        self._database_expiry = value
        EventBus().settings_have_changed.emit()

    @property
    def build_steam_database_dlc_data(self) -> bool:
        return self._build_steam_database_dlc_data

    @build_steam_database_dlc_data.setter
    def build_steam_database_dlc_data(self, value: bool) -> None:
        if value == self._build_steam_database_dlc_data:
            return
        self._build_steam_database_dlc_data = value
        EventBus().settings_have_changed.emit()

    @property
    def build_steam_database_update_toggle(self) -> bool:
        return self._build_steam_database_update_toggle

    @build_steam_database_update_toggle.setter
    def build_steam_database_update_toggle(self, value: bool) -> None:
        if value == self._build_steam_database_update_toggle:
            return
        self._build_steam_database_update_toggle = value
        EventBus().settings_have_changed.emit()

    @property
    def watchdog_toggle(self) -> bool:
        return self._watchdog_toggle

    @watchdog_toggle.setter
    def watchdog_toggle(self, value: bool) -> None:
        if value == self._watchdog_toggle:
            return
        self._watchdog_toggle = value
        EventBus().settings_have_changed.emit()

    @property
    def mod_type_filter_toggle(self) -> bool:
        return self._mod_type_filter_toggle

    @mod_type_filter_toggle.setter
    def mod_type_filter_toggle(self, value: bool) -> None:
        if value == self._mod_type_filter_toggle:
            return
        self._mod_type_filter_toggle = value
        EventBus().settings_have_changed.emit()

    @property
    def duplicate_mods_warning(self) -> bool:
        return self._duplicate_mods_warning

    @duplicate_mods_warning.setter
    def duplicate_mods_warning(self, value: bool) -> None:
        if value == self._duplicate_mods_warning:
            return
        self._duplicate_mods_warning = value
        EventBus().settings_have_changed.emit()

    @property
    def steam_mods_update_check(self) -> bool:
        return self._steam_mods_update_check

    @steam_mods_update_check.setter
    def steam_mods_update_check(self, value: bool) -> None:
        if value == self._steam_mods_update_check:
            return
        self._steam_mods_update_check = value
        EventBus().settings_have_changed.emit()

    @property
    def try_download_missing_mods(self) -> bool:
        return self._try_download_missing_mods

    @try_download_missing_mods.setter
    def try_download_missing_mods(self, value: bool) -> None:
        if value == self._try_download_missing_mods:
            return
        self._try_download_missing_mods = value
        EventBus().settings_have_changed.emit()

    @property
    def steamcmd_validate_downloads(self) -> bool:
        return self._steamcmd_validate_downloads

    @steamcmd_validate_downloads.setter
    def steamcmd_validate_downloads(self, value: bool) -> None:
        if value == self._steamcmd_validate_downloads:
            return
        self._steamcmd_validate_downloads = value
        EventBus().settings_have_changed.emit()

    @property
    def todds_preset(self) -> str:
        return self._todds_preset

    @todds_preset.setter
    def todds_preset(self, value: str) -> None:
        if value == self._todds_preset:
            return
        self._todds_preset = value
        EventBus().settings_have_changed.emit()

    @property
    def todds_active_mods_target(self) -> bool:
        return self._todds_active_mods_target

    @todds_active_mods_target.setter
    def todds_active_mods_target(self, value: bool) -> None:
        if value == self._todds_active_mods_target:
            return
        self._todds_active_mods_target = value
        EventBus().settings_have_changed.emit()

    @property
    def todds_dry_run(self) -> bool:
        return self._todds_dry_run

    @todds_dry_run.setter
    def todds_dry_run(self, value: bool) -> None:
        if value == self._todds_dry_run:
            return
        self._todds_dry_run = value
        EventBus().settings_have_changed.emit()

    @property
    def todds_overwrite(self) -> bool:
        return self._todds_overwrite

    @todds_overwrite.setter
    def todds_overwrite(self, value: bool) -> None:
        if value == self._todds_overwrite:
            return
        self._todds_overwrite = value
        EventBus().settings_have_changed.emit()

    @property
    def current_instance(self) -> str:
        return self._current_instance

    @current_instance.setter
    def current_instance(self, value: str) -> None:
        if value == self._current_instance:
            return
        self._current_instance = value
        EventBus().settings_have_changed.emit()

    @property
    def instances(self) -> Dict[str, Dict[str, str]]:
        return self._instances

    @instances.setter
    def instances(self, value: Dict[str, Dict[str, str]]) -> None:
        if value == self._instances:
            return
        self._instances = value
        EventBus().settings_have_changed.emit()

    @property
    def stylesheet_enabled(self) -> bool:
        return self._stylesheet_enabled

    @stylesheet_enabled.setter
    def stylesheet_enabled(self, value: bool) -> None:
        if value == self._stylesheet_enabled:
            return
        self._stylesheet_enabled = value
        EventBus().settings_have_changed.emit()

    @property
    def github_username(self) -> str:
        return self._github_username

    @github_username.setter
    def github_username(self, value: str) -> None:
        if value == self._github_username:
            return
        self._github_username = value
        EventBus().settings_have_changed.emit()

    @property
    def github_token(self) -> str:
        return self._github_token

    @github_token.setter
    def github_token(self, value: str) -> None:
        if value == self._github_token:
            return
        self._github_token = value
        EventBus().settings_have_changed.emit()

    @property
    def steam_apikey(self) -> str:
        return self._steam_apikey

    @steam_apikey.setter
    def steam_apikey(self, value: str) -> None:
        if value == self._steam_apikey:
            return
        self._steam_apikey = value
        EventBus().settings_have_changed.emit()

    def load(self) -> None:
        if self._debug_file.exists() and self._debug_file.is_file():
            self._debug_logging_enabled = True
        else:
            self._debug_logging_enabled = False

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
                        "Default": {
                            "game_folder": data.get("game_folder", ""),
                            "local_folder": data.get("local_folder", ""),
                            "workshop_folder": data.get("workshop_folder", ""),
                            "config_folder": data.get("config_folder", ""),
                            "run_args": data.get("run_args", []),
                            "steamcmd_install_path": steamcmd_prefix_default_instance_path,
                        }
                    }
                    steamcmd_prefix_to_mitigate = data.get("steamcmd_install_path")
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
                            rmtree(steamcmd_path_to_mitigate)
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
                            rmtree(steam_path_to_mitigate)
                        except Exception as e:
                            logger.error(
                                f"Failed to migrate SteamCMD install path. Error: {e}"
                            )
                elif (
                    not data.get("current_instance")
                    or not data["current_instance"] in data["instances"]
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
        if self._debug_logging_enabled:
            self._debug_file.touch(exist_ok=True)
        else:
            self._debug_file.unlink(missing_ok=True)

        with open(str(self._settings_file), "w") as file:
            json.dump(self._to_dict(), file, indent=4)

    def _from_dict(self, data: Dict[str, Any]) -> None:
        if "show_folder_rows" in data:
            self.show_folder_rows = data["show_folder_rows"]
            del data["show_folder_rows"]

        if "check_for_update_startup" in data:
            self.check_for_update_startup = data["check_for_update_startup"]
            del data["check_for_update_startup"]

        if "sorting_algorithm" in data:
            self.sorting_algorithm = data["sorting_algorithm"]
            del data["sorting_algorithm"]

        if "external_steam_metadata_file_path" in data:
            self.external_steam_metadata_file_path = data[
                "external_steam_metadata_file_path"
            ]
            del data["external_steam_metadata_file_path"]

        if "external_steam_metadata_repo" in data:
            self.external_steam_metadata_repo = data["external_steam_metadata_repo"]
            del data["external_steam_metadata_repo"]

        if "external_steam_metadata_source" in data:
            self.external_steam_metadata_source = data["external_steam_metadata_source"]
            del data["external_steam_metadata_source"]

        if "external_community_rules_file_path" in data:
            self.external_community_rules_file_path = data[
                "external_community_rules_file_path"
            ]
            del data["external_community_rules_file_path"]

        if "external_community_rules_repo" in data:
            self.external_community_rules_repo = data["external_community_rules_repo"]
            del data["external_community_rules_repo"]

        if "external_community_rules_metadata_source" in data:
            self.external_community_rules_metadata_source = data[
                "external_community_rules_metadata_source"
            ]
            del data["external_community_rules_metadata_source"]

        if "db_builder_include" in data:
            self.db_builder_include = data["db_builder_include"]
            del data["db_builder_include"]

        if "database_expiry" in data:
            self.database_expiry = data["database_expiry"]
            del data["database_expiry"]

        if "build_steam_database_dlc_data" in data:
            self.build_steam_database_dlc_data = data["build_steam_database_dlc_data"]
            del data["build_steam_database_dlc_data"]

        if "build_steam_database_update_toggle" in data:
            self.build_steam_database_update_toggle = data[
                "build_steam_database_update_toggle"
            ]
            del data["build_steam_database_update_toggle"]

        if "watchdog_toggle" in data:
            self.watchdog_toggle = data["watchdog_toggle"]
            del data["watchdog_toggle"]

        if "mod_type_filter_toggle" in data:
            self.mod_type_filter_toggle = data["mod_type_filter_toggle"]
            del data["mod_type_filter_toggle"]

        if "duplicate_mods_warning" in data:
            self.duplicate_mods_warning = data["duplicate_mods_warning"]
            del data["duplicate_mods_warning"]

        if "steam_mods_update_check" in data:
            self.steam_mods_update_check = data["steam_mods_update_check"]
            del data["steam_mods_update_check"]

        if "try_download_missing_mods" in data:
            self.try_download_missing_mods = data["try_download_missing_mods"]
            del data["try_download_missing_mods"]

        if "steamcmd_validate_downloads" in data:
            self.steamcmd_validate_downloads = data["steamcmd_validate_downloads"]
            del data["steamcmd_validate_downloads"]

        if "todds_preset" in data:
            self.todds_preset = data["todds_preset"]
            del data["todds_preset"]

        if "todds_active_mods_target" in data:
            self.todds_active_mods_target = data["todds_active_mods_target"]
            del data["todds_active_mods_target"]

        if "todds_dry_run" in data:
            self.todds_dry_run = data["todds_dry_run"]
            del data["todds_dry_run"]

        if "todds_overwrite" in data:
            self.todds_overwrite = data["todds_overwrite"]
            del data["todds_overwrite"]

        if "current_instance" in data:
            self.current_instance = data["current_instance"]
            del data["current_instance"]

        if "instances" in data:
            self.instances = data["instances"]
            del data["instances"]

        if "stylesheet_enabled" in data:
            self.stylesheet_enabled = data["stylesheet_enabled"]
            del data["stylesheet_enabled"]

        if "github_username" in data:
            self.github_username = data["github_username"]
            del data["github_username"]

        if "github_token" in data:
            self.github_token = data["github_token"]
            del data["github_token"]

        if "steam_apikey" in data:
            self.steam_apikey = data["steam_apikey"]
            del data["steam_apikey"]

    def _to_dict(self) -> Dict[str, Any]:
        data = {
            "check_for_update_startup": self.check_for_update_startup,
            "show_folder_rows": self.show_folder_rows,
            "sorting_algorithm": self.sorting_algorithm,
            "external_steam_metadata_file_path": self.external_steam_metadata_file_path,
            "external_steam_metadata_repo": self.external_steam_metadata_repo,
            "external_steam_metadata_source": self.external_steam_metadata_source,
            "external_community_rules_file_path": self.external_community_rules_file_path,
            "external_community_rules_repo": self.external_community_rules_repo,
            "external_community_rules_metadata_source": self.external_community_rules_metadata_source,
            "db_builder_include": self.db_builder_include,
            "database_expiry": self.database_expiry,
            "build_steam_database_dlc_data": self.build_steam_database_dlc_data,
            "build_steam_database_update_toggle": self.build_steam_database_update_toggle,
            "watchdog_toggle": self.watchdog_toggle,
            "mod_type_filter_toggle": self.mod_type_filter_toggle,
            "duplicate_mods_warning": self.duplicate_mods_warning,
            "steam_mods_update_check": self.steam_mods_update_check,
            "try_download_missing_mods": self.try_download_missing_mods,
            "steamcmd_validate_downloads": self.steamcmd_validate_downloads,
            "todds_preset": self.todds_preset,
            "todds_active_mods_target": self.todds_active_mods_target,
            "todds_dry_run": self.todds_dry_run,
            "todds_overwrite": self.todds_overwrite,
            "current_instance": self.current_instance,
            "instances": self.instances,
            "stylesheet_enabled": self.stylesheet_enabled,
            "github_username": self.github_username,
            "github_token": self.github_token,
            "steam_apikey": self.steam_apikey,
        }
        return data
