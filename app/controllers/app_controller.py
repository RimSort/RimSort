import json
import sys

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from app.controllers.main_window_controller import MainWindowController
from app.controllers.settings_controller import SettingsController
from app.models.settings import Settings
from app.utils.app_info import AppInfo
from app.utils.constants import DEFAULT_USER_RULES
from app.utils.gui_info import GUIInfo
from app.utils.metadata import MetadataManager
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.views.main_window import MainWindow
from app.views.settings_dialog import SettingsDialog


class AppController(QObject):
    def __init__(self) -> None:
        super().__init__()

        self.app = QApplication(sys.argv)

        self.app.setStyle("Fusion")

        self.app.setStyleSheet(  # Add style sheet for styling layouts and widgets
            (
                AppInfo().application_folder / "themes" / "RimPy" / "style.qss"
            ).read_text()
        )
        self.app.setWindowIcon(GUIInfo().app_icon)

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

        # Initialize SteamcmdInterface
        self.steamcmd_wrapper = SteamcmdInterface.instance(
            self.settings_controller.settings.instances[
                self.settings_controller.settings.current_instance
            ].steamcmd_install_path,
            self.settings_controller.settings.steamcmd_validate_downloads,
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
        self.main_window.initialize_content(is_initial=True)
        return self.app.exec()

    def shutdown_watchdog(self) -> None:
        self.main_window.shutdown_watchdog()

    def quit(self) -> None:
        self.app.quit()
