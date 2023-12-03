from loguru import logger
from typing import Any, Dict, Optional

from app.models.dialogue import show_warning


def validate_rimworld_mods_list(
    mods_config_data: Dict[str, Any]
) -> Optional[list[str]]:
    """
    Validate format of a Rimworld ModsConfig.xml

    :return: True if the ModsConfig is in the expected format, otherwise False.
    """
    logger.debug(f"Validating RimWorld mods list")
    if mods_config_data:
        # ModsConfig.xml format
        if (
            mods_config_data.get("ModsConfigData", {})
            .get("activeMods", {})
            .get("li", {})
        ):
            logger.info("Validated XML formatting (ModsConfig.xml style)")
            return mods_config_data["ModsConfigData"]["activeMods"]["li"]
        # RimWorld .rws save file format
        elif (
            mods_config_data.get("savegame", {})
            .get("meta", {})
            .get("modIds", {})
            .get("li", {})
        ):
            logger.info("Validated XML formatting (RimWorld savegame style)")
            return mods_config_data["savegame"]["meta"]["modIds"]["li"]
        else:
            logger.error(f"Invalid format: {mods_config_data}")
    show_warning(
        text="Unable to read data from file",
        information=(
            "RimSort was unable to read the supplied mods list because it may be invalid or missing."
        ),
        details=str(mods_config_data),
    )
    return False
