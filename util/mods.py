import json
import logging
import os
import platform
import re
import traceback
from typing import Any, Dict, List, Optional, Tuple

from util.error import show_warning
from util.schema import validate_mods_config_format
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
        list_of_violating_mods = ""
        for invalid_mod in invalid_mods:
            list_of_violating_mods = list_of_violating_mods + f"* {invalid_mod}\n"
        show_warning(
            text="Could not find data for some mods",
            information=(
                "The following list of mods were set active in your ModsConfig.xml but "
                "no data could be found from the workshop or in your local mods. "
                "Did you set your game install and workshop/local mods path correctly?"
            ),
            details=list_of_violating_mods,
        )

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
        invalid_dirs = []
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
                    invalid_dirs.append(file.name)
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
        if invalid_dirs:
            logger.warning(
                f"The following scanned dirs did not contain mod info: {invalid_dirs}"
            )
    else:
        logger.error(f"The provided mods path does not exist: {mods_path}")
        if mods_path:
            show_warning(
                text="One or more set paths do not exist",
                information=(
                    f"The path set for {intent} does not exist: [{mods_path}]. This will affect RimSort's "
                    "ability to collect mod data. Please check that your path is set correctly."
                ),
            )
    logger.info(f"Finished parsing mod data for intent: {intent}")
    return mods


def get_installed_expansions(game_path: str, game_version: str) -> Dict[str, Any]:
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
    for package_id, data in mod_data.items():
        if package_id == "ludeon.rimworld":
            data["name"] = "Core (Base game)"
        elif package_id == "ludeon.rimworld.royalty":
            data["name"] = "Royalty (DLC #1)"
        elif package_id == "ludeon.rimworld.ideology":
            data["name"] = "Ideology (DLC #2)"
        elif package_id == "ludeon.rimworld.biotech":
            data["name"] = "Biotech (DLC #3)"
        else:
            logger.error(
                f"An unknown mod has been found in the expansions folder: {package_id} {data}"
            )
        data["supportedVersions"] = {"li": game_version}
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
        text="Steam dependency database not found",
        information=(
            "RimSort relies on RimPy's steam database to collect mod dependencies listed "
            "on Steam but not in mod packages themselves. Not having this database means "
            "a lower accuracy for surfacing mod dependencies. RimSort was unable to find "
            "RimPy in your workshop or local mods folder. Do you have the mod installed "
            "and/or are your paths set correctly?"
        ),
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
        text="Community load order rules not found",
        information=(
            "RimSort relies on RimPy's community rules for mod load order rules that "
            "are not in mod packages themselves. Not having these rules means "
            "(potentially) inaccuracies with the auto-sort function. RimSort was unable to find "
            "RimPy in your workshop or local mods folder. Do you have the mod installed "
            "and/or are your paths set correctly?"
        ),
    )
    return {}


