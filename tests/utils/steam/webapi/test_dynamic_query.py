"""Tests for DynamicQuery caching and re-processing of WebAPI responses."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.utils.steam.webapi.wrapper import DynamicQuery


@pytest.fixture
def dq() -> DynamicQuery:
    """Create a DynamicQuery with a mocked API, bypassing QObject.__init__."""
    with patch.object(DynamicQuery, "__init__", lambda self: None):
        obj = DynamicQuery.__new__(DynamicQuery)
        obj.apikey = "x" * 32
        obj.appid = 294100
        obj.expiry = 0
        obj.get_appid_deps = False
        obj.callback = lambda msg: None
        obj.api = MagicMock()  # type: ignore[assignment]
        obj.database = {}
        obj.next_cursor = "*"
        obj.pagenum = 1
        obj.pages = 1
        obj.publishedfileids = []
        obj.total = 0
        return obj


def _make_mod(
    pfid: str,
    title: str,
    children: list[str] | None = None,
    result: int = 1,
) -> dict[str, Any]:
    """Build a publishedfiledetails dict for testing."""
    detail: dict[str, Any] = {
        "publishedfileid": pfid,
        "result": result,
        "title": title,
    }
    if children:
        detail["children"] = [{"publishedfileid": c} for c in children]
    return detail


def _skeleton(pfid: str) -> dict[str, str]:
    """Build a skeleton DB entry matching _init_empty_db_from_publishedfileids."""
    return {"url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"}


def _make_database(*pfids: str) -> dict[str, Any]:
    """Build a database dict with skeleton entries for the given pfids."""
    return {"version": 0, "database": {p: _skeleton(p) for p in pfids}}


class TestProcessModDetails:
    """_process_mod_details resolves dependencies from raw API details."""

    def test_populates_metadata(self, dq: DynamicQuery) -> None:
        details = [_make_mod("111", "Test Mod")]
        db: dict[str, Any] = {"database": {}}
        dq._process_mod_details(details, db)
        assert db["database"]["111"]["steamName"] == "Test Mod"
        assert "111" in db["database"]["111"]["url"]

    def test_resolves_known_child(self, dq: DynamicQuery) -> None:
        details = [_make_mod("111", "Parent", children=["222"])]
        db: dict[str, Any] = {
            "database": {
                "222": {
                    "steamName": "Child Mod",
                    "url": "https://steamcommunity.com/sharedfiles/filedetails/?id=222",
                }
            }
        }
        dq._process_mod_details(details, db)
        assert "222" in db["database"]["111"]["dependencies"]
        assert db["database"]["111"]["dependencies"]["222"][0] == "Child Mod"

    def test_returns_missing_children(self, dq: DynamicQuery) -> None:
        details = [_make_mod("111", "Parent", children=["999"])]
        db: dict[str, Any] = {"database": {}}
        missing = dq._process_mod_details(details, db)
        assert "999" in missing

    def test_marks_unpublished(self, dq: DynamicQuery) -> None:
        details = [_make_mod("111", "Gone", result=5)]
        db: dict[str, Any] = {"database": {}}
        dq._process_mod_details(details, db)
        assert db["database"]["111"]["unpublished"] is True

    def test_filters_unpublished_from_missing(self, dq: DynamicQuery) -> None:
        details = [_make_mod("111", "Parent", children=["222"])]
        db: dict[str, Any] = {"database": {"222": {"unpublished": True}}}
        missing = dq._process_mod_details(details, db)
        assert "222" not in missing

    def test_prefers_local_name(self, dq: DynamicQuery) -> None:
        details = [_make_mod("111", "Parent", children=["222"])]
        db: dict[str, Any] = {
            "database": {
                "222": {
                    "name": "Local Name",
                    "steamName": "Steam Name",
                    "url": "https://example.com",
                }
            }
        }
        dq._process_mod_details(details, db)
        assert db["database"]["111"]["dependencies"]["222"][0] == "Local Name"


class TestGetDetailsReturnsCachedDetails:
    """IPublishedFileService_GetDetails returns raw details as third tuple element."""

    def test_returns_three_element_tuple(self, dq: DynamicQuery) -> None:
        dq.api.call.return_value = {"response": {"publishedfiledetails": []}}  # type: ignore[attr-defined]
        result = dq.IPublishedFileService_GetDetails({"database": {}}, [])
        assert result is not None
        assert len(result) == 3

    def test_cached_details_match_api_response(self, dq: DynamicQuery) -> None:
        mod = _make_mod("111", "Test Mod")
        dq.api.call.return_value = {"response": {"publishedfiledetails": [mod]}}  # type: ignore[attr-defined]
        result = dq.IPublishedFileService_GetDetails({"database": {}}, ["111"])
        assert result is not None
        _, _, cached = result
        assert len(cached) == 1
        assert cached[0]["publishedfileid"] == "111"

    def test_returns_none_without_api(self, dq: DynamicQuery) -> None:
        dq.api = None
        result = dq.IPublishedFileService_GetDetails({"database": {}}, [])
        assert result is None


class TestCreateSteamDbCaching:
    """create_steam_db uses cached re-processing instead of a redundant full re-query."""

    def _setup_api(
        self, dq: DynamicQuery, mods: dict[str, dict[str, Any]]
    ) -> list[list[str]]:
        """Configure mock API and return a list that tracks which pfids were queried."""
        queried_batches: list[list[str]] = []

        def mock_call(**kwargs: Any) -> dict[str, Any]:
            # __initialize_webapi calls GetServerInfo first
            if kwargs.get("method_path") == "ISteamWebAPIUtil.GetServerInfo":
                return {"servertime": 1}
            pfids = kwargs.get("publishedfileids", [])
            queried_batches.append(list(pfids))
            details = [mods[p] for p in pfids if p in mods]
            return {"response": {"publishedfiledetails": details}}

        dq.api.call.side_effect = mock_call  # type: ignore[attr-defined]
        return queried_batches

    def test_no_redundant_full_requery(self, dq: DynamicQuery) -> None:
        """A depends on C (missing). Should query [A,B] then [C], not [A,B] again."""
        mods = {
            "A": _make_mod("A", "Mod A", children=["C"]),
            "B": _make_mod("B", "Mod B"),
            "C": _make_mod("C", "Mod C"),
        }
        batches = self._setup_api(dq, mods)
        dq.create_steam_db(
            database=_make_database("A", "B"), publishedfileids=["A", "B"]
        )

        all_queried = [pfid for batch in batches for pfid in batch]
        assert all_queried == ["A", "B", "C"]
        assert "C" in dq.database["database"]["A"]["dependencies"]
        assert dq.database["database"]["A"]["dependencies"]["C"][0] == "Mod C"

    # jscpd:ignore-start
    def test_no_missing_children_single_query(self, dq: DynamicQuery) -> None:
        """When all deps are in the initial set, only 1 round of API calls."""
        mods = {
            "A": _make_mod("A", "Mod A", children=["B"]),
            "B": _make_mod("B", "Mod B"),
        }
        batches = self._setup_api(dq, mods)
        dq.create_steam_db(
            database=_make_database("A", "B"), publishedfileids=["A", "B"]
        )

        all_queried = [pfid for batch in batches for pfid in batch]
        assert all_queried == ["A", "B"]
        assert "B" in dq.database["database"]["A"]["dependencies"]

    # jscpd:ignore-end

    def test_cached_replay_resolves_unknown_names(self, dq: DynamicQuery) -> None:
        """
        If A is processed before B in round 1, A's dep on B gets "UNKNOWN".
        The cached replay after round 2 should fix this since B now has steamName.
        """
        mods = {
            "A": _make_mod("A", "Mod A", children=["B"]),
            "B": _make_mod("B", "Mod B", children=["C"]),
            "C": _make_mod("C", "Mod C"),
        }
        batches = self._setup_api(dq, mods)

        # B is in the initial set but A depends on it. The cached replay
        # re-processes A after B has steamName populated.
        # C is missing, triggering round 2 + replay.
        dq.create_steam_db(
            database=_make_database("A", "B"), publishedfileids=["A", "B"]
        )

        all_queried = [pfid for batch in batches for pfid in batch]
        assert all_queried == ["A", "B", "C"]
        assert dq.database["database"]["A"]["dependencies"]["B"][0] == "Mod B"
        assert dq.database["database"]["B"]["dependencies"]["C"][0] == "Mod C"

    def test_appid_deps_receives_all_pfids(self, dq: DynamicQuery) -> None:
        """ISteamUGC_GetAppDependencies should receive initial + missing pfids."""
        mods = {
            "A": _make_mod("A", "Mod A", children=["C"]),
            "C": _make_mod("C", "Mod C"),
        }
        self._setup_api(dq, mods)
        dq.get_appid_deps = True

        with patch.object(dq, "ISteamUGC_GetAppDependencies") as mock_appid:
            dq.create_steam_db(database=_make_database("A"), publishedfileids=["A"])
            mock_appid.assert_called_once()
            pfids = mock_appid.call_args[1]["publishedfileids"]
            assert "A" in pfids
            assert "C" in pfids
