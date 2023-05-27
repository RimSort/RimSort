import json
from logger_tt import logger
from model.dialogue import show_warning
import os

from time import localtime, strftime, time
import traceback
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt

from model.dialogue import show_warning
from util.steam.steamfiles.wrapper import acf_to_dict
from util.steam.webapi.wrapper import AppIDQuery, DynamicQuery
from window.runner_panel import RunnerPanel

# Steam metadata / Community Rules


class SteamDatabaseBuilder:
    def __init__(
        self,
        apikey: str,
        appid: int,
        database_expiry: int,
        mode: str,
        output_database_path: str,
        get_appid_deps=None,
        mods=None,
    ):
        if mods:
            self.mods = mods
        self.apikey = apikey
        self.appid = appid
        self.database = {}
        self.database_expiry = database_expiry
        self.get_appid_deps = get_appid_deps
        self.mode = mode
        self.output_database_path = output_database_path
        self.query_runner = RunnerPanel()
        # self.query_runner.setWindowModality(Qt.ApplicationModal)
        self.query_runner.message(
            f"\nInitiating RimSort Steam Database Builder with mode : {self.mode}\n"
        )

    def run(self):
        self.query_runner.show()
        if self.mode is "complete":
            self.database = self._build_database_complete()
        elif self.mode is "local_only":
            if not self.mods:
                self.query_runner.message(
                    "SteamDatabaseBuilder: Please passthrough a dict of mod metadata for this mode."
                )
                return
            else:
                self.database = self._build_database_local_only()
        else:
            self.query_runner.message("SteamDatabaseBuilder: Invalid mode specified.")

    def _build_database_complete(self) -> Optional[Dict[str, Any]]:
        if len(self.apikey) == 32:  # If apikey is 32 characters
            self.query_runner.message("Received valid Steam API key from settings")
            # Since the key is valid, we try to launch a live query
            self.query_runner.message(
                f"\nInitializing AppIDQuery with configured Steam API key for AppID: {self.appid}...\n"
            )
            appid_query = AppIDQuery(
                self.apikey, self.appid, query_runner=self.query_runner
            )
            all_publishings_metadata_query = DynamicQuery(
                apikey=self.apikey,
                appid=self.appid,
                life=self.database_expiry,
                query_runner=self.query_runner,
                get_appid_deps=self.get_appid_deps,
            )
            if not len(appid_query.publishedfileids) > 0:  # If we didn't get any pfids
                return  # Exit operation
            db = {}
            db["version"] = all_publishings_metadata_query.expiry
            db["database"] = {}
            self.query_runner.message(
                f"Populating {str(len(appid_query.publishedfileids))} empty keys into initial database for "
                + f"{self.appid}."
            )
            for publishedfileid in appid_query.publishedfileids:
                db["database"][publishedfileid] = {
                    "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={publishedfileid}"
                }
            publishedfileids = appid_query.publishedfileids
            self.query_runner.message(
                f"Populated {str(len(appid_query.publishedfileids))} PublishedFileIds into database"
            )
            appid_query.all_mods_metadata = (
                all_publishings_metadata_query.cache_parsable_db_data(
                    db, publishedfileids
                )
            )
            # None check, if None, this means that our query failed!
            if appid_query.all_mods_metadata is None:
                self.query_runner.message("Unable to complete AppIDQuery!\n")
                self.query_runner.message("DynamicQuery failed to initialize database.")
                self.query_runner.message(
                    "There is no external metadata being factored for sorting!"
                )
                self.query_runner.message(
                    "Failed to initialize new DynamicQuery with configured Steam API key."
                )
                self.query_runner.message(
                    "Please right-click the 'Refresh' button and ensure that you have configure a valid Steam API key so that you can generate a database."
                )
                self.query_runner.message(
                    "Please reference: https://github.com/oceancabbage/RimSort/wiki/User-Guide#obtaining-your-steam-api-key--using-it-with-rimsort-dynamic-query"
                )
                return db
            self.query_runner.message(
                f"Caching DynamicQuery result: {self.output_database_path}"
            )
            with open(self.output_database_path, "w") as output:
                json.dump(appid_query.all_mods_metadata, output, indent=4)
            self.query_runner.message("AppIDQuery: Completed!")
            return db
        else:
            self.query_runner.message(
                "SteamWorkshopDatabaseBuilder (complete): Invalid Steam WebAPI key!"
            )
            self.query_runner.message(
                "SteamWorkshopDatabaseBuilder (complete): Exiting..."
            )

    def _build_database_local_only(self) -> Optional[Dict[str, Any]]:
        """
        Query Steam Workshop metadata for any active/inactive mods found that have a 'publishedfileid'.
        attribute contained in their mod metadata, used for the sorting functions.
        The resultant database is cached to the path specified.

        :param apikey: a Steam apikey that is pulled from game_configuration.steam_apikey
        :param db_json_data_life: expiry timer used for a cached Dynamic Query
        :param self.output_database_path: path to be used for caching the Dynamic Query
        :param mods: A Dict equivalent to 'all_mods' or mod_list.get_list_items_by_dict() in
        which contains possible Steam mods to lookup metadata for
        :return: Tuple containing the updated json data from database, and community_rules
        """
        db_data = {}  # This is kept to fall back on.
        db_data_expired = None
        db_data_missing = None
        db_json_data = {}
        self.query_runner.message(
            "Checking for cached Steam db..."
        )  # TODO: Make this info visible to the user
        if os.path.exists(
            self.output_database_path
        ):  # Look for cached data & load it if available & not expired
            self.query_runner.message(
                f"Found cached Steam db at {self.output_database_path}"
            )
            with open(self.output_database_path, encoding="utf-8") as f:
                json_string = f.read()
                self.query_runner.message(
                    f"Reading info from {self.output_database_path}"
                )
                db_data = json.loads(json_string)
                current_time = int(time())
                db_time = int(db_data["version"])
                if (
                    current_time - db_time > self.database_expiry
                ):  # If the duration elapsed since db creation is greater than expiry
                    db_json_data = db_data[
                        "database"
                    ]  # TODO: additional check to verify integrity of this data's schema
                    self.query_runner.message(
                        f"Cached Steam metadata is valid: {db_json_data}"
                    )
                    return db_json_data
                else:
                    db_data_expired = True
        else:
            db_data_missing = True
        if db_data_expired or db_data_missing:
            self.query_runner.message(
                "Cached data expired or missing. Attempting live query..."
            )
        # Attempt live query & cache the query
        if len(self.apikey) == 32:  # If apikey is less than 32 characters
            self.query_runner.message("Received valid Steam API key from settings")
            if len(self.mods.keys()) > 0:  # No empty queries!
                # Since the key is valid, and we have a list of pfid, we try to launch a live query
                self.query_runner.message(
                    f"\nInitializing DynamicQuery with configured Steam API key for {self.appid}...\n"
                )
                authors = ""
                gameVersions = []
                pfid = ""
                pid = ""
                name = ""
                local_metadata = {"version": 0, "database": {}}
                publishedfileids = []
                for v in self.mods.values():
                    if v.get("publishedfileid"):
                        pfid = v["publishedfileid"]
                        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"
                        local_metadata["database"][pfid] = {}
                        local_metadata["database"][pfid]["url"] = url
                        publishedfileids.append(pfid)
                        if v.get("packageId"):
                            pid = v["packageId"]
                            local_metadata["database"][pfid]["packageId"] = pid
                        if v.get("name"):
                            name = v["name"]
                            local_metadata["database"][pfid]["name"] = name
                        if v.get("author"):
                            authors = v["author"]
                            local_metadata["database"][pfid]["authors"] = authors
                        if v["supportedVersions"].get("li"):
                            gameVersions = v["supportedVersions"]["li"]
                            local_metadata["database"][pfid][
                                "gameVersions"
                            ] = gameVersions
                    elif v.get("steamAppId"):
                        steam_appid = v["steamAppId"]
                        url = f"https://store.steampowered.com/app/{steam_appid}"
                        local_metadata["database"][steam_appid] = {}
                        local_metadata["database"][steam_appid]["appid"] = True
                        local_metadata["database"][steam_appid]["url"] = url
                        if v.get("packageId"):
                            pid = v["packageId"]
                            local_metadata["database"][steam_appid]["packageId"] = pid
                        if v.get("name"):
                            name = v["name"]
                            local_metadata["database"][steam_appid]["name"] = name
                        if v.get("author"):
                            authors = v["author"]
                            local_metadata["database"][steam_appid]["authors"] = authors
                        if v.get("supportedVersions"):
                            if v["supportedVersions"].get("li"):
                                gameVersions = v["supportedVersions"]["li"]
                                local_metadata["database"][steam_appid][
                                    "gameVersions"
                                ] = gameVersions
                        local_metadata["database"][steam_appid]["dependencies"] = {}
                        self.query_runner.message(
                            f"Populated local metadata for Steam appid: [{pid} | {steam_appid}]"
                        )
                mods_query = DynamicQuery(
                    apikey=self.apikey,
                    appid=self.appid,
                    life=self.database_expiry,
                    query_runner=self.query_runner,
                    get_appid_deps=self.get_appid_deps,
                )
                mods_query.workshop_json_data = mods_query.cache_parsable_db_data(
                    local_metadata, publishedfileids
                )
                if mods_query.workshop_json_data is None:
                    self.query_runner.message("Unable to complete DynamicQuery!\n")
                    self.query_runner.message(
                        "DynamicQuery failed to initialize database."
                    )
                    self.query_runner.message(
                        "There is no external metadata being factored for sorting!"
                    )
                    self.query_runner.message(
                        "Cached Dynamic Query database not found!"
                    )
                    self.query_runner.message(
                        "Failed to initialize new DynamicQuery with configured Steam API key."
                    )
                    self.query_runner.message(
                        "Please right-click the 'Refresh' button and ensure that you have configure a valid Steam API key so that you can generate a database."
                    )
                    self.query_runner.message(
                        "Please reference: https://github.com/oceancabbage/RimSort/wiki/User-Guide#obtaining-your-steam-api-key--using-it-with-rimsort-dynamic-query"
                    )
                    return db_json_data
                self.query_runner.message(
                    f"Caching DynamicQuery result: {self.output_database_path}"
                )
                with open(self.output_database_path, "w") as output:
                    json.dump(mods_query.workshop_json_data, output, indent=4)
                db_json_data = mods_query.workshop_json_data[
                    "database"
                ]  # Get json data directly from memory upon query completion
            else:
                self.query_runner.message(
                    "Tried to generate DynamicQuery with 0 mods...? Unable to initialize DynamicQuery for live metadata..."
                )  # TODO: Make this warning visible to the user
        else:  # Otherwise, API key is not valid
            if (
                db_data_expired and not db_data_missing
            ):  # If the cached db data is expired but NOT missing
                # Fallback to the expired metadata
                self.query_runner.message(
                    "\nFailed to read a valid Steam API key from settings.json"
                )
                self.query_runner.message(
                    "Unable to initialize DynamicQuery for live metadata!"
                )
                self.query_runner.message(
                    "Falling back to cached, but EXPIRED Dynamic Query database..."
                )
                db_json_data = db_data[
                    "database"
                ]  # TODO: additional check to verify integrity of this data's schema
            else:  # Assume db_data_missing
                self.query_runner.message("Unable to initialize external metadata.")
                self.query_runner.message(
                    "There is no external metadata being factored for sorting!"
                )
                self.query_runner.message("Cached Dynamic Query database not found!")
                self.query_runner.message(
                    "Please right-click the 'Refresh' button and configure a valid Steam API key so that you can generate a database."
                )
                self.query_runner.message(
                    "Please reference: https://github.com/oceancabbage/RimSort/wiki/User-Guide#obtaining-your-steam-api-key--using-it-with-rimsort-dynamic-query"
                )
        return db_json_data


