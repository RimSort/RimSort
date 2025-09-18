import gzip
import os
from typing import Any

import xmltodict
import zstandard as zstd
from bs4 import BeautifulSoup
from loguru import logger
from lxml import etree


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


def json_to_xml_write(
    data: dict[str, Any], path: str, raise_errs: bool = False
) -> None:
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
        if raise_errs:
            raise e
        logger.error(f"Error writing XML file: {e}")
        return

    logger.debug("Finished writing JSON to XML")


def extract_xml_package_ids(path: str) -> set[str]:
    """
    Extracts package ids between <modIds> and </modIds>.

    Compatible with gzip. (RimKeeper)

    :param path: Path to the XML file.
    :return: Set of package ids found in the XML file.
    """
    if not os.path.exists(path):
        logger.error(f"Path does not exist for XML package id extraction: {path}")
        return set()

    package_ids = set()
    found_modIds = False

    try:
        with __open_save_file(path) as file:
            context = etree.iterparse(file, events=("start", "end"))
            for event, elem in context:
                if not found_modIds and event == "start" and elem.tag == "modIds":
                    found_modIds = True
                elif event == "end" and elem.tag == "modIds":
                    text = (elem.text or "").strip()
                    if text != "":
                        package_ids.add(text)
                    elem.clear()
                    break

                if found_modIds and event == "end" and elem.tag == "li":
                    text = (elem.text or "").strip()
                    if text != "":
                        package_ids.add(text)
                    elem.clear()

        return package_ids

    except Exception as e:
        logger.error(f"Error running XML package id extraction: {e}")
        return set()


def fast_rimworld_xml_save_validation(path: str) -> bool:
    """
    Very quickly runs really basic structure validation of RimWorlds save.

    Checks we have the following tags (Each tag inside the previous one):

    <savegame>
        <meta>
            <modIds>
                <li>

    Compatible with gzip. (RimKeeper)

    :param path: Path to the XML file.
    :return: True if the XML file has the expected structure, False otherwise.
    """
    if not os.path.exists(path):
        logger.error(f"Path does not exist for RimWorld XML save validation: {path}")
        return False

    stack = []

    try:
        with __open_save_file(path) as file:
            context = etree.iterparse(file, events=("start", "end"))
            for event, elem in context:
                if event == "start":
                    stack.append(elem.tag)
                elif event == "end":
                    stack.pop()

                if stack == ["savegame", "meta", "modIds", "li"]:
                    return True

                if event == "end" and (
                    elem.tag == "modIds" or elem.tag == "meta" or elem.tag == "savegame"
                ):
                    # No package ids or save file format is not right
                    return False

                elem.clear()
    except Exception as e:
        logger.error(f"Error running RimWorld XML save validation: {e}")
        return False

    return False


def using_gzip(fp: str) -> bool:
    """
    RimKeeper compatibility. Check if dealing with gzip save file

    :param fp: File path to check.
    :return: True if the file is gzipped, False otherwise.
    """
    try:
        with open(fp, "rb") as f:
            return f.read(2) == b"\x1f\x8b"
    except Exception as e:
        logger.error(f"Failed checking if save file is using gzip: {e}")
        return False


def using_zstd(fp: str) -> bool:
    """
    Save File Compression compatibility. Check if dealing with zstd save file

    :param fp: File path to check.
    :return: True if the file is ZStandard zipped, False otherwise.
    """
    try:
        with open(fp, "rb") as f:
            return f.read(4) == b"\x28\xb5\x2f\xfd"
    except Exception as e:
        logger.error(f"Failed checking if save file is using zstd: {e}")
        return False


def __open_save_file(path: str) -> Any:
    """
    Open a save file.

    Compatible with gzip and zstd. (RimKeeper and Save File Compression)

    :param path: Path to the save file.
    :return: File object for the opened save file.
    """
    if using_gzip(path):
        return gzip.open(path, "rb")
    elif using_zstd(path):
        return zstd.open(path, "rb")
    else:
        return open(path, "rb")
