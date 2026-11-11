"""Headless implementation of RimSort's MCP tool surface.

Everything here drives the real application stack — :class:`MetadataController`,
:class:`Sorter`, :class:`ImportExportService` — with no Qt widgets, dialogs or
event loops involved, so the tools can be served over a stdio MCP transport
while the GUI owns a different process.

Tool payloads are agent-facing JSON, so the strings in them are plain English
rather than Qt translations (they never reach a QWidget).
"""

from __future__ import annotations

import shutil
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from app.controllers.metadata_controller import MetadataController
from app.controllers.sort_controller import Sorter
from app.models.instance import Instance
from app.models.metadata.metadata_factory import value_extractor
from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    CaseInsensitiveStr,
    ModsConfig,
    ModType,
    SteamDbEntry,
)
from app.models.settings import Settings
from app.services.dependency_resolver import build_dependencies_dialog_context
from app.services.import_export_service import ImportExportService
from app.sort import topo_sort as topo_sort_module
from app.utils.app_info import AppInfo
from app.utils.constants import RIMWORLD_DLC_METADATA
from app.utils.mod_info import parse_major_minor
from app.utils.xml import xml_path_to_json

MODS_CONFIG_FILENAME = "ModsConfig.xml"
MAX_SEARCH_RESULTS = 200
DESCRIPTION_LIMIT = 500
CORE_PACKAGE_ID = "ludeon.rimworld"
_STEAM_SUFFIX = "_steam"

Diagnostic = dict[str, Any]

_sort_dialog_lock = threading.Lock()
_sort_dialog_depth = 0
_sort_dialog_original: Callable[..., None] | None = None
_sort_dialog_tls = threading.local()


def _diagnostic(kind: str, message: str, **extra: Any) -> Diagnostic:
    """Build one structured warning/error record."""
    return {"type": kind, "message": message, **extra}


def _supporting_major_minor(supported_versions: set[str]) -> list[str]:
    """Normalize a mod's ``supportedVersions`` entries to ``major.minor``."""
    normalized: set[str] = set()
    for version in supported_versions:
        parsed = parse_major_minor(version)
        if parsed is not None:
            normalized.add(f"{parsed[0]}.{parsed[1]}")
    return sorted(normalized)


def _strip_steam_suffix(package_id: str) -> str:
    """Return the bare package ID, dropping a trailing ``_steam`` suffix."""
    if package_id.lower().endswith(_STEAM_SUFFIX):
        return package_id[: -len(_STEAM_SUFFIX)]
    return package_id


def _intercepted_show_warning(
    title: str | None = None,
    text: str | None = None,
    information: str | None = None,
    details: str | None = None,
    parent: Any = None,
) -> None:
    """Headless stand-in for ``topo_sort.show_warning`` while sorts are active."""
    captured = getattr(_sort_dialog_tls, "captured", None)
    if captured is not None:
        captured.append(
            {
                "title": title,
                "text": text,
                "information": information,
                "details": details,
            }
        )
        return
    logger.warning(
        "topo_sort.show_warning fired without an MCP capture sink "
        f"(title={title!r}, text={text!r})"
    )


@contextmanager
def _capture_sort_dialogs() -> Iterator[list[dict[str, Any]]]:
    """Capture the modal warnings the sort pipeline would otherwise block on.

    ``do_topo_sort`` reports circular dependencies through
    ``app.sort.topo_sort.show_warning``, which spins a ``QMessageBox`` and would
    hang a headless server. The dialog payloads are collected instead so the
    caller can turn them into structured diagnostics.

    Overlapping sorts share one interceptor under a refcount: the real dialog
    callback is restored only when the outermost capture exits.
    """
    global _sort_dialog_depth, _sort_dialog_original

    captured: list[dict[str, Any]] = []
    with _sort_dialog_lock:
        if _sort_dialog_depth == 0:
            _sort_dialog_original = topo_sort_module.show_warning
            topo_sort_module.show_warning = _intercepted_show_warning
        _sort_dialog_depth += 1
    _sort_dialog_tls.captured = captured
    try:
        yield captured
    finally:
        _sort_dialog_tls.captured = None
        with _sort_dialog_lock:
            _sort_dialog_depth -= 1
            if _sort_dialog_depth == 0:
                if _sort_dialog_original is not None:
                    topo_sort_module.show_warning = _sort_dialog_original
                _sort_dialog_original = None


