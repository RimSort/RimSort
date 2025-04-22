from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class TroubleshootingDialog(QDialog):
    """
    Dialog window for troubleshooting options including game file recovery,
    mod configuration management, and Steam utilities.
    """

    def __init__(self) -> None:
        super().__init__()

        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowTitle("Troubleshooting")

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Style constants
        self._group_box_style = """
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid blue;
                border-radius: 5px;
                margin-top: 10px;
                padding: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 3px;
                color: blue;
            }
        """
        self._button_style_base = """
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                min-width: 160px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
        """
        self._button_style_danger = """
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                min-width: 160px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """

        # game files recovery section
        group_box = QGroupBox("Game Files Recovery")
        group_box.setStyleSheet(self._group_box_style)
        main_layout.addWidget(group_box)
        group_layout = QVBoxLayout()
        group_box.setLayout(group_layout)
        group_layout.setSpacing(8)
        group_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # warning label with icon
        warning_layout = QVBoxLayout()
        warning_label = QLabel(
            "⚠️ Warning: These operations will delete selected files permanently!"
        )
        warning_label.setStyleSheet("color: red; font-size: 20px; font-weight: bold;")
        warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning_layout.addWidget(warning_label)
        warning_layout.addStretch()
        group_layout.addLayout(warning_layout)

        # info label
        info_label = QLabel(
            "If you're experiencing issues with your game, you can try the following recovery options. "
            "Steam will automatically redownload any deleted files on next launch."
        )
        info_label.setStyleSheet("color: yellow; font-size: 12px; padding: 5px;")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        group_layout.addWidget(info_label)

        # checkboxes for integrity options with tooltips
        self.integrity_delete_game_files = QCheckBox(
            "Reset game files (Preserves local mods, deletes and redownloads game files)"
        )
        self.integrity_delete_game_files.setStyleSheet("padding: 5px;")
        self.integrity_delete_game_files.setToolTip(
            "Deletes and redownloads game files but keeps your local mods intact."
        )
        group_layout.addWidget(self.integrity_delete_game_files)

        self.integrity_delete_steam_mods = QCheckBox(
            "Reset Steam Workshop mods (Deletes and redownloads all Steam mods)"
        )
        self.integrity_delete_steam_mods.setStyleSheet("padding: 5px;")
        self.integrity_delete_steam_mods.setToolTip(
            "Deletes all Steam Workshop mods and triggers redownload."
        )
        group_layout.addWidget(self.integrity_delete_steam_mods)

        self.integrity_delete_mod_configs = QCheckBox(
            "Reset mod configurations (Preserves ModsConfig.xml and Prefs.xml)"
        )
        self.integrity_delete_mod_configs.setStyleSheet("padding: 5px;")
        self.integrity_delete_mod_configs.setToolTip(
            "Deletes mod configuration files except ModsConfig.xml and Prefs.xml."
        )
        group_layout.addWidget(self.integrity_delete_mod_configs)

        self.integrity_delete_game_configs = QCheckBox(
            "Reset game configurations (ModsConfig.xml, Prefs.xml, KeyPrefs.xml)*"
        )
        self.integrity_delete_game_configs.setStyleSheet("padding: 5px;")
        self.integrity_delete_game_configs.setToolTip(
            "Deletes game configuration files including ModsConfig.xml, Prefs.xml, and KeyPrefs.xml."
        )
        group_layout.addWidget(self.integrity_delete_game_configs)

        # note about ModsConfig.xml
        note_label = QLabel(
            "After resetting game configurations, launch the game directly through Steam to regenerate ModsConfig.xml, then restart RimSort."
        )
        note_label.setStyleSheet("color: yellow; font-size: 12px; padding: 5px;")
        note_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        group_layout.addWidget(note_label)

        # buttons layout
        button_layout: QHBoxLayout = QHBoxLayout()
        group_layout.addLayout(button_layout)

        # Apply button
        self.integrity_apply_button = QPushButton("Apply Recovery")
        self.integrity_apply_button.setStyleSheet(self._button_style_danger)
        self.integrity_apply_button.setShortcut("Ctrl+R")
        self.integrity_apply_button.setToolTip("Apply the selected recovery options")
        # Cancel button
        self.integrity_cancel_button = QPushButton("Cancel")
        self.integrity_cancel_button.setStyleSheet(self._button_style_base)
        self.integrity_cancel_button.setShortcut("Ctrl+C")
        self.integrity_cancel_button.setToolTip("Cancel and clear selections")

        # Add Apply and Cancel buttons to layout
        button_layout.addWidget(self.integrity_apply_button)
        button_layout.addWidget(self.integrity_cancel_button)
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # mod configuration options section
        mod_config_group = QGroupBox("Mod Configuration Options")
        mod_config_group.setStyleSheet(self._group_box_style)
        main_layout.addWidget(mod_config_group)
        mod_config_layout = QVBoxLayout()
        mod_config_group.setLayout(mod_config_layout)
        mod_config_layout.setSpacing(8)

        # info label for mod configuration
        mod_config_info = QLabel(
            "Manage your mod configurations and load order. These options help you organize and share your mod setup."
        )
        mod_config_info.setStyleSheet(
            "color: yellow; font-size: 15px; margin-bottom: 5px;"
        )
        mod_config_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mod_config_layout.addWidget(mod_config_info)

        # mod list import/export section
        mod_list_layout = QHBoxLayout()
        mod_config_layout.addLayout(mod_list_layout)
        mod_list_layout.setSpacing(8)

        # Export mod list vertical layout
        export_mod_layout = QVBoxLayout()
        mod_list_layout.addLayout(export_mod_layout)

        export_mod_list_desc = QLabel(
            "Save your current mod list to a .xml file to share with others."
        )
        export_mod_list_desc.setStyleSheet(
            "color: white; padding-left: 0px; margin-top: 5px; font-size: 15px;"
        )
        export_mod_list_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        export_mod_layout.addWidget(export_mod_list_desc)

        self.mod_export_list_button = QPushButton("Export Mod List")
        self.mod_export_list_button.setStyleSheet(self._button_style_base)
        self.mod_export_list_button.setToolTip("Export your current mod list to a file")
        export_mod_layout.addWidget(self.mod_export_list_button)

        # Import mod list vertical layout
        import_mod_layout = QVBoxLayout()
        mod_list_layout.addLayout(import_mod_layout)

        import_mod_list_desc = QLabel(
            "Import a mod list in .xml format from another player"
        )
        import_mod_list_desc.setStyleSheet(
            "color: white; padding-left: 0px; margin-top: 5px; font-size: 15px;"
        )
        import_mod_list_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        import_mod_layout.addWidget(import_mod_list_desc)

        self.mod_import_list_button = QPushButton("Import Mod List")
        self.mod_import_list_button.setStyleSheet(self._button_style_base)
        self.mod_import_list_button.setToolTip("Import a mod list from a file")
        import_mod_layout.addWidget(self.mod_import_list_button)

        # Clear mods section (in red)
        clear_mods_layout = QVBoxLayout()
        clear_mods_layout.setSpacing(8)
        mod_config_layout.addLayout(clear_mods_layout)

        clear_mods_desc = QLabel(
            "⚠️ WARNING: This will delete all mods in your Mods folder and reset to vanilla state"
        )
        clear_mods_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clear_mods_desc.setStyleSheet(
            "color: #e74c3c; font-weight: bold; font-size: 20px; margin-top: 5px;"
        )
        clear_mods_layout.addWidget(clear_mods_desc)

        self.clear_mods_button = QPushButton("Clear Mods")
        self.clear_mods_button.setStyleSheet(self._button_style_danger)
        self.clear_mods_button.setMinimumWidth(160)
        self.clear_mods_button.setToolTip("Delete all mods and reset to vanilla state")
        clear_mods_layout.addWidget(
            self.clear_mods_button, alignment=Qt.AlignmentFlag.AlignCenter
        )

        # steam tools section
        steam_group = QGroupBox("Steam Utilities")
        steam_group.setStyleSheet(self._group_box_style)
        main_layout.addWidget(steam_group)
        steam_layout = QHBoxLayout()
        steam_group.setLayout(steam_layout)
        steam_group.setAlignment(Qt.AlignmentFlag.AlignCenter)
        steam_layout.setSpacing(8)

        # Initialize steam buttons
        self.steam_clear_cache_button = QPushButton("🔄 Clear Download Cache")
        self.steam_verify_game_button = QPushButton("✓ Verify Game Files")
        self.steam_repair_library_button = QPushButton("🔧 Repair Steam library")

        # steam buttons with icons and descriptions
        steam_buttons = [
            (
                self.steam_clear_cache_button,
                "Delete Steam's downloading folder to fix download issues",
            ),
            (
                self.steam_verify_game_button,
                "Check and repair RimWorld game files",
            ),
            (
                self.steam_repair_library_button,
                "Verify integrity of all installed Steam games",
            ),
        ]

        button_style_steam = """
            QPushButton {
                text-align: left;
                padding: 8px;
                border-radius: 3px;
                background-color: #4a90e2;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
        """

        for button, description in steam_buttons:
            button_container = QVBoxLayout()
            button_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
            button.setStyleSheet(button_style_steam)
            button.setToolTip(description)
            desc_label = QLabel(description)
            desc_label.setStyleSheet("color: white; font-size: 12px; padding: 5px 8px;")
            desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            button_container.addWidget(button)
            button_container.addWidget(desc_label)
            steam_layout.addLayout(button_container)

        button_layout = QHBoxLayout()
        main_layout.addLayout(button_layout)
        button_layout.addStretch()
