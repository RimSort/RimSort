"""Tests for app.sort.mod_sorting — inactive mods list sorting helpers."""

from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.sort.mod_sorting import (
    DEFAULT_REVERSE_FLAGS,
    ModsPanelSortKey,
    _build_sort_key_map,
    get_cached_metadata_for_batch,
    get_dir_size,
    get_mod_metadata,
    sort_uuids,
    uuid_no_key,
    uuid_to_author,
    uuid_to_filesystem_modified_time,
    uuid_to_folder_size,
    uuid_to_mod_color,
    uuid_to_mod_name,
    uuid_to_mod_tags,
    uuid_to_packageid,
    uuid_to_version,
)


@pytest.fixture(autouse=True)
def _clear_folder_size_cache() -> Generator[None, None, None]:
    """Clear the module-level folder size cache between tests."""
    yield
    from app.sort.mod_sorting import _FOLDER_SIZE_CACHE

    _FOLDER_SIZE_CACHE.clear()


# ---------------------------------------------------------------------------
# uuid_no_key — identity function
# ---------------------------------------------------------------------------


class TestUuidNoKey:
    def test_returns_uuid_unchanged(self) -> None:
        assert uuid_no_key("some-uuid-123") == "some-uuid-123"

    def test_empty_string(self) -> None:
        assert uuid_no_key("") == ""


# ---------------------------------------------------------------------------
# uuid_to_mod_name
# ---------------------------------------------------------------------------


class TestUuidToModName:
    def test_cached_metadata_with_name(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"name": "MyMod"}}
        assert uuid_to_mod_name("uuid1", cached) == "mymod"

    def test_cached_metadata_missing_uuid(self) -> None:
        cached: dict[str, Any] = {}
        assert uuid_to_mod_name("missing", cached) == "name error in mod about.xml"

    def test_cached_metadata_name_is_none(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"name": None}}
        assert uuid_to_mod_name("uuid1", cached) == "name error in mod about.xml"

    def test_cached_metadata_name_is_non_string(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"name": 42}}
        assert uuid_to_mod_name("uuid1", cached) == "name error in mod about.xml"

    def test_uncached_path(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid1": {"name": "TestMod"},
        }
        assert uuid_to_mod_name("uuid1") == "testmod"

    def test_name_preserves_lowercase(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"name": "ALLCAPS"}}
        assert uuid_to_mod_name("uuid1", cached) == "allcaps"

    def test_metadata_is_none(self) -> None:
        cached: dict[str, Any] = {"uuid1": None}
        assert uuid_to_mod_name("uuid1", cached) == "name error in mod about.xml"


# ---------------------------------------------------------------------------
# uuid_to_packageid
# ---------------------------------------------------------------------------


class TestUuidToPackageid:
    def test_cached_with_packageid(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"packageid": "author.ModName"}}
        assert uuid_to_packageid("uuid1", cached) == "author.modname"

    def test_cached_missing_uuid(self) -> None:
        cached: dict[str, Any] = {}
        assert uuid_to_packageid("missing", cached) == ""

    def test_packageid_is_non_string(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"packageid": 123}}
        assert uuid_to_packageid("uuid1", cached) == ""

    def test_packageid_is_none(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"packageid": None}}
        assert uuid_to_packageid("uuid1", cached) == ""

    def test_uncached_path(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid1": {"packageid": "Author.Mod"},
        }
        assert uuid_to_packageid("uuid1") == "author.mod"


# ---------------------------------------------------------------------------
# uuid_to_version
# ---------------------------------------------------------------------------


class TestUuidToVersion:
    def test_cached_with_version(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"modversion": "1.2.3"}}
        assert uuid_to_version("uuid1", cached) == "1.2.3"

    def test_cached_missing_uuid(self) -> None:
        cached: dict[str, Any] = {}
        assert uuid_to_version("missing", cached) == ""

    def test_version_is_non_string(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"modversion": 100}}
        assert uuid_to_version("uuid1", cached) == ""

    def test_uncached_path(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid1": {"modversion": "2.0.0-BETA"},
        }
        assert uuid_to_version("uuid1") == "2.0.0-beta"


