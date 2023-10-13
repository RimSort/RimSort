from concurrent.futures import Future
from functools import partial
import json
from logger_tt import logger
from natsort import natsorted
import os
from pathlib import Path
import platform
from requests.exceptions import HTTPError
from time import localtime, strftime, time
import traceback
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from PySide6.QtCore import (
    Qt,
    QEventLoop,
    QMutex,
    QMutexLocker,
    QObject,
    QRunnable,
    QThread,
    QThreadPool,
    Signal,
)

from model.dialogue import (
    show_dialogue_conditional,
    show_dialogue_file,
    show_information,
    show_warning,
)
from util.constants import (
    DB_BUILDER_PRUNE_EXCEPTIONS,
    DB_BUILDER_PURGE_KEYS,
    DB_BUILDER_RECURSE_EXCEPTIONS,
    DEFAULT_USER_RULES,
    RIMWORLD_DLC_METADATA,
)
from util.generic import directories
from util.schema import validate_mods_config_format
from util.steam.steamcmd.wrapper import SteamcmdInterface
from util.steam.steamfiles.wrapper import acf_to_dict, dict_to_acf
from util.steam.webapi.wrapper import (
    DynamicQuery,
    ISteamRemoteStorage_GetPublishedFileDetails,
)
from util.xml import xml_path_to_json
from view.game_configuration_panel import GameConfiguration
from window.runner_panel import RunnerPanel

# Locally installed mod metadata


