import json
from pathlib import Path
from unittest.mock import MagicMock
from xml.etree import ElementTree

import pytest

from app.controllers.metadata_controller import MetadataController
from app.models.metadata.metadata_factory import (
    _legacy_package_id_from_xml,
    create_about_mod,
    create_listed_mod_from_path,
    read_mods_config,
)
from app.models.metadata.metadata_structure import AboutXmlMod
from app.services.window_manager import WindowManager
from app.utils.constants import DEFAULT_MISSING_PACKAGEID
from app.utils.schema import generate_rimworld_mods_list
from app.utils.xml import json_to_xml_write

REFERENCE_IDS = json.loads(
    (Path(__file__).parents[2] / "data" / "legacy_package_ids.json").read_text(
        encoding="utf-8"
    )
)


def _parse_xml(
    tmp_path: Path, data: dict[str, str], folder: str = "Legacy"
) -> AboutXmlMod:
    path = tmp_path / "Local" / folder
    about = path / "About"
    about.mkdir(parents=True)
    xml_path = about / "About.xml"
    root = ElementTree.Element("ModMetaData")
    for key, value in data.items():
        ElementTree.SubElement(root, key).text = value
    xml_path.write_bytes(ElementTree.tostring(root, encoding="utf-8"))
    original = xml_path.read_bytes()
    valid, mod = create_listed_mod_from_path(
        path, "1.6.4871", tmp_path / "Local", tmp_path / "Game", None
    )
    assert valid and isinstance(mod, AboutXmlMod)
    assert xml_path.read_bytes() == original
    return mod


@pytest.mark.parametrize("from_xml", [False, True])
@pytest.mark.parametrize("case", REFERENCE_IDS["cases"])
def test_legacy_game_identity(
    case: dict[str, str], from_xml: bool, tmp_path: Path
) -> None:
    """Use IDs captured from the game's actual TryParsePackageId method."""
    data = {key: value for key, value in case.items() if key != "expected"}
    if from_xml:
        mod = _parse_xml(tmp_path, data)
    else:
        valid, mod = create_about_mod(data, "1.6.4871")
        assert valid
    assert mod.package_id == case["expected"]


@pytest.mark.parametrize("package_id", ["", " "])
def test_empty_and_whitespace_xml_id(tmp_path: Path, package_id: str) -> None:
    mod = _parse_xml(
        tmp_path,
        {"name": "B", "author": "A", "description": "D", "packageId": package_id},
    )
    assert mod.package_id == "a781.b"


@pytest.mark.parametrize("case", REFERENCE_IDS["xml_cases"])
def test_game_xml_whitespace(case: dict[str, str], tmp_path: Path) -> None:
    mod = _parse_xml_bytes(tmp_path, case["xml"].encode("utf-8"))
    assert mod.package_id == case["expected"]


def _parse_xml_bytes(tmp_path: Path, xml: bytes) -> AboutXmlMod:
    path = tmp_path / "Local" / "Legacy"
    about = path / "About"
    about.mkdir(parents=True)
    xml_path = about / "About.xml"
    xml_path.write_bytes(xml)
    valid, mod = create_listed_mod_from_path(
        path, "1.6.4871", tmp_path / "Local", tmp_path / "Game", None
    )
    assert valid and isinstance(mod, AboutXmlMod)
    assert xml_path.read_bytes() == xml
    return mod


@pytest.mark.parametrize("package_id", [" ", 123, {"li": ["invalid", "id"]}])
def test_malformed_package_id_does_not_generate(package_id: object) -> None:
    _, mod = create_about_mod(
        {"author": "A", "name": "B", "packageId": package_id}, "1.6.4871"
    )
    assert mod.package_id == DEFAULT_MISSING_PACKAGEID


@pytest.mark.parametrize("encoding", ["shift_jis", "gb2312"])
def test_unsupported_xml_encoding_stays_unresolved(
    tmp_path: Path, encoding: str
) -> None:
    mod = _parse_xml_bytes(
        tmp_path,
        (
            f'<?xml version="1.0" encoding="{encoding}"?>'
            "<ModMetaData><author>A</author><name>B</name></ModMetaData>"
        ).encode("ascii"),
    )
    assert mod.package_id == DEFAULT_MISSING_PACKAGEID


