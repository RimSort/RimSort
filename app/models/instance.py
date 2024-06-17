from os import path
from pathlib import Path
from typing import Any

import msgspec

from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus


class Instance(msgspec.Struct):
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
        EventBus().settings_have_changed.emit()
        return super().__setattr__(name, value)

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
