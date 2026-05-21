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


# --- filter_eligible_mods_for_update tests ---


def _make_mod(
    name: str = "Test Mod",
    pfid: str = "12345",
    data_source: str = "workshop",
    internal_time_touched: int | None = None,
    internal_time_updated: int | None = None,
    external_time_updated: int | None = None,
    steamcmd: bool = False,
) -> dict[str, Any]:
    """Helper to build a mod metadata dict for testing."""
    mod: dict[str, Any] = {
        "name": name,
        "publishedfileid": pfid,
        "data_source": data_source,
    }
    if steamcmd:
        mod["steamcmd"] = True
    if internal_time_touched is not None:
        mod["internal_time_touched"] = internal_time_touched
    if internal_time_updated is not None:
        mod["internal_time_updated"] = internal_time_updated
    if external_time_updated is not None:
        mod["external_time_updated"] = external_time_updated
    return mod


class TestFilterEligibleModsForUpdate:
    """Tests for filter_eligible_mods_for_update."""

    def test_basic_eligible_mod(self) -> None:
        """A workshop mod where external > internal_time_touched is eligible."""
        mods = {
            "uuid1": _make_mod(
                internal_time_touched=1000,
                external_time_updated=2000,
            ),
        }
        result = filter_eligible_mods_for_update(mods)
        assert len(result) == 1
        assert result[0]["name"] == "Test Mod"

    def test_fallback_to_internal_time_updated(self) -> None:
        """When internal_time_touched is missing, falls back to internal_time_updated."""
        mods = {
            "uuid1": _make_mod(
                internal_time_updated=1000,
                external_time_updated=2000,
            ),
        }
        result = filter_eligible_mods_for_update(mods)
        assert len(result) == 1

    def test_internal_time_touched_preferred_over_updated(self) -> None:
        """internal_time_touched takes priority when both are present."""
        # internal_time_touched=3000 > external=2000 => not eligible
        # internal_time_updated=1000 < external=2000 => would be eligible if used
        mods = {
            "uuid1": _make_mod(
                internal_time_touched=3000,
                internal_time_updated=1000,
                external_time_updated=2000,
            ),
        }
        result = filter_eligible_mods_for_update(mods)
        assert len(result) == 0, (
            "Should use internal_time_touched, not internal_time_updated"
        )

    def test_neither_internal_timestamp_present(self) -> None:
        """Mods with no internal timestamps at all are skipped."""
        mods = {
            "uuid1": _make_mod(
                external_time_updated=2000,
            ),
        }
        result = filter_eligible_mods_for_update(mods)
        assert len(result) == 0

    def test_up_to_date_mod_skipped(self) -> None:
        """Mods where external <= internal are skipped."""
        mods = {
            "uuid1": _make_mod(
                internal_time_touched=2000,
                external_time_updated=2000,
            ),
            "uuid2": _make_mod(
                name="Older External",
                pfid="99999",
                internal_time_touched=3000,
                external_time_updated=1000,
            ),
        }
        result = filter_eligible_mods_for_update(mods)
        assert len(result) == 0

    def test_non_workshop_mod_skipped(self) -> None:
        """Non-workshop mods are never eligible."""
        mods = {
            "uuid1": _make_mod(
                data_source="local",
                internal_time_touched=1000,
                external_time_updated=2000,
            ),
        }
        result = filter_eligible_mods_for_update(mods)
        assert len(result) == 0

    def test_steamcmd_mod_eligible(self) -> None:
        """SteamCMD mods are treated like workshop mods."""
        mods = {
            "uuid1": _make_mod(
                data_source="local",
                steamcmd=True,
                internal_time_touched=1000,
                external_time_updated=2000,
            ),
        }
        result = filter_eligible_mods_for_update(mods)
        assert len(result) == 1

    def test_mixed_mods(self) -> None:
        """Only workshop/steamcmd mods with updates are returned from a mixed set."""
        mods = {
            "uuid1": _make_mod(
                name="Eligible Workshop",
                pfid="111",
                internal_time_touched=1000,
                external_time_updated=2000,
            ),
            "uuid2": _make_mod(
                name="Local Mod",
                pfid="222",
                data_source="local",
                internal_time_touched=1000,
                external_time_updated=2000,
            ),
            "uuid3": _make_mod(
                name="Up To Date Workshop",
                pfid="333",
                internal_time_touched=3000,
                external_time_updated=2000,
            ),
            "uuid4": _make_mod(
                name="Eligible SteamCMD",
                pfid="444",
                data_source="local",
                steamcmd=True,
                internal_time_updated=500,
                external_time_updated=2000,
            ),
        }
        result = filter_eligible_mods_for_update(mods)
        names = {m["name"] for m in result}
        assert names == {"Eligible Workshop", "Eligible SteamCMD"}

    def test_zero_internal_time_touched_treated_as_missing(self) -> None:
        """internal_time_touched=0 should fall back to internal_time_updated."""
        mods = {
            "uuid1": _make_mod(
                internal_time_touched=0,
                internal_time_updated=1000,
                external_time_updated=2000,
            ),
        }
        result = filter_eligible_mods_for_update(mods)
        assert len(result) == 1

    def test_zero_internal_time_updated_treated_as_missing(self) -> None:
        """Both timestamps being zero means no valid internal time."""
        mods = {
            "uuid1": _make_mod(
                internal_time_touched=0,
                internal_time_updated=0,
                external_time_updated=2000,
            ),
        }
        result = filter_eligible_mods_for_update(mods)
        assert len(result) == 0

    def test_zero_external_time_treated_as_missing(self) -> None:
        """external_time_updated=0 should cause the mod to be skipped."""
        mods = {
            "uuid1": _make_mod(
                internal_time_touched=1000,
                external_time_updated=0,
            ),
        }
        result = filter_eligible_mods_for_update(mods)
        assert len(result) == 0

    def test_no_external_time(self) -> None:
        """Mods missing external_time_updated entirely are skipped."""
        mods = {
            "uuid1": _make_mod(
                internal_time_touched=1000,
            ),
        }
        result = filter_eligible_mods_for_update(mods)
        assert len(result) == 0

    def test_empty_metadata(self) -> None:
        """Empty metadata dict returns empty list."""
        result = filter_eligible_mods_for_update({})
        assert result == []

    def test_signature_unchanged(self) -> None:
        """Function signature accepts dict[str, dict[str, Any]] and returns list[dict[str, Any]]."""
        metadata: dict[str, dict[str, Any]] = {}
        result: list[dict[str, Any]] = filter_eligible_mods_for_update(metadata)
        assert isinstance(result, list)
