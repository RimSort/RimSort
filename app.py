import os
import sys
import traceback
from pathlib import Path

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from util.error import show_fatal
from util.proxy_style import ProxyStyle
from view.game_configuration_panel import GameConfiguration
from view.main_content_panel import MainContent
from view.status_panel import Status


class MainWindow(QMainWindow):
    """
    Subclass QMainWindow to customize your application's main window
    """

    def __init__(self) -> None:
        super(MainWindow, self).__init__()

        # Create the main application window
        self.setWindowTitle("RimSort Alpha v1.0.0")
        self.setFixedSize(QSize(1100, 700))  # TODO: support resizing

        # Create the main application layout
        app_layout = QVBoxLayout()
        app_layout.setContentsMargins(0, 0, 0, 0)  # Space from main layout to border
        app_layout.setSpacing(0)  # Space between widgets

        # Create various panels on the application GUI
        self.game_configuration_panel = GameConfiguration()
        self.main_content_panel = MainContent(self.game_configuration_panel)
        self.bottom_panel = Status()

        # Connect Signals and Slots
        # ======================================
        # Connect actions signal to Status panel to display fading action text
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

        print("Finished MainWindow initialization")


try:
    app = QApplication(sys.argv)
    app.setApplicationName("RimSort")
    app.setStyle(ProxyStyle())  # Add proxy style for overriding some styling elements
    app.setStyleSheet(  # Add style sheet for styling layouts and widgets
        Path(os.path.join(os.path.dirname(__file__), "data/style.qss")).read_text()
    )
    window = MainWindow()
    window.show()
    app.exec_()
except Exception as e:
    show_fatal(details=str(traceback.format_exc()))
finally:
    sys.exit()
