import json
from json import JSONDecodeError
from os import path, rename
from pathlib import Path
from shutil import copytree, rmtree
from time import time
from typing import Any, Dict, Optional

import msgspec
from loguru import logger
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from app.models.instance import Instance
from app.models.secure_settings import SecureSettings
from app.utils.app_info import AppInfo
from app.utils.constants import SortMethod
from app.utils.event_bus import EventBus
from app.utils.generic import handle_remove_read_only


class Settings(QObject):
    def __init__(self) -> None:
        super().__init__()

        self._settings_file = AppInfo().app_settings_file
        self._debug_file = AppInfo().app_storage_folder / "DEBUG"

        # Initialize secure settings manager
        self._secure_settings = SecureSettings()

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
        self.external_use_this_instead_folder_path: str = str(
            AppInfo().app_storage_folder / "UseThisInstead" / "Replacements"
        )
        self.external_use_this_instead_repo_path: str = (
            "https://github.com/emipa606/UseThisInstead"
        )

        # Sorting
        self.sorting_algorithm: SortMethod = SortMethod.TOPOLOGICAL
        self.check_dependencies_on_sort: bool = (
            True  # Whether to check for missing dependencies when sorting
        )
        self.use_moddependencies_as_loadTheseBefore: bool = (
            False  # Whether to use moddependencies as loadTheseBefore
        )

        # DB Builder
        self.db_builder_include: str = "all_mods"
        self.build_steam_database_dlc_data: bool = True
        self.build_steam_database_update_toggle: bool = False
        # DEPRECATED: steam_apikey - now stored securely
        self._steam_apikey_deprecated: str = ""

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

        self.font_family: str = QApplication.font().family()
        self.font_size: int = 12

        # Language
        self.language = "en_US"

        # Window size configuration
        self.window_x: int = 0
        self.window_y: int = 0
        self.window_width: int = 0
        self.window_height: int = 0

        # Advanced
        self.debug_logging_enabled: bool = False
        self.watchdog_toggle: bool = True
        self.mod_type_filter_toggle: bool = True
        self.hide_invalid_mods_when_filtering_toggle: bool = False
        self.duplicate_mods_warning: bool = False
        self.steam_mods_update_check: bool = False
        self.try_download_missing_mods: bool = False
        self.render_unity_rich_text: bool = True
        self.update_databases_on_startup: bool = True

        # DEPRECATED: These are now stored securely
        self._rentry_auth_code_deprecated: str = ""
        self._github_username_deprecated: str = ""
        self._github_token_deprecated: str = ""

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

    # Secure settings properties
    @property
    def steam_apikey(self) -> str:
        """Get Steam API key from secure storage."""
        return self._secure_settings.get_steam_api_key() or ""

    @steam_apikey.setter
    def steam_apikey(self, value: str) -> None:
        """Store Steam API key in secure storage."""
        if value:
            self._secure_settings.set_steam_api_key(value)
        else:
            self._secure_settings.delete_steam_api_key()

    @property
    def github_token(self) -> str:
        """Get GitHub token from secure storage."""
        return self._secure_settings.get_github_token(self.github_username) or ""

    @github_token.setter
    def github_token(self, value: str) -> None:
        """Store GitHub token in secure storage."""
        if value:
            self._secure_settings.set_github_token(self.github_username, value)
        else:
            self._secure_settings.delete_github_token(self.github_username)

    @property
    def github_username(self) -> str:
        """Get GitHub username (stored in plaintext for user identification)."""
        return getattr(self, "_github_username_value", "")

    @github_username.setter
    def github_username(self, value: str) -> None:
        """Set GitHub username."""
        self._github_username_value = value
        EventBus().settings_have_changed.emit()

    @property
    def rentry_auth_code(self) -> str:
        """Get Rentry auth code from secure storage."""
        return self._secure_settings.get_rentry_auth_code() or ""

    @rentry_auth_code.setter
    def rentry_auth_code(self, value: str) -> None:
        """Store Rentry auth code in secure storage."""
        if value:
            self._secure_settings.set_rentry_auth_code(value)
        else:
            self._secure_settings.delete_rentry_auth_code()

    def is_secure_storage_available(self) -> bool:
        """Check if secure storage is available."""
        return self._secure_settings.is_keyring_available()

    def get_storage_info(self) -> dict[str, Any]:
        """Get information about current storage backend."""
        return self._secure_settings.get_storage_info()

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

                # Migrate secrets to secure storage if available
                self._migrate_secrets_to_secure_storage(data)

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

    def _migrate_secrets_to_secure_storage(self, data: Dict[str, Any]) -> None:
        """Migrate secrets from plaintext to secure storage."""
        if not self._secure_settings.is_keyring_available():
            logger.debug("Keyring not available, skipping secret migration")
            return

        migrated_any = False

        # Migrate and remove secrets from data dict
        if self._secure_settings.migrate_from_plaintext_settings(data):
            # Remove migrated secrets from the data to be saved
            secrets_to_remove = ["steam_apikey", "github_token", "rentry_auth_code"]
            for secret in secrets_to_remove:
                if secret in data:
                    del data[secret]
                    migrated_any = True

            if migrated_any:
                logger.info(
                    "Migrated secrets to secure storage and removed from plaintext settings"
                )

    def save(self) -> None:
        if self.debug_logging_enabled:
            self._debug_file.touch(exist_ok=True)
        else:
            self._debug_file.unlink(missing_ok=True)

        with open(str(self._settings_file), "w") as file:
            json.dump(self._to_dict(), file, indent=4)

    def _from_dict(self, data: Dict[str, Any]) -> None:
        special_attributes = ["instances"]
        # Don't load deprecated/migrated secrets from file
        deprecated_secrets = ["steam_apikey", "github_token", "rentry_auth_code"]

        for key, value in data.items():
            if key in special_attributes:
                continue
            if key in deprecated_secrets:
                # Store deprecated values for potential fallback
                setattr(self, f"_{key}_deprecated", value)
                continue
            if not hasattr(self, key):
                continue
            # Special handling for github_username
            if key == "github_username":
                self._github_username_value = value
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
        skip_attributes = ["destroyed", "objectNameChanged", "_secure_settings"]
        # Don't save deprecated/migrated secrets to file
        deprecated_secrets = ["steam_apikey", "github_token", "rentry_auth_code"]

        data = {}

        for key, value in self.__dict__.items():
            if key in special_attributes:
                continue
            if key in skip_attributes:
                continue
            if skip_private and key.startswith("_"):
                continue
            if key in deprecated_secrets:
                continue
            data[key] = value

        # Add github_username if it exists
        if hasattr(self, "_github_username_value"):
            data["github_username"] = self._github_username_value

        data["instances"] = {
            name: instance.as_dict() for name, instance in self.instances.items()
        }
        return data

    def get_fallback_secret(self, secret_type: str) -> Optional[str]:
        """Get fallback secret from deprecated storage for backwards compatibility."""
        deprecated_attr = f"_{secret_type}_deprecated"
        return (
            getattr(self, deprecated_attr, "")
            if hasattr(self, deprecated_attr)
            else None
        )