class MetadataManager(QObject):
    _instance: Optional["MetadataManager"] = None

    show_warning_signal = Signal(str, str, str, str)
    update_game_configuration_signal = Signal()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MetadataManager, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "initialized"):
            super(MetadataManager, self).__init__()
            logger.info("Initializing MetadataManager")

            # Initialize our threadpool for multithreaded parsing
            self.parser_threadpool = QThreadPool.globalInstance()

            # Connect a warning signal for thread-safe prompts
            self.show_warning_signal.connect(show_warning)

            # Store parsed metadata & paths
            self.all_mods_compiled = {}
            self.info_from_steam_package_id_to_name = {}
            self.external_steam_metadata = None
            self.external_steam_metadata_path = None
            self.external_community_rules = None
            self.external_community_rules_path = None
            self.external_user_rules = None
            self.internal_local_metadata = {}
            self.expansion_subdirectories = []
            self.local_subdirectories = []
            self.workshop_subdirectories = []

            # Empty game version string unless the data is populated
            self.game_version = ""

            # Generate Steam .acf file path
            self.steam_acf_path = str(
                Path(
                    # This is just getting the path 2 directories up from content/294100,
                    # so that we can find workshop/appworkshop_294100.acf
                    os.path.join(
                        os.path.split(
                            os.path.split(
                                GameConfiguration.instance().workshop_folder_line.text()
                            )[0]
                        )[0],
                        "appworkshop_294100.acf",
                    )
                ).resolve()
            )
            logger.info("Finished MetadataManager initialization")
            self.initialized = True

    @classmethod
    def instance(cls, *args: Any, **kwargs: Any) -> "MetadataManager":
        if cls._instance is None:
            cls._instance = cls(*args, **kwargs)
        elif args or kwargs:
            raise ValueError("MetadataManager instance has already been initialized.")
        return cls._instance

    def __refresh_external_metadata(self) -> None:
        def get_configured_steam_db(
            self, life: int, path: str
        ) -> Tuple[Optional[Dict], Optional[str]]:
            logger.info(f"Checking for Steam DB at: {path}")
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
                        logger.info(
                            "Cached Steam DB is valid! Returning data to RimSort..."
                        )
                        total_entries = len(db_json_data)
                        logger.info(
                            f"Loaded metadata for {total_entries} Steam Workshop mods from Steam DB"
                        )
                    else:  # If the cached db data is expired but NOT missing
                        # Fallback to the expired metadata
                        self.show_warning_signal.emit(
                            "Steam DB metadata expired",
                            "Steam DB is expired! Consider updating!\n",
                            f'Steam DB last updated: {strftime("%Y-%m-%d %H:%M:%S", localtime(db_data["version"] - life))}\n\n'
                            + "Falling back to cached, but EXPIRED Steam Database...",
                            "",
                        )
                        db_json_data = db_data[
                            "database"
                        ]  # TODO: additional check to verify integrity of this data's schema
                        total_entries = len(db_json_data)
                        logger.info(
                            f"Loaded metadata for {total_entries} Steam Workshop mods from Steam DB"
                        )
                    return db_json_data, path

            else:  # Assume db_data_missing
                self.show_warning_signal.emit(
                    "Steam DB is missing",
                    "Configured Steam DB not found!",
                    "Unable to initialize external metadata. There is no external Steam metadata being factored!\n"
                    + "\nPlease use DB Builder to create a database, or update to the latest RimSort Steam Workshop Database.",
                    "",
                )
                return None, None

        def get_configured_community_rules_db(
            self, path: str
        ) -> Tuple[Optional[Dict], Optional[str]]:
            logger.info(f"Checking for Community Rules DB at: {path}")
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
                    community_rules_json_data = rule_data["rules"]
                    total_entries = len(community_rules_json_data)
                    logger.info(
                        f"Loaded {total_entries} additional sorting rules from Community Rules"
                    )
                    return community_rules_json_data, path

            else:  # Assume db_data_missing
                self.show_warning_signal.emit(
                    "Community Rules DB is missing",
                    "Configured Community Rules DB not found!",
                    "Unable to initialize external metadata. There is no external Community Rules metadata being factored!\n"
                    + "\nPlease use Rule Editor to create a database, or update to the latest RimSort Community Rules database.",
                    "",
                )
                return None, None

        # Load external metadata
        # External Steam metadata
        if (
            GameConfiguration.instance().settings_panel.external_steam_metadata_cb.currentText()
            == "Configured file path"
        ):
            (
                self.external_steam_metadata,
                self.external_steam_metadata_path,
            ) = get_configured_steam_db(
                self,
                life=GameConfiguration.instance().database_expiry,
                path=GameConfiguration.instance().steam_db_file_path,
            )
        elif (
            GameConfiguration.instance().settings_panel.external_steam_metadata_cb.currentText()
            == "Configured git repository"
        ):
            (
                self.external_steam_metadata,
                self.external_steam_metadata_path,
            ) = get_configured_steam_db(
                self,
                life=GameConfiguration.instance().database_expiry,
                path=str(
                    Path(
                        os.path.join(
                            GameConfiguration.instance().dbs_path,
                            os.path.split(GameConfiguration.instance().steam_db_repo)[
                                1
                            ],
                            "steamDB.json",
                        )
                    ).resolve()
                ),
            )
        else:
            logger.info(
                "External Steam metadata disabled by user. Please choose a metadata source in settings."
            )

        # External Community Rules metadata
        if (
            GameConfiguration.instance().settings_panel.external_community_rules_metadata_cb.currentText()
            == "Configured file path"
        ):
            (
                self.external_community_rules,
                self.external_community_rules_path,
            ) = get_configured_community_rules_db(
                self,
                path=GameConfiguration.instance().community_rules_file_path,
            )
        elif (
            GameConfiguration.instance().settings_panel.external_community_rules_metadata_cb.currentText()
            == "Configured git repository"
        ):
            (
                self.external_community_rules,
                self.external_community_rules_path,
            ) = get_configured_community_rules_db(
                self,
                path=str(
                    Path(
                        os.path.join(
                            GameConfiguration.instance().dbs_path,
                            os.path.split(
                                GameConfiguration.instance().community_rules_repo
                            )[1],
                            "communityRules.json",
                        )
                    ).resolve()
                ),
            )
        else:
            logger.info(
                "External Community Rules metadata disabled by user. Please choose a metadata source in settings."
            )
        # External User Rules metadata
        if os.path.exists(GameConfiguration.instance().user_rules_file_path):
            logger.info("Loading userRules.json")
            with open(
                GameConfiguration.instance().user_rules_file_path, encoding="utf-8"
            ) as f:
                json_string = f.read()
                self.external_user_rules = json.loads(json_string)["rules"]
            total_entries = len(self.external_user_rules)
            logger.info(
                f"Loaded {total_entries} additional sorting rules from User Rules"
            )
        else:
            logger.info(
                "Unable to find userRules.json in storage. Creating new user rules db!"
            )
            with open(
                GameConfiguration.instance().user_rules_file_path, "w", encoding="utf-8"
            ) as output:
                json.dump(DEFAULT_USER_RULES, output, indent=4)
            self.external_user_rules = DEFAULT_USER_RULES["rules"]

    def __refresh_internal_metadata(self) -> None:
        def get_workshop_acf_data(
            self, appworkshop_acf_path: str, workshop_mods: Dict[str, Any]
        ) -> None:
            """
            Given a path to the Rimworld Steam Workshop appworkshop_294100.acf file, and parse it into a dict.

            The purpose of this function is to populate the info from this file to mod_json_data for later usage.

            :param appworkshop_acf_path: path to the Rimworld Steam Workshop appworkshop_294100.acf file
            :param workshop_mods: a Dict containing parsed mod metadata from Steam workshop mods. This can be
            all_mods or just a dict of Steam mods where their ["data_source"] is "workshop".
            :param steamcmd_mode: set to True for mode which forces match of folder name + publishedfileid for parsing
            """
            workshop_acf_data = acf_to_dict(appworkshop_acf_path)
            workshop_mods_pfid_to_uuid = {
                v["publishedfileid"]: v["uuid"]
                for v in workshop_mods.values()
                if v.get("publishedfileid")
            }
            # Reference needed information from appworkshop_294100.acf
            workshop_item_details = workshop_acf_data["AppWorkshop"][
                "WorkshopItemDetails"
            ]
            workshop_items_installed = workshop_acf_data["AppWorkshop"][
                "WorkshopItemsInstalled"
            ]
            # Loop through our metadata, append values
            for publishedfileid, mod_uuid in workshop_mods_pfid_to_uuid.items():
                if (
                    workshop_item_details.get(publishedfileid, {}).get("timetouched")
                    and workshop_item_details.get(publishedfileid, {}).get(
                        "timetouched"
                    )
                    != 0
                ):
                    # The last time SteamCMD/Steam client touched a mod according to its entry
                    workshop_mods[mod_uuid]["internal_time_touched"] = int(
                        workshop_item_details[publishedfileid]["timetouched"]
                    )
                if workshop_item_details.get(publishedfileid, {}).get("timeupdated"):
                    # The last time SteamCMD/Steam client updated a mod according to its entry
                    workshop_mods[mod_uuid]["internal_time_updated"] = int(
                        workshop_item_details[publishedfileid]["timeupdated"]
                    )
                if workshop_items_installed.get(publishedfileid, {}).get("timeupdated"):
                    # The last time SteamCMD/Steam client updated a mod according to its entry
                    workshop_mods[mod_uuid]["internal_time_updated"] = int(
                        workshop_items_installed[publishedfileid]["timeupdated"]
                    )

        def get_game_version(self, game_path: str) -> str:
            """
            This function starts the Rimworld game version string from the file
            'Version.txt' that is found in the configured game directory.

            :param game_path: path to Rimworld game
            :return: the game version as a string
            """
            logger.info(f"Getting game version from Game Folder: {game_path}")
            version = ""
            version_file_path = str(
                Path(os.path.join(game_path, "Version.txt")).resolve()
            )
            logger.debug(f"Generated Version.txt path: {version_file_path}")
            if os.path.exists(version_file_path):
                try:
                    with open(version_file_path) as f:
                        version = f.read()
                        logger.info(
                            f"Retrieved game version from Version.txt: {version.strip()}"
                        )
                except:
                    logger.error(
                        f"Unable to parse Version.txt from game folder: {version_file_path}"
                    )
            else:
                logger.error(
                    f"The provided Version.txt path does not exist: {version_file_path}"
                )
                self.show_warning_signal.emit(
                    "Missing Version.txt",
                    f"RimSort is unable to get the game version at the expected path: [{version_file_path}].",
                    f"\nIs your game path [{game_path}] set correctly? There should be a Version.txt file in the game install directory.",
                    "",
                )
            return version.strip()

        def get_installed_expansions(self) -> Dict[str, Any]:
            """
            Given a path to the game's install folder, return a dict
            containing data for all of the installed expansions
            keyed to their package ids. The dict values are the converted
            About.xmls. If the path does not exist, the dict
            will be empty.

            :param path: path to the Rimworld install folder
            :return: a Dict of expansions by package id
            """
            expansion_data = {}
            if GameConfiguration.instance().game_folder_line.text() != "":
                logger.info(
                    f"Getting installed expansions with game folder path: {GameConfiguration.instance().game_folder_line.text()}"
                )

                # Get mod data
                data_path = str(
                    Path(
                        os.path.join(
                            GameConfiguration.instance().game_folder_line.text(), "Data"
                        )
                    ).resolve()
                )
                logger.info(
                    f"Attempting to get expansion data from RimWorld's Data folder: {data_path}"
                )
                self.expansion_subdirectories = directories(data_path)
                expansion_data = self.process_mods(
                    directories_to_process=self.expansion_subdirectories,
                    intent="expansion",
                )
                logger.info("Finished getting expansion data")

                # Base game and expansion About.xml do not contain name, so these
                # must be manually added
                logger.info("Manually populating expansion data")
                dlcs_packageid_to_appid = {
                    "ludeon.rimworld": {
                        "appid": "294100",
                    },
                    "ludeon.rimworld.royalty": {
                        "appid": "1149640",
                    },
                    "ludeon.rimworld.ideology": {
                        "appid": "1392840",
                    },
                    "ludeon.rimworld.biotech": {
                        "appid": "1826140",
                    },
                }
                for data in expansion_data.values():
                    package_id = data["packageid"]
                    if package_id in dlcs_packageid_to_appid:
                        dlc_data = dlcs_packageid_to_appid[package_id]
                        data.update(
                            {
                                "appid": dlc_data["appid"],
                                "name": RIMWORLD_DLC_METADATA[dlc_data["appid"]][
                                    "name"
                                ],
                                "steam_url": RIMWORLD_DLC_METADATA[dlc_data["appid"]][
                                    "steam_url"
                                ],
                                "description": RIMWORLD_DLC_METADATA[dlc_data["appid"]][
                                    "description"
                                ],
                                "supportedversions": {
                                    "li": ".".join(self.game_version.split(".")[:2])
                                }
                                if not data.get("supportedversions")
                                else data.get("supportedversions"),
                            }
                        )
                    else:
                        logger.error(
                            f"An unknown mod has been found in the expansions folder: {package_id} {data}"
                        )
                logger.info("Finished getting installed expansions")
            else:
                logger.error(
                    "Skipping parsing data from empty game data path. Is the game path configured?"
                )
            return expansion_data

        def get_local_mods(self) -> Dict[str, Any]:
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
            if GameConfiguration.instance().local_folder_line.text() != "":
                if GameConfiguration.instance().game_folder_line.text():
                    logger.info(
                        f"Supplementing call with game folder path: {GameConfiguration.instance().game_folder_line.text()}"
                    )

                # Get mod data
                logger.info(
                    f"Getting local mods from path: {GameConfiguration.instance().local_folder_line.text()}"
                )
                self.local_subdirectories = directories(
                    GameConfiguration.instance().local_folder_line.text()
                )
                mod_data = self.process_mods(
                    directories_to_process=self.local_subdirectories, intent="local"
                )
                logger.info("Finished getting local mod data")
            else:
                logger.debug(
                    "Skipping parsing data from empty local mods path. Is the local mods path configured?"
                )
            return mod_data

        def get_workshop_mods(self) -> Dict[str, Any]:
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
            if GameConfiguration.instance().workshop_folder_line.text() != "":
                logger.info(
                    f"Getting workshop mods from path: {GameConfiguration.instance().workshop_folder_line.text()}"
                )
                self.workshop_subdirectories = directories(
                    GameConfiguration.instance().workshop_folder_line.text()
                )
                mod_data = self.process_mods(
                    directories_to_process=self.workshop_subdirectories,
                    intent="workshop",
                )
                logger.info("Finished getting workshop mods")
            else:
                logger.debug(
                    "Skipping parsing data from empty workshop mods path. Is the workshop mods path configured?"
                )
            return mod_data

        def merge_mod_data(self, *dict_args: dict[str, Any]) -> Dict[str, Any]:
            """
            Given any number of dictionaries, shallow copy and merge into a new dict,
            precedence goes to key-value pairs in latter dictionaries.
            """
            logger.info(f"Merging mods from {len(dict_args)} sources")
            result = {}
            for dictionary in dict_args:
                result.update(dictionary)
            return result

        # Get & set Rimworld version string
        self.game_version = get_game_version(
            self, game_path=GameConfiguration.instance().game_folder_line.text()
        )

        # Get and cache installed base game / DLC data
        if (
            GameConfiguration.instance().game_folder_line.text()
            and GameConfiguration.instance().game_folder_line.text() != ""
        ):
            expansions = get_installed_expansions(self)
        else:
            expansions = {}

        # Get and cache installed local/SteamCMD Workshop mods
        if (
            GameConfiguration.instance().local_folder_line.text()
            and GameConfiguration.instance().local_folder_line.text() != ""
        ):
            local_mods = get_local_mods(self)

            # If we can find the appworkshop_294100.acf files from SteamCMD or Steam client
            # SteamCMD
            if os.path.exists(
                SteamcmdInterface.instance().steamcmd_appworkshop_acf_path
            ):  # If the file we want to parse exists
                get_workshop_acf_data(
                    self,
                    appworkshop_acf_path=SteamcmdInterface.instance().steamcmd_appworkshop_acf_path,
                    workshop_mods=local_mods,
                )  # ... get data
                logger.info(
                    f"Successfully parsed SteamCMD appworkshop.acf metadata from: {SteamcmdInterface.instance().steamcmd_appworkshop_acf_path}"
                )
            else:
                logger.debug(
                    f"SteamCMD appworkshop.acf metadata not found. Skipping: {SteamcmdInterface.instance().steamcmd_appworkshop_acf_path}"
                )
                logger.debug(
                    "Parsing timetouched from the Workshop mod folders on the filesystem"
                )
        else:
            local_mods = {}
        # Get and cache installed Steam client Workshop mods
        if (
            GameConfiguration.instance().workshop_folder_line.text()
            and GameConfiguration.instance().workshop_folder_line.text() != ""
        ):
            workshop_mods = get_workshop_mods(self)
            # Steam client
            if os.path.exists(
                self.steam_acf_path
            ):  # If the file we want to parse exists
                get_workshop_acf_data(
                    self,
                    appworkshop_acf_path=self.steam_acf_path,
                    workshop_mods=workshop_mods,
                )  # ... get data
                logger.info(
                    f"Successfully parsed Steam client appworkshop.acf metadata from: {self.steam_acf_path}"
                )
            else:
                logger.debug(
                    f"Steam client appworkshop.acf metadata not found. Skipping: {self.steam_acf_path}"
                )
        else:
            workshop_mods = {}
        # One working Dictionary for ALL mods
        self.internal_local_metadata = merge_mod_data(
            self, expansions, local_mods, workshop_mods
        )
        logger.info(
            f"Combined {len(expansions)} expansions, {len(local_mods)} local mods, and {len(workshop_mods)}. Total elements to get dependencies for: {len(self.internal_local_metadata)}"
        )

        # Calculate and cache dependencies for ALL mods
        logger.info("Parsing dependencies & load order rules from metadata")
        (
            self.all_mods_compiled,
            self.info_from_steam_package_id_to_name,
        ) = self.compile_all_mods(
            self.internal_local_metadata,
            self.external_steam_metadata,
            self.external_community_rules,
            self.external_user_rules,
        )

    def process_mods(self, directories_to_process: list, intent: str) -> Dict[str, Any]:
        logger.info(
            f"Processing updates for {len(directories_to_process)} mod directories"
        )
        # Create a shared results dict for our metadata
        results = {}
        # Process our parsers
        for directory in directories_to_process:
            parser = ModParser(
                directory=directory,
                intent=intent,
                results=results,
                steam_db=self.external_steam_metadata,
            )
            # Start each parser in the pool
            self.parser_threadpool.start(parser)
        # Wait for pool to complete
        self.parser_threadpool.waitForDone()
        # Collect our results
        logger.info(f"Finished processing directories for {intent}")
        return results

    def refresh_cache(self, is_initial=None) -> None:
        """
        This function contains expensive calculations for getting workshop
        mods, known expansions, community rules, and most importantly, calculating
        dependencies for all mods.

        This function should be called on app initialization
        and whenever the refresh button is pressed (mostly after changing the workshop
        somehow, e.g. re-setting workshop path, mods config path, or downloading another mod,
        but also after ModsConfig.xml path has been changed).
        """
        logger.info("Refreshing cache calculations")

        # If we are refreshing cache from user action, update user paths as well in case of change
        if not is_initial:
            self.update_game_configuration_signal.emit()

        # Update paths from game configuration

        # Populate metadata
        self.__refresh_external_metadata()
        self.__refresh_internal_metadata()

        logger.info("Finished refreshing cache calculations")

    def compile_all_mods(
        self,
        all_mods: Dict[str, Any],
        steam_db: Dict[str, Any],
        community_rules: Dict[str, Any],
        user_rules: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Iterate through each expansion or mod and add new key-values describing
        its dependencies, incompatibilities, and load order rules from external metadata.

        :param all_mods: dict of all mods from local mod (and expansion) metadata
        :param steam_db: a dict containing the ["database"] rules from external metadata
        :param community_rules: dict of community established rules from external metadata
        :param user_rules: dict of user-configured rules from external metadata
        :return all_mods_compiled: expansions + mods with all data compiled
        """
        logger.info("Started compiling all mods from internal/external metadata")

        # Create an index for all_mods
        packageid_to_uuid = {
            mod.get("packageid"): uuid for uuid, mod in all_mods.items()
        }

        # Add dependencies to installed mods based on dependencies listed in About.xml TODO manifest.xml
        logger.info("Started compiling metadata from About.xml")
        for uuid in all_mods:
            logger.debug(f"UUID: {uuid} packageid: " + all_mods[uuid].get("packageid"))

            # moddependencies are not equal to mod load order rules
            if all_mods[uuid].get("moddependencies"):
                dependencies = all_mods[uuid]["moddependencies"].get("li")
                if dependencies:
                    logger.debug(
                        f"Current mod requires these mods to work: {dependencies}"
                    )
                    add_dependency_to_mod(all_mods[uuid], dependencies, all_mods)

            if all_mods[uuid].get("moddependenciesbyversion"):
                if all_mods[uuid]["moddependenciesbyversion"].get("v1.4"):
                    dependencies_by_ver = all_mods[uuid]["moddependenciesbyversion"][
                        "v1.4"
                    ].get("li")
                    if dependencies_by_ver:
                        logger.debug(
                            f"Current mod requires these mods by version to work: {dependencies_by_ver}"
                        )
                        add_dependency_to_mod(
                            all_mods[uuid], dependencies_by_ver, all_mods
                        )

            if all_mods[uuid].get("incompatiblewith"):
                incompatibilities = all_mods[uuid]["incompatiblewith"].get("li")
                if incompatibilities:
                    logger.debug(
                        f"Current mod is incompatible with these mods: {incompatibilities}"
                    )
                    add_incompatibility_to_mod(
                        all_mods[uuid], incompatibilities, all_mods
                    )

            if all_mods[uuid].get("incompatiblewithbyversion"):
                if all_mods[uuid]["incompatiblewithbyversion"].get("v1.4"):
                    incompatibilities_by_ver = all_mods[uuid][
                        "incompatiblewithbyversion"
                    ]["v1.4"].get("li")
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
            if all_mods[uuid].get("loadafter"):
                try:
                    load_these_before = all_mods[uuid]["loadafter"].get("li")
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
                            packageid_to_uuid,
                        )
                except:
                    mod_path = all_mods[uuid]["path"]
                    logger.warning(
                        f"About.xml syntax error. Unable to read <loadafter> tag from XML: {mod_path}"
                    )

            if all_mods[uuid].get("forceloadafter"):
                try:
                    force_load_these_before = all_mods[uuid]["forceloadafter"].get("li")
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
                            packageid_to_uuid,
                        )
                except:
                    mod_path = all_mods[uuid]["path"]
                    logger.warning(
                        f"About.xml syntax error. Unable to read <forceloadafter> tag from XML: {mod_path}"
                    )

            if all_mods[uuid].get("loadafterbyversion"):
                if all_mods[uuid]["loadafterbyversion"].get("v1.4"):
                    try:
                        load_these_before_by_ver = all_mods[uuid]["loadafterbyversion"][
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
                                packageid_to_uuid,
                            )
                    except:
                        mod_path = all_mods[uuid]["path"]
                        logger.warning(
                            f"About.xml syntax error. Unable to read <loadafterbyversion><v1.4> tag from XML: {mod_path}"
                        )

            # Current mod should be loaded BEFORE these mods
            # The current mod is a dependency for all these mods
            if all_mods[uuid].get("loadbefore"):
                try:
                    load_these_after = all_mods[uuid]["loadbefore"].get("li")
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
                            packageid_to_uuid,
                        )
                except:
                    mod_path = all_mods[uuid]["path"]
                    logger.warning(
                        f"About.xml syntax error. Unable to read <loadbefore> tag from XML: {mod_path}"
                    )

            if all_mods[uuid].get("forceloadbefore"):
                try:
                    force_load_these_after = all_mods[uuid]["forceloadbefore"].get("li")
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
                            packageid_to_uuid,
                        )
                except:
                    mod_path = all_mods[uuid]["path"]
                    logger.warning(
                        f"About.xml syntax error. Unable to read <forceloadbefore> tag from XML: {mod_path}"
                    )

            if all_mods[uuid].get("loadbeforebyversion"):
                if all_mods[uuid]["loadbeforebyversion"].get("v1.4"):
                    try:
                        load_these_after_by_ver = all_mods[uuid]["loadbeforebyversion"][
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
                                packageid_to_uuid,
                            )
                    except:
                        mod_path = all_mods[uuid]["path"]
                        logger.warning(
                            f"About.xml syntax error. Unable to read <loadbeforebyversion><v1.4> tag from XML: {mod_path}"
                        )

        logger.info("Finished adding dependencies through About.xml information")
        log_deps_order_info(all_mods)

        # Steam references dependencies based on PublishedFileID, not package ID
        info_from_steam_package_id_to_name = {}
        if steam_db:
            logger.info("Started compiling metadata from configured SteamDB")
            tracking_dict: dict[str, set[str]] = {}
            steam_id_to_package_id: dict[str, str] = {}
            for publishedfileid, mod_data in steam_db.items():
                db_packageid = mod_data.get("packageid")
                # If our DB has a packageid for this
                if db_packageid:
                    db_packageid = db_packageid.lower()  # Normalize packageid
                    steam_id_to_package_id[publishedfileid] = db_packageid
                    info_from_steam_package_id_to_name[db_packageid] = mod_data.get(
                        "name"
                    )
                    package_uuid = packageid_to_uuid.get(db_packageid)
                    if (
                        package_uuid
                        and all_mods[package_uuid].get("publishedfileid")
                        == publishedfileid
                    ):
                        dependencies = mod_data.get("dependencies")
                        if dependencies:
                            tracking_dict.setdefault(db_packageid, set()).update(
                                dependencies.keys()
                            )

            logger.debug(
                f"Tracking {len(steam_id_to_package_id)} SteamDB packageids for lookup"
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
                            all_mods[packageid_to_uuid[installed_mod_package_id]],
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
            logger.info("Started compiling metadata from configured Community Rules")
            for package_id in community_rules:
                # Note: requiring the package be in all_mods should be fine, as
                # if the mod doesn't exist all_mods, then either mod_data or dependency_id
                # will be None, and then we don't insert a dependency
                if package_id.lower() in packageid_to_uuid:
                    load_these_after = community_rules[package_id].get("loadBefore")
                    if load_these_after:
                        logger.debug(
                            f"Current mod should load before these mods: {load_these_after}"
                        )
                        # In Alphabetical, load_these_after is at least an empty dict
                        # Cannot call add_load_rule_to_mod outside of this for loop,
                        # as that expects a list
                        for load_this_after in load_these_after:
                            add_load_rule_to_mod(
                                all_mods[
                                    packageid_to_uuid[package_id.lower()]
                                ],  # Already checked above
                                load_this_after,  # Lower() done in call
                                "loadTheseAfter",
                                "loadTheseBefore",
                                all_mods,
                                packageid_to_uuid,
                            )

                    load_these_before = community_rules[package_id].get("loadAfter")
                    if load_these_before:
                        logger.debug(
                            f"Current mod should load after these mods: {load_these_before}"
                        )
                        # In Alphabetical, load_these_before is at least an empty dict
                        for load_this_before in load_these_before:
                            add_load_rule_to_mod(
                                all_mods[
                                    packageid_to_uuid[package_id.lower()]
                                ],  # Already checked above
                                load_this_before,  # lower() done in call
                                "loadTheseBefore",
                                "loadTheseAfter",
                                all_mods,
                                packageid_to_uuid,
                            )
                    load_this_bottom = community_rules[package_id].get("loadBottom")
                    if load_this_bottom:
                        logger.debug(
                            f'Current mod should load at the bottom of a mods list, and will be considered a "tier 3" mod'
                        )
                        all_mods[packageid_to_uuid[package_id.lower()]][
                            "loadBottom"
                        ] = True
            logger.info("Finished adding dependencies from Community Rules")
            log_deps_order_info(all_mods)
        else:
            logger.info(
                "No Community Rules database supplied from external metadata. skipping."
            )
        # Add load order rules to installed mods based on rules from user rules
        if user_rules:
            logger.info("Started compiling metadata from User Rules")
            for package_id in user_rules:
                # Note: requiring the package be in all_mods should be fine, as
                # if the mod doesn't exist all_mods, then either mod_data or dependency_id
                # will be None, and then we don't insert a dependency
                if package_id.lower() in packageid_to_uuid:
                    load_these_after = user_rules[package_id].get("loadBefore")
                    if load_these_after:
                        logger.debug(
                            f"Current mod should load before these mods: {load_these_after}"
                        )
                        # In Alphabetical, load_these_after is at least an empty dict
                        # Cannot call add_load_rule_to_mod outside of this for loop,
                        # as that expects a list
                        for load_this_after in load_these_after:
                            add_load_rule_to_mod(
                                all_mods[
                                    packageid_to_uuid[package_id.lower()]
                                ],  # Already checked above
                                load_this_after,  # lower() done in call
                                "loadTheseAfter",
                                "loadTheseBefore",
                                all_mods,
                                packageid_to_uuid,
                            )

                    load_these_before = user_rules[package_id].get("loadAfter")
                    if load_these_before:
                        logger.debug(
                            f"Current mod should load after these mods: {load_these_before}"
                        )
                        # In Alphabetical, load_these_before is at least an empty dict
                        for load_this_before in load_these_before:
                            add_load_rule_to_mod(
                                all_mods[
                                    packageid_to_uuid[package_id.lower()]
                                ],  # Already checked above
                                load_this_before,  # lower() done in call
                                "loadTheseBefore",
                                "loadTheseAfter",
                                all_mods,
                                packageid_to_uuid,
                            )
                    load_this_bottom = user_rules[package_id].get("loadBottom")
                    if load_this_bottom:
                        logger.debug(
                            f'Current mod should load at the bottom of a mods list, and will be considered a "tier 3" mod'
                        )
                        all_mods[packageid_to_uuid[package_id.lower()]][
                            "loadBottom"
                        ] = True
            logger.info("Finished adding dependencies from User Rules")
            log_deps_order_info(all_mods)
        else:
            logger.info(
                "No User Rules database supplied from external metadata. skipping."
            )
        logger.info("Returning all mods now")
        return all_mods, info_from_steam_package_id_to_name


class ModParser(QRunnable):
    def __init__(
        self,
        directory: str,
        intent: str,
        results: Dict[str, Any],
        steam_db: Dict[str, Any],
    ):
        super(ModParser, self).__init__()
        # This is very spammy - only enable if you are really wanting to debug this class.
        # logger.debug("Initializing ModParser")
        self.directory = directory
        self.intent = intent
        self.results = results
        self.steam_db = steam_db

    def __parse_mod_data(
        self, directory: str, intent: str, steam_db: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.debug(f"Parsing directory: {directory}")
        mods = {}
        directory_name = os.path.split(directory)[1]
        # Use this to trigger invalid clause intentionally, i.e. when handling exceptions
        data_malformed = None
        # Any pfid parsed will be stored here locally
        pfid = None
        # Generate a UUID for the directory we are populating
        uuid = str(uuid4())
        # Look for a case-insensitive "About" folder
        invalid_about_folder_path_found = True
        about_folder_name = "About"
        for temp_file in os.scandir(directory):
            if (
                temp_file.name.lower() == about_folder_name.lower()
                and temp_file.is_dir()
            ):
                about_folder_name = temp_file.name
                invalid_about_folder_path_found = False
                break
        # Look for a case-insensitive "About.xml" file
        invalid_about_file_path_found = True
        if not invalid_about_folder_path_found:
            about_file_name = "About.xml"
            for temp_file in os.scandir(
                str(Path(os.path.join(directory, about_folder_name)).resolve())
            ):
                if (
                    temp_file.name.lower() == about_file_name.lower()
                    and temp_file.is_file()
                ):
                    about_file_name = temp_file.name
                    invalid_about_file_path_found = False
                    break
        # Look for .rsc scenario files to load metadata from if we didn't find About.xml
        if invalid_about_file_path_found:
            logger.debug(
                f"No variations of /About/About.xml could be found! Checking for RimWorld scenario to parse (.rsc file)"
            )
            scenario_rsc_found = None
            for temp_file in os.scandir(directory):
                if temp_file.name.lower().endswith(".rsc") and not temp_file.is_dir():
                    scenario_rsc_file = temp_file.name
                    scenario_rsc_found = True
                    break
        # If a mod's folder name is a valid PublishedFileId in SteamDB
        if steam_db and directory_name in steam_db.keys():
            pfid = directory_name
            logger.debug(
                f"Found valid PublishedFileId for dir {directory_name} in SteamDB: {pfid}"
            )
        # Look for a case-insensitive "PublishedFileId.txt" file if we didn't find a pfid
        elif not pfid and not invalid_about_folder_path_found:
            pfid_file_name = "PublishedFileId.txt"
            logger.debug(
                f"Unable to find PublishedFileId for dir {directory_name} in Steam DB. Trying to find a {pfid_file_name} to parse"
            )
            for temp_file in os.scandir(
                str(Path(os.path.join(directory, about_folder_name)).resolve())
            ):
                if (
                    temp_file.name.lower() == pfid_file_name.lower()
                    and temp_file.is_file()
                ):
                    pfid_file_name = temp_file.name
                    pfid_path = str(
                        Path(
                            os.path.join(directory, about_folder_name, pfid_file_name)
                        ).resolve()
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
                    break
                else:
                    logger.debug(
                        f"No variations of /About/PublishedFileId.txt could be found: {directory}"
                    )
        # If we were able to find an About.xml, populate mod data...
        if not invalid_about_file_path_found:
            mod_data_path = str(
                Path(
                    os.path.join(directory, about_folder_name, about_file_name)
                ).resolve()
            )
            logger.debug(f"Found mod metadata at: {mod_data_path}")
            mod_data = {}
            try:
                # Try to parse .xml
                mod_data = xml_path_to_json(mod_data_path)
            except:
                # If there was an issue parsing the .xml, track and exit
                logger.error(
                    f"Unable to parse {about_file_name} with the exception: {traceback.format_exc()}"
                )
                data_malformed = True
            else:
                # Case-insensitive `ModMetaData` key.
                logger.debug("Normalizing top level XML keys")
                mod_data = {k.lower(): v for k, v in mod_data.items()}
                logger.debug("Editing XML content")
                if mod_data.get("modmetadata"):
                    # Initialize our dict from the formatted About.xml metadata
                    mod_metadata = mod_data["modmetadata"]
                    # Case-insensitive metadata keys
                    logger.debug("Normalizing XML metadata keys")
                    mod_metadata = {k.lower(): v for k, v in mod_metadata.items()}
                    if (  # If we don't have a <name>
                        not mod_metadata.get("name")
                        and steam_db  # ... try to find it in Steam DB
                        and steam_db.get(pfid, {}).get("steamName")
                    ):
                        mod_metadata.setdefault("name", steam_db[pfid]["steamName"])
                        # This is so that DB builder shows we do not have local metadata
                        mod_metadata.setdefault("DB_BUILDER_NO_NAME", True)
                    else:
                        mod_metadata.setdefault("name", "Missing XML: <name>")
                    # Rename author tag appropriately to normalize it in usage and lookups
                    mod_metadata = {
                        ("authors" if key.lower() == "author" else key): value
                        for key, value in mod_metadata.items()
                    }
                    # Make sure <supportedversions> or <targetversion> is correct format
                    if mod_metadata.get("supportedversions") and not isinstance(
                        mod_metadata.get("supportedversions"), dict
                    ):
                        logger.error(
                            f"About.xml syntax error. Unable to read <supportedversions> tag from XML: {mod_data_path}"
                        )
                        mod_metadata.pop("supportedversions", None)
                    elif mod_data.get("supportedversions", {}).get("li"):
                        if isinstance(mod_data["supportedversions"]["li"], str):
                            mod_data["supportedversions"]["li"] = (
                                ".".join(
                                    mod_data["supportedversions"]["li"].split(".")[:2]
                                )
                                if mod_data["supportedversions"]["li"].count(".") > 1
                                else mod_data["supportedversions"]["li"]
                            )
                        elif isinstance(mod_data["supportedversions"]["li"], list):
                            for mod_data["supportedversions"]["li"] in mod_data[
                                "supportedversions"
                            ]["li"]:
                                mod_data["supportedversions"]["li"] = (
                                    ".".join(
                                        mod_data["supportedversions"]["li"].split(".")[
                                            :2
                                        ]
                                    )
                                    if mod_data["supportedversions"]["li"].count(".")
                                    > 1
                                    and isinstance(
                                        mod_data["supportedversions"]["li"], str
                                    )
                                    else mod_data["supportedversions"]["li"]
                                )
                    if mod_metadata.get("targetversion"):
                        mod_metadata["targetversion"] = mod_metadata["targetversion"]
                        mod_metadata["targetversion"] = (
                            ".".join(mod_metadata["targetversion"].split(".")[:2])
                            if mod_metadata["targetversion"].count(".") > 1
                            and isinstance(mod_metadata["targetversion"], str)
                            else mod_metadata["targetversion"]
                        )
                    # If we parsed a packageid from modmetadata...
                    if mod_metadata.get("packageid"):
                        # ...check type of packageid, use first packageid parsed
                        if isinstance(mod_metadata["packageid"], list):
                            mod_metadata["packageid"] = mod_metadata["packageid"][
                                0
                            ].lower()
                        # Normalize package ID in metadata
                        mod_metadata["packageid"] = mod_metadata["packageid"].lower()
                    else:  # ...otherwise, we don't have one from About.xml, and we can check Steam DB...
                        # ...this can be needed if a mod depends on a RW generated packageid via built-in hashing mechanism.
                        if steam_db and steam_db.get(pfid, {}).get("packageId"):
                            mod_metadata["packageid"] = steam_db[pfid][
                                "packageId"
                            ].lower()
                        else:
                            mod_metadata.setdefault("packageid", "missing.packageid")
                    # Track pfid if we parsed one earlier
                    if pfid:  # Make some assumptions if we have a pfid
                        mod_metadata["publishedfileid"] = pfid
                        mod_metadata[
                            "steam_uri"
                        ] = f"steam://url/CommunityFilePage/{pfid}"
                        mod_metadata[
                            "steam_url"
                        ] = f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"
                    # If a mod contains C# assemblies, we want to tag the mod
                    assemblies_path = str(
                        Path(os.path.join(directory, "Assemblies")).resolve()
                    )
                    if os.path.exists(assemblies_path):
                        if any(
                            filename.endswith((".dll", ".DLL"))
                            for filename in os.listdir(assemblies_path)
                        ):
                            mod_metadata["csharp"] = True
                    else:
                        subfolder_paths = [
                            str(Path(os.path.join(directory, folder)).resolve())
                            for folder in os.listdir(directory)
                            if os.path.isdir(
                                str(Path(os.path.join(directory, folder)).resolve())
                            )
                        ]
                        for subfolder_path in subfolder_paths:
                            assemblies_path = str(
                                Path(
                                    os.path.join(subfolder_path, "Assemblies")
                                ).resolve()
                            )
                            if os.path.exists(assemblies_path):
                                if any(
                                    filename.endswith((".dll", ".DLL"))
                                    for filename in os.listdir(assemblies_path)
                                ):
                                    mod_metadata["csharp"] = True
                    # data_source will be used with setIcon later
                    mod_metadata["data_source"] = intent
                    mod_metadata["folder"] = directory_name
                    # This is overwritten if acf data is parsed for Steam/SteamCMD mods
                    mod_metadata["internal_time_touched"] = int(
                        os.path.getmtime(directory)
                    )
                    mod_metadata["path"] = directory
                    # Track source & uuid in case metadata becomes detached
                    mod_metadata["uuid"] = uuid
                    logger.debug(
                        f"Finished editing XML mod content, adding final content to larger list: {mod_metadata}"
                    )
                    mods[uuid] = mod_metadata
                else:
                    logger.error(
                        f"Key <modmetadata> does not exist in this data: {mod_data}"
                    )
                    data_malformed = True
        # ...or, if we didn't find an About.xml, but we have a RimWorld scenario .rsc to parse...
        elif invalid_about_file_path_found and scenario_rsc_found:
            scenario_data_path = str(
                Path(os.path.join(directory, scenario_rsc_file)).resolve()
            )
            logger.debug(f"Found scenario metadata at: {scenario_data_path}")
            scenario_data = {}
            try:
                # Try to parse .rsc
                scenario_data = xml_path_to_json(scenario_data_path)
            except:
                # If there was an issue parsing the .rsc, track and exit
                logger.error(
                    f"Unable to parse {scenario_rsc_file} with the exception: {traceback.format_exc()}"
                )
                data_malformed = True
            else:
                # Case-insensitive `savedscenario` key.
                logger.debug("Normalizing top level XML keys")
                scenario_data = {k.lower(): v for k, v in scenario_data.items()}
                logger.debug("Editing XML content")
                if scenario_data.get("savedscenario", {}).get(
                    "scenario"
                ):  # If our .rsc metadata has a packageid key
                    # Initialize our dict from the formatted .rsc metadata
                    scenario_metadata = scenario_data["savedscenario"]["scenario"]
                    # Case-insensitive keys.
                    logger.debug("Normalizing XML metadata keys")
                    scenario_metadata = {
                        k.lower(): v for k, v in scenario_metadata.items()
                    }
                    scenario_metadata.setdefault("packageid", "scenario.rsc")
                    scenario_metadata["scenario"] = True
                    scenario_metadata.pop("playerfaction", None)
                    scenario_metadata.pop("parts", None)
                    if (
                        scenario_data["savedscenario"]
                        .get("meta", {})
                        .get("gameVersion")
                    ):
                        scenario_metadata["supportedversions"] = {
                            "li": scenario_data["savedscenario"]["meta"]["gameVersion"]
                        }
                    else:
                        logger.warning(
                            f"Unable to parse [gameversion] from this scenario [meta] tag: {scenario_data}"
                        )
                    # Track pfid if we parsed one earlier and don't already have one from metadata
                    if pfid and not scenario_data.get("publishedfileid"):
                        scenario_data["publishedfileid"] = pfid
                    if scenario_metadata.get(
                        "publishedfileid"
                    ):  # Make some assumptions if we have a pfid
                        scenario_metadata[
                            "steam_uri"
                        ] = f"steam://url/CommunityFilePage/{pfid}"
                        scenario_metadata[
                            "steam_url"
                        ] = f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"
                    # data_source will be used with setIcon later
                    scenario_metadata["data_source"] = intent
                    scenario_metadata["folder"] = directory_name
                    scenario_metadata["path"] = directory
                    # Track source & uuid in case metadata becomes detached
                    scenario_metadata["uuid"] = uuid
                    logger.debug(
                        f"Finished editing XML scenario content, adding final content to larger list: {scenario_metadata}"
                    )
                    mods[uuid] = scenario_metadata
                else:
                    logger.error(
                        f"Key <savedscenario><scenario> does not exist in this data: {scenario_metadata}"
                    )
                    data_malformed = True
        if (
            invalid_about_file_path_found and not scenario_rsc_found
        ) or data_malformed:  # ...finally, if we don't have any metadata parsed, populate invalid mod entry for visibility
            logger.debug(f"Invalid dir. Populating invalid mod for path: {directory}")
            mods[uuid] = {
                "invalid": True,
                "name": "Invalid item",
                "packageid": "invalid.item",
                "authors": "Not found",
                "description": (
                    "This mod is considered invalid by RimSort (and the RimWorld game)."
                    + "\n\nThis mod does NOT contain an ./About/About.xml and is likely leftover from previous usage."
                    + "\n\nThis can happen sometimes with Steam mods if there are leftover .dds textures or unexpected data."
                ),
                "data_source": intent,
                "folder": directory_name,
                "path": directory,
                "uuid": uuid,
            }
            if pfid:
                mods[uuid].update({"publishedfileid": pfid})
        # Additional checks for local mods
        if intent == "local":
            metadata = mods[uuid]
            # Check for git repository inside local mods, tag appropriately
            if os.path.exists(str(Path(os.path.join(directory, ".git")).resolve())):
                metadata["git_repo"] = True
            # Check for local mods that are SteamCMD mods, tag appropriately
            if metadata.get("folder") == metadata.get("publishedfileid"):
                metadata["steamcmd"] = True
        logger.debug(f"Finished parsing directory")
        return mods

    def run(self):
        try:
            mod_metadata = self.__parse_mod_data(
                self.directory, self.intent, self.steam_db
            )
            self.results.update(mod_metadata)
        except Exception as e:
            error_message = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_message)


# Mod helper functions


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
        # Create a new key with empty set as value by default
        mod_data.setdefault("dependencies", set())

        # If the value is a single dict (for moddependencies)
        if isinstance(dependency_or_dependency_ids, dict):
            if dependency_or_dependency_ids.get("packageId") and not isinstance(
                dependency_or_dependency_ids["packageId"], list
            ):
                # if dependency_id in all_mods:
                # ^ dependencies are required regardless of whether they are in all_mods
                mod_data["dependencies"].add(
                    dependency_or_dependency_ids["packageId"].lower()
                )
            else:
                logger.error(
                    f"Dependency dict does not contain packageid or correct format: [{dependency_or_dependency_ids}]"
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


def add_dependency_to_mod_from_steamdb(
    mod_data: Dict[str, Any], dependency_id: Any, all_mods: Dict[str, Any]
) -> None:
    mod_name = mod_data.get("name")
    # Create a new key with empty set as value by default
    mod_data.setdefault("dependencies", set())

    # If the value is a single str (for steamDB)
    if isinstance(dependency_id, str):
        mod_data["dependencies"].add(dependency_id)
    else:
        logger.error(f"Dependencies is not a single str: [{dependency_id}]")
    logger.debug(f"Added dependency to [{mod_name}] from SteamDB: [{dependency_id}]")


def get_num_dependencies(all_mods: Dict[str, Any], key_name: str) -> int:
    """Debug func for getting total number of dependencies"""
    counter = 0
    for mod_data in all_mods.values():
        if mod_data.get(key_name):
            counter = counter + len(mod_data[key_name])
    return counter


def add_incompatibility_to_mod(
    mod_data: Dict[str, Any],
    dependency_or_dependency_ids: Any,
    all_mods: Dict[str, Any],
) -> None:
    """
    Incompatibility data is collected only if that incompatibility is in `all_mods`.
    There's no need to surface incompatibilities if they aren't even downloaded.
    """
    logger.debug(
        f"Adding incompatibilities for packages [{dependency_or_dependency_ids}] to mod data: {mod_data} (and reverse direction too)"
    )
    if mod_data:
        # Create a new key with empty set as value by default
        mod_data.setdefault("incompatibilities", set())

        all_package_ids = set(all_mods[uuid]["packageid"] for uuid in all_mods)

        # If the value is a single string...
        if isinstance(dependency_or_dependency_ids, str):
            dependency_id = dependency_or_dependency_ids.lower()
            if dependency_id in all_package_ids:
                mod_data["incompatibilities"].add(dependency_id)

        # If the value is a LIST of strings
        elif isinstance(dependency_or_dependency_ids, list):
            if isinstance(dependency_or_dependency_ids[0], str):
                for dependency in dependency_or_dependency_ids:
                    dependency_id = dependency.lower()
                    if dependency_id in all_package_ids:
                        mod_data["incompatibilities"].add(dependency_id)
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
    packageid_to_uuid: Dict[str, Any],
) -> None:
    """
    Load order data is collected only if the mod referenced is in `all_mods`, as
    mods that are not installed do not need to be ordered.

    Rules that do not exist in all_mods are not added.

    :param mod_data: mod data dict to add dependencies to
    :param dependency_or_dependency_ids: either string or list of strings (or sometimes None)
    :param explicit_key: indicates if the rule is added because it was explicitly defined
    somewhere, e.g. About.xml, or if it was inferred, e.g. If A loads after B,
    B should load before A
    :param indirect_key:
    :param all_mods: dict of all mods to verify keys against
    :param packageid_to_uuid: a helper dict to reduce work
    """
    if not mod_data:
        return

    # Pre-processing: Normalize dependency_or_dependency_ids to a list of strings
    dependencies = []
    if isinstance(dependency_or_dependency_ids, str):
        dependencies.append(dependency_or_dependency_ids.lower())
    elif isinstance(dependency_or_dependency_ids, dict):
        if "#text" in dependency_or_dependency_ids:
            dependencies.append(dependency_or_dependency_ids["#text"].lower())
        else:
            logger.error(
                f"Load rule with MayRequire does not contain expected #text key: {dependency_or_dependency_ids}"
            )
    elif isinstance(dependency_or_dependency_ids, list):
        for dep in dependency_or_dependency_ids:
            if isinstance(dep, str):
                dependencies.append(dep.lower())
            elif isinstance(dep, dict) and "#text" in dep:
                dependencies.append(dep["#text"].lower())
            else:
                logger.error(f"Load rule is not an expected str or dict: {dep}")
    else:
        logger.error(
            f"Load order rules is not a single string/dict or a list of strigs/dicts: [{dependency_or_dependency_ids}]"
        )
        return

    mod_data.setdefault(explicit_key, set())
    for dep in dependencies:
        if dep in packageid_to_uuid:
            uuid = packageid_to_uuid[dep]
            mod_data[explicit_key].add((dep, True))
            all_mods[uuid].setdefault(indirect_key, set()).add(
                (mod_data["packageid"], False)
            )


def get_active_inactive_mods(
    config_path: str, all_mods: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], list]:
    """
    Given a path to the ModsConfig.xml folder and a complete list of
    mods (including base game and DLC) and their dependencies,
    return a list of mods for the active list widget and a list of
    mods for the inactive list widget.

    :param config_path: path to ModsConfig.xml folder
    :param all_mods: dict of all mods
    :return: a Tuple which contains the active mods dict, inactive mods dict,
    duplicate mods dict, and missing mods list
    """
    active_mods: dict[str, Any] = {}
    inactive_mods: dict[str, Any] = {}
    duplicate_mods = {}
    duplicates_processed = []
    missing_mods = []
    logger.debug("Started generating active and inactive mods")
    # Calculate duplicate mods (SCHEMA: {str packageid: list[str duplicate uuids]})
    for mod_uuid, mod_data in all_mods.items():
        # Using setdefault() to initialize the dictionary and then assigning the value
        duplicate_mods.setdefault(mod_data["packageid"], []).append(mod_uuid)
    # Filter out non-duplicate mods
    duplicate_mods = {k: v for k, v in duplicate_mods.items() if len(v) > 1}
    # Calculate mod lists
    logger.info(f"Retrieving active mods from RimWorld ModsConfig.xml")
    mod_data = xml_path_to_json(config_path)
    populated_mods = []
    to_populate = []
    if not validate_mods_config_format(mod_data):
        logger.error(
            f"Unable to get active mods from config with read data: {mod_data}"
        )
        return active_mods, inactive_mods, duplicate_mods, missing_mods
    # Parse the ModsConfig.xml data
    for package_id in mod_data["ModsConfigData"]["activeMods"][
        "li"
    ]:  # Go through active mods, handle packageids
        package_id_normalized = package_id.lower()
        package_id_steam_suffix = "_steam"
        package_id_normalized_stripped = package_id_normalized.replace(
            package_id_steam_suffix, ""
        )
        # bool to determine whether or not _steam suffix present in ModsConfig entry
        is_steam = package_id_steam_suffix in package_id_normalized
        # Determine target_id based on whether suffix exists
        target_id = (
            package_id_normalized_stripped
            if is_steam  # Use suffix if _steam in our ModsConfig entry
            else package_id_normalized
        )
        # Append our packageid to list, used to calculate missing mods later
        to_populate.append(target_id)
        sources_order = (
            # Prioritize workshop duplicate if _steam suffix used...
            ["workshop", "local"]
            if is_steam
            # ... otherwise, we use standard data source priority if suffix not used
            else ["expansion", "local", "workshop"]
        )
        # Loop through all mods
        for uuid, metadata in all_mods.items():
            metadata_package_id = metadata["packageid"]
            metadata_path = metadata["path"]
            if (
                metadata_package_id
                in [  # If we have a match with or without _steam present
                    package_id_normalized,
                    package_id_normalized_stripped,
                ]
            ):
                # Add non-duplicates to active mods
                if target_id not in duplicate_mods.keys():
                    populated_mods.append(target_id)
                    active_mods[uuid] = metadata
                else:  # Otherwise, duplicate needs calculated
                    if (
                        target_id in duplicates_processed
                    ):  # Skip duplicates that have already been processed
                        continue
                    logger.info(
                        f"Found duplicate mod present in active mods list: {target_id}"
                    )
                    # Loop through sorted paths and determine which duplicate to used based on priority
                    for source in sources_order:
                        logger.debug(f"Checking for duplicate with source: {source}")
                        # Sort duplicate mod paths by source priority
                        paths_to_uuid = {}
                        for duplicate_uuid in duplicate_mods[target_id]:
                            if source in all_mods[duplicate_uuid]["data_source"]:
                                paths_to_uuid[
                                    all_mods[duplicate_uuid]["path"]
                                ] = duplicate_uuid
                        # Sort duplicate mod paths from current source priority using natsort
                        source_paths_sorted = natsorted(paths_to_uuid.keys())
                        if source_paths_sorted:  # If we have paths returned
                            # If we are here, we've found our calculated duplicate, log and use this mod
                            duplicate_mod_metadata = all_mods[
                                paths_to_uuid[source_paths_sorted[0]]
                            ]
                            logger.debug(
                                f"Using duplicate {source} mod for {target_id}: {duplicate_mod_metadata['path']}"
                            )
                            populated_mods.append(target_id)
                            duplicates_processed.append(target_id)
                            active_mods[
                                duplicate_mod_metadata["uuid"]
                            ] = duplicate_mod_metadata
                            break
                        else:  # Skip this source priority if no paths
                            logger.debug(f"No paths returned for {source}")
                            continue
    # Calculate missing mods from the difference
    missing_mods = list(set(to_populate) - set(populated_mods))
    logger.debug(f"Generated active mods dict with {len(active_mods)} mods")
    # Get the inactive mods by subtracting active mods from workshop + expansions
    inactive_mods = get_inactive_mods(all_mods, active_mods)
    logger.info(f"# active mods: {len(active_mods)}")
    logger.info(f"# inactive mods: {len(inactive_mods)}")
    logger.info(f"# duplicate mods: {len(duplicate_mods)}")
    logger.info(f"# missing mods: {len(missing_mods)}")
    return active_mods, inactive_mods, duplicate_mods, missing_mods


def get_inactive_mods(
    all_mods: Dict[str, Any],
    active_mods: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate a list of inactive mods by cross-referencing the list of
    installed workshop mods with the active mods and known expansions.

    Move the first local instance of any duplicate found alphabetically
    ascending by filename to the active mods list; and the rest of the dupes
    to the inactive mods list. TODO this is not accurate

    :param all_mods: dict of workshop mods and expansions
    :param active_mods: dict of active mods
    :param duplicate_mods: dict keyed with packageids to list of dupe uuids
    :return: a dict for inactive mods
    """
    logger.info("Generating inactive mod list")
    inactive_mods = all_mods.copy()

    # Remove active_mods uuids from inactive_mods in a more efficient way using dict comprehension
    inactive_mods = {
        mod_uuid: mod_data
        for mod_uuid, mod_data in inactive_mods.items()
        if mod_uuid not in active_mods
    }

    logger.info("Finished generating inactive mods list")
    return inactive_mods


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


# DB Builder


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
        GameConfiguration.instance().database_expiry = database_expiry
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
                    life=GameConfiguration.instance().database_expiry,
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
                            life=GameConfiguration.instance().database_expiry,
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
                **{
                    v["appid"]: {
                        "appid": True,
                        "url": f'https://store.steampowered.com/app/{v["appid"]}',
                        "packageid": v.get("packageid"),
                        "name": v.get("name"),
                        "authors": ", ".join(v.get("authors").get("li"))
                        if v.get("authors")
                        and isinstance(v.get("authors"), dict)
                        and v.get("authors").get("li")
                        else v.get("authors", "Missing XML: <author(s)>"),
                    }
                    for v in self.mods.values()
                    if v.get("appid")
                },
                **{
                    v["publishedfileid"]: {
                        "url": f'https://steamcommunity.com/sharedfiles/filedetails/?id={v["publishedfileid"]}',
                        "packageId": v.get("packageid"),
                        "name": v.get("name")
                        if not v.get("DB_BUILDER_NO_NAME")
                        else "Missing XML: <name>",
                        "authors": ", ".join(v.get("authors").get("li"))
                        if v.get("authors")
                        and isinstance(v.get("authors"), dict)
                        and v.get("authors").get("li")
                        else v.get("authors", "Missing XML: <author(s)>"),
                        "gameVersions": v.get("supportedversions").get("li")
                        if isinstance(v.get("supportedversions", {}).get("li"), list)
                        else [
                            v.get("supportedversions", {}).get(
                                "li",
                            )
                            if v.get("supportedversions")
                            else v.get(
                                "targetversion",
                                "Missing XML: <supportedversions> or <targetversion>",
                            )
                        ],
                    }
                    for v in self.mods.values()
                    if v.get("publishedfileid")
                },
            },
        }
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
                        "packageid": metadata.get("packageid"),
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
            f"\nPopulated {total} items queried from Steam Workshop into initial database for AppId {self.appid}"
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
                    prune_exceptions=DB_BUILDER_PRUNE_EXCEPTIONS,
                    recurse_exceptions=DB_BUILDER_RECURSE_EXCEPTIONS,
                )
                with open(self.output_database_path, "w", encoding="utf-8") as output:
                    json.dump(db_to_update, output, indent=4)
            else:
                self.db_builder_message_output_signal.emit(
                    "Unable to load database from specified path! Does the file exist...?"
                )
                appended_path = str(
                    Path(
                        os.path.join(
                            os.path.split(self.output_database_path)[0],
                            "NEW_" + str(os.path.split(self.output_database_path[1])),
                        )
                    ).resolve()
                )
                self.db_builder_message_output_signal.emit(
                    f"\nCaching DynamicQuery result:\n\n{appended_path}"
                )
                with open(appended_path, "w", encoding="utf-8") as output:
                    json.dump(database, output, indent=4)
        else:  # Dump new db to specified path, effectively "overwriting" the db with fresh data
            self.db_builder_message_output_signal.emit(
                f"\nCaching DynamicQuery result:\n{self.output_database_path}"
            )
            with open(self.output_database_path, "w", encoding="utf-8") as output:
                json.dump(database, output, indent=4)


