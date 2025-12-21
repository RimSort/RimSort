import os
import sys

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QObject, QTranslator
from PySide6.QtWidgets import QApplication

from app.controllers.main_window_controller import MainWindowController
from app.controllers.settings_controller import SettingsController
from app.controllers.theme_controller import ThemeController
from app.models.settings import Settings
from app.utils.app_info import AppInfo
from app.utils.dds_utility import DDSUtility
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

        # Initialize the application settings.
        self.initialize_settings()
        # set the language of the application.
        self.set_language()
        # Initialize the theme controller
        self.initialize_theme_controller()
        # Set the theme of the application.
        self.set_theme()
        # Initialize the Steamcmd interface
        self.initialize_steamcmd_interface()
        # NOTE: SteamworksInterface is NOT initialized in main process
        # It's lazily initialized when first used (typically in Qt thread pool workers)
        # Each usage context gets the same singleton instance
        # Perform cleanup of orphaned DDS files if the setting is enabled
        self.do_dds_cleanup()
        # Initialize the metadata manager
        self.initialize_metadata_manager()
        # Initialize the main window controller
        self.initialize_main_window()

    def set_language(self) -> None:
        """Sets the language of the application on initial setup."""
        available_languages = self.settings_controller.language_controller.languages
        os_language = os.getenv("LANG", "").split(".")[0]
        is_inital = self.settings_controller.active_instance.initial_setup
        if is_inital and os_language in available_languages:
            self.settings_controller.settings.language = os_language
            self.settings_controller.settings.save()
            self.initialize_settings()

    def set_theme(self) -> None:
        """Sets the theme for the application."""
        self.app.setStyle("Fusion")
        self.theme_controller.set_font(
            self.settings.font_family,
            self.settings.font_size,
        )
        self.theme_controller.apply_selected_theme(
            self.settings.enable_themes,
            self.settings.theme_name,
        )

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
        path = AppInfo().language_data_folder / f"{language}.qm"
        if app_translator.load(str(path)):
            QCoreApplication.installTranslator(app_translator)
        else:
            print(f"Translation file {path} not found.")

        qt_translations_path = QLibraryInfo.path(
            QLibraryInfo.LibraryPath.TranslationsPath
        )

        qt_file_path = os.path.join(qt_translations_path, f"qtbase_{language}.qm")
        if qt_translator.load(qt_file_path):
            QCoreApplication.installTranslator(qt_translator)
        else:
            print(f"Qt translation file {qt_file_path} not found.")

    def initialize_steamcmd_interface(self) -> None:
        """Initializes the SteamcmdInterface."""
        self.steamcmd_wrapper = SteamcmdInterface.instance(
            self.settings_controller.settings.instances[
                self.settings_controller.settings.current_instance
            ].steamcmd_install_path,
            self.settings_controller.settings.steamcmd_validate_downloads,
        )

    def do_dds_cleanup(self) -> None:
        """Performs cleanup of orphaned DDS files if the setting is enabled."""
        if self.settings.auto_delete_orphaned_dds:
            dds_utility = DDSUtility(self.settings_controller)
            dds_utility.delete_dds_files_without_png()

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
        """Exit the application."""
        # NOTE: No need to shutdown SteamworksInterface here
        # It's only initialized in child processes which clean up on termination
        self.app.quit()
