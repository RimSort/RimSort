from functools import partial
from logger_tt import logger
import os
from pathlib import Path
import sys
from tempfile import gettempdir

from PySide6.QtCore import QPoint, QSize, QStandardPaths, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
)

from model.dialogue import show_information
from util.generic import platform_specific_open, upload_data_to_0x0_st


class CenteredItemDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignCenter


class SettingsPanel(QDialog):
    clear_paths_signal = Signal(str)
    actions_signal = Signal(str)

    def __init__(self, storage_path: str) -> None:
        logger.debug("Initializing SettingsPanel")
        super(SettingsPanel, self).__init__()

        self.storage_path = storage_path

        # Create window
        self.setFixedSize(QSize(575, 625))
        self.setWindowTitle("Settings")

        # Allow for styling
        self.centered_item_delegate = CenteredItemDelegate()
        self.setObjectName("settingsPanel")

        # Create main layout
        self.layout = QVBoxLayout()

        # General layouts
        self.general_options_layout = QHBoxLayout()
        self.general_actions_layout = QVBoxLayout()
        self.general_preferences_layout = QVBoxLayout()
        # General widgets
        self.general_label = QLabel("General")
        self.general_label.setObjectName("summaryValue")
        self.general_label.setAlignment(Qt.AlignCenter)
        self.rimsort_actions_label = QLabel("RimSort actions:")
        self.rimsort_actions_label.setObjectName("summaryValue")
        self.rimsort_actions_label.setAlignment(Qt.AlignCenter)
        self.clear_paths_button = QPushButton("Clear game cfg paths")
        self.clear_paths_button.clicked.connect(
            partial(self.clear_paths_signal.emit, "clear_paths")
        )
        self.set_github_identity_button = QPushButton("Github identity")
        self.set_github_identity_button.clicked.connect(
            partial(self.actions_signal.emit, "configure_github_identity")
        )
        self.open_log_button = QPushButton("Open RimSort.log")
        self.open_log_button.clicked.connect(
            partial(
                platform_specific_open,
                str(Path(os.path.join(gettempdir(), "RimSort.log")).resolve()),
            )
        )
        self.open_storage_button = QPushButton("Open RimSort storage")
        self.open_storage_button.clicked.connect(
            partial(
                platform_specific_open,
                self.storage_path,
            )
        )
        self.upload_log_button = QPushButton("Upload RimSort.log")
        self.upload_log_button.setToolTip(
            "RimSort.log will be uploaded to http://0x0.st/ and\n"
            + "the URL will be copied to your clipboard."
        )
        self.upload_log_button.clicked.connect(
            partial(self.actions_signal.emit, "upload_rs_log")
        )
        self.upload_log_old_button = QPushButton("Upload RimSort.old.log")
        self.upload_log_old_button.setToolTip(
            "RimSort.old.log will be uploaded to http://0x0.st/ and\n"
            + "the URL will be copied to your clipboard."
        )
        self.upload_log_old_button.clicked.connect(
            partial(self.actions_signal.emit, "upload_rs_old_log")
        )
        self.rimsort_options_label = QLabel("RimSort Options:")
        self.rimsort_options_label.setObjectName("summaryValue")
        self.rimsort_options_label.setAlignment(Qt.AlignCenter)
        self.logger_debug_checkbox = QCheckBox(
            "Enable RimSort logger verbose DEBUG mode"
        )
        self.logger_debug_checkbox.setObjectName("summaryValue")
        self.logger_debug_checkbox.setToolTip(
            "If enabled, changes logger level from INFO to DEBUG, enabling us to\n"
            + "supply a multitude of information relevant to debugging if needed.\n\n"
            + "This option is applied on RimSort initialization."
        )
        self.logger_debug_checkbox.clicked.connect(self.loggerDebugCheckboxEvent)
        self.watchdog_checkbox = QCheckBox(
            "Enable RimSort to use watchdog file monitor daemon"
        )
        self.watchdog_checkbox.setObjectName("summaryValue")
        self.watchdog_checkbox.setToolTip(
            "Primarily used to detect file-changes to mods and activate the Refresh\n"
            + "button animation. This may potentially be used later for other things.\n\n"
            + "This option is applied on RimSort initialization."
        )
        self.mod_type_filter_checkbox = QCheckBox(
            "Show mod type filter in the active/inactive mod lists"
        )
        self.mod_type_filter_checkbox.setObjectName("summaryValue")
        self.mod_type_filter_checkbox.setToolTip(
            "Displays icon in mod list widget to signify.\n"
            + "Requires restart for preference to take effect."
        )
        self.duplicate_mods_checkbox = QCheckBox(
            "Show list of detected duplicate mods on refresh"
        )
        self.duplicate_mods_checkbox.setObjectName("summaryValue")
        self.steam_mods_update_checkbox = QCheckBox(
            "Show list of available Workshop mod updates on refresh"
        )
        self.steam_mods_update_checkbox.setObjectName("summaryValue")
        self.steam_mods_update_checkbox.setToolTip(
            "This option requires a live internet connection to function properly.\n"
            + 'Uses Steam WebAPI to query "Last Updated" timestamp from mod publishings'
        )
        self.try_download_missing_mods_checkbox = QCheckBox(
            "Try to download missing mods when detected"
        )
        self.try_download_missing_mods_checkbox.setObjectName("summaryValue")
        self.try_download_missing_mods_checkbox.setToolTip(
            "This option will allow you to attempt to download any missing mods\n"
            + "detected when importing mods, or when the active mods list is refreshed. \n"
            + "Relies on a Steam DB which contains accurate dependency information.\n\n"
            + "Prompts a choice between SteamCMD and Steam client to retrieve the missing mods."
        )
        # Build the general options layout
        self.general_actions_layout.addWidget(self.rimsort_actions_label)
        self.general_actions_layout.addWidget(self.clear_paths_button)
        self.general_actions_layout.addWidget(self.set_github_identity_button)
        self.general_actions_layout.addWidget(self.open_log_button)
        self.general_actions_layout.addWidget(self.open_storage_button)
        self.general_actions_layout.addWidget(self.upload_log_button)
        self.general_actions_layout.addWidget(self.upload_log_old_button)
        self.general_preferences_layout.addWidget(self.rimsort_options_label)
        self.general_preferences_layout.addWidget(self.logger_debug_checkbox)
        self.general_preferences_layout.addWidget(self.watchdog_checkbox)
        self.general_preferences_layout.addWidget(self.mod_type_filter_checkbox)
        self.general_preferences_layout.addWidget(self.duplicate_mods_checkbox)
        self.general_preferences_layout.addWidget(self.steam_mods_update_checkbox)
        self.general_preferences_layout.addWidget(
            self.try_download_missing_mods_checkbox
        )
        self.general_options_layout.addLayout(self.general_actions_layout, 5)
        self.general_options_layout.addLayout(self.general_preferences_layout, 10)

        # sorting algorithm
        self.sorting_algorithm_label = QLabel("Sorting Algorithm")
        self.sorting_algorithm_label.setObjectName("summaryValue")
        self.sorting_algorithm_label.setAlignment(Qt.AlignCenter)
        self.sorting_algorithm_cb = QComboBox()
        self.sorting_algorithm_cb.setObjectName("MainUI")
        self.sorting_algorithm_cb.addItems(["Alphabetical", "Topological"])
        self.sorting_algorithm_cb.setItemDelegate(self.centered_item_delegate)

        # metadata layouts
        self.metadata_options_layout = QHBoxLayout()
        self.metadata_configuration_layout = QVBoxLayout()
        self.metadata_steam_configuration_layout = QHBoxLayout()
        self.metadata_community_rules_configuration_layout = QHBoxLayout()
        self.database_tools_layout = QVBoxLayout()
        self.database_tools_builder_layout = QHBoxLayout()
        self.database_tools_actions_layout = QHBoxLayout()
        # metadata widgets
        self.external_metadata_icon = QIcon(
            str(
                Path(
                    os.path.join(os.path.dirname(__file__), "../data/database.png")
                ).resolve()
            )
        )
        self.external_metadata_label = QLabel("External Metadata")
        self.external_metadata_label.setObjectName("summaryValue")
        self.external_metadata_label.setAlignment(Qt.AlignCenter)
        # external steam metadata
        self.external_steam_metadata_label = QLabel("Steam Workshop DB")
        self.external_steam_metadata_label.setObjectName("summaryValue")
        self.external_steam_metadata_label.setAlignment(Qt.AlignCenter)
        self.external_steam_metadata_button = QToolButton()
        self.external_steam_metadata_button.setIcon(self.external_metadata_icon)
        self.external_steam_metadata_button.setToolTip(
            "Right-click to access Steam Workshop Database options"
        )
        # Set context menu policy and connect custom context menu event
        self.external_steam_metadata_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.external_steam_metadata_button.customContextMenuRequested.connect(
            self.externalSteamDbBtnContextMenuEvent
        )
        # external steam metadata combobox
        self.external_steam_metadata_cb = QComboBox()
        self.external_steam_metadata_cb.setObjectName("MainUI")
        self.external_steam_metadata_cb.addItems(
            [
                "None",
                "Configured file path",
                "Configured git repository",                
            ]
        )
        self.external_steam_metadata_cb.setItemDelegate(self.centered_item_delegate)
        # external community rules metadata
        self.external_community_rules_metadata_label = QLabel("Community Rules DB")
        self.external_community_rules_metadata_label.setObjectName("summaryValue")
        self.external_community_rules_metadata_label.setAlignment(Qt.AlignCenter)
        self.external_community_rules_metadata_button = QToolButton()
        self.external_community_rules_metadata_button.setIcon(
            self.external_metadata_icon
        )
        self.external_community_rules_metadata_button.setToolTip(
            "Right-click to access Community Rules Database options"
        )
        # Set context menu policy and connect custom context menu event
        self.external_community_rules_metadata_button.setContextMenuPolicy(
            Qt.CustomContextMenu
        )
        self.external_community_rules_metadata_button.customContextMenuRequested.connect(
            self.externalCommunityRulesDbBtnContextMenuEvent
        )
        # external community rules metadata combobox
        self.external_community_rules_metadata_cb = QComboBox()
        self.external_community_rules_metadata_cb.setObjectName("MainUI")
        self.external_community_rules_metadata_cb.addItems(
            [
                "None",
                "Configured file path",
                "Configured git repository",                
            ]
        )
        self.external_community_rules_metadata_cb.setItemDelegate(
            self.centered_item_delegate
        )
        self.build_steam_database_label = QLabel("Steam DB Builder Options:")
        self.build_steam_database_label.setObjectName("summaryValue")
        self.build_steam_database_label.setAlignment(Qt.AlignCenter)
        self.build_steam_database_include_label = QLabel("Include:")
        self.build_steam_database_include_label.setObjectName("summaryValue")
        self.build_steam_database_include_label.setAlignment(Qt.AlignCenter)
        self.build_steam_database_include_cb = QComboBox()
        self.build_steam_database_include_cb.setObjectName("MainUI")
        self.build_steam_database_include_cb.addItems(["No local data", "All Mods"])
        self.build_steam_database_include_cb.setItemDelegate(
            self.centered_item_delegate
        )
        self.build_steam_database_button = QPushButton("Build database")
        self.build_steam_database_button.setToolTip(
            "Right-click to:"
            + "\n\n- Merge 2 databases"
            + "\n- Set Database expiry"
            + "\n- Set Steam WebAPI key"
            + '\n\nPlease consult the "User Guide" on the RimSort wiki'
            + "\n\nRequires:"
            + "\n- A live Internet connection"
            + "\n- A Steam WebAPI key configured"
        )
        # Set context menu policy and connect custom context menu event
        self.build_steam_database_button.clicked.connect(
            partial(self.actions_signal.emit, "build_steam_database_thread")
        )
        self.build_steam_database_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.build_steam_database_button.customContextMenuRequested.connect(
            self.buildDatabaseBtnContextMenuEvent
        )
        self.build_steam_database_dlc_data_checkbox = QCheckBox(
            "Include DLC dependency data in database"
        )
        self.build_steam_database_dlc_data_checkbox.setToolTip(
            "Requires:\n"
            + "- A live Internet connection\n"
            + "- An online Steam client with RimWorld purchased & present in library"
        )
        self.build_steam_database_dlc_data_checkbox.setObjectName("summaryValue")
        self.build_steam_database_update_checkbox = QCheckBox(
            "Update database instead of overwriting"
        )
        self.build_steam_database_update_checkbox.setToolTip(
            "If the designated database exists, update it instead of overwriting it."
        )
        self.build_steam_database_update_checkbox.setObjectName("summaryValue")
        self.comparison_report_button = QPushButton("Comparison report")
        self.comparison_report_button.setToolTip(
            "Generate dependency comparison report between 2 Steam DBs"
        )
        self.comparison_report_button.clicked.connect(
            partial(self.actions_signal.emit, "comparison_report")
        )
        self.download_all_mods_btn = QPushButton("Download all mods")
        self.download_all_mods_btn.setToolTip(
            "Right-click me to access my options...\n"
            + "Use this to attempt to download every mod that is available on Steam Workshop"
        )
        self.download_all_mods_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self.download_all_mods_btn.customContextMenuRequested.connect(
            self.downloadAllModsContextMenuEvent
        )
        # Build the metadata options layout
        self.metadata_steam_configuration_layout.addWidget(
            self.external_steam_metadata_label
        )
        self.metadata_steam_configuration_layout.addWidget(
            self.external_steam_metadata_button
        )
        self.metadata_configuration_layout.addLayout(
            self.metadata_steam_configuration_layout
        )
        self.metadata_configuration_layout.addWidget(self.external_steam_metadata_cb)
        self.metadata_community_rules_configuration_layout.addWidget(
            self.external_community_rules_metadata_label
        )
        self.metadata_community_rules_configuration_layout.addWidget(
            self.external_community_rules_metadata_button
        )
        self.metadata_configuration_layout.addLayout(
            self.metadata_community_rules_configuration_layout
        )
        self.metadata_configuration_layout.addWidget(
            self.external_community_rules_metadata_cb
        )
        self.database_tools_layout.addWidget(self.build_steam_database_label)
        self.database_tools_builder_layout.addWidget(
            self.build_steam_database_include_label
        )
        self.database_tools_builder_layout.addWidget(
            self.build_steam_database_include_cb
        )
        self.database_tools_builder_layout.addWidget(self.build_steam_database_button)
        self.database_tools_layout.addLayout(self.database_tools_builder_layout)
        self.database_tools_layout.addWidget(
            self.build_steam_database_dlc_data_checkbox
        )
        self.database_tools_layout.addWidget(self.build_steam_database_update_checkbox)
        self.database_tools_actions_layout.addWidget(self.comparison_report_button)
        self.database_tools_actions_layout.addWidget(self.download_all_mods_btn)

        self.metadata_options_layout.addLayout(self.metadata_configuration_layout)
        self.metadata_options_layout.addLayout(self.database_tools_layout)
        self.database_tools_layout.addLayout(self.database_tools_actions_layout)

        # steamcmd
        self.steamcmd_label = QLabel("SteamCMD")
        self.steamcmd_label.setObjectName("summaryValue")
        self.steamcmd_label.setAlignment(Qt.AlignCenter)
        self.steamcmd_validate_downloads_checkbox = QCheckBox(
            "Force SteamCMD to validate downloaded workshop mods"
        )
        self.steamcmd_validate_downloads_checkbox.setObjectName("summaryValue")
        # todds
        self.todds_label = QLabel("todds Options")
        self.todds_label.setObjectName("summaryValue")
        self.todds_label.setAlignment(Qt.AlignCenter)
        # layout for Quality preset
        self.todds_preset_layout = QHBoxLayout()
        self.todds_preset_label = QLabel("Quality preset:")
        self.todds_preset_label.setObjectName("summaryValue")
        self.todds_presets_cb = QComboBox()
        self.todds_presets_cb.setObjectName("MainUI")
        self.todds_presets_cb.addItems(
            [
                "Optimized - Recommended for RimWorld",
            ]
        )
        # QComboBox alignment is hardcoded...? too lazy to override...
        # https://stackoverflow.com/questions/41497773/align-text-in-a-qcombobox-without-making-it-editable
        self.todds_presets_cb.setStyleSheet("QComboBox {" "   padding-left: 25px;" "}")
        self.todds_presets_cb.setItemDelegate(self.centered_item_delegate)
        self.todds_active_mods_target_checkbox = QCheckBox(
            "Force todds to only target mods in the active mods list"
        )
        self.todds_active_mods_target_checkbox.setToolTip(
            "If unchecked, todds will convert textures for all\n"
            + "applicable mods parsed from a mod data source."
        )
        self.todds_active_mods_target_checkbox.setObjectName("summaryValue")
        self.todds_dry_run_checkbox = QCheckBox(
            'Force todds to use a special "dry run" mode'
        )
        self.todds_dry_run_checkbox.setToolTip(
            "You can save this output to file using the action in the runner panel.\n"
            + "This will not write any changes to the disk, and is useful to get a list\n"
            + "of all input files that will be converted to .dds format by todds."
        )
        self.todds_dry_run_checkbox.setObjectName("summaryValue")
        self.todds_overwrite_checkbox = QCheckBox(
            "Force todds to overwrite existing optimized textures"
        )
        self.todds_overwrite_checkbox.setToolTip(
            "By default, if an optimized texture already exists,\n"
            + "but the existing texture is older than the input file,\n"
            + "it will be overwritten with a newly optimized texture.\n\n"
            + "This option will force all textures to be converted again."
        )
        self.todds_overwrite_checkbox.setObjectName("summaryValue")

        # Add layouts/widgets to layout
        self.layout.addWidget(self.general_label)
        self.layout.addLayout(self.general_options_layout)

        self.layout.addWidget(self.external_metadata_label)
        self.layout.addLayout(self.metadata_options_layout)

        self.layout.addWidget(self.sorting_algorithm_label)
        self.layout.addWidget(self.sorting_algorithm_cb)

        self.layout.addWidget(self.steamcmd_label)
        self.layout.addWidget(self.steamcmd_validate_downloads_checkbox)

        self.layout.addWidget(self.todds_label)
        self.todds_preset_layout.addWidget(self.todds_preset_label, 0)
        self.todds_preset_layout.addWidget(self.todds_presets_cb, 10)
        self.layout.addLayout(self.todds_preset_layout)
        self.layout.addWidget(self.todds_active_mods_target_checkbox)
        self.layout.addWidget(self.todds_dry_run_checkbox)
        self.layout.addWidget(self.todds_overwrite_checkbox)

        # Display items
        self.setLayout(self.layout)

        logger.debug("Finished SettingsPanel initialization")

    def buildDatabaseBtnContextMenuEvent(self, point: QPoint) -> None:
        contextMenu = QMenu(self)  # Build Database btn context menu event
        merge_databases = contextMenu.addAction(
            "Merge Steam databases"
        )  # merge databases
        set_database_expiry = contextMenu.addAction(
            "Set database expiry"
        )  # db builder expiry
        set_steam_apikey = contextMenu.addAction(
            "Set Steam WebAPI key"
        )  # steam API-key
        merge_databases.triggered.connect(
            partial(self.actions_signal.emit, "merge_databases")
        )
        set_database_expiry.triggered.connect(
            partial(self.actions_signal.emit, "set_database_expiry")
        )
        set_steam_apikey.triggered.connect(
            partial(self.actions_signal.emit, "edit_steam_webapi_key")
        )
        action = contextMenu.exec_(self.build_steam_database_button.mapToGlobal(point))

    def downloadAllModsContextMenuEvent(self, point: QPoint) -> None:
        contextMenu = QMenu(self)  # Download all mods btn context menu event
        download_with_steamcmd = contextMenu.addAction(
            "Download with SteamCMD"
        )  # steamcmd
        download_with_steamworks = contextMenu.addAction(
            "Download with Steam client"
        )  # steamworks
        download_with_steamcmd.triggered.connect(
            partial(
                self.actions_signal.emit,
                "download_entire_workshop_steamcmd",
            )
        )
        download_with_steamworks.triggered.connect(
            partial(
                self.actions_signal.emit,
                "download_entire_workshop_steamworks",
            )
        )
        action = contextMenu.exec_(self.download_all_mods_btn.mapToGlobal(point))

    def externalSteamDbBtnContextMenuEvent(self, point: QPoint) -> None:
        contextMenu = QMenu(self)  # Build Database btn context menu event
        config_steam_db_path = contextMenu.addAction(
            "Configure Steam Database file path"
        )  # configure file path
        config_steam_db_repo = contextMenu.addAction(
            "Configure Steam Database repository"
        )  # configure repo URL
        download_steam_db = contextMenu.addAction(
            "Download Steam Database from repository"
        )  # download db from repo
        upload_steam_db_changes = contextMenu.addAction(
            "Upload Steam Database changes to repository"
        )  # make pull request with changes
        # ACTIONS
        config_steam_db_path.triggered.connect(
            partial(self.actions_signal.emit, "configure_steam_database_path")
        )
        config_steam_db_repo.triggered.connect(
            partial(self.actions_signal.emit, "configure_steam_database_repo")
        )
        download_steam_db.triggered.connect(
            partial(self.actions_signal.emit, "download_steam_database")
        )
        upload_steam_db_changes.triggered.connect(
            partial(self.actions_signal.emit, "upload_steam_database")
        )
        action = contextMenu.exec_(
            self.external_steam_metadata_button.mapToGlobal(point)
        )

    def externalCommunityRulesDbBtnContextMenuEvent(self, point: QPoint) -> None:
        contextMenu = QMenu(self)  # Build Database btn context menu event
        config_community_rules_db_path = contextMenu.addAction(
            "Configure Community Rules Database file path"
        )  # configure file path
        config_community_rules_db_repo = contextMenu.addAction(
            "Configure Community Rules Database repository"
        )  # configure repo URL
        download_community_rules_db = contextMenu.addAction(
            "Download/Update Community Rules Database from repository"
        )  # download db from repo
        open_rule_editor = contextMenu.addAction(
            "Open Community Rules Database with Rule Editor"
        )
        upload_community_rules_changes = contextMenu.addAction(
            "Upload Community Rules Database changes to repository"
        )  # make pull request with changes
        # ACTIONS
        config_community_rules_db_path.triggered.connect(
            partial(
                self.actions_signal.emit,
                "configure_community_rules_db_path",
            )
        )
        config_community_rules_db_repo.triggered.connect(
            partial(
                self.actions_signal.emit,
                "configure_community_rules_db_repo",
            )
        )
        download_community_rules_db.triggered.connect(
            partial(
                self.actions_signal.emit,
                "download_community_rules_database",
            )
        )
        open_rule_editor.triggered.connect(
            partial(
                self.actions_signal.emit,
                "open_community_rules_with_rule_editor",
            )
        )
        upload_community_rules_changes.triggered.connect(
            partial(
                self.actions_signal.emit,
                "upload_community_rules_database",
            )
        )
        action = contextMenu.exec_(
            self.external_community_rules_metadata_button.mapToGlobal(point)
        )

    def loggerDebugCheckboxEvent(self) -> None:
        data_path = str(
            Path(
                os.path.join(os.path.split(os.path.dirname(__file__))[0], "data")
            ).resolve()
        )
        debug_file = str(Path(os.path.join(data_path, "DEBUG")).resolve())
        if self.logger_debug_checkbox.isChecked():
            if not os.path.exists(debug_file):
                # Create an empty file
                with open(debug_file, "w"):
                    pass
        else:
            if os.path.exists(debug_file):
                os.remove(debug_file)
