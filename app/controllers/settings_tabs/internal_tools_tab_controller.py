from pathlib import Path

from PySide6.QtCore import Slot

from app.controllers.settings_tabs.base_tab_controller import BaseTabController
from app.utils.event_bus import EventBus
from app.views.dialogue import show_dialogue_file


class InternalToolsTabController(BaseTabController):
    """Controller for the Internal Tools settings tab.

    Manages: SteamCMD settings (validate, auto-clear, delete-before-update,
    install location, action buttons) and todds texture optimization settings
    (quality preset, target scope, dry-run, overwrite, orphaned DDS, auto-run).
    """

    def connect_signals(self) -> None:
        # SteamCMD signals
        self.dialog.steamcmd_install_location_choose_button.clicked.connect(
            self._on_install_location_choose
        )
        self.dialog.steamcmd_clear_depot_cache_button.clicked.connect(
            self._on_clear_depot_cache
        )
        self.dialog.steamcmd_import_acf_button.clicked.connect(self._on_import_acf)
        self.dialog.steamcmd_delete_acf_button.clicked.connect(self._on_delete_acf)
        self.dialog.steamcmd_install_button.clicked.connect(self._on_install)

    def update_view_from_model(self) -> None:
        # --- SteamCMD ---
        instance = self.settings.instances[self.settings.current_instance]

        self.dialog.steamcmd_validate_downloads_checkbox.setChecked(
            self.settings.steamcmd_validate_downloads
        )
        self.dialog.steamcmd_auto_clear_depot_cache_checkbox.setChecked(
            instance.steamcmd_auto_clear_depot_cache
        )
        self.dialog.steamcmd_delete_before_update_checkbox.setChecked(
            self.settings.steamcmd_delete_before_update
        )
        self.dialog.steamcmd_install_location.setText(
            str(instance.steamcmd_install_path)
        )

        # --- todds ---
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
        # --- SteamCMD ---
        instance = self.settings.instances[self.settings.current_instance]

        self.settings.steamcmd_validate_downloads = (
            self.dialog.steamcmd_validate_downloads_checkbox.isChecked()
        )
        self.settings.steamcmd_delete_before_update = (
            self.dialog.steamcmd_delete_before_update_checkbox.isChecked()
        )
        instance.steamcmd_auto_clear_depot_cache = (
            self.dialog.steamcmd_auto_clear_depot_cache_checkbox.isChecked()
        )
        instance.steamcmd_install_path = self.dialog.steamcmd_install_location.text()

        # --- todds ---
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

    # --- SteamCMD handlers ---

    @Slot()
    def _on_install_location_choose(self) -> None:
        steamcmd_install_location = show_dialogue_file(
            mode="open_dir",
            caption="Select Steamcmd Install Location",
            _dir=str(self._last_file_dialog_path),
        )
        if not steamcmd_install_location:
            return

        self.dialog.steamcmd_install_location.setText(steamcmd_install_location)
        if self._on_path_selected:
            self._on_path_selected(str(Path(steamcmd_install_location).parent))

    @Slot()
    def _on_clear_depot_cache(self) -> None:
        EventBus().do_clear_steamcmd_depot_cache.emit()

    @Slot()
    def _on_import_acf(self) -> None:
        self.dialog.global_ok_button.click()
        EventBus().do_import_acf.emit()

    @Slot()
    def _on_delete_acf(self) -> None:
        self.dialog.global_ok_button.click()
        EventBus().do_delete_acf.emit()

    @Slot()
    def _on_install(self) -> None:
        self.dialog.global_ok_button.click()
        EventBus().do_install_steamcmd.emit()
