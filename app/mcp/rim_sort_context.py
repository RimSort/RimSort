"""Read-only RimSort instance context for MCP tools (no Qt)."""

from __future__ import annotations

import json
import os
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from app.ai.tools.localization_finder import find_russian_localizations_for_active_mods
from app.utils.app_info import AppInfo
from app.utils.schema import validate_rimworld_mods_list
from app.utils.steam.workshop_search import search_workshop_by_text
from app.utils.steam.workshop_validate import validate_publishedfileids
from app.utils.xml import xml_path_to_json

DESCRIPTION_MAX_LEN = 2000
LOG_MAX_BYTES = 32768


def _load_settings() -> dict[str, Any]:
    path = Path(AppInfo().app_storage_folder) / "settings.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_steam_apikey(steam_apikey_override: str | None = None) -> str:
    if steam_apikey_override is not None:
        return str(steam_apikey_override).strip()
    settings = _load_settings()
    return str(settings.get("steam_apikey", "") or "").strip()


def _steam_apikey_status(steam_apikey_override: str | None = None) -> tuple[bool, int]:
    key = _resolve_steam_apikey(steam_apikey_override)
    return bool(key), len(key)


def _installed_mods_by_package_id(
    instance_name: str | None = None,
) -> dict[str, dict[str, Any]]:
    by_pid: dict[str, dict[str, Any]] = {}
    for pid, mod_path in _iter_mod_paths(instance_name):
        info = _parse_about_path(mod_path)
        if info:
            by_pid[pid.lower()] = info
    return by_pid


def _active_mod_entries(instance_name: str | None = None) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for package_id in list_active_package_ids(instance_name):
        info = describe_mod(package_id, instance_name)
        if info is None:
            entries.append({"package_id": package_id, "name": package_id})
        else:
            entries.append(
                {
                    "package_id": info["package_id"],
                    "name": info.get("name", package_id),
                }
            )
    return entries


def get_instance_config(instance_name: str | None = None) -> dict[str, Any]:
    data = _load_settings()
    name = (
        instance_name
        or os.environ.get("RIMSORT_INSTANCE")
        or data.get("current_instance", "Default")
    )
    instances = data.get("instances", {})
    if name not in instances:
        return {}
    inst = instances[name]
    if isinstance(inst, dict):
        return inst
    return {}


def _current_instance_name(instance_name: str | None = None) -> str:
    if instance_name:
        return instance_name
    data = _load_settings()
    return str(
        os.environ.get("RIMSORT_INSTANCE") or data.get("current_instance", "Default")
    )


def list_active_package_ids(instance_name: str | None = None) -> list[str]:
    inst = get_instance_config(instance_name)
    config_folder = inst.get("config_folder", "")
    if not config_folder:
        return []
    mods_config = Path(config_folder) / "ModsConfig.xml"
    if not mods_config.exists():
        return []
    data = xml_path_to_json(str(mods_config))
    return validate_rimworld_mods_list(data)