class RimSortMcpCore:
    """Tool implementations backed by RimSort's live metadata state."""

    def __init__(
        self,
        settings: Settings,
        metadata_controller: MetadataController,
    ) -> None:
        self.settings = settings
        self.metadata_controller = metadata_controller
        self._packageid_to_steam_entry: dict[str, SteamDbEntry] | None = None
        # ``--instance`` (or the active instance at bootstrap) must survive
        # ``Settings.load()`` during metadata refresh.
        self._bound_instance_name = settings.current_instance

    # ---- shared helpers ----

    @property
    def instance(self) -> Instance:
        """The RimWorld instance the server is bound to."""
        return self.settings.instances[self.settings.current_instance]

    @property
    def mods_config_path(self) -> Path | None:
        """Path to the instance's ``ModsConfig.xml``, when configured."""
        config_folder = self.instance.config_folder
        if not config_folder:
            return None
        return Path(config_folder) / MODS_CONFIG_FILENAME

    def _read_mods_config(self) -> ModsConfig | None:
        """Parse the instance's ``ModsConfig.xml``.

        :meth:`MetadataController.get_mods_from_list` reads the same file, but
        it *creates* a default list when the file is missing; a read-only tool
        must not have that side effect, and the parser here tolerates files that
        omit ``knownExpansions`` (which RimWorld itself allows).

        :return: The parsed config, or None when absent or unparseable
        """
        path = self.mods_config_path
        if path is None or not path.is_file():
            return None
        raw = xml_path_to_json(str(path))
        container = raw.get("ModsConfigData")
        if not isinstance(container, dict):
            logger.warning(f"ModsConfig.xml at {path} has no ModsConfigData root")
            return None

        active = value_extractor(container.get("activeMods", []))
        expansions = value_extractor(container.get("knownExpansions", []))
        version = value_extractor(container.get("version", "Unknown"))
        active_ids = [active] if isinstance(active, str) else active
        expansion_ids = [expansions] if isinstance(expansions, str) else expansions
        return ModsConfig(
            version=version if isinstance(version, str) else "Unknown",
            activeMods=[CaseInsensitiveStr(str(item)) for item in active_ids if item],
            knownExpansions=[
                CaseInsensitiveStr(str(item)) for item in expansion_ids if item
            ],
        )

    def _active_mod_paths(self) -> set[str]:
        """Resolve the currently active mods to their metadata path keys."""
        mods_config = self._read_mods_config()
        if mods_config is None:
            return set()
        active_paths, _inactive, _duplicates, _missing = (
            self.metadata_controller.get_mods_from_list(
                mod_list=[str(package_id) for package_id in mods_config.activeMods]
            )
        )
        return set(active_paths)

    def _about_mods(self) -> list[AboutXmlMod]:
        """Every installed mod that carries ``About.xml`` metadata."""
        return [
            mod
            for mod in self.metadata_controller.mods_metadata.values()
            if isinstance(mod, AboutXmlMod)
        ]

    def _resolve_package_ids(
        self, package_ids: list[str]
    ) -> tuple[list[AboutXmlMod], list[str], dict[str, list[str]]]:
        """Resolve package IDs to installed mods, preserving request order.

        Resolution reuses :meth:`MetadataController.get_mods_from_list` so the
        ``_steam`` suffix and duplicate-copy precedence behave exactly like the
        GUI's import path.

        :param package_ids: Package IDs to resolve, in the requested order
        :return: ``(resolved mods, unresolved package IDs, duplicate map)``
        """
        normalized = [
            package_id.strip()
            for package_id in package_ids
            if isinstance(package_id, str) and package_id.strip()
        ]
        if not normalized:
            return [], [], {}
        paths, _inactive, duplicates, missing = (
            self.metadata_controller.get_mods_from_list(mod_list=normalized)
        )
        mods = []
        for path in paths:
            mod = self.metadata_controller.get_mod(path)
            if isinstance(mod, AboutXmlMod):
                mods.append(mod)
        return mods, missing, duplicates

    def _steam_entry_for(self, package_id: str) -> SteamDbEntry | None:
        """Look up the Steam Workshop DB entry for a package ID."""
        if self._packageid_to_steam_entry is None:
            mapping: dict[str, SteamDbEntry] = {}
            steam_db = self.metadata_controller.steam_db
            if steam_db is not None:
                for entry in steam_db.database.values():
                    if entry.packageId:
                        mapping.setdefault(entry.packageId.lower(), entry)
            self._packageid_to_steam_entry = mapping
        return self._packageid_to_steam_entry.get(package_id.lower())

    @staticmethod
    def _dedupe(package_ids: list[str]) -> list[str]:
        """Drop blank and case-insensitively duplicate package IDs, keep order."""
        seen: set[str] = set()
        result: list[str] = []
        for package_id in package_ids:
            if not isinstance(package_id, str):
                continue
            cleaned = package_id.strip()
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            result.append(cleaned)
        return result

    def _ensure_core_content(self, package_ids: list[str]) -> list[str]:
        """Add the base game (and already-enabled DLC) when the caller omits it.

        DLC is only added when it is currently active in ``ModsConfig.xml``:
        silently enabling an expansion the player deliberately disabled would
        change their save.
        """
        candidates = self._dedupe(package_ids)
        present = {package_id.lower() for package_id in candidates}
        installed = set(self.metadata_controller.packageid_to_paths)

        mods_config = self._read_mods_config()
        active_now = (
            {str(package_id).lower() for package_id in mods_config.activeMods}
            if mods_config is not None
            else set()
        )

        additions: list[str] = []
        for metadata in RIMWORLD_DLC_METADATA.values():
            package_id = metadata["packageid"]
            if package_id.lower() in present or package_id not in installed:
                continue
            if package_id.lower() == "ludeon.rimworld":
                additions.insert(0, package_id)
            elif package_id.lower() in active_now:
                additions.append(package_id)

        # Keep the canonical DLC order (base game first, then release order).
        order = {
            metadata["packageid"].lower(): index
            for index, metadata in enumerate(RIMWORLD_DLC_METADATA.values())
        }
        additions.sort(key=lambda package_id: order.get(package_id.lower(), 0))
        return additions + candidates

    # ---- tool 1 ----

    def get_instance_status(self) -> dict[str, Any]:
        """Report the bound instance, game version, paths and mod counts."""
        about_mods = self._about_mods()
        active_paths = self._active_mod_paths()
        mods_config = self._read_mods_config()
        duplicates = sorted(
            package_id
            for package_id, paths in self.metadata_controller.packageid_to_paths.items()
            if len(paths) > 1
        )
        instance = self.instance
        return {
            "instance_name": self.settings.current_instance,
            "game_version": self.metadata_controller.game_version,
            "is_waylith": self.metadata_controller.is_waylith,
            "paths": {
                "game_folder": instance.game_folder,
                "config_folder": instance.config_folder,
                "local_folder": instance.local_folder,
                "workshop_folder": instance.workshop_folder,
                "mods_config": (
                    str(self.mods_config_path) if self.mods_config_path else None
                ),
            },
            "database_paths": {
                "steam_db": (
                    str(path)
                    if (path := self.metadata_controller.steam_db_path) is not None
                    else None
                ),
                "community_rules": (
                    str(path)
                    if (path := self.metadata_controller.community_rules_path)
                    is not None
                    else None
                ),
                "user_rules": str(AppInfo().user_rules_file),
            },
            "total_installed_mods": len({str(mod.package_id) for mod in about_mods}),
            "total_mod_entries": len(about_mods),
            "active_mods_count": len(active_paths),
            "active_mods_declared_count": (
                len(mods_config.activeMods) if mods_config is not None else 0
            ),
            "known_expansions": (
                [str(package_id) for package_id in mods_config.knownExpansions]
                if mods_config is not None
                else []
            ),
            "duplicate_package_ids": duplicates,
        }

    # ---- tool 2 ----

    def search_installed_mods(
        self,
        query: str = "",
        supported_version: str | None = None,
        active_only: bool = False,
        include_description: bool = False,
    ) -> list[dict[str, Any]]:
        """Search installed mods by keyword, version and active state."""
        tokens = [token for token in query.casefold().split() if token]
        wanted_version = (
            parse_major_minor(supported_version) if supported_version else None
        )
        active_paths = self._active_mod_paths()

        results: list[dict[str, Any]] = []
        for mod in self._about_mods():
            is_active = mod.uuid in active_paths
            if active_only and not is_active:
                continue

            versions = _supporting_major_minor(mod.supported_versions)
            if wanted_version is not None:
                wanted = f"{wanted_version[0]}.{wanted_version[1]}"
                if wanted not in versions:
                    continue

            if tokens:
                haystack = " ".join(
                    (
                        mod.name or "",
                        str(mod.package_id),
                        " ".join(str(author) for author in mod.authors),
                        mod.description or "",
                    )
                ).casefold()
                if not all(token in haystack for token in tokens):
                    continue

            record: dict[str, Any] = {
                "packageid": str(mod.package_id),
                "name": mod.name,
                "uuid": mod.uuid,
                "authors": [str(author) for author in mod.authors],
                "supportedversions": versions,
                "path": str(mod.mod_path) if mod.mod_path is not None else None,
                "workshop_id": mod.published_file_id,
                "is_active": is_active,
                "mod_type": mod.mod_type.value,
            }
            if include_description:
                description = mod.description or ""
                if len(description) > DESCRIPTION_LIMIT:
                    description = description[:DESCRIPTION_LIMIT] + "..."
                record["description"] = description
            results.append(record)

        # Sort before truncating so the retained subset is deterministic rather
        # than dependent on directory iteration order.
        results.sort(key=lambda record: str(record["name"]).casefold())
        total_matches = len(results)
        if total_matches > MAX_SEARCH_RESULTS:
            results = results[:MAX_SEARCH_RESULTS]
            returned = len(results)
            results.append(
                {
                    "truncated": True,
                    "total_matches": total_matches,
                    "returned": returned,
                    "hint": (
                        "Narrow the query, or call get_mod_details with explicit "
                        "package IDs, to see the remaining matches."
                    ),
                }
            )
        return results

    # ---- tool 3 ----

    def get_mod_details(self, package_ids: list[str]) -> dict[str, Any]:
        """Return full metadata and rule sets for the given package IDs."""
        requested = self._dedupe(package_ids)
        mods, unresolved, _duplicates = self._resolve_package_ids(requested)
        details: dict[str, Any] = {}
        for mod in mods:
            package_id = str(mod.package_id)
            rules = mod.overall_rules
            steam_entry = self._steam_entry_for(package_id)
            details[package_id] = {
                "packageid": package_id,
                "name": mod.name,
                "uuid": mod.uuid,
                "path": str(mod.mod_path) if mod.mod_path is not None else None,
                "mod_type": mod.mod_type.value,
                "workshop_id": mod.published_file_id,
                "authors": [str(author) for author in mod.authors],
                "mod_version": mod.mod_version,
                "url": mod.url,
                "supportedversions": sorted(mod.supported_versions),
                "dependencies": [
                    {
                        "packageid": str(dep_id),
                        "name": dependency.name,
                        "workshop_url": dependency.workshop_url,
                        "alternative_package_ids": sorted(
                            str(alt) for alt in dependency.alternative_package_ids
                        ),
                    }
                    for dep_id, dependency in rules.dependencies.items()
                ],
                "loadbefore": sorted(str(entry) for entry in rules.load_before),
                "loadafter": sorted(str(entry) for entry in rules.load_after),
                "incompatiblewith": sorted(
                    str(entry) for entry in rules.incompatible_with
                ),
                "load_first": rules.load_first,
                "load_last": rules.load_last,
                "description": mod.description,
                "community_rules": {
                    "loadbefore": sorted(
                        str(entry) for entry in mod.community_rules.load_before
                    ),
                    "loadafter": sorted(
                        str(entry) for entry in mod.community_rules.load_after
                    ),
                    "load_first": mod.community_rules.load_first,
                    "load_last": mod.community_rules.load_last,
                },
                "user_rules": {
                    "loadbefore": sorted(
                        str(entry) for entry in mod.user_rules.load_before
                    ),
                    "loadafter": sorted(
                        str(entry) for entry in mod.user_rules.load_after
                    ),
                    "load_first": mod.user_rules.load_first,
                    "load_last": mod.user_rules.load_last,
                },
                "steam_db_entry": (
                    {
                        "name": steam_entry.name,
                        "steam_name": steam_entry.steamName,
                        "url": steam_entry.url,
                        "unpublished": steam_entry.unpublished,
                        "game_versions": steam_entry.gameVersions,
                        "tags": steam_entry.tags,
                        "blacklisted": steam_entry.blacklist.value,
                        "blacklist_comment": steam_entry.blacklist.comment,
                    }
                    if steam_entry is not None
                    else None
                ),
            }
        return {
            "requested": requested,
            "found": list(details),
            "not_found": unresolved,
            "mods": details,
        }

    # ---- tool 4 ----

    def get_active_modlist(self) -> dict[str, Any]:
        """Return the ordered ``ModsConfig.xml`` list and any missing entries."""
        path = self.mods_config_path
        mods_config = self._read_mods_config()
        if mods_config is None:
            return {
                "mods_config_path": str(path) if path else None,
                "found": False,
                "active_mods": [],
                "missing": [],
                "known_expansions": [],
                "game_version_in_file": None,
            }

        declared = [str(package_id) for package_id in mods_config.activeMods]
        mods, missing, _duplicates = self._resolve_package_ids(declared)
        ordered = [
            {
                "packageid": str(mod.package_id),
                "name": mod.name,
                "supportedversions": sorted(mod.supported_versions),
                "workshop_id": mod.published_file_id,
            }
            for mod in mods
        ]
        return {
            "mods_config_path": str(path) if path else None,
            "found": True,
            "count": len(declared),
            "active_mods": ordered,
            "missing": missing,
            "known_expansions": [
                str(package_id) for package_id in mods_config.knownExpansions
            ],
            "game_version_in_file": mods_config.version,
        }

    # ---- tool 5 ----

    def analyze_and_sort_modlist(self, package_ids: list[str]) -> dict[str, Any]:
        """Validate a candidate list and run RimSort's native sort on it."""
        candidate_ids = self._ensure_core_content(package_ids)
        mods, unresolved, duplicates = self._resolve_package_ids(candidate_ids)
        mods_by_pid = {str(mod.package_id): mod for mod in mods}
        mods_by_uuid = {mod.uuid: mod for mod in mods}
        active_paths = {mod.uuid for mod in mods if mod.mod_path is not None}

        warnings: list[Diagnostic] = []
        errors: list[Diagnostic] = []
        for package_id in unresolved:
            errors.append(
                _diagnostic(
                    "unresolved_package_id",
                    f"{package_id} is not installed; it cannot be sorted or saved.",
                    packageid=package_id,
                )
            )

        missing_installed, missing_uninstalled = self._dependency_diagnostics(
            active_paths, warnings
        )
        incompatibilities = self._incompatibility_diagnostics(mods, warnings)
        version_mismatches = self._version_mismatch_diagnostics(mods, warnings)

        compiled = self.metadata_controller.compile(
            use_moddependencies_as_loadTheseBefore=(
                self.settings.use_moddependencies_as_loadTheseBefore
            ),
            use_alternative_package_ids=(
                self.settings.use_alternative_package_ids_as_satisfying_dependencies
            ),
        )
        algorithm = self.settings.sorting_algorithm
        sorted_package_ids: list[str] = []
        sort_success = False
        try:
            sorter = Sorter(
                algorithm,
                compiled,
                self.metadata_controller.mods_metadata,
                active_paths,
            )
            with _capture_sort_dialogs() as captured:
                sort_success, sorted_paths = sorter.sort()
        except NotImplementedError as exc:
            errors.append(_diagnostic("sorting_algorithm_unimplemented", str(exc)))
            sorted_paths = []
        else:
            if sort_success:
                # Emit ModsConfig identities (including ``_steam``) so callers that
                # write the sorted list keep the Workshop copy analysis chose.
                sorted_package_ids = [
                    self._config_package_id(mods_by_uuid[path], duplicates)
                    for path in sorted_paths
                    if path in mods_by_uuid
                ]
                warnings.extend(
                    self._load_order_violations(sorted_package_ids, mods_by_pid)
                )
            else:
                cycles = [
                    detail
                    for payload in captured
                    for detail in (payload.get("details") or "").split("\n\n")
                    if detail.strip()
                ]
                errors.append(
                    _diagnostic(
                        "circular_dependency",
                        "The dependency graph contains a cycle; no load order can "
                        "satisfy it. Break the cycle in the mods' About.xml or the "
                        "rules database.",
                        cycles=cycles,
                    )
                )

        sorted_bare = {_strip_steam_suffix(pid) for pid in sorted_package_ids}
        dropped = sorted(set(mods_by_pid) - sorted_bare)
        if sort_success and dropped:
            warnings.append(
                _diagnostic(
                    "mods_dropped_from_sort",
                    "RimSort could not place these mods in the load order.",
                    packageids=dropped,
                )
            )

        return {
            "game_version": self.metadata_controller.game_version,
            "sorting_algorithm": str(getattr(algorithm, "value", algorithm)),
            "sort_success": sort_success,
            "input_package_ids": self._dedupe(package_ids),
            "candidate_package_ids": candidate_ids,
            "sorted_package_ids": sorted_package_ids,
            "unresolved_package_ids": unresolved,
            "missing_installed_dependencies": missing_installed,
            "missing_uninstalled_dependencies": missing_uninstalled,
            "incompatibilities": incompatibilities,
            "version_mismatches": version_mismatches,
            "warnings": warnings,
            "errors": errors,
        }

    def _dependency_diagnostics(
        self, active_paths: set[str], warnings: list[Diagnostic]
    ) -> tuple[list[Diagnostic], list[Diagnostic]]:
        """Split unsatisfied dependencies into installed and not-installed."""
        _summary, missing_deps, dep_resolve = build_dependencies_dialog_context(
            self.metadata_controller, active_paths
        )
        active_pids = {
            str(mod.package_id)
            for mod in self._about_mods()
            if mod.uuid in active_paths
        }
        installed_pids = set(self.metadata_controller.packageid_to_paths)

        missing_installed: list[Diagnostic] = []
        missing_uninstalled: list[Diagnostic] = []
        for required_by, dependencies in sorted(missing_deps.items()):
            for dependency in sorted(dependencies):
                if dependency in installed_pids:
                    missing_installed.append(
                        {
                            "packageid": dependency,
                            "required_by": required_by,
                            "reason": "installed but not part of the requested list",
                        }
                    )
                    continue
                resolved = dep_resolve.get(dependency)
                missing_uninstalled.append(
                    {
                        "packageid": dependency,
                        "required_by": required_by,
                        "workshop_id": resolved.workshop_id
                        if resolved is not None
                        else None,
                        "workshop_url": resolved.workshop_url
                        if resolved is not None
                        else None,
                    }
                )
        for entry in missing_installed:
            warnings.append(
                _diagnostic(
                    "missing_dependency_installed",
                    f"{entry['required_by']} requires {entry['packageid']}, which "
                    "is installed but not in the list.",
                    packageid=entry["packageid"],
                    required_by=entry["required_by"],
                )
            )
        for entry in missing_uninstalled:
            warnings.append(
                _diagnostic(
                    "missing_dependency_uninstalled",
                    f"{entry['required_by']} requires {entry['packageid']}, which "
                    "is not installed.",
                    packageid=entry["packageid"],
                    required_by=entry["required_by"],
                    workshop_id=entry["workshop_id"],
                )
            )
        logger.debug(
            f"MCP analysis: {len(active_pids)} active mods, "
            f"{len(missing_installed)} local + {len(missing_uninstalled)} "
            "downloadable missing dependencies"
        )
        return missing_installed, missing_uninstalled

    def _incompatibility_diagnostics(
        self, mods: list[AboutXmlMod], warnings: list[Diagnostic]
    ) -> list[Diagnostic]:
        """Report declared ``incompatibleWith`` pairs among the candidate mods."""
        active_pids = {str(mod.package_id) for mod in mods}
        conflicts: list[Diagnostic] = []
        seen: set[tuple[str, str]] = set()
        for mod in mods:
            for other_id in mod.overall_rules.incompatible_with:
                other = str(other_id)
                if other not in active_pids or other == str(mod.package_id):
                    continue
                this_id = str(mod.package_id)
                pair: tuple[str, str] = (
                    (this_id, other) if this_id <= other else (other, this_id)
                )
                if pair in seen:
                    continue
                seen.add(pair)
                conflicts.append(
                    {
                        "packageids": list(pair),
                        "declared_by": str(mod.package_id),
                    }
                )
        for conflict in conflicts:
            warnings.append(
                _diagnostic(
                    "incompatible_mods",
                    f"{conflict['packageids'][0]} and "
                    f"{conflict['packageids'][1]} declare incompatibility.",
                    packageids=conflict["packageids"],
                )
            )
        return conflicts

    def _version_mismatch_diagnostics(
        self, mods: list[AboutXmlMod], warnings: list[Diagnostic]
    ) -> list[Diagnostic]:
        """Report mods that do not support the detected game version."""
        mismatches: list[Diagnostic] = []
        for mod in mods:
            path = mod.uuid
            if not self.metadata_controller.is_version_mismatch(path):
                continue
            soft = self.metadata_controller.is_soft_version_mismatch(path)
            entry = {
                "packageid": str(mod.package_id),
                "supportedversions": sorted(mod.supported_versions),
                "game_version": self.metadata_controller.game_version,
                "soft": soft,
            }
            mismatches.append(entry)
            warnings.append(
                _diagnostic(
                    "version_mismatch_soft" if soft else "version_mismatch",
                    f"{mod.package_id} does not list support for game version "
                    f"{self.metadata_controller.game_version}.",
                    **entry,
                )
            )
        return mismatches

    def _load_order_violations(
        self, sorted_package_ids: list[str], mods_by_pid: Mapping[str, AboutXmlMod]
    ) -> list[Diagnostic]:
        """Verify the produced order honours explicit load-order rules."""
        position = {
            _strip_steam_suffix(package_id): index
            for index, package_id in enumerate(sorted_package_ids)
        }
        violations: list[Diagnostic] = []
        for package_id, mod in mods_by_pid.items():
            if package_id not in position:
                continue
            rules = mod.overall_rules
            for other_id in rules.load_after:
                other = str(other_id)
                if other in position and position[other] > position[package_id]:
                    violations.append(
                        _diagnostic(
                            "load_order_violation",
                            f"{package_id} must load after {other} but does not.",
                            packageid=package_id,
                            relation="loadAfter",
                            target=other,
                        )
                    )
            for other_id in rules.load_before:
                other = str(other_id)
                if other in position and position[other] < position[package_id]:
                    violations.append(
                        _diagnostic(
                            "load_order_violation",
                            f"{package_id} must load before {other} but does not.",
                            packageid=package_id,
                            relation="loadBefore",
                            target=other,
                        )
                    )
        return violations

    # ---- tool 6 ----

    def apply_active_modlist(
        self,
        package_ids: list[str],
        auto_sort: bool = True,
        create_backup: bool = True,
    ) -> dict[str, Any]:
        """Write a validated load order to the instance's ``ModsConfig.xml``."""
        mods_config_path = self.mods_config_path
        if mods_config_path is None:
            return {
                "saved": False,
                "errors": [
                    _diagnostic(
                        "config_folder_missing",
                        "The instance has no config folder configured; "
                        "ModsConfig.xml cannot be written.",
                    )
                ],
                "warnings": [],
                "mods_config_path": None,
                "backup_path": None,
                "sorted_package_ids": [],
            }

        # An empty/Unknown write is worse than refusing: if Core never made it
        # into metadata (bad game folder, failed scan), do not clobber the file.
        if not self._core_is_resolvable():
            return {
                "saved": False,
                "errors": [
                    _diagnostic(
                        "core_unresolved",
                        "RimWorld Core is not available in metadata; refusing "
                        "to write ModsConfig.xml. Fix the game folder path and "
                        "refresh metadata.",
                    )
                ],
                "warnings": [],
                "mods_config_path": str(mods_config_path),
                "backup_path": None,
                "sorted_package_ids": [],
            }

        analysis = self.analyze_and_sort_modlist(package_ids)
        warnings = list(analysis["warnings"])
        errors = list(analysis["errors"])

        # Writes are refused for anything the caller asked for but we could not
        # resolve: silently dropping a package ID would save a list the caller
        # never asked for. Reinstalling or fixing the ID is the caller's call.
        if analysis["unresolved_package_ids"]:
            return {
                "saved": False,
                "errors": errors,
                "warnings": warnings,
                "mods_config_path": str(mods_config_path),
                "backup_path": None,
                "sorted_package_ids": [],
            }

        if auto_sort:
            if not analysis["sort_success"]:
                errors.append(
                    _diagnostic(
                        "sort_failed",
                        "Refusing to write a list that could not be sorted.",
                    )
                )
                return {
                    "saved": False,
                    "errors": errors,
                    "warnings": warnings,
                    "mods_config_path": str(mods_config_path),
                    "backup_path": None,
                    "sorted_package_ids": [],
                }
            final_ids = list(analysis["sorted_package_ids"])
        else:
            mods, _unresolved, duplicates = self._resolve_package_ids(
                self._ensure_core_content(package_ids)
            )
            final_ids = [self._config_package_id(mod, duplicates) for mod in mods]

        mods, unresolved, duplicates = self._resolve_package_ids(final_ids)
        if unresolved:
            errors.append(
                _diagnostic(
                    "unresolved_package_id",
                    "Some requested package IDs are not installed.",
                    packageids=unresolved,
                )
            )
            return {
                "saved": False,
                "errors": errors,
                "warnings": warnings,
                "mods_config_path": str(mods_config_path),
                "backup_path": None,
                "sorted_package_ids": final_ids,
            }

        written_ids = [self._config_package_id(mod, duplicates) for mod in mods]
        backup_path = self._backup_mods_config() if create_backup else None

        try:
            saved_path = ImportExportService(
                self.metadata_controller, self.settings
            ).save_to_mods_config(written_ids)
        except OSError as exc:
            errors.append(
                _diagnostic(
                    "write_failed",
                    f"Could not write ModsConfig.xml: {exc}",
                )
            )
            return {
                "saved": False,
                "errors": errors,
                "warnings": warnings,
                "mods_config_path": str(mods_config_path),
                "backup_path": str(backup_path) if backup_path else None,
                "sorted_package_ids": final_ids,
            }

        logger.info(f"MCP wrote {len(written_ids)} active mods to {saved_path}")
        return {
            "saved": True,
            "errors": errors,
            "warnings": warnings,
            "mods_config_path": saved_path,
            "backup_path": str(backup_path) if backup_path else None,
            "sorted_package_ids": final_ids,
            "written_package_ids": written_ids,
            "active_mods_count": len(written_ids),
        }

    @staticmethod
    def _config_package_id(
        mod: AboutXmlMod, duplicates: Mapping[str, list[str]]
    ) -> str:
        """Return the package ID as it must appear in ``ModsConfig.xml``.

        RimWorld resolves duplicates by the ``_steam`` suffix, matching the
        behavior of :meth:`ImportExportService.collect_active_mods`.
        """
        package_id = str(mod.package_id)
        if package_id in duplicates and mod.mod_type == ModType.STEAM_WORKSHOP:
            return f"{package_id}{_STEAM_SUFFIX}"
        return package_id

    def _core_is_resolvable(self) -> bool:
        """Return whether the base game package is present in metadata."""
        installed = {
            package_id.lower()
            for package_id in self.metadata_controller.packageid_to_paths
        }
        return CORE_PACKAGE_ID in installed

    def _backup_mods_config(self) -> Path | None:
        """Copy the existing ``ModsConfig.xml`` to a unique timestamped backup."""
        source = self.mods_config_path
        if source is None or not source.is_file():
            return None
        backup_dir = AppInfo().backups_folder / "mods_config"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        target = backup_dir / f"ModsConfig_{stamp}.xml"
        suffix = 1
        while target.exists():
            target = backup_dir / f"ModsConfig_{stamp}_{suffix}.xml"
            suffix += 1
        shutil.copy2(source, target)
        logger.info(f"Backed up ModsConfig.xml to {target}")
        return target

    # ---- tool 7 ----

    def refresh_metadata_cache(self) -> dict[str, Any]:
        """Re-scan the filesystem and ``ModsConfig.xml``.

        The settings file is reloaded first so paths edited outside this process
        (a user editing ``settings.json``, or an agent fixing
        ``workshop_folder``) take effect without restarting the server. Saves
        that :meth:`Settings.load` performs during mitigation stay on disk; the
        in-memory object is authoritative afterwards. The instance selected at
        bootstrap (``--instance`` or the then-active instance) stays bound even
        when the reloaded file names a different ``current_instance``.

        :return: Summary counts for the refreshed metadata
        """
        self.settings.load()
        if self._bound_instance_name in self.settings.instances:
            self.settings.current_instance = self._bound_instance_name
        else:
            logger.warning(
                f"Bound MCP instance {self._bound_instance_name!r} is no longer "
                f"configured; staying on {self.settings.current_instance!r}"
            )
        self.metadata_controller.reset_paths()
        self.metadata_controller.metadata_mediator.refresh_metadata(
            prefer_versioned=self.settings.prefer_versioned_about_tags,
            case_insensitive_about_xml=(
                self.settings.case_insensitive_about_xml_lookup
            ),
        )
        self._packageid_to_steam_entry = None
        about_mods = self._about_mods()
        active_paths = self._active_mod_paths()
        return {
            "refreshed": True,
            "game_version": self.metadata_controller.game_version,
            "total_installed_mods": len({str(mod.package_id) for mod in about_mods}),
            "total_mod_entries": len(about_mods),
            "active_mods_count": len(active_paths),
            "steam_db_loaded": self.metadata_controller.steam_db is not None,
            "community_rules_loaded": (
                self.metadata_controller.community_rules is not None
            ),
        }
