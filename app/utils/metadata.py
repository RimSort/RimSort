import json
import os
from pathlib import Path
from re import match
from time import localtime, strftime, time
from typing import Any, Iterable, Union
from uuid import uuid4

from loguru import logger
from natsort import natsorted
from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Signal

from app.controllers.settings_controller import SettingsController
from app.utils.app_info import AppInfo
from app.utils.constants import (
    DB_BUILDER_PRUNE_EXCEPTIONS,
    DB_BUILDER_RECURSE_EXCEPTIONS,
    DEFAULT_USER_RULES,
    RIMWORLD_DLC_METADATA,
)
from app.utils.generic import directories
from app.utils.schema import generate_rimworld_mods_list, validate_rimworld_mods_list
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.utils.steam.steamfiles.wrapper import acf_to_dict, dict_to_acf
from app.utils.steam.webapi.wrapper import (
    DynamicQuery,
    ISteamRemoteStorage_GetPublishedFileDetails,
)
from app.utils.xml import json_to_xml_write, xml_path_to_json
from app.views.dialogue import (
    show_dialogue_conditional,
    show_dialogue_file,
    show_warning,
)

# Locally installed mod metadata


class MetadataManager(QObject):
    _instance: "None | MetadataManager" = None
    mod_created_signal = Signal(str)
    mod_deleted_signal = Signal(str)
    mod_metadata_updated_signal = Signal(str)
    show_warning_signal = Signal(str, str, str, str)

    def __new__(cls, *args: Any, **kwargs: Any) -> "MetadataManager":
        if cls._instance is None:
            cls._instance = super(MetadataManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, settings_controller: SettingsController) -> None:
        if not hasattr(self, "initialized"):
            super(MetadataManager, self).__init__()
            logger.info("Initializing MetadataManager")

            self.settings_controller = settings_controller
            self.steamcmd_wrapper = SteamcmdInterface.instance()

            # Initialize our threadpool for multithreaded parsing
            self.parser_threadpool = QThreadPool.globalInstance()

            # Connect a warning signal for thread-safe prompts
            self.show_warning_signal.connect(show_warning)

            # Store parsed metadata & paths
            self.external_steam_metadata: dict[str, Any] | None = None
            self.external_steam_metadata_path: str | None = None
            self.external_community_rules: dict[str, Any] | None = None
            self.external_community_rules_path: str | None = None
            self.external_user_rules: dict[str, Any] | None = None
            self.external_user_rules_path: str = str(
                AppInfo().databases_folder / "userRules.json"
            )
            # Local metadata
            self.internal_local_metadata: dict[str, Any] = {}
            # Mappers
            self.mod_metadata_file_mapper: dict[str, str] = {}
            self.mod_metadata_dir_mapper: dict[str, str] = {}
            self.packageid_to_uuids: dict[str, set[str]] = {}
            self.steamdb_packageid_to_name: dict[str, str] = {}
            # Empty game version string unless the data is populated
            self.game_version: str = ""
            # SteamCMD .acf file data
            self.steamcmd_acf_data: dict[str, Any] = {}
            # Steam .acf file path / data
            current_instance = self.settings_controller.settings.current_instance
            self.workshop_acf_path: str = str(
                # This is just getting the path 2 directories up from content/294100,
                # so that we can find workshop/appworkshop_294100.acf
                Path(
                    self.settings_controller.settings.instances[
                        current_instance
                    ].workshop_folder
                ).parent.parent
                / "appworkshop_294100.acf",
            )
            self.workshop_acf_data: dict[str, Any] = {}

    @classmethod
    def instance(cls, *args: Any, **kwargs: Any) -> "MetadataManager":
        if cls._instance is None:
            cls._instance = cls(*args, **kwargs)
        elif args or kwargs:
            raise ValueError("MetadataManager instance has already been initialized.")
        return cls._instance

    def __refresh_external_metadata(self) -> None:
        def validate_db_path(path: str, db_type: str) -> bool:
            if not os.path.exists(path):
                self.show_warning_signal.emit(
                    f"{db_type} DB is missing",
                    f"Configured {db_type} DB not found!",
                    f"Unable to initialize external metadata. There is no external {db_type} metadata being factored!\n"
                    + "\nPlease make sure your Database location settings are correct.",
                    f"{path}",
                )
                return False

            if os.path.isdir(path):
                self.show_warning_signal.emit(
                    f"{db_type} DB is missing",
                    f"Configured {db_type} DB path is a directory! Expected a file path.",
                    f"Unable to initialize external metadata. There is no external {db_type} metadata being factored!\n"
                    + "\nPlease make sure your Database location settings are correct.",
                    f"{path}",
                )
                return False

            return True

        def get_configured_steam_db(
            life: int, path: str
        ) -> tuple[dict[str, Any] | None, str | None]:
            logger.info(f"Checking for Steam DB at: {path}")
            if not validate_db_path(path, "Steam"):
                return None, None

            # Look for cached data & load it if available & not expired
            logger.info(
                "Steam DB exists!",
            )
            with open(path, encoding="utf-8") as f:
                json_string = f.read()
                logger.info("Checking metadata expiry against database...")
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
                    if life != 0:  # Disable Notification if value is 0
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

        def get_configured_community_rules_db(
            path: str,
        ) -> tuple[dict[str, Any] | None, str | None]:
            logger.info(f"Checking for Community Rules DB at: {path}")

            if not validate_db_path(path, "Community Rules"):
                return None, None

            # Look for cached data & load it if available & not expired
            logger.info(
                "Community Rules DB exists!",
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
            total_entries = 0
            if self.external_user_rules is not None:
                total_entries = len(self.external_user_rules)
            else:
                logger.warning("Unable to load userRules.json. 'rules' is None")
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
            self.external_user_rules = (
                DEFAULT_USER_RULES["rules"]
                if isinstance(DEFAULT_USER_RULES["rules"], dict)
                else {}
            )

    def __refresh_internal_metadata(self, is_initial: bool = False) -> None:
        def batch_by_data_source(
            data_source: str, mod_directories: list[str]
        ) -> dict[str, Any]:
            """
            Returns a batch of mod path <-> uuid mappings for a given data source.

            Parameters:
                data_source (str): The data source to batch.
                mod_directories (list[str]): A list of mod directories to use to filter items not in that batch.
            """
            return {
                path: self.mod_metadata_dir_mapper.get(path, str(uuid4()))
                for path in mod_directories
            }

        def purge_by_data_source(data_source: str, batch: list[str] = []) -> None:
            """
            Removes all metadata for a given data source.

            Optionally pass a batch of uuids to use to filter items not in the batch.

            Parameters:
                data_source (str): The data source to purge.
                batch (list[str], optional): A list of uuids to use to filter items not in the batch.
            """
            if not batch:  # Purge all metadata for a given data source
                uuids_to_remove = [
                    uuid
                    for uuid, metadata in self.internal_local_metadata.items()
                    if metadata.get("data_source") == data_source
                ]
            else:  # Purge all metadata for a given data source that is not in the batch
                uuids_to_remove = [
                    uuid
                    for uuid, metadata in self.internal_local_metadata.items()
                    if metadata.get("data_source") == data_source and uuid not in batch
                ]
            # If we have uuids to remove
            if uuids_to_remove:
                logger.debug(
                    f"[{data_source}] Purging leftover metadata from directories that no longer exist"
                )
                # Purge metadata from internal metadata
                for uuid in uuids_to_remove:
                    logger.debug(
                        f"Removing metadata for {uuid}: {self.internal_local_metadata.get(uuid)}"
                    )
                    deleted_mod = self.internal_local_metadata.get(uuid)
                    if deleted_mod is None:
                        logger.warning(
                            f"Unable to find metadata for {uuid} in internal metadata, skipping removal. Possible race condition!"
                        )
                        continue

                    deleted_mod_packageid = deleted_mod.get("packageid")
                    self.internal_local_metadata.pop(uuid)

                    if deleted_mod_packageid and self.packageid_to_uuids.get(
                        deleted_mod_packageid
                    ):
                        self.packageid_to_uuids[deleted_mod_packageid].remove(uuid)

        # Get & set Rimworld version string
        game_folder = self.settings_controller.settings.instances[
            self.settings_controller.settings.current_instance
        ].game_folder
        version_file_path = str(game_folder / Path("Version.txt"))
        if os.path.exists(version_file_path):
            try:
                with open(version_file_path, encoding="utf-8") as f:
                    self.game_version = f.read().strip()
                    logger.info(
                        f"Retrieved game version from Version.txt: {self.game_version}"
                    )
            except Exception:
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
                f"\nIs your game path [{self.settings_controller.settings.instances[self.settings_controller.settings.current_instance].game_folder}] set correctly? There should be a Version.txt file in the game install directory.",
                "",
            )
        # Get and cache installed base game / DLC data
        if game_folder and game_folder != Path():
            # Get mod data
            data_path = str(game_folder / Path("Data"))
            logger.info(
                f"Querying Official expansions from RimWorld's Data folder: {data_path}"
            )
            # Scan our Official expansions directory
            expansion_subdirectories = directories(data_path)
            expansions_batch = batch_by_data_source(
                "expansion", expansion_subdirectories
            )
            if not is_initial:
                # Pop any uuids from metadata that are not in the batch - these can be leftover from a previous directory
                purge_by_data_source("expansion", list(expansions_batch.values()))
            # Query the batch
            self.process_batch(
                batch=expansions_batch,
                data_source="expansion",
            )
            # Wait for pool to complete
            self.parser_threadpool.waitForDone()
            self.parser_threadpool.clear()
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
            # Check for and purge any found expansion metadata from cache
            purge_by_data_source("expansion")
        # Get and cache installed local/SteamCMD Workshop mods
        current_instance = self.settings_controller.settings.current_instance
        local_folder = self.settings_controller.settings.instances[
            current_instance
        ].local_folder
        if local_folder and local_folder != "":
            # Get mod data
            logger.info(f"Querying local mods from path: {local_folder}")
            local_subdirectories = directories(local_folder)
            local_batch = batch_by_data_source("local", local_subdirectories)
            if not is_initial:
                # Pop any uuids from metadata that are not in the batch - these can be leftover from a previous directory
                purge_by_data_source("local", list(local_batch.values()))
            # Query the batch
            self.process_batch(
                batch=local_batch,
                data_source="local",
            )
        else:
            logger.debug(
                "Skipping parsing data from empty local mods path. Is the local mods path configured?"
            )
            # Check for and purge any found local mod metadata from cache
            purge_by_data_source("local")
        # Get and cache installed Steam client Workshop mods
        current_instance = self.settings_controller.settings.current_instance
        workshop_folder = self.settings_controller.settings.instances[
            current_instance
        ].workshop_folder
        if workshop_folder and workshop_folder != "":
            logger.info(f"Querying workshop mods from path: {workshop_folder}")
            workshop_subdirectories = directories(workshop_folder)
            workshop_batch = batch_by_data_source("workshop", workshop_subdirectories)
            if not is_initial:
                # Pop any uuids from metadata that are not in the batch - these can be leftover from a previous directory
                purge_by_data_source("workshop", list(workshop_batch.values()))
            # Query the batch
            self.process_batch(
                batch=workshop_batch,
                data_source="workshop",
            )
        else:
            logger.debug(
                "Skipping parsing data from empty workshop mods path. Is the workshop mods path configured?"
            )
            # Check for and purge any found workshop mod metadata from cache
            purge_by_data_source("workshop")
        # Wait for pool to complete
        self.parser_threadpool.waitForDone()
        self.parser_threadpool.clear()
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

    def __update_from_settings(self) -> None:
        self.community_rules_repo = (
            self.settings_controller.settings.external_community_rules_repo
        )
        self.dbs_path = AppInfo().databases_folder
        self.external_community_rules_metadata_source = (
            self.settings_controller.settings.external_community_rules_metadata_source
        )
        self.external_community_rules_file_path = (
            self.settings_controller.settings.external_community_rules_file_path
        )
        self.external_steam_metadata_file_path = (
            self.settings_controller.settings.external_steam_metadata_file_path
        )
        self.external_steam_metadata_source = (
            self.settings_controller.settings.external_steam_metadata_source
        )
        self.steamcmd_acf_path = self.steamcmd_wrapper.steamcmd_appworkshop_acf_path
        self.user_rules_file_path = str(AppInfo().databases_folder / "userRules.json")

    def compile_metadata(self, uuids: list[str] = []) -> None:
        """
        Compile metadata for each expansion or mod, adding new key-values
        describing dependencies, incompatibilities, and load order rules
        compiled from metadata.
        """
        uuids = uuids or list(self.internal_local_metadata.keys())
        logger.info(f"Started compiling metadata for {len(uuids)} mods")

        def process_dependencies(
            uuid: str, dependencies: list[dict[str, str]] | None
        ) -> None:
            """
            Process dependencies for a given mod UUID.
            """
            if isinstance(dependencies, list):
                for dependency in dependencies:
                    if isinstance(dependency, dict) and "packageId" in dependency:
                        package_id = dependency.get("packageId")
                        if package_id:
                            add_dependency_to_mod(
                                self.internal_local_metadata[uuid],
                                package_id,
                                self.internal_local_metadata,
                            )
                            if self.settings_controller.settings.dependency_for_sorting:
                                add_load_rule_to_mod(
                                    self.internal_local_metadata[uuid],
                                    package_id,
                                    "loadTheseBefore",
                                    "loadTheseAfter",
                                    self.internal_local_metadata,
                                    self.packageid_to_uuids,
                                )
                        else:
                            logger.warning(
                                f"Missing packageId in dependency for mod {uuid}: {dependency}"
                            )
                    else:
                        logger.warning(
                            f"Illegal dependency format for mod {uuid}: {dependency}"
                        )

        def process_incompatibilities(uuid: str, incompatibilities: list[str]) -> None:
            """
            Process incompatibilities for a given mod UUID.

            Args:
                uuid (str): The unique identifier for the mod.
                incompatibilities (list[str]): A list of incompatibilities for the mod.
            """
            if not isinstance(incompatibilities, list):
                logger.warning(f"Incompatibilities for mod {uuid} are not a list.")
                return

            for incompatibility in incompatibilities:
                if isinstance(incompatibility, str):
                    add_incompatibility_to_mod(
                        self.internal_local_metadata[uuid],
                        incompatibility,
                        self.internal_local_metadata,
                    )
                else:
                    logger.warning(
                        f"Illegal incompatibility format for mod {uuid}: {incompatibility}"
                    )

        def process_load_order(
            uuid: str, load_these: list[str], rule_type: str, opposite_rule_type: str
        ) -> None:
            """
            Process load order rules for a given mod UUID.

            Args:
                uuid (str): The unique identifier for the mod.
                load_these (list[str]): A list of load order rules for the mod.
                rule_type (str): The type of load order rule.
                opposite_rule_type (str): The opposite type of load order rule.
            """
            if not isinstance(load_these, list):
                logger.warning(f"Load order rules for mod {uuid} are not a list.")
                return

            for load_this in load_these:
                if isinstance(load_this, str):
                    add_load_rule_to_mod(
                        self.internal_local_metadata[uuid],
                        load_this,
                        rule_type,
                        opposite_rule_type,
                        self.internal_local_metadata,
                        self.packageid_to_uuids,
                    )
                else:
                    logger.warning(
                        f"Illegal load order format for mod {uuid}: {load_this}"
                    )

        for uuid in uuids:
            mod_metadata = self.internal_local_metadata.get(uuid)
            if not mod_metadata:
                logger.warning(f"Metadata not found for UUID: {uuid}")
                continue

            logger.debug(f"UUID: {uuid} packageId: {mod_metadata.get('packageId')}")

            # Process moddependencies
            mod_dependencies = mod_metadata.get("moddependencies", {})
            dependencies = mod_dependencies.get("li") if mod_dependencies else None
            process_dependencies(uuid, dependencies)

            # Process moddependenciesbyversion
            dependencies_by_version = mod_metadata.get("moddependenciesbyversion", {})
            major, minor = self.game_version.split(".")[:2]
            version_regex = rf"v{major}\.{minor}"
            for version, deps in dependencies_by_version.items():
                if match(version_regex, version):
                    dependencies = deps.get("li") if deps else None
                    process_dependencies(uuid, dependencies)

            # Process incompatiblewith
            incompatible_with = mod_metadata.get("incompatiblewith", {})
            incompatibilities = (
                incompatible_with.get("li") if incompatible_with else None
            )
            process_incompatibilities(uuid, incompatibilities or [])

            # Process incompatiblewithbyversion
            incompatibilities_by_version = mod_metadata.get(
                "incompatiblewithbyversion", {}
            )
            for version, incs in incompatibilities_by_version.items():
                if match(version_regex, version):
                    incompatibilities = incs.get("li") if incs else None
                    process_incompatibilities(uuid, incompatibilities or [])

            # Process loadafter
            load_after = mod_metadata.get("loadafter", {})
            load_after_list = load_after.get("li") if load_after else None
            process_load_order(
                uuid, load_after_list or [], "loadTheseBefore", "loadTheseAfter"
            )

            # Process forceloadafter
            force_load_after = mod_metadata.get("forceloadafter", {})
            force_load_after_list = (
                force_load_after.get("li") if force_load_after else None
            )
            process_load_order(
                uuid, force_load_after_list or [], "loadTheseBefore", "loadTheseAfter"
            )

            # Process loadafterbyversion
            load_after_by_version = mod_metadata.get("loadafterbyversion", {})
            if load_after_by_version and isinstance(load_after_by_version, dict):
                for version, load_before_by_ver in load_after_by_version.items():
                    if match(version_regex, version):
                        if isinstance(load_before_by_ver, dict):
                            load_before_by_ver_list = (
                                load_before_by_ver.get("li")
                                if load_before_by_ver
                                else None
                            )
                            process_load_order(
                                uuid,
                                load_before_by_ver_list or [],
                                "loadTheseBefore",
                                "loadTheseAfter",
                            )
                        else:
                            logger.warning(
                                f"Invalid format for 'loadafterbyversion' data for mod {uuid}: {load_before_by_ver}"
                            )

            # Process loadbefore
            load_before = mod_metadata.get("loadbefore", {})
            load_before_list = load_before.get("li") if load_before else None
            process_load_order(
                uuid, load_before_list or [], "loadTheseAfter", "loadTheseBefore"
            )

            # Process forceloadbefore
            force_load_before = mod_metadata.get("forceloadbefore", {})
            force_load_before_list = (
                force_load_before.get("li") if force_load_before else None
            )
            process_load_order(
                uuid, force_load_before_list or [], "loadTheseAfter", "loadTheseBefore"
            )

            # Process loadbeforebyversion
            load_before_by_version = mod_metadata.get("loadbeforebyversion", {})
            if isinstance(load_before_by_version, dict):
                for version, load_after_by_ver in load_before_by_version.items():
                    if match(version_regex, version):
                        if isinstance(load_after_by_ver, dict):
                            load_after_by_ver_list = (
                                load_after_by_ver.get("li")
                                if load_after_by_ver
                                else None
                            )
                            process_load_order(
                                uuid,
                                load_after_by_ver_list or [],
                                "loadTheseAfter",
                                "loadTheseBefore",
                            )
                        else:
                            logger.warning(
                                f"Invalid format for 'loadbeforebyversion' data for mod {uuid}: {load_after_by_ver}"
                            )

        logger.info("Finished compiling metadata")
        log_deps_order_info(self.internal_local_metadata)

        if self.external_steam_metadata:
            logger.info("Started compiling metadata from configured SteamDB")
            tracking_dict: dict[str, set[str]] = {}
            steam_id_to_package_id: dict[str, str] = {}

            for publishedfileid, mod_data in self.external_steam_metadata.items():
                db_packageid = mod_data.get("packageId")
                if db_packageid:
                    db_packageid = db_packageid.lower()
                    steam_id_to_package_id[publishedfileid] = db_packageid
                    self.steamdb_packageid_to_name[db_packageid] = mod_data.get("name")
                    potential_uuids = self.packageid_to_uuids.get(db_packageid)
                    if potential_uuids:
                        for uuid in potential_uuids:
                            mod_metadata = self.internal_local_metadata.get(uuid)
                            if (
                                mod_metadata
                                and mod_metadata.get("publishedfileid")
                                == publishedfileid
                            ):
                                dependencies = mod_data.get("dependencies")
                                if dependencies:
                                    tracking_dict.setdefault(uuid, set()).update(
                                        dependencies.keys()
                                    )

            logger.debug(
                f"Tracking {len(steam_id_to_package_id)} SteamDB packageIds for lookup"
            )
            logger.debug(
                f"Tracking Steam dependency data for {len(tracking_dict)} installed mods"
            )

            for (
                installed_mod_uuid,
                set_of_dependency_publishedfileids,
            ) in tracking_dict.items():
                for dependency_steam_id in set_of_dependency_publishedfileids:
                    if dependency_steam_id in steam_id_to_package_id:
                        add_dependency_to_mod_from_steamdb(
                            self.internal_local_metadata[installed_mod_uuid],
                            steam_id_to_package_id[dependency_steam_id],
                            self.internal_local_metadata,
                        )
                    else:
                        logger.debug(
                            f"Unable to lookup Steam AppID/PublishedFileID in Steam metadata: {dependency_steam_id}"
                        )

            logger.info("Finished adding dependencies from SteamDB")
            log_deps_order_info(self.internal_local_metadata)
        else:
            logger.info("No Steam database supplied from external metadata. skipping.")

        def process_external_rules(
            rules: dict[str, Any], rule_type: str, opposite_rule_type: str
        ) -> None:
            """
            Process external load order rules for mods.

            Args:
                rules (dict[str, Any]): A dictionary containing external rules.
                rule_type (str): The type of load order rule.
                opposite_rule_type (str): The opposite type of load order rule.
            """
            for package_id, rule_data in rules.items():
                package_id_lower = package_id.lower()
                if package_id_lower in self.packageid_to_uuids:
                    potential_uuids = self.packageid_to_uuids.get(
                        package_id_lower, set()
                    )
                    load_these = rule_data.get(rule_type)
                    if load_these and isinstance(load_these, list):
                        for load_this in load_these:
                            if isinstance(load_this, str):
                                for uuid in potential_uuids:
                                    add_load_rule_to_mod(
                                        self.internal_local_metadata[uuid],
                                        load_this,
                                        rule_type,
                                        opposite_rule_type,
                                        self.internal_local_metadata,
                                        self.packageid_to_uuids,
                                    )
                            else:
                                logger.warning(
                                    f"Illegal load order format for mod {package_id_lower}: {load_this}"
                                )
                    load_this_bottom = rule_data.get("loadBottom")
                    if load_this_bottom and isinstance(load_this_bottom, list):
                        for load_this in load_this_bottom:
                            if isinstance(load_this, str):
                                for uuid in potential_uuids:
                                    add_load_rule_to_mod(
                                        self.internal_local_metadata[uuid],
                                        load_this,
                                        rule_type,
                                        opposite_rule_type,
                                        self.internal_local_metadata,
                                        self.packageid_to_uuids,
                                    )
                            else:
                                logger.warning(
                                    f"Illegal load order format for mod {package_id_lower}: {load_this}"
                                )
                    load_this_top = rule_data.get("loadTop")
                    if load_this_top and isinstance(load_this_top, list):
                        for load_this in load_this_top:
                            if isinstance(load_this, str):
                                for uuid in potential_uuids:
                                    add_load_rule_to_mod(
                                        self.internal_local_metadata[uuid],
                                        load_this,
                                        rule_type,
                                        opposite_rule_type,
                                        self.internal_local_metadata,
                                        self.packageid_to_uuids,
                                    )
                            else:
                                logger.warning(
                                    f"Illegal load order format for mod {package_id_lower}: {load_this}"
                                )

        if self.external_community_rules:
            logger.info("Started compiling metadata from configured Community Rules")
            process_external_rules(
                self.external_community_rules, "loadBefore", "loadAfter"
            )
            process_external_rules(
                self.external_community_rules, "loadAfter", "loadBefore"
            )
            logger.info("Finished adding dependencies from Community Rules")
            log_deps_order_info(self.internal_local_metadata)
        else:
            logger.info(
                "No Community Rules database supplied from external metadata. skipping."
            )

        if self.external_user_rules:
            logger.info("Started compiling metadata from configured User Rules")
            process_external_rules(self.external_user_rules, "loadBefore", "loadAfter")
            process_external_rules(self.external_user_rules, "loadAfter", "loadBefore")
            logger.info("Finished adding dependencies from User Rules")
            log_deps_order_info(self.internal_local_metadata)
        else:
            logger.info(
                "No User Rules database supplied from external metadata. skipping."
            )

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
    ) -> None:
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
        )
        self.mod_created_signal.emit(uuid)

    def process_deletion(self, data_source: str, mod_directory: str, uuid: str) -> None:
        logger.debug(
            f"Processing deletion for {self.internal_local_metadata.get(uuid, {}).get('name', 'Unknown')}: {mod_directory}"
        )
        deleted_mod = self.internal_local_metadata.get(uuid)
        if deleted_mod is None:
            logger.debug(
                f"Mod {uuid} not found in metadata, skipping deletion. Possible race condition!"
            )
            return

        deleted_mod_packageid = deleted_mod.get("packageid")
        self.internal_local_metadata.pop(uuid, None)
        if deleted_mod_packageid and self.packageid_to_uuids.get(deleted_mod_packageid):
            self.packageid_to_uuids[deleted_mod_packageid].remove(uuid)
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
            uuid=uuid,
        )
        self.parser_threadpool.start(parser)
        # Wait for pool to complete if this is a single update
        if not batch:
            logger.debug("Waiting for metadata update to complete...")
            self.parser_threadpool.waitForDone()
            self.parser_threadpool.clear()
        # Send signal to UI to update mod list if the mod we are updating exists
        if exists and not batch:
            self.compile_metadata(uuids=[uuid])
            self.mod_metadata_updated_signal.emit(uuid)

    def refresh_acf_metadata(
        self, steamclient: bool = True, steamcmd: bool = True
    ) -> None:
        # If we can find the appworkshop_294100.acf files from...
        # ...Steam client
        if steamclient and os.path.exists(self.workshop_acf_path):
            try:
                self.workshop_acf_data = acf_to_dict(self.workshop_acf_path)
                logger.info(
                    f"Successfully parsed Steam client appworkshop.acf metadata from: {self.workshop_acf_path}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to parse Steam client appworkshop.acf metadata from: {self.workshop_acf_path}. Error: {e}"
                )
        # ...SteamCMD
        if steamcmd and os.path.exists(
            self.steamcmd_wrapper.steamcmd_appworkshop_acf_path
        ):
            try:
                self.steamcmd_acf_data = acf_to_dict(
                    self.steamcmd_wrapper.steamcmd_appworkshop_acf_path
                )
                logger.info(
                    f"Successfully parsed SteamCMD appworkshop.acf metadata from: {self.steamcmd_wrapper.steamcmd_appworkshop_acf_path}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to parse SteamCMD appworkshop.acf metadata from: {self.steamcmd_wrapper.steamcmd_appworkshop_acf_path}. Error: {e}"
                )

    def refresh_cache(self, is_initial: bool = False) -> None:
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
            self.__update_from_settings()

        # Update paths from game configuration

        # Populate metadata
        self.refresh_acf_metadata(steamclient=True, steamcmd=True)
        self.__refresh_external_metadata()
        self.__refresh_internal_metadata(is_initial=is_initial)
        self.compile_metadata(uuids=list(self.internal_local_metadata.keys()))

    def steamcmd_purge_mods(self, publishedfileids: set[str]) -> None:
        """
        Removes a mod from SteamCMD install
        """
        # Parse the SteamCMD workshop .acf metadata file
        acf_path = self.steamcmd_wrapper.steamcmd_appworkshop_acf_path
        acf_metadata = acf_to_dict(path=acf_path)
        depotcache_path = self.steamcmd_wrapper.steamcmd_depotcache_path
        # WorkshopItemsInstalled
        workshop_items_installed = acf_metadata.get("AppWorkshop", {}).get(
            "WorkshopItemsInstalled"
        )
        # WorkshopItemDetails
        workshop_item_details = acf_metadata.get("AppWorkshop", {}).get(
            "WorkshopItemDetails"
        )
        # List of mod manifest ids to remove afterward
        mod_manifest_ids = set()
        # Loop through the supplied PublishedFileID's
        for delete_pfid in publishedfileids:
            # Parse the mod manifest id from acf metadata
            if workshop_items_installed is not None:
                mod_manifest_id = workshop_items_installed.get(delete_pfid, {}).get(
                    "manifest"
                )
                if mod_manifest_id is not None:
                    mod_manifest_ids.add(mod_manifest_id)
                workshop_items_installed.pop(delete_pfid, None)

            if workshop_item_details is not None:
                mod_manifest_id = workshop_item_details.get(delete_pfid, {}).get(
                    "manifest"
                )
                if (
                    mod_manifest_id is not None
                    and mod_manifest_id not in mod_manifest_ids
                ):
                    mod_manifest_ids.add(mod_manifest_id)
                workshop_item_details.pop(delete_pfid, None)
        # Save the updated .acf metadata
        dict_to_acf(data=acf_metadata, path=acf_path)
        # Remove the depotcache files if we have manifest id and file(s) exist
        for mod_manifest_id in mod_manifest_ids:
            manifest_path = Path(depotcache_path) / f"294100_{mod_manifest_id}.manifest"
            if manifest_path.exists():
                logger.debug(f"Removing mod manifest file: {manifest_path}")
                try:
                    os.remove(manifest_path)
                except Exception as e:
                    logger.error(e)


