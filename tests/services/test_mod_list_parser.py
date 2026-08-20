from pathlib import Path

from app.services.mod_list_parser import ModListFormatError, parse_mod_list_file

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

    def test_parse_single_li_xml(self) -> None:
        parsed = parse_mod_list_file(FIXTURES / "single_li.xml")
        assert parsed.package_ids == ["ludeon.rimworld"]

    def test_invalid_file_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.txt"
        bad.write_text("not a mod list", encoding="utf-8")
        try:
            parse_mod_list_file(bad)
            assert False, "expected ModListFormatError"
        except ModListFormatError:
            pass
