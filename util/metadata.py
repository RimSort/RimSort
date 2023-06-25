import json
from logger_tt import logger
from model.dialogue import show_warning
import os

from time import localtime, strftime, time
import traceback
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QThread, Signal

from model.dialogue import show_information, show_warning
from util.constants import DB_BUILDER_EXCEPTIONS, RIMWORLD_DLC_METADATA
from util.steam.steamfiles.wrapper import acf_to_dict
from util.steam.webapi.wrapper import DynamicQuery
from window.runner_panel import RunnerPanel

# Steam metadata / Community Rules


class SteamDatabaseBuilder(QThread):
    db_builder_message_output_signal = Signal(str)

    def __init__(
        self,
        apikey: str,
        appid: int,
        database_expiry: int,
        mode: str,
        output_database_path=None,
        get_appid_deps=None,
        update=None,
        mods=None,
    ):
        QThread.__init__(self)
        self.apikey = apikey
        self.appid = appid
        self.database_expiry = database_expiry
        self.get_appid_deps = get_appid_deps
        self.mode = mode
        self.mods = mods
        self.output_database_path = output_database_path
        self.publishedfileids = []
        self.update = update

    def run(self):
        self.db_builder_message_output_signal.emit(
            f"\nInitiating RimSort Steam Database Builder with mode : {self.mode}\n"
        )
        if len(self.apikey) == 32:  # If supplied WebAPI key is 32 characters
            self.db_builder_message_output_signal.emit(
                "Received valid Steam WebAPI key from settings"
            )
            # Since the key is valid, we try to launch a live query
            if self.mode == "no_local":
                self.db_builder_message_output_signal.emit(
                    f'\nInitializing "DynamicQuery" with configured Steam API key for AppID: {self.appid}\n\n'
                )
                # Create query
                dynamic_query = DynamicQuery(
                    apikey=self.apikey,
                    appid=self.appid,
                    life=self.database_expiry,
                    get_appid_deps=self.get_appid_deps,
                )
                # Connect messaging signal
                dynamic_query.dq_messaging_signal.connect(
                    self.db_builder_message_output_signal.emit
                )
                # Compile PublishedFileIds
                dynamic_query.pfids_by_appid()
                # Make sure we have PublishedFileIds to work with...
                if (
                    not len(dynamic_query.publishedfileids) > 0
                ):  # If we didn't get any pfids
                    self.db_builder_message_output_signal.emit(
                        "Did not receive any PublishedFileIds from IPublishedFileService/QueryFiles! Cannot continue!"
                    )
                    return  # Exit operation

                database = self._init_empty_db_from_publishedfileids(
                    dynamic_query.publishedfileids
                )
                dynamic_query.create_steam_db(
                    database=database, publishedfileids=dynamic_query.publishedfileids
                )
                self._output_database(dynamic_query.database)
                self.db_builder_message_output_signal.emit(
                    "SteamDatabasebuilder: Completed!"
                )
            elif self.mode == "all_mods":
                if not self.mods:
                    self.db_builder_message_output_signal.emit(
                        "SteamDatabaseBuilder: Please passthrough a dict of mod metadata for this mode."
                    )
                    return
                else:
                    if len(self.mods.keys()) > 0:  # No empty queries!
                        # Since the key is valid, and we have a list of pfid, we try to launch a live query
                        self.db_builder_message_output_signal.emit(
                            f'\nInitializing "DynamicQuery" with configured Steam API key for {self.appid}...\n'
                        )
                        database = self._init_db_from_local_metadata()
                        publishedfileids = []
                        for publishedfileid, metadata in database["database"].items():
                            if not metadata.get("appid"):  # If it's not an appid
                                publishedfileids.append(
                                    publishedfileid
                                )  # Add it to our list
                        dynamic_query = DynamicQuery(
                            apikey=self.apikey,
                            appid=self.appid,
                            life=self.database_expiry,
                            get_appid_deps=self.get_appid_deps,
                        )
                        dynamic_query.dq_messaging_signal.connect(
                            self.db_builder_message_output_signal.emit
                        )
                        dynamic_query.create_steam_db(database, publishedfileids)
                        self._output_database(dynamic_query.database)
                        self.db_builder_message_output_signal.emit(
                            "SteamDatabasebuilder: Completed!"
                        )
                    else:
                        self.db_builder_message_output_signal.emit(
                            "Tried to generate DynamicQuery with 0 mods...? Unable to initialize DynamicQuery for live metadata..."
                        )  # TODO: Make this warning visible to the user
                        return
            elif self.mode == "pfids_by_appid":
                self.db_builder_message_output_signal.emit(
                    f'\nInitializing "PublishedFileIDs by AppID" Query with configured Steam API key for AppID: {self.appid}...\n\n'
                )
                # Create query
                dynamic_query = DynamicQuery(self.apikey, self.appid)
                # Connect messaging signal
                dynamic_query.dq_messaging_signal.connect(
                    self.db_builder_message_output_signal.emit
                )
                # Compile PublishedFileIds
                dynamic_query.pfids_by_appid()
                self.publishedfileids = dynamic_query.publishedfileids.copy()
                self.db_builder_message_output_signal.emit(
                    "SteamDatabasebuilder: Completed!"
                )
            else:
                self.db_builder_message_output_signal.emit(
                    "SteamDatabaseBuilder: Invalid mode specified."
                )
        else:  # Otherwise, API key is not valid
            self.db_builder_message_output_signal.emit(
                f"SteamDatabaseBuilder ({self.mode}): Invalid Steam WebAPI key!"
            )
            self.db_builder_message_output_signal.emit(
                f"SteamDatabaseBuilder ({self.mode}): Exiting..."
            )

    def _init_db_from_local_metadata(self) -> Dict[str, Any]:
        db_from_local_metadata = {
            "version": 0,
            "database": {
                v["publishedfileid"]: {
                    "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={v['publishedfileid']}",
                    "packageId": v.get("packageId"),
                    "name": v.get("name"),
                    "authors": v.get("author"),
                    "gameVersions": v["supportedVersions"].get("li"),
                }
                for v in self.mods.values()
                if v.get("publishedfileid")
            },
        }

        db_from_local_metadata["database"].update(
            {
                v["steamAppId"]: {
                    "appid": True,
                    "url": f"https://store.steampowered.com/app/{v['steamAppId']}",
                    "packageId": v.get("packageId"),
                    "name": v.get("name"),
                    "authors": v.get("author"),
                    "gameVersions": v.get("supportedVersions", {}).get("li"),
                    "dependencies": {},
                }
                for v in self.mods.values()
                if v.get("steamAppId")
            }
        )
        total = len(db_from_local_metadata["database"].keys())
        self.db_builder_message_output_signal.emit(
            f"Populated {total} items from locally found metadata into initial database for "
            + f"{self.appid}..."
        )
        return db_from_local_metadata

    def _init_empty_db_from_publishedfileids(
        self, publishedfileids: list
    ) -> Dict[str, Any]:
        database = {
            "version": 0,
            "database": {
                **{
                    appid: {
                        "appid": True,
                        "url": f"https://store.steampowered.com/app/{appid}",
                        "packageId": metadata.get("packageId"),
                        "name": metadata.get("name"),
                    }
                    for appid, metadata in RIMWORLD_DLC_METADATA.items()
                },
                **{
                    publishedfileid: {
                        "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={publishedfileid}"
                    }
                    for publishedfileid in publishedfileids
                },
            },
        }
        total = len(database["database"].keys())
        self.db_builder_message_output_signal.emit(
            f"\nPopulated {total} items queried from Steam Workshop into initial database for "
            + f"{self.appid}..."
        )
        return database

    def _output_database(self, database: Dict[str, Any]) -> None:
        # If user-configured `update` parameter, update old db with new query data recursively
        if self.update and os.path.exists(self.output_database_path):
            self.db_builder_message_output_signal.emit(
                f"\nIn-place DB update configured. Existing DB to update:\n{self.output_database_path}"
            )
            if self.output_database_path and os.path.exists(self.output_database_path):
                with open(self.output_database_path, encoding="utf-8") as f:
                    json_string = f.read()
                    self.db_builder_message_output_signal.emit(
                        f"\nReading info from file..."
                    )
                    db_to_update = json.loads(json_string)
                    self.db_builder_message_output_signal.emit(
                        "Retreived cached database!\n"
                    )
                self.db_builder_message_output_signal.emit(
                    "Recursively updating previous database with new metadata...\n"
                )
                recursively_update_dict(
                    db_to_update,
                    database,
                    exceptions=DB_BUILDER_EXCEPTIONS,
                )
                with open(self.output_database_path, "w") as output:
                    json.dump(db_to_update, output, indent=4)
            else:
                self.db_builder_message_output_signal.emit(
                    "Unable to load database from specified path! Does the file exist...?"
                )
                appended_path = os.path.join(
                    os.path.split(self.output_database_path)[0],
                    "NEW_" + str(os.path.split(self.output_database_path[1])),
                )
                self.db_builder_message_output_signal.emit(
                    f"\nCaching DynamicQuery result:\n\n{appended_path}"
                )
                with open(appended_path, "w") as output:
                    json.dump(database, output, indent=4)
        else:  # Dump new db to specified path, effectively "overwriting" the db with fresh data
            self.db_builder_message_output_signal.emit(
                f"\nCaching DynamicQuery result:\n{self.output_database_path}"
            )
            with open(self.output_database_path, "w") as output:
                json.dump(database, output, indent=4)


