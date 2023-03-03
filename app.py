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

logging_file_path = Path(os.path.join(os.path.dirname(__file__), "rs_log.log"))

# Delete previous log file
logging_file_path.unlink(missing_ok=True)

logging.basicConfig(
    format="[%(levelname)s][%(asctime)s][%(process)d][%(name)s][%(funcName)s][%(lineno)d] : %(message)s",
    filename=logging_file_path,
    level=logging.DEBUG,
)
logger = logging.getLogger(__name__)
logger.info("Starting RimSort application")


def handle_exception(exc_type, exc_value, exc_traceback):
    # Ignore KeyboardInterrupt
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.error(
        "Main application loop has failed with an uncaught exception",
        exc_info=(exc_type, exc_value, exc_traceback),
    )
    show_fatal_error(
        details="".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    )
    sys.exit()


sys.excepthook = handle_exception


class MainWindow(QMainWindow):
    """
    Subclass QMainWindow to customize your application's main window
    """

    def __init__(self) -> None:
        logger.info("Starting MainWindow initialization")
        super(MainWindow, self).__init__()

        # Create the main application window
        self.setWindowTitle("RimSort Alpha v1.0.2")
        self.setFixedSize(QSize(1200, 700))  # TODO: support resizing

        # Create the main application layout
        app_layout = QVBoxLayout()
        app_layout.setContentsMargins(0, 0, 0, 0)  # Space from main layout to border
        app_layout.setSpacing(0)  # Space between widgets

        # Create various panels on the application GUI
        logger.info("Start creating main panels")
        self.game_configuration_panel = GameConfiguration()
        self.main_content_panel = MainContent(self.game_configuration_panel)
        self.bottom_panel = Status()
        logger.info("Finished creating main panels")

        # Connect Signals and Slots
        # ======================================
        # Connect actions signal to Status panel to display fading action text
        logger.info("Connecting MainWindow signals and slots")
        self.main_content_panel.actions_panel.actions_signal.connect(
            self.bottom_panel.actions_slot
        )

        # Arrange all panels on the application GUI grid
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
    # Note: this only works for uncaught exceptions during initial
    # application instantiation. Other uncaught exceptions that occur during
    # the application flow are caught with sys.excepthook
    stacktrace = traceback.format_exc()
    logger.error(
        "Main application instantiation has failed with an uncaught exception:"
    )
    logger.error(stacktrace)
    show_fatal_error(details=stacktrace)
finally:
    logger.info("Exiting program")
    sys.exit()
