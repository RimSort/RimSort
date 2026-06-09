"""Tests for app.models.mod_list — ModEntry, create_mod_entry, ModListDiff, ModList."""

import pytest

from app.models.metadata.metadata_structure import CaseInsensitiveStr, ModType
from app.models.mod_list import ModEntry, ModList, ModListDiff, create_mod_entry


class TestModEntry:
    def test_frozen(self) -> None:
        entry = ModEntry(
            path="/mods/local_mod",
            package_id=CaseInsensitiveStr("author.modname"),
            config_id="author.modname",
        )
        try:
            entry.path = "/other"  # type: ignore[misc]
            assert False, "Should have raised FrozenInstanceError"
        except AttributeError:
            pass

    def test_equality(self) -> None:
        a = ModEntry("/mods/a", CaseInsensitiveStr("pkg.a"), "pkg.a")
        b = ModEntry("/mods/a", CaseInsensitiveStr("pkg.a"), "pkg.a")
        assert a == b

    def test_hashable(self) -> None:
        entry = ModEntry("/mods/a", CaseInsensitiveStr("pkg.a"), "pkg.a")
        s = {entry}
        assert entry in s


class TestCreateModEntry:
    def test_no_duplicate_local(self) -> None:
        entry = create_mod_entry(
            path="/mods/local_mod",
            package_id=CaseInsensitiveStr("author.modname"),
            mod_type=ModType.LOCAL,
            has_duplicate=False,
        )
        assert entry.config_id == "author.modname"

    def test_no_duplicate_workshop(self) -> None:
        entry = create_mod_entry(
            path="/mods/workshop_mod",
            package_id=CaseInsensitiveStr("author.modname"),
            mod_type=ModType.STEAM_WORKSHOP,
            has_duplicate=False,
        )
        assert entry.config_id == "author.modname"

    def test_duplicate_workshop_gets_steam_suffix(self) -> None:
        entry = create_mod_entry(
            path="/mods/workshop_mod",
            package_id=CaseInsensitiveStr("author.modname"),
            mod_type=ModType.STEAM_WORKSHOP,
            has_duplicate=True,
        )
        assert entry.config_id == "author.modname_steam"

    def test_duplicate_local_no_suffix(self) -> None:
        entry = create_mod_entry(
            path="/mods/local_mod",
            package_id=CaseInsensitiveStr("author.modname"),
            mod_type=ModType.LOCAL,
            has_duplicate=True,
        )
        assert entry.config_id == "author.modname"

    def test_duplicate_steamcmd_no_suffix(self) -> None:
        entry = create_mod_entry(
            path="/mods/steamcmd_mod",
            package_id=CaseInsensitiveStr("author.modname"),
            mod_type=ModType.STEAM_CMD,
            has_duplicate=True,
        )
        assert entry.config_id == "author.modname"

    def test_path_and_package_id_preserved(self) -> None:
        entry = create_mod_entry(
            path="/some/path",
            package_id=CaseInsensitiveStr("Some.Mod"),
            mod_type=ModType.LOCAL,
            has_duplicate=False,
        )
        assert entry.path == "/some/path"
        assert entry.package_id == CaseInsensitiveStr("some.mod")


def _entry(path: str, pid: str = "", config_id: str = "") -> ModEntry:
    """Helper to build ModEntry with sensible defaults."""
    pid = pid or path.split("/")[-1]
    config_id = config_id or pid
    return ModEntry(path=path, package_id=CaseInsensitiveStr(pid), config_id=config_id)


class TestModListDiff:
    def test_empty_diff(self) -> None:
        diff = ModListDiff(added=[], removed=[], reordered=False)
        assert len(diff.added) == 0
        assert len(diff.removed) == 0
        assert diff.reordered is False

    def test_diff_fields(self) -> None:
        a = ModEntry("/a", CaseInsensitiveStr("a"), "a")
        b = ModEntry("/b", CaseInsensitiveStr("b"), "b")
        diff = ModListDiff(added=[a], removed=[b], reordered=True)
        assert diff.added == [a]
        assert diff.removed == [b]
        assert diff.reordered is True


