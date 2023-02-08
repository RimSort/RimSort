import os
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
    # Get all mods from the workshop folder
    # Each mod is a dict initialized with data from the About.xml
    workshop_mods = get_workshop_mods(workshop_path)

    # Get and populate initial data for known DLCs and base game
    known_expansions = get_known_expansions_from_config_format(config_path)
    for package_id in known_expansions.keys():
        populate_expansions_static_data(known_expansions, package_id)

    # Populate dependencies for mods and expansions
    workshop_and_expansions = get_dependencies_for_mods(workshop_mods, known_expansions)

    # Get the list of active mods and populate data from workshop + expansions
    active_mods = get_active_mods_from_config_format(config_path)
    active_mods, invalid_mods = populate_active_mods_workshop_data(
        active_mods, workshop_and_expansions
    )

    # Return an error if some active mod was in the ModsConfig but no data
    # could be found for it
    if invalid_mods:
        warning_message = "The following list of mods could not be loaded:"
        for invalid_mod in invalid_mods:
            warning_message = warning_message + f"\n * {invalid_mod}"
        show_warning(warning_message)

    # Get the inactive mods by subtracting active mods from workshop + expansions
    inactive_mods = get_inactive_mods(workshop_and_expansions, active_mods)
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
                    case_normalized_package_id = mod_data["modmetadata"][
                        "packageId"
                    ].lower()
                    mod_data["modmetadata"]["packageId"] = case_normalized_package_id
                    workshop_mods[case_normalized_package_id] = mod_data["modmetadata"]
                except:
                    raise InvalidWorkshopModAboutFormat
    return workshop_mods


