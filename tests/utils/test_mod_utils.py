"""Tests for app.utils.mod_utils — mod utility functions."""

from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    CaseInsensitiveStr,
    ListedMod,
    ModType,
    SteamDbEntry,
    SteamDbSchema,
)
from app.utils.mod_utils import (
    filter_eligible_mods_for_update,
    get_mod_name_from_pfid,
    get_mod_paths,
)


def _make_listed_mod(
    name: str = "Test Mod",
    mod_path: str | None = None,
    mod_type: ModType = ModType.STEAM_WORKSHOP,
    pfid: str | None = "12345",
) -> ListedMod:
    """Helper to build a ListedMod for testing."""
    mod = ListedMod(name=name, _mod_type=mod_type)
    if mod_path is not None:
        object.__setattr__(mod, "_mod_path", Path(mod_path))
    if pfid is not None:
        # Override the cached property
        mod.__dict__["published_file_id"] = pfid
    return mod


def _make_about_xml_mod(
    name: str = "Test Mod",
    package_id: str = "test.mod",
    mod_path: str | None = None,
    mod_type: ModType = ModType.STEAM_WORKSHOP,
    pfid: str | None = "12345",
    authors: list[str] | None = None,
    mod_version: str = "",
) -> AboutXmlMod:
    """Helper to build an AboutXmlMod for testing."""
    mod = AboutXmlMod(
        name=name,
        package_id=CaseInsensitiveStr(package_id),
        _mod_type=mod_type,
        authors=authors or [],
        mod_version=mod_version,
    )
    if mod_path is not None:
        object.__setattr__(mod, "_mod_path", Path(mod_path))
    if pfid is not None:
        mod.__dict__["published_file_id"] = pfid
    return mod


@pytest.fixture
def metadata_controller_mock() -> Generator[MagicMock, None, None]:
    with patch("app.utils.mod_utils.MetadataController.instance") as mock_instance:
        mock = MagicMock()
        p1 = str(Path("/path/to/mod1"))
        p2 = str(Path("/path/to/mod2"))
        mod1 = _make_listed_mod(name="Mod One", mod_path=p1, pfid="123")
        mod2 = _make_listed_mod(name="Mod Two", mod_path=p2, pfid="456")
        mock.mods_metadata = {
            p1: mod1,
            p2: mod2,
        }
        # Set up steam_db mock
        steam_db = MagicMock(spec=SteamDbSchema)
        entry = SteamDbEntry(steamName="External Mod", name="External Mod")
        steam_db.database = {"789": entry}
        mock.steam_db = steam_db
        mock_instance.return_value = mock
        yield mock


def test_get_mod_name_from_pfid_valid_internal(
    metadata_controller_mock: MagicMock,
) -> None:
    assert get_mod_name_from_pfid("123") == "Mod One"
    assert get_mod_name_from_pfid(123) == "Mod One"


def test_get_mod_name_from_pfid_valid_external(
    metadata_controller_mock: MagicMock,
) -> None:
    assert get_mod_name_from_pfid("789") == "External Mod"


def test_get_mod_name_from_pfid_invalid(
    metadata_controller_mock: MagicMock,
) -> None:
    assert get_mod_name_from_pfid("999") == "Invalid ID: 999"
    assert get_mod_name_from_pfid("abc") == "Invalid ID: abc"
    assert get_mod_name_from_pfid(None) == "Unknown Mod"


def test_get_mod_paths(metadata_controller_mock: MagicMock) -> None:
    p1 = str(Path("/path/to/mod1"))
    p2 = str(Path("/path/to/mod2"))
    with patch("os.path.isdir") as isdir_mock:
        isdir_mock.side_effect = lambda path: path in [p1, p2]
        paths = get_mod_paths([p1, p2, str(Path("/nonexistent"))])
        assert p1 in paths
        assert p2 in paths
        assert len(paths) == 2


def test_get_mod_paths_with_nonexistent_path(
    metadata_controller_mock: MagicMock,
) -> None:
    with patch("os.path.isdir") as isdir_mock:
        isdir_mock.return_value = False
        paths = get_mod_paths([str(Path("/path/to/mod1"))])
        assert paths == []


# --- filter_eligible_mods_for_update tests ---


def _make_update_mod(
    name: str = "Test Mod",
    pfid: str = "12345",
    mod_type: ModType = ModType.STEAM_WORKSHOP,
    mod_path: str = "/mods/test",
) -> ListedMod:
    """Helper to build a ListedMod for update eligibility testing."""
    mod = _make_listed_mod(name=name, mod_path=mod_path, mod_type=mod_type, pfid=pfid)
    return mod


