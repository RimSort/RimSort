"""Find localization mods on Steam Workshop for active mods (no Qt)."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.utils.steam.workshop_search import search_workshop_by_text

ProgressCallback = Callable[[int, int, str], None]

# Marker substrings (lowercase) that indicate a Workshop item is a localization
# for a given language, plus a short English search term used to query the
# Workshop for that language ("<mod name> <search_term>").
LANGUAGE_MARKERS: dict[str, tuple[str, ...]] = {
    "ru": ("russian", "рус", "русификатор", "[ru]", "(ru)"),
    "en": ("english", "[en]", "(en)"),
    "fr": ("french", "française", "francais", "[fr]", "(fr)"),
    "de": ("german", "deutsch", "[de]", "(de)"),
    "es": ("spanish", "español", "espanol", "[es]", "(es)"),
    "zh": ("chinese", "简体中文", "繁體中文", "中文", "[zh]", "(zh)"),
    "ja": ("japanese", "日本語", "[ja]", "(ja)"),
    "pl": ("polish", "polski", "[pl]", "(pl)"),
    "pt": ("portuguese", "português", "portugues", "[pt]", "(pt)"),
}
LANGUAGE_SEARCH_TERMS: dict[str, str] = {
    "ru": "russian",
    "en": "english",
    "fr": "french",
    "de": "german",
    "es": "spanish",
    "zh": "chinese",
    "ja": "japanese",
    "pl": "polish",
    "pt": "portuguese",
}
WIP_MARKERS = ("wip", "outdated", "deprecated", "abandon")
NAME_STOPWORDS = {
    "continued",
    "fork",
    "mod",
    "rimworld",
    "edition",
    "pack",
    "framework",
}


def _is_official_rimworld_content(package_id: str) -> bool:
    """Core game/DLC package IDs ship with official localization."""
    return package_id.lower().startswith("ludeon.rimworld")


def _has_language_marker(text: str, language: str) -> bool:
    lower = text.lower()
    markers = LANGUAGE_MARKERS.get(language, ())
    if any(marker in lower for marker in markers):
        return True
    return re.search(rf"\b{re.escape(language)}\b", lower) is not None


def _title_looks_localized(title: str, language: str) -> bool:
    return _has_language_marker(title, language)


def _name_tokens(text: str) -> set[str]:
    tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-zА-Яа-я0-9]+", text)
        if len(token) >= 3
    }
    return {token for token in tokens if token not in NAME_STOPWORDS}


def _is_already_localized(
    target_package_id: str,
    target_name: str,
    active_package_ids: set[str],
    installed_by_pid: dict[str, dict[str, Any]],
    language: str,
) -> bool:
    if _has_language_marker(target_name, language) or _has_language_marker(
        target_package_id, language
    ):
        return True

    target_lower = target_name.lower()
    target_pid_lower = target_package_id.lower()

    for pid in active_package_ids:
        if pid.lower() == target_pid_lower:
            continue
        info = installed_by_pid.get(pid.lower())
        if info is None:
            continue
        name = str(info.get("name", ""))
        if not _has_language_marker(name, language) and not _has_language_marker(
            pid, language
        ):
            continue
        name_lower = name.lower()
        if target_lower and target_lower in name_lower:
            return True
        overlap = _name_tokens(target_name) & _name_tokens(name)
        if len(overlap) >= 2:
            return True
        load_after = info.get("load_after", [])
        mod_deps = info.get("mod_dependencies", [])
        if target_pid_lower in {d.lower() for d in load_after}:
            return True
        if target_pid_lower in {d.lower() for d in mod_deps}:
            return True

    return False


def _score_candidate(
    candidate: dict[str, Any],
    target_name: str,
    target_package_id: str,
    language: str,
) -> float:
    title = str(candidate.get("title", ""))
    title_lower = title.lower()
    score = 0.0

    search_term = LANGUAGE_SEARCH_TERMS.get(language, language)
    if search_term in title_lower:
        score += 2.0
    if re.search(rf"\b{re.escape(language)}\b", title_lower) or f"[{language}]" in title_lower:
        score += 1.5
    if _has_language_marker(title, language):
        score += 0.5

    target_lower = target_name.lower()
    if target_lower and target_lower in title_lower:
        score += 2.0
    elif target_package_id.lower().replace(".", " ") in title_lower:
        score += 1.0

    for marker in WIP_MARKERS:
        if marker in title_lower:
            score -= 1.0

    return score


def _merge_candidates(
    existing: dict[str, dict[str, Any]],
    new_items: list[dict[str, Any]],
) -> None:
    for item in new_items:
        pfid = str(item.get("publishedfileid", "")).strip()
        if not pfid:
            continue
        if pfid not in existing:
            existing[pfid] = item


def _search_localization_candidates(
    api_key: str,
    target_name: str,
    target_package_id: str,
    limit_per_mod: int,
    language: str,
) -> list[dict[str, Any]]:
    search_term = LANGUAGE_SEARCH_TERMS.get(language, language)
    queries = [
        f"{target_name} {search_term}",
        f"{target_name} {language}",
        f"{target_package_id} {search_term}",
    ]
    merged: dict[str, dict[str, Any]] = {}
    per_query = max(3, min(limit_per_mod, 10))

    for query in queries:
        try:
            matches = search_workshop_by_text(api_key, query, limit=per_query)
        except Exception:
            continue
        filtered = [
            m
            for m in matches
            if _title_looks_localized(str(m.get("title", "")), language)
        ]
        _merge_candidates(merged, filtered if filtered else matches)

    scored = []
    for item in merged.values():
        score = _score_candidate(item, target_name, target_package_id, language)
        if score <= 0 and not _title_looks_localized(
            str(item.get("title", "")), language
        ):
            continue
        entry = dict(item)
        entry["score"] = round(score, 2)
        scored.append(entry)

    scored.sort(key=lambda x: (-x.get("score", 0), x.get("title", "")))
    return scored[:limit_per_mod]


def find_localizations_for_active_mods(
    active_mods: list[dict[str, str]],
    installed_by_pid: dict[str, dict[str, Any]],
    api_key: str,
    *,
    language: str,
    limit_per_mod: int = 5,
    package_ids: list[str] | None = None,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Find workshop localization candidates (for `language`) for active mods."""
    limit_per_mod = max(1, min(int(limit_per_mod), 10))
    api_key = api_key.strip()
    language = language.strip().lower()

    if language not in LANGUAGE_MARKERS:
        return {
            "suggestions": [],
            "mods_needing_localization": [],
            "skipped_already_localized": [],
            "errors": [
                (
                    f"Unsupported language '{language}'. Supported: "
                    f"{', '.join(sorted(LANGUAGE_MARKERS))}."
                )
            ],
        }

    if not api_key:
        return {
            "suggestions": [],
            "mods_needing_localization": [],
            "skipped_already_localized": [],
            "errors": [
                "steam_apikey is not configured. Add a Steam Web API key in "
                "Settings (Database Builder tab) to search the Workshop."
            ],
        }

    active_set = {m["package_id"] for m in active_mods}
    filter_pids: set[str] | None = None
    if package_ids:
        filter_pids = {p.strip() for p in package_ids if p.strip()}

    mods_to_scan: list[dict[str, str]] = []
    for mod in active_mods:
        pid = mod["package_id"]
        if filter_pids is not None and pid not in filter_pids:
            continue
        if _is_official_rimworld_content(pid):
            continue
        mods_to_scan.append({"package_id": pid, "name": mod.get("name", pid)})

    scan_total = len(mods_to_scan)
    if on_progress is not None:
        on_progress(0, scan_total, "Scanning active mods for existing localizations")

    mods_needing: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for index, mod in enumerate(mods_to_scan, start=1):
        pid = mod["package_id"]
        name = mod["name"]
        if on_progress is not None:
            on_progress(index, scan_total, f"Checking: {name}")
        if _is_already_localized(pid, name, active_set, installed_by_pid, language):
            skipped.append({"package_id": pid, "name": name})
        else:
            mods_needing.append({"package_id": pid, "name": name})

    suggestions: list[dict[str, Any]] = []
    errors: list[str] = []
    search_total = len(mods_needing)

    if on_progress is not None and search_total > 0:
        on_progress(
            0, search_total, "Searching Steam Workshop for localizations"
        )

    for index, mod in enumerate(mods_needing, start=1):
        pid = mod["package_id"]
        name = mod["name"]
        if on_progress is not None:
            on_progress(index, search_total, f"Workshop search: {name}")
        try:
            candidates = _search_localization_candidates(
                api_key, name, pid, limit_per_mod, language
            )
        except Exception as exc:
            errors.append(f"{pid}: {exc}")
            candidates = []

        entry: dict[str, Any] = {
            "target_package_id": pid,
            "target_name": name,
            "candidates": candidates,
        }
        if candidates:
            best = candidates[0]
            entry["recommended"] = {
                "publishedfileid": best["publishedfileid"],
                "title": best.get("title", ""),
                "url": best.get("url", ""),
                "score": best.get("score", 0),
            }
        suggestions.append(entry)

    return {
        "mods_needing_localization": mods_needing,
        "skipped_already_localized": skipped,
        "suggestions": suggestions,
        "errors": errors,
        "source": "steam_api",
    }