def get_configured_steam_db(life: int, path: str) -> Tuple[Dict[str, Any], Any]:
    logger.info(f"Checking for Steam DB at: {path}")
    db_json_data = {}
    if os.path.exists(
        path
    ):  # Look for cached data & load it if available & not expired
        logger.info(
            f"Steam DB exists!",
        )
        with open(path, encoding="utf-8") as f:
            json_string = f.read()
            logger.info(f"Checking metadata expiry against database...")
            db_data = json.loads(json_string)
            current_time = int(time())
            db_time = int(db_data["version"])
            elapsed = current_time - db_time
            if (
                elapsed <= life
            ):  # If the duration elapsed since db creation is less than expiry than expiry
                # The data is valid
                db_json_data = db_data[
                    "database"
                ]  # TODO: additional check to verify integrity of this data's schema
                logger.info("Cached Steam DB is valid! Returning data to RimSort...")
            else:  # If the cached db data is expired but NOT missing
                # Fallback to the expired metadata
                show_warning(
                    title="Steam DB metadata expired",
                    text="Steam DB is expired! Consider updating!\n",
                    information="Unable to initialize Dynamic Query for live metadata!\n"
                    + "Falling back to cached, but EXPIRED Steam Database...\n",
                )
                db_json_data = db_data[
                    "database"
                ]  # TODO: additional check to verify integrity of this data's schema
            return db_json_data, path

    else:  # Assume db_data_missing
        show_warning(
            title="Steam DB is missing",
            text="Configured Steam DB not found!",
            information="Unable to initialize external metadata. There is no external Steam metadata being factored!\n"
            + "\nPlease use DB Builder to create a database, or update to the latest RimSort Steam Workshop Database.",
        )
        return db_json_data, None


