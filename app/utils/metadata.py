import gzip
import json
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from re import match
from time import localtime, strftime, time
from typing import Any, Callable, Iterable, Union
from uuid import uuid4

from loguru import logger
from natsort import natsorted
from PySide6.QtCore import (
    QCoreApplication,
    QObject,
    QRunnable,
    QThread,
    QThreadPool,
    Signal,
)

from app.controllers.settings_controller import SettingsController
from app.utils.acf_utils import refresh_acf_metadata
from app.utils.app_info import AppInfo
from app.utils.constants import (
    DB_BUILDER_PRUNE_EXCEPTIONS,
    DB_BUILDER_RECURSE_EXCEPTIONS,
    DEFAULT_MISSING_PACKAGEID,
    RIMWORLD_DLC_METADATA,
)
from app.utils.generic import directories, scanpath
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

# Metadata loader source constants
SOURCE_FILE_PATH = "Configured file path"
SOURCE_GIT_REPO = "Configured git repository"
SOURCE_DISABLED = "Disabled"

# Metadata file names
STEAM_DB_FILE = "steamDB.json"
COMMUNITY_RULES_FILE = "communityRules.json"
NO_VERSION_WARNING_FILE = "ModIdsToFix.xml"
USE_THIS_INSTEAD_FILE = "replacements.json.gz"


class ModReplacement:
    def __init__(
        self,
        name: str,
        author: str,
        packageid: str,
        pfid: str,
        supportedversions: list[str],
        source: str = "database",
    ):
        self.name = name
        self.author = author
        self.packageid = packageid
        self.pfid = pfid
        self.supportedversions = supportedversions
        self.source = source


