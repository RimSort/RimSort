import json
import sys

from PySide6.QtCore import QCoreApplication, QObject, QTranslator
from PySide6.QtWidgets import QApplication

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

app_translator = QTranslator()
qt_translator = QTranslator()


class AppController(QObject):
    def __init__(self) -> None:
        super().__init__()

        self.app = QApplication(sys.argv)
        self.app.setWindowIcon(GUIInfo().app_icon)

        self.initialize_user_rules()
        self.initialize_settings()
        self.initialize_theme_controller()
        self.initialize_steamcmd_interface()
        self.initialize_metadata_manager()
        self.initialize_main_window()

        self.app.setStyle("Fusion")
        self.theme_controller.set_font(
            self.settings.font_family,
            self.settings.font_size,
        )
        self.theme_controller.apply_selected_theme(
            self.settings.enable_themes,
            self.settings.theme_name,
        )

    def initialize_user_rules(self) -> None:
        """Initializes userRules.json if it does not exist."""
        user_rules_path = AppInfo().user_rules_file
        if not user_rules_path.exists():
            initial_rules_db = DEFAULT_USER_RULES
            with open(user_rules_path, "w", encoding="utf-8") as output:
                json.dump(initial_rules_db, output, indent=4)

    def initialize_settings(self) -> None:
        """Initializes the settings model, view, and controller."""
        self.settings = Settings()
        self.settings.load()
        self.initialize_translator(self.settings.language)
        self.settings_dialog = SettingsDialog()
        self.settings_controller = SettingsController(
            model=self.settings, view=self.settings_dialog
        )

    def initialize_theme_controller(self) -> None:
        """Initializes the ThemeController."""
        self.theme_controller = ThemeController()

    def initialize_translator(self, language: str) -> None:
        """Initializes the translator with the specified language."""
        path = AppInfo()._language_data_folder / f"{language}.qm"
        if app_translator.load(str(path)):
            QCoreApplication.installTranslator(app_translator)
        else:
            print(f"Translation file {path} not found.")

        qt_path = AppInfo()._language_data_folder / f"qtbase_{language}.qm"
        if qt_translator.load(str(qt_path)):
            QCoreApplication.installTranslator(qt_translator)
        else:
            print(f"Qt translation file {qt_path} not found.")

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
