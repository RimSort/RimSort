import logging
import os
import sys
import traceback
from pathlib import Path

from PySide2.QtCore import QSize
from PySide2.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from util.error import show_fatal_error
from util.proxy_style import ProxyStyle
from view.game_configuration_panel import GameConfiguration
from view.main_content_panel import MainContent
from view.status_panel import Status

# The log file is stored inside the app directory (on Mac, it is inside the package)
logging_file_path = Path(os.path.join(os.path.dirname(__file__), "rs_log.log"))

# Only the most recent log file is kept
logging_file_path.unlink(missing_ok=True)

# Configure logger settings
logging.basicConfig(
    format="[%(levelname)s][%(asctime)s][%(process)d][%(name)s][%(funcName)s][%(lineno)d] : %(message)s",
    filename=logging_file_path,
    level=logging.DEBUG,
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


try:
    app = QApplication(sys.argv)
    app.setApplicationName("RimSort")
    logger.info("Setting application styles")
    app.setStyle(ProxyStyle())  # Add proxy style for overriding some styling elements
    app.setStyleSheet(  # Add style sheet for styling layouts and widgets
        Path(os.path.join(os.path.dirname(__file__), "data/style.qss")).read_text()
    )
    window = MainWindow()
    logger.info("Showing MainWindow")
    window.show()
    app.exec_()
except:
    # Catch exceptions during initial application instantiation
    # Uncaught exceptions during the application loop are caught with excepthook
    stacktrace = traceback.format_exc()
    logger.error(
        "The main application instantiation has failed with an uncaught exception:"
    )
    logger.error(stacktrace)
    show_fatal_error(details=stacktrace)
finally:
    logger.info("Exiting program")
    sys.exit()
