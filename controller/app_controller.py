import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from controller.main_window_controller import MainWindowController
from controller.settings_controller import SettingsController
from model.settings import Settings
from util.app_info import AppInfo
from util.constants import DEFAULT_USER_RULES
from util.metadata import MetadataManager
from util.system_info import SystemInfo
from view.main_window import MainWindow
from view.settings_dialog import SettingsDialog


class AppController(QObject):
    def __init__(self):
        super().__init__()

        self.app = QApplication(sys.argv)

        if SystemInfo().operating_system == SystemInfo.OperatingSystem.WINDOWS:
            self.app.setStyle("Fusion")
        elif SystemInfo().operating_system == SystemInfo.OperatingSystem.LINUX:
            self.app.setStyle("Fusion")
        elif SystemInfo().operating_system == SystemInfo.OperatingSystem.MACOS:
            self.app.setStyle("macOS")

        # self.app.setStyleSheet(  # Add style sheet for styling layouts and widgets
        #     Path(
        #         os.path.join(AppInfo().application_folder, "themes/RimPy/style.qss")
        #     ).read_text()
        # )

        # One-time initialization of userRules.json
        user_rules_path = AppInfo().databases_folder / "userRules.json"
        if not user_rules_path.exists():
            initial_rules_db = DEFAULT_USER_RULES
            with open(user_rules_path, "w", encoding="utf-8") as output:
                json.dump(initial_rules_db, output, indent=4)

        # Instantiate the settings model, view and controller
        self.settings = Settings()
        self.settings_dialog = SettingsDialog()
        self.settings_controller = SettingsController(
            model=self.settings, view=self.settings_dialog
        )

        # Initialize the MetadataManager
        self.metadata_manager = MetadataManager.instance(
            settings_controller=self.settings_controller
        )

        # Instantiate the main window and its controller
        self.main_window = MainWindow(settings_controller=self.settings_controller)
        self.main_window_controller = MainWindowController(self.main_window)

    def run(self) -> int:
        self.main_window.show()
        self.main_window.initialize_content()
        return self.app.exec()

    def shutdown_watchdog(self) -> None:
        self.main_window.shutdown_watchdog()

    def quit(self) -> None:
        self.app.quit()
