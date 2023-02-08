import os
import sys
from typing import Any, Dict, List, Tuple
import xmltodict
from PySide2.QtWidgets import *

from util.error import show_warning
from util.exception import (
    InvalidModsConfigFormat,
    InvalidWorkshopModAboutFormat,
    UnexpectedModMetaData,
)
from util.xml import fix_non_utf8_xml, xml_path_to_json


def get_active_inactive_mods(
    config_path: str, workshop_path: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Given a path to a file in the ModsConfig.xml format and a path
    to the Rimworld workshop folder, return a list of mods for the active
    list widget and a list of mods for the inactive list widget.

    :param config_path: path to some ModsConfig.xml
    :param workshop_path: path to workshop mods folder
    :return: a Dict for active mods and a Dict for inactive mods
    """
    workshop_mods = get_workshop_mods(workshop_path)
    active_mods = get_active_mods_from_config_format(config_path)
    for package_id in active_mods.keys():
        populate_expansions_static_data(active_mods, package_id)
    known_expansions = get_known_expansions_from_config_format(config_path)
    for package_id in known_expansions.keys():
        populate_expansions_static_data(known_expansions, package_id)
    active_mods, invalid_mods = populate_active_mods_workshop_data(
        active_mods, workshop_mods
    )
    if invalid_mods:
        warning_message = "The following list of mods could not be loaded:"
        for invalid_mod in invalid_mods:
            warning_message = warning_message + f"\n * {invalid_mod}"
        show_warning(warning_message)
    inactive_mods = get_inactive_mods(workshop_mods, active_mods, known_expansions)
    return active_mods, inactive_mods


def get_workshop_mods(path: str) -> Dict[str, Any]:
    """
    Given a path to the Rimworld Steam workshop folder, return a dict
    containing data for all the mods keyed to their package ids.
    The root-level key is the package id, and the root-level value
    is the converted About.xml. If the path does not exist, the dict
    will be empty.

    :param path: path to the Rimworld workshop mods folder
    :return: a Dict of workshop mods by package id
    """
    workshop_mods = {}
    if os.path.exists(path):
        for file in os.scandir(path):
            if not file.is_file():
                mod_data_path = os.path.join(file.path, "About", "About.xml")
                mod_data = dict()
                try:
                    # Default: try to parse About.xml with UTF-8 encodnig
                    mod_data = xml_path_to_json(mod_data_path)
                except UnicodeDecodeError:
                    # It may be necessary to remove all non-UTF-8 characters
                    mod_data = xmltodict.parse(fix_non_utf8_xml(mod_data_path))
                # Account for variation in modMetaData vs. ModMetaData
                mod_data = {k.lower(): v for k, v in mod_data.items()}
                try:
                    if not mod_data["modmetadata"]:
                        raise UnexpectedModMetaData
                    workshop_mods[
                        mod_data["modmetadata"]["packageId"].lower()
                    ] = mod_data["modmetadata"]
                except:
                    raise InvalidWorkshopModAboutFormat
    return workshop_mods


def get_active_mods_from_config_format(path: str) -> Dict[str, Any]:
    """
    Given a path to a file in the ModsConfig.xml format, return the
    mods in the active mods section.

    :param path: path to a ModsConfig.xml file
    :return: a Dict keyed to mod package ids
    """
    mod_data = xml_path_to_json(path)
    try:
        if mod_data:
            return dict(
                [
                    (package_id, {})
                    for package_id in mod_data["ModsConfigData"]["activeMods"]["li"]
                ]
            )
        return {}
    except:
        raise InvalidModsConfigFormat


def get_known_expansions_from_config_format(path: str) -> Dict[str, Any]:
    """
    Given a path to a file in the ModsConfig.xml format, return the
    mods in the known expansions section.

    :param path: path to a ModsConfig.xml file
    :return: a Dict keyed to mod package ids
    """
    mod_data = xml_path_to_json(path)
    try:
        if mod_data:
            if mod_data["ModsConfigData"]["knownExpansions"] is None:
                return {}
            else:
                return dict(
                    [
                        (package_id.lower(), {})
                        for package_id in mod_data["ModsConfigData"]["knownExpansions"][
                            "li"
                        ]
                    ]
                )
        return {}
    except Exception:
        raise InvalidModsConfigFormat


def populate_expansions_static_data(mod_data: Dict[str, Any], package_id: str) -> None:
    """
    Given a dict of mods and a package id, check if the package id belongs
    to the base game or any of the DLC. If so, populate the relevant key value
    with the DLC name.

    :param mod_data: dict of mod data keyed to package id
    :param package_id: package id to check if it is DLC
    """
    if package_id == "ludeon.rimworld":
        mod_data[package_id] = {
            "name": "Rimworld",
            "packageId": package_id,
            "isBase": True,
        }
    if package_id == "ludeon.rimworld.royalty":
        mod_data[package_id] = {
            "name": "Royalty",
            "packageId": package_id,
            "isDLC": True,
        }
    if package_id == "ludeon.rimworld.ideology":
        mod_data[package_id] = {
            "name": "Ideology",
            "packageId": package_id,
            "isDLC": True,
        }
    if package_id == "ludeon.rimworld.biotech":
        mod_data[package_id] = {
            "name": "Biotech",
            "packageId": package_id,
            "isDLC": True,
        }


def populate_active_mods_workshop_data(
    unpopulated_mods: Dict[str, Any], workshop_mods: Dict[str, Any]
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Given a dict of mods with no attached data, populate all
    workshop mods with workshop mods data (taken from the workshop directory).
    Note that key-values in unpopulated mods that cannot find a
    corresponding package id in workshop mods will not have their
    values modified (will be kept empty).

    :param unpopulated_mods: dict of package-id-keyed active mods
    :param workshop_mods: dict of workshop mods keyed to packge-id
    :return: active mod list with populated data, and list of package ids of invalid mods
    """
    populated_mods = unpopulated_mods.copy()
    invalid_mods = []
    for mod_package_id in unpopulated_mods:
        # Cross reference package ids with mods in the workshop folder.
        # If unable to, that means either the mod hasn't been downloaded
        # of it is an invalid entry.
        if mod_package_id in workshop_mods:
            populated_mods[mod_package_id] = workshop_mods[mod_package_id]
        else:
            if not populated_mods[mod_package_id]:  # Base/DLC will already have data
                invalid_mods.append(mod_package_id)
                del populated_mods[mod_package_id]
                # populated_mods[mod_package_id] = {"name": f"ERROR({mod_package_id})", "packageId": mod_package_id}
    return populated_mods, invalid_mods


def get_inactive_mods(
    workshop_mods: Dict[str, Any],
    active_mods: Dict[str, Any],
    known_expansions: List[str],
) -> Dict[str, Any]:
    """
    Generate a list of inactive mods by cross-referencing the list of
    installed workshop mods with the active mods and known expansions.

    :param workshop_mods: dict of workshop mods
    :param active_mods: dict of active mods
    :param known_expansion: dict of known expansions
    :return: a dict for inactive mods
    """
    inactive_mods = workshop_mods.copy()
    for mod_package_id in active_mods:
        if mod_package_id in workshop_mods:
            del inactive_mods[mod_package_id]
    for mod_package_id in known_expansions:
        if mod_package_id not in active_mods:
            inactive_mods[mod_package_id] = known_expansions[mod_package_id]
    return inactive_mods
