from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from app.views.mods_panel import SettingsController, TagEditDialog


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
                settings_controller=MagicMock(spec=SettingsController),
                existing_selected_tags={"a", "aa", "b", "bb"},
            )
            qtbot.addWidget(dialog)
            assert dialog.tags_list.count() == 6
            assert len(dialog.tags_list.selectedItems()) == 4
            return dialog

    @staticmethod
    def _get_tags(widget: QListWidget) -> list[QListWidgetItem]:
        """
        Get tags from the witget as a list to iterate over.

        :return: A list of tag items.
        """
        return [widget.item(i) for i in range(widget.count())]

    def test_insert_new_tag(self, dialog: TagEditDialog) -> None:
        """
        Test inserting a new tag.

        :param dialog: The TagEditDialog instance to test.
        """
        dialog.tags_text_input.setText("dd,")

        # jscpd:ignore-start
        found_items = dialog.tags_list.findItems("dd", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "dd"
        assert item.isSelected() is True
        assert item.isHidden() is False

        found_items = dialog.tags_list.findItems("a", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "a"
        assert item.isSelected() is True
        assert item.isHidden() is False

        found_items = dialog.tags_list.findItems("c", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "c"
        assert item.isSelected() is False
        assert item.isHidden() is False
        # jscpd:ignore-end

    def test_update_existing_tag_already_selected(self, dialog: TagEditDialog) -> None:
        """
        Test updating an existing tag that is already selected.

        :param dialog: The TagEditDialog instance to test.
        """
        dialog.tags_text_input.setText("a,")

        # jscpd:ignore-start
        found_items = dialog.tags_list.findItems("a", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "a"
        assert item.isSelected() is False
        assert item.isHidden() is False

        found_items = dialog.tags_list.findItems("aa", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "aa"
        assert item.isSelected() is True
        assert item.isHidden() is False

        found_items = dialog.tags_list.findItems("c", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "c"
        assert item.isSelected() is False
        assert item.isHidden() is False
        # jscpd:ignore-end

    def test_update_existing_tag_not_already_selected(
        self, dialog: TagEditDialog
    ) -> None:
        """
        Test updating an existing tag that is not already selected.

        :param dialog: The TagEditDialog instance to test.
        """
        dialog.tags_text_input.setText("cc,")

        # jscpd:ignore-start
        found_items = dialog.tags_list.findItems("cc", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "cc"
        assert item.isSelected() is True
        assert item.isHidden() is False

        found_items = dialog.tags_list.findItems("a", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "a"
        assert item.isSelected() is True
        assert item.isHidden() is False
        # jscpd:ignore-end

    def test_select_all_and_none(self, dialog: TagEditDialog) -> None:
        """
        Test selecting all tags and selecting none of the tags.

        :param dialog: The TagEditDialog instance to test.
        """
        dialog.select_all()
        assert all(tag.isSelected() is True for tag in self._get_tags(dialog.tags_list))

        dialog.select_none()
        assert all(
            tag.isSelected() is False for tag in self._get_tags(dialog.tags_list)
        )

    def filter_tags(self, dialog: TagEditDialog) -> None:
        """
        Test filtering tags based on user input.

        :param dialog: The TagEditDialog instance to test.
        """
        dialog.tags_text_input.setText("a")
        assert all(
            tag.isHidden() is ("a" not in tag.text())
            for tag in self._get_tags(dialog.tags_list)
        )

        dialog.tags_text_input.setText("aa")
        assert all(
            tag.isHidden() is ("aa" not in tag.text())
            for tag in self._get_tags(dialog.tags_list)
        )

        dialog.tags_text_input.clear()
        assert all(tag.isHidden() is False for tag in self._get_tags(dialog.tags_list))

        dialog.tags_text_input.setText("d")
        assert all(tag.isHidden() is True for tag in self._get_tags(dialog.tags_list))