class ModParser(QRunnable):
    def __init__(
        self, mod_directory: str, data_source: str, uuid: str, pfid: str = ""
    ) -> None:
        """
        Initialize the ModParser.

        Args:
            mod_directory (str): The directory of the mod.
            data_source (str): The source of the data.
            uuid (str): The unique identifier for the mod.
            pfid (str, optional): The published file ID. Defaults to None.
        """
        self.mod_directory = mod_directory
        self.data_source = data_source
        self.uuid = uuid
        self.pfid = pfid
        self.metadata: dict[str, Any] = {}

    def run(self) -> None:
        self.parse()

    def parse(self) -> dict[str, Any]:
        """
        Parse the mod metadata.

        Returns:
            dict[str, Any]: The parsed metadata.
        """
        try:
            scenario_data_path = os.path.join(self.mod_directory, "About", "About.xml")
            if os.path.exists(scenario_data_path):
                with open(scenario_data_path, "r", encoding="utf-8") as file:
                    scenario_data = file.read()
                scenario_metadata = self._parse_scenario_data(scenario_data)
                if scenario_metadata:
                    scenario_metadata["metadata_file_mtime"] = int(
                        os.path.getmtime(scenario_data_path)
                    )
                    scenario_metadata["uuid"] = self.uuid
                    self.metadata[self.uuid] = scenario_metadata
                else:
                    logger.error(
                        f"Key <savedscenario><scenario> does not exist in this data: {scenario_data}"
                    )
                    self._populate_invalid_mod_entry(data_malformed=True)
            else:
                self._populate_invalid_mod_entry(invalid_about_file_path_found=True)
        except Exception as e:
            logger.error(f"Error parsing mod metadata: {e}")
            self._populate_invalid_mod_entry(data_malformed=True)

        return self.metadata

    def _parse_scenario_data(self, scenario_data: str) -> dict[str, Any] | None:
        """
        Parse the scenario data from the XML content.

        Args:
            scenario_data (str): The XML content of the scenario data.

        Returns:
            dict[str, Any] | None: The parsed scenario metadata or None if parsing fails.
        """
        try:
            # Implement the actual XML parsing logic here
            # For example, using xml.etree.ElementTree or any other XML parser
            parsed_data: dict[str, Any] = {}  # Replace with actual parsing logic
            return parsed_data
        except Exception as e:
            logger.error(f"Error parsing scenario data: {e}")
            return None

    def _populate_invalid_mod_entry(
        self, invalid_about_file_path_found: bool = False, data_malformed: bool = False
    ) -> None:
        """
        Populate the metadata with an invalid mod entry.

        Args:
            invalid_about_file_path_found (bool, optional): Whether the About.xml file path was found to be invalid. Defaults to False.
            data_malformed (bool, optional): Whether the data was found to be malformed. Defaults to False.
        """
        logger.debug(
            f"Invalid dir. Populating invalid mod for path: {self.mod_directory}"
        )
        self.metadata[self.uuid] = {
            "invalid": True,
            "name": "Invalid item",
            "packageid": "invalid.item",
            "authors": "Not found",
            "description": (
                "This mod is considered invalid by RimSort (and the RimWorld game)."
                + "\n\nThis mod does NOT contain an ./About/About.xml and is likely leftover from previous usage."
                + "\n\nThis can happen sometimes with Steam mods if there are leftover .dds textures or unexpected data."
            ),
            "data_source": self.data_source,
            "folder": os.path.basename(self.mod_directory),
            "path": self.mod_directory,
            "internal_time_touched": int(os.path.getmtime(self.mod_directory)),
            "uuid": self.uuid,
        }
        if self.pfid:
            self.metadata[self.uuid].update({"publishedfileid": self.pfid})


