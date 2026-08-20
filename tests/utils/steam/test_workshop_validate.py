from unittest.mock import patch

from app.utils.steam.workshop_validate import validate_publishedfileids


def test_validate_publishedfileids_splits_valid_invalid() -> None:
    metadata = [
        {
            "publishedfileid": "111",
            "result": 1,
            "appid": 294100,
            "title": "Valid Mod",
        }
    ]
    with patch(
        "app.utils.steam.workshop_validate.ISteamRemoteStorage_GetPublishedFileDetails",
        return_value=(metadata, ["222"], []),
    ):
        result = validate_publishedfileids(["111", "222", "333"])

    assert result["valid"] == ["111"]
    assert "222" in result["invalid"]
    assert "333" in result["invalid"]
    assert result["valid_details"][0]["title"] == "Valid Mod"


def test_validate_publishedfileids_empty() -> None:
    result = validate_publishedfileids([])
    assert result["valid"] == []
    assert result["invalid"] == []


def test_validate_publishedfileids_metadata_only_without_appid_result() -> None:
    metadata = [
        {
            "publishedfileid": "555",
            "title": "Metadata Only Mod",
        }
    ]
    with patch(
        "app.utils.steam.workshop_validate.ISteamRemoteStorage_GetPublishedFileDetails",
        return_value=(metadata, [], []),
    ):
        result = validate_publishedfileids(["555"])

    assert result["valid"] == ["555"]
    assert result["invalid"] == []
    assert result["valid_details"][0]["title"] == "Metadata Only Mod"


def test_validate_publishedfileids_rejects_wrong_appid() -> None:
    metadata = [
        {
            "publishedfileid": "777",
            "result": 1,
            "appid": 730,
            "title": "CS2 Skin",
        }
    ]
    with patch(
        "app.utils.steam.workshop_validate.ISteamRemoteStorage_GetPublishedFileDetails",
        return_value=(metadata, [], []),
    ):
        result = validate_publishedfileids(["777"])

    assert result["valid"] == []
    assert result["invalid"] == ["777"]