def get_dependencies_for_mods(
    all_workshop_mods: Dict[str, Any], known_expansions: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Iterate through each workshop + known expansion + base game and add new key-values
    describing its dependencies, soft-dependencies (what it should be loaded after),
    and incompatibilities (currently not being used).

    :param all_workshop_mods: dict of all workshop mods
    :param known_expansions: dict of known expansions + base
    :return workshop_and_expansions: workshop mods + official modules with dependency data
    """
    workshop_and_expansions = {**all_workshop_mods, **known_expansions}

    for package_id in workshop_and_expansions:
        # Check if there are mods that the current mod needs to be loaded with
        if workshop_and_expansions[package_id].get("modDependencies"):
            dependencies = workshop_and_expansions[package_id]["modDependencies"]["li"]
            if dependencies:
                add_value_to_key_or_create_key_set(
                    workshop_and_expansions[package_id],
                    "dependencies",
                    dependencies,
                    workshop_and_expansions,
                )

        # Check if there are mods that should be loaded before the current mod (soft dependency)
        # In other words, your mod should be loaded AFTER these mods
        if workshop_and_expansions[package_id].get("loadAfter"):
            dependencies = workshop_and_expansions[package_id]["loadAfter"]["li"]
            if dependencies:
                add_value_to_key_or_create_key_set(
                    workshop_and_expansions[package_id],
                    "softDependencies",
                    dependencies,
                    workshop_and_expansions,
                )

        # Check if there are mods that should to be loaded after the current mod (soft dependency)
        # In other words, your mod should be loaded BEFORE these mods
        if workshop_and_expansions[package_id].get("loadBefore"):
            dependencies = workshop_and_expansions[package_id]["loadBefore"]["li"]
            if dependencies:
                if isinstance(dependencies, str):
                    add_value_to_key_or_create_key_set(
                        # Will be None if mod does not exist
                        workshop_and_expansions.get(dependencies.lower()),
                        "softDependencies",
                        package_id,
                        workshop_and_expansions,
                    )
                elif isinstance(dependencies, list):
                    for dependency_id in dependencies:
                        add_value_to_key_or_create_key_set(
                            workshop_and_expansions.get(dependency_id.lower()),
                            "softDependencies",
                            package_id,
                            workshop_and_expansions,
                        )

        # Check if there are mods that are incompatible
        if workshop_and_expansions[package_id].get("incompatibleWith"):
            dependencies = workshop_and_expansions[package_id]["incompatibleWith"]["li"]
            if dependencies:  # Sometimes this is None
                add_value_to_key_or_create_key_set(
                    workshop_and_expansions[package_id],
                    "incompatibilities",
                    dependencies,
                    workshop_and_expansions,
                )

    return workshop_and_expansions


def add_value_to_key_or_create_key_set(
    mod_data: Dict[str, Any],
    key: str,
    value: Any,
    workshop_and_expansions: Dict[str, Any],
) -> None:
    """
    Given a mod dict, a key, and a value, add the contents of value to the key
    in the dict. If the key does not exist, add an empty list at that key. This
    is to support dependency schemas being either strings or list of strings.

    :param mod_data: mod data dict
    :param key: key to add data to
    :param value: either string or list of strings (or sometimes None)
    :param workshop_and_expansions: ?
    """
    if mod_data:
        # Create a new key with empty set as value
        if key not in mod_data:
            mod_data[key] = set()

        # If the value is a single string...
        if isinstance(value, str):
            if value.lower() in workshop_and_expansions:
                mod_data[key].add(value.lower())

        # If the value is a single dict (for modDependencies)
        elif isinstance(value, dict):
            if value["packageId"].lower() in workshop_and_expansions:
                mod_data[key].add(value["packageId"].lower())

        # If the value is a LIST of strings or dicts
        elif isinstance(value, list):
            if isinstance(value[0], str):
                for dependency in value:
                    if dependency.lower() in workshop_and_expansions:
                        mod_data[key].add(dependency.lower())
            elif isinstance(value[0], dict):
                for dependency in value:
                    if dependency["packageId"].lower() in workshop_and_expansions:
                        mod_data[key].add(dependency["packageId"].lower())


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
                    (package_id.lower(), {})
                    for package_id in mod_data["ModsConfigData"]["activeMods"]["li"]
                ]
            )
        return {}
    except:
        raise InvalidModsConfigFormat


def get_known_expansions_from_config_format(path: str) -> Dict[str, Any]:
    """
    Given a path to a file in the ModsConfig.xml format, return the
    mods in the known expansions section (and add base game).

    :param path: path to a ModsConfig.xml file
    :return: a Dict keyed to mod package ids
    """
    mod_data = xml_path_to_json(path)
    try:
        ret = {"ludeon.rimworld": {}}  # Base game always exists
        if mod_data:
            if mod_data["ModsConfigData"]["knownExpansions"]:
                for package_id in mod_data["ModsConfigData"]["knownExpansions"]["li"]:
                    ret[package_id.lower()] = {}
        return ret
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
            "dependencies": {"ludeon.rimworld"},
        }
    if package_id == "ludeon.rimworld.ideology":
        mod_data[package_id] = {
            "name": "Ideology",
            "packageId": package_id,
            "isDLC": True,
            "dependencies": {"ludeon.rimworld", "ludeon.rimworld.royalty"},
        }
    if package_id == "ludeon.rimworld.biotech":
        mod_data[package_id] = {
            "name": "Biotech",
            "packageId": package_id,
            "isDLC": True,
            "dependencies": {
                "ludeon.rimworld",
                "ludeon.rimworld.royalty",
                "ludeon.rimworld.ideology",
            },
        }


def populate_active_mods_workshop_data(
    unpopulated_mods: Dict[str, Any], workshop_and_expansions: Dict[str, Any]
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Given a dict of mods with no attached data, populate all
    workshop mods with workshop mods data (taken from the workshop directory).
    Note that key-values in unpopulated mods that cannot find a
    corresponding package id in workshop mods will not have their
    values modified (will be kept empty).

    :param unpopulated_mods: dict of package-id-keyed active mods
    :param workshop_mods: dict of workshop mods keyed to packge-id
    :param known_expansions: dict of known expansions
    :return: active mod list with populated data, and list of package ids of invalid mods
    """
    populated_mods = unpopulated_mods.copy()
    invalid_mods = []
    for mod_package_id in unpopulated_mods:
        # Cross reference package ids with mods in the workshop folder.
        # If unable to, that means either the mod hasn't been downloaded
        # of it is an invalid entry.
        if mod_package_id in workshop_and_expansions:
            populated_mods[mod_package_id] = workshop_and_expansions[mod_package_id]
        else:
            invalid_mods.append(mod_package_id)
            del populated_mods[mod_package_id]
            # populated_mods[mod_package_id] = {"name": f"ERROR({mod_package_id})", "packageId": mod_package_id}
    return populated_mods, invalid_mods


def get_inactive_mods(
    workshop_and_expansions: Dict[str, Any],
    active_mods: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate a list of inactive mods by cross-referencing the list of
    installed workshop mods with the active mods and known expansions.

    :param workshop_mods: dict of workshop mods
    :param active_mods: dict of active mods
    :param known_expansion: dict of known expansions
    :return: a dict for inactive mods
    """
    inactive_mods = workshop_and_expansions.copy()
    # For each mod in active mods, remove from workshop_and_expansions
    for mod_package_id in active_mods:
        if mod_package_id in workshop_and_expansions:
            del inactive_mods[mod_package_id]
    return inactive_mods
