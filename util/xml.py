import os
from typing import Any, Dict

import xmltodict
from util.error import show_warning

import logging

logger = logging.getLogger(__name__)


def xml_path_to_json(path: str) -> Dict[str, Any]:
    """
    Return the contents of an xml file as json.
    If the file does not exist, return an empty dict.

    :param path: path to the xml file
    :return: json dict of xml file contents
    """
    data = {}
    if os.path.exists(path):
        logging.info(f"Parsing XML file at: {path}")
        with open(path, encoding="utf-8") as f:
            data = xmltodict.parse(f.read())
            logging.debug(f"XML file parsed with the following data: {data}")
    else:
        logging.error(f"XML file does not exist at: {path}")
    return data


def non_utf8_xml_path_to_json(path: str) -> Dict[str, Any]:
    """
    Return the contents of an xml file as json. The xml
    may have some non utf-8 characters.
    If the file does not exist, return an empty dict.

    :param path: path to the xml file
    :return: json dict of xml file contents
    """
    data = {}
    if os.path.exists(path):
        logging.info(f"Parsing non UTF-8 XML file at: {path}")
        data = xmltodict.parse(fix_non_utf8_xml(path))
        logging.debug(f"XML file parsed with the following data: {data}")
    else:
        logging.error(f"Non UTF-8 XML file does not exist at: {path}")
    return data


def fix_non_utf8_xml(path: str) -> str:
    """
    Fixes files that are supposed to be UTF-8, but
    somehow are not. Iterates through every line and
    attempts to encode as UTF-8, ignoring cases that cannot
    be encoded. Then decodes. Does not directly modify the
    file itself.

    :param path: path to the problematic file
    :return: the contents of the file
    """
    logger.info("Transforming non UTF-8 XML")
    t = ""
    with open(path, "rb") as problematic_file:
        t = problematic_file.read()
    r = t.decode("utf-8", "ignore").encode("utf-8")
    return r


def json_to_xml_write(data: Dict[str, Any], path: str) -> None:
    """
    Write json data as an xml file.

    :param data: json data to write
    :param path: path to write the xml file to
    """
    new_xml_data = xmltodict.unparse(data, pretty=True, newl="\n", indent="  ")
    with open(path, "w") as f:
        f.write(new_xml_data)
