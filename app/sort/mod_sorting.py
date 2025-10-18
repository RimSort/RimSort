import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from typing import Optional

from loguru import logger
from PySide6.QtCore import QObject, Signal, Slot

from app.controllers.metadata_db_controller import AuxMetadataController
from app.utils.metadata import MetadataManager, ModMetadata


def get_sorting_data_from_db(mod_path: str, field_name: str) -> Optional[str | int]:
    """
    Retrieve sorting data from the auxiliary metadata database.

    Args:
        mod_path (str): The path to the mod.
        field_name (str): The name of the field to retrieve.

    Returns:
        Optional[str | int]: The value of the field if found, None otherwise.
    """
    try:
        db_path = MetadataManager.instance().settings_controller.settings.db_path
        controller = AuxMetadataController.get_or_create_cached_instance(db_path)
        with controller.Session() as session:
            sorting_data = AuxMetadataController.get_sorting_data(session, mod_path)
            if sorting_data and sorting_data.get(field_name):
                value = sorting_data[field_name]
                if isinstance(value, (str, int)):
                    return value
    except Exception as e:
        logger.debug(f"Failed to get {field_name} from DB for {mod_path}: {e}")
    return None


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
    # Try to get from aux_metadata.db first
    metadata = get_mod_metadata(uuid)
    mod_path = metadata.get("path") if metadata else None
    if mod_path:
        mod_name = get_sorting_data_from_db(mod_path, "mod_name")
        if isinstance(mod_name, str):
            return mod_name.lower()

    # Fallback to MetadataManager
    name = metadata.get("name") if metadata else None
    if isinstance(name, str):
        return name.lower()
    else:
        return "name error in mod about.xml"


def uuid_to_author(uuid: str) -> str:
    """
    Converts a UUID to the corresponding author's name used for sorting.
    Returns the first author in lowercase if available; otherwise an empty string.
    """
    # Try to get from aux_metadata.db first
    metadata = get_mod_metadata(uuid)
    mod_path = metadata.get("path") if metadata else None
    if mod_path:
        author_db = get_sorting_data_from_db(mod_path, "author")
        if isinstance(author_db, str):
            return author_db.lower()

    # Fallback to MetadataManager
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


def uuid_to_packageid(uuid: str) -> str:
    """
    Converts a UUID to the corresponding mod packageid used for sorting.
    Returns the packageid in lowercase if available; otherwise an empty string.
    """
    # Try to get from aux_metadata.db first
    metadata = get_mod_metadata(uuid)
    mod_path = metadata.get("path") if metadata else None
    if mod_path:
        packageid_db = get_sorting_data_from_db(mod_path, "packageid")
        if isinstance(packageid_db, str):
            return packageid_db.lower()

    # Fallback to MetadataManager
    packageid = metadata.get("packageid") if metadata else None
    if isinstance(packageid, str):
        return packageid.lower()
    else:
        return ""


def uuid_to_supported_versions(uuid: str) -> tuple[int, ...]:
    """
    Converts a UUID to the corresponding mod version as a tuple of integers for proper semantic sorting.
    Returns a tuple of integers parsed from the highest supported game version.
    If supportedVersions is not available, returns (0,).
    """
    # Try to get from aux_metadata.db first
    metadata = get_mod_metadata(uuid)
    mod_path = metadata.get("path") if metadata else None
    if mod_path:
        supported_versions_db = get_sorting_data_from_db(mod_path, "supported_version")
        if isinstance(supported_versions_db, str):
            try:
                parts = supported_versions_db.split(".")
                return tuple(int(part) for part in parts if part.isdigit())
            except ValueError:
                return (0,)

    # Fallback to MetadataManager
    supported_versions = metadata.get("supportedversions") if metadata else None
    version_list = None
    if isinstance(supported_versions, dict):
        version_list = supported_versions.get("li")
    elif isinstance(supported_versions, set):
        version_list = supported_versions
    elif isinstance(supported_versions, list):
        version_list = supported_versions
    elif isinstance(supported_versions, str):
        version_list = [supported_versions]

    if version_list:
        version_tuples = []
        for ver_str in version_list:
            if isinstance(ver_str, str):
                try:
                    parts = ver_str.split(".")
                    version_tuples.append(
                        tuple(int(part) for part in parts if part.isdigit())
                    )
                except ValueError:
                    continue
        if version_tuples:
            max_version_tuple = max(version_tuples)
            # Store the max version as string in DB
            if mod_path:
                max_version_str = ".".join(str(part) for part in max_version_tuple)
                try:
                    db_path = (
                        MetadataManager.instance().settings_controller.settings.db_path
                    )
                    controller = AuxMetadataController.get_or_create_cached_instance(
                        db_path
                    )
                    with controller.Session() as session:
                        AuxMetadataController.update_sorting_data(
                            session, mod_path, supported_version=max_version_str
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to store supported version in DB for {uuid}: {e}"
                    )
            return max_version_tuple
    return (0,)


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
    if mod_path:
        # Try to get from aux_metadata.db first
        filesystem_mtime = get_sorting_data_from_db(mod_path, "filesystem_mtime")
        if isinstance(filesystem_mtime, int) and filesystem_mtime > 0:
            mod_name = metadata.get("name") if metadata else "Unknown"
            logger.debug(
                f"Using cached filesystem mtime from DB for mod '{mod_name}': {filesystem_mtime}"
            )
            return filesystem_mtime

        # Compute and store in DB
        if os.path.exists(mod_path):
            fs_time = int(os.path.getmtime(mod_path))
            mod_name = metadata.get("name") if metadata else "Unknown"
            logger.debug(f"Computing filesystem mtime for mod '{mod_name}': {fs_time}")
            try:
                db_path = (
                    MetadataManager.instance().settings_controller.settings.db_path
                )
                controller = AuxMetadataController.get_or_create_cached_instance(
                    db_path
                )
                with controller.Session() as session:
                    AuxMetadataController.update_sorting_data(
                        session, mod_path, filesystem_mtime=fs_time
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to store filesystem mtime in DB for {uuid}: {e}"
                )
            return fs_time
    return 0


