from os import path
from pathlib import Path
from typing import Any

import msgspec

from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus


class Instance(msgspec.Struct):
    """A msgspec.Struct class representing an instance.

    When an attribute is set, the settings_have_changed event is emitted.

    :param name: The name of the instance
    :type name: str

    :param game_folder: The path to the game folder
    :type game_folder: str

    :param config_folder: The path to the config folder
    :type config_folder: str

    :param local_folder: The path to the local folder
    :type local_folder: str

    :param workshop_folder: The path to the workshop folder
    :type workshop_folder: str

    :param run_args: The run arguments of the instance
    :type run_args: list[str]

    :param steamcmd_install_path: The path to the SteamCMD install folder
    :type steamcmd_install_path: str

    :param steam_client_integration: Whether to integrate the Steam client with the instance
    :type steam_client_integration: bool
    """

    name: str = "Default"
    game_folder: str = ""
    config_folder: str = ""
    local_folder: str = ""
    workshop_folder: str = ""
    run_args: list[str] = msgspec.field(default_factory=list)
    steamcmd_install_path: str = str(
        Path(AppInfo().app_storage_folder / "instances" / "Default")
    )
    steam_client_integration: bool = False

    def __setattr__(self, name: str, value: Any) -> None:
        # If the value is the same as the current value, do nothing
        if getattr(self, name) == value:
            return
        super().__setattr__(name, value)
        EventBus().settings_have_changed.emit()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "game_folder": self.game_folder,
            "config_folder": self.config_folder,
            "local_folder": self.local_folder,
            "workshop_folder": self.workshop_folder,
            "run_args": self.run_args,
            "steamcmd_install_path": self.steamcmd_install_path,
            "steam_client_integration": self.steam_client_integration,
        }

    def validate_paths(self, clear: bool = True) -> list[str]:
        """Validates the paths of the instance. If clear is True, invalid paths are set to an empty string.

        :param clear: Whether to clear invalid paths, defaults to True
        :type clear: bool, optional
        :return: A list of invalid paths
        :rtype: list[str]
        """
        invalid_paths = []
        for path_name in [
            "game_folder",
            "config_folder",
            "local_folder",
            "workshop_folder",
            "steamcmd_install_path",
        ]:
            if not path.exists(getattr(self, path_name)):
                invalid_paths.append(path_name)
                if clear:
                    setattr(self, path_name, "")
        return invalid_paths
