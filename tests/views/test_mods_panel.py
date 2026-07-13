from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from app.models.settings import Settings
from app.utils.custom_list_widget_item import CustomListWidgetItem
from app.utils.custom_list_widget_item_metadata import CustomListWidgetItemMetadata
from app.views.mods_panel import ModListItemInner, TagEditDialog


class TestTagEditDialog:
    """Test suite for the TagEditDialog dialog."""

    @pytest.fixture
    def dialog(self, qtbot: Any) -> TagEditDialog:
        """
        Create a TagEditDialog instance for testing.

        :param qtbot: Pytest-Qt bot for widget testing.
        :return: A mock TagEditDialog instance for testing.
        """
        with patch(
            "app.views.mods_panel.auxdb_get_all_tags",
            return_value={"a", "aa", "b", "bb", "c", "cc"},
        ):
            dialog = TagEditDialog(
                title="Test Dialog",
                settings=MagicMock(spec=Settings),
                existing_selected_tags={"a", "aa", "b", "bb"},
            )
            qtbot.addWidget(dialog)
            assert dialog.tags_list.count() == 6
            checked = [
                dialog.tags_list.item(i)
                for i in range(dialog.tags_list.count())
                if dialog.tags_list.item(i).checkState() == Qt.CheckState.Checked
            ]
            assert len(checked) == 4
            return dialog

    @staticmethod
    def _get_tags(widget: QListWidget) -> list[QListWidgetItem]:
        """
        Get tags from the witget as a list to iterate over.

        :return: A list of tag items.
        """
        return [widget.item(i) for i in range(widget.count())]

    def test_filter_matches_some(self, dialog: TagEditDialog) -> None:
        """Filtering shows only items containing the filter text."""
        dialog.new_tags_input.setText("a")

        for tag in self._get_tags(dialog.tags_list):
            if "a" in tag.text():
                assert tag.isHidden() is False
            else:
                assert tag.isHidden() is True

    def test_filter_matches_some_substring(self, dialog: TagEditDialog) -> None:
        """Filter with substring matches the relevant items."""
        dialog.new_tags_input.setText("aa")

        for tag in self._get_tags(dialog.tags_list):
            if "aa" in tag.text():
                assert tag.isHidden() is False
            else:
                assert tag.isHidden() is True

    def test_filter_no_match(self, dialog: TagEditDialog) -> None:
        """Filter with no matches hides all items."""
        dialog.new_tags_input.setText("d")

        assert all(tag.isHidden() for tag in self._get_tags(dialog.tags_list))

    def test_select_all_and_none(self, dialog: TagEditDialog) -> None:
        """
        Test selecting all tags and selecting none of the tags.

        :param dialog: The TagEditDialog instance to test.
        """
        dialog.select_all()
        assert all(
            tag.checkState() == Qt.CheckState.Checked
            for tag in self._get_tags(dialog.tags_list)
        )

        dialog.select_none()
        assert all(
            tag.checkState() == Qt.CheckState.Unchecked
            for tag in self._get_tags(dialog.tags_list)
        )


class TestStartupImpactLabel:
    """The startup impact label on mod list items, driven via repolish."""

    @pytest.fixture
    def widget(self, qtbot: Any) -> ModListItemInner:
        settings = MagicMock(spec=Settings)
        settings.mod_type_filter = False
        settings.show_save_comparison_indicators = False
        settings.mod_list_updated_indicator = False
        settings.mod_list_startup_impact = True
        metadata_controller = MagicMock()
        metadata_controller.get_mod.return_value = None
        with patch("app.views.mods_panel.auxdb_get_mod_tags", return_value=[]):
            widget = ModListItemInner(
                errors_warnings="",
                errors="",
                warnings="",
                filtered=False,
                invalid=False,
                mismatch=False,
                alternative=False,
                settings=settings,
                path="/mods/test",
                mod_color=None,  # type: ignore[arg-type]
                metadata_controller=metadata_controller,
            )
        qtbot.addWidget(widget)
        return widget

    @staticmethod
    def _item(
        startup_impact_s: float | None, tooltip: str = ""
    ) -> CustomListWidgetItem:
        """Build an item whose metadata carries only what repolish reads."""
        data = object.__new__(CustomListWidgetItemMetadata)
        data.errors = ""
        data.warnings = ""
        data.mod_tags = []
        data.mod_color = None
        data.filtered = False
        data.list_type = "Active"
        data.startup_impact_s = startup_impact_s
        data.startup_impact_tooltip = tooltip
        item = CustomListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, data)
        return item

    def test_label_shown_with_impact(self, widget: ModListItemInner) -> None:
        widget.repolish(self._item(0.42, "Startup impact: 420ms"))

        assert not widget.startup_impact_label.isHidden()
        assert widget.startup_impact_label.text() == "420ms"
        assert widget.startup_impact_label.toolTip() == "Startup impact: 420ms"
        # below the warn threshold: green
        assert "#5cb85c" in widget.startup_impact_label.styleSheet()

    def test_label_placed_after_warning_and_error_icons(
        self, widget: ModListItemInner
    ) -> None:
        layout = widget.main_item_layout
        indices = {
            item.widget(): i
            for i in range(layout.count())
            if (item := layout.itemAt(i)) is not None and item.widget() is not None
        }
        # the updated icon (when enabled) is added before these two, so being
        # after warning/error also puts the label after the updated icon
        impact_index = indices[widget.startup_impact_label]
        assert impact_index > indices[widget.warning_icon_label]
        assert impact_index > indices[widget.error_icon_label]

    def test_label_color_thresholds(self, widget: ModListItemInner) -> None:
        widget.repolish(self._item(1.5))
        assert "#f0ad4e" in widget.startup_impact_label.styleSheet()

        widget.repolish(self._item(7.2))
        assert "#d9534f" in widget.startup_impact_label.styleSheet()

    def test_label_hidden_without_impact(self, widget: ModListItemInner) -> None:
        widget.repolish(self._item(2.34))
        widget.repolish(self._item(None))

        assert widget.startup_impact_label.isHidden()
        assert widget.startup_impact_label.text() == ""

    def test_label_hidden_when_setting_disabled(self, widget: ModListItemInner) -> None:
        widget.settings.mod_list_startup_impact = False
        widget.repolish(self._item(2.34))

        assert widget.startup_impact_label.isHidden()
