"""Tests for app.models.mod_list — ModEntry, create_mod_entry, ModListDiff, ModList."""

from unittest.mock import MagicMock, PropertyMock

import pytest

from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    CaseInsensitiveStr,
    ListedMod,
    ModsConfig,
    ModType,
    ScenarioMod,
)
from app.models.mod_list import ModEntry, ModList, ModListDiff, create_mod_entry


def _config(
    version: str,
    active: list[str],
    expansions: list[str] | None = None,
) -> ModsConfig:
    """Build a ModsConfig with plain strings (wraps to CaseInsensitiveStr for pyright)."""
    return ModsConfig(
        version=version,
        activeMods=[CaseInsensitiveStr(s) for s in active],
        knownExpansions=[CaseInsensitiveStr(s) for s in (expansions or [])],
    )


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
        assert set(dupes[CaseInsensitiveStr("dup.mod")]) == {
            "/local/mod",
            "/workshop/mod",
        }
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


class TestToModsConfig:
    def test_basic(self) -> None:
        entries = [
            _entry("/a", "pkg.a"),
            _entry("/b", "pkg.b"),
        ]
        ml = ModList(entries)
        config = ml.to_mods_config("1.5", [CaseInsensitiveStr("ludeon.rimworld")])
        assert config.version == "1.5"
        assert config.activeMods == [
            CaseInsensitiveStr("pkg.a"),
            CaseInsensitiveStr("pkg.b"),
        ]
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


def _make_mock_metadata_controller(
    mods: dict[str, tuple[str, ModType]],
) -> MagicMock:
    """Build a mock MetadataController with mods_metadata and packageid_to_paths.

    :param mods: dict of path -> (packageId, ModType)
    """
    mc = MagicMock()

    mods_metadata: dict[str, ListedMod] = {}
    pid_to_paths: dict[str, set[str]] = {}

    for path, (pid, mod_type) in mods.items():
        mod = MagicMock(spec=AboutXmlMod)
        mod.package_id = CaseInsensitiveStr(pid)
        mod.mod_type = mod_type
        mods_metadata[path] = mod
        pid_to_paths.setdefault(pid.lower(), set()).add(path)

    mc.mods_metadata = mods_metadata
    type(mc).packageid_to_paths = PropertyMock(return_value=pid_to_paths)
    return mc


class TestFromModsConfig:
    def test_basic_resolution(self) -> None:
        mc = _make_mock_metadata_controller(
            {
                "/local/mod_a": ("author.moda", ModType.LOCAL),
                "/local/mod_b": ("author.modb", ModType.LOCAL),
            }
        )
        config = _config("1.5", ["author.moda", "author.modb"])
        mod_list, missing = ModList.from_mods_config(config, mc)
        assert mod_list.paths() == ["/local/mod_a", "/local/mod_b"]
        assert missing == []

    def test_missing_mod(self) -> None:
        mc = _make_mock_metadata_controller(
            {
                "/local/mod_a": ("author.moda", ModType.LOCAL),
            }
        )
        config = _config("1.5", ["author.moda", "ghost.mod"])
        mod_list, missing = ModList.from_mods_config(config, mc)
        assert mod_list.paths() == ["/local/mod_a"]
        assert "ghost.mod" in missing

    def test_steam_suffix_prefers_workshop(self) -> None:
        mc = _make_mock_metadata_controller(
            {
                "/local/mymod": ("author.mod", ModType.LOCAL),
                "/workshop/mymod": ("author.mod", ModType.STEAM_WORKSHOP),
            }
        )
        config = _config("1.5", ["author.mod_steam"])
        mod_list, missing = ModList.from_mods_config(config, mc)
        assert len(mod_list) == 1
        assert mod_list[0].path == "/workshop/mymod"
        assert mod_list[0].config_id == "author.mod_steam"

    def test_no_suffix_prefers_expansion(self) -> None:
        mc = _make_mock_metadata_controller(
            {
                "/game/Data/Core": ("ludeon.rimworld", ModType.LUDEON),
                "/workshop/rimworld": ("ludeon.rimworld", ModType.STEAM_WORKSHOP),
            }
        )
        config = _config("1.5", ["ludeon.rimworld"])
        mod_list, missing = ModList.from_mods_config(config, mc)
        assert mod_list[0].path == "/game/Data/Core"

    def test_no_suffix_fallback_to_local(self) -> None:
        mc = _make_mock_metadata_controller(
            {
                "/local/mymod": ("author.mod", ModType.LOCAL),
                "/workshop/mymod": ("author.mod", ModType.STEAM_WORKSHOP),
            }
        )
        config = _config("1.5", ["author.mod"])
        mod_list, missing = ModList.from_mods_config(config, mc)
        assert mod_list[0].path == "/local/mymod"

    def test_preserves_order(self) -> None:
        mc = _make_mock_metadata_controller(
            {
                "/a": ("mod.a", ModType.LOCAL),
                "/b": ("mod.b", ModType.LOCAL),
                "/c": ("mod.c", ModType.LOCAL),
            }
        )
        config = _config("1.5", ["mod.c", "mod.a", "mod.b"])
        mod_list, _ = ModList.from_mods_config(config, mc)
        assert mod_list.package_ids() == [
            CaseInsensitiveStr("mod.c"),
            CaseInsensitiveStr("mod.a"),
            CaseInsensitiveStr("mod.b"),
        ]

    def test_round_trip(self) -> None:
        mc = _make_mock_metadata_controller(
            {
                "/a": ("mod.a", ModType.LOCAL),
                "/b": ("mod.b", ModType.STEAM_WORKSHOP),
            }
        )
        original_config = _config("1.5", ["mod.a", "mod.b"], ["ludeon.rimworld"])
        mod_list, _ = ModList.from_mods_config(original_config, mc)
        roundtripped = mod_list.to_mods_config(
            "1.5", [CaseInsensitiveStr("ludeon.rimworld")]
        )
        assert roundtripped.activeMods == original_config.activeMods
        assert roundtripped.knownExpansions == original_config.knownExpansions

    def test_empty_config(self) -> None:
        mc = _make_mock_metadata_controller({})
        config = _config("1.5", [])
        mod_list, missing = ModList.from_mods_config(config, mc)
        assert len(mod_list) == 0
        assert missing == []

    def test_all_missing(self) -> None:
        mc = _make_mock_metadata_controller({})
        config = _config("1.5", ["gone.a", "gone.b"])
        mod_list, missing = ModList.from_mods_config(config, mc)
        assert len(mod_list) == 0
        assert set(missing) == {"gone.a", "gone.b"}


