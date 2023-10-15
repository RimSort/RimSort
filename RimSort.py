import sys

from multiprocessing import current_process, freeze_support, set_start_method

import os
from pathlib import Path
import platform
from requests.exceptions import HTTPError
from tempfile import gettempdir
import traceback
from typing import Any, Optional

from logger_tt import handlers, logger, setup_logging
from logging import getLogger, WARNING
from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

SYSTEM = platform.system()
# Watchdog conditionals
if SYSTEM == "Darwin":
    from watchdog.observers import Observer

    # Comment to see logging for watchdog handler on Darwin
    getLogger("watchdog.observers.fsevents").setLevel(WARNING)
elif SYSTEM == "Linux":
    from watchdog.observers import Observer

    # Comment to see logging for watchdog handler on Linux
    getLogger("watchdog.observers.inotify_buffer").setLevel(WARNING)
elif SYSTEM == "Windows":
    from watchdog.observers.polling import PollingObserver

    # Comment to see logging for watchdog handler on Windows
    # This is a stub if it's ever even needed...
    # I still can't figure out why it won't log at all on Windows...?
    # getLogger("").setLevel(WARNING)

from model.dialogue import show_fatal_error
from util.proxy_style import ProxyStyle
from util.watchdog import RSFileSystemEventHandler
from view.game_configuration_panel import GameConfiguration
from view.main_content_panel import MainContent
from view.status_panel import Status


