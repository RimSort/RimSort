from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from app.models.settings import Settings
from app.views.mods_panel import TagEditDialog


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
