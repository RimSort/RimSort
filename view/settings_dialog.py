from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QWidget,
    QVBoxLayout,
    QRadioButton,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QCheckBox,
    QLineEdit,
    QGroupBox,
    QToolButton,
    QBoxLayout,
    QComboBox,
)

from util.gui_info import GUIInfo


class SettingsDialog(QDialog):
    def __init__(
        self,
    ) -> None:
        super().__init__()

        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self.setWindowTitle("Settings")
        self.resize(800, 600)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Initialize the QTabWidget
        self._tab_widget = QTabWidget()
        main_layout.addWidget(self._tab_widget)

        # Initialize the tabs
        self._do_locations_tab()
        self._do_databases_tab()
        self._do_sorting_tab()
        self._do_db_builder_tab()
        self._do_steamcmd_tab()
        self._do_todds_tab()
        self._do_advanced_tab()

        # "Cancel" and "Apply" buttons layout
        button_layout = QHBoxLayout()

        self.global_reset_to_defaults_button = QPushButton("Reset to Defaults", self)
        button_layout.addWidget(self.global_reset_to_defaults_button)

        button_layout.addStretch(1)  # Push buttons to the right

        # Cancel button
        self.global_cancel_button = QPushButton("Cancel", self)
        button_layout.addWidget(self.global_cancel_button)

        # OK button
        self.global_ok_button = QPushButton("OK", self)
        self.global_ok_button.setDefault(True)
        button_layout.addWidget(self.global_ok_button)

        # Add button layout to the main layout
        main_layout.addLayout(button_layout)

    def _do_locations_tab(self) -> None:
        tab = QWidget()
        self._tab_widget.addTab(tab, "Locations")

        tab_layout = QVBoxLayout(tab)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._do_game_location_area(tab_layout)
        self._do_config_folder_location_area(tab_layout)
        self._do_steam_mods_folder_location_area(tab_layout)
        self._do_local_mods_folder_location_area(tab_layout)

        # Push the buttons to the bottom
        tab_layout.addStretch(1)

        # Create a QHBoxLayout for the buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch(1)

        # Create the "Clear" button and connect its signal
        self.locations_clear_button = QPushButton("Clear", tab)
        buttons_layout.addWidget(self.locations_clear_button)

        # Create the "Autodetect" button and connect its signal
        self.locations_autodetect_button = QPushButton("Autodetect", tab)
        buttons_layout.addWidget(self.locations_autodetect_button)

        # Add the buttons layout to the main QVBoxLayout
        tab_layout.addLayout(buttons_layout)

    def _do_game_location_area(self, tab_layout: QVBoxLayout) -> None:
        header_layout = QHBoxLayout()
        tab_layout.addLayout(header_layout)

        section_label = QLabel("Game location")
        section_label.setFont(GUIInfo().emphasis_font)
        header_layout.addWidget(section_label)

        self.game_location_choose_button = QToolButton()
        self.game_location_choose_button.setText("Choose…")
        header_layout.addWidget(self.game_location_choose_button)

        self.game_location = QLineEdit()
        self.game_location.setTextMargins(GUIInfo().text_field_margins)
        self.game_location.setFixedHeight(GUIInfo().default_font_line_height * 2)
        self.game_location.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        tab_layout.addWidget(self.game_location)

    def _do_config_folder_location_area(self, tab_layout: QVBoxLayout) -> None:
        header_layout = QHBoxLayout()
        tab_layout.addLayout(header_layout)

        section_label = QLabel("Config location")
        section_label.setFont(GUIInfo().emphasis_font)
        header_layout.addWidget(section_label)

        self.config_folder_location_choose_button = QToolButton()
        self.config_folder_location_choose_button.setText("Choose…")
        header_layout.addWidget(self.config_folder_location_choose_button)

        self.config_folder_location = QLineEdit()
        self.config_folder_location.setTextMargins(GUIInfo().text_field_margins)
        self.config_folder_location.setFixedHeight(
            GUIInfo().default_font_line_height * 2
        )
        self.config_folder_location.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        tab_layout.addWidget(self.config_folder_location)

    def _do_steam_mods_folder_location_area(self, tab_layout: QVBoxLayout) -> None:
        header_layout = QHBoxLayout()
        tab_layout.addLayout(header_layout)

        section_label = QLabel("Steam mods location")
        section_label.setFont(GUIInfo().emphasis_font)
        header_layout.addWidget(section_label)

        self.steam_mods_folder_location_choose_button = QToolButton()
        self.steam_mods_folder_location_choose_button.setText("Choose…")
        header_layout.addWidget(self.steam_mods_folder_location_choose_button)

        self.steam_mods_folder_location = QLineEdit()
        self.steam_mods_folder_location.setTextMargins(GUIInfo().text_field_margins)
        self.steam_mods_folder_location.setFixedHeight(
            GUIInfo().default_font_line_height * 2
        )
        self.steam_mods_folder_location.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        tab_layout.addWidget(self.steam_mods_folder_location)

    def _do_local_mods_folder_location_area(self, tab_layout: QVBoxLayout) -> None:
        header_layout = QHBoxLayout()
        tab_layout.addLayout(header_layout)

        section_label = QLabel("Local mods location")
        section_label.setFont(GUIInfo().emphasis_font)
        header_layout.addWidget(section_label)

        self.local_mods_folder_location_choose_button = QToolButton()
        self.local_mods_folder_location_choose_button.setText("Choose…")
        header_layout.addWidget(self.local_mods_folder_location_choose_button)

        self.local_mods_folder_location = QLineEdit()
        self.local_mods_folder_location.setTextMargins(GUIInfo().text_field_margins)
        self.local_mods_folder_location.setFixedHeight(
            GUIInfo().default_font_line_height * 2
        )
        self.local_mods_folder_location.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        tab_layout.addWidget(self.local_mods_folder_location)

    def _do_databases_tab(self) -> None:
        tab = QWidget()
        self._tab_widget.addTab(tab, "Databases")

        tab_layout = QVBoxLayout()
        tab.setLayout(tab_layout)

        self._do_community_rules_db_group(tab_layout)
        self._do_steam_workshop_db_group(tab_layout)

    def _do_community_rules_db_group(self, tab_layout: QBoxLayout) -> None:
        group = QGroupBox()
        tab_layout.addWidget(group, stretch=1)

        group_layout = QVBoxLayout()
        group_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        group.setLayout(group_layout)

        section_label = QLabel("Community rules database")
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

        self.community_rules_db_none_radio = QRadioButton("None")
        self.community_rules_db_none_radio.setMinimumSize(
            0, GUIInfo().default_font_line_height * 2
        )
        self.community_rules_db_none_radio.setChecked(True)
        item_layout.addWidget(self.community_rules_db_none_radio, stretch=2)

        label = QLabel("No community rules database will be used.")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        label.setEnabled(False)
        item_layout.addWidget(label, stretch=8)

        item_layout = QHBoxLayout()
        section_layout.addLayout(item_layout, stretch=1)

        self.community_rules_db_github_radio = QRadioButton("GitHub")
        self.community_rules_db_github_radio.setMinimumSize(
            0, GUIInfo().default_font_line_height * 2
        )
        item_layout.addWidget(self.community_rules_db_github_radio, stretch=2)

        row_layout = QHBoxLayout()
        row_layout.setSpacing(8)
        item_layout.addLayout(row_layout, stretch=8)

        self.community_rules_db_github_url = QLineEdit()
        self.community_rules_db_github_url.setFixedHeight(
            GUIInfo().default_font_line_height * 2
        )
        self.community_rules_db_github_url.setTextMargins(GUIInfo().text_field_margins)
        self.community_rules_db_github_url.setClearButtonEnabled(True)
        self.community_rules_db_github_url.setEnabled(False)
        row_layout.addWidget(self.community_rules_db_github_url)

        self.community_rules_db_github_download_button = QToolButton()
        self.community_rules_db_github_download_button.setText("Download…")
        self.community_rules_db_github_download_button.setEnabled(False)
        row_layout.addWidget(self.community_rules_db_github_download_button)

        item_layout = QHBoxLayout()
        section_layout.addLayout(item_layout, stretch=1)
        self.community_rules_db_local_file_radio = QRadioButton("Local File")
        self.community_rules_db_local_file_radio.setMinimumSize(
            0, GUIInfo().default_font_line_height * 2
        )
        item_layout.addWidget(self.community_rules_db_local_file_radio, stretch=2)

        row_layout = QHBoxLayout()
        row_layout.setSpacing(8)
        item_layout.addLayout(row_layout, stretch=8)

        self.community_rules_db_local_file = QLineEdit()
        self.community_rules_db_local_file.setFixedHeight(
            GUIInfo().default_font_line_height * 2
        )
        self.community_rules_db_local_file.setTextMargins(GUIInfo().text_field_margins)
        self.community_rules_db_local_file.setClearButtonEnabled(True)
        self.community_rules_db_local_file.setEnabled(False)
        row_layout.addWidget(self.community_rules_db_local_file)

        self.community_rules_db_local_file_choose_button = QToolButton()
        self.community_rules_db_local_file_choose_button.setText("Choose…")
        self.community_rules_db_local_file_choose_button.setEnabled(False)
        self.community_rules_db_local_file_choose_button.setFixedWidth(
            self.community_rules_db_github_download_button.sizeHint().width()
        )
        row_layout.addWidget(self.community_rules_db_local_file_choose_button)

        section_layout.addStretch(1)

        item_layout = QHBoxLayout()
        section_layout.addLayout(item_layout, stretch=1)

        info_label = QLabel("")
        info_label.setWordWrap(True)
        item_layout.addWidget(info_label)

    def _do_steam_workshop_db_group(self, tab_layout: QBoxLayout) -> None:
        group = QGroupBox()
        tab_layout.addWidget(group, stretch=1)

        group_layout = QVBoxLayout()
        group_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        group.setLayout(group_layout)

        section_label = QLabel("Steam Workshop database")
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

        self.steam_workshop_db_none_radio = QRadioButton("None")
        self.steam_workshop_db_none_radio.setMinimumSize(
            0, GUIInfo().default_font_line_height * 2
        )
        self.steam_workshop_db_none_radio.setChecked(True)
        item_layout.addWidget(self.steam_workshop_db_none_radio, stretch=2)

        label = QLabel("No Steam Workshop database will be used.")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        label.setEnabled(False)
        item_layout.addWidget(label, stretch=8)

        item_layout = QHBoxLayout()
        section_layout.addLayout(item_layout, stretch=1)

        self.steam_workshop_db_github_radio = QRadioButton("GitHub")
        self.steam_workshop_db_github_radio.setMinimumSize(
            0, GUIInfo().default_font_line_height * 2
        )
        item_layout.addWidget(self.steam_workshop_db_github_radio, stretch=2)

        row_layout = QHBoxLayout()
        row_layout.setSpacing(8)
        item_layout.addLayout(row_layout, stretch=8)

        self.steam_workshop_db_github_url = QLineEdit()
        self.steam_workshop_db_github_url.setFixedHeight(
            GUIInfo().default_font_line_height * 2
        )
        self.steam_workshop_db_github_url.setTextMargins(GUIInfo().text_field_margins)
        self.steam_workshop_db_github_url.setClearButtonEnabled(True)
        self.steam_workshop_db_github_url.setEnabled(False)
        row_layout.addWidget(self.steam_workshop_db_github_url)

        self.steam_workshop_db_github_download_button = QToolButton()
        self.steam_workshop_db_github_download_button.setText("Download…")
        self.steam_workshop_db_github_download_button.setEnabled(False)
        row_layout.addWidget(self.steam_workshop_db_github_download_button)

        item_layout = QHBoxLayout()
        section_layout.addLayout(item_layout, stretch=1)
        self.steam_workshop_db_local_file_radio = QRadioButton("Local File")
        self.steam_workshop_db_local_file_radio.setMinimumSize(
            0, GUIInfo().default_font_line_height * 2
        )
        item_layout.addWidget(self.steam_workshop_db_local_file_radio, stretch=2)

        row_layout = QHBoxLayout()
        row_layout.setSpacing(8)
        item_layout.addLayout(row_layout, stretch=8)

        self.steam_workshop_db_local_file = QLineEdit()
        self.steam_workshop_db_local_file.setFixedHeight(
            GUIInfo().default_font_line_height * 2
        )
        self.steam_workshop_db_local_file.setTextMargins(GUIInfo().text_field_margins)
        self.steam_workshop_db_local_file.setClearButtonEnabled(True)
        self.steam_workshop_db_local_file.setEnabled(False)
        row_layout.addWidget(self.steam_workshop_db_local_file)

        self.steam_workshop_db_local_file_choose_button = QToolButton()
        self.steam_workshop_db_local_file_choose_button.setText("Choose…")
        self.steam_workshop_db_local_file_choose_button.setEnabled(False)
        self.steam_workshop_db_local_file_choose_button.setFixedWidth(
            self.steam_workshop_db_github_download_button.sizeHint().width()
        )
        row_layout.addWidget(self.steam_workshop_db_local_file_choose_button)

        section_layout.addStretch(1)

        item_layout = QHBoxLayout()
        section_layout.addLayout(item_layout, stretch=1)

        info_label = QLabel("")
        info_label.setWordWrap(True)
        item_layout.addWidget(info_label)

    def _do_sorting_tab(self) -> None:
        tab = QWidget()
        self._tab_widget.addTab(tab, "Sorting")

        tab_layout = QVBoxLayout(tab)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        sorting_layout = QHBoxLayout()
        tab_layout.addLayout(sorting_layout)

        sorting_label = QLabel("Sort Mods:")
        sorting_layout.addWidget(sorting_label, alignment=Qt.AlignmentFlag.AlignTop)

        radios_layout = QVBoxLayout()
        sorting_layout.addLayout(radios_layout)

        self.sorting_alphabetical_radio = QRadioButton("Alphabetically")
        radios_layout.addWidget(self.sorting_alphabetical_radio)

        self.sorting_topological_radio = QRadioButton("Topologically")
        radios_layout.addWidget(self.sorting_topological_radio)

        sorting_layout.addStretch()

        tab_layout.addStretch(1)

        explanatory_text = ""
        explanatory_label = QLabel(explanatory_text)
        explanatory_label.setWordWrap(True)
        tab_layout.addWidget(explanatory_label)

    def _do_db_builder_tab(self) -> None:
        tab = QWidget()
        self._tab_widget.addTab(tab, "DB Builder")

        tab_layout = QVBoxLayout(tab)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.db_builder_include_local_checkbox = QCheckBox("Include local mod metadata")
        tab_layout.addWidget(self.db_builder_include_local_checkbox)

        self.db_builder_query_dlc_checkbox = QCheckBox(
            "Query DLC dependency data with Steamworks API"
        )
        tab_layout.addWidget(self.db_builder_query_dlc_checkbox)

        self.db_builder_update_instead_of_overwriting_checkbox = QCheckBox(
            "Update database instead of overwriting"
        )
        tab_layout.addWidget(self.db_builder_update_instead_of_overwriting_checkbox)

    def _do_steamcmd_tab(self) -> None:
        tab = QWidget()
        self._tab_widget.addTab(tab, "SteamCMD")

        tab_layout = QVBoxLayout(tab)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.steamcmd_validate_downloads_checkbox = QCheckBox(
            "Validate downloaded mods"
        )
        tab_layout.addWidget(self.steamcmd_validate_downloads_checkbox)

    def _do_todds_tab(self) -> None:
        tab = QWidget()
        self._tab_widget.addTab(tab, "todds")

        tab_layout = QVBoxLayout(tab)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        quality_preset_layout = QHBoxLayout()
        tab_layout.addLayout(quality_preset_layout)

        quality_preset_label = QLabel("Quality preset:")
        quality_preset_label.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        quality_preset_layout.addWidget(quality_preset_label)

        self.todds_preset_combobox = QComboBox()
        self.todds_preset_combobox.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        self.todds_preset_combobox.addItem("Optimized - Recommended for RimWorld")
        quality_preset_layout.addWidget(self.todds_preset_combobox)

        quality_preset_layout.addStretch()

        when_optimizing_layout = QHBoxLayout()
        tab_layout.addLayout(when_optimizing_layout)

        when_optimizing_label = QLabel("When optimizing textures:")
        when_optimizing_layout.addWidget(
            when_optimizing_label, alignment=Qt.AlignmentFlag.AlignTop
        )

        radios_layout = QVBoxLayout()
        radios_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        when_optimizing_layout.addLayout(radios_layout)

        when_optimizing_layout.addStretch()

        self.todds_active_mods_only_radio = QRadioButton("Optimize active mods only")
        radios_layout.addWidget(self.todds_active_mods_only_radio)

        self.todds_all_mods_radio = QRadioButton("Optimize all mods")
        radios_layout.addWidget(self.todds_all_mods_radio)

        tab_layout.addSpacing(GUIInfo().default_font_line_height)

        self.todds_dry_run_checkbox = QCheckBox("Enable dry-run mode")
        tab_layout.addWidget(self.todds_dry_run_checkbox)

        self.todds_overwrite_checkbox = QCheckBox(
            "Overwrite existing optimized textures"
        )
        tab_layout.addWidget(self.todds_overwrite_checkbox)

    def _do_advanced_tab(self) -> None:
        tab = QWidget()
        self._tab_widget.addTab(tab, "Advanced")

        tab_layout = QVBoxLayout(tab)
        tab_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.debug_logging_checkbox = QCheckBox("Enable debug logging")
        tab_layout.addWidget(self.debug_logging_checkbox)

        self.watchdog_checkbox = QCheckBox("Enable watchdog file monitor daemon")
        tab_layout.addWidget(self.watchdog_checkbox)

        self.mod_type_filter_checkbox = QCheckBox("Enable mod type filter")
        tab_layout.addWidget(self.mod_type_filter_checkbox)

        self.show_duplicate_mods_warning_checkbox = QCheckBox(
            "Show duplicate mods warning"
        )
        tab_layout.addWidget(self.show_duplicate_mods_warning_checkbox)

        self.show_mod_updates_checkbox = QCheckBox("Check for mod updates on refresh")
        tab_layout.addWidget(self.show_mod_updates_checkbox)

        self.download_missing_mods_checkbox = QCheckBox(
            "Download missing mods automatically"
        )
        tab_layout.addWidget(self.download_missing_mods_checkbox)

        tab_layout.addSpacing(GUIInfo().default_font_line_height)

        upload_buttons_layout = QHBoxLayout()
        tab_layout.addLayout(upload_buttons_layout)

        self.upload_log_button = QPushButton("Upload Log")
        upload_buttons_layout.addWidget(self.upload_log_button)

        upload_buttons_layout.addStretch()
