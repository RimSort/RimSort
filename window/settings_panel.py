from functools import partial
from logger_tt import logger
import os
from pathlib import Path
import sys
from tempfile import gettempdir

from PySide6.QtCore import QPoint, QSize, QStandardPaths, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QStyledItemDelegate,
    QVBoxLayout,
)

from util.generic import platform_specific_open, upload_data_to_0x0_st


class CenteredItemDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignCenter


class SettingsPanel(QDialog):
    clear_paths_signal = Signal(str)
    settings_panel_actions_signal = Signal(str)

    def __init__(self, storage_path: str) -> None:
        logger.info("Starting SettingsPanel initialization")
        super(SettingsPanel, self).__init__()

        self.storage_path = storage_path

        # Create window
        self.setFixedSize(QSize(500, 525))
        self.setWindowTitle("Settings")

        # Allow for styling
        self.centered_item_delegate = CenteredItemDelegate()
        self.setObjectName("settingsPanel")

        # Create main layout
        self.layout = QVBoxLayout()
        self.layout.setAlignment(Qt.AlignTop)

        # General layouts
        self.general_options_layout = QHBoxLayout()
        self.general_actions_layout = QVBoxLayout()
        self.general_preferences_layout = QVBoxLayout()
        # General widgets
        self.general_label = QLabel("General")
        self.general_label.setObjectName("summaryValue")
        self.general_label.setAlignment(Qt.AlignCenter)
        self.rimsort_actions_label = QLabel("RimSort Actions:")
        self.rimsort_actions_label.setObjectName("summaryValue")
        self.rimsort_actions_label.setAlignment(Qt.AlignCenter)
        self.clear_paths_button = QPushButton("Clear Paths")
        self.clear_paths_button.clicked.connect(
            partial(self.clear_paths_signal.emit, "clear_paths")
        )
        self.open_log_button = QPushButton("Open RimSort Log")
        self.open_log_button.clicked.connect(
            partial(
                platform_specific_open,
                os.path.join(gettempdir(), "RimSort.log"),
            )
        )
        self.upload_log_button = QPushButton("Upload RimSort Log")
        self.upload_log_button.setToolTip(
            "Log will be uploaded to http://0x0.st/ and\n"
            + "the URL will be copied to your clipboard."
        )
        self.upload_log_button.clicked.connect(
            partial(
                upload_data_to_0x0_st,
                os.path.join(gettempdir(), "RimSort.log"),
            )
        )
        self.open_storage_button = QPushButton("Open Storage Dir")
        self.open_storage_button.clicked.connect(
            partial(
                platform_specific_open,
                self.storage_path,
            )
        )
        self.rimsort_options_label = QLabel("RimSort Options:")
        self.rimsort_options_label.setObjectName("summaryValue")
        self.rimsort_options_label.setAlignment(Qt.AlignCenter)
        self.logger_debug_checkbox = QCheckBox(
            "Enable RimSort logger verbose DEBUG mode"
        )
        self.logger_debug_checkbox.setObjectName("summaryValue")
        self.logger_debug_checkbox.setToolTip(
            "If enabled, changes logger level from INFO to DEBUG, enabling us to supply\n"
            + "a multitude of information relevant to debugging if needed.\n\n"
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
        self.duplicate_mods_checkbox = QCheckBox(
            "Show duplicate mods check UI warning on refresh"
        )
        self.duplicate_mods_checkbox.setObjectName("summaryValue")
        self.steam_mods_update_checkbox = QCheckBox(
            "Show Steam mods check + UI warning on refresh"
        )
        self.steam_mods_update_checkbox.setObjectName("summaryValue")
        self.steam_mods_update_checkbox.setToolTip(
            "This option requires you to have a Steam apikey configured with\n"
            + 'the below "Metadata" option set to "RimSort Dynamic Query"\n\n'
            + '"Metadata" should be set to RimPy MMDB when sorting for now.'
        )
        self.try_download_missing_mods_checkbox = QCheckBox(
            "Try to download missing mods when detected"
        )
        self.try_download_missing_mods_checkbox.setObjectName("summaryValue")
        self.try_download_missing_mods_checkbox.setToolTip(
            "This option will allow you to attempt to download any missing mods\n"
            + "detected when importing mods, or when the active mods list\n\n"
            + "is refreshed. Prompts a choice betwen SteamCMD and Steam client."
        )
        # Build the general options layout
        self.general_actions_layout.addWidget(self.rimsort_actions_label)
        self.general_actions_layout.addWidget(self.clear_paths_button)
        self.general_actions_layout.addWidget(self.open_log_button)
        self.general_actions_layout.addWidget(self.upload_log_button)
        self.general_actions_layout.addWidget(self.open_storage_button)
        self.general_preferences_layout.addWidget(self.rimsort_options_label)
        self.general_preferences_layout.addWidget(self.logger_debug_checkbox)
        self.general_preferences_layout.addWidget(self.watchdog_checkbox)
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
        self.sorting_algorithm_cb.addItems(["RimPy", "Topological"])
        self.sorting_algorithm_cb.setItemDelegate(self.centered_item_delegate)

        # metadata layouts
        self.metadata_options_layout = QHBoxLayout()
        self.metadata_configuration_layout = QVBoxLayout()
        self.database_tools_layout = QVBoxLayout()
        self.database_tools_builder_layout = QHBoxLayout()
        self.database_tools_actions_layout = QHBoxLayout()
        # metadata widgets
        self.external_metadata_label = QLabel("External Metadata")
        self.external_metadata_label.setObjectName("summaryValue")
        self.external_metadata_label.setAlignment(Qt.AlignCenter)
        # external steam metadata
        self.external_steam_metadata_label = QLabel("Steam Workshop:")
        self.external_steam_metadata_label.setObjectName("summaryValue")
        self.external_steam_metadata_label.setAlignment(Qt.AlignCenter)
        self.external_steam_metadata_cb = QComboBox()
        self.external_steam_metadata_cb.addItems(
            ["RimPy Mod Manager Database", "RimSort Dynamic Query", "None"]
        )
        self.external_steam_metadata_cb.setItemDelegate(self.centered_item_delegate)
        # external community rules metadata
        self.external_community_rules_metadata_label = QLabel("Community Rules:")
        self.external_community_rules_metadata_label.setObjectName("summaryValue")
        self.external_community_rules_metadata_label.setAlignment(Qt.AlignCenter)
        self.external_community_rules_metadata_cb = QComboBox()
        self.external_community_rules_metadata_cb.addItems(
            ["RimPy Mod Manager Database", "None"]
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
        self.build_steam_database_include_cb.addItems(["No local data", "All Mods"])
        self.build_steam_database_include_cb.setItemDelegate(
            self.centered_item_delegate
        )
        self.build_steam_database_button = QPushButton("Build database")
        self.build_steam_database_button.setToolTip(
            "Right-click to set:\n"
            + "- Database expiry\n\tDefault: 1 week (604800 seconds)\n"
            + "- Steam WebAPI key\n\t"
            + "You can get this from Steam.\n\t"
            + 'Please consult the "User Guide" on the RimSort wiki\n\n'
            + "Requires: \n"
            + "- A live internet connection"
            + "-A Steam WebAPI key configured"
        )
        # Set context menu policy and connect custom context menu event
        self.build_steam_database_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.build_steam_database_button.customContextMenuRequested.connect(
            self.buildDatabaseBtnContextMenuEvent
        )
        self.build_steam_database_button.clicked.connect(
            partial(
                self.settings_panel_actions_signal.emit, "build_steam_database_thread"
            )
        )
        self.build_steam_database_dlc_data_checkbox = QCheckBox(
            "Include DLC dependency data in database"
        )
        self.build_steam_database_dlc_data_checkbox.setToolTip(
            "Requires:\n"
            + "- A live internet connection\n"
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
        self.comparison_report_button.clicked.connect(
            partial(self.settings_panel_actions_signal.emit, "comparison_report")
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
        self.metadata_configuration_layout.addWidget(self.external_steam_metadata_label)
        self.metadata_configuration_layout.addWidget(self.external_steam_metadata_cb)
        self.metadata_configuration_layout.addWidget(
            self.external_community_rules_metadata_label
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
        self.todds_presets_cb.addItems(
            [
                "Low quality (for low VRAM/older GPU, optimize for VRAM)",
                "High quality (default, good textures, long encode time)",
                "Very high quality (better textures, longer encode time)",
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

        logger.info("Finished SettingsPanel initialization")

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
        )  # steam webapi key
        merge_databases.triggered.connect(
            partial(self.settings_panel_actions_signal.emit, "merge_databases")
        )
        set_database_expiry.triggered.connect(
            partial(self.settings_panel_actions_signal.emit, "set_database_expiry")
        )
        set_steam_apikey.triggered.connect(
            partial(self.settings_panel_actions_signal.emit, "edit_steam_webapi_key")
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
                self.settings_panel_actions_signal.emit,
                "download_entire_workshop_steamcmd",
            )
        )
        download_with_steamworks.triggered.connect(
            partial(
                self.settings_panel_actions_signal.emit,
                "download_entire_workshop_steamworks",
            )
        )
        action = contextMenu.exec_(self.download_all_mods_btn.mapToGlobal(point))

    def loggerDebugCheckboxEvent(self) -> None:
        data_path = os.path.join(os.path.dirname(__file__), "../data")
        debug_file = os.path.join(data_path, "DEBUG")
        if self.logger_debug_checkbox.isChecked():
            if not os.path.exists(debug_file):
                # Create an empty file
                with open(debug_file, "w"):
                    pass
        else:
            if os.path.exists(debug_file):
                os.remove(debug_file)