# ---------------------------------------------------------------------------
# uuid_to_mod_color
# ---------------------------------------------------------------------------


class TestUuidToModColor:
    def test_cached_with_color_hex(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"color_hex": "#FF00AA"}}
        assert uuid_to_mod_color("uuid1", cached) == "#ff00aa"

    def test_cached_missing_uuid(self) -> None:
        cached: dict[str, Any] = {}
        assert uuid_to_mod_color("missing", cached) == ""

    def test_color_hex_is_non_string(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"color_hex": 0xFF00AA}}
        assert uuid_to_mod_color("uuid1", cached) == ""

    def test_uncached_path(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid1": {"color_hex": "#AABBCC"},
        }
        assert uuid_to_mod_color("uuid1") == "#aabbcc"


# ---------------------------------------------------------------------------
# uuid_to_author — complex multi-format extractor
# ---------------------------------------------------------------------------


class TestUuidToAuthor:
    def test_dict_li_list(self) -> None:
        """{'li': ['Author1', 'Author2']} → first author lowercased."""
        cached: dict[str, Any] = {"uuid1": {"authors": {"li": ["Author1", "Author2"]}}}
        assert uuid_to_author("uuid1", cached) == "author1"

    def test_dict_li_string(self) -> None:
        """{'li': 'SingleAuthor'} → lowercased."""
        cached: dict[str, Any] = {"uuid1": {"authors": {"li": "SingleAuthor"}}}
        assert uuid_to_author("uuid1", cached) == "singleauthor"

    def test_list_format(self) -> None:
        """['Author1', 'Author2'] → first author lowercased."""
        cached: dict[str, Any] = {"uuid1": {"authors": ["Author1", "Author2"]}}
        assert uuid_to_author("uuid1", cached) == "author1"

    def test_string_format(self) -> None:
        """'JustAString' → lowercased."""
        cached: dict[str, Any] = {"uuid1": {"authors": "JustAString"}}
        assert uuid_to_author("uuid1", cached) == "justastring"

    def test_none_authors(self) -> None:
        """None → empty string."""
        cached: dict[str, Any] = {"uuid1": {"authors": None}}
        assert uuid_to_author("uuid1", cached) == ""

    def test_missing_authors_key(self) -> None:
        """No 'authors' key at all → empty string."""
        cached: dict[str, Any] = {"uuid1": {"name": "SomeMod"}}
        assert uuid_to_author("uuid1", cached) == ""

    def test_empty_list(self) -> None:
        """[] → empty string."""
        cached: dict[str, Any] = {"uuid1": {"authors": []}}
        assert uuid_to_author("uuid1", cached) == ""

    def test_empty_dict(self) -> None:
        """{} → empty string (no 'li' key)."""
        cached: dict[str, Any] = {"uuid1": {"authors": {}}}
        assert uuid_to_author("uuid1", cached) == ""

    def test_dict_li_empty_list(self) -> None:
        """{'li': []} → empty string."""
        cached: dict[str, Any] = {"uuid1": {"authors": {"li": []}}}
        assert uuid_to_author("uuid1", cached) == ""

    def test_missing_uuid(self) -> None:
        cached: dict[str, Any] = {}
        assert uuid_to_author("missing", cached) == ""

    def test_metadata_is_none(self) -> None:
        cached: dict[str, Any] = {"uuid1": None}
        assert uuid_to_author("uuid1", cached) == ""

    def test_uncached_path(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid1": {"authors": "UncachedAuthor"},
        }
        assert uuid_to_author("uuid1") == "uncachedauthor"


# ---------------------------------------------------------------------------
# uuid_to_filesystem_modified_time
# ---------------------------------------------------------------------------


