import gzip
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import zstandard as zstd

from app.utils.xml import (
    dict_to_etree,
    etree_to_dict,
    extract_xml_package_ids,
    fast_rimworld_xml_save_validation,
    json_to_xml_write,
    using_gzip,
    using_zstd,
    xml_path_to_json,
)


class TestEtreeToDict:
    def test_simple_element(self) -> None:
        root = ET.fromstring("<root><name>Test</name></root>")
        result = etree_to_dict(root)
        assert result == {"root": {"name": "Test"}}

    def test_nested_elements(self) -> None:
        root = ET.fromstring("<root><parent><child>value</child></parent></root>")
        result = etree_to_dict(root)
        assert result == {"root": {"parent": {"child": "value"}}}

    def test_element_with_attributes(self) -> None:
        root = ET.fromstring('<item id="42">content</item>')
        result = etree_to_dict(root)
        assert result == {"item": {"@id": "42", "#text": "content"}}

    def test_duplicate_children_become_list(self) -> None:
        root = ET.fromstring("<list><li>a</li><li>b</li><li>c</li></list>")
        result = etree_to_dict(root)
        assert result == {"list": {"li": ["a", "b", "c"]}}

    def test_empty_element(self) -> None:
        root = ET.fromstring("<root></root>")
        result = etree_to_dict(root)
        assert result == {"root": {}}

    def test_text_only_element(self) -> None:
        root = ET.fromstring("<tag>hello</tag>")
        result = etree_to_dict(root)
        assert result == {"tag": "hello"}


class TestDictToEtree:
    def test_simple_dict(self) -> None:
        d = {"root": {"name": "Test"}}
        elem = dict_to_etree(d)
        assert elem.tag == "root"
        assert elem.find("name") is not None
        assert elem.find("name").text == "Test"

    def test_dict_with_attributes(self) -> None:
        d = {"item": {"@id": "42", "#text": "content"}}
        elem = dict_to_etree(d)
        assert elem.tag == "item"
        assert elem.get("id") == "42"
        assert elem.text == "content"

    def test_list_children(self) -> None:
        d = {"list": {"li": [{"sub": "a"}, {"sub": "b"}]}}
        elem = dict_to_etree(d)
        items = elem.findall("li")
        assert len(items) == 2

    def test_roundtrip(self) -> None:
        original = {"root": {"child": "value", "nested": {"inner": "deep"}}}
        elem = dict_to_etree(original)
        result = etree_to_dict(elem)
        assert result == original

    def test_rejects_multi_root(self) -> None:
        with pytest.raises(AssertionError):
            dict_to_etree({"a": "1", "b": "2"})


class TestXmlPathToJson:
    def test_simple_xml_file(self, tmp_path: Path) -> None:
        xml_file = tmp_path / "test.xml"
        xml_file.write_text('<?xml version="1.0"?><root><name>Test</name></root>')
        result = xml_path_to_json(str(xml_file))
        assert result == {"root": {"name": "Test"}}

    def test_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        result = xml_path_to_json(str(tmp_path / "missing.xml"))
        assert result == {}

    def test_gzip_compressed_xml(self, tmp_path: Path) -> None:
        xml_content = b'<?xml version="1.0"?><root><data>gzipped</data></root>'
        gz_file = tmp_path / "test.xml.gz"
        with gzip.open(gz_file, "wb") as f:
            f.write(xml_content)
        result = xml_path_to_json(str(gz_file))
        assert result == {"root": {"data": "gzipped"}}

    def test_zstd_compressed_xml(self, tmp_path: Path) -> None:
        xml_content = b'<?xml version="1.0"?><root><data>zstd</data></root>'
        zstd_file = tmp_path / "test.xml.zst"
        cctx = zstd.ZstdCompressor()
        with open(zstd_file, "wb") as f:
            f.write(cctx.compress(xml_content))
        result = xml_path_to_json(str(zstd_file))
        assert result == {"root": {"data": "zstd"}}

    def test_malformed_xml_falls_back_to_beautifulsoup(self, tmp_path: Path) -> None:
        xml_file = tmp_path / "bad.xml"
        xml_file.write_text("<root><name>Test</name><unclosed>")
        result = xml_path_to_json(str(xml_file))
        assert isinstance(result, dict)


