"""Tests for SortingTabController view↔model sync."""
# mypy: ignore-errors

from unittest.mock import MagicMock, patch


class TestSortingTabUpdateView:
    """Test update_view_from_model pushes model state into dialog widgets."""

    @patch("app.models.settings.QApplication")
    @patch("app.models.settings.AppInfo")
    def test_topological_algorithm_sets_topological_radio(
        self, mock_app_info: MagicMock, mock_qapp: MagicMock
    ) -> None:
        mock_qapp.font.return_value.family.return_value = "monospace"
        mock_app_info.return_value.app_storage_folder = MagicMock()
        mock_app_info.return_value.app_settings_file = MagicMock()

        from app.controllers.settings_tabs.sorting_tab_controller import (
            SortingTabController,
        )

        from app.models.settings import Settings
        from app.utils.constants import SortMethod

        settings = Settings()
        settings.sorting_algorithm = SortMethod.TOPOLOGICAL
        dialog = MagicMock()

        controller = SortingTabController(settings, dialog)
        controller.update_view_from_model()

        dialog.sorting_topological_radio.setChecked.assert_called_with(True)

    @patch("app.models.settings.QApplication")
    @patch("app.models.settings.AppInfo")
    def test_alphabetical_algorithm_sets_alphabetical_radio(
        self, mock_app_info: MagicMock, mock_qapp: MagicMock
    ) -> None:
        mock_qapp.font.return_value.family.return_value = "monospace"
        mock_app_info.return_value.app_storage_folder = MagicMock()
        mock_app_info.return_value.app_settings_file = MagicMock()

        from app.controllers.settings_tabs.sorting_tab_controller import (
            SortingTabController,
        )

        from app.models.settings import Settings
        from app.utils.constants import SortMethod

        settings = Settings()
        settings.sorting_algorithm = SortMethod.ALPHABETICAL
        dialog = MagicMock()

        controller = SortingTabController(settings, dialog)
        controller.update_view_from_model()

        dialog.sorting_alphabetical_radio.setChecked.assert_called_with(True)

    @patch("app.models.settings.QApplication")
    @patch("app.models.settings.AppInfo")
    def test_unconditional_checkboxes_pushed_to_view(
        self, mock_app_info: MagicMock, mock_qapp: MagicMock
    ) -> None:
        """Checkboxes using unconditional setChecked(value) are always synced."""
        mock_qapp.font.return_value.family.return_value = "monospace"
        mock_app_info.return_value.app_storage_folder = MagicMock()
        mock_app_info.return_value.app_settings_file = MagicMock()

        from app.controllers.settings_tabs.sorting_tab_controller import (
            SortingTabController,
        )

        from app.models.settings import Settings

        settings = Settings()
        settings.try_download_missing_mods = True
        settings.duplicate_mods_warning = False
        settings.mod_type_filter = True
        settings.inactive_mods_sorting = False
        dialog = MagicMock()

        controller = SortingTabController(settings, dialog)
        controller.update_view_from_model()

        dialog.download_missing_mods_checkbox.setChecked.assert_called_with(True)
        dialog.show_duplicate_mods_warning_checkbox.setChecked.assert_called_with(False)
        dialog.mod_type_filter_checkbox.setChecked.assert_called_with(True)
        dialog.inactive_mods_sorting_checkbox.setChecked.assert_called_with(False)

    @patch("app.models.settings.QApplication")
    @patch("app.models.settings.AppInfo")
    def test_if_guarded_checkboxes_only_set_when_true(
        self, mock_app_info: MagicMock, mock_qapp: MagicMock
    ) -> None:
        """Some checkboxes use if-guard: only call setChecked(True) when model value is True.
        When False, setChecked is never called (matches existing SettingsController behavior)."""
        mock_qapp.font.return_value.family.return_value = "monospace"
        mock_app_info.return_value.app_storage_folder = MagicMock()
        mock_app_info.return_value.app_settings_file = MagicMock()

        from app.controllers.settings_tabs.sorting_tab_controller import (
            SortingTabController,
        )

        from app.models.settings import Settings

        settings = Settings()
        settings.use_moddependencies_as_loadTheseBefore = False
        settings.use_alternative_package_ids_as_satisfying_dependencies = False
        settings.prefer_versioned_about_tags = False
        dialog = MagicMock()

        controller = SortingTabController(settings, dialog)
        controller.update_view_from_model()

        dialog.use_moddependencies_as_loadTheseBefore.setChecked.assert_not_called()
        dialog.use_alternative_package_ids_as_satisfying_dependencies_checkbox.setChecked.assert_not_called()
        dialog.prefer_versioned_about_tags_checkbox.setChecked.assert_not_called()


