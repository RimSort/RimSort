from typing import Union
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from app.views.merge_preview_dialog import MergePreviewDialog


@pytest.fixture
def metadata_manager(mock_metadata_manager: MagicMock) -> MagicMock:
    """Provide a mock MetadataManager with test mod data."""
    mock_metadata_manager.internal_local_metadata = {
        "uuid-a": {"name": "Mod A", "packageid": "author.moda"},
        "uuid-b": {"name": "Mod B", "packageid": "author.modb"},
        "uuid-c": {"name": "Mod C", "packageid": "author.modc"},
    }
    return mock_metadata_manager


class TestMergePreviewDialogCategorization:
    def test_all_new_mods(
        self,
        metadata_manager: MagicMock,
        qapp: Union[QApplication, QCoreApplication],
    ) -> None:
        dialog = MergePreviewDialog(
            new_mods=["uuid-a", "uuid-b"],
            already_present=[],
            missing_packageids=[],
        )
        assert dialog.new_mod_count == 2
        assert dialog.already_present_count == 0
        assert dialog.missing_count == 0

    def test_all_already_present(
        self,
        metadata_manager: MagicMock,
        qapp: Union[QApplication, QCoreApplication],
    ) -> None:
        dialog = MergePreviewDialog(
            new_mods=[],
            already_present=["uuid-a", "uuid-c"],
            missing_packageids=[],
        )
        assert dialog.new_mod_count == 0
        assert dialog.already_present_count == 2

    def test_mixed_categories(
        self,
        metadata_manager: MagicMock,
        qapp: Union[QApplication, QCoreApplication],
    ) -> None:
        dialog = MergePreviewDialog(
            new_mods=["uuid-a"],
            already_present=["uuid-b"],
            missing_packageids=["removed.mod", "private.mod"],
        )
        assert dialog.new_mod_count == 1
        assert dialog.already_present_count == 1
        assert dialog.missing_count == 2


class TestMergePreviewDialogButtonState:
    def test_merge_button_disabled_when_no_new_mods(
        self,
        metadata_manager: MagicMock,
        qapp: Union[QApplication, QCoreApplication],
    ) -> None:
        dialog = MergePreviewDialog(
            new_mods=[],
            already_present=["uuid-a"],
            missing_packageids=[],
        )
        assert not dialog.merge_button.isEnabled()
        assert dialog.merge_button.toolTip() == "No new mods to add."

    def test_merge_button_enabled_when_new_mods_exist(
        self,
        metadata_manager: MagicMock,
        qapp: Union[QApplication, QCoreApplication],
    ) -> None:
        dialog = MergePreviewDialog(
            new_mods=["uuid-a"],
            already_present=[],
            missing_packageids=[],
        )
        assert dialog.merge_button.isEnabled()


class TestMergePreviewDialogSections:
    def test_new_section_expanded_by_default(
        self,
        metadata_manager: MagicMock,
        qapp: Union[QApplication, QCoreApplication],
    ) -> None:
        dialog = MergePreviewDialog(
            new_mods=["uuid-a"],
            already_present=["uuid-b"],
            missing_packageids=[],
        )
        # Use isHidden() because the dialog is never shown, so isVisible()
        # always returns False for children of an unshown parent.
        assert not dialog.new_section.list_widget.isHidden()

    def test_already_present_section_collapsed_by_default(
        self,
        metadata_manager: MagicMock,
        qapp: Union[QApplication, QCoreApplication],
    ) -> None:
        dialog = MergePreviewDialog(
            new_mods=["uuid-a"],
            already_present=["uuid-b"],
            missing_packageids=[],
        )
        assert dialog.already_present_section.list_widget.isHidden()

    def test_missing_section_expanded_when_non_empty(
        self,
        metadata_manager: MagicMock,
        qapp: Union[QApplication, QCoreApplication],
    ) -> None:
        dialog = MergePreviewDialog(
            new_mods=["uuid-a"],
            already_present=[],
            missing_packageids=["missing.mod"],
        )
        assert not dialog.missing_section.list_widget.isHidden()

    def test_missing_section_hidden_when_empty(
        self,
        metadata_manager: MagicMock,
        qapp: Union[QApplication, QCoreApplication],
    ) -> None:
        dialog = MergePreviewDialog(
            new_mods=["uuid-a"],
            already_present=[],
            missing_packageids=[],
        )
        assert dialog.missing_section.isHidden()
