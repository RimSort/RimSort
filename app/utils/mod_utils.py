import os
from typing import Union

from loguru import logger

from app.utils.metadata import MetadataManager


def get_mod_name_from_pfid(pfid: Union[str, int, None]) -> str:
    """
    Get a mod's name from its PublishedFileID.

    Args:
        pfid (Union[str, int, None]): The PublishedFileID to lookup (str, int or None)

    Returns:
        str: The mod name or "Unknown Mod" if not found

    Examples:
        >>> get_mod_name_from_pfid("123456789")
        'Example Mod Name'
        >>> get_mod_name_from_pfid(None)
        'Unknown Mod'
        >>> get_mod_name_from_pfid("invalid_id")
        'Invalid ID: invalid_id'
    """
    if not pfid:
        return "Unknown Mod"

    pfid_str = str(pfid)
    if not pfid_str.isdigit():
        return f"Invalid ID: {pfid_str}"

    metadata_manager = MetadataManager.instance()

    # Check internal metadata
    for mod_data in metadata_manager.internal_local_metadata.values():
        if mod_data.get("publishedfileid") == pfid_str:
            return mod_data.get("name", pfid_str)

    # Check external Steam metadata
    if metadata_manager.external_steam_metadata:
        steam_metadata = metadata_manager.external_steam_metadata.get(pfid_str)
        if steam_metadata and "name" in steam_metadata:
            return steam_metadata["name"]

    # Fallback to returning a descriptive message
    return f"Invalid ID: {pfid_str}"


def get_mod_paths_from_uuids(uuids: list[str]) -> list[str]:
    """
    Utility function to get direct paths to mod folders from a list of mod UUIDs.

    Args:
        uuids (List[str]): List of mod UUID strings.

    Returns:
        List[str]: Mod folder paths corresponding to the UUIDs.

    Examples:
        >>> get_mod_paths_from_uuids(['uuid1', 'uuid2'])
        ['/path/to/mod1', '/path/to/mod2']
    """
    metadata_manager = MetadataManager.instance()
    mod_paths = []

    for uuid in uuids:
        if uuid in metadata_manager.internal_local_metadata:
            mod_path = metadata_manager.internal_local_metadata[uuid].get("path", "")
            if mod_path and os.path.isdir(mod_path):
                logger.debug(f"Adding mod path: {mod_path}")
                mod_paths.append(mod_path)

    logger.info(f"Processed {len(uuids)} UUIDs for mod paths")
    return mod_paths
