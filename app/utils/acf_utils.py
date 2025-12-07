"""
ACF Utilities Module

This module provides utility functions for handling ACF (AppWorkshop ACF) data,
which contains Steam Workshop item metadata including timestamps and other
information about installed workshop items.

The module includes functions for loading, parsing, merging, and manipulating
ACF files from both Steam client and SteamCMD installations. It handles errors
gracefully and provides logging for debugging and monitoring.

Key functions:
- load_acf_from_path: Safely load and parse ACF files
- refresh_acf_metadata: Load ACF data into MetadataManager
- load_and_merge_acf_data: Merge ACF data from multiple sources
- steamcmd_purge_mods: Remove mods from SteamCMD ACF metadata
- validate_acf_file_exists: Validate that appworkshop_294100.acf exists
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from app.utils.steam.steamfiles.wrapper import acf_to_dict, dict_to_acf

if TYPE_CHECKING:
    from app.utils.metadata import MetadataManager


def load_acf_from_path(acf_path: str | Path) -> dict[str, Any]:
    """
    Load and parse an ACF file from a given file path.

    Safely loads an ACF (AppWorkshop ACF) file and returns the parsed data as a
    dictionary. ACF files contain Steam Workshop metadata in a key-value format.
    Returns an empty dictionary if the file doesn't exist or parsing fails,
    allowing calling code to handle missing files gracefully.

    Args:
        acf_path: Path to the ACF file (string or Path object). Typically
                 appworkshop_294100.acf for RimWorld workshop data.

    Returns:
        Parsed ACF data dictionary containing workshop metadata, or empty dict {}
        if file not found or parsing fails. The dictionary structure includes
        sections like "AppWorkshop" with nested data.

    Example:
        >>> data = load_acf_from_path("path/to/appworkshop_294100.acf")
        >>> workshop_items = data.get("AppWorkshop", {}).get("WorkshopItemsInstalled", {})
    """
    # Convert string path to Path object for consistency
    acf_path = Path(acf_path) if isinstance(acf_path, str) else acf_path

    # Check if file exists before attempting to parse
    if not acf_path.exists():
        logger.warning(f"ACF file not found: {acf_path}")
        return {}

    # Parse the ACF file using the steamfiles wrapper
    try:
        return acf_to_dict(str(acf_path))
    except Exception as e:
        logger.error(f"Failed to parse ACF file at {acf_path}: {e}")
        return {}


def refresh_acf_metadata(
    metadata_manager: "MetadataManager", steamclient: bool = True, steamcmd: bool = True
) -> None:
    """
    Load and cache ACF metadata from Steam and SteamCMD sources.

    Parses appworkshop_294100.acf files from both Steam client and SteamCMD
    installations, storing the results in MetadataManager for later use.
    Each source is loaded independently; errors in one do not affect the other.
    This function is typically called during application startup or when
    refreshing metadata cache.

    Args:
        metadata_manager: The MetadataManager instance to update with ACF data.
                         Must have workshop_acf_path and steamcmd_wrapper configured.
        steamclient: If True, load Steam client ACF data. Defaults to True.
        steamcmd: If True, load SteamCMD ACF data. Defaults to True.

    Note:
        - Steam client ACF data is stored in metadata_manager.workshop_acf_data
        - SteamCMD ACF data is stored in metadata_manager.steamcmd_acf_data
        - Failed loads are logged but don't raise exceptions
    """
    # Load Steam client appworkshop_294100.acf if enabled
    if steamclient:
        workshop_data = load_acf_from_path(metadata_manager.workshop_acf_path)
        if workshop_data:
            metadata_manager.workshop_acf_data = workshop_data
            logger.info(
                f"Successfully parsed Steam client appworkshop.acf metadata from: {metadata_manager.workshop_acf_path}"
            )
        else:
            logger.warning("Failed to load Steam client ACF data")

    # Load SteamCMD appworkshop_294100.acf if enabled
    if steamcmd:
        steamcmd_data = load_acf_from_path(
            metadata_manager.steamcmd_wrapper.steamcmd_appworkshop_acf_path
        )
        if steamcmd_data:
            metadata_manager.steamcmd_acf_data = steamcmd_data
            logger.info(
                f"Successfully parsed SteamCMD appworkshop.acf metadata from: {metadata_manager.steamcmd_wrapper.steamcmd_appworkshop_acf_path}"
            )
        else:
            logger.warning("Failed to load SteamCMD ACF data")


def parse_timeupdated(timeupdated_raw: Any) -> int | None:
    """
    Parse and validate a timeupdated value from ACF metadata.

    Attempts to convert the raw value to an integer timestamp. ACF files store
    timestamps as strings, but this function handles various input types robustly.
    Returns None for missing or invalid values without raising exceptions,
    allowing robust handling of malformed ACF entries.

    Args:
        timeupdated_raw: The raw timeupdated value from ACF data (typically a string
                        in ACF format, but may be int or other types).

    Returns:
        Parsed integer timestamp (Unix epoch time), or None if value is missing,
        not convertible, or invalid.

    Example:
        >>> parse_timeupdated("1640995200")  # Valid string timestamp
        1640995200
        >>> parse_timeupdated(1640995200)    # Valid int timestamp
        1640995200
        >>> parse_timeupdated("invalid")     # Invalid string
        None
        >>> parse_timeupdated(None)          # Missing value
        None
    """
    if timeupdated_raw is None:
        return None
    try:
        return int(timeupdated_raw)
    except (ValueError, TypeError):
        return None


def get_workshop_items_from_acf(acf_data: dict[str, Any]) -> dict[str, Any]:
    """
    Extract workshop item information from parsed ACF data.

    Safely retrieves the WorkshopItemsInstalled section from ACF metadata,
    which contains details about installed workshop mods. Returns an empty
    dictionary if the section is missing or malformed, allowing graceful
    handling of incomplete ACF files.

    Args:
        acf_data: Parsed ACF data dictionary (typically from load_acf_from_path
                 or acf_to_dict). Should contain AppWorkshop section.

    Returns:
        WorkshopItemsInstalled dictionary mapping PFID strings to item metadata
        dictionaries. Each item dict typically contains keys like "timeupdated",
        "manifest", etc. Returns empty dict {} if the section is not found.

    Example:
        >>> acf_data = load_acf_from_path("appworkshop_294100.acf")
        >>> items = get_workshop_items_from_acf(acf_data)
        >>> # items["123456789"] might contain {"timeupdated": "1640995200", ...}
    """
    return acf_data.get("AppWorkshop", {}).get("WorkshopItemsInstalled", {})


def _merge_workshop_items_from_sources(
    steamcmd_items: dict[str, Any],
    steam_items: dict[str, Any],
    steamcmd_source: str,
    steam_source: str,
) -> list[tuple[str, str, int | None]]:
    """
    Merge workshop items from two sources with source attribution and deduplication.

    Internal helper function to avoid code duplication between get_acf_workshop_items
    and load_and_merge_acf_data. Processes workshop items from the first source
    (prioritized), then adds items from the second source, skipping any PFIDs
    already processed. Each item gets source attribution and parsed timestamps.

    Args:
        steamcmd_items: Workshop items dict from first source (typically SteamCMD).
                       Maps PFID strings to item metadata dicts.
        steam_items: Workshop items dict from second source (typically Steam).
                    Maps PFID strings to item metadata dicts.
        steamcmd_source: Label for first source (e.g., "SteamCMD").
        steam_source: Label for second source (e.g., "Steam").

    Returns:
        List of (pfid, source, timeupdated) tuples with deduplication applied.
        Each tuple contains:
        - pfid: Published File ID as string
        - source: Source label (steamcmd_source or steam_source)
        - timeupdated: Parsed timestamp as int, or None if invalid/missing

    Note:
        - First source items take precedence over second source for same PFID
        - Invalid timeupdated values are logged but included with None timestamp
        - Only dict-type items are processed; others are skipped
    """
    entries: list[tuple[str, str, int | None]] = []
    seen_pfids = set()

    # Process first source (prioritized) - typically SteamCMD
    for pfid, item in steamcmd_items.items():
        if not isinstance(item, dict):
            continue
        pfid_str = str(pfid)
        if pfid_str not in seen_pfids:
            # Parse timestamp with validation
            timeupdated_int = parse_timeupdated(item.get("timeupdated"))
            if timeupdated_int is None and item.get("timeupdated") is not None:
                logger.warning(
                    f"Invalid timeupdated for PFID {pfid_str}: {item.get('timeupdated')}"
                )
            entries.append((pfid_str, steamcmd_source, timeupdated_int))
            seen_pfids.add(pfid_str)

    # Process second source, skipping any PFIDs already added
    for pfid, item in steam_items.items():
        if not isinstance(item, dict):
            continue
        pfid_str = str(pfid)
        if pfid_str not in seen_pfids:
            # Parse timestamp with validation
            timeupdated_int = parse_timeupdated(item.get("timeupdated"))
            if timeupdated_int is None and item.get("timeupdated") is not None:
                logger.warning(
                    f"Invalid timeupdated for PFID {pfid_str}: {item.get('timeupdated')}"
                )
            entries.append((pfid_str, steam_source, timeupdated_int))
            seen_pfids.add(pfid_str)

    return entries


def get_acf_workshop_items(
    metadata_manager: "MetadataManager",
) -> tuple[list[tuple[str, str, int | None]], dict[str, Any], dict[str, Any]]:
    """
    Merge and deduplicate workshop items from both SteamCMD and Steam sources.

    Uses cached ACF data from MetadataManager to combine workshop item entries
    from both ACF sources. Prioritizes SteamCMD items over Steam items when
    duplicates are found (same PFID). This function is used by the ACF log reader
    to display workshop items from both installations.

    Args:
        metadata_manager: The MetadataManager instance containing cached ACF data.
                         Must have steamcmd_acf_data and workshop_acf_data populated
                         (typically via refresh_acf_metadata).

    Returns:
        Tuple of (entries, steamcmd_acf_data, workshop_acf_data) where:
        - entries: List of (pfid, source, timeupdated) tuples with deduplication
          applied. Source is "SteamCMD" or "Steam", timeupdated is parsed int or None.
        - steamcmd_acf_data: Raw SteamCMD ACF data dict (may be None)
        - workshop_acf_data: Raw Steam Workshop ACF data dict (may be None)

    Note:
        - Returns empty lists/dicts if no ACF data is cached
        - SteamCMD items take precedence over Steam items for same PFID
        - Invalid timeupdated values are logged but included with None timestamp
    """
    # Extract workshop items from cached SteamCMD ACF data
    steamcmd_items = (
        get_workshop_items_from_acf(metadata_manager.steamcmd_acf_data)
        if metadata_manager.steamcmd_acf_data
        else {}
    )
    # Extract workshop items from cached Steam ACF data
    workshop_items = (
        get_workshop_items_from_acf(metadata_manager.workshop_acf_data)
        if metadata_manager.workshop_acf_data
        else {}
    )

    # Merge items with source attribution and deduplication
    entries = _merge_workshop_items_from_sources(
        steamcmd_items, workshop_items, "SteamCMD", "Steam"
    )

    return (
        entries,
        metadata_manager.steamcmd_acf_data,
        metadata_manager.workshop_acf_data,
    )


def load_and_merge_acf_data(
    steamcmd_acf_path: "str | Path | None",
    steam_acf_path: "str | Path | None",
) -> tuple[list[tuple[str, str, int | None]], dict[str, Any], dict[str, Any]]:
    """
    Load ACF files from both sources and merge workshop item data.

    Loads and parses ACF files from SteamCMD and Steam paths, then merges the
    workshop item entries with proper source attribution. Handles missing files,
    parsing errors, and source-based deduplication gracefully.

    Args:
        steamcmd_acf_path: Path to SteamCMD appworkshop_294100.acf, or None.
        steam_acf_path: Path to Steam appworkshop_294100.acf, or None.

    Returns:
        Tuple of (entries, steamcmd_acf_data, steam_acf_data) where:
        - entries: List of (pfid, source, timeupdated) tuples with source labels
                  and deduplication applied. Source is "SteamCMD" or "Steam"
        - steamcmd_acf_data: Raw parsed SteamCMD ACF data dict
        - steam_acf_data: Raw parsed Steam ACF data dict

    Raises:
        ValueError: If no ACF data could be loaded from either source.
    """
    # Load ACF files from both sources
    steamcmd_acf_data = (
        load_acf_from_path(steamcmd_acf_path) if steamcmd_acf_path else {}
    )
    steam_acf_data = load_acf_from_path(steam_acf_path) if steam_acf_path else {}

    if not steamcmd_acf_data and not steam_acf_data:
        raise ValueError("Failed to load any ACF data from SteamCMD or Steam paths")

    # Get workshop items from each source
    steamcmd_items = get_workshop_items_from_acf(steamcmd_acf_data)
    steam_items = get_workshop_items_from_acf(steam_acf_data)

    if not isinstance(steamcmd_items, dict) or not isinstance(steam_items, dict):
        raise ValueError("Invalid workshop items data format")

    # Merge items with source attribution using shared helper
    entries = _merge_workshop_items_from_sources(
        steamcmd_items, steam_items, "SteamCMD", "Steam"
    )

    return entries, steamcmd_acf_data, steam_acf_data


def _extract_manifest_ids_and_remove_pfid(
    workshop_section: dict[str, Any] | None, delete_pfid: str
) -> set[str]:
    """
    Extract manifest IDs from a workshop section and remove a PFID entry.

    Helper for steamcmd_purge_mods. Extracts any manifest IDs associated with
    the PFID and removes the entry from the section.

    Args:
        workshop_section: WorkshopItemsInstalled or WorkshopItemDetails dict, or None.
        delete_pfid: Published File ID to remove.

    Returns:
        Set of manifest IDs found for this PFID (may be empty).
    """
    manifest_ids = set()
    if workshop_section is not None:
        item = workshop_section.get(delete_pfid, {})
        if isinstance(item, dict):
            manifest_id = item.get("manifest")
            if manifest_id is not None:
                manifest_ids.add(manifest_id)
        workshop_section.pop(delete_pfid, None)
    return manifest_ids


def steamcmd_purge_mods(
    metadata_manager: "MetadataManager",
    publishedfileids: set[str],
    auto_clear_enabled: bool = True,
) -> None:
    """
    Remove mods from SteamCMD installation and clean up associated files.

    Deletes specified workshop items from the SteamCMD appworkshop_294100.acf file
    and removes associated manifest files from the depotcache directory. Handles
    both WorkshopItemsInstalled and WorkshopItemDetails sections to ensure
    complete removal.

    This function is called when mods are deleted from the mod list to keep the
    SteamCMD installation synchronized. It's designed to be robust and continue
    operation even if some files are missing or operations fail.

    Args:
        metadata_manager: The MetadataManager instance with SteamCMD paths
                         configured. Must have steamcmd_wrapper with valid paths.
        publishedfileids: Set of published file IDs (PFIDs) as strings to remove
                         from SteamCMD. These correspond to workshop item IDs.
        auto_clear_enabled: Whether to perform the purge operation. If False,
                           returns early without making any changes. Defaults to True.

    Note:
        The operation is tolerant of missing files and parsing errors:
        - If auto_clear_enabled is False, returns early without error
        - If ACF file is missing, returns early without error
        - If parsing fails, returns early without error
        - Individual manifest file deletions are logged but don't halt the operation
        - No exceptions are raised; all errors are logged instead

    Example:
        >>> steamcmd_purge_mods(metadata_manager, {"123456789", "987654321"})
        # Removes the specified mods from SteamCMD ACF and deletes manifest files
    """
    # Return early if auto-clear is not enabled
    if not auto_clear_enabled:
        logger.debug("SteamCMD auto-clear is disabled, skipping mod purge operation")
        return

    # Load SteamCMD workshop ACF metadata file
    acf_path = metadata_manager.steamcmd_wrapper.steamcmd_appworkshop_acf_path
    acf_metadata = load_acf_from_path(acf_path)
    if not acf_metadata:
        logger.warning(
            f"SteamCMD ACF file not found or failed to parse at: {acf_path}. Skipping mod removal."
        )
        return

    # Get depotcache directory path for manifest file cleanup
    depotcache_path = metadata_manager.steamcmd_wrapper.steamcmd_depotcache_path

    # Extract workshop sections from ACF metadata
    workshop_items_installed = acf_metadata.get("AppWorkshop", {}).get(
        "WorkshopItemsInstalled"
    )
    workshop_item_details = acf_metadata.get("AppWorkshop", {}).get(
        "WorkshopItemDetails"
    )

    # Collect manifest IDs associated with mods being removed
    mod_manifest_ids = set()

    # Process each PFID to be removed
    for delete_pfid in publishedfileids:
        # Extract manifest IDs from both sections and remove entries
        manifest_ids_installed = _extract_manifest_ids_and_remove_pfid(
            workshop_items_installed, delete_pfid
        )
        manifest_ids_details = _extract_manifest_ids_and_remove_pfid(
            workshop_item_details, delete_pfid
        )
        # Accumulate all manifest IDs found
        mod_manifest_ids.update(manifest_ids_installed)
        mod_manifest_ids.update(manifest_ids_details)

    # Write updated ACF metadata back to file
    dict_to_acf(data=acf_metadata, path=acf_path)

    # Clean up manifest files from depotcache directory
    for mod_manifest_id in mod_manifest_ids:
        manifest_path = Path(depotcache_path) / f"294100_{mod_manifest_id}.manifest"
        if manifest_path.exists():
            logger.debug(f"Removing mod manifest file: {manifest_path}")
            try:
                manifest_path.unlink()
            except Exception as e:
                logger.error(f"Failed to remove manifest file {manifest_path}: {e}")


def validate_acf_file_exists(steam_mods_location: str) -> bool:
    """
    Validate that appworkshop_294100.acf file exists in the provided path.

    Checks if appworkshop_294100.acf exists directly in the provided directory.
    Supports custom Steam locations and cross-platform usage.

    Args:
        steam_mods_location: Path to search for appworkshop_294100.acf file.

    Returns:
        True if appworkshop_294100.acf exists in the path, False otherwise.

    Example:
        >>> validate_acf_file_exists("C:\\Steam\\steamapps")
        True  # if appworkshop_294100.acf exists there
    """
    if not steam_mods_location or not steam_mods_location.strip():
        logger.debug("Steam mods location is empty or None")
        return False

    try:
        acf_file_path = Path(steam_mods_location) / "appworkshop_294100.acf"
        exists = acf_file_path.exists() and acf_file_path.is_file()

        if exists:
            logger.debug(f"ACF file found at: {acf_file_path}")
        else:
            logger.debug(f"ACF file not found at: {acf_file_path}")

        return exists
    except Exception as e:
        logger.warning(f"Error checking ACF file at {steam_mods_location}: {e}")
        return False
