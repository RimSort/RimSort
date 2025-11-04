import os
from enum import Enum
from typing import Optional

from loguru import logger
from PySide6.QtCore import QObject, Signal, Slot

from app.utils.generic import scanpath
from app.utils.metadata import MetadataManager, ModMetadata

# Simple in-memory cache for folder sizes: {mod_path: (mtime, size_bytes)}
_FOLDER_SIZE_CACHE: dict[str, tuple[int, int]] = {}


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
        str: If mod name not None and is a string, returns mod name in lowercase. Otherwise, returns "name error in mod about.xml".
    """
    metadata = get_mod_metadata(uuid)
    name = metadata.get("name") if metadata else None
    if isinstance(name, str):
        return name.lower()
    else:
        return "name error in mod about.xml"


def uuid_to_filesystem_modified_time(uuid: str) -> int:
    """
    Converts a UUID to the corresponding mod's filesystem modification time.
    Args:
        uuid (str): The UUID of the mod.
    Returns:
        int: The filesystem modification time, or 0 if not available.
    """
    metadata = get_mod_metadata(uuid)
    mod_path = metadata.get("path") if metadata else None
    if mod_path and os.path.exists(mod_path):
        fs_time = int(os.path.getmtime(mod_path))
        mod_name = metadata.get("name") if metadata else None
        logger.debug(f"Mod: {mod_name}, Filesystem time: {fs_time}")
        return fs_time
    return 0


def uuid_to_author(uuid: str) -> str:
    """
    Converts a UUID to the corresponding author's name used for sorting.
    Returns the first author in lowercase if available; otherwise an empty string.
    """
    metadata = get_mod_metadata(uuid)
    authors = metadata.get("authors") if metadata else None
    author: Optional[str] = None
    if isinstance(authors, dict):
        # Possible formats: {"li": ["a", "b"]} or {"li": "a"}
        li_value = authors.get("li")
        if isinstance(li_value, list) and li_value:
            author = li_value[0]
        elif isinstance(li_value, str):
            author = li_value
    elif isinstance(authors, list):
        if authors:
            author = authors[0]
    elif isinstance(authors, str):
        author = authors

    return author.lower() if isinstance(author, str) else ""


def uuid_to_folder_size(uuid: str) -> int:
    """
    Calculate the total size in bytes of the mod folder for the given UUID.
    Returns 0 if the path is missing.
    """
    metadata = get_mod_metadata(uuid)
    mod_path = metadata.get("path") if metadata else None
    if not mod_path or not os.path.isdir(mod_path):
        return 0
    try:
        mtime = int(os.path.getmtime(mod_path))
    except OSError:
        return 0

    cached = _FOLDER_SIZE_CACHE.get(mod_path)
    if cached and cached[0] == mtime:
        return cached[1]

    total_size = get_dir_size(mod_path)

    _FOLDER_SIZE_CACHE[mod_path] = (mtime, total_size)
    return total_size


def uuid_to_packageid(uuid: str) -> str:
    """
    Converts a UUID to the corresponding mod packageid used for sorting.
    Returns the packageid in lowercase if available; otherwise an empty string.
    """
    metadata = get_mod_metadata(uuid)
    packageid = metadata.get("packageid") if metadata else None
    if isinstance(packageid, str):
        return packageid.lower()
    else:
        return ""


def uuid_to_version(uuid: str) -> str:
    """
    Converts a UUID to the corresponding mod version used for sorting.
    Returns the version in lowercase if available; otherwise an empty string.
    """
    metadata = get_mod_metadata(uuid)
    version = metadata.get("modversion") if metadata else None
    if isinstance(version, str):
        return version.lower()
    else:
        return ""


def get_dir_size(path: str) -> int:
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            for entry in scanpath(current):
                if entry.is_file():
                    total += entry.stat().st_size
                elif entry.is_dir():
                    stack.append(entry.path)
        except OSError:
            pass  # Skip file
    return total


def get_mod_metadata(uuid: str) -> Optional[ModMetadata]:
    """
    Safely retrieve metadata for a mod by UUID.

    Args:
        uuid (str): The UUID of the mod.

    Returns:
        Optional[ModMetadata]: The metadata dict if found, None otherwise.
    """
    return MetadataManager.instance().internal_local_metadata.get(uuid)


class ModsPanelSortKey(Enum):
    """
    Enum class representing different sorting keys for mods.
    """

    NOKEY = 0
    MODNAME = 1
    FILESYSTEM_MODIFIED_TIME = 2
    AUTHOR = 3
    FOLDER_SIZE = 4
    PACKAGEID = 5
    VERSION = 6


def sort_uuids(
    uuids: list[str], key: ModsPanelSortKey, descending: Optional[bool] = None
) -> list[str]:
    """
    Sort the list of UUIDs based on the provided key.
    Args:
        key (ModsPanelSortKey): The key to sort the list by.
    Returns:
        list[str]: The sorted list of UUIDs.
    """
    # Sort the list of UUIDs based on the provided key
    if key == ModsPanelSortKey.MODNAME:
        # Default alphabetical ascending unless explicitly overridden
        reverse_flag = bool(descending) if descending is not None else False
        return sorted(uuids, key=uuid_to_mod_name, reverse=reverse_flag)
    elif key == ModsPanelSortKey.FILESYSTEM_MODIFIED_TIME:
        # Default to most recent first unless explicitly overridden
        reverse_flag = bool(descending) if descending is not None else True
        return sorted(uuids, key=uuid_to_filesystem_modified_time, reverse=reverse_flag)
    elif key == ModsPanelSortKey.AUTHOR:
        reverse_flag = bool(descending) if descending is not None else False
        return sorted(uuids, key=uuid_to_author, reverse=reverse_flag)
    elif key == ModsPanelSortKey.FOLDER_SIZE:
        # Default to largest first unless explicitly overridden
        reverse_flag = bool(descending) if descending is not None else True
        return sorted(uuids, key=uuid_to_folder_size, reverse=reverse_flag)
    elif key == ModsPanelSortKey.PACKAGEID:
        reverse_flag = bool(descending) if descending is not None else False
        return sorted(uuids, key=uuid_to_packageid, reverse=reverse_flag)
    elif key == ModsPanelSortKey.VERSION:
        # Default to latest version first unless explicitly overridden
        reverse_flag = bool(descending) if descending is not None else True
        return sorted(uuids, key=uuid_to_version, reverse=reverse_flag)
    else:
        reverse_flag = bool(descending) if descending is not None else False
        return sorted(uuids, key=lambda x: x, reverse=reverse_flag)


class FolderSizeWorker(QObject):
    """Background worker to compute folder sizes with progress updates."""

    progress = Signal(int, int)  # current, total
    finished = Signal(dict)  # uuid -> size bytes

    def __init__(self, uuids: list[str]) -> None:
        super().__init__()
        self._uuids = uuids

    @Slot()
    def run(self) -> None:
        total = len(self._uuids)
        sizes: dict[str, int] = {}
        for idx, uuid in enumerate(self._uuids, start=1):
            sizes[uuid] = uuid_to_folder_size(uuid)
            self.progress.emit(idx, total)
        self.finished.emit(sizes)
