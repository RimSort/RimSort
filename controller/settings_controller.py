import getpass
import os
from os.path import expanduser
from pathlib import Path

from PySide6.QtCore import QObject, Slot, Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox, QApplication
from logger_tt import logger

from model.settings import Settings
from util.system_info import SystemInfo
from view.settings_dialog import SettingsDialog


class SettingsController(QObject):
    """
    Controller class to manage interactions with the `Settings` model.

    The `SettingsController` class provides a clear interface for working with the `Settings` model.
    It ensures that the associated settings model is loaded upon initialization.

    Attributes:
        settings (Settings): The underlying settings model managed by this controller.
        settings_dialog (SettingsDialog): The settings dialog managed by this controller.

    Examples:
        >>> settings_model = Settings()
        >>> controller = SettingsController(settings_model)
        >>> controller.settings.some_property
    """

    def __init__(self, model: Settings, view: SettingsDialog) -> None:
        """
        Initialize the `SettingsController` with the given `Settings` model and `SettingsDialog` view.

        Upon initialization, the provided settings model's `load` method is called to ensure
        that the settings are loaded and available for use. The view is also initialized with values
        from the settings model.

        Args:
            model (Settings): The settings model to be managed by this controller.
            view (SettingsDialog): The settings dialog to be managed by this controller.
        """
        super().__init__()

        self.settings = model
        self.settings.load()

        self.settings_dialog = view

        self._last_file_dialog_path = str(Path.home())

        # Initialize the settings dialog from the settings model

        self._update_view_from_model()

        # Wire up the settings dialog's global buttons

        self.settings_dialog.global_reset_to_defaults_button.clicked.connect(
            self._on_global_reset_to_defaults_button_clicked
        )

        self.settings_dialog.global_cancel_button.clicked.connect(
            self._on_global_cancel_button_clicked
        )

        self.settings_dialog.global_ok_button.clicked.connect(
            self._on_global_ok_button_clicked
        )

        # Wire up the settings dialog's location tab buttons

        self.settings_dialog.game_location_choose_button.clicked.connect(
            self._on_game_location_choose_button_clicked
        )

        self.settings_dialog.config_folder_location_choose_button.clicked.connect(
            self._on_config_folder_location_choose_button_clicked
        )

        self.settings_dialog.steam_mods_folder_location_choose_button.clicked.connect(
            self._on_steam_mods_folder_location_choose_button_clicked
        )

        self.settings_dialog.local_mods_folder_location_choose_button.clicked.connect(
            self._on_local_mods_folder_location_choose_button_clicked
        )

        self.settings_dialog.locations_clear_button.clicked.connect(
            self._on_locations_clear_button_clicked
        )

        self.settings_dialog.locations_autodetect_button.clicked.connect(
            self._on_locations_autodetect_button_clicked
        )

        # Wire up the Databases tab buttons

        self.settings_dialog.community_rules_db_none_radio.clicked.connect(
            self._on_community_rules_db_radio_clicked
        )
        self.settings_dialog.community_rules_db_github_radio.clicked.connect(
            self._on_community_rules_db_radio_clicked
        )
        self.settings_dialog.community_rules_db_local_file_radio.clicked.connect(
            self._on_community_rules_db_radio_clicked
        )

        self.settings_dialog.community_rules_db_local_file_choose_button.clicked.connect(
            self._on_community_rules_db_local_file_choose_button_clicked
        )

        self.settings_dialog.steam_workshop_db_none_radio.clicked.connect(
            self._on_steam_workshop_db_radio_clicked
        )
        self.settings_dialog.steam_workshop_db_github_radio.clicked.connect(
            self._on_steam_workshop_db_radio_clicked
        )
        self.settings_dialog.steam_workshop_db_local_file_radio.clicked.connect(
            self._on_steam_workshop_db_radio_clicked
        )

        self.settings_dialog.steam_workshop_db_local_file_choose_button.clicked.connect(
            self._on_steam_workshop_db_local_file_choose_button_clicked
        )

    def show_settings_dialog(self) -> None:
        """
        Show the settings dialog.
        """
        self._update_view_from_model()
        self.settings_dialog.show()

    def _update_view_from_model(self) -> None:
        """
        Update the view from the settings model.
        """

        # Locations tab

        self.settings_dialog.game_location.setText(self.settings.game_folder)
        self.settings_dialog.config_folder_location.setText(self.settings.config_folder)
        self.settings_dialog.steam_mods_folder_location.setText(
            self.settings.workshop_folder
        )
        self.settings_dialog.local_mods_folder_location.setText(
            self.settings.local_folder
        )

        # Databases tab

        if self.settings.external_community_rules_metadata_source == "None":
            self.settings_dialog.community_rules_db_none_radio.setChecked(True)
            self.settings_dialog.community_rules_db_github_url.setEnabled(False)
            self.settings_dialog.community_rules_db_github_url_download_button.setEnabled(
                False
            )
            self.settings_dialog.community_rules_db_local_file.setEnabled(False)
            self.settings_dialog.community_rules_db_local_file_choose_button.setEnabled(
                False
            )
        elif (
            self.settings.external_community_rules_metadata_source
            == "Configured git repository"
        ):
            self.settings_dialog.community_rules_db_github_radio.setChecked(True)
            self.settings_dialog.community_rules_db_github_url.setEnabled(True)
            self.settings_dialog.community_rules_db_github_url_download_button.setEnabled(
                True
            )
            self.settings_dialog.community_rules_db_local_file.setEnabled(False)
            self.settings_dialog.community_rules_db_local_file_choose_button.setEnabled(
                False
            )
        elif (
            self.settings.external_community_rules_metadata_source
            == "Configured file path"
        ):
            self.settings_dialog.community_rules_db_local_file_radio.setChecked(True)
            self.settings_dialog.community_rules_db_github_url.setEnabled(False)
            self.settings_dialog.community_rules_db_github_url_download_button.setEnabled(
                False
            )
            self.settings_dialog.community_rules_db_local_file.setEnabled(True)
            self.settings_dialog.community_rules_db_local_file_choose_button.setEnabled(
                True
            )

        self.settings_dialog.community_rules_db_local_file.setText(
            self.settings.external_community_rules_file_path
        )

        self.settings_dialog.community_rules_db_github_url.setText(
            self.settings.external_community_rules_repo
        )

        if self.settings.external_steam_metadata_source == "None":
            self.settings_dialog.steam_workshop_db_none_radio.setChecked(True)
            self.settings_dialog.steam_workshop_db_github_url.setEnabled(False)
            self.settings_dialog.steam_workshop_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.steam_workshop_db_local_file.setEnabled(False)
            self.settings_dialog.steam_workshop_db_local_file_choose_button.setEnabled(
                False
            )
        elif (
            self.settings.external_steam_metadata_source == "Configured git repository"
        ):
            self.settings_dialog.steam_workshop_db_github_radio.setChecked(True)
            self.settings_dialog.steam_workshop_db_github_url.setEnabled(True)
            self.settings_dialog.steam_workshop_db_github_download_button.setEnabled(
                True
            )
            self.settings_dialog.steam_workshop_db_local_file.setEnabled(False)
            self.settings_dialog.steam_workshop_db_local_file_choose_button.setEnabled(
                False
            )
        elif self.settings.external_steam_metadata_source == "Configured file path":
            self.settings_dialog.steam_workshop_db_local_file_radio.setChecked(True)
            self.settings_dialog.steam_workshop_db_github_url.setEnabled(False)
            self.settings_dialog.steam_workshop_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.steam_workshop_db_local_file.setEnabled(True)
            self.settings_dialog.steam_workshop_db_local_file_choose_button.setEnabled(
                True
            )

        self.settings_dialog.steam_workshop_db_local_file.setText(
            self.settings.external_steam_metadata_file_path
        )

        self.settings_dialog.steam_workshop_db_github_url.setText(
            self.settings.external_steam_metadata_repo
        )

    def _update_model_from_view(self) -> None:
        """
        Update the settings model from the view.
        """

        # Locations tab

        self.settings.game_folder = self.settings_dialog.game_location.text()
        self.settings.config_folder = self.settings_dialog.config_folder_location.text()
        self.settings.workshop_folder = (
            self.settings_dialog.steam_mods_folder_location.text()
        )
        self.settings.local_folder = (
            self.settings_dialog.local_mods_folder_location.text()
        )

        # Databases tab

        if self.settings_dialog.community_rules_db_none_radio.isChecked():
            self.settings.external_community_rules_metadata_source = "None"
        elif self.settings_dialog.community_rules_db_local_file_radio.isChecked():
            self.settings.external_community_rules_metadata_source = (
                "Configured file path"
            )
        elif self.settings_dialog.community_rules_db_github_radio.isChecked():
            self.settings.external_community_rules_metadata_source = (
                "Configured git repository"
            )

        self.settings.external_community_rules_file_path = (
            self.settings_dialog.community_rules_db_local_file.text()
        )

        self.settings.external_community_rules_repo = (
            self.settings_dialog.community_rules_db_github_url.text()
        )

        if self.settings_dialog.steam_workshop_db_none_radio.isChecked():
            self.settings.external_steam_metadata_source = "None"
        elif self.settings_dialog.steam_workshop_db_local_file_radio.isChecked():
            self.settings.external_steam_metadata_source = "Configured file path"
        elif self.settings_dialog.steam_workshop_db_github_radio.isChecked():
            self.settings.external_steam_metadata_source = "Configured git repository"

        self.settings.external_steam_metadata_repo = (
            self.settings_dialog.steam_workshop_db_github_url.text()
        )

        self.settings.external_steam_metadata_file_path = (
            self.settings_dialog.steam_workshop_db_local_file.text()
        )

    @Slot()
    def _on_global_reset_to_defaults_button_clicked(self) -> None:
        """
        Reset the settings to their default values.
        """
        message_box = QMessageBox(self.settings_dialog)
        message_box.setWindowTitle("Reset to defaults")
        message_box.setText(
            "Are you sure you want to reset all settings to their default values?"
        )
        message_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        message_box.setDefaultButton(QMessageBox.StandardButton.No)
        message_box.setWindowModality(Qt.WindowModality.WindowModal)

        pressed_button = message_box.exec()
        if pressed_button == QMessageBox.StandardButton.No:
            return

        self.settings.apply_default_settings()
        self._update_view_from_model()

    @Slot()
    def _on_global_cancel_button_clicked(self) -> None:
        """
        Close the settings dialog without saving the settings.
        """
        self.settings_dialog.close()
        self._update_view_from_model()

    @Slot()
    def _on_global_ok_button_clicked(self) -> None:
        """
        Close the settings dialog, update the model from the view, and save the settings..
        """
        self.settings_dialog.close()
        self._update_model_from_view()
        self.settings.save()

    @Slot()
    def _on_game_location_choose_button_clicked(self) -> None:
        game_location, _ = QFileDialog.getOpenFileName(
            parent=self.settings_dialog,
            dir=str(self._last_file_dialog_path),
        )
        if game_location == "":
            return
        game_location_path = Path(game_location).resolve()
        self.settings.game_location = game_location
        self.settings_dialog.game_location.setText(self.settings.game_location)
        self._last_file_dialog_path = str(game_location_path.parent)

    @Slot()
    def _on_config_folder_location_choose_button_clicked(self) -> None:
        config_folder_location = QFileDialog.getExistingDirectory(
            parent=self.settings_dialog,
            dir=str(self._last_file_dialog_path),
        )
        if config_folder_location == "":
            return
        self.settings.config_folder = config_folder_location
        self.settings_dialog.config_folder_location.setText(self.settings.config_folder)
        self._last_file_dialog_path = config_folder_location

    @Slot()
    def _on_steam_mods_folder_location_choose_button_clicked(self) -> None:
        steam_mods_folder_location = QFileDialog.getExistingDirectory(
            parent=self.settings_dialog,
            dir=str(self._last_file_dialog_path),
        )
        if steam_mods_folder_location == "":
            return
        self.settings.workshop_folder = steam_mods_folder_location
        self.settings_dialog.steam_mods_folder_location.setText(
            self.settings.workshop_folder
        )
        self._last_file_dialog_path = steam_mods_folder_location

    @Slot()
    def _on_local_mods_folder_location_choose_button_clicked(self) -> None:
        local_mods_folder_location = QFileDialog.getExistingDirectory(
            parent=self.settings_dialog,
            dir=str(self._last_file_dialog_path),
        )
        if local_mods_folder_location == "":
            return
        self.settings.local_folder = local_mods_folder_location
        self.settings_dialog.local_mods_folder_location.setText(
            self.settings.local_folder
        )
        self._last_file_dialog_path = local_mods_folder_location

    @Slot()
    def _on_locations_clear_button_clicked(self) -> None:
        """
        Clear the settings dialog's location fields.
        """
        message_box = QMessageBox(self.settings_dialog)
        message_box.setWindowTitle("Clear all locations")
        message_box.setText("Are you sure you want to clear all locations?")
        message_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        message_box.setDefaultButton(QMessageBox.StandardButton.No)
        message_box.setWindowModality(Qt.WindowModality.WindowModal)

        pressed_button = message_box.exec()
        if pressed_button == QMessageBox.StandardButton.No:
            return

        self.settings_dialog.game_location.setText("")
        self.settings_dialog.config_folder_location.setText("")
        self.settings_dialog.steam_mods_folder_location.setText("")
        self.settings_dialog.local_mods_folder_location.setText("")

    @Slot()
    def _on_locations_autodetect_button_clicked(self) -> None:
        """
        This function tries to autodetect Rimworld paths based on the
        defaults typically found per-platform, and set them in the client.
        """
        logger.info("USER ACTION: starting autodetect paths")
        os_paths = []
        darwin_paths = [
            f"/Users/{getpass.getuser()}/Library/Application Support/Steam/steamapps/common/Rimworld/RimworldMac.app/",
            f"/Users/{getpass.getuser()}/Library/Application Support/Rimworld/Config/",
            f"/Users/{getpass.getuser()}/Library/Application Support/Steam/steamapps/workshop/content/294100/",
        ]
        # If on mac and the steam path doesn't exist, try the default path
        if not (os.path.exists(darwin_paths[0])):
            darwin_paths[0] = f"/Applications/RimWorld.app/"
        if os.path.exists("{expanduser('~')}/.steam/debian-installation"):
            linux_paths = [
                f"{expanduser('~')}/.steam/debian-installation/steamapps/common/RimWorld",
                f"{expanduser('~')}/.config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/Config",
                f"{expanduser('~')}/.steam/debian-installation/steamapps/workshop/content/294100",
            ]
        else:
            linux_paths = [  # TODO detect the path and not having hardcoded thing
                f"{expanduser('~')}/.steam/steam/steamapps/common/RimWorld",
                f"{expanduser('~')}/.config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/Config",
                f"{expanduser('~')}/.steam/steam/steamapps/workshop/content/294100",
            ]
        windows_paths = [
            str(
                Path(
                    os.path.join(
                        "C:" + os.sep,
                        "Program Files (x86)",
                        "Steam",
                        "steamapps",
                        "common",
                        "Rimworld",
                    )
                ).resolve()
            ),
            str(
                Path(
                    os.path.join(
                        "C:" + os.sep,
                        "Users",
                        getpass.getuser(),
                        "AppData",
                        "LocalLow",
                        "Ludeon Studios",
                        "RimWorld by Ludeon Studios",
                        "Config",
                    )
                ).resolve()
            ),
            str(
                Path(
                    os.path.join(
                        "C:" + os.sep,
                        "Program Files (x86)",
                        "Steam",
                        "steamapps",
                        "workshop",
                        "content",
                        "294100",
                    )
                ).resolve()
            ),
        ]

        if SystemInfo().operating_system == SystemInfo.OperatingSystem.MACOS:
            os_paths = darwin_paths
            logger.info(f"Running on MacOS with the following paths: {os_paths}")
        elif SystemInfo().operating_system == SystemInfo.OperatingSystem.LINUX:
            os_paths = linux_paths
            logger.info(f"Running on Linux with the following paths: {os_paths}")
        elif SystemInfo().operating_system == SystemInfo.OperatingSystem.WINDOWS:
            os_paths = windows_paths
            logger.info(f"Running on Windows with the following paths: {os_paths}")
        else:
            logger.error("Attempting to autodetect paths on an unknown system.")

        # If the game folder exists...
        if os.path.exists(os_paths[0]):
            logger.info(f"Autodetected game folder path exists: {os_paths[0]}")
            if not self.settings_dialog.game_location.text():
                logger.info(
                    "No value set currently for game folder. Overwriting with autodetected path"
                )
                self.settings_dialog.game_location.setText(os_paths[0])
            else:
                logger.info("Value already set for game folder. Passing")
        else:
            logger.warning(
                f"Autodetected game folder path does not exist: {os_paths[0]}"
            )

        # If the config folder exists...
        if os.path.exists(os_paths[1]):
            logger.info(f"Autodetected config folder path exists: {os_paths[1]}")
            if not self.settings_dialog.config_folder_location.text():
                logger.info(
                    "No value set currently for config folder. Overwriting with autodetected path"
                )
                self.settings_dialog.config_folder_location.setText(os_paths[1])
            else:
                logger.info("Value already set for config folder. Passing")
        else:
            logger.warning(
                f"Autodetected config folder path does not exist: {os_paths[1]}"
            )

        # If the workshop folder exists
        if os.path.exists(os_paths[2]):
            logger.info(f"Autodetected workshop folder path exists: {os_paths[2]}")
            if not self.settings_dialog.steam_mods_folder_location.text():
                logger.info(
                    "No value set currently for workshop folder. Overwriting with autodetected path"
                )
                self.settings_dialog.steam_mods_folder_location.setText(os_paths[2])
            else:
                logger.info("Value already set for workshop folder. Passing")
        else:
            logger.warning(
                f"Autodetected workshop folder path does not exist: {os_paths[2]}"
            )

        # Checking for an existing Rimworld/Mods folder
        rimworld_mods_path = str(Path(os.path.join(os_paths[0], "Mods")).resolve())
        if os.path.exists(rimworld_mods_path):
            logger.info(
                f"Autodetected local mods folder path exists: {rimworld_mods_path}"
            )
            if not self.settings_dialog.local_mods_folder_location.text():
                logger.info(
                    "No value set currently for local mods folder. Overwriting with autodetected path"
                )
                self.settings_dialog.local_mods_folder_location.setText(
                    rimworld_mods_path
                )
            else:
                logger.info("Value already set for local mods folder. Passing")
        else:
            logger.warning(
                f"Autodetected game folder path does not exist: {rimworld_mods_path}"
            )

    @Slot()
    def _on_community_rules_db_radio_clicked(self, checked: bool) -> None:
        if (
            self.sender() == self.settings_dialog.community_rules_db_none_radio
            and checked
        ):
            self.settings_dialog.community_rules_db_github_url.setEnabled(False)
            self.settings_dialog.community_rules_db_github_url_download_button.setEnabled(
                False
            )
            self.settings_dialog.community_rules_db_local_file.setEnabled(False)
            self.settings_dialog.community_rules_db_local_file_choose_button.setEnabled(
                False
            )
            app_instance = QApplication.instance()
            if isinstance(app_instance, QApplication):
                focused_widget = app_instance.focusWidget()
                if focused_widget:
                    focused_widget.clearFocus()
            return

        if (
            self.sender() == self.settings_dialog.community_rules_db_github_radio
            and checked
        ):
            self.settings_dialog.community_rules_db_github_url.setEnabled(True)
            self.settings_dialog.community_rules_db_github_url_download_button.setEnabled(
                True
            )
            self.settings_dialog.community_rules_db_local_file.setEnabled(False)
            self.settings_dialog.community_rules_db_local_file_choose_button.setEnabled(
                False
            )
            self.settings_dialog.community_rules_db_github_url.setFocus()
            return

        if (
            self.sender() == self.settings_dialog.community_rules_db_local_file_radio
            and checked
        ):
            self.settings_dialog.community_rules_db_github_url.setEnabled(False)
            self.settings_dialog.community_rules_db_github_url_download_button.setEnabled(
                False
            )
            self.settings_dialog.community_rules_db_local_file.setEnabled(True)
            self.settings_dialog.community_rules_db_local_file_choose_button.setEnabled(
                True
            )
            self.settings_dialog.community_rules_db_local_file.setFocus()
            return

    @Slot()
    def _on_community_rules_db_local_file_choose_button_clicked(self) -> None:
        community_rules_db_location, _ = QFileDialog.getOpenFileName(
            parent=self.settings_dialog,
            dir=str(self._last_file_dialog_path),
        )
        if community_rules_db_location == "":
            return
        self.settings_dialog.community_rules_db_local_file.setText(
            community_rules_db_location
        )
        self._last_file_dialog_path = str(Path(community_rules_db_location).parent)

    @Slot()
    def _on_steam_workshop_db_radio_clicked(self, checked: bool) -> None:
        if (
            self.sender() == self.settings_dialog.steam_workshop_db_none_radio
            and checked
        ):
            self.settings_dialog.steam_workshop_db_github_url.setEnabled(False)
            self.settings_dialog.steam_workshop_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.steam_workshop_db_local_file.setEnabled(False)
            self.settings_dialog.steam_workshop_db_local_file_choose_button.setEnabled(
                False
            )
            app_instance = QApplication.instance()
            if isinstance(app_instance, QApplication):
                focused_widget = app_instance.focusWidget()
                if focused_widget:
                    focused_widget.clearFocus()
            return

        if (
            self.sender() == self.settings_dialog.steam_workshop_db_github_radio
            and checked
        ):
            self.settings_dialog.steam_workshop_db_github_url.setEnabled(True)
            self.settings_dialog.steam_workshop_db_github_download_button.setEnabled(
                True
            )
            self.settings_dialog.steam_workshop_db_local_file.setEnabled(False)
            self.settings_dialog.steam_workshop_db_local_file_choose_button.setEnabled(
                False
            )
            self.settings_dialog.steam_workshop_db_github_url.setFocus()
            return

        if (
            self.sender() == self.settings_dialog.steam_workshop_db_local_file_radio
            and checked
        ):
            self.settings_dialog.steam_workshop_db_github_url.setEnabled(False)
            self.settings_dialog.steam_workshop_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.steam_workshop_db_local_file.setEnabled(True)
            self.settings_dialog.steam_workshop_db_local_file_choose_button.setEnabled(
                True
            )
            self.settings_dialog.steam_workshop_db_local_file.setFocus()
            return

    @Slot()
    def _on_steam_workshop_db_local_file_choose_button_clicked(self) -> None:
        steam_workshop_db_location, _ = QFileDialog.getOpenFileName(
            parent=self.settings_dialog,
            dir=str(self._last_file_dialog_path),
        )
        if steam_workshop_db_location == "":
            return
        self.settings_dialog.steam_workshop_db_local_file.setText(
            steam_workshop_db_location
        )
        self._last_file_dialog_path = str(Path(steam_workshop_db_location).parent)
