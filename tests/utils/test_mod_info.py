from unittest.mock import MagicMock, patch

import pytest

from app.utils.mod_info import DATABASE, LOCAL, STEAM, STEAM_CMD, UNKNOWN, ModInfo


class TestModInfoInit:
    def test_valid_construction(self) -> None:
        info = ModInfo(
            key="abc",
            name="Test Mod",
            authors="Author",
            packageid="test.mod",
            published_file_id="12345",
            supported_versions="1.4",
            source=LOCAL,
            path="/mods/test",
            downloaded_time_raw=1000000.0,
            updated_time_raw=2000000.0,
            workshop_url="",
            type="Original",
            installed_status="Installed",
        )
        assert info.name == "Test Mod"
        assert info.packageid == "test.mod"

    def test_empty_packageid_raises(self) -> None:
        with pytest.raises(ValueError, match="packageid cannot be empty"):
            ModInfo(
                key="abc",
                name="Test",
                authors="",
                packageid="",
                published_file_id="",
                supported_versions="",
                source="",
                path="",
                downloaded_time_raw=None,
                updated_time_raw=None,
                workshop_url="",
                type="",
                installed_status="",
            )

    def test_whitespace_packageid_raises(self) -> None:
        with pytest.raises(ValueError, match="packageid cannot be empty"):
            ModInfo(
                key="abc",
                name="Test",
                authors="",
                packageid="   ",
                published_file_id="",
                supported_versions="",
                source="",
                path="",
                downloaded_time_raw=None,
                updated_time_raw=None,
                workshop_url="",
                type="",
                installed_status="",
            )

    def test_empty_name_set_to_unknown(self) -> None:
        info = ModInfo(
            key="abc",
            name="",
            authors="",
            packageid="valid.id",
            published_file_id="",
            supported_versions="",
            source="",
            path="",
            downloaded_time_raw=None,
            updated_time_raw=None,
            workshop_url="",
            type="",
            installed_status="",
        )
        assert info.name == UNKNOWN


class TestFromMetadata:
    def test_basic_metadata(self) -> None:
        metadata = {
            "name": "Cool Mod",
            "authors": "Author1",
            "packageid": "cool.mod",
            "publishedfileid": "99999",
            "supportedversions": {"li": ["1.4", "1.5"]},
            "data_source": "workshop",
            "path": "/mods/cool",
        }
        info = ModInfo.from_metadata("key-1", metadata)
        assert info.name == "Cool Mod"
        assert info.packageid == "cool.mod"
        assert info.source == STEAM
        assert info.published_file_id == "99999"
        assert "1.4" in info.supported_versions
        assert "1.5" in info.supported_versions

    def test_steamcmd_source(self) -> None:
        metadata = {"name": "Mod", "packageid": "test.mod", "steamcmd": True}
        info = ModInfo.from_metadata("key", metadata)
        assert info.source == STEAM_CMD

    def test_local_source(self) -> None:
        metadata = {"name": "Mod", "packageid": "test.mod", "data_source": "local"}
        info = ModInfo.from_metadata("key", metadata)
        assert info.source == LOCAL

    def test_database_source_fallback(self) -> None:
        metadata = {"name": "Mod", "packageid": "test.mod"}
        info = ModInfo.from_metadata("key", metadata)
        assert info.source == DATABASE

    def test_missing_packageid_raises(self) -> None:
        metadata = {"name": "Mod", "packageid": ""}
        with pytest.raises(ValueError, match="Failed to create ModInfo"):
            ModInfo.from_metadata("key", metadata)

    def test_authors_as_list(self) -> None:
        metadata = {
            "name": "Mod",
            "packageid": "test.mod",
            "authors": ["Alice", "Bob"],
        }
        info = ModInfo.from_metadata("key", metadata)
        assert info.authors == "Alice, Bob"

    def test_fallback_name_from_steamname(self) -> None:
        metadata = {"steamName": "Steam Name", "packageid": "test.mod"}
        info = ModInfo.from_metadata("key", metadata)
        assert info.name == "Steam Name"


class TestNormalizeVersion:
    def test_major_minor(self) -> None:
        assert ModInfo._normalize_version("1.4") == "1.4"

    def test_major_minor_patch_truncated(self) -> None:
        assert ModInfo._normalize_version("1.4.3") == "1.4"

    def test_single_part(self) -> None:
        assert ModInfo._normalize_version("1") == "1"

    def test_non_string_returns_str(self) -> None:
        assert ModInfo._normalize_version(42) == "42"  # type: ignore[arg-type]


class TestParseSupportedVersions:
    def test_dict_with_list(self) -> None:
        result = ModInfo._parse_supported_versions_static({"li": ["1.4", "1.3"]})
        assert result == "1.3, 1.4"

    def test_dict_with_single_string(self) -> None:
        result = ModInfo._parse_supported_versions_static({"li": "1.4"})
        assert result == "1.4"

    def test_list_input(self) -> None:
        result = ModInfo._parse_supported_versions_static(["1.4", "1.5"])
        assert result == "1.4, 1.5"

    def test_string_input(self) -> None:
        result = ModInfo._parse_supported_versions_static("1.4")
        assert result == "1.4"

    def test_none_returns_unknown(self) -> None:
        result = ModInfo._parse_supported_versions_static(None)
        assert result == UNKNOWN

    def test_deduplication(self) -> None:
        result = ModInfo._parse_supported_versions_static(["1.4", "1.4", "1.5"])
        assert result == "1.4, 1.5"

    def test_version_normalization_in_list(self) -> None:
        result = ModInfo._parse_supported_versions_static({"li": ["1.4.3", "1.5.1"]})
        assert result == "1.4, 1.5"


class TestGenerateWorkshopUrl:
    def test_valid_numeric_id(self) -> None:
        url = ModInfo._generate_workshop_url("12345")
        assert url == "https://steamcommunity.com/sharedfiles/filedetails/?id=12345"

    def test_empty_id_returns_empty(self) -> None:
        assert ModInfo._generate_workshop_url("") == ""

    def test_non_numeric_id_returns_empty(self) -> None:
        assert ModInfo._generate_workshop_url("abc") == ""


class TestTimeProperties:
    @staticmethod
    def _make_info(
        downloaded: float | None = None,
        updated: float | None = None,
    ) -> ModInfo:
        return ModInfo(
            key="a",
            name="M",
            authors="",
            packageid="p.id",
            published_file_id="",
            supported_versions="",
            source="",
            path="",
            downloaded_time_raw=downloaded,
            updated_time_raw=updated,
            workshop_url="",
            type="",
            installed_status="",
        )

    @patch("app.utils.mod_info.format_time_display")
    def test_downloaded_time_with_value(self, mock_fmt: MagicMock) -> None:
        mock_fmt.return_value = ("2024-01-01 00:00:00 | 1 day ago", 1000)
        info = self._make_info(downloaded=1000.0)
        assert info.downloaded_time == "2024-01-01 00:00:00 | 1 day ago"

    def test_downloaded_time_none(self) -> None:
        info = self._make_info()
        assert info.downloaded_time == UNKNOWN

    def test_updated_on_workshop_none(self) -> None:
        info = self._make_info()
        assert info.updated_on_workshop == UNKNOWN
