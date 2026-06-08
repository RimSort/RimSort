"""
Integration tests for the modlist merge flow.

This module tests the merge handler in MainContent:
- Merge appends new mods to active list
- Cancel makes no changes
- Sort is called after merge
- Button states match conditions
"""

from contextlib import contextmanager
from typing import Union
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QDialog

from app.views.merge_preview_dialog import MergePreviewDialog


@pytest.fixture
def metadata_manager(mock_metadata_manager: MagicMock) -> MagicMock:
    """MetadataManager with test mod data."""
    mods = {
        "uuid-a": {"name": "Mod A", "packageid": "author.moda"},
        "uuid-b": {"name": "Mod B", "packageid": "author.modb"},
        "uuid-c": {"name": "Mod C", "packageid": "author.modc"},
        "uuid-d": {"name": "Mod D", "packageid": "author.modd"},
    }
    mock_metadata_manager.internal_local_metadata = mods
    return mock_metadata_manager


@contextmanager
def _patch_merge_handler(
    imported_active: list[str],
    dialog_result: QDialog.DialogCode = QDialog.DialogCode.Accepted,
):
    """Patch the file dialog, mod list parser, and preview dialog for merge tests."""
    with (
        patch(
            "app.views.main_content_panel.dialogue.show_dialogue_file",
            return_value="/fake/mods.xml",
        ),
        patch(
            "app.views.main_content_panel.metadata.get_mods_from_list",
            return_value=(imported_active, [], {}, []),
        ),
        patch.object(MergePreviewDialog, "exec", return_value=dialog_result),
    ):
        yield


class TestMergeHandlerIntegration:
    """Integration tests for _do_merge_list_file_xml on MainContent."""

    @pytest.fixture
    def main_content(
        self,
        metadata_manager: MagicMock,
        mock_settings_controller: MagicMock,
        qapp: Union[QApplication, QCoreApplication],
    ) -> MagicMock:
        """Mock MainContent with the attributes the merge handler accesses."""
        mc = MagicMock()
        mc.metadata_manager = metadata_manager
        mc.mods_panel.active_mods_list.uuids = ["uuid-a", "uuid-b"]
        mc.mods_panel.data_source_filter_icons = [1, 2, 3]
        mc.settings_controller = mock_settings_controller
        mc.duplicate_mods = {}
        mc.missing_mods = []
        return mc

    def test_merge_appends_new_mods_to_active(
        self,
        main_content: MagicMock,
        metadata_manager: MagicMock,
    ) -> None:
        """After merge, _insert_data_into_lists is called with the union."""
        from app.views.main_content_panel import MainContent

        with _patch_merge_handler(
            imported_active=["uuid-b", "uuid-c", "uuid-d"],
        ):
            MainContent._do_merge_list_file_xml(main_content)

        main_content._insert_data_into_lists.assert_called_once()
        merged_active = main_content._insert_data_into_lists.call_args[0][0]
        assert merged_active == ["uuid-a", "uuid-b", "uuid-c", "uuid-d"]

    def test_merge_cancel_makes_no_changes(
        self,
        main_content: MagicMock,
        metadata_manager: MagicMock,
    ) -> None:
        """Cancelling the preview dialog leaves the active list unchanged."""
        from app.views.main_content_panel import MainContent

        with _patch_merge_handler(
            imported_active=["uuid-c"],
            dialog_result=QDialog.DialogCode.Rejected,
        ):
            MainContent._do_merge_list_file_xml(main_content)

        main_content._insert_data_into_lists.assert_not_called()

    def test_merge_calls_sort(
        self,
        main_content: MagicMock,
        metadata_manager: MagicMock,
    ) -> None:
        """After merge, _do_sort is called directly."""
        from app.views.main_content_panel import MainContent

        with _patch_merge_handler(imported_active=["uuid-c"]):
            MainContent._do_merge_list_file_xml(main_content)

        main_content._do_sort.assert_called_once()

    def test_full_overlap_button_disabled(
        self,
        metadata_manager: MagicMock,
        qapp: Union[QApplication, QCoreApplication],
    ) -> None:
        """When all imported mods are already active, Merge button is disabled."""
        dialog = MergePreviewDialog(
            new_mods=[],
            already_present=["uuid-a", "uuid-b"],
            missing_packageids=[],
        )
        assert not dialog.merge_button.isEnabled()
