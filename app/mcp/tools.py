"""MCP tool definitions and dispatch (shared with Gemini assistant)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.mcp import command_queue, rim_sort_context
from app.utils.steam.workshop_validate import validate_publishedfileids

_GUI_REQUIRED = (
    "RimSort GUI must be running. Enable MCP in Settings and keep RimSort open."
)


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_installed_mods",
            "description": "List installed mods with package_id, name, and path",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "list_active_mods",
            "description": "List active mod package IDs from ModsConfig.xml",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_mod_info",
            "description": "Legacy alias for basic mod metadata by package_id",
            "inputSchema": {
                "type": "object",
                "properties": {"package_id": {"type": "string"}},
                "required": ["package_id"],
            },
        },
        {
            "name": "describe_mod",
            "description": (
                "Full About.xml metadata: authors, description, dependencies, "
                "load order hints, supported versions"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"package_id": {"type": "string"}},
                "required": ["package_id"],
            },
        },
        {
            "name": "search_installed_mods",
            "description": "Search installed mods by substring in name or package_id",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
            },
        },
        {
            "name": "search_workshop_mods",
            "description": (
                "Search RimWorld Steam Workshop by text (title/description). "
                "Requires steam_apikey in RimSort settings (Database Builder tab). "
                "Does not require workshop_folder. Returns publishedfileid, title, "
                "url, and short description. Use these IDs for queue_download."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
            },
        },
        {
            "name": "search_steam_workshop",
            "description": (
                "Alias for search_workshop_mods: search RimWorld Steam Workshop "
                "by text via Steam Web API (requires steam_apikey in settings)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
            },
        },
        {
            "name": "find_russian_localizations_for_active_mods",
            "description": (
                "Find Russian localization mods on Steam Workshop for active mods "
                "that lack rus/Russian markers or an active localization. Uses real "
                "Steam API search. Returns verified publishedfileids with recommended "
                "pick per mod. Use this instead of guessing workshop IDs."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit_per_mod": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                    },
                    "package_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional subset of active package IDs",
                    },
                },
            },
        },
        {
            "name": "validate_workshop_ids",
            "description": (
                "Verify publishedfileids exist on RimWorld Steam Workshop before "
                "download. Returns valid and invalid IDs."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "publishedfileids": {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                },
                "required": ["publishedfileids"],
            },
        },
        {
            "name": "list_missing_deps",
            "description": (
                "For each active mod, list modDependencies package IDs not installed. "
                "Does not resolve alternative package IDs or Steam workshop IDs."
            ),
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_instance_summary",
            "description": (
                "Current instance paths, game version, installed/active mod counts, "
                "and whether steam_apikey is configured"
            ),
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "read_log",
            "description": "Tail Player.log or RimSort.log (max 200 lines, ~32KiB)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["player", "rimsort"],
                    },
                    "tail_lines": {"type": "integer", "minimum": 1, "maximum": 200},
                    "grep": {"type": "string"},
                },
                "required": ["source"],
            },
        },
        {
            "name": "queue_download",
            "description": (
                f"Queue SteamCMD download via GUI. IDs are validated before queueing. "
                f"{_GUI_REQUIRED}"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "publishedfileids": {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                },
                "required": ["publishedfileids"],
            },
        },
        {
            "name": "queue_sort_mods",
            "description": f"Queue active mod list sort via GUI. {_GUI_REQUIRED}",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "queue_save_mods",
            "description": f"Queue save active mod list via GUI. {_GUI_REQUIRED}",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "queue_run_game",
            "description": f"Queue game launch via GUI. {_GUI_REQUIRED}",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


def gemini_tool_declarations() -> list[dict[str, Any]]:
    return [
        {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["inputSchema"],
        }
        for tool in list_tools()
        if tool["name"] not in ("get_mod_info", "search_steam_workshop")
    ]


def _parse_limit(raw: Any, default: int, maximum: int) -> int:
    try:
        return max(1, min(int(raw), maximum))
    except (TypeError, ValueError):
        return default


def call_tool(
    name: str,
    arguments: dict[str, Any] | None = None,
    steam_apikey_override: str | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> Any:
    args = arguments or {}

    if name == "list_installed_mods":
        return rim_sort_context.list_installed_mods()
    if name == "list_active_mods":
        return rim_sort_context.list_active_package_ids()
    if name == "get_mod_info":
        pid = str(args.get("package_id", "")).strip()
        return rim_sort_context.get_mod_info(pid)
    if name == "describe_mod":
        pid = str(args.get("package_id", "")).strip()
        if not pid:
            return {"found": False, "error": "package_id is required"}
        info = rim_sort_context.describe_mod(pid)
        if info is None:
            return {"found": False, "package_id": pid}
        return {"found": True, **info}
    if name == "search_installed_mods":
        query = str(args.get("query", "")).strip()
        if not query:
            return {"matches": [], "error": "query is required"}
        limit = _parse_limit(args.get("limit", 20), 20, 50)
        matches = rim_sort_context.search_installed_mods(query, limit=limit)
        return {"query": query, "matches": matches, "count": len(matches)}
    if name in ("search_workshop_mods", "search_steam_workshop"):
        query = str(args.get("query", "")).strip()
        if not query:
            return {"matches": [], "error": "query is required"}
        limit = _parse_limit(args.get("limit", 20), 20, 50)
        return rim_sort_context.search_workshop_mods(
            query,
            limit=limit,
            steam_apikey_override=steam_apikey_override,
        )
    if name == "find_russian_localizations_for_active_mods":
        limit_per_mod = _parse_limit(args.get("limit_per_mod", 5), 5, 10)
        raw_pids = args.get("package_ids")
        package_ids: list[str] | None = None
        if isinstance(raw_pids, list):
            package_ids = [str(p).strip() for p in raw_pids if str(p).strip()]
        return rim_sort_context.find_russian_localizations_for_active_mods_tool(
            limit_per_mod=limit_per_mod,
            package_ids=package_ids,
            steam_apikey_override=steam_apikey_override,
            on_progress=on_progress,
        )
    if name == "validate_workshop_ids":
        pfids = args.get("publishedfileids") or []
        if not isinstance(pfids, list) or not pfids:
            return {"valid": [], "invalid": [], "error": "publishedfileids is required"}
        cleaned = [str(p).strip() for p in pfids if str(p).strip()]
        return validate_publishedfileids(cleaned)
    if name == "list_missing_deps":
        return rim_sort_context.list_missing_deps()
    if name == "get_instance_summary":
        return rim_sort_context.get_instance_summary(
            steam_apikey_override=steam_apikey_override
        )
    if name == "read_log":
        source = str(args.get("source", "")).strip().lower()
        if source not in ("player", "rimsort"):
            return {"error": "source must be 'player' or 'rimsort'"}
        tail_lines = _parse_limit(args.get("tail_lines", 80), 80, 200)
        grep = args.get("grep")
        grep_str = str(grep).strip() if grep else None
        return rim_sort_context.read_log(
            source, tail_lines=tail_lines, grep=grep_str or None
        )
    if name == "queue_download":
        blocked = command_queue.require_gui_for_mutation()
        if blocked:
            return blocked
        pfids = args.get("publishedfileids") or []
        if not isinstance(pfids, list) or not pfids:
            return {"ok": False, "error": "publishedfileids is required"}
        cleaned = [str(p).strip() for p in pfids if str(p).strip()]
        if not cleaned:
            return {"ok": False, "error": "publishedfileids is required"}
        validation = validate_publishedfileids(cleaned)
        valid = validation.get("valid", [])
        invalid = validation.get("invalid", [])
        if not valid:
            return {
                "ok": False,
                "error": "No valid RimWorld Workshop IDs to download",
                "invalid_ids": invalid,
                "valid_ids": [],
            }
        command_queue.enqueue(
            {"type": "steamcmd_download", "publishedfileids": valid}
        )
        result: dict[str, Any] = {
            "ok": True,
            "queued": "steamcmd_download",
            "count": len(valid),
            "valid_ids": valid,
        }
        if invalid:
            result["invalid_ids"] = invalid
            result["warning"] = (
                f"Skipped {len(invalid)} invalid workshop ID(s). "
                "Only IDs verified via Steam API were queued."
            )
        return result
    if name == "queue_sort_mods":
        blocked = command_queue.require_gui_for_mutation()
        if blocked:
            return blocked
        command_queue.enqueue({"type": "sort"})
        return {"ok": True, "queued": "sort"}
    if name == "queue_save_mods":
        blocked = command_queue.require_gui_for_mutation()
        if blocked:
            return blocked
        command_queue.enqueue({"type": "save"})
        return {"ok": True, "queued": "save"}
    if name == "queue_run_game":
        blocked = command_queue.require_gui_for_mutation()
        if blocked:
            return blocked
        command_queue.enqueue({"type": "run_game"})
        return {"ok": True, "queued": "run_game"}

    raise ValueError(f"Unknown tool: {name}")