class MainWindow(QMainWindow):
    """
    Subclass QMainWindow to customize the main application window.
    """

    def __init__(self, DEBUG_MODE=None) -> None:
        """
        Initialize the main application window. Construct the layout,
        add the three main views, and set up relevant signals and slots.
        """
        logger.info("Initializing MainWindow")
        super(MainWindow, self).__init__()

        # Create the main application window
        self.DEBUG_MODE = DEBUG_MODE
        self.init = None  # Content initialization should only fire on startup. Otherwise, this is handled by Refresh button
        self.version_string = "Alpha-v1.0.6.2-hf"

        # Check for SHA and append to version string if found
        sha_file = str(Path(os.path.join(data_path, "SHA")).resolve())
        if os.path.exists(sha_file):
            with open(sha_file) as f:
                sha = f.read().strip()
            self.version_string += f" [Edge {sha}]"

        # Watchdog
        self.watchdog_event_handler = None
        self.watchdog_observer = None

        # Setup the window
        self.setWindowTitle(f"RimSort {self.version_string}")
        self.setMinimumSize(QSize(1024, 768))

        # Create the window layout
        app_layout = QVBoxLayout()
        app_layout.setContentsMargins(0, 0, 0, 0)  # Space from main layout to border
        app_layout.setSpacing(0)  # Space between widgets

        # Create various panels on the application GUI
        self.game_configuration = GameConfiguration.instance(
            DEBUG_MODE=DEBUG_MODE, RIMSORT_VERSION=self.version_string
        )
        self.main_content_panel = MainContent()
        self.bottom_panel = Status()

        # Connect the game configuration actions signals to Status panel to display fading action text
        self.game_configuration.configuration_signal.connect(
            self.bottom_panel.actions_slot
        )
        self.game_configuration.settings_panel.actions_signal.connect(
            self.bottom_panel.actions_slot
        )
        # Connect the actions_signal to Status panel to display fading action text
        self.main_content_panel.actions_panel.actions_signal.connect(
            self.bottom_panel.actions_slot
        )
        self.main_content_panel.status_signal.connect(self.bottom_panel.actions_slot)

        # Arrange all panels vertically on the main window layout
        app_layout.addLayout(self.game_configuration.panel)
        app_layout.addWidget(self.main_content_panel.main_layout_frame)
        app_layout.addWidget(self.bottom_panel.frame)

        # Display all items
        widget = QWidget()
        widget.setLayout(app_layout)
        self.setCentralWidget(widget)

        logger.debug("Finished MainWindow initialization")

    def showEvent(self, event) -> None:
        # Call the original showEvent handler
        super().showEvent(event)
        if not self.init:
            # HIDE/SHOW FOLDER ROWS BASED ON PREFERENCE
            if self.game_configuration.show_folder_rows:
                self.game_configuration.hide_show_folder_rows_button.setText(
                    "Hide paths"
                )
            else:
                self.game_configuration.hide_show_folder_rows_button.setText(
                    "Show paths"
                )
            # set visibility
            self.game_configuration.game_folder_frame.setVisible(
                self.game_configuration.show_folder_rows
            )
            self.game_configuration.config_folder_frame.setVisible(
                self.game_configuration.show_folder_rows
            )
            self.game_configuration.local_folder_frame.setVisible(
                self.game_configuration.show_folder_rows
            )
            self.game_configuration.workshop_folder_frame.setVisible(
                self.game_configuration.show_folder_rows
            )

    def __initialize_content(self) -> None:
        self.init = True

        # IF CHECK FOR UPDATE ON STARTUP...
        if self.game_configuration.check_for_updates_action.isChecked():
            self.main_content_panel.actions_slot("check_for_update")

        # REFRESH CONFIGURED METADATA
        self.main_content_panel._do_refresh(is_initial=True)

        # CHECK USER PREFERENCE FOR WATCHDOG
        if self.game_configuration.watchdog_toggle:
            # Setup watchdog
            self.__initialize_watchdog()

    def __initialize_watchdog(self) -> None:
        logger.info("Initializing watchdog FS Observer")
        # INITIALIZE WATCHDOG - WE WAIT TO START UNTIL DONE PARSING MOD LIST
        game_folder_path = self.game_configuration.game_folder_line.text()
        local_folder_path = self.game_configuration.local_folder_line.text()
        workshop_folder_path = self.game_configuration.workshop_folder_line.text()
        self.watchdog_event_handler = RSFileSystemEventHandler()
        if SYSTEM == "Windows":
            self.watchdog_observer = PollingObserver()
        else:
            self.watchdog_observer = Observer()
        if game_folder_path and game_folder_path != "":
            self.watchdog_observer.schedule(
                self.watchdog_event_handler,
                game_folder_path,
                # recursive=True,
            )
        if local_folder_path and local_folder_path != "":
            self.watchdog_observer.schedule(
                self.watchdog_event_handler,
                local_folder_path,
                # recursive=True,
            )
        if workshop_folder_path and workshop_folder_path != "":
            self.watchdog_observer.schedule(
                self.watchdog_event_handler,
                workshop_folder_path,
                # recursive=True,
            )
        # Connect watchdog to our refresh button animation
        self.watchdog_event_handler.file_changes_signal.connect(
            self.main_content_panel._do_refresh_animation
        )
        # Connect main content signal so it can stop watchdog
        self.main_content_panel.stop_watchdog_signal.connect(self.__shutdown_watchdog)
        # Start watchdog
        try:
            self.watchdog_observer.start()
        except Exception as e:
            logger.warning(
                f"Unable to initialize watchdog Observer due to exception: {e.__class__.__name__}"
            )

    def __shutdown_watchdog(self) -> None:
        if self.watchdog_observer and self.watchdog_observer.is_alive():
            self.watchdog_observer.stop()
            self.watchdog_observer.join()
            self.watchdog_observer = None


def handle_exception(exc_type, exc_value, exc_traceback):
    """
    This function is called (through excepthook) when the main application
    loop encounters an uncaught exception. When this happens, the error is
    logged to the log file and a Fatal QMessageBox is shown.
    """

    # Ignore KeyboardInterrupt exceptions, for when running through the terminal
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    else:  # Anything else, we want to log an error and notify the user
        logger.error(
            "The main application loop has failed with an uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        show_fatal_error(
            title="RimSort crashed",
            text="The RimSort application crashed! Sorry for the inconvenience!",
            information="Please contact us on the Discord/Github to report the issue.",
            details="".join(
                traceback.format_exception(exc_type, exc_value, exc_traceback)
            ),
        )

    sys.exit()


# Uncaught exceptions during the application loop are handled
# through the function above
sys.excepthook = handle_exception


