from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest

from app.utils.mod_utils import (
    filter_eligible_mods_for_update,
    get_mod_name_from_pfid,
    get_mod_paths_from_uuids,
)


@pytest.fixture
def metadata_manager_mock() -> Generator[MagicMock, None, None]:
    with patch("app.utils.metadata.MetadataManager.instance") as mock_instance:
        mock = MagicMock()
        mock.internal_local_metadata = {
            "uuid1": {
                "publishedfileid": "123",
                "name": "Mod One",
                "path": "/path/to/mod1",
            },
            "uuid2": {
                "publishedfileid": "456",
                "name": "Mod Two",
                "path": "/path/to/mod2",
            },
        }
        mock.external_steam_metadata = {"789": {"name": "External Mod"}}
        mock_instance.return_value = mock
        yield mock


def test_get_mod_name_from_pfid_valid_internal(
    metadata_manager_mock: MagicMock,
) -> None:
    assert get_mod_name_from_pfid("123") == "Mod One"
    assert get_mod_name_from_pfid(123) == "Mod One"


def test_get_mod_name_from_pfid_valid_external(
    metadata_manager_mock: MagicMock,
) -> None:
    assert get_mod_name_from_pfid("789") == "External Mod"


def test_get_mod_name_from_pfid_invalid(metadata_manager_mock: MagicMock) -> None:
    assert get_mod_name_from_pfid("999") == "Invalid ID: 999"
    assert get_mod_name_from_pfid("abc") == "Invalid ID: abc"
    assert get_mod_name_from_pfid(None) == "Unknown Mod"


def test_get_mod_paths_from_uuids(metadata_manager_mock: MagicMock) -> None:
    with patch("os.path.isdir") as isdir_mock:
        isdir_mock.side_effect = lambda path: path in ["/path/to/mod1", "/path/to/mod2"]
        paths = get_mod_paths_from_uuids(["uuid1", "uuid2", "uuid3"])
        assert "/path/to/mod1" in paths
        assert "/path/to/mod2" in paths
        assert len(paths) == 2


def test_get_mod_paths_from_uuids_with_nonexistent_path(
    metadata_manager_mock: MagicMock,
) -> None:
    with patch("os.path.isdir") as isdir_mock:
        isdir_mock.return_value = False
        paths = get_mod_paths_from_uuids(["uuid1"])
        assert paths == []


# Tests for filter_eligible_mods_for_update


def test_filter_eligible_mods_outdated() -> None:
    """Test that mods with external > internal are marked for update."""
    now = 1700000000  # Fixed timestamp for reproducibility
    week_ago = now - (7 * 86400)

    metadata = {
        "uuid1": {
            "name": "Outdated Mod",
            "publishedfileid": "123456",
            "data_source": "workshop",
            "internal_time_touched": week_ago,
            "external_time_updated": now,
        },
        "uuid2": {
            "name": "Up-to-date Mod",
            "publishedfileid": "789012",
            "data_source": "workshop",
            "internal_time_touched": now,
            "external_time_updated": week_ago,
        },
    }

    eligible = filter_eligible_mods_for_update(metadata)

    assert len(eligible) == 1
    assert eligible[0]["name"] == "Outdated Mod"
    assert eligible[0]["publishedfileid"] == "123456"


def test_filter_eligible_mods_up_to_date() -> None:
    """Test that mods with internal >= external are filtered out."""
    now = 1700000000
    week_ago = now - (7 * 86400)

    metadata = {
        "uuid1": {
            "name": "Current Mod",
            "publishedfileid": "123456",
            "data_source": "workshop",
            "internal_time_touched": now,
            "external_time_updated": week_ago,
        },
        "uuid2": {
            "name": "Equal Timestamp Mod",
            "publishedfileid": "789012",
            "data_source": "workshop",
            "internal_time_touched": now,
            "external_time_updated": now,  # Equal timestamps
        },
    }

    eligible = filter_eligible_mods_for_update(metadata)

    assert len(eligible) == 0


def test_filter_eligible_mods_missing_timestamps() -> None:
    """Test that mods with missing timestamps are skipped."""
    now = 1700000000

    metadata: dict[str, dict[str, Any]] = {
        "uuid1": {
            "name": "Missing Internal",
            "publishedfileid": "123456",
            "data_source": "workshop",
            "external_time_updated": now,
            # Missing internal_time_touched
        },
        "uuid2": {
            "name": "Missing External",
            "publishedfileid": "789012",
            "data_source": "workshop",
            "internal_time_touched": now,
            # Missing external_time_updated
        },
        "uuid3": {
            "name": "Missing Both",
            "publishedfileid": "345678",
            "data_source": "workshop",
            # Missing both timestamps
        },
    }

    eligible = filter_eligible_mods_for_update(metadata)

    assert len(eligible) == 0


def test_filter_eligible_mods_fallback_to_updated() -> None:
    """Test that internal_time_updated is used as fallback when internal_time_touched missing."""
    now = 1700000000
    week_ago = now - (7 * 86400)

    metadata = {
        "uuid1": {
            "name": "Fallback Mod",
            "publishedfileid": "123456",
            "data_source": "workshop",
            # No internal_time_touched
            "internal_time_updated": week_ago,  # Fallback timestamp
            "external_time_updated": now,
        },
    }

    eligible = filter_eligible_mods_for_update(metadata)

    assert len(eligible) == 1
    assert eligible[0]["name"] == "Fallback Mod"


def test_filter_eligible_mods_mixed_sources() -> None:
    """Test filtering with mix of workshop and steamcmd mods."""
    now = 1700000000
    week_ago = now - (7 * 86400)

    metadata = {
        "uuid1": {
            "name": "Workshop Mod Outdated",
            "publishedfileid": "123456",
            "data_source": "workshop",
            "internal_time_touched": week_ago,
            "external_time_updated": now,
        },
        "uuid2": {
            "name": "SteamCMD Mod Outdated",
            "publishedfileid": "789012",
            "steamcmd": True,
            "internal_time_touched": week_ago,
            "external_time_updated": now,
        },
        "uuid3": {
            "name": "Local Mod",
            "data_source": "local",  # Not workshop or steamcmd
            "internal_time_touched": week_ago,
            "external_time_updated": now,
        },
    }

    eligible = filter_eligible_mods_for_update(metadata)

    assert len(eligible) == 2
    names = {mod["name"] for mod in eligible}
    assert "Workshop Mod Outdated" in names
    assert "SteamCMD Mod Outdated" in names
    assert "Local Mod" not in names


def test_filter_eligible_mods_empty_metadata() -> None:
    """Test with empty metadata dict."""
    eligible = filter_eligible_mods_for_update({})
    assert len(eligible) == 0
