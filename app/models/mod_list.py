"""Domain model for ordered mod lists.

Provides ModEntry (frozen identity handle), ModList (indexed ordered collection),
and ModListDiff (change detection) — bridging PATH and packageId identity systems.
No Qt dependency.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger
from natsort import natsorted

from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    CaseInsensitiveStr,
    ModsConfig,
    ModType,
)

if TYPE_CHECKING:
    from app.controllers.metadata_controller import MetadataController


_STEAM_SUFFIX = "_steam"
_SYNTHETIC_PID_PREFIX = "__path:"

_SOURCE_PRIORITY_STEAM: list[ModType] = [
    ModType.STEAM_WORKSHOP,
    ModType.LOCAL,
    ModType.STEAM_CMD,
    ModType.GIT,
]
_SOURCE_PRIORITY_DEFAULT: list[ModType] = [
    ModType.LUDEON,
    ModType.LOCAL,
    ModType.STEAM_CMD,
    ModType.GIT,
    ModType.STEAM_WORKSHOP,
]


@dataclass(frozen=True)
class ModEntry:
    """Identifies a mod within an ordered list.

    :param path: Canonical identifier (filesystem path as string), matches
        MetadataController.mods_metadata keys.
    :param package_id: RimWorld package ID for dependency lookups and
        CompiledDependencyData bridging.
    :param config_id: Serialization identity written to ModsConfig.xml.
        Usually equals str(package_id) but includes '_steam' suffix for
        Workshop copies when duplicates exist.
    """

    path: str
    package_id: CaseInsensitiveStr
    config_id: str


@dataclass
class ModListDiff:
    """Result of comparing two ModLists.

    :param added: Entries in the other list but not this one.
    :param removed: Entries in this list but not the other.
    :param reordered: True if both lists have the same entries but in different order.
    """

    added: list[ModEntry]
    removed: list[ModEntry]
    reordered: bool


def create_mod_entry(
    path: str,
    package_id: CaseInsensitiveStr,
    mod_type: ModType,
    has_duplicate: bool,
) -> ModEntry:
    """Build a ModEntry with correct config_id resolution.

    :param path: Filesystem path to the mod.
    :param package_id: The mod's package ID.
    :param mod_type: Source type of the mod.
    :param has_duplicate: Whether another copy of this packageId exists.
    :return: A frozen ModEntry.
    """
    if has_duplicate and mod_type == ModType.STEAM_WORKSHOP:
        config_id = f"{package_id}_steam"
    else:
        config_id = str(package_id)
    return ModEntry(path=path, package_id=package_id, config_id=config_id)


class ModList:
    """Ordered collection of mod entries with maintained indices.

    Pure Python — no Qt dependency. Both ModsConfig serialization and
    ModListWidget rendering project from this.
    """

    def __init__(self, entries: Iterable[ModEntry] = ()) -> None:
        self._entries: list[ModEntry] = list(entries)
        self._path_index: dict[str, int] = {}
        self._pid_index: dict[CaseInsensitiveStr, list[int]] = {}
        self._rebuild_indices()

    def _rebuild_indices(self) -> None:
        """Full index rebuild from _entries. O(n).

        :raises ValueError: If duplicate paths are found in _entries.
        """
        self._path_index = {}
        self._pid_index = {}
        for i, entry in enumerate(self._entries):
            if entry.path in self._path_index:
                raise ValueError(f"Duplicate path in entries: {entry.path}")
            self._path_index[entry.path] = i
            self._pid_index.setdefault(entry.package_id, []).append(i)

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[ModEntry]:
        return iter(self._entries)

    def __contains__(self, path: str) -> bool:
        return path in self._path_index

    def __getitem__(self, index: int) -> ModEntry:
        return self._entries[index]

    def index_of(self, path: str) -> int | None:
        """Return the position of a mod by path, or None if not found."""
        return self._path_index.get(path)

    def entries_for_package_id(self, pid: CaseInsensitiveStr) -> list[ModEntry]:
        """Return all entries matching a package ID, in list order."""
        indices = self._pid_index.get(pid, [])
        return [self._entries[i] for i in indices]

    def paths(self) -> list[str]:
        """Return ordered list of paths."""
        return [e.path for e in self._entries]

    def package_ids(self) -> list[CaseInsensitiveStr]:
        """Return ordered list of package IDs."""
        return [e.package_id for e in self._entries]

    def find_duplicate_package_ids(self) -> dict[CaseInsensitiveStr, list[str]]:
        """Return packageIds that appear more than once, with their paths."""
        return {
            pid: [self._entries[i].path for i in indices]
            for pid, indices in self._pid_index.items()
            if len(indices) > 1
        }

    def insert(self, index: int, entry: ModEntry) -> None:
        """Insert an entry at the given index.

        :raises ValueError: If the path already exists in the list.
        :raises IndexError: If index is out of range.
        """
        if entry.path in self._path_index:
            raise ValueError(f"Path already exists: {entry.path}")
        if index < 0 or index > len(self._entries):
            raise IndexError(
                f"Index {index} out of range for list of length {len(self._entries)}"
            )
        self._entries.insert(index, entry)
        self._rebuild_indices()

    def remove_by_path(self, path: str) -> ModEntry:
        """Remove and return the entry with the given path.

        :raises KeyError: If the path is not in the list.
        """
        idx = self._path_index.get(path)
        if idx is None:
            raise KeyError(f"Path not found: {path}")
        entry = self._entries.pop(idx)
        self._rebuild_indices()
        return entry

    def reorder(self, path: str, new_index: int) -> None:
        """Move an existing entry to a new position.

        :raises KeyError: If the path is not in the list.
        :raises IndexError: If new_index is out of range.
        """
        old_index = self._path_index.get(path)
        if old_index is None:
            raise KeyError(f"Path not found: {path}")
        if new_index < 0 or new_index >= len(self._entries):
            raise IndexError(
                f"Index {new_index} out of range for list of length {len(self._entries)}"
            )
        entry = self._entries.pop(old_index)
        self._entries.insert(new_index, entry)
        self._rebuild_indices()

    def move_batch(self, paths: list[str], target_index: int) -> None:
        """Move multiple entries to a target position, preserving their relative order.

        Entries are ordered by their current position (not the order in `paths`),
        removed, then reinserted at `target_index` (clamped to list bounds).
        """
        paths = list(dict.fromkeys(paths))
        current_positions = []
        for p in paths:
            idx = self._path_index.get(p)
            if idx is not None:
                current_positions.append((idx, self._entries[idx]))
        current_positions.sort(key=lambda x: x[0])
        moved_entries = [entry for _, entry in current_positions]
        for entry in moved_entries:
            self._entries.remove(entry)
        insert_at = max(0, min(target_index, len(self._entries)))
        for i, entry in enumerate(moved_entries):
            self._entries.insert(insert_at + i, entry)
        self._rebuild_indices()

    def replace_order(self, entries: list[ModEntry]) -> None:
        """Replace all entries with a new ordered list. Full index rebuild."""
        self._entries = list(entries)
        self._rebuild_indices()

    def clear(self) -> None:
        """Remove all entries and clear indices."""
        self._entries.clear()
        self._path_index.clear()
        self._pid_index.clear()

    def diff(self, other: ModList) -> ModListDiff:
        """Compare this list against another, returning added/removed/reordered."""
        self_paths = set(self._path_index.keys())
        other_paths = set(other._path_index.keys())

        added_paths = other_paths - self_paths
        added = sorted(
            [other[other._path_index[p]] for p in added_paths],
            key=lambda e: other._path_index[e.path],
        )
        removed_paths = self_paths - other_paths
        removed = sorted(
            [self[self._path_index[p]] for p in removed_paths],
            key=lambda e: self._path_index[e.path],
        )

        common = self_paths & other_paths
        reordered = False
        if not added and not removed and common:
            self_order = [e.path for e in self._entries if e.path in common]
            other_order = [e.path for e in other._entries if e.path in common]
            reordered = self_order != other_order

        return ModListDiff(added=added, removed=removed, reordered=reordered)

    def to_mods_config(
        self,
        version: str,
        expansions: list[CaseInsensitiveStr],
    ) -> ModsConfig:
        """Serialize to RimWorld's ModsConfig format.

        :param version: Game version string.
        :param expansions: Known expansion package IDs.
        :return: A ModsConfig ready for XML serialization.
        """
        active_mods = [CaseInsensitiveStr(e.config_id) for e in self._entries]
        return ModsConfig(
            version=version,
            activeMods=active_mods,
            knownExpansions=expansions,
        )

    @classmethod
    def from_sorted_paths(cls, sorted_paths: list[str], source: ModList) -> ModList:
        """Create a new ModList by reordering entries from source.

        Copies existing ModEntry objects (preserving config_id). Paths not
        found in source are logged and skipped.

        :param sorted_paths: Desired order of paths.
        :param source: ModList to pull entries from.
        :return: A new ModList in the sorted order.
        """
        entries: list[ModEntry] = []
        for path in sorted_paths:
            idx = source.index_of(path)
            if idx is not None:
                entries.append(source[idx])
            else:
                logger.warning(
                    f"from_sorted_paths: path not in source, skipping: {path}"
                )
        return cls(entries)

    @classmethod
    def from_mods_config(
        cls,
        config: ModsConfig,
        metadata_controller: MetadataController,
    ) -> tuple[ModList, list[str]]:
        """Resolve a ModsConfig into a ModList by mapping packageIds to paths.

        Handles _steam suffix detection and source-priority resolution for
        duplicate mods. Unresolved packageIds are returned in the missing list.

        :param config: The ModsConfig loaded from XML.
        :param metadata_controller: Provides mods_metadata and packageid_to_paths.
        :return: (resolved ModList, list of missing packageId strings)
        """
        entries: list[ModEntry] = []
        missing: list[str] = []
        seen_paths: set[str] = set()
        pid_to_paths = metadata_controller.packageid_to_paths

        for config_id_ci in config.activeMods:
            config_id_str = str(config_id_ci)
            is_steam = config_id_str.endswith(_STEAM_SUFFIX)
            raw_pid = (
                config_id_str[: -len(_STEAM_SUFFIX)] if is_steam else config_id_str
            )

            candidate_paths = pid_to_paths.get(raw_pid, set())
            if not candidate_paths:
                missing.append(raw_pid)
                continue

            sources = _SOURCE_PRIORITY_STEAM if is_steam else _SOURCE_PRIORITY_DEFAULT
            resolved_path = cls._resolve_path(
                candidate_paths,
                sources,
                metadata_controller,
                seen_paths,
            )

            if resolved_path is None:
                missing.append(raw_pid)
                continue

            seen_paths.add(resolved_path)
            mod = metadata_controller.mods_metadata[resolved_path]
            has_duplicate = len(candidate_paths) > 1
            entry = create_mod_entry(
                path=resolved_path,
                package_id=CaseInsensitiveStr(raw_pid),
                mod_type=mod.mod_type,
                has_duplicate=has_duplicate,
            )
            entries.append(entry)

        return cls(entries), missing

    @staticmethod
    def _resolve_path(
        candidate_paths: set[str],
        source_priority: list[ModType],
        metadata_controller: MetadataController,
        seen_paths: set[str],
    ) -> str | None:
        """Pick the best path from candidates using source priority and natsort tiebreaking."""
        for source_type in source_priority:
            source_paths = [
                p
                for p in candidate_paths
                if p not in seen_paths
                and metadata_controller.mods_metadata[p].mod_type == source_type
            ]
            if source_paths:
                return natsorted(source_paths)[0]
        remaining = [p for p in candidate_paths if p not in seen_paths]
        if remaining:
            return natsorted(remaining)[0]
        return None

    @classmethod
    def from_remaining(
        cls,
        all_mod_paths: set[str],
        active: ModList,
        metadata_controller: MetadataController,
    ) -> ModList:
        """Build the inactive mod list from all known paths minus active paths.

        Entries use config_id = str(package_id) (no _steam suffix) since
        inactive mods don't serialize to ModsConfig.xml.

        :param all_mod_paths: Set of all known mod paths.
        :param active: The active ModList to subtract.
        :param metadata_controller: For looking up packageId and ModType per path.
        :return: A ModList of inactive mods.
        """
        active_paths = set(active.paths())
        inactive_paths = all_mod_paths - active_paths

        entries: list[ModEntry] = []
        for path in sorted(inactive_paths):
            mod = metadata_controller.mods_metadata.get(path)
            if mod is None:
                logger.warning(
                    f"from_remaining: path not in metadata, skipping: {path}"
                )
                continue
            if not isinstance(mod, AboutXmlMod):
                entry = create_mod_entry(
                    path=path,
                    package_id=CaseInsensitiveStr(f"{_SYNTHETIC_PID_PREFIX}{path}"),
                    mod_type=mod.mod_type,
                    has_duplicate=False,
                )
            else:
                entry = create_mod_entry(
                    path=path,
                    package_id=mod.package_id,
                    mod_type=mod.mod_type,
                    has_duplicate=False,
                )
            entries.append(entry)
        return cls(entries)