def get_dependencies_for_mods(
    expansions: Dict[str, Any],
    mods: Dict[str, Any],
    steam_db_rules: Dict[str, Any],
    community_rules: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
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
    logger.info(
        f"Total number of loadTheseBefore rules: {_get_num_dependencies(all_mods, 'loadTheseBefore')}"
    )
    logger.info(
        f"Total number of loadTheseAfter rules: {_get_num_dependencies(all_mods, 'loadTheseAfter')}"
    )
    logger.info(
        f"Total number of dependencies: {_get_num_dependencies(all_mods, 'dependencies')}"
    )
    logger.info(
        f"Total number of incompatibilities: {_get_num_dependencies(all_mods, 'incompatibilities')}"
    )
    logger.info("Starting adding dependencies through About.xml information")
    for package_id in all_mods:
        logger.debug(f"Current mod: {package_id}")

        # modDependencies are not equal to mod load order rules
        if all_mods[package_id].get("modDependencies"):
            dependencies = all_mods[package_id]["modDependencies"].get("li")
            if dependencies:
                logger.debug(f"Current mod requires these mods to work: {dependencies}")
                add_dependency_to_mod(all_mods[package_id], dependencies, all_mods)

        if all_mods[package_id].get("modDependenciesByVersion"):
            if all_mods[package_id]["modDependenciesByVersion"].get("v1.4"):
                dependencies_by_ver = all_mods[package_id]["modDependenciesByVersion"][
                    "v1.4"
                ].get("li")
                if dependencies_by_ver:
                    logger.debug(
                        f"Current mod requires these mods by version to work: {dependencies_by_ver}"
                    )
                    add_dependency_to_mod(
                        all_mods[package_id], dependencies_by_ver, all_mods
                    )

        if all_mods[package_id].get("incompatibleWith"):
            incompatibilities = all_mods[package_id]["incompatibleWith"].get("li")
            if incompatibilities:
                logger.debug(
                    f"Current mod is incompatible with these mods: {incompatibilities}"
                )
                add_incompatibility_to_mod(
                    all_mods[package_id], incompatibilities, all_mods
                )

        if all_mods[package_id].get("incompatibleWithByVersion"):
            if all_mods[package_id]["incompatibleWithByVersion"].get("v1.4"):
                incompatibilities_by_ver = all_mods[package_id][
                    "incompatibleWithByVersion"
                ]["v1.4"].get("li")
                if incompatibilities_by_ver:
                    logger.debug(
                        f"Current mod is incompatible by version with these mods: {incompatibilities_by_ver}"
                    )
                    add_incompatibility_to_mod(
                        all_mods[package_id], incompatibilities_by_ver, all_mods
                    )

        # Current mod should be loaded AFTER these mods. These mods can be thought
        # of as "load these before". These are not necessarily dependencies in the sense
        # that they "depend" on them. But, if they exist in the same mod list, they
        # should be loaded before.
        if all_mods[package_id].get("loadAfter"):
            load_these_before = all_mods[package_id]["loadAfter"].get("li")
            if load_these_before:
                logger.debug(
                    f"Current mod should load after these mods: {load_these_before}"
                )
                add_load_rule_to_mod(
                    all_mods[package_id],
                    load_these_before,
                    "loadTheseBefore",
                    "loadTheseAfter",
                    all_mods,
                )

        if all_mods[package_id].get("forceLoadAfter"):
            force_load_these_before = all_mods[package_id]["forceLoadAfter"].get("li")
            if force_load_these_before:
                logger.debug(
                    f"Current mod should force load after these mods: {force_load_these_before}"
                )
                add_load_rule_to_mod(
                    all_mods[package_id],
                    force_load_these_before,
                    "loadTheseBefore",
                    "loadTheseAfter",
                    all_mods,
                )

        if all_mods[package_id].get("loadAfterByVersion"):
            if all_mods[package_id]["loadAfterByVersion"].get("v1.4"):
                load_these_before_by_ver = all_mods[package_id]["loadAfterByVersion"][
                    "v1.4"
                ].get("li")
                if load_these_before_by_ver:
                    logger.debug(
                        f"Current mod should load after these mods for v1.4: {load_these_before_by_ver}"
                    )
                    add_load_rule_to_mod(
                        all_mods[package_id],
                        load_these_before_by_ver,
                        "loadTheseBefore",
                        "loadTheseAfter",
                        all_mods,
                    )

        # Current mod should be loaded BEFORE these mods
        # The current mod is a dependency for all these mods
        if all_mods[package_id].get("loadBefore"):
            load_these_after = all_mods[package_id]["loadBefore"].get("li")
            if load_these_after:
                logger.debug(
                    f"Current mod should load before these mods: {load_these_after}"
                )
                add_load_rule_to_mod(
                    all_mods[package_id],
                    load_these_after,
                    "loadTheseAfter",
                    "loadTheseBefore",
                    all_mods,
                )

        if all_mods[package_id].get("forceLoadBefore"):
            force_load_these_after = all_mods[package_id]["forceLoadBefore"].get("li")
            if force_load_these_after:
                logger.debug(
                    f"Current mod should force load before these mods: {force_load_these_after}"
                )
                add_load_rule_to_mod(
                    all_mods[package_id],
                    force_load_these_after,
                    "loadTheseAfter",
                    "loadTheseBefore",
                    all_mods,
                )

        if all_mods[package_id].get("loadBeforeByVersion"):
            if all_mods[package_id]["loadBeforeByVersion"].get("v1.4"):
                load_these_after_by_ver = all_mods[package_id]["loadBeforeByVersion"][
                    "v1.4"
                ].get("li")
                if load_these_after_by_ver:
                    logger.debug(
                        f"Current mod should load before these mods for v1.4: {load_these_after_by_ver}"
                    )
                    add_load_rule_to_mod(
                        all_mods[package_id],
                        load_these_after_by_ver,
                        "loadTheseAfter",
                        "loadTheseBefore",
                        all_mods,
                    )

    logger.info("Finished adding dependencies through About.xml information")
    logger.info(
        f"Total number of loadTheseBefore rules: {_get_num_dependencies(all_mods, 'loadTheseBefore')}"
    )
    logger.info(
        f"Total number of loadTheseAfter rules: {_get_num_dependencies(all_mods, 'loadTheseAfter')}"
    )
    logger.info(
        f"Total number of dependencies: {_get_num_dependencies(all_mods, 'dependencies')}"
    )
    logger.info(
        f"Total number of incompatibilities: {_get_num_dependencies(all_mods, 'incompatibilities')}"
    )

    # RimPy's references depdencies based on publisher ID, not package ID
    # TODO: optimization: maybe everything could be based off publisher ID
    info_from_steam_package_id_to_name = {}
    if steam_db_rules:
        tracking_dict: dict[str, set[str]] = {}
        steam_id_to_package_id = {}

        # Iterate through all workshop items in the Steam DB.
        for folder_id, mod_data in steam_db_rules.items():
            db_package_id = mod_data["packageId"].lower()

            # Record the Steam ID => package_id
            steam_id_to_package_id[folder_id] = db_package_id

            # Also record package_ids to names (use in tooltips)
            info_from_steam_package_id_to_name[db_package_id] = mod_data["name"]

            # If the package_id is in all_mods...
            if db_package_id in all_mods:
                # Iterate through each dependency (Steam ID) listed on Steam
                for dependency_folder_id, steam_dep_data in mod_data[
                    "dependencies"
                ].items():
                    if db_package_id not in tracking_dict:
                        tracking_dict[db_package_id] = set()
                    # Add Steam ID to dependencies of mod
                    tracking_dict[db_package_id].add(dependency_folder_id)

        # For each mod that exists in all_mods -> dependencies (in Steam ID form)
        for installed_mod_id, set_of_dependency_steam_ids in tracking_dict.items():
            for dependency_steam_id in set_of_dependency_steam_ids:
                # Dependencies are added as package_ids. We should be able to
                # resolve the package_id from the Steam ID for any mod, unless
                # the DB.json actually references a Steam ID that itself does not
                # wire to a package_id.
                if dependency_steam_id in steam_id_to_package_id:
                    add_single_str_dependency_to_mod(
                        all_mods[installed_mod_id],  # Already checked above
                        steam_id_to_package_id[dependency_steam_id],
                        all_mods,
                    )
                else:
                    logger.error(
                        f"package_id not found for steam id [{dependency_steam_id}] for Steam db.json"
                    )

    # Add load order to installed mods based on dependencies from community rules
    logger.info("Starting adding dependencies through Community Rules")
    if community_rules:
        for package_id in community_rules:
            # Note: requiring the package be in all_mods should be fine, as
            # if the mod doesn't exist all_mods, then either mod_data or dependency_id
            # will be None, and then we don't insert a dependency
            if package_id.lower() in all_mods:  # all_mods is normalized
                logger.debug(f"Current mod: {package_id} (we use normalized)")

                load_these_after = community_rules[package_id].get("loadBefore")
                if load_these_after:
                    logger.debug(
                        f"Current mod should load before these mods: {load_these_after}"
                    )
                    # In Rimpy, load_these_after is at least an empty dict
                    # Cannot call add_load_rule_to_mod outside of this for loop,
                    # as that expects a list
                    for load_this_after in load_these_after:
                        add_load_rule_to_mod(
                            all_mods[package_id.lower()],  # Already checked above
                            load_this_after,  # Lower() done in call
                            "loadTheseAfter",
                            "loadTheseBefore",
                            all_mods,
                        )

                load_these_before = community_rules[package_id].get("loadAfter")
                if load_these_before:
                    logger.debug(
                        f"Current mod should load after these mods: {load_these_before}"
                    )
                    # In Rimpy, load_these_before is at least an empty dict
                    for load_this_before in load_these_before:
                        add_load_rule_to_mod(
                            all_mods[package_id.lower()],  # Already checked above
                            load_this_before,  # Lower() done in call
                            "loadTheseBefore",
                            "loadTheseAfter",
                            all_mods,
                        )
    logger.info("Finished adding dependencies through Community Rules")
    logger.info(
        f"Total number of loadTheseBefore rules: {_get_num_dependencies(all_mods, 'loadTheseBefore')}"
    )
    logger.info(
        f"Total number of loadTheseAfter rules: {_get_num_dependencies(all_mods, 'loadTheseAfter')}"
    )
    logger.info(
        f"Total number of dependencies: {_get_num_dependencies(all_mods, 'dependencies')}"
    )
    logger.info(
        f"Total number of incompatibilities: {_get_num_dependencies(all_mods, 'incompatibilities')}"
    )
    logger.info("Returing all mods now")
    return all_mods, info_from_steam_package_id_to_name


def _get_num_dependencies(all_mods: Dict[str, Any], key_name: str) -> int:
    """Debug func for getting total number of dependencies"""
    counter = 0
    for package_id, mod_data in all_mods.items():
        if mod_data.get(key_name):
            counter = counter + len(mod_data[key_name])
    return counter


def add_dependency_to_mod(
    mod_data: Dict[str, Any],
    dependency_or_dependency_ids: Any,
    all_mods: Dict[str, Any],
) -> None:
    """
    Dependency data is collected regardless of whether or not that dependency
    is in `all_mods`. This makes sense as dependencies exist outside of the realm
    of the mods the user currently has installed. Dependencies are one-way, so
    if A depends on B, B does not necessarily depend on A.
    """
    logger.debug(
        f"Adding dependencies for packages [{dependency_or_dependency_ids}] to mod data: {mod_data}"
    )
    if mod_data:
        # Create a new key with empty set as value
        if "dependencies" not in mod_data:
            mod_data["dependencies"] = set()

        # If the value is a single dict (for modDependencies)
        if isinstance(dependency_or_dependency_ids, dict):
            if dependency_or_dependency_ids.get("packageId"):
                dependency_id = dependency_or_dependency_ids["packageId"].lower()
                # if dependency_id in all_mods:
                # ^ dependencies are required regardless of whether they are in all_mods
                mod_data["dependencies"].add(dependency_id)
            else:
                logger.error(
                    f"Dependency dict does not contain packageId: [{dependency_or_dependency_ids}]"
                )
        # If the value is a LIST of dicts
        elif isinstance(dependency_or_dependency_ids, list):
            if isinstance(dependency_or_dependency_ids[0], dict):
                for dependency in dependency_or_dependency_ids:
                    if dependency.get("packageId"):
                        # Below works with `MayRequire`` dependencies
                        dependency_id = dependency["packageId"].lower()
                        # if dependency_id in all_mods:
                        # ^ dependencies are required regardless of whether they are in all_mods
                        mod_data["dependencies"].add(dependency_id)
                    else:
                        logger.error(
                            f"Dependency dict does not contain packageId: [{dependency_or_dependency_ids}]"
                        )
            else:
                logger.error(
                    f"List of dependencies does not contain dicts: [{dependency_or_dependency_ids}]"
                )
        else:
            logger.error(
                f"Dependencies is not a single dict or a list of dicts: [{dependency_or_dependency_ids}]"
            )


def add_single_str_dependency_to_mod(
    mod_data: Dict[str, Any],
    dependency_id: Any,
    all_mods: Dict[str, Any],
) -> None:
    logger.debug(
        f"Adding dependencies for package [{dependency_id}] to mod data: {mod_data}"
    )
    if mod_data:
        # Create a new key with empty set as value
        if "dependencies" not in mod_data:
            mod_data["dependencies"] = set()

        # If the value is a single dict (for modDependencies)
        if isinstance(dependency_id, str):
            mod_data["dependencies"].add(dependency_id)
        else:
            logger.error(f"Dependencies is not a single str: [{dependency_id}]")


def add_incompatibility_to_mod(
    mod_data: Dict[str, Any],
    dependency_or_dependency_ids: Any,
    all_mods: Dict[str, Any],
) -> None:
    """
    Incompatibility data is collected only if that incompatibility is in `all_mods`.
    There's no need to surface incompatibilities if they aren't even downloaded.
    Reverse incompatibilities are not being added (commented out) as it has been brought
    up that in certain cases mod authors may disagree on whether each other's mods
    are incompatible with each other.
    """
    logger.debug(
        f"Adding incompatibilities for packages [{dependency_or_dependency_ids}] to mod data: {mod_data} (and reverse direction too)"
    )
    if mod_data:
        # Create a new key with empty set as value
        if "incompatibilities" not in mod_data:
            mod_data["incompatibilities"] = set()

        # If the value is a single string...
        if isinstance(dependency_or_dependency_ids, str):
            dependency_id = dependency_or_dependency_ids.lower()
            if dependency_id in all_mods:
                mod_data["incompatibilities"].add(dependency_id)
                # if "incompatibilities" not in all_mods[dependency_id]:
                #     all_mods[dependency_id]["incompatibilities"] = set()
                # all_mods[dependency_id]["incompatibilities"].add(mod_data["packageId"])

        # If the value is a LIST of strings
        elif isinstance(dependency_or_dependency_ids, list):
            if isinstance(dependency_or_dependency_ids[0], str):
                for dependency in dependency_or_dependency_ids:
                    dependency_id = dependency.lower()
                    if dependency_id in all_mods:
                        mod_data["incompatibilities"].add(dependency_id)
                        # if "incompatibilities" not in all_mods[dependency_id]:
                        #     all_mods[dependency_id]["incompatibilities"] = set()
                        # all_mods[dependency_id]["incompatibilities"].add(
                        #     mod_data["packageId"]
                        # )
            else:
                logger.error(
                    f"List of incompatibilities does not contain strings: [{dependency_or_dependency_ids}]"
                )
        else:
            logger.error(
                f"Incompatibilities is not a single string or a list of strings: [{dependency_or_dependency_ids}]"
            )


def add_load_rule_to_mod(
    mod_data: Dict[str, Any],
    dependency_or_dependency_ids: Any,
    explicit_key: str,
    indirect_key: str,
    all_mods: Dict[str, Any],
) -> None:
    """
    Load order data is collected only if the mod referenced is in `all_mods`, as
    mods that are not installed do not need to be ordered.

    Explicit = indicates if the rule is added because it was explicitly defined
    somewhere, e.g. About.xml, or if it was inferred, e.g. If A loads after B,
    B should load before A

    Given a mod dict and a value, add the contents of value to the loadTheseBefore
    and loadTheseAfter keys in the dict. If the key does not exist, add an empty list
    at that key. This is to support load rule schemas being either strings or list of strings.

    TODO: optimization. Currently, hardcodes adding loadTheseBefore and then reasons about
    loadTheseAfter. This requires the calling part (reading About.xml and calling this function)
    to have some confusing logic for placing variables in the right position to call this func.
    Instead, expose 2 key names (explicit, indirect) as variables.

    This is by design:
    IMPORTANT!! Rules that DO NOT EXIST in all_mods ARE NOT ADDED!!
    IMPORTANT!! "Current mods" that DO NOT EXIST in all_mods WILL NOT HAVE
        DEPENDENCIES ADDED!

    :param mod_data: mod data dict to add dependencies to
    :param value: either string or list of strings (or sometimes None)
    :param workshop_and_expansions: dict of all mods to verify keys against
    """
    logger.debug(
        f"Adding load order rules containing packages [{dependency_or_dependency_ids}] for mod data: {mod_data} (and reverse direction too)"
    )
    if mod_data:
        # Create a new key with empty set as value
        if explicit_key not in mod_data:
            mod_data[explicit_key] = set()

        # If the value is a single string...
        if isinstance(dependency_or_dependency_ids, str):
            dependency_id = dependency_or_dependency_ids.lower()

            if dependency_id:
                if dependency_id in all_mods:
                    mod_data[explicit_key].add((dependency_id, True))
                    if indirect_key not in all_mods[dependency_id]:
                        all_mods[dependency_id][indirect_key] = set()
                    all_mods[dependency_id][indirect_key].add(
                        (mod_data["packageId"], False)
                    )

        # If the value is a single dict (case of MayRequire rules)
        elif isinstance(dependency_or_dependency_ids, dict):
            dependency_id = ""
            if "#text" in dependency_or_dependency_ids:
                dependency_id = dependency_or_dependency_ids["#text"].lower()
            else:
                logger.error(
                    f"Load rule with MayRequire does not contain expected #text key: {dependency_or_dependency_ids}"
                )
            if dependency_id:
                if dependency_id in all_mods:
                    mod_data[explicit_key].add((dependency_id, True))
                    if indirect_key not in all_mods[dependency_id]:
                        all_mods[dependency_id][indirect_key] = set()
                    all_mods[dependency_id][indirect_key].add(
                        (mod_data["packageId"], False)
                    )

        # If the value is a LIST of strings
        elif isinstance(dependency_or_dependency_ids, list):
            for dependency in dependency_or_dependency_ids:
                dependency_id = ""
                if isinstance(dependency, str):
                    dependency_id = dependency.lower()
                elif isinstance(dependency, dict):
                    # MayRequire may be used here
                    if "#text" in dependency:
                        dependency_id = dependency["#text"].lower()
                    else:
                        logger.error(
                            f"Load rule with MayRequire does not contain expected #text key: {dependency}"
                        )
                else:
                    logger.error(
                        f"Load rule is not an expected str or dict: {dependency}"
                    )

                if dependency_id:
                    if dependency_id in all_mods:
                        mod_data[explicit_key].add((dependency_id, True))
                        if indirect_key not in all_mods[dependency_id]:
                            all_mods[dependency_id][indirect_key] = set()
                        all_mods[dependency_id][indirect_key].add(
                            (mod_data["packageId"], False)
                        )
        else:
            logger.error(
                f"Load order rules is not a single string/dict or a list of strigs/dicts: [{dependency_or_dependency_ids}]"
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
            text="Issue Getting Game Version",
            information=(
                f"RimSort is unable to get the game version at the expected path: [{version_file_path}]. "
                f"Is your game path [{game_path}] set correctly? There should be a Version.txt "
                "file in the game install directory."
            ),
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
    if validate_mods_config_format(mod_data):
        empty_active_mods_dict: dict[str, Any] = {}
        for package_id in mod_data["ModsConfigData"]["activeMods"]["li"]:
            empty_active_mods_dict[package_id.lower()] = {}
        logger.info(
            f"Returning empty active mods dict with {len(empty_active_mods_dict)} entries"
        )
        return empty_active_mods_dict
    logger.error(f"Unable to get active mods from config with read data: {mod_data}")
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


def merge_mod_data(*dict_args: dict[str, Any]) -> Dict[str, Any]:
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


def add_more_versions_to_mod(
    mod_data: Dict[str, Any],
    version_to_add: str
) -> Dict[str, Any]:
    """
    Adds a version to the supported versions tag of a mod if needed
    """
    mod_versions = mod_data["supportedVersions"]['li']
    if isinstance(mod_versions, str):
        if mod_versions == version_to_add:
            return mod_data
        mod_data["supportedVersions"]['li'] = set()
        mod_data["supportedVersions"]['li'].add(version_to_add)
        mod_data["supportedVersions"]['li'].add(mod_versions)
        mod_data["description"] = version_to_add + "-tag added by No Version Warning-mod\n" + mod_data["description"]  
        return mod_data    
    if not isinstance(mod_versions, list):
        return mod_data    
    if version_to_add in mod_versions:
        return mod_data        
    mod_data["supportedVersions"]['li'].insert(0, version_to_add)  
    mod_data["description"] = version_to_add + "-tag added by No Version Warning-mod\n" + mod_data["description"]  
    logger.info(f"[NoVersionWarning]: Added support for game-version {version_to_add} for mod: {mod_data}")
    return mod_data


def get_modids_from_noversionwarning_xml(
    version_folder
    ):
    """
    Parses the ModIdsToFix.xml in the "No version warning" mod and returns the supported mod-ids
    """
    file_to_find = os.path.join(version_folder.path, "ModIdsToFix.xml")
    if not os.path.exists(file_to_find):
        logger.warning(f"[NoVersionWarning]: No ModIdsToFix found at {file_to_find}")            
        return None
    try:
        try:
            # Default: try to parse with UTF-8 encodnig
            version_xml_data = xml_path_to_json(file_to_find)
        except UnicodeDecodeError:
            # It may be necessary to remove all non-UTF-8 characters and parse again
            logger.warning("[NoVersionWarning]: Unable to parse no-version file with UTF-8, attempting to decode")
            version_xml_data = non_utf8_xml_path_to_json(file_to_find)
    except:
        # If there was an issue parsing the no-version file, track and exit
        logger.error(f"[NoVersionWarning]: Unable to parse no-version file with the exception: {traceback.format_exc()}")
        return None
    if not "li" in version_xml_data["ModIdsToFix"]:
        logger.warning(f"[NoVersionWarning]: No-version file has no mod-ids defined")
        return None
    return version_xml_data["ModIdsToFix"]['li']


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
