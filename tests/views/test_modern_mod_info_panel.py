"""Tests for the Modern info panel's incompatibility derivation.

The Incompatibilities card reports what the rules analysis actually
finds for the selected mod; these tests pin the split between
self-declared and reverse-only conflicts against the active set.
"""

from __future__ import annotations

from app.views.modern.modern_mod_info_panel import _active_incompatibilities


class _Rules:
    def __init__(self, package_ids: set[str]) -> None:
        self.incompatible_with = package_ids


class _FakeMod:
    def __init__(self, overall: set[str], about: set[str]) -> None:
        self.overall_rules = _Rules(overall)
        self.about_rules = _Rules(about)


ACTIVE_PIDS = {"core", "hat.mod", "gun.mod"}


class TestActiveIncompatibilities:
    def test_declared_conflict_with_active_mod(self) -> None:
        mod = _FakeMod(overall={"hat.mod"}, about={"hat.mod"})
        declared, reverse_only = _active_incompatibilities(mod, ACTIVE_PIDS)
        assert declared == {"hat.mod"}
        assert reverse_only == set()

    def test_reverse_only_conflict_via_community_rules(self) -> None:
        mod = _FakeMod(overall={"gun.mod"}, about=set())
        declared, reverse_only = _active_incompatibilities(mod, ACTIVE_PIDS)
        assert declared == set()
        assert reverse_only == {"gun.mod"}

    def test_inactive_targets_are_ignored(self) -> None:
        mod = _FakeMod(overall={"other.mod"}, about={"other.mod"})
        declared, reverse_only = _active_incompatibilities(mod, ACTIVE_PIDS)
        assert declared == set()
        assert reverse_only == set()

    def test_clean_mod_reports_nothing(self) -> None:
        mod = _FakeMod(overall=set(), about=set())
        declared, reverse_only = _active_incompatibilities(mod, ACTIVE_PIDS)
        assert declared == set()
        assert reverse_only == set()