# TODO: Someday, it is probably worth typing out the keys
# For now, I'm creating this alias to make it clear in new code what this represents.
ModMetadata = dict[str, Any]


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
            self.external_no_version_warning: list[str] | None = None
            self.external_no_version_warning_path: str | None = None
            self.external_use_this_instead_replacements: dict[str, Any] | None = None
            self.external_user_rules: dict[str, Any] | None = None
            self.external_user_rules_path: str = str(AppInfo().user_rules_file)
            # Local metadata
            self.internal_local_metadata: dict[str, Any] = {}
            # Track mods with missing packageIds for user notification
            self.mods_with_missing_packageid: list[str] = []
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

    def _emit_db_error(self, db_type: str, title: str, message: str, path: str) -> None:
        """Emit a database validation error signal."""
        self.show_warning_signal.emit(
            self.tr(title),
            self.tr(message),
            self.tr(message),
            path,
        )

    def _validate_db_path(
        self, path: str, db_type: str, expect_directory: bool = False
    ) -> bool:
        """Validate that a database path exists and matches expected type."""
        if not os.path.exists(path):
            self._emit_db_error(
                db_type,
                f"{db_type} DB is missing",
                f"Configured {db_type} DB not found!\n"
                + "Unable to initialize external metadata. There is no external {db_type} metadata being factored!\n"
                + "\nPlease make sure your Database location settings are correct.",
                path,
            )
            return False

        is_dir = os.path.isdir(path)
        if is_dir != expect_directory:
            path_type = "directory" if expect_directory else "file"
            self._emit_db_error(
                db_type,
                f"{db_type} DB is missing",
                f"Configured {db_type} DB path is {'a' if expect_directory else 'not a'} {path_type}! Expected a {'directory' if expect_directory else 'file'} path.\n"
                + "Unable to initialize external metadata. There is no external {db_type} metadata being factored!\n"
                + "\nPlease make sure your Database location settings are correct.",
                path,
            )
            return False

        return True

    def _load_json_file(self, path: str) -> dict[str, Any] | None:
        """Load JSON from file with error handling."""
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load JSON from {path}: {e}")
            return None

    def _load_use_this_instead_file(self, path: Path) -> dict[str, Any] | None:
        """Load Use This Instead DB, handling both .gz and regular JSON files."""
        try:
            if path.suffix == ".gz":
                with gzip.open(str(path), "rt", encoding="utf-8-sig") as f:
                    return json.load(f)
            else:
                with open(str(path), "r", encoding="utf-8-sig") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load Use This Instead DB from {path}: {e}")
            return None

    def _get_repo_path(self, repo_path: str, file_name: str, subdir: str = "") -> str:
        """Construct path for git repository metadata file."""
        base_path = AppInfo().databases_folder / Path(os.path.split(repo_path)[1])
        if subdir:
            base_path = base_path / subdir
        return str(base_path / file_name)

    def _load_metadata_by_source(
        self,
        source: str,
        file_path: str,
        repo_path: str,
        file_name: str,
        getter_func: Callable[[str], tuple[Any, str | None]],
        subdir: str = "",
    ) -> tuple[Any, str | None]:
        """Load metadata from either file path or git repository.

        Args:
            source: SOURCE_FILE_PATH, SOURCE_GIT_REPO, or SOURCE_DISABLED
            file_path: Path to file when using SOURCE_FILE_PATH
            repo_path: Path to git repo when using SOURCE_GIT_REPO
            file_name: Name of the file to load (e.g., 'steamDB.json')
            getter_func: Callable that loads and validates the file at given path
            subdir: Optional subdirectory within git repo path

        Returns:
            Tuple of (loaded_data, path_used) or (None, None) if disabled
        """
        if source == SOURCE_FILE_PATH:
            return getter_func(file_path)
        elif source == SOURCE_GIT_REPO:
            path = self._get_repo_path(repo_path, file_name, subdir)
            return getter_func(path)
        else:
            logger.info(f"{file_name} metadata disabled by user.")
            return None, None

    def _load_user_rules(self) -> None:
        """Load user rules from file, creating default if missing."""
        path = Path(self.external_user_rules_path)

        if path.exists():
            logger.info("Loading userRules.json")
            rule_data = self._load_json_file(str(path))

            if rule_data is None:
                logger.warning("Unable to parse userRules.json")
                return

            rules: Any = rule_data.get("rules") if rule_data else None
            if isinstance(rules, dict):
                self.external_user_rules = rules
            else:
                self.external_user_rules = None
            total_entries = (
                len(self.external_user_rules) if self.external_user_rules else 0
            )
            if self.external_user_rules is None:
                logger.warning(
                    "Unable to load userRules.json. 'rules' is None or not a dict"
                )
            logger.info(
                f"Loaded {total_entries} additional sorting rules from User Rules"
            )

    def _load_steam_db(
        self, life: int, path: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Load and validate Steam database with expiry checking.

        NOTE: Steam DB has special handling for expired data - it will still be loaded
        and used even if past the configured expiry time, but a warning is emitted to
        the user. Other databases fail if missing/invalid.

        Args:
            life: Database expiry time in seconds (0 = never expire)
            path: Path to Steam DB JSON file

        Returns:
            Tuple of (database_dict, path) or (None, None) if validation fails
        """
        logger.info(f"Checking for Steam DB at: {path}")
        if not self._validate_db_path(path, "Steam"):
            return None, None

        logger.info("Steam DB exists!")
        db_data = self._load_json_file(path)
        if db_data is None:
            return None, None

        current_time = int(time())
        db_time = int(db_data.get("version", 0))
        elapsed = current_time - db_time
        is_valid = elapsed <= life

        if not is_valid and life != 0:
            self.show_warning_signal.emit(
                self.tr("Steam DB metadata expired"),
                self.tr("Steam DB is expired! Consider updating!\n"),
                self.tr(
                    "Steam DB last updated: {last_updated}\n\n"
                    + "Falling back to cached, but EXPIRED Steam Database..."
                ).format(
                    last_updated=strftime(
                        "%Y-%m-%d %H:%M:%S",
                        localtime(db_time),
                    )
                ),
                "",
            )

        db_json_data = db_data.get("database", {})
        total_entries = len(db_json_data)
        logger.info(
            f"Loaded metadata for {total_entries} Steam Workshop mods from Steam DB"
        )

        # Build packageid to name mapping for faster lookups
        self.steamdb_packageid_to_name = {
            metadata["packageid"]: metadata["name"]
            for metadata in db_json_data.values()
            if metadata.get("packageid") and metadata.get("name")
        }

        return db_json_data, path

    def _load_steam_metadata(self, settings: Any) -> None:
        """Load Steam database metadata from configured source."""
        steam_source = settings.external_steam_metadata_source
        self.external_steam_metadata, self.external_steam_metadata_path = (
            self._load_metadata_by_source(
                steam_source,
                settings.external_steam_metadata_file_path,
                settings.external_steam_metadata_repo,
                STEAM_DB_FILE,
                lambda p: self._load_steam_db(settings.database_expiry, p),
            )
            if steam_source != SOURCE_DISABLED
            else (None, None)
        )

    def _load_community_rules_db(
        self, path: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Load and validate Community Rules database."""
        logger.info(f"Checking for Community Rules DB at: {path}")
        if not self._validate_db_path(path, "Community Rules"):
            return None, None

        logger.info("Community Rules DB exists!")
        rule_data = self._load_json_file(path)
        if rule_data is None:
            return None, None

        community_rules_json_data = rule_data.get("rules", {})
        total_entries = len(community_rules_json_data)
        logger.info(
            f"Loaded {total_entries} additional sorting rules from Community Rules"
        )
        return community_rules_json_data, path

    def _load_community_rules_metadata(self, settings: Any) -> None:
        """Load Community Rules metadata from configured source."""
        rules_source = settings.external_community_rules_metadata_source
        self.external_community_rules, self.external_community_rules_path = (
            self._load_metadata_by_source(
                rules_source,
                settings.external_community_rules_file_path,
                settings.external_community_rules_repo,
                COMMUNITY_RULES_FILE,
                self._load_community_rules_db,
            )
            if rules_source != SOURCE_DISABLED
            else (None, None)
        )

    def _load_no_version_warning_db(
        self, path: str
    ) -> tuple[list[str] | None, str | None]:
        """Load and validate No Version Warning database."""
        logger.info(f'Checking for "No Version Warning" DB at: {path}')
        if not self._validate_db_path(path, "No Version Warning"):
            return None, None

        logger.info("No Version Warning DB exists, loading")
        no_version_warning_json_data = xml_path_to_json(path)
        total_entries = len(no_version_warning_json_data)
        logger.info(
            f'Loaded {total_entries} compatibility version overrides from "No Version Warning"'
        )
        return list(
            map(
                str.lower,
                no_version_warning_json_data.get("ModIdsToFix", {}).get("li", []),
            )
        ), path

    def _load_no_version_warning_metadata(self, settings: Any) -> None:
        """Load 'No Version Warning' metadata from configured source."""
        no_version_source = settings.external_no_version_warning_metadata_source
        self.external_no_version_warning, self.external_no_version_warning_path = (
            self._load_metadata_by_source(
                no_version_source,
                settings.external_no_version_warning_file_path,
                settings.external_no_version_warning_repo_path,
                NO_VERSION_WARNING_FILE,
                self._load_no_version_warning_db,
                subdir=self.game_version[:3],
            )
            if no_version_source != SOURCE_DISABLED
            else (None, None)
        )

    def _load_use_this_instead_db(
        self, path: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Load and validate Use This Instead database."""
        logger.info(f"Checking for Use This Instead DB at: {path}")
        if not self._validate_db_path(path, "Use This Instead"):
            return None, None

        logger.info("Use This Instead DB exists!")
        db_data = self._load_use_this_instead_file(Path(path))
        if db_data is None:
            return None, None

        total_entries = len(db_data)
        logger.info(
            f"Loaded metadata for {total_entries} mod replacements from Use This Instead DB"
        )
        return db_data, path

    def _load_use_this_instead_metadata(self, settings: Any) -> None:
        """Load 'Use This Instead' metadata from configured source."""
        use_instead_source = settings.external_use_this_instead_metadata_source
        self.external_use_this_instead_replacements, _ = (
            self._load_metadata_by_source(
                use_instead_source,
                settings.external_use_this_instead_file_path,
                settings.external_use_this_instead_repo_path,
                USE_THIS_INSTEAD_FILE,
                self._load_use_this_instead_db,
            )
            if use_instead_source != SOURCE_DISABLED
            else (None, None)
        )

    def __read_game_version(self) -> None:
        """Read game version from Version.txt file.

        This must be called before loading external metadata like "No Version Warning"
        since those loaders may depend on the game version for constructing file paths.
        """
        settings_instance = self.settings_controller.settings.instances[
            self.settings_controller.settings.current_instance
        ]
        game_folder = settings_instance.game_folder
        version_file_path = game_folder / Path("Version.txt")

        if version_file_path.exists():
            try:
                self.game_version = version_file_path.read_text(
                    encoding="utf-8"
                ).strip()
                logger.info(
                    f"Retrieved game version from Version.txt: {self.game_version}"
                )
            except Exception as e:
                logger.error(
                    f"Unable to parse Version.txt from game folder: {version_file_path}: {e}"
                )
        else:
            logger.error(
                f"The provided Version.txt path does not exist: {version_file_path}"
            )
            self.show_warning_signal.emit(
                self.tr("Missing Version.txt"),
                self.tr(
                    "RimSort is unable to get the game version at the expected path: [{version_file_path}]."
                ).format(version_file_path=str(version_file_path)),
                self.tr(
                    "\nIs your game path {folder} set correctly? There should be a Version.txt file in the game install directory."
                ).format(folder=game_folder),
                "",
            )

    def __refresh_external_metadata(self) -> None:
        """Load all external metadata from configured sources.

        Uses ThreadPoolExecutor for parallel loading of independent metadata sources.
        All threads are awaited before method returns to ensure data consistency.
        """
        logger.info("Starting external metadata refresh...")
        settings = self.settings_controller.settings

        # Load metadata sources in parallel
        futures = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures.append(executor.submit(self._load_user_rules))
            futures.append(executor.submit(self._load_steam_metadata, settings))
            futures.append(
                executor.submit(self._load_community_rules_metadata, settings)
            )
            futures.append(
                executor.submit(self._load_no_version_warning_metadata, settings)
            )
            futures.append(
                executor.submit(self._load_use_this_instead_metadata, settings)
            )

        # Wait for all threads to complete with error handling
        loader_names = [
            "User Rules",
            "Steam Database",
            "Community Rules",
            "No Version Warning",
            "Use This Instead",
        ]
        completed_count = 0

        for idx, future in enumerate(futures):
            try:
                future.result(timeout=30)  # 30 second timeout per loader
                completed_count += 1
            except TimeoutError:
                logger.error(f"External metadata loader timed out: {loader_names[idx]}")
            except Exception as e:
                logger.error(
                    f"External metadata loader failed ({loader_names[idx]}): {e}"
                )

        logger.info(
            f"External metadata refresh completed ({completed_count}/{len(futures)} loaders successful)"
        )

    def __refresh_internal_metadata(self, is_initial: bool = False) -> None:
        """
        Refresh all internal mod metadata from the file system.

        This method performs a complete scan of all mod directories (expansions, local, and workshop),
        parsing metadata for each discovered mod. It maintains consistency between internal metadata
        state and the file system by:

        1. Reading game version from Version.txt for DLC/base game compatibility
        2. Scanning three data sources for mods:
           - Expansion: Official RimWorld DLC and base game content
           - Local: Locally installed mods (SteamCMD)
           - Workshop: Steam Workshop mods
        3. Purging metadata for mods that no longer exist on disk
        4. Rebuilding path-to-uuid mappers used by file watchers

        On initial load (`is_initial=True`), orphaned metadata is not purged. On subsequent refreshes,
        only mods found in the current file system scan are retained for each data source.

        Parameters:
            is_initial (bool): If True, skip purging to preserve any existing metadata during initialization.
                              If False (default), purge metadata for mods no longer present on disk.
        """

        def batch_by_data_source(
            data_source: str, mod_directories: list[str]
        ) -> dict[str, str]:
            """
            Create a batch of mod path <-> uuid mappings for discovered directories.

            For each discovered directory, retrieves an existing UUID from the mapper or generates
            a new one. This ensures consistent UUID assignment across refreshes, allowing mods to
            be tracked even as their physical locations may change.

            Parameters:
                data_source (str): The data source type (expansion, local, or workshop).
                                  Used for filtering and logging purposes.
                mod_directories (list[str]): List of absolute directory paths discovered in the file system.

            Returns:
                dict[str, str]: Mapping of directory path to UUID. New UUIDs are generated for
                               previously unknown directories; existing UUIDs are reused from the mapper.
            """
            mapper = self.mod_metadata_dir_mapper
            return {path: mapper.get(path, str(uuid4())) for path in mod_directories}

        def purge_by_data_source(
            data_source: str, batch: dict[str, str] | None = None
        ) -> None:
            """
            Remove metadata for mods that no longer exist in the file system.

            When refreshing metadata, this function identifies and removes any stored metadata
            entries for mods that:
            1. Belong to a specific data source (expansion, local, or workshop)
            2. Are NOT in the current batch of discovered directories

            This keeps internal metadata in sync with the actual file system state. Also updates
            the packageid_to_uuids index to maintain referential integrity.

            Parameters:
                data_source (str): The data source type to filter by (expansion, local, or workshop).
                batch (dict[str, str], optional): A dict mapping discovered paths to their UUIDs.
                                                 If provided, only mods NOT in this batch are purged.
                                                 If None, ALL metadata for the data_source is purged.

            Notes:
                - Uses optimized list comprehension with early branch for batch existence
                - Handles race conditions where metadata may be deleted during iteration
                - Updates packageid_to_uuids index when removing mods with packageids
            """
            # Collect uuids to remove
            batch_uuids = set(batch.values()) if batch else None
            internal_meta = self.internal_local_metadata

            # Optimized filtering: branch on batch_uuids to avoid ternary check in hot loop
            # When batch is None (full purge), simpler comprehension; when batch exists, exclude members
            if batch_uuids is None:
                # Full purge: remove all metadata for this data_source
                uuids_to_remove = [
                    uuid
                    for uuid, metadata in internal_meta.items()
                    if metadata.get("data_source") == data_source
                ]
            else:
                # Selective purge: remove only metadata NOT in current batch (file system state)
                uuids_to_remove = [
                    uuid
                    for uuid, metadata in internal_meta.items()
                    if metadata.get("data_source") == data_source
                    and uuid not in batch_uuids
                ]

            # Early return if nothing to purge
            if not uuids_to_remove:
                return

            logger.debug(
                f"[{data_source}] Purging {len(uuids_to_remove)} leftover metadata entries"
            )

            # Remove metadata entries and update reverse indices
            packageid_to_uuids = self.packageid_to_uuids
            for uuid in uuids_to_remove:
                deleted_mod = internal_meta.pop(uuid, None)
                if deleted_mod is None:
                    # Race condition: another thread may have already deleted this entry
                    logger.warning(
                        f"Unable to find metadata for {uuid} in internal metadata. Possible race condition!"
                    )
                    continue

                # Maintain packageid_to_uuids reverse index consistency
                if deleted_mod_packageid := deleted_mod.get("packageid"):
                    if packageid_uuids := packageid_to_uuids.get(deleted_mod_packageid):
                        packageid_uuids.discard(uuid)

        # ===== INITIALIZATION =====
        # Cache settings instance to avoid repeated attribute lookups
        settings_instance = self.settings_controller.settings.instances[
            self.settings_controller.settings.current_instance
        ]
        game_folder = settings_instance.game_folder

        # ===== GAME VERSION DETECTION =====
        # Game version is already loaded by __read_game_version() before this method is called.
        # This ensures external metadata loaders can use it for path construction (e.g., No Version Warning).

        def process_data_source_folder(
            data_source: str, folder_path: Path | str | None, subfolder: str = ""
        ) -> None:
            """
            Scan a data source folder and update metadata for all discovered mods.

            This function handles the complete lifecycle of processing a single data source:
            1. Validates the folder path exists and is configured
            2. Discovers all subdirectories (each represents a mod)
            3. Generates or reuses UUIDs for consistent tracking
            4. Removes metadata for mods no longer present (unless initial load)
            5. Queues batch processing via thread pool

            Parameters:
                data_source (str): The data source type (expansion, local, or workshop).
                                  Controls logging level and data source filtering.
                folder_path (Path | str | None): The root folder containing mods.
                                                 Can be None or empty Path if not configured.
                subfolder (str, optional): Optional subdirectory to scan within folder_path.
                                          Used for expansion data which is in the "Data" subfolder.

            Notes:
                - Returns early if folder_path is not configured (None or empty)
                - Returns early if no subdirectories found (prevents unnecessary processing)
                - On initial load, metadata is not purged to preserve state
                - Processing is queued asynchronously via self.process_batch()
            """
            # Check if folder path is empty
            if not folder_path or folder_path == Path():
                log_func = logger.error if data_source == "expansion" else logger.debug
                log_func(
                    f"Skipping parsing data from empty {data_source} path. Is the {data_source} path configured?"
                )
                purge_by_data_source(data_source)
                return

            # Construct folder path
            folder_to_scan = Path(folder_path)
            if subfolder:
                folder_to_scan = folder_to_scan / subfolder

            logger.info(f"Querying {data_source} from path: {folder_to_scan}")
            subdirectories = directories(str(folder_to_scan))

            # Skip processing if no subdirectories found
            if not subdirectories:
                logger.debug(f"No subdirectories found in {folder_to_scan}")
                purge_by_data_source(data_source)
                return

            batch = batch_by_data_source(data_source, subdirectories)

            if not is_initial:
                purge_by_data_source(data_source, batch)
            self.process_batch(batch=batch, data_source=data_source)

        # ===== METADATA SCANNING =====
        # Scan three data sources for mods, each queued for concurrent parsing via threadpool

        # Process official RimWorld content (Base game + DLC)
        process_data_source_folder("expansion", game_folder, "Data")

        # Process locally installed mods (SteamCMD, manual installs)
        process_data_source_folder("local", settings_instance.local_folder)

        # Process Steam Workshop mods
        process_data_source_folder("workshop", settings_instance.workshop_folder)

        # ===== THREAD SYNCHRONIZATION =====
        # Wait for all queued metadata parsing tasks to complete before rebuilding mappers
        # This ensures all internal_local_metadata updates are visible before we rebuild indices
        self.parser_threadpool.waitForDone()
        self.parser_threadpool.clear()

        # ===== MAPPER RECONSTRUCTION =====
        # Rebuild path-to-uuid mapping indices used by file watchers for change detection
        # Single pass through metadata builds both file mapper and directory mapper simultaneously
        file_mapper = {}
        dir_mapper = {}
        for uuid, metadata in self.internal_local_metadata.items():
            if mfp := metadata.get("metadata_file_path"):
                file_mapper[mfp] = uuid
            if mp := metadata.get("path"):
                dir_mapper[mp] = uuid

        self.mod_metadata_file_mapper = file_mapper
        self.mod_metadata_dir_mapper = dir_mapper

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

    def supplement_dlc_metadata(self, uuid: str) -> None:
        """
        Normalize metadata for official RimWorld content (Core + DLC).

        Applies canonical fields (name, steam_url, description, appid) and ensures
        a default supportedversions if missing. Safe to call for any UUID.
        """
        mod = self.internal_local_metadata.get(uuid)
        if not mod:
            return
        # Only adjust for entries parsed from the game's Data folder
        if mod.get("data_source") != "expansion":
            return
        package_id = mod.get("packageid")
        if not isinstance(package_id, str):
            return
        # Map packageId -> appid
        package_to_app = {
            v["packageid"]: appid for appid, v in RIMWORLD_DLC_METADATA.items()
        }
        appid = package_to_app.get(package_id)
        if not appid:
            return
        dlc_meta = RIMWORLD_DLC_METADATA[appid]
        # Ensure supportedversions exists and is sane
        if not isinstance(mod.get("supportedversions"), dict):
            version = (
                ".".join(self.game_version.split(".")[:2])
                if self.game_version
                else None
            )
            if version:
                mod["supportedversions"] = {"li": version}
            else:
                mod.pop("supportedversions", None)
        # Apply canonical fields
        mod.update(
            {
                "appid": appid,
                "name": dlc_meta["name"],
                "steam_url": dlc_meta["steam_url"],
                "description": dlc_meta["description"],
            }
        )

    def compile_metadata(self, uuids: list[str] = []) -> None:
        """
        Iterate through each expansion or mod and add new key-values describing the
        dependencies, incompatibilities, and load order rules compiled from metadata.

        About.xml ByVersion precedence (controlled by settings.prefer_versioned_about_tags):
        - Toggle OFF: Ignore all ByVersion tags entirely; use only base tags
          (preserves pre-ByVersion behavior).
        - Toggle ON: For each supported tag group (descriptionsByVersion,
          modDependenciesByVersion, incompatibleWithByVersion, loadAfterByVersion,
          loadBeforeByVersion):
          * If a matching key for current v<major>.<minor> exists and has content,
            use only that versioned value and suppress the base tag (non-additive).
          * If a matching key exists but is empty/invalid, treat as "no requirement"
            for this version and suppress the base tag.
          * If a ByVersion block exists but there is no matching key, fall back to
            the base tag for that group.
          * If the game version cannot be parsed, treat as "no matching key".
        All collections (dependencies, incompatibilities, load rules) are sets, so
        repeated additions from base/versioned paths do not duplicate.
        """
        # Compile metadata for all mods if uuids is None
        uuids = uuids or list(self.internal_local_metadata.keys())
        logger.info(f"Started compiling metadata for {len(uuids)} mods")

        # Add dependencies to installed mods based on dependencies listed in About.xml TODO manifest.xml
        logger.info("Started compiling metadata from About.xml")
        # Go through each mod and add dependencies
        dependencies = None
        for uuid in uuids:
            # Toggle: prefer versioned About.xml tags over base tags
            prefer_versioned = False
            try:
                prefer_versioned = (
                    self.settings_controller.settings.prefer_versioned_about_tags
                )
            except Exception:
                prefer_versioned = False
            # Normalize DLC/base game entries so they always show canonical names
            try:
                self.supplement_dlc_metadata(uuid)
            except Exception as e:
                logger.debug(f"supplement_dlc_metadata failed for {uuid}: {e}")
            logger.debug(
                f"UUID: {uuid} packageid: "
                + self.internal_local_metadata[uuid].get("packageid")
            )
            # Prefer descriptionsByVersion over base description if enabled
            if prefer_versioned and self.internal_local_metadata[uuid].get(
                "descriptionsbyversion"
            ):
                try:
                    major, minor = self.game_version.split(".")[:2]
                    version_regex = rf"v{major}\.{minor}"
                except Exception:
                    version_regex = None
                if version_regex:
                    for version, desc_by_ver in self.internal_local_metadata[uuid][
                        "descriptionsbyversion"
                    ].items():
                        if match(version_regex, version):
                            if isinstance(desc_by_ver, str):
                                self.internal_local_metadata[uuid]["description"] = (
                                    desc_by_ver
                                )
                                logger.debug(
                                    "Prefer versioned tags: using descriptionsByVersion over base description"
                                )
                            else:
                                # Empty or invalid means override to empty description
                                self.internal_local_metadata[uuid]["description"] = ""
                                logger.debug(
                                    "Prefer versioned tags: descriptionsByVersion present but empty; clearing base description"
                                )
                            break
            # modDependencies and modDependenciesByVersion with precedence
            base_deps = None
            if self.internal_local_metadata[uuid].get("moddependencies"):
                if isinstance(
                    self.internal_local_metadata[uuid]["moddependencies"], dict
                ):
                    base_deps = self.internal_local_metadata[uuid][
                        "moddependencies"
                    ].get("li")
                elif isinstance(
                    self.internal_local_metadata[uuid]["moddependencies"], list
                ):
                    for potential_dependencies in self.internal_local_metadata[uuid][
                        "moddependencies"
                    ]:
                        if (
                            potential_dependencies
                            and isinstance(potential_dependencies, dict)
                            and potential_dependencies.get("li")
                        ):
                            base_deps = potential_dependencies["li"]

            matched_versioned_deps = None
            version_key_matched = False
            if self.internal_local_metadata[uuid].get("moddependenciesbyversion"):
                try:
                    major, minor = self.game_version.split(".")[:2]
                    version_regex = rf"v{major}\.{minor}"
                except Exception:
                    version_regex = None
                if version_regex:
                    for version, deps_by_ver in self.internal_local_metadata[uuid][
                        "moddependenciesbyversion"
                    ].items():
                        if match(version_regex, version):
                            version_key_matched = True
                            if (
                                deps_by_ver
                                and isinstance(deps_by_ver, dict)
                                and deps_by_ver.get("li")
                            ):
                                matched_versioned_deps = deps_by_ver.get("li")
                            else:
                                matched_versioned_deps = []
                            break

            if prefer_versioned and version_key_matched:
                if matched_versioned_deps:
                    logger.debug(
                        f"Current mod requires these mods by version to work: {matched_versioned_deps}"
                    )
                    add_dependency_to_mod(
                        self.internal_local_metadata[uuid],
                        matched_versioned_deps,
                        self.internal_local_metadata,
                    )
                else:
                    logger.debug(
                        "Prefer versioned tags: dependencies key present for this version but empty; suppressing base modDependencies"
                    )
            else:
                if base_deps:
                    logger.debug(
                        f"Current mod requires these mods to work: {base_deps}"
                    )
                    add_dependency_to_mod(
                        self.internal_local_metadata[uuid],
                        base_deps,
                        self.internal_local_metadata,
                    )
                # prefer_versioned is disabled: ignore versioned deps entirely and rely on base only
            # incompatibleWith + incompatibleWithByVersion precedence
            # Found an example: 'incompatiblewith': {'li': ['majorhoff.rimthreaded', 'nova.rimworldtogether']}
            base_incompat = None
            if self.internal_local_metadata[uuid].get(
                "incompatiblewith"
            ) and isinstance(
                self.internal_local_metadata[uuid].get("incompatiblewith"), dict
            ):
                base_incompat = self.internal_local_metadata[uuid][
                    "incompatiblewith"
                ].get("li")

            matched_versioned_incompat = None
            version_key_matched_incompat = False
            if self.internal_local_metadata[uuid].get("incompatiblewithbyversion"):
                try:
                    major, minor = self.game_version.split(".")[:2]
                    version_regex = rf"v{major}\.{minor}"
                except Exception:
                    version_regex = None
                if version_regex:
                    for version, inc_by_ver in self.internal_local_metadata[uuid][
                        "incompatiblewithbyversion"
                    ].items():
                        if match(version_regex, version):
                            version_key_matched_incompat = True
                            if (
                                inc_by_ver
                                and isinstance(inc_by_ver, dict)
                                and inc_by_ver.get("li")
                            ):
                                matched_versioned_incompat = inc_by_ver.get("li")
                            else:
                                matched_versioned_incompat = []
                            break

            if prefer_versioned and version_key_matched_incompat:
                if matched_versioned_incompat:
                    logger.debug(
                        f"Current mod is incompatible by version with these mods: {matched_versioned_incompat}"
                    )
                    add_incompatibility_to_mod(
                        self.internal_local_metadata[uuid],
                        matched_versioned_incompat,
                        self.internal_local_metadata,
                    )
                else:
                    logger.debug(
                        "Prefer versioned tags: incompatibleWith key present for this version but empty; suppressing base incompatibleWith"
                    )
            else:
                if base_incompat:
                    logger.debug(
                        f"Current mod is incompatible with these mods: {base_incompat}"
                    )
                    add_incompatibility_to_mod(
                        self.internal_local_metadata[uuid],
                        base_incompat,
                        self.internal_local_metadata,
                    )
                # prefer_versioned is disabled: ignore versioned incompat entries
            # Current mod should be loaded AFTER these mods. These mods can be thought
            # of as "load these before".
            base_after = None
            if self.internal_local_metadata[uuid].get("loadafter"):
                try:
                    base_after = self.internal_local_metadata[uuid]["loadafter"].get(
                        "li"
                    )
                except Exception as e:
                    mod_metadata_path = self.internal_local_metadata[uuid][
                        "metadata_file_path"
                    ]
                    logger.warning(
                        f"About.xml syntax error. Unable to read <loadafter> tag from XML: {mod_metadata_path}"
                    )
                    logger.debug(e)

            matched_after = None
            version_key_matched_after = False
            if self.internal_local_metadata[uuid].get("loadafterbyversion"):
                try:
                    major, minor = self.game_version.split(".")[:2]
                    version_regex = rf"v{major}\.{minor}"
                except Exception:
                    version_regex = None
                if version_regex:
                    for (
                        version,
                        load_these_before_by_ver,
                    ) in self.internal_local_metadata[uuid][
                        "loadafterbyversion"
                    ].items():
                        if match(version_regex, version):
                            version_key_matched_after = True
                            if (
                                load_these_before_by_ver
                                and isinstance(load_these_before_by_ver, dict)
                                and load_these_before_by_ver.get("li")
                            ):
                                matched_after = load_these_before_by_ver.get("li")
                            else:
                                matched_after = []
                            break

            if prefer_versioned and version_key_matched_after:
                if matched_after:
                    logger.debug(
                        f"Current mod should load after these mods by version: {matched_after}"
                    )
                    add_load_rule_to_mod(
                        self.internal_local_metadata[uuid],
                        matched_after,
                        "loadTheseBefore",
                        "loadTheseAfter",
                        self.internal_local_metadata,
                        self.packageid_to_uuids,
                    )
                else:
                    logger.debug(
                        "Prefer versioned tags: loadAfter key present for this version but empty; suppressing base loadAfter"
                    )
            else:
                if base_after:
                    logger.debug(
                        f"Current mod should load after these mods: {base_after}"
                    )
                    add_load_rule_to_mod(
                        self.internal_local_metadata[uuid],
                        base_after,
                        "loadTheseBefore",
                        "loadTheseAfter",
                        self.internal_local_metadata,
                        self.packageid_to_uuids,
                    )
                # prefer_versioned is disabled: ignore versioned loadAfter entries

            # Always respect forceloadafter regardless of precedence flag
            if self.internal_local_metadata[uuid].get("forceloadafter"):
                try:
                    force_load_these_before = self.internal_local_metadata[uuid][
                        "forceloadafter"
                    ].get("li")
                    if force_load_these_before:
                        logger.debug(
                            f"Current mod should force load after these mods: {force_load_these_before}"
                        )
                        add_load_rule_to_mod(
                            self.internal_local_metadata[uuid],
                            force_load_these_before,
                            "loadTheseBefore",
                            "loadTheseAfter",
                            self.internal_local_metadata,
                            self.packageid_to_uuids,
                        )
                except Exception as e:
                    mod_metadata_path = self.internal_local_metadata[uuid].get(
                        "metadata_file_path"
                    )
                    logger.warning(
                        f"About.xml syntax error. Unable to read <forceloadafter> tag from XML: {mod_metadata_path}"
                    )
                    logger.debug(e)

            # Current mod should be loaded BEFORE these mods
            # The current mod is a dependency for all these mods
            base_before = None
            if self.internal_local_metadata[uuid].get("loadbefore"):
                try:
                    base_before = self.internal_local_metadata[uuid]["loadbefore"].get(
                        "li"
                    )
                except Exception as e:
                    mod_metadata_path = self.internal_local_metadata[uuid][
                        "metadata_file_path"
                    ]
                    logger.warning(
                        f"About.xml syntax error. Unable to read <loadbefore> tag from XML: {mod_metadata_path}"
                    )
                    logger.debug(e)

            if self.internal_local_metadata[uuid].get("forceloadbefore"):
                try:
                    force_load_these_after = self.internal_local_metadata[uuid][
                        "forceloadbefore"
                    ].get("li")
                    if force_load_these_after:
                        logger.debug(
                            f"Current mod should force load before these mods: {force_load_these_after}"
                        )
                        add_load_rule_to_mod(
                            self.internal_local_metadata[uuid],
                            force_load_these_after,
                            "loadTheseAfter",
                            "loadTheseBefore",
                            self.internal_local_metadata,
                            self.packageid_to_uuids,
                        )
                except Exception as e:
                    mod_metadata_path = self.internal_local_metadata[uuid][
                        "metadata_file_path"
                    ]
                    logger.warning(
                        f"About.xml syntax error. Unable to read <forceloadbefore> tag from XML: {mod_metadata_path}"
                    )
                    logger.debug(e)

            matched_before = None
            version_key_matched_before = False
            if self.internal_local_metadata[uuid].get("loadbeforebyversion"):
                try:
                    major, minor = self.game_version.split(".")[:2]
                    version_regex = rf"v{major}\.{minor}"
                except Exception:
                    version_regex = None
                if version_regex:
                    for version, loadbefore_by_ver in self.internal_local_metadata[
                        uuid
                    ]["loadbeforebyversion"].items():
                        if match(version_regex, version):
                            version_key_matched_before = True
                            if (
                                loadbefore_by_ver
                                and isinstance(loadbefore_by_ver, dict)
                                and loadbefore_by_ver.get("li")
                            ):
                                matched_before = loadbefore_by_ver.get("li")
                            else:
                                matched_before = []
                            break

            if prefer_versioned and version_key_matched_before:
                if matched_before:
                    logger.debug(
                        f"Current mod should load before these mods by version: {matched_before}"
                    )
                    add_load_rule_to_mod(
                        self.internal_local_metadata[uuid],
                        matched_before,
                        "loadTheseAfter",
                        "loadTheseBefore",
                        self.internal_local_metadata,
                        self.packageid_to_uuids,
                    )
                else:
                    logger.debug(
                        "Prefer versioned tags: loadBefore key present for this version but empty; suppressing base loadBefore"
                    )
            else:
                if base_before:
                    logger.debug(
                        f"Current mod should load before these mods: {base_before}"
                    )
                    add_load_rule_to_mod(
                        self.internal_local_metadata[uuid],
                        base_before,
                        "loadTheseAfter",
                        "loadTheseBefore",
                        self.internal_local_metadata,
                        self.packageid_to_uuids,
                    )
                # prefer_versioned is disabled: ignore versioned loadBefore entries

        logger.info("Finished adding dependencies through About.xml information")
        log_deps_order_info(self.internal_local_metadata)

        # Steam references dependencies based on PublishedFileID, not package ID
        if self.external_steam_metadata:
            logger.info("Started compiling metadata from configured SteamDB")
            tracking_dict: dict[str, set[str]] = {}
            steam_id_to_package_id: dict[str, str] = {}
            for publishedfileid, mod_data in self.external_steam_metadata.items():
                db_packageid = mod_data.get("packageid")
                # If our DB has a packageid for this
                if db_packageid:
                    db_packageid = db_packageid.lower()  # Normalize packageid
                    steam_id_to_package_id[publishedfileid] = db_packageid
                    self.steamdb_packageid_to_name[db_packageid] = mod_data.get("name")
                    potential_uuids = self.packageid_to_uuids.get(db_packageid)
                    if potential_uuids:  # Potential uuids is a set
                        for uuid in potential_uuids:
                            if (
                                uuid
                                and self.internal_local_metadata[uuid].get(
                                    "publishedfileid"
                                )
                                == publishedfileid
                            ):
                                dependencies = mod_data.get("dependencies")
                                if dependencies:
                                    tracking_dict.setdefault(uuid, set()).update(
                                        dependencies.keys()
                                    )
            logger.debug(
                f"Tracking {len(steam_id_to_package_id)} SteamDB packageids for lookup"
            )
            logger.debug(
                f"Tracking Steam dependency data for {len(tracking_dict)} installed mods"
            )
            # For each mod that exists in self.internal_local_metadata -> dependencies (in Steam ID form)
            for (
                installed_mod_uuid,
                set_of_dependency_publishedfileids,
            ) in tracking_dict.items():
                for dependency_steam_id in set_of_dependency_publishedfileids:
                    # Dependencies are added as package_ids. We should be able to
                    # resolve the package_id from the Steam ID for any mod, unless
                    # the metadata actually references a Steam ID that itself does not
                    # wire to a package_id defined in an installed & valid mod.
                    if dependency_steam_id in steam_id_to_package_id:
                        add_dependency_to_mod_from_steamdb(
                            self.internal_local_metadata[installed_mod_uuid],
                            steam_id_to_package_id[dependency_steam_id],
                            self.internal_local_metadata,
                        )
                    else:
                        # This should only happen with RimPy Mod Manager Database, since it does not contain
                        # keyed information for Core + DLCs in it's ["database"] - this is only referenced by
                        # RPMMDB with the ["database"][pfid]["children"] values.
                        logger.debug(
                            f"Unable to lookup Steam AppID/PublishedFileID in Steam metadata: {dependency_steam_id}"
                        )
            logger.info("Finished adding dependencies from SteamDB")
            log_deps_order_info(self.internal_local_metadata)
        else:
            logger.info("No Steam database supplied from external metadata. skipping.")
        # Add load order to installed mods based on dependencies from community rules
        if self.external_community_rules:
            logger.info("Started compiling metadata from configured Community Rules")
            for package_id in self.external_community_rules:
                # Note: requiring the package be in self.internal_local_metadata should be fine, as
                # if the mod doesn't exist self.internal_local_metadata, then either mod_data or dependency_id
                # will be None, and then we don't insert a dependency
                if package_id.lower() in self.packageid_to_uuids:
                    potential_uuids = self.packageid_to_uuids.get(
                        package_id.lower(), set()
                    )
                    load_these_after = self.external_community_rules[package_id].get(
                        "loadBefore"
                    )
                    if load_these_after:
                        logger.debug(
                            f"Current mod should load before these mods: {load_these_after}"
                        )
                        # In Alphabetical, load_these_after is at least an empty dict
                        # Cannot call add_load_rule_to_mod outside of this for loop,
                        # as that expects a list
                        for load_this_after in load_these_after:
                            for uuid in potential_uuids:
                                add_load_rule_to_mod(
                                    self.internal_local_metadata[
                                        uuid
                                    ],  # Already checked above
                                    load_this_after,  # Lower() done in call
                                    "loadTheseAfter",
                                    "loadTheseBefore",
                                    self.internal_local_metadata,
                                    self.packageid_to_uuids,
                                )
                    load_these_before = self.external_community_rules[package_id].get(
                        "loadAfter"
                    )
                    if load_these_before:
                        logger.debug(
                            f"Current mod should load after these mods: {load_these_before}"
                        )
                        # In Alphabetical, load_these_before is at least an empty dict
                        for load_this_before in load_these_before:
                            for uuid in potential_uuids:
                                add_load_rule_to_mod(
                                    self.internal_local_metadata[
                                        uuid
                                    ],  # Already checked above
                                    load_this_before,  # lower() done in call
                                    "loadTheseBefore",
                                    "loadTheseAfter",
                                    self.internal_local_metadata,
                                    self.packageid_to_uuids,
                                )
                    incompatibilities = self.external_community_rules[package_id].get(
                        "incompatibleWith"
                    )
                    if incompatibilities:
                        logger.debug(
                            f"Current mod is incompatible with these mods: {incompatibilities}"
                        )
                        for incompatibilities in incompatibilities:
                            for uuid in potential_uuids:
                                add_incompatibility_to_mod(
                                    self.internal_local_metadata[uuid],
                                    incompatibilities,
                                    self.internal_local_metadata,
                                )
                    load_this_top = self.external_community_rules[package_id].get(
                        "loadTop"
                    )
                    if load_this_top:
                        logger.debug(
                            "Current mod should load at the top of a mods list, and will be considered a 'tier 1' mod"
                        )
                        for uuid in potential_uuids:
                            self.internal_local_metadata[uuid]["loadTop"] = True
                    load_this_bottom = self.external_community_rules[package_id].get(
                        "loadBottom"
                    )
                    if load_this_bottom:
                        logger.debug(
                            'Current mod should load at the bottom of a mods list, and will be considered a "tier 3" mod'
                        )
                        for uuid in potential_uuids:
                            self.internal_local_metadata[uuid]["loadBottom"] = True
            logger.info("Finished adding dependencies from Community Rules")
            log_deps_order_info(self.internal_local_metadata)
        else:
            logger.info(
                "No Community Rules database supplied from external metadata. skipping."
            )
        # Add load order rules to installed mods based on rules from user rules
        if self.external_user_rules:
            logger.info("Started compiling metadata from User Rules")
            for package_id in self.external_user_rules:
                # Note: requiring the package be in self.internal_local_metadata should be fine, as
                # if the mod doesn't exist self.internal_local_metadata, then either mod_data or dependency_id
                # will be None, and then we don't insert a dependency
                if package_id.lower() in self.packageid_to_uuids:
                    potential_uuids = self.packageid_to_uuids.get(
                        package_id.lower(), set()
                    )
                    load_these_after = self.external_user_rules[package_id].get(
                        "loadBefore"
                    )
                    if load_these_after:
                        logger.debug(
                            f"Current mod should load before these mods: {load_these_after}"
                        )
                        # In Alphabetical, load_these_after is at least an empty dict
                        # Cannot call add_load_rule_to_mod outside of this for loop,
                        # as that expects a list
                        for load_this_after in load_these_after:
                            for uuid in potential_uuids:
                                add_load_rule_to_mod(
                                    self.internal_local_metadata[
                                        uuid
                                    ],  # Already checked above
                                    load_this_after,  # lower() done in call
                                    "loadTheseAfter",
                                    "loadTheseBefore",
                                    self.internal_local_metadata,
                                    self.packageid_to_uuids,
                                )

                    load_these_before = self.external_user_rules[package_id].get(
                        "loadAfter"
                    )
                    if load_these_before:
                        logger.debug(
                            f"Current mod should load after these mods: {load_these_before}"
                        )
                        # In Alphabetical, load_these_before is at least an empty dict
                        for load_this_before in load_these_before:
                            for uuid in potential_uuids:
                                add_load_rule_to_mod(
                                    self.internal_local_metadata[
                                        uuid
                                    ],  # Already checked above
                                    load_this_before,  # lower() done in call
                                    "loadTheseBefore",
                                    "loadTheseAfter",
                                    self.internal_local_metadata,
                                    self.packageid_to_uuids,
                                )
                    incompatibilities = self.external_user_rules[package_id].get(
                        "incompatibleWith"
                    )
                    if incompatibilities:
                        logger.debug(
                            f"Current mod is incompatible with these mods: {incompatibilities}"
                        )
                        for incompatibilities in incompatibilities:
                            for uuid in potential_uuids:
                                add_incompatibility_to_mod(
                                    self.internal_local_metadata[uuid],
                                    incompatibilities,
                                    self.internal_local_metadata,
                                )
                    load_this_top = self.external_user_rules[package_id].get("loadTop")
                    if load_this_top:
                        logger.debug(
                            "Current mod should load at the top of a mods list, and will be considered a 'tier 1' mod"
                        )
                        for uuid in potential_uuids:
                            self.internal_local_metadata[uuid]["loadTop"] = True
                    load_this_bottom = self.external_user_rules[package_id].get(
                        "loadBottom"
                    )
                    if load_this_bottom:
                        logger.debug(
                            'Current mod should load at the bottom of a mods list, and will be considered a "tier 3" mod'
                        )
                        for uuid in potential_uuids:
                            self.internal_local_metadata[uuid]["loadBottom"] = True
            logger.info("Finished adding dependencies from User Rules")
            log_deps_order_info(self.internal_local_metadata)
        else:
            logger.info(
                "No User Rules database supplied from external metadata. skipping."
            )

        if self.external_use_this_instead_replacements:
            logger.info("Flagging obsoleted mods from the Use This Instead database")
            for uuid in uuids:
                if self.has_alternative_mod(uuid):
                    self.internal_local_metadata[uuid]["obsolete"] = True

        logger.info("Finished compiling internal metadata with external metadata")

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

        # check if mod_data exists and packageid is included in the external "No Version Warning" list
        if (
            mod_data
            and self.external_no_version_warning
            and mod_data["packageid"] in self.external_no_version_warning
        ):
            logger.info(
                f'mod with id "{mod_data["packageid"]}" was found on the "No Version Warning" list. Skipping version mismatch check!'
            )
            return False
        elif (  # Check if game_version exists and mod_data exists and mod_data contains 'supportedversions' with 'li' key
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

    def has_alternative_mod(self, uuid: str) -> ModReplacement | None:
        """
        If the user has configured a "Use This Instead" database, this function checks if a given mod has
        a recommended alternative.

        If the user does not, it always returns None
        """
        if not self.external_use_this_instead_replacements:
            return None

        mod_data = self.internal_local_metadata.get(uuid, False)
        if not mod_data:
            return None

        mod_workshop_id = str(mod_data.get("publishedfileid", ""))
        if not mod_workshop_id:
            return None

        # Get the rules array from the replacements database
        rules = self.external_use_this_instead_replacements.get("rules", [])

        # Search through replacements database for a match
        for replacement_entry in rules:
            if (
                isinstance(replacement_entry, dict)
                and str(replacement_entry.get("oldWorkshopId", "")) == mod_workshop_id
            ):
                return ModReplacement(
                    name=replacement_entry.get("newName", ""),
                    author=replacement_entry.get("newAuthor", ""),
                    packageid=replacement_entry.get("newPackageId", ""),
                    pfid=replacement_entry.get("newWorkshopId", ""),
                    supportedversions=replacement_entry.get("newVersions", []),
                    source="database",
                )

        return None

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
            f"Processing creation of {data_source + ' mod' if data_source != 'expansion' else data_source} for {mod_directory}"
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
            metadata_manager=self,
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

    def refresh_cache(self, is_initial: bool = False) -> None:
        """
        Refresh the metadata cache by performing a comprehensive update of mod metadata.

        This method is called on app initialization and whenever the refresh button is pressed,
        typically after changes to workshop settings, mod paths, or downloading new mods.

        It performs the following steps in a specific order to ensure dependencies are met:
        1. Updates user paths from settings if not initial load.
        2. Refreshes ACF metadata from Steam client and SteamCMD for workshop mod details.
        3. Reads the game version from Version.txt; this must be done before external metadata loading
           since loaders like "No Version Warning" depend on the game version for path construction.
        4. Loads external metadata sources in parallel (user rules, Steam database, community rules,
           no version warning, and use this instead replacements); loading external metadata before
           scanning internal mod metadata ensures that mods depending on SteamDB for generating
           missing mod info are assigned proper data correctly, compatible with old mods.
        5. Scans internal mod directories (expansion, local, workshop) to parse and update mod metadata,
           purging outdated entries (unless initial load) and rebuilding path-to-UUID mappers.
        6. Compiles metadata to calculate dependencies, incompatibilities, and load order rules.

        Parameters:
            is_initial (bool): If True, indicates initial load and skips purging orphaned metadata.
        """
        logger.warning("Refreshing metadata cache...")

        # If we are refreshing cache from user action, update user paths as well in case of change
        if not is_initial:
            self.__update_from_settings()

        # Update paths from game configuration

        # Refresh ACF metadata from Steam sources for workshop mod details
        refresh_acf_metadata(self, steamclient=True, steamcmd=True)
        # Read game version first since external metadata loading (e.g., No Version Warning) depends on it
        self.__read_game_version()
        # Load external metadata sources in parallel (user rules, Steam DB, community rules, etc.)
        # Loading external metadata before scanning internal mod metadata ensures that mods
        # which depend on SteamDB for generating missing mod info are assigned proper data correctly.
        # This is necessary for compatibility with old mods, such as https://steamcommunity.com/sharedfiles/filedetails/?id=1147799676
        self.__refresh_external_metadata()
        # Scan and refresh internal mod metadata from file system (expansion, local, workshop)
        self.__refresh_internal_metadata(is_initial=is_initial)
        # Compile metadata to calculate dependencies, incompatibilities, and load rules
        self.compile_metadata(uuids=list(self.internal_local_metadata.keys()))

    def get_mod_name_from_package_id(self, package_id: str) -> str:
        """Get a mod's name from its package ID"""
        for mod_data in self.internal_local_metadata.values():
            if mod_data.get("packageid") == package_id:
                return mod_data.get("name", package_id)
        return package_id

    def get_missing_dependencies(
        self, active_mods_uuids: set[str]
    ) -> dict[str, set[str]]:
        """
        Check for missing dependencies among active mods
        Returns a dict mapping mod package IDs to sets of missing dependency package IDs
        """
        missing_deps = {}
        active_mod_ids = {
            self.internal_local_metadata[uuid]["packageid"]
            for uuid in active_mods_uuids
        }

        # check each active mod's dependencies
        for uuid in active_mods_uuids:
            mod_data = self.internal_local_metadata[uuid]
            mod_id = mod_data["packageid"]

            # get mod's dependencies
            if mod_data.get("dependencies"):
                # check which dependencies are missing, honoring alternativePackageIds
                missing: set[str] = set()
                for dep_entry in mod_data["dependencies"]:
                    alt_ids: set[str] = set()
                    if isinstance(dep_entry, tuple):
                        dep_id = dep_entry[0]
                        if (
                            len(dep_entry) > 1
                            and isinstance(dep_entry[1], dict)
                            and isinstance(dep_entry[1].get("alternatives"), set)
                        ):
                            alt_ids = dep_entry[1]["alternatives"]
                    else:
                        dep_id = dep_entry

                    consider_alternatives = self.settings_controller.settings.use_alternative_package_ids_as_satisfying_dependencies
                    satisfied = dep_id in active_mod_ids
                    if not satisfied and consider_alternatives:
                        satisfied = any(alt in active_mod_ids for alt in alt_ids)
                    if not satisfied:
                        missing.add(dep_id)
                if missing:
                    missing_deps[mod_id] = missing

        return missing_deps

    def refresh_workshop_timestamps_via_steamworks(self) -> None:
        """
        Query Steam client via Steamworks API for current installation timestamps.

        This gets the authoritative "when did Steam last update this mod" timestamp
        directly from Steam's internal state, eliminating stale ACF file issues.
        """
        from app.utils.app_info import AppInfo
        from app.utils.steam.steamworks.wrapper import SteamworksInterface

        logger.info("Refreshing Workshop mod timestamps via Steamworks API")

        # Initialize Steamworks
        steamworks = SteamworksInterface.instance(
            _libs=str((AppInfo().application_folder / "libs"))
        )

        if steamworks.steam_not_running or not steamworks.steamworks.loaded():
            logger.warning(
                "Steam not running - cannot query install info via Steamworks"
            )
            return

        # Query each Workshop mod for current install timestamp
        workshop_mods_updated = 0
        for uuid, metadata in self.internal_local_metadata.items():
            # Only check Workshop mods
            if metadata.get("data_source") != "workshop":
                continue

            pfid = metadata.get("publishedfileid")
            if not pfid:
                continue

            try:
                # Query Steam for current install info
                # Convert pfid from string to int (metadata stores as string)
                install_info = steamworks.steamworks.Workshop.GetItemInstallInfo(
                    int(pfid)
                )

                if install_info and install_info.get("timestamp"):
                    # Update with authoritative timestamp from Steam
                    metadata["internal_time_touched"] = install_info["timestamp"]
                    workshop_mods_updated += 1
                    logger.debug(
                        f"Updated timestamp for {metadata.get('name')}: {install_info['timestamp']}"
                    )
            except Exception as e:
                logger.warning(f"Failed to get install info for PFID {pfid}: {e}")

        logger.info(
            f"Updated timestamps for {workshop_mods_updated} Workshop mods via Steamworks API"
        )


class ModParser(QRunnable):
    mod_metadata_updated_signal = Signal(str)

    def __init__(
        self,
        data_source: str,
        mod_directory: str,
        metadata_manager: MetadataManager,
        uuid: str = "",
    ):
        super(ModParser, self).__init__()
        self.data_source = data_source
        self.mod_directory = mod_directory
        self.metadata_manager = metadata_manager
        self.uuid = uuid

        # Set autoDelete to True
        self.setAutoDelete(True)

    def __parse_mod_metadata(
        self,
        data_source: str,
        mod_directory: str,
        metadata_manager: MetadataManager,
        uuid: str,
    ) -> dict[str, Any]:
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
        # Define defaults for scenario
        scenario_rsc_found = False
        scenario_rsc_file = ""
        scenario_data = {}
        scenario_metadata = {}
        # Define defaults for "About" folder and "About.xml" file
        invalid_about_folder_path_found = True
        invalid_about_file_path_found = True
        about_folder_name = "About"
        about_file_name = "About.xml"
        # Look for a case-insensitive "About" folder
        for temp_file in scanpath(mod_directory):
            if (
                temp_file.name.lower() == about_folder_name.lower()
                and temp_file.is_dir()
            ):
                about_folder_name = temp_file.name
                invalid_about_folder_path_found = False
                break
            # Look for a case-insensitive "About.xml" file
        if not invalid_about_folder_path_found:
            for temp_file in scanpath(str((directory_path / about_folder_name))):
                if (
                    temp_file.name.lower() == about_file_name.lower()
                    and temp_file.is_file()
                ):
                    about_file_name = temp_file.name
                    invalid_about_file_path_found = False
                    break
        # Look for .rsc scenario files to load metadata from if we didn't find About.xml
        if invalid_about_file_path_found:
            for temp_file in scanpath(mod_directory):
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
            for temp_file in scanpath(str((directory_path / about_folder_name))):
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
                    except Exception:
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
            except Exception:
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
                        and pfid
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
                    # Normalize authors to a string
                    authors = mod_metadata.get("authors")
                    if isinstance(authors, dict) and authors.get("li"):
                        mod_metadata["authors"] = ", ".join(authors["li"])
                    elif isinstance(authors, list):
                        mod_metadata["authors"] = ", ".join(authors)
                    elif isinstance(authors, str):
                        pass  # Keep as is
                    else:
                        mod_metadata["authors"] = "Unknown"
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
                                li = mod_data["supportedversions"]["li"]
                                if not isinstance(li, str):
                                    logger.error(f"Failed to parse {li} as a string")
                                    continue
                                mod_data["supportedversions"]["li"] = (
                                    ".".join(li.split(".")[:2])
                                    if li.count(".") > 1 and isinstance(li, str)
                                    else li
                                )

                    if mod_metadata.get("supportedversions", {}).get("li"):
                        li = mod_metadata["supportedversions"]["li"]
                        if isinstance(li, str):
                            mod_metadata["supportedversions"]["li"] = li.strip()
                        elif isinstance(li, list):
                            for i, version in enumerate(li):
                                if not isinstance(version, str):
                                    logger.error(
                                        f"Failed to parse {version} as a string"
                                    )
                                    continue
                                li[i] = version.strip()

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
                        if isinstance(mod_metadata["packageid"], str):
                            mod_metadata["packageid"] = mod_metadata[
                                "packageid"
                            ].lower()
                        elif isinstance(mod_metadata["packageid"], dict):
                            # Handle dict packageid (from malformed XML), try to extract text
                            if mod_metadata["packageid"].get("#text"):
                                mod_metadata["packageid"] = mod_metadata["packageid"][
                                    "#text"
                                ].lower()
                    else:  # ...otherwise, we don't have one from About.xml, and we can check Steam DB...
                        # ...this can be needed if a mod depends on a RW generated packageid via built-in hashing mechanism.
                        if (
                            pfid
                            and self.metadata_manager.external_steam_metadata
                            and self.metadata_manager.external_steam_metadata.get(
                                pfid, {}
                            ).get("packageId")
                        ):
                            mod_metadata["packageid"] = (
                                self.metadata_manager.external_steam_metadata[pfid][
                                    "packageId"
                                ].lower()
                            )
                    # Log warning if packageid is missing and assign DEFAULT_MISSING_PACKAGEID
                    if not mod_metadata.get("packageid"):
                        mod_metadata["packageid"] = DEFAULT_MISSING_PACKAGEID
                        logger.warning(f"Invalid packageId in mod: {mod_data_path}")
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
                    # Grab our mod's publishedfileid
                    publishedfileid = mod_metadata.get("publishedfileid")
                    if publishedfileid:
                        # Get our metadata based on data source
                        workshop_acf_data = (
                            self.metadata_manager.workshop_acf_data
                            if data_source == "workshop"
                            else self.metadata_manager.steamcmd_acf_data
                        )
                        workshop_item_details = workshop_acf_data.get(
                            "AppWorkshop", {}
                        ).get("WorkshopItemDetails", {})
                        workshop_items_installed = workshop_acf_data.get(
                            "AppWorkshop", {}
                        ).get("WorkshopItemsInstalled", {})
                        # Edit our metadata, append values
                        if (
                            workshop_item_details.get(publishedfileid, {}).get(
                                "timetouched"
                            )
                            and workshop_item_details.get(publishedfileid, {}).get(
                                "timetouched"
                            )
                            != "0"
                        ):
                            # The last time SteamCMD/Steam client touched a mod according to its entry
                            mod_metadata["internal_time_touched"] = int(
                                workshop_item_details[publishedfileid]["timetouched"]
                            )
                        if publishedfileid and workshop_item_details.get(
                            publishedfileid, {}
                        ).get("timeupdated"):
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
                    # Assign our metadata to the UUID
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
            try:
                # Try to parse .rsc
                scenario_data = xml_path_to_json(scenario_data_path)
            except Exception:
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
                    scenario_metadata["metadata_file_path"] = scenario_data_path
                    scenario_metadata["metadata_file_mtime"] = int(
                        os.path.getmtime(scenario_data_path)
                    )
                    # Track source & uuid in case metadata becomes detached
                    scenario_metadata["uuid"] = uuid
                    # Assign our metadata to the UUID
                    metadata[uuid] = scenario_metadata
                else:
                    logger.error(
                        f"Key <savedscenario><scenario> does not exist in this data: {scenario_metadata}"
                    )
                    data_malformed = True
        if (
            (invalid_about_file_path_found and not scenario_rsc_found) or data_malformed
        ):  # ...finally, if we don't have any metadata parsed, populate invalid mod entry for visibility
            logger.debug(
                f"Invalid dir. Populating invalid mod for path: {mod_directory}"
            )
            # Assign our metadata to the UUID
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

    def run(self) -> None:
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
        except Exception as e:
            error_message = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"ERROR: Unable to initialize ModParser {error_message}")


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
        # Shape of stored dependencies
        # - We keep a list to support rich entries (tuples containing a dict + set)
        # - Each element is either:
        #     "<packageId>"  (plain string), or
        #     ("<packageId>", {"alternatives": set[str]})  (primary + alternatives)
        # A list is used instead of a set because Python sets cannot contain dicts.
        mod_data.setdefault("dependencies", [])

        # Helper: ensure a dependency with alternatives is present, merging when needed.
        # - If a tuple for the same dep already exists, merge the alternatives into it.
        # - If only a plain string exists for that dep, upgrade it to the tuple form.
        # - Otherwise append a new tuple entry.
        def _ensure_dep_with_alts(
            dep_list: list[Any], dep_id: str, alt_ids: set[str]
        ) -> None:
            """Add or merge a dependency with alternatives into dep_list.

            Typical sources that may converge here:
            - Base <modDependencies>
            - Matched <modDependenciesByVersion> section for the current game version
              If both specify the same dependency but different alternatives,
              this function merges them, keeping a single entry per primary dep.
            """
            for i, existing in enumerate(dep_list):
                if isinstance(existing, tuple) and existing and existing[0] == dep_id:
                    # Merge alternatives into existing set if present
                    alt = (
                        existing[1].get("alternatives")
                        if isinstance(existing[1], dict)
                        else None
                    )
                    if isinstance(alt, set):
                        alt.update(alt_ids)
                    else:
                        dep_list[i] = (dep_id, {"alternatives": set(alt_ids)})
                    return
                if existing == dep_id:
                    # Replace simple dep with dep+alternatives
                    dep_list[i] = (dep_id, {"alternatives": set(alt_ids)})
                    return
            dep_list.append((dep_id, {"alternatives": set(alt_ids)}))

        # Helper: ensure a plain dependency is present, without duplicating
        # an existing plain entry or a tuple entry for the same dep.
        def _ensure_plain_dep(dep_list: list[Any], dep_id: str) -> None:
            """Add a plain dependency if it doesn't already exist (as string or tuple)."""
            for existing in dep_list:
                if existing == dep_id:
                    return
                if isinstance(existing, tuple) and existing and existing[0] == dep_id:
                    return
            dep_list.append(dep_id)

        def _parse_alt_ids(alt_obj: Any) -> set[str]:
            alt_ids: set[str] = set()
            if isinstance(alt_obj, dict):
                li = alt_obj.get("li")
                if isinstance(li, list):
                    for v in li:
                        if isinstance(v, str):
                            alt_ids.add(v.lower())
                        elif (
                            isinstance(v, dict)
                            and "#text" in v
                            and isinstance(v["#text"], str)
                        ):
                            alt_ids.add(v["#text"].lower())
                elif isinstance(li, str):
                    alt_ids.add(li.lower())
            elif isinstance(alt_obj, list):
                for v in alt_obj:
                    if isinstance(v, str):
                        alt_ids.add(v.lower())
            elif isinstance(alt_obj, str):
                alt_ids.add(alt_obj.lower())
            return alt_ids

        # If the value is a single dict (for moddependencies)
        if isinstance(dependency_or_dependency_ids, dict):
            pkg = dependency_or_dependency_ids.get("packageId")
            if pkg and not isinstance(pkg, (list, dict)):
                dep_id = str(pkg).lower()
                alt_ids = _parse_alt_ids(
                    dependency_or_dependency_ids.get("alternativePackageIds")
                )
                if alt_ids:
                    _ensure_dep_with_alts(mod_data["dependencies"], dep_id, alt_ids)
                else:
                    _ensure_plain_dep(mod_data["dependencies"], dep_id)
            else:
                logger.error(
                    f"Dependency dict does not contain packageid or correct format: [{dependency_or_dependency_ids}]"
                )
        # If the value is a LIST of dicts
        elif isinstance(dependency_or_dependency_ids, list):
            if dependency_or_dependency_ids and isinstance(
                dependency_or_dependency_ids[0], dict
            ):
                for dependency in dependency_or_dependency_ids:
                    pkg = (
                        dependency.get("packageId")
                        if isinstance(dependency, dict)
                        else None
                    )
                    if pkg:
                        dep_id = str(pkg).lower()
                        alt_ids = set()
                        if isinstance(dependency, dict):
                            alt_ids = _parse_alt_ids(
                                dependency.get("alternativePackageIds")
                            )
                        if alt_ids:
                            _ensure_dep_with_alts(
                                mod_data["dependencies"], dep_id, alt_ids
                            )
                        else:
                            _ensure_plain_dep(mod_data["dependencies"], dep_id)
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
    mod_data: dict[str, Any], dependency_id: Any, all_mods: dict[str, Any]
) -> None:
    mod_name = mod_data.get("name")
    # Store dependencies as a list to support rich entries
    mod_data.setdefault("dependencies", [])

    # If the value is a single str (for steamDB)
    if isinstance(dependency_id, str):
        # Avoid duplicates if present
        dep_list = mod_data["dependencies"]
        if all(
            not (
                existing == dependency_id
                or (
                    isinstance(existing, tuple)
                    and existing
                    and existing[0] == dependency_id
                )
            )
            for existing in dep_list
        ):
            dep_list.append(dependency_id)
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
        # Import here to avoid circular dependencies
        from app.utils.db_builder_core import DBBuilderCore

        # For backwards compatibility with GUI code that uses these attributes
        self.apikey = apikey
        self.appid = appid
        self.database_expiry = database_expiry
        self.get_appid_deps = get_appid_deps
        self.mode = mode
        self.mods = mods
        self.output_database_path = output_database_path
        self.publishedfileids: list[str] = []
        self.update = update
        self.core: DBBuilderCore | None

        # Note: DBBuilderCore only supports "no_local" mode currently
        # The "all_mods" and "pfids_by_appid" modes remain in the Qt wrapper
        if mode == "no_local":
            # Create core instance with callback connected to Qt signal
            self.core = DBBuilderCore(
                apikey=apikey,
                appid=appid,
                database_expiry=database_expiry,
                output_database_path=output_database_path,
                get_appid_deps=get_appid_deps,
                update=update,
                progress_callback=self.db_builder_message_output_signal.emit,
            )
        else:
            self.core = None

    def run(self) -> None:
        # Use core implementation for no_local mode
        if self.mode == "no_local" and self.core:
            self.core.run()
            return

        # Original implementation for other modes
        self.db_builder_message_output_signal.emit(
            f"\nInitiating RimSort Steam Database Builder with mode : {self.mode}\n"
        )
        if len(self.apikey) == 32:  # If supplied WebAPI key is 32 characters
            self.db_builder_message_output_signal.emit(
                "Received valid Steam WebAPI key from settings"
            )
            # Since the key is valid, we try to launch a live query
            if self.mode == "all_mods":
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
                        "url": f"https://store.steampowered.com/app/{v['appid']}",
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
                        "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={v['publishedfileid']}",
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
    # Define defaults for blacklisted mods
    blacklisted_mods = {}
    publishedfileid = ""
    # Check if any of the mods are blacklisted
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
                f"{blacklisted_mods[publishedfileid]['name']} ({publishedfileid})\n"
            )
            blacklisted_mods_report += f"Reason for blacklisting: {blacklisted_mods[publishedfileid]['comment']}"
        answer = show_dialogue_conditional(
            title="Blacklisted mods found",
            text="Some mods are blacklisted in your SteamDB",
            information="Are you sure you want to download these mods? These mods are known mods that are recommended to be avoided.",
            details=blacklisted_mods_report,
            button_text_override=[
                QCoreApplication.translate(
                    "check_if_pfids_blacklisted", "Download blacklisted mods"
                ),
                QCoreApplication.translate(
                    "check_if_pfids_blacklisted", "Skip blacklisted mods"
                ),
            ],
        )
        # Remove blacklisted mods from list if user wants to download them still
        answer_str = str(answer)
        download_text = QCoreApplication.translate(
            "check_if_pfids_blacklisted", "Download blacklisted mods"
        )
        if download_text in answer_str:
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
    return None
