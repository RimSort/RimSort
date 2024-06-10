from pathlib import Path

from app.models.metadata.metadata_factory import (
    MalformedDataException,
    _parse_required,
    value_extractor,
)
from app.models.metadata.metadata_structure import LudeonMod, RuledMod
from app.utils.xml import xml_path_to_json


def test_value_extractor_string() -> None:
    # Test case: input is a string
    input_str = "Hello, World!"
    assert value_extractor(input_str) == input_str


def test_value_extractor_list() -> None:
    # Test case: input is a list
    input_list = ["apple", "banana", "cherry"]
    assert value_extractor(input_list) == input_list


def test_value_extractor_dict_li() -> None:
    # Test case: input is a dictionary with "li" key
    input_dict = {"li": ["apple", "banana", "cherry"]}
    assert value_extractor(input_dict) == input_dict["li"]


def test_value_extractor_dict_single_key() -> None:
    # Test case: input is a dictionary with single key
    input_dict = {"key": ["apple", "banana", "cherry"]}
    assert value_extractor(input_dict) == input_dict["key"]


def test_value_extractor_dict_string_value() -> None:
    # Test case: input is a dictionary string value
    input_dict = {"key": "apple"}
    assert value_extractor(input_dict) == input_dict["key"]


def test_value_extractor_dict_multiple_keys() -> None:
    # Test case: input is a dictionary with multiple keys
    input_dict = {"li": "value", "key2": "value2"}
    try:
        value_extractor(input_dict)
        assert False, "MalformedDataException not raised"
    except MalformedDataException:
        pass


def test_value_extractor_dict_li_one_value_list() -> None:
    # Test case: input is a dictionary with "li" key. Only one value list
    input_dict = {"li": ["apple"]}
    assert value_extractor(input_dict) == input_dict["li"]


def test_value_extractor_dict_li_one_value() -> None:
    # Test case: input is a dictionary with "li" key. Only one value
    input_dict = {"li": "apple"}
    assert value_extractor(input_dict) == input_dict["li"]


def test_value_extractor_ignore_if_no_matching_field() -> None:
    # Test case: Ignore if no matching field
    input_dict = {"@IgnoreIfNoMatchingField": "True", "#text": "input text"}
    assert value_extractor(input_dict) == input_dict["#text"]


def test__parse_required_ludeon_core() -> None:
    # Test parse required using data from data folder - Ludeon Core
    path = Path("tests/data/mod_examples/Data/Core/About/About.xml")
    mod_data = xml_path_to_json(str(path))["ModMetaData"]
    mod = _parse_required(mod_data, RuledMod())

    assert isinstance(mod, LudeonMod)
    assert mod.package_id == "ludeon.rimworld"
    assert mod.authors == ["Ludeon Studios"]
    assert mod.steam_app_id == 294100
    assert mod.valid


def test__parse_required_ludeon_royalty() -> None:
    # Test parse required using data from data folder - Ludeon Royalty
    path = Path("tests/data/mod_examples/Data/Royalty/About/About.xml")
    mod_data = xml_path_to_json(str(path))["ModMetaData"]
    mod = _parse_required(mod_data, RuledMod())

    assert isinstance(mod, LudeonMod)
    assert mod.package_id == "ludeon.rimworld.royalty"
    assert mod.authors == ["Ludeon Studios"]
    assert mod.steam_app_id == 1149640
    assert mod.supported_versions == {"1.5"}
    assert mod.valid


def test__parse_required_ludeon_biotech() -> None:
    # Test parse required using data from data folder - Ludeon Biotech
    path = Path("tests/data/mod_examples/Data/Biotech/About/About.xml")
    mod_data = xml_path_to_json(str(path))["ModMetaData"]
    mod = _parse_required(mod_data, RuledMod())

    assert isinstance(mod, LudeonMod)
    assert mod.package_id == "ludeon.rimworld.biotech"
    assert mod.authors == ["Ludeon Studios"]
    assert mod.steam_app_id == 1826140
    assert mod.supported_versions == {"1.5"}
    assert mod.valid


def test__parse_required_future_dlc() -> None:
    # Test parse required using data from data folder - Future DLC (Unknown dlc not in constants). Has valid steam app id
    path = Path("tests/data/mod_examples/Data/FutureDLC/About/About.xml")
    mod_data = xml_path_to_json(str(path))["ModMetaData"]
    mod = _parse_required(mod_data, RuledMod())

    assert isinstance(mod, LudeonMod)
    assert mod.supported_versions == {"1.999999", "3.141"}
    assert mod.valid


def test__parse_required_local_fishery() -> None:
    # Test case: Fishery mod
    path = Path("tests/data/mod_examples/Local/Fishery/About/About.xml")
    mod_data = xml_path_to_json(str(path))["ModMetaData"]
    mod = _parse_required(mod_data, RuledMod())

    assert isinstance(mod, RuledMod)
    assert mod.package_id == "bs.fishery"
    assert mod.name == "Fishery - Modding Library"
    assert mod.authors == ["bradson"]
    assert mod.supported_versions == {"1.2", "1.3", "1.4", "1.5"}
    assert mod.valid


def test_parse_required_invalid() -> None:
    pass
