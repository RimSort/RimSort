"""Tests for the filter panel components: TagChip, FilterPanel, FilterButton."""

from __future__ import annotations

from typing import Any

import pytest

from app.models.filter_state import FilterState
from app.views.filter_panel import FilterButton, FilterPanel, TagChip

# ---------------------------------------------------------------------------
# TagChip Tests
# ---------------------------------------------------------------------------


class TestTagChip:
    """Tests for the TagChip clickable tag widget."""

    @pytest.fixture
    def chip(self, qtbot: Any) -> TagChip:
        """Create a basic TagChip for testing."""
        c = TagChip("Favorites")
        qtbot.addWidget(c)
        return c

    @pytest.fixture
    def no_tags_chip(self, qtbot: Any) -> TagChip:
        """Create a 'no tags' TagChip for testing."""
        c = TagChip("No tags", is_no_tags=True)
        qtbot.addWidget(c)
        return c

    def test_initial_state_inactive(self, chip: TagChip) -> None:
        """TagChip starts inactive by default."""
        assert chip.active is False
        assert chip.tag_name == "Favorites"
        assert chip.is_no_tags is False

    def test_click_toggles_active(self, chip: TagChip) -> None:
        """Clicking a chip toggles it to active."""
        chip.mousePressEvent(None)  # type: ignore[arg-type]
        assert chip.active is True

    def test_click_again_deactivates(self, chip: TagChip) -> None:
        """Clicking an active chip deactivates it."""
        chip.mousePressEvent(None)  # type: ignore[arg-type]
        assert chip.active is True
        chip.mousePressEvent(None)  # type: ignore[arg-type]
        assert chip.active is False

    def test_set_active_programmatic(self, chip: TagChip) -> None:
        """set_active() changes state without requiring a click."""
        chip.set_active(True)
        assert chip.active is True
        chip.set_active(False)
        assert chip.active is False

    def test_no_tags_chip_is_italic(self, no_tags_chip: TagChip) -> None:
        """The 'no tags' chip uses italic text."""
        assert no_tags_chip.is_no_tags is True
        assert no_tags_chip._label.font().italic() is True

    def test_label_shows_cross_when_active(self, chip: TagChip) -> None:
        """Active chip label includes a dismiss cross mark."""
        chip.set_active(True)
        assert "✕" in chip._label.text()  # ✕

    def test_label_no_cross_when_inactive(self, chip: TagChip) -> None:
        """Inactive chip label has no cross mark."""
        chip.set_active(False)
        assert "✕" not in chip._label.text()
        assert chip._label.text() == "Favorites"

    def test_toggled_signal_emitted(self, chip: TagChip, qtbot: Any) -> None:
        """The toggled signal is emitted when the chip is clicked."""
        with qtbot.waitSignal(chip.toggled, timeout=1000):
            chip.mousePressEvent(None)  # type: ignore[arg-type]

    def test_dynamic_property_active(self, chip: TagChip) -> None:
        """The 'active' dynamic property is updated on state change."""
        assert chip.property("active") is False
        chip.set_active(True)
        assert chip.property("active") is True
        chip.set_active(False)
        assert chip.property("active") is False


# ---------------------------------------------------------------------------
# FilterPanel Tests
# ---------------------------------------------------------------------------