class TestModListConstruction:
    def test_empty(self) -> None:
        ml = ModList()
        assert len(ml) == 0
        assert list(ml) == []

    def test_from_entries(self) -> None:
        entries = [_entry("/a"), _entry("/b"), _entry("/c")]
        ml = ModList(entries)
        assert len(ml) == 3
        assert ml[0] == entries[0]
        assert ml[1] == entries[1]
        assert ml[2] == entries[2]

    def test_contains(self) -> None:
        ml = ModList([_entry("/a"), _entry("/b")])
        assert "/a" in ml
        assert "/c" not in ml

    def test_index_of_found(self) -> None:
        ml = ModList([_entry("/a"), _entry("/b"), _entry("/c")])
        assert ml.index_of("/b") == 1

    def test_index_of_missing(self) -> None:
        ml = ModList([_entry("/a")])
        assert ml.index_of("/z") is None

    def test_getitem_out_of_bounds(self) -> None:
        ml = ModList([_entry("/a")])
        try:
            ml[5]
            assert False, "Should have raised IndexError"
        except IndexError:
            pass

    def test_paths(self) -> None:
        ml = ModList([_entry("/a", "pkg.a"), _entry("/b", "pkg.b")])
        assert ml.paths() == ["/a", "/b"]

    def test_package_ids(self) -> None:
        ml = ModList([_entry("/a", "pkg.a"), _entry("/b", "pkg.b")])
        pids = ml.package_ids()
        assert pids == [CaseInsensitiveStr("pkg.a"), CaseInsensitiveStr("pkg.b")]

    def test_entries_for_package_id(self) -> None:
        e1 = _entry("/local/mymod", "author.mod")
        e2 = _entry("/workshop/mymod", "author.mod")
        ml = ModList([e1, e2])
        found = ml.entries_for_package_id(CaseInsensitiveStr("author.mod"))
        assert found == [e1, e2]

    def test_entries_for_package_id_missing(self) -> None:
        ml = ModList([_entry("/a", "pkg.a")])
        assert ml.entries_for_package_id(CaseInsensitiveStr("pkg.z")) == []

    def test_find_duplicate_package_ids(self) -> None:
        e1 = _entry("/local/mod", "dup.mod")
        e2 = _entry("/workshop/mod", "dup.mod")
        e3 = _entry("/other", "unique.mod")
        ml = ModList([e1, e2, e3])
        dupes = ml.find_duplicate_package_ids()
        assert CaseInsensitiveStr("dup.mod") in dupes
        assert set(dupes[CaseInsensitiveStr("dup.mod")]) == {"/local/mod", "/workshop/mod"}
        assert CaseInsensitiveStr("unique.mod") not in dupes

    def test_iter(self) -> None:
        entries = [_entry("/a"), _entry("/b")]
        ml = ModList(entries)
        assert list(ml) == entries


