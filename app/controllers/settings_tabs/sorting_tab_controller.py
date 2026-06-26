from PySide6.QtCore import Slot

from app.controllers.settings_tabs.base_tab_controller import BaseTabController
from app.models.settings import Settings
from app.utils.constants import SortMethod
from app.utils.event_bus import EventBus
from app.views.settings_dialog import SettingsDialog


class SortingTabController(BaseTabController):
    """Controller for the Sorting settings tab.

    Manages: sorting algorithm, dependency handling, XML parsing behavior,
    mod list options, mod coloring mode, and inactive mods sorting.
    """

    def __init__(
        self,
        settings: Settings,
        dialog: SettingsDialog,
    ) -> None:
        super().__init__(settings, dialog)
        self._change_mod_coloring_mode = False

    def connect_signals(self) -> None:
        self.dialog.color_background_instead_of_text_checkbox.stateChanged.connect(
            self._on_use_background_coloring_checkbox_changed
        )
        EventBus().settings_have_changed.connect(self._handle_mod_coloring_mode_changed)

    def update_view_from_model(self) -> None:
        # Match the existing SettingsController behavior exactly:
        # radio buttons use if/elif (only setChecked(True) on match),
        # some checkboxes use if-guard (only set when True),
        # others use unconditional setChecked(value).
        if self.settings.sorting_algorithm == SortMethod.ALPHABETICAL:
            self.dialog.sorting_alphabetical_radio.setChecked(True)
        elif self.settings.sorting_algorithm == SortMethod.TOPOLOGICAL:
            self.dialog.sorting_topological_radio.setChecked(True)

        if self.settings.use_moddependencies_as_loadTheseBefore:
            self.dialog.use_moddependencies_as_loadTheseBefore.setChecked(True)
        if self.settings.use_alternative_package_ids_as_satisfying_dependencies:
            self.dialog.use_alternative_package_ids_as_satisfying_dependencies_checkbox.setChecked(
                True
            )
        self.dialog.check_deps_checkbox.setChecked(
            self.settings.check_dependencies_on_sort
        )
        if self.settings.prefer_versioned_about_tags:
            self.dialog.prefer_versioned_about_tags_checkbox.setChecked(True)
        self.dialog.case_insensitive_about_xml_checkbox.setChecked(
            self.settings.case_insensitive_about_xml_lookup
        )
        self.dialog.render_unity_rich_text_checkbox.setChecked(
            self.settings.render_unity_rich_text
        )
        self.dialog.color_background_instead_of_text_checkbox.setChecked(
            self.settings.color_background_instead_of_text_toggle
        )
        self.dialog.download_missing_mods_checkbox.setChecked(
            self.settings.try_download_missing_mods
        )
        self.dialog.show_duplicate_mods_warning_checkbox.setChecked(
            self.settings.duplicate_mods_warning
        )
        self.dialog.hide_invalid_mods_when_filtering_checkbox.setChecked(
            self.settings.hide_invalid_mods_when_filtering
        )
        self.dialog.save_inactive_mods_sort_state_checkbox.setChecked(
            self.settings.save_inactive_mods_sort_state
        )

    def update_model_from_view(self) -> None:
        if self.dialog.sorting_alphabetical_radio.isChecked():
            self.settings.sorting_algorithm = SortMethod.ALPHABETICAL
        elif self.dialog.sorting_topological_radio.isChecked():
            self.settings.sorting_algorithm = SortMethod.TOPOLOGICAL

        self.settings.use_moddependencies_as_loadTheseBefore = (
            self.dialog.use_moddependencies_as_loadTheseBefore.isChecked()
        )
        self.settings.use_alternative_package_ids_as_satisfying_dependencies = self.dialog.use_alternative_package_ids_as_satisfying_dependencies_checkbox.isChecked()
        self.settings.check_dependencies_on_sort = (
            self.dialog.check_deps_checkbox.isChecked()
        )
        self.settings.prefer_versioned_about_tags = (
            self.dialog.prefer_versioned_about_tags_checkbox.isChecked()
        )
        self.settings.case_insensitive_about_xml_lookup = (
            self.dialog.case_insensitive_about_xml_checkbox.isChecked()
        )
        self.settings.render_unity_rich_text = (
            self.dialog.render_unity_rich_text_checkbox.isChecked()
        )
        self.settings.color_background_instead_of_text_toggle = (
            self.dialog.color_background_instead_of_text_checkbox.isChecked()
        )
        self.settings.try_download_missing_mods = (
            self.dialog.download_missing_mods_checkbox.isChecked()
        )
        self.settings.duplicate_mods_warning = (
            self.dialog.show_duplicate_mods_warning_checkbox.isChecked()
        )
        self.settings.hide_invalid_mods_when_filtering = (
            self.dialog.hide_invalid_mods_when_filtering_checkbox.isChecked()
        )
        self.settings.save_inactive_mods_sort_state = (
            self.dialog.save_inactive_mods_sort_state_checkbox.isChecked()
        )

    @Slot()
    def _on_use_background_coloring_checkbox_changed(self) -> None:
        self._change_mod_coloring_mode = not self._change_mod_coloring_mode

    @Slot()
    def _handle_mod_coloring_mode_changed(self) -> None:
        if self._change_mod_coloring_mode:
            self._change_mod_coloring_mode = False
            EventBus().do_change_mod_coloring_mode.emit()
