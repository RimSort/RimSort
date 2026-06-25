from pathlib import Path
from typing import Callable

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QMessageBox

from app.controllers.settings_tabs.base_tab_controller import BaseTabController
from app.models.settings import Settings
from app.utils.constants import DEFAULT_INSTANCE_NAME
from app.utils.generic import platform_specific_open
from app.utils.system_info import SystemInfo
from app.views.dialogue import BinaryChoiceDialog, show_dialogue_file
from app.views.settings_dialog import SettingsDialog


class FolderPathGroup:
    """Reusable helper for one folder-path row (text field + open/choose/clear buttons)."""

    def __init__(
        self,
        prefix: str,
        choose_callback: Callable[[SettingsDialog], str | None] | None = None,
        clear_callback: Callable[[SettingsDialog], None] | None = None,
    ) -> None:
        self._prefix = prefix
        self._choose_callback = choose_callback
        self._clear_callback = clear_callback

    def connect_signals(self, dialog: SettingsDialog) -> None:
        location = getattr(dialog, f"{self._prefix}_location")
        open_btn = getattr(dialog, f"{self._prefix}_location_open_button")
        choose_btn = getattr(dialog, f"{self._prefix}_location_choose_button")
        clear_btn = getattr(dialog, f"{self._prefix}_location_clear_button")

        location.textChanged.connect(lambda: open_btn.setEnabled(location.text() != ""))
        open_btn.clicked.connect(lambda: platform_specific_open(location.text()))
        choose_btn.clicked.connect(lambda: self._on_choose(dialog))
        clear_btn.clicked.connect(lambda: self._on_clear(dialog))

    def update_view(self, dialog: SettingsDialog, path: str) -> None:
        location = getattr(dialog, f"{self._prefix}_location")
        open_btn = getattr(dialog, f"{self._prefix}_location_open_button")
        location.setText(path)
        location.setCursorPosition(0)
        open_btn.setEnabled(path != "")

    def _on_choose(self, dialog: SettingsDialog) -> None:
        if self._choose_callback:
            result = self._choose_callback(dialog)
        else:
            result = show_dialogue_file(mode="open_dir")
        if result:
            getattr(dialog, f"{self._prefix}_location").setText(result)

    def _on_clear(self, dialog: SettingsDialog) -> None:
        getattr(dialog, f"{self._prefix}_location").setText("")
        if self._clear_callback:
            self._clear_callback(dialog)


