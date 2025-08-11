from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QDialog,
    QFontComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.settings import Settings
from app.utils.gui_info import GUIInfo


class SettingsDialog(QDialog):
    """
    Dialog for application settings, organized into tabs.
    Provides UI elements for all settings categories.
    """

    def __init__(self) -> None:
        super().__init__()

        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self.setWindowTitle(self.tr("Settings"))
        self.setObjectName("settingsPanel")

        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Initialize the tabs
        self._init_tabs()

        # Bottom buttons layout
        button_layout = QHBoxLayout()
        main_layout.addLayout(button_layout)

        # Reset to defaults button
        self.global_reset_to_defaults_button = QPushButton(
            self.tr("Reset to Defaults"), self
        )
        button_layout.addWidget(self.global_reset_to_defaults_button)

        button_layout.addStretch()

        # Cancel button
        self.global_cancel_button = QPushButton(self.tr("Cancel"), self)
        button_layout.addWidget(self.global_cancel_button)

        # OK button
        self.global_ok_button = QPushButton(self.tr("OK"), self)
        self.global_ok_button.setDefault(True)
        button_layout.addWidget(self.global_ok_button)

    def _init_tabs(self) -> None:
        """Initialize all tabs in the settings dialog."""
        self._do_locations_tab()
        self._do_databases_tab()
        self._do_cross_version_databases_tab()
        self._do_sorting_tab()
        self._do_db_builder_tab()
        self._do_steamcmd_tab()
        self._do_todds_tab()
        self._do_themes_tab()
        self._do_launch_state_tab()
        self._do_authentication_tab()
        self._do_aux_db_settings_tab()
        self._do_advanced_tab()

    def _do_locations_tab(self) -> None:
        tab = QWidget()
        self.tab_widget.addTab(tab, self.tr("Locations"))

        tab_layout = QVBoxLayout(tab)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._do_game_location_area(tab_layout)
        self._do_config_folder_location_area(tab_layout)
        self._do_steam_mods_folder_location_area(tab_layout)
        self._do_local_mods_folder_location_area(tab_layout)

        # Set the tab order:
        # "Game location" → "Config location" → "Steam mods location" → "Local mods location"
        self.setTabOrder(self.game_location, self.config_folder_location)
        self.setTabOrder(self.config_folder_location, self.steam_mods_folder_location)
        self.setTabOrder(
            self.steam_mods_folder_location, self.local_mods_folder_location
        )

        # Push the buttons to the bottom
        tab_layout.addStretch()

        # Create a QHBoxLayout for the buttons
        buttons_layout = QHBoxLayout()
        tab_layout.addLayout(buttons_layout)

        # Push the buttons as far as possible to the right
        buttons_layout.addStretch()

        # "Clear" button"
        self.locations_clear_button = QPushButton(self.tr("Clear All Locations"), tab)
        buttons_layout.addWidget(self.locations_clear_button)

        # "Autodetect" button
        self.locations_autodetect_button = QPushButton(self.tr("Autodetect"), tab)
        buttons_layout.addWidget(self.locations_autodetect_button)

    def _do_game_location_area(self, tab_layout: QVBoxLayout) -> None:
        group_box = QGroupBox()
        tab_layout.addWidget(group_box)

        group_layout = QVBoxLayout(group_box)

        header_layout = QHBoxLayout()
        group_layout.addLayout(header_layout)

        section_label = QLabel(self.tr("Game location"))
        section_label.setFont(GUIInfo().emphasis_font)
        header_layout.addWidget(section_label)

        self.game_location_open_button = QToolButton()
        self.game_location_open_button.setText(self.tr("Open…"))
        header_layout.addWidget(self.game_location_open_button)

        self.game_location_choose_button = QToolButton()
        self.game_location_choose_button.setText(self.tr("Choose…"))
        header_layout.addWidget(self.game_location_choose_button)

        self.game_location_clear_button = QToolButton()
        self.game_location_clear_button.setText(self.tr("Clear…"))
        header_layout.addWidget(self.game_location_clear_button)

        self.game_location = QLineEdit()
        self.game_location.setPlaceholderText(
            self.tr(
                r"Should be like: C:\Program Files (x86)\Steam\steamapps\common\RimWorld"
            )
        )
        self.game_location.setTextMargins(GUIInfo().text_field_margins)
        self.game_location.setFixedHeight(GUIInfo().default_font_line_height * 2)
        group_layout.addWidget(self.game_location)

    def _do_config_folder_location_area(self, tab_layout: QVBoxLayout) -> None:
        group_box = QGroupBox()
        tab_layout.addWidget(group_box)

        group_layout = QVBoxLayout(group_box)

        header_layout = QHBoxLayout()
        group_layout.addLayout(header_layout)

        section_label = QLabel(self.tr("Config location"))
        section_label.setFont(GUIInfo().emphasis_font)
        header_layout.addWidget(section_label)

        self.config_folder_location_open_button = QToolButton()
        self.config_folder_location_open_button.setText(self.tr("Open…"))
        header_layout.addWidget(self.config_folder_location_open_button)

        self.config_folder_location_choose_button = QToolButton()
        self.config_folder_location_choose_button.setText(self.tr("Choose…"))
        header_layout.addWidget(self.config_folder_location_choose_button)

        self.config_folder_location_clear_button = QToolButton()
        self.config_folder_location_clear_button.setText(self.tr("Clear…"))
        header_layout.addWidget(self.config_folder_location_clear_button)

        self.config_folder_location = QLineEdit()
        self.config_folder_location.setPlaceholderText(
            self.tr(
                r"Should be like: C:\Users\UserName\AppData\LocalLow\Ludeon Studios\RimWorld by Ludeon Studios\Config"
            )
        )
        self.config_folder_location.setTextMargins(GUIInfo().text_field_margins)
        self.config_folder_location.setFixedHeight(
            GUIInfo().default_font_line_height * 2
        )
        group_layout.addWidget(self.config_folder_location)

    def _do_steam_mods_folder_location_area(self, tab_layout: QVBoxLayout) -> None:
        group_box = QGroupBox()
        tab_layout.addWidget(group_box)

        group_layout = QVBoxLayout(group_box)

        header_layout = QHBoxLayout()
        group_layout.addLayout(header_layout)

        section_label = QLabel(self.tr("Steam mods location"))
        section_label.setFont(GUIInfo().emphasis_font)
        header_layout.addWidget(section_label)

        self.steam_mods_folder_location_open_button = QToolButton()
        self.steam_mods_folder_location_open_button.setText(self.tr("Open…"))
        header_layout.addWidget(self.steam_mods_folder_location_open_button)

        self.steam_mods_folder_location_choose_button = QToolButton()
        self.steam_mods_folder_location_choose_button.setText(self.tr("Choose…"))
        header_layout.addWidget(self.steam_mods_folder_location_choose_button)

        self.steam_mods_folder_location_clear_button = QToolButton()
        self.steam_mods_folder_location_clear_button.setText(self.tr("Clear…"))
        header_layout.addWidget(self.steam_mods_folder_location_clear_button)

        self.steam_mods_folder_location = QLineEdit()
        self.steam_mods_folder_location.setPlaceholderText(
            self.tr(
                r"Only if you use steam should be like: C:\Program Files (x86)\Steam\steamapps\workshop\content\294100"
            )
        )
        self.steam_mods_folder_location.setTextMargins(GUIInfo().text_field_margins)
        self.steam_mods_folder_location.setFixedHeight(
            GUIInfo().default_font_line_height * 2
        )
        group_layout.addWidget(self.steam_mods_folder_location)

    def _do_local_mods_folder_location_area(self, tab_layout: QVBoxLayout) -> None:
        group_box = QGroupBox()
        tab_layout.addWidget(group_box)

        group_layout = QVBoxLayout(group_box)

        header_layout = QHBoxLayout()
        group_layout.addLayout(header_layout)

        section_label = QLabel(self.tr("Local mods location"))
        section_label.setFont(GUIInfo().emphasis_font)
        header_layout.addWidget(section_label)

        self.local_mods_folder_location_open_button = QToolButton()
        self.local_mods_folder_location_open_button.setText(self.tr("Open…"))
        header_layout.addWidget(self.local_mods_folder_location_open_button)

        self.local_mods_folder_location_choose_button = QToolButton()
        self.local_mods_folder_location_choose_button.setText(self.tr("Choose…"))
        header_layout.addWidget(self.local_mods_folder_location_choose_button)

        self.local_mods_folder_location_clear_button = QToolButton()
        self.local_mods_folder_location_clear_button.setText(self.tr("Clear…"))
        header_layout.addWidget(self.local_mods_folder_location_clear_button)

        self.local_mods_folder_location = QLineEdit()
        self.local_mods_folder_location.setPlaceholderText(
            self.tr(
                r"should be like: C:\Program Files (x86)\Steam\steamapps\common\Rimworld\Mods"
            )
        )
        self.local_mods_folder_location.setTextMargins(GUIInfo().text_field_margins)
        self.local_mods_folder_location.setFixedHeight(
            GUIInfo().default_font_line_height * 2
        )
        group_layout.addWidget(self.local_mods_folder_location)

    def _do_databases_tab(self) -> None:
        tab = QWidget()
        self.tab_widget.addTab(tab, self.tr("Databases"))

        tab_layout = QVBoxLayout()
        tab.setLayout(tab_layout)

        self._do_community_rules_db_group(tab_layout)
        self._do_steam_workshop_db_group(tab_layout)

    def _do_cross_version_databases_tab(self) -> None:
        tab = QWidget()
        self.tab_widget.addTab(tab, self.tr("Additional Databases"))

        tab_layout = QVBoxLayout()
        tab.setLayout(tab_layout)

        self._do_no_version_warning_db_group(tab_layout)
        self._do_use_this_instead_db_group(tab_layout)

    def _do_aux_db_settings_tab(self) -> None:
        tab = QWidget()
        self.tab_widget.addTab(tab, self.tr("Auxiliary DB"))

        tab_layout = QVBoxLayout()
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        tab.setLayout(tab_layout)

        self._do_aux_db_time_limit_group(tab_layout)
        self._do_aux_db_performance_group(tab_layout)
        # New section for save-comparison feature
        self._do_recent_save_integration_group(tab_layout)

    def _do_recent_save_integration_group(self, tab_layout: QBoxLayout) -> None:
        section_label = QLabel(self.tr("Integration with recent save"))
        section_label.setFont(GUIInfo().emphasis_font)
        section_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tab_layout.addWidget(section_label)

        row_layout = QHBoxLayout()
        self.show_save_comparison_indicators_checkbox = QCheckBox(
            self.tr("Compare mod lists with the recent save file")
        )
        row_layout.addWidget(self.show_save_comparison_indicators_checkbox)
        tab_layout.addLayout(row_layout)

    def __create_db_group(
        self, section_lbl: str, none_lbl: str, tab_layout: QBoxLayout
    ) -> tuple[
        QVBoxLayout,
        QRadioButton,
        QRadioButton,
        QLineEdit,
        QToolButton,
        QToolButton,
        QRadioButton,
        QLineEdit,
        QToolButton,
    ]:
        group = QGroupBox()
        tab_layout.addWidget(group, stretch=1)

        group_layout = QVBoxLayout()
        group_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        group.setLayout(group_layout)

        section_label = QLabel(section_lbl)
        section_label.setFont(GUIInfo().emphasis_font)
        section_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        group_layout.addWidget(section_label)

        section_layout = QVBoxLayout()
        section_layout.setSpacing(0)
        group_layout.addLayout(section_layout)

        item_layout = QHBoxLayout()
        section_layout.addLayout(item_layout, stretch=1)

        none_radio = QRadioButton(self.tr("None"))
        none_radio.setMinimumSize(0, GUIInfo().default_font_line_height * 2)
        none_radio.setChecked(True)
        item_layout.addWidget(none_radio, stretch=2)

        label = QLabel(self.tr("No {none_lbl} will be used.").format(none_lbl=none_lbl))
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        label.setEnabled(False)
        item_layout.addWidget(label, stretch=8)

        item_layout = QHBoxLayout()
        section_layout.addLayout(item_layout, stretch=1)

        github_radio = QRadioButton(self.tr("GitHub"))
        github_radio.setMinimumSize(0, GUIInfo().default_font_line_height * 2)
        item_layout.addWidget(github_radio, stretch=2)

        row_layout = QHBoxLayout()
        row_layout.setSpacing(8)
        item_layout.addLayout(row_layout, stretch=8)

        github_url = QLineEdit()
        github_url.setFixedHeight(GUIInfo().default_font_line_height * 2)
        github_url.setTextMargins(GUIInfo().text_field_margins)
        github_url.setClearButtonEnabled(True)
        github_url.setEnabled(False)
        row_layout.addWidget(github_url)

        github_upload_button = QToolButton()
        github_upload_button.setText(self.tr("Upload…"))
        github_upload_button.setEnabled(False)
        row_layout.addWidget(github_upload_button)

        github_download_button = QToolButton()
        github_download_button.setText(self.tr("Download…"))
        github_download_button.setEnabled(False)
        row_layout.addWidget(github_download_button)

        item_layout = QHBoxLayout()
        section_layout.addLayout(item_layout, stretch=1)
        local_file_radio = QRadioButton(self.tr("Local File"))
        local_file_radio.setMinimumSize(0, GUIInfo().default_font_line_height * 2)
        item_layout.addWidget(local_file_radio, stretch=2)

        row_layout = QHBoxLayout()
        row_layout.setSpacing(8)
        item_layout.addLayout(row_layout, stretch=8)

        local_file = QLineEdit()
        local_file.setFixedHeight(GUIInfo().default_font_line_height * 2)
        local_file.setTextMargins(GUIInfo().text_field_margins)
        local_file.setClearButtonEnabled(True)
        local_file.setEnabled(False)
        row_layout.addWidget(local_file)

        local_file_choose_button = QToolButton()
        local_file_choose_button.setText(self.tr("Choose…"))
        local_file_choose_button.setEnabled(False)
        local_file_choose_button.setFixedWidth(
            github_download_button.sizeHint().width()
        )
        row_layout.addWidget(local_file_choose_button)

        section_layout.addStretch(1)

        item_layout = QHBoxLayout()
        section_layout.addLayout(item_layout, stretch=1)

        info_label = QLabel("")
        info_label.setWordWrap(True)
        item_layout.addWidget(info_label)

        return (
            group_layout,
            none_radio,
            github_radio,
            github_url,
            github_upload_button,
            github_download_button,
            local_file_radio,
            local_file,
            local_file_choose_button,
        )

    def _do_community_rules_db_group(self, tab_layout: QBoxLayout) -> None:
        section_lbl = self.tr("Community Rules database")
        none_lbl = self.tr("community rules database")

        (
            _,
            self.community_rules_db_none_radio,
            self.community_rules_db_github_radio,
            self.community_rules_db_github_url,
            self.community_rules_db_github_upload_button,
            self.community_rules_db_github_download_button,
            self.community_rules_db_local_file_radio,
            self.community_rules_db_local_file,
            self.community_rules_db_local_file_choose_button,
        ) = self.__create_db_group(section_lbl, none_lbl, tab_layout)

    def _do_steam_workshop_db_group(self, tab_layout: QBoxLayout) -> None:
        section_lbl = self.tr("Steam Workshop database")
        none_lbl = self.tr("Steam Workshop database")

        (
            group_layout,
            self.steam_workshop_db_none_radio,
            self.steam_workshop_db_github_radio,
            self.steam_workshop_db_github_url,
            self.steam_workshop_db_github_upload_button,
            self.steam_workshop_db_github_download_button,
            self.steam_workshop_db_local_file_radio,
            self.steam_workshop_db_local_file,
            self.steam_workshop_db_local_file_choose_button,
        ) = self.__create_db_group(section_lbl, none_lbl, tab_layout)
        database_expiry_label = QLabel(
            self.tr(
                "Database expiry in seconds for example, 604800 for 7 days. and 0 for no expiry."
            )
        )
        database_expiry_label.setFont(GUIInfo().emphasis_font)
        group_layout.addWidget(database_expiry_label)

        self.database_expiry = QLineEdit()
        self.database_expiry.setTextMargins(GUIInfo().text_field_margins)
        self.database_expiry.setFixedHeight(GUIInfo().default_font_line_height * 2)
        group_layout.addWidget(self.database_expiry)

    def _do_no_version_warning_db_group(self, tab_layout: QBoxLayout) -> None:
        section_lbl = self.tr('"No Version Warning" Database')
        none_lbl = self.tr('"No Version Warning" Database')
        (
            _,
            self.no_version_warning_db_none_radio,
            self.no_version_warning_db_github_radio,
            self.no_version_warning_db_github_url,
            self.no_version_warning_db_github_upload_button,
            self.no_version_warning_db_github_download_button,
            self.no_version_warning_db_local_file_radio,
            self.no_version_warning_db_local_file,
            self.no_version_warning_db_local_file_choose_button,
        ) = self.__create_db_group(section_lbl, none_lbl, tab_layout)

    def _do_use_this_instead_db_group(self, tab_layout: QBoxLayout) -> None:
        section_lbl = self.tr('"Use This Instead" Database')
        none_lbl = self.tr('"Use This Instead" Database')
        (
            _,
            self.use_this_instead_db_none_radio,
            self.use_this_instead_db_github_radio,
            self.use_this_instead_db_github_url,
            self.use_this_instead_db_github_upload_button,
            self.use_this_instead_db_github_download_button,
            self.use_this_instead_db_local_file_radio,
            self.use_this_instead_db_local_file,
            self.use_this_instead_db_local_file_choose_button,
        ) = self.__create_db_group(section_lbl, none_lbl, tab_layout)

    def _do_aux_db_time_limit_group(self, tab_layout: QBoxLayout) -> None:
        self.aux_db_time_limit_label = QLabel(
            self.tr(
                "Auxiliary Metadata DB deletion time limit in seconds. (Delete instantly 0, Never Delete -1)"
            )
        )
        aux_db_tooltip = self.tr("""To enable editing of this time limit, check the relevant checkbox in Advanced settings.
After a mod is deleted, this is the time we wait until this mod item is deleted from the Auxiliary Metadata DB. 
This Auxiliary DB contains info for mod colors, toggled warning, user notes etc. 
This basically preserves your mod coloring, user notes etc. for this many seconds after deletion. 
(This applies to deletion outside of RimSort too)""")
        self.aux_db_time_limit_label.setToolTip(aux_db_tooltip)
        self.aux_db_time_limit_label.setFont(GUIInfo().emphasis_font)

        self.aux_db_time_limit = QLineEdit()
        int_validator = QIntValidator()
        self.aux_db_time_limit.setValidator(int_validator)
        self.aux_db_time_limit.setTextMargins(GUIInfo().text_field_margins)
        self.aux_db_time_limit.setFixedHeight(GUIInfo().default_font_line_height * 2)

        self.enable_aux_db_behavior_editing = QCheckBox(self.tr("Enable editing"))
        self.enable_aux_db_behavior_editing.stateChanged.connect(
            self.enable_aux_db_time_limit_line_edit
        )
        self.enable_aux_db_behavior_editing.setToolTip(
            self.tr(
                "This enables the editing of the time limit for Aux Metadata DB data deletion."
            )
        )

        label_layout = QHBoxLayout()
        label_layout.addWidget(self.aux_db_time_limit_label)
        label_layout.addStretch()
        label_layout.addWidget(self.enable_aux_db_behavior_editing)

        tab_layout.addLayout(label_layout)
        tab_layout.addWidget(self.aux_db_time_limit)

    def _do_aux_db_performance_group(self, tab_layout: QBoxLayout) -> None:
        self.aux_db_performance_mode = QCheckBox(
            self.tr("Enable Auxiliary Metadata DB performance mode")
        )
        self.aux_db_performance_mode.setToolTip(
            self.tr(
                "This improves Auxiliary DB performance at the increased risk of data loss/corruption in the event of crashes."
                "\nImproves performance by ~50%."
            )
        )

        aux_db_group = QHBoxLayout()
        aux_db_group.addWidget(self.aux_db_performance_mode)

        tab_layout.addLayout(aux_db_group)

    def _do_sorting_tab(self) -> None:
        tab = QWidget()
        self.tab_widget.addTab(tab, self.tr("Sorting"))

        tab_layout = QVBoxLayout(tab)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Sort mods group
        sort_group_box = QGroupBox()
        tab_layout.addWidget(sort_group_box)

        sort_group_box_layout = QVBoxLayout()
        sort_group_box.setLayout(sort_group_box_layout)

        sorting_label = QLabel(self.tr("Sort mods"))
        sorting_label.setFont(GUIInfo().emphasis_font)
        sort_group_box_layout.addWidget(sorting_label)

        self.sorting_alphabetical_radio = QRadioButton(self.tr("Alphabetically"))
        sort_group_box_layout.addWidget(self.sorting_alphabetical_radio)

        self.sorting_topological_radio = QRadioButton(self.tr("Topologically"))
        sort_group_box_layout.addWidget(self.sorting_topological_radio)

        # Use dependencies for sorting checkbox
        self.use_moddependencies_as_loadTheseBefore = QCheckBox(
            self.tr("Use dependency rules for sorting.")
        )
        self.use_moddependencies_as_loadTheseBefore.setToolTip(
            self.tr(
                "If enabled, also uses moddependencies as loadTheseBefore, and mods will be sorted such that dependencies are loaded before the dependent mod."
            )
        )
        sort_group_box_layout.addWidget(self.use_moddependencies_as_loadTheseBefore)

        # Dependencies group
        deps_group_box = QGroupBox()
        tab_layout.addWidget(deps_group_box)

        deps_group_box_layout = QVBoxLayout()
        deps_group_box.setLayout(deps_group_box_layout)

        deps_label = QLabel(self.tr("Sort Dependencies"))
        deps_label.setFont(GUIInfo().emphasis_font)
        deps_group_box_layout.addWidget(deps_label)

        self.check_deps_checkbox = QCheckBox(
            self.tr("Prompt user to download dependencies when click in Sort")
        )
        deps_group_box_layout.addWidget(self.check_deps_checkbox)

        tab_layout.addStretch()

        explanatory_text = ""
        explanatory_label = QLabel(explanatory_text)
        explanatory_label.setWordWrap(True)
        tab_layout.addWidget(explanatory_label)

    def _do_db_builder_tab(self) -> None:
        tab = QWidget()
        self.tab_widget.addTab(tab, self.tr("DB Builder"))

        tab_layout = QVBoxLayout(tab)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # "When building the database:" radio buttons
        group_box = QGroupBox()
        tab_layout.addWidget(group_box)

        group_layout = QVBoxLayout()
        group_box.setLayout(group_layout)

        when_building_database_label = QLabel(self.tr("When building the database:"))
        when_building_database_label.setFont(GUIInfo().emphasis_font)
        group_layout.addWidget(when_building_database_label)

        self.db_builder_include_all_radio = QRadioButton(
            self.tr("Get PublishedFileIDs from locally installed mods.")
        )
        group_layout.addWidget(self.db_builder_include_all_radio)

        explanatory_label = QLabel(
            self.tr(
                "Mods you wish to update must be installed, "
                "as the initial DB is built including data from mods' About.xml files."
            )
        )
        group_layout.addWidget(explanatory_label)

        self.db_builder_include_no_local_radio = QRadioButton(
            self.tr("Get PublishedFileIDs from the Steam Workshop.")
        )
        group_layout.addWidget(self.db_builder_include_no_local_radio)

        explanatory_label = QLabel(
            self.tr(
                "Mods to be updated don't have to be installed, "
                "as the initial DB is built by scraping the Steam Workshop."
            )
        )
        group_layout.addWidget(explanatory_label)

        # Checkboxes
        group_box = QGroupBox()
        tab_layout.addWidget(group_box)

        group_layout = QVBoxLayout()
        group_box.setLayout(group_layout)

        self.db_builder_query_dlc_checkbox = QCheckBox(
            self.tr("Query DLC dependency data with Steamworks API")
        )
        group_layout.addWidget(self.db_builder_query_dlc_checkbox)

        self.db_builder_update_instead_of_overwriting_checkbox = QCheckBox(
            self.tr("Update database instead of overwriting")
        )
        group_layout.addWidget(self.db_builder_update_instead_of_overwriting_checkbox)

        # Text fields
        group_box = QGroupBox()
        tab_layout.addWidget(group_box)

        grid_group_layout = QGridLayout()
        group_box.setLayout(grid_group_layout)

        steam_api_key_label = QLabel(self.tr("Steam API key:"))
        grid_group_layout.addWidget(steam_api_key_label, 1, 0)

        self.db_builder_steam_api_key = QLineEdit()
        self.db_builder_steam_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.db_builder_steam_api_key.setTextMargins(GUIInfo().text_field_margins)
        self.db_builder_steam_api_key.setFixedHeight(
            GUIInfo().default_font_line_height * 2
        )
        grid_group_layout.addWidget(self.db_builder_steam_api_key, 1, 1)

        grid_group_layout.setColumnStretch(0, 0)
        grid_group_layout.setColumnStretch(1, 1)

        tab_layout.addStretch()

        # "Download all workshop mods via" buttons
        item_layout = QHBoxLayout()
        tab_layout.addLayout(item_layout)

        item_layout.addStretch()

        item_label = QLabel(self.tr("Download all published Workshop mods via:"))
        item_layout.addWidget(item_label)

        self.db_builder_download_all_mods_via_steamcmd_button = QPushButton(
            self.tr("SteamCMD")
        )
        item_layout.addWidget(self.db_builder_download_all_mods_via_steamcmd_button)

        self.db_builder_download_all_mods_via_steam_button = QPushButton(
            self.tr("Steam")
        )
        self.db_builder_download_all_mods_via_steam_button.setFixedWidth(
            self.db_builder_download_all_mods_via_steamcmd_button.sizeHint().width()
        )
        item_layout.addWidget(self.db_builder_download_all_mods_via_steam_button)

        # Compare/Merge/Build database buttons
        item_layout = QHBoxLayout()
        tab_layout.addLayout(item_layout)

        item_layout.addStretch()

        self.db_builder_compare_databases_button = QPushButton(
            self.tr("Compare Databases")
        )
        item_layout.addWidget(self.db_builder_compare_databases_button)

        self.db_builder_merge_databases_button = QPushButton(self.tr("Merge Databases"))
        self.db_builder_merge_databases_button.setFixedWidth(
            self.db_builder_compare_databases_button.sizeHint().width()
        )
        item_layout.addWidget(self.db_builder_merge_databases_button)

        self.db_builder_build_database_button = QPushButton(self.tr("Build Database"))
        self.db_builder_build_database_button.setFixedWidth(
            self.db_builder_compare_databases_button.sizeHint().width()
        )
        item_layout.addWidget(self.db_builder_build_database_button)

    def _do_steamcmd_tab(self) -> None:
        tab = QWidget()
        self.tab_widget.addTab(tab, self.tr("SteamCMD"))

        tab_layout = QVBoxLayout(tab)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        group_box = QGroupBox()
        tab_layout.addWidget(group_box)

        group_layout = QVBoxLayout()
        group_box.setLayout(group_layout)

        self.steamcmd_validate_downloads_checkbox = QCheckBox(
            self.tr("Validate downloaded mods")
        )
        group_layout.addWidget(self.steamcmd_validate_downloads_checkbox)

        self.steamcmd_auto_clear_depot_cache_checkbox = QCheckBox(
            self.tr("Automatically clear depot cache")
        )
        self.steamcmd_auto_clear_depot_cache_checkbox.setToolTip(
            (
                self.tr(
                    "Automatically clear the depot cache before downloading mods through SteamCMD.\n"
                    "This may potentially prevent some issues with downloading mods such as download failures and deleted mods repopulating."
                )
            )
        )
        group_layout.addWidget(self.steamcmd_auto_clear_depot_cache_checkbox)

        self.steamcmd_delete_before_update_checkbox = QCheckBox(
            self.tr("Delete before update")
        )
        self.steamcmd_delete_before_update_checkbox.setToolTip(
            self.tr("This is useful if you want to ensure clean mod updates.")
        )
        group_layout.addWidget(self.steamcmd_delete_before_update_checkbox)

        group_box = QGroupBox()
        tab_layout.addWidget(group_box)

        group_layout = QVBoxLayout()
        group_box.setLayout(group_layout)

        header_layout = QHBoxLayout()
        group_layout.addLayout(header_layout)

        section_label = QLabel(self.tr("SteamCMD installation location"))
        section_label.setFont(GUIInfo().emphasis_font)
        header_layout.addWidget(section_label)

        self.steamcmd_install_location_choose_button = QToolButton()
        self.steamcmd_install_location_choose_button.setText(self.tr("Choose…"))
        header_layout.addWidget(self.steamcmd_install_location_choose_button)

        self.steamcmd_install_location = QLineEdit()
        self.steamcmd_install_location.setTextMargins(GUIInfo().text_field_margins)
        self.steamcmd_install_location.setFixedHeight(
            GUIInfo().default_font_line_height * 2
        )
        group_layout.addWidget(self.steamcmd_install_location)

        tab_layout.addStretch()

        button_layout = QHBoxLayout()
        tab_layout.addLayout(button_layout)

        button_layout.addStretch()

        self.steamcmd_clear_depot_cache_button = QPushButton(
            self.tr("Clear depot cache")
        )
        self.steamcmd_clear_depot_cache_button.setToolTip(
            self.tr(
                "Clear the depot cache manually. This may be useful if you encounter issues with downloading mods through SteamCMD."
            )
        )
        button_layout.addWidget(self.steamcmd_clear_depot_cache_button)

        self.steamcmd_import_acf_button = QPushButton(self.tr("Import .acf"))
        button_layout.addWidget(self.steamcmd_import_acf_button)

        self.steamcmd_delete_acf_button = QPushButton(self.tr("Delete .acf"))
        button_layout.addWidget(self.steamcmd_delete_acf_button)

        self.steamcmd_install_button = QPushButton(self.tr("Install SteamCMD"))
        button_layout.addWidget(self.steamcmd_install_button)

    def _do_todds_tab(self) -> None:
        tab = QWidget()
        self.tab_widget.addTab(tab, self.tr("todds"))

        tab_layout = QVBoxLayout(tab)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        group_box = QGroupBox()
        tab_layout.addWidget(group_box)

        group_layout = QVBoxLayout()
        group_box.setLayout(group_layout)

        quality_preset_label = QLabel(self.tr("Quality preset"))
        quality_preset_label.setFont(GUIInfo().emphasis_font)
        group_layout.addWidget(quality_preset_label)

        self.todds_preset_combobox = QComboBox()
        self.todds_preset_combobox.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        self.todds_preset_combobox.addItem(
            self.tr("Optimized - Recommended for RimWorld")
        )
        group_layout.addWidget(self.todds_preset_combobox)

        group_box = QGroupBox()
        tab_layout.addWidget(group_box)

        group_layout = QVBoxLayout()
        group_box.setLayout(group_layout)

        when_optimizing_label = QLabel(self.tr("When optimizing textures"))
        when_optimizing_label.setFont(GUIInfo().emphasis_font)
        group_layout.addWidget(when_optimizing_label)

        self.todds_active_mods_only_radio = QRadioButton(
            self.tr("Optimize active mods only")
        )
        group_layout.addWidget(self.todds_active_mods_only_radio)

        self.todds_all_mods_radio = QRadioButton(self.tr("Optimize all mods"))
        group_layout.addWidget(self.todds_all_mods_radio)

        group_box = QGroupBox()
        tab_layout.addWidget(group_box)

        group_layout = QVBoxLayout()
        group_box.setLayout(group_layout)

        self.todds_dry_run_checkbox = QCheckBox(self.tr("Enable dry-run mode"))
        group_layout.addWidget(self.todds_dry_run_checkbox)

        self.todds_overwrite_checkbox = QCheckBox(
            self.tr("Overwrite existing optimized textures")
        )
        group_layout.addWidget(self.todds_overwrite_checkbox)

    def _do_themes_tab(self) -> None:
        tab = QWidget()
        self.tab_widget.addTab(tab, self.tr("Theme"))

        tab_layout = QVBoxLayout(tab)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Theme settings group
        theme_group_label = QLabel(self.tr("Theme Settings"))
        theme_group_label.setFont(GUIInfo().emphasis_font)
        tab_layout.addWidget(theme_group_label)

        theme_group_box = QGroupBox()
        tab_layout.addWidget(theme_group_box)

        theme_layout = QHBoxLayout()
        theme_group_box.setLayout(theme_layout)

        self.enable_themes_checkbox = QCheckBox(
            self.tr("Enable to use theme / stylesheet instead of system Theme")
        )
        self.enable_themes_checkbox.setToolTip(
            self.tr(
                "To add your own theme / stylesheet \n\n"
                "1) Create a new-folder in 'themes' folder in your 'RimSort' config folder \n"
                "2) Using the default 'RimPy' theme copy it to the folder you created \n"
                "3) Edit the copied 'style.qss' as per your imagination \n"
                "4) Start 'RimSort' and select your theme from dropdown \n"
                "5) Click 'ok' to save settings and apply the selected theme \n\n"
                "NOTE \n"
                "Name of folder will be used as name of the theme and any invalid theme will be ignored \n"
            )
        )
        theme_layout.addWidget(self.enable_themes_checkbox)

        self.themes_combobox = QComboBox()
        self.themes_combobox.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        theme_layout.addWidget(self.themes_combobox)

        self.theme_location_open_button = QToolButton()
        self.theme_location_open_button.setText(self.tr("Open Theme Location"))
        theme_layout.addWidget(self.theme_location_open_button)

        # Font settings group
        font_group_label = QLabel(self.tr("Font Settings"))
        font_group_label.setFont(GUIInfo().emphasis_font)
        tab_layout.addWidget(font_group_label)

        font_group = QGroupBox()
        tab_layout.addWidget(font_group)

        font_layout = QVBoxLayout(font_group)

        font_family_layout = QHBoxLayout()
        font_layout.addLayout(font_family_layout)

        font_family_label = QLabel(self.tr("Font Family"))
        font_family_layout.addWidget(font_family_label)

        self.font_family_combobox = QFontComboBox()
        self.font_family_combobox.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        font_family_layout.addWidget(self.font_family_combobox)

        font_size_layout = QHBoxLayout()
        font_layout.addLayout(font_size_layout)

        font_size_label = QLabel(self.tr("Font Size"))
        font_size_layout.addWidget(font_size_label)

        self.font_size_spinbox = QSpinBox()
        self.font_size_spinbox.setRange(8, 20)
        self.font_size_spinbox.setValue(12)
        self.font_size_spinbox.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        font_size_layout.addWidget(self.font_size_spinbox)

        reset_button = QPushButton(self.tr("Reset"))
        reset_button.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )

        reset_button_layout = QHBoxLayout()
        reset_button_layout.addStretch(1)
        reset_button_layout.addWidget(reset_button)
        font_layout.addLayout(reset_button_layout)
        reset_button.clicked.connect(self.reset_font_settings)

        if self.enable_themes_checkbox.isChecked():
            self.enable_themes_checkbox.stateChanged.connect(
                self.connect_populate_themes_combobox
            )
        else:
            self.themes_combobox.clear()

        # Language configuration group
        language_group_label = QLabel(self.tr("Language Setting"))
        language_group_label.setFont(GUIInfo().emphasis_font)
        tab_layout.addWidget(language_group_label)

        language_group_box = QGroupBox()
        tab_layout.addWidget(language_group_box)

        language_group_layout = QHBoxLayout()
        language_group_box.setLayout(language_group_layout)

        language_label = QLabel(
            self.tr("Select Language (Restart required to apply changes)")
        )
        language_group_layout.addWidget(language_label)

        self.language_combobox = QComboBox()
        self.language_combobox.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )

        language_group_layout.addWidget(self.language_combobox)

        self.connect_populate_languages_combobox()

    def _do_launch_state_tab(self) -> None:
        tab = QWidget()
        self.tab_widget.addTab(tab, self.tr("Launch State"))

        tab_layout = QVBoxLayout(tab)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Windows launch state group
        group_box = QGroupBox()
        tab_layout.addWidget(group_box)

        group_layout = QVBoxLayout()
        group_box.setLayout(group_layout)

        user_note = QLabel(self.tr("RimSort restart required for some settings"))
        user_note.setFont(GUIInfo().emphasis_font)
        user_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        group_layout.addWidget(user_note)

        size_note = QLabel(
            self.tr(
                "Min is {MIN_SIZE} and Max is {MAX_SIZE}. Values outside this range will be reset to defaults."
            ).format(
                MIN_SIZE=Settings.MIN_SIZE,
                MAX_SIZE=Settings.MAX_SIZE
            )
        )
        size_note.setFont(GUIInfo().emphasis_font)
        size_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        group_layout.addWidget(size_note)

        # Main Window
        (
            self.main_window_group,
            self.main_launch_maximized_radio,
            self.main_launch_normal_radio,
            self.main_launch_custom_radio,
            self.main_custom_width_spinbox,
            self.main_custom_height_spinbox,
        ) = create_launch_state_group(
            self.tr("Maximized"),
            self.tr("Normal"),
            self.tr("Custom size"),
            Settings.MIN_SIZE,
            Settings.MAX_SIZE,
            Settings.DEFAULT_WIDTH,
            Settings.DEFAULT_HEIGHT,
        )
        # Add QLabel as title for Main Window Launch State
        main_window_title_label = QLabel(self.tr("Main Window Launch State"))
        main_window_title_label.setFont(GUIInfo().emphasis_font)
        group_layout.addWidget(main_window_title_label)
        group_layout.addWidget(self.main_window_group)

        # Connect main window radio buttons to enable/disable custom size spinboxes dynamically
        self.main_launch_maximized_radio.toggled.connect(
            self.disable_main_custom_size_spinboxes
        )
        self.main_launch_normal_radio.toggled.connect(
            self.disable_main_custom_size_spinboxes
        )
        self.main_launch_custom_radio.toggled.connect(
            self.enable_main_custom_size_spinboxes
        )

        # Browser Window
        (
            self.browser_window_group,
            self.browser_launch_maximized_radio,
            self.browser_launch_normal_radio,
            self.browser_launch_custom_radio,
            self.browser_custom_width_spinbox,
            self.browser_custom_height_spinbox,
        ) = create_launch_state_group(
            self.tr("Maximized"),
            self.tr("Normal"),
            self.tr("Custom size"),
            Settings.MIN_SIZE,
            Settings.MAX_SIZE,
            Settings.DEFAULT_WIDTH,
            Settings.DEFAULT_HEIGHT,
        )
        # Add QLabel as title for Browser Window Launch State
        browser_window_title_label = QLabel(self.tr("Browser Window Launch State"))
        browser_window_title_label.setFont(GUIInfo().emphasis_font)
        group_layout.addWidget(browser_window_title_label)
        group_layout.addWidget(self.browser_window_group)

        # Connect browser window radio buttons to enable/disable custom size spinboxes dynamically
        self.browser_launch_maximized_radio.toggled.connect(
            self.disable_browser_custom_size_spinboxes
        )
        self.browser_launch_normal_radio.toggled.connect(
            self.disable_browser_custom_size_spinboxes
        )
        self.browser_launch_custom_radio.toggled.connect(
            self.enable_browser_custom_size_spinboxes
        )

        # Settings Window (only custom option)
        settings_window_title_label = QLabel(self.tr("Settings Window Launch State"))
        settings_window_title_label.setFont(GUIInfo().emphasis_font)
        group_layout.addWidget(settings_window_title_label)

        settings_window_group = QGroupBox()
        settings_window_layout = QHBoxLayout()
        settings_window_group.setLayout(settings_window_layout)

        self.settings_custom_width_spinbox = QSpinBox()
        self.settings_custom_width_spinbox.setRange(
            Settings.MIN_SIZE, Settings.MAX_SIZE
        )
        self.settings_custom_width_spinbox.setValue(Settings.DEFAULT_WIDTH)
        self.settings_custom_width_spinbox.setSuffix(" px")
        self.settings_custom_width_spinbox.setFixedWidth(100)
        custom_width_label = QLabel(self.tr("Custom Width:"))
        custom_width_label.setFont(GUIInfo().emphasis_font)  # Set font for label
        settings_window_layout.addWidget(custom_width_label)
        settings_window_layout.addWidget(self.settings_custom_width_spinbox)

        self.settings_custom_height_spinbox = QSpinBox()
        self.settings_custom_height_spinbox.setRange(
            Settings.MIN_SIZE, Settings.MAX_SIZE
        )
        self.settings_custom_height_spinbox.setValue(Settings.DEFAULT_HEIGHT)
        self.settings_custom_height_spinbox.setSuffix(" px")
        self.settings_custom_height_spinbox.setFixedWidth(100)
        custom_height_label = QLabel(self.tr("Custom Height:"))
        custom_height_label.setFont(GUIInfo().emphasis_font)  # Set font for label
        settings_window_layout.addWidget(custom_height_label)
        settings_window_layout.addWidget(self.settings_custom_height_spinbox)

        group_layout.addWidget(settings_window_group)

    def disable_main_custom_size_spinboxes(self) -> None:
        """Disable main window custom size spinboxes when 'Maximized' or 'Normal' radio buttons are checked"""
        self.main_custom_width_spinbox.setEnabled(False)
        self.main_custom_height_spinbox.setEnabled(False)

    def enable_main_custom_size_spinboxes(self) -> None:
        """Enable main window custom size spinboxes when 'Custom size' radio button is checked"""
        self.main_custom_width_spinbox.setEnabled(True)
        self.main_custom_height_spinbox.setEnabled(True)

    def disable_browser_custom_size_spinboxes(self) -> None:
        """Disable browser window custom size spinboxes when 'Maximized' or 'Normal' radio buttons are checked"""
        self.browser_custom_width_spinbox.setEnabled(False)
        self.browser_custom_height_spinbox.setEnabled(False)

    def enable_browser_custom_size_spinboxes(self) -> None:
        """Enable browser window custom size spinboxes when 'Custom size' radio button is checked"""
        self.browser_custom_width_spinbox.setEnabled(True)
        self.browser_custom_height_spinbox.setEnabled(True)

    def reset_font_settings(self) -> None:
        default_font = QApplication.font()
        self.font_family_combobox.setCurrentFont(default_font)
        self.font_size_spinbox.setValue(12)

    def enable_aux_db_time_limit_line_edit(self) -> None:
        """Enables/Disables aux DB time limit line edit based on the checkbox state."""
        enable = self.enable_aux_db_behavior_editing.isChecked()
        self.aux_db_time_limit.setEnabled(enable)

    def connect_populate_themes_combobox(self) -> None:
        """Populate the themes combobox with available themes."""
        from app.controllers.theme_controller import ThemeController

        if self.enable_themes_checkbox.isChecked():
            theme_controller = ThemeController()
            theme_controller.populate_themes_combobox
        else:
            self.themes_combobox.clear()

    def connect_populate_languages_combobox(self) -> None:
        from app.controllers.language_controller import LanguageController

        language_controller = LanguageController()
        language_controller.populate_languages_combobox

    def _do_authentication_tab(self) -> None:
        tab = QWidget()
        self.tab_widget.addTab(tab, self.tr("Authentication"))

        tab_layout = QVBoxLayout(tab)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        auth_group = QGroupBox()
        tab_layout.addWidget(auth_group)

        auth_group_layout = QGridLayout()
        auth_group.setLayout(auth_group_layout)

        rentry_auth_label = QLabel(self.tr("Rentry Auth:"))
        auth_group_layout.addWidget(
            rentry_auth_label, 0, 0, alignment=Qt.AlignmentFlag.AlignRight
        )

        self.rentry_auth_code = QLineEdit()
        self.rentry_auth_code.setTextMargins(GUIInfo().text_field_margins)
        self.rentry_auth_code.setFixedHeight(GUIInfo().default_font_line_height * 2)
        self.rentry_auth_code.setPlaceholderText(
            self.tr("Obtain rentry auth code by emailing: support@rentry.co")
        )
        # TODO: If we add a rentry auth code with builds, we should change placeholder to clarify this code will be used instead of the provided one
        auth_group_layout.addWidget(self.rentry_auth_code, 0, 1)

        github_identity_group = QGroupBox()
        tab_layout.addWidget(github_identity_group)

        github_identity_layout = QGridLayout()
        github_identity_group.setLayout(github_identity_layout)

        github_username_label = QLabel(self.tr("GitHub username:"))
        github_identity_layout.addWidget(
            github_username_label, 0, 0, alignment=Qt.AlignmentFlag.AlignRight
        )

        self.github_username = QLineEdit()
        self.github_username.setTextMargins(GUIInfo().text_field_margins)
        self.github_username.setFixedHeight(GUIInfo().default_font_line_height * 2)
        github_identity_layout.addWidget(self.github_username, 0, 1)

        github_token_label = QLabel(self.tr("GitHub personal access token:"))
        github_identity_layout.addWidget(
            github_token_label, 1, 0, alignment=Qt.AlignmentFlag.AlignRight
        )

        self.github_token = QLineEdit()
        self.github_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.github_token.setTextMargins(GUIInfo().text_field_margins)
        self.github_token.setFixedHeight(GUIInfo().default_font_line_height * 2)
        github_identity_layout.addWidget(self.github_token, 1, 1)

        self.setTabOrder(self.github_username, self.github_token)

        buttons_layout = QHBoxLayout()
        tab_layout.addLayout(buttons_layout)

        buttons_layout.addStretch()

    def _do_advanced_tab(self) -> None:
        tab = QWidget()
        self.tab_widget.addTab(tab, self.tr("Advanced"))

        tab_layout = QVBoxLayout(tab)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        group_box = QGroupBox()
        tab_layout.addWidget(group_box)

        group_layout = QVBoxLayout()
        group_box.setLayout(group_layout)

        user_note = QLabel(self.tr("RimSort restart required for some settings"))
        user_note.setFont(GUIInfo().emphasis_font)
        user_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        group_layout.addWidget(user_note)

        self.debug_logging_checkbox = QCheckBox(self.tr("Enable debug logging"))
        group_layout.addWidget(self.debug_logging_checkbox)

        self.watchdog_checkbox = QCheckBox(
            self.tr("Enable watchdog file monitor daemon")
        )
        group_layout.addWidget(self.watchdog_checkbox)

        self.mod_type_filter_checkbox = QCheckBox(self.tr("Enable mod type filter"))
        group_layout.addWidget(self.mod_type_filter_checkbox)

        self.hide_invalid_mods_when_filtering_checkbox = QCheckBox(
            self.tr("Hide invalid mods when filtering")
        )
        group_layout.addWidget(self.hide_invalid_mods_when_filtering_checkbox)

        # Moved to Performance tab under "Integration with recent save"

        self.show_duplicate_mods_warning_checkbox = QCheckBox(
            self.tr("Show duplicate mods warning")
        )
        group_layout.addWidget(self.show_duplicate_mods_warning_checkbox)

        # Clear button behavior
        self.clear_moves_dlc_checkbox = QCheckBox(
            self.tr("Clear also moves DLC")
        )
        group_layout.addWidget(self.clear_moves_dlc_checkbox)

        self.show_mod_updates_checkbox = QCheckBox(
            self.tr("Check for mod updates on refresh")
        )
        group_layout.addWidget(self.show_mod_updates_checkbox)

        self.steam_client_integration_checkbox = QCheckBox(
            self.tr("Enable Steam client integration")
        )
        group_layout.addWidget(self.steam_client_integration_checkbox)

        self.download_missing_mods_checkbox = QCheckBox(
            self.tr("Download missing mods automatically")
        )
        group_layout.addWidget(self.download_missing_mods_checkbox)

        self.render_unity_rich_text_checkbox = QCheckBox(
            self.tr("Render Unity Rich Text in mod descriptions")
        )
        self.color_background_instead_of_text_checkbox = QCheckBox(
            self.tr("Apply mod coloring to background instead of text")
        )
        group_layout.addWidget(self.color_background_instead_of_text_checkbox)
        self.render_unity_rich_text_checkbox.setToolTip(
            self.tr(
                "Enable this option to render Unity Rich Text in mod descriptions. Images will not be displayed."
            )
        )
        group_layout.addWidget(self.render_unity_rich_text_checkbox)

        # Dependencies: alternativePackageIds support
        self.consider_alternative_package_ids_checkbox = QCheckBox(
            self.tr("Consider alternativePackageIds as satisfying dependencies")
        )
        self.consider_alternative_package_ids_checkbox.setToolTip(
            self.tr(
                "If enabled, an alternativePackageIds entry in About.xml can satisfy a mod's dependency when the main dependency is missing."
            )
        )
        group_layout.addWidget(self.consider_alternative_package_ids_checkbox)

        self.update_databases_on_startup_checkbox = QCheckBox(
            self.tr("Update databases on startup")
        )
        self.update_databases_on_startup_checkbox.setToolTip(
            self.tr(
                "Enable this option to automatically update enabled databases when RimSort starts. "
                "This will check for updates and download them if available."
            )
        )
        group_layout.addWidget(self.update_databases_on_startup_checkbox)

        # Prefer versioned About.xml tags over base tags
        self.prefer_versioned_about_tags_checkbox = QCheckBox(
            self.tr("Prefer versioned About.xml tags over base tags")
        )
        self.prefer_versioned_about_tags_checkbox.setToolTip(
            self.tr(
                "When enabled, *ByVersion tags (e.g., modDependenciesByVersion, loadAfterByVersion, "
                "loadBeforeByVersion, incompatibleWithByVersion, descriptionsByVersion) take precedence "
                "over the base tags. If a matching version tag exists but is empty, the base tag is ignored."
            )
        )
        group_layout.addWidget(self.prefer_versioned_about_tags_checkbox)

        run_args_group = QGroupBox()
        tab_layout.addWidget(run_args_group)

        run_args_layout = QGridLayout()
        run_args_group.setLayout(run_args_layout)

        run_args_info_layout = QHBoxLayout()

        self.run_args_info_label = QLabel(
            self.tr(
                "Enter a comma separated list of arguments to pass to the Rimworld executable \n"
                "\n Examples : \n"
                "\n -logfile,/path/to/file.log,-savedatafolder=/path/to/savedata,-popupwindow \n"
            )
        )
        self.run_args_info_label.setFixedHeight(GUIInfo().default_font_line_height * 6)
        run_args_info_layout.addWidget(self.run_args_info_label, 0)
        self.run_args_info_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        run_args_layout.addLayout(run_args_info_layout, 0, 0, 1, 2)

        run_args_label = QLabel(self.tr("Edit Game Run Arguments:"))
        run_args_layout.addWidget(
            run_args_label, 1, 0, alignment=Qt.AlignmentFlag.AlignRight
        )

        self.run_args = QLineEdit()
        self.run_args.setTextMargins(GUIInfo().text_field_margins)
        self.run_args.setFixedHeight(GUIInfo().default_font_line_height * 2)
        run_args_layout.addWidget(self.run_args, 1, 1)

        self.setTabOrder(self.run_args_info_label, self.run_args)

    def _find_tab_index(self, tab_name: str) -> int:
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == tab_name:
                return i
        return -1  # Return -1 if no tab found

    def switch_to_tab(self, tab_name: str) -> None:
        """
        Switch to the specified tab by name if it exists.
        """
        index = self._find_tab_index(tab_name)
        if index and index != -1:
            self.tab_widget.setCurrentIndex(index)

    def showEvent(self, arg__1: QShowEvent) -> None:
        """Using arg__1 instead of event to avoid name conflict"""
        super().showEvent(arg__1)
        self.global_ok_button.setFocus()


