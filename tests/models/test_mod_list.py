"""Tests for app.models.mod_list — ModEntry, create_mod_entry, ModListDiff, ModList."""

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
