import os
from functools import partial

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyledItemDelegate,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from app.models.multibutton import MultiButton
from app.utils.app_info import AppInfo
from app.utils.generic import platform_specific_open


class CenteredItemDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignCenter


class SettingsPanel(QDialog):
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

        # Create tabs
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        self.__create_general_tab()
        self.__create_db_builder_tab()
        self.__create_steamcmd_tab()
        self.__create_todds_tab()
        # Display items
        self.setLayout(self.layout)

        logger.debug("Finished SettingsPanel initialization")

    def __create_general_tab(self) -> None:
        # General tab
        self.general_tab = QWidget()
        # General layouts
        self.general_options_layout = QVBoxLayout(self.general_tab)
        self.general_options_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.general_actions_layout = QHBoxLayout()
        self.general_preferences_layout = QVBoxLayout()
        # General widgets
        self.set_github_identity_button = QPushButton("Github identity")
        self.set_github_identity_button.clicked.connect(
            partial(self.actions_signal.emit, "configure_github_identity")
        )
        self.open_storage_action = QAction("Open RimSort storage")
        self.open_storage_action.triggered.connect(
            partial(
                platform_specific_open,
                self.storage_path,
            )
        )
        self.rimworld_woodlog_icon_path = str(
            str(AppInfo().theme_data_folder / "default-icons" / "WoodLog_a.png")
        )
        self.logger_debug_checkbox = QCheckBox(
            "Enable RimSort logger verbose DEBUG mode"
        )
        self.logger_debug_checkbox.setObjectName("summaryValue")
        self.logger_debug_checkbox.setToolTip(
            "If enabled, changes logger level from INFO to DEBUG, enabling us to\n"
            + "supply a multitude of information relevant to debugging if needed.\n\n"
            + "This option is applied on RimSort initialization."
        )
        self.logger_debug_checkbox.clicked.connect(self.__loggerDebugCheckboxEvent)
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
        self.general_actions_layout.addWidget(self.set_github_identity_button)
        self.general_preferences_layout.addWidget(self.logger_debug_checkbox)
        self.general_preferences_layout.addWidget(self.watchdog_checkbox)
        self.general_preferences_layout.addWidget(self.mod_type_filter_checkbox)
        self.general_preferences_layout.addWidget(self.duplicate_mods_checkbox)
        self.general_preferences_layout.addWidget(self.steam_mods_update_checkbox)
        self.general_preferences_layout.addWidget(
            self.try_download_missing_mods_checkbox
        )
        self.general_options_layout.addLayout(self.general_actions_layout)
        self.general_options_layout.addLayout(self.general_preferences_layout)

        # metadata layouts
        self.metadata_sorting_options_layout = QHBoxLayout()
        self.steam_metadata_configuration_layout = QVBoxLayout()
        self.community_rules_metadata_configuration_layout = QVBoxLayout()
        self.sorting_algorithm_configuration_layout = QVBoxLayout()
        # metadata / sorting widgets
        self.external_metadata_icon_path = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "database.png")
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
        self.general_options_layout.addLayout(self.metadata_sorting_options_layout)
        # Add General tab
        self.tabs.addTab(self.general_tab, "General")

    def __create_db_builder_tab(self) -> None:
        # DB Builder tab
        self.db_builder_tab = QWidget()
        # DB Builder layouts
        self.database_tools_layout = QVBoxLayout(self.db_builder_tab)
        self.database_tools_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.database_tools_builder_layout = QHBoxLayout()
        self.database_tools_actions_layout = QHBoxLayout()
        # DB Builder widgets
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
        self.build_steam_database_download_src_label = QLabel(
            "Download all published Workshop mods via:"
        )
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
        # Compose layout(s)
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
        # Add DB Builder tab
        self.tabs.addTab(self.db_builder_tab, "DB Builder")

    def __create_steamcmd_tab(self) -> None:
        # SteamCMD tab
        self.steamcmd_tab = QWidget()
        # SteamCMD tab layout
        self.steamcmd_tab_layout = QVBoxLayout(self.steamcmd_tab)
        self.steamcmd_tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        # SteamCMD tab widgets
        self.steamcmd_validate_downloads_checkbox = QCheckBox(
            "Force SteamCMD to validate downloaded workshop mods"
        )
        self.steamcmd_validate_downloads_checkbox.setObjectName("summaryValue")
        # Compose layout(s)
        self.steamcmd_tab_layout.addWidget(self.steamcmd_validate_downloads_checkbox)
        # Add SteamCMD tab
        self.tabs.addTab(self.steamcmd_tab, "SteamCMD")

    def __create_todds_tab(self) -> None:
        # todds tab
        self.todds_tab = QWidget()
        # todds tab layout
        self.todds_tab_layout = QVBoxLayout(self.todds_tab)
        self.todds_tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        # layout for Quality preset
        self.todds_preset_layout = QHBoxLayout()
        # todds widget(s)
        self.todds_preset_label = QLabel("Quality preset:")
        self.todds_preset_label.setObjectName("summaryValue")
        self.todds_presets_cb = QComboBox()
        self.todds_presets_cb.setObjectName("MainUI")
        self.todds_presets_cb.addItems(
            [
                "Optimized - Recommended for RimWorld",
            ]
        )
        self.todds_presets_cb.setObjectName("padInternal")
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
        # Compose layout(s)
        self.todds_preset_layout.addWidget(self.todds_preset_label, 0)
        self.todds_preset_layout.addWidget(self.todds_presets_cb, 10)
        self.todds_tab_layout.addLayout(self.todds_preset_layout)
        self.todds_tab_layout.addWidget(self.todds_active_mods_target_checkbox)
        self.todds_tab_layout.addWidget(self.todds_dry_run_checkbox)
        self.todds_tab_layout.addWidget(self.todds_overwrite_checkbox)
        # Add todds tab
        self.tabs.addTab(self.todds_tab, "todds")

    def __loggerDebugCheckboxEvent(self) -> None:
        debug_file = str((AppInfo.application_folder / "DEBUG"))
        if self.logger_debug_checkbox.isChecked():
            if not os.path.exists(debug_file):
                # Create an empty file
                with open(debug_file, "w", encoding="utf-8"):
                    pass
        else:
            if os.path.exists(debug_file):
                os.remove(debug_file)
