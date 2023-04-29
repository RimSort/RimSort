import multiprocessing
import sys

print(f"RimSort.py: {multiprocessing.current_process()}")
print(f"__name__: {__name__}\nsys.argv: {sys.argv}")
from multiprocessing import freeze_support, set_start_method
import os
from pathlib import Path
import platform
from requests.exceptions import HTTPError
import traceback

from logger_tt import handlers, logger, setup_logging
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from model.dialogue import show_fatal_error
from util.proxy_style import ProxyStyle
from view.game_configuration_panel import GameConfiguration
from view.main_content_panel import MainContent
from view.status_panel import Status

is_nuitka = "__compiled__" in globals()
system = platform.system()

# If RimSort is running from a --onefile Nuitka build, there are some nuances to consider:
# https://nuitka.net/doc/user-manual.html#onefile-finding-files
# You can override by passing --onefile-tempdir-spec to `nuitka`
# See also: https://nuitka.net/doc/user-manual.html#use-case-4-program-distribution
# Otherwise, use sys.argv[0] to get the actual relative path to the executable
data_path = os.path.join(os.path.dirname(__file__), "data")
logging_config_path = os.path.join(data_path, "logging_config.json")
logging_file_path = os.path.join(os.path.dirname(sys.argv[0]), "RimSort.log")

if system == "Linux":
    setup_logging(
        config_path=logging_config_path,
        log_path=logging_file_path,
        use_multiprocessing="fork",
    )
else:
    setup_logging(
        config_path=logging_config_path,
        log_path=logging_file_path,
        use_multiprocessing="spawn",
    )


def handle_exception(exc_type, exc_value, exc_traceback):
    """
    This function is called (through excepthook) when the main application
    loop encounters an uncaught exception. When this happens, the error is
    logged to the log file and a Fatal QMessageBox is shown.
    """

    # Ignore KeyboardInterrupt exceptions, for when running through the terminal
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.error(
        "The main application loop has failed with an uncaught exception",
        exc_info=(exc_type, exc_value, exc_traceback),
    )
    show_fatal_error(
        details="".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    )
    sys.exit()


# Uncaught exceptions during the application loop are handled
# through the function above
sys.excepthook = handle_exception


class MainWindow(QMainWindow):
    """
    Subclass QMainWindow to customize the main application window.
    """

    def __init__(self) -> None:
        """
        Initialize the main application window. Construct the layout,
        add the three main views, and set up relevant signals and slots.
        """
        logger.info("Starting MainWindow initialization")
        super(MainWindow, self).__init__()

        # Create the main application window
        self.setWindowTitle("RimSort Alpha v1.0.4")
        self.setMinimumSize(QSize(1200, 700))

        # Create the window layout
        app_layout = QVBoxLayout()
        app_layout.setContentsMargins(0, 0, 0, 0)  # Space from main layout to border
        app_layout.setSpacing(0)  # Space between widgets

        # Create various panels on the application GUI
        logger.info("Start creating main panels")
        self.game_configuration_panel = GameConfiguration()
        self.main_content_panel = MainContent(self.game_configuration_panel)
        self.bottom_panel = Status()
        logger.info("Finished creating main panels")

        logger.info("Connecting MainWindow signals and slots")
        # Connect the actions_signal to Status panel to display fading action text
        self.main_content_panel.actions_panel.actions_signal.connect(
            self.bottom_panel.actions_slot
        )

        # Arrange all panels vertically on the main window layout
        app_layout.addLayout(self.game_configuration_panel.panel)
        app_layout.addWidget(self.main_content_panel.main_layout_frame)
        app_layout.addWidget(self.bottom_panel.frame)

        # Display all items
        widget = QWidget()
        widget.setLayout(app_layout)
        self.setCentralWidget(widget)

        logger.info("Finished MainWindow initialization")


def main_thread():
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("RimSort")
        logger.info("Setting application styles")
        app.setStyle(
            ProxyStyle()
        )  # Add proxy style for overriding some styling elements
        app.setStyleSheet(  # Add style sheet for styling layouts and widgets
            Path(os.path.join(os.path.dirname(__file__), "data/style.qss")).read_text()
        )
        window = MainWindow()
        logger.info("Showing MainWindow")
        window.show()
        app.exec()
    except Exception as e:
        # Catch exceptions during initial application instantiation
        # Uncaught exceptions during the application loop are caught with excepthook
        if (
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
        logger.debug("Stopping watchdog...")
        window.main_content_panel.game_configuration_config_observer.stop()
        window.main_content_panel.game_configuration_config_observer.join()
        logger.info("Exiting!")
        sys.exit()


if __name__ == "__main__":
    # This check was PREVIOUSLY used to check whether RimSort was running via PyInstaller
    # TODO: Remove this.
    # if getattr(sys, "frozen", False):
    #     logger.warning("Running using PyInstaller bundle")
    #     if system != "Linux":
    #         logger.warning(
    #             "Non-Linux platform detected: using multiprocessing.freeze_support() & setting 'spawn' as MP method"
    #         )
    #         freeze_support()
    #         set_start_method('spawn')
    # else:
    #     logger.warning("Running using Python interpreter")

    # This check is used whether RimSort is running via Nuitka bundle
    if is_nuitka:
        logger.warning("Running using Nuitka bundle")
        if system != "Linux":
            logger.warning(
                "Non-Linux platform detected: using multiprocessing.freeze_support() & setting 'spawn' as MP method"
            )
            freeze_support()
            set_start_method("spawn")
    else:
        logger.warning("Running using Python interpreter")
    logger.info("Starting RimSort application")
    main_thread()
