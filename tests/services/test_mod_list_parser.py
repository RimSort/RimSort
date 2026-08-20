from pathlib import Path

import pytest

from app.services.mod_list_parser import (
    ModListFormatError,
    ParsedModList,
    parse_mod_list_file,
    parsed_to_mods_config_dict,
)

FIXTURES = Path(__file__).parent.parent / "data" / "mod_lists"


class TestModListParser:
    def test_parse_mods_config_xml(self) -> None:
        parsed = parse_mod_list_file(FIXTURES / "mods_config.xml")
        assert parsed.source_format == "mods_config_xml"
        assert "author.testmod" in parsed.package_ids
        assert parsed.game_version == "1.5"

    def test_parse_rimsort_json_with_xml_extension(self) -> None:
        parsed = parse_mod_list_file(FIXTURES / "rimsort_json.xml")
        assert parsed.source_format == "rimsort_json"
        assert parsed.package_ids == ["ludeon.rimworld", "author.jsonmod"]

    def test_parse_empty_mods_config_xml(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.xml"
        empty.write_text("<ModsConfigData></ModsConfigData>", encoding="utf-8")
        parsed = parse_mod_list_file(empty)
        assert parsed.source_format == "mods_config_xml"
        assert parsed.package_ids == []
        assert parsed.known_expansions == []

    def test_parse_mods_config_without_active_mods(self, tmp_path: Path) -> None:
        xml = tmp_path / "no_active.xml"
        xml.write_text(
            "<ModsConfigData><version>1.6</version></ModsConfigData>",
            encoding="utf-8",
        )
        parsed = parse_mod_list_file(xml)
        assert parsed.package_ids == []
        assert parsed.game_version == "1.6"

    def test_parse_empty_known_expansions_object(self, tmp_path: Path) -> None:
        xml = tmp_path / "empty_expansions.xml"
        xml.write_text(
            "<ModsConfigData><knownExpansions></knownExpansions></ModsConfigData>",
            encoding="utf-8",
        )
        parsed = parse_mod_list_file(xml)
        assert parsed.known_expansions == []

    def test_parse_single_li_xml(self) -> None:
        parsed = parse_mod_list_file(FIXTURES / "single_li.xml")
        assert parsed.package_ids == ["ludeon.rimworld"]

    def test_invalid_file_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.txt"
        bad.write_text("not a mod list", encoding="utf-8")
        with pytest.raises(ModListFormatError):
            parse_mod_list_file(bad)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ModListFormatError, match="File not found"):
            parse_mod_list_file(tmp_path / "does_not_exist.xml")

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        bad_json = tmp_path / "broken.json"
        bad_json.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ModListFormatError, match="Invalid JSON"):
            parse_mod_list_file(bad_json)

    def test_json_array_unrecognized(self, tmp_path: Path) -> None:
        array_json = tmp_path / "array.json"
        array_json.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(ModListFormatError, match="Unrecognized mod list format"):
            parse_mod_list_file(array_json)

    def test_json_missing_required_keys_raises(self, tmp_path: Path) -> None:
        incomplete = tmp_path / "incomplete.json"
        incomplete.write_text('{"version": "1.5"}', encoding="utf-8")
        with pytest.raises(ModListFormatError, match="activeMods"):
            parse_mod_list_file(incomplete)

    def test_json_non_string_version(self, tmp_path: Path) -> None:
        json_path = tmp_path / "numeric_version.json"
        json_path.write_text(
            '{"version": 1.5, "activeMods": ["author.test"], "knownExpansions": []}',
            encoding="utf-8",
        )
        parsed = parse_mod_list_file(json_path)
        assert parsed.source_format == "rimsort_json"
        assert parsed.game_version == "1.5"
        assert parsed.package_ids == ["author.test"]

    def test_savegame_xml_source_format(self, tmp_path: Path) -> None:
        save_xml = tmp_path / "save.xml"
        save_xml.write_text(
            "<savegame><ModsConfigData><version>1.4</version></ModsConfigData></savegame>",
            encoding="utf-8",
        )
        parsed = parse_mod_list_file(save_xml)
        assert parsed.source_format == "savegame"
        assert parsed.package_ids == []

    def test_rws_suffix_source_format(self, tmp_path: Path) -> None:
        rws = tmp_path / "list.rws"
        rws.write_text(
            "<ModsConfigData><version>1.4</version></ModsConfigData>",
            encoding="utf-8",
        )
        parsed = parse_mod_list_file(rws)
        assert parsed.source_format == "rws"

    def test_rml_suffix_source_format(self, tmp_path: Path) -> None:
        rml = tmp_path / "list.rml"
        rml.write_text(
            "<ModsConfigData><version>1.4</version></ModsConfigData>",
            encoding="utf-8",
        )
        parsed = parse_mod_list_file(rml)
        assert parsed.source_format == "rml"

    def test_parsed_to_mods_config_dict_default_version(self) -> None:
        parsed = ParsedModList(
            package_ids=["author.test"],
            game_version=None,
            known_expansions=[],
            source_format="mods_config_xml",
        )
        result = parsed_to_mods_config_dict(parsed)
        assert result["ModsConfigData"]["version"] == "1.4"
        assert result["ModsConfigData"]["activeMods"]["li"] == ["author.test"]
        assert result["ModsConfigData"]["knownExpansions"]["li"] == []

    def test_parsed_to_mods_config_dict_with_version(self) -> None:
        parsed = ParsedModList(
            package_ids=["a.b", "c.d"],
            game_version="1.6",
            known_expansions=["Ludeon.RimWorld"],
            source_format="mods_config_xml",
        )
        result = parsed_to_mods_config_dict(parsed)
        assert result["ModsConfigData"]["version"] == "1.6"
        assert result["ModsConfigData"]["activeMods"]["li"] == ["a.b", "c.d"]
        assert result["ModsConfigData"]["knownExpansions"]["li"] == [
            "Ludeon.RimWorld"
        ]
