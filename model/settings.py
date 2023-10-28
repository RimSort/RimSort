import json
from json import JSONDecodeError
from typing import Dict, Any

from PySide6.QtCore import QObject

from util.app_info import AppInfo
from util.event_bus import EventBus


class Settings(QObject):
    def __init__(self) -> None:
        super().__init__()

        self._settings_file = AppInfo().user_data_folder / "settings.json"

        # Application-wide settings: default values go here
        self._check_for_updates_on_startup: bool = False
        self._show_folder_rows: bool = True
        self._sorting_algorithm: str = "Alphabetical"
        self._external_steam_metadata_file_path: str = str(
            AppInfo().user_data_folder / "steamDB.json"
        )
        self._external_steam_metadata_repo: str = (
            "https://github.com/RimSort/Steam-Workshop-Database"
        )
        self._external_steam_metadata_source: str = "None"
        self._external_community_rules_file_path: str = str(
            AppInfo().user_data_folder / "communityRules.json"
        )
        self._external_community_rules_repo: str = (
            "https://github.com/RimSort/Community-Rules-Database"
        )
        self._external_community_rules_metadata_source: str = "None"
        self._db_builder_include: str = "all_mods"
        self._database_expiry: int = 604800
        self._build_steam_database_dlc_data: bool = True
        self._build_steam_database_update_toggle: bool = False
        self._watchdog_toggle: bool = True
        self._mod_type_filter_toggle: bool = True
        self._duplicate_mods_warning: bool = False
        self._steam_mods_update_check: bool = False
        self._try_download_missing_mods: bool = False
        self._steamcmd_install_path: str = "."
        self._steamcmd_validate_downloads: bool = True
        self._todds_preset: str = "optimized"
        self._todds_active_mods_target: bool = True
        self._todds_dry_run: bool = False
        self._todds_overwrite: bool = False
        self._game_folder: str = ""
        self._config_folder: str = ""
        self._local_folder: str = ""
        self._workshop_folder: str = ""

    @property
    def check_for_updates_on_startup(self) -> bool:
        return self._check_for_updates_on_startup

    @check_for_updates_on_startup.setter
    def check_for_updates_on_startup(self, value: bool) -> None:
        self._check_for_updates_on_startup = value
        EventBus().settings_have_changed.emit()

    @property
    def show_folder_rows(self) -> bool:
        return self._show_folder_rows

    @show_folder_rows.setter
    def show_folder_rows(self, value: bool) -> None:
        self._show_folder_rows = value
        EventBus().settings_have_changed.emit()

    @property
    def sorting_algorithm(self) -> str:
        return self._sorting_algorithm

    @sorting_algorithm.setter
    def sorting_algorithm(self, value: str) -> None:
        self._sorting_algorithm = value
        EventBus().settings_have_changed.emit()

    @property
    def external_steam_metadata_file_path(self) -> str:
        return self._external_steam_metadata_file_path

    @external_steam_metadata_file_path.setter
    def external_steam_metadata_file_path(self, value: str) -> None:
        self._external_steam_metadata_file_path = value
        EventBus().settings_have_changed.emit()

    @property
    def external_steam_metadata_repo(self) -> str:
        return self._external_steam_metadata_repo

    @external_steam_metadata_repo.setter
    def external_steam_metadata_repo(self, value: str) -> None:
        self._external_steam_metadata_repo = value
        EventBus().settings_have_changed.emit()

    @property
    def external_steam_metadata_source(self) -> str:
        return self._external_steam_metadata_source

    @external_steam_metadata_source.setter
    def external_steam_metadata_source(self, value: str) -> None:
        self._external_steam_metadata_source = value
        EventBus().settings_have_changed.emit()

    @property
    def external_community_rules_file_path(self) -> str:
        return self._external_community_rules_file_path

    @external_community_rules_file_path.setter
    def external_community_rules_file_path(self, value: str) -> None:
        self._external_community_rules_file_path = value
        EventBus().settings_have_changed.emit()

    @property
    def external_community_rules_repo(self) -> str:
        return self._external_community_rules_repo

    @external_community_rules_repo.setter
    def external_community_rules_repo(self, value: str) -> None:
        self._external_community_rules_repo = value
        EventBus().settings_have_changed.emit()

    @property
    def external_community_rules_metadata_source(self) -> str:
        return self._external_community_rules_metadata_source

    @external_community_rules_metadata_source.setter
    def external_community_rules_metadata_source(self, value: str) -> None:
        self._external_community_rules_metadata_source = value
        EventBus().settings_have_changed.emit()

    @property
    def db_builder_include(self) -> str:
        return self._db_builder_include

    @db_builder_include.setter
    def db_builder_include(self, value: str) -> None:
        self._db_builder_include = value
        EventBus().settings_have_changed.emit()

    @property
    def database_expiry(self) -> int:
        return self._database_expiry

    @database_expiry.setter
    def database_expiry(self, value: int) -> None:
        self._database_expiry = value
        EventBus().settings_have_changed.emit()

    @property
    def build_steam_database_dlc_data(self) -> bool:
        return self._build_steam_database_dlc_data

    @build_steam_database_dlc_data.setter
    def build_steam_database_dlc_data(self, value: bool) -> None:
        self._build_steam_database_dlc_data = value
        EventBus().settings_have_changed.emit()

    @property
    def build_steam_database_update_toggle(self) -> bool:
        return self._build_steam_database_update_toggle

    @build_steam_database_update_toggle.setter
    def build_steam_database_update_toggle(self, value: bool) -> None:
        self._build_steam_database_update_toggle = value
        EventBus().settings_have_changed.emit()

    @property
    def watchdog_toggle(self) -> bool:
        return self._watchdog_toggle

    @watchdog_toggle.setter
    def watchdog_toggle(self, value: bool) -> None:
        self._watchdog_toggle = value
        EventBus().settings_have_changed.emit()

    @property
    def mod_type_filter_toggle(self) -> bool:
        return self._mod_type_filter_toggle

    @mod_type_filter_toggle.setter
    def mod_type_filter_toggle(self, value: bool) -> None:
        self._mod_type_filter_toggle = value
        EventBus().settings_have_changed.emit()

    @property
    def duplicate_mods_warning(self) -> bool:
        return self._duplicate_mods_warning

    @duplicate_mods_warning.setter
    def duplicate_mods_warning(self, value: bool) -> None:
        self._duplicate_mods_warning = value
        EventBus().settings_have_changed.emit()

    @property
    def steam_mods_update_check(self) -> bool:
        return self._steam_mods_update_check

    @steam_mods_update_check.setter
    def steam_mods_update_check(self, value: bool) -> None:
        self._steam_mods_update_check = value
        EventBus().settings_have_changed.emit()

    @property
    def try_download_missing_mods(self) -> bool:
        return self._try_download_missing_mods

    @try_download_missing_mods.setter
    def try_download_missing_mods(self, value: bool) -> None:
        self._try_download_missing_mods = value
        EventBus().settings_have_changed.emit()

    @property
    def steamcmd_install_path(self) -> str:
        return self._steamcmd_install_path

    @steamcmd_install_path.setter
    def steamcmd_install_path(self, value: str) -> None:
        self._steamcmd_install_path = value
        EventBus().settings_have_changed.emit()

    @property
    def steamcmd_validate_downloads(self) -> bool:
        return self._steamcmd_validate_downloads

    @steamcmd_validate_downloads.setter
    def steamcmd_validate_downloads(self, value: bool) -> None:
        self._steamcmd_validate_downloads = value
        EventBus().settings_have_changed.emit()

    @property
    def todds_preset(self) -> str:
        return self._todds_preset

    @todds_preset.setter
    def todds_preset(self, value: str) -> None:
        self._todds_preset = value
        EventBus().settings_have_changed.emit()

    @property
    def todds_active_mods_target(self) -> bool:
        return self._todds_active_mods_target

    @todds_active_mods_target.setter
    def todds_active_mods_target(self, value: bool) -> None:
        self._todds_active_mods_target = value
        EventBus().settings_have_changed.emit()

    @property
    def todds_dry_run(self) -> bool:
        return self._todds_dry_run

    @todds_dry_run.setter
    def todds_dry_run(self, value: bool) -> None:
        self._todds_dry_run = value
        EventBus().settings_have_changed.emit()

    @property
    def todds_overwrite(self) -> bool:
        return self._todds_overwrite

    @todds_overwrite.setter
    def todds_overwrite(self, value: bool) -> None:
        self._todds_overwrite = value
        EventBus().settings_have_changed.emit()

    @property
    def game_folder(self) -> str:
        return self._game_folder

    @game_folder.setter
    def game_folder(self, value: str) -> None:
        self._game_folder = value
        EventBus().settings_have_changed.emit()

    @property
    def config_folder(self) -> str:
        return self._config_folder

    @config_folder.setter
    def config_folder(self, value: str) -> None:
        self._config_folder = value
        EventBus().settings_have_changed.emit()

    @property
    def local_folder(self) -> str:
        return self._local_folder

    @local_folder.setter
    def local_folder(self, value: str) -> None:
        self._local_folder = value
        EventBus().settings_have_changed.emit()

    @property
    def workshop_folder(self) -> str:
        return self._workshop_folder

    @workshop_folder.setter
    def workshop_folder(self, value: str) -> None:
        self._workshop_folder = value
        EventBus().settings_have_changed.emit()

    def load(self) -> None:
        try:
            with open(str(self._settings_file), "r") as file:
                data = json.load(file)
                self._from_dict(data)
        except (FileNotFoundError, JSONDecodeError):
            # TODO: Handle these exceptions in a sane and reasonable way.
            pass

    def save(self) -> None:
        with open(str(self._settings_file), "w") as file:
            json.dump(self._to_dict(), file, indent=4)

    def _from_dict(self, data: Dict[str, Any]) -> None:
        if "show_folder_rows" in data:
            self.show_folder_rows = data["show_folder_rows"]
            del data["show_folder_rows"]

        if "check_for_update_startup" in data:
            self.check_for_updates_on_startup = data["check_for_update_startup"]
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

    def _to_dict(self) -> Dict[str, Any]:
        data = {
            "check_for_update_startup": self.check_for_updates_on_startup,
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
        }
        return data
