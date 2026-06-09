"""Tests for app.models.mod_list — ModEntry, create_mod_entry, ModListDiff, ModList."""

from app.models.metadata.metadata_structure import CaseInsensitiveStr, ModType
from app.models.mod_list import ModEntry, create_mod_entry


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
