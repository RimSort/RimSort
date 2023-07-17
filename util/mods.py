import json
import os
import platform
import traceback
from time import localtime, strftime, time
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from natsort import natsorted
from requests.exceptions import HTTPError

from logger_tt import logger
from model.dialogue import show_fatal_error, show_information, show_warning
from util.constants import RIMWORLD_DLC_METADATA
from util.schema import validate_mods_config_format
from util.steam.webapi.wrapper import DynamicQuery
from util.xml import xml_path_to_json


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
                        # Below works with `MayRequire` dependencies
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
            for uuid in all_mods:
                if all_mods[uuid]["packageId"] == dependency_id:
                    mod_data["incompatibilities"].add(dependency_id)

        # If the value is a LIST of strings
        elif isinstance(dependency_or_dependency_ids, list):
            if isinstance(dependency_or_dependency_ids[0], str):
                for dependency in dependency_or_dependency_ids:
                    dependency_id = dependency.lower()
                    for uuid in all_mods:
                        if all_mods[uuid]["packageId"] == dependency_id:
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
    if mod_data:
        # Create a new key with empty set as value
        if explicit_key not in mod_data:
            mod_data[explicit_key] = set()

        # If the value is a single string...
        if isinstance(dependency_or_dependency_ids, str):
            total = 1
            dependency_id = dependency_or_dependency_ids.lower()
            for uuid in all_mods:
                if all_mods[uuid]["packageId"] == dependency_id:
                    mod_data[explicit_key].add((dependency_id, True))
                    if indirect_key not in all_mods[uuid]:
                        all_mods[uuid][indirect_key] = set()
                    all_mods[uuid][indirect_key].add((mod_data["packageId"], False))

        # If the value is a single dict (case of MayRequire rules)
        elif isinstance(dependency_or_dependency_ids, dict):
            total = len(dependency_or_dependency_ids)
            dependency_id = ""
            if "#text" in dependency_or_dependency_ids:
                dependency_id = dependency_or_dependency_ids["#text"].lower()
            else:
                logger.error(
                    f"Load rule with MayRequire does not contain expected #text key: {dependency_or_dependency_ids}"
                )
            if dependency_id:
                for uuid in all_mods:
                    if all_mods[uuid]["packageId"] == dependency_id:
                        mod_data[explicit_key].add((dependency_id, True))
                        if indirect_key not in all_mods[uuid]:
                            all_mods[uuid][indirect_key] = set()
                        all_mods[uuid][indirect_key].add((mod_data["packageId"], False))

        # If the value is a LIST of strings
        elif isinstance(dependency_or_dependency_ids, list):
            total = len(dependency_or_dependency_ids)
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
                    for uuid in all_mods:
                        if all_mods[uuid]["packageId"] == dependency_id:
                            mod_data[explicit_key].add((dependency_id, True))
                            if indirect_key not in all_mods[uuid]:
                                all_mods[uuid][indirect_key] = set()
                            all_mods[uuid][indirect_key].add(
                                (mod_data["packageId"], False)
                            )
        else:
            logger.error(
                f"Load order rules is not a single string/dict or a list of strigs/dicts: [{dependency_or_dependency_ids}]"
            )
            return


def add_dependency_to_mod_from_steamdb(
    mod_data: Dict[str, Any], dependency_id: Any, all_mods: Dict[str, Any]
) -> None:
    mod_name = mod_data.get("name")
    if mod_data:
        # Create a new key with empty set as value
        if "dependencies" not in mod_data:
            mod_data["dependencies"] = set()

        # If the value is a single str (for steamDB)
        if isinstance(dependency_id, str):
            mod_data["dependencies"].add(dependency_id)
        else:
            logger.error(f"Dependencies is not a single str: [{dependency_id}]")
    logger.debug(f"Added dependency to [{mod_name}] from SteamDB: [{dependency_id}]")


def get_active_inactive_mods(
    config_path: str,
    workshop_and_expansions: Dict[str, Any],
    duplicate_mods_warning_toggle: bool,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], list]:
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
    # Calculate duplicate mods (SCHEMA: {str packageId: {str uuid: list[str data_source, str mod_path]} })
    duplicate_mods = {}
    packageId_to_uuids = {}
    for mod_uuid, mod_data in workshop_and_expansions.items():
        try:
            data_source = mod_data["data_source"]  # Track data_source
        except:
            print(mod_data)
        package_id = mod_data["packageId"]  # Track packageId to UUIDs
        mod_path = mod_data["path"]  # Track path
        if package_id not in packageId_to_uuids:
            packageId_to_uuids[package_id] = {}
        packageId_to_uuids[package_id][mod_uuid] = [data_source, mod_path]
    duplicate_mods = packageId_to_uuids.copy()
    for package_id in packageId_to_uuids:  # If a packageId has > 1 UUID listed
        if not len(packageId_to_uuids[package_id]) > 1:  # ...it is not a duplicate mod
            # Remove non-duplicates from our tracking dict
            del duplicate_mods[package_id]
    # Get the list of active mods and populate data from workshop + expansions
    logger.info(f"Calling get active mods with Config Path: {config_path}")
    active_mods, missing_mods = get_active_mods_from_config(
        config_path, duplicate_mods, workshop_and_expansions
    )
    # Return an error if some active mod was in the ModsConfig but no data
    # could be found for it
    if duplicate_mods:
        logger.debug(
            f"The following duplicate mods were found in the list of active mods: {duplicate_mods}"
        )
        if duplicate_mods_warning_toggle:
            list_of_duplicate_mods = ""
            for duplicate_mod in duplicate_mods.keys():
                list_of_duplicate_mods = list_of_duplicate_mods + f"* {duplicate_mod}\n"
            show_warning(
                text="Duplicate mods found for package ID(s) in your ModsConfig.xml (active mods list)",
                information=(
                    "The following list of mods were set active in your ModsConfig.xml and "
                    "duplicate instances were found of these mods in your mod data sources. "
                    "The vanilla game will use the first 'local mod' of a particular package ID "
                    "that is found - so RimSort will also adhere to this logic."
                ),
                details=list_of_duplicate_mods,
            )
        else:
            logger.debug(
                "User preference is not configured to display duplicate mods. Skipping..."
            )
    # Get the inactive mods by subtracting active mods from workshop + expansions
    logger.info("Calling get inactive mods")
    inactive_mods = get_inactive_mods(workshop_and_expansions, active_mods)
    logger.info(f"# active mods: {len(active_mods)}")
    logger.info(f"# inactive mods: {len(inactive_mods)}")
    logger.info(f"# duplicate mods: {len(duplicate_mods)}")
    logger.info(f"# missing mods: {len(missing_mods)}")
    return active_mods, inactive_mods, duplicate_mods, missing_mods