class LocationsTabController(BaseTabController):
    """Controller for the Locations settings tab.

    Manages: game, config, steam mods, local mods folder paths,
    steam integration checkbox, instance folder override, and
    the clear/autodetect action buttons.
    """

    def __init__(
        self,
        settings: Settings,
        dialog: SettingsDialog,
        validate_game_location: Callable[[str], tuple[bool, str]],
        validate_config_folder_location: Callable[[str], tuple[bool, str]],
        validate_local_mods_location: Callable[[str], tuple[bool, str]],
        on_path_selected: Callable[[str], None],
        on_autodetect: Callable[[], None],
        on_instance_folder_choose: Callable[[], None],
        on_instance_folder_clear: Callable[[], None],
    ) -> None:
        super().__init__(settings, dialog)
        self._validate_game_location = validate_game_location
        self._validate_config_folder_location = validate_config_folder_location
        self._validate_local_mods_location = validate_local_mods_location
        self._path_selected_callback = on_path_selected
        self._on_autodetect_callback = on_autodetect
        self._on_instance_folder_choose_callback = on_instance_folder_choose
        self._on_instance_folder_clear_callback = on_instance_folder_clear

        self._groups: list[FolderPathGroup] = [
            FolderPathGroup(
                prefix="game",
                choose_callback=self._on_game_choose,
                clear_callback=self._on_game_clear,
            ),
            FolderPathGroup(
                prefix="config_folder",
                choose_callback=self._on_config_choose,
            ),
            FolderPathGroup(
                prefix="steam_mods_folder",
                choose_callback=self._on_steam_mods_choose,
                clear_callback=self._on_steam_mods_clear,
            ),
            FolderPathGroup(
                prefix="local_mods_folder",
                choose_callback=self._on_local_mods_choose,
            ),
        ]

    def connect_signals(self) -> None:
        for group in self._groups:
            group.connect_signals(self.dialog)

        # Instance folder location
        self.dialog.instance_folder_location_choose_button.clicked.connect(
            self._on_instance_folder_choose_callback
        )
        self.dialog.instance_folder_location_clear_button.clicked.connect(
            self._on_instance_folder_clear_callback
        )

        # Clear and autodetect buttons
        self.dialog.locations_clear_button.clicked.connect(
            self._on_clear_all_button_clicked
        )
        self.dialog.locations_autodetect_button.clicked.connect(
            self._on_autodetect_callback
        )

    def update_view_from_model(self) -> None:
        instance = self.settings.instances[self.settings.current_instance]

        self.dialog.steam_client_integration_checkbox.setChecked(
            instance.steam_client_integration
        )
        # Explicitly sync UI enable states so the handler runs even when the
        # checkbox state hasn't changed (e.g. default unchecked + model unchecked).
        self.dialog._on_steam_integration_toggled()

        self._groups[0].update_view(self.dialog, str(instance.game_folder))
        self._groups[1].update_view(self.dialog, str(instance.config_folder))
        self._groups[2].update_view(self.dialog, str(instance.workshop_folder))
        self._groups[3].update_view(self.dialog, str(instance.local_folder))

        is_default = self.settings.current_instance == DEFAULT_INSTANCE_NAME
        self.dialog.instance_folder_location.setText(instance.instance_folder_override)
        self.dialog.instance_folder_location.setCursorPosition(0)
        self.dialog.instance_folder_location.setEnabled(is_default)
        self.dialog.instance_folder_location_choose_button.setEnabled(is_default)
        self.dialog.instance_folder_location_clear_button.setEnabled(is_default)

    def update_model_from_view(self) -> None:
        instance = self.settings.instances[self.settings.current_instance]
        instance.game_folder = self.dialog.game_location.text()
        instance.config_folder = self.dialog.config_folder_location.text()
        instance.workshop_folder = self.dialog.steam_mods_folder_location.text()
        instance.local_folder = self.dialog.local_mods_folder_location.text()
        instance.steam_client_integration = (
            self.dialog.steam_client_integration_checkbox.isChecked()
        )

    # --- Folder path group callbacks ---

    def _on_game_choose(self, dialog: SettingsDialog) -> str | None:
        if SystemInfo().operating_system == SystemInfo.OperatingSystem.MACOS:
            game_location = show_dialogue_file(
                mode="open_dir",
                caption="Select Game Location",
            )
            if not game_location:
                return None
            result = Path(game_location)
        else:
            game_location = show_dialogue_file(
                mode="open_dir",
                caption="Select Game Location",
            )
            if not game_location:
                return None
            result = Path(game_location).resolve()

        is_valid, error_msg = self._validate_game_location(str(result))
        if not is_valid:
            QMessageBox.information(
                dialog,
                dialog.tr("Invalid Game Location"),
                error_msg,
            )
            return None

        dialog.local_mods_folder_location.setText(str(result / "Mods"))
        self._path_selected_callback(str(result))
        return str(result)

    @staticmethod
    def _on_game_clear(dialog: SettingsDialog) -> None:
        dialog.local_mods_folder_location.setText("")

    def _on_config_choose(self, dialog: SettingsDialog) -> str | None:
        config_folder = show_dialogue_file(
            mode="open_dir",
            caption="Select Config Folder",
        )
        if not config_folder:
            return None

        is_valid, error_msg = self._validate_config_folder_location(config_folder)
        if not is_valid:
            QMessageBox.warning(
                dialog,
                dialog.tr("Invalid Config Folder"),
                error_msg,
            )
            return None

        self._path_selected_callback(str(Path(config_folder).parent))
        return config_folder

    def _on_steam_mods_choose(self, dialog: SettingsDialog) -> str | None:
        steam_mods_folder = show_dialogue_file(
            mode="open_dir",
            caption="Select Steam Mods Folder",
        )
        if not steam_mods_folder:
            return None

        self._path_selected_callback(str(Path(steam_mods_folder).parent))
        return steam_mods_folder

    @staticmethod
    def _on_steam_mods_clear(dialog: SettingsDialog) -> None:
        dialog.steam_client_integration_checkbox.setChecked(False)
        dialog.launch_via_steam_protocol_checkbox.setChecked(False)

    def _on_local_mods_choose(self, dialog: SettingsDialog) -> str | None:
        local_mods_folder = show_dialogue_file(
            mode="open_dir",
            caption="Select Local Mods Folder",
        )
        if not local_mods_folder:
            return None

        is_valid, error_msg = self._validate_local_mods_location(local_mods_folder)
        if not is_valid:
            QMessageBox.warning(
                dialog,
                dialog.tr("Invalid Local Mods Folder"),
                error_msg,
            )
            return None

        self._path_selected_callback(str(Path(local_mods_folder).parent))
        return local_mods_folder

    # --- Clear all button ---

    @Slot()
    def _on_clear_all_button_clicked(self, skip_confirmation: bool = False) -> None:
        if not skip_confirmation:
            answer = BinaryChoiceDialog(
                title=self.dialog.tr("Clear all locations"),
                text=self.dialog.tr("Are you sure you want to clear all locations?"),
            )
            if not answer.exec_is_positive():
                return

        self.dialog.game_location.setText("")
        self.dialog.config_folder_location.setText("")
        self.dialog.steam_mods_folder_location.setText("")
        self.dialog.local_mods_folder_location.setText("")
        self.dialog.steam_client_integration_checkbox.setChecked(False)
        self.dialog.launch_via_steam_protocol_checkbox.setChecked(False)
