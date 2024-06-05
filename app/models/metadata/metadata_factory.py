import traceback
from typing import Any, Sequence

from loguru import logger

from app.models.metadata.metadata_structure import ListedMod
from app.utils.xml import xml_path_to_json


class MalformedDataException(Exception):
    """
    Exception raised when the data given is detected to be malformed.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = f"Malformed data: {message}"


def value_extractor(
    input: dict[str, str] | dict[str, list[str]] | Sequence[str] | str,
) -> str | list[str]:
    """
    Extract the value from a mod_data entry. Stops at the outermost list or string.

    :param input: The dictionary or string or list of strings to extract the value from.
    :return: The extracted value or the input string.
    :raises:

    """

    if isinstance(input, str):
        return input
    elif isinstance(input, Sequence):
        # Convert sequence to list
        return list(input)
    elif isinstance(input, dict):
        # If only one key, recurse into the value
        if len(input) == 1:
            return value_extractor(next(iter(input.values())))
        else:
            raise MalformedDataException(
                f"Could not extract value from {input}. More than one key found."
            )


def create_listed_mod(mod_data: dict[str, Any], target_version: str) -> tuple[bool, ListedMod]:
    """Factory method for creating a ListedMod object."""
    raise NotImplementedError


def create_listed_mod_from_xml(mod_xml_path: str, target_version: str) -> tuple[bool, ListedMod]:
    try:
        mod_data = xml_path_to_json(mod_xml_path)
    except Exception:
        logger.error(
            f"Unable to parse {mod_xml_path} with the exception: {traceback.format_exc()}"
        )
        return False, ListedMod()

    return create_listed_mod(mod_data, target_version)