class TestFilterEligibleModsForUpdate:
    """Tests for filter_eligible_mods_for_update."""

    @pytest.fixture(autouse=True)
    def _mock_controller(self) -> Generator[None, None, None]:
        """Mock MetadataController.instance() for all tests."""
        with patch("app.utils.mod_utils.MetadataController.instance") as mock_instance:
            mock = MagicMock()
            # Default: no aux DB entries
            mock.get_metadata_with_path.return_value = (None, None)
            mock_instance.return_value = mock
            self.mock_controller = mock
            yield

    def _setup_aux_timestamps(
        self,
        path: str,
        acf_time_updated: int = -1,
        external_time_updated: int = -1,
        acf_time_touched: int = -1,
    ) -> None:
        """Configure aux DB mock to return timestamps for a given path."""
        aux_entry = MagicMock()
        aux_entry.acf_time_updated = acf_time_updated
        aux_entry.external_time_updated = external_time_updated
        aux_entry.acf_time_touched = acf_time_touched
        self.mock_controller.get_metadata_with_path.side_effect = lambda p: (
            (MagicMock(), aux_entry) if p == path else (None, None)
        )

    def test_basic_eligible_mod(self) -> None:
        """A workshop mod where external > internal_time_touched is eligible."""
        mod = _make_update_mod(mod_path="/mods/test1")
        # Set internal time via mocked path mtime
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getmtime", return_value=1000.0),
        ):
            self._setup_aux_timestamps("/mods/test1", external_time_updated=2000)
            result = filter_eligible_mods_for_update({"/mods/test1": mod})
        assert len(result) == 1
        assert result[0]["name"] == "Test Mod"

    def test_non_workshop_mod_skipped(self) -> None:
        """Non-workshop mods are never eligible."""
        mod = _make_update_mod(mod_type=ModType.LOCAL, mod_path="/mods/local")
        result = filter_eligible_mods_for_update({"/mods/local": mod})
        assert len(result) == 0

    def test_empty_metadata(self) -> None:
        """Empty metadata dict returns empty list."""
        result = filter_eligible_mods_for_update({})
        assert result == []

    def test_steamcmd_mod_eligible(self) -> None:
        """SteamCMD mods are treated like workshop mods."""
        mod = _make_update_mod(mod_type=ModType.STEAM_CMD, mod_path="/mods/steamcmd")
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getmtime", return_value=1000.0),
        ):
            self._setup_aux_timestamps("/mods/steamcmd", external_time_updated=2000)
            result = filter_eligible_mods_for_update({"/mods/steamcmd": mod})
        assert len(result) == 1

    def test_fallback_to_acf_time_updated(self) -> None:
        """When mod path doesn't exist (internal_time_touched=-1), falls back to acf_time_updated."""
        mod = _make_update_mod(mod_path="/mods/nopath")
        # mod path doesn't exist => internal_time_touched returns -1
        with patch("os.path.exists", return_value=False):
            self._setup_aux_timestamps(
                "/mods/nopath",
                acf_time_updated=1000,
                external_time_updated=2000,
            )
            result = filter_eligible_mods_for_update({"/mods/nopath": mod})
        assert len(result) == 1
        assert result[0]["name"] == "Test Mod"

    def test_internal_time_touched_preferred_over_acf_fallback(self) -> None:
        """When file mtime is more recent than acf_time_updated, it is used."""
        mod = _make_update_mod(mod_path="/mods/test2")
        # internal_time_touched=3000 > external=2000 => not eligible
        # acf_time_updated=1000 < external=2000 => would be eligible if used
        # max(3000, 1000) = 3000, so uses file mtime
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getmtime", return_value=3000.0),
        ):
            self._setup_aux_timestamps(
                "/mods/test2",
                acf_time_updated=1000,
                external_time_updated=2000,
            )
            result = filter_eligible_mods_for_update({"/mods/test2": mod})
        assert len(result) == 0, (
            "Should use the more recent of internal_time_touched and acf_time_updated"
        )

    def test_acf_time_updated_preferred_when_more_recent_than_file_mtime(
        self,
    ) -> None:
        """acf_time_updated is used when it is more recent than file mtime."""
        mod = _make_update_mod(mod_path="/mods/test3")
        # internal_time_touched=1000 < external=2000 => would be eligible
        # acf_time_updated=3000 > external=2000 => not eligible (up-to-date)
        # max(1000, 3000) = 3000, so uses acf_time_updated
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getmtime", return_value=1000.0),
        ):
            self._setup_aux_timestamps(
                "/mods/test3",
                acf_time_updated=3000,
                external_time_updated=2000,
            )
            result = filter_eligible_mods_for_update({"/mods/test3": mod})
        assert len(result) == 0, (
            "Should use acf_time_updated when it is more recent than file mtime"
        )

    def test_no_internal_timestamps_at_all(self) -> None:
        """Mods with no internal_time_touched and no acf_time_updated are included."""
        mod = _make_update_mod(mod_path="/mods/nots")
        with patch("os.path.exists", return_value=False):
            # No aux entry => no fallback either
            result = filter_eligible_mods_for_update({"/mods/nots": mod})
        assert len(result) == 1

    def test_up_to_date_mod_skipped(self) -> None:
        """Mods where external <= internal are skipped."""
        mod1 = _make_update_mod(name="Equal", pfid="111", mod_path="/mods/eq")
        mod2 = _make_update_mod(name="Older External", pfid="222", mod_path="/mods/old")
        with (
            patch("os.path.exists", return_value=True),
            patch(
                "os.path.getmtime",
                side_effect=lambda p: 2000.0 if p == Path("/mods/eq") else 3000.0,
            ),
        ):
            self._setup_aux_timestamps("/mods/eq", external_time_updated=2000)
            # For multi-path mocking, chain side_effect
            aux_eq = MagicMock()
            aux_eq.acf_time_updated = -1
            aux_eq.external_time_updated = 2000
            aux_eq.acf_time_touched = -1
            aux_old = MagicMock()
            aux_old.acf_time_updated = -1
            aux_old.external_time_updated = 1000
            aux_old.acf_time_touched = -1

            def multi_aux(p: str) -> tuple[MagicMock | None, MagicMock | None]:
                if p == "/mods/eq":
                    return (MagicMock(), aux_eq)
                if p == "/mods/old":
                    return (MagicMock(), aux_old)
                return (None, None)

            self.mock_controller.get_metadata_with_path.side_effect = multi_aux
            result = filter_eligible_mods_for_update(
                {
                    "/mods/eq": mod1,
                    "/mods/old": mod2,
                }
            )
        assert len(result) == 0

    def test_no_external_time(self) -> None:
        """Mods with no external_time_updated in aux DB are included."""
        mod = _make_update_mod(mod_path="/mods/noext")
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getmtime", return_value=1000.0),
        ):
            # No aux entry => no external time
            result = filter_eligible_mods_for_update({"/mods/noext": mod})
        assert len(result) == 1

    def test_zero_external_time_treated_as_missing(self) -> None:
        """external_time_updated=0 causes the mod to be included (needs API fetch)."""
        mod = _make_update_mod(mod_path="/mods/zeroext")
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getmtime", return_value=1000.0),
        ):
            self._setup_aux_timestamps("/mods/zeroext", external_time_updated=0)
            result = filter_eligible_mods_for_update({"/mods/zeroext": mod})
        assert len(result) == 1

    def test_mixed_mods(self) -> None:
        """Only workshop/steamcmd mods with updates are returned from a mixed set."""
        eligible_ws = _make_update_mod(
            name="Eligible Workshop", pfid="111", mod_path="/mods/ws"
        )
        local_mod = _make_update_mod(
            name="Local Mod",
            pfid="222",
            mod_type=ModType.LOCAL,
            mod_path="/mods/local",
        )
        up_to_date = _make_update_mod(
            name="Up To Date Workshop", pfid="333", mod_path="/mods/utd"
        )
        eligible_cmd = _make_update_mod(
            name="Eligible SteamCMD",
            pfid="444",
            mod_type=ModType.STEAM_CMD,
            mod_path="/mods/cmd",
        )

        aux_ws = MagicMock()
        aux_ws.acf_time_updated = -1
        aux_ws.external_time_updated = 2000
        aux_ws.acf_time_touched = -1
        aux_utd = MagicMock()
        aux_utd.acf_time_updated = -1
        aux_utd.external_time_updated = 2000
        aux_utd.acf_time_touched = -1
        aux_cmd = MagicMock()
        aux_cmd.acf_time_updated = 500
        aux_cmd.external_time_updated = 2000
        aux_cmd.acf_time_touched = -1

        def multi_aux(p: str) -> tuple[MagicMock | None, MagicMock | None]:
            mapping: dict[str, MagicMock] = {
                "/mods/ws": aux_ws,
                "/mods/utd": aux_utd,
                "/mods/cmd": aux_cmd,
            }
            if p in mapping:
                return (MagicMock(), mapping[p])
            return (None, None)

        self.mock_controller.get_metadata_with_path.side_effect = multi_aux

        with (
            patch("os.path.exists", return_value=True),
            patch(
                "os.path.getmtime",
                side_effect=lambda p: 3000.0 if p == Path("/mods/utd") else 1000.0,
            ),
        ):
            result = filter_eligible_mods_for_update(
                {
                    "/mods/ws": eligible_ws,
                    "/mods/local": local_mod,
                    "/mods/utd": up_to_date,
                    "/mods/cmd": eligible_cmd,
                }
            )
        names = {m["name"] for m in result}
        assert names == {"Eligible Workshop", "Eligible SteamCMD"}
