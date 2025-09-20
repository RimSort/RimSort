import errno
from pathlib import Path
from typing import Any, Dict, Generator, Union
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from app.controllers.settings_controller import SettingsController
from app.utils.metadata import MetadataManager
from app.views.deletion_menu import DeletionResult, ModDeletionMenu


@pytest.fixture(scope="session")
def qapp() -> Generator[Union[QApplication, QCoreApplication], None, None]:
    """Create a QApplication instance for Qt tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def mock_settings_controller() -> MagicMock:
    """Mock SettingsController."""
    controller = MagicMock(spec=SettingsController)
    controller.settings = MagicMock()
    controller.settings.aux_db_time_limit = 1  # Enable DB operations
    controller.settings.current_instance_path = "/fake/path"
    return controller


@pytest.fixture
def mock_metadata_manager() -> MagicMock:
    """Mock MetadataManager."""
    manager = MagicMock(spec=MetadataManager)
    manager.instance.return_value = manager
    return manager


@pytest.fixture
def sample_mod_metadata() -> Dict[str, Any]:
    """Sample mod metadata for testing."""
    return {
        "name": "Test Mod",
        "path": "/fake/mod/path",
        "uuid": "test-uuid-123",
        "publishedfileid": "123456789",
        "steamcmd": True,
    }


@pytest.fixture
def deletion_menu(
    mock_settings_controller: MagicMock,
    mock_metadata_manager: MagicMock,
    qapp: Union[QApplication, QCoreApplication],
) -> ModDeletionMenu:
    """Create a ModDeletionMenu instance for testing."""
    with patch(
        "app.views.deletion_menu.MetadataManager.instance",
        return_value=mock_metadata_manager,
    ):
        menu = ModDeletionMenu(
            settings_controller=mock_settings_controller,
            get_selected_mod_metadata=lambda: [],
            menu_title="Test Menu",
        )
        return menu


class TestDeletionResult:
    """Test the DeletionResult class."""

    def test_initialization(self) -> None:
        """Test DeletionResult initializes correctly."""
        result = DeletionResult()
        assert result.success_count == 0
        assert result.failed_count == 0
        assert result.steamcmd_purge_ids == set()
        assert result.mods_for_unsubscribe == []


class TestModDeletionMenu:
    """Test the ModDeletionMenu class."""

    def test_initialization(self, deletion_menu: ModDeletionMenu) -> None:
        """Test menu initializes with correct title."""
        # The title is set in the class constructor to "Deletion options"
        assert deletion_menu.title() == "Deletion options"

    def test_confirm_deletion_accept(self, deletion_menu: ModDeletionMenu) -> None:
        """Test deletion confirmation when user accepts."""
        with patch("app.views.deletion_menu.show_dialogue_conditional") as mock_dialog:
            from PySide6.QtWidgets import QMessageBox

            mock_dialog.return_value = QMessageBox.StandardButton.Yes
            result = deletion_menu._confirm_deletion("Title", "Text", "Info")
            assert result is True
            mock_dialog.assert_called_once()

    def test_confirm_deletion_reject(self, deletion_menu: ModDeletionMenu) -> None:
        """Test deletion confirmation when user rejects."""
        with patch("app.views.deletion_menu.show_dialogue_conditional") as mock_dialog:
            from PySide6.QtWidgets import QMessageBox

            mock_dialog.return_value = QMessageBox.StandardButton.No
            result = deletion_menu._confirm_deletion("Title", "Text", "Info")
            assert result is False

    def test_perform_deletion_operation_no_mods(
        self, deletion_menu: ModDeletionMenu
    ) -> None:
        """Test deletion operation with no selected mods."""
        with patch("app.views.deletion_menu.show_information") as mock_info:
            deletion_menu._perform_deletion_operation(
                "Title", "Text", "Info", lambda x: True
            )
            mock_info.assert_called_once()

    def test_perform_deletion_operation_with_mods(
        self, deletion_menu: ModDeletionMenu, sample_mod_metadata: Dict[str, Any]
    ) -> None:
        """Test deletion operation with selected mods."""
        deletion_menu.get_selected_mod_metadata = lambda: [sample_mod_metadata]

        with (
            patch.object(
                deletion_menu, "_confirm_deletion", return_value=True
            ) as mock_confirm,
            patch.object(deletion_menu, "_iterate_mods") as mock_iterate,
            patch.object(deletion_menu, "_process_deletion_result") as mock_process,
        ):
            mock_iterate.return_value = DeletionResult()

            deletion_menu._perform_deletion_operation(
                "Title", "Text", "Info", lambda x: True
            )

            mock_confirm.assert_called_once()
            mock_iterate.assert_called_once()
            mock_process.assert_called_once()

    def test_delete_mod_directory_success(
        self,
        deletion_menu: ModDeletionMenu,
        sample_mod_metadata: Dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Test successful mod directory deletion."""
        # Create a temporary directory to delete
        test_dir = tmp_path / "test_mod"
        test_dir.mkdir()
        sample_mod_metadata["path"] = str(test_dir)

        result = deletion_menu._delete_mod_directory(sample_mod_metadata)
        assert result is True
        assert not test_dir.exists()

    def test_delete_mod_directory_not_found(
        self, deletion_menu: ModDeletionMenu, sample_mod_metadata: Dict[str, Any]
    ) -> None:
        """Test deletion of non-existent directory."""
        # On Windows, rmtree might succeed for non-existent paths, so we'll mock it
        with patch(
            "app.views.deletion_menu.rmtree",
            side_effect=FileNotFoundError("No such file or directory"),
        ):
            sample_mod_metadata["path"] = "/non/existent/path"
            result = deletion_menu._delete_mod_directory(sample_mod_metadata)
            assert result is False

    def test_delete_mod_directory_permission_error(
        self,
        deletion_menu: ModDeletionMenu,
        sample_mod_metadata: Dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Test deletion with permission error."""
        test_dir = tmp_path / "test_mod"
        test_dir.mkdir()

        # Mock rmtree to raise OSError
        with patch(
            "app.views.deletion_menu.rmtree",
            side_effect=OSError(errno.EACCES, "Permission denied"),
        ):
            sample_mod_metadata["path"] = str(test_dir)
            result = deletion_menu._delete_mod_directory(sample_mod_metadata)
            assert result is False

    def test_is_official_expansion_true(self, deletion_menu: ModDeletionMenu) -> None:
        """Test detection of official expansion."""
        mod = {"packageid": "ludeon.rimworld.expansion", "data_source": "expansion"}
        assert deletion_menu._is_official_expansion(mod) is True

    def test_is_official_expansion_false(self, deletion_menu: ModDeletionMenu) -> None:
        """Test non-official mod is not detected as expansion."""
        mod = {"packageid": "author.modname", "data_source": "workshop"}
        assert deletion_menu._is_official_expansion(mod) is False

    def test_process_deletion_result_success(
        self, deletion_menu: ModDeletionMenu
    ) -> None:
        """Test processing successful deletion result."""
        result = DeletionResult()
        result.success_count = 2

        with patch("app.views.deletion_menu.show_information") as mock_info:
            deletion_menu._process_deletion_result(result)
            mock_info.assert_called_once()

    def test_process_deletion_result_with_failures(
        self, deletion_menu: ModDeletionMenu
    ) -> None:
        """Test processing result with both success and failures."""
        result = DeletionResult()
        result.success_count = 1
        result.failed_count = 1

        with (
            patch("app.views.deletion_menu.show_information") as mock_info,
            patch("app.views.deletion_menu.show_warning") as mock_warn,
        ):
            deletion_menu._process_deletion_result(result)
            mock_info.assert_called_once()
            mock_warn.assert_called_once()

    def test_handle_steam_action_valid_ids(
        self, deletion_menu: ModDeletionMenu, sample_mod_metadata: Dict[str, Any]
    ) -> None:
        """Test Steam action handling with valid IDs."""
        mods = [sample_mod_metadata]

        with (
            patch("app.views.deletion_menu.EventBus") as mock_eventbus,
            patch("app.views.deletion_menu.show_information") as mock_info,
        ):
            deletion_menu._handle_steam_action("unsubscribe", mods)

            mock_eventbus().do_steamworks_api_call.emit.assert_called_once_with(
                ["unsubscribe", [123456789]]
            )
            mock_info.assert_called_once()

    def test_handle_steam_action_invalid_id(
        self, deletion_menu: ModDeletionMenu
    ) -> None:
        """Test Steam action handling with invalid ID."""
        mod = {"publishedfileid": "invalid", "name": "Test"}
        mods = [mod]

        with patch("app.views.deletion_menu.logger") as mock_logger:
            deletion_menu._handle_steam_action("unsubscribe", mods)
            mock_logger.debug.assert_called_once()

    def test_delete_mod_from_aux_db_time_limit_negative(
        self, deletion_menu: ModDeletionMenu
    ) -> None:
        """Test aux DB deletion when time limit is negative."""
        deletion_menu.settings_controller.settings.aux_db_time_limit = -1

        with patch("app.views.deletion_menu.logger") as mock_logger:
            deletion_menu.delete_mod_from_aux_db("/fake/path")
            mock_logger.debug.assert_called_once()

    def test_delete_mod_from_aux_db_time_limit_positive(
        self, deletion_menu: ModDeletionMenu
    ) -> None:
        """Test aux DB marking as outdated when time limit is positive."""
        deletion_menu.settings_controller.settings.aux_db_time_limit = 1

        with patch("app.views.deletion_menu.AuxMetadataController") as mock_aux_class:
            mock_instance = MagicMock()
            mock_session = MagicMock()
            mock_aux_class.get_or_create_cached_instance.return_value = mock_instance
            mock_instance.Session.return_value.__enter__.return_value = mock_session
            mock_instance.update = MagicMock()

            deletion_menu.delete_mod_from_aux_db("/fake/path")

            # When time_limit > 0, it should call update with outdated=True
            mock_instance.update.assert_called_once_with(
                mock_session, Path("/fake/path"), outdated=True
            )

    def test_dummy_translations(self, deletion_menu: ModDeletionMenu) -> None:
        """Test dummy translations method."""
        # This method just calls tr() for translation extraction
        deletion_menu._dummy_translations()
        # No assertions needed, just ensure it doesn't crash

    def test_handle_uuid_removal_with_missing_uuid(
        self, deletion_menu: ModDeletionMenu, mock_metadata_manager: MagicMock
    ) -> None:
        """Test _handle_uuid_removal when mod_metadata lacks 'uuid' but has 'path'."""
        # Setup mod_metadata without 'uuid' but with 'path'
        mod_path = "/fake/mod/path"
        uuid = "retrieved-uuid-456"
        mod_metadata = {"name": "Test Mod", "path": mod_path}

        # Setup remove_from_uuids list to include the UUID
        deletion_menu.remove_from_uuids = [uuid]

        # Mock metadata_manager.mod_metadata_dir_mapper to return the UUID for the path
        mock_metadata_manager.mod_metadata_dir_mapper = {mod_path: uuid}

        # Patch the metadata_manager instance in deletion_menu to use the mock
        deletion_menu.metadata_manager = mock_metadata_manager

        # Patch the mod_deleted_signal.emit method to track calls
        with patch.object(
            mock_metadata_manager.mod_deleted_signal, "emit"
        ) as mock_emit:
            deletion_menu._handle_uuid_removal(mod_metadata)

            # Assert that the UUID was added to mod_metadata
            assert mod_metadata["uuid"] == uuid

            # Assert that mod_deleted_signal.emit was called with the UUID
            mock_emit.assert_called_once_with(uuid)

            # Assert that the UUID was removed from remove_from_uuids
            assert uuid not in deletion_menu.remove_from_uuids
