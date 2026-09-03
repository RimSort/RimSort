"""Tests for the mod list history snapshot service."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.models.metadata.metadata_structure import ModType
from app.services.modlist_history_service import (
    ModlistHistoryService,
    compute_list_id,
)


@dataclass
class _StubMod:
    package_id: str
    name: str = ""
    published_file_id: str | None = None
    mod_type: ModType = ModType.LOCAL


class _StubMetadataController:
    """Minimal stand-in: uuid == package_id for test convenience."""

    game_version = "1.5"

    def __init__(self, mods: dict[str, _StubMod]) -> None:
        self._mods = mods

    def get_mod(self, uuid: str) -> _StubMod | None:
        return self._mods.get(uuid)


class _StubSettings:
    current_instance = "Default"
    modlist_history_retention_count = 100


def _make_service(
    package_ids: list[str],
) -> tuple[ModlistHistoryService, _StubSettings]:
    mods = {
        pid: _StubMod(
            package_id=pid,
            name=pid.split(".")[-1].title(),
            mod_type=ModType.STEAM_WORKSHOP if "steam" in pid else ModType.LOCAL,
        )
        for pid in package_ids
    }
    settings = _StubSettings()
    service = ModlistHistoryService(_StubMetadataController(mods), settings)  # type: ignore[arg-type]
    return service, settings


class TestComputeListId:
    def test_deterministic(self) -> None:
        assert compute_list_id(["a.b", "c.d"]) == compute_list_id(["a.b", "c.d"])

    def test_case_insensitive(self) -> None:
        assert compute_list_id(["A.B"]) == compute_list_id(["a.b"])

    def test_order_sensitive(self) -> None:
        assert compute_list_id(["a.b", "c.d"]) != compute_list_id(["c.d", "a.b"])


class TestWriteSnapshot:
    def test_writes_file_and_log(self) -> None:
        service, _ = _make_service(["ludeon.rimworld", "a.mod", "b.mod", "c.mod"])
        snap = service.write_snapshot(["ludeon.rimworld", "a.mod", "b.mod"], ["c.mod"])

        assert snap is not None
        assert snap.path.exists()
        assert snap.active_package_ids == ["ludeon.rimworld", "a.mod", "b.mod"]
        assert len(snap.inactive) == 1

        payload = json.loads(snap.path.read_text(encoding="utf-8"))
        assert payload["activeMods"] == ["ludeon.rimworld", "a.mod", "b.mod"]
        assert payload["rimsortSnapshot"]["id"] == snap.id

        log = service.history_dir() / "history.log"
        assert log.exists()
        assert snap.short_id in log.read_text(encoding="utf-8")

    def test_identical_list_is_not_rewritten(self) -> None:
        service, _ = _make_service(["a.mod", "b.mod"])
        first = service.write_snapshot(["a.mod", "b.mod"], [])
        second = service.write_snapshot(["a.mod", "b.mod"], [])

        assert first is not None
        assert second is None
        assert len(list(service.history_dir().glob("*.json"))) == 1

    def test_previous_id_chains(self) -> None:
        service, _ = _make_service(["a.mod", "b.mod"])
        first = service.write_snapshot(["a.mod"], ["b.mod"])
        second = service.write_snapshot(["a.mod", "b.mod"], [])

        assert first is not None and second is not None
        assert second.previous_id == first.id


class TestPrune:
    def test_keeps_newest(self) -> None:
        service, _ = _make_service(["a.mod", "b.mod", "c.mod"])
        service.write_snapshot(["a.mod"], [])
        service.write_snapshot(["a.mod", "b.mod"], [])
        service.write_snapshot(["a.mod", "b.mod", "c.mod"], [])

        service.prune(keep=2)
        remaining = sorted(p.name for p in service.history_dir().glob("*.json"))
        assert len(remaining) == 2

        newest = service.list_snapshots()[0]
        assert newest.active_package_ids == ["a.mod", "b.mod", "c.mod"]

    def test_negative_keeps_all(self) -> None:
        service, _ = _make_service(["a.mod", "b.mod"])
        service.write_snapshot(["a.mod"], [])
        service.write_snapshot(["a.mod", "b.mod"], [])
        service.prune(keep=-1)
        assert len(list(service.history_dir().glob("*.json"))) == 2


class TestDiff:
    def test_detects_add_remove_reorder(self) -> None:
        service, _ = _make_service(["a.mod", "b.mod", "c.mod", "d.mod"])
        old = service.write_snapshot(["a.mod", "b.mod", "c.mod"], ["d.mod"])
        new = service.write_snapshot(["a.mod", "c.mod", "b.mod", "d.mod"], [])

        assert old is not None and new is not None
        diff = service.diff(old, new)

        assert [e.package_id for e in diff.active_added] == ["d.mod"]
        assert diff.active_removed == []
        reordered = {e.package_id for e in diff.active_reordered}
        # b and c swapped; difflib flags the minimal moved set (at least one of them).
        assert reordered
        assert reordered <= {"b.mod", "c.mod"}
        assert [e.package_id for e in diff.inactive_removed] == ["d.mod"]

    def test_empty_diff_for_same_snapshot(self) -> None:
        service, _ = _make_service(["a.mod", "b.mod"])
        snap = service.write_snapshot(["a.mod", "b.mod"], [])
        assert snap is not None
        assert service.diff(snap, snap).is_empty
