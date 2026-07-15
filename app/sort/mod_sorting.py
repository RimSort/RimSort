import os
import time
from enum import Enum

from loguru import logger
from PySide6.QtCore import QObject, Signal, Slot

from app.controllers.metadata_controller import MetadataController
from app.controllers.metadata_db_controller import AuxMetadataController
from app.models.metadata.metadata_structure import AboutXmlMod, ListedMod
from app.models.settings import Settings
from app.utils.aux_db_utils import auxdb_get_mod_tags
from app.utils.generic import scanpath

# Simple in-memory cache for folder sizes: {mod_path: (mtime, size_bytes)}
_FOLDER_SIZE_CACHE: dict[str, tuple[int, int]] = {}


def path_no_key(path: str) -> str:
    """
    Returns the path of the mod (identity function for no-key sorting).

    :param path: The path of the mod.
    :return: The path of the mod.
    """
    return path


def path_to_mod_name(
    path: str, cached_metadata: dict[str, ListedMod | None] | None = None
) -> str:
    """
    Get mod name for inactive mods list sorting.

    Optionally uses pre-cached metadata to avoid repeated lookups.

    :param path: The mod path
    :param cached_metadata: Optional pre-cached metadata dict
    :return: Mod name in lowercase, or error string if not found
    """
    if cached_metadata is not None:
        mod = cached_metadata.get(path)
    else:
        mod = get_mod_metadata(path)

    if mod is not None:
        return mod.name.lower()
    return "name error in mod about.xml"


def path_to_filesystem_modified_time(
    path: str, cached_metadata: dict[str, ListedMod | None] | None = None
) -> int:
    """
    Get filesystem modification time for inactive mods list sorting.

    :param path: The path of the mod
    :param cached_metadata: Optional pre-cached metadata dict
    :return: The filesystem modification time as Unix timestamp, or 0 if not available
    """
    if cached_metadata is not None:
        mod = cached_metadata.get(path)
    else:
        mod = get_mod_metadata(path)

    if mod is not None and mod.mod_path is not None:
        mod_path_str = str(mod.mod_path)
        if os.path.exists(mod_path_str):
            fs_time = int(os.path.getmtime(mod_path_str))
            logger.debug(f"Mod: {mod.name}, Filesystem time: {fs_time}")
            return fs_time
    return 0


def path_to_author(
    path: str, cached_metadata: dict[str, ListedMod | None] | None = None
) -> str:
    """
    Get mod author for inactive mods list sorting.

    :param path: The path of the mod
    :param cached_metadata: Optional pre-cached metadata dict
    :return: First author name in lowercase, or empty string if not found
    """
    if cached_metadata is not None:
        mod = cached_metadata.get(path)
    else:
        mod = get_mod_metadata(path)

    if isinstance(mod, AboutXmlMod) and mod.authors:
        return str(mod.authors[0]).lower()
    return ""


def path_to_folder_size(
    path: str, cached_metadata: dict[str, ListedMod | None] | None = None
) -> int:
    """
    Calculate mod folder size for inactive mods list sorting.

    :param path: The path of the mod
    :param cached_metadata: Optional pre-cached metadata dict
    :return: Total folder size in bytes, or 0 if folder not found
    """
    if cached_metadata is not None:
        mod = cached_metadata.get(path)
    else:
        mod = get_mod_metadata(path)

    if mod is None or mod.mod_path is None:
        return 0
    mod_path_str = str(mod.mod_path)
    if not os.path.isdir(mod_path_str):
        return 0
    try:
        mtime = int(os.path.getmtime(mod_path_str))
    except OSError:
        return 0

    cached = _FOLDER_SIZE_CACHE.get(mod_path_str)
    if cached and cached[0] == mtime:
        return cached[1]

    total_size = get_dir_size(mod_path_str)

    _FOLDER_SIZE_CACHE[mod_path_str] = (mtime, total_size)
    return total_size