class TestModListMutations:
    def test_insert(self) -> None:
        ml = ModList([_entry("/a"), _entry("/c")])
        ml.insert(1, _entry("/b"))
        assert ml.paths() == ["/a", "/b", "/c"]
        assert ml.index_of("/b") == 1

    def test_insert_at_start(self) -> None:
        ml = ModList([_entry("/b")])
        ml.insert(0, _entry("/a"))
        assert ml.paths() == ["/a", "/b"]

    def test_insert_at_end(self) -> None:
        ml = ModList([_entry("/a")])
        ml.insert(1, _entry("/b"))
        assert ml.paths() == ["/a", "/b"]

    def test_insert_duplicate_path_raises(self) -> None:
        ml = ModList([_entry("/a")])
        with pytest.raises(ValueError):
            ml.insert(0, _entry("/a"))

    def test_remove_by_path(self) -> None:
        ml = ModList([_entry("/a"), _entry("/b"), _entry("/c")])
        removed = ml.remove_by_path("/b")
        assert removed.path == "/b"
        assert ml.paths() == ["/a", "/c"]
        assert ml.index_of("/c") == 1
        assert "/b" not in ml

    def test_remove_missing_raises(self) -> None:
        ml = ModList([_entry("/a")])
        with pytest.raises(KeyError):
            ml.remove_by_path("/z")

    def test_reorder_forward(self) -> None:
        ml = ModList([_entry("/a"), _entry("/b"), _entry("/c")])
        ml.reorder("/a", 2)
        assert ml.paths() == ["/b", "/c", "/a"]

    def test_reorder_backward(self) -> None:
        ml = ModList([_entry("/a"), _entry("/b"), _entry("/c")])
        ml.reorder("/c", 0)
        assert ml.paths() == ["/c", "/a", "/b"]

    def test_reorder_missing_raises(self) -> None:
        ml = ModList([_entry("/a")])
        with pytest.raises(KeyError):
            ml.reorder("/z", 0)

    def test_reorder_out_of_bounds_raises(self) -> None:
        ml = ModList([_entry("/a"), _entry("/b")])
        with pytest.raises(IndexError):
            ml.reorder("/a", 5)

    def test_move_batch(self) -> None:
        ml = ModList([_entry("/a"), _entry("/b"), _entry("/c"), _entry("/d")])
        ml.move_batch(["/a", "/c"], 3)
        assert ml.paths() == ["/b", "/d", "/a", "/c"]

    def test_move_batch_to_start(self) -> None:
        ml = ModList([_entry("/a"), _entry("/b"), _entry("/c")])
        ml.move_batch(["/b", "/c"], 0)
        assert ml.paths() == ["/b", "/c", "/a"]

    def test_move_batch_preserves_relative_order(self) -> None:
        ml = ModList([_entry("/a"), _entry("/b"), _entry("/c"), _entry("/d")])
        ml.move_batch(["/c", "/a"], 1)
        assert ml.paths() == ["/b", "/a", "/c", "/d"]

    def test_replace_order(self) -> None:
        entries = [_entry("/a"), _entry("/b"), _entry("/c")]
        ml = ModList(entries)
        ml.replace_order([entries[2], entries[0], entries[1]])
        assert ml.paths() == ["/c", "/a", "/b"]

    def test_clear(self) -> None:
        ml = ModList([_entry("/a"), _entry("/b")])
        ml.clear()
        assert len(ml) == 0
        assert ml.paths() == []
        assert "/a" not in ml


class TestModListIndexConsistency:
    """Verify indices stay correct after every mutation type."""

    def _check_indices(self, ml: ModList) -> None:
        """Assert _path_index and _pid_index are consistent with _entries."""
        for i, entry in enumerate(ml._entries):
            assert ml._path_index[entry.path] == i, (
                f"_path_index[{entry.path}] = {ml._path_index[entry.path]}, expected {i}"
            )
            assert i in ml._pid_index[entry.package_id], (
                f"{i} not in _pid_index[{entry.package_id}]"
            )
        assert len(ml._path_index) == len(ml._entries)
        total_pid_refs = sum(len(v) for v in ml._pid_index.values())
        assert total_pid_refs == len(ml._entries)

    def test_after_insert(self) -> None:
        ml = ModList([_entry("/a"), _entry("/c")])
        ml.insert(1, _entry("/b"))
        self._check_indices(ml)

    def test_after_remove(self) -> None:
        ml = ModList([_entry("/a"), _entry("/b"), _entry("/c")])
        ml.remove_by_path("/b")
        self._check_indices(ml)

    def test_after_reorder(self) -> None:
        ml = ModList([_entry("/a"), _entry("/b"), _entry("/c")])
        ml.reorder("/a", 2)
        self._check_indices(ml)

    def test_after_move_batch(self) -> None:
        ml = ModList([_entry("/a"), _entry("/b"), _entry("/c"), _entry("/d")])
        ml.move_batch(["/a", "/c"], 3)
        self._check_indices(ml)

    def test_after_replace_order(self) -> None:
        entries = [_entry("/a"), _entry("/b"), _entry("/c")]
        ml = ModList(entries)
        ml.replace_order([entries[2], entries[0], entries[1]])
        self._check_indices(ml)

    def test_after_clear_and_reuse(self) -> None:
        ml = ModList([_entry("/a"), _entry("/b")])
        ml.clear()
        ml.insert(0, _entry("/x"))
        self._check_indices(ml)


