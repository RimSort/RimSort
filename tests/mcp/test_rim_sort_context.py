from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.mcp import rim_sort_context


@pytest.fixture
def mcp_instance_layout(tmp_path: Path) -> dict[str, Any]:
    storage = tmp_path / "storage"
    storage.mkdir()
    logs = tmp_path / "logs"
    logs.mkdir()
    logs.joinpath("RimSort.log").write_text(
        "line1\nline2\nerror: boom\n", encoding="utf-8"
    )

    game = tmp_path / "game"
    game.mkdir()
    (game / "Version.txt").write_text("1.5.4409 rev1120\n", encoding="utf-8")
    config = game / "Config"
    config.mkdir()
    mods = game / "Mods"
    mods.mkdir()

    fixtures = Path(__file__).parent / "fixtures"
    for name in ("fishery", "harmony"):
        src = fixtures / name
        dst = mods / name
        dst.mkdir()
        (dst / "About").mkdir()
        (dst / "About" / "About.xml").write_text(
            (src / "About" / "About.xml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    (config / "ModsConfig.xml").write_text(
        (fixtures / "ModsConfig.xml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    player_log = game / "Player.log"
    player_log.write_text("Player started\nException: test\n", encoding="utf-8")

    settings = {
        "current_instance": "Default",
        "instances": {
            "Default": {
                "game_folder": str(game),
                "config_folder": str(config),
                "local_folder": str(mods),
                "workshop_folder": "",
            }
        },
    }
    (storage / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    return {
        "storage": storage,
        "logs": logs,
        "game": game,
        "config": config,
        "mods": mods,
    }


@pytest.fixture
def patch_app_info(
    mcp_instance_layout: dict[str, Any],
) -> Generator[None, None, None]:
    with patch("app.mcp.rim_sort_context.AppInfo") as mock_info:
        mock_info.return_value.app_storage_folder = mcp_instance_layout["storage"]
        mock_info.return_value.user_log_folder = mcp_instance_layout["logs"]
        yield


def test_search_installed_mods(patch_app_info: None) -> None:
    matches = rim_sort_context.search_installed_mods("fish", limit=10)
    assert len(matches) == 1
    assert matches[0]["package_id"] == "bs.fishery"


def test_describe_mod(patch_app_info: None) -> None:
    info = rim_sort_context.describe_mod("bs.fishery")
    assert info is not None
    assert info["name"] == "Fishery - Modding Library"
    assert "brrainz.harmony" in info["mod_dependencies"]
    assert "missing.dep" in info["mod_dependencies"]


def test_list_missing_deps(patch_app_info: None) -> None:
    result = rim_sort_context.list_missing_deps()
    assert result["missing_by_mod"]["bs.fishery"] == ["missing.dep"]


def test_get_instance_summary(
    patch_app_info: None, mcp_instance_layout: dict[str, Any]
) -> None:
    summary = rim_sort_context.get_instance_summary()
    assert summary["current_instance"] == "Default"
    assert summary["installed_mod_count"] == 2
    assert summary["active_mod_count"] == 2
    assert summary["game_version"] == "1.5.4409 rev1120"
    assert summary["game_folder"] == str(mcp_instance_layout["game"])
    assert summary["steam_apikey_configured"] is False
    assert summary["steam_apikey_length"] == 0


def test_get_instance_summary_steam_key_override() -> None:
    summary = rim_sort_context.get_instance_summary(
        steam_apikey_override="abcd1234abcd1234abcd1234abcd1234"
    )
    assert summary["steam_apikey_configured"] is True
    assert summary["steam_apikey_length"] == 32


def test_read_log_rimsort(patch_app_info: None) -> None:
    result = rim_sort_context.read_log("rimsort", tail_lines=10)
    assert result["line_count"] == 3
    assert "error: boom" in result["lines"][-1]


def test_read_log_player_grep(patch_app_info: None) -> None:
    result = rim_sort_context.read_log("player", tail_lines=10, grep="Exception")
    assert result["line_count"] == 1
    assert "Exception" in result["lines"][0]


def test_search_workshop_mods_no_api_key(patch_app_info: None) -> None:
    result = rim_sort_context.search_workshop_mods("harmony")
    assert result["matches"] == []
    assert "steam_apikey" in result["error"]


def test_search_workshop_mods_with_api_key(
    patch_app_info: None, mcp_instance_layout: dict[str, Any]
) -> None:
    settings_path = mcp_instance_layout["storage"] / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["steam_apikey"] = "test-steam-key"
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    fake_matches = [
        {
            "publishedfileid": "123",
            "title": "Test Mod",
            "url": "https://steamcommunity.com/sharedfiles/filedetails/?id=123",
        }
    ]
    with patch(
        "app.mcp.rim_sort_context.search_workshop_by_text",
        return_value=fake_matches,
    ) as mock_search:
        result = rim_sort_context.search_workshop_mods("test", limit=5)

    mock_search.assert_called_once_with("test-steam-key", "test", limit=5)
    assert result["count"] == 1
    assert result["matches"][0]["title"] == "Test Mod"
    assert result["source"] == "steam_api"


def _fake_localization_result(
    candidates: list[dict[str, Any]], recommended: dict[str, Any]
) -> dict[str, Any]:
    return {
        "mods_needing_localization": [{"package_id": "x.y", "name": "X Y"}],
        "skipped_already_localized": [],
        "suggestions": [
            {
                "target_package_id": "x.y",
                "target_name": "X Y",
                "candidates": candidates,
                "recommended": recommended,
            }
        ],
        "errors": [],
        "source": "steam_api",
    }


def test_find_localizations_validates_candidates(
    patch_app_info: None,
) -> None:
    fake_result = _fake_localization_result(
        candidates=[
            {
                "publishedfileid": "111",
                "title": "X Y Russian",
                "url": "https://steamcommunity.com/sharedfiles/filedetails/?id=111",
                "score": 2.0,
            },
            {
                "publishedfileid": "999",
                "title": "Fake",
                "url": "https://steamcommunity.com/sharedfiles/filedetails/?id=999",
                "score": 1.0,
            },
        ],
        recommended={"publishedfileid": "111", "title": "X Y Russian"},
    )
    with (
        patch(
            "app.mcp.rim_sort_context.find_localizations_for_active_mods",
            return_value=fake_result,
        ),
        patch(
            "app.mcp.rim_sort_context.validate_publishedfileids",
            return_value={"valid": ["111"], "invalid": ["999"], "valid_details": []},
        ),
    ):
        result = rim_sort_context.find_localizations_for_active_mods_tool(
            language="ru",
            steam_apikey_override="test-key",
        )

    assert len(result["suggestions"]) == 1
    assert len(result["suggestions"][0]["candidates"]) == 1
    assert result["suggestions"][0]["candidates"][0]["publishedfileid"] == "111"
    assert result["suggestions"][0]["recommended"]["publishedfileid"] == "111"
    assert result["validation"]["removed_invalid_candidates"] == 1


def test_find_localizations_keeps_metadata_only_candidates(
    patch_app_info: None,
) -> None:
    fake_result = _fake_localization_result(
        candidates=[
            {
                "publishedfileid": "555",
                "title": "X Y Russian",
                "url": "https://steamcommunity.com/sharedfiles/filedetails/?id=555",
                "score": 2.0,
            }
        ],
        recommended={"publishedfileid": "555", "title": "X Y Russian"},
    )
    metadata = [{"publishedfileid": "555", "title": "X Y Russian"}]
    with (
        patch(
            "app.mcp.rim_sort_context.find_localizations_for_active_mods",
            return_value=fake_result,
        ),
        patch(
            "app.utils.steam.workshop_validate.ISteamRemoteStorage_GetPublishedFileDetails",
            return_value=(metadata, [], []),
        ),
    ):
        result = rim_sort_context.find_localizations_for_active_mods_tool(
            language="ru",
            steam_apikey_override="test-key",
        )

    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["candidates"][0]["publishedfileid"] == "555"
    assert result["suggestions"][0]["recommended"]["publishedfileid"] == "555"
    assert "validation" not in result
