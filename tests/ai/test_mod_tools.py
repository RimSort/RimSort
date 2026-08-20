from typing import Any

import pytest

from app.ai.tools.mod_tools import ModToolExecutor
from app.mcp.tools import call_tool


class TestModToolExecutor:
    def test_describe_mod_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.mcp.tools.rim_sort_context.describe_mod",
            lambda package_id, instance_name=None: {
                "package_id": package_id,
                "name": "Test Mod",
                "description": "A test mod",
                "mod_dependencies": ["dep.mod"],
            },
        )
        executor = ModToolExecutor()
        result = executor("describe_mod", {"package_id": "test.mod"})
        assert result["found"] is True
        assert result["name"] == "Test Mod"
        assert result["mod_dependencies"] == ["dep.mod"]

    def test_describe_mod_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.mcp.tools.rim_sort_context.describe_mod",
            lambda package_id, instance_name=None: None,
        )
        executor = ModToolExecutor()
        result = executor("describe_mod", {"package_id": "missing.mod"})
        assert result["found"] is False

    def test_search_installed_mods(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.mcp.tools.rim_sort_context.search_installed_mods",
            lambda query, limit=20, instance_name=None: [
                {"package_id": "author.mod", "name": "My Mod"}
            ],
        )
        executor = ModToolExecutor()
        result = executor("search_installed_mods", {"query": "my", "limit": 5})
        assert result["count"] == 1
        assert result["matches"][0]["package_id"] == "author.mod"

    def test_unknown_tool(self) -> None:
        executor = ModToolExecutor()
        result = executor("unknown_tool", {})
        assert "error" in result

    def test_steam_apikey_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, str | None] = {}

        def fake_search(
            query: str,
            limit: int = 20,
            instance_name: str | None = None,
            steam_apikey_override: str | None = None,
        ) -> dict[str, Any]:
            captured["override"] = steam_apikey_override
            return {"query": query, "matches": [], "count": 0, "source": "steam_api"}

        monkeypatch.setattr(
            "app.mcp.tools.rim_sort_context.search_workshop_mods",
            fake_search,
        )
        executor = ModToolExecutor(steam_apikey_override="live-key")
        executor("search_workshop_mods", {"query": "test"})
        assert captured["override"] == "live-key"

    def test_shared_call_tool_describe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.mcp.tools.rim_sort_context.describe_mod",
            lambda package_id, instance_name=None: None,
        )
        result = call_tool("describe_mod", {"package_id": "x.y"})
        assert result["found"] is False
