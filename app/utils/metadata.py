import json
import os
import traceback
from pathlib import Path
from time import localtime, strftime, time
from typing import Any, Dict, Optional, Tuple, Union
from uuid import uuid4

from PySide6.QtCore import (
    QObject,
    QRunnable,
    QThread,
    QThreadPool,
    Signal,
)
from loguru import logger
from natsort import natsorted

from app.controllers.settings_controller import SettingsController
from app.models.dialogue import (
    show_dialogue_conditional,
    show_dialogue_file,
    show_warning,
)
from app.utils.app_info import AppInfo
from app.utils.constants import (
    DB_BUILDER_PRUNE_EXCEPTIONS,
    DB_BUILDER_RECURSE_EXCEPTIONS,
    DEFAULT_USER_RULES,
    MOD_RECURSE_EXCEPTIONS,
    RIMWORLD_DLC_METADATA,
)
from app.utils.generic import directories
from app.utils.schema import validate_rimworld_mods_list
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.utils.steam.steamfiles.wrapper import acf_to_dict, dict_to_acf
from app.utils.steam.webapi.wrapper import (
    DynamicQuery,
    ISteamRemoteStorage_GetPublishedFileDetails,
)
from app.utils.xml import xml_path_to_json


# Locally installed mod metadata


class MetadataManager(QObject):
    _instance: Optional["MetadataManager"] = None
    mod_created_signal = Signal(str)
    mod_deleted_signal = Signal(str)
    mod_metadata_updated_signal = Signal(str)
    show_warning_signal = Signal(str, str, str, str)
    update_game_configuration_signal = Signal()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MetadataManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, settings_controller: SettingsController) -> None:
        if not hasattr(self, "initialized"):
            super(MetadataManager, self).__init__()
            logger.info("Initializing MetadataManager")

            self.settings_controller = settings_controller

            # Initialize our threadpool for multithreaded parsing
            self.parser_threadpool = QThreadPool.globalInstance()

            # Connect a warning signal for thread-safe prompts
            self.show_warning_signal.connect(show_warning)

            # Store parsed metadata & paths
            self.external_steam_metadata: Optional[Dict[str, Any]] = None
            self.external_steam_metadata_path: Optional[str] = None
            self.external_community_rules: Optional[Dict[str, Any]] = None
            self.external_community_rules_path: Optional[str] = None
            self.external_user_rules: Optional[Dict[str, Any]] = None
            self.external_user_rules_path: Optional[str] = str(
                AppInfo().databases_folder / "userRules.json"
            )
            # Local metadata
            self.internal_local_metadata: Dict[str, Any] = {}
            # Mappers
            self.mod_metadata_file_mapper: Dict[str, str] = {}
            self.mod_metadata_dir_mapper: Dict[str, str] = {}
            self.packageid_to_uuids: Dict[str, set(str)] = {}
            self.steamdb_packageid_to_name: Dict[str, str] = {}
            # Empty game version string unless the data is populated
            self.game_version: str = ""
            # SteamCMD .acf file data
            self.steamcmd_acf_data: Dict[str, Any] = {}
            # Steam .acf file path / data
            self.workshop_acf_path: Optional[str] = str(
                # This is just getting the path 2 directories up from content/294100,
                # so that we can find workshop/appworkshop_294100.acf
                Path(self.settings_controller.settings.workshop_folder).parent.parent
                / "appworkshop_294100.acf",
            )
            self.workshop_acf_data: Dict[str, Any] = {}

    @classmethod
    def instance(cls, *args: Any, **kwargs: Any) -> "MetadataManager":
        if cls._instance is None:
            cls._instance = cls(*args, **kwargs)
        elif args or kwargs:
            raise ValueError("MetadataManager instance has already been initialized.")
        return cls._instance

    def __refresh_acf_metadata(self) -> None:
        # If we can find the appworkshop_294100.acf files from...
        # ...SteamCMD
        if os.path.exists(SteamcmdInterface.instance().steamcmd_appworkshop_acf_path):
            try:
                self.steamcmd_acf_data = acf_to_dict(
                    SteamcmdInterface.instance().steamcmd_appworkshop_acf_path
                )
                logger.info(
                    f"Successfully parsed SteamCMD appworkshop.acf metadata from: {SteamcmdInterface.instance().steamcmd_appworkshop_acf_path}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to parse SteamCMD appworkshop.acf metadata from: {SteamcmdInterface.instance().steamcmd_appworkshop_acf_path}. Error: {e}"
                )
        # ...Steam client
        if os.path.exists(self.workshop_acf_path):
            try:
                self.workshop_acf_data = acf_to_dict(self.workshop_acf_path)
                logger.info(
                    f"Successfully parsed Steam client appworkshop.acf metadata from: {self.workshop_acf_path}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to parse Steam client appworkshop.acf metadata from: {self.workshop_acf_path}. Error: {e}"
                )

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
                    self.steamdb_packageid_to_name = {
                        metadata["packageid"]: metadata["name"]
                        for metadata in db_data.get("database", {}).values()
                        if metadata.get("packageid") and metadata.get("name")
                    }
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
            self.settings_controller.settings.external_steam_metadata_source
            == "Configured file path"
        ):
            (
                self.external_steam_metadata,
                self.external_steam_metadata_path,
            ) = get_configured_steam_db(
                self,
                life=self.settings_controller.settings.database_expiry,
                path=self.settings_controller.settings.external_steam_metadata_file_path,
            )
        elif (
            self.settings_controller.settings.external_steam_metadata_source
            == "Configured git repository"
        ):
            (
                self.external_steam_metadata,
                self.external_steam_metadata_path,
            ) = get_configured_steam_db(
                self,
                life=self.settings_controller.settings.database_expiry,
                path=str(
                    (
                        os.path.join(
                            str(AppInfo().databases_folder),
                            os.path.split(
                                self.settings_controller.settings.external_steam_metadata_repo
                            )[1],
                            "steamDB.json",
                        )
                    )
                ),
            )
        else:
            logger.info(
                "External Steam metadata disabled by user. Please choose a metadata source in settings."
            )

        # External Community Rules metadata
        if (
            self.settings_controller.settings.external_community_rules_metadata_source
            == "Configured file path"
        ):
            (
                self.external_community_rules,
                self.external_community_rules_path,
            ) = get_configured_community_rules_db(
                self,
                path=self.settings_controller.settings.external_community_rules_file_path,
            )
        elif (
            self.settings_controller.settings.external_community_rules_metadata_source
            == "Configured git repository"
        ):
            (
                self.external_community_rules,
                self.external_community_rules_path,
            ) = get_configured_community_rules_db(
                self,
                path=str(
                    (
                        Path(str(AppInfo().databases_folder))
                        / Path(
                            os.path.split(
                                self.settings_controller.settings.external_community_rules_repo
                            )[1]
                        )
                        / "communityRules.json"
                    )
                ),
            )
        else:
            logger.info(
                "External Community Rules metadata disabled by user. Please choose a metadata source in settings."
            )
        # External User Rules metadata
        if os.path.exists(self.external_user_rules_path):
            logger.info("Loading userRules.json")
            with open(self.external_user_rules_path, encoding="utf-8") as f:
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
                self.external_user_rules_path,
                "w",
                encoding="utf-8",
            ) as output:
                json.dump(DEFAULT_USER_RULES, output, indent=4)
            self.external_user_rules = DEFAULT_USER_RULES["rules"]

    def __refresh_internal_metadata(self, is_initial: bool = False) -> None:
        def batch_by_data_source(
            self, data_source: str, mod_directories: list[str]
        ) -> dict[str, Any]:
            return {
                path: self.mod_metadata_dir_mapper.get(path, str(uuid4()))
                for path in mod_directories
            }

        # Get & set Rimworld version string
        version_file_path = str(
            (Path(self.settings_controller.settings.game_folder) / "Version.txt")
        )
        if os.path.exists(version_file_path):
            try:
                with open(version_file_path, encoding="utf-8") as f:
                    self.game_version = f.read().strip()
                    logger.info(
                        f"Retrieved game version from Version.txt: {self.game_version}"
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
                f"\nIs your game path [{self.settings_controller.settings.game_folder}] set correctly? There should be a Version.txt file in the game install directory.",
                "",
            )
        # Get and cache installed base game / DLC data
        if (
            self.settings_controller.settings.game_folder
            and self.settings_controller.settings.game_folder != ""
        ):
            # Get mod data
            data_path = str(
                (Path(self.settings_controller.settings.game_folder) / "Data")
            )
            logger.info(
                f"Querying Official expansions from RimWorld's Data folder: {data_path}"
            )
            # Scan our Official expansions directory
            expansion_subdirectories = directories(data_path)
            # Query the batch
            self.process_batch(
                batch=batch_by_data_source(self, "expansion", expansion_subdirectories),
                data_source="expansion",
            )
            # Wait for pool to complete
            self.parser_threadpool.waitForDone()
            logger.info(
                "Finished querying Official expansions. Supplementing metadata..."
            )
            # Create a packageid to appid mapping for quicker lookup
            package_to_app = {
                dlc["packageid"]: appid for appid, dlc in RIMWORLD_DLC_METADATA.items()
            }
            # Base game and expansion About.xml do not contain name, so these
            # must be manually added
            for metadata in self.internal_local_metadata.values():
                package_id = metadata["packageid"]
                appid = package_to_app.get(package_id)
                if appid:
                    dlc_metadata = RIMWORLD_DLC_METADATA[appid]
                    # Default for supported versions if not already present
                    default_versions = {
                        "li": ".".join(self.game_version.split(".")[:2])
                    }
                    # Update metadata efficiently
                    metadata.update(
                        {
                            "appid": appid,
                            "name": dlc_metadata["name"],
                            "steam_url": dlc_metadata["steam_url"],
                            "description": dlc_metadata["description"],
                            "supportedversions": metadata.get(
                                "supportedversions", default_versions
                            ),
                        }
                    )
        else:
            logger.error(
                "Skipping parsing data from empty game data path. Is the game path configured?"
            )
        # Get and cache installed local/SteamCMD Workshop mods
        if (
            self.settings_controller.settings.local_folder
            and self.settings_controller.settings.local_folder != ""
        ):
            # Get mod data
            logger.info(
                f"Querying local mods from path: {self.settings_controller.settings.local_folder}"
            )
            local_subdirectories = directories(
                self.settings_controller.settings.local_folder
            )
            self.process_batch(
                batch=batch_by_data_source(self, "local", local_subdirectories),
                data_source="local",
            )
        else:
            logger.debug(
                "Skipping parsing data from empty local mods path. Is the local mods path configured?"
            )
        # Get and cache installed Steam client Workshop mods
        if (
            self.settings_controller.settings.workshop_folder
            and self.settings_controller.settings.workshop_folder != ""
        ):
            logger.info(
                f"Querying workshop mods from path: {self.settings_controller.settings.workshop_folder}"
            )
            workshop_subdirectories = directories(
                self.settings_controller.settings.workshop_folder
            )
            self.process_batch(
                batch=batch_by_data_source(self, "workshop", workshop_subdirectories),
                data_source="workshop",
            )
        else:
            logger.debug(
                "Skipping parsing data from empty workshop mods path. Is the workshop mods path configured?"
            )
        # Wait for pool to complete
        self.parser_threadpool.waitForDone()
        # Generate our file <-> UUID mappers for Watchdog and friends
        # Map mod uuid to metadata file path
        self.mod_metadata_file_mapper = {
            **{
                metadata.get(
                    "metadata_file_path"
                ): uuid  # We watch the mod's parent directory for changes, so we need to map to the mod's uuid
                for uuid, metadata in self.internal_local_metadata.items()
            },
        }
        # Map mod uuid to mod dir path
        self.mod_metadata_dir_mapper = {
            **{
                metadata.get(
                    "path"
                ): uuid  # We watch the mod's parent directory for changes, so we need to map to the mod's uuid
                for uuid, metadata in self.internal_local_metadata.items()
            },
        }

    def is_version_mismatch(self, uuid: str) -> bool:
        """
        Check version for everything except Core.
        Return True if the version does not match.
        Return False if the version matches.
        If there is an error, log it and return True.
        """
        # Initialize result to True, if an error occurs, it will be changed to False
        result = True

        # Get mod data
        mod_data = self.internal_local_metadata.get(uuid, {})

        # Check if game_version exists and mod_data exists and mod_data contains 'supportedversions' with 'li' key
        if (
            self.game_version
            and mod_data
            and mod_data.get("supportedversions", {}).get("li")
        ):
            # Get supported versions
            supported_versions = self.internal_local_metadata[uuid][
                "supportedversions"
            ]["li"]

            # Check if supported versions is a string or a list
            if isinstance(supported_versions, str):
                # If game_version starts with supported_versions, result is False
                if self.game_version.startswith(supported_versions):
                    result = False
            elif isinstance(supported_versions, list):
                # If any version from supported_versions starts with game_version, result is False
                result = not any(
                    [
                        ver
                        for ver in supported_versions
                        if self.game_version.startswith(ver)
                    ]
                )
            else:
                # If supported_versions is not a string or a list, log error and return True
                logger.error(
                    f"supportedversions value not str or list: {supported_versions}"
                )
                result = True

        # Return result
        return result

    def process_batch(
        self,
        batch: dict[str, str],  # Batch is a mapper of mod directory <-> UUID to parse
        data_source: str,
    ) -> dict[str, Any]:
        for directory, uuid in batch.items():
            self.process_update(
                batch=True,
                exists=uuid in self.internal_local_metadata.keys(),
                data_source=data_source,
                mod_directory=directory,
                uuid=uuid,
            )

    def process_creation(self, data_source: str, mod_directory: str, uuid: str) -> None:
        logger.debug(
            f'Processing creation of {data_source + " mod" if data_source != "expansion" else data_source} for {mod_directory}'
        )
        self.process_update(
            batch=False,
            exists=uuid in self.internal_local_metadata.keys(),
            data_source=data_source,
            mod_directory=mod_directory,
            uuid=uuid,
        ),
        self.mod_created_signal.emit(uuid)

    def process_deletion(self, data_source: str, mod_directory: str, uuid: str) -> None:
        logger.debug(
            f"Processing deletion for {self.internal_local_metadata.get(uuid, {}).get('name', 'Unknown')}: {mod_directory}"
        )
        self.internal_local_metadata.pop(uuid, None)
        self.mod_deleted_signal.emit(uuid)

    def process_update(
        self,
        batch: bool,
        exists: bool,
        data_source: str,
        mod_directory: str,
        uuid: str,
    ) -> None:
        # logger.warning(exists)
        parser = ModParser(
            mod_directory=mod_directory,
            data_source=data_source,
            metadata_manager=self,
            uuid=uuid,
        )
        self.parser_threadpool.start(parser)
        # Wait for pool to complete if this is a single update
        if not batch:
            logger.debug(f"Waiting for metadata update to complete...")
            self.parser_threadpool.waitForDone()
        # Send signal to UI to update mod list if the mod we are updating exists
        if exists:
            self.mod_metadata_updated_signal.emit(uuid)

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
        logger.info("Refreshing metadata cache...")

        # If we are refreshing cache from user action, update user paths as well in case of change
        if not is_initial:
            self.update_game_configuration_signal.emit()

        # Update paths from game configuration

        # Populate metadata
        self.__refresh_acf_metadata()
        self.__refresh_external_metadata()
        self.__refresh_internal_metadata(is_initial=is_initial)