class TestModListDiffMethod:
    def test_identical_lists(self) -> None:
        entries = [_entry("/a"), _entry("/b")]
        a = ModList(entries)
        b = ModList(entries)
        d = a.diff(b)
        assert d.added == []
        assert d.removed == []
        assert d.reordered is False

    def test_added(self) -> None:
        a = ModList([_entry("/a")])
        new_entry = _entry("/b")
        b = ModList([_entry("/a"), new_entry])
        d = a.diff(b)
        assert d.added == [new_entry]
        assert d.removed == []

    def test_removed(self) -> None:
        removed_entry = _entry("/b")
        a = ModList([_entry("/a"), removed_entry])
        b = ModList([_entry("/a")])
        d = a.diff(b)
        assert d.added == []
        assert d.removed == [removed_entry]

    def test_reordered(self) -> None:
        e1, e2 = _entry("/a"), _entry("/b")
        a = ModList([e1, e2])
        b = ModList([e2, e1])
        d = a.diff(b)
        assert d.added == []
        assert d.removed == []
        assert d.reordered is True

    def test_both_empty(self) -> None:
        d = ModList().diff(ModList())
        assert d.added == []
        assert d.removed == []
        assert d.reordered is False

    def test_added_and_removed(self) -> None:
        ea = _entry("/a")
        eb = _entry("/b")
        a = ModList([ea])
        b = ModList([eb])
        d = a.diff(b)
        assert d.added == [eb]
        assert d.removed == [ea]
        assert d.reordered is False


from app.models.metadata.metadata_structure import ModsConfig


class TestToModsConfig:
    def test_basic(self) -> None:
        entries = [
            _entry("/a", "pkg.a"),
            _entry("/b", "pkg.b"),
        ]
        ml = ModList(entries)
        config = ml.to_mods_config("1.5", [CaseInsensitiveStr("ludeon.rimworld")])
        assert config.version == "1.5"
        assert config.activeMods == [CaseInsensitiveStr("pkg.a"), CaseInsensitiveStr("pkg.b")]
        assert config.knownExpansions == [CaseInsensitiveStr("ludeon.rimworld")]

    def test_uses_config_id(self) -> None:
        entry = ModEntry("/w/mod", CaseInsensitiveStr("author.mod"), "author.mod_steam")
        ml = ModList([entry])
        config = ml.to_mods_config("1.5", [])
        assert config.activeMods == [CaseInsensitiveStr("author.mod_steam")]

    def test_empty(self) -> None:
        ml = ModList()
        config = ml.to_mods_config("1.5", [])
        assert config.activeMods == []


class TestFromSortedPaths:
    def test_reorders_from_source(self) -> None:
        e1 = _entry("/a", "pkg.a")
        e2 = _entry("/b", "pkg.b")
        e3 = _entry("/c", "pkg.c")
        source = ModList([e1, e2, e3])
        result = ModList.from_sorted_paths(["/c", "/a", "/b"], source)
        assert result.paths() == ["/c", "/a", "/b"]
        assert result[0] is e3
        assert result[1] is e1
        assert result[2] is e2

    def test_missing_path_skipped(self) -> None:
        e1 = _entry("/a", "pkg.a")
        source = ModList([e1])
        result = ModList.from_sorted_paths(["/a", "/missing"], source)
        assert result.paths() == ["/a"]

    def test_empty_sort(self) -> None:
        source = ModList([_entry("/a")])
        result = ModList.from_sorted_paths([], source)
        assert len(result) == 0
