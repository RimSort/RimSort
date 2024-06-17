from pathlib import Path

from app.models.metadata.metadata_factory import (
    _parse_required,
    create_base_rules,
    create_mod_dependency,
    get_rules_db,
    match_version,
    value_extractor,
)
from app.models.metadata.metadata_structure import (
    CaseInsensitiveSet,
    ExternalRule,
    ExternalRulesSchema,
    LudeonMod,
    RuledMod,
    SubExternalBoolRule,
    SubExternalRule,
)
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
    assert value_extractor(input_dict) == input_dict


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


def test_match_version_found() -> None:
    # Test case: matching key is found
    input_dict = {"v1.2": "value1", "v1.3": "value2", "v1.4": "value3"}
    target_version = "1.3"
    assert match_version(input_dict, target_version) == (True, ["value2"])


def test_match_version_not_found() -> None:
    # Test case: matching key is not found
    input_dict = {"v1.2": "value1", "v1.3": "value2", "v1.4": "value3"}
    target_version = "1.5"
    assert match_version(input_dict, target_version) == (False, None)


def test_match_version_multiple_results() -> None:
    # Test case: multiple matching keys are found
    input_dict = {"v1.2": "value1", "v1.3": "value2", "v1.3.1": "value3"}
    target_version = "1.3"
    assert match_version(input_dict, target_version) == (True, ["value2", "value3"])


def test_match_version_multiple_results_stop_at_first() -> None:
    # Test case: stop_at_first parameter is set to True
    input_dict = {"v1.2": "value1", "v1.3": "value2", "v1.3.1": "value3"}
    target_version = "1.3"
    assert match_version(input_dict, target_version, stop_at_first=True) == (
        True,
        ["value2"],
    )


def test_create_mod_dependency() -> None:
    # Test case: valid input dictionary
    input_dict = {
        "packageId": "com.example.mod",
        "displayName": "Example Mod",
        "workshopUrl": "https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890",
    }
    mod = create_mod_dependency(input_dict)
    assert mod.package_id == "com.example.mod"
    assert mod.name == "Example Mod"
    assert (
        mod.workshop_url
        == "https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890"
    )


def test_create_mod_dependency_missing_fields() -> None:
    # Test case: missing fields in the input dictionary
    input_dict = {"packageId": "com.example.mod"}
    mod = create_mod_dependency(input_dict)
    assert mod.package_id == "com.example.mod"
    assert mod.name == "Unknown Mod Name"
    assert mod.workshop_url == ""


def test_create_base_rules_ludeon_core() -> None:
    # Test case: Ludeon Core
    path = Path("tests/data/mod_examples/Data/Core/About/About.xml")
    mod_data = xml_path_to_json(str(path))["ModMetaData"]
    rules = create_base_rules(mod_data, "1.5")

    assert rules.dependencies == {}
    assert rules.load_before == CaseInsensitiveSet(
        {"ludeon.rimworld.ideology", "ludeon.rimworld.royalty"}
    )
    assert rules.load_after == CaseInsensitiveSet()


def test_get_rules_db_large_db() -> None:
    path = Path("tests/data/dbs/large_rules.json")
    _ = get_rules_db(path)


def test_get_rules_db_values() -> None:
    path = Path("tests/data/dbs/userRules.json")
    rules = get_rules_db(path)

    expected_value = ExternalRulesSchema(
        timestamp=1715795801,
        rules={
            "test.test1": ExternalRule(
                loadAfter={},
                loadBefore={
                    "a.a": SubExternalRule(name="AA", comment="test1 load before"),
                    "b.b": SubExternalRule(name="aa", comment="test2 load before"),
                    "c.c.core": SubExternalRule(name="test3", comment=""),
                },
                loadTop=SubExternalBoolRule(False),
                loadBottom=SubExternalBoolRule(),
            ),
            "test.test2": ExternalRule(
                loadAfter={
                    "a.a": SubExternalRule(name="AA", comment="test1 load before"),
                    "b.b": SubExternalRule(name="aa", comment="test2 load before"),
                    "c.c.core": SubExternalRule(name="test3", comment=""),
                },
                loadBefore={},
                loadTop=SubExternalBoolRule(False),
                loadBottom=SubExternalBoolRule(value=True, comment="It is known."),
            ),
        },
    )

    assert rules == expected_value
