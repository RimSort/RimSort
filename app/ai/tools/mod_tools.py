from collections.abc import Callable
from typing import Any

from app.mcp.tools import call_tool, gemini_tool_declarations

GEMINI_MOD_TOOL_DECLARATIONS = gemini_tool_declarations()
ProgressCallback = Callable[[int, int, str], None]


def summarize_tool_result(name: str, result: dict[str, Any]) -> str:
    """Short summary for tool trace UI."""
    if "error" in result and result.get("error"):
        return f"error: {result['error']}"
    if name in ("search_workshop_mods", "search_steam_workshop"):
        return f"{result.get('count', len(result.get('matches', [])))} matches"
    if name == "find_russian_localizations_for_active_mods":
        needing = len(result.get("mods_needing_localization", []))
        suggestions = len(result.get("suggestions", []))
        with_rec = sum(1 for s in result.get("suggestions", []) if s.get("recommended"))
        return (
            f"{needing} need localization, {with_rec}/{suggestions} with recommendation"
        )
    if name == "validate_workshop_ids":
        valid = len(result.get("valid", []))
        invalid = len(result.get("invalid", []))
        return f"{valid} valid, {invalid} invalid"
    if name == "queue_download":
        if result.get("ok"):
            parts = [f"queued {result.get('count', 0)}"]
            if result.get("invalid_ids"):
                parts.append(f"skipped {len(result['invalid_ids'])} invalid")
            return ", ".join(parts)
        return f"failed: {result.get('error', 'unknown')}"
    if name == "get_instance_summary":
        configured = result.get("steam_apikey_configured", False)
        return (
            f"active {result.get('active_mod_count', 0)}, "
            f"steam key {'yes' if configured else 'no'}"
        )
    if name == "search_installed_mods":
        return f"{result.get('count', 0)} matches"
    if name == "read_log":
        return f"{result.get('line_count', 0)} lines"
    if "count" in result:
        return f"count={result['count']}"
    if result.get("ok"):
        return "ok"
    return "done"


class ModToolExecutor:
    """Thin wrapper so Gemini tool calls use the same dispatch as MCP."""

    def __init__(
        self,
        steam_apikey_override: str | None = None,
        on_tool_call: Callable[[str, dict[str, Any], dict[str, Any]], None]
        | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self._steam_apikey_override = steam_apikey_override
        self._on_tool_call = on_tool_call
        self._on_progress = on_progress

    def __call__(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            result = call_tool(
                name,
                args,
                steam_apikey_override=self._steam_apikey_override,
                on_progress=self._on_progress,
            )
        except ValueError as exc:
            result = {"error": str(exc)}
        if not isinstance(result, dict):
            result = {"result": result}
        if self._on_tool_call is not None:
            self._on_tool_call(name, args, result)
        return result


def build_tool_executor(
    metadata_controller: object | None = None,
    active_paths: list[str] | None = None,
    steam_apikey_override: str | None = None,
    on_tool_call: Callable[[str, dict[str, Any], dict[str, Any]], None] | None = None,
    on_progress: ProgressCallback | None = None,
) -> ModToolExecutor:
    del metadata_controller, active_paths
    return ModToolExecutor(
        steam_apikey_override=steam_apikey_override,
        on_tool_call=on_tool_call,
        on_progress=on_progress,
    )
