from pathlib import Path

from PySide6.QtCore import QObject, Slot

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


class MetadataController(QObject):
    """Controller class for metadata."""

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

    @Slot()
    def refresh_metadata(self) -> None:
        """Refresh the metadata."""
        self.metadata_mediator.refresh_metadata()
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

        cr_path = _get_path(active_settings.external_community_rules_file_path)
        steam_db_path = _get_path(active_settings.external_steam_metadata_file_path)
        workshop_mods_path = _get_path(active_instance.workshop_folder)
        local_mods_path = _get_path(active_instance.local_folder)
        game_path = _get_path(active_instance.game_folder)

        self.metadata_mediator.community_rules_path = cr_path
        self.metadata_mediator.steam_db_path = steam_db_path
        self.metadata_mediator.workshop_mods_path = workshop_mods_path
        self.metadata_mediator.local_mods_path = local_mods_path
        self.metadata_mediator.game_path = game_path

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

    @staticmethod
    def _build_compiled_data(
        mods_metadata: dict[str, ListedMod],
        use_moddependencies_as_loadTheseBefore: bool = False,
        use_alternative_package_ids_as_satisfying_dependencies: bool = True,
    ) -> CompiledDependencyData:
        """Build compiled dependency data from parsed mods.

        This is the core compilation step that replaces the old
        ``MetadataManager.compile_metadata()`` method.  It is a pure
        function (static method) so that it can be tested without
        instantiating any Qt objects or singletons.

        :param mods_metadata: Mapping of mod-path strings to ``ListedMod``
            objects, as produced by ``MetadataMediator``.
        :param use_moddependencies_as_loadTheseBefore: When *True*, treat
            declared ``modDependencies`` as implicit ``loadAfter`` edges.
        :param use_alternative_package_ids_as_satisfying_dependencies: When
            *True*, alternative package IDs on ``DependencyMod`` objects are
            considered valid satisfiers when building the dependency graph.
        :return: A fully-populated ``CompiledDependencyData`` instance.
        """
        compiled = CompiledDependencyData()

        # CRITICAL: copy the known-tier sets so we never mutate the module-level constants.
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

        # --- Step 2 & 3: Build forward and reverse dependency graphs ---
        for mod in mods_metadata.values():
            if not isinstance(mod, AboutXmlMod):
                continue

            pid = str(mod.package_id)

            # Choose rules variant based on the deps-as-load-order flag
            if use_moddependencies_as_loadTheseBefore:
                rules = mod.overall_rules_with_deps
            else:
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

            # --- Step 4: Record incompatibilities (only between existing mods) ---
            for incompat_ci in rules.incompatible_with:
                incompat = str(incompat_ci)
                if incompat not in all_package_ids:
                    continue
                compiled.incompatibilities.setdefault(pid, set()).add(incompat)

            # --- Step 5: Tier classification ---
            if rules.load_first and pid not in compiled.tier_zero_mods:
                compiled.tier_one_mods.add(pid)

            if rules.load_last:
                compiled.tier_three_mods.add(pid)

        return compiled
