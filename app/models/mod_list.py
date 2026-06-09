"""Domain model for ordered mod lists.

Provides ModEntry (frozen identity handle), ModList (indexed ordered collection),
and ModListDiff (change detection) — bridging PATH and packageId identity systems.
No Qt dependency.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from app.models.metadata.metadata_structure import (
    CaseInsensitiveStr,
    ModType,
)


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
        """Full index rebuild from _entries. O(n)."""
        self._path_index = {}
        self._pid_index = {}
        for i, entry in enumerate(self._entries):
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
            raise IndexError(f"Index {index} out of range for list of length {len(self._entries)}")
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
        current_positions = []
        for p in paths:
            idx = self._path_index.get(p)
            if idx is not None:
                current_positions.append((idx, self._entries[idx]))
        current_positions.sort(key=lambda x: x[0])
        moved_entries = [entry for _, entry in current_positions]
        for entry in moved_entries:
            self._entries.remove(entry)
        insert_at = min(target_index, len(self._entries))
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
