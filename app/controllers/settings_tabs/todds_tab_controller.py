from app.controllers.settings_tabs.base_tab_controller import BaseTabController
from app.models.settings import Settings
from app.views.settings_dialog import SettingsDialog


class ToddsTabController(BaseTabController):
    """Controller for the todds settings tab.

    Manages: quality preset (optimized/custom), target mods scope,
    dry-run/overwrite toggles, orphaned DDS cleanup, auto-run on launch.
    """

    def __init__(
        self,
        settings: Settings,
        dialog: SettingsDialog,
    ) -> None:
        super().__init__(settings, dialog)

    def connect_signals(self) -> None:
        pass  # All signal wiring is internal to the view

    def update_view_from_model(self) -> None:
        if self.settings.todds_preset == "optimized":
            self.dialog.todds_preset_optimized_radio.setChecked(True)
            self.dialog.todds_custom_command_lineedit.setEnabled(False)
        elif self.settings.todds_preset == "custom":
            self.dialog.todds_preset_custom_radio.setChecked(True)
            self.dialog.todds_custom_command_lineedit.setEnabled(True)
        else:
            self.dialog.todds_preset_optimized_radio.setChecked(True)
            self.dialog.todds_custom_command_lineedit.setEnabled(False)
        if self.settings.todds_active_mods_target:
            self.dialog.todds_active_mods_only_radio.setChecked(True)
        else:
            self.dialog.todds_all_mods_radio.setChecked(True)
        self.dialog.todds_dry_run_checkbox.setChecked(self.settings.todds_dry_run)
        self.dialog.todds_overwrite_checkbox.setChecked(self.settings.todds_overwrite)
        self.dialog.todds_custom_command_lineedit.setText(
            self.settings.todds_custom_command
        )
        self.dialog.auto_delete_orphaned_dds_checkbox.setChecked(
            self.settings.auto_delete_orphaned_dds
        )
        self.dialog.auto_run_todds_before_launch_checkbox.setChecked(
            self.settings.auto_run_todds_before_launch
        )

    def update_model_from_view(self) -> None:
        if self.dialog.todds_preset_custom_radio.isChecked():
            self.settings.todds_preset = "custom"
            self.settings.todds_custom_command = (
                self.dialog.todds_custom_command_lineedit.text()
            )
        else:
            self.settings.todds_preset = "optimized"
        if self.dialog.todds_active_mods_only_radio.isChecked():
            self.settings.todds_active_mods_target = True
        elif self.dialog.todds_all_mods_radio.isChecked():
            self.settings.todds_active_mods_target = False
        self.settings.todds_dry_run = self.dialog.todds_dry_run_checkbox.isChecked()
        self.settings.todds_overwrite = self.dialog.todds_overwrite_checkbox.isChecked()
        self.settings.auto_delete_orphaned_dds = (
            self.dialog.auto_delete_orphaned_dds_checkbox.isChecked()
        )
        self.settings.auto_run_todds_before_launch = (
            self.dialog.auto_run_todds_before_launch_checkbox.isChecked()
        )
