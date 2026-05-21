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


def _format_timestamp(ts: int) -> str:
    """
    Format a Unix timestamp as a human-readable string.

    :param ts: Unix timestamp (seconds since epoch)
    :return: Formatted datetime string, or ``"N/A"`` if the timestamp is zero or negative
    """
    if ts <= 0:
        return "N/A"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return f"<invalid:{ts}>"


def filter_eligible_mods_for_update(
    internal_local_metadata: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Filter mods that are eligible for update.

    A mod is eligible when it originates from Steam Workshop (or SteamCMD),
    has a valid internal timestamp, has a valid external timestamp, and the
    external timestamp is strictly newer than the internal one.

    The internal timestamp is resolved with a fallback chain:
    ``internal_time_touched`` is preferred; if absent or zero,
    ``internal_time_updated`` is used instead.

    :param internal_local_metadata: Dictionary of internal local metadata
        keyed by UUID.
    :return: List of metadata dictionaries for mods eligible for update.
    """
    eligible: list[dict[str, Any]] = []

    skipped_not_workshop = 0
    skipped_no_internal_time = 0
    skipped_no_external_time = 0
    skipped_up_to_date = 0
    total = 0

    for uuid, metadata in internal_local_metadata.items():
        total += 1
        mod_name = metadata.get("name", uuid)
        pfid = metadata.get("publishedfileid", "N/A")

        # Must be a workshop/steamcmd mod
        is_workshop = metadata.get("steamcmd") or metadata.get("data_source") == "workshop"
        if not is_workshop:
            skipped_not_workshop += 1
            logger.debug(
                "[mod_update] SKIP (not workshop) mod={mod_name!r} pfid={pfid}",
                mod_name=mod_name,
                pfid=pfid,
            )
            continue

        # Resolve internal timestamp with fallback
        internal_time: int | None = None
        timestamp_source: str = "none"

        raw_touched = metadata.get("internal_time_touched")
        raw_updated = metadata.get("internal_time_updated")

        if raw_touched and int(raw_touched) > 0:
            internal_time = int(raw_touched)
            timestamp_source = "internal_time_touched"
        elif raw_updated and int(raw_updated) > 0:
            internal_time = int(raw_updated)
            timestamp_source = "internal_time_updated (fallback)"

        if internal_time is None:
            skipped_no_internal_time += 1
            logger.debug(
                "[mod_update] SKIP (no internal time) mod={mod_name!r} pfid={pfid}",
                mod_name=mod_name,
                pfid=pfid,
            )
            continue

        # External timestamp
        raw_external = metadata.get("external_time_updated")
        if not raw_external or int(raw_external) <= 0:
            skipped_no_external_time += 1
            logger.debug(
                "[mod_update] SKIP (no external time) mod={mod_name!r} pfid={pfid}",
                mod_name=mod_name,
                pfid=pfid,
            )
            continue
        external_time = int(raw_external)

        delta = external_time - internal_time
        delta_days = delta / 86400

        if external_time > internal_time:
            eligible.append(metadata)
            logger.debug(
                "[mod_update] ELIGIBLE mod={mod_name!r} pfid={pfid} "
                "internal={internal_fmt} external={external_fmt} "
                "delta={delta}s ({delta_days:.1f} days) source={source}",
                mod_name=mod_name,
                pfid=pfid,
                internal_fmt=_format_timestamp(internal_time),
                external_fmt=_format_timestamp(external_time),
                delta=delta,
                delta_days=delta_days,
                source=timestamp_source,
            )
        else:
            skipped_up_to_date += 1
            logger.debug(
                "[mod_update] SKIP (up to date) mod={mod_name!r} pfid={pfid} "
                "internal={internal_fmt} external={external_fmt} "
                "delta={delta}s ({delta_days:.1f} days) source={source}",
                mod_name=mod_name,
                pfid=pfid,
                internal_fmt=_format_timestamp(internal_time),
                external_fmt=_format_timestamp(external_time),
                delta=delta,
                delta_days=delta_days,
                source=timestamp_source,
            )

    logger.info(
        "[mod_update] Eligibility summary: {eligible}/{total} eligible, "
        "skipped: not_workshop={not_ws}, no_internal_time={no_int}, "
        "no_external_time={no_ext}, up_to_date={up_to_date}",
        eligible=len(eligible),
        total=total,
        not_ws=skipped_not_workshop,
        no_int=skipped_no_internal_time,
        no_ext=skipped_no_external_time,
        up_to_date=skipped_up_to_date,
    )

    return eligible