def path_to_packageid(
    path: str, cached_metadata: dict[str, ListedMod | None] | None = None
) -> str:
    """
    Get mod package ID for inactive mods list sorting.

    :param path: The path of the mod
    :param cached_metadata: Optional pre-cached metadata dict
    :return: Package ID in lowercase, or empty string if not found
    """
    if cached_metadata is not None:
        mod = cached_metadata.get(path)
    else:
        mod = get_mod_metadata(path)

    if isinstance(mod, AboutXmlMod):
        return str(mod.package_id).lower()
    return ""


def path_to_version(
    path: str, cached_metadata: dict[str, ListedMod | None] | None = None
) -> str:
    """
    Get mod version for inactive mods list sorting.

    :param path: The path of the mod
    :param cached_metadata: Optional pre-cached metadata dict
    :return: Version string in lowercase, or empty string if not found
    """
    if cached_metadata is not None:
        mod = cached_metadata.get(path)
    else:
        mod = get_mod_metadata(path)

    if isinstance(mod, AboutXmlMod) and mod.mod_version:
        return mod.mod_version.lower()
    return ""


def path_to_mod_color(path: str, path_to_color: dict[str, str] | None = None) -> str:
    """
    Get mod color hex value for inactive mods list sorting.

    :param path: The path of the mod
    :param path_to_color: Pre-built path→color mapping from aux DB
    :return: Color hex string (e.g., "#rrggbb"), or empty string if no color assigned
    """
    if path_to_color is not None:
        color_hex = path_to_color.get(path)
        if color_hex:
            return color_hex.lower()
    return ""


def path_to_mod_tags(
    path: str,
    cached_metadata: dict[str, ListedMod | None] | None = None,
    settings: Settings | None = None,
) -> str:
    """
    Get user tags for inactive mods list sorting.

    Mods without tags sort first by an empty string. Tagged mods are sorted by
    their comma-separated, normalized tag list.
    """
    if settings is None:
        return ""

    try:
        tags = auxdb_get_mod_tags(settings, path)
    except Exception as e:
        logger.debug(f"Failed to retrieve tags for sorting path {path}: {e}")
        return ""

    return ", ".join(sorted(tag.lower() for tag in tags))


def path_to_mod_updated(
    path: str, path_to_updated: dict[str, int] | None = None
) -> int:
    """
    Get time a mod was updated on the Steam Workshop for inactive mods list sorting.

    :param path: The path of the mod
    :param path_to_updated: Pre-built path→timestamp mapping from aux DB
    :return: Update timestamp as int, or 0 if not available
    """
    if path_to_updated is not None:
        return path_to_updated.get(path, 0)
    return 0


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


def get_mod_metadata(path: str) -> ListedMod | None:
    """
    Safely retrieve metadata for a mod by path.

    :param path: The path of the mod.
    :return: The ListedMod if found, None otherwise.
    """
    return MetadataController.instance().mods_metadata.get(path)


def get_cached_metadata_for_batch(
    paths: list[str],
) -> dict[str, ListedMod | None]:
    """
    Pre-fetch metadata for a batch of paths to optimize sorting operations.

    Batch-fetches all metadata once before sorting, reducing repeated
    MetadataController lookups during the sort process.

    :param paths: List of mod paths to fetch metadata for
    :return: Dictionary mapping path -> ListedMod (or None if not found).
    """
    metadata_controller = MetadataController.instance()
    cached: dict[str, ListedMod | None] = {}

    for path in paths:
        cached[path] = metadata_controller.mods_metadata.get(path)

    return cached


def _get_path_to_color_map(
    paths: list[str],
    settings: Settings,
) -> dict[str, str]:
    """Build a path→color_hex mapping from the aux DB for color-based sorting.

    :param paths: List of mod paths to fetch colors for
    :param settings: Settings instance
    :return: Dictionary mapping path -> color_hex string (only includes mods with colors)
    """
    path_to_color: dict[str, str] = {}
    try:
        aux_controller = AuxMetadataController.get_or_create_cached_instance(
            settings.aux_db_path
        )
        with aux_controller.Session() as aux_session:
            for path in paths:
                aux_entry = aux_controller.get(aux_session, path)
                if aux_entry and aux_entry.color_hex:
                    path_to_color[path] = aux_entry.color_hex
    except Exception as e:
        logger.warning(f"Failed to fetch auxiliary metadata for batch: {e}")
    return path_to_color


