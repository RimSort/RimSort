import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.version_data_service import RimWorldVersion, VersionDataService

SAMPLE_VERSIONS_DATA = {
    "win64": [
        {
            "manifest_id": "abc123",
            "version": "1.5.0",
            "status": "release",
            "dlcs": {"royalty": "def456", "ideology": "ghi789"},
        },
        {
            "manifest_id": "xyz789",
            "version": "1.4.0",
            "status": "release",
            "dlcs": {"royalty": "old123"},
        },
    ],
    "linux": [
        {
            "manifest_id": "lin001",
            "version": "1.5.0",
            "status": "release",
            "dlcs": {},
        },
    ],
}

SAMPLE_DEPOTS_DATA = {
    "base_game": {"win64": 294100, "linux": 294101},
    "royalty": {"win64": 294110},
}

SAMPLE_FULL_DATA = {
    "depots": SAMPLE_DEPOTS_DATA,
    "versions": SAMPLE_VERSIONS_DATA,
}


@pytest.fixture
def versions_json_file(tmp_path: Path) -> Path:
    path = tmp_path / "rimworld_versions.json"
    path.write_text(json.dumps(SAMPLE_FULL_DATA), encoding="utf-8")
    return path


def make_service(versions_path: Path) -> VersionDataService:
    """Helper to create a VersionDataService with a mock settings pointing to a given path."""
    mock_settings = MagicMock()
    mock_settings.external_rimworld_versions_file_path = str(versions_path)
    with patch(
        "app.services.version_data_service.Settings", return_value=mock_settings
    ):
        return VersionDataService()


class TestRimWorldVersionDataclass:
    def test_fields(self) -> None:
        v = RimWorldVersion(
            manifest_id="abc",
            version_string="1.5",
            status="release",
            dlcs={"royalty": "def"},
        )
        assert v.manifest_id == "abc"
        assert v.version_string == "1.5"
        assert v.status == "release"
        assert v.dlcs == {"royalty": "def"}


class TestVersionDataServiceInit:
    def test_loads_data_from_existing_file(self, versions_json_file: Path) -> None:
        service = make_service(versions_json_file)
        assert service._versions_data == SAMPLE_VERSIONS_DATA
        assert service._depots_data == SAMPLE_DEPOTS_DATA

    def test_handles_missing_file_gracefully(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.json"
        service = make_service(missing)
        assert service._versions_data == {}
        assert service._depots_data == {}

    def test_handles_invalid_json_gracefully(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{invalid json", encoding="utf-8")
        service = make_service(bad)
        assert service._versions_data == {}
        assert service._depots_data == {}

    def test_handles_missing_keys_in_json(self, tmp_path: Path) -> None:
        path = tmp_path / "minimal.json"
        path.write_text(json.dumps({}), encoding="utf-8")
        service = make_service(path)
        assert service._versions_data == {}
        assert service._depots_data == {}


class TestGetAvailableVersions:
    def test_returns_parsed_versions_for_platform(
        self, versions_json_file: Path
    ) -> None:
        service = make_service(versions_json_file)
        versions = service.get_available_versions("win64")
        assert len(versions) == 2
        assert all(isinstance(v, RimWorldVersion) for v in versions)

    def test_returns_newest_first(self, versions_json_file: Path) -> None:
        service = make_service(versions_json_file)
        versions = service.get_available_versions("win64")
        assert versions[0].version_string == "1.5.0"
        assert versions[1].version_string == "1.4.0"

    def test_includes_dlc_data(self, versions_json_file: Path) -> None:
        service = make_service(versions_json_file)
        versions = service.get_available_versions("win64")
        assert versions[0].dlcs == {"royalty": "def456", "ideology": "ghi789"}

    def test_returns_empty_list_for_unknown_platform(
        self, versions_json_file: Path
    ) -> None:
        service = make_service(versions_json_file)
        versions = service.get_available_versions("mac")
        assert versions == []

    def test_handles_missing_optional_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "minimal_versions.json"
        path.write_text(
            json.dumps({"versions": {"win64": [{"manifest_id": "abc"}]}}),
            encoding="utf-8",
        )
        service = make_service(path)
        versions = service.get_available_versions("win64")
        assert len(versions) == 1
        v = versions[0]
        assert v.version_string == "Unknown"
        assert v.status == "Unknown"
        assert v.dlcs == {}

    def test_returns_empty_when_no_data_loaded(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.json"
        service = make_service(missing)
        assert service.get_available_versions("win64") == []


class TestGetDepotId:
    def test_returns_depot_id_for_valid_item_and_platform(
        self, versions_json_file: Path
    ) -> None:
        service = make_service(versions_json_file)
        assert service.get_depot_id("base_game", "win64") == 294100

    def test_returns_none_for_missing_item(self, versions_json_file: Path) -> None:
        service = make_service(versions_json_file)
        assert service.get_depot_id("nonexistent", "win64") is None

    def test_returns_none_for_missing_platform(self, versions_json_file: Path) -> None:
        service = make_service(versions_json_file)
        assert service.get_depot_id("base_game", "mac") is None

    def test_returns_none_when_no_depots_loaded(self, tmp_path: Path) -> None:
        path = tmp_path / "no_depots.json"
        path.write_text(json.dumps({"versions": {}}), encoding="utf-8")
        service = make_service(path)
        assert service.get_depot_id("base_game", "win64") is None


class TestGetPlatformKey:
    @patch("platform.architecture")
    @patch("platform.system")
    def test_win64(self, mock_system: MagicMock, mock_arch: MagicMock) -> None:
        mock_system.return_value = "Windows"
        mock_arch.return_value = ("64bit", "WindowsPE")
        service = make_service(Path("/fake/path.json"))
        assert service.get_platform_key() == "win64"

    @patch("platform.architecture")
    @patch("platform.system")
    def test_win32(self, mock_system: MagicMock, mock_arch: MagicMock) -> None:
        mock_system.return_value = "Windows"
        mock_arch.return_value = ("32bit", "WindowsPE")
        service = make_service(Path("/fake/path.json"))
        assert service.get_platform_key() == "win32"

    @patch("platform.system")
    def test_mac(self, mock_system: MagicMock) -> None:
        mock_system.return_value = "Darwin"
        service = make_service(Path("/fake/path.json"))
        assert service.get_platform_key() == "mac"

    @patch("platform.system")
    def test_linux(self, mock_system: MagicMock) -> None:
        mock_system.return_value = "Linux"
        service = make_service(Path("/fake/path.json"))
        assert service.get_platform_key() == "linux"

    @patch("platform.system")
    def test_unknown_os_defaults_to_win64(self, mock_system: MagicMock) -> None:
        mock_system.return_value = "Java"
        service = make_service(Path("/fake/path.json"))
        assert service.get_platform_key() == "win64"
