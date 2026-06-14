from pathlib import Path

import pytest

import app.models.metadata.metadata_structure as metadata_structure
from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    ListedMod,
    ModType,
    SteamDbEntry,
)


def test_case_insensitive() -> None:
    pid = metadata_structure.CaseInsensitiveStr("TestPackage")
    assert pid == "testpackage"


@pytest.mark.parametrize(
    "input1, input2",
    [
        ("TestPackage", "testpackage"),
        ("testpackage", "TestPackage"),
        ("測試包", "測試包"),
        ("TEST.測試包", "test.測試包"),
        ("testpackage", "testpackage"),
    ],
)
def test_case_insensitive_equality(input1: str, input2: str) -> None:
    pid1 = metadata_structure.CaseInsensitiveStr(input1)
    pid2 = metadata_structure.CaseInsensitiveStr(input2)
    assert pid1 == pid2


@pytest.mark.parametrize(
    "pid, string",
    [
        ("TestPackage", "testpackage"),
        ("TESTPACKAGE", "testpackage"),
        ("測試包", "測試包"),
        ("TEST.測試包", "test.測試包"),
    ],
)
def test_case_insensitive_str(pid: str, string: str) -> None:
    package_id = metadata_structure.CaseInsensitiveStr(pid)
    assert str(package_id) == string
    assert package_id == string.lower()


def test_case_insensitive_set_contains() -> None:
    package_id_set = metadata_structure.CaseInsensitiveSet(
        ["TestPackage", "AnotherPackage"]
    )
    assert "TestPackage" in package_id_set
    assert "AnotherPackage" in package_id_set
    assert "NonExistingPackage" not in package_id_set


def test_case_insensitive_set_add() -> None:
    package_id_set = metadata_structure.CaseInsensitiveSet()
    package_id_set.add("TestPackage")
    assert "TestPackage" in package_id_set
    assert "testpackage" in package_id_set


def test_case_insensitive_set_discard() -> None:
    package_id_set = metadata_structure.CaseInsensitiveSet(["TestPackage"])
    package_id_set.discard("TestPackage")
    assert "TestPackage" not in package_id_set

    package_id_set = metadata_structure.CaseInsensitiveSet(["TestPackage"])
    package_id_set.discard("testpackage")
    assert "TestPackage" not in package_id_set


def test_case_insensitive_set_len() -> None:
    package_id_set = metadata_structure.CaseInsensitiveSet(
        ["TestPackage", "AnotherPackage"]
    )
    assert len(package_id_set) == 2

    package_id_set = metadata_structure.CaseInsensitiveSet(
        ["TestPackage", "testpackage"]
    )
    assert len(package_id_set) == 1


def test_case_insensitive_set_iter() -> None:
    package_id_set = metadata_structure.CaseInsensitiveSet(
        ["TestPackage", "AnotherPackage"]
    )
    assert set(package_id_set) == {"testpackage", "anotherpackage"}


def test_case_insensitive_set_and() -> None:
    package_id_set1 = metadata_structure.CaseInsensitiveSet(
        ["TestPackage", "AnotherPackage"]
    )
    package_id_set2 = metadata_structure.CaseInsensitiveSet(
        ["anotherpackage", "AdditionalPackage"]
    )
    intersection = package_id_set1 & package_id_set2
    assert set(intersection) == {"anotherpackage"}


def test_case_insensitive_set_parametrize() -> None:
    package_id_set = metadata_structure.CaseInsensitiveSet(
        ["TestPackage", "AnotherPackage"]
    )
    assert package_id_set == metadata_structure.CaseInsensitiveSet(
        ["testpackage", "anotherpackage"]
    )


def test_case_insensitive_set_union() -> None:
    package_id_set1 = metadata_structure.CaseInsensitiveSet(
        ["TestPackage", "AnotherPackage"]
    )
    package_id_set2 = metadata_structure.CaseInsensitiveSet(
        ["anotherpackage", "AdditionalPackage"]
    )
    union = package_id_set1 | package_id_set2
    assert set(union) == {"testpackage", "anotherpackage", "additionalpackage"}


def test_listed_mod_mod_path() -> None:
    mod = ListedMod()
    assert mod.mod_path is None

    mod.mod_path = Path("path/to/mod")
    assert mod.mod_path == Path("path/to/mod")

    with pytest.raises(ValueError):
        mod.mod_path = Path("another/path/to/mod")


def test_listed_mod_mod_folder() -> None:
    mod = ListedMod()
    mod.mod_path = Path("path/to/mod")
    assert mod.mod_folder == "mod"