def _text(el: ElementTree.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _list_items(parent: ElementTree.Element | None, tag: str = "li") -> list[str]:
    if parent is None:
        return []
    items: list[str] = []
    for child in parent.findall(tag):
        package_id = child.find("packageId")
        if package_id is not None and package_id.text:
            items.append(package_id.text.strip())
        elif child.text and child.text.strip():
            items.append(child.text.strip())
    return items


def _parse_about_path(mod_path: Path) -> dict[str, Any] | None:
    about = mod_path / "About" / "About.xml"
    if not about.exists():
        return None
    try:
        root = ElementTree.parse(about).getroot()
    except ElementTree.ParseError:
        return None

    package_id = _text(root.find("packageId"))
    if not package_id:
        return None

    authors: list[str] = []
    for tag in ("author", "authors"):
        node = root.find(tag)
        if node is None:
            continue
        if node.text and node.text.strip():
            authors.append(node.text.strip())
        authors.extend(_list_items(node))

    description = _text(root.find("description"))
    if len(description) > DESCRIPTION_MAX_LEN:
        description = description[:DESCRIPTION_MAX_LEN] + "..."

    return {
        "package_id": package_id,
        "name": _text(root.find("name")) or package_id,
        "authors": authors,
        "description": description,
        "path": str(mod_path),
        "mod_type": "workshop" if "workshop" in str(mod_path).lower() else "local",
        "supported_versions": _list_items(root.find("supportedVersions")),
        "mod_dependencies": _list_items(root.find("modDependencies")),
        "incompatibilities": _list_items(root.find("incompatibleWith")),
        "load_before": _list_items(root.find("loadBefore")),
        "load_after": _list_items(root.find("loadAfter")),
    }


def _iter_mod_paths(instance_name: str | None = None) -> list[tuple[str, Path]]:
    inst = get_instance_config(instance_name)
    folders = [inst.get("local_folder", ""), inst.get("workshop_folder", "")]
    seen: set[str] = set()
    entries: list[tuple[str, Path]] = []
    for folder in folders:
        if not folder:
            continue
        base = Path(folder)
        if not base.is_dir():
            continue
        for child in base.iterdir():
            if not child.is_dir():
                continue
            info = _parse_about_path(child)
            if info is None:
                continue
            pid = info["package_id"]
            key = pid.lower()
            if key in seen:
                continue
            seen.add(key)
            entries.append((pid, child))
    return entries


def list_installed_mods(instance_name: str | None = None) -> list[dict[str, Any]]:
    mods: list[dict[str, Any]] = []
    for package_id, mod_path in _iter_mod_paths(instance_name):
        info = _parse_about_path(mod_path)
        if info:
            mods.append(_mod_summary(info))
    return mods


def _mod_summary(info: dict[str, Any]) -> dict[str, Any]:
    return {
        "package_id": info["package_id"],
        "name": info["name"],
        "path": info["path"],
        "mod_type": info["mod_type"],
    }


def _find_mod_path(package_id: str, instance_name: str | None) -> Path | None:
    needle = package_id.lower()
    for pid, mod_path in _iter_mod_paths(instance_name):
        if pid.lower() == needle:
            return mod_path
    return None


def get_mod_info(
    package_id: str, instance_name: str | None = None
) -> dict[str, Any] | None:
    mod_path = _find_mod_path(package_id, instance_name)
    if mod_path is None:
        return None
    info = _parse_about_path(mod_path)
    return _mod_summary(info) if info else None


def describe_mod(
    package_id: str, instance_name: str | None = None
) -> dict[str, Any] | None:
    mod_path = _find_mod_path(package_id, instance_name)
    return _parse_about_path(mod_path) if mod_path is not None else None


def search_installed_mods(
    query: str, limit: int = 20, instance_name: str | None = None
) -> list[dict[str, str]]:
    q = query.lower().strip()
    if not q:
        return []
    limit = max(1, min(limit, 50))
    matches: list[dict[str, str]] = []
    for mod in list_installed_mods(instance_name):
        name = mod.get("name", "").lower()
        pid = mod.get("package_id", "").lower()
        if q in name or q in pid:
            matches.append(
                {
                    "package_id": mod["package_id"],
                    "name": mod.get("name", mod["package_id"]),
                }
            )
        if len(matches) >= limit:
            break
    return matches


def search_workshop_mods(
    query: str,
    limit: int = 20,
    instance_name: str | None = None,
    steam_apikey_override: str | None = None,
) -> dict[str, Any]:
    """Search Steam Workshop by text via Web API (requires steam_apikey in settings)."""
    q = query.strip()
    if not q:
        return {"query": query, "matches": [], "error": "query is required"}

    limit = max(1, min(int(limit), 50))
    api_key = _resolve_steam_apikey(steam_apikey_override)
    if not api_key:
        return {
            "query": q,
            "matches": [],
            "error": (
                "steam_apikey is not configured. Add a Steam Web API key in "
                "Settings (Database Builder tab) to search the Workshop."
            ),
        }

    try:
        matches = search_workshop_by_text(api_key, q, limit=limit)
        return {
            "query": q,
            "matches": matches,
            "count": len(matches),
            "source": "steam_api",
        }
    except Exception as exc:  # noqa: BLE001
        return {"query": q, "matches": [], "error": str(exc)}


def find_russian_localizations_for_active_mods_tool(
    instance_name: str | None = None,
    limit_per_mod: int = 5,
    package_ids: list[str] | None = None,
    steam_apikey_override: str | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    api_key = _resolve_steam_apikey(steam_apikey_override)
    active_mods = _active_mod_entries(instance_name)
    installed = _installed_mods_by_package_id(instance_name)
    result = find_russian_localizations_for_active_mods(
        active_mods,
        installed,
        api_key,
        limit_per_mod=limit_per_mod,
        package_ids=package_ids,
        on_progress=on_progress,
    )
    suggestions = result.get("suggestions", [])
    if not isinstance(suggestions, list) or not suggestions:
        return result

    candidate_ids: list[str] = []
    for entry in suggestions:
        if not isinstance(entry, dict):
            continue
        for cand in entry.get("candidates", []):
            if not isinstance(cand, dict):
                continue
            pfid = str(cand.get("publishedfileid", "")).strip()
            if pfid:
                candidate_ids.append(pfid)

    if not candidate_ids:
        return result

    validated = validate_publishedfileids(candidate_ids)
    valid_ids = set(validated.get("valid", []))
    if not valid_ids:
        result.setdefault("errors", []).append(
            "No valid RimWorld Workshop IDs remained after validation."
        )
        result["suggestions"] = []
        return result

    removed_count = 0
    for entry in suggestions:
        if not isinstance(entry, dict):
            continue
        filtered: list[dict[str, Any]] = []
        for cand in entry.get("candidates", []):
            if not isinstance(cand, dict):
                continue
            pfid = str(cand.get("publishedfileid", "")).strip()
            if pfid in valid_ids:
                filtered.append(cand)
            else:
                removed_count += 1
        entry["candidates"] = filtered
        entry.pop("recommended", None)
        if filtered:
            best = filtered[0]
            entry["recommended"] = {
                "publishedfileid": best.get("publishedfileid", ""),
                "title": best.get("title", ""),
                "url": best.get("url", ""),
                "score": best.get("score", 0),
            }

    result["suggestions"] = [
        entry
        for entry in suggestions
        if isinstance(entry, dict) and entry.get("candidates")
    ]
    if removed_count:
        result["validation"] = {
            "removed_invalid_candidates": removed_count,
            "valid_candidate_count": len(valid_ids),
            "invalid_ids": validated.get("invalid", []),
        }
    return result


def list_missing_deps(instance_name: str | None = None) -> dict[str, Any]:
    installed = {m["package_id"].lower() for m in list_installed_mods(instance_name)}
    missing_by_mod: dict[str, list[str]] = {}
    for package_id in list_active_package_ids(instance_name):
        info = describe_mod(package_id, instance_name)
        if info is None:
            continue
        missing = [
            dep
            for dep in info.get("mod_dependencies", [])
            if dep.lower() not in installed
        ]
        if missing:
            missing_by_mod[package_id] = missing
    return {
        "missing_by_mod": missing_by_mod,
        "note": (
            "Package IDs only; does not resolve alternative package IDs or "
            "Steam workshop IDs."
        ),
    }


def _read_game_version(game_folder: str) -> str | None:
    if not game_folder:
        return None
    version_file = Path(game_folder) / "Version.txt"
    if not version_file.exists():
        return None
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def get_instance_summary(
    instance_name: str | None = None,
    steam_apikey_override: str | None = None,
) -> dict[str, Any]:
    name = _current_instance_name(instance_name)
    inst = get_instance_config(instance_name)
    installed = list_installed_mods(instance_name)
    active = list_active_package_ids(instance_name)
    game_folder = str(inst.get("game_folder", "") or "")
    configured, key_len = _steam_apikey_status(steam_apikey_override)
    return {
        "current_instance": name,
        "game_folder": game_folder,
        "config_folder": str(inst.get("config_folder", "") or ""),
        "local_folder": str(inst.get("local_folder", "") or ""),
        "workshop_folder": str(inst.get("workshop_folder", "") or ""),
        "game_version": _read_game_version(game_folder),
        "installed_mod_count": len(installed),
        "active_mod_count": len(active),
        "steam_apikey_configured": configured,
        "steam_apikey_length": key_len,
    }


def _resolve_log_path(source: str, instance_name: str | None = None) -> Path | None:
    if source == "rimsort":
        return Path(AppInfo().user_log_folder) / "RimSort.log"
    if source == "player":
        inst = get_instance_config(instance_name)
        config_folder = inst.get("config_folder", "")
        if not config_folder:
            return None
        player_log = Path(config_folder).parent / "Player.log"
        return player_log if player_log.exists() else None
    return None


def read_log(
    source: str,
    tail_lines: int = 80,
    grep: str | None = None,
    instance_name: str | None = None,
) -> dict[str, Any]:
    tail_lines = max(1, min(int(tail_lines), 200))
    log_path = _resolve_log_path(source, instance_name)
    if log_path is None:
        return {
            "source": source,
            "path": None,
            "lines": [],
            "error": f"Log file not found for source '{source}'",
        }
    if not log_path.exists():
        return {
            "source": source,
            "path": str(log_path),
            "lines": [],
            "error": "Log file does not exist",
        }

    try:
        with log_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            read_size = min(size, LOG_MAX_BYTES)
            handle.seek(max(0, size - read_size))
            chunk = handle.read(read_size).decode("utf-8", errors="replace")
    except OSError as exc:
        return {
            "source": source,
            "path": str(log_path),
            "lines": [],
            "error": str(exc),
        }

    lines = chunk.splitlines()
    lines = list(deque(lines, maxlen=tail_lines))
    if grep:
        pattern = grep.lower()
        lines = [line for line in lines if pattern in line.lower()]

    return {
        "source": source,
        "path": str(log_path),
        "line_count": len(lines),
        "lines": lines,
    }
