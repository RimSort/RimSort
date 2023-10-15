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

from PySide6.QtCore import QObject, QPoint, QSize, QStandardPaths, Qt, Signal
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

from model.dialogue import *
from util.constants import DEFAULT_SETTINGS, DEFAULT_USER_RULES
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

    def __init__(self, RIMSORT_VERSION: str, DEBUG_MODE=None) -> None:
        """
        Initialize the game configuration.
        """
        if not hasattr(self, "initialized"):
            super(GameConfiguration, self).__init__()
            logger.debug("Initializing GameConfiguration")

            self.debug_mode = DEBUG_MODE
            self.rimsort_version = RIMSORT_VERSION
            self.system_name = platform.system()

            self.storage_path = QStandardPaths.writableLocation(
                QStandardPaths.AppLocalDataLocation
            )
            self.dbs_path = "."
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
            self.show_folder_rows = False

            # RUN ARGUMENTS
            self.run_arguments = []

            # GITHUB IDENTITY
            self.github_username = ""
            self.github_token = ""

            # DB FILE PATHS
            self.steam_db_file_path = ""
            self.community_rules_file_path = ""

            # DB REPOS
            self.steam_db_repo = ""
            self.community_rules_repo = ""

            # STEAM APIKEY
            self.steam_apikey = ""

            # DATABASE EXPIRY
            self.database_expiry = 604800

            # WATCHDOG TOGGLE
            self.watchdog_toggle = False

            # MOD TYPE FILTER MODS TOGGLE
            self.mod_type_filter_toggle = False

            # DUPE MODS WARNING TOGGLE
            self.duplicate_mods_warning_toggle = False

            # STEAM MODS UPDATE CHECK TOGGLE
            self.steam_mods_update_check_toggle = False

            # TRY TO DOWNLOAD MISSING MODS TOGGLE
            self.try_download_missing_mods_toggle = False

            # DB BUILDER MODE
            self.db_builder_include = "all_mods"

            # DQ GETAPPDEPENDENCIES TOGGLE
            self.build_steam_database_dlc_data_toggle = False

            # DB BUILDER UPDATE TOGGLE
            self.build_steam_database_update_toggle = False

            # STEAMCMD INSTALL PATH
            self.steamcmd_install_path = ""

            # STEAMCMD VALIDATE DOWNLOADS TOGGLE
            self.steamcmd_validate_downloads_toggle = False

            # TODDS PRESET
            self.todds_preset = "optimized"

            # TODDS ACTIVE MODS TARGET TOGGLE
            self.todds_active_mods_target_toggle = False

            # TODDS DRY RUN TOGGLE
            self.todds_dry_run_toggle = False

            # TODDS OVERWRITE TOGGLE
            self.todds_overwrite_toggle = False

            # BASE LAYOUT
            self._panel = QVBoxLayout()
            # Represents spacing between edge and layout
            # Set to 0 on the bottom to maintain consistent spacing to the main content panel
            self._panel.setContentsMargins(7, 7, 7, 0)

            # CONTAINER LAYOUTS
            self.client_settings_row = QHBoxLayout()
            self.client_settings_row.setContentsMargins(0, 0, 0, 2)
            self.client_settings_row.setSpacing(0)
            self.game_folder_row = QHBoxLayout()
            self.game_folder_row.setContentsMargins(0, 0, 0, 2)
            self.game_folder_row.setSpacing(0)
            self.config_folder_row = QHBoxLayout()
            self.config_folder_row.setContentsMargins(0, 0, 0, 2)
            self.config_folder_row.setSpacing(0)
            self.workshop_folder_row = QHBoxLayout()
            self.workshop_folder_row.setContentsMargins(0, 0, 0, 2)
            self.workshop_folder_row.setSpacing(0)
            self.local_folder_row = QHBoxLayout()
            self.local_folder_row.setContentsMargins(0, 0, 0, 0)
            self.local_folder_row.setSpacing(0)

            # INSTANTIATE WIDGETS
            self.auto_detect_paths_button = QPushButton("Autodetect paths")
            self.auto_detect_paths_button.clicked.connect(
                self.autodetect_paths_by_platform
            )
            self.auto_detect_paths_button.setObjectName("LeftButton")
            self.client_settings_button = QPushButton("Settings")
            self.client_settings_button.clicked.connect(self._open_settings_panel)
            self.client_settings_button.setObjectName("LeftButton")
            self.hide_show_folder_rows_button = QPushButton()
            self.hide_show_folder_rows_button.clicked.connect(self.__toggle_folder_rows)
            self.check_for_updates_action = QAction("Check for update on startup")
            self.check_for_updates_action.setCheckable(True)
            self.check_for_updates_button = QPushButton("Check for update")
            self.check_for_updates_button.setToolTip(
                "Right-click to configure automatic update check"
            )
            self.check_for_updates_button.clicked.connect(
                partial(self.configuration_signal.emit, "check_for_update")
            )
            self.check_for_updates_button.setObjectName("RightButton")
            self.check_for_updates_button.setContextMenuPolicy(Qt.CustomContextMenu)
            self.check_for_updates_button.customContextMenuRequested.connect(
                self.checkForUpdateBtnContextMenuEvent
            )
            self.game_version_label = QLabel("Game version:")
            self.game_version_label.setObjectName("gameVersion")
            self.game_version_line = QLineEdit()
            self.game_version_line.setDisabled(True)
            self.game_version_line.setPlaceholderText("Unknown")
            self.game_version_line.setReadOnly(True)
            self.wiki_button = QPushButton("Wiki")
            self.wiki_button.clicked.connect(
                partial(open_url_browser, "https://github.com/RimSort/RimSort/wiki")
            )
            self.wiki_button.setObjectName("RightButton")

            if self.system_name == "Darwin":
                self.game_folder_open_button = QPushButton("Game App")
                self.game_folder_open_button.setToolTip("Open Game Folder")
            else:
                self.game_folder_open_button = QPushButton("Game folder")
                self.game_folder_open_button.setToolTip(
                    "Open the game installation directory"
                )
            self.game_folder_open_button.setObjectName("LeftButton")
            self.game_folder_line = QLineEdit()
            self.game_folder_open_button.clicked.connect(
                partial(self.open_directory, self.game_folder_line.text)
            )
            self.game_folder_line.setReadOnly(True)
            self.game_folder_line.setClearButtonEnabled(True)
            self.game_folder_line_clear_button = self.game_folder_line.findChild(
                QToolButton
            )
            self.game_folder_line_clear_button.setEnabled(True)
            self.game_folder_line_clear_button.clicked.connect(
                self.clear_game_folder_line
            )
            self.game_folder_line.setPlaceholderText("Unconfigured")
            self.game_folder_line.setToolTip(
                "The game installation directory contains the game executable.\n"
                "Set the game installation directory with the button on the right."
            )
            self.game_folder_line_edit_button = QToolButton()
            self.game_folder_line_edit_button.setIcon(
                QIcon(self.lock_icon_path).pixmap(QSize(20, 20))
            )
            self.game_folder_line_edit_button.clicked.connect(
                partial(self.__toggle_line_editable, "game")
            )
            self.game_folder_select_button = QPushButton("...")
            self.game_folder_select_button.clicked.connect(self.set_game_exe_folder)
            self.game_folder_select_button.setObjectName("RightButton")

            if self.system_name == "Darwin":
                self.game_folder_select_button.setToolTip(
                    "Select the RimWorld game app location"
                )
            else:
                self.game_folder_select_button.setToolTip(
                    "Set the RimWorld game installation directory"
                )

            self.config_folder_open_button = QPushButton("Config folder")
            self.config_folder_open_button.setObjectName("LeftButton")
            self.config_folder_open_button.setToolTip(
                "Open the RimWorld game configuration directory"
            )
            self.config_folder_line = QLineEdit()
            self.config_folder_open_button.clicked.connect(
                partial(self.open_directory, self.config_folder_line.text)
            )
            self.config_folder_line.setReadOnly(True)
            self.config_folder_line.setClearButtonEnabled(True)
            self.config_folder_line_clear_button = self.config_folder_line.findChild(
                QToolButton
            )
            self.config_folder_line_clear_button.setEnabled(True)
            self.config_folder_line_clear_button.clicked.connect(
                self.clear_config_folder_line
            )
            self.config_folder_line.setPlaceholderText("Unconfigured")
            self.config_folder_line.setToolTip(
                "The this directory contains the ModsConfig.xml file, which shows your\n"
                "active mods and their load order. It may also contain other mod configs."
                "Set the ModsConfig.xml directory manually with the button on the right."
            )
            self.config_folder_line_edit_button = QToolButton()
            self.config_folder_line_edit_button.setIcon(
                QIcon(self.lock_icon_path).pixmap(QSize(20, 20))
            )
            self.config_folder_line_edit_button.clicked.connect(
                partial(self.__toggle_line_editable, "config")
            )
            self.config_folder_select_button = QPushButton("...")
            self.config_folder_select_button.clicked.connect(self.set_config_folder)
            self.config_folder_select_button.setObjectName("RightButton")
            if self.system_name == "Darwin":
                self.config_folder_select_button.setToolTip(
                    "Select the RimWorld game app location"
                )
            else:
                self.config_folder_select_button.setToolTip(
                    "Set the RimWorld game configuration directory"
                )

            self.local_folder_open_button = QPushButton("Local mods")
            self.local_folder_open_button.setObjectName("LeftButton")
            self.local_folder_open_button.setToolTip("Open the local mods directory")
            self.local_folder_line = QLineEdit()
            self.local_folder_open_button.clicked.connect(
                partial(self.open_directory, self.local_folder_line.text)
            )
            self.local_folder_line.setReadOnly(True)
            self.local_folder_line.setClearButtonEnabled(True)
            self.local_folder_line_clear_button = self.local_folder_line.findChild(
                QToolButton
            )
            self.local_folder_line_clear_button.setEnabled(True)
            self.local_folder_line_clear_button.clicked.connect(
                self.clear_local_folder_line
            )
            self.local_folder_line.setPlaceholderText("Unconfigured")
            self.local_folder_line.setToolTip(
                "The local mods directory contains manually downloaded mod folders.\n"
                "By default, this folder is located in the game install directory.\n"
                "If you are a SteamCMD user, this is also where mods will be located."
                "Set the Local mods directory manually with the button on the right."
            )
            self.local_folder_line_edit_button = QToolButton()
            self.local_folder_line_edit_button.setIcon(
                QIcon(self.lock_icon_path).pixmap(QSize(20, 20))
            )
            self.local_folder_line_edit_button.clicked.connect(
                partial(self.__toggle_line_editable, "local")
            )
            self.local_folder_select_button = QPushButton("...")
            self.local_folder_select_button.clicked.connect(self.set_local_folder)
            self.local_folder_select_button.setObjectName("RightButton")
            self.local_folder_select_button.setToolTip("Set the local mods directory.")

            self.workshop_folder_open_button = QPushButton("Steam mods")
            self.workshop_folder_open_button.setObjectName("LeftButton")
            self.workshop_folder_open_button.setToolTip(
                "Open the Steam Workshop mods directory"
            )
            self.workshop_folder_line = QLineEdit()
            self.workshop_folder_open_button.clicked.connect(
                partial(self.open_directory, self.workshop_folder_line.text)
            )
            self.workshop_folder_line.setReadOnly(True)
            self.workshop_folder_line.setClearButtonEnabled(True)
            self.workshop_folder_line_clear_button = (
                self.workshop_folder_line.findChild(QToolButton)
            )
            self.workshop_folder_line_clear_button.setEnabled(True)
            self.workshop_folder_line_clear_button.clicked.connect(
                self.clear_workshop_folder_line
            )
            self.workshop_folder_line.setPlaceholderText("Unconfigured")
            self.workshop_folder_line.setToolTip(
                "The Steam Workshop mods directory contains mods downloaded from Steam client.\n"
                "Set the Steam Workshop mods directory manually with the button on the right."
            )
            self.workshop_folder_line_edit_button = QToolButton()
            self.workshop_folder_line_edit_button.setIcon(
                QIcon(self.lock_icon_path).pixmap(QSize(20, 20))
            )
            self.workshop_folder_line_edit_button.clicked.connect(
                partial(self.__toggle_line_editable, "workshop")
            )
            self.workshop_folder_select_button = QPushButton("...")
            self.workshop_folder_select_button.clicked.connect(self.set_workshop_folder)
            self.workshop_folder_select_button.setObjectName("RightButton")
            self.workshop_folder_select_button.setToolTip(
                "Set the Steam Workshop Mods directory"
            )

            # WIDGETS INTO CONTAINER LAYOUTS
            self.client_settings_row.addWidget(self.auto_detect_paths_button)
            self.client_settings_row.addWidget(self.client_settings_button)
            self.client_settings_row.addWidget(self.hide_show_folder_rows_button)
            self.client_settings_row.addWidget(self.game_version_label)
            self.client_settings_row.addWidget(self.game_version_line)
            self.client_settings_row.addWidget(self.check_for_updates_button)
            self.client_settings_row.addWidget(self.wiki_button)

            self.game_folder_row.addWidget(self.game_folder_open_button)
            self.game_folder_row.addWidget(self.game_folder_line)
            self.game_folder_row.addWidget(self.game_folder_line_edit_button)
            self.game_folder_row.addWidget(self.game_folder_select_button)

            self.config_folder_row.addWidget(self.config_folder_open_button)
            self.config_folder_row.addWidget(self.config_folder_line)
            self.config_folder_row.addWidget(self.config_folder_line_edit_button)
            self.config_folder_row.addWidget(self.config_folder_select_button)

            self.local_folder_row.addWidget(self.local_folder_open_button)
            self.local_folder_row.addWidget(self.local_folder_line)
            self.local_folder_row.addWidget(self.local_folder_line_edit_button)
            self.local_folder_row.addWidget(self.local_folder_select_button)

            self.workshop_folder_row.addWidget(self.workshop_folder_open_button)
            self.workshop_folder_row.addWidget(self.workshop_folder_line)
            self.workshop_folder_row.addWidget(self.workshop_folder_line_edit_button)
            self.workshop_folder_row.addWidget(self.workshop_folder_select_button)

            # CONTAINER LAYOUTS INTO BASE LAYOUT
            self.client_settings_frame = QFrame()
            self.client_settings_frame.setObjectName("configLine")
            self.client_settings_frame.setLayout(self.client_settings_row)
            self.game_folder_frame = QFrame()
            self.game_folder_frame.setObjectName("configLine")
            self.game_folder_frame.setLayout(self.game_folder_row)
            self.config_folder_frame = QFrame()
            self.config_folder_frame.setObjectName("configLine")
            self.config_folder_frame.setLayout(self.config_folder_row)
            self.local_folder_frame = QFrame()
            self.local_folder_frame.setObjectName("configLine")
            self.local_folder_frame.setLayout(self.local_folder_row)
            self.workshop_folder_frame = QFrame()
            self.workshop_folder_frame.setObjectName("configLine")
            self.workshop_folder_frame.setLayout(self.workshop_folder_row)

            self._panel.addWidget(self.client_settings_frame)
            self._panel.addWidget(self.game_folder_frame)
            self._panel.addWidget(self.config_folder_frame)
            self._panel.addWidget(self.local_folder_frame)
            self._panel.addWidget(self.workshop_folder_frame)

            # INITIALIZE WIDGETS / FEATURES
            self._initialize_settings_panel()
            self._initialize_storage()

            # SIGNALS AND SLOTS
            self.check_for_updates_action.toggled.connect(self._check_updates_toggle)
            self.game_folder_line.textChanged.connect(
                partial(self.__handle_line_edit, line="game")
            )
            self.config_folder_line.textChanged.connect(
                partial(self.__handle_line_edit, line="config")
            )
            self.local_folder_line.textChanged.connect(
                partial(self.__handle_line_edit, line="local")
            )
            self.workshop_folder_line.textChanged.connect(
                partial(self.__handle_line_edit, line="workshop")
            )
            self.settings_panel.clear_paths_signal.connect(
                self.delete_all_paths_data
            )  # Actions delete_all_paths_data

            # General Preferences
            self.settings_panel.logger_debug_checkbox.setChecked(self.debug_mode)
            self.settings_panel.watchdog_checkbox.setChecked(self.watchdog_toggle)
            self.settings_panel.mod_type_filter_checkbox.setChecked(
                self.mod_type_filter_toggle
            )
            self.settings_panel.duplicate_mods_checkbox.setChecked(
                self.duplicate_mods_warning_toggle
            )
            self.settings_panel.steam_mods_update_checkbox.setChecked(
                self.steam_mods_update_check_toggle
            )
            self.settings_panel.try_download_missing_mods_checkbox.setChecked(
                self.try_download_missing_mods_toggle
            )

            # DQ GetAppDependencies
            self.settings_panel.build_steam_database_dlc_data_checkbox.setChecked(
                self.build_steam_database_dlc_data_toggle
            )

            # DB Builder update toggle
            self.settings_panel.build_steam_database_update_checkbox.setChecked(
                self.build_steam_database_update_toggle
            )

            # SteamCMD
            self.settings_panel.steamcmd_validate_downloads_checkbox.setChecked(
                self.steamcmd_validate_downloads_toggle
            )

            # todds
            self.settings_panel.todds_active_mods_target_checkbox.setChecked(
                self.todds_active_mods_target_toggle
            )
            self.settings_panel.todds_dry_run_checkbox.setChecked(
                self.todds_dry_run_toggle
            )
            self.settings_panel.todds_overwrite_checkbox.setChecked(
                self.todds_overwrite_toggle
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

    def __handle_line_edit(self, path: str, line: str) -> None:
        self._update_persistent_storage({f"{line}_folder": path})

    def __toggle_folder_rows(self) -> None:
        self.show_folder_rows = not self.show_folder_rows
        self.game_folder_frame.setVisible(self.show_folder_rows)
        self.config_folder_frame.setVisible(self.show_folder_rows)
        self.local_folder_frame.setVisible(self.show_folder_rows)
        self.workshop_folder_frame.setVisible(self.show_folder_rows)
        if self.show_folder_rows:
            self.hide_show_folder_rows_button.setText("Hide paths")
        else:
            self.hide_show_folder_rows_button.setText("Show paths")
        self._update_persistent_storage(
            settings={"show_folder_rows": self.show_folder_rows}
        )

    def __toggle_line_editable(self, folder_line: str):
        # Determine which line to toggle
        if folder_line == "game":
            line = self.game_folder_line
            button = self.game_folder_line_edit_button
        elif folder_line == "config":
            line = self.config_folder_line
            button = self.config_folder_line_edit_button
        elif folder_line == "local":
            line = self.local_folder_line
            button = self.local_folder_line_edit_button
        elif folder_line == "workshop":
            line = self.workshop_folder_line
            button = self.workshop_folder_line_edit_button
        # Toggle the line's editability
        if line.isReadOnly():
            line.setReadOnly(False)
            line.setClearButtonEnabled(True)
            line.findChild(QToolButton).setEnabled(True)
            button.setIcon(QIcon(self.unlock_icon_path).pixmap(QSize(20, 20)))
        else:
            line.setReadOnly(True)
            line.setClearButtonEnabled(True)
            line.findChild(QToolButton).setEnabled(True)
            button.setIcon(QIcon(self.lock_icon_path).pixmap(QSize(20, 20)))

    @property
    def panel(self) -> QVBoxLayout:
        return self._panel

    def _check_updates_toggle(self) -> None:
        self._update_persistent_storage(
            settings={
                "check_for_update_startup": self.check_for_updates_action.isChecked()
            }
        )

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
        self.dbs_path = str(Path(os.path.join(self.storage_path, "dbs")).resolve())
        self.user_rules_file_path = str(
            Path(os.path.join(self.dbs_path, "userRules.json")).resolve()
        )
        logger.info(f"Determined dbs path: {self.dbs_path}")
        if not os.path.exists(self.dbs_path):
            os.makedirs(self.dbs_path)
        if not os.path.exists(self.user_rules_file_path):
            initial_rules_db = DEFAULT_USER_RULES
            with open(self.user_rules_file_path, "w", encoding="utf-8") as output:
                json.dump(initial_rules_db, output, indent=4)
        # Always check for settings path, create with defaults if it doesn't exist
        settings_path = str(
            Path(os.path.join(self.storage_path, "settings.json")).resolve()
        )
        logger.info(f"Determined settings file path: {settings_path}")
        if not os.path.exists(settings_path):
            logger.info(f"Settings file does not exist!")
            # Create a new empty settings.json file
            default_settings: dict[str, Any] = DEFAULT_SETTINGS
            default_settings["external_steam_metadata_file_path"] = str(
                Path(
                    os.path.join(
                        self.storage_path,
                        default_settings["external_steam_metadata_file_path"],
                    )
                ).resolve()
            )
            default_settings["external_community_rules_file_path"] = str(
                Path(
                    os.path.join(
                        self.storage_path,
                        default_settings["external_community_rules_file_path"],
                    )
                ).resolve()
            )
            default_settings["steamcmd_install_path"] = self.storage_path
            json_object = json.dumps(default_settings, indent=4)
            logger.info(f"Writing default settings to: {settings_path}")
            with open(settings_path, "w", encoding="utf-8") as outfile:
                outfile.write(json_object)
        # RimSort depends on this settings.json file existing.
        # This should automatically be prepopulated with defaults above, or from user configuration.
        logger.info(f"Settings file exists!")
        with open(settings_path) as infile:
            settings_data = json.load(infile)
            logger.debug("Loaded JSON from file!")

            # Hide/show folder rows
            if settings_data.get("show_folder_rows"):
                self.show_folder_rows = settings_data["show_folder_rows"]

            # Update check
            if settings_data.get("check_for_update_startup"):
                self.check_for_updates_action.setChecked(
                    settings_data["check_for_update_startup"]
                )

            # Game configuration paths
            if settings_data.get("game_folder"):
                game_folder_path = settings_data["game_folder"]
                if os.path.exists(game_folder_path):
                    self.game_folder_line.setText(game_folder_path)
                else:
                    logger.warning(
                        f"The game folder that was loaded does not exist: {game_folder_path}"
                    )
            if settings_data.get("config_folder"):
                config_folder_path = settings_data["config_folder"]
                if os.path.exists(config_folder_path):
                    self.config_folder_line.setText(config_folder_path)
                else:
                    logger.warning(
                        f"The config folder that was loaded does not exist: {config_folder_path}"
                    )
            if settings_data.get("workshop_folder"):
                workshop_folder_path = settings_data["workshop_folder"]
                if os.path.exists(workshop_folder_path):
                    self.workshop_folder_line.setText(workshop_folder_path)
                else:
                    logger.warning(
                        f"The workshop folder that was loaded does not exist: {workshop_folder_path}"
                    )
            if settings_data.get("local_folder"):
                local_folder_path = settings_data["local_folder"]
                if os.path.exists(local_folder_path):
                    self.local_folder_line.setText(local_folder_path)
                else:
                    logger.warning(
                        f"The local folder that was loaded does not exist: {local_folder_path}"
                    )

            # general
            if settings_data.get("watchdog_toggle"):
                self.watchdog_toggle = settings_data["watchdog_toggle"]
            if settings_data.get("mod_type_filter_toggle"):
                self.mod_type_filter_toggle = settings_data["mod_type_filter_toggle"]
            if settings_data.get("duplicate_mods_warning"):
                self.duplicate_mods_warning_toggle = settings_data[
                    "duplicate_mods_warning"
                ]
            if settings_data.get("steam_mods_update_check"):
                self.steam_mods_update_check_toggle = settings_data[
                    "steam_mods_update_check"
                ]
            if settings_data.get("try_download_missing_mods"):
                self.try_download_missing_mods_toggle = settings_data[
                    "try_download_missing_mods"
                ]

            # sorting algorithm
            if settings_data.get("sorting_algorithm"):
                self.settings_panel.sorting_algorithm_cb.setCurrentText(
                    settings_data["sorting_algorithm"]
                )

            # metadata
            if settings_data.get("external_steam_metadata_file_path"):
                self.steam_db_file_path = settings_data[
                    "external_steam_metadata_file_path"
                ]
            if settings_data.get("external_steam_metadata_repo"):
                self.steam_db_repo = settings_data["external_steam_metadata_repo"]
            if settings_data.get("external_steam_metadata_source"):
                self.settings_panel.external_steam_metadata_cb.setCurrentText(
                    settings_data["external_steam_metadata_source"]
                )
            if settings_data.get("external_community_rules_file_path"):
                self.community_rules_file_path = settings_data[
                    "external_community_rules_file_path"
                ]
            if settings_data.get("external_community_rules_repo"):
                self.community_rules_repo = settings_data[
                    "external_community_rules_repo"
                ]
            if settings_data.get("external_community_rules_metadata_source"):
                self.settings_panel.external_community_rules_metadata_cb.setCurrentText(
                    settings_data["external_community_rules_metadata_source"]
                )

            # game args
            if settings_data.get("runArgs"):
                self.run_arguments = settings_data["runArgs"]

            # db builder
            if settings_data.get("db_builder_include"):
                self.db_builder_include = settings_data["db_builder_include"]
            if self.db_builder_include == "no_local":
                self.settings_panel.build_steam_database_include_cb.setCurrentText(
                    "No local data"
                )
            if self.db_builder_include == "all_mods":
                self.settings_panel.build_steam_database_include_cb.setCurrentText(
                    "All Mods"
                )
            if settings_data.get("build_steam_database_dlc_data"):
                self.build_steam_database_dlc_data_toggle = settings_data[
                    "build_steam_database_dlc_data"
                ]
            if settings_data.get("build_steam_database_update_toggle"):
                self.build_steam_database_update_toggle = settings_data[
                    "build_steam_database_update_toggle"
                ]
            if settings_data.get("database_expiry"):
                self.database_expiry = settings_data["database_expiry"]
            if settings_data.get("steam_apikey"):
                self.steam_apikey = settings_data["steam_apikey"]

            # github
            if settings_data.get("github_username"):
                self.github_username = settings_data["github_username"]
            if settings_data.get("github_token"):
                self.github_token = settings_data["github_token"]

            # steamcmd
            if settings_data.get("steamcmd_validate_downloads"):
                self.steamcmd_validate_downloads_toggle = settings_data[
                    "steamcmd_validate_downloads"
                ]
            if settings_data.get("steamcmd_install_path"):
                self.steamcmd_install_path = settings_data["steamcmd_install_path"]
            if not os.path.exists(self.steamcmd_install_path):
                logger.warning(
                    f"Configured steamcmd prefix does not exist. Creating new steamcmd prefix at: {self.steamcmd_install_path}"
                )  # This shouldn't be happening, but we check it anyways.
                os.makedirs(self.steamcmd_install_path)

            # todds
            if settings_data.get("todds_preset"):
                self.todds_preset = settings_data["todds_preset"]
            if self.todds_preset == "optimized":
                self.settings_panel.todds_presets_cb.setCurrentText(
                    "Optimized - Recommended for RimWorld"
                )
            if settings_data.get("todds_active_mods_target"):
                self.todds_active_mods_target_toggle = settings_data[
                    "todds_active_mods_target"
                ]
            if settings_data.get("todds_dry_run"):
                self.todds_dry_run_toggle = settings_data["todds_dry_run"]
            if settings_data.get("todds_overwrite"):
                self.todds_overwrite_toggle = settings_data["todds_overwrite"]

        logger.info("Finished storage initialization")

    def _on_settings_close(self) -> None:
        logger.info(
            "Settings panel closed, updating persistent storage for these options..."
        )

        # Close the window
        self.settings_panel.close()

        # Determine configurations
        # watchdog toggle
        if self.settings_panel.watchdog_checkbox.isChecked():
            self.watchdog_toggle = True
        else:
            self.watchdog_toggle = False
        # mod type filter toggle mods toggle
        if self.settings_panel.mod_type_filter_checkbox.isChecked():
            self.mod_type_filter_toggle = True
        else:
            self.mod_type_filter_toggle = False
        # duplicate mods check toggle
        if self.settings_panel.duplicate_mods_checkbox.isChecked():
            self.duplicate_mods_warning_toggle = True
        else:
            self.duplicate_mods_warning_toggle = False
        # steam mods update check toggle
        if self.settings_panel.steam_mods_update_checkbox.isChecked():
            self.steam_mods_update_check_toggle = True
        else:
            self.steam_mods_update_check_toggle = False
        # missing mods download toggle
        if self.settings_panel.try_download_missing_mods_checkbox.isChecked():
            self.try_download_missing_mods_toggle = True
        else:
            self.try_download_missing_mods_toggle = False

        # db builder mode
        if (
            "No local data"
            in self.settings_panel.build_steam_database_include_cb.currentText()
        ):
            self.db_builder_include = "no_local"
        elif (
            "All Mods"
            in self.settings_panel.build_steam_database_include_cb.currentText()
        ):
            self.db_builder_include = "all_mods"
        # dq getappdependencies toggle
        if self.settings_panel.build_steam_database_dlc_data_checkbox.isChecked():
            self.build_steam_database_dlc_data_toggle = True
        else:
            self.build_steam_database_dlc_data_toggle = False
        # db builder update toggle
        if self.settings_panel.build_steam_database_update_checkbox.isChecked():
            self.build_steam_database_update_toggle = True
        else:
            self.build_steam_database_update_toggle = False

        # steamcmd validate downloads toggle
        if self.settings_panel.steamcmd_validate_downloads_checkbox.isChecked():
            self.steamcmd_validate_downloads_toggle = True
        else:
            self.steamcmd_validate_downloads_toggle = False

        # todds preset
        if "Optimized - Recommended for RimWorld" in self.settings_panel.todds_presets_cb.currentText():
            self.todds_preset = "optimized"
        # todds active mods target
        if self.settings_panel.todds_active_mods_target_checkbox.isChecked():
            self.todds_active_mods_target_toggle = True
        else:
            self.todds_active_mods_target_toggle = False
        # todds dry run
        if self.settings_panel.todds_dry_run_checkbox.isChecked():
            self.todds_dry_run_toggle = True
        else:
            self.todds_dry_run_toggle = False
        # todds overwrite textures
        if self.settings_panel.todds_overwrite_checkbox.isChecked():
            self.todds_overwrite_toggle = True
        else:
            self.todds_overwrite_toggle = False

        # Update settings.json
        self._update_persistent_storage(
            {
                "build_steam_database_dlc_data": self.build_steam_database_dlc_data_toggle,
                "build_steam_database_update_toggle": self.build_steam_database_update_toggle,
                "mod_type_filter_toggle": self.mod_type_filter_toggle,
                "db_builder_include": self.db_builder_include,
                "duplicate_mods_warning": self.duplicate_mods_warning_toggle,
                "external_steam_metadata_source": self.settings_panel.external_steam_metadata_cb.currentText(),
                "external_community_rules_metadata_source": self.settings_panel.external_community_rules_metadata_cb.currentText(),
                "sorting_algorithm": self.settings_panel.sorting_algorithm_cb.currentText(),
                "steam_mods_update_check": self.steam_mods_update_check_toggle,
                "steamcmd_validate_downloads": self.steamcmd_validate_downloads_toggle,
                "try_download_missing_mods": self.try_download_missing_mods_toggle,
                "todds_active_mods_target": self.todds_active_mods_target_toggle,
                "todds_dry_run": self.todds_dry_run_toggle,
                "todds_overwrite": self.todds_overwrite_toggle,
                "todds_preset": self.todds_preset,
                "watchdog_toggle": self.watchdog_toggle,
            }
        )
        # Update mod type filter toggle
        self.configuration_signal.emit("update_mod_type_filter_toggle")
        # Update SteamCMD validate toggle
        self.configuration_signal.emit("update_steamcmd_validate_toggle")

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

    def _update_persistent_storage(self, settings: Dict[str, Any]) -> None:
        """
        Given a key and value, write this key and value to the
        persistent settings.json.

        :param key: key to use
        :param value: value to replace
        """
        logger.info("Updating persistent storage")
        settings_path = str(
            Path(os.path.join(self.storage_path, "settings.json")).resolve()
        )
        logger.info(f"Generated settings.json path: {settings_path}")
        if os.path.exists(settings_path):
            logger.info("settings.json exists, opening to write")
            with open(settings_path) as infile:
                settings_data = json.load(infile)
                settings_data.update(settings)
                json_object = json.dumps(settings_data, indent=4)
                with open(settings_path, "w", encoding="utf-8") as outfile:
                    outfile.write(json_object)
                    logger.info("JSON data written")
        else:
            logger.error(
                "settings.json does not exist despite already running _initialize_storage...?!"
            )

    # PATHS

    def autodetect_paths_by_platform(self) -> None:
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

        if self.system_name == "Darwin":
            os_paths = darwin_paths
            logger.info(f"Running on MacOS with the following paths: {os_paths}")
        elif self.system_name == "Linux":
            os_paths = linux_paths
            logger.info(f"Running on Linux with the following paths: {os_paths}")
        elif self.system_name == "Windows":
            os_paths = windows_paths
            logger.info(f"Running on Windows with the following paths: {os_paths}")
        else:
            logger.error("Attempting to autodetect paths on an unknown system.")

        # If the game folder exists...
        if os.path.exists(os_paths[0]):
            logger.info(f"Autodetected game folder path exists: {os_paths[0]}")
            if not self.game_folder_line.text():
                logger.info(
                    "No value set currently for game folder. Overwriting with autodetected path"
                )
                self.game_folder_line.setText(os_paths[0])
                self._update_persistent_storage({"game_folder": os_paths[0]})
            else:
                logger.info("Value already set for game folder. Passing")
        else:
            logger.warning(
                f"Autodetected game folder path does not exist: {os_paths[0]}"
            )

        # If the config folder exists...
        if os.path.exists(os_paths[1]):
            logger.info(f"Autodetected config folder path exists: {os_paths[1]}")
            if not self.config_folder_line.text():
                logger.info(
                    "No value set currently for config folder. Overwriting with autodetected path"
                )
                self.config_folder_line.setText(os_paths[1])
                self._update_persistent_storage({"config_folder": os_paths[1]})
            else:
                logger.info("Value already set for config folder. Passing")
        else:
            logger.warning(
                f"Autodetected config folder path does not exist: {os_paths[1]}"
            )

        # If the workshop folder exists
        if os.path.exists(os_paths[2]):
            logger.info(f"Autodetected workshop folder path exists: {os_paths[2]}")
            if not self.workshop_folder_line.text():
                logger.info(
                    "No value set currently for workshop folder. Overwriting with autodetected path"
                )
                self.workshop_folder_line.setText(os_paths[2])
                self._update_persistent_storage({"workshop_folder": os_paths[2]})
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
            if not self.local_folder_line.text():
                logger.info(
                    "No value set currently for local mods folder. Overwriting with autodetected path"
                )
                self.local_folder_line.setText(rimworld_mods_path)
                self._update_persistent_storage({"local_folder": rimworld_mods_path})
            else:
                logger.info("Value already set for local mods folder. Passing")
        else:
            logger.warning(
                f"Autodetected game folder path does not exist: {rimworld_mods_path}"
            )

    def check_if_essential_paths_are_set(self) -> bool:
        """
        When the user starts the app for the first time, none
        of the paths will be set. We should check for this and
        not throw a fatal error trying to load mods until the
        user has had a chance to set paths.
        """
        game_folder_path = self.game_folder_line.text()
        config_folder_path = self.config_folder_line.text()
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

    def clear_game_folder_line(self) -> None:
        logger.info("USER ACTION: clear game folder line")
        self._update_persistent_storage({"game_folder": ""})
        self.game_folder_line.setText("")

    def clear_config_folder_line(self) -> None:
        logger.info("USER ACTION: clear config folder line")
        self._update_persistent_storage({"config_folder": ""})
        self.config_folder_line.setText("")

    def clear_workshop_folder_line(self) -> None:
        logger.info("USER ACTION: clear workshop folder line")
        self._update_persistent_storage({"workshop_folder": ""})
        self.workshop_folder_line.setText("")

    def clear_local_folder_line(self) -> None:
        logger.info("USER ACTION: clear local folder line")
        self._update_persistent_storage({"local_folder": ""})
        self.local_folder_line.setText("")

    def delete_all_paths_data(self) -> None:
        logger.info("USER ACTION: clear all paths")
        folders = ["workshop_folder", "game_folder", "config_folder", "local_folder"]
        # Update storage to remove all paths data
        self._update_persistent_storage({folder: "" for folder in folders})

        # Visually delete paths data
        self.game_folder_line.setText("")
        self.config_folder_line.setText("")
        self.workshop_folder_line.setText("")
        self.local_folder_line.setText("")
        self.game_version_line.setText("")

    def open_directory(self, callable: Any) -> None:
        """
        This slot is called when the user presses any of the left-side
        game configuration buttons to open up corresponding folders.

        :param callable: function to get the corresponding folder path
        """
        logger.info("USER ACTION: open directory with callable")
        path = callable()
        logger.info(f"Directory callable resolved to: {path}")
        if os.path.exists(path):
            if os.path.isfile(path) or path.endswith(".app"):
                logger.info("Opening parent directory of file or MacOS app")
                platform_specific_open(os.path.dirname(path))
            else:
                logger.info("Opening directory")
                platform_specific_open(path)
        else:
            logger.warning(f"The path {path} does not exist")
            show_warning(
                text="Could not open invalid path",
                information=(
                    f"The path [{path}] you are trying to open does not exist. Has the "
                    "folder been deleted or moved? Try re-setting the path with the button "
                    "on the right or using the AutoDetect Paths functionality."
                ),
            )

    def set_game_exe_folder(self) -> None:
        """
        Open a file dialog to allow the user to select the game executable.
        """
        logger.info("USER ACTION: set the game install folder")
        start_dir = None
        if self.game_folder_line.text():
            possible_dir = self.game_folder_line.text()
            if os.path.exists(possible_dir):
                start_dir = possible_dir
        if self.system_name == "Darwin":
            game_exe_folder_path = show_dialogue_file(
                mode="open", caption="Select RimWorld app", _dir=start_dir
            )
        else:
            game_exe_folder_path = show_dialogue_file(
                mode="open_dir",
                caption="Select RimWorld game folder",
                _dir=start_dir if start_dir else None,
            )
        logger.info(f"Selected path: {game_exe_folder_path}")
        if game_exe_folder_path and game_exe_folder_path != ".":
            logger.info(
                f"Game install folder chosen. Setting UI and updating storage: {game_exe_folder_path}"
            )
            self.game_folder_line.setText(game_exe_folder_path)
        else:
            logger.info("USER ACTION: pressed cancel, passing")

    def set_config_folder(self) -> None:
        """
        Open a file dialog to allow the user to select the ModsConfig.xml directory.
        """
        logger.info("USER ACTION: set the ModsConfig.xml folder")
        start_dir = None
        if self.config_folder_line.text():
            possible_dir = self.config_folder_line.text()
            if os.path.exists(possible_dir):
                start_dir = possible_dir
        config_folder_path = show_dialogue_file(
            mode="open_dir",
            caption="Select RimWorld config folder",
            _dir=start_dir if start_dir else None,
        )
        logger.info(f"Selected path: {config_folder_path}")
        if config_folder_path and config_folder_path != ".":
            logger.info(
                f"ModsConfig.xml folder chosen. Setting UI and updating storage: {config_folder_path}"
            )
            self.config_folder_line.setText(config_folder_path)
        else:
            logger.debug("USER ACTION: pressed cancel, passing")

    def set_local_folder(self) -> None:
        """
        Open a file dialog to allow the user to select a directory
        to set as the local mods folder.
        """
        logger.info("USER ACTION: set the local mods folder")
        start_dir = None
        if self.system_name == "Darwin":
            if self.game_folder_line.text():
                possible_dir = self.game_folder_line.text()
                if os.path.exists(possible_dir):
                    start_dir = os.path.split(possible_dir)[0]
        else:
            if self.local_folder_line.text():
                possible_dir = self.local_folder_line.text()
                if os.path.exists(possible_dir):
                    start_dir = possible_dir
        if self.system_name == "Darwin":
            # On Mac it need too many hoops to jump through to select the mods dir
            # Instead we ask the user to select the app and we append the mods dir to the path as needed
            game_app_path = show_dialogue_file(
                mode="open",
                caption="Select game app",
                _dir=start_dir if start_dir else None,
            )
            if game_app_path:
                local_path = os.path.join(
                    game_app_path,
                    "Mods",
                )
            else:
                local_path = None
        else:
            local_path = show_dialogue_file(
                mode="open_dir",
                caption="Select local mods folder",
                _dir=start_dir if start_dir else None,
            )
        logger.info(f"Selected path: {local_path}")
        if local_path:
            logger.info(
                f"Local mods folder chosen. Setting UI and updating storage: {local_path}"
            )
            self.local_folder_line.setText(local_path)
        else:
            logger.debug("USER ACTION: pressed cancel, passing")

    def set_workshop_folder(self) -> None:
        """
        Open a file dialog to allow the user to select a directory
        to set as the workshop folder.
        """
        logger.info("USER ACTION: set the workshop folder")
        start_dir = None
        if self.workshop_folder_line.text():
            possible_dir = self.workshop_folder_line.text()
            if os.path.exists(possible_dir):
                start_dir = possible_dir
        workshop_path = show_dialogue_file(
            mode="open_dir",
            caption="Select workshop mods folder",
            _dir=start_dir if start_dir else None,
        )
        logger.info(f"Selected path: {workshop_path}")
        if workshop_path:
            logger.info(
                f"Workshop folder chosen. Setting UI and updating storage: {workshop_path}"
            )
            self.workshop_folder_line.setText(workshop_path)
        else:
            logger.debug("USER ACTION: pressed cancel, passing")

    def checkForUpdateBtnContextMenuEvent(self, point: QPoint) -> None:
        contextMenu = QMenu()  # Check for update context menu event
        contextMenu.addAction(
            self.check_for_updates_action
        )  # check for update on startup
        action = contextMenu.exec_(self.check_for_updates_button.mapToGlobal(point))
