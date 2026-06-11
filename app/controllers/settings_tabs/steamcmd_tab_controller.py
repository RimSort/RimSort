from pathlib import Path
from typing import Callable

from PySide6.QtCore import Slot

from app.controllers.settings_tabs.base_tab_controller import BaseTabController
from app.models.settings import Settings
from app.utils.event_bus import EventBus
from app.views.dialogue import show_dialogue_file
from app.views.settings_dialog import SettingsDialog


class SteamcmdTabController(BaseTabController):
    """Controller for the SteamCMD settings tab.

    Manages: validate downloads toggle, auto-clear depot cache toggle,
    delete-before-update toggle, install location path with file chooser,
    and 4 action buttons (clear cache, import ACF, delete ACF, install).
    """

    def __init__(
        self,
        settings: Settings,
        dialog: SettingsDialog,
        last_file_dialog_path: str,
        on_path_selected: Callable[[str], None],
    ) -> None:
        super().__init__(settings, dialog)
        self._last_file_dialog_path = last_file_dialog_path
        self._on_path_selected = on_path_selected

    def connect_signals(self) -> None:
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

    def update_model_from_view(self) -> None:
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
