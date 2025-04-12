from enum import Enum

from app.utils.metadata import MetadataManager


def uuid_no_key(uuid: str) -> str:
    """
    Returns the UUID of the mod.
    Args:
        uuid (str): The UUID of the mod.
    Returns:
        str: The UUID of the mod.
    """
    return uuid


def uuid_to_mod_name(uuid: str) -> str:
    """
    Converts a UUID to the corresponding mod name.
    Args:
        uuid (str): The UUID of the mod.
    Returns:
        str: If mod name not None, returns mod name in lowercase. Otherwise, returns "# unnamed mod".
    """
    name = MetadataManager.instance().internal_local_metadata[uuid]["name"]
    return name.lower() if name is not None else "# unnamed mod"


class ModsPanelSortKey(Enum):
    """
    Enum class representing different sorting keys for mods.
    """

    NOKEY = 0
    MODNAME = 1


def sort_uuids(uuids: list[str], key: ModsPanelSortKey) -> list[str]:
    """
    Sort the list of UUIDs based on the provided key.
    Args:
        key (ModsPanelSortKey): The key to sort the list by.
    Returns:
        None
    """
    # Sort the list of UUIDs based on the provided key
    if key == ModsPanelSortKey.MODNAME:
        key_function = uuid_to_mod_name
    else:
        return sorted(uuids, key=lambda x: x)
    return sorted(uuids, key=key_function)