def _get_path_to_updated_map(
    paths: list[str],
    settings: Settings,
) -> dict[str, int]:
    """Build a path→acf_time_updated mapping from the aux DB for update-time sorting.

    :param paths: List of mod paths to fetch update times for
    :param settings: Settings instance
    :return: Dictionary mapping path -> update timestamp (only includes mods with valid timestamps)
    """
    path_to_updated: dict[str, int] = {}
    try:
        aux_controller = AuxMetadataController.get_or_create_cached_instance(
            settings.aux_db_path
        )
        with aux_controller.Session() as aux_session:
            for path in paths:
                aux_entry = aux_controller.get(aux_session, path)
                if aux_entry and aux_entry.acf_time_updated > 0:
                    path_to_updated[path] = aux_entry.acf_time_updated
    except Exception as e:
        logger.warning(f"Failed to fetch update times from auxiliary metadata: {e}")
    return path_to_updated


def _build_sort_key_map(
    paths: list[str],
    key: "ModsPanelSortKey",
    cached_metadata: dict[str, ListedMod | None] | None = None,
    settings: Settings | None = None,
    path_to_color: dict[str, str] | None = None,
    path_to_updated: dict[str, int] | None = None,
) -> dict[str, str | int]:
    """
    Pre-compute sort keys for all paths to improve sort performance.

    :param paths: List of mod paths to compute keys for
    :param key: The ModsPanelSortKey enum indicating which attribute to extract
    :param cached_metadata: Optional pre-cached metadata dict
    :param settings: Optional Settings for tag sorting
    :param path_to_color: Optional pre-built path→color mapping for color sorting
    :param path_to_updated: Optional pre-built path→timestamp mapping for update-time sorting
    :return: Dictionary mapping path -> computed sort key value (str or int).
    """
    sort_key_map: dict[str, str | int] = {}
    for path in paths:
        if key == ModsPanelSortKey.MODNAME:
            sort_key_map[path] = path_to_mod_name(path, cached_metadata)
        elif key == ModsPanelSortKey.FILESYSTEM_MODIFIED_TIME:
            sort_key_map[path] = path_to_filesystem_modified_time(path, cached_metadata)
        elif key == ModsPanelSortKey.AUTHOR:
            sort_key_map[path] = path_to_author(path, cached_metadata)
        elif key == ModsPanelSortKey.FOLDER_SIZE:
            sort_key_map[path] = path_to_folder_size(path, cached_metadata)
        elif key == ModsPanelSortKey.PACKAGEID:
            sort_key_map[path] = path_to_packageid(path, cached_metadata)
        elif key == ModsPanelSortKey.VERSION:
            sort_key_map[path] = path_to_version(path, cached_metadata)
        elif key == ModsPanelSortKey.MOD_COLOR:
            sort_key_map[path] = path_to_mod_color(path, path_to_color)
        elif key == ModsPanelSortKey.MOD_TAGS:
            sort_key_map[path] = path_to_mod_tags(path, cached_metadata, settings)
        elif key == ModsPanelSortKey.MOD_UPDATED:
            sort_key_map[path] = path_to_mod_updated(path, path_to_updated)
        else:
            sort_key_map[path] = path
    return sort_key_map


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
    MOD_COLOR = 7
    MOD_TAGS = 8
    MOD_UPDATED = 9


# Lookup dictionary for default sort direction flags
# All sorts default to False (ascending) - actual direction controlled by UI toggle
DEFAULT_REVERSE_FLAGS = {
    ModsPanelSortKey.NOKEY: False,
    ModsPanelSortKey.MODNAME: False,
    ModsPanelSortKey.FILESYSTEM_MODIFIED_TIME: False,
    ModsPanelSortKey.AUTHOR: False,
    ModsPanelSortKey.FOLDER_SIZE: False,
    ModsPanelSortKey.PACKAGEID: False,
    ModsPanelSortKey.VERSION: False,
    ModsPanelSortKey.MOD_COLOR: False,
    ModsPanelSortKey.MOD_TAGS: False,
    ModsPanelSortKey.MOD_UPDATED: False,
}


