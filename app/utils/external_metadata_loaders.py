import gzip
import json
import os
from pathlib import Path
from time import localtime, strftime, time
from typing import Any, Callable

from loguru import logger

from app.utils.app_info import AppInfo
from app.utils.xml import xml_path_to_json

# Metadata loader source constants
SOURCE_FILE_PATH = "Configured file path"
SOURCE_GIT_REPO = "Configured git repository"
SOURCE_DISABLED = "Disabled"

# Metadata file names
STEAM_DB_FILE = "steamDB.json"
COMMUNITY_RULES_FILE = "communityRules.json"
NO_VERSION_WARNING_FILE = "ModIdsToFix.xml"
USE_THIS_INSTEAD_FILE = "replacements.json.gz"


class ExternalMetadataLoader:
    def __init__(self, manager: Any) -> None:
        self.manager = manager

    def _emit_db_error(self, db_type: str, title: str, message: str, path: str) -> None:
        """Emit a database validation error signal."""
        self.manager.show_warning_signal.emit(
            self.manager.tr(title),
            self.manager.tr(message),
            self.manager.tr(message),
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
        path = Path(self.manager.external_user_rules_path)

        if path.exists():
            logger.info("Loading userRules.json")
            rule_data = self._load_json_file(str(path))

            if rule_data is None:
                logger.warning("Unable to parse userRules.json")
                return

            rules: Any = rule_data.get("rules") if rule_data else None
            if isinstance(rules, dict):
                self.manager.external_user_rules = rules
            else:
                self.manager.external_user_rules = None
            total_entries = (
                len(self.manager.external_user_rules)
                if self.manager.external_user_rules
                else 0
            )
            if self.manager.external_user_rules is None:
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
            self.manager.show_warning_signal.emit(
                self.manager.tr("Steam DB metadata expired"),
                self.manager.tr("Steam DB is expired! Consider updating!\n"),
                self.manager.tr(
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
        self.manager.steamdb_packageid_to_name = {
            metadata["packageid"]: metadata["name"]
            for metadata in db_json_data.values()
            if metadata.get("packageid") and metadata.get("name")
        }

        return db_json_data, path

    def _load_steam_metadata(self, settings: Any) -> None:
        """Load Steam database metadata from configured source."""
        steam_source = settings.external_steam_metadata_source
        (
            self.manager.external_steam_metadata,
            self.manager.external_steam_metadata_path,
        ) = (
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
        (
            self.manager.external_community_rules,
            self.manager.external_community_rules_path,
        ) = (
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
        (
            self.manager.external_no_version_warning,
            self.manager.external_no_version_warning_path,
        ) = (
            self._load_metadata_by_source(
                no_version_source,
                settings.external_no_version_warning_file_path,
                settings.external_no_version_warning_repo_path,
                NO_VERSION_WARNING_FILE,
                self._load_no_version_warning_db,
                subdir=self.manager.game_version[:3],
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
        self.manager.external_use_this_instead_replacements, _ = (
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
