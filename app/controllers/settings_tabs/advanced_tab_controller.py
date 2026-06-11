from PySide6.QtCore import Slot

from app.controllers.settings_tabs.base_tab_controller import BaseTabController
from app.models.settings import Settings
from app.utils.event_bus import EventBus
from app.views.settings_dialog import SettingsDialog


class AdvancedTabController(BaseTabController):
    """Controller for the Advanced settings tab.

    Manages: debug logging, watchdog, clear/DLC behavior, mod update checks,
    rich text rendering, DB auto-update, mod name search scope, backup policy,
    save-comparison indicators, mod coloring mode.
    """

    def __init__(
        self,
        settings: Settings,
        dialog: SettingsDialog,
    ) -> None:
        super().__init__(settings, dialog)
        self._change_mod_coloring_mode = False

    def connect_signals(self) -> None:
        try:
            self.dialog.show_save_comparison_indicators_checkbox.toggled.connect(
                self._on_toggle_show_save_comparison_indicators
            )
        except (AttributeError, TypeError):
            from loguru import logger

            logger.warning(
                "show_save_comparison_indicators_checkbox not available for signal wiring"
            )

        self.dialog.color_background_instead_of_text_checkbox.stateChanged.connect(
            self._on_use_background_coloring_checkbox_changed
        )

        self.dialog.include_mod_notes_in_mod_name_filter_checkbox.stateChanged.connect(
            self._on_include_mod_notes_in_mod_name_filter_changed
        )

        EventBus().settings_have_changed.connect(self._handle_mod_coloring_mode_changed)

    def update_view_from_model(self) -> None:
        try:
            self.dialog.show_save_comparison_indicators_checkbox.setChecked(
                self.settings.show_save_comparison_indicators
            )
        except (AttributeError, TypeError):
            from loguru import logger

            logger.warning(
                "show_save_comparison_indicators_checkbox not available for view update"
            )

        self.dialog.debug_logging_checkbox.setChecked(
            self.settings.debug_logging_enabled
        )
        self.dialog.watchdog_checkbox.setChecked(self.settings.watchdog_toggle)
        self.dialog.backup_saves_on_launch_checkbox.setChecked(
            self.settings.backup_saves_on_launch
        )
        self.dialog.auto_backup_retention_count_spinbox.setValue(
            self.settings.auto_backup_retention_count
        )
        self.dialog.auto_backup_compression_count_spinbox.setValue(
            self.settings.auto_backup_compression_count
        )
        self.dialog.color_background_instead_of_text_checkbox.setChecked(
            self.settings.color_background_instead_of_text_toggle
        )
        self.dialog.clear_moves_dlc_checkbox.setChecked(self.settings.clear_moves_dlc)
        self.dialog.show_mod_updates_checkbox.setChecked(
            self.settings.steam_mods_update_check
        )
        self.dialog.render_unity_rich_text_checkbox.setChecked(
            self.settings.render_unity_rich_text
        )
        self.dialog.update_databases_on_startup_checkbox.setChecked(
            self.settings.update_databases_on_startup
        )
        self.dialog.include_mod_notes_in_mod_name_filter_checkbox.setChecked(
            self.settings.include_mod_notes_in_mod_name_filter
        )
        self.dialog.enable_backup_before_update_checkbox.setChecked(
            self.settings.enable_backup_before_update
        )
        self.dialog.max_backups_spinbox.setValue(self.settings.max_backups)

    def update_model_from_view(self) -> None:
        self.settings.debug_logging_enabled = (
            self.dialog.debug_logging_checkbox.isChecked()
        )
        self.settings.watchdog_toggle = self.dialog.watchdog_checkbox.isChecked()
        self.settings.backup_saves_on_launch = (
            self.dialog.backup_saves_on_launch_checkbox.isChecked()
        )
        self.settings.auto_backup_retention_count = (
            self.dialog.auto_backup_retention_count_spinbox.value()
        )
        self.settings.auto_backup_compression_count = (
            self.dialog.auto_backup_compression_count_spinbox.value()
        )
        self.settings.color_background_instead_of_text_toggle = (
            self.dialog.color_background_instead_of_text_checkbox.isChecked()
        )
        self.settings.clear_moves_dlc = self.dialog.clear_moves_dlc_checkbox.isChecked()
        self.settings.steam_mods_update_check = (
            self.dialog.show_mod_updates_checkbox.isChecked()
        )
        self.settings.render_unity_rich_text = (
            self.dialog.render_unity_rich_text_checkbox.isChecked()
        )
        self.settings.update_databases_on_startup = (
            self.dialog.update_databases_on_startup_checkbox.isChecked()
        )
        self.settings.include_mod_notes_in_mod_name_filter = (
            self.dialog.include_mod_notes_in_mod_name_filter_checkbox.isChecked()
        )
        self.settings.enable_backup_before_update = (
            self.dialog.enable_backup_before_update_checkbox.isChecked()
        )
        self.settings.max_backups = self.dialog.max_backups_spinbox.value()

    @Slot(bool)
    def _on_toggle_show_save_comparison_indicators(self, checked: bool) -> None:
        self.settings.show_save_comparison_indicators = checked
        self.settings.save()

    @Slot()
    def _on_use_background_coloring_checkbox_changed(self) -> None:
        self._change_mod_coloring_mode = not self._change_mod_coloring_mode

    @Slot()
    def _on_include_mod_notes_in_mod_name_filter_changed(self) -> None:
        self.settings.include_mod_notes_in_mod_name_filter = (
            self.dialog.include_mod_notes_in_mod_name_filter_checkbox.isChecked()
        )

    @Slot()
    def _handle_mod_coloring_mode_changed(self) -> None:
        if self._change_mod_coloring_mode:
            self._change_mod_coloring_mode = False
            EventBus().do_change_mod_coloring_mode.emit()