@pytest.mark.parametrize("encoding", ["shift_jis", "gb2312", "notencoding"])
def test_raw_xml_encoding_failure_returns_unresolved(
    tmp_path: Path, encoding: str
) -> None:
    path = tmp_path / "About.xml"
    path.write_bytes(
        (
            f'<?xml version="1.0" encoding="{encoding}"?>'
            "<ModMetaData><author>A</author><name>B</name></ModMetaData>"
        ).encode("ascii")
    )
    assert _legacy_package_id_from_xml(path) is None


def test_custom_entities_stay_unresolved(tmp_path: Path) -> None:
    mod = _parse_xml_bytes(
        tmp_path,
        b'<!DOCTYPE ModMetaData [<!ENTITY d "D">]>'
        b"<ModMetaData><author>A</author><name>B</name>"
        b"<description>&d;</description></ModMetaData>",
    )
    assert mod.package_id == DEFAULT_MISSING_PACKAGEID


def test_duplicate_xml_fields_stay_unresolved(tmp_path: Path) -> None:
    mod = _parse_xml_bytes(
        tmp_path,
        b"<ModMetaData><author>A</author><name>B</name>"
        b'<description xml:space="preserve"> </description>'
        b"<description>D</description></ModMetaData>",
    )
    assert mod.package_id == DEFAULT_MISSING_PACKAGEID


@pytest.mark.parametrize("field", ["name", "author"])
def test_incomplete_legacy_metadata_stays_unresolved(field: str) -> None:
    data = {"name": "LegacyMod", "author": "LegacyAuthor"}
    del data[field]
    _, mod = create_about_mod(data, "1.6.4871")
    assert mod.package_id == DEFAULT_MISSING_PACKAGEID


def test_explicit_id_takes_precedence() -> None:
    _, mod = create_about_mod(
        {"author": "A", "name": "B", "packageId": "Author.Explicit"}, "1.6.4871"
    )
    assert mod.package_id == "author.explicit"


@pytest.mark.parametrize("field", ["author", "name", "description"])
def test_nested_xml_fields_stay_unresolved(tmp_path: Path, field: str) -> None:
    mod = _parse_xml(tmp_path, {"name": "B", "author": "A", "description": "D"})
    path = mod.mod_path
    assert path is not None
    xml_path = path / "About" / "About.xml"
    root = ElementTree.parse(xml_path).getroot()
    element = root.find(field)
    assert element is not None
    element.text = None
    ElementTree.SubElement(element, "li").text = "Nested"
    ElementTree.ElementTree(root).write(xml_path, encoding="utf-8")
    _, parsed = create_listed_mod_from_path(
        path, "1.6.4871", tmp_path / "Local", tmp_path / "Game", None
    )
    assert isinstance(parsed, AboutXmlMod)
    assert parsed.package_id == DEFAULT_MISSING_PACKAGEID


def test_legacy_xml_active_list_and_warnings(
    tmp_path: Path, mock_metadata_controller: MagicMock
) -> None:
    mods = {}
    for name in ("LegacyMod", "AnotherMod"):
        mod = _parse_xml(
            tmp_path,
            {"name": name, "author": "LegacyAuthor", "description": "D"},
            folder=name,
        )
        mods[str(mod.mod_path)] = mod
    mock_metadata_controller.mods_metadata = mods
    ids = ["legacyauthor781.legacymod", "legacyauthor781.anothermod"]
    config_path = tmp_path / "ModsConfig.xml"
    json_to_xml_write(generate_rimworld_mods_list("1.6.4871", ids), str(config_path))
    active, inactive, duplicates, missing = MetadataController.get_mods_from_list(
        mock_metadata_controller, str(config_path)
    )
    assert active == list(mods)
    assert inactive == []
    assert duplicates == {}
    assert missing == []
    assert WindowManager(mock_metadata_controller).get_missing_packageid_paths() == []
    config = read_mods_config(config_path)
    assert config is not None and config.activeMods == ids
