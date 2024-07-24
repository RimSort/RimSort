import os
from typing import Any

import xmltodict
from bs4 import BeautifulSoup
from loguru import logger


def xml_path_to_json(path: str) -> dict[str, Any]:
    """
    Return the contents of an XML file as JSON.
    If the file does not exist, return an empty dict.

    :param path: Path to the XML file.
    :return: JSON dict of XML file contents.
    """
    data: dict[str, Any] = {}
    if not os.path.exists(path):
        logger.error(f"XML file does not exist at: {path}")
        return data
    try:
        try:
            # Try parsing the XML file using xmltodict
            with open(path, "rb") as file:
                data = xmltodict.parse(file.read(), dict_constructor=dict)
        except Exception as e:
            # If xmltodict parsing fails, attempt parsing with BeautifulSoup
            logger.debug(f"Error parsing XML file with xmltodict: {e}")
            logger.debug("Trying to parse with BeautifulSoup as a fallback")
            with open(path, "rb") as f:
                soup = BeautifulSoup(f.read(), "lxml-xml")
                # Find and remove empty tags
                empty_tags = soup.find_all(
                    lambda tag: not tag.text.strip() or len(tag) == 0
                )
                for empty_tag in empty_tags:
                    empty_tag.extract()
                # Convert the BeautifulSoup object to a dictionary using xmltodict
                data = xmltodict.parse(str(soup), dict_constructor=dict)
        # Return the parsed data
        return data
    except Exception as e:
        logger.debug(f"Error parsing XML file with BeautifulSoup: {e}")
        logger.error(f"Error parsing XML file: {path}")
        return data


def json_to_xml_write(data: dict[str, Any], path: str) -> None:
    """
    Write JSON data to an XML file.

    :param data: JSON data to write.
    :param path: Path to write the XML file to.
    """
    logger.debug("Started writing JSON to XML")
    try:
        # Convert JSON data to XML format using xmltodict
        xml_data = xmltodict.unparse(data, pretty=True)
        # Write the XML data to the specified file path
        with open(path, "w", encoding="utf-8") as file:
            file.write(xml_data)
    except Exception as e:
        logger.error(f"Error writing XML file: {e}")
        return

    logger.debug("Finished writing JSON to XML")
