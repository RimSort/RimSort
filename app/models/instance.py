from pathlib import Path

import msgspec

from app.utils.app_info import AppInfo
from app.utils.constants import DEFAULT_INSTANCE_NAME, INSTANCE_FOLDER_NAME


class Instance(msgspec.Struct):
    """
    Data model for a RimWorld game instance.

    Pure data class with no side effects on attribute mutation.
    Validation and signal emission handled by controllers and settings management.
    """

    name: str = DEFAULT_INSTANCE_NAME
    game_folder: str = ""
    config_folder: str = ""
    local_folder: str = ""
    workshop_folder: str = ""
    run_args: list[str] = msgspec.field(default_factory=list)
    steamcmd_auto_clear_depot_cache: bool = True
    steamcmd_install_path: str = str(
        Path(
            AppInfo().app_storage_folder / INSTANCE_FOLDER_NAME / DEFAULT_INSTANCE_NAME
        )
    )
    steamcmd_ignore: bool = False
    steam_client_integration: bool = False
    instance_folder_override: str = (
        ""  # Custom instance folder path, empty = use default
    )
    initial_setup: bool = True
