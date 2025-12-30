import os
from datetime import datetime
from typing import Any

from loguru import logger

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


def filter_eligible_mods_for_update(
    internal_local_metadata: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Filter mods that are eligible for update.

    Compares external Workshop update time against local installation time to determine
    if a mod needs updating. Uses internal_time_touched (from Steamworks live query or
    ACF timetouched) with fallback to internal_time_updated (from ACF timeupdated).

    Args:
        internal_local_metadata: Dictionary of internal local metadata.

    Returns:
        List of metadata dictionaries for mods eligible for update.
    """
    eligible = []
    skipped_not_workshop = 0
    skipped_no_internal_time = 0
    skipped_no_external_time = 0
    skipped_up_to_date = 0

    for metadata in internal_local_metadata.values():
        # Filter to only Workshop/SteamCMD mods
        if not (metadata.get("steamcmd") or metadata.get("data_source") == "workshop"):
            skipped_not_workshop += 1
            continue

        mod_name = metadata.get("name", "Unknown")
        pfid = metadata.get("publishedfileid", "N/A")

        # Use internal_time_touched with fallback to internal_time_updated
        internal_ts = metadata.get("internal_time_touched") or metadata.get(
            "internal_time_updated"
        )

        if not internal_ts:
            skipped_no_internal_time += 1
            logger.debug(
                f"Skipping {mod_name} (PFID: {pfid}): no internal timestamp available"
            )
            continue

        external_ts = metadata.get("external_time_updated")
        if not external_ts:
            skipped_no_external_time += 1
            logger.debug(
                f"Skipping {mod_name} (PFID: {pfid}): no external_time_updated"
            )
            continue

        # Check if update is needed: external (author's last update) > internal (our last download)
        if external_ts > internal_ts:
            delta_seconds = external_ts - internal_ts
            delta_days = delta_seconds / 86400

            # Determine which timestamp source was used
            timestamp_source = (
                "internal_time_touched"
                if metadata.get("internal_time_touched")
                else "internal_time_updated (fallback)"
            )

            logger.info(
                f"UPDATE AVAILABLE: {mod_name} (PFID: {pfid}) | "
                f"External: {external_ts} ({datetime.fromtimestamp(external_ts).strftime('%Y-%m-%d %H:%M:%S')}) | "
                f"Internal: {internal_ts} ({datetime.fromtimestamp(internal_ts).strftime('%Y-%m-%d %H:%M:%S')}) | "
                f"Delta: {delta_seconds}s ({delta_days:.1f} days) | "
                f"Source: {timestamp_source}"
            )
            eligible.append(metadata)
        else:
            skipped_up_to_date += 1
            delta_seconds = internal_ts - external_ts
            delta_days = delta_seconds / 86400
            logger.debug(
                f"UP-TO-DATE: {mod_name} (PFID: {pfid}) | "
                f"Internal is {delta_seconds}s ({delta_days:.1f} days) newer than external"
            )

    # Log summary statistics
    total_workshop_mods = (
        len(eligible)
        + skipped_up_to_date
        + skipped_no_internal_time
        + skipped_no_external_time
    )
    logger.info(
        f"Update detection summary: {len(eligible)} eligible for update, "
        f"{skipped_up_to_date} up-to-date, "
        f"{skipped_no_internal_time} missing internal timestamp, "
        f"{skipped_no_external_time} missing external timestamp "
        f"(Total Workshop mods checked: {total_workshop_mods})"
    )

    return eligible
