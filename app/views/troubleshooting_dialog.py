from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class TroubleshootingDialog(QDialog):
    """
    Modern troubleshooting dialog with clean, professional design and adaptive layout
    """

    def __init__(self) -> None:
        super().__init__()

        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowTitle("Troubleshooting")

        main_layout = QVBoxLayout()
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)
        self.setObjectName("TroubleshootingDialog")

        # 1. Game Files Recovery Section
        self._create_game_recovery_section(main_layout)

        # 2. Mod Configuration Section
        self._create_mod_configuration_section(main_layout)

        # 3. Steam Utilities Section
        self._create_steam_utilities_section(main_layout)

    def _create_section_frame(self) -> QFrame:
        """Create a styled section frame"""
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.NoFrame)
        frame.setObjectName("section")
        return frame

    def _create_section_header(self, title: str) -> QLabel:
        """Create a styled section header"""
        label = QLabel(title)
        label.setObjectName("sectionHeader")
        return label

    def _create_description_label(self, text: str) -> QLabel:
        """Create a styled description label"""
        label = QLabel(text)
        label.setObjectName("description")
        label.setWordWrap(True)
        return label

    def _create_button_with_layout(
        self, text: str, description: str, object_name: str
    ) -> tuple[QPushButton, QVBoxLayout]:
        """Create a button with its layout - reusable utility method"""
        layout = QVBoxLayout()
        layout.setSpacing(3)

        # Title
        title_label = QLabel(text)
        title_label.setObjectName("utilityTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Description
        desc_label = QLabel(description)
        desc_label.setObjectName("utilityDescription")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Button
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setToolTip(description)
        layout.addWidget(button)

        return button, layout

    def _setup_section_base(self, parent_layout: QVBoxLayout, title: str) -> tuple[QFrame, QVBoxLayout, QWidget, QVBoxLayout]:
        """Set up the common base structure for all sections to eliminate duplication"""
        section_frame = self._create_section_frame()
        parent_layout.addWidget(section_frame)

        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(0)
        section_frame.setLayout(section_layout)

        # Header
        header = self._create_section_header(title)
        section_layout.addWidget(header)

        # Content widget
        content_widget = QWidget()
        content_widget.setObjectName("contentWidget")
        section_layout.addWidget(content_widget)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 8)
        content_layout.setSpacing(0)
        content_widget.setLayout(content_layout)

        return section_frame, section_layout, content_widget, content_layout

    def _create_game_recovery_section(self, parent_layout: QVBoxLayout) -> None:
        """Create the game files recovery section"""
        section_frame, section_layout, content_widget, content_layout = self._setup_section_base(
            parent_layout, self.tr("Game Files Recovery")
        )

        # Description
        description = self._create_description_label(
            self.tr(
                "If you're experiencing issues with your game, you can try the following recovery options. "
                "Steam will automatically redownload any deleted files on next launch."
            )
        )
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(description)

        warning_label = QLabel(
            self.tr("Warning: These operations will delete selected files permanently!")
        )
        warning_label.setObjectName("warningLabel")
        warning_label.setWordWrap(True)
        warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(warning_label)

        # Container widget for checkboxes to control alignment
        checkboxes_container = QWidget()
        content_layout.addWidget(checkboxes_container)

        checkboxes_layout = QVBoxLayout()
        checkboxes_layout.setContentsMargins(0, 0, 0, 0)
        checkboxes_layout.setSpacing(5)
        checkboxes_container.setLayout(checkboxes_layout)

        checkbox_items_container = QWidget()
        checkbox_items_container.setMaximumWidth(800)
        checkbox_items_layout = QVBoxLayout()
        checkbox_items_layout.setContentsMargins(0, 0, 0, 0)
        checkbox_items_layout.setSpacing(8)
        checkbox_items_container.setLayout(checkbox_items_layout)

        center_layout = QHBoxLayout()
        center_layout.addStretch()
        center_layout.addWidget(checkbox_items_container)
        center_layout.addStretch()
        checkboxes_layout.addLayout(center_layout)

        self.integrity_delete_game_files = QCheckBox(
            self.tr(
                "Reset game files (Preserves local mods, deletes and redownloads game files)"
            )
        )
        self.integrity_delete_game_files.setObjectName("styledCheckbox")
        self.integrity_delete_game_files.setToolTip(
            self.tr(
                "Deletes and redownloads game files but keeps your local mods intact."
            )
        )
        checkbox_items_layout.addWidget(self.integrity_delete_game_files)

        self.integrity_delete_steam_mods = QCheckBox(
            self.tr(
                "Reset Steam Workshop mods (Deletes and redownloads all Steam mods)"
            )
        )
        self.integrity_delete_steam_mods.setObjectName("styledCheckbox")
        self.integrity_delete_steam_mods.setToolTip(
            self.tr("Deletes all Steam Workshop mods and triggers redownload.")
        )
        checkbox_items_layout.addWidget(self.integrity_delete_steam_mods)

        self.integrity_delete_mod_configs = QCheckBox(
            self.tr(
                "Reset game configurations (ModsConfig.xml, Prefs.xml, KeyPrefs.xml)*"
            )
        )
        self.integrity_delete_mod_configs.setObjectName("styledCheckbox")
        self.integrity_delete_mod_configs.setToolTip(
            self.tr(
                "Deletes mod configuration files except ModsConfig.xml and Prefs.xml."
            )
        )
        checkbox_items_layout.addWidget(self.integrity_delete_mod_configs)

        self.integrity_delete_game_configs = QCheckBox(
            self.tr(
                "Reset game configurations (ModsConfig.xml, Prefs.xml, KeyPrefs.xml)*"
            )
        )
        self.integrity_delete_game_configs.setObjectName("styledCheckbox")
        self.integrity_delete_game_configs.setToolTip(
            self.tr(
                "Deletes game configuration files including ModsConfig.xml, Prefs.xml, and KeyPrefs.xml."
            )
        )
        checkbox_items_layout.addWidget(self.integrity_delete_game_configs)

        note_label = QLabel(
            self.tr(
                "After resetting game configurations, launch the game directly through Steam to regenerate ModsConfig.xml, then restart RimSort."
            )
        )
        note_label.setObjectName("noteLabel")
        note_label.setWordWrap(True)
        note_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(note_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(14, 6, 14, 0)
        button_layout.setSpacing(10)
        content_layout.addLayout(button_layout)

        button_layout.addStretch()

        self.integrity_apply_button = QPushButton(self.tr("Apply Recovery"))
        self.integrity_apply_button.setObjectName("dangerButton")
        self.integrity_apply_button.setShortcut("Ctrl+R")
        button_layout.addWidget(self.integrity_apply_button)

        self.integrity_cancel_button = QPushButton(self.tr("Cancel"))
        self.integrity_cancel_button.setObjectName("secondaryButton")
        self.integrity_cancel_button.setShortcut("Ctrl+C")
        button_layout.addWidget(self.integrity_cancel_button)

        button_layout.addStretch()

        content_layout.addStretch(1)

    def _create_mod_configuration_section(self, parent_layout: QVBoxLayout) -> None:
        """Create the mod configuration section"""
        section_frame, section_layout, content_widget, content_layout = self._setup_section_base(
            parent_layout, self.tr("Mod Configuration Options")
        )

        # Set specific spacing for this section
        content_layout.setSpacing(8)

        # Description
        description = self._create_description_label(
            self.tr(
                "Manage your mod configurations and load order. These options help you organize and share your mod setup."
            )
        )
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(description)

        # Import/Export section
        import_export_layout = QHBoxLayout()
        import_export_layout.setContentsMargins(14, 0, 14, 0)
        import_export_layout.setSpacing(16)
        content_layout.addLayout(import_export_layout)

        # Export section
        export_layout = QVBoxLayout()
        export_layout.setSpacing(3)
        import_export_layout.addLayout(export_layout)

        export_label = QLabel(self.tr("Export Mod List"))
        export_label.setObjectName("sectionTitle")
        export_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        export_layout.addWidget(export_label)

        export_desc = QLabel(
            self.tr("Save your current mod list to a .xml file to share with others.")
        )
        export_desc.setObjectName("sectionDescription")
        export_desc.setWordWrap(True)
        export_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        export_layout.addWidget(export_desc)

        self.mod_export_list_button = QPushButton(self.tr("Export List"))
        self.mod_export_list_button.setObjectName("actionButton")
        self.mod_export_list_button.setToolTip(
            self.tr("Export your current mod list to a file")
        )
        export_layout.addWidget(self.mod_export_list_button)

        # Import section
        import_layout = QVBoxLayout()
        import_layout.setSpacing(3)
        import_export_layout.addLayout(import_layout)

        import_label = QLabel(self.tr("Import Mod List"))
        import_label.setObjectName("sectionTitle")
        import_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        import_layout.addWidget(import_label)

        import_desc = QLabel(
            self.tr("Import a mod list in .xml format from another player")
        )
        import_desc.setObjectName("sectionDescription")
        import_desc.setWordWrap(True)
        import_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        import_layout.addWidget(import_desc)

        self.mod_import_list_button = QPushButton(self.tr("Import List"))
        self.mod_import_list_button.setObjectName("actionButton")
        self.mod_import_list_button.setToolTip(self.tr("Import a mod list from a file"))
        import_layout.addWidget(self.mod_import_list_button)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("separator")
        content_layout.addWidget(separator)

        # Clear mods section
        clear_layout = QVBoxLayout()
        clear_layout.setContentsMargins(14, 4, 14, 0)
        clear_layout.setSpacing(3)
        content_layout.addLayout(clear_layout)

        clear_label = QLabel(self.tr("Reset to Vanilla"))
        clear_label.setObjectName("sectionTitle")
        clear_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clear_layout.addWidget(clear_label)

        clear_warning = QLabel(
            self.tr(
                "This will delete all mods in your Mods folder and reset to vanilla state"
            )
        )
        clear_warning.setObjectName("warningLabel")
        clear_warning.setWordWrap(True)
        clear_warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clear_layout.addWidget(clear_warning)

        clear_button_layout = QHBoxLayout()
        clear_button_layout.setContentsMargins(0, 4, 0, 0)
        clear_layout.addLayout(clear_button_layout)

        self.clear_mods_button = QPushButton(self.tr("Clear All Mods"))
        self.clear_mods_button.setObjectName("dangerButton")
        self.clear_mods_button.setToolTip(
            self.tr("Delete all mods and reset to vanilla state")
        )
        clear_button_layout.addStretch()
        clear_button_layout.addWidget(self.clear_mods_button)
        clear_button_layout.addStretch()

        content_layout.addStretch(1)

    def _create_steam_utilities_section(self, parent_layout: QVBoxLayout) -> None:
        """Create the Steam utilities section"""
        section_frame, section_layout, content_widget, content_layout = self._setup_section_base(
            parent_layout, self.tr("Steam Utilities")
        )

        # Description
        content_description = self._create_description_label(
            self.tr(
                "Steam-specific utilities to help resolve download and game file issues."
            )
        )
        content_description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(content_description)

        # Steam utilities grid
        utilities_layout = QHBoxLayout()
        utilities_layout.setContentsMargins(14, 0, 14, 0)
        content_layout.addLayout(utilities_layout)

        utilities_layout.addStretch()

        # Create steam utility buttons using the reusable method
        self.steam_clear_cache_button, cache_layout = self._create_button_with_layout(
            self.tr("Clear Download Cache"),
            self.tr("Delete Steam's downloading folder to fix download issues"),
            "primaryButton",
        )
        utilities_layout.addLayout(cache_layout)
        utilities_layout.addStretch()

        self.steam_verify_game_button, verify_layout = self._create_button_with_layout(
            self.tr("Verify Game Files"),
            self.tr("Check and repair RimWorld game files"),
            "primaryButton",
        )
        utilities_layout.addLayout(verify_layout)
        utilities_layout.addStretch()

        self.steam_repair_library_button, repair_layout = self._create_button_with_layout(
            self.tr("Repair Steam Library"),
            self.tr("Verify integrity of all installed Steam games"),
            "primaryButton",
        )
        utilities_layout.addLayout(repair_layout)
        utilities_layout.addStretch()

        content_layout.addStretch(1)