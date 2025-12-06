from pathlib import Path

import msgspec

from app.utils.app_info import AppInfo


class Instance(msgspec.Struct):
    """
    Data model for a RimWorld game instance.

    Pure data class with no side effects on attribute mutation.
    Validation and signal emission handled by controllers and settings management.
    """

    name: str = "Default"
    game_folder: str = ""
    config_folder: str = ""
    local_folder: str = ""
    workshop_folder: str = ""
    run_args: list[str] = msgspec.field(default_factory=list)
    steamcmd_auto_clear_depot_cache: bool = True
    steamcmd_install_path: str = str(
        Path(AppInfo().app_storage_folder / "instances" / "Default")
    )
    steamcmd_ignore: bool = False
    steam_client_integration: bool = False
    initial_setup: bool = True
