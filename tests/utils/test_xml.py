import errno
import gzip
import os
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from contextlib import contextmanager
from io import TextIOWrapper
from pathlib import Path
from unittest.mock import patch

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
        data = {"ModsConfigData": {"activeMods": {"li": ["ludeon.rimworld", "é.mod"]}}}
        target = tmp_path / "ModsConfig.xml"
        json_to_xml_write(data, str(target), raise_errs=True)

        expected_xml = (
            '<?xml version="1.0" ?>\n'
            "<ModsConfigData>\n"
            "  <activeMods>\n"
            "    <li>ludeon.rimworld</li>\n"
            "    <li>é.mod</li>\n"
            "  </activeMods>\n"
            "</ModsConfigData>\n"
        )
        assert target.read_bytes() == expected_xml.replace("\n", os.linesep).encode(
            "utf-8"
        )
        assert xml_path_to_json(str(target)) == data
        assert list(tmp_path.iterdir()) == [target]

    def test_mid_write_failure_preserves_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "ModsConfig.xml"
        original = b"<ModsConfigData><activeMods/></ModsConfigData>\n"
        target.write_bytes(original)
        mode = target.stat().st_mode

        @contextmanager
        def failing_open(
            file: str | int, mode: str, *, encoding: str, closefd: bool = True
        ) -> Iterator[TextIOWrapper]:
            assert mode == "w"
            with open(file, "w", encoding=encoding, closefd=closefd) as stream:
                write = stream.write

                def write_prefix_then_fail(data: str) -> int:
                    write(data[:10])
                    stream.flush()
                    raise OSError("injected disk write failure")

                with patch.object(stream, "write", side_effect=write_prefix_then_fail):
                    yield stream

        monkeypatch.setattr("app.utils.xml.open", failing_open, raising=False)
        with pytest.raises(OSError, match="injected disk write failure"):
            json_to_xml_write(
                {"ModsConfigData": {"version": "1.6"}}, str(target), raise_errs=True
            )

        assert target.read_bytes() == original
        assert target.stat().st_mode == mode
        assert list(tmp_path.iterdir()) == [target]

    def test_stream_open_failure_closes_and_removes_staging_file(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "ModsConfig.xml"
        original = b"<ModsConfigData/>"
        target.write_bytes(original)

        with (
            patch(
                "app.utils.xml.open",
                side_effect=PermissionError("injected stream open failure"),
                create=True,
            ) as failed_open,
            pytest.raises(PermissionError, match="injected stream open failure"),
        ):
            json_to_xml_write(
                {"ModsConfigData": {"version": "1.6"}}, str(target), raise_errs=True
            )
        assert failed_open.call_args is not None
        fd = failed_open.call_args.args[0]
        with pytest.raises(OSError) as error:
            os.fstat(fd)
        assert error.value.errno == errno.EBADF
        assert target.read_bytes() == original
        assert list(tmp_path.iterdir()) == [target]

    def test_replace_failure_preserves_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "ModsConfig.xml"
        original = b"<ModsConfigData><activeMods/></ModsConfigData>\n"
        target.write_bytes(original)
        mode = target.stat().st_mode
        data = {"ModsConfigData": {"version": "1.6"}}

        def fail_replace(source: str, destination: str) -> None:
            staging = Path(source)
            assert staging.parent == target.parent.resolve()
            assert xml_path_to_json(source) == data
            assert Path(destination).read_bytes() == original
            raise PermissionError("injected replacement failure")

        monkeypatch.setattr(os, "replace", fail_replace)
        with (
            patch("app.utils.json_utils.time.sleep") as sleep,
            pytest.raises(PermissionError, match="injected replacement failure"),
        ):
            json_to_xml_write(data, str(target), raise_errs=True)

        assert sleep.call_count == 4
        assert target.read_bytes() == original
        assert target.stat().st_mode == mode
        assert list(tmp_path.iterdir()) == [target]

    def test_write_through_config_symlink(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "data"
        config_dir.mkdir()
        target = config_dir / "ModsConfig.xml"
        target.write_bytes(b"<ModsConfigData/>")
        if sys.platform != "win32":
            target.chmod(0o640)
        mode = target.stat().st_mode

        link = tmp_path / "ModsConfig.xml"
        link_target = target.relative_to(tmp_path)
        try:
            link.symlink_to(link_target)
        except OSError as error:
            if getattr(error, "winerror", None) == 1314:
                pytest.skip(
                    "Windows symlink creation requires Developer Mode or privilege"
                )
            raise

        data = {"ModsConfigData": {"version": "1.6"}}
        json_to_xml_write(data, str(link), raise_errs=True)

        assert link.readlink() == link_target
        assert target.stat().st_mode == mode
        assert xml_path_to_json(str(target)) == data
        assert list(config_dir.iterdir()) == [target]

    def test_write_preserves_locked_config(self, tmp_path: Path) -> None:
        if sys.platform != "win32":
            pytest.skip("Windows file sharing semantics")
        target = tmp_path / "ModsConfig.xml"
        original = b"<ModsConfigData/>"
        target.write_bytes(original)
        before = target.stat()

        with target.open("rb"), pytest.raises(PermissionError):
            json_to_xml_write(
                {"ModsConfigData": {"version": "1.6"}}, str(target), raise_errs=True
            )

        assert target.read_bytes() == original
        assert target.stat().st_file_attributes == before.st_file_attributes
        assert list(tmp_path.iterdir()) == [target]

    def test_write_preserves_read_only_config(self, tmp_path: Path) -> None:
        target = tmp_path / "ModsConfig.xml"
        original = b"<ModsConfigData/>"
        target.write_bytes(original)
        target.chmod(0o444)
        before = target.stat()
        try:
            if os.access(target, os.W_OK):
                pytest.skip("Process can write to read-only files")
            with pytest.raises(PermissionError):
                json_to_xml_write(
                    {"ModsConfigData": {"version": "1.6"}}, str(target), raise_errs=True
                )
            assert target.read_bytes() == original
            after = target.stat()
            assert after.st_mode == before.st_mode
            if sys.platform == "win32":
                assert after.st_file_attributes == before.st_file_attributes
            assert list(tmp_path.iterdir()) == [target]
        finally:
            target.chmod(0o600)

    def test_write_raises_on_error_when_requested(self, tmp_path: Path) -> None:
        with pytest.raises(Exception):  # noqa: B017
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
