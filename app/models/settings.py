import json
from json import JSONDecodeError
from pathlib import Path
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
        self._steamcmd_install_path: str = ""
        self._steamcmd_validate_downloads: bool = False
        self._todds_preset: str = ""
        self._todds_active_mods_target: bool = False
        self._todds_dry_run: bool = False
        self._todds_overwrite: bool = False
        self._game_folder: Optional[Path] = None
        self._config_folder: Optional[Path] = None
        self._local_folder: Optional[Path] = None
        self._workshop_folder: Optional[Path] = None
        self._github_username: str = ""
        self._github_token: str = ""
        self._steam_apikey: str = ""
        self._run_args: List[str] = []

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
        self._steamcmd_install_path = str(AppInfo().app_storage_folder)
        self._steamcmd_validate_downloads = True
        self._todds_preset = "optimized"
        self._todds_active_mods_target = True
        self._todds_dry_run = False
        self._todds_overwrite = False
        self._game_folder = None
        self._config_folder = None
        self._local_folder = None
        self._workshop_folder = None
        self._github_username = ""
        self._github_token = ""
        self._steam_apikey = ""
        self._run_args = []

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
    def steamcmd_install_path(self) -> str:
        return self._steamcmd_install_path

    @steamcmd_install_path.setter
    def steamcmd_install_path(self, value: str) -> None:
        if value == self._steamcmd_install_path:
            return
        self._steamcmd_install_path = value
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
    def game_folder(self) -> str:
        if self._game_folder is None:
            return ""
        else:
            return str(self._game_folder)

    @game_folder.setter
    def game_folder(self, value: str) -> None:
        if value == str(self._game_folder):
            return
        if value == "":
            self._game_folder = None
            EventBus().settings_have_changed.emit()
            return
        p = Path(value).resolve()
        if not p.exists() or not p.is_dir():
            logger.warning(f"Invalid game folder: {p}")
            self._game_folder = None
            EventBus().settings_have_changed.emit()
            return
        self._game_folder = p
        EventBus().settings_have_changed.emit()

    @property
    def config_folder(self) -> str:
        if self._config_folder is None:
            return ""
        else:
            return str(self._config_folder)

    @config_folder.setter
    def config_folder(self, value: str) -> None:
        if value == str(self._config_folder):
            return
        if value == "":
            self._config_folder = None
            EventBus().settings_have_changed.emit()
            return
        p = Path(value).resolve()
        if not p.exists() or not p.is_dir():
            logger.warning(f"Invalid config folder: {p}")
            self._config_folder = None
            EventBus().settings_have_changed.emit()
            return
        self._config_folder = p
        EventBus().settings_have_changed.emit()

    @property
    def local_folder(self) -> str:
        if self._local_folder is None:
            return ""
        else:
            return str(self._local_folder)

    @local_folder.setter
    def local_folder(self, value: str) -> None:
        if value == str(self._local_folder):
            return
        if value == "":
            self._local_folder = None
            EventBus().settings_have_changed.emit()
            return
        p = Path(value).resolve()
        if not p.exists() or not p.is_dir():
            logger.warning(f"Invalid local folder: {p}")
            self._local_folder = None
            EventBus().settings_have_changed.emit()
            return
        self._local_folder = p
        EventBus().settings_have_changed.emit()

    @property
    def workshop_folder(self) -> str:
        if self._workshop_folder is None:
            return ""
        else:
            return str(self._workshop_folder)

    @workshop_folder.setter
    def workshop_folder(self, value: str) -> None:
        if value == str(self._workshop_folder):
            return
        if value == "":
            self._workshop_folder = None
            EventBus().settings_have_changed.emit()
            return
        p = Path(value).resolve()
        if not p.exists() or not p.is_dir():
            logger.warning(f"Invalid workshop folder: {p}")
            self._workshop_folder = None
            EventBus().settings_have_changed.emit()
            return
        self._workshop_folder = p
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

    @property
    def run_args(self) -> List[str]:
        return self._run_args

    @run_args.setter
    def run_args(self, value: List[str]) -> None:
        if value == self._run_args:
            return
        self._run_args = value
        EventBus().settings_have_changed.emit()

    def load(self) -> None:
        if self._debug_file.exists() and self._debug_file.is_file():
            self._debug_logging_enabled = True
        else:
            self._debug_logging_enabled = False

        try:
            with open(str(self._settings_file), "r") as file:
                data = json.load(file)
                self._from_dict(data)
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

        if "steamcmd_install_path" in data:
            self.steamcmd_install_path = data["steamcmd_install_path"]
            del data["steamcmd_install_path"]

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

        if "game_folder" in data:
            self.game_folder = data["game_folder"]
            del data["game_folder"]

        if "config_folder" in data:
            self.config_folder = data["config_folder"]
            del data["config_folder"]

        if "local_folder" in data:
            self.local_folder = data["local_folder"]
            del data["local_folder"]

        if "workshop_folder" in data:
            self.workshop_folder = data["workshop_folder"]
            del data["workshop_folder"]

        if "github_username" in data:
            self.github_username = data["github_username"]
            del data["github_username"]

        if "github_token" in data:
            self.github_token = data["github_token"]
            del data["github_token"]

        if "steam_apikey" in data:
            self.steam_apikey = data["steam_apikey"]
            del data["steam_apikey"]

        if "run_args" in data:
            self.run_args = data["run_args"]
            del data["run_args"]

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
            "steamcmd_install_path": self.steamcmd_install_path,
            "steamcmd_validate_downloads": self.steamcmd_validate_downloads,
            "todds_preset": self.todds_preset,
            "todds_active_mods_target": self.todds_active_mods_target,
            "todds_dry_run": self.todds_dry_run,
            "todds_overwrite": self.todds_overwrite,
            "game_folder": self.game_folder,
            "config_folder": self.config_folder,
            "local_folder": self.local_folder,
            "workshop_folder": self.workshop_folder,
            "github_username": self.github_username,
            "github_token": self.github_token,
            "steam_apikey": self.steam_apikey,
            "run_args": self.run_args,
        }
        return data