class TestSortingTabUpdateModel:
    """Test update_model_from_view reads dialog widget state into model."""

    @patch("app.models.settings.QApplication")
    @patch("app.models.settings.AppInfo")
    def test_alphabetical_radio_sets_algorithm(
        self, mock_app_info: MagicMock, mock_qapp: MagicMock
    ) -> None:
        mock_qapp.font.return_value.family.return_value = "monospace"
        mock_app_info.return_value.app_storage_folder = MagicMock()
        mock_app_info.return_value.app_settings_file = MagicMock()

        from app.controllers.settings_tabs.sorting_tab_controller import (
            SortingTabController,
        )

        from app.models.settings import Settings
        from app.utils.constants import SortMethod

        settings = Settings()
        settings.sorting_algorithm = SortMethod.TOPOLOGICAL  # start different
        dialog = MagicMock()
        dialog.sorting_alphabetical_radio.isChecked.return_value = True
        dialog.sorting_topological_radio.isChecked.return_value = False

        controller = SortingTabController(settings, dialog)
        controller.update_model_from_view()

        assert settings.sorting_algorithm == SortMethod.ALPHABETICAL

    @patch("app.models.settings.QApplication")
    @patch("app.models.settings.AppInfo")
    def test_topological_radio_sets_algorithm(
        self, mock_app_info: MagicMock, mock_qapp: MagicMock
    ) -> None:
        mock_qapp.font.return_value.family.return_value = "monospace"
        mock_app_info.return_value.app_storage_folder = MagicMock()
        mock_app_info.return_value.app_settings_file = MagicMock()

        from app.controllers.settings_tabs.sorting_tab_controller import (
            SortingTabController,
        )

        from app.models.settings import Settings
        from app.utils.constants import SortMethod

        settings = Settings()
        settings.sorting_algorithm = SortMethod.ALPHABETICAL  # start different
        dialog = MagicMock()
        dialog.sorting_alphabetical_radio.isChecked.return_value = False
        dialog.sorting_topological_radio.isChecked.return_value = True

        controller = SortingTabController(settings, dialog)
        controller.update_model_from_view()

        assert settings.sorting_algorithm == SortMethod.TOPOLOGICAL

    @patch("app.models.settings.QApplication")
    @patch("app.models.settings.AppInfo")
    def test_checkbox_values_read_into_model(
        self, mock_app_info: MagicMock, mock_qapp: MagicMock
    ) -> None:
        mock_qapp.font.return_value.family.return_value = "monospace"
        mock_app_info.return_value.app_storage_folder = MagicMock()
        mock_app_info.return_value.app_settings_file = MagicMock()

        from app.controllers.settings_tabs.sorting_tab_controller import (
            SortingTabController,
        )

        from app.models.settings import Settings

        settings = Settings()
        dialog = MagicMock()
        # Set all checkbox mocks to return specific values
        dialog.sorting_alphabetical_radio.isChecked.return_value = False
        dialog.sorting_topological_radio.isChecked.return_value = True
        dialog.use_moddependencies_as_loadTheseBefore.isChecked.return_value = True
        dialog.use_alternative_package_ids_as_satisfying_dependencies_checkbox.isChecked.return_value = False
        dialog.check_deps_checkbox.isChecked.return_value = False
        dialog.prefer_versioned_about_tags_checkbox.isChecked.return_value = True
        dialog.download_missing_mods_checkbox.isChecked.return_value = False
        dialog.show_duplicate_mods_warning_checkbox.isChecked.return_value = True
        dialog.mod_type_filter_checkbox.isChecked.return_value = False
        dialog.hide_invalid_mods_when_filtering_checkbox.isChecked.return_value = True
        dialog.inactive_mods_sorting_checkbox.isChecked.return_value = False
        dialog.save_inactive_mods_sort_state_checkbox.isChecked.return_value = True

        controller = SortingTabController(settings, dialog)
        controller.update_model_from_view()

        assert settings.use_moddependencies_as_loadTheseBefore is True
        assert settings.use_alternative_package_ids_as_satisfying_dependencies is False
        assert settings.check_dependencies_on_sort is False
        assert settings.prefer_versioned_about_tags is True
        assert settings.try_download_missing_mods is False
        assert settings.duplicate_mods_warning is True
        assert settings.mod_type_filter is False
        assert settings.hide_invalid_mods_when_filtering is True
        assert settings.inactive_mods_sorting is False
        assert settings.save_inactive_mods_sort_state is True