class TestJsonToXmlWrite:
    def test_write_and_read_roundtrip(self, tmp_path: Path) -> None:
        data = {"config": {"setting": "value"}}
        out_path = str(tmp_path / "output.xml")
        json_to_xml_write(data, out_path)
        result = xml_path_to_json(out_path)
        assert result == data

    def test_write_raises_on_error_when_requested(self, tmp_path: Path) -> None:
        with pytest.raises(Exception):
            json_to_xml_write(
                {"a": "1", "b": "2"}, str(tmp_path / "out.xml"), raise_errs=True
            )

    def test_write_swallows_error_by_default(self, tmp_path: Path) -> None:
        json_to_xml_write({"a": "1", "b": "2"}, str(tmp_path / "out.xml"))


class TestCompressionDetection:
    def test_using_gzip_true(self, tmp_path: Path) -> None:
        gz_file = tmp_path / "test.gz"
        with gzip.open(gz_file, "wb") as f:
            f.write(b"content")
        assert using_gzip(str(gz_file)) is True

    def test_using_gzip_false(self, tmp_path: Path) -> None:
        plain_file = tmp_path / "test.txt"
        plain_file.write_text("plain text")
        assert using_gzip(str(plain_file)) is False

    def test_using_zstd_true(self, tmp_path: Path) -> None:
        zstd_file = tmp_path / "test.zst"
        cctx = zstd.ZstdCompressor()
        with open(zstd_file, "wb") as f:
            f.write(cctx.compress(b"content"))
        assert using_zstd(str(zstd_file)) is True

    def test_using_zstd_false(self, tmp_path: Path) -> None:
        plain_file = tmp_path / "test.txt"
        plain_file.write_text("plain text")
        assert using_zstd(str(plain_file)) is False

    def test_using_gzip_nonexistent(self, tmp_path: Path) -> None:
        assert using_gzip(str(tmp_path / "nope")) is False

    def test_using_zstd_nonexistent(self, tmp_path: Path) -> None:
        assert using_zstd(str(tmp_path / "nope")) is False


VALID_SAVEGAME_XML = """\
<?xml version="1.0"?>
<savegame>
  <meta>
    <modIds>
      <li>ludeon.rimworld</li>
      <li>brrainz.harmony</li>
    </modIds>
  </meta>
</savegame>
"""


class TestExtractXmlPackageIds:
    def test_extracts_package_ids(self, tmp_path: Path) -> None:
        save_file = tmp_path / "save.rws"
        save_file.write_text(VALID_SAVEGAME_XML)
        result = extract_xml_package_ids(str(save_file))
        assert result == {"ludeon.rimworld", "brrainz.harmony"}

    def test_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        result = extract_xml_package_ids(str(tmp_path / "missing.rws"))
        assert result == set()

    def test_no_modIds_returns_empty(self, tmp_path: Path) -> None:
        xml_file = tmp_path / "no_mods.xml"
        xml_file.write_text("<savegame><meta></meta></savegame>")
        result = extract_xml_package_ids(str(xml_file))
        assert result == set()

    def test_gzip_savefile(self, tmp_path: Path) -> None:
        gz_file = tmp_path / "save.rws.gz"
        with gzip.open(gz_file, "wb") as f:
            f.write(VALID_SAVEGAME_XML.encode())
        result = extract_xml_package_ids(str(gz_file))
        assert result == {"ludeon.rimworld", "brrainz.harmony"}


class TestFastRimworldXmlSaveValidation:
    def test_valid_save(self, tmp_path: Path) -> None:
        save_file = tmp_path / "save.rws"
        save_file.write_text(VALID_SAVEGAME_XML)
        assert fast_rimworld_xml_save_validation(str(save_file)) is True

    def test_invalid_structure(self, tmp_path: Path) -> None:
        save_file = tmp_path / "bad.rws"
        save_file.write_text("<root><data>not a save</data></root>")
        assert fast_rimworld_xml_save_validation(str(save_file)) is False

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        assert fast_rimworld_xml_save_validation(str(tmp_path / "nope")) is False

    def test_empty_modids(self, tmp_path: Path) -> None:
        save_file = tmp_path / "empty.rws"
        save_file.write_text("<savegame><meta><modIds></modIds></meta></savegame>")
        assert fast_rimworld_xml_save_validation(str(save_file)) is False
