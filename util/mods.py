import json
import logging
import os
import platform
import traceback
from typing import Any, Dict, List, Optional, Tuple

from PySide2.QtWidgets import *

from util.error import show_warning
from util.exception import InvalidModsConfigFormat
from util.xml import non_utf8_xml_path_to_json, xml_path_to_json

logger = logging.getLogger(__name__)


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
    logger.info("Starting generating active and inactive mods")

    # Get the list of active mods and populate data from workshop + expansions
    logger.info(f"Calling get active mods with Config Path: {config_path}")
    active_mods = get_active_mods_from_config(config_path)

    logger.info("Calling populate active mods with data")
    active_mods, invalid_mods = populate_active_mods_workshop_data(
        active_mods, workshop_and_expansions
    )

    # Return an error if some active mod was in the ModsConfig but no data
    # could be found for it
    if invalid_mods:
        logger.warning(
            f"Could not find data for the list of active mods: {invalid_mods}"
        )
        warning_message = "The following list of mods could not be loaded\nDid you set your game install and workshop/local mods path correctly?:"
        for invalid_mod in invalid_mods:
            warning_message = warning_message + f"\n * {invalid_mod}"
        show_warning(warning_message)

    # Get the inactive mods by subtracting active mods from workshop + expansions
    logger.info("Calling get inactive mods")
    inactive_mods = get_inactive_mods(workshop_and_expansions, active_mods)

    logger.info(
        f"Returning newly generated active mods [{len(active_mods)}] and inactive mods [{len(inactive_mods)}] list"
    )
    return active_mods, inactive_mods


def parse_mod_data(mods_path: str, intent: str) -> Dict[str, Any]:
    logger.info(f"Starting parsing mod data for intent: {intent}")
    mods = {}
    if os.path.exists(mods_path):
        logger.info(f"The provided mods path exists: {mods_path}")
        # Iterate through each item in the workshop folder
        files_scanned = []
        dirs_scanned = []
        for file in os.scandir(mods_path):
            if file.is_dir():  # Mods are contained in folders
                dirs_scanned.append(file.name)
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
                    logger.warning(
                        f"There was an issue getting the expected sub-path for this path, no variations of /About/About.xml could be found: {file.path}"
                    )
                    logger.warning(
                        "^ this may not be an issue, as workshop sometimes forgets to delete unsubscribed mod folders."
                    )
                else:
                    mod_data_path = os.path.join(
                        file.path, about_folder_name, about_file_name
                    )
                    logger.info(
                        f"Found a variation of /About/About.xml at: {mod_data_path}"
                    )
                    mod_data = {}
                    try:
                        try:
                            # Default: try to parse About.xml with UTF-8 encodnig
                            mod_data = xml_path_to_json(mod_data_path)
                        except UnicodeDecodeError:
                            # It may be necessary to remove all non-UTF-8 characters and parse again
                            logger.warning(
                                "Unable to parse About.xml with UTF-8, attempting to decode"
                            )
                            mod_data = non_utf8_xml_path_to_json(mod_data_path)
                    except:
                        # If there was an issue parsing the About.xml, track and exit
                        logger.error(
                            f"Unable to parse About.xml with the exception: {traceback.format_exc()}"
                        )
                    else:
                        # Case-insensitive `ModMetaData` key.
                        logger.debug("Attempting to normalize XML content keys")
                        mod_data = {k.lower(): v for k, v in mod_data.items()}
                        logger.debug(f"Normalized XML content: {mod_data}")
                        logger.debug("Editing XML content")
                        if mod_data.get("modmetadata"):
                            if mod_data["modmetadata"].get("packageId"):
                                normalized_package_id = mod_data["modmetadata"][
                                    "packageId"
                                ].lower()
                                mod_data["modmetadata"][
                                    "packageId"
                                ] = normalized_package_id
                                mod_data["modmetadata"]["folder"] = file.name
                                mod_data["modmetadata"]["path"] = file.path
                                logger.debug(
                                    f"Finished editing XML content, adding final content to larger list: {mod_data['modmetadata']}"
                                )
                                mods[normalized_package_id] = mod_data["modmetadata"]
                            else:
                                logger.error(
                                    f"Key [packageId] does not exist in this data's [modmetadata]: {mod_data}"
                                )
                        else:
                            logger.error(
                                f"Key [modmetadata] does not exist in this data: {mod_data}"
                            )
            else:
                files_scanned.append(file.name)
        logger.info(f"Scanned the following files in mods path: {files_scanned}")
        logger.info(f"Scanned the following dirs in mods path: {dirs_scanned}")
    else:
        logger.error(f"The provided mods path does not exist: {mods_path}")
        if mods_path:
            show_warning(
                f"Unable to get data for {intent}.\nThe path [{mods_path}] is invalid.\nCheck that your paths are set correctly."
            )
    logger.info(f"Finished parsing mod data for intent: {intent}")
    return mods


