import json
import logging
from natsort import natsorted
import os
import platform
from requests.exceptions import HTTPError
from time import time
import traceback
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from util.error import show_fatal_error, show_information, show_warning
from util.steam.webapi.wrapper import DynamicQuery
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
    # Calculate duplicate mods (SCEMA: {str packageId: {str uuid: str data_source} })
    duplicate_mods = {}
    packageId_to_uuids = {}
    for mod_uuid, mod_data in workshop_and_expansions.items():
        data_source = mod_data["data_source"]  # Track data_source
        package_id = mod_data["packageId"]  # Track packageId to UUIDs
        mod_path = mod_data["path"]  # Track path
        if not packageId_to_uuids.get(package_id):
            packageId_to_uuids[package_id] = {}
        packageId_to_uuids[package_id][mod_uuid] = [data_source, mod_path]
    duplicate_mods = packageId_to_uuids.copy()
    for package_id in packageId_to_uuids:  # If a packageId has > 1 UUID listed
        if len(packageId_to_uuids[package_id]) > 1:  # ...it is a duplicate mod
            logger.info(
                f"Duplicate mods found for mod {package_id}: {packageId_to_uuids[package_id]}"
            )
        else:  # Otherwise, remove non-duplicates from our tracking dict
            del duplicate_mods[package_id]
    # Get the list of active mods and populate data from workshop + expansions
    logger.info(f"Calling get active mods with Config Path: {config_path}")
    active_mods, missing_mods = get_active_mods_from_config(
        config_path, duplicate_mods, workshop_and_expansions
    )
    # Return an error if some active mod was in the ModsConfig but no data
    # could be found for it
    if (
        duplicate_mods
    ):  # TODO: make this warning configurable (allow users to completely disable it if they choose to do so)
        logger.warning(
            f"Could not find data for the list of active mods: {duplicate_mods}"
        )
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
    if missing_mods:
        logger.warning(
            f"Could not find data for the list of active mods: {missing_mods}"
        )
        list_of_missing_mods = ""
        for missing_mod in missing_mods:
            list_of_missing_mods = list_of_missing_mods + f"* {missing_mod}\n"
        show_warning(
            text="Could not find data for some mods",
            information=(
                "The following list of mods were set active in your ModsConfig.xml but "
                "no data could be found from the workshop or in your local mods. "
                "Did you set your game install and workshop/local mods path correctly?"
            ),
            details=list_of_missing_mods,
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
                pfid = ""
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
                    logger.warning(
                        f"There was an issue getting the expected sub-path for this path, no variations of /About/PublishedFileId.txt could be found: {file.path}"
                    )
                    logger.warning(
                        "^ this may not be an issue, as workshop sometimes forgets to delete unsubscribed mod folders, or a mod may not contain this information (mods can be unpublished)"
                    )
                else:
                    pfid_path = os.path.join(
                        file.path, about_folder_name, pfid_file_name
                    )
                    logger.info(
                        f"Found a variation of /About/PublishedFileId.txt at: {pfid_path}"
                    )
                    try:
                        with open(pfid_path) as pfid_file:
                            pfid = pfid_file.read()
                            pfid = pfid.strip()
                    except:
                        logger.error(f"Failed to read pfid from {pfid_path}")
                # If there was an issue getting the expected path, track and exit
                if invalid_folder_path_found or invalid_about_file_path_found:
                    logger.warning(
                        f"There was an issue getting the expected sub-path for this path, no variations of /About/About.xml could be found: {file.path}"
                    )
                    logger.warning(
                        "^ this may not be an issue, as workshop sometimes forgets to delete unsubscribed mod folders."
                    )
                    invalid_dirs.append(file.name)
                    logger.info(f"Populating invalid mod: {file.path}")
                    uuid = str(uuid4())
                    mods[uuid] = {}
                    mods[uuid]["invalid"] = True
                    mods[uuid]["folder"] = file.name
                    mods[uuid]["path"] = file.path
                    mods[uuid]["name"] = "UNKNOWN"
                    mods[uuid]["packageId"] = "UNKNOWN"
                    mods[uuid]["author"] = "UNKNOWN"
                    mods[uuid]["description"] = (
                        "This mod is considered invalid by RimSort (and the RimWorld game)."
                        + "\n\nThis mod does NOT contain an ./About/About.xml and is likely leftover from previous usage."
                        + "\n\nThis can happen sometimes with Steam mods if there are leftover .dds textures or unexpected data."
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
                                uuid = str(uuid4())
                                mod_data["modmetadata"]["packageId"] = mod_data[
                                    "modmetadata"
                                ][
                                    "packageId"
                                ].lower()  # normalize package ID in metadata
                                mod_data["modmetadata"]["folder"] = file.name
                                mod_data["modmetadata"]["path"] = file.path
                                logger.debug(
                                    f"Finished editing XML content, adding final content to larger list: {mod_data['modmetadata']}"
                                )
                                if pfid != "":
                                    mod_data["modmetadata"]["publishedfileid"] = pfid
                                    mod_data["modmetadata"][
                                        "steam_uri"
                                    ] = f"steam://url/CommunityFilePage/{pfid}"
                                    mod_data["modmetadata"][
                                        "steam_url"
                                    ] = f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"
                                if not mod_data["modmetadata"].get("name"):
                                    mod_data["modmetadata"][
                                        "name"
                                    ] = "Mod name unspecified"
                                mods[uuid] = mod_data["modmetadata"]
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
    for uuid, data in mod_data.items():
        package_id = data["packageId"]
        if package_id == "ludeon.rimworld":
            data["name"] = "Core (Base game)"
            data["steam_url"] = "https://store.steampowered.com/app/294100/RimWorld"
        elif package_id == "ludeon.rimworld.royalty":
            data["name"] = "Royalty (DLC #1)"
            data[
                "steam_url"
            ] = "https://store.steampowered.com/app/1149640/RimWorld__Royalty"
        elif package_id == "ludeon.rimworld.ideology":
            data["name"] = "Ideology (DLC #2)"
            data[
                "steam_url"
            ] = "https://store.steampowered.com/app/1392840/RimWorld__Ideology"
        elif package_id == "ludeon.rimworld.biotech":
            data["name"] = "Biotech (DLC #3)"
            data[
                "steam_url"
            ] = "https://store.steampowered.com/app/1826140/RimWorld__Biotech"
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


def get_rimpy_database_mod(
    mods: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Extract the RimPy Mod Manager Database mod's SteamDB rules, essential for the sorting functions.
    Produces an error if the DB mod is not found.

    Extract the RimPy Mod Manager Database mod's Community Rules, essential for the sorting functions.
    Produces an error if the DB mod is not found.
    """
    logger.info("Using Paladin's RimPy Mod Manager Database mod for external rules")
    db_json_data = {}
    community_rules_json_data = {}
    for uuid in mods:
        if (
            mods[uuid].get("packageId") == "rupal.rimpymodmanagerdatabase"
            or mods[uuid].get("publishedfileid") == "1847679158"
        ):  # TODO make this a DB mod packageID a configurable preference
            logger.info("Found RimPy Mod Manager Database mod")
            steam_db_rules_path = os.path.join(mods[uuid]["path"], "db", "db.json")
            logger.info(f"Generated path to db.json: {steam_db_rules_path}")
            if os.path.exists(steam_db_rules_path):
                with open(steam_db_rules_path, encoding="utf-8") as f:
                    json_string = f.read()
                    logger.info("Reading info from db.json")
                    db_data = json.loads(json_string)
                    logger.debug(
                        "Returning db.json, this data is long so we forego logging it here"
                    )
                    db_json_data = db_data["database"]
            else:
                logger.error("The db.json path does not exist")
            community_rules_path = os.path.join(
                mods[uuid]["path"], "db", "communityRules.json"
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
                    community_rules_json_data = rule_data["rules"]
            else:
                logger.error("The communityRules.json path does not exist")
            return db_json_data, community_rules_json_data
    logger.warning(
        "No RimPy Mod Manager Database was found. This will affect the accuracy of mod dependencies"
    )
    show_warning(
        text="RimPy Mod Manager Database mod was not found",
        information=(
            "RimSort relies on RimPy Mod Manager database mod to collect mod dependencies listed "
            "on Steam but not in mod packages themselves. Not having this database means "
            "a lower accuracy for surfacing mod dependencies. RimSort was unable to find "
            "this mod in your workshop or local mods folder. Do you have the mod installed "
            "and/or are your paths set correctly?"
        ),
    )
    return db_json_data, community_rules_json_data


def get_3rd_party_metadata(
    apikey: str, db_json_data_life: int, mods: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Query Steam Workshop metadata for any mods that have a 'publishedfileid' attribute
    contained in their mod_data, essential for the sorting functions. Will produce warnings
    if the data is unable to be retrieved.


    TODO: Implement this with associated workflows!
    Possibly implement a separate root key (i.e. ["community_rules"] instead of ["database"]...?)

    Return RimSort Community Rules db, essential for the sorting functions.
    Produces an error if the data is not found.

    :param apikey: a Steam apikey that is pulled from game_configuration.steam_apikey
    :param mods: A Dict equivalent to 'all_mods' or mod_list.get_list_items_by_dict() in
    which contains possible Steam mods to lookup metadata for
    :return: Tuple containing the updated json data from database, and community_rules
    """
    db_data = {}  # This is kept to fall back on.
    db_data_expired = None
    db_data_missing = None
    db_json_data = {}
    community_rules_json_data = {}
    db_json_folder = "data"
    db_json_filename = "steam_metadata.json"
    db_json_data_path = os.path.join(os.getcwd(), db_json_folder, db_json_filename)
    logger.info(
        "Checking for cached Steam db..."
    )  # TODO: Make this info visible to the user
    if os.path.exists(
        db_json_data_path
    ):  # Look for cached data & load it if available & not expired
        logger.info(f"Found cached Steam db at {db_json_data_path}")
        with open(db_json_data_path, encoding="utf-8") as f:
            json_string = f.read()
            logger.info(f"Reading info from {db_json_filename}")
            db_data = json.loads(json_string)
            current_time = int(time())
            db_time = int(db_data["version"])
            if (
                current_time < db_time
            ):  # if current epoch is less than the database's epoch
                db_json_data = db_data[
                    "database"
                ]  # TODO: additional check to verify integrity of this data's schema
                logger.info(f"Cached Steam metadata is valid: {db_json_data}")
                return db_json_data, community_rules_json_data
            else:
                db_data_expired = True
    else:
        db_data_missing = True
    if db_data_expired or db_data_missing:
        show_information(
            text="RimSort Dynamic Query",
            information="Cached data expired or missing.\nAttempting live query...",
        )  # Notify the user
        logger.info("Cached data expired or missing. Attempting live query...")
    # Attempt live query & cache the query
    if len(apikey) == 32:  # If apikey is less than 32 characters
        logger.info("Retreived Steam API key from settings.json")
        if len(mods.keys()) > 0:  # No empty queries!
            try:  # Since the key is valid, we try to launch a live query
                appid = 294100
                logger.info(
                    f"Initializing DynamicQuery with configured Steam API key for {appid}..."
                )
                mods_query = DynamicQuery(apikey, appid, db_json_data_life)
                mods_query.workshop_json_data = mods_query.cache_parsable_db_data(mods)
                db_output_path = os.path.join(
                    os.getcwd(), "data", "steam_metadata.json"
                )
                logger.info(f"Caching DynamicQuery result: {db_output_path}")
                with open(db_output_path, "w") as output:
                    json.dump(mods_query.workshop_json_data, output, indent=4)
                db_json_data = mods_query.workshop_json_data[
                    "database"
                ]  # Get json data directly from memory upon query completion
            except HTTPError:
                stacktrace = traceback.format_exc()
                pattern = "&key="
                stacktrace = stacktrace[
                    : len(stacktrace)
                    - (len(stacktrace) - (stacktrace.find(pattern) + len(pattern)))
                ]  # If an HTTPError from steam/urllib3 module(s) somehow is uncaught, try to remove the Steam API key from the stacktrace
                show_fatal_error(
                    text="RimSort Dynamic Query",
                    information="DynamicQuery failed to initialize database.\nThere is no external metadata being factored for sorting!\n\nCached Dynamic Query database not found!\n\nFailed to initialize new DynamicQuery with configured Steam API key.\n\nAre you connected to the internet?\n\nIs your configured key invalid or revoked?\n\nPlease right-click the 'Refresh' button and configure a valid Steam API key so that you can generate a database.\n\nPlease reference: https://github.com/oceancabbage/RimSort/wiki/User-Guide#obtaining-your-steam-api-key--using-it-with-rimsort-dynamic-query",
                    details=stacktrace,
                )
        else:
            logger.warning(
                "Tried to generate DynamicQuery with 0 mods...? Unable to initialize DynamicQuery for live metadata..."
            )  # TODO: Make this warning visible to the user
    else:  # Otherwise, API key is not valid
        if (
            db_data_expired and not db_data_missing
        ):  # If the cached db data is expired but NOT missing
            # Fallback to the expired metadata
            show_warning(
                text="RimSort Dynamic Query",
                information="Failed to read a valid Steam API key from settings.json",
                details="Unable to initialize DynamicQuery for live metadata.\n\nFalling back to cached, but EXPIRED Dynamic Query database...",
            )  # Notify the user
            logger.warning("Falling back to cached, but EXPIRED Dynamic Query database")
            db_json_data = db_data[
                "database"
            ]  # TODO: additional check to verify integrity of this data's schema
        else:  # Assume db_data_missing
            show_warning(
                text="RimSort Dynamic Query",
                information="Unable to initialize external metadata.\nThere is no external metadata being factored for sorting!",
                details="Cached Dynamic Query database not found!\n\nPlease right-click the 'Refresh' button and configure a valid Steam API key so that you can generate a database.\n\nPlease reference: https://github.com/oceancabbage/RimSort/wiki/User-Guide#obtaining-your-steam-api-key--using-it-with-rimsort-dynamic-query",
            )
    return db_json_data, community_rules_json_data


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
    _log_deps_order_info(all_mods)

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

        if all_mods[uuid].get("forceLoadAfter"):
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

        if all_mods[uuid].get("loadAfterByVersion"):
            if all_mods[uuid]["loadAfterByVersion"].get("v1.4"):
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

        # Current mod should be loaded BEFORE these mods
        # The current mod is a dependency for all these mods
        if all_mods[uuid].get("loadBefore"):
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

        if all_mods[uuid].get("forceLoadBefore"):
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

        if all_mods[uuid].get("loadBeforeByVersion"):
            if all_mods[uuid]["loadBeforeByVersion"].get("v1.4"):
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

    logger.info("Finished adding dependencies through About.xml information")
    _log_deps_order_info(all_mods)

    # Next two sections utilize this helper dict
    package_id_to_uuid = {}
    for mod_uuid, modmetadata in all_mods.items():
        package_id_to_uuid[modmetadata["packageId"]] = mod_uuid

    # Steam's WebAPI references dependencies based on PublishedFileID, not package ID
    info_from_steam_package_id_to_name = {}
    if steam_db_rules:
        logger.info("Starting adding dependencies from Steam db")
        tracking_dict: dict[str, set[str]] = {}
        steam_id_to_package_id = {}
        # Iterate through all workshop items in the Steam DB.
        for publishedfileid, mod_data in steam_db_rules.items():
            try:
                db_package_id = mod_data["packageId"].lower()

                # Record the Steam ID => package_id
                steam_id_to_package_id[publishedfileid] = db_package_id

                # Also record package_ids to names (use in tooltips)
                info_from_steam_package_id_to_name[db_package_id] = mod_data["name"]

                # If the package_id is in all_mods...
                if db_package_id in package_id_to_uuid:
                    # Iterate through each dependency (Steam ID) listed on Steam
                    for dependency_publishedfileid, steam_dep_data in mod_data[
                        "dependencies"
                    ].items():
                        if db_package_id not in tracking_dict:
                            tracking_dict[db_package_id] = set()
                        # Add Steam ID to dependencies of mod
                        tracking_dict[db_package_id].add(dependency_publishedfileid)
            except:
                logger.warning(
                    f"Skipping parsing Steam metadata mod for {publishedfileid}"
                )
                continue

        # For each mod that exists in all_mods -> dependencies (in Steam ID form)
        for (
            installed_mod_package_id,
            set_of_dependency_steam_ids,
        ) in tracking_dict.items():
            for dependency_steam_id in set_of_dependency_steam_ids:
                # Dependencies are added as package_ids. We should be able to
                # resolve the package_id from the Steam ID for any mod, unless
                # the DB.json actually references a Steam ID that itself does not
                # wire to a package_id defined in an installed & valid mod.
                if dependency_steam_id in steam_id_to_package_id:
                    add_single_str_dependency_to_mod(
                        all_mods[
                            package_id_to_uuid[installed_mod_package_id]
                        ],  # Already checked above
                        steam_id_to_package_id[dependency_steam_id],
                        all_mods,
                    )
                else:
                    logger.error(
                        f"package_id not found for steam id [{dependency_steam_id}] for Steam db.json"
                    )
        logger.info("Finished adding dependencies from Steam db")

    _log_deps_order_info(all_mods)

    # Add load order to installed mods based on dependencies from community rules
    if community_rules:
        logger.info("Starting adding dependencies from Community Rules")
        for package_id in community_rules:
            # Note: requiring the package be in all_mods should be fine, as
            # if the mod doesn't exist all_mods, then either mod_data or dependency_id
            # will be None, and then we don't insert a dependency
            if package_id.lower() in package_id_to_uuid:

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
                                package_id_to_uuid[package_id.lower()]
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
                    # In Rimpy, load_these_before is at least an empty dict
                    for load_this_before in load_these_before:
                        add_load_rule_to_mod(
                            all_mods[
                                package_id_to_uuid[package_id.lower()]
                            ],  # Already checked above
                            load_this_before,  # Lower() done in call
                            "loadTheseBefore",
                            "loadTheseAfter",
                            all_mods,
                        )
        logger.info("Finished adding dependencies from Community Rules")

    _log_deps_order_info(all_mods)

    logger.info("Returing all mods now")
    return all_mods, info_from_steam_package_id_to_name


def _get_num_dependencies(all_mods: Dict[str, Any], key_name: str) -> int:
    """Debug func for getting total number of dependencies"""
    counter = 0
    for uuid, mod_data in all_mods.items():
        if mod_data.get(key_name):
            counter = counter + len(mod_data[key_name])
    return counter


def _log_deps_order_info(all_mods) -> None:
    """This block is used quite a bit - deserves own function"""
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
            for uuid in all_mods:
                if all_mods[uuid]["packageId"] == dependency_id:
                    mod_data["incompatibilities"].add(dependency_id)
                    # if "incompatibilities" not in all_mods[dependency_id]:
                    #     all_mods[dependency_id]["incompatibilities"] = set()
                    # all_mods[dependency_id]["incompatibilities"].add(mod_data["packageId"])

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
            for uuid in all_mods:
                if all_mods[uuid]["packageId"] == dependency_id:
                    mod_data[explicit_key].add((dependency_id, True))
                    if indirect_key not in all_mods[uuid]:
                        all_mods[uuid][indirect_key] = set()
                    all_mods[uuid][indirect_key].add((mod_data["packageId"], False))

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
                for uuid in all_mods:
                    if all_mods[uuid]["packageId"] == dependency_id:
                        mod_data[explicit_key].add((dependency_id, True))
                        if indirect_key not in all_mods[uuid]:
                            all_mods[uuid][indirect_key] = set()
                        all_mods[uuid][indirect_key].add((mod_data["packageId"], False))

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
        ]:  # Go thru active mods
            package_id_normalized = package_id.lower()
            to_populate.append(package_id_normalized)
            for (
                uuid
            ) in workshop_and_expansions:  # Find this mods' metadata packageId & path
                metadata_package_id = workshop_and_expansions[uuid]["packageId"]
                metadata_path = workshop_and_expansions[uuid]["path"]
                if metadata_package_id == package_id_normalized:
                    # If the mod to populate DOESN'T have have duplicates, populate like normal
                    if not package_id_normalized in duplicate_mods.keys():
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
                            # Go thru each duplicate path by data_source
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
                            if len(natsort_expansion_paths) > 1:  # EXPANSIONS
                                if metadata_path == natsort_expansion_paths[0]:
                                    logger.warning(
                                        f"Found duplicate expansions for {package_id_normalized}: {natsort_expansion_paths}"
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
                                    f"Found duplicate expansion for {package_id_normalized}: {metadata_path}"
                                )
                                populated_mods.append(package_id_normalized)
                                active_mods_dict[uuid] = workshop_and_expansions[uuid]
                            if len(natsort_local_paths) > 1:  # LOCAL mods
                                if metadata_path == natsort_local_paths[0]:
                                    logger.warning(
                                        f"Found duplicate local mods for {package_id_normalized}: {natsort_local_paths}"
                                    )
                                    populated_mods.append(package_id_normalized)
                                    active_mods_dict[uuid] = workshop_and_expansions[
                                        uuid
                                    ]
                                    continue
                            # If the metadata_path is even in our local_paths <=1 item list for this duplicate (if 0 count, this would be false):
                            elif metadata_path in local_paths:
                                logger.warning(
                                    f"Found duplicate expansion for {package_id_normalized}: {metadata_path}"
                                )
                                populated_mods.append(package_id_normalized)
                                active_mods_dict[uuid] = workshop_and_expansions[uuid]
                            if len(natsort_workshop_paths) > 1:  # WORKSHOP mods
                                if metadata_path == natsort_workshop_paths[0]:
                                    logger.warning(
                                        f"Found duplicate workshop mods for {package_id_normalized}: {natsort_workshop_paths}"
                                    )
                                    populated_mods.append(package_id_normalized)
                                    active_mods_dict[uuid] = workshop_and_expansions[
                                        uuid
                                    ]
                                    continue
                            # If the metadata_path is even in our workshop_paths <=1 item list for this duplicate (if 0 count, this would be false):
                            elif metadata_path in workshop_paths:
                                logger.warning(
                                    f"Found duplicate expansion for {package_id_normalized}: {metadata_path}"
                                )
                                populated_mods.append(package_id_normalized)
                                active_mods_dict[uuid] = workshop_and_expansions[uuid]

        missing_mods = list(set(to_populate) - set(populated_mods))
        logger.info(
            f"Generated active_mods_dict with {len(active_mods_dict)} entries: {active_mods_dict}"
        )
        logger.info(f"Returning missing mods: {missing_mods}")
        return active_mods_dict, missing_mods
    else:
        logger.error(
            f"Unable to get active mods from config with read data: {mod_data}"
        )
        return active_mods_dict, missing_mods


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
