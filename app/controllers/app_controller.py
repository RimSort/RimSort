import json
import sys

from PySide6.QtCore import QObject
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

import app.utils.rimsort_boot_config as rimsort_boot_config
from app.controllers.main_window_controller import MainWindowController
from app.controllers.settings_controller import SettingsController
from app.controllers.theme_controller import ThemeController
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
        self.set_config_variables()

        self.initialize_user_rules()
        self.initialize_settings()  ###
        self.initialize_theme_controller()
        self.initialize_steamcmd_interface()
        self.initialize_metadata_manager()
        self.initialize_main_window()

        self.app.setStyle("Fusion")
        self.theme_controller.apply_selected_theme(
            self.settings.enable_themes,
            self.settings.theme_name,
        )

        self.app.setWindowIcon(GUIInfo().app_icon)  ###

        # Set global font size after main window is loaded
        self.set_global_font_size(self.global_font)

    def set_global_font_size(self, new_size: float) -> None:
        font = QFont()
        font.setPointSizeF(new_size)
        self.app.setFont(font)
        # TODO: If we want to apply changes without RimSort restart
        # self.update_global_font

    def set_config_variables(self) -> None:
        rimsort_boot_config.MOD_ITEM_TEXT_DEFAULT_FONT_SIZE = QFont().pointSize()
        rimsort_boot_config.MOD_ITEM_ICON_DEFAULT_SIZE = (
            20 - rimsort_boot_config.MOD_ITEM_TEXT_DEFAULT_FONT_SIZE
        )

    def initialize_user_rules(self) -> None:
        """Initializes userRules.json if it does not exist."""
        user_rules_path = AppInfo().databases_folder / "userRules.json"
        if not user_rules_path.exists():
            initial_rules_db = DEFAULT_USER_RULES
            with open(user_rules_path, "w", encoding="utf-8") as output:
                json.dump(initial_rules_db, output, indent=4)

    def initialize_settings(self) -> None:
        """Initializes the settings model, view, and controller."""
        self.settings = Settings()
        self.apply_initial_settings()
        self.settings_dialog = SettingsDialog()
        self.settings_controller = SettingsController(
            model=self.settings, view=self.settings_dialog
        )

    def apply_initial_settings(self) -> None:
        """Applies critical settings required at app boot."""
        self.global_font = self.settings.global_font_size
        self.set_global_font_size(self.global_font)

    def initialize_theme_controller(self) -> None:
        """Initializes the ThemeController."""
        self.theme_controller = ThemeController()

    def initialize_steamcmd_interface(self) -> None:
        """Initializes the SteamcmdInterface."""
        self.steamcmd_wrapper = SteamcmdInterface.instance(
            self.settings_controller.settings.instances[
                self.settings_controller.settings.current_instance
            ].steamcmd_install_path,
            self.settings_controller.settings.steamcmd_validate_downloads,
        )

    def initialize_metadata_manager(self) -> None:
        """Initializes the MetadataManager."""
        self.metadata_manager = MetadataManager.instance(
            settings_controller=self.settings_controller
        )

    def initialize_main_window(self) -> None:
        """Initializes the main window and its controller."""
        self.main_window = MainWindow(settings_controller=self.settings_controller)
        self.main_window_controller = MainWindowController(self.main_window)

    def run(self) -> int:
        """Runs the main application loop after initializing the main window."""
        self.main_window.show()
        self.main_window.initialize_content(is_initial=True)
        return self.app.exec()

    def shutdown_watchdog(self) -> None:
        """Initiates the shutdown procedure for the watchdog."""
        self.main_window.shutdown_watchdog()

    def quit(self) -> None:
        """Exits the application."""
        self.app.quit()
