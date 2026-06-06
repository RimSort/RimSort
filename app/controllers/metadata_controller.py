from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from PySide6.QtCore import QObject, Signal, Slot

from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController
from app.models.metadata.metadata_db import AuxMetadataEntry
from app.models.metadata.metadata_mediator import MetadataMediator
from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    CompiledDependencyData,
    ListedMod,
    ModType,
)
from app.utils.app_info import AppInfo
from app.utils.constants import KNOWN_TIER_ONE_MODS, KNOWN_TIER_ZERO_MODS
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface

if TYPE_CHECKING:
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

    def __init__(
        self,
        settings_controller: SettingsController,
        metadata_db_controller: AuxMetadataController,
    ) -> None:
        super().__init__()

        self.settings_controller = settings_controller

        self.metadata_mediator = MetadataMediator(
            user_rules_path=AppInfo().user_rules_file,
            community_rules_path=None,
            steam_db_path=None,
            workshop_mods_path=None,
            local_mods_path=None,
            game_path=None,
        )
        self.reset_paths()

        self.metadata_db_controller = metadata_db_controller
        self.steamcmd_wrapper = SteamcmdInterface.instance()

    @classmethod
    def instance(
        cls,
        settings_controller: SettingsController | None = None,
        metadata_db_controller: AuxMetadataController | None = None,
    ) -> MetadataController:
        """Get or create the singleton instance.

        :param settings_controller: Required on first call
        :param metadata_db_controller: Required on first call
        :return: The singleton instance
        :raises RuntimeError: If called before initialization
        """
        if cls._instance is None:
            if settings_controller is None or metadata_db_controller is None:
                raise RuntimeError(
                    "MetadataController.instance() called before initialization"
                )
            cls._instance = cls(settings_controller, metadata_db_controller)
        return cls._instance

    @Slot()
    def refresh_metadata(self) -> None:
        """Refresh the metadata."""
        self.reset_paths()
        prefer_versioned = self.settings_controller.settings.prefer_versioned_about_tags
        self.metadata_mediator.refresh_metadata(prefer_versioned=prefer_versioned)
        self._refresh_metadata_db()

        with self.metadata_db_controller.Session() as session:
            self.metadata_db_controller.update_from_acf(
                session,
                Path(self.steamcmd_wrapper.steamcmd_appworkshop_acf_path),
                ModType.STEAM_CMD,
            )

            if self.metadata_mediator.workshop_mods_path is not None:
                self.metadata_db_controller.update_from_acf(
                    session,
                    self.metadata_mediator.workshop_mods_path.parent.parent
                    / "appworkshop_294100.acf",
                    ModType.STEAM_WORKSHOP,
                )

    def _refresh_metadata_db(self) -> None:
        """Refresh the metadata database."""
        with self.metadata_db_controller.Session() as session:
            for path, mod_data in self.metadata_mediator.mods_metadata.items():
                entry = self.metadata_db_controller.get_or_create(session, path)

                entry.type = str(mod_data.mod_type)
                entry.published_file_id = mod_data.published_file_id

            session.commit()

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
        # "Configured URL" or "Configured git repository"
        repo_name = Path(repo_url).name
        return AppInfo().databases_folder / repo_name / file_name

    @Slot()
    def reset_paths(self) -> None:
        """Reset the paths.
        This is used when the paths are changed in the settings.

        Does not refresh the metadata.
        """

        def _get_path(path_str: str) -> Path | None:
            return Path(path_str) if path_str else None

        active_instance = self.settings_controller.active_instance
        active_settings = self.settings_controller.settings

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

        self.metadata_mediator.community_rules_path = cr_path
        self.metadata_mediator.steam_db_path = steam_db_path
        self.metadata_mediator.workshop_mods_path = workshop_mods_path
        self.metadata_mediator.local_mods_path = local_mods_path
        self.metadata_mediator.game_path = game_path
        self.metadata_mediator.no_version_warning_path = _get_path(
            active_settings.external_no_version_warning_file_path
        )
        self.metadata_mediator.use_this_instead_path = _get_path(
            active_settings.external_use_this_instead_file_path
        )

    def get_metadata_with_path(
        self, path: str | Path
    ) -> tuple[ListedMod, AuxMetadataEntry] | tuple[None, None]:
        mod_data = self.metadata_mediator.mods_metadata.get(str(path), None)
        if mod_data is None:
            return None, None

        with self.metadata_db_controller.Session() as session:
            entry = self.metadata_db_controller.get_or_create(session, path)

        return mod_data, entry

    @Slot(str)
    def delete_mod(self, *path: Path) -> None:
        """Delete a mod from the metadata, and aux metadata
        Does not remove the mod from disk.

        :param path:
        :type Path: Path
        """
        with self.metadata_db_controller.Session() as session:
            self.metadata_db_controller.delete(session, *path)

        for p in path:
            self.metadata_mediator.mods_metadata.pop(str(p), None)

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
        return self._build_compiled_data(
            self.metadata_mediator.mods_metadata,
            use_moddependencies_as_loadTheseBefore,
            use_alternative_package_ids,
        )

    @property
    def mods_metadata(self) -> dict[str, ListedMod]:
        """Get the current mods metadata dictionary."""
        return self.metadata_mediator.mods_metadata

    @property
    def packageid_to_paths(self) -> dict[str, set[str]]:
        """Build a mapping from package IDs to sets of mod paths."""
        result: dict[str, set[str]] = {}
        for path, mod in self.mods_metadata.items():
            if isinstance(mod, AboutXmlMod):
                pid = str(mod.package_id)
                result.setdefault(pid, set()).add(path)
        return result

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
    def steamdb_packageid_to_name(self) -> dict[str, str]:
        """Build a mapping from package IDs to Steam names from the Steam DB."""
        if self.metadata_mediator.steam_db is None:
            return {}
        return {
            pid: entry.steamName or entry.name
            for pid, entry in self.metadata_mediator.steam_db.database.items()
            if entry.steamName or entry.name
        }

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
        if not mod.supported_versions:
            return False
        game_major_minor = ".".join(self.game_version.split(".")[:2])
        return game_major_minor not in mod.supported_versions

    def has_alternative_mod(self, path: str) -> dict[str, Any] | None:
        """Check if a mod has a recommended replacement from Use This Instead DB.

        :param path: Mod path
        :return: Replacement info dict or None
        """
        mod = self.mods_metadata.get(path)
        if not isinstance(mod, AboutXmlMod):
            return None
        use_this_instead = self.metadata_mediator.use_this_instead
        if use_this_instead is None:
            return None
        pid = str(mod.package_id)
        return use_this_instead.get(pid)

    @staticmethod
    def _build_compiled_data(
        mods_metadata: Mapping[str, ListedMod],
        use_moddependencies_as_loadTheseBefore: bool = False,
        use_alternative_package_ids: bool = False,
    ) -> CompiledDependencyData:
        """Build compiled dependency data from parsed mods.

        When ``use_moddependencies_as_loadTheseBefore`` is True, declared
        ``modDependencies`` are treated as implicit ``loadAfter`` edges.
        Explicit load-order rules always take precedence: if an explicit
        rule says A loads after B, an inferred rule saying B loads after A
        is silently dropped to avoid creating a cycle.

        :param mods_metadata: Mapping of mod-path strings to ``ListedMod``.
        :param use_moddependencies_as_loadTheseBefore: Treat modDependencies as loadAfter.
        :param use_alternative_package_ids: Fall back to alternative package IDs for deps.
        :return: A fully-populated ``CompiledDependencyData`` instance.
        """
        compiled = CompiledDependencyData()

        compiled.tier_zero_mods = KNOWN_TIER_ZERO_MODS.copy()
        compiled.tier_one_mods = KNOWN_TIER_ONE_MODS.copy()

        # --- Step 1: Build packageid -> set[path] index and collect all known pids ---
        packageid_to_paths: dict[str, set[str]] = {}
        all_package_ids: set[str] = set()

        for path_str, mod in mods_metadata.items():
            if not isinstance(mod, AboutXmlMod):
                continue
            pid = str(mod.package_id)
            all_package_ids.add(pid)
            packageid_to_paths.setdefault(pid, set()).add(path_str)

        # --- Step 2: Build explicit forward and reverse dependency graphs ---
        for mod in mods_metadata.values():
            if not isinstance(mod, AboutXmlMod):
                continue

            pid = str(mod.package_id)
            rules = mod.overall_rules

            # load_after: "I (pid) load after dep" -> pid depends on dep
            for dep_ci in rules.load_after:
                dep = str(dep_ci)
                if dep not in all_package_ids:
                    continue
                compiled.deps_graph.setdefault(pid, set()).add(dep)
                compiled.rev_deps_graph.setdefault(dep, set()).add(pid)

            # load_before: "I (pid) load before target" -> target depends on pid
            for target_ci in rules.load_before:
                target = str(target_ci)
                if target not in all_package_ids:
                    continue
                compiled.deps_graph.setdefault(target, set()).add(pid)
                compiled.rev_deps_graph.setdefault(pid, set()).add(target)

            # --- Step 3: Record incompatibilities ---
            for incompat_ci in rules.incompatible_with:
                incompat = str(incompat_ci)
                if incompat not in all_package_ids:
                    continue
                compiled.incompatibilities.setdefault(pid, set()).add(incompat)

            # --- Step 4: Tier classification ---
            if rules.load_first and pid not in compiled.tier_zero_mods:
                compiled.tier_one_mods.add(pid)

            if rules.load_last:
                compiled.tier_three_mods.add(pid)

        # --- Step 5: Inferred edges from dependencies (with conflict resolution) ---
        # Matches old gen_tier_two_deps_graph: skip tier-one and tier-three mods
        # (both as source and target). Tier-zero is NOT excluded — the old code
        # allowed inferred edges involving Core/DLCs within tier-two processing.
        if use_moddependencies_as_loadTheseBefore:
            excluded_tiers = compiled.tier_one_mods | compiled.tier_three_mods
            conflicts_ignored = 0
            for mod in mods_metadata.values():
                if not isinstance(mod, AboutXmlMod):
                    continue
                pid = str(mod.package_id)
                if pid in excluded_tiers:
                    continue
                for dep_mod in mod.overall_rules.dependencies.values():
                    dep = str(dep_mod.package_id)
                    # Resolve: prefer primary, fall back to alternative if enabled
                    if dep not in all_package_ids:
                        if not use_alternative_package_ids:
                            continue
                        resolved = None
                        for alt in dep_mod.alternative_package_ids:
                            alt_str = str(alt)
                            if alt_str in all_package_ids:
                                resolved = alt_str
                                break
                        if resolved is None:
                            continue
                        dep = resolved
                    if dep in excluded_tiers:
                        continue
                    # Conflict check: would adding pid -> dep contradict
                    # an existing explicit edge dep -> pid?
                    if pid in compiled.deps_graph.get(dep, set()):
                        logger.warning(
                            f"Ignoring inferred dependency {pid} -> {dep}: "
                            f"conflicts with explicit rule {dep} -> {pid}"
                        )
                        conflicts_ignored += 1
                        continue
                    compiled.deps_graph.setdefault(pid, set()).add(dep)
                    compiled.rev_deps_graph.setdefault(dep, set()).add(pid)

            if conflicts_ignored > 0:
                logger.info(
                    f"Resolved {conflicts_ignored} conflicts by prioritizing "
                    f"explicit load order rules over inferred dependencies"
                )

        return compiled