class TestUuidToFilesystemModifiedTime:
    def test_path_exists(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"path": "/mods/mymod", "name": "MyMod"}}
        with (
            patch("app.sort.mod_sorting.os.path.exists", return_value=True),
            patch("app.sort.mod_sorting.os.path.getmtime", return_value=1700000000.5),
        ):
            result = uuid_to_filesystem_modified_time("uuid1", cached)
        assert result == 1700000000

    def test_path_does_not_exist(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"path": "/mods/gone", "name": "Gone"}}
        with patch("app.sort.mod_sorting.os.path.exists", return_value=False):
            result = uuid_to_filesystem_modified_time("uuid1", cached)
        assert result == 0

    def test_no_metadata(self) -> None:
        cached: dict[str, Any] = {}
        assert uuid_to_filesystem_modified_time("missing", cached) == 0

    def test_path_is_none(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"path": None}}
        assert uuid_to_filesystem_modified_time("uuid1", cached) == 0

    def test_uncached_path(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid1": {"path": "/mods/test", "name": "Test"},
        }
        with (
            patch("app.sort.mod_sorting.os.path.exists", return_value=True),
            patch("app.sort.mod_sorting.os.path.getmtime", return_value=1600000000.0),
        ):
            result = uuid_to_filesystem_modified_time("uuid1")
        assert result == 1600000000


# ---------------------------------------------------------------------------
# uuid_to_folder_size
# ---------------------------------------------------------------------------


class TestUuidToFolderSize:
    def test_directory_exists(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"path": "/mods/mymod"}}
        with (
            patch("app.sort.mod_sorting.os.path.isdir", return_value=True),
            patch("app.sort.mod_sorting.os.path.getmtime", return_value=12345.0),
            patch("app.sort.mod_sorting.get_dir_size", return_value=4096),
        ):
            result = uuid_to_folder_size("uuid1", cached)
        assert result == 4096

    def test_path_not_a_directory(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"path": "/mods/file.txt"}}
        with patch("app.sort.mod_sorting.os.path.isdir", return_value=False):
            result = uuid_to_folder_size("uuid1", cached)
        assert result == 0

    def test_no_metadata(self) -> None:
        cached: dict[str, Any] = {}
        assert uuid_to_folder_size("missing", cached) == 0

    def test_path_is_none(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"path": None}}
        assert uuid_to_folder_size("uuid1", cached) == 0

    def test_cache_hit_same_mtime(self) -> None:
        """Second call with same mtime returns cached value without calling get_dir_size."""
        cached: dict[str, Any] = {"uuid1": {"path": "/mods/mymod"}}
        with (
            patch("app.sort.mod_sorting.os.path.isdir", return_value=True),
            patch("app.sort.mod_sorting.os.path.getmtime", return_value=12345.0),
            patch("app.sort.mod_sorting.get_dir_size", return_value=8192) as mock_size,
        ):
            first = uuid_to_folder_size("uuid1", cached)
            second = uuid_to_folder_size("uuid1", cached)

        assert first == 8192
        assert second == 8192
        # get_dir_size should only be called once (cache hit on second call)
        mock_size.assert_called_once()

    def test_cache_miss_different_mtime(self) -> None:
        """Different mtime forces recalculation."""
        from app.sort.mod_sorting import _FOLDER_SIZE_CACHE

        # Pre-populate cache with old mtime
        _FOLDER_SIZE_CACHE["/mods/mymod"] = (10000, 1024)

        cached: dict[str, Any] = {"uuid1": {"path": "/mods/mymod"}}
        with (
            patch("app.sort.mod_sorting.os.path.isdir", return_value=True),
            patch(
                "app.sort.mod_sorting.os.path.getmtime", return_value=99999.0
            ),  # different mtime
            patch("app.sort.mod_sorting.get_dir_size", return_value=2048) as mock_size,
        ):
            result = uuid_to_folder_size("uuid1", cached)

        assert result == 2048
        mock_size.assert_called_once_with("/mods/mymod")

    def test_oserror_on_getmtime(self) -> None:
        """OSError during getmtime returns 0."""
        cached: dict[str, Any] = {"uuid1": {"path": "/mods/mymod"}}
        with (
            patch("app.sort.mod_sorting.os.path.isdir", return_value=True),
            patch(
                "app.sort.mod_sorting.os.path.getmtime", side_effect=OSError("denied")
            ),
        ):
            result = uuid_to_folder_size("uuid1", cached)
        assert result == 0

    def test_metadata_is_none(self) -> None:
        cached: dict[str, Any] = {"uuid1": None}
        assert uuid_to_folder_size("uuid1", cached) == 0


