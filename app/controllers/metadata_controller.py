from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import msgspec
from loguru import logger
from natsort import natsorted
from PySide6.QtCore import QMutex, QObject, Signal, Slot

from app.controllers.metadata_db_controller import AuxMetadataController
from app.models.metadata.metadata_mediator import MetadataMediator
from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    CompiledDependencyData,
    ListedMod,
    ModType,
    ReplacementInfo,
    SteamDbEntry,
    SteamDbEntryBlacklist,
)
from app.models.settings import Instance, Settings
from app.utils.acf_utils import load_acf_from_path
from app.utils.app_info import AppInfo
from app.utils.schema import generate_rimworld_mods_list, validate_rimworld_mods_list
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.utils.xml import json_to_xml_write, xml_path_to_json

if TYPE_CHECKING:
    from app.models.metadata.metadata_db import AuxMetadataEntry
    from app.models.metadata.metadata_structure import (
        ExternalRulesSchema,
        SteamDbSchema,
    )


class MetadataController(QObject):
    """Controller class for metadata."""

    _instance: MetadataController | None = None

    mod_created_signal = Signal(str)
    mod_deleted_signal = Signal(str)
    mod_metadata_updated_signal = Signal(str)
    show_warning_signal = Signal(str, str, str, str)
    metadata_refreshed = Signal()
    steam_db_updated = Signal()

    # ---- Lifecycle ----

    def __init__(
        self,
        settings: Settings,
        get_active_instance: Callable[[], Instance],
        metadata_db_controller: AuxMetadataController,
    ) -> None:
        super().__init__()

        self.settings = settings
        self._get_active_instance = get_active_instance

        self.metadata_mediator = MetadataMediator(
            user_rules_path=AppInfo().user_rules_file,
            community_rules_path=None,
            steam_db_path=None,
            workshop_mods_path=None,
            local_mods_path=None,
            game_path=None,
        )

        self._steamdb_packageid_to_name_cache: dict[str, str] | None = None
        self._packageid_to_paths_cache: dict[str, set[str]] | None = None
        self.workshop_acf_data: dict[str, Any] = {}
        self.steamcmd_acf_data: dict[str, Any] = {}

        self.metadata_db_controller = metadata_db_controller
        self.steamcmd_wrapper = SteamcmdInterface.instance()

        self.reset_paths()

    @classmethod
    def instance(
        cls,
        settings: Settings | None = None,
        get_active_instance: Callable[[], Instance] | None = None,
        metadata_db_controller: AuxMetadataController | None = None,
    ) -> MetadataController:
        """Get or create the singleton instance.

        :param settings: Required on first call
        :param get_active_instance: Required on first call
        :param metadata_db_controller: Required on first call
        :return: The singleton instance
        :raises RuntimeError: If called before initialization
        """
        if cls._instance is None:
            if (
                settings is None
                or get_active_instance is None
                or metadata_db_controller is None
            ):
                raise RuntimeError(
                    "MetadataController.instance() called before initialization"
                )
            cls._instance = cls(settings, get_active_instance, metadata_db_controller)
        return cls._instance

    @Slot()
    def refresh_metadata(self) -> None:
        """Refresh the metadata."""
        self.reset_paths()
        prefer_versioned = self.settings.prefer_versioned_about_tags
        case_insensitive = self.settings.case_insensitive_about_xml_lookup
        self.metadata_mediator.refresh_metadata(
            prefer_versioned=prefer_versioned,
            case_insensitive_about_xml=case_insensitive,
        )

        with self.metadata_db_controller.Session() as session:
            for path, mod_data in self.metadata_mediator.mods_metadata.items():
                try:
                    entry = self.metadata_db_controller.get_or_create(session, path)
                    entry.type = str(mod_data.mod_type)
                    entry.published_file_id = mod_data.published_file_id
                except Exception:
                    session.rollback()
                    logger.exception(f"Failed to update aux metadata for mod at {path}")

            self.metadata_db_controller.update_from_acf(
                session,
                Path(self.steamcmd_wrapper.steamcmd_appworkshop_acf_path),
                ModType.STEAM_CMD,
            )
            if self.workshop_acf_path is not None:
                self.metadata_db_controller.update_from_acf(
                    session,
                    self.workshop_acf_path,
                    ModType.STEAM_WORKSHOP,
                )

            session.commit()

        self.steamcmd_acf_data = load_acf_from_path(
            self.steamcmd_wrapper.steamcmd_appworkshop_acf_path
        )
        if self.workshop_acf_path is not None:
            self.workshop_acf_data = load_acf_from_path(self.workshop_acf_path)
        else:
            self.workshop_acf_data = {}

        self._invalidate_caches()
        self.metadata_refreshed.emit()

    @Slot()
    def reset_paths(self) -> None:
        """Reset the paths from current settings. Does not refresh metadata."""

        def _get_path(path_str: str) -> Path | None:
            return Path(path_str) if path_str else None

        active_instance = self._get_active_instance()
        active_settings = self.settings

        cr_path = self._resolve_db_path(
            active_settings.external_community_rules_metadata_source,
            active_settings.external_community_rules_file_path,
            active_settings.external_community_rules_repo,
            "communityRules.json",
        )
        steam_db_path = self._resolve_db_path(
            active_settings.external_steam_metadata_source,
            active_settings.external_steam_metadata_file_path,
            active_settings.external_steam_metadata_repo,
            "steamDB.json",
        )
        workshop_mods_path = _get_path(active_instance.workshop_folder)
        local_mods_path = _get_path(active_instance.local_folder)
        game_path = _get_path(active_instance.game_folder)

        if local_mods_path is None and game_path is not None:
            local_mods_path = game_path / "Mods"

        self.metadata_mediator.community_rules_path = cr_path
        self.metadata_mediator.steam_db_path = steam_db_path
        self.metadata_mediator.workshop_mods_path = workshop_mods_path
        self.metadata_mediator.local_mods_path = local_mods_path
        self.metadata_mediator.game_path = game_path
        self.metadata_mediator.no_version_warning_path = self._resolve_db_path(
            active_settings.external_no_version_warning_metadata_source,
            active_settings.external_no_version_warning_file_path,
            active_settings.external_no_version_warning_repo_path,
            "ModIdsToFix.xml",
        )
        self.metadata_mediator.use_this_instead_path = self._resolve_db_path(
            active_settings.external_use_this_instead_metadata_source,
            active_settings.external_use_this_instead_file_path,
            active_settings.external_use_this_instead_repo_path,
            "replacements.json.gz",
        )

        self._invalidate_caches()

    # ---- Data properties ----

    @property
    def mods_metadata(self) -> dict[str, ListedMod]:
        """Get the current mods metadata dictionary."""
        return self.metadata_mediator.mods_metadata

    @property
    def game_version(self) -> str:
        """Get the current game version."""
        return self.metadata_mediator.game_version

    @property
    def steam_db(self) -> SteamDbSchema | None:
        """Get the loaded Steam database, if any."""
        return self.metadata_mediator.steam_db

    @property
    def community_rules(self) -> ExternalRulesSchema | None:
        """Get the loaded community rules, if any."""
        return self.metadata_mediator.community_rules

    @property
    def user_rules(self) -> ExternalRulesSchema | None:
        """Get the loaded user rules, if any."""
        return self.metadata_mediator.user_rules

    @property
    def packageid_to_paths(self) -> dict[str, set[str]]:
        """Build a mapping from package IDs to sets of mod paths (cached)."""
        if self._packageid_to_paths_cache is None:
            result: dict[str, set[str]] = {}
            for path, mod in self.mods_metadata.items():
                if isinstance(mod, AboutXmlMod):
                    pid = str(mod.package_id)
                    result.setdefault(pid, set()).add(path)
            self._packageid_to_paths_cache = result
        return self._packageid_to_paths_cache

    @property
    def steamdb_packageid_to_name(self) -> dict[str, str]:
        """Build a mapping from package IDs to Steam names from the Steam DB (cached).

        Keys are actual packageIds (lowercased), NOT published file IDs.
        Prefers steamName (Workshop display title) over name for better UX.
        """
        if self._steamdb_packageid_to_name_cache is None:
            if self.metadata_mediator.steam_db is None:
                self._steamdb_packageid_to_name_cache = {}
            else:
                self._steamdb_packageid_to_name_cache = {
                    entry.packageId.lower(): entry.steamName or entry.name
                    for entry in self.metadata_mediator.steam_db.database.values()
                    if entry.packageId and (entry.steamName or entry.name)
                }
        return self._steamdb_packageid_to_name_cache

    @property
    def is_abort_requested(self) -> bool:
        """Whether a metadata refresh abort has been requested."""
        return getattr(self, "_abort_requested", False)

    @is_abort_requested.setter
    def is_abort_requested(self, value: bool) -> None:
        self._abort_requested = value

    def update_workshop_timestamps(
        self,
        mod_path: str,
        time_created: int | None = None,
        time_updated: int | None = None,
    ) -> None:
        """Write workshop timestamps to aux DB for a mod.

        :param mod_path: Mod path (the identity key)
        :param time_created: Steam Workshop creation timestamp (epoch seconds)
        :param time_updated: Steam Workshop last-updated timestamp (epoch seconds)
        """
        with self.metadata_db_controller.Session() as session:
            entry = self.metadata_db_controller.get_or_create(session, mod_path)
            if time_created is not None:
                entry.external_time_created = time_created
            if time_updated is not None:
                entry.external_time_updated = time_updated
            session.commit()

    # ---- Path accessors ----

    @property
    def workshop_acf_path(self) -> Path | None:
        """Path to Steam Workshop's appworkshop_294100.acf.

        Derived from the workshop mods path: two directories up from
        content/294100 to find workshop/appworkshop_294100.acf.
        Returns None if workshop path is not configured.
        """
        workshop_path = self.metadata_mediator.workshop_mods_path
        if workshop_path is None:
            return None
        return workshop_path.parent.parent / "appworkshop_294100.acf"

    @property
    def steamcmd_acf_path(self) -> str:
        """Path to the SteamCMD appworkshop ACF file.

        :return: The ACF file path as a string
        """
        return self.steamcmd_wrapper.steamcmd_appworkshop_acf_path

    @property
    def steam_db_path(self) -> Path | None:
        """Path to the Steam database file on disk.

        :return: The resolved path, or None if Steam DB is disabled
        """
        return self.metadata_mediator.steam_db_path

    @property
    def community_rules_path(self) -> Path | None:
        """Path to the community rules database file on disk.

        :return: The resolved path, or None if community rules are disabled
        """
        return self.metadata_mediator.community_rules_path

    # ---- Lookups ----

    def get_mod(self, path: str | Path) -> ListedMod | None:
        """Get mod metadata by path.

        :param path: Mod path (string or Path)
        :return: The ListedMod at that path, or None
        """
        return self.metadata_mediator.mods_metadata.get(str(path))

    def has_mod(self, path: str | Path) -> bool:
        """Check if a mod exists at the given path.

        :param path: Mod path (string or Path)
        :return: True if a mod exists at the path
        """
        return str(path) in self.metadata_mediator.mods_metadata

    def resolve_about_xml_to_mod_path(self, about_xml_path: str) -> str | None:
        """Resolve an About.xml file path to its mod's path key.

        About.xml lives at ``<mod_path>/About/About.xml``, so the mod path
        is the grandparent directory. Returns None if no mod exists there.

        :param about_xml_path: Path to an About.xml file
        :return: The mod path key, or None
        """
        candidate = str(Path(about_xml_path).parent.parent)
        if candidate in self.metadata_mediator.mods_metadata:
            return candidate
        return None

    def get_metadata_with_path(
        self, path: str | Path
    ) -> tuple[ListedMod, AuxMetadataEntry] | tuple[None, None]:
        """Get mod metadata and aux DB entry for a given path.

        :param path: Mod path (string or Path)
        :return: (ListedMod, AuxMetadataEntry) if found, (None, None) otherwise
        """
        mod_data = self.metadata_mediator.mods_metadata.get(str(path), None)
        if mod_data is None:
            return None, None

        with self.metadata_db_controller.Session() as session:
            entry = self.metadata_db_controller.get_or_create(session, path)

        return mod_data, entry

    def get_mod_name_from_package_id(self, package_id: str) -> str:
        """Get a mod's display name from its package ID.

        Resolution order:
        1. Check parsed mods metadata (packageid_to_paths + mods_metadata)
        2. Fall back to Steam DB name mapping
        3. Return the package_id itself as last resort

        :param package_id: The mod's package ID (case-insensitive)
        :return: The mod's display name, or the package_id if not found
        """
        pid_lower = package_id.lower()
        paths = self.packageid_to_paths.get(pid_lower, set())
        for path in paths:
            mod = self.mods_metadata.get(path)
            if mod is not None and mod.name:
                return mod.name
        steam_name = self.steamdb_packageid_to_name.get(pid_lower)
        if steam_name:
            return steam_name
        return package_id

    # ---- Queries ----

    def compile(
        self,
        use_moddependencies_as_loadTheseBefore: bool = False,
        use_alternative_package_ids: bool = False,
    ) -> CompiledDependencyData:
        """Compile dependency data from current metadata state.

        :param use_moddependencies_as_loadTheseBefore: Treat modDependencies as loadAfter
        :param use_alternative_package_ids: Fall back to alternative package IDs for deps
        :return: Compiled dependency data
        """
        return CompiledDependencyData.build(
            self.metadata_mediator.mods_metadata,
            use_moddependencies_as_loadTheseBefore,
            use_alternative_package_ids,
        )

    def get_missing_dependencies(
        self, active_mod_paths: set[str]
    ) -> dict[str, set[str]]:
        """Compute missing dependencies for the given active mod paths.

        :param active_mod_paths: Set of active mod paths
        :return: Mapping from package ID to set of missing dependency package IDs
        """
        active_package_ids: set[str] = set()
        for path in active_mod_paths:
            mod = self.mods_metadata.get(path)
            if isinstance(mod, AboutXmlMod):
                active_package_ids.add(str(mod.package_id))

        missing: dict[str, set[str]] = {}
        for path in active_mod_paths:
            mod = self.mods_metadata.get(path)
            if not isinstance(mod, AboutXmlMod):
                continue
            pid = str(mod.package_id)
            for dep_id in mod.overall_rules.dependencies:
                dep_str = str(dep_id)
                if dep_str not in active_package_ids:
                    missing.setdefault(pid, set()).add(dep_str)
        return missing

    def is_version_mismatch(self, path: str) -> bool:
        """Check if a mod has version mismatch with the current game version.

        :param path: Mod path
        :return: True if version mismatch, False otherwise
        """
        mod = self.mods_metadata.get(path)
        if not isinstance(mod, AboutXmlMod):
            return False
        if self.metadata_mediator.no_version_warning:
            pid = str(mod.package_id).lower()
            if pid in self.metadata_mediator.no_version_warning:
                return False
        if not mod.supported_versions:
            return False
        game_major_minor = ".".join(self.game_version.split(".")[:2])
        return game_major_minor not in mod.supported_versions

    def has_alternative_mod(self, path: str) -> ReplacementInfo | None:
        """Check if a mod has a recommended replacement from Use This Instead DB.

        Matches by the mod's published_file_id (Steam Workshop ID) against the
        ``oldWorkshopId`` entries in the database.

        :param path: Mod path
        :return: ReplacementInfo or None
        """
        mod = self.mods_metadata.get(path)
        if not isinstance(mod, AboutXmlMod):
            return None
        use_this_instead = self.metadata_mediator.use_this_instead
        if use_this_instead is None:
            return None
        pfid = mod.published_file_id
        if pfid is None:
            return None
        entry = use_this_instead.get(str(pfid))
        if entry is None:
            return None
        return ReplacementInfo(
            name=entry.get("newName", ""),
            author=entry.get("newAuthor", ""),
            packageid=entry.get("newPackageId", ""),
            pfid=entry.get("newWorkshopId", ""),
            supportedversions=entry.get("newVersions", []),
            source="database",
        )

    def get_mods_from_list(
        self,
        mod_list: str | list[str],
    ) -> tuple[list[str], list[str], dict[str, list[str]], list[str]]:
        """Given a mod list (file path or list of package IDs), compute active/inactive/duplicate/missing.

        :param mod_list: Path to .rws/.xml mod list file, or list of package IDs
        :return: (active_mod_paths, inactive_mod_paths, duplicate_mods, missing_mods)
        """
        SOURCE_PRIORITY_STEAM: list[ModType] = [ModType.STEAM_WORKSHOP, ModType.LOCAL]
        SOURCE_PRIORITY_DEFAULT: list[ModType] = [
            ModType.LUDEON,
            ModType.LOCAL,
            ModType.STEAM_WORKSHOP,
        ]

        all_mods = self.mods_metadata
        active_mod_paths: list[str] = []
        inactive_mod_paths: list[str] = []
        duplicate_mods: dict[str, list[str]] = {}
        duplicates_processed: list[str] = []
        missing_mods: list[str] = []
        populated_mods: list[str] = []
        to_populate: list[str] = []

        logger.debug("Started generating active and inactive mods")

        for path, mod_data in all_mods.items():
            if isinstance(mod_data, AboutXmlMod):
                pid = str(mod_data.package_id)
                duplicate_mods.setdefault(pid, []).append(path)
        duplicate_mods = {k: v for k, v in duplicate_mods.items() if len(v) > 1}

        if isinstance(mod_list, str):
            if not os.path.exists(mod_list):
                logger.debug(f"Could not find mods list at: {mod_list}")
                logger.debug("Creating an empty list with available expansions...")
                generated_xml = generate_rimworld_mods_list(
                    self.game_version, ["Ludeon.RimWorld"]
                )
                logger.debug(f"Saving new mods list to: {mod_list}")
                json_to_xml_write(generated_xml, mod_list)
            logger.info(f"Retrieving active mods from RimWorld mod list: {mod_list}")
            mod_data_xml = xml_path_to_json(mod_list)
            package_ids_to_import = validate_rimworld_mods_list(mod_data_xml)
        elif isinstance(mod_list, list):
            logger.info("Retrieving active mods from the provided list of package ids")
            package_ids_to_import = mod_list

        logger.info("Generating active mod list")
        for package_id in package_ids_to_import:
            package_id_normalized = package_id.lower()
            package_id_steam_suffix = "_steam"
            package_id_normalized_stripped = package_id_normalized.replace(
                package_id_steam_suffix, ""
            )
            is_steam = package_id_steam_suffix in package_id_normalized
            target_id = (
                package_id_normalized_stripped if is_steam else package_id_normalized
            )
            to_populate.append(target_id)
            sources_order = (
                SOURCE_PRIORITY_STEAM if is_steam else SOURCE_PRIORITY_DEFAULT
            )
            for path, mod in all_mods.items():
                if not isinstance(mod, AboutXmlMod):
                    continue
                metadata_package_id = str(mod.package_id)
                if metadata_package_id in [
                    package_id_normalized,
                    package_id_normalized_stripped,
                ]:
                    if target_id not in duplicate_mods:
                        populated_mods.append(target_id)
                        active_mod_paths.append(path)
                    else:
                        if target_id in duplicates_processed:
                            continue
                        logger.info(
                            f"Found duplicate mod present in active mods list: {target_id}"
                        )
                        for source_type in sources_order:
                            logger.debug(
                                f"Checking for duplicate with source: {source_type.value}"
                            )
                            matching_paths: list[str] = []
                            for dup_path in duplicate_mods[target_id]:
                                dup_mod = all_mods.get(dup_path)
                                if (
                                    isinstance(dup_mod, AboutXmlMod)
                                    and dup_mod.mod_type == source_type
                                ):
                                    matching_paths.append(dup_path)
                            source_paths_sorted = natsorted(matching_paths)
                            if source_paths_sorted:
                                calculated_dup = source_paths_sorted[0]
                                logger.debug(
                                    f"Using duplicate {source_type.value} mod for {target_id}: {calculated_dup}"
                                )
                                populated_mods.append(target_id)
                                duplicates_processed.append(target_id)
                                active_mod_paths.append(calculated_dup)
                                break

        missing_mods = list(set(to_populate) - set(populated_mods))
        logger.debug(f"Generated active mods with {len(active_mod_paths)} mods")

        logger.info("Generating inactive mod list")
        inactive_mod_paths = [
            path for path in all_mods.keys() if path not in active_mod_paths
        ]
        logger.info(f"# active mods: {len(active_mod_paths)}")
        logger.info(f"# inactive mods: {len(inactive_mod_paths)}")
        logger.info(f"# duplicate mods: {len(duplicate_mods)}")
        logger.info(f"# missing mods: {len(missing_mods)}")
        return active_mod_paths, inactive_mod_paths, duplicate_mods, missing_mods

    # ---- Mutations ----

    def _parse_single_mod(self, mod_path: str) -> bool:
        """Parse a single mod directory and merge the result into metadata.

        :param mod_path: Filesystem path to the mod directory
        :return: True if the mod was successfully parsed and is present in metadata
        """
        path = Path(mod_path)
        if not path.is_dir():
            return False
        if (
            self.metadata_mediator.local_mods_path is None
            or self.metadata_mediator.game_path is None
        ):
            return False
        if self.metadata_mediator._mods_metadata is None:
            return False

        prefer_versioned = self.settings.prefer_versioned_about_tags
        worker = self.metadata_mediator._ParserWorker(
            [path],
            self.metadata_mediator.game_version,
            self.metadata_mediator.local_mods_path,
            self.metadata_mediator.game_path,
            self.metadata_mediator.workshop_mods_path,
            self.metadata_mediator.user_rules,
            self.metadata_mediator.community_rules,
            self.metadata_mediator.steam_db,
            QMutex(),
            self.metadata_mediator.mods_metadata,
            prefer_versioned,
        )
        worker.run()

        return mod_path in self.mods_metadata

    @Slot(str, str)
    def process_creation(self, data_source: str, mod_path: str) -> None:
        """Parse a single mod and add it to metadata. Emits mod_created_signal."""
        if self._parse_single_mod(mod_path):
            self._invalidate_caches()
            self.mod_created_signal.emit(mod_path)

    @Slot(str, str)
    def process_deletion(self, data_source: str, mod_path: str) -> None:
        """Remove a mod from metadata and aux DB. Emits mod_deleted_signal."""
        if mod_path not in self.mods_metadata:
            return
        self.metadata_mediator.mods_metadata.pop(mod_path, None)
        with self.metadata_db_controller.Session() as session:
            self.metadata_db_controller.delete(session, Path(mod_path))
        self._invalidate_caches()
        self.mod_deleted_signal.emit(mod_path)

    @Slot(str, str)
    def process_update(self, data_source: str, mod_path: str) -> None:
        """Re-parse a single mod and update metadata. Emits mod_metadata_updated_signal."""
        if self._parse_single_mod(mod_path):
            self._invalidate_caches()
            self.mod_metadata_updated_signal.emit(mod_path)

    def delete_mod(self, *path: Path) -> None:
        """Delete one or more mods from metadata and aux DB by path.

        Does not remove mod files from disk. Emits ``mod_deleted_signal``
        for each removed path.

        :param path: One or more mod paths to remove
        """
        with self.metadata_db_controller.Session() as session:
            self.metadata_db_controller.delete(session, *path)

        for p in path:
            self.metadata_mediator.mods_metadata.pop(str(p), None)
            self.mod_deleted_signal.emit(str(p))

        self._invalidate_caches()

    def notify_files_deleted(self, mod_path: str) -> None:
        """Clean up metadata after a mod's files have been deleted externally.

        Removes the mod from the in-memory metadata cache and invalidates
        caches. Does not touch aux DB or filesystem — the caller is
        responsible for those.

        :param mod_path: The mod path key to remove from metadata
        """
        self.metadata_mediator.mods_metadata.pop(mod_path, None)
        self._invalidate_caches()
        self.mod_deleted_signal.emit(mod_path)

    def set_steam_db_blacklist(
        self,
        published_file_id: str,
        blacklisted: bool,
        comment: str = "",
    ) -> bool:
        """Set or clear the blacklist status for a SteamDB entry.

        Creates the entry if the published_file_id doesn't exist in the
        database yet. Persists the updated database to disk.

        :param published_file_id: The Steam Workshop published file ID
        :param blacklisted: True to blacklist, False to clear
        :param comment: Reason for blacklisting (ignored when clearing)
        :return: True if the operation succeeded, False if no DB loaded
        """
        steam_db = self.metadata_mediator.steam_db
        if steam_db is None or self.metadata_mediator.steam_db_path is None:
            return False

        if published_file_id not in steam_db.database:
            steam_db.database[published_file_id] = SteamDbEntry()

        entry = steam_db.database[published_file_id]

        if blacklisted:
            entry.blacklist = SteamDbEntryBlacklist(value=True, comment=comment)
        else:
            entry.blacklist = SteamDbEntryBlacklist()

        result = self._persist_steam_db()
        if result:
            self.steam_db_updated.emit()
        return result

    # ---- Private helpers ----

    def _invalidate_caches(self) -> None:
        self._packageid_to_paths_cache = None
        self._steamdb_packageid_to_name_cache = None

    @staticmethod
    def _resolve_db_path(
        source: str, file_path: str, repo_url: str, file_name: str
    ) -> Path | None:
        """Resolve the actual on-disk path for an external DB file.

        Mirrors the path resolution logic from ExternalMetadataLoader._get_repo_path:
        when the source is a URL or git repo, the download lands in
        ``AppInfo().databases_folder / <repo-name> / <file_name>``, not
        at the settings default.
        """
        if source == "Disabled":
            return None
        if source == "Configured file path":
            return Path(file_path) if file_path else None
        repo_name = Path(repo_url).name
        return AppInfo().databases_folder / repo_name / file_name

    def _persist_steam_db(self) -> bool:
        """Persist the in-memory SteamDbSchema to disk.

        Updates the version timestamp using the configured database_expiry
        offset, then serializes the full schema with msgspec.

        :return: True if written successfully, False if no DB or path
        """
        steam_db = self.metadata_mediator.steam_db
        steam_db_path = self.metadata_mediator.steam_db_path
        if steam_db is None or steam_db_path is None:
            return False

        steam_db.version = int(time.time() + self.settings.database_expiry)
        encoded = msgspec.json.encode(steam_db)
        formatted = msgspec.json.format(encoded, indent=4)
        steam_db_path.write_bytes(formatted)
        return True
