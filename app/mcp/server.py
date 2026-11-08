"""MCP server construction: binds :mod:`app.mcp.core` to the tool protocol.

The server object is built separately from the process bootstrap so tests can
exercise the exact tool schemas and dispatch path without a stdio transport.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from loguru import logger
from mcp.server.mcpserver import MCPServer

from app.mcp.core import RimSortMcpCore
from app.utils.app_info import AppInfo

SERVER_NAME = "RimSort"


def _guarded(name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a tool so unexpected failures surface as structured errors.

    A raised exception would abort the JSON-RPC frame and leave the agent with
    no diagnostics, so every tool returns a payload carrying an ``error`` key
    instead. The traceback still reaches the log sink for later inspection.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            logger.opt(exception=exc).error(f"MCP tool {name} failed")
            return {
                "error": f"{type(exc).__name__}: {exc}",
                "tool": name,
                "hint": "Check the RimSort log for the full traceback.",
            }

    return wrapper


def build_server(core: RimSortMcpCore) -> MCPServer[Any]:
    """Build the RimSort MCP server exposing the tool surface.

    :param core: Tool implementation bound to the loaded metadata state
    :return: A configured server; the caller decides which transport to run
    """
    server: MCPServer[Any] = MCPServer(
        SERVER_NAME,
        version=AppInfo().app_version,
        instructions=(
            "RimSort mod manager tools for RimWorld. Start with "
            "get_instance_status to confirm the game version and configured "
            "paths, then use get_active_modlist or search_installed_mods to "
            "discover package IDs. analyze_and_sort_modlist validates and "
            "returns an optimal load order without touching disk; "
            "apply_active_modlist writes ModsConfig.xml and only accepts a "
            "list it could validate. Package IDs are case-insensitive."
        ),
    )

    def register(name: str, fn: Callable[..., Any]) -> None:
        server.add_tool(_guarded(name, fn), name=name)

    register("get_instance_status", core.get_instance_status)
    register("search_installed_mods", core.search_installed_mods)
    register("get_mod_details", core.get_mod_details)
    register("get_active_modlist", core.get_active_modlist)
    register("analyze_and_sort_modlist", core.analyze_and_sort_modlist)
    register("apply_active_modlist", core.apply_active_modlist)
    register("refresh_metadata_cache", core.refresh_metadata_cache)

    return server
