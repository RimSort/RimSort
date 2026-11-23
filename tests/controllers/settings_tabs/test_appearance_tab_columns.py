"""Regression tests for the Active Columns slot identifiers.

The slot comboboxes translate their display labels, so the saved
settings must carry the stable identifier from item data; loading must
resolve the identifier (and, for settings saved by older versions, the
plain label) regardless of the UI language.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QComboBox

from app.controllers.settings_tabs.appearance_tab_controller import (
    AppearanceTabController,
)
from app.models.settings import Settings

# A translated run displays different labels; the item data keeps the
# identifiers the table matches on. Every slot combobox offers every
# choice, like the real dialog.
CHOICES: list[tuple[str, str]] = [
    ("Bundled", "Default"),
    ("Category", "Category"),
    ("无", "None"),
]


@pytest.fixture()
def appearance_tab(
    qtbot: Any,
    _mock_settings_deps: None,
) -> Iterator[tuple[AppearanceTabController, Settings, list[QComboBox]]]:
    """A controller over a mock dialog whose slot comboboxes are real."""
    settings = Settings()
    dialog = MagicMock()
    comboboxes = []
    for _slot in range(6):
        box = QComboBox()
        for label, identifier in CHOICES:
            box.addItem(label, identifier)
        qtbot.addWidget(box)
        comboboxes.append(box)
    dialog.active_columns_comboboxes = comboboxes
    # The other style comboboxes stay mocks; their findText must
    # compare like a real one
    for name in (
        "modern_row_style_combobox",
        "modern_category_style_combobox",
        "modern_category_align_combobox",
        "modern_active_style_combobox",
    ):
        getattr(dialog, name).findText.return_value = -1
    # Skip the heavy constructor: only the attributes the two update
    # methods read are needed
    controller = AppearanceTabController.__new__(AppearanceTabController)
    controller.settings = settings
    controller.dialog = dialog
    controller._theme_controller = MagicMock()
    controller._language_controller = MagicMock()
    yield controller, settings, comboboxes


class TestActiveColumnsIdentifiers:
    def test_save_stores_identifiers_not_labels(self, appearance_tab: Any) -> None:
        controller, settings, comboboxes = appearance_tab
        # Every slot starts on its first choice; slot 2 is switched to
        # the translated "Bundled" label whose identifier is "Default"
        comboboxes[1].setCurrentIndex(1)
        comboboxes[2].setCurrentIndex(0)
        for box in comboboxes[3:]:
            box.setCurrentIndex(2)
        controller.update_model_from_view()
        assert settings.active_columns == [
            "Default",
            "Category",
            "Default",
            "None",
            "None",
            "None",
        ]

    def test_load_selects_by_identifier(self, appearance_tab: Any) -> None:
        controller, settings, comboboxes = appearance_tab
        settings.active_columns = [
            "Category",
            "Default",
            "None",
            "None",
            "None",
            "None",
        ]
        controller.update_view_from_model()
        assert [box.currentData() for box in comboboxes] == [
            "Category",
            "Default",
            "None",
            "None",
            "None",
            "None",
        ]

    def test_load_falls_back_to_label_match(self, appearance_tab: Any) -> None:
        # Settings written by an older version may carry the label
        # itself; the text lookup still resolves the slot
        controller, settings, comboboxes = appearance_tab
        settings.active_columns = ["无", "无", "无", "无", "无", "无"]
        controller.update_view_from_model()
        assert all(box.currentIndex() == 2 for box in comboboxes)