class ModParser(QRunnable):

    mod_metadata_updated_signal = Signal(str)

    def __init__(
        self,
        data_source: str,
        mod_directory: str,
        metadata_manager: MetadataManager,
        uuid: str = None,
    ):
        super(ModParser, self).__init__()
        self.data_source = data_source
        self.mod_directory = mod_directory
        self.metadata_manager = metadata_manager
        self.uuid = uuid

    def __compile_mod_metadata(self, uuid: str) -> None:
        """
        Iterate through each expansion or mod and add new key-values describing the
        dependencies, incompatibilities, and load order rules compiled from metadata.
        """
        mod_metadata = self.metadata_manager.internal_local_metadata.get(uuid, {})
        if not mod_metadata:
            logger.error(f"FATAL: No metadata found for {uuid}")
            return
        data_source = mod_metadata["data_source"]
        # Grab our mod's publishedfileid
        publishedfileid = self.metadata_manager.internal_local_metadata.get(
            uuid, {}
        ).get("publishedfileid")
        if publishedfileid:
            # Get our metadata based on data source
            if data_source == "local":
                workshop_item_details = self.metadata_manager.steamcmd_acf_data[
                    "AppWorkshop"
                ]["WorkshopItemDetails"]
                workshop_items_installed = self.metadata_manager.steamcmd_acf_data[
                    "AppWorkshop"
                ]["WorkshopItemsInstalled"]
            elif data_source == "workshop":
                # Reference needed information from appworkshop_294100.acf
                workshop_item_details = self.metadata_manager.workshop_acf_data[
                    "AppWorkshop"
                ]["WorkshopItemDetails"]
                workshop_items_installed = self.metadata_manager.workshop_acf_data[
                    "AppWorkshop"
                ]["WorkshopItemsInstalled"]
            # Edit our metadata, append values
            if (
                workshop_item_details.get(publishedfileid, {}).get("timetouched")
                and workshop_item_details.get(publishedfileid, {}).get("timetouched")
                != 0
            ):
                # The last time SteamCMD/Steam client touched a mod according to its entry
                mod_metadata["internal_time_touched"] = int(
                    workshop_item_details[publishedfileid]["timetouched"]
                )
            if publishedfileid and workshop_item_details.get(publishedfileid, {}).get(
                "timeupdated"
            ):
                # The last time SteamCMD/Steam client updated a mod according to its entry
                mod_metadata["internal_time_updated"] = int(
                    workshop_item_details[publishedfileid]["timeupdated"]
                )
            if publishedfileid and workshop_items_installed.get(
                publishedfileid, {}
            ).get("timeupdated"):
                # The last time SteamCMD/Steam client updated a mod according to its entry
                mod_metadata["internal_time_updated"] = int(
                    workshop_items_installed[publishedfileid]["timeupdated"]
                )
        #####################
        # About.xml dependencies, incompatibilities, and load order rules
        #####################
        # moddependencies are not equal to mod load order rules
        if mod_metadata.get("moddependencies"):
            if isinstance(
                mod_metadata["moddependencies"],
                dict,
            ):
                dependencies = mod_metadata["moddependencies"].get("li")
            elif isinstance(
                mod_metadata["moddependencies"],
                list,
            ):
                # Loop through the list and try to find dictionary. If we find one, use it.
                for potential_dependencies in mod_metadata["moddependencies"]:
                    if (
                        potential_dependencies
                        and isinstance(potential_dependencies, dict)
                        and potential_dependencies.get("li")
                    ):
                        dependencies = potential_dependencies["li"]
            if dependencies:
                add_dependency_to_mod(
                    mod_metadata,
                    dependencies,
                    self.metadata_manager.internal_local_metadata,
                )

        if mod_metadata.get("moddependenciesbyversion"):
            if mod_metadata["moddependenciesbyversion"].get("v1.4"):
                dependencies_by_ver = self.metadata_manager.internal_local_metadata[
                    uuid
                ]["moddependenciesbyversion"]["v1.4"].get("li")
                if dependencies_by_ver:
                    add_dependency_to_mod(
                        mod_metadata,
                        dependencies_by_ver,
                        self.metadata_manager.internal_local_metadata,
                    )
        if mod_metadata.get("incompatiblewith"):
            incompatibilities = mod_metadata["incompatiblewith"].get("li")
            if incompatibilities:
                add_incompatibility_to_mod(
                    mod_metadata,
                    incompatibilities,
                    self.metadata_manager.internal_local_metadata,
                )
        if mod_metadata.get("incompatiblewithbyversion"):
            if mod_metadata["incompatiblewithbyversion"].get("v1.4"):
                incompatibilities_by_ver = mod_metadata["incompatiblewithbyversion"][
                    "v1.4"
                ].get("li")
                if incompatibilities_by_ver:
                    add_incompatibility_to_mod(
                        mod_metadata,
                        incompatibilities_by_ver,
                        self.metadata_manager.internal_local_metadata,
                    )
        # Current mod should be loaded AFTER these mods. These mods can be thought
        # of as "load these before". These are not necessarily dependencies in the sense
        # that they "depend" on them. But, if they exist in the same mod list, they
        # should be loaded before.
        if mod_metadata.get("loadafter"):
            try:
                load_these_before = mod_metadata["loadafter"].get("li")
                if load_these_before:
                    add_load_rule_to_mod(
                        mod_metadata,
                        load_these_before,
                        "loadTheseBefore",
                        "loadTheseAfter",
                        self.metadata_manager.internal_local_metadata,
                        self.metadata_manager.packageid_to_uuids,
                    )
            except:
                mod_path = mod_metadata["path"]
                logger.warning(
                    f"About.xml syntax error. Unable to read <loadafter> tag from XML: {mod_path}"
                )
                logger.warning(json.dumps(mod_metadata, indent=4))
        if mod_metadata.get("forceloadafter"):
            try:
                force_load_these_before = self.metadata_manager.internal_local_metadata[
                    uuid
                ]["forceloadafter"].get("li")
                if force_load_these_before:
                    add_load_rule_to_mod(
                        mod_metadata,
                        force_load_these_before,
                        "loadTheseBefore",
                        "loadTheseAfter",
                        self.metadata_manager.internal_local_metadata,
                        self.metadata_manager.packageid_to_uuids,
                    )
            except:
                mod_path = mod_metadata["path"]
                logger.warning(
                    f"About.xml syntax error. Unable to read <forceloadafter> tag from XML: {mod_path}"
                )
        if mod_metadata.get("loadafterbyversion"):
            if mod_metadata["loadafterbyversion"].get("v1.4"):
                try:
                    load_these_before_by_ver = mod_metadata["loadafterbyversion"][
                        "v1.4"
                    ].get("li")
                    if load_these_before_by_ver:
                        add_load_rule_to_mod(
                            mod_metadata,
                            load_these_before_by_ver,
                            "loadTheseBefore",
                            "loadTheseAfter",
                            self.metadata_manager.internal_local_metadata,
                            self.metadata_manager.packageid_to_uuids,
                        )
                except:
                    mod_path = mod_metadata["path"]
                    logger.warning(
                        f"About.xml syntax error. Unable to read <loadafterbyversion><v1.4> tag from XML: {mod_path}"
                    )
        # Current mod should be loaded BEFORE these mods
        # The current mod is a dependency for all these mods
        if mod_metadata.get("loadbefore"):
            try:
                load_these_after = mod_metadata["loadbefore"].get("li")
                if load_these_after:
                    add_load_rule_to_mod(
                        mod_metadata,
                        load_these_after,
                        "loadTheseAfter",
                        "loadTheseBefore",
                        self.metadata_manager.internal_local_metadata,
                        self.metadata_manager.packageid_to_uuids,
                    )
            except:
                mod_path = mod_metadata["path"]
                logger.warning(
                    f"About.xml syntax error. Unable to read <loadbefore> tag from XML: {mod_path}"
                )
        if mod_metadata.get("forceloadbefore"):
            try:
                force_load_these_after = self.metadata_manager.internal_local_metadata[
                    uuid
                ]["forceloadbefore"].get("li")
                if force_load_these_after:
                    add_load_rule_to_mod(
                        mod_metadata,
                        force_load_these_after,
                        "loadTheseAfter",
                        "loadTheseBefore",
                        self.metadata_manager.internal_local_metadata,
                        self.metadata_manager.packageid_to_uuids,
                    )
            except:
                mod_path = mod_metadata["path"]
                logger.warning(
                    f"About.xml syntax error. Unable to read <forceloadbefore> tag from XML: {mod_path}"
                )
        if mod_metadata.get("loadbeforebyversion"):
            if mod_metadata["loadbeforebyversion"].get("v1.4"):
                try:
                    load_these_after_by_ver = mod_metadata["loadbeforebyversion"][
                        "v1.4"
                    ].get("li")
                    if load_these_after_by_ver:
                        add_load_rule_to_mod(
                            mod_metadata,
                            load_these_after_by_ver,
                            "loadTheseAfter",
                            "loadTheseBefore",
                            self.metadata_manager.internal_local_metadata,
                            self.metadata_manager.packageid_to_uuids,
                        )
                except:
                    mod_path = mod_metadata["path"]
                    logger.warning(
                        f"About.xml syntax error. Unable to read <loadbeforebyversion><v1.4> tag from XML: {mod_path}"
                    )
        ##############################
        # SteamDB dependencies by PublishedFileID
        # Steam references dependencies based on PublishedFileID, not package ID
        #############################
        is_expansion = mod_metadata.get("data_source", "") == "expansion"
        if not is_expansion and self.metadata_manager.external_steam_metadata:
            dependencies_set = set()
            packageid = mod_metadata.get("packageid")
            publishedfileid = mod_metadata.get("publishedfileid")
            # If we have publishedfileid that is in the steamdb, we can cross-reference the packageid
            db_packageid = (
                self.metadata_manager.external_steam_metadata.get(publishedfileid, {})
                .get("packageId", "")
                .lower()
            )
            if db_packageid == packageid:
                db_packageid = db_packageid.lower()  # Normalize packageid
                # Store name for later convenience
                name = self.metadata_manager.external_steam_metadata[
                    publishedfileid
                ].get("name")
                self.metadata_manager.steamdb_packageid_to_name[db_packageid] = name
                # Get dependencies set from SteamDB
                dependencies_set.update(
                    self.metadata_manager.external_steam_metadata[publishedfileid]
                    .get("dependencies", {})
                    .keys()
                )
            # For each mod that exists in self.metadata_manager.internal_local_metadata -> dependencies (in Steam ID form)
            for dependency_publishedfileid in dependencies_set:
                # Dependencies are added as packageids in metadata / RimWorld
                dependency_packageid = (
                    self.metadata_manager.external_steam_metadata.get(
                        dependency_publishedfileid, {}
                    )
                    .get("packageId", "")
                    .lower()
                )
                # Create a new key with empty set as value by default
                mod_metadata.setdefault("dependencies", set())
                # If the value is a single str (for steamDB)
                if dependency_packageid:
                    mod_metadata["dependencies"].add(dependency_packageid)
                else:
                    logger.error(
                        f"Dependencies is not a single str: [{dependency_packageid}]"
                    )
        # Add load order to installed mods based on dependencies from community rules
        if self.metadata_manager.external_community_rules:
            logger.info("Started compiling metadata from configured Community Rules")
            mod_package_id = mod_metadata.get("packageid")
            for db_package_id in self.metadata_manager.external_community_rules:
                if mod_package_id != db_package_id.lower:
                    continue
                load_these_after = self.metadata_manager.external_community_rules[
                    db_package_id
                ].get("loadBefore")
                if load_these_after:
                    logger.debug(
                        f"Current mod should load before these mods: {load_these_after}"
                    )
                    # In Alphabetical, load_these_after is at least an empty dict
                    # Cannot call add_load_rule_to_mod outside of this for loop,
                    # as that expects a list
                    for load_this_after in load_these_after:
                        add_load_rule_to_mod(
                            mod_metadata,
                            load_this_after,  # Lower() done in call
                            "loadTheseAfter",
                            "loadTheseBefore",
                            self.metadata_manager.internal_local_metadata,
                            self.metadata_manager.packageid_to_uuids,
                        )
                load_these_before = self.metadata_manager.external_community_rules[
                    db_package_id
                ].get("loadAfter")
                if load_these_before:
                    logger.debug(
                        f"Current mod should load after these mods: {load_these_before}"
                    )
                    # In Alphabetical, load_these_before is at least an empty dict
                    for load_this_before in load_these_before:
                        add_load_rule_to_mod(
                            self.metadata_manager.internal_local_metadata[
                                uuid
                            ],  # Already checked above
                            load_this_before,  # lower() done in call
                            "loadTheseBefore",
                            "loadTheseAfter",
                            self.metadata_manager.internal_local_metadata,
                            self.metadata_manager.packageid_to_uuids,
                        )
                load_this_bottom = self.metadata_manager.external_community_rules[
                    db_package_id
                ].get("loadBottom")
                if load_this_bottom:
                    logger.debug(
                        f'Current mod should load at the bottom of a mods list, and will be considered a "tier 3" mod'
                    )
                    mod_metadata["loadBottom"] = True
            logger.info("Finished adding dependencies from Community Rules")
        # Add load order rules to installed mods based on rules from user rules
        if self.metadata_manager.external_user_rules:
            mod_package_id = mod_metadata.get("packageid")
            logger.info("Started compiling metadata from User Rules")
            for db_package_id in self.metadata_manager.external_community_rules:
                if mod_package_id != db_package_id.lower:
                    continue
                load_these_after = self.metadata_manager.external_user_rules[
                    db_package_id
                ].get("loadBefore")
                if load_these_after:
                    logger.debug(
                        f"Current mod should load before these mods: {load_these_after}"
                    )
                    # In Alphabetical, load_these_after is at least an empty dict
                    # Cannot call add_load_rule_to_mod outside of this for loop,
                    # as that expects a list
                    for load_this_after in load_these_after:
                        add_load_rule_to_mod(
                            self.metadata_manager.internal_local_metadata[
                                uuid
                            ],  # Already checked above
                            load_this_after,  # lower() done in call
                            "loadTheseAfter",
                            "loadTheseBefore",
                            self.metadata_manager.internal_local_metadata,
                            self.metadata_manager.packageid_to_uuids,
                        )

                load_these_before = self.metadata_manager.external_user_rules[
                    db_package_id
                ].get("loadAfter")
                if load_these_before:
                    logger.debug(
                        f"Current mod should load after these mods: {load_these_before}"
                    )
                    # In Alphabetical, load_these_before is at least an empty dict
                    for load_this_before in load_these_before:
                        add_load_rule_to_mod(
                            self.metadata_manager.internal_local_metadata[
                                uuid
                            ],  # Already checked above
                            load_this_before,  # lower() done in call
                            "loadTheseBefore",
                            "loadTheseAfter",
                            self.metadata_manager.internal_local_metadata,
                            self.metadata_manager.packageid_to_uuids,
                        )
                load_this_bottom = self.metadata_manager.external_user_rules[
                    db_package_id
                ].get("loadBottom")
                if load_this_bottom:
                    logger.debug(
                        f'Current mod should load at the bottom of a mods list, and will be considered a "tier 3" mod'
                    )
                    mod_metadata["loadBottom"] = True
            logger.info("Finished adding dependencies from User Rules")

    def __parse_mod_metadata(
        self,
        data_source: str,
        mod_directory: str,
        metadata_manager: MetadataManager,
        uuid: str,
    ) -> Dict[str, Any]:
        logger.debug(f"Parsing [{data_source}] directory: {mod_directory}")
        metadata = {}
        # Populate a UUID for the directory we are populating - re-use the same UUID
        # if passed as the "data_source" parameter for single-mod updates
        uuid = uuid
        directory_path = Path(mod_directory)
        directory_name = str(directory_path.name)
        # Use this to trigger invalid clause intentionally, i.e. when handling exceptions
        data_malformed = None
        # Any pfid parsed will be stored here locally
        pfid = None
        # Look for a case-insensitive "About" folder
        invalid_about_folder_path_found = True
        about_folder_name = "About"
        for temp_file in os.scandir(mod_directory):
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
            for temp_file in os.scandir(str((directory_path / about_folder_name))):
                if (
                    temp_file.name.lower() == about_file_name.lower()
                    and temp_file.is_file()
                ):
                    about_file_name = temp_file.name
                    invalid_about_file_path_found = False
                    break
        # Look for .rsc scenario files to load metadata from if we didn't find About.xml
        if invalid_about_file_path_found:
            scenario_rsc_found = None
            for temp_file in os.scandir(mod_directory):
                if temp_file.name.lower().endswith(".rsc") and not temp_file.is_dir():
                    scenario_rsc_file = temp_file.name
                    scenario_rsc_found = True
                    break
        # If a mod's folder name is a valid PublishedFileId in SteamDB
        if (
            self.metadata_manager.external_steam_metadata
            and directory_name in self.metadata_manager.external_steam_metadata.keys()
        ):
            pfid = directory_name
        # Look for a case-insensitive "PublishedFileId.txt" file if we didn't find a pfid
        elif not pfid and not invalid_about_folder_path_found:
            pfid_file_name = "PublishedFileId.txt"
            for temp_file in os.scandir(str((directory_path / about_folder_name))):
                if (
                    temp_file.name.lower() == pfid_file_name.lower()
                    and temp_file.is_file()
                ):
                    pfid_file_name = temp_file.name
                    pfid_path = str(
                        (directory_path / about_folder_name / pfid_file_name)
                    )
                    try:
                        with open(pfid_path, encoding="utf-8-sig") as pfid_file:
                            pfid = pfid_file.read()
                            pfid = pfid.strip()
                    except:
                        logger.error(f"Failed to read pfid from {pfid_path}")
                    break
        # If we were able to find an About.xml, populate mod data...
        if not invalid_about_file_path_found:
            mod_data_path = str((directory_path / about_folder_name / about_file_name))
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
                mod_data = {k.lower(): v for k, v in mod_data.items()}
                if mod_data.get("modmetadata"):
                    # Initialize our dict from the formatted About.xml metadata
                    mod_metadata = mod_data["modmetadata"]
                    # Case-insensitive metadata keys
                    mod_metadata = {k.lower(): v for k, v in mod_metadata.items()}
                    if (  # If we don't have a <name>
                        not mod_metadata.get("name")
                        and self.metadata_manager.external_steam_metadata  # ... try to find it in Steam DB
                        and self.metadata_manager.external_steam_metadata.get(
                            pfid, {}
                        ).get("steamName")
                    ):
                        mod_metadata.setdefault(
                            "name",
                            self.metadata_manager.external_steam_metadata[pfid][
                                "steamName"
                            ],
                        )
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
                            # Loop through the list and find str. If we find one, use it.
                            for potential_packageid in mod_metadata["packageid"]:
                                if potential_packageid and isinstance(
                                    potential_packageid, str
                                ):
                                    mod_metadata["packageid"] = potential_packageid
                                    break
                        # Normalize package ID in metadata
                        mod_metadata["packageid"] = mod_metadata["packageid"].lower()
                    else:  # ...otherwise, we don't have one from About.xml, and we can check Steam DB...
                        # ...this can be needed if a mod depends on a RW generated packageid via built-in hashing mechanism.
                        if (
                            self.metadata_manager.external_steam_metadata
                            and self.metadata_manager.external_steam_metadata.get(
                                pfid, {}
                            ).get("packageId")
                        ):
                            mod_metadata["packageid"] = (
                                self.metadata_manager.external_steam_metadata[pfid][
                                    "packageId"
                                ].lower()
                            )
                        else:
                            mod_metadata.setdefault("packageid", "missing.packageid")
                    # Track pfid if we parsed one earlier
                    if pfid:  # Make some assumptions if we have a pfid
                        mod_metadata["publishedfileid"] = pfid
                        mod_metadata["steam_uri"] = (
                            f"steam://url/CommunityFilePage/{pfid}"
                        )
                        mod_metadata["steam_url"] = (
                            f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"
                        )
                    # If a mod contains C# assemblies, we want to tag the mod
                    assemblies_path = str(directory_path / "Assemblies")
                    # Check if the 'Assemblies' directory exists and is a directory
                    if os.path.exists(assemblies_path) and os.path.isdir(
                        assemblies_path
                    ):
                        try:
                            # Check if there are any .dll files in the 'Assemblies' directory
                            if any(
                                filename.endswith((".dll", ".DLL"))
                                for filename in os.listdir(assemblies_path)
                            ):
                                mod_metadata["csharp"] = (
                                    True  # Tag the mod as containing C# code
                                )
                        except Exception as e:
                            logger.error(
                                f"Failed to list directory {assemblies_path}: {e}"
                            )
                    else:
                        # If no 'Assemblies' directory in the main folder, check in subfolders
                        subfolder_paths = [
                            str(directory_path / folder)
                            for folder in os.listdir(mod_directory)
                            if os.path.isdir(str(directory_path / folder))
                        ]
                        for subfolder_path in subfolder_paths:
                            assemblies_path = str(Path(subfolder_path) / "Assemblies")
                            # Check if the 'Assemblies' directory exists in the subfolder
                            if os.path.exists(assemblies_path):
                                # Check if there are any .dll files in this 'Assemblies' directory
                                if any(
                                    filename.endswith((".dll", ".DLL"))
                                    for filename in os.listdir(assemblies_path)
                                ):
                                    mod_metadata["csharp"] = (
                                        True  # Tag the mod as containing C# code
                                    )
                    # data_source will be used with setIcon later
                    mod_metadata["data_source"] = data_source
                    mod_metadata["folder"] = directory_name
                    # This is overwritten if acf data is parsed for Steam/SteamCMD mods
                    mod_metadata["internal_time_touched"] = int(
                        os.path.getmtime(mod_directory)
                    )
                    mod_metadata["path"] = mod_directory
                    mod_metadata["metadata_file_mtime"] = int(
                        os.path.getmtime(mod_data_path)
                    )
                    mod_metadata["metadata_file_path"] = mod_data_path
                    metadata[uuid] = mod_metadata
                else:
                    logger.error(
                        f"Key <modmetadata> does not exist in this data: {mod_data}"
                    )
                    data_malformed = True
        # ...or, if we didn't find an About.xml, but we have a RimWorld scenario .rsc to parse...
        elif invalid_about_file_path_found and scenario_rsc_found:
            scenario_data_path = str((directory_path / scenario_rsc_file))
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
                scenario_data = {k.lower(): v for k, v in scenario_data.items()}
                if scenario_data.get("savedscenario", {}).get(
                    "scenario"
                ):  # If our .rsc metadata has a packageid key
                    # Initialize our dict from the formatted .rsc metadata
                    scenario_metadata = scenario_data["savedscenario"]["scenario"]
                    # Case-insensitive keys.
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
                        scenario_metadata["steam_uri"] = (
                            f"steam://url/CommunityFilePage/{pfid}"
                        )
                        scenario_metadata["steam_url"] = (
                            f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"
                        )
                    # data_source will be used with setIcon later
                    scenario_metadata["data_source"] = data_source
                    scenario_metadata["folder"] = directory_name
                    scenario_metadata["path"] = mod_directory
                    # This is overwritten if acf data is parsed for Steam/SteamCMD mods
                    scenario_metadata["internal_time_touched"] = int(
                        os.path.getmtime(mod_directory)
                    )
                    scenario_metadata["metadata_file_path"] = mod_data_path
                    scenario_metadata["metadata_file_mtime"] = int(
                        os.path.getmtime(mod_data_path)
                    )
                    # Track source & uuid in case metadata becomes detached
                    scenario_metadata["uuid"] = uuid
                    metadata[uuid] = scenario_metadata
                else:
                    logger.error(
                        f"Key <savedscenario><scenario> does not exist in this data: {scenario_metadata}"
                    )
                    data_malformed = True
        if (
            invalid_about_file_path_found and not scenario_rsc_found
        ) or data_malformed:  # ...finally, if we don't have any metadata parsed, populate invalid mod entry for visibility
            logger.debug(
                f"Invalid dir. Populating invalid mod for path: {mod_directory}"
            )
            metadata[uuid] = {
                "invalid": True,
                "name": "Invalid item",
                "packageid": "invalid.item",
                "authors": "Not found",
                "description": (
                    "This mod is considered invalid by RimSort (and the RimWorld game)."
                    + "\n\nThis mod does NOT contain an ./About/About.xml and is likely leftover from previous usage."
                    + "\n\nThis can happen sometimes with Steam mods if there are leftover .dds textures or unexpected data."
                ),
                "data_source": data_source,
                "folder": directory_name,
                "path": mod_directory,
                # This is overwritten if acf data is parsed for Steam/SteamCMD mods
                "internal_time_touched": int(os.path.getmtime(mod_directory)),
                "uuid": uuid,
            }
            if pfid:
                metadata[uuid].update({"publishedfileid": pfid})
        # Additional checks for local mods
        if data_source == "local":
            local_mod_metadata = metadata[uuid]
            # Check for git repository inside local mods, tag appropriately
            if os.path.exists(str((directory_path / ".git"))):
                local_mod_metadata["git_repo"] = True
            # Check for local mods that are SteamCMD mods, tag appropriately
            if local_mod_metadata.get("folder") == local_mod_metadata.get(
                "publishedfileid"
            ):
                local_mod_metadata["steamcmd"] = True
        return metadata

    def run(self):
        try:
            mod_metadata = self.__parse_mod_metadata(
                self.data_source, self.mod_directory, self.metadata_manager, self.uuid
            )
            packageid = mod_metadata[self.uuid].get("packageid")
            self.metadata_manager.internal_local_metadata.update(mod_metadata)
            # Track packageid -> uuid relationships for future uses
            self.metadata_manager.packageid_to_uuids.setdefault(packageid, set()).add(
                self.uuid
            )
            self.__compile_mod_metadata(self.uuid)
        except Exception as e:
            error_message = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"ERROR: Unable to initialize ModParser {error_message}")


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
                    if (
                        dependency
                    ):  # Sometimes, this can be None or an empty string if XML syntax error/extra elements
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
    packageid_to_uuids: Dict[str, Any],
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
    :param packageid_to_uuids: a helper dict to reduce work
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
        if dep in packageid_to_uuids:
            for uuid in packageid_to_uuids.get(dep, set()):
                mod_data[explicit_key].add((dep, True))
                all_mods[uuid].setdefault(indirect_key, set()).add(
                    (mod_data["packageid"], False)
                )


