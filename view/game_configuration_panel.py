import getpass
import json
from logging import INFO
from logger_tt import logger
import os
from pathlib import Path
import platform
import webbrowser
from functools import partial
from os.path import expanduser
from typing import Any, Dict

from PySide6.QtCore import QObject, QPoint, QSize, QStandardPaths, Qt, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
)

from controller.settings_controller import SettingsController
from model.dialogue import *
from model.multibutton import MultiButton
from util.app_info import AppInfo
from util.constants import DEFAULT_SETTINGS, DEFAULT_USER_RULES
from util.event_bus import EventBus
from util.generic import *
from window.settings_panel import SettingsPanel


class GameConfiguration(QObject):
    """
    This class controls the layout and functionality of the top-most
    panel of the GUI, containing the paths to the ModsConfig.xml folder,
    workshop folder, and game executable folder. It is also responsible
    for initializing the storage feature, getting paths data out of
    the storage feature, and allowing for setting paths and writing those
    paths to the persistent storage.

    It Subclasses QObject to allow emitting signals.
    """

    _instance: Optional["GameConfiguration"] = None

    # Signal emitter for this class
    configuration_signal = Signal(str)

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(GameConfiguration, cls).__new__(cls)
        return cls._instance

    def __init__(
        self,
        RIMSORT_VERSION: str,
        settings_controller: SettingsController = None,
        DEBUG_MODE=None,
    ) -> None:
        """
        Initialize the game configuration.
        """
        if not hasattr(self, "initialized"):
            super(GameConfiguration, self).__init__()
            logger.debug("Initializing GameConfiguration")

            self.settings_controller = settings_controller

            self.debug_mode = DEBUG_MODE
            self.rimsort_version = RIMSORT_VERSION
            self.system_name = platform.system()

            self.storage_path = QStandardPaths.writableLocation(
                QStandardPaths.AppLocalDataLocation
            )
            self.lock_icon_path = str(
                Path(
                    os.path.join(os.path.dirname(__file__), "../data/lock.png")
                ).resolve()
            )
            self.unlock_icon_path = str(
                Path(
                    os.path.join(os.path.dirname(__file__), "../data/unlock.png")
                ).resolve()
            )

            # INITIALIZE WIDGETS / FEATURES
            self._initialize_settings_panel()
            self._initialize_storage()

            # SIGNALS AND SLOTS

            # General Preferences
            self.settings_panel.logger_debug_checkbox.setChecked(self.debug_mode)
            self.settings_panel.watchdog_checkbox.setChecked(
                self.settings_controller.settings.watchdog_toggle
            )
            self.settings_panel.mod_type_filter_checkbox.setChecked(
                self.settings_controller.settings.mod_type_filter_toggle
            )
            self.settings_panel.duplicate_mods_checkbox.setChecked(
                self.settings_controller.settings.duplicate_mods_warning
            )
            self.settings_panel.steam_mods_update_checkbox.setChecked(
                self.settings_controller.settings.steam_mods_update_check
            )
            self.settings_panel.try_download_missing_mods_checkbox.setChecked(
                self.settings_controller.settings.try_download_missing_mods
            )

            # DQ GetAppDependencies
            self.settings_panel.build_steam_database_dlc_data_checkbox.setChecked(
                self.settings_controller.settings.build_steam_database_dlc_data
            )

            # DB Builder update toggle
            self.settings_panel.build_steam_database_update_checkbox.setChecked(
                self.settings_controller.settings.build_steam_database_update_toggle
            )

            # SteamCMD
            self.settings_panel.steamcmd_validate_downloads_checkbox.setChecked(
                self.settings_controller.settings.steamcmd_validate_downloads
            )

            # todds
            self.settings_panel.todds_active_mods_target_checkbox.setChecked(
                self.settings_controller.settings.todds_active_mods_target
            )

            self.settings_panel.todds_dry_run_checkbox.setChecked(
                self.settings_controller.settings.todds_dry_run
            )

            self.settings_panel.todds_overwrite_checkbox.setChecked(
                self.settings_controller.settings.todds_overwrite
            )

            logger.debug("Finished GameConfiguration initialization")
            self.initialized = True

    @classmethod
    def instance(cls, *args: Any, **kwargs: Any) -> "GameConfiguration":
        if cls._instance is None:
            cls._instance = cls(*args, **kwargs)
        elif args or kwargs:
            raise ValueError("GameConfiguration instance has already been initialized.")
        return cls._instance

    def _initialize_settings_panel(self) -> None:
        """
        Initializes the app's settings pop up dialog, but does
        not show it. The settings panel allows the user to
        tweak certain settings of RimSort, like which sorting
        algorithm to use, or what theme to use.
        Window modality is set so the user cannot interact with
        the rest of the application while the settings panel is open.
        """
        self.settings_panel = SettingsPanel(self.storage_path)
        self.settings_panel.setWindowModality(Qt.ApplicationModal)
        self.settings_panel.finished.connect(self._on_settings_close)

    def _initialize_storage(self) -> None:
        """
        Initialize the app's storage feature.
        If the storage path or settings.json file do not exist,
        create them. If they do exist, set the path widgets
        to have paths written on the settings.json.
        """
        logger.info("Initializing storage")
        logger.info(f"Determined storage path: {self.storage_path}")
        # Always check for storage path, create in OS-specific "app data" if it doesn't exist
        if not os.path.exists(self.storage_path):
            logger.info(f"Storage path [{self.storage_path}] does not exist")
            information = (
                "It looks like you may be running RimSort for the first time! RimSort stores some client "
                + f"information in this directory:\n[{self.storage_path}].\n"
                + "It doesn't look like this directory exists, so we'll make it for you now."
            )
            show_information(
                title="Welcome", text="Welcome to RimSort!", information=information
            )
            logger.info("Making storage directory")
            os.makedirs(self.storage_path)
        # Always check for dbs/userRules.json path, create if it doesn't exist
        self.user_rules_file_path = str(
            Path(os.path.join(AppInfo().databases_folder, "userRules.json")).resolve()
        )
        if not os.path.exists(self.user_rules_file_path):
            initial_rules_db = DEFAULT_USER_RULES
            with open(self.user_rules_file_path, "w", encoding="utf-8") as output:
                json.dump(initial_rules_db, output, indent=4)

        # sorting algorithm
        self.settings_panel.sorting_algorithm_cb.setCurrentText(
            self.settings_controller.settings.sorting_algorithm
        )

        # metadata
        self.settings_panel.external_steam_metadata_multibutton.main_action.setCurrentText(
            self.settings_controller.settings.external_steam_metadata_source
        )
        self.settings_panel.external_community_rules_metadata_multibutton.main_action.setCurrentText(
            self.settings_controller.settings.external_community_rules_metadata_source
        )

        # db builder
        if self.settings_controller.settings.db_builder_include == "no_local":
            self.settings_panel.build_steam_database_include_cb.setCurrentText("No")
        if self.settings_controller.settings.db_builder_include == "all_mods":
            self.settings_panel.build_steam_database_include_cb.setCurrentText("Yes")

        # steamcmd
        steamcmd_install_path = Path(
            self.settings_controller.settings.steamcmd_install_path
        )
        if not steamcmd_install_path.exists():
            logger.warning(
                f"Configured steamcmd prefix does not exist. Creating new steamcmd prefix at: "
                f"{steamcmd_install_path}"
            )  # This shouldn't be happening, but we check it anyways.
            steamcmd_install_path.mkdir(parents=True)

        # todds
        if self.settings_controller.settings.todds_preset == "optimized":
            self.settings_panel.todds_presets_cb.setCurrentText(
                "Optimized - Recommended for RimWorld"
            )

        logger.info("Finished storage initialization")

    def _on_settings_close(self) -> None:
        logger.info(
            "Settings panel closed, updating persistent storage for these options..."
        )

        # Close the window
        self.settings_panel.close()

        # Determine configurations
        # watchdog toggle
        self.settings_controller.settings.watchdog_toggle = (
            self.settings_panel.watchdog_checkbox.isChecked()
        )

        # mod type filter toggle mods toggle
        self.settings_controller.settings.mod_type_filter_toggle = (
            self.settings_panel.mod_type_filter_checkbox.isChecked()
        )

        # duplicate mods check toggle
        self.settings_controller.settings.duplicate_mods_warning = (
            self.settings_panel.duplicate_mods_checkbox.isChecked()
        )

        # steam mods update check toggle
        self.settings_controller.settings.steam_mods_update_check = (
            self.settings_panel.steam_mods_update_checkbox.isChecked()
        )

        # db builder mode
        if "No" in self.settings_panel.build_steam_database_include_cb.currentText():
            self.settings_controller.settings.db_builder_include = "no_local"
        elif "Yes" in self.settings_panel.build_steam_database_include_cb.currentText():
            self.settings_controller.settings.db_builder_include = "all_mods"

        # dq getappdependencies toggle
        self.settings_controller.settings.build_steam_database_dlc_data = (
            self.settings_panel.build_steam_database_dlc_data_checkbox.isChecked()
        )

        # db builder update toggle
        self.settings_controller.settings.build_steam_database_update_toggle = (
            self.settings_panel.build_steam_database_update_checkbox.isChecked()
        )

        # steamcmd validate downloads toggle
        self.settings_controller.settings.steamcmd_validate_downloads = (
            self.settings_panel.steamcmd_validate_downloads_checkbox.isChecked()
        )

        # todds preset
        if (
            "Optimized - Recommended for RimWorld"
            in self.settings_panel.todds_presets_cb.currentText()
        ):
            self.settings_controller.settings.todds_preset = "optimized"

        # todds active mods target
        self.settings_controller.settings.todds_active_mods_target = (
            self.settings_panel.todds_active_mods_target_checkbox.isChecked()
        )

        # todds dry run
        self.settings_controller.settings.todds_dry_run = (
            self.settings_panel.todds_dry_run_checkbox.isChecked()
        )

        # todds overwrite textures
        self.settings_controller.settings.todds_overwrite = (
            self.settings_panel.todds_overwrite_checkbox.isChecked()
        )

        self.settings_controller.settings.try_download_missing_mods = (
            self.settings_panel.try_download_missing_mods_checkbox.isChecked()
        )

        self.settings_controller.settings.sorting_algorithm = (
            self.settings_panel.sorting_algorithm_cb.currentText()
        )
        self.settings_controller.settings.external_steam_metadata_source = (
            self.settings_panel.external_steam_metadata_multibutton.main_action.currentText()
        )
        self.settings_controller.settings.external_community_rules_metadata_source = (
            self.settings_panel.external_community_rules_metadata_multibutton.main_action.currentText()
        )

        self.settings_controller.settings.save()

    def _open_settings_panel(self) -> None:
        """
        Opens the settings panel (as a modal window), blocking
        access to the rest of the application until it is closed.
        Do NOT use exec here: https://doc.qt.io/qt-6/qdialog.html#exec
        For some reason, open() does not work for making this a modal
        window.
        """
        logger.info("USER ACTION: opening settings panel")
        self.settings_panel.show()

    # PATHS

    def check_if_essential_paths_are_set(self) -> bool:
        """
        When the user starts the app for the first time, none
        of the paths will be set. We should check for this and
        not throw a fatal error trying to load mods until the
        user has had a chance to set paths.
        """
        game_folder_path = self.settings_controller.settings.game_folder
        config_folder_path = self.settings_controller.settings.config_folder
        logger.debug(f"Game folder: {game_folder_path}")
        logger.debug(f"Config folder: {config_folder_path}")
        if not game_folder_path or not config_folder_path:
            logger.warning("Essential path(s) not set!")
            show_warning(
                text="Essential path(s) not set!",
                information=(
                    "RimSort requires, at the minimum, for the game install folder and the "
                    "config folder paths to be set. Please set both these either manually "
                    "or by using the AutoDetect functionality."
                ),
            )
            return False
        if not os.path.exists(game_folder_path) or not os.path.exists(
            config_folder_path
        ):
            logger.warning("Essential path(s) invalid!")
            show_warning(
                text="Essential path(s) are invalid!",
                information=(
                    "RimSort has detected that the game install folder path or the "
                    "config folder path is invalid. Please check that both of these path(s) "
                    "reference folders that actually exist at the specified location."
                ),
            )
            return False
        logger.info("Essential paths set!")
        return True