def sort_paths(
    paths: list[str],
    key: ModsPanelSortKey,
    descending: bool | None = None,
    cached_metadata: dict[str, ListedMod | None] | None = None,
    settings: Settings | None = None,
) -> list[str]:
    """
    Sort mod paths by the specified attribute.

    Core sorting function for mods list operations. Uses pre-computed
    sort keys and optional pre-cached metadata for performance optimization.

    :param paths: List of mod paths to sort
    :param key: ModsPanelSortKey enum specifying the sort attribute
    :param descending: Optional bool to override default sort direction.
    :param cached_metadata: Optional pre-cached metadata dict.
    :param settings: Optional Settings for fetching auxiliary metadata.
    :return: Sorted list of paths in the specified order.
    """
    # Performance instrumentation - track sort timing
    start_time = time.perf_counter()

    # Build color map if sorting by color
    path_to_color: dict[str, str] | None = None
    if key == ModsPanelSortKey.MOD_COLOR and settings is not None:
        path_to_color = _get_path_to_color_map(paths, settings)

    # Build update-time map if sorting by update time
    path_to_updated: dict[str, int] | None = None
    if key == ModsPanelSortKey.MOD_UPDATED and settings is not None:
        path_to_updated = _get_path_to_updated_map(paths, settings)

    # Pre-compute sort keys to avoid repeated function calls during sort
    sort_key_map = _build_sort_key_map(
        paths,
        key,
        cached_metadata,
        settings=settings,
        path_to_color=path_to_color,
        path_to_updated=path_to_updated,
    )

    # Get sort direction from default flags or explicit override
    default_reverse = DEFAULT_REVERSE_FLAGS.get(key, False)
    reverse_flag = bool(descending) if descending is not None else default_reverse

    # Sort using the pre-computed keys
    sorted_result = sorted(
        paths,
        key=lambda p: sort_key_map[p],
        reverse=reverse_flag,
    )

    # Log performance metrics for debugging and monitoring
    elapsed = time.perf_counter() - start_time
    logger.debug(
        f"Sorted {len(paths)} mods by {key.name} ({reverse_flag and 'desc' or 'asc'}) in {elapsed:.3f}s"
    )

    return sorted_result


class FolderSizeWorker(QObject):
    """
    Background worker for calculating mod folder sizes with progress updates.

    Runs in a separate QThread to calculate folder sizes for all mods without
    blocking the UI.

    Signals:
        progress: Emitted with (current_idx: int, total: int) during calculation
        finished: Emitted on completion with dict[path -> size_in_bytes]
    """

    progress = Signal(int, int)  # current, total
    finished = Signal(dict)  # path -> size bytes

    def __init__(self, paths: list[str]) -> None:
        """
        Initialize the folder size worker.

        :param paths: List of mod paths whose folder sizes to calculate
        """
        super().__init__()
        self._paths = paths

    @Slot()
    def run(self) -> None:
        """
        Calculate folder sizes for all paths with progress reporting.

        Emits progress signals during calculation and a finished signal on completion.
        """
        # Performance instrumentation - track folder size calculation time
        start_time = time.perf_counter()

        total = len(self._paths)
        sizes: dict[str, int] = {}

        # Pre-fetch all metadata once to avoid repeated lookups
        cached_metadata = get_cached_metadata_for_batch(self._paths)
        logger.debug(
            f"Pre-cached metadata for {len(cached_metadata)} mods in FolderSizeWorker"
        )

        # Calculate folder sizes with progress reporting
        for idx, path in enumerate(self._paths, start=1):
            sizes[path] = path_to_folder_size(path, cached_metadata)
            self.progress.emit(idx, total)

        # Log folder size calculation performance metrics
        elapsed = time.perf_counter() - start_time
        logger.debug(
            f"Calculated folder sizes for {total} mods in {elapsed:.3f}s ({elapsed / total * 1000:.1f}ms per mod)"
        )

        # Signal completion with results
        self.finished.emit(sizes)
