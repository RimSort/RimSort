from typing import Any

from loguru import logger

from app.utils.constants import RIMWORLD_PACKAGE_IDS
from app.views.dialogue import show_warning


def generate_rimworld_mods_list(
    game_version: str,
    packageids: list[str],
) -> dict[str, Any]:
    """
    Generate the default Rimworld mods list
    """
    return {
        "ModsConfigData": {
            "version": game_version,
            "activeMods": {
                "li": packageids,
            },
            "knownExpansions": {
                "li": [
                    packageid
                    for packageid in packageids
                    if packageid.lower() in RIMWORLD_PACKAGE_IDS
                    and packageid.lower() != "ludeon.rimworld"
                ],
            },
        },
    }


def validate_rimworld_mods_list(
    mods_config_data: dict[str, Any],
) -> list[str]:
    """
    Validate format of RimWorld-supported mod lists

    :return: True if the ModsConfig is in the expected format, otherwise False.
    """
    logger.debug("Validating RimWorld mods list")
    try:
        # RimWorld Config/ModsConfig.xml format
        if (
            mods_config_data.get("ModsConfigData", {})
            .get("activeMods", {})
            .get("li", {})
        ):
            logger.info("Validated XML formatting (RimWorld Config/ModsConfig.xml)")
            active_mods = mods_config_data["ModsConfigData"]["activeMods"]["li"]
            if isinstance(active_mods, list):
                return active_mods
            elif isinstance(active_mods, str):
                return [active_mods]
        # RimWorld .rws XML save file format
        elif (
            mods_config_data.get("savegame", {})
            .get("meta", {})
            .get("modIds", {})
            .get("li", {})
        ):
            logger.info("Validated XML formatting (RimWorld .rws savegame)")
            return mods_config_data["savegame"]["meta"]["modIds"]["li"]
        # RimWorld .rws XML file format
        elif (
            mods_config_data.get("savedModList", {})
            .get("meta", {})
            .get("modIds", {})
            .get("li", {})
        ):
            logger.info("Validated XML formatting (RimWorld .rml modlist)")
            return mods_config_data["savedModList"]["meta"]["modIds"]["li"]
    except Exception as e:
        logger.error(f"Error trying to validate data: {e}")
        show_warning(
            title="Unable to read data",
            text=("RimSort was unable to read the supplied mods list."),
            information="The supplied mods list may be missing or invalid. "
            + "If you just (re)installed RimWorld, you may need to run it once to generate the mods list.",
            details=str(e),
        )
    else:
        logger.error(f"Invalid format: {mods_config_data}")
        show_warning(
            title="Unable to read data",
            text=(
                "RimSort was unable to read the supplied mods list because it may be invalid or missing."
            ),
        )

    return ["Ludeon.RimWorld"]
