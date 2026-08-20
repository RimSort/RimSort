"""Steam Workshop text search via IPublishedFileService/QueryFiles (no Qt)."""

from __future__ import annotations

from typing import Any

from steam.webapi import WebAPI

RIMWORLD_APPID = 294100
QUERY_TYPE_RANKED_BY_TEXT_SEARCH = 12
DESCRIPTION_MAX_LEN = 300


def _normalize_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    if raw.get("result") != 1:
        return None
    pfid = str(raw.get("publishedfileid", "")).strip()
    if not pfid:
        return None
    title = str(raw.get("title", "")).strip() or pfid
    item: dict[str, Any] = {
        "publishedfileid": pfid,
        "title": title,
        "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}",
    }
    preview = raw.get("preview_url")
    if preview:
        item["preview_url"] = str(preview)
    desc = raw.get("short_description") or raw.get("description")
    if desc:
        text = str(desc)
        if len(text) > DESCRIPTION_MAX_LEN:
            text = text[:DESCRIPTION_MAX_LEN] + "..."
        item["short_description"] = text
    return item


def search_workshop_by_text(
    api_key: str,
    query: str,
    *,
    limit: int = 20,
    appid: int = RIMWORLD_APPID,
) -> list[dict[str, Any]]:
    """Search RimWorld Workshop items by title/description text."""
    text = query.strip()
    if not text:
        return []
    if not api_key.strip():
        raise ValueError("Steam Web API key is required")

    limit = max(1, min(int(limit), 50))
    api = WebAPI(api_key.strip(), format="json", https=True)
    # jscpd:ignore-start
    response = api.call(
        method_path="IPublishedFileService.QueryFiles",
        key=api_key.strip(),
        query_type=QUERY_TYPE_RANKED_BY_TEXT_SEARCH,
        page=1,
        cursor="*",
        numperpage=limit,
        creator_appid=appid,
        appid=appid,
        requiredtags=None,
        excludedtags=None,
        match_all_tags=False,
        required_flags=None,
        omitted_flags=None,
        search_text=text,
        filetype=0,
        child_publishedfileid=None,
        days=None,
        include_recent_votes_only=False,
        required_kv_tags=None,
        taggroups=None,
        date_range_created=None,
        date_range_updated=None,
        excluded_content_descriptors=None,
        special_filter=None,
        appids_required_for_use=None,
        excluded_appids_required_for_use=None,
        search_text_target=None,
        totalonly=False,
        ids_only=False,
        return_vote_data=False,
        return_tags=False,
        return_kv_tags=False,
        return_previews=True,
        return_children=False,
        return_short_description=True,
        return_for_sale_data=False,
        return_playtime_stats=False,
        return_details=True,
        strip_description_bbcode=True,
        admin_query=False,
    )
    # jscpd:ignore-end

    raw_items = response.get("response", {}).get("publishedfiledetails", [])
    if not isinstance(raw_items, list):
        return []

    matches: list[dict[str, Any]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        item = _normalize_item(raw)
        if item is not None:
            matches.append(item)
        if len(matches) >= limit:
            break
    return matches