class TestFilterPanel:
    """Tests for the FilterPanel popup widget."""

    @pytest.fixture
    def panel(self, qtbot: Any) -> FilterPanel:
        """Create a FilterPanel for testing."""
        p = FilterPanel()
        qtbot.addWidget(p)
        return p

    def test_initial_state_no_filters(self, panel: FilterPanel) -> None:
        """Panel starts with default filter state (no active filters)."""
        state = panel.filter_state
        assert state.sources == FilterState.ALL_SOURCES
        assert state.mod_type == "all"
        assert state.tags == set()
        assert state.tag_match_mode == "or"
        assert state.include_no_tags is False
        assert state.has_active_filters() is False

    def test_source_checkbox_unchecked_updates_state(self, panel: FilterPanel) -> None:
        """Unchecking a source checkbox excludes it from the filter state."""
        panel._source_checkboxes["workshop"].setChecked(False)
        state = panel.filter_state
        assert "workshop" not in state.sources
        assert state.has_active_filters() is True

    def test_type_radio_updates_state(self, panel: FilterPanel) -> None:
        """Selecting a non-default type radio updates the filter state."""
        panel._type_radios["csharp"].setChecked(True)
        state = panel.filter_state
        assert state.mod_type == "csharp"

    def test_tag_chip_updates_state(self, panel: FilterPanel) -> None:
        """Activating a tag chip adds it to the filter state tags."""
        panel.set_available_tags(["Favorites", "QoL"])
        panel._tag_chips["Favorites"].set_active(True)
        state = panel.filter_state
        assert "Favorites" in state.tags

    def test_tag_match_mode_updates_state(self, panel: FilterPanel) -> None:
        """Selecting All changes tag matching to AND mode."""
        panel._tag_match_mode_radios["and"].setChecked(True)
        state = panel.filter_state
        assert state.tag_match_mode == "and"

    def test_no_tags_chip(self, panel: FilterPanel) -> None:
        """Activating the 'no tags' chip sets include_no_tags."""
        panel._no_tags_chip.set_active(True)
        state = panel.filter_state
        assert state.include_no_tags is True

    def test_clear_resets_all(self, panel: FilterPanel) -> None:
        """clear() resets all filters to default state."""
        # Engage some filters first
        panel._source_checkboxes["local"].setChecked(False)
        panel._type_radios["xml"].setChecked(True)
        panel.set_available_tags(["QoL"])
        panel._tag_chips["QoL"].set_active(True)
        panel._no_tags_chip.set_active(True)

        # Reset
        panel.clear()

        state = panel.filter_state
        assert state.sources == FilterState.ALL_SOURCES
        assert state.mod_type == "all"
        assert state.tags == set()
        assert state.tag_match_mode == "or"
        assert state.include_no_tags is False

    def test_filters_changed_signal_emitted(
        self, panel: FilterPanel, qtbot: Any
    ) -> None:
        """filters_changed signal is emitted when a source checkbox changes."""
        with qtbot.waitSignal(panel.filters_changed, timeout=1000):
            panel._source_checkboxes["workshop"].setChecked(False)

    def test_set_available_tags_creates_chips(self, panel: FilterPanel) -> None:
        """set_available_tags creates tag chips for each provided tag."""
        panel.set_available_tags(["Favorites", "Cosmetic", "QoL"])
        assert "Favorites" in panel._tag_chips
        assert "Cosmetic" in panel._tag_chips
        assert "QoL" in panel._tag_chips
        # "no tags" chip is always present
        assert "__no_tags__" in panel._tag_chips

    def test_set_available_tags_replaces_old_chips(self, panel: FilterPanel) -> None:
        """Calling set_available_tags again replaces previous user tag chips."""
        panel.set_available_tags(["Alpha", "Beta"])
        assert "Alpha" in panel._tag_chips
        assert "Beta" in panel._tag_chips

        panel.set_available_tags(["Gamma"])
        assert "Gamma" in panel._tag_chips
        assert "Alpha" not in panel._tag_chips
        assert "Beta" not in panel._tag_chips
        # "no tags" chip survives
        assert "__no_tags__" in panel._tag_chips

    def test_select_all_tags(self, panel: FilterPanel) -> None:
        """'Select All' activates all tag chips including 'no tags'."""
        panel.set_available_tags(["Favorites", "QoL"])
        panel._on_select_all_tags(None)  # type: ignore[arg-type]

        for chip in panel._tag_chips.values():
            assert chip.active is True

    def test_select_none_tags(self, panel: FilterPanel) -> None:
        """'None' deactivates all tag chips."""
        panel.set_available_tags(["Favorites", "QoL"])
        # Activate all first
        for chip in panel._tag_chips.values():
            chip.set_active(True)

        panel._on_select_none_tags(None)  # type: ignore[arg-type]

        for chip in panel._tag_chips.values():
            assert chip.active is False

    def test_clear_emits_filters_changed(self, panel: FilterPanel, qtbot: Any) -> None:
        """clear() emits the filters_changed signal."""
        with qtbot.waitSignal(panel.filters_changed, timeout=1000):
            panel.clear()

    def test_type_radio_mutual_exclusion(self, panel: FilterPanel) -> None:
        """Only one type radio can be selected at a time."""
        panel._type_radios["csharp"].setChecked(True)
        assert panel._type_radios["all"].isChecked() is False
        assert panel._type_radios["xml"].isChecked() is False

        panel._type_radios["xml"].setChecked(True)
        assert panel._type_radios["csharp"].isChecked() is False


# ---------------------------------------------------------------------------
# FilterButton Tests
# ---------------------------------------------------------------------------


class TestFilterButton:
    """Tests for the FilterButton toolbar button with badge."""

    @pytest.fixture
    def button(self, qtbot: Any) -> FilterButton:
        """Create a FilterButton for testing."""
        btn = FilterButton()
        qtbot.addWidget(btn)
        return btn

    def test_initial_badge_hidden(self, button: FilterButton) -> None:
        """Badge is hidden when no filters are active."""
        assert button._badge_label.isHidden() is True

    def test_badge_shows_count(self, button: FilterButton) -> None:
        """Badge shows the number of active filter categories."""
        # Uncheck a source to activate the sources category
        button.filter_panel._source_checkboxes["workshop"].setChecked(False)
        assert button._badge_label.isHidden() is False
        assert button._badge_label.text() == "1"

    def test_badge_hides_when_cleared(self, button: FilterButton) -> None:
        """Badge hides when all filters are cleared."""
        button.filter_panel._source_checkboxes["workshop"].setChecked(False)
        assert button._badge_label.isHidden() is False

        button.filter_panel.clear()
        assert button._badge_label.isHidden() is True

    def test_badge_counts_categories_not_items(self, button: FilterButton) -> None:
        """Badge counts active categories, not individual filter items."""
        # Activate two sources category changes
        button.filter_panel._source_checkboxes["workshop"].setChecked(False)
        button.filter_panel._source_checkboxes["local"].setChecked(False)
        # Both are source changes, so still only 1 category
        assert button._badge_label.text() == "1"

        # Now also change the type — adds a second category
        button.filter_panel._type_radios["csharp"].setChecked(True)
        assert button._badge_label.text() == "2"

    def test_clicking_shows_panel(self, button: FilterButton, qtbot: Any) -> None:
        """Clicking the button shows the filter panel."""
        button.show()
        button.resize(32, 32)
        qtbot.addWidget(button.filter_panel)

        # Use _show_panel directly to avoid popup grab issues in tests
        button._show_panel()
        assert button.filter_panel.isVisible() is True
        button.filter_panel.hide()

    def test_filter_panel_attribute(self, button: FilterButton) -> None:
        """FilterButton exposes its filter panel as an attribute."""
        assert isinstance(button.filter_panel, FilterPanel)
