"""Validate Steam Workshop publishedfileids via GetPublishedFileDetails."""

from __future__ import annotations

from typing import Any

from app.utils.steam.webapi.wrapper import ISteamRemoteStorage_GetPublishedFileDetails
from app.utils.steam.workshop_search import RIMWORLD_APPID


def validate_publishedfileids(ids: list[str]) -> dict[str, Any]:
    """Return valid and invalid workshop IDs for RimWorld (appid 294100)."""
    cleaned = [str(p).strip() for p in ids if str(p).strip()]
    if not cleaned:
        return {"valid": [], "invalid": [], "valid_details": []}

    metadata, failed_pfids, errors = ISteamRemoteStorage_GetPublishedFileDetails(cleaned)
    valid_details: list[dict[str, Any]] = []
    valid_ids: list[str] = []

    for item in metadata:
        if not isinstance(item, dict):
            continue
        pfid = str(item.get("publishedfileid", "")).strip()
        if not pfid or pfid in failed_pfids:
            continue
        appid = item.get("appid")
        if appid is not None and int(appid) != RIMWORLD_APPID:
            continue
        valid_ids.append(pfid)
        valid_details.append(
            {
                "publishedfileid": pfid,
                "title": str(item.get("title", "") or pfid),
                "url": (
                    f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"
                ),
            }
        )

    invalid = list(failed_pfids)
    seen_valid = set(valid_ids)
    for pfid in cleaned:
        if pfid not in seen_valid and pfid not in invalid:
            invalid.append(pfid)

    response: dict[str, Any] = {
        "valid": valid_ids,
        "invalid": invalid,
        "valid_details": valid_details,
    }
    if errors:
        response["errors"] = errors
    return response
