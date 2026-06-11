import os
from datetime import datetime
from typing import Any

from loguru import logger

from app.controllers.metadata_controller import MetadataController
from app.models.metadata.metadata_structure import AboutXmlMod, ListedMod


def get_mod_path_from_pfid(pfid: str) -> str | None:
    """
    Get the mod path from a published file ID.

    :param pfid: Published file ID.
    :return: Mod path if found, None otherwise.
    """
    metadata_controller = MetadataController.instance()
    for path, mod in metadata_controller.mods_metadata.items():
        if mod.published_file_id == pfid:
            return path
    return None


def get_mod_name_from_pfid(pfid: str | int | None) -> str:
    """
    Get a mod's name from its PublishedFileID.

    :param pfid: The PublishedFileID to lookup (str, int or None)
    :return: The mod name or "Unknown Mod" if not found
    """
    if not pfid:
        return "Unknown Mod"

    pfid_str = str(pfid)
    if not pfid_str.isdigit():
        return f"Invalid ID: {pfid_str}"

    metadata_controller = MetadataController.instance()

    # First check parsed mods metadata
    for mod in metadata_controller.mods_metadata.values():
        if mod.published_file_id == pfid_str:
            return mod.name if mod.name else f"Invalid ID: {pfid_str}"

    # Then check SteamDB if available
    steam_db = metadata_controller.steam_db
    if steam_db is not None and pfid_str in steam_db.database:
        entry = steam_db.database[pfid_str]
        name = entry.steamName or entry.name
        return name if name else f"Invalid ID: {pfid_str}"

    return f"Invalid ID: {pfid_str}"


def get_mod_paths(paths: list[str]) -> list[str]:
    """
    Filter a list of mod paths to only include valid, existing directories.

    :param paths: List of mod path strings.
    :return: List of mod folder paths that exist on disk.
    """
    metadata_controller = MetadataController.instance()
    mod_paths = []

    for path in paths:
        if path in metadata_controller.mods_metadata:
            mod = metadata_controller.mods_metadata[path]
            if mod.mod_path and os.path.isdir(str(mod.mod_path)):
                mod_paths.append(str(mod.mod_path))

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
    mods_metadata: dict[str, ListedMod],
) -> list[dict[str, Any]]:
    """
    Filter mods that are eligible for update.

    A mod is eligible when it originates from Steam Workshop (or SteamCMD),
    has a valid internal timestamp, has a valid external timestamp, and the
    external timestamp is strictly newer than the internal one.

    :param mods_metadata: Dictionary of mods metadata keyed by path.
    :return: List of metadata dictionaries for mods eligible for update.
    """
    from app.models.metadata.metadata_structure import ModType

    eligible: list[dict[str, Any]] = []

    skipped_not_workshop = 0
    skipped_no_internal_time = 0
    skipped_no_external_time = 0
    skipped_up_to_date = 0
    total = 0

    metadata_controller = MetadataController.instance()

    for path, mod in mods_metadata.items():
        total += 1
        mod_name = mod.name
        pfid = mod.published_file_id or "N/A"

        # Must be a workshop/steamcmd mod
        is_workshop = mod.mod_type in (ModType.STEAM_WORKSHOP, ModType.STEAM_CMD)
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

        raw_touched = mod.internal_time_touched
        if raw_touched > 0:
            internal_time = raw_touched
            timestamp_source = "internal_time_touched"

        # Fallback to ACF timestamps from aux DB
        if internal_time is None:
            _, aux_entry = metadata_controller.get_metadata_with_path(path)
            if aux_entry is not None and aux_entry.acf_time_updated > 0:
                internal_time = aux_entry.acf_time_updated
                timestamp_source = "acf_time_updated (fallback)"

        if internal_time is None:
            skipped_no_internal_time += 1
            logger.debug(
                "[mod_update] SKIP (no internal time) mod={mod_name!r} pfid={pfid}",
                mod_name=mod_name,
                pfid=pfid,
            )
            continue

        # External timestamp from aux DB
        _, aux_entry = metadata_controller.get_metadata_with_path(path)
        external_time = (
            aux_entry.external_time_updated
            if aux_entry is not None and aux_entry.external_time_updated > 0
            else 0
        )
        if external_time <= 0:
            skipped_no_external_time += 1
            logger.debug(
                "[mod_update] SKIP (no external time) mod={mod_name!r} pfid={pfid}",
                mod_name=mod_name,
                pfid=pfid,
            )
            continue

        delta = external_time - internal_time
        delta_days = delta / 86400

        if external_time > internal_time:
            # Build a compat dict for ModInfo.from_metadata consumption
            compat_metadata: dict[str, Any] = {
                "name": mod.name,
                "publishedfileid": mod.published_file_id or "",
                "path": str(mod.mod_path) if mod.mod_path else "",
                "data_source": (
                    "workshop" if mod.mod_type == ModType.STEAM_WORKSHOP else "steamcmd"
                ),
                "steamcmd": mod.mod_type == ModType.STEAM_CMD,
                "internal_time_touched": mod.internal_time_touched,
                "external_time_updated": external_time,
            }
            if isinstance(mod, AboutXmlMod):
                compat_metadata["packageid"] = str(mod.package_id)
                compat_metadata["authors"] = mod.authors
                compat_metadata["supportedversions"] = sorted(mod.supported_versions)
            eligible.append(compat_metadata)
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