# Misc helper functions


def check_if_pfids_blacklisted(publishedfileids: list, steamdb: Dict[str, Any]) -> list:
    # Warn attempt of blacklisted mods
    blacklisted_mods = {}
    for publishedfileid in publishedfileids:
        if steamdb.get(publishedfileid, {}).get("blacklist"):
            blacklisted_mods[publishedfileid] = {
                "name": steamdb[publishedfileid]["steamName"],
                "comment": steamdb[publishedfileid]["blacklist"]["comment"],
            }
        elif steamdb.get(str(publishedfileid), {}).get("blacklist"):
            blacklisted_mods[publishedfileid] = {
                "name": steamdb[str(publishedfileid)]["steamName"],
                "comment": steamdb[str(publishedfileid)]["blacklist"]["comment"],
            }
    # Generate report if we have blacklisted mods found
    if blacklisted_mods:
        blacklisted_mods_report = ""
        for publishedfileid in blacklisted_mods:
            blacklisted_mods_report += (
                f'{blacklisted_mods[publishedfileid]["name"]} ({publishedfileid})\n'
            )
            blacklisted_mods_report += f'Reason for blacklisting: {blacklisted_mods[publishedfileid]["comment"]}'
        answer = show_dialogue_conditional(
            "Blacklisted mods found",
            "Some mods are blacklisted in your SteamDB",
            "Are you sure you want to download these mods? These mods are known mods that are recommended to be avoided.",
            blacklisted_mods_report,
        )
        if answer != "&Yes":
            publishedfileids.remove(publishedfileid)
            logger.debug(
                f"Skipping download of unpublished Workshop mod: {publishedfileid}"
            )
    return publishedfileids