def uuid_to_folder_size(uuid: str) -> int:
    """
    Calculate the total size in bytes of the mod folder for the given UUID.
    Returns 0 if the path is missing.
    """
    metadata = get_mod_metadata(uuid)
    mod_path = metadata.get("path") if metadata else None
    if not mod_path or not os.path.isdir(mod_path):
        return 0

    # Try to get from aux_metadata.db first
    folder_size = get_sorting_data_from_db(mod_path, "folder_size")
    if isinstance(folder_size, int) and folder_size > 0:
        mod_name = metadata.get("name") if metadata else "Unknown"
        logger.debug(
            f"Using cached folder size from DB for mod '{mod_name}': {folder_size} bytes"
        )
        return folder_size

    # Compute and store in DB
    mod_name = metadata.get("name") if metadata else "Unknown"
    logger.debug(f"Computing folder size for mod '{mod_name}' (not cached)")
    total_size = get_dir_size(mod_path)

    # Store in database
    try:
        db_path = MetadataManager.instance().settings_controller.settings.db_path
        controller = AuxMetadataController.get_or_create_cached_instance(db_path)
        with controller.Session() as session:
            AuxMetadataController.update_sorting_data(
                session, mod_path, folder_size=total_size
            )
    except Exception as e:
        logger.warning(f"Failed to store folder size in DB for {uuid}: {e}")

    return total_size


def get_dir_size(path: str) -> int:
    """
    Calculate the total size of a directory using os.walk for better performance.
    """
    total = 0
    try:
        for root, dirs, files in os.walk(path):
            for file in files:
                try:
                    total += os.path.getsize(os.path.join(root, file))
                except OSError:
                    pass  # Skip inaccessible files
    except OSError:
        pass  # Skip inaccessible directories
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
    AUTHOR = 2
    PACKAGEID = 3
    SUPPORTED_VERSION = 4
    FILESYSTEM_MODIFIED_TIME = 5
    FOLDER_SIZE = 6


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
    elif key == ModsPanelSortKey.AUTHOR:
        reverse_flag = bool(descending) if descending is not None else False
        return sorted(uuids, key=uuid_to_author, reverse=reverse_flag)
    elif key == ModsPanelSortKey.PACKAGEID:
        reverse_flag = bool(descending) if descending is not None else False
        return sorted(uuids, key=uuid_to_packageid, reverse=reverse_flag)
    elif key == ModsPanelSortKey.SUPPORTED_VERSION:
        # Default to latest version first unless explicitly overridden
        reverse_flag = bool(descending) if descending is not None else True
        return sorted(uuids, key=uuid_to_supported_versions, reverse=reverse_flag)
    elif key == ModsPanelSortKey.FILESYSTEM_MODIFIED_TIME:
        # Default to most recent first unless explicitly overridden
        reverse_flag = bool(descending) if descending is not None else True
        return sorted(uuids, key=uuid_to_filesystem_modified_time, reverse=reverse_flag)
    elif key == ModsPanelSortKey.FOLDER_SIZE:
        # Default to largest first unless explicitly overridden
        reverse_flag = bool(descending) if descending is not None else True
        return sorted(uuids, key=uuid_to_folder_size, reverse=reverse_flag)
    else:
        reverse_flag = bool(descending) if descending is not None else False
        return sorted(uuids, key=lambda x: x, reverse=reverse_flag)


class FolderSizeWorker(QObject):
    """Background worker to compute folder sizes with progress updates using parallel computation."""

    progress = Signal(int, int)  # current, total
    finished = Signal(dict)  # uuid -> size bytes

    def __init__(self, uuids: list[str]) -> None:
        super().__init__()
        self._uuids = uuids

    @Slot()
    def run(self) -> None:
        total = len(self._uuids)
        sizes: dict[str, int] = {}
        completed = 0

        # Increase max_workers for better parallelism (up to 16 or total, whichever is smaller)
        max_workers = min(16, total)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(uuid_to_folder_size, uuid): uuid for uuid in self._uuids
            }
            for future in as_completed(futures):
                uuid = futures[future]
                try:
                    sizes[uuid] = future.result()
                except Exception as exc:
                    logger.error(f"Error computing size for {uuid}: {exc}")
                    sizes[uuid] = 0
                completed += 1
                self.progress.emit(completed, total)

        self.finished.emit(sizes)


class SilentFolderSizeWorker(QObject):
    """Background worker to silently compute folder sizes for all inactive mods without progress updates."""

    finished = Signal()  # No data needed, just signal completion

    def __init__(self, uuids: list[str]) -> None:
        super().__init__()
        self._uuids = uuids

    @Slot()
    def run(self) -> None:
        # Increase max_workers for better parallelism (up to 16 or total, whichever is smaller)
        max_workers = min(16, len(self._uuids))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(uuid_to_folder_size, uuid): uuid for uuid in self._uuids
            }
            for future in as_completed(futures):
                uuid = futures[future]
                try:
                    future.result()  # This will update the cache
                except Exception as exc:
                    logger.error(f"Error computing size for {uuid}: {exc}")

        self.finished.emit()