def get_installed_expansions(game_path: str) -> Dict[str, Any]:
    """
    Given a path to the game's install folder, return a dict
    containing data for all of the installed expansions
    keyed to their package ids. The dict values are the convereted
    About.xmls. If the path does not exist, the dict
    will be empty.

    :param path: path to the Rimworld install folder
    :return: a Dict of expansions by package id
    """
    logger.info(f"Getting installed expansions with Game Folder path: {game_path}")
    # RimWorld folder on mac contains RimWorldMac.app which
    # is actually a folder itself
    if platform.system() == "Darwin" and game_path:
        game_path = os.path.join(game_path, "RimWorldMac.app")
        logger.info(f"Running on MacOS, generating new game path: {game_path}")

    # Get mod data
    data_path = os.path.join(game_path, "Data")
    logger.info(
        f"Attempting to get BASE/EXPANSIONS data from Rimworld's /Data folder: {data_path}"
    )
    mod_data = parse_mod_data(data_path, "game install")
    logger.info("Finished getting BASE/EXPANSION data")
    logger.debug(mod_data)

    # Base game and expansion About.xml do not contain name, so these
    # must be manually added
    logger.info("Manually populating names for BASE/EXPANSION data")
    for package_id in mod_data.keys():
        if package_id == "ludeon.rimworld":
            mod_data[package_id]["name"] = "Core (Base game)"
        if package_id == "ludeon.rimworld.royalty":
            mod_data[package_id]["name"] = "Royalty (DLC #1)"
        if package_id == "ludeon.rimworld.ideology":
            mod_data[package_id]["name"] = "Ideology (DLC #2)"
        if package_id == "ludeon.rimworld.biotech":
            mod_data[package_id]["name"] = "Biotech (DLC #3)"
    logger.info(
        "Finished getting installed expansions, returning final BASE/EXPANSIONS data now"
    )
    logger.debug(mod_data)
    return mod_data


