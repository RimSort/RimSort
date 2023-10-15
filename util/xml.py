import os
from typing import Any, Dict

from bs4 import BeautifulSoup
import xmltodict

from logger_tt import logger


def xml_path_to_json(path: str) -> Dict[str, Any]:
    """
    Return the contents of an xml file as json.
    If the file does not exist, return an empty dict.

    :param path: path to the xml file
    :return: json dict of xml file contents
    """
    data: Dict[str, Any] = {}
    if os.path.exists(path):
        logger.debug(f"Parsing XML file at: {path}")
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
    else:
        logger.error(f"XML file does not exist at: {path}")
    return data


def json_to_xml_write(data: Dict[str, Any], path: str) -> None:
    """
    Write json data as an xml file.

    :param data: json data to write
    :param path: path to write the xml file to
    """
    logger.debug("Started writing JSON to XML")
    new_xml_data = xmltodict.unparse(data, pretty=True, newl="\n", indent="  ")
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_xml_data)
    logger.debug("Finished writing JSON to XML")
