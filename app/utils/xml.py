import os
from typing import Any, Dict
from bs4 import BeautifulSoup
import xmltodict
from loguru import logger


def xml_path_to_json(path: str) -> Dict[str, Any]:
    """
    Return the contents of an XML file as JSON.
    If the file does not exist, return an empty dict.

    :param path: Path to the XML file.
    :return: JSON dict of XML file contents.
    """
    if not os.path.exists(path):
        logger.error(f"XML file does not exist at: {path}")
        return {}

    logger.debug(f"Parsing XML file at: {path}")
    try:
        try:
            with open(path, "rb") as file:
                data = xmltodict.parse(file.read(), dict_constructor=dict)
        except Exception as e:
            logger.error(f"Error parsing XML file with xmltodict: {e}")
            logger.debug("Trying to parse with bs4 as a fallback")
            with open(path, "rb") as f:
                xml_data = f.read()
                soup = BeautifulSoup(xml_data, "lxml-xml")
                # Find and remove empty tags
                empty_tags = soup.find_all(
                    lambda tag: not tag.text.strip() or len(tag) == 0
                )
                for empty_tag in empty_tags:
                    empty_tag.extract()
                data = xmltodict.parse(str(soup), dict_constructor=dict)
                logger.debug(f"XML file parsed")
    except Exception as e:
        logger.error(f"Error parsing XML file with bs4: {e}")
        return {}

    logger.debug("XML file parsed successfully")
    return data


def json_to_xml_write(data: Dict[str, Any], path: str) -> None:
    """
    Write JSON data as an XML file.

    :param data: JSON data to write.
    :param path: Path to write the XML file to.
    """
    logger.debug("Started writing JSON to XML")
    try:
        xml_data = xmltodict.unparse(data, pretty=True)
        with open(path, "w", encoding="utf-8") as file:
            file.write(xml_data)
    except Exception as e:
        logger.error(f"Error writing XML file: {e}")
        return

    logger.debug("Finished writing JSON to XML")