# ---------------------------------------------------------------------------
# get_dir_size — real filesystem via tmp_path
# ---------------------------------------------------------------------------


class TestGetDirSize:
    def test_empty_directory(self, tmp_path: Path) -> None:
        assert get_dir_size(str(tmp_path)) == 0

    def test_single_file(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_bytes(b"hello")  # 5 bytes
        assert get_dir_size(str(tmp_path)) == 5

    def test_multiple_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_bytes(b"aaa")  # 3
        (tmp_path / "b.txt").write_bytes(b"bb")  # 2
        assert get_dir_size(str(tmp_path)) == 5

    def test_nested_directories(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "top.txt").write_bytes(b"top")  # 3
        (sub / "nested.txt").write_bytes(b"nested")  # 6
        assert get_dir_size(str(tmp_path)) == 9

    def test_deeply_nested(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.txt").write_bytes(b"deep")  # 4
        assert get_dir_size(str(tmp_path)) == 4

    def test_oserror_on_inaccessible_subdir(self, tmp_path: Path) -> None:
        """OSError on a subdirectory is silently skipped."""
        (tmp_path / "file.txt").write_bytes(b"ok")  # 2
        # Patch scanpath to raise OSError for a specific subdirectory
        with patch(
            "app.sort.mod_sorting.scanpath", side_effect=OSError("permission denied")
        ):
            # OSError is caught, returns 0
            result = get_dir_size(str(tmp_path))
        assert result == 0


# ---------------------------------------------------------------------------
# uuid_to_mod_tags
# ---------------------------------------------------------------------------


class TestUuidToModTags:
    def test_no_settings_controller(self) -> None:
        assert uuid_to_mod_tags("uuid1", settings_controller=None) == ""

    def test_normal_tags(self) -> None:
        mock_sc = MagicMock()
        with patch(
            "app.sort.mod_sorting.auxdb_get_mod_tags",
            return_value=["Zebra", "Alpha", "Beta"],
        ):
            result = uuid_to_mod_tags("uuid1", settings_controller=mock_sc)
        assert result == "alpha, beta, zebra"

    def test_empty_tags(self) -> None:
        mock_sc = MagicMock()
        with patch("app.sort.mod_sorting.auxdb_get_mod_tags", return_value=[]):
            result = uuid_to_mod_tags("uuid1", settings_controller=mock_sc)
        assert result == ""

    def test_exception_returns_empty(self) -> None:
        mock_sc = MagicMock()
        with patch(
            "app.sort.mod_sorting.auxdb_get_mod_tags",
            side_effect=RuntimeError("db error"),
        ):
            result = uuid_to_mod_tags("uuid1", settings_controller=mock_sc)
        assert result == ""

    def test_single_tag(self) -> None:
        mock_sc = MagicMock()
        with patch("app.sort.mod_sorting.auxdb_get_mod_tags", return_value=["OnlyTag"]):
            result = uuid_to_mod_tags("uuid1", settings_controller=mock_sc)
        assert result == "onlytag"


# ---------------------------------------------------------------------------
# get_mod_metadata
# ---------------------------------------------------------------------------


class TestGetModMetadata:
    def test_uuid_exists(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid1": {"name": "TestMod"},
        }
        result = get_mod_metadata("uuid1")
        assert result == {"name": "TestMod"}

    def test_uuid_missing(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {}
        result = get_mod_metadata("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# get_cached_metadata_for_batch
# ---------------------------------------------------------------------------


class TestGetCachedMetadataForBatch:
    def test_basic_batch_fetch(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid1": {"name": "Mod1"},
            "uuid2": {"name": "Mod2"},
        }
        result = get_cached_metadata_for_batch(["uuid1", "uuid2"])
        assert result["uuid1"] == {"name": "Mod1"}
        assert result["uuid2"] == {"name": "Mod2"}

    def test_missing_uuids_map_to_none(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid1": {"name": "Mod1"},
        }
        result = get_cached_metadata_for_batch(["uuid1", "uuid_missing"])
        assert result["uuid1"] == {"name": "Mod1"}
        assert result["uuid_missing"] is None

    def test_empty_uuids(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {}
        result = get_cached_metadata_for_batch([])
        assert result == {}


# ---------------------------------------------------------------------------
# _build_sort_key_map
# ---------------------------------------------------------------------------


class TestBuildSortKeyMap:
    def test_modname_key(self) -> None:
        cached: dict[str, Any] = {
            "uuid1": {"name": "Bravo"},
            "uuid2": {"name": "Alpha"},
        }
        result = _build_sort_key_map(
            ["uuid1", "uuid2"], ModsPanelSortKey.MODNAME, cached
        )
        assert result["uuid1"] == "bravo"
        assert result["uuid2"] == "alpha"

    def test_nokey_returns_uuid(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"name": "Irrelevant"}}
        result = _build_sort_key_map(["uuid1"], ModsPanelSortKey.NOKEY, cached)
        assert result["uuid1"] == "uuid1"

    def test_packageid_key(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"packageid": "Author.Pkg"}}
        result = _build_sort_key_map(["uuid1"], ModsPanelSortKey.PACKAGEID, cached)
        assert result["uuid1"] == "author.pkg"

    def test_version_key(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"modversion": "1.0.0"}}
        result = _build_sort_key_map(["uuid1"], ModsPanelSortKey.VERSION, cached)
        assert result["uuid1"] == "1.0.0"

    def test_author_key(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"authors": "SomeAuthor"}}
        result = _build_sort_key_map(["uuid1"], ModsPanelSortKey.AUTHOR, cached)
        assert result["uuid1"] == "someauthor"

    def test_mod_color_key(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"color_hex": "#ABC123"}}
        result = _build_sort_key_map(["uuid1"], ModsPanelSortKey.MOD_COLOR, cached)
        assert result["uuid1"] == "#abc123"

    def test_filesystem_modified_time_key(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"path": "/mods/m", "name": "M"}}
        with (
            patch("app.sort.mod_sorting.os.path.exists", return_value=True),
            patch("app.sort.mod_sorting.os.path.getmtime", return_value=1700000000.0),
        ):
            result = _build_sort_key_map(
                ["uuid1"], ModsPanelSortKey.FILESYSTEM_MODIFIED_TIME, cached
            )
        assert result["uuid1"] == 1700000000

    def test_folder_size_key(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"path": "/mods/m"}}
        with (
            patch("app.sort.mod_sorting.os.path.isdir", return_value=True),
            patch("app.sort.mod_sorting.os.path.getmtime", return_value=100.0),
            patch("app.sort.mod_sorting.get_dir_size", return_value=999),
        ):
            result = _build_sort_key_map(
                ["uuid1"], ModsPanelSortKey.FOLDER_SIZE, cached
            )
        assert result["uuid1"] == 999

    def test_mod_tags_key(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"name": "M"}}
        mock_sc = MagicMock()
        with patch(
            "app.sort.mod_sorting.auxdb_get_mod_tags",
            return_value=["Tag2", "Tag1"],
        ):
            result = _build_sort_key_map(
                ["uuid1"],
                ModsPanelSortKey.MOD_TAGS,
                cached,
                settings_controller=mock_sc,
            )
        assert result["uuid1"] == "tag1, tag2"