def get_active_mods_from_config(
    config_path: str,
    duplicate_mods: Dict[str, Any],
    workshop_and_expansions: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Given a path to a file in the ModsConfig.xml format, return the
    mods in the active mods section.
    :param path: path to a ModsConfig.xml file
    :return: a Dict keyed to mod package ids
    """
    logger.info(f"Getting active mods with Config Path: {config_path}")
    active_mods_dict: dict[str, Any] = {}
    duplicates_processed = []
    missing_mods = []
    mod_data = xml_path_to_json(config_path)
    populated_mods = []
    to_populate = []
    if validate_mods_config_format(mod_data):
        for package_id in mod_data["ModsConfigData"]["activeMods"][
            "li"
        ]:  # Go through active mods
            package_id_normalized = package_id.lower()
            to_populate.append(package_id_normalized)
            for (
                uuid
            ) in workshop_and_expansions:  # Find this mods' metadata packageId & path
                metadata_package_id = workshop_and_expansions[uuid]["packageId"]
                metadata_path = workshop_and_expansions[uuid]["path"]
                package_id_steam_suffix = "_steam"
                package_id_normalized_stripped = package_id_normalized.replace(
                    package_id_steam_suffix, ""
                )
                if metadata_package_id == package_id_normalized:
                    # If the mod to populate DOESN'T have duplicates, populate like normal
                    if not package_id_normalized in duplicate_mods.keys():
                        logger.debug(f"Adding mod to active: {package_id_normalized}")
                        populated_mods.append(package_id_normalized)
                        active_mods_dict[uuid] = workshop_and_expansions[uuid]
                    # ...else, the mod to populate DOES have duplicates found in metadata
                    else:  # If we haven't already processed this duplicate
                        if not package_id_normalized in duplicates_processed:
                            # Track this dupe - it should only need processed once
                            duplicates_processed.append(package_id_normalized)
                            logger.debug(f"DUPLICATE FOUND: {package_id_normalized}")
                            expansion_paths = []
                            local_paths = []
                            workshop_paths = []
                            # Go through each duplicate path by data_source
                            for dupe_uuid, data_source in duplicate_mods[
                                package_id_normalized
                            ].items():
                                # Compile lists of our paths by source
                                # logger.debug(f"{dupe_uuid}: {data_source}")
                                if data_source[0] == "expansion":
                                    expansion_paths.append(data_source[1])
                                if data_source[0] == "local":
                                    local_paths.append(data_source[1])
                                if data_source[0] == "workshop":
                                    workshop_paths.append(data_source[1])
                            # Naturally sorted paths
                            natsort_expansion_paths = natsorted(expansion_paths)
                            natsort_local_paths = natsorted(local_paths)
                            natsort_workshop_paths = natsorted(workshop_paths)
                            logger.debug(
                                f"Natsorted expansion paths: {natsort_expansion_paths}"
                            )
                            logger.debug(
                                f"Natsorted local paths: {natsort_local_paths}"
                            )
                            logger.debug(
                                f"Natsorted workshop paths: {natsort_workshop_paths}"
                            )
                            # SOURCE PRIORITY: Expansions > Local > Workshop
                            # IF we have multiple duplicate paths in SAME data_source, set the first naturally occurring mod
                            # by path in the active_mods_dict, any additional uuids will be later set to inactive.
                            # OTHERWISE we use the first path we find in order of SOURCE PRIORITY
                            logger.debug(metadata_path)
                            logger.debug(expansion_paths)
                            logger.debug(local_paths)
                            logger.debug(workshop_paths)
                            if len(natsort_expansion_paths) > 1:  # EXPANSIONS
                                if metadata_path == natsort_expansion_paths[0]:
                                    logger.warning(
                                        f"Using duplicate expansion for {package_id_normalized}: {metadata_path}"
                                    )
                                    logger.warning(
                                        f"Using mod located at: {metadata_path}"
                                    )
                                    populated_mods.append(package_id_normalized)
                                    active_mods_dict[uuid] = workshop_and_expansions[
                                        uuid
                                    ]
                                    continue
                            # If the metadata_path is even in our expansion_paths <=1 item list for this duplicate (if 0 count, this would be false):
                            elif metadata_path in expansion_paths:
                                logger.warning(
                                    f"Using duplicate expansion for {package_id_normalized}: {metadata_path}"
                                )
                                populated_mods.append(package_id_normalized)
                                active_mods_dict[uuid] = workshop_and_expansions[uuid]
                                continue
                            if len(natsort_local_paths) > 1:  # LOCAL mods
                                if metadata_path == natsort_local_paths[0]:
                                    logger.warning(
                                        f"Using duplicate local mod for {package_id_normalized}: {metadata_path}"
                                    )
                                    populated_mods.append(package_id_normalized)
                                    active_mods_dict[uuid] = workshop_and_expansions[
                                        uuid
                                    ]
                                    continue
                            # If the metadata_path is even in our local_paths <=1 item list for this duplicate (if 0 count, this would be false):
                            elif metadata_path in local_paths:
                                logger.warning(
                                    f"Using duplicate local mod for {package_id_normalized}: {metadata_path}"
                                )
                                populated_mods.append(package_id_normalized)
                                active_mods_dict[uuid] = workshop_and_expansions[uuid]
                                continue
                            if len(natsort_workshop_paths) > 1:  # WORKSHOP mods
                                if metadata_path == natsort_workshop_paths[0]:
                                    logger.warning(
                                        f"Using duplicate workshop mod for {package_id_normalized}: {metadata_path}"
                                    )
                                    populated_mods.append(package_id_normalized)
                                    active_mods_dict[uuid] = workshop_and_expansions[
                                        uuid
                                    ]
                                    continue
                            # If the metadata_path is even in our workshop_paths <=1 item list for this duplicate (if 0 count, this would be false):
                            elif metadata_path in workshop_paths:
                                logger.warning(
                                    f"Using duplicate workshop mod for {package_id_normalized}: {metadata_path}"
                                )
                                populated_mods.append(package_id_normalized)
                                active_mods_dict[uuid] = workshop_and_expansions[uuid]
                                continue
                # Otherwise check for `_steam`
                elif metadata_package_id == package_id_normalized_stripped:
                    if (
                        package_id_steam_suffix in package_id_normalized
                    ):  # If `_steam`, we check for dupes
                        if (
                            not package_id_normalized_stripped in duplicate_mods.keys()
                        ):  # If no dupes, just add whatever we find
                            logger.debug(
                                f"Adding mod to active: {package_id_normalized_stripped}"
                            )
                            populated_mods.append(package_id_normalized_stripped)
                            active_mods_dict[uuid] = workshop_and_expansions[uuid]
                        else:  # ...else, it has duplicates, so we find the Steam mod specifically
                            if (
                                not package_id_normalized_stripped
                                in duplicates_processed
                            ):  # If we haven't already processed this duplicate
                                logger.info(
                                    f"Handling special case with `_steam` suffix for packageId: {package_id_normalized}"
                                )
                                logger.debug(
                                    f"DUPLICATE FOUND: {package_id_normalized_stripped}"
                                )
                                workshop_paths = []
                                local_paths = []
                                # Go through each duplicate path by data_source
                                for dupe_uuid, data_source in duplicate_mods[
                                    package_id_normalized_stripped
                                ].items():
                                    # Compile lists of our paths by source
                                    # logger.debug(f"{dupe_uuid}: {data_source}")
                                    if data_source[0] == "workshop":
                                        workshop_paths.append(data_source[1])
                                    if data_source[0] == "local":
                                        local_paths.append(data_source[1])
                                # Naturally sorted paths
                                natsort_workshop_paths = natsorted(workshop_paths)
                                natsort_local_paths = natsorted(local_paths)
                                logger.debug(
                                    f"Natsorted workshop paths: {natsort_workshop_paths}"
                                )
                                logger.debug(
                                    f"Natsorted local paths: {natsort_local_paths}"
                                )
                                # Explicit case for mods with `_steam` suffix
                                # SOURCE PRIORITY: Workshop > Local (this should NOT be used for expansions...)
                                # We use the first path we find in order of SOURCE PRIORITY
                                logger.debug(metadata_path)
                                logger.debug(workshop_paths)
                                logger.debug(local_paths)
                                if not metadata_path in workshop_paths:
                                    logger.debug(
                                        f"Skipping local instance of duplicate `_steam` suffixed mod: {metadata_path}"
                                    )
                                    continue
                                else:
                                    logger.warning(
                                        f"Using duplicate workshop mod for {package_id_normalized_stripped}: {metadata_path}"
                                    )
                                    populated_mods.append(package_id_normalized)
                                    active_mods_dict[uuid] = workshop_and_expansions[
                                        uuid
                                    ]
                                    # Track this dupe once we find the steam mod
                                    duplicates_processed.append(package_id_normalized)
                                    duplicates_processed.append(
                                        package_id_normalized_stripped
                                    )
                                    continue

        missing_mods = list(set(to_populate) - set(populated_mods))
        logger.debug(
            f"Generated active_mods_dict with {len(active_mods_dict)} entries: {active_mods_dict}"
        )
        return active_mods_dict, missing_mods
    else:
        logger.error(
            f"Unable to get active mods from config with read data: {mod_data}"
        )
        return active_mods_dict, missing_mods


def get_dependencies_for_mods(
    all_mods: Dict[str, Any],
    steam_db: Dict[str, Any],
    community_rules: Dict[str, Any],
    user_rules: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Iterate through each workshop mod + known expansion + base game and add new key-values
    describing its dependencies (what it should be loaded after), and incompatibilities
    (currently not being used).

    :param all_mods: dict of all mods from local mod (and expansion) metadata
    :param steam_db: a dict containing the ["database"] rules from external metadata
    :param community_rules: dict of community established rules from external metadata
    :param user_rules: dict of user-configured rules from external metadata
    :return workshop_and_expansions: workshop mods + official modules with dependency data
    """
    logger.info("Starting getting dependencies for all mods")

    # Add dependencies to installed mods based on dependencies listed in About.xml TODO manifest.xml
    logger.info("Starting adding dependencies through About.xml information")
    for uuid in all_mods:
        logger.debug(f"UUID: {uuid} packageId: " + all_mods[uuid].get("packageId"))

        # modDependencies are not equal to mod load order rules
        if all_mods[uuid].get("modDependencies"):
            dependencies = all_mods[uuid]["modDependencies"].get("li")
            if dependencies:
                logger.debug(f"Current mod requires these mods to work: {dependencies}")
                add_dependency_to_mod(all_mods[uuid], dependencies, all_mods)

        if all_mods[uuid].get("modDependenciesByVersion"):
            if all_mods[uuid]["modDependenciesByVersion"].get("v1.4"):
                dependencies_by_ver = all_mods[uuid]["modDependenciesByVersion"][
                    "v1.4"
                ].get("li")
                if dependencies_by_ver:
                    logger.debug(
                        f"Current mod requires these mods by version to work: {dependencies_by_ver}"
                    )
                    add_dependency_to_mod(all_mods[uuid], dependencies_by_ver, all_mods)

        if all_mods[uuid].get("incompatibleWith"):
            incompatibilities = all_mods[uuid]["incompatibleWith"].get("li")
            if incompatibilities:
                logger.debug(
                    f"Current mod is incompatible with these mods: {incompatibilities}"
                )
                add_incompatibility_to_mod(all_mods[uuid], incompatibilities, all_mods)

        if all_mods[uuid].get("incompatibleWithByVersion"):
            if all_mods[uuid]["incompatibleWithByVersion"].get("v1.4"):
                incompatibilities_by_ver = all_mods[uuid]["incompatibleWithByVersion"][
                    "v1.4"
                ].get("li")
                if incompatibilities_by_ver:
                    logger.debug(
                        f"Current mod is incompatible by version with these mods: {incompatibilities_by_ver}"
                    )
                    add_incompatibility_to_mod(
                        all_mods[uuid], incompatibilities_by_ver, all_mods
                    )

        # Current mod should be loaded AFTER these mods. These mods can be thought
        # of as "load these before". These are not necessarily dependencies in the sense
        # that they "depend" on them. But, if they exist in the same mod list, they
        # should be loaded before.
        if all_mods[uuid].get("loadAfter"):
            try:
                load_these_before = all_mods[uuid]["loadAfter"].get("li")
                if load_these_before:
                    logger.debug(
                        f"Current mod should load after these mods: {load_these_before}"
                    )
                    add_load_rule_to_mod(
                        all_mods[uuid],
                        load_these_before,
                        "loadTheseBefore",
                        "loadTheseAfter",
                        all_mods,
                    )
            except:
                mod_path = all_mods[uuid]["path"]
                logger.warning(
                    f"About.xml syntax error. Unable to read <loadAfter> tag from XML: {mod_path}"
                )

        if all_mods[uuid].get("forceLoadAfter"):
            try:
                force_load_these_before = all_mods[uuid]["forceLoadAfter"].get("li")
                if force_load_these_before:
                    logger.debug(
                        f"Current mod should force load after these mods: {force_load_these_before}"
                    )
                    add_load_rule_to_mod(
                        all_mods[uuid],
                        force_load_these_before,
                        "loadTheseBefore",
                        "loadTheseAfter",
                        all_mods,
                    )
            except:
                mod_path = all_mods[uuid]["path"]
                logger.warning(
                    f"About.xml syntax error. Unable to read <forceLoadAFter> tag from XML: {mod_path}"
                )

        if all_mods[uuid].get("loadAfterByVersion"):
            if all_mods[uuid]["loadAfterByVersion"].get("v1.4"):
                try:
                    load_these_before_by_ver = all_mods[uuid]["loadAfterByVersion"][
                        "v1.4"
                    ].get("li")
                    if load_these_before_by_ver:
                        logger.debug(
                            f"Current mod should load after these mods for v1.4: {load_these_before_by_ver}"
                        )
                        add_load_rule_to_mod(
                            all_mods[uuid],
                            load_these_before_by_ver,
                            "loadTheseBefore",
                            "loadTheseAfter",
                            all_mods,
                        )
                except:
                    mod_path = all_mods[uuid]["path"]
                    logger.warning(
                        f"About.xml syntax error. Unable to read <loadAfterByVersion><v1.4> tag from XML: {mod_path}"
                    )

        # Current mod should be loaded BEFORE these mods
        # The current mod is a dependency for all these mods
        if all_mods[uuid].get("loadBefore"):
            try:
                load_these_after = all_mods[uuid]["loadBefore"].get("li")
                if load_these_after:
                    logger.debug(
                        f"Current mod should load before these mods: {load_these_after}"
                    )
                    add_load_rule_to_mod(
                        all_mods[uuid],
                        load_these_after,
                        "loadTheseAfter",
                        "loadTheseBefore",
                        all_mods,
                    )
            except:
                mod_path = all_mods[uuid]["path"]
                logger.warning(
                    f"About.xml syntax error. Unable to read <loadBefore> tag from XML: {mod_path}"
                )

        if all_mods[uuid].get("forceLoadBefore"):
            try:
                force_load_these_after = all_mods[uuid]["forceLoadBefore"].get("li")
                if force_load_these_after:
                    logger.debug(
                        f"Current mod should force load before these mods: {force_load_these_after}"
                    )
                    add_load_rule_to_mod(
                        all_mods[uuid],
                        force_load_these_after,
                        "loadTheseAfter",
                        "loadTheseBefore",
                        all_mods,
                    )
            except:
                mod_path = all_mods[uuid]["path"]
                logger.warning(
                    f"About.xml syntax error. Unable to read <forceLoadBefore> tag from XML: {mod_path}"
                )

        if all_mods[uuid].get("loadBeforeByVersion"):
            if all_mods[uuid]["loadBeforeByVersion"].get("v1.4"):
                try:
                    load_these_after_by_ver = all_mods[uuid]["loadBeforeByVersion"][
                        "v1.4"
                    ].get("li")
                    if load_these_after_by_ver:
                        logger.debug(
                            f"Current mod should load before these mods for v1.4: {load_these_after_by_ver}"
                        )
                        add_load_rule_to_mod(
                            all_mods[uuid],
                            load_these_after_by_ver,
                            "loadTheseAfter",
                            "loadTheseBefore",
                            all_mods,
                        )
                except:
                    mod_path = all_mods[uuid]["path"]
                    logger.warning(
                        f"About.xml syntax error. Unable to read <loadBeforeByVersion><v1.4> tag from XML: {mod_path}"
                    )

    logger.info("Finished adding dependencies through About.xml information")
    log_deps_order_info(all_mods)

    # Next two sections utilize this helper dict
    packageId_to_uuid = {
        metadata["packageId"]: metadata["uuid"]
        for metadata in all_mods.values()
        if metadata.get("packageId")
    }

    # Steam references dependencies based on PublishedFileID, not package ID
    info_from_steam_package_id_to_name = {}
    if steam_db:
        logger.info("Starting adding dependencies from SteamDB")
        tracking_dict: dict[str, set[str]] = {}
        steam_id_to_package_id: dict[str, str] = {}
        for publishedfileid, mod_data in steam_db.items():
            db_packageId = mod_data.get("packageId")
            # If our DB has a packageId for this
            if db_packageId:
                db_packageId = db_packageId.lower()  # Normalize packageId
                steam_id_to_package_id[publishedfileid] = db_packageId
                info_from_steam_package_id_to_name[db_packageId] = mod_data.get("name")
                package_uuid = packageId_to_uuid.get(db_packageId)
                if (
                    package_uuid
                    and all_mods[package_uuid].get("publishedfileid") == publishedfileid
                ):
                    dependencies = mod_data.get("dependencies")
                    if dependencies:
                        if db_packageId not in tracking_dict:
                            tracking_dict[db_packageId] = set(dependencies.keys())
                        else:
                            tracking_dict[db_packageId].update(dependencies.keys())
            else:  # Otherwise, skip the entry
                continue
        logger.debug(
            f"Tracking {len(steam_id_to_package_id)} SteamDB packageIds for lookup"
        )
        logger.debug(
            f"Tracking Steam dependency data for {len(tracking_dict)} installed mods"
        )

        # For each mod that exists in all_mods -> dependencies (in Steam ID form)
        for (
            installed_mod_package_id,
            set_of_dependency_steam_ids,
        ) in tracking_dict.items():
            for dependency_steam_id in set_of_dependency_steam_ids:
                # Dependencies are added as package_ids. We should be able to
                # resolve the package_id from the Steam ID for any mod, unless
                # the metadata actually references a Steam ID that itself does not
                # wire to a package_id defined in an installed & valid mod.
                if dependency_steam_id in steam_id_to_package_id:
                    add_dependency_to_mod_from_steamdb(
                        all_mods[
                            packageId_to_uuid[installed_mod_package_id]
                        ],  # Already checked above
                        steam_id_to_package_id[dependency_steam_id],
                        all_mods,
                    )
                else:
                    # This should only happen with RimPy Mod Manager Database, since it does not contain
                    # keyed information for Core + DLCs in it's ["database"] - this is only referenced by
                    # RPMMDB with the ["database"][pfid]["children"] values.
                    logger.debug(
                        f"Unable to lookup Steam AppID/PublishedFileID in Steam metadata: {dependency_steam_id}"
                    )
        logger.info("Finished adding dependencies from SteamDB")
        log_deps_order_info(all_mods)
    else:
        logger.info("No Steam database supplied from external metadata. skipping.")

    # Add load order to installed mods based on dependencies from community rules
    if community_rules:
        logger.info("Starting adding rules from configured Community Rules")
        for package_id in community_rules:
            # Note: requiring the package be in all_mods should be fine, as
            # if the mod doesn't exist all_mods, then either mod_data or dependency_id
            # will be None, and then we don't insert a dependency
            if package_id.lower() in packageId_to_uuid:
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
                            all_mods[
                                packageId_to_uuid[package_id.lower()]
                            ],  # Already checked above
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
                    # In RimPy, load_these_before is at least an empty dict
                    for load_this_before in load_these_before:
                        add_load_rule_to_mod(
                            all_mods[
                                packageId_to_uuid[package_id.lower()]
                            ],  # Already checked above
                            load_this_before,  # lower() done in call
                            "loadTheseBefore",
                            "loadTheseAfter",
                            all_mods,
                        )
                load_this_bottom = community_rules[package_id].get("loadBottom")
                if load_this_bottom:
                    logger.debug(
                        f'Current mod should load at the bottom of a mods list, and will be considered a "tier 3" mod'
                    )
                    all_mods[packageId_to_uuid[package_id.lower()]]["loadBottom"] = True
        logger.info("Finished adding dependencies from Community Rules")
        log_deps_order_info(all_mods)
    else:
        logger.info(
            "No Community Rules database supplied from external metadata. skipping."
        )
    # Add load order rules to installed mods based on rules from user rules
    if user_rules:
        logger.info("Starting adding rules from User Rules")
        for package_id in user_rules:
            # Note: requiring the package be in all_mods should be fine, as
            # if the mod doesn't exist all_mods, then either mod_data or dependency_id
            # will be None, and then we don't insert a dependency
            if package_id.lower() in packageId_to_uuid:
                load_these_after = user_rules[package_id].get("loadBefore")
                if load_these_after:
                    logger.debug(
                        f"Current mod should load before these mods: {load_these_after}"
                    )
                    # In RimPy, load_these_after is at least an empty dict
                    # Cannot call add_load_rule_to_mod outside of this for loop,
                    # as that expects a list
                    for load_this_after in load_these_after:
                        add_load_rule_to_mod(
                            all_mods[
                                packageId_to_uuid[package_id.lower()]
                            ],  # Already checked above
                            load_this_after,  # lower() done in call
                            "loadTheseAfter",
                            "loadTheseBefore",
                            all_mods,
                        )

                load_these_before = user_rules[package_id].get("loadAfter")
                if load_these_before:
                    logger.debug(
                        f"Current mod should load after these mods: {load_these_before}"
                    )
                    # In RimPy, load_these_before is at least an empty dict
                    for load_this_before in load_these_before:
                        add_load_rule_to_mod(
                            all_mods[
                                packageId_to_uuid[package_id.lower()]
                            ],  # Already checked above
                            load_this_before,  # lower() done in call
                            "loadTheseBefore",
                            "loadTheseAfter",
                            all_mods,
                        )
                load_this_bottom = user_rules[package_id].get("loadBottom")
                if load_this_bottom:
                    logger.debug(
                        f'Current mod should load at the bottom of a mods list, and will be considered a "tier 3" mod'
                    )
                    all_mods[packageId_to_uuid[package_id.lower()]]["loadBottom"] = True
        logger.info("Finished adding dependencies from User Rules")
        log_deps_order_info(all_mods)
    else:
        logger.info("No User Rules database supplied from external metadata. skipping.")
    logger.info("Returning all mods now")
    return all_mods, info_from_steam_package_id_to_name


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
    logger.debug(
        f"Finished getting game version from Game Folder, returning now: {version.strip()}"
    )
    return version.strip()


def get_inactive_mods(
    workshop_and_expansions: Dict[str, Any],
    active_mods: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate a list of inactive mods by cross-referencing the list of
    installed workshop mods with the active mods and known expansions.

    Move the first local instance of any duplicate found alphabetically
    ascending by filename to the active mods list; and the rest of the dupes
    to the inactive mods list. TODO this is not accurate

    :param workshop_and_expansions: dict of workshop mods and expansions
    :param active_mods: dict of active mods
    :param duplicate_mods: dict keyed with packageIds to list of dupe uuids
    :return: a dict for inactive mods
    """
    logger.info(
        "Generating inactive mod lists from subtracting all mods with active mods"
    )
    inactive_mods = workshop_and_expansions.copy()
    # For each mod in active mods
    for mod_uuid, mod_data in active_mods.items():
        package_id = active_mods[mod_uuid]["packageId"]
        if (  # Remove all active_mods uuids from inactive_mods
            package_id == workshop_and_expansions[mod_uuid]["packageId"]
        ):
            del inactive_mods[mod_uuid]
    logger.info("Finished generating inactive mods list")
    return inactive_mods


def get_installed_expansions(game_path: str, game_version: str) -> Dict[str, Any]:
    """
    Given a path to the game's install folder, return a dict
    containing data for all of the installed expansions
    keyed to their package ids. The dict values are the converted
    About.xmls. If the path does not exist, the dict
    will be empty.

    :param path: path to the Rimworld install folder
    :return: a Dict of expansions by package id
    """
    mod_data = {}
    if game_path != "":
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
        mod_data = parse_mod_data(data_path, "expansion")
        logger.debug("Finished getting BASE/EXPANSION data")
        # logger.debug(mod_data)

        # Base game and expansion About.xml do not contain name, so these
        # must be manually added
        logger.info("Manually populating names for BASE/EXPANSION data")
        dlc_mapping = {
            "ludeon.rimworld": {
                "appid": "294100",
                "description": RIMWORLD_DLC_METADATA["294100"]["description"],
            },
            "ludeon.rimworld.royalty": {
                "appid": "1149640",
                "description": RIMWORLD_DLC_METADATA["1149640"]["description"],
            },
            "ludeon.rimworld.ideology": {
                "appid": "1392840",
                "description": RIMWORLD_DLC_METADATA["1392840"]["description"],
            },
            "ludeon.rimworld.biotech": {
                "appid": "1826140",
                "description": RIMWORLD_DLC_METADATA["1826140"]["description"],
            },
        }
        for data in mod_data.values():
            package_id = data["packageId"]
            if package_id in dlc_mapping:
                dlc_data = dlc_mapping[package_id]
                data.update(
                    {
                        "appid": dlc_data["appid"],
                        "name": RIMWORLD_DLC_METADATA[dlc_data["appid"]]["name"],
                        "steam_url": RIMWORLD_DLC_METADATA[dlc_data["appid"]][
                            "steam_url"
                        ],
                        "description": dlc_data["description"],
                        "supportedVersions": {"li": game_version},
                    }
                )
            else:
                logger.error(
                    f"An unknown mod has been found in the expansions folder: {package_id} {data}"
                )
        logger.info(
            "Finished getting installed expansions, returning final BASE/EXPANSIONS data now"
        )
        # logger.debug(mod_data)
    else:
        logger.error(
            "Skipping parsing data from empty game data path. Is the game path configured?"
        )
    return mod_data


def get_local_mods(local_path: str, game_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Given a path to the local GAME_INSTALL_DIR/Mods folder, return a dict
    containing data for all the mods keyed to their package ids.
    The root-level key is the uuid, and the root-level value
    is the converted About.xml. If the path does not exist, the dict
    will be empty.

    :param path: path to the Rimworld workshop mods folder
    :return: a Dict of workshop mods by package id, and dict of community rules
    """
    mod_data = {}
    if local_path != "":
        logger.info(f"Getting local mods with Local path: {local_path}")
        logger.info(f"Supplementing call with Game Folder path: {game_path}")

        # If local mods path is same as game path and we're running on a Mac,
        # that means use the default local mods folder

        system_name = platform.system()
        if system_name == "Darwin" and local_path and local_path == game_path:
            local_path = os.path.join(local_path, "RimWorldMac.app", "Mods")
            logger.info(
                f"Running on MacOS, generating new local mods path: {local_path}"
            )

        # Get mod data
        logger.info(
            f"Attempting to get LOCAL mods data from custom local path or Rimworld's /Mods folder: {local_path}"
        )
        mod_data = parse_mod_data(local_path, "local")
        logger.info("Finished getting LOCAL mods data, returning LOCAL mods data now")
        # logger.debug(mod_data)
    else:
        logger.debug(
            "Skipping parsing data from empty local mods path. Is the local mods path configured?"
        )
    return mod_data


def get_num_dependencies(all_mods: Dict[str, Any], key_name: str) -> int:
    """Debug func for getting total number of dependencies"""
    counter = 0
    for mod_data in all_mods.values():
        if mod_data.get(key_name):
            counter = counter + len(mod_data[key_name])
    return counter


def get_workshop_mods(workshop_path: str) -> Dict[str, Any]:
    """
    Given a path to the Rimworld Steam workshop folder, return a dict
    containing data for all the mods keyed to their package ids.
    The root-level key is the uuid, and the root-level value
    is the converted About.xml. If the path does not exist, the dict
    will be empty.

    :param path: path to the Rimworld workshop mods folder
    :return: a Dict of workshop mods by package id, and dict of community rules
    """
    mod_data = {}
    if workshop_path != "":
        logger.info(f"Getting WORKSHOP data with Workshop path: {workshop_path}")
        mod_data = parse_mod_data(workshop_path, "workshop")
        logger.info("Finished getting WORKSHOP data, returning WORKSHOP data now")
        # logger.debug(mod_data)
    else:
        logger.debug(
            "Skipping parsing data from empty workshop mods path. Is the workshop mods path configured?"
        )
    return mod_data


def log_deps_order_info(all_mods) -> None:
    """This block is used quite a bit - deserves own function"""
    logger.info(
        f"Total number of loadTheseBefore rules: {get_num_dependencies(all_mods, 'loadTheseBefore')}"
    )
    logger.info(
        f"Total number of loadTheseAfter rules: {get_num_dependencies(all_mods, 'loadTheseAfter')}"
    )
    logger.info(
        f"Total number of dependencies: {get_num_dependencies(all_mods, 'dependencies')}"
    )
    logger.info(
        f"Total number of incompatibilities: {get_num_dependencies(all_mods, 'incompatibilities')}"
    )


def merge_mod_data(*dict_args: dict[str, Any]) -> Dict[str, Any]:
    """
    Given any number of dictionaries, shallow copy and merge into a new dict,
    precedence goes to key-value pairs in latter dictionaries.
    """
    logger.info(f"Merging mods from {len(dict_args)} sources")
    result = {}
    for dictionary in dict_args:
        result.update(dictionary)
    return result


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
                pfid = None
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
                invalid_about_file_path_found = True
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
                            invalid_about_file_path_found = False
                            break
                # Look for a case-insensitive "PublishedFileId.txt" file
                invalid_pfid_file_path_found = True
                if not invalid_folder_path_found:
                    pfid_file_name = "PublishedFileId.txt"
                    for temp_file in os.scandir(
                        os.path.join(file.path, about_folder_name)
                    ):
                        if (
                            temp_file.name.lower() == pfid_file_name.lower()
                            and temp_file.is_file()
                        ):
                            pfid_file_name = temp_file.name
                            invalid_pfid_file_path_found = False
                            break
                # If there was an issue getting the expected path, track and exit
                if invalid_folder_path_found or invalid_pfid_file_path_found:
                    logger.debug(
                        f"There was an issue getting the expected sub-path for this path, no variations of /About/PublishedFileId.txt could be found: {file.path}"
                    )
                    logger.debug(
                        "^ this may not be an issue, as workshop sometimes forgets to delete unsubscribed mod folders, or a mod may not contain this information (mods can be unpublished)"
                    )
                else:
                    pfid_path = os.path.join(
                        file.path, about_folder_name, pfid_file_name
                    )
                    logger.debug(
                        f"Found a variation of /About/PublishedFileId.txt at: {pfid_path}"
                    )
                    try:
                        with open(pfid_path, encoding="utf-8-sig") as pfid_file:
                            pfid = pfid_file.read()
                            pfid = pfid.strip()
                    except:
                        logger.error(f"Failed to read pfid from {pfid_path}")
                # If there was an issue getting the expected path, track and exit
                if invalid_folder_path_found or invalid_about_file_path_found:
                    logger.debug(
                        f"There was an issue getting the expected sub-path for this path, no variations of /About/About.xml could be found: {file.path}"
                    )
                    logger.debug(
                        "^ this may not be an issue, as workshop sometimes forgets to delete unsubscribed mod folders."
                    )
                    invalid_dirs.append(file.name)
                    logger.debug(f"Populating invalid mod: {file.path}")
                    uuid = str(uuid4())
                    mods[uuid] = {
                        "invalid": True,
                        "name": "UNKNOWN",
                        "packageId": "UNKNOWN",
                        "publishedfileid": pfid if pfid else None,
                        "author": "UNKNOWN",
                        "description": (
                            "This mod is considered invalid by RimSort (and the RimWorld game)."
                            + "\n\nThis mod does NOT contain an ./About/About.xml and is likely leftover from previous usage."
                            + "\n\nThis can happen sometimes with Steam mods if there are leftover .dds textures or unexpected data."
                        ),
                        "data_source": intent,
                        "folder": file.name,
                        "path": file.path,
                        "uuid": uuid,
                    }
                else:
                    mod_data_path = os.path.join(
                        file.path, about_folder_name, about_file_name
                    )
                    logger.debug(
                        f"Found a variation of /About/About.xml at: {mod_data_path}"
                    )
                    mod_data = {}
                    try:
                        # Try to parse About.xml
                        mod_data = xml_path_to_json(mod_data_path)
                    except:
                        # If there was an issue parsing the About.xml, track and exit
                        logger.error(
                            f"Unable to parse About.xml with the exception: {traceback.format_exc()}"
                        )
                    else:
                        # Case-insensitive `ModMetaData` key.
                        logger.debug("Normalizing XML content keys")
                        mod_data = {k.lower(): v for k, v in mod_data.items()}
                        logger.debug("Editing XML content")
                        if mod_data.get("modmetadata"):
                            if "modmetadata" in mod_data and mod_data[
                                "modmetadata"
                            ].get(
                                "packageId"
                            ):  # If our About.xml metadata has a packageId key
                                # Initialize our dict from the formatted About.xml metadata
                                mod_metadata = mod_data["modmetadata"]
                                # Check type of packageId, use first packageId parsed
                                if isinstance(mod_metadata["packageId"], list):
                                    mod_metadata["packageId"] = mod_metadata[
                                        "packageId"
                                    ][0]
                                # Normalize package ID in metadata
                                mod_metadata["packageId"] = mod_metadata[
                                    "packageId"
                                ].lower()
                                # Track pfid if we parsed one earlier
                                if pfid:
                                    mod_metadata["publishedfileid"] = pfid
                                if intent == "workshop" and not mod_metadata.get(
                                    "publishedfileid"
                                ):  # If workshop mods intent and we don't have a pfid...
                                    mod_metadata[
                                        "publishedfileid"
                                    ] = file.name  # ... set the pfid to the folder name
                                # Make some assumptions if we have a pfid
                                if mod_metadata.get("publishedfileid"):
                                    mod_metadata[
                                        "steam_uri"
                                    ] = f"steam://url/CommunityFilePage/{pfid}"
                                    mod_metadata[
                                        "steam_url"
                                    ] = f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"
                                # Track source & uuid in case metadata becomes detached
                                # data_source will be used with setIcon later
                                # If a mod contains C# assemblies, we want to tag the mod
                                assemblies_path = os.path.join(file.path, "Assemblies")
                                if os.path.exists(assemblies_path):
                                    if any(
                                        filename.endswith((".dll", ".DLL"))
                                        for filename in os.listdir(assemblies_path)
                                    ):
                                        mod_metadata["csharp"] = True
                                else:
                                    subfolder_paths = [
                                        os.path.join(file.path, folder)
                                        for folder in os.listdir(file.path)
                                        if os.path.isdir(
                                            os.path.join(file.path, folder)
                                        )
                                    ]
                                    for subfolder_path in subfolder_paths:
                                        assemblies_path = os.path.join(
                                            subfolder_path, "Assemblies"
                                        )
                                        if os.path.exists(assemblies_path):
                                            if any(
                                                filename.endswith((".dll", ".DLL"))
                                                for filename in os.listdir(
                                                    assemblies_path
                                                )
                                            ):
                                                mod_metadata["csharp"] = True
                                # Check for git repository inside local mods, tag appropriately
                                if intent == "local":
                                    git_repo_path = os.path.join(file.path, ".git")
                                    if os.path.exists(git_repo_path):
                                        mod_metadata["git_repo"] = True
                                mod_metadata["data_source"] = intent
                                mod_metadata["folder"] = file.name
                                mod_metadata["path"] = file.path
                                uuid = str(uuid4())
                                mod_metadata["uuid"] = uuid
                                logger.debug(
                                    f"Finished editing XML content, adding final content to larger list: {mod_metadata}"
                                )
                                mods[uuid] = mod_metadata
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
        # logger.debug(f"Scanned the following files in mods path: {files_scanned}")
        # logger.debug(f"Scanned the following dirs in mods path: {dirs_scanned}")
        # if invalid_dirs:
        #     logger.debug(
        #         f"The following scanned dirs did not contain mod info: {invalid_dirs}"
        #     )
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