def import_steamcmd_acf_data(
    rimsort_storage_path: str, steamcmd_appworkshop_acf_path: str
) -> None:
    logger.info(f"SteamCMD acf data path to update: {steamcmd_appworkshop_acf_path}")
    if os.path.exists(steamcmd_appworkshop_acf_path):
        logger.debug(f"Reading info...")
        steamcmd_appworkshop_acf = acf_to_dict(steamcmd_appworkshop_acf_path)
        logger.debug("Retrieved SteamCMD data to update...")
    else:
        logger.warning("Specified SteamCMD acf file not found! Nothing was done...")
        return
    logger.info("Opening file dialog to specify acf file to import")
    acf_to_import_path = show_dialogue_file(
        mode="open",
        caption="Input appworkshop_294100.acf from another SteamCMD prefix",
        _dir=rimsort_storage_path,
        _filter="ACF (*.acf)",
    )
    logger.info(f"SteamCMD acf data path to import: {acf_to_import_path}")
    if acf_to_import_path and os.path.exists(acf_to_import_path):
        logger.debug(f"Reading info...")
        acf_to_import = acf_to_dict(acf_to_import_path)
        logger.debug("Retrieved SteamCMD data to import...")
    else:
        logger.warning("Specified SteamCMD acf file not found! Nothing was done...")
        return
    # Output
    items_installed_before = len(
        steamcmd_appworkshop_acf["AppWorkshop"]["WorkshopItemsInstalled"].keys()
    )
    logger.debug(f"WorkshopItemsInstalled beforehand: {items_installed_before}")
    item_details_before = len(
        steamcmd_appworkshop_acf["AppWorkshop"]["WorkshopItemDetails"].keys()
    )
    logger.debug(f"WorkshopItemDetails beforehand: {item_details_before}")
    recursively_update_dict(
        steamcmd_appworkshop_acf["AppWorkshop"]["WorkshopItemsInstalled"],
        acf_to_import["AppWorkshop"]["WorkshopItemsInstalled"],
    )
    recursively_update_dict(
        steamcmd_appworkshop_acf["AppWorkshop"]["WorkshopItemDetails"],
        acf_to_import["AppWorkshop"]["WorkshopItemDetails"],
    )
    items_installed_after = len(
        steamcmd_appworkshop_acf["AppWorkshop"]["WorkshopItemsInstalled"].keys()
    )
    logger.debug(f"WorkshopItemsInstalled after: {items_installed_after}")
    item_details_after = len(
        steamcmd_appworkshop_acf["AppWorkshop"]["WorkshopItemDetails"].keys()
    )
    logger.debug(f"WorkshopItemDetails after: {item_details_after}")
    logger.info("Successfully imported data!")
    logger.info(f"Writing updated data back to path: {steamcmd_appworkshop_acf_path}")
    dict_to_acf(data=steamcmd_appworkshop_acf, path=steamcmd_appworkshop_acf_path)


