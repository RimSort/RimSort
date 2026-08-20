from collections.abc import Callable
from typing import Any

from app.mcp.tools import call_tool, gemini_tool_declarations

GEMINI_MOD_TOOL_DECLARATIONS = gemini_tool_declarations()


class ModToolExecutor:
    """Thin wrapper so Gemini tool calls use the same dispatch as MCP."""

    def __call__(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            result = call_tool(name, args)
        except ValueError as exc:
            return {"error": str(exc)}
        if isinstance(result, dict):
            return result
        return {"result": result}


def build_tool_executor(
    metadata_controller: object | None = None,
    active_paths: list[str] | None = None,
) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    del metadata_controller, active_paths
    return ModToolExecutor()
