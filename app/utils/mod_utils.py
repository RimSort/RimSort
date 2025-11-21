import os

from app.utils.metadata import MetadataManager


def get_mod_path_from_pfid(pfid: str) -> str | None:
    """
    Get the mod path from a published file ID.

    Args:
        pfid: Published file ID.

    Returns:
        Mod path if found, None otherwise.
    """
    metadata_manager = MetadataManager.instance()
    for metadata in metadata_manager.internal_local_metadata.values():
        if metadata.get("publishedfileid") == pfid:
            return metadata.get("path")
    return None


def get_mod_name_from_pfid(pfid: str | int | None) -> str:
    """
    Get a mod's name from its PublishedFileID.

    Args:
        pfid: The PublishedFileID to lookup (str, int or None)

    Returns:
        str: The mod name or "Unknown Mod" if not found
    """
    if not pfid:
        return "Unknown Mod"

    pfid_str = str(pfid)
    if not pfid_str.isdigit():
        return f"Invalid ID: {pfid_str}"

    metadata_manager = MetadataManager.instance()

    # First check internal local metadata
    for metadata in metadata_manager.internal_local_metadata.values():
        if metadata.get("publishedfileid") == pfid_str:
            name = metadata.get("name") or metadata.get("steamName")
            return name if name else f"Invalid ID: {pfid_str}"

    # Then check external steam metadata if available
    if hasattr(metadata_manager, "external_steam_metadata"):
        steam_metadata = getattr(metadata_manager, "external_steam_metadata", {})
        if isinstance(steam_metadata, dict) and pfid_str in steam_metadata:
            metadata = steam_metadata[pfid_str]
            if isinstance(metadata, dict):
                name = metadata.get("title") or metadata.get("name")
                return name if name else f"Invalid ID: {pfid_str}"

    return f"Invalid ID: {pfid_str}"


def get_mod_paths_from_uuids(uuids: list[str]) -> list[str]:
    """
    Get mod paths from a list of UUIDs.

    Args:
        uuids: List of mod UUID strings.

    Returns:
        List of mod folder paths corresponding to the UUIDs.
    """
    metadata_manager = MetadataManager.instance()
    mod_paths = []

    for uuid in uuids:
        if uuid in metadata_manager.internal_local_metadata:
            mod_path = metadata_manager.internal_local_metadata[uuid]["path"]
            if mod_path and os.path.isdir(mod_path):
                mod_paths.append(mod_path)

    return mod_paths
