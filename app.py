import logging
import os
import sys
import traceback
from pathlib import Path

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from util.error import show_fatal_error
from util.proxy_style import ProxyStyle
from view.game_configuration_panel import GameConfiguration
from view.main_content_panel import MainContent
from view.status_panel import Status

logging_file_path = Path(os.path.join(os.path.dirname(__file__), "rs_log.log"))
logging.basicConfig(
    format="[%(levelname)s][%(asctime)s][%(name)s][%(funcName)s][%(lineno)d] : %(message)s",
    filename=logging_file_path,
    level=logging.DEBUG,
)
logger = logging.getLogger(__name__)
logger.info("Starting RimSort application")


class MainWindow(QMainWindow):
    """
    Subclass QMainWindow to customize your application's main window
    """

    def __init__(self) -> None:
        logger.info("Starting MainWindow initialization")
        super(MainWindow, self).__init__()

        # Create the main application window
        self.setWindowTitle("RimSort Alpha v1.0.0")
        self.setFixedSize(QSize(1100, 700))  # TODO: support resizing

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
    stacktrace = traceback.format_exc()
    logger.info("Main application loop has failed with an uncaught exception:")
    logger.info(stacktrace)
    show_fatal_error(stacktrace)
finally:
    logger.info("Exiting program")
    sys.exit()