def query_workshop_update_data(mods: Dict[str, Any]) -> Optional[str]:
    """
    Query Steam WebAPI for update data, for any workshop mods that have a 'publishedfileid'
    attribute contained in their mod_data, and from there, populate mod_json_data with it.

    Append mod update data found for Steam Workshop mods to internal metadata

    :param mods: A Dict equivalent to 'all_mods' or mod_list.get_list_items_by_dict() in
    which contains possible Steam mods to lookup metadata for
    """
    logger.info("Querying Steam WebAPI for SteamCMD/Steam mod update metadata")

    workshop_mods_pfid_to_uuid = {
        metadata["publishedfileid"]: uuid
        for uuid, metadata in mods.items()
        if (metadata.get("steamcmd") or metadata.get("data_source") == "workshop")
        and metadata.get("publishedfileid")
    }

    workshop_mods_query_updates = ISteamRemoteStorage_GetPublishedFileDetails(
        list(workshop_mods_pfid_to_uuid.keys())
    )
    if workshop_mods_query_updates and len(workshop_mods_query_updates) > 0:
        for workshop_mod_metadata in workshop_mods_query_updates:
            uuid = workshop_mods_pfid_to_uuid[workshop_mod_metadata["publishedfileid"]]
            if workshop_mod_metadata.get("time_created"):
                mods[uuid]["external_time_created"] = workshop_mod_metadata[
                    "time_created"
                ]
            if workshop_mod_metadata.get("time_updated"):
                mods[uuid]["external_time_updated"] = workshop_mod_metadata[
                    "time_updated"
                ]
    else:
        return "failed"


