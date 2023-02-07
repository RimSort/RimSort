import os
import platform
import subprocess
from functools import partial
from typing import Any

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


class GameConfiguration(QObject):
    """
    This class controls the layout and functionality of the top-most
    panel of the GUI, containing the paths to ModsConfig.xml, workshop
    mods, etc. Subclasses QObject to allow emitting signals.
    """

    # Signal emitter for this class
    configuration_signal = Signal(str)

    def __init__(self) -> None:
        """
        Initialize the game configuration.
        Construct the layout and add widgets.
        Emit signals where applicable.
        """
        super(GameConfiguration, self).__init__()

        # Base layout
        self._panel = QVBoxLayout()
        # Spacing between edge and layout, 0 on bottom (closer to next layout)
        self._panel.setContentsMargins(7, 7, 7, 0)

        # Container layouts
        # self.client_settings_row = QHBoxLayout()
        self.game_folder_row = QHBoxLayout()
        self.config_folder_row = QHBoxLayout()
        self.workshop_folder_row = QHBoxLayout()

        # Instantiate widgets
        self.game_folder_open_button = QPushButton("RimWorld App")
        self.game_folder_open_button.clicked.connect(
            partial(self.open_directory, self.get_game_folder_path)
        )
        self.game_folder_open_button.setObjectName("LeftButton")
        self.game_folder_line = QLineEdit()
        self.game_folder_line.setDisabled(True)
        self.game_folder_select_button = QPushButton("...")
        self.game_folder_select_button.clicked.connect(self.set_game_executable)
        self.game_folder_select_button.setObjectName("RightButton")

        self.config_folder_open_button = QPushButton("Config File")
        self.config_folder_open_button.clicked.connect(
            partial(self.open_directory, self.get_mods_config_path)
        )
        self.config_folder_open_button.setObjectName("LeftButton")
        self.config_folder_line = QLineEdit()
        self.config_folder_line.setDisabled(True)
        self.config_folder_select_button = QPushButton("...")
        self.config_folder_select_button.clicked.connect(self.set_config_folder)
        self.config_folder_select_button.setObjectName("RightButton")

        self.workshop_folder_open_button = QPushButton("Steam Mods")
        self.workshop_folder_open_button.clicked.connect(
            partial(self.open_directory, self.get_workshop_folder_path)
        )
        self.workshop_folder_open_button.setObjectName("LeftButton")
        self.workshop_folder_line = QLineEdit()
        self.workshop_folder_line.setDisabled(True)
        self.workshop_folder_select_button = QPushButton("...")
        self.workshop_folder_select_button.clicked.connect(self.set_workshop_folder)
        self.workshop_folder_select_button.setObjectName("RightButton")

        # Add widgets to container layouts
        self.game_folder_row.addWidget(self.game_folder_open_button)
        self.game_folder_row.addWidget(self.game_folder_line)
        self.game_folder_row.addWidget(self.game_folder_select_button)

        self.config_folder_row.addWidget(self.config_folder_open_button)
        self.config_folder_row.addWidget(self.config_folder_line)
        self.config_folder_row.addWidget(self.config_folder_select_button)

        self.workshop_folder_row.addWidget(self.workshop_folder_open_button)
        self.workshop_folder_row.addWidget(self.workshop_folder_line)
        self.workshop_folder_row.addWidget(self.workshop_folder_select_button)

        # Add container layouts to base layout
        # self._panel.addLayout(self.client_settings_row)
        self._panel.addLayout(self.game_folder_row)
        self._panel.addLayout(self.config_folder_row)
        self._panel.addLayout(self.workshop_folder_row)

    @property
    def panel(self):
        return self._panel

    def open_directory(self, callable: Any) -> None:
        """
        This slot is called when the user presses any of the left-side
        game configuration buttons to open up corresponding folders.

        :param callable: function to get the corresponding folder path
        """
        path = callable()
        if os.path.exists(path):
            if os.path.isfile(path) or path.endswith(".app"):
                self.platform_specific_open(os.path.dirname(path))
            else:
                self.platform_specific_open(path)
        else:
            print("Path is invalid")  # TODO

    def platform_specific_open(self, path: str) -> None:
        """
        Function to open a folder in the platform-specific
        explorer app.

        :param path: path to open
        """
        system_name = platform.system()
        if system_name == "Darwin":
            subprocess.Popen(["open", path])
        elif system_name == "Windows":
            os.startfile(path)
        elif system_name == "Linux":
            subprocess.Popen(["xdg-open", path])
        else:
            print("Unknown System")  # TODO

    def set_game_executable(self) -> None:
        """
        Open a file dialog to allow the user to select the game executable.
        """
        start_dir = ""
        possible_dir = self.get_game_folder_path()
        if os.path.exists(possible_dir):
            start_dir = os.path.dirname(possible_dir)
        game_executable_path = QFileDialog.getOpenFileName(
            caption="Open RimWorld App",
            dir=start_dir,
            filter="APP (*.app);;EXE (*.exe)",
        )
        self.game_folder_line.setText(game_executable_path[0])

    def set_config_folder(self) -> None:
        """
        Open a file dialog to allow the user to select the ModsConfig.xml.
        """
        start_dir = ""
        possible_dir = self.get_mods_config_path()
        if os.path.exists(possible_dir):
            start_dir = os.path.dirname(possible_dir)
        mods_config_path = QFileDialog.getOpenFileName(
            caption="Select Mods Config", dir=start_dir, filter="XML (*.xml)"
        )
        self.config_folder_line.setText(mods_config_path[0])
        # TODO refresh mods

    def set_workshop_folder(self) -> None:
        """
        Open a file dialog to allow the user to select a directory
        to set as the workshop folder.
        """
        start_dir = ""
        possible_dir = self.get_workshop_folder_path()
        if os.path.exists(possible_dir):
            start_dir = possible_dir
        workshop_path = str(
            QFileDialog.getExistingDirectory(
                caption="Select Workshop Folder", dir=start_dir
            )
        )
        self.workshop_folder_line.setText(workshop_path)
        # TODO refresh mods

    def get_game_folder_path(self) -> str:
        """
        Return a manually-entered game folder path if it exists.
        Otherwise, return the platform-specific placeholder path.

        :return: path to game folder
        """
        if self.game_folder_line.text():
            return self.game_folder_line.text()
        else:
            return self.game_folder_line.placeholderText()

    def get_mods_config_path(self) -> str:
        """
        Return a manually-entered ModsConfig.xml path if it exists.
        Otherwise, return the platform-specific placeholder path.

        :return: path to ModsConfig.xml
        """
        if self.config_folder_line.text():
            return self.config_folder_line.text()
        else:
            return self.config_folder_line.placeholderText()

    def get_workshop_folder_path(self) -> str:
        """
        Return a manually-entered workshop folder path if it exists.
        Otherwise, return the platform-specific placeholder path.

        :return: path to workshop folder
        """
        if self.workshop_folder_line.text():
            return self.workshop_folder_line.text()
        else:
            return self.workshop_folder_line.placeholderText()