# Mod helper functions


def add_dependency_to_mod(
    mod_data: dict[str, Any],
    dependency_or_dependency_ids: Any,
    all_mods: dict[str, Any],
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
            if (
                dependency_or_dependency_ids.get("packageId")
                and not isinstance(dependency_or_dependency_ids["packageId"], list)
                and not isinstance(dependency_or_dependency_ids["packageId"], dict)
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


def add_dependency_to_mod_from_steamdb(
    mod_data: dict[str, Any], dependency_id: Any, all_mods: dict[str, Any]
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


def get_num_dependencies(all_mods: dict[str, Any], key_name: str) -> int:
    """Debug func for getting total number of dependencies"""
    counter = 0
    for mod_data in all_mods.values():
        if mod_data.get(key_name):
            counter = counter + len(mod_data[key_name])
    return counter


def add_incompatibility_to_mod(
    mod_data: dict[str, Any],
    dependency_or_dependency_ids: Any,
    all_mods: dict[str, Any],
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
                    if dependency:  # Sometimes, this can be None or an empty string if XML syntax error/extra elements
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
    mod_data: dict[str, Any],
    dependency_or_dependency_ids: Any,
    explicit_key: str,
    indirect_key: str,
    all_mods: dict[str, Any],
    packageid_to_uuids: dict[str, Any],
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
            f"Load order rules is not a single string/dict/list of strings/dicts: [{dependency_or_dependency_ids}]"
        )
        return

    mod_data.setdefault(explicit_key, set())
    for dep in dependencies:
        if dep in packageid_to_uuids:
            mod_data[explicit_key].add((dep, True))
            potential_dep_uuids = packageid_to_uuids[dep]
            for dep_uuid in potential_dep_uuids:
                all_mods[dep_uuid].setdefault(indirect_key, set()).add(
                    (mod_data["packageid"], False)
                )


def get_mods_from_list(
    mod_list: Union[str, list[str]],
) -> tuple[list[str], list[str], dict[str, Any], list[str]]:
    """
    Given a RimWorld mods list containing a complete list of mods,
    including base game and DLC, as well as their dependencies in order,
    return a list of mods for the active list widget and a list of
    mods for the inactive list widget.

    :param mod_list:
        A path to an .rws/.xml style list, or a list of package ids
        OR a list of mod uuids
    :return: a tuple which contains the active mods dict, inactive mods dict,
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
        # Handle the mod list not existing
        if not os.path.exists(mod_list):
            logger.debug(f"Could not find mods list at: {mod_list}")
            logger.debug("Creating an empty list with available expansions...")
            metadata_manager = MetadataManager.instance()
            game_version = metadata_manager.game_version
            generated_xml = generate_rimworld_mods_list(
                game_version, ["Ludeon.RimWorld"]
            )
            logger.debug(f"Saving new mods list to: {mod_list}")
            json_to_xml_write(generated_xml, mod_list)
        # Parse the ModsConfig.xml activeMods list
        logger.info(f"Retrieving active mods from RimWorld mod list: {mod_list}")
        mod_data = xml_path_to_json(mod_list)
        package_ids_to_import = validate_rimworld_mods_list(mod_data)
    elif isinstance(mod_list, list):
        logger.info("Retrieving active mods from the provided list of package ids")
        package_ids_to_import = mod_list
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


def log_deps_order_info(all_mods: dict[str, Any]) -> None:
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
        output_database_path: str = "",
        get_appid_deps: bool = False,
        update: bool = False,
        mods: dict[str, Any] = {},
    ):
        QThread.__init__(self)
        self.apikey = apikey
        self.appid = appid
        self.database_expiry = database_expiry
        self.get_appid_deps = get_appid_deps
        self.mode = mode
        self.mods = mods
        self.output_database_path = output_database_path
        self.publishedfileids: list[str] = []
        self.update = update

    def run(self) -> None:
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
                    len(dynamic_query.publishedfileids) == 0
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

    def _init_db_from_local_metadata(self) -> dict[str, Any]:
        db_from_local_metadata = {
            "version": 0,
            "database": {
                **{
                    v["appid"]: {
                        "appid": True,
                        "url": f'https://store.steampowered.com/app/{v["appid"]}',
                        "packageId": v.get("packageid"),
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
        total = (
            len(db_from_local_metadata["database"].keys())
            if isinstance(db_from_local_metadata["database"], dict)
            else 0
        )
        self.db_builder_message_output_signal.emit(
            f"Populated {total} items from locally found metadata into initial database for "
            + f"{self.appid}"
        )
        return db_from_local_metadata

    def _init_empty_db_from_publishedfileids(
        self, publishedfileids: list[str]
    ) -> dict[str, Any]:
        database: dict[str, int | dict[str, Any]] = {
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
        total = (
            len(database["database"].keys())
            if isinstance(database["database"], dict)
            else 0
        )
        self.db_builder_message_output_signal.emit(
            f"\nPopulated {total} items queried from Steam Workshop into initial database for AppId {self.appid}"
        )
        return database

    def _output_database(self, database: dict[str, Any]) -> None:
        # If user-configured `update` parameter, update old db with new query data recursively
        if self.update and os.path.exists(self.output_database_path):
            self.db_builder_message_output_signal.emit(
                f"\nIn-place DB update configured. Existing DB to update:\n{self.output_database_path}"
            )
            if self.output_database_path and os.path.exists(self.output_database_path):
                with open(self.output_database_path, encoding="utf-8") as f:
                    json_string = f.read()
                    self.db_builder_message_output_signal.emit(
                        "\nReading info from file..."
                    )
                    db_to_update = json.loads(json_string)
                    self.db_builder_message_output_signal.emit(
                        "Retrieved cached database!\n"
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


def check_if_pfids_blacklisted(
    publishedfileids: list[str], steamdb: dict[str, Any]
) -> list[str]:
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
        elif steamdb.get(str(publishedfileid), {}).get(
            "blacklist"
        ):  # TODO: Is this needed?
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
            for publishedfileid in list(blacklisted_mods.keys()):
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
        logger.debug("Reading info...")
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
        logger.debug("Reading info...")
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


def query_workshop_update_data(mods: dict[str, Any]) -> str | None:
    """
    Query Steam WebAPI for update data, for any workshop mods that have a 'publishedfileid'
    attribute contained in their mod_data, and from there, populate mod_json_data with it.

    Append mod update data found for Steam Workshop mods to internal metadata

    :param mods: A dict equivalent to 'all_mods' or mod_list.get_list_items_by_dict() in
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

    return None


def recursively_update_dict(
    a_dict: dict[str, Any],
    b_dict: dict[str, Any],
    prune_exceptions: Iterable[str] = [],
    purge_keys: Iterable[str] = [],
    recurse_exceptions: Iterable[str] = [],
) -> None:
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