def get_mods_from_list(
    mod_list: Union[str, list[str]],
) -> Tuple[list[str], list[str], Dict[str, Any], list]:
    """
    Given a RimWorld mods list containing a complete list of mods,
    including base game and DLC, as well as their dependencies in order,
    return a list of mods for the active list widget and a list of
    mods for the inactive list widget.

    :param mod_list: path to an .rws/.xml style list, or a list of package ids
    :return: a Tuple which contains the active mods dict, inactive mods dict,
    duplicate mods dict, and missing mods list
    """
    all_mods = MetadataManager.instance().internal_local_metadata

    active_mods_uuids: list[str] = []
    inactive_mods_uuids: list[str] = []
    duplicate_mods: dict[str, Any] = {}
    duplicates_processed = []
    missing_mods: list[str] = []
    populated_mods = []
    to_populate = []
    logger.debug("Started generating active and inactive mods")
    # Calculate duplicate mods (SCHEMA: {str packageid: list[str duplicate uuids]})
    for mod_uuid, mod_data in all_mods.items():
        # Using setdefault() to initialize the dictionary and then assigning the value
        duplicate_mods.setdefault(mod_data["packageid"], []).append(mod_uuid)
    # Filter out non-duplicate mods
    duplicate_mods = {k: v for k, v in duplicate_mods.items() if len(v) > 1}
    # Calculate mod lists
    if isinstance(mod_list, str):
        logger.info(f"Retrieving active mods from RimWorld mod list")
        mod_data = xml_path_to_json(mod_list)
        package_ids_to_import = validate_rimworld_mods_list(mod_data)
        if not package_ids_to_import:
            logger.error(
                f"Unable to get active mods from config with read data: {mod_data}"
            )
            return active_mods_uuids, inactive_mods_uuids, duplicate_mods, missing_mods
    elif isinstance(mod_list, list):
        logger.info("Retrieving active mods from the provided list of package ids")
        package_ids_to_import = mod_list
    else:
        logger.error(
            "This should only be a path to XML mod list, or a list of package ids!"
        )
        return active_mods_uuids, inactive_mods_uuids, duplicate_mods, missing_mods
    # Parse the ModsConfig.xml data
    logger.info("Generating active mod list")
    for (
        package_id
    ) in package_ids_to_import:  # Go through active mods, handle packageids
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
                    active_mods_uuids.append(uuid)
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
                                paths_to_uuid[all_mods[duplicate_uuid]["path"]] = (
                                    duplicate_uuid
                                )
                        # Sort duplicate mod paths from current source priority using natsort
                        source_paths_sorted = natsorted(paths_to_uuid.keys())
                        if source_paths_sorted:  # If we have paths returned
                            # If we are here, we've found our calculated duplicate, log and use this mod
                            calculated_duplicate_uuid = paths_to_uuid[
                                source_paths_sorted[0]
                            ]
                            logger.debug(
                                f"Using duplicate {source} mod for {target_id}: {all_mods[calculated_duplicate_uuid]['path']}"
                            )
                            populated_mods.append(target_id)
                            duplicates_processed.append(target_id)
                            active_mods_uuids.append(calculated_duplicate_uuid)
                            break
                        else:  # Skip this source priority if no paths
                            logger.debug(f"No paths returned for {source}")
                            continue
    # Calculate missing mods from the difference
    missing_mods = list(set(to_populate) - set(populated_mods))
    logger.debug(f"Generated active mods dict with {len(active_mods_uuids)} mods")
    # Get the inactive mods by subtracting active mods from workshop + expansions
    logger.info("Generating inactive mod list")
    inactive_mods_uuids = [
        uuid for uuid in all_mods.keys() if uuid not in active_mods_uuids
    ]
    logger.info(f"# active mods: {len(active_mods_uuids)}")
    logger.info(f"# inactive mods: {len(inactive_mods_uuids)}")
    logger.info(f"# duplicate mods: {len(duplicate_mods)}")
    logger.info(f"# missing mods: {len(missing_mods)}")
    return active_mods_uuids, inactive_mods_uuids, duplicate_mods, missing_mods


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
                            f'\nInitializing "DynamicQuery" with configured Steam API key for {self.appid}\n'
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
                    f'\nInitializing "PublishedFileIDs by AppID" Query with configured Steam API key for AppID: {self.appid}\n\n'
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
                        "authors": (
                            ", ".join(v.get("authors").get("li"))
                            if v.get("authors")
                            and isinstance(v.get("authors"), dict)
                            and v.get("authors").get("li")
                            else v.get("authors", "Missing XML: <author(s)>")
                        ),
                    }
                    for v in self.mods.values()
                    if v.get("appid")
                },
                **{
                    v["publishedfileid"]: {
                        "url": f'https://steamcommunity.com/sharedfiles/filedetails/?id={v["publishedfileid"]}',
                        "packageId": v.get("packageid"),
                        "name": (
                            v.get("name")
                            if not v.get("DB_BUILDER_NO_NAME")
                            else "Missing XML: <name>"
                        ),
                        "authors": (
                            ", ".join(v.get("authors").get("li"))
                            if v.get("authors")
                            and isinstance(v.get("authors"), dict)
                            and v.get("authors").get("li")
                            else v.get("authors", "Missing XML: <author(s)>")
                        ),
                        "gameVersions": (
                            v.get("supportedversions").get("li")
                            if isinstance(
                                v.get("supportedversions", {}).get("li"), list
                            )
                            else [
                                (
                                    v.get("supportedversions", {}).get(
                                        "li",
                                    )
                                    if v.get("supportedversions")
                                    else v.get(
                                        "targetversion",
                                        "Missing XML: <supportedversions> or <targetversion>",
                                    )
                                )
                            ]
                        ),
                    }
                    for v in self.mods.values()
                    if v.get("publishedfileid")
                },
            },
        }
        total = len(db_from_local_metadata["database"].keys())
        self.db_builder_message_output_signal.emit(
            f"Populated {total} items from locally found metadata into initial database for "
            + f"{self.appid}"
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
                    Path(self.output_database_path).parent
                    / ("NEW_" + Path(self.output_database_path).name)
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
    # None-check for steamdb
    if not steamdb:
        show_warning(
            title="No SteamDB found",
            text="Unable to check for blacklisted mods. Please configure a SteamDB for RimSort to use in Settings.",
        )
        return publishedfileids
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
            title="Blacklisted mods found",
            text="Some mods are blacklisted in your SteamDB",
            information="Are you sure you want to download these mods? These mods are known mods that are recommended to be avoided.",
            details=blacklisted_mods_report,
            button_text_override=[
                "Download blacklisted mods",
                "Skip blacklisted mods",
            ],
        )
        # Remove blacklisted mods from list if user wants to download them still
        if "Download" in answer:
            publishedfileids.remove(publishedfileid)
            logger.debug(
                f"Skipping download of blacklisted Workshop mod: {publishedfileid}"
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