def test_listed_mod_internal_time_touched() -> None:
    mod = ListedMod()
    mod.mod_path = Path("path/to/mod")
    assert mod.internal_time_touched == -1

    mod = ListedMod()
    mod.mod_path = Path(__file__)
    assert mod.internal_time_touched != -1


def test_listed_mod_mod_type() -> None:
    mod = ListedMod()
    assert mod.mod_type == ModType.UNKNOWN


def test_listed_mod_uuid() -> None:
    mod = ListedMod()
    assert mod.uuid != ""

    mod.mod_path = Path("path/to/mod")
    assert mod.uuid == str(Path("path/to/mod"))


def test_about_xml_mod_overall_rules() -> None:
    mod = AboutXmlMod()

    assert mod.overall_rules.load_before == set()
    assert mod.overall_rules.load_after == {}
    assert not mod.overall_rules.load_first
    assert not mod.overall_rules.load_last

    mod.about_rules.load_after = metadata_structure.CaseInsensitiveSet(["TestPackage"])
    assert mod.overall_rules.load_after == {}
    mod.clear_cache()
    assert mod.overall_rules.load_after == metadata_structure.CaseInsensitiveSet(
        ["TestPackage"]
    )

    mod.about_rules.load_after = metadata_structure.CaseInsensitiveSet(
        ["AnotherPackage", "testpackage"]
    )
    mod.clear_cache()
    assert mod.overall_rules.load_after == {"testpackage", "anotherpackage"}
    assert mod.overall_rules.load_before == set()

    mod.about_rules.load_before = metadata_structure.CaseInsensitiveSet(
        ["TestPackage1"]
    )
    mod.clear_cache()
    assert mod.overall_rules.load_before == metadata_structure.CaseInsensitiveSet(
        ["TestPackage1"]
    )

    mod.user_rules.load_before = metadata_structure.CaseInsensitiveSet(
        ["AnotherPackage1", "testpackage1"]
    )
    mod.community_rules.load_before = metadata_structure.CaseInsensitiveSet(
        ["AnotherPackage2", "testpackage2"]
    )
    mod.clear_cache()
    assert mod.overall_rules.load_before == {
        "testpackage1",
        "anotherpackage1",
        "testpackage2",
        "anotherpackage2",
    }

    mod.user_rules.load_first = True
    mod.clear_cache()
    assert mod.overall_rules.load_first
    assert not mod.overall_rules.load_last

    mod.community_rules.load_last = True
    mod.clear_cache()
    assert mod.overall_rules.load_first
    assert mod.overall_rules.load_last


def test_listed_mod_c_sharp_mod_default() -> None:
    mod = ListedMod()
    assert not mod.c_sharp_mod


def test_compiled_dependency_data_defaults() -> None:
    from app.models.metadata.metadata_structure import CompiledDependencyData

    compiled = CompiledDependencyData()
    assert compiled.deps_graph == {}
    assert compiled.rev_deps_graph == {}
    assert compiled.tier_zero_mods == set()
    assert compiled.tier_one_mods == set()
    assert compiled.tier_three_mods == set()
    assert compiled.incompatibilities == {}


def test_listed_mod_new_fields() -> None:
    mod = ListedMod()
    assert mod.obsolete is False
    assert mod.db_builder_no_name is False
    mod.obsolete = True
    mod.db_builder_no_name = True
    assert mod.obsolete is True
    assert mod.db_builder_no_name is True


class TestPublishedFileId:
    """Tests for ListedMod.published_file_id with corrupt/edge-case files."""

    def test_normal_id(self, tmp_path: Path) -> None:
        about = tmp_path / "About"
        about.mkdir()
        (about / "PublishedFileId.txt").write_text("1234567890")
        mod = ListedMod()
        mod.mod_path = tmp_path
        assert mod.published_file_id == "1234567890"

    def test_id_with_whitespace(self, tmp_path: Path) -> None:
        about = tmp_path / "About"
        about.mkdir()
        (about / "PublishedFileId.txt").write_text("  1234567890  \n")
        mod = ListedMod()
        mod.mod_path = tmp_path
        assert mod.published_file_id == "1234567890"

    def test_non_numeric_returns_none(self, tmp_path: Path) -> None:
        about = tmp_path / "About"
        about.mkdir()
        (about / "PublishedFileId.txt").write_text("not_a_number")
        mod = ListedMod()
        mod.mod_path = tmp_path
        assert mod.published_file_id is None

    def test_empty_file_returns_none(self, tmp_path: Path) -> None:
        about = tmp_path / "About"
        about.mkdir()
        (about / "PublishedFileId.txt").write_text("")
        mod = ListedMod()
        mod.mod_path = tmp_path
        assert mod.published_file_id is None

    def test_bom_handled(self, tmp_path: Path) -> None:
        """UTF-8 BOM is stripped by utf-8-sig encoding."""
        about = tmp_path / "About"
        about.mkdir()
        (about / "PublishedFileId.txt").write_bytes(b"\xef\xbb\xbf1234567890")
        mod = ListedMod()
        mod.mod_path = tmp_path
        assert mod.published_file_id == "1234567890"

    def test_concatenated_ids_returns_none(self, tmp_path: Path) -> None:
        """Two IDs without separator is not a valid numeric ID."""
        about = tmp_path / "About"
        about.mkdir()
        (about / "PublishedFileId.txt").write_text("1234567890 9876543210")
        mod = ListedMod()
        mod.mod_path = tmp_path
        assert mod.published_file_id is None

    def test_no_file_uses_folder_name(self, tmp_path: Path) -> None:
        mod_dir = tmp_path / "1617282896"
        mod_dir.mkdir()
        mod = ListedMod()
        mod.mod_path = mod_dir
        assert mod.published_file_id == "1617282896"

    def test_no_file_non_numeric_folder(self, tmp_path: Path) -> None:
        mod_dir = tmp_path / "my_cool_mod"
        mod_dir.mkdir()
        mod = ListedMod()
        mod.mod_path = mod_dir
        assert mod.published_file_id is None

    def test_no_path_returns_none(self) -> None:
        mod = ListedMod()
        assert mod.published_file_id is None


