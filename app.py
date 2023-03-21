import logging
import os
import platform
import sys
import traceback
from pathlib import Path
from requests.exceptions import HTTPError

from logger_tt import setup_logging
from PySide2.QtCore import QSize
from PySide2.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from util.error import show_fatal_error
from util.proxy_style import ProxyStyle
from view.game_configuration_panel import GameConfiguration
from view.main_content_panel import MainContent
from view.status_panel import Status

# The log file is stored inside the RimSort install directory (on Mac, it is inside the package)
data_path = os.path.join(os.path.dirname(__file__), "data")
logging_config_path = os.path.join(data_path, "logging_config.json")
logging_file_path = os.path.join(data_path, "RimSort.log")

if platform.system() == "Linux":
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

logger = logging.getLogger(__name__)
logger.info("Starting RimSort application")


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
        self.setWindowTitle("RimSort Alpha v1.0.3")
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


if __name__ == "__main__":
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
        app.exec_()
    except Exception as e:
        # Catch exceptions during initial application instantiation
        # Uncaught exceptions during the application loop are caught with excepthook
        if e.__class__.__name__ == "HTTPError":  # requests.exceptions.HTTPError
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
        logger.info("Exiting program")
        sys.exit()