def get_local_mods(local_path: str, game_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Given a path to the local GAME_INSTALL_DIR/Mods folder, return a dict
    containing data for all the mods keyed to their package ids.
    The root-level key is the package id, and the root-level value
    is the converted About.xml. If the path does not exist, the dict
    will be empty.

    :param path: path to the Rimworld workshop mods folder
    :return: a Dict of workshop mods by package id, and dict of community rules
    """
    logger.info(f"Getting local mods with Local path: {local_path}")
    logger.info(f"Supplementing call with Game Folder path: {game_path}")

    # If local mods path is same as game path and we're running on a Mac,
    # that means use the default local mods folder

    system_name = platform.system()
    if system_name == "Darwin" and local_path and local_path == game_path:
        local_path = os.path.join(local_path, "RimWorldMac.app", "Mods")
        logger.info(f"Running on MacOS, generating new local mods path: {local_path}")

    # Get mod data
    logger.info(
        f"Attempting to get LOCAL mods data from custom local path or Rimworld's /Mods folder: {local_path}"
    )
    mod_data = parse_mod_data(local_path, "local mods")
    logger.info("Finished getting LOCAL mods data, returning LOCAL mods data now")
    logger.debug(mod_data)
    return mod_data


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
    logger.info(f"Getting WORKSHOP data with Workshop path: {workshop_path}")
    mod_data = parse_mod_data(workshop_path, "workshop mods")
    logger.info("Finished getting WORKSHOP data, returning WORKSHOP data now")
    logger.debug(mod_data)
    return mod_data


def get_steam_db_rules(mods: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract the configured DB mod's SteamDB rules, essential for the sort
    function. Produces an error if the DB mod is not found.
    """
    logger.info("Getting steam DB rules")
    for package_id in mods:
        if (
            package_id == "rupal.rimpymodmanagerdatabase"
            or mods[package_id]["folder"] == "1847679158"
        ):  # TODO make this a DB mod packageID a configurable preference
            logger.info("Found RimPy ModManager DB")
            steam_db_rules_path = os.path.join(
                mods[package_id]["path"], "db", "db.json"
            )
            logger.info(f"Generated path to db.json: {steam_db_rules_path}")
            if os.path.exists(steam_db_rules_path):
                with open(steam_db_rules_path, encoding="utf-8") as f:
                    json_string = f.read()
                    logger.info("Reading info from db.json")
                    db_data = json.loads(json_string)
                    logger.debug(
                        "Returning db.json, this data is long so we forego logging it here"
                    )
                    return db_data["database"]
            else:
                logger.error("The db.json path does not exist")
    logger.warning(
        "No Steam DB data was found. This will affect the accuracy of mod dependencies"
    )
    show_warning(
        "The configured DB mod was not detected.\nRimPy DB was also not found.\nPlease install & configure a valid DB mod and refresh/restart RimSort."
    )
    return {}


def get_community_rules(mods: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract the configured DB mod's community rules, essential for the sort
    function. Produces an error if the DB mod is not found.
    """
    logger.info("Getting community rules")
    for package_id in mods:
        if (
            package_id == "rupal.rimpymodmanagerdatabase"
            or mods[package_id]["folder"] == "1847679158"
        ):  # TODO make this a DB mod packageID a configurable preference
            logger.info("Found RimPy ModManager rules")
            community_rules_path = os.path.join(
                mods[package_id]["path"], "db", "communityRules.json"
            )
            logger.info(
                f"Generated path to communityRules.json: {community_rules_path}"
            )
            if os.path.exists(community_rules_path):
                with open(community_rules_path, encoding="utf-8") as f:
                    json_string = f.read()
                    logger.info("Reading info from communityRules.json")
                    rule_data = json.loads(json_string)
                    logger.debug(
                        "Returning communityRules.json, this data is long so we forego logging it here"
                    )
                    return rule_data["rules"]
            else:
                logger.error("The communityRules.json path does not exist")
    logger.warning(
        "No Community Rules data was found. This will affect the accuracy of mod load order"
    )
    show_warning(
        "The configured DB mod was not detected.\nRimPy DB was also not found.\nPlease install & configure a valid DB mod and refresh/restart RimSort."
    )
    return {}


def get_dependencies_for_mods(
    expansions: Dict[str, Any],
    mods: Dict[str, Any],
    steam_db_rules: Dict[str, Any],
    community_rules: Dict[str, Any],
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
    logger.info("Starting getting dependencies for all mods")
    # Dependencies will apply to installed expansions, as well as local/workshop mods
    all_mods = {**expansions, **mods}
    logger.info(
        f"Combined {len(expansions)} expansions with {len(mods)} mods, totaling {len(all_mods)} elements to get dependencies for"
    )

    # Add dependencies to installed mods based on dependencies listed in About.xml TODO manifest.xml
    logger.info(f"Total number of dependencies: {_get_num_dependencies(all_mods)}")
    logger.info("Starting adding dependencies through About.xml information")
    for package_id in all_mods:
        logger.debug(f"Current mod: {package_id}")
        # All modDependencies are dependencies
        # if all_mods[package_id].get("modDependencies"):
        #     dependencies = all_mods[package_id]["modDependencies"]["li"]
        #     if dependencies:
        #         add_dependency_to_mod(
        #             all_mods[package_id],
        #             "dependencies",
        #             dependencies,
        #             all_mods,
        #         )

        # Current mod should be loaded AFTER these mods
        # These are all dependencies for the current mod
        if all_mods[package_id].get("loadAfter"):
            dependencies = all_mods[package_id]["loadAfter"].get("li")
            if dependencies:
                logger.debug(
                    f"Current mod should load after these mods: {dependencies}"
                )
                add_dependency_to_mod(
                    all_mods[package_id],
                    "dependencies",
                    dependencies,
                    all_mods,
                )

        if all_mods[package_id].get("forceLoadAfter"):
            dependencies = all_mods[package_id]["forceLoadAfter"].get("li")
            if dependencies:
                logger.debug(
                    f"Current mod should force load after these mods: {dependencies}"
                )
                add_dependency_to_mod(
                    all_mods[package_id],
                    "dependencies",
                    dependencies,
                    all_mods,
                )

        if all_mods[package_id].get("loadAfterByVersion"):
            if all_mods[package_id]["loadAfterByVersion"].get("v1.4"):
                dependencies = all_mods[package_id]["loadAfterByVersion"]["v1.4"].get(
                    "li"
                )
                if dependencies:
                    logger.debug(
                        f"Current mod should load after these mods for v1.4: {dependencies}"
                    )
                    add_dependency_to_mod(
                        all_mods[package_id],
                        "dependencies",
                        dependencies,
                        all_mods,
                    )

        # Current mod should be loaded BEFORE these mods
        # The current mod is a dependency for all these mods
        if all_mods[package_id].get("loadBefore"):
            dependencies = all_mods[package_id]["loadBefore"].get("li")
            if dependencies:
                logger.debug(
                    f"Current mod should load before these mods: {dependencies}"
                )
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

        if all_mods[package_id].get("forceLoadBefore"):
            dependencies = all_mods[package_id]["forceLoadBefore"].get("li")
            if dependencies:
                logger.debug(
                    f"Current mod should force load before these mods: {dependencies}"
                )
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

        if all_mods[package_id].get("loadBeforeByVersion"):
            if all_mods[package_id]["loadBeforeByVersion"].get("v1.4"):
                dependencies = all_mods[package_id]["loadBeforeByVersion"]["v1.4"].get(
                    "li"
                )
                if dependencies:
                    logger.debug(
                        f"Current mod should load before these mods for v1.4: {dependencies}"
                    )
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
            dependencies = all_mods[package_id]["incompatibleWith"].get("li")
            if dependencies:
                logger.debug(
                    f"Current mod is incompatible with these mods: {dependencies}"
                )
                add_dependency_to_mod(
                    all_mods[package_id],
                    "incompatibilities",
                    dependencies,
                    all_mods,
                )
    logger.info("Finished adding dependencies through About.xml information")
    logger.info(f"Total number of dependencies: {_get_num_dependencies(all_mods)}")

    # RimPy's references depdencies based on publisher ID, not package ID
    # Create a temporary publisher ID -> package ID dict here
    # This cooresponds with the folder name of the folder used to "contain" the mod in the Steam mods directory
    # TODO: optimization: maybe everything could be based off publisher ID
    # TODO: optimization: all of this (and communityRules.json parsing) could probably be done in the first loop
    # if steam_db_rules:
    #     folder_to_package_id = {}
    #     for package_id, mod_data in all_mods.items():
    #         if mod_data.get("folder"):
    #             folder_to_package_id[mod_data["folder"]] = mod_data["packageId"]

    #     for folder_id, mod_data in steam_db_rules.items():
    #         # We could use `folder_in in folder_to_package_id` too
    #         if mod_data["packageId"].lower() in all_mods:
    #             for dependency_folder_id in mod_data["dependencies"]:
    #                 if dependency_folder_id in folder_to_package_id:
    #                     # This means the dependency is in all mods
    #                     dependency_package_id = folder_to_package_id[dependency_folder_id]
    #                     add_dependency_to_mod(
    #                         all_mods.get(mod_data["packageId"].lower()),
    #                         "dependencies",
    #                         dependency_package_id.lower(),
    #                         all_mods
    #                     )
    # Add dependencies to installed mods based on dependencies from community rules
    logger.info("Starting adding dependencies through Community Rules")
    if community_rules:
        for package_id in community_rules:
            # TODO: requiring the package be in all_mods should be fine, as
            # if the mod doesn't exist all_mods, then either mod_data or dependency_id
            # will be None, and then we don't insert a dependency
            if package_id in all_mods:
                logger.debug(f"Current mod: {package_id}")
                load_before_deps = community_rules[package_id].get("loadBefore")
                if load_before_deps:
                    logger.debug(
                        f"Current mod should load before these mods: {load_before_deps}"
                    )
                    for dependency_id in load_before_deps:
                        # Current mod should be loaded BEFORE these mods
                        add_dependency_to_mod(
                            all_mods.get(dependency_id.lower()),
                            "dependencies",
                            package_id.lower(),
                            all_mods,
                        )
                load_after_deps = community_rules[package_id].get("loadAfter")
                if load_after_deps:
                    logger.debug(
                        f"Current mod should load after these mods: {load_after_deps}"
                    )
                    for dependency_id in load_after_deps:
                        # Current mod should be loaded AFTER these mods
                        add_dependency_to_mod(
                            all_mods.get(
                                package_id.lower()
                            ),  # Community rules may be referencing not-installed mod
                            "dependencies",
                            dependency_id.lower(),
                            all_mods,
                        )
    logger.info("Finished adding dependencies through Community Rules")
    logger.info(f"Total number of dependencies: {_get_num_dependencies(all_mods)}")
    logger.info("Returing all mods now")
    return all_mods


def _get_num_dependencies(all_mods: Dict[str, Any]) -> None:
    """Debug func for getting total number of dependencies"""
    counter = 0
    for package_id, mod_data in all_mods.items():
        if mod_data.get("dependencies"):
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
    logger.debug(
        f"Adding to key [{new_data_key}], packages [{dependency_or_dependency_ids}], for mod data: {mod_data}"
    )
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
                        all_mods[dependency_id]["isDependencyOf"].add(
                            mod_data["packageId"]
                        )
            elif isinstance(dependency_or_dependency_ids[0], dict):
                for dependency in dependency_or_dependency_ids:
                    dependency_id = dependency["packageId"].lower()
                    if dependency_id in all_mods:
                        mod_data[new_data_key].add(dependency_id)
                        if "isDependencyOf" not in all_mods[dependency_id]:
                            all_mods[dependency_id]["isDependencyOf"] = set()
                        all_mods[dependency_id]["isDependencyOf"].add(
                            mod_data["packageId"]
                        )


def get_game_version(game_path: str) -> str:
    """
    This function starts the Rimworld game version string from the file
    'Version.txt' that is found in the configured game directory.

    :param game_path: path to Rimworld game
    :return: the game version as a string
    """
    logger.info(f"Getting game version from Game Folder: {game_path}")
    version = ""
    if platform.system() == "Darwin" and game_path:
        game_path = os.path.join(game_path, "RimWorldMac.app")
        logger.info(f"Running on MacOS, generating new game path: {game_path}")
    version_file_path = os.path.join(game_path, "Version.txt")
    logger.info(f"Generated Version.txt path: {version_file_path}")
    if os.path.exists(version_file_path):
        logger.info("Version.txt path exists")
        with open(version_file_path) as f:
            version = f.read()
            logger.info(f"Retrieved game version from Version.txt: {version.strip()}")
    else:
        logger.error(
            f"The provided Version.txt path does not exist: {version_file_path}"
        )
        show_warning(
            f"Unable to get data for game version.\nThe path [{game_path}] is invalid.\nCheck that your paths are set correctly."
        )
    logger.info(
        f"Finished getting game version from Game Folder, returning now: {version.strip()}"
    )
    return version.strip()


def get_active_mods_from_config(config_path: str) -> Dict[str, Any]:
    """
    Given a path to a file in the ModsConfig.xml format, return the
    mods in the active mods section.

    :param path: path to a ModsConfig.xml file
    :return: a Dict keyed to mod package ids
    """
    logger.info(f"Getting active mods with Config Path: {config_path}")
    mod_data = xml_path_to_json(config_path)
    if mod_data:
        if mod_data.get("ModsConfigData"):
            if mod_data["ModsConfigData"].get("activeMods"):
                if mod_data["ModsConfigData"]["activeMods"].get("li"):
                    empty_active_mods_dict = {}
                    for package_id in mod_data["ModsConfigData"]["activeMods"]["li"]:
                        empty_active_mods_dict[package_id.lower()] = {}
                    logger.info(
                        f"Returning empty active mods dict with {len(empty_active_mods_dict)} entries"
                    )
                    return empty_active_mods_dict
        logger.error(f"Invalid ModsConfig.xml format: {mod_data}")
        # TODO: show warning invalid mods config format
        return {}
    logger.error(f"Empty ModsConfig.xml: {mod_data}")
    show_warning(
        f"Unable to get data for active mods.\nThe path [{config_path}] is invalid.\nCheck that your paths are set correctly."
    )
    return {}


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
    logger.info("Populating empty active mods with data")
    populated_mods = unpopulated_mods.copy()
    invalid_mods = []
    for mod_package_id in unpopulated_mods:
        # Cross reference package ids with mods in the workshop folder.
        # If unable to, that means either the mod hasn't been downloaded
        # of it is an invalid entry.
        if mod_package_id in workshop_and_expansions:
            populated_mods[mod_package_id] = workshop_and_expansions[mod_package_id]
        else:
            logger.warning(
                f"Unable to find local/workshop data for listed active mod: {mod_package_id}"
            )
            invalid_mods.append(mod_package_id)
            del populated_mods[mod_package_id]
            # populated_mods[mod_package_id] = {"name": f"ERROR({mod_package_id})", "packageId": mod_package_id}
    logger.info("Finished populating empty active mods with data")
    return populated_mods, invalid_mods


def merge_mod_data(*dict_args) -> Dict[str, Any]:
    """
    Given any number of dictionaries, shallow copy and merge into a new dict,
    precedence goes to key-value pairs in latter dictionaries.
    """
    logger.info("Merging LOCAL mods with WORKSHOP mods")
    result = {}
    for dictionary in dict_args:
        result.update(dictionary)
    logger.debug(f"Merged LOCAL and WORKSHOP mods: {result}")
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
    logger.info(
        "Generating inactive mod lists from subtracting all mods with active mods"
    )
    inactive_mods = workshop_and_expansions.copy()
    # For each mod in active mods, remove from workshop_and_expansions
    for mod_package_id in active_mods:
        if mod_package_id in workshop_and_expansions:
            del inactive_mods[mod_package_id]
    logger.info("Finished generating inactive mods list")
    return inactive_mods
