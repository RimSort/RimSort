"""Tests for app.sort.mod_sorting -- inactive mods list sorting helpers."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    CaseInsensitiveStr,
    ListedMod,
)
from app.sort.mod_sorting import (
    DEFAULT_REVERSE_FLAGS,
    ModsPanelSortKey,
    _build_sort_key_map,
    get_cached_metadata_for_batch,
    get_dir_size,
    get_mod_metadata,
    path_no_key,
    path_to_author,
    path_to_filesystem_modified_time,
    path_to_folder_size,
    path_to_mod_color,
    path_to_mod_name,
    path_to_mod_tags,
    path_to_packageid,
    path_to_version,
    sort_paths,
)


def _make_listed_mod(
    path: str,
    name: str = "Unknown Mod",
    package_id: str | None = None,
    authors: list[str] | None = None,
    mod_version: str = "",
) -> ListedMod | AboutXmlMod:
    """Build a typed ListedMod or AboutXmlMod for sorting tests.

    If package_id is provided, builds an AboutXmlMod; otherwise a ListedMod.
    """
    mod: ListedMod | AboutXmlMod
    if package_id is not None:
        mod = AboutXmlMod(
            name=name,
            package_id=CaseInsensitiveStr(package_id),
            authors=authors or [],
            mod_version=mod_version,
        )
    else:
        mod = ListedMod(name=name)
    mod.mod_path = Path(path)
    return mod


@pytest.fixture(autouse=True)
def _clear_folder_size_cache() -> Generator[None, None, None]:
    """Clear the module-level folder size cache between tests."""
    yield
    from app.sort.mod_sorting import _FOLDER_SIZE_CACHE

    _FOLDER_SIZE_CACHE.clear()


# ---------------------------------------------------------------------------
# path_no_key -- identity function
# ---------------------------------------------------------------------------


class TestPathNoKey:
    def test_returns_path_unchanged(self) -> None:
        assert path_no_key("/some/path/123") == "/some/path/123"

    def test_empty_string(self) -> None:
        assert path_no_key("") == ""


# ---------------------------------------------------------------------------
# path_to_mod_name
# ---------------------------------------------------------------------------


class TestPathToModName:
    def test_cached_metadata_with_name(self) -> None:
        mod = _make_listed_mod("/mods/mod1", name="MyMod")
        cached: dict[str, ListedMod | None] = {"/mods/mod1": mod}
        assert path_to_mod_name("/mods/mod1", cached) == "mymod"

    def test_cached_metadata_missing_path(self) -> None:
        cached: dict[str, ListedMod | None] = {}
        assert path_to_mod_name("/missing", cached) == "name error in mod about.xml"

    def test_uncached_path(self, mock_metadata_controller: MagicMock) -> None:
        mod = _make_listed_mod("/mods/mod1", name="TestMod")
        mock_metadata_controller.mods_metadata = {"/mods/mod1": mod}
        assert path_to_mod_name("/mods/mod1") == "testmod"

    def test_name_preserves_lowercase(self) -> None:
        mod = _make_listed_mod("/mods/mod1", name="ALLCAPS")
        cached: dict[str, ListedMod | None] = {"/mods/mod1": mod}
        assert path_to_mod_name("/mods/mod1", cached) == "allcaps"

    def test_metadata_is_none(self) -> None:
        cached: dict[str, ListedMod | None] = {"/mods/mod1": None}
        assert path_to_mod_name("/mods/mod1", cached) == "name error in mod about.xml"


# ---------------------------------------------------------------------------
# path_to_packageid
# ---------------------------------------------------------------------------


class TestPathToPackageid:
    def test_cached_with_packageid(self) -> None:
        mod = _make_listed_mod("/mods/mod1", package_id="author.ModName")
        cached: dict[str, ListedMod | None] = {"/mods/mod1": mod}
        assert path_to_packageid("/mods/mod1", cached) == "author.modname"

    def test_cached_missing_path(self) -> None:
        cached: dict[str, ListedMod | None] = {}
        assert path_to_packageid("/missing", cached) == ""

    def test_listed_mod_without_packageid(self) -> None:
        mod = ListedMod(name="NoPkg")
        mod.mod_path = Path("/mods/mod1")
        cached: dict[str, ListedMod | None] = {"/mods/mod1": mod}
        assert path_to_packageid("/mods/mod1", cached) == ""

    def test_uncached_path(self, mock_metadata_controller: MagicMock) -> None:
        mod = _make_listed_mod("/mods/mod1", package_id="Author.Mod")
        mock_metadata_controller.mods_metadata = {"/mods/mod1": mod}
        assert path_to_packageid("/mods/mod1") == "author.mod"


# ---------------------------------------------------------------------------
# path_to_version
# ---------------------------------------------------------------------------


class TestPathToVersion:
    def test_cached_with_version(self) -> None:
        mod = _make_listed_mod("/mods/mod1", package_id="a.b", mod_version="1.2.3")
        cached: dict[str, ListedMod | None] = {"/mods/mod1": mod}
        assert path_to_version("/mods/mod1", cached) == "1.2.3"

    def test_cached_missing_path(self) -> None:
        cached: dict[str, ListedMod | None] = {}
        assert path_to_version("/missing", cached) == ""

    def test_listed_mod_without_version(self) -> None:
        mod = ListedMod(name="NoVer")
        mod.mod_path = Path("/mods/mod1")
        cached: dict[str, ListedMod | None] = {"/mods/mod1": mod}
        assert path_to_version("/mods/mod1", cached) == ""

    def test_uncached_path(self, mock_metadata_controller: MagicMock) -> None:
        mod = _make_listed_mod("/mods/mod1", package_id="a.b", mod_version="2.0.0-BETA")
        mock_metadata_controller.mods_metadata = {"/mods/mod1": mod}
        assert path_to_version("/mods/mod1") == "2.0.0-beta"


# ---------------------------------------------------------------------------
# path_to_mod_color -- now uses path_to_color dict, not metadata
# ---------------------------------------------------------------------------


class TestPathToModColor:
    def test_with_color_in_map(self) -> None:
        color_map = {"/mods/mod1": "#FF00AA"}
        assert path_to_mod_color("/mods/mod1", color_map) == "#ff00aa"

    def test_missing_path(self) -> None:
        color_map: dict[str, str] = {}
        assert path_to_mod_color("/missing", color_map) == ""

    def test_no_map_provided(self) -> None:
        assert path_to_mod_color("/mods/mod1") == ""


# ---------------------------------------------------------------------------
# path_to_author
# ---------------------------------------------------------------------------


class TestPathToAuthor:
    def test_aboutxmlmod_with_authors(self) -> None:
        mod = _make_listed_mod(
            "/mods/mod1", package_id="a.b", authors=["Author1", "Author2"]
        )
        cached: dict[str, ListedMod | None] = {"/mods/mod1": mod}
        assert path_to_author("/mods/mod1", cached) == "author1"

    def test_listed_mod_no_authors(self) -> None:
        mod = ListedMod(name="NoAuthor")
        mod.mod_path = Path("/mods/mod1")
        cached: dict[str, ListedMod | None] = {"/mods/mod1": mod}
        assert path_to_author("/mods/mod1", cached) == ""

    def test_empty_authors_list(self) -> None:
        mod = _make_listed_mod("/mods/mod1", package_id="a.b", authors=[])
        cached: dict[str, ListedMod | None] = {"/mods/mod1": mod}
        assert path_to_author("/mods/mod1", cached) == ""

    def test_missing_path(self) -> None:
        cached: dict[str, ListedMod | None] = {}
        assert path_to_author("/missing", cached) == ""

    def test_metadata_is_none(self) -> None:
        cached: dict[str, ListedMod | None] = {"/mods/mod1": None}
        assert path_to_author("/mods/mod1", cached) == ""

    def test_uncached_path(self, mock_metadata_controller: MagicMock) -> None:
        mod = _make_listed_mod(
            "/mods/mod1", package_id="a.b", authors=["UncachedAuthor"]
        )
        mock_metadata_controller.mods_metadata = {"/mods/mod1": mod}
        assert path_to_author("/mods/mod1") == "uncachedauthor"


# ---------------------------------------------------------------------------
# path_to_filesystem_modified_time
# ---------------------------------------------------------------------------


class TestPathToFilesystemModifiedTime:
    def test_path_exists(self) -> None:
        p = str(Path("/mods/mymod"))
        mod = _make_listed_mod(p, name="MyMod")
        cached: dict[str, ListedMod | None] = {p: mod}
        with (
            patch("app.sort.mod_sorting.os.path.exists", return_value=True),
            patch("app.sort.mod_sorting.os.path.getmtime", return_value=1700000000.5),
        ):
            result = path_to_filesystem_modified_time(p, cached)
        assert result == 1700000000

    def test_path_does_not_exist(self) -> None:
        p = str(Path("/mods/gone"))
        mod = _make_listed_mod(p, name="Gone")
        cached: dict[str, ListedMod | None] = {p: mod}
        with patch("app.sort.mod_sorting.os.path.exists", return_value=False):
            result = path_to_filesystem_modified_time(p, cached)
        assert result == 0

    def test_no_metadata(self) -> None:
        cached: dict[str, ListedMod | None] = {}
        assert path_to_filesystem_modified_time("/missing", cached) == 0

    def test_metadata_is_none(self) -> None:
        cached: dict[str, ListedMod | None] = {"/mods/mod1": None}
        assert path_to_filesystem_modified_time("/mods/mod1", cached) == 0

    def test_uncached_path(self, mock_metadata_controller: MagicMock) -> None:
        mod = _make_listed_mod("/mods/test", name="Test")
        mock_metadata_controller.mods_metadata = {"/mods/test": mod}
        with (
            patch("app.sort.mod_sorting.os.path.exists", return_value=True),
            patch("app.sort.mod_sorting.os.path.getmtime", return_value=1600000000.0),
        ):
            result = path_to_filesystem_modified_time("/mods/test")
        assert result == 1600000000


# ---------------------------------------------------------------------------
# path_to_folder_size
# ---------------------------------------------------------------------------


_DEFAULT_MOD_PATH = str(Path("/mods/mymod"))


def _make_folder_size_fixtures(
    path: str = _DEFAULT_MOD_PATH,
) -> tuple[ListedMod | AboutXmlMod, dict[str, ListedMod | None]]:
    """Build a mod and cached-metadata dict for ``path_to_folder_size`` tests."""
    mod = _make_listed_mod(path)
    cached: dict[str, ListedMod | None] = {path: mod}
    return mod, cached


class TestPathToFolderSize:
    def test_directory_exists(self) -> None:
        _mod, cached = _make_folder_size_fixtures()
        with (
            patch("app.sort.mod_sorting.os.path.isdir", return_value=True),
            patch("app.sort.mod_sorting.os.path.getmtime", return_value=12345.0),
            patch("app.sort.mod_sorting.get_dir_size", return_value=4096),
        ):
            result = path_to_folder_size(_DEFAULT_MOD_PATH, cached)
        assert result == 4096

    def test_path_not_a_directory(self) -> None:
        p = str(Path("/mods/file.txt"))
        _mod, cached = _make_folder_size_fixtures(p)
        with patch("app.sort.mod_sorting.os.path.isdir", return_value=False):
            result = path_to_folder_size(p, cached)
        assert result == 0

    def test_no_metadata(self) -> None:
        cached: dict[str, ListedMod | None] = {}
        assert path_to_folder_size(str(Path("/missing")), cached) == 0

    def test_metadata_is_none(self) -> None:
        p = str(Path("/mods/mod1"))
        cached: dict[str, ListedMod | None] = {p: None}
        assert path_to_folder_size(p, cached) == 0

    def test_cache_hit_same_mtime(self) -> None:
        _mod, cached = _make_folder_size_fixtures()
        with (
            patch("app.sort.mod_sorting.os.path.isdir", return_value=True),
            patch("app.sort.mod_sorting.os.path.getmtime", return_value=12345.0),
            patch("app.sort.mod_sorting.get_dir_size", return_value=8192) as mock_size,
        ):
            first = path_to_folder_size(_DEFAULT_MOD_PATH, cached)
            second = path_to_folder_size(_DEFAULT_MOD_PATH, cached)
        assert first == 8192
        assert second == 8192
        mock_size.assert_called_once()

    def test_cache_miss_different_mtime(self) -> None:
        from app.sort.mod_sorting import _FOLDER_SIZE_CACHE

        _FOLDER_SIZE_CACHE[_DEFAULT_MOD_PATH] = (10000, 1024)
        _mod, cached = _make_folder_size_fixtures()
        with (
            patch("app.sort.mod_sorting.os.path.isdir", return_value=True),
            patch("app.sort.mod_sorting.os.path.getmtime", return_value=99999.0),
            patch("app.sort.mod_sorting.get_dir_size", return_value=2048) as mock_size,
        ):
            result = path_to_folder_size(_DEFAULT_MOD_PATH, cached)
        assert result == 2048
        mock_size.assert_called_once_with(_DEFAULT_MOD_PATH)

    def test_oserror_on_getmtime(self) -> None:
        _mod, cached = _make_folder_size_fixtures()
        with (
            patch("app.sort.mod_sorting.os.path.isdir", return_value=True),
            patch(
                "app.sort.mod_sorting.os.path.getmtime", side_effect=OSError("denied")
            ),
        ):
            result = path_to_folder_size("/mods/mymod", cached)
        assert result == 0


# ---------------------------------------------------------------------------
# get_dir_size -- real filesystem via tmp_path
# ---------------------------------------------------------------------------


class TestGetDirSize:
    def test_empty_directory(self, tmp_path: Path) -> None:
        assert get_dir_size(str(tmp_path)) == 0

    def test_single_file(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_bytes(b"hello")
        assert get_dir_size(str(tmp_path)) == 5

    def test_multiple_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_bytes(b"aaa")
        (tmp_path / "b.txt").write_bytes(b"bb")
        assert get_dir_size(str(tmp_path)) == 5

    def test_nested_directories(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "top.txt").write_bytes(b"top")
        (sub / "nested.txt").write_bytes(b"nested")
        assert get_dir_size(str(tmp_path)) == 9

    def test_deeply_nested(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.txt").write_bytes(b"deep")
        assert get_dir_size(str(tmp_path)) == 4

    def test_oserror_on_inaccessible_subdir(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_bytes(b"ok")
        with patch(
            "app.sort.mod_sorting.scanpath", side_effect=OSError("permission denied")
        ):
            result = get_dir_size(str(tmp_path))
        assert result == 0


# ---------------------------------------------------------------------------
# path_to_mod_tags
# ---------------------------------------------------------------------------


class TestPathToModTags:
    def test_no_settings(self) -> None:
        assert path_to_mod_tags("/mods/mod1", settings=None) == ""

    def test_normal_tags(self) -> None:
        mock_sc = MagicMock()
        with patch(
            "app.sort.mod_sorting.auxdb_get_mod_tags",
            return_value=["Zebra", "Alpha", "Beta"],
        ):
            result = path_to_mod_tags("/mods/mod1", settings=mock_sc)
        assert result == "alpha, beta, zebra"

    def test_empty_tags(self) -> None:
        mock_sc = MagicMock()
        with patch("app.sort.mod_sorting.auxdb_get_mod_tags", return_value=[]):
            result = path_to_mod_tags("/mods/mod1", settings=mock_sc)
        assert result == ""

    def test_exception_returns_empty(self) -> None:
        mock_sc = MagicMock()
        with patch(
            "app.sort.mod_sorting.auxdb_get_mod_tags",
            side_effect=RuntimeError("db error"),
        ):
            result = path_to_mod_tags("/mods/mod1", settings=mock_sc)
        assert result == ""

    def test_single_tag(self) -> None:
        mock_sc = MagicMock()
        with patch("app.sort.mod_sorting.auxdb_get_mod_tags", return_value=["OnlyTag"]):
            result = path_to_mod_tags("/mods/mod1", settings=mock_sc)
        assert result == "onlytag"


# ---------------------------------------------------------------------------
# get_mod_metadata
# ---------------------------------------------------------------------------


class TestGetModMetadata:
    def test_path_exists(self, mock_metadata_controller: MagicMock) -> None:
        mod = _make_listed_mod("/mods/mod1", name="TestMod")
        mock_metadata_controller.mods_metadata = {"/mods/mod1": mod}
        result = get_mod_metadata("/mods/mod1")
        assert result is mod

    def test_path_missing(self, mock_metadata_controller: MagicMock) -> None:
        mock_metadata_controller.mods_metadata = {}
        result = get_mod_metadata("/nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# get_cached_metadata_for_batch
# ---------------------------------------------------------------------------


class TestGetCachedMetadataForBatch:
    def test_basic_batch_fetch(self, mock_metadata_controller: MagicMock) -> None:
        mod1 = _make_listed_mod("/mods/mod1", name="Mod1")
        mod2 = _make_listed_mod("/mods/mod2", name="Mod2")
        mock_metadata_controller.mods_metadata = {
            "/mods/mod1": mod1,
            "/mods/mod2": mod2,
        }
        result = get_cached_metadata_for_batch(["/mods/mod1", "/mods/mod2"])
        assert result["/mods/mod1"] is mod1
        assert result["/mods/mod2"] is mod2

    def test_missing_paths_map_to_none(
        self, mock_metadata_controller: MagicMock
    ) -> None:
        mod1 = _make_listed_mod("/mods/mod1", name="Mod1")
        mock_metadata_controller.mods_metadata = {"/mods/mod1": mod1}
        result = get_cached_metadata_for_batch(["/mods/mod1", "/mods/missing"])
        assert result["/mods/mod1"] is mod1
        assert result["/mods/missing"] is None

    def test_empty_paths(self, mock_metadata_controller: MagicMock) -> None:
        mock_metadata_controller.mods_metadata = {}
        result = get_cached_metadata_for_batch([])
        assert result == {}


# ---------------------------------------------------------------------------
# _build_sort_key_map
# ---------------------------------------------------------------------------


class TestBuildSortKeyMap:
    def test_modname_key(self) -> None:
        mod1 = _make_listed_mod("/mods/mod1", name="Bravo")
        mod2 = _make_listed_mod("/mods/mod2", name="Alpha")
        cached: dict[str, ListedMod | None] = {"/mods/mod1": mod1, "/mods/mod2": mod2}
        result = _build_sort_key_map(
            ["/mods/mod1", "/mods/mod2"], ModsPanelSortKey.MODNAME, cached
        )
        assert result["/mods/mod1"] == "bravo"
        assert result["/mods/mod2"] == "alpha"

    def test_nokey_returns_path(self) -> None:
        mod = _make_listed_mod("/mods/mod1", name="Irrelevant")
        cached: dict[str, ListedMod | None] = {"/mods/mod1": mod}
        result = _build_sort_key_map(["/mods/mod1"], ModsPanelSortKey.NOKEY, cached)
        assert result["/mods/mod1"] == "/mods/mod1"

    def test_packageid_key(self) -> None:
        mod = _make_listed_mod("/mods/mod1", package_id="Author.Pkg")
        cached: dict[str, ListedMod | None] = {"/mods/mod1": mod}
        result = _build_sort_key_map(["/mods/mod1"], ModsPanelSortKey.PACKAGEID, cached)
        assert result["/mods/mod1"] == "author.pkg"

    def test_version_key(self) -> None:
        mod = _make_listed_mod("/mods/mod1", package_id="a.b", mod_version="1.0.0")
        cached: dict[str, ListedMod | None] = {"/mods/mod1": mod}
        result = _build_sort_key_map(["/mods/mod1"], ModsPanelSortKey.VERSION, cached)
        assert result["/mods/mod1"] == "1.0.0"

    def test_author_key(self) -> None:
        mod = _make_listed_mod("/mods/mod1", package_id="a.b", authors=["SomeAuthor"])
        cached: dict[str, ListedMod | None] = {"/mods/mod1": mod}
        result = _build_sort_key_map(["/mods/mod1"], ModsPanelSortKey.AUTHOR, cached)
        assert result["/mods/mod1"] == "someauthor"

    def test_mod_color_key(self) -> None:
        result = _build_sort_key_map(
            ["/mods/mod1"],
            ModsPanelSortKey.MOD_COLOR,
            None,
            path_to_color={"/mods/mod1": "#ABC123"},
        )
        assert result["/mods/mod1"] == "#abc123"

    def test_filesystem_modified_time_key(self) -> None:
        mod = _make_listed_mod("/mods/m", name="M")
        cached: dict[str, ListedMod | None] = {"/mods/m": mod}
        with (
            patch("app.sort.mod_sorting.os.path.exists", return_value=True),
            patch("app.sort.mod_sorting.os.path.getmtime", return_value=1700000000.0),
        ):
            result = _build_sort_key_map(
                ["/mods/m"], ModsPanelSortKey.FILESYSTEM_MODIFIED_TIME, cached
            )
        assert result["/mods/m"] == 1700000000

    def test_folder_size_key(self) -> None:
        mod = _make_listed_mod("/mods/m")
        cached: dict[str, ListedMod | None] = {"/mods/m": mod}
        with (
            patch("app.sort.mod_sorting.os.path.isdir", return_value=True),
            patch("app.sort.mod_sorting.os.path.getmtime", return_value=100.0),
            patch("app.sort.mod_sorting.get_dir_size", return_value=999),
        ):
            result = _build_sort_key_map(
                ["/mods/m"], ModsPanelSortKey.FOLDER_SIZE, cached
            )
        assert result["/mods/m"] == 999

    def test_mod_tags_key(self) -> None:
        mod = _make_listed_mod("/mods/m", name="M")
        cached: dict[str, ListedMod | None] = {"/mods/m": mod}
        mock_sc = MagicMock()
        with patch(
            "app.sort.mod_sorting.auxdb_get_mod_tags",
            return_value=["Tag2", "Tag1"],
        ):
            result = _build_sort_key_map(
                ["/mods/m"],
                ModsPanelSortKey.MOD_TAGS,
                cached,
                settings=mock_sc,
            )
        assert result["/mods/m"] == "tag1, tag2"


# ---------------------------------------------------------------------------
# sort_paths -- orchestration
# ---------------------------------------------------------------------------


class TestSortPaths:
    def _make_cached(self) -> tuple[dict[str, ListedMod | None], list[str]]:
        mod_z = _make_listed_mod("/mods/z", name="Zebra")
        mod_a = _make_listed_mod("/mods/a", name="Alpha")
        mod_m = _make_listed_mod("/mods/m", name="Middle")
        cached: dict[str, ListedMod | None] = {
            "/mods/z": mod_z,
            "/mods/a": mod_a,
            "/mods/m": mod_m,
        }
        paths = ["/mods/z", "/mods/a", "/mods/m"]
        return cached, paths

    def test_sort_by_modname_ascending(self) -> None:
        cached, paths = self._make_cached()
        result = sort_paths(
            paths,
            ModsPanelSortKey.MODNAME,
            descending=False,
            cached_metadata=cached,
        )
        assert result == ["/mods/a", "/mods/m", "/mods/z"]

    def test_sort_by_modname_descending(self) -> None:
        cached, paths = self._make_cached()
        result = sort_paths(
            paths,
            ModsPanelSortKey.MODNAME,
            descending=True,
            cached_metadata=cached,
        )
        assert result == ["/mods/z", "/mods/m", "/mods/a"]

    def test_descending_none_uses_default_flags(self) -> None:
        mod_b = _make_listed_mod("/mods/b", name="Bravo")
        mod_a = _make_listed_mod("/mods/a", name="Alpha")
        cached: dict[str, ListedMod | None] = {"/mods/b": mod_b, "/mods/a": mod_a}
        result = sort_paths(
            ["/mods/b", "/mods/a"],
            ModsPanelSortKey.MODNAME,
            descending=None,
            cached_metadata=cached,
        )
        assert result == ["/mods/a", "/mods/b"]

    def test_sort_preserves_original_list(self) -> None:
        mod_b = _make_listed_mod("/mods/b", name="Bravo")
        mod_a = _make_listed_mod("/mods/a", name="Alpha")
        cached: dict[str, ListedMod | None] = {"/mods/b": mod_b, "/mods/a": mod_a}
        original = ["/mods/b", "/mods/a"]
        result = sort_paths(
            original,
            ModsPanelSortKey.MODNAME,
            cached_metadata=cached,
        )
        assert result == ["/mods/a", "/mods/b"]
        assert original == ["/mods/b", "/mods/a"]

    def test_sort_empty_list(self) -> None:
        result = sort_paths(
            [],
            ModsPanelSortKey.MODNAME,
            cached_metadata={},
        )
        assert result == []

    def test_sort_single_item(self) -> None:
        mod = _make_listed_mod("/mods/mod1", name="Only")
        cached: dict[str, ListedMod | None] = {"/mods/mod1": mod}
        result = sort_paths(
            ["/mods/mod1"],
            ModsPanelSortKey.MODNAME,
            cached_metadata=cached,
        )
        assert result == ["/mods/mod1"]

    def test_sort_by_nokey_preserves_relative_order(self) -> None:
        mod_c = _make_listed_mod("/mods/c", name="C")
        mod_a = _make_listed_mod("/mods/a", name="A")
        mod_b = _make_listed_mod("/mods/b", name="B")
        cached: dict[str, ListedMod | None] = {
            "/mods/c": mod_c,
            "/mods/a": mod_a,
            "/mods/b": mod_b,
        }
        result = sort_paths(
            ["/mods/c", "/mods/a", "/mods/b"],
            ModsPanelSortKey.NOKEY,
            cached_metadata=cached,
        )
        assert result == ["/mods/a", "/mods/b", "/mods/c"]


# ---------------------------------------------------------------------------
# DEFAULT_REVERSE_FLAGS and ModsPanelSortKey
# ---------------------------------------------------------------------------


class TestModsPanelSortKeyEnum:
    def test_all_enum_values_have_default_reverse_flag(self) -> None:
        for member in ModsPanelSortKey:
            assert member in DEFAULT_REVERSE_FLAGS

    def test_all_defaults_are_false(self) -> None:
        for member in ModsPanelSortKey:
            assert DEFAULT_REVERSE_FLAGS[member] is False
