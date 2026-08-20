import os
import sys

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QObject, QTimer, QTranslator
from PySide6.QtWidgets import QApplication

import app.utils.globals as app_globals
from app.controllers.main_window_controller import MainWindowController
from app.controllers.metadata_controller import MetadataController
from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController
from app.controllers.theme_controller import ThemeController
from app.mcp.command_queue import clear_gui_alive, drain, mark_gui_alive
from app.mcp.supervisor import stop_mcp_subprocess, sync_mcp_subprocess
from app.models.settings import Settings
from app.services.instance_service import InstanceService
from app.utils.app_info import AppInfo
from app.utils.dds_utility import DDSUtility
from app.utils.event_bus import EventBus
from app.utils.gui_info import GUIInfo
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.views.main_window import MainWindow
from app.views.settings_dialog import SettingsDialog

app_translator = QTranslator()
qt_translator = QTranslator()


class AppController(QObject):
    def __init__(self) -> None:
        super().__init__()

        self.app = QApplication(sys.argv)
        self.app.setDesktopFileName("io.github.rimsort.RimSort")
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
        # Perform cleanup of orphaned DDS files if the setting is enabled
        self.do_dds_cleanup()
        # Initialize the new MetadataController
        self.initialize_metadata_controller()
        # Initialize the instance service (self-subscribes to EventBus)
        self.initialize_instance_service()
        # Initialize the main window controller
        self.initialize_main_window()
        self._mcp_sync_timer = QTimer(self)
        self._mcp_sync_timer.setSingleShot(True)
        self._mcp_sync_timer.timeout.connect(self._sync_mcp_subprocess)
        EventBus().settings_have_changed.connect(self._schedule_mcp_sync)
        self._mcp_drain_timer = QTimer(self)
        self._mcp_drain_timer.timeout.connect(self._drain_mcp_commands)
        self.app.aboutToQuit.connect(self._shutdown_mcp)

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
        app_globals.SETTINGS = self.settings

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
            dds_utility = DDSUtility(self.settings_controller.settings)
            dds_utility.delete_dds_files_without_png()

    def initialize_metadata_controller(self) -> None:
        """Initializes the MetadataController."""
        aux_db_controller = AuxMetadataController.get_or_create_cached_instance(
            self.settings_controller.settings.aux_db_path
        )
        self.metadata_controller = MetadataController.instance(
            settings=self.settings_controller.settings,
            get_active_instance=lambda: self.settings_controller.active_instance,
            metadata_db_controller=aux_db_controller,
        )

    def initialize_instance_service(self) -> None:
        """Initializes the instance service."""
        InstanceService(
            settings=self.settings_controller.settings,
            steamcmd_wrapper=self.steamcmd_wrapper,
        )

    def initialize_main_window(self) -> None:
        """Initializes the main window and its controller."""
        self.main_window = MainWindow(
            settings=self.settings,
            get_active_instance=lambda: self.settings_controller.active_instance,
            set_instance=self.settings_controller.set_instance,
            show_settings_dialog=self.settings_controller.show_settings_dialog,
            metadata_controller=self.metadata_controller,
        )
        self.main_window_controller = MainWindowController(self.main_window)

    def run(self) -> int:
        """Runs the main application loop after initializing the main window."""
        self.main_window.show()
        self.main_window.initialize_content(is_initial=True)
        # If the window was closed during initialization (e.g. user closed during
        # mod scanning), skip the main event loop — Qt resets the quit flag in exec()
        # so a prior quit() from quitOnLastWindowClosed would have no effect and the
        # event loop would block forever with no visible windows.
        if not self.main_window.isVisible():
            return 0
        mark_gui_alive()
        self._mcp_drain_timer.start(400)
        self._sync_mcp_subprocess()
        return self.app.exec()

    def _shutdown_mcp(self) -> None:
        self._mcp_drain_timer.stop()
        clear_gui_alive()
        stop_mcp_subprocess()

    def _drain_mcp_commands(self) -> None:
        bus = EventBus()
        for cmd in drain():
            ctype = cmd.get("type", "")
            if ctype == "steamcmd_download":
                pfids = cmd.get("publishedfileids", [])
                if isinstance(pfids, list) and pfids:
                    bus.do_steamcmd_download.emit([str(p) for p in pfids])
            elif ctype == "sort":
                bus.do_sort_active_mods_list.emit()
            elif ctype == "save":
                bus.do_save_active_mods_list.emit()
            elif ctype == "run_game":
                bus.do_run_game.emit()

    def _schedule_mcp_sync(self) -> None:
        self._mcp_sync_timer.start(300)

    def _sync_mcp_subprocess(self) -> None:
        sync_mcp_subprocess(self.settings)

    def shutdown_watchdog(self) -> None:
        """Initiates the shutdown procedure for the watchdog."""
        self.main_window.shutdown_watchdog()

    def quit(self) -> None:
        """Exits the application."""
        self.app.quit()
