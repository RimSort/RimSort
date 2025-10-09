import gzip
import os
import xml.dom.minidom as minidom
import xml.etree.ElementTree as ET
from typing import Any

import zstandard as zstd
from bs4 import BeautifulSoup
from loguru import logger


def etree_to_dict(t: Any) -> dict[str, Any]:
    """
    Convert xml.etree.ElementTree element to a dictionary.
    """
    d: dict[str, Any] = {str(t.tag): {}}
    children = list(t)
    if children:
        dd: dict[str, Any] = {}
        for dc in map(etree_to_dict, children):
            for k, v in dc.items():
                if k in dd:
                    if not isinstance(dd[k], list):
                        dd[k] = [dd[k]]
                    dd[k].append(v)
                else:
                    dd[k] = v
        d[str(t.tag)] = dd
    if t.attrib:
        d[str(t.tag)].update(("@" + str(k), str(v)) for k, v in t.attrib.items())
    if t.text:
        text = str(t.text or "").strip()
        if children or t.attrib:
            if text:
                d[str(t.tag)]["#text"] = text
        else:
            d[str(t.tag)] = text
    return d


def bs4_to_dict(soup: Any) -> Any:
    """
    Convert BeautifulSoup object to dictionary.
    """
    if soup.name is None:
        return str(soup.string or "")
    if soup.name == "[document]":
        result = {}
        for child in soup.children:
            if child.name is not None:
                result.update(bs4_to_dict(child))
        return result
    result = {}
    for child in soup.children:
        if child.name is not None:
            result[str(child.name)] = bs4_to_dict(child)
    return {str(soup.name): result} if result else str(soup.string or "")


def dict_to_etree(d: dict[str, Any]) -> Any:
    """
    Convert dictionary to xml.etree.ElementTree element.
    """

    def _to_etree(d: Any, root: Any) -> None:
        if isinstance(d, dict):
            for k, v in d.items():
                if k.startswith("@"):
                    root.set(k[1:], v)
                elif k == "#text":
                    root.text = v
                elif isinstance(v, list):
                    for e in v:
                        _to_etree(e, ET.SubElement(root, k))
                else:
                    _to_etree(v, ET.SubElement(root, k))
        else:
            root.text = str(d)

    assert isinstance(d, dict) and len(d) == 1
    tag, body = next(iter(d.items()))
    node = ET.Element(tag)
    _to_etree(body, node)
    return node


def xml_path_to_json(path: str) -> dict[str, Any]:
    """
    Return the contents of an XML file as a dictionary. The XML file can be a compressed file supported by __open_file_maybe_compressed.
    If the file does not exist, return an empty dict.

    :param path: Path to the XML file.
    :return: Dictionary of XML file contents.
    """
    data: dict[str, Any] = {}
    if not os.path.exists(path):
        logger.error(f"XML file does not exist at: {path}")
        return data
    try:
        # Parse XML file using xml.etree.ElementTree for standard library parsing
        with __open_file_maybe_compressed(path) as f:
            tree = ET.parse(f)
            root = tree.getroot()
            data = etree_to_dict(root)
    except Exception as e:
        # If ET parsing fails, attempt parsing with BeautifulSoup
        logger.debug(f"Error parsing XML file with xml.etree.ElementTree: {e}")
        logger.debug("Trying to parse with BeautifulSoup as a fallback")
        try:
            with __open_file_maybe_compressed(path) as f:
                soup = BeautifulSoup(f.read(), "lxml-xml")
                # Find and remove empty tags
                empty_tags = soup.find_all(
                    lambda tag: not tag.text.strip() or len(tag) == 0
                )
                for empty_tag in empty_tags:
                    empty_tag.extract()
                # Convert the BeautifulSoup object to a dictionary
                data = bs4_to_dict(soup)
        except Exception as e2:
            logger.debug(f"Error parsing XML file with BeautifulSoup: {e2}")
            logger.error(f"Error parsing XML file: {path}")
            return data
    if isinstance(data, dict) and "[document]" in data:
        data = data["[document]"]
    # Return the parsed data
    return data


def json_to_xml_write(
    data: dict[str, Any], path: str, raise_errs: bool = False
) -> None:
    """
    Write dictionary data to an XML file.

    :param data: Dictionary data to write.
    :param path: Path to write the XML file to.
    """
    logger.debug("Started writing dictionary to XML")
    try:
        # Convert dictionary data to XML format using xml.etree.ElementTree
        root = dict_to_etree(data)
        rough_string = ET.tostring(root, encoding="utf-8")
        # Use minidom for pretty printing since ET doesn't have pretty_print
        reparsed = minidom.parseString(rough_string)
        with open(path, "w", encoding="utf-8") as f:
            f.write(reparsed.toprettyxml(indent="  ", encoding=None))
    except Exception as e:
        if raise_errs:
            raise e
        logger.error(f"Error writing XML file: {e}")
        return

    logger.debug("Finished writing dictionary to XML")


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
        with __open_file_maybe_compressed(path) as file:
            context = ET.iterparse(file, events=("start", "end"))
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
        with __open_file_maybe_compressed(path) as file:
            context = ET.iterparse(file, events=("start", "end"))
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


def __open_file_maybe_compressed(path: str) -> Any:
    """
    Open a file which may be compressed.
    Mostly intended for savefiles but can be other compressed text files too.

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
