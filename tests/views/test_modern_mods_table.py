"""Tests for the Modern mods table's module-level helpers.

Covers the source/type filter matching (the popup must honor the same
rules as the classic lists) and the live-source-item guard that keeps
paint and interaction paths away from deleted list items.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QListWidget, QListWidgetItem

from app.models.filter_state import FilterState
from app.models.metadata.metadata_structure import ModType
from app.views.modern.modern_mods_table import (
    _live_source_item,
    _source_filter_fails,
    _type_filter_fails,
)


class _FakeMod:
    """The two attributes the filter helpers read from a mod."""

    def __init__(self, mod_type: ModType, c_sharp: bool = False) -> None:
        self.mod_type = mod_type
        self.c_sharp_mod = c_sharp


class TestSourceFilter:
    """Git and SteamCMD mods must be reachable through their own source
    keys, not only through local."""

    def test_steamcmd_only_selection_shows_steamcmd_mod(self) -> None:
        state = FilterState(sources={"steamcmd"})
        assert _source_filter_fails(_FakeMod(ModType.STEAM_CMD), state) is False

    def test_git_only_selection_shows_git_mod(self) -> None:
        state = FilterState(sources={"git_repo"})
        assert _source_filter_fails(_FakeMod(ModType.GIT), state) is False

    def test_local_selection_still_includes_git_and_steamcmd(self) -> None:
        state = FilterState(sources={"local"})
        assert _source_filter_fails(_FakeMod(ModType.GIT), state) is False
        assert _source_filter_fails(_FakeMod(ModType.STEAM_CMD), state) is False

    def test_local_selection_hides_workshop_mod(self) -> None:
        state = FilterState(sources={"local"})
        assert _source_filter_fails(_FakeMod(ModType.STEAM_WORKSHOP), state) is True

    def test_steamcmd_selection_hides_plain_local_mod(self) -> None:
        state = FilterState(sources={"steamcmd"})
        assert _source_filter_fails(_FakeMod(ModType.LOCAL), state) is True

    def test_all_sources_show_everything(self) -> None:
        state = FilterState()
        assert _source_filter_fails(_FakeMod(ModType.LUDEON), state) is False


class TestTypeFilter:
    """The popup's C# Mods / XML-only constraint hides the other kind."""

    def test_csharp_selection_hides_xml_mod(self) -> None:
        state = FilterState(mod_type="csharp")
        assert _type_filter_fails(_FakeMod(ModType.LOCAL, c_sharp=False), state) is True

    def test_csharp_selection_shows_csharp_mod(self) -> None:
        state = FilterState(mod_type="csharp")
        assert _type_filter_fails(_FakeMod(ModType.LOCAL, c_sharp=True), state) is False

    def test_xml_selection_hides_csharp_mod(self) -> None:
        state = FilterState(mod_type="xml")
        assert _type_filter_fails(_FakeMod(ModType.LOCAL, c_sharp=True), state) is True

    def test_xml_selection_shows_xml_mod(self) -> None:
        state = FilterState(mod_type="xml")
        assert (
            _type_filter_fails(_FakeMod(ModType.LOCAL, c_sharp=False), state) is False
        )

    def test_all_shows_every_mod(self) -> None:
        state = FilterState(mod_type="all")
        assert _type_filter_fails(_FakeMod(ModType.LOCAL, c_sharp=True), state) is False


class TestLiveSourceItem:
    """Rows keep source-item references across list rebuilds; the guard
    refuses wrappers whose C++ object a rebuild already deleted."""

    def test_none_and_strings_are_not_items(self) -> None:
        assert _live_source_item(None) is None
        assert _live_source_item("group name") is None

    def test_live_item_is_returned(self, qtbot: Any) -> None:
        widget = QListWidget()
        qtbot.addWidget(widget)
        item = QListWidgetItem(widget)
        assert _live_source_item(item) is item

    def test_deleted_item_is_reported_dead(self, qtbot: Any) -> None:
        widget = QListWidget()
        qtbot.addWidget(widget)
        item = QListWidgetItem(widget)
        widget.clear()
        assert _live_source_item(item) is None
