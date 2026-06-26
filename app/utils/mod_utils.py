import os
from datetime import datetime
from typing import Any

from loguru import logger

from app.controllers.metadata_controller import MetadataController
from app.models.metadata.metadata_db import AuxMetadataEntry
from app.models.metadata.metadata_structure import AboutXmlMod, ListedMod, ModType


def resolve_aux_timestamps(
    aux_entry: AuxMetadataEntry | None,
) -> tuple[int | None, int | None]:
    """Extract download-time and workshop-update-time from an aux DB entry.

    *Download time*:  ACF ``timetouched`` (``WorkshopItemsInstalled``) — the
    actual moment Steam/SteamCMD last touched the mod on disk.  This is the
    best available ``downloaded_time_raw`` for SteamCMD mods.

    *Workshop update time*:  Prefers the Steam WebAPI ``external_time_updated``
    value, falling back to the ACF ``timeupdated`` (``WorkshopItemDetails``)
    when the API didn't return a result (e.g. mod removed from Workshop).

    Returns ``(acf_time_touched, resolved_external_time_updated)`` where
    *None* means the source was missing or not positive.
    """
    if aux_entry is None:
        return None, None

    raw_touched = getattr(aux_entry, "acf_time_touched", -1)
    acf_touched = raw_touched if raw_touched is not None and raw_touched > 0 else None

    ext_updated: int | None = None
    raw_external = getattr(aux_entry, "external_time_updated", -1)
    if raw_external is not None and raw_external > 0:
        ext_updated = raw_external
    else:
        raw_acf = getattr(aux_entry, "acf_time_updated", -1)
        if raw_acf is not None and raw_acf > 0:
            ext_updated = raw_acf

    return acf_touched, ext_updated


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
    Filter mods that need user action (update or initial download/population).

    A mod needs action when it originates from Steam Workshop (or SteamCMD)
    and one of:
    - external timestamp is strictly newer than internal (update available)
    - no internal timestamp (needs initial download to generate one)
    - no external timestamp (needs Steam API fetch to populate)

    :param mods_metadata: Dictionary of mods metadata keyed by path.
    :return: List of metadata dictionaries for mods needing action.
    """
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

        # ── Resolve internal timestamp ──────────────────────────────────
        # ``internal_time`` = when we last had the mod on disk.
        # We try two sources and take the more recent one:
        #   1. File mtime  (mod.internal_time_touched) – the mod folder's
        #      last-modified time on the filesystem.
        #   2. ACF time_updated  (aux DB) – the timestamp written by
        #      Steam/SteamCMD when it last downloaded the mod.
        #
        # Steam/SteeamCMD often preserve original workshop upload timestamps
        # as file mtimes, making source #1 unreliable.  We therefore prefer
        # source #2 when it is available *and* more recent.
        internal_time: int | None = None
        timestamp_source: str = "none"

        raw_touched = mod.internal_time_touched
        if raw_touched > 0:
            internal_time = raw_touched
            timestamp_source = "internal_time_touched"

        _, aux_entry = metadata_controller.get_metadata_with_path(path)
        if aux_entry is not None and aux_entry.acf_time_updated > 0:
            if internal_time is None or aux_entry.acf_time_updated > internal_time:
                internal_time = aux_entry.acf_time_updated
                timestamp_source = "acf_time_updated"

        # 0 signals "no valid internal timestamp" in the decision logic below
        if internal_time is None:
            internal_time = 0

        # ── External timestamp (from Steam API via aux DB) ──────────────
        # ``external_time`` = when Steam Workshop says the mod was last
        # updated.  Populated by query_workshop_update_data().  Falls back
        # to acf_time_updated (from ACF WorkshopItemDetails.timeupdated)
        # when the Steam API didn't return a value (e.g. mod removed from
        # Workshop, network failure, etc.).
        acf_touched, external_time_raw = resolve_aux_timestamps(aux_entry)
        external_time = external_time_raw if external_time_raw is not None else 0

        # ── Decision ────────────────────────────────────────────────────
        # Include the mod if it needs any form of user action:
        if external_time > internal_time:
            # Steam reports a newer version than what we have on disk.
            reason = "update_available"
        elif internal_time == 0:
            # We have no record of ever downloading this mod (missing file
            # mtime *and* no ACF timestamp).  Include so the user can
            # trigger an initial download that will populate the data.
            skipped_no_internal_time += 1
            reason = "no_internal_time"
        elif external_time == 0:
            # Steam API has not returned a time_updated yet (first run,
            # API failure, etc.).  Include so the user can re-download
            # and trigger a fresh API fetch on the next refresh.
            skipped_no_external_time += 1
            reason = "no_external_time"
        else:
            # Both timestamps exist and internal >= external → up-to-date.
            skipped_up_to_date += 1
            logger.debug(
                "[mod_update] SKIP (up to date) mod={mod_name!r} pfid={pfid} "
                "internal={internal_fmt} external={external_fmt} "
                "delta={delta}s ({delta_days:.1f} days) source={source}",
                mod_name=mod_name,
                pfid=pfid,
                internal_fmt=_format_timestamp(internal_time),
                external_fmt=_format_timestamp(external_time),
                delta=external_time - internal_time,
                delta_days=(external_time - internal_time) / 86400,
                source=timestamp_source,
            )
            continue

        delta = external_time - internal_time
        delta_days = delta / 86400

        # Build a dict compatible with ModInfo.from_metadata() so the
        # WorkshopModUpdaterPanel table can display the mod row.
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
            "acf_time_touched": acf_touched,
        }
        if isinstance(mod, AboutXmlMod):
            compat_metadata["packageid"] = str(mod.package_id)
            compat_metadata["authors"] = mod.authors
            compat_metadata["supportedversions"] = sorted(mod.supported_versions)
        eligible.append(compat_metadata)
        logger.debug(
            "[mod_update]{} mod={mod_name!r} pfid={pfid} "
            "internal={internal_fmt} external={external_fmt} "
            "delta={delta}s ({delta_days:.1f} days) reason={reason} source={source}",
            " ELIGIBLE" if reason == "update_available" else " INCLUDED",
            mod_name=mod_name,
            pfid=pfid,
            internal_fmt=_format_timestamp(internal_time),
            external_fmt=_format_timestamp(external_time),
            delta=delta,
            delta_days=delta_days,
            reason=reason,
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