def get_rpmmdb_community_rules_db(mods: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract the RimPy Mod Manager Database mod's `communityRules.json` database, which is
    used for sorting. Produces an error if the DB mod is not found.
    """
    logger.info(
        "Using Paladin's RimPy Mod Manager Database mod for external community rules..."
    )
    community_rules_json_data = {}
    for uuid in mods:
        if (
            mods[uuid].get("packageId") == "rupal.rimpymodmanagerdatabase"
            or mods[uuid].get("publishedfileid") == "1847679158"
        ):
            logger.info("Found RimPy Mod Manager Database mod")
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
            return community_rules_json_data
    logger.warning(
        "No RimPy Mod Manager Database was found. Unable to load rules from RPMMDB communityRules.json!"
    )
    show_warning(
        text="RimPy Mod Manager Database mod was not found!",
        information=(
            "RimSort was unable to find this mod in your workshop or local mods folder.\n"
            + "Do you have the mod installed and/or are your paths set correctly?"
        ),
    )
    return community_rules_json_data


def get_rpmmdb_steam_metadata(mods: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract the RimPy Mod Manager Database mod's `db.json` Steam Workshop metadata, which is
    used for sorting. Produces an error if the DB mod is not found.
    """
    logger.info(
        "Using Paladin's RimPy Mod Manager Database mod for external Steam Workshop metadata..."
    )
    db_json_data = {}
    for uuid in mods:
        if (
            mods[uuid].get("packageId") == "rupal.rimpymodmanagerdatabase"
            or mods[uuid].get("publishedfileid") == "1847679158"
        ):
            logger.info("Found RimPy Mod Manager Database mod")
            steam_db_rules_path = os.path.join(mods[uuid]["path"], "db", "db.json")
            logger.info(f"Generated path to db.json: {steam_db_rules_path}")
            if os.path.exists(steam_db_rules_path):
                with open(steam_db_rules_path, encoding="utf-8") as f:
                    json_string = f.read()
                    logger.info("Reading info from db.json")
                    db_data = json.loads(json_string)
                    logger.debug(
                        "Returning db.json, this data is long so we forego logging it here."
                    )
                    db_json_data = db_data["database"]
            else:
                logger.error("The db.json path does not exist")
            return db_json_data
    logger.warning(
        "RimPy Mod Manager Database was not found! Unable to load database from RPMMDB db.json!"
    )
    show_warning(
        text="RimPy Mod Manager Database mod was not found!",
        information=(
            "RimSort was unable to find this mod in your workshop or local mods folder.\n"
            + "Do you have the mod installed and/or are your paths set correctly?"
        ),
    )
    return db_json_data


# Steam client / SteamCMD metadata


def get_external_time_data_for_workshop_mods(
    steam_db_rules: Dict[str, Any], mods: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Query Steam Workshop metadata for time data, for any mods that have a 'publishedfileid'
    attribute contained in their mod_data, and from there, populate mod_json_data with it.

    Return a dict of any potential mod updates found for Steam Workshop mods, with time data

    :param steam_db_rules: a dict containing the ["database"] rules from external metadata
    :param mods: A Dict equivalent to 'all_mods' or mod_list.get_list_items_by_dict() in
    which contains possible Steam mods to lookup metadata for
    :return: a dict of any potential mod updates found for Steam Workshop mods, with time data
    """
    logger.info("Parsing Steam mod metadata for most recent time data")
    workshop_mods_potential_updates = {}
    for v in mods.values():
        if v["data_source"] == "workshop":  # If the mod we are parsing is a Steam mod
            if v.get("publishedfileid"):
                pfid = v["publishedfileid"]  # ... assume pfid exists in mod metadata
                uuid = v["uuid"]
                # It is possible for a mod to not have metadata in an outdated/stale Dynamic Query
                if steam_db_rules.get(pfid):
                    if steam_db_rules[pfid].get("external_time_created"):
                        mods[uuid]["external_time_created"] = steam_db_rules[pfid][
                            "external_time_created"  # ... populate external metadata into mod_json_data
                        ]
                    if steam_db_rules[pfid].get("external_time_updated"):
                        mods[uuid]["external_time_updated"] = steam_db_rules[pfid][
                            "external_time_updated"  # ... populate external metadata into mod_json_data
                        ]
                # logger.debug(f"Checking time data for mod {pfid}")
                try:
                    if v.get("name"):
                        name = v["name"]
                    elif steam_db_rules[pfid].get("steamName"):
                        name = steam_db_rules[pfid]["steamName"]
                    else:
                        name = "UNKNOWN"
                    name = f"############################\n{name}"  # ... get the name
                    etc = v["external_time_created"]
                    etu = v["external_time_updated"]
                    itt = v["internal_time_touched"]
                    itu = v["internal_time_updated"]
                    time_data_human_readable = (  # ... create human readable string
                        f"\n{name}"
                        + f"\nInstalled mod last touched: {strftime('%Y-%m-%d %H:%M:%S', localtime(itt))}"
                        + f"\nPublishing last updated: {strftime('%Y-%m-%d %H:%M:%S', localtime(etu))}\n"
                    )
                    # logger.debug(time_data_human_readable)
                    if (
                        itt != 0 and etu > itt
                    ):  # If external_mod_updated time is PAST the time Steam client last touched a Steam mod
                        logger.info(f"Potential update found for Steam mod: {pfid}")
                        workshop_mods_potential_updates[pfid] = {}
                        workshop_mods_potential_updates[pfid][
                            "external_time_created"
                        ] = etc
                        workshop_mods_potential_updates[pfid][
                            "external_time_updated"
                        ] = etu
                        workshop_mods_potential_updates[pfid][
                            "internal_time_touched"
                        ] = itt
                        workshop_mods_potential_updates[pfid][
                            "internal_time_updated"
                        ] = itu
                        workshop_mods_potential_updates[pfid][
                            "ui_string"
                        ] = time_data_human_readable
                except KeyError as e:
                    stacktrace = traceback.format_exc()
                    logger.info(f"Missing time data for Steam mod: {pfid}")
                    logger.info(stacktrace)
    return workshop_mods_potential_updates


def get_workshop_acf_data(
    appworkshop_acf_path: str, workshop_mods: Dict[str, Any]
) -> None:
    """
    Given a path to the Rimworld Steam Workshop appworkshop_294100.acf file, and parse it into a dict.

    The purpose of this function is to populate the info from this file to mod_json_data for later usage.

    :param appworkshop_acf_path: path to the Rimworld Steam Workshop appworkshop_294100.acf file
    :param workshop_mods: a Dict containing parsed mod metadata from Steam workshop mods. This can be
    all_mods or just a dict of Steam mods where their ["data_source"] is "workshop".
    """
    workshop_acf_data = acf_to_dict(appworkshop_acf_path)
    workshop_mods_pfid_to_uuid = {}
    for v in workshop_mods.values():
        if v.get("invalid"):
            logger.debug(f"Unable to parse acf data for invalid mod: {v}")
            continue
        else:
            if v.get("publishedfileid"):
                pfid = v["publishedfileid"]
                workshop_mods_pfid_to_uuid[pfid] = v["uuid"]
    for publishedfileid in workshop_acf_data["AppWorkshop"][
        "WorkshopItemDetails"
    ].keys():
        if publishedfileid in workshop_mods_pfid_to_uuid:
            mod_uuid = workshop_mods_pfid_to_uuid[publishedfileid]
            workshop_mods[mod_uuid]["internal_time_touched"] = int(
                workshop_acf_data["AppWorkshop"]["WorkshopItemDetails"][
                    publishedfileid
                ][
                    "timetouched"
                ]  # The last time Steam client touched a mod according to it's entry in appworkshop_294100.acf
            )
    for publishedfileid in workshop_acf_data["AppWorkshop"][
        "WorkshopItemsInstalled"
    ].keys():
        if publishedfileid in workshop_mods_pfid_to_uuid:
            mod_uuid = workshop_mods_pfid_to_uuid[publishedfileid]
            workshop_mods[mod_uuid]["internal_time_updated"] = int(
                workshop_acf_data["AppWorkshop"]["WorkshopItemsInstalled"][
                    publishedfileid
                ]["timeupdated"]
            )  # I think this is always equivalent to the external_metadata entry for this same data. Unsure. Probably not unless a mod is outdated by quite some time
