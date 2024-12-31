from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
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
    def __init__(self) -> None:
        super().__init__()

        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowTitle("Troubleshooting")
        self.resize(800, 600)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # game files recovery section
        group_box = QGroupBox("Game Files Recovery")
        main_layout.addWidget(group_box)
        group_layout = QVBoxLayout()
        group_box.setLayout(group_layout)
        group_layout.setSpacing(10)

        # warning label with icon
        warning_layout = QHBoxLayout()
        warning_icon = QLabel("⚠️")
        warning_icon.setStyleSheet("color: #FF4444; font-size: 16px;")
        warning_layout.addWidget(warning_icon)

        warning_label = QLabel(
            "Warning: These operations will delete selected files permanently!"
        )
        warning_label.setStyleSheet("color: #FF4444; font-weight: bold;")
        warning_layout.addWidget(warning_label)
        warning_layout.addStretch()
        group_layout.addLayout(warning_layout)

        # info label
        info_label = QLabel(
            "If you're experiencing issues with your game, you can try the following recovery options.\n"
            "Steam will automatically redownload any deleted files on next launch."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666666;")
        group_layout.addWidget(info_label)

        # checkboxes for integrity options
        self.integrity_delete_game_files = QCheckBox(
            "Reset game files (Preserves local mods, deletes and redownloads game files)"
        )
        self.integrity_delete_game_files.setStyleSheet("padding: 5px;")
        group_layout.addWidget(self.integrity_delete_game_files)

        self.integrity_delete_steam_mods = QCheckBox(
            "Reset Steam Workshop mods (Deletes and redownloads all Steam mods)"
        )
        self.integrity_delete_steam_mods.setStyleSheet("padding: 5px;")
        group_layout.addWidget(self.integrity_delete_steam_mods)

        self.integrity_delete_mod_configs = QCheckBox(
            "Reset mod configurations (Preserves ModsConfig.xml and Prefs.xml)"
        )
        self.integrity_delete_mod_configs.setStyleSheet("padding: 5px;")
        group_layout.addWidget(self.integrity_delete_mod_configs)

        self.integrity_delete_game_configs = QCheckBox(
            "Reset game configurations (ModsConfig.xml, Prefs.xml, KeyPrefs.xml)*"
        )
        self.integrity_delete_game_configs.setStyleSheet("padding: 5px;")
        group_layout.addWidget(self.integrity_delete_game_configs)

        # note about ModsConfig.xml
        note_label = QLabel(
            "*Note: After resetting game configurations, launch the game directly through Steam\n"
            "to regenerate ModsConfig.xml, then restart RimSort."
        )
        note_label.setWordWrap(True)
        note_label.setStyleSheet("color: #666666; font-style: italic; padding: 5px;")
        group_layout.addWidget(note_label)

        # buttons layout
        button_layout = QHBoxLayout()
        group_layout.addLayout(button_layout)

        button_layout.addStretch()
        self.integrity_apply_button = QPushButton("Apply Recovery")
        self.integrity_apply_button.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
        """)
        self.integrity_cancel_button = QPushButton("Cancel")
        self.integrity_cancel_button.setStyleSheet("""
            QPushButton {
                padding: 5px 15px;
                border-radius: 3px;
            }
        """)
        button_layout.addWidget(self.integrity_cancel_button)
        button_layout.addWidget(self.integrity_apply_button)

        # mod configuration options section
        mod_config_group = QGroupBox("Mod Configuration Options")
        main_layout.addWidget(mod_config_group)
        mod_config_layout = QVBoxLayout()
        mod_config_group.setLayout(mod_config_layout)
        mod_config_layout.setSpacing(10)

        # info label for mod configuration
        mod_config_info = QLabel(
            "Manage your mod configurations and load order. These options help you organize and share your mod setup."
        )
        mod_config_info.setWordWrap(True)
        mod_config_info.setStyleSheet("color: #666666;")
        mod_config_layout.addWidget(mod_config_info)

        # mod list import/export section
        mod_list_layout = QHBoxLayout()
        mod_config_layout.addLayout(mod_list_layout)

        mod_list_buttons_layout = QVBoxLayout()
        mod_list_layout.addLayout(mod_list_buttons_layout)

        self.mod_export_list_button = QPushButton("Export Mod List")
        self.mod_export_list_button.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 3px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
        """)
        mod_list_buttons_layout.addWidget(self.mod_export_list_button)

        self.mod_import_list_button = QPushButton("Import Mod List")
        self.mod_import_list_button.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 3px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
        """)
        mod_list_buttons_layout.addWidget(self.mod_import_list_button)

        mod_list_desc = QLabel(
            "Save your current mod list to a .rml file to share with others,\n"
            "or import a mod list in .rml format from another player"
        )
        mod_list_desc.setStyleSheet("color: #666666; padding-left: 10px;")
        mod_list_layout.addWidget(mod_list_desc)
        mod_list_layout.addStretch()

        # Clear mods section (in red)
        clear_mods_layout = QHBoxLayout()
        mod_config_layout.addLayout(clear_mods_layout)

        self.clear_mods_button = QPushButton("Clear Mods")
        self.clear_mods_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 3px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        clear_mods_layout.addWidget(self.clear_mods_button)

        clear_mods_desc = QLabel(
            "⚠️ WARNING: This will delete all mods in your Mods folder and reset to vanilla state"
        )
        clear_mods_desc.setStyleSheet(
            "color: #e74c3c; padding-left: 10px; font-weight: bold;"
        )
        clear_mods_layout.addWidget(clear_mods_desc)
        clear_mods_layout.addStretch()

        # steam tools section
        steam_group = QGroupBox("Steam Utilities")
        main_layout.addWidget(steam_group)
        steam_layout = QVBoxLayout()
        steam_group.setLayout(steam_layout)
        steam_layout.setSpacing(10)

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

        button_style = """
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
            button_layout = QVBoxLayout()
            button.setStyleSheet(button_style)
            desc_label = QLabel(description)
            desc_label.setStyleSheet(
                "color: #666666; font-size: 11px; padding: 5px 8px;"
            )
            button_layout.addWidget(button)
            button_layout.addWidget(desc_label)
            steam_layout.addLayout(button_layout)

        button_layout = QHBoxLayout()
        main_layout.addLayout(button_layout)
        button_layout.addStretch()

        self.close_button = QPushButton("Close")
        self.close_button.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                border-radius: 3px;
            }
        """)
        self.close_button.clicked.connect(self.close)
        button_layout.addWidget(self.close_button)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.close_button.setFocus()