def recursively_update_dict(
    a_dict, b_dict, prune_exceptions=None, purge_keys=None, recurse_exceptions=None
):
    # Check for keys in recurse_exceptions in a_dict that are not in b_dict and remove them
    for key in set(a_dict.keys()) - set(b_dict.keys()):
        if recurse_exceptions and key in recurse_exceptions:
            del a_dict[key]
    # Recursively update A with B, excluding recurse exceptions (list of keys to just overwrite)
    for key, value in b_dict.items():
        if recurse_exceptions and key in recurse_exceptions:
            # If the key is an exception, update its value directly from B
            a_dict[key] = value
        elif (
            key in a_dict and isinstance(a_dict[key], dict) and isinstance(value, dict)
        ):
            # If the key exists in both dictionaries and the values are dictionaries,
            # recursively update the nested dictionaries except for the recurse exceptions list
            recursively_update_dict(
                a_dict[key],
                value,
                prune_exceptions=prune_exceptions,
                purge_keys=purge_keys,
                recurse_exceptions=recurse_exceptions,
            )
        else:
            # Otherwise, update the value in A with the value from B
            a_dict[key] = value
    # Prune keys with empty dictionary values (except for keys in prune exceptions list)
    keys_to_delete = [
        key
        for key, value in a_dict.items()
        if isinstance(value, dict)
        and not value
        and (prune_exceptions is None or key not in prune_exceptions)
    ]
    for key in keys_to_delete:
        del a_dict[key]
    # Delete keys from the list of keys to delete
    if purge_keys is not None:
        for key in purge_keys:
            if key in a_dict:
                del a_dict[key]
