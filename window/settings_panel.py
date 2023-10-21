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
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
)

from model.dialogue import show_information
from model.multibutton import MultiButton
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
        self.general_label = QLabel("General options")
        self.general_label.setObjectName("summaryHeader")
        # Create a QFrame, styled to look like a horizontal line
        self.general_line = QFrame()
        self.general_line.setFixedHeight(1)
        self.general_line.setFrameShape(QFrame.HLine)
        self.general_line.setFrameShadow(QFrame.Sunken)
        self.general_line.setObjectName("horizontalLine")
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

        # metadata layouts
        self.metadata_sorting_options_layout = QHBoxLayout()
        self.steam_metadata_configuration_layout = QVBoxLayout()
        self.community_rules_metadata_configuration_layout = QVBoxLayout()
        self.sorting_algorithm_configuration_layout = QVBoxLayout()
        # metadata / sorting widgets
        self.external_metadata_sorting_label = QLabel(
            "External metadata / sorting algorithm preferences"
        )
        self.external_metadata_sorting_label.setObjectName("summaryHeader")
        # Create a QFrame, styled to look like a horizontal line
        self.external_metadata_sorting_line = QFrame()
        self.external_metadata_sorting_line.setFixedHeight(1)
        self.external_metadata_sorting_line.setFrameShape(QFrame.HLine)
        self.external_metadata_sorting_line.setFrameShadow(QFrame.Sunken)
        self.external_metadata_sorting_line.setObjectName("horizontalLine")
        self.external_metadata_icon_path = QIcon(
            str(
                Path(
                    os.path.join(os.path.dirname(__file__), "../data/database.png")
                ).resolve()
            )
        )
        # external steam metadata
        self.external_steam_metadata_label = QLabel("Steam Workshop DB")
        self.external_steam_metadata_label.setObjectName("summaryValue")
        self.external_steam_metadata_label.setAlignment(Qt.AlignCenter)
        # external steam metadata multibutton
        self.external_steam_metadata_multibutton = MultiButton(
            main_action=[
                "None",
                "Configured file path",
                "Configured git repository",
            ],
            main_action_tooltip="Use menu to access Steam Workshop Database options",
            context_menu_content={
                "configure_steam_database_path": "Configure Steam Database file path",
                "configure_steam_database_repo": "Configure Steam Database repository",
                "download_steam_database": "Download Steam Database from repository",
                "upload_steam_database": "Upload Steam Database changes to repository",
            },
            actions_signal=self.actions_signal,
            secondary_action_icon_path=self.external_metadata_icon_path,
        )
        self.external_steam_metadata_multibutton.main_action.setItemDelegate(
            self.centered_item_delegate
        )
        # external community rules metadata
        self.external_community_rules_metadata_label = QLabel("Community Rules DB")
        self.external_community_rules_metadata_label.setObjectName("summaryValue")
        self.external_community_rules_metadata_label.setAlignment(Qt.AlignCenter)
        # external community rules metadata multibutton
        self.external_community_rules_metadata_multibutton = MultiButton(
            main_action=[
                "None",
                "Configured file path",
                "Configured git repository",
            ],
            main_action_tooltip="Use menu to access Community Rules Database options",
            context_menu_content={
                "configure_community_rules_db_path": "Configure Community Rules Database file path",
                "configure_community_rules_db_repo": "Configure Community Rules Database repository",
                "download_community_rules_database": "Download/Update Community Rules Database from repository",
                "open_community_rules_with_rule_editor": "Open Community Rules Database with Rule Editor",
                "upload_community_rules_database": "Upload Community Rules Database changes to repository",
            },
            actions_signal=self.actions_signal,
            secondary_action_icon_path=self.external_metadata_icon_path,
        )
        self.external_community_rules_metadata_multibutton.main_action.setItemDelegate(
            self.centered_item_delegate
        )
        # sorting algorithm
        self.sorting_algorithm_label = QLabel("Sorting Algorithm")
        self.sorting_algorithm_label.setObjectName("summaryValue")
        self.sorting_algorithm_label.setAlignment(Qt.AlignCenter)
        self.sorting_algorithm_cb = QComboBox()
        self.sorting_algorithm_cb.setObjectName("MainUI")
        self.sorting_algorithm_cb.addItems(["Alphabetical", "Topological"])
        self.sorting_algorithm_cb.setItemDelegate(self.centered_item_delegate)
        # Build the metadata / sorting options layout
        self.steam_metadata_configuration_layout.addWidget(
            self.external_steam_metadata_label
        )
        self.steam_metadata_configuration_layout.addWidget(
            self.external_steam_metadata_multibutton
        )
        self.community_rules_metadata_configuration_layout.addWidget(
            self.external_community_rules_metadata_label
        )
        self.community_rules_metadata_configuration_layout.addWidget(
            self.external_community_rules_metadata_multibutton
        )
        self.sorting_algorithm_configuration_layout.addWidget(
            self.sorting_algorithm_label
        )
        self.sorting_algorithm_configuration_layout.addWidget(self.sorting_algorithm_cb)
        self.metadata_sorting_options_layout.addLayout(
            self.steam_metadata_configuration_layout
        )
        self.metadata_sorting_options_layout.addLayout(
            self.community_rules_metadata_configuration_layout
        )
        self.metadata_sorting_options_layout.addLayout(
            self.sorting_algorithm_configuration_layout
        )

        # db builder layouts
        self.database_tools_layout = QVBoxLayout()
        self.database_tools_builder_layout = QHBoxLayout()
        self.database_tools_actions_layout = QHBoxLayout()
        # db builder widgets
        self.build_steam_database_label = QLabel("Steam DB Builder options:")
        self.build_steam_database_label.setObjectName("summaryHeader")
        # Create a QFrame, styled to look like a horizontal line
        self.build_steam_database_line = QFrame()
        self.build_steam_database_line.setFixedHeight(1)
        self.build_steam_database_line.setFrameShape(QFrame.HLine)
        self.build_steam_database_line.setFrameShadow(QFrame.Sunken)
        self.build_steam_database_line.setObjectName("horizontalLine")
        self.build_steam_database_include_label = QLabel("Include local metadata:")
        self.build_steam_database_include_label.setObjectName("summaryValue")
        self.build_steam_database_include_label.setAlignment(Qt.AlignCenter)
        self.build_steam_database_include_cb = QComboBox()
        self.build_steam_database_include_cb.setObjectName("MainUI")
        self.build_steam_database_include_cb.addItems(["No", "Yes"])
        self.build_steam_database_include_cb.setItemDelegate(
            self.centered_item_delegate
        )
        self.build_steam_database_multibutton = MultiButton(
            main_action="Build database",
            main_action_tooltip="Use menu to access additional options:"
            + "\n\n- Compare dependencies found in 2 provided SteamDB"
            + "\n- Merge 2 SteamDBs recursively"
            + "\n- Set SteamDB expiry"
            + "\n- Set Steam WebAPI key"
            + '\n\nPlease consult the "User Guide" on the RimSort wiki'
            + "\n\nDB Builder at a minimum requires:"
            + "\n- A live Internet connection"
            + "\n- A Steam WebAPI key configured",
            context_menu_content={
                "comparison_report": "Compare dependencies found in 2 provided SteamDB",
                "merge_databases": "Merge 2 SteamDBs recursively",
                "set_database_expiry": "Set SteamDB expiry",
                "edit_steam_webapi_key": "Set Steam WebAPI key",
            },
            actions_signal=self.actions_signal,
        )
        self.build_steam_database_multibutton.main_action.clicked.connect(
            partial(self.actions_signal.emit, "build_steam_database_thread")
        )
        self.build_steam_database_dlc_data_checkbox = QCheckBox(
            "Query DLC dependency data with Steamworks API"
        )
        self.build_steam_database_dlc_data_checkbox.setToolTip(
            "Requires:\n"
            + "- A live Internet connection\n"
            + "- An online Steam client with RimWorld purchased & present in library"
        )
        self.build_steam_database_dlc_data_checkbox.setObjectName("summaryValue")
        self.build_steam_database_update_checkbox = QCheckBox(
            "Update database instead of overwriting if it exists"
        )
        self.build_steam_database_update_checkbox.setToolTip(
            "If the designated database exists, update it instead of overwriting it."
        )
        self.build_steam_database_update_checkbox.setObjectName("summaryValue")
        # scraping options
        self.build_steam_database_download_label = QLabel(
            "Steam Workshop mod scraping options:"
        )
        self.build_steam_database_download_label.setObjectName("summaryValue")
        self.build_steam_database_download_label.setAlignment(Qt.AlignCenter)
        self.build_steam_database_download_src_label = QLabel("Download all mods via:")
        self.build_steam_database_download_src_label.setObjectName("summaryValue")
        self.build_steam_database_download_src_label.setAlignment(Qt.AlignCenter)
        self.build_steam_database_download_all_steamcmd = QPushButton("SteamCMD")
        self.build_steam_database_download_all_steamcmd.setToolTip(
            "Scrape Steam Workshop and download all published mods with SteamCMD"
        )
        self.build_steam_database_download_all_steamcmd.clicked.connect(
            partial(self.actions_signal.emit, "download_entire_workshop_steamcmd")
        )
        self.build_steam_database_download_all_steam = QPushButton("Steam")
        self.build_steam_database_download_all_steam.setToolTip(
            "Scrape Steam Workshop and download all published mods with Steam client"
        )
        self.build_steam_database_download_all_steam.clicked.connect(
            partial(self.actions_signal.emit, "download_entire_workshop_steamworks")
        )
        # build the DB Builder layouts
        self.database_tools_builder_layout.addWidget(
            self.build_steam_database_include_label
        )
        self.database_tools_builder_layout.addWidget(
            self.build_steam_database_include_cb
        )
        self.database_tools_builder_layout.addWidget(
            self.build_steam_database_multibutton
        )
        self.database_tools_layout.addLayout(self.database_tools_builder_layout)
        self.database_tools_layout.addWidget(
            self.build_steam_database_dlc_data_checkbox
        )
        self.database_tools_layout.addWidget(self.build_steam_database_update_checkbox)
        self.database_tools_layout.addWidget(self.build_steam_database_download_label)
        self.database_tools_actions_layout.addWidget(
            self.build_steam_database_download_src_label
        )
        self.database_tools_actions_layout.addWidget(
            self.build_steam_database_download_all_steamcmd
        )
        self.database_tools_actions_layout.addWidget(
            self.build_steam_database_download_all_steam
        )
        self.database_tools_layout.addLayout(self.database_tools_actions_layout)

        # steamcmd
        self.steamcmd_label = QLabel("SteamCMD options")
        self.steamcmd_label.setObjectName("summaryHeader")
        # Create a QFrame, styled to look like a horizontal line
        self.steamcmd_line = QFrame()
        self.steamcmd_line.setFixedHeight(1)
        self.steamcmd_line.setFrameShape(QFrame.HLine)
        self.steamcmd_line.setFrameShadow(QFrame.Sunken)
        self.steamcmd_line.setObjectName("horizontalLine")
        self.steamcmd_validate_downloads_checkbox = QCheckBox(
            "Force SteamCMD to validate downloaded workshop mods"
        )
        self.steamcmd_validate_downloads_checkbox.setObjectName("summaryValue")
        # todds
        self.todds_label = QLabel("todds Options")
        self.todds_label.setObjectName("summaryHeader")
        # Create a QFrame, styled to look like a horizontal line
        self.todds_line = QFrame()
        self.todds_line.setFixedHeight(1)
        self.todds_line.setFrameShape(QFrame.HLine)
        self.todds_line.setFrameShadow(QFrame.Sunken)
        self.todds_line.setObjectName("horizontalLine")
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
        self.layout.addWidget(self.general_line)
        self.layout.addLayout(self.general_options_layout)
        # self.layout.addWidget(self.external_metadata_sorting_label)
        # self.layout.addWidget(self.external_metadata_sorting_line)
        self.layout.addLayout(self.metadata_sorting_options_layout)
        self.layout.addWidget(self.steamcmd_label)
        self.layout.addWidget(self.steamcmd_line)
        self.layout.addWidget(self.steamcmd_validate_downloads_checkbox)
        self.layout.addWidget(self.build_steam_database_label)
        self.layout.addWidget(self.build_steam_database_line)
        self.layout.addLayout(self.database_tools_layout)
        self.layout.addWidget(self.todds_label)
        self.layout.addWidget(self.todds_line)
        self.todds_preset_layout.addWidget(self.todds_preset_label, 0)
        self.todds_preset_layout.addWidget(self.todds_presets_cb, 10)
        self.layout.addLayout(self.todds_preset_layout)
        self.layout.addWidget(self.todds_active_mods_target_checkbox)
        self.layout.addWidget(self.todds_dry_run_checkbox)
        self.layout.addWidget(self.todds_overwrite_checkbox)

        # Display items
        self.setLayout(self.layout)

        logger.debug("Finished SettingsPanel initialization")

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
