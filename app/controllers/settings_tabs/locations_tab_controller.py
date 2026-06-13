from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from loguru import logger
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QLineEdit, QMessageBox

from app.controllers.instance_controller import InstanceController
from app.controllers.settings_tabs.base_tab_controller import (
    BaseTabController,
    SharedFileDialogState,
)
from app.models.settings import Settings
from app.utils.acf_utils import validate_acf_file_exists
from app.utils.constants import DEFAULT_INSTANCE_NAME
from app.utils.generic import platform_specific_open, validate_game_executable
from app.utils.steam_path_detection import detect_platform_paths
from app.utils.system_info import SystemInfo
from app.views.dialogue import BinaryChoiceDialog, show_dialogue_file, show_warning
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
        file_dialog_state: SharedFileDialogState,
    ) -> None:
        super().__init__(settings, dialog, file_dialog_state=file_dialog_state)

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
            self._on_instance_folder_choose
        )
        self.dialog.instance_folder_location_clear_button.clicked.connect(
            self._on_instance_folder_clear
        )

        # Clear and autodetect buttons
        self.dialog.locations_clear_button.clicked.connect(
            self._on_clear_all_button_clicked
        )
        self.dialog.locations_autodetect_button.clicked.connect(
            self._on_autodetect_button_clicked
        )

    def update_view_from_model(self) -> None:
        instance = self.settings.instances[self.settings.current_instance]

        self._groups[0].update_view(self.dialog, str(instance.game_folder))
        self._groups[1].update_view(self.dialog, str(instance.config_folder))
        self._groups[2].update_view(self.dialog, str(instance.workshop_folder))
        self._groups[3].update_view(self.dialog, str(instance.local_folder))

        self.dialog.steam_client_integration_checkbox.setChecked(
            instance.steam_client_integration
        )
        checked = self.dialog.steam_client_integration_checkbox.isChecked()
        self.dialog.steam_mods_folder_location.setEnabled(checked)
        self.dialog.steam_mods_folder_location_open_button.setEnabled(checked)
        self.dialog.steam_mods_folder_location_choose_button.setEnabled(checked)
        self.dialog.steam_mods_folder_location_clear_button.setEnabled(checked)

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

    def validate_before_save(self) -> bool:
        game_folder_text = self.dialog.game_location.text().strip()
        if game_folder_text and not self._validate_game_location(game_folder_text):
            return False

        config_folder_text = self.dialog.config_folder_location.text().strip()
        if config_folder_text and not self._validate_config_folder_location(
            config_folder_text
        ):
            return False

        if self.dialog.steam_client_integration_checkbox.isChecked():
            if not self._validate_steam_integration():
                return False

        return True

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

        if not self._validate_game_location(str(result)):
            return None

        dialog.local_mods_folder_location.setText(str(result / "Mods"))
        if self._file_dialog_state:
            self._file_dialog_state.last_path = str(result)
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

        if not self._validate_config_folder_location(config_folder):
            return None

        if self._file_dialog_state:
            self._file_dialog_state.last_path = str(Path(config_folder).parent)
        return config_folder

    def _on_steam_mods_choose(self, dialog: SettingsDialog) -> str | None:
        steam_mods_folder = show_dialogue_file(
            mode="open_dir",
            caption="Select Steam Mods Folder",
        )
        if not steam_mods_folder:
            return None
        if self._file_dialog_state:
            self._file_dialog_state.last_path = str(Path(steam_mods_folder).parent)
        return steam_mods_folder

    def _on_local_mods_choose(self, dialog: SettingsDialog) -> str | None:
        local_mods_folder = show_dialogue_file(
            mode="open_dir",
            caption="Select Local Mods Folder",
        )
        if not local_mods_folder:
            return None
        if self._file_dialog_state:
            self._file_dialog_state.last_path = str(Path(local_mods_folder).parent)
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

    # --- Autodetect ---

    @Slot()
    def _on_autodetect_button_clicked(self) -> None:
        """Autodetect RimWorld paths based on platform defaults."""
        logger.info("USER ACTION: starting autodetect paths")

        try:
            paths = detect_platform_paths()
        except RuntimeError:
            logger.error("Attempting to autodetect paths on an unknown system")
            return

        if paths.steam_root is not None and "snap" in paths.steam_root.parts:
            show_warning(
                title="Unsupported Steam installation",
                text="Snap-based Steam installation detected.",
                information=(
                    "Steam installed via Snap is not officially supported and may cause issues. "
                    "We recommend installing Steam via your distribution's native package manager "
                    "or Flatpak instead.\n\n"
                    "Autodetection will continue, but some paths may not work correctly."
                ),
            )

        @dataclass
        class _PathGroup:
            folder: Path
            settings_line: QLineEdit
            name: str

        path_groups = [
            _PathGroup(paths.game_folder, self.dialog.game_location, "game"),
            _PathGroup(
                paths.config_folder, self.dialog.config_folder_location, "config"
            ),
            _PathGroup(
                paths.steam_mods_folder,
                self.dialog.steam_mods_folder_location,
                "workshop mods",
            ),
            _PathGroup(
                paths.game_folder / "Mods",
                self.dialog.local_mods_folder_location,
                "local mods",
            ),
        ]

        for group in path_groups:
            if group.folder.exists():
                logger.info(
                    f"Auto-detected {group.name} folder path exists: {group.folder}"
                )
                if not group.settings_line.text():
                    logger.info(
                        f"No value set currently for {group.name} folder. Overwriting with auto-detected path"
                    )
                    group.settings_line.setText(str(group.folder))
                else:
                    logger.info(f"Value already set for {group.name} folder. Passing")
            else:
                logger.warning(
                    f"Auto-detected {group.name} folder path does not exist: {group.folder}"
                )

    # --- Instance folder ---

    @Slot()
    def _on_instance_folder_choose(self) -> None:
        """Open folder dialog to select custom instance folder location."""
        if self.settings.current_instance != DEFAULT_INSTANCE_NAME:
            show_warning(
                title="Cannot Modify Instance Folder",
                text="Only the Default instance can have a custom folder location.",
                information="Custom instance folder location is managed by the Default instance.",
            )
            return

        instance_folder_location = show_dialogue_file(
            mode="open_dir",
            caption="Select Instance Folder Location",
            _dir=self._file_dialog_state.last_path if self._file_dialog_state else "",
        )
        if not instance_folder_location:
            return

        test_controller = InstanceController(
            self.settings.instances[self.settings.current_instance]
        )
        test_controller.instance.instance_folder_override = instance_folder_location
        is_valid, error_msg = test_controller.validate_instance_folder_override()

        if not is_valid:
            show_warning(
                title="Invalid Instance Folder",
                text="Cannot use selected folder as instance location.",
                information=error_msg,
            )
            return

        self.settings.instances[
            self.settings.current_instance
        ].instance_folder_override = instance_folder_location
        self.dialog.instance_folder_location.setText(instance_folder_location)
        if self._file_dialog_state:
            self._file_dialog_state.last_path = str(
                Path(instance_folder_location).parent
            )
        self.settings.save()

    @Slot()
    def _on_instance_folder_clear(self) -> None:
        """Clear custom instance folder and use default location."""
        if self.settings.current_instance != DEFAULT_INSTANCE_NAME:
            show_warning(
                title="Cannot Modify Instance Folder",
                text="Only the Default instance can have a custom folder location.",
                information="Custom instance folder location is managed by the Default instance.",
            )
            return

        self.settings.instances[
            self.settings.current_instance
        ].instance_folder_override = ""
        self.dialog.instance_folder_location.setText("")
        self.settings.save()

    # --- Validation ---

    def _validate_game_location(self, game_location: str) -> bool:
        """Validate the game location and show a warning if invalid."""
        if not validate_game_executable(game_location):
            QMessageBox.information(
                self.dialog,
                self.dialog.tr("Invalid Game Location"),
                self.dialog.tr(
                    "The selected game folder does not contain a valid RimWorld executable. Please select a valid game location."
                ),
            )
            return False
        return True

    def _validate_config_folder_location(self, config_folder: str) -> bool:
        """Validate the config folder location and show a warning if invalid."""
        if not (Path(config_folder) / "ModsConfig.xml").exists():
            QMessageBox.warning(
                self.dialog,
                self.dialog.tr("Invalid Config Folder"),
                self.dialog.tr(
                    "The selected config folder does not contain ModsConfig.xml. Please select a valid config folder."
                ),
            )
            return False
        return True

    @staticmethod
    def _check_steam_integration_validity(
        steam_client_integration: bool, steam_mods_location: str
    ) -> bool:
        """Check if Steam client integration and Steam mods location are valid."""
        if not steam_client_integration and not steam_mods_location:
            return True
        if steam_client_integration and not steam_mods_location:
            return False
        if steam_mods_location:
            return validate_acf_file_exists(steam_mods_location)
        return True

    def _disable_steam_integration_ui(self) -> None:
        """Clear all Steam integration dependent UI settings."""
        self.dialog.steam_client_integration_checkbox.setChecked(False)
        self.dialog.steam_mods_folder_location.setText("")
        self.dialog.launch_via_steam_protocol_checkbox.setChecked(False)

    def _validate_steam_integration(self) -> bool:
        """Validate Steam client integration and Steam mods location configuration."""
        steam_client_integration = (
            self.dialog.steam_client_integration_checkbox.isChecked()
        )
        steam_mods_location = self.dialog.steam_mods_folder_location.text().strip()

        if not steam_client_integration:
            QMessageBox.warning(
                self.dialog,
                self.dialog.tr("Steam Client Integration Disabled"),
                self.dialog.tr(
                    "Steam client integration is disabled. Steam mods location and Steam protocol launch will be cleared."
                ),
            )
            self.dialog.steam_mods_folder_location.setText("")
            self.dialog.launch_via_steam_protocol_checkbox.setChecked(False)

        is_valid = self._check_steam_integration_validity(
            steam_client_integration, steam_mods_location
        )

        if not is_valid:
            self._disable_steam_integration_ui()

            if steam_client_integration and not steam_mods_location:
                QMessageBox.warning(
                    self.dialog,
                    self.dialog.tr("Steam Mods Location Required"),
                    self.dialog.tr(
                        "Steam client integration requires a Steam mods location to be configured. "
                        "Steam client integration, Steam mods location, and Steam protocol launch have been disabled."
                    ),
                )
            elif steam_mods_location and not validate_acf_file_exists(
                steam_mods_location
            ):
                QMessageBox.warning(
                    self.dialog,
                    self.dialog.tr("Steam Workshop File Not Found"),
                    self.dialog.tr(
                        "The Steam Workshop file 'appworkshop_294100.acf' was not found at the expected location. "
                        "Steam client integration, Steam mods location, and Steam protocol launch have been disabled. "
                        "Please ensure Steam is properly installed and has downloaded RimWorld Workshop data."
                    ),
                )

        return is_valid
