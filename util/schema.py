import logging
from typing import Any, Dict

from util.error import show_warning

logger = logging.getLogger(__name__)


def validate_mods_config_format(mods_config_data: Dict[str, Any]) -> bool:
    """
    Return True if the ModsConfig is in the expected format, otherwise False.
    """
    logger.info(f"Validating mods config: {mods_config_data}")
    if mods_config_data:
        if mods_config_data.get("ModsConfigData"):
            if mods_config_data["ModsConfigData"].get("activeMods"):
                if mods_config_data["ModsConfigData"]["activeMods"].get("li"):
                    logger.info("ModsConfig.xml is properly formatted")
                    return True
        logger.error(f"Invalid ModsConfig.xml format: {mods_config_data}")
        show_warning(
            text="Invalid ModsConfig.xml format",
            information=(
                "RimSort was unable to read your ModsConfig.xml because it is incorrectly formatted. "
                "You may have to re-create the file by deleting it and running RimWorld. See details "
                "for what RimSort was able to read from your file."
            ),
            details=str(mods_config_data),
        )
    else:
        show_warning(
            text="Missing ModsConfig.xml",
            information=(
                "RimSort was unable to read your ModsConfig.xml because it may be missing. "
                "Please check that a file called ModsConfig.xml exists in the game install "
                "directory that you have set."
            ),
            details=str(mods_config_data),
        )
        logger.error(f"Empty mods config data: {mods_config_data}")
    return False
