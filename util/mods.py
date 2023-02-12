import os
from typing import Any, Dict, List, Tuple
from PySide2.QtWidgets import *
import json
from util.error import show_warning, show_fatal_error
from util.exception import InvalidModsConfigFormat
from util.xml import non_utf8_xml_path_to_json, xml_path_to_json


def get_active_inactive_mods(
    config_path: str, workshop_and_expansions: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Given a path to the ModsConfig.xml folder and a complete list of
    mods (including base game and DLC) and their dependencies,
    return a list of mods for the active list widget and a list of
    mods for the inactive list widget.

    :param config_path: path to ModsConfig.xml folder
    :param workshop_and_expansions: dict of all mods
    :return: a Dict for active mods and a Dict for inactive mods
    """

    # Get the list of active mods and populate data from workshop + expansions
    active_mods = get_active_mods_from_config(config_path)
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


def parse_mod_data(mods_path: str) -> Dict[str, Any]:
    mods = {}
    invalid_folders = set()
    invalid_abouts = set()
    if os.path.exists(mods_path):
        # Iterate through each item in the workshop folder
        for file in os.scandir(mods_path):
            if file.is_dir():  # Mods are contained in folders
                # Look for a case-insensitive "About" folder
                invalid_folder_path_found = True
                about_folder_name = "About"
                for temp_file in os.scandir(file.path):
                    if (
                        temp_file.name.lower() == about_folder_name.lower()
                        and temp_file.is_dir()
                    ):
                        about_folder_name = temp_file.name
                        invalid_folder_path_found = False
                        break
                # Look for a case-insensitive "About.xml" file
                invalid_file_path_found = True
                if not invalid_folder_path_found:
                    about_file_name = "About.xml"
                    for temp_file in os.scandir(
                        os.path.join(file.path, about_folder_name)
                    ):
                        if (
                            temp_file.name.lower() == about_file_name.lower()
                            and temp_file.is_file()
                        ):
                            about_file_name = temp_file.name
                            invalid_file_path_found = False
                            break
                # If there was an issue getting the expected path, track and exit
                if invalid_folder_path_found or invalid_file_path_found:
                    invalid_folders.add(file.name)
                else:
                    mod_data_path = os.path.join(
                        file.path, about_folder_name, about_file_name
                    )
                    mod_data = {}
                    try:
                        try:
                            # Default: try to parse About.xml with UTF-8 encodnig
                            mod_data = xml_path_to_json(mod_data_path)
                        except UnicodeDecodeError:
                            # It may be necessary to remove all non-UTF-8 characters and parse again
                            mod_data = non_utf8_xml_path_to_json(mod_data_path)
                    except:
                        # If there was an issue parsing the About.xml, track and exit
                        invalid_abouts.add(file.name)
                    else:
                        # Case-insensitive `ModMetaData` key.
                        mod_data = {k.lower(): v for k, v in mod_data.items()}
                        try:
                            normalized_package_id = mod_data["modmetadata"][
                                "packageId"
                            ].lower()
                            mod_data["modmetadata"]["packageId"] = normalized_package_id
                            mod_data["modmetadata"]["folder"] = file.name
                            mod_data["modmetadata"]["path"] = file.path
                            mods[normalized_package_id] = mod_data["modmetadata"]
                        except:
                            print(
                                "Failed in getting modmetadata for mod:"
                                + mod_data["modmetadata"]["name"]
                            )
                            # If there was an issue with expected About.xml content, track and exit
                            invalid_abouts.add(file.name)
                        # else:
                        #     print(
                        #         "Succeeeded in getting modmetadata for mod:"
                        #         + mod_data["modmetadata"]["name"]
                        #     )
    if invalid_folders:
        warning_message = "The following workshop folders could not be loaded:"
        for invalid_folder in invalid_folders:
            warning_message = warning_message + f"\n * {invalid_folder}"
        show_warning(warning_message)
    if invalid_abouts:
        warning_message = "The following workshop folders had invalid About.xml:"
        for invalid_about in invalid_abouts:
            warning_message = warning_message + f"\n * {invalid_about}"
        show_warning(warning_message)
    return mods


def get_local_mods(local_path: str) -> Dict[str, Any]:
    """
    Given a path to the local GAME_INSTALL_DIR/Mods folder, return a dict
    containing data for all the mods keyed to their package ids.
    The root-level key is the package id, and the root-level value
    is the converted About.xml. If the path does not exist, the dict
    will be empty.

    :param path: path to the Rimworld workshop mods folder
    :return: a Dict of workshop mods by package id, and dict of community rules
    """
    return parse_mod_data(local_path)


def get_workshop_mods(workshop_path: str) -> Dict[str, Any]:
    """
    Given a path to the Rimworld Steam workshop folder, return a dict
    containing data for all the mods keyed to their package ids.
    The root-level key is the package id, and the root-level value
    is the converted About.xml. If the path does not exist, the dict
    will be empty.

    :param path: path to the Rimworld workshop mods folder
    :return: a Dict of workshop mods by package id, and dict of community rules
    """
    return parse_mod_data(workshop_path)


def get_community_rules(workshop_mods: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract the RimPy community rules, essential for the sort
    function. Produces an error if the RimPy mod is not found.
    """
    for package_id in workshop_mods:
        if workshop_mods[package_id]["folder"] == "1847679158":
            community_rules_path = os.path.join(
                workshop_mods[package_id]["path"], "db", "communityRules.json"
            )
            with open(community_rules_path) as f:
                rule_data = json.load(f)
                return rule_data["rules"]
    show_warning(
        "The RimPy mod was not detected.\nPlease install the mod and restart RimSort."
    )


def get_rimpy_db(workshop_mods: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract the RimPy db, essential for the sort
    function. Produces an error if the RimPy mod is not found.
    """
    for package_id in workshop_mods:
        if workshop_mods[package_id]["folder"] == "1847679158":
            db_path = os.path.join(workshop_mods[package_id]["path"], "db", "db.json")
            with open(db_path) as f:
                db_data = json.load(f)
                return db_data["database"]
    show_warning(
        "The RimPy mod was not detected.\nPlease install the mod and restart RimSort."
    )


def get_dependencies_for_mods(
    mods: Dict[str, Any],
    known_expansions: Dict[str, Any],
    community_rules: Dict[str, Any],
    db_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Iterate through each workshop mod + known expansion + base game and add new key-values
    describing its dependencies (what it should be loaded after), and incompatibilities
    (currently not being used).

    :param all_workshop_mods: dict of all workshop mods
    :param known_expansions: dict of known expansions + base
    :param community_rules: dict of community established rules
    :return workshop_and_expansions: workshop mods + official modules with dependency data
    """
    # Dependencies will apply to workshop mods and known expansions
    all_mods = {**mods, **known_expansions}

    print("Start: ", _get_num_dependencies(all_mods))

    # Add dependencies to installed mods based on dependencies listed in About.xml
    for package_id in all_mods:
        # All modDependencies are dependencies
        if all_mods[package_id].get("modDependencies"):
            dependencies = all_mods[package_id]["modDependencies"]["li"]
            if dependencies:
                add_dependency_to_mod(
                    all_mods[package_id],
                    "dependencies",
                    dependencies,
                    all_mods,
                )

        # Current mod should be loaded AFTER these mods
        # These are all dependencies for the current mod
        if all_mods[package_id].get("loadAfter"):
            dependencies = all_mods[package_id]["loadAfter"]["li"]
            if dependencies:
                add_dependency_to_mod(
                    all_mods[package_id],
                    "dependencies",
                    dependencies,
                    all_mods,
                )

        # Current mod should be loaded BEFORE these mods
        # The current mod is a dependency for all these mods
        if all_mods[package_id].get("loadBefore"):
            dependencies = all_mods[package_id]["loadBefore"]["li"]
            if dependencies:
                if isinstance(dependencies, str):
                    add_dependency_to_mod(
                        all_mods.get(
                            dependencies.lower()
                        ),  # Will be None if mod does not exist
                        "dependencies",
                        package_id,
                        all_mods,
                    )
                elif isinstance(dependencies, list):
                    for dependency_id in dependencies:
                        add_dependency_to_mod(
                            all_mods.get(dependency_id.lower()),
                            "dependencies",
                            package_id,
                            all_mods,
                        )

        # Check for incompatible mods (TODO: currently unused)
        if all_mods[package_id].get("incompatibleWith"):
            dependencies = all_mods[package_id]["incompatibleWith"]["li"]
            if dependencies:
                add_dependency_to_mod(
                    all_mods[package_id],
                    "incompatibilities",
                    dependencies,
                    all_mods,
                )

    print("About XMLs: ", _get_num_dependencies(all_mods))

    # Add dependencies to installed mods based on dependencies from community rules
    for package_id in community_rules:
        for dependency_id in community_rules[package_id][
            "loadBefore"
        ]:  # Current mod should be loaded BEFORE these mods
            add_dependency_to_mod(
                all_mods.get(dependency_id.lower()),
                "dependencies",
                package_id.lower(),
                all_mods,
            )
        for dependency_id in community_rules[package_id][
            "loadAfter"
        ]:  # Current mod should be loaded AFTER these mods
            add_dependency_to_mod(
                all_mods.get(
                    package_id.lower()
                ),  # Community rules may be referencing not-installed mod
                "dependencies",
                dependency_id.lower(),
                all_mods,
            )

    print("Community Rules: ", _get_num_dependencies(all_mods, True))

    # RimPy's references depdencies based on folder ID, not package ID
    # Create a temporary folder ID -> package ID dict here
    # TODO: optimization: maybe everything could be based off folder ID
    # TODO: optimization: all of this (and rules.json parsing) could probably be done in the first loop
    folder_to_package_id = {}
    for package_id, mod_data in all_mods.items():
        if mod_data.get("folder"):
            folder_to_package_id[mod_data["folder"]] = mod_data["packageId"]

    for folder_id, mod_data in db_data.items():
        # We could use `folder_in in folder_to_package_id` too
        if mod_data["packageId"].lower() in all_mods:
            for dependency_folder_id in mod_data["dependencies"]:
                if dependency_folder_id in folder_to_package_id:
                    # This means the dependency is in all mods
                    dependency_package_id = folder_to_package_id[dependency_folder_id]
                    add_dependency_to_mod(
                        all_mods.get(mod_data["packageId"].lower()),
                        "dependencies",
                        dependency_package_id.lower(),
                        all_mods,
                    )

    print("Rimpy DB: ", _get_num_dependencies(all_mods, True))

    # At this point, `all_mods` contains all install mods keyed to their package_id
    # and having dependencies from About.xml, communityRules.json, and db.json

    return all_mods


def _get_num_dependencies(all_mods: Dict[str, Any], to_print=False) -> None:
    """Debug func for getting total number of dependencies"""
    counter = 0
    for package_id, mod_data in all_mods.items():
        if mod_data.get("dependencies"):
            # if to_print:
            #     print(package_id, mod_data["dependencies"])
            counter = counter + len(mod_data["dependencies"])
    return counter


def add_dependency_to_mod(
    mod_data: Dict[str, Any],
    new_data_key: str,
    dependency_or_dependency_ids: Any,
    all_mods: Dict[str, Any],
) -> None:
    """
    Given a mod dict, a key, and a value, add the contents of value to the key
    in the dict. If the key does not exist, add an empty list at that key. This
    is to support dependency schemas being either strings or list of strings.

    This is by design:
    IMPORTANT!! Depdencies that DO NOT EXIST in all_mods ARE NOT ADDED!!
    IMPORTANT!! "Current mods" that DO NOT EXIST in all_mods WILL NOT HAVE
        DEPENDENCIES ADDED!

    :param mod_data: mod data dict to add dependencies to
    :param key: key to add data to
    :param value: either string or list of strings (or sometimes None)
    :param workshop_and_expansions: dict of all mods to verify keys against
    """
    if mod_data:
        # Create a new key with empty set as value
        if new_data_key not in mod_data:
            mod_data[new_data_key] = set()

        # If the value is a single string...
        if isinstance(dependency_or_dependency_ids, str):
            dependency_id = dependency_or_dependency_ids.lower()
            if dependency_id in all_mods:
                mod_data[new_data_key].add(dependency_id)
                if "isDependencyOf" not in all_mods[dependency_id]:
                    all_mods[dependency_id]["isDependencyOf"] = set()
                all_mods[dependency_id]["isDependencyOf"].add(mod_data["packageId"])

        # If the value is a single dict (for modDependencies)
        elif isinstance(dependency_or_dependency_ids, dict):
            dependency_id = dependency_or_dependency_ids["packageId"].lower()
            if dependency_id in all_mods:
                mod_data[new_data_key].add(dependency_id)
                if "isDependencyOf" not in all_mods[dependency_id]:
                    all_mods[dependency_id]["isDependencyOf"] = set()
                all_mods[dependency_id]["isDependencyOf"].add(mod_data["packageId"])

        # If the value is a LIST of strings or dicts
        elif isinstance(dependency_or_dependency_ids, list):
            if isinstance(dependency_or_dependency_ids[0], str):
                for dependency in dependency_or_dependency_ids:
                    dependency_id = dependency.lower()
                    if dependency_id in all_mods:
                        mod_data[new_data_key].add(dependency_id)
                        if "isDependencyOf" not in all_mods[dependency_id]:
                            all_mods[dependency_id]["isDependencyOf"] = set()
                        all_mods[dependency_id]["isDependencyOf"].add(mod_data["packageId"])
            elif isinstance(dependency_or_dependency_ids[0], dict):
                for dependency in dependency_or_dependency_ids:
                    dependency_id = dependency["packageId"].lower()
                    if dependency_id in all_mods:
                        mod_data[new_data_key].add(dependency_id)
                        if "isDependencyOf" not in all_mods[dependency_id]:
                            all_mods[dependency_id]["isDependencyOf"] = set()
                        all_mods[dependency_id]["isDependencyOf"].add(mod_data["packageId"])


def get_active_mods_from_config(config_path: str) -> Dict[str, Any]:
    """
    Given a path to a file in the ModsConfig.xml format, return the
    mods in the active mods section.

    :param path: path to a ModsConfig.xml file
    :return: a Dict keyed to mod package ids
    """
    mod_data = xml_path_to_json(config_path)
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


def get_known_expansions_from_config(config_path: str) -> Dict[str, Any]:
    """
    Given a path to a file in the ModsConfig.xml format, return the
    mods in the known expansions section (and add base game).

    :param path: path to a ModsConfig.xml file
    :return: a Dict keyed to mod package ids
    """
    mod_data = xml_path_to_json(config_path)
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
            "folder": "294100",
            "isBase": True,
            "author": "Ludeon Studios",
        }
    if package_id == "ludeon.rimworld.royalty":
        mod_data[package_id] = {
            "name": "Royalty",
            "packageId": package_id,
            "folder": "1149640",
            "isDLC": True,
            "dependencies": {"ludeon.rimworld"},
            "author": "Ludeon Studios",
        }
    if package_id == "ludeon.rimworld.ideology":
        mod_data[package_id] = {
            "name": "Ideology",
            "packageId": package_id,
            "folder": "1392840",
            "isDLC": True,
            "dependencies": {"ludeon.rimworld", "ludeon.rimworld.royalty"},
            "author": "Ludeon Studios",
        }
    if package_id == "ludeon.rimworld.biotech":
        mod_data[package_id] = {
            "name": "Biotech",
            "packageId": package_id,
            "folder": "1826140",
            "isDLC": True,
            "dependencies": {
                "ludeon.rimworld",
                "ludeon.rimworld.royalty",
                "ludeon.rimworld.ideology",
            },
            "author": "Ludeon Studios",
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
    :param workshop_and_expansions: dict of workshop mods (and expansions) keyed to packge-id
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


def merge_mod_data(*dict_args) -> Dict[str, Any]:
    """
    Given any number of dictionaries, shallow copy and merge into a new dict,
    precedence goes to key-value pairs in latter dictionaries.
    """
    result = {}
    for dictionary in dict_args:
        result.update(dictionary)
    return result


def get_inactive_mods(
    workshop_and_expansions: Dict[str, Any],
    active_mods: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate a list of inactive mods by cross-referencing the list of
    installed workshop mods with the active mods and known expansions.

    :param workshop_and_expansions: dict of workshop mods and expansions
    :param active_mods: dict of active mods
    :return: a dict for inactive mods
    """
    inactive_mods = workshop_and_expansions.copy()
    # For each mod in active mods, remove from workshop_and_expansions
    for mod_package_id in active_mods:
        if mod_package_id in workshop_and_expansions:
            del inactive_mods[mod_package_id]
    return inactive_mods
