"""Tests for SortingTabController view↔model sync."""

from unittest.mock import MagicMock

from app.controllers.settings_tabs.sorting_tab_controller import SortingTabController
from app.models.settings import Settings
from app.utils.constants import SortMethod


class TestSortingTabUpdateView:
    """Test update_view_from_model pushes model state into dialog widgets."""

    def test_topological_algorithm_sets_topological_radio(
        self, sorting_tab: tuple[SortingTabController, Settings, MagicMock]
    ) -> None:
        controller, settings, dialog = sorting_tab
        settings.sorting_algorithm = SortMethod.TOPOLOGICAL

        controller.update_view_from_model()

        dialog.sorting_topological_radio.setChecked.assert_called_with(True)

    def test_alphabetical_algorithm_sets_alphabetical_radio(
        self, sorting_tab: tuple[SortingTabController, Settings, MagicMock]
    ) -> None:
        controller, settings, dialog = sorting_tab
        settings.sorting_algorithm = SortMethod.ALPHABETICAL

        controller.update_view_from_model()

        dialog.sorting_alphabetical_radio.setChecked.assert_called_with(True)

    def test_unconditional_checkboxes_pushed_to_view(
        self, sorting_tab: tuple[SortingTabController, Settings, MagicMock]
    ) -> None:
        """Checkboxes using unconditional setChecked(value) are always synced."""
        controller, settings, dialog = sorting_tab
        settings.try_download_missing_mods = True
        settings.duplicate_mods_warning = False
        settings.save_inactive_mods_sort_state = False

        controller.update_view_from_model()

        dialog.download_missing_mods_checkbox.setChecked.assert_called_with(True)
        dialog.show_duplicate_mods_warning_checkbox.setChecked.assert_called_with(False)
        dialog.save_inactive_mods_sort_state_checkbox.setChecked.assert_called_with(
            False
        )

    def test_if_guarded_checkboxes_only_set_when_true(
        self, sorting_tab: tuple[SortingTabController, Settings, MagicMock]
    ) -> None:
        """Some checkboxes use if-guard: only call setChecked(True) when model value is True.
        When False, setChecked is never called (matches existing SettingsController behavior)."""
        controller, settings, dialog = sorting_tab
        settings.use_moddependencies_as_loadTheseBefore = False
        settings.use_alternative_package_ids_as_satisfying_dependencies = False
        settings.prefer_versioned_about_tags = False

        controller.update_view_from_model()

        dialog.use_moddependencies_as_loadTheseBefore.setChecked.assert_not_called()
        dialog.use_alternative_package_ids_as_satisfying_dependencies_checkbox.setChecked.assert_not_called()
        dialog.prefer_versioned_about_tags_checkbox.setChecked.assert_not_called()


class TestSortingTabUpdateModel:
    """Test update_model_from_view reads dialog widget state into model."""

    def test_alphabetical_radio_sets_algorithm(
        self, sorting_tab: tuple[SortingTabController, Settings, MagicMock]
    ) -> None:
        controller, settings, dialog = sorting_tab
        settings.sorting_algorithm = SortMethod.TOPOLOGICAL
        dialog.sorting_alphabetical_radio.isChecked.return_value = True
        dialog.sorting_topological_radio.isChecked.return_value = False

        controller.update_model_from_view()

        assert settings.sorting_algorithm == SortMethod.ALPHABETICAL

    def test_topological_radio_sets_algorithm(
        self, sorting_tab: tuple[SortingTabController, Settings, MagicMock]
    ) -> None:
        controller, settings, dialog = sorting_tab
        settings.sorting_algorithm = SortMethod.ALPHABETICAL
        dialog.sorting_alphabetical_radio.isChecked.return_value = False
        dialog.sorting_topological_radio.isChecked.return_value = True

        controller.update_model_from_view()

        assert settings.sorting_algorithm == SortMethod.TOPOLOGICAL

    def test_checkbox_values_read_into_model(
        self, sorting_tab: tuple[SortingTabController, Settings, MagicMock]
    ) -> None:
        controller, settings, dialog = sorting_tab
        dialog.sorting_alphabetical_radio.isChecked.return_value = False
        dialog.sorting_topological_radio.isChecked.return_value = True
        dialog.use_moddependencies_as_loadTheseBefore.isChecked.return_value = True
        dialog.use_alternative_package_ids_as_satisfying_dependencies_checkbox.isChecked.return_value = False
        dialog.check_deps_checkbox.isChecked.return_value = False
        dialog.prefer_versioned_about_tags_checkbox.isChecked.return_value = True
        dialog.download_missing_mods_checkbox.isChecked.return_value = False
        dialog.show_duplicate_mods_warning_checkbox.isChecked.return_value = True
        dialog.hide_invalid_mods_when_filtering_checkbox.isChecked.return_value = True
        dialog.save_inactive_mods_sort_state_checkbox.isChecked.return_value = True

        controller.update_model_from_view()

        assert settings.use_moddependencies_as_loadTheseBefore is True
        assert settings.use_alternative_package_ids_as_satisfying_dependencies is False
        assert settings.check_dependencies_on_sort is False
        assert settings.prefer_versioned_about_tags is True
        assert settings.try_download_missing_mods is False
        assert settings.duplicate_mods_warning is True
        assert settings.hide_invalid_mods_when_filtering is True
        assert settings.save_inactive_mods_sort_state is True
