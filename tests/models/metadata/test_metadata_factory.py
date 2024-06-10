from pathlib import Path

from app.models.metadata.metadata_factory import (
    MalformedDataException,
    _parse_required,
    value_extractor,
)
from app.models.metadata.metadata_structure import LudeonMod, RuledMod
from app.utils.xml import xml_path_to_json


def test_value_extractor() -> None:
    # Test case 1: input is a string
    input_str_1 = "Hello, World!"
    assert value_extractor(input_str_1) == input_str_1

    # Test case 2: input is a list
    input_list_2 = ["apple", "banana", "cherry"]
    assert value_extractor(input_list_2) == input_list_2

    # Test case 3: input is a dictionary with "li" key
    input_dict_3 = {"li": ["apple", "banana", "cherry"]}
    assert value_extractor(input_dict_3) == input_dict_3["li"]

    # Test case 4: input is a dictionary with single key
    input_dict_4 = {"key": ["apple", "banana", "cherry"]}
    assert value_extractor(input_dict_4) == input_dict_4["key"]

    # Test case 5: input is a dictionary string value
    input_dict_5 = {"key": "apple"}
    assert value_extractor(input_dict_5) == input_dict_5["key"]

    # Test case 6: input is a dictionary with multiple keys
    input_dict_6 = {"li": "value", "key2": "value2"}
    try:
        value_extractor(input_dict_6)
        assert False, "MalformedDataException not raised"
    except MalformedDataException:
        pass

    # Test case 7: input is a dictionary with "li" key. Only one value list
    input_dict_7 = {"li": ["apple"]}
    assert value_extractor(input_dict_7) == input_dict_7["li"]

    # Test case 8: input is a dictionary with "li" key. Only one value
    input_dict_8 = {"li": "apple"}
    assert value_extractor(input_dict_8) == input_dict_8["li"]


def test_parse_required_ludeon() -> None:
    # Test parse required using data from data folder

    # Test case 1: Ludeon Core
    path = Path("tests/data/mod_examples/Data/Core/About/About.xml")
    mod_data = xml_path_to_json(str(path))["ModMetaData"]
    mod = _parse_required(mod_data, RuledMod())

    assert isinstance(mod, LudeonMod)
    assert mod.package_id == "ludeon.rimworld"
    assert mod.authors == ["Ludeon Studios"]
    assert mod.steam_app_id == 294100
    assert mod.valid

    # Test case 2: Ludeon Royalty
    path = Path("tests/data/mod_examples/Data/Royalty/About/About.xml")
    mod_data = xml_path_to_json(str(path))["ModMetaData"]
    mod = _parse_required(mod_data, RuledMod())

    assert isinstance(mod, LudeonMod)
    assert mod.package_id == "ludeon.rimworld.royalty"
    assert mod.authors == ["Ludeon Studios"]
    assert mod.steam_app_id == 1149640
    assert mod.supported_versions == {"1.5"}
    assert mod.valid

    # Test case 3 Ludeon Biotech
    path = Path("tests/data/mod_examples/Data/Biotech/About/About.xml")
    mod_data = xml_path_to_json(str(path))["ModMetaData"]
    mod = _parse_required(mod_data, RuledMod())

    assert isinstance(mod, LudeonMod)
    assert mod.package_id == "ludeon.rimworld.biotech"
    assert mod.authors == ["Ludeon Studios"]
    assert mod.steam_app_id == 1826140
    assert mod.supported_versions == {"1.5"}
    assert mod.valid

    # Test case - Future DLC (Unknown dlc not in constants). Has valid steam app id
    path = Path("tests/data/mod_examples/Data/FutureDLC/About/About.xml")
    mod_data = xml_path_to_json(str(path))["ModMetaData"]
    mod = _parse_required(mod_data, RuledMod())

    assert isinstance(mod, LudeonMod)
    assert mod.supported_versions == {"1.999999", "3.141"}
    assert mod.valid


def test_parse_required_non_ludeon() -> None:
    pass


def test_parse_required_invalid() -> None:
    pass