def create_launch_state_group(
    minimized_text: str,
    normal_text: str,
    custom_text: str,
    min_size: int,
    max_size: int,
    default_width: int,
    default_height: int,
) -> tuple[
    QGroupBox,
    QRadioButton,
    QRadioButton,
    QRadioButton,
    QSpinBox,
    QSpinBox,
]:
    group_box = QGroupBox()
    layout = QVBoxLayout()
    group_box.setLayout(layout)

    maximized_radio = QRadioButton(minimized_text)
    layout.addWidget(maximized_radio)

    normal_radio = QRadioButton(normal_text)
    layout.addWidget(normal_radio)

    custom_layout = QHBoxLayout()
    custom_radio = QRadioButton(custom_text)
    custom_layout.addWidget(custom_radio)

    custom_width_spinbox = QSpinBox()
    custom_width_spinbox.setRange(min_size, max_size)
    custom_width_spinbox.setValue(default_width)
    custom_width_spinbox.setSuffix(" px")
    custom_width_spinbox.setFixedWidth(100)
    custom_layout.addWidget(custom_width_spinbox)

    custom_height_spinbox = QSpinBox()
    custom_height_spinbox.setRange(min_size, max_size)
    custom_height_spinbox.setValue(default_height)
    custom_height_spinbox.setSuffix(" px")
    custom_height_spinbox.setFixedWidth(100)
    custom_layout.addWidget(custom_height_spinbox)

    layout.addLayout(custom_layout)

    return (
        group_box,
        maximized_radio,
        normal_radio,
        custom_radio,
        custom_width_spinbox,
        custom_height_spinbox,
    )