def get_configured_community_rules_db(path: str) -> Tuple[Dict[str, Any], Any]:
    logger.info(f"Checking for Community Rules DB at: {path}")
    community_rules_json_data = {}
    if os.path.exists(
        path
    ):  # Look for cached data & load it if available & not expired
        logger.info(
            f"Community Rules DB exists!",
        )
        with open(path, encoding="utf-8") as f:
            json_string = f.read()
            logger.info("Reading info from communityRules.json")
            rule_data = json.loads(json_string)
            logger.debug(
                "Returning communityRules.json, this data is long so we forego logging it here"
            )
            total_entries = len(rule_data["rules"])
            logger.info(
                f"Loaded {total_entries} additional sorting rules from Community Rules"
            )
            community_rules_json_data = rule_data["rules"]
            return community_rules_json_data, path

    else:  # Assume db_data_missing
        show_warning(
            title="Community Rules DB is missing",
            text="Configured Community Rules DB not found!",
            information="Unable to initialize external metadata. There is no external Community Rules metadata being factored!\n"
            + "\nPlease use Rule Editor to create a database, or update to the latest RimSort Community Rules database.",
        )
        return community_rules_json_data, None


def get_rpmmdb_steam_metadata(mods: Dict[str, Any]) -> Tuple[Dict[str, Any], Any]:
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
                    total_entries = len(db_data["database"])
                    logger.info(
                        f"Loaded {total_entries} additional sorting rules from RPMMDB Steam DB"
                    )
                    db_json_data = db_data["database"]
                    return db_json_data, steam_db_rules_path
            else:
                logger.error("The db.json path does not exist!")
    logger.warning(
        "No RimPy Mod Manager Database mod was not found, or db.json was not found. Unable to load database from RPMMDB db.json!"
    )
    show_warning(
        text="RimPy Mod Manager Database mod was not found!",
        information=(
            "RimSort was unable to find this mod in your workshop or local mods folder.\n"
            + "Do you have the mod installed and/or are your paths set correctly?"
        ),
    )
    return db_json_data, None


def get_rpmmdb_community_rules_db(mods: Dict[str, Any]) -> Tuple[Dict[str, Any], Any]:
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
                    total_entries = len(rule_data["rules"])
                    logger.info(
                        f"Loaded {total_entries} additional sorting rules from RPMMDB Community Rules"
                    )
                    community_rules_json_data = rule_data["rules"]
                    return community_rules_json_data, community_rules_path
            else:
                logger.error("The communityRules.json path does not exist")
    logger.warning(
        "No RimPy Mod Manager Database mod was found, or communityRules.json was not found. Unable to load rules from RPMMDB communityRules.json!"
    )
    show_warning(
        text="RimPy Mod Manager Database mod was not found!",
        information=(
            "RimSort was unable to find this mod in your workshop or local mods folder.\n"
            + "Do you have the mod installed and/or are your paths set correctly?"
        ),
    )
    return community_rules_json_data, None


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


# Recursive function to update dictionary values with exceptions
def recursively_update_dict(a_dict, b_dict, exceptions=None):
    for key, value in b_dict.items():
        if exceptions and key in exceptions:
            # If the key is an exception, update its value directly from B
            a_dict[key] = value
        elif (
            key in a_dict and isinstance(a_dict[key], dict) and isinstance(value, dict)
        ):
            # If the key exists in both dictionaries and the values are dictionaries,
            # recursively update the nested dictionaries with exceptions
            recursively_update_dict(a_dict[key], value, exceptions)
        else:
            # Otherwise, update the value in A with the value from B
            a_dict[key] = value
