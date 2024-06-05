from app.models.metadata.metadata_factory import MalformedDataException, value_extractor


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
    input_dict_6= {"li": "value", "key2": "value2"}
    try:
        value_extractor(input_dict_6)
        assert False, "MalformedDataException not raised"
    except MalformedDataException:
        pass