def main_thread() -> None:
    try:
        # Create the application
        app = QApplication(sys.argv)
        app.setApplicationName("RimSort")
        # Get styling from game configuration
        logger.debug("Setting application style")
        app.setStyle(
            ProxyStyle()
        )  # Add proxy style for overriding some styling elements
        app.setStyleSheet(  # Add style sheet for styling layouts and widgets
            Path(os.path.join(os.path.dirname(__file__), "data/style.qss")).read_text()
        )
        # Create the main window
        window = MainWindow(DEBUG_MODE=DEBUG_MODE)
        logger.info("Showing MainWindow")
        window.show()
        window.__initialize_content()
        app.exec()
    except Exception as e:
        # Catch exceptions during initial application instantiation
        # Uncaught exceptions during the application loop are caught with excepthook
        if e is SystemExit:
            logger.warning("Exiting application")
        elif (
            e.__class__.__name__ == "HTTPError" or e.__class__.__name__ == "SSLError"
        ):  # requests.exceptions.HTTPError OR urllib3.exceptions.SSLError
            stacktrace = traceback.format_exc()
            pattern = "&key="
            stacktrace = stacktrace[
                : len(stacktrace)
                - (len(stacktrace) - (stacktrace.find(pattern) + len(pattern)))
            ]  # If an HTTPError from steam/urllib3 module(s) somehow is uncaught, try to remove the Steam API key from the stacktrace
        else:
            stacktrace = traceback.format_exc()
        logger.error(
            "The main application instantiation has failed with an uncaught exception:"
        )
        logger.error(stacktrace)
        show_fatal_error(details=stacktrace)
    finally:
        if "window" in locals():
            try:
                logger.debug("Stopping watchdog...")
                window.__shutdown_watchdog()
            except:
                stacktrace = traceback.format_exc()
                logger.warning(
                    f"watchdog received the following exception while exiting: {stacktrace}"
                )
        logger.info("Exiting application!")
        sys.exit()


if __name__ == "__main__":
    # If RimSort is running from a --onefile Nuitka build, there are some nuances to consider:
    # https://nuitka.net/doc/user-manual.html#onefile-finding-files
    # You can override by passing --onefile-tempdir-spec to `nuitka`
    # See also: https://nuitka.net/doc/user-manual.html#use-case-4-program-distribution
    # Otherwise, use sys.argv[0] to get the actual relative path to the executable
    #########################################################################################
    #
    # Setup logging
    #
    data_path = str(Path(os.path.join(os.path.dirname(__file__), "data")).resolve())
    debug_file = str(Path(os.path.join(data_path, "DEBUG")).resolve())
    # Check if 'RimSort.log' exists and rename it to 'RimSort.old.log'
    log_file_path = str(Path(os.path.join(gettempdir(), "RimSort.log")).resolve())
    log_old_file_path = str(
        Path(os.path.join(gettempdir(), "RimSort.old.log")).resolve()
    )
    # Rename old log if found
    if os.path.exists(log_file_path):
        os.replace(log_file_path, log_old_file_path)
    if os.path.exists(log_file_path):
        os.rename(log_file_path, log_old_file_path)
    # Enable logging options based on presence of DEBUG file
    if os.path.exists(debug_file):
        logging_config_path = str(
            Path(os.path.join(data_path, "logger_tt-DEBUG.json")).resolve()
        )
        DEBUG_MODE = True
    else:
        logging_config_path = str(
            Path(os.path.join(data_path, "logger_tt-INFO.json")).resolve()
        )
        DEBUG_MODE = False
    # Setup log file
    logging_file_path = str(Path(os.path.join(gettempdir(), "RimSort.log")).resolve())
    # Setup Environment
    if "__compiled__" in globals():
        os.environ[
            "QTWEBENGINE_LOCALES_PATH"
        ] = f'{str(Path(os.path.join(os.path.dirname(__file__), "qtwebengine_locales")).resolve())}'
    if SYSTEM == "Linux":
        # logger_tt
        setup_logging(
            config_path=logging_config_path,
            log_path=logging_file_path,
            use_multiprocessing="fork",
        )
        # Disable IBus integration on Linux
        os.environ["QT_IM_MODULE"] = ""
    else:
        # logger_tt
        setup_logging(
            config_path=logging_config_path,
            log_path=logging_file_path,
            use_multiprocessing="spawn",
        )
    # This check is used whether RimSort is running via Nuitka bundle
    if "__compiled__" in globals():
        logger.debug("Running using Nuitka bundle")
        if SYSTEM != "Linux":
            logger.warning(  # MacOS and Windows do not support fork, and can only use spawn
                "Non-Linux platform detected: using multiprocessing.freeze_support() & setting 'spawn' as MP method"
            )
            freeze_support()
            set_start_method("spawn")
    else:
        logger.debug("Running using Python interpreter")
    logger.debug("Initializing RimSort application")
    main_thread()