class TestFromRemaining:
    def test_basic(self) -> None:
        mc = _make_mock_metadata_controller(
            {
                "/a": ("mod.a", ModType.LOCAL),
                "/b": ("mod.b", ModType.LOCAL),
                "/c": ("mod.c", ModType.STEAM_WORKSHOP),
            }
        )
        active = ModList([_entry("/a", "mod.a")])
        remaining = ModList.from_remaining({"/a", "/b", "/c"}, active, mc)
        remaining_paths = set(remaining.paths())
        assert remaining_paths == {"/b", "/c"}

    def test_no_steam_suffix(self) -> None:
        mc = _make_mock_metadata_controller(
            {
                "/a": ("dup.mod", ModType.LOCAL),
                "/b": ("dup.mod", ModType.STEAM_WORKSHOP),
            }
        )
        active = ModList()
        remaining = ModList.from_remaining({"/a", "/b"}, active, mc)
        for entry in remaining:
            assert "_steam" not in entry.config_id

    def test_all_active(self) -> None:
        mc = _make_mock_metadata_controller(
            {
                "/a": ("mod.a", ModType.LOCAL),
            }
        )
        active = ModList([_entry("/a", "mod.a")])
        remaining = ModList.from_remaining({"/a"}, active, mc)
        assert len(remaining) == 0

    def test_non_about_xml_mod_gets_synthetic_pid(self) -> None:
        """ScenarioMod and invalid ListedMod entries get __path: prefixed package_id."""
        mc = MagicMock()
        scenario = MagicMock(spec=ScenarioMod)
        scenario.mod_type = ModType.LOCAL
        invalid = MagicMock(spec=ListedMod)
        invalid.mod_type = ModType.UNKNOWN
        mc.mods_metadata = {
            "/scenarios/my_scenario": scenario,
            "/invalid/leftover": invalid,
        }
        active = ModList()
        remaining = ModList.from_remaining(
            {"/scenarios/my_scenario", "/invalid/leftover"}, active, mc
        )
        assert len(remaining) == 2
        for entry in remaining:
            assert entry.package_id.startswith("__path:")
            assert entry.path in str(entry.package_id)
        dupes = remaining.find_duplicate_package_ids()
        assert len(dupes) == 0

    def test_empty_all(self) -> None:
        mc = _make_mock_metadata_controller({})
        active = ModList()
        remaining = ModList.from_remaining(set(), active, mc)
        assert len(remaining) == 0