def _create_mod_with_about_xml(
    tmp_path: Path,
    folder_name: str = "test_mod",
    published_file_id: str | None = None,
) -> ListedMod:
    """Create a minimal mod directory and parse it, returning the ListedMod.

    :param tmp_path: pytest tmp_path fixture
    :param folder_name: Name for the mod directory
    :param published_file_id: If set, written to About/PublishedFileId.txt
    :return: Parsed ListedMod
    """
    from app.models.metadata.metadata_factory import create_listed_mod_from_path

    mod_path = tmp_path / folder_name
    mod_path.mkdir()
    about_dir = mod_path / "About"
    about_dir.mkdir()
    (about_dir / "About.xml").write_text("<ModMetaData><name>Test</name></ModMetaData>")
    if published_file_id is not None:
        (about_dir / "PublishedFileId.txt").write_text(published_file_id)

    _valid, mod = create_listed_mod_from_path(
        mod_path, "1.5", tmp_path, tmp_path, None, True
    )
    return mod


def test_published_file_id_returns_string(tmp_path: Path) -> None:
    """published_file_id should return str when PublishedFileId.txt exists."""
    mod = _create_mod_with_about_xml(tmp_path, published_file_id="123456789")
    assert mod.published_file_id == "123456789"
    assert isinstance(mod.published_file_id, str)


def test_published_file_id_returns_none_when_absent(tmp_path: Path) -> None:
    """published_file_id should return None when no PublishedFileId.txt."""
    mod = _create_mod_with_about_xml(tmp_path)
    assert mod.published_file_id is None


def test_published_file_id_from_folder_name(tmp_path: Path) -> None:
    """published_file_id should return folder name as string when numeric."""
    mod = _create_mod_with_about_xml(tmp_path, folder_name="987654321")
    assert mod.published_file_id == "987654321"


def test_published_file_id_strips_utf8_bom(tmp_path: Path) -> None:
    """published_file_id should strip a UTF-8 BOM prefix (GH-2150)."""
    from app.models.metadata.metadata_factory import create_listed_mod_from_path

    mod_path = tmp_path / "bom_mod"
    mod_path.mkdir()
    about_dir = mod_path / "About"
    about_dir.mkdir()
    (about_dir / "About.xml").write_text("<ModMetaData><name>Test</name></ModMetaData>")
    (about_dir / "PublishedFileId.txt").write_bytes(b"\xef\xbb\xbf3612563959")

    _valid, mod = create_listed_mod_from_path(
        mod_path, "1.5", tmp_path, tmp_path, None, True
    )
    assert mod.published_file_id == "3612563959"


def test_steam_db_entry_preserves_tags() -> None:
    """SteamDbEntry should preserve tags through serialization round-trip."""
    import msgspec

    entry = SteamDbEntry(
        packageId="test.mod",
        name="Test Mod",
        tags=[{"tag": "Translation"}, {"tag": "Mod"}],
    )
    encoded = msgspec.json.encode(entry)
    decoded = msgspec.json.decode(encoded, type=SteamDbEntry)
    assert decoded.tags == [{"tag": "Translation"}, {"tag": "Mod"}]


def test_steam_db_entry_tags_default_empty() -> None:
    """SteamDbEntry tags should default to empty list."""
    entry = SteamDbEntry()
    assert entry.tags == []
