from unittest.mock import patch

from app.mcp.tools import call_tool


def test_queue_download_rejects_invalid_ids() -> None:
    with patch(
        "app.mcp.tools.command_queue.require_gui_for_mutation",
        return_value=None,
    ), patch(
        "app.mcp.tools.command_queue.enqueue",
    ) as mock_enqueue, patch(
        "app.mcp.tools.validate_publishedfileids",
        return_value={"valid": ["111"], "invalid": ["fake999"], "valid_details": []},
    ):
        result = call_tool(
            "queue_download",
            {"publishedfileids": ["111", "fake999"]},
        )

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["valid_ids"] == ["111"]
    assert "fake999" in result["invalid_ids"]
    mock_enqueue.assert_called_once()
    assert mock_enqueue.call_args[0][0]["publishedfileids"] == ["111"]


def test_queue_download_all_invalid() -> None:
    with patch(
        "app.mcp.tools.command_queue.require_gui_for_mutation",
        return_value=None,
    ), patch(
        "app.mcp.tools.validate_publishedfileids",
        return_value={"valid": [], "invalid": ["bad"], "valid_details": []},
    ):
        result = call_tool("queue_download", {"publishedfileids": ["bad"]})

    assert result["ok"] is False
    assert "invalid" in result["error"].lower() or "valid" in result["error"].lower()


def test_queue_download_accepts_metadata_only_ids() -> None:
    metadata = [{"publishedfileid": "555", "title": "Metadata Only Mod"}]
    with patch(
        "app.mcp.tools.command_queue.require_gui_for_mutation",
        return_value=None,
    ), patch(
        "app.mcp.tools.command_queue.enqueue",
    ) as mock_enqueue, patch(
        "app.utils.steam.workshop_validate.ISteamRemoteStorage_GetPublishedFileDetails",
        return_value=(metadata, [], []),
    ):
        result = call_tool(
            "queue_download",
            {"publishedfileids": ["555"]},
        )

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["valid_ids"] == ["555"]
    assert "invalid_ids" not in result
    mock_enqueue.assert_called_once()
    assert mock_enqueue.call_args[0][0]["publishedfileids"] == ["555"]


def test_queue_download_rejects_wrong_appid_ids() -> None:
    metadata = [
        {
            "publishedfileid": "777",
            "result": 1,
            "appid": 730,
            "title": "CS2 Skin",
        }
    ]
    with patch(
        "app.mcp.tools.command_queue.require_gui_for_mutation",
        return_value=None,
    ), patch(
        "app.utils.steam.workshop_validate.ISteamRemoteStorage_GetPublishedFileDetails",
        return_value=(metadata, [], []),
    ):
        result = call_tool(
            "queue_download",
            {"publishedfileids": ["777"]},
        )

    assert result["ok"] is False
    assert result["valid_ids"] == []
    assert "777" in result["invalid_ids"]


def test_find_russian_localizations_tool() -> None:
    fake = {
        "mods_needing_localization": [],
        "suggestions": [],
        "skipped_already_localized": [],
        "errors": [],
    }
    with patch(
        "app.mcp.tools.rim_sort_context.find_russian_localizations_for_active_mods_tool",
        return_value=fake,
    ) as mock_find:
        result = call_tool("find_russian_localizations_for_active_mods", {})

    mock_find.assert_called_once()
    assert result == fake


def test_validate_workshop_ids_tool() -> None:
    with patch(
        "app.mcp.tools.validate_publishedfileids",
        return_value={"valid": ["1"], "invalid": [], "valid_details": []},
    ):
        result = call_tool(
            "validate_workshop_ids",
            {"publishedfileids": ["1"]},
        )
    assert result["valid"] == ["1"]


def test_search_workshop_mods_tool() -> None:
    fake = {
        "query": "harmony",
        "matches": [
            {
                "publishedfileid": "2009463077",
                "title": "Harmony",
                "url": "https://steamcommunity.com/sharedfiles/filedetails/?id=2009463077",
            }
        ],
        "count": 1,
        "source": "steam_api",
    }
    with patch(
        "app.mcp.tools.rim_sort_context.search_workshop_mods",
        return_value=fake,
    ) as mock_search:
        result = call_tool("search_workshop_mods", {"query": "harmony", "limit": 5})

    mock_search.assert_called_once()
    assert result["count"] == 1
    assert result["matches"][0]["publishedfileid"] == "2009463077"


def test_search_steam_workshop_alias() -> None:
    with patch(
        "app.mcp.tools.rim_sort_context.search_workshop_mods",
        return_value={"query": "x", "matches": [], "count": 0, "source": "steam_api"},
    ) as mock_search:
        call_tool("search_steam_workshop", {"query": "x"})
    mock_search.assert_called_once()
