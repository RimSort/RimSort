"""Service for recording and comparing mod list history snapshots.

Every time the active mod list is saved to ``ModsConfig.xml`` the application
also writes a timestamped JSON snapshot of the full mod setup (active +
inactive) here. Each snapshot carries a content-hash identifier so identical
lists can be recognised across time, and the snapshots form a ``previousId``
chain. The :class:`ModlistHistoryService` also diffs any two snapshots so the
user can see exactly which mods were added, removed or reordered between two
saves.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from app.controllers.metadata_controller import MetadataController
from app.models.divider import is_divider_uuid
from app.models.settings import Settings
from app.utils.app_info import AppInfo
from app.utils.constants import RIMWORLD_PACKAGE_IDS
from app.utils.json_utils import atomic_json_dump

_SHORT_ID_LEN = 12
# Filename-safe timestamp (microsecond precision so snapshots written within the
# same second still sort chronologically by name). Stored on the Snapshot and used
# as the sort key; ``display_timestamp`` parses it back for the UI.
_TIMESTAMP_FMT = "%Y-%m-%dT%H-%M-%S.%f"
_META_KEY = "rimsortSnapshot"


def _sanitize_folder_name(name: str) -> str:
    """Reduce an instance name to something safe to use as a folder name."""
    cleaned = re.sub(r"[^\w.\- ]", "_", name).strip()
    return cleaned or "instance"


@dataclass
class SnapshotEntry:
    """A single mod recorded in a snapshot."""

    package_id: str
    name: str
    published_file_id: str | None
    source: str

    @property
    def label(self) -> str:
        return f"{self.name} [{self.package_id}]" if self.name else self.package_id


@dataclass
class Snapshot:
    """A parsed mod list history snapshot."""

    id: str
    short_id: str
    timestamp: str
    rimsort_version: str
    game_version: str
    instance: str
    previous_id: str | None
    note: str
    active: list[SnapshotEntry]
    inactive: list[SnapshotEntry]
    path: Path

    @property
    def active_package_ids(self) -> list[str]:
        return [entry.package_id for entry in self.active]

    @property
    def display_timestamp(self) -> str:
        """Human-friendly timestamp, falling back to the raw stored value."""
        for fmt in (_TIMESTAMP_FMT, "%Y-%m-%dT%H-%M-%S"):
            try:
                parsed = datetime.strptime(self.timestamp, fmt)  # noqa: DTZ007
            except ValueError:
                continue
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        return self.timestamp


@dataclass
class ModListDiff:
    """The difference between two snapshots."""

    active_added: list[SnapshotEntry] = field(default_factory=list)
    active_removed: list[SnapshotEntry] = field(default_factory=list)
    active_reordered: list[SnapshotEntry] = field(default_factory=list)
    inactive_added: list[SnapshotEntry] = field(default_factory=list)
    inactive_removed: list[SnapshotEntry] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (
            self.active_added
            or self.active_removed
            or self.active_reordered
            or self.inactive_added
            or self.inactive_removed
        )

    @property
    def summary(self) -> str:
        """Compact ``+a -r ~m`` counts, active list only."""
        return (
            f"+{len(self.active_added)} "
            f"-{len(self.active_removed)} "
            f"~{len(self.active_reordered)}"
        )


def compute_list_id(package_ids: list[str]) -> str:
    """Return the SHA-256 hex digest identifying an ordered active mod list.

    Package IDs are lower-cased so casing differences do not change the id, but
    order is significant because RimWorld load order matters.
    """
    joined = "\n".join(package_id.lower() for package_id in package_ids)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


class ModlistHistoryService:
    """Read/write and diff mod list history snapshots for the current instance."""

    def __init__(
        self,
        metadata_controller: MetadataController,
        settings: Settings,
    ) -> None:
        self.metadata_controller = metadata_controller
        self.settings = settings

    # ------------------------------------------------------------------ paths
    def history_dir(self) -> Path:
        """Per-instance history folder, created on demand."""
        directory = (
            AppInfo().saved_modlists_folder
            / "history"
            / _sanitize_folder_name(self.settings.current_instance)
        )
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _log_file(self) -> Path:
        return self.history_dir() / "history.log"

    # --------------------------------------------------------------- collect
    def _entries_from_uuids(self, uuids: list[str]) -> list[SnapshotEntry]:
        """Resolve list-widget UUIDs to snapshot entries, de-duplicated by id."""
        entries: list[SnapshotEntry] = []
        seen: set[str] = set()
        for uuid in uuids:
            if is_divider_uuid(uuid):
                continue
            mod = self.metadata_controller.get_mod(uuid)
            if mod is None:
                continue
            package_id = str(getattr(mod, "package_id", "") or "").strip()
            if not package_id or package_id.lower() in seen:
                continue
            seen.add(package_id.lower())
            pfid = getattr(mod, "published_file_id", None)
            mod_type = getattr(mod, "mod_type", None)
            entries.append(
                SnapshotEntry(
                    package_id=package_id,
                    name=str(getattr(mod, "name", "") or ""),
                    published_file_id=str(pfid) if pfid else None,
                    source=mod_type.name.lower() if mod_type is not None else "unknown",
                )
            )
        return entries

    # ----------------------------------------------------------------- write
    def write_snapshot(
        self,
        active_uuids: list[str],
        inactive_uuids: list[str],
    ) -> Snapshot | None:
        """Write a snapshot of the current mod setup.

        :return: the written :class:`Snapshot`, or ``None`` when the active
            list is identical to the most recent snapshot (nothing is written).
        """
        active = self._entries_from_uuids(active_uuids)
        inactive = self._entries_from_uuids(inactive_uuids)
        active_package_ids = [entry.package_id for entry in active]
        list_id = compute_list_id(active_package_ids)

        existing = self.list_snapshots()
        if existing and existing[0].id == list_id:
            logger.info(
                "Mod list unchanged since last snapshot "
                f"({existing[0].short_id}); skipping history write"
            )
            return None

        previous_id = existing[0].id if existing else None
        now = datetime.now()  # noqa: DTZ005 - local time matches the app's logs
        # Filename-/sort-safe form; the meta block keeps the ISO form with colons.
        timestamp = now.strftime(_TIMESTAMP_FMT)
        short_id = list_id[:_SHORT_ID_LEN]
        game_version = self.metadata_controller.game_version or ""

        known_expansions = [
            package_id
            for package_id in active_package_ids
            if package_id.lower() in {p.lower() for p in RIMWORLD_PACKAGE_IDS}
            and package_id.lower() != "ludeon.rimworld"
        ]

        payload: dict[str, Any] = {
            "version": game_version,
            "activeMods": active_package_ids,
            "knownExpansions": known_expansions,
            _META_KEY: {
                "id": list_id,
                "shortId": short_id,
                "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S.%f"),
                "rimsortVersion": AppInfo().app_version,
                "gameVersion": game_version,
                "instance": self.settings.current_instance,
                "previousId": previous_id,
                "note": "",
                "activeMods": [self._entry_to_dict(e) for e in active],
                "inactiveMods": [self._entry_to_dict(e) for e in inactive],
            },
        }

        history_dir = self.history_dir()
        filename = f"{timestamp}__{short_id}.json"
        target = history_dir / filename
        # Microsecond-precision names collide only in pathological cases; guard anyway.
        counter = 1
        while target.exists():
            target = history_dir / f"{timestamp}__{short_id}.{counter}.json"
            counter += 1

        atomic_json_dump(payload, str(target), indent=2)
        self._append_log_line(now, list_id, active, inactive, existing)
        logger.info(f"Wrote mod list history snapshot: {target.name}")

        self.prune(self.settings.modlist_history_retention_count)

        return Snapshot(
            id=list_id,
            short_id=short_id,
            timestamp=timestamp,
            rimsort_version=AppInfo().app_version,
            game_version=game_version,
            instance=self.settings.current_instance,
            previous_id=previous_id,
            note="",
            active=active,
            inactive=inactive,
            path=target,
        )

    @staticmethod
    def _entry_to_dict(entry: SnapshotEntry) -> dict[str, Any]:
        return {
            "packageId": entry.package_id,
            "name": entry.name,
            "publishedFileId": entry.published_file_id,
            "source": entry.source,
        }

    def _append_log_line(
        self,
        now: datetime,
        list_id: str,
        active: list[SnapshotEntry],
        inactive: list[SnapshotEntry],
        existing: list[Snapshot],
    ) -> None:
        delta = ""
        if existing:
            diff = self._diff_entries(
                existing[0].active, active, existing[0].inactive, inactive
            )
            delta = f"  {diff.summary}"
        line = (
            f"{now.strftime('%Y-%m-%d %H:%M:%S')}  "
            f"id={list_id[:_SHORT_ID_LEN]}  "
            f"active={len(active)} inactive={len(inactive)}{delta}\n"
        )
        try:
            with open(self._log_file(), "a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError as exc:
            logger.warning(f"Could not append to mod list history log: {exc}")

    # ------------------------------------------------------------------ read
    def list_snapshots(self) -> list[Snapshot]:
        """All snapshots for the current instance, newest first."""
        snapshots: list[Snapshot] = []
        for path in self.history_dir().glob("*.json"):
            try:
                snapshots.append(self.load_snapshot(path))
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                logger.warning(
                    f"Skipping unreadable history snapshot {path.name}: {exc}"
                )
        snapshots.sort(key=lambda snap: (snap.timestamp, snap.path.name), reverse=True)
        return snapshots

    def load_snapshot(self, path: str | Path) -> Snapshot:
        """Parse a single snapshot file."""
        path = Path(path)
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise TypeError("snapshot root is not an object")

        meta = data.get(_META_KEY)
        if isinstance(meta, dict):
            active = [
                self._entry_from_dict(item) for item in meta.get("activeMods", [])
            ]
            inactive = [
                self._entry_from_dict(item) for item in meta.get("inactiveMods", [])
            ]
            list_id = str(
                meta.get("id") or compute_list_id([e.package_id for e in active])
            )
            raw_timestamp = str(meta.get("timestamp") or "")
            return Snapshot(
                id=list_id,
                short_id=str(meta.get("shortId") or list_id[:_SHORT_ID_LEN]),
                timestamp=raw_timestamp.replace(":", "-"),
                rimsort_version=str(meta.get("rimsortVersion") or ""),
                game_version=str(meta.get("gameVersion") or data.get("version") or ""),
                instance=str(meta.get("instance") or ""),
                previous_id=(
                    str(meta["previousId"]) if meta.get("previousId") else None
                ),
                note=str(meta.get("note") or ""),
                active=active,
                inactive=inactive,
                path=path,
            )

        # Fall back: a plain RimSort JSON mod list without our metadata block.
        active_ids = data.get("activeMods") or []
        if isinstance(active_ids, dict):
            active_ids = active_ids.get("li", [])
        active = [
            SnapshotEntry(str(pid), "", None, "unknown")
            for pid in active_ids
            if isinstance(pid, str)
        ]
        list_id = compute_list_id([e.package_id for e in active])
        return Snapshot(
            id=list_id,
            short_id=list_id[:_SHORT_ID_LEN],
            timestamp=path.stem.split("__")[0],
            rimsort_version="",
            game_version=str(data.get("version") or ""),
            instance="",
            previous_id=None,
            note="",
            active=active,
            inactive=[],
            path=path,
        )

    @staticmethod
    def _entry_from_dict(item: Any) -> SnapshotEntry:
        if not isinstance(item, dict):
            return SnapshotEntry(str(item), "", None, "unknown")
        pfid = item.get("publishedFileId")
        return SnapshotEntry(
            package_id=str(item.get("packageId") or ""),
            name=str(item.get("name") or ""),
            published_file_id=str(pfid) if pfid else None,
            source=str(item.get("source") or "unknown"),
        )

    # ------------------------------------------------------------------ note
    def set_note(self, path: str | Path, note: str) -> None:
        """Update the free-text note stored on a snapshot file."""
        path = Path(path)
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        meta = data.get(_META_KEY)
        if not isinstance(meta, dict):
            meta = {}
            data[_META_KEY] = meta
        meta["note"] = note
        atomic_json_dump(data, str(path), indent=2)

    # ----------------------------------------------------------------- prune
    def prune(self, keep: int) -> None:
        """Delete the oldest snapshots beyond ``keep`` (``-1`` keeps everything)."""
        if keep < 0:
            return
        files = sorted(
            self.history_dir().glob("*.json"),
            key=lambda p: p.name,
            reverse=True,
        )
        for stale in files[max(keep, 0) :]:
            try:
                stale.unlink()
                logger.debug(f"Pruned old mod list history snapshot: {stale.name}")
            except OSError as exc:
                logger.warning(f"Could not prune history snapshot {stale.name}: {exc}")

    # ------------------------------------------------------------------ diff
    def diff(self, old: Snapshot, new: Snapshot) -> ModListDiff:
        """Diff two snapshots (``old`` -> ``new``)."""
        return self._diff_entries(old.active, new.active, old.inactive, new.inactive)

    @staticmethod
    def _diff_entries(
        old_active: list[SnapshotEntry],
        new_active: list[SnapshotEntry],
        old_inactive: list[SnapshotEntry],
        new_inactive: list[SnapshotEntry],
    ) -> ModListDiff:
        def key(entry: SnapshotEntry) -> str:
            return entry.package_id.lower()

        old_active_map = {key(e): e for e in old_active}
        new_active_map = {key(e): e for e in new_active}
        old_inactive_map = {key(e): e for e in old_inactive}
        new_inactive_map = {key(e): e for e in new_inactive}

        result = ModListDiff()
        result.active_added = [e for e in new_active if key(e) not in old_active_map]
        result.active_removed = [e for e in old_active if key(e) not in new_active_map]

        # Reorder detection: compare the two sequences restricted to the mods
        # that are present in both, then flag the mods difflib does not place
        # in an "equal" block (the minimal moved set).
        common_old = [key(e) for e in old_active if key(e) in new_active_map]
        common_new = [key(e) for e in new_active if key(e) in old_active_map]
        moved: set[str] = set()
        matcher = difflib.SequenceMatcher(a=common_old, b=common_new, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "equal":
                moved.update(common_old[i1:i2])
                moved.update(common_new[j1:j2])
        result.active_reordered = [e for e in new_active if key(e) in moved]

        result.inactive_added = [
            e for e in new_inactive if key(e) not in old_inactive_map
        ]
        result.inactive_removed = [
            e for e in old_inactive if key(e) not in new_inactive_map
        ]
        return result
