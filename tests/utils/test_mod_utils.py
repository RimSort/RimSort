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
        mod1 = _make_listed_mod(name="Mod One", mod_path="/path/to/mod1", pfid="123")
        mod2 = _make_listed_mod(name="Mod Two", mod_path="/path/to/mod2", pfid="456")
        mock.mods_metadata = {
            "/path/to/mod1": mod1,
            "/path/to/mod2": mod2,
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
    with patch("os.path.isdir") as isdir_mock:
        isdir_mock.side_effect = lambda path: path in ["/path/to/mod1", "/path/to/mod2"]
        paths = get_mod_paths(["/path/to/mod1", "/path/to/mod2", "/nonexistent"])
        assert "/path/to/mod1" in paths
        assert "/path/to/mod2" in paths
        assert len(paths) == 2


def test_get_mod_paths_with_nonexistent_path(
    metadata_controller_mock: MagicMock,
) -> None:
    with patch("os.path.isdir") as isdir_mock:
        isdir_mock.return_value = False
        paths = get_mod_paths(["/path/to/mod1"])
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
    ) -> None:
        """Configure aux DB mock to return timestamps for a given path."""
        aux_entry = MagicMock()
        aux_entry.acf_time_updated = acf_time_updated
        aux_entry.external_time_updated = external_time_updated
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