# ---------------------------------------------------------------------------
# sort_uuids — orchestration
# ---------------------------------------------------------------------------


class TestSortUuids:
    _three_mod_cached: dict[str, Any] = {
        "uuid_z": {"name": "Zebra"},
        "uuid_a": {"name": "Alpha"},
        "uuid_m": {"name": "Middle"},
    }
    _three_mod_uuids = ["uuid_z", "uuid_a", "uuid_m"]

    def test_sort_by_modname_ascending(self) -> None:
        result = sort_uuids(
            self._three_mod_uuids,
            ModsPanelSortKey.MODNAME,
            descending=False,
            cached_metadata=self._three_mod_cached,
        )
        assert result == ["uuid_a", "uuid_m", "uuid_z"]

    def test_sort_by_modname_descending(self) -> None:
        result = sort_uuids(
            self._three_mod_uuids,
            ModsPanelSortKey.MODNAME,
            descending=True,
            cached_metadata=self._three_mod_cached,
        )
        assert result == ["uuid_z", "uuid_m", "uuid_a"]

    def test_descending_none_uses_default_flags(self) -> None:
        """When descending=None, uses DEFAULT_REVERSE_FLAGS (all False = ascending)."""
        cached: dict[str, Any] = {
            "uuid_b": {"name": "Bravo"},
            "uuid_a": {"name": "Alpha"},
        }
        result = sort_uuids(
            ["uuid_b", "uuid_a"],
            ModsPanelSortKey.MODNAME,
            descending=None,
            cached_metadata=cached,
        )
        # Default is ascending (False)
        assert result == ["uuid_a", "uuid_b"]

    def test_sort_preserves_original_list(self) -> None:
        """sort_uuids returns a new list; original is not mutated."""
        cached: dict[str, Any] = {
            "uuid_b": {"name": "Bravo"},
            "uuid_a": {"name": "Alpha"},
        }
        original = ["uuid_b", "uuid_a"]
        result = sort_uuids(
            original,
            ModsPanelSortKey.MODNAME,
            cached_metadata=cached,
        )
        assert result == ["uuid_a", "uuid_b"]
        assert original == ["uuid_b", "uuid_a"]

    def test_sort_empty_list(self) -> None:
        result = sort_uuids(
            [],
            ModsPanelSortKey.MODNAME,
            cached_metadata={},
        )
        assert result == []

    def test_sort_single_item(self) -> None:
        cached: dict[str, Any] = {"uuid1": {"name": "Only"}}
        result = sort_uuids(
            ["uuid1"],
            ModsPanelSortKey.MODNAME,
            cached_metadata=cached,
        )
        assert result == ["uuid1"]

    def test_sort_by_nokey_preserves_relative_order(self) -> None:
        """NOKEY sorts by UUID string value (lexicographic)."""
        cached: dict[str, Any] = {
            "uuid_c": {"name": "C"},
            "uuid_a": {"name": "A"},
            "uuid_b": {"name": "B"},
        }
        result = sort_uuids(
            ["uuid_c", "uuid_a", "uuid_b"],
            ModsPanelSortKey.NOKEY,
            cached_metadata=cached,
        )
        assert result == ["uuid_a", "uuid_b", "uuid_c"]


# ---------------------------------------------------------------------------
# DEFAULT_REVERSE_FLAGS and ModsPanelSortKey
# ---------------------------------------------------------------------------


class TestModsPanelSortKeyEnum:
    def test_all_enum_values_have_default_reverse_flag(self) -> None:
        """Every enum member should have an entry in DEFAULT_REVERSE_FLAGS."""
        for member in ModsPanelSortKey:
            assert member in DEFAULT_REVERSE_FLAGS

    def test_all_defaults_are_false(self) -> None:
        """All default reverse flags are False (ascending)."""
        for member in ModsPanelSortKey:
            assert DEFAULT_REVERSE_FLAGS[member] is False
