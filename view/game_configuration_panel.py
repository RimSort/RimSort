import os
import platform
import subprocess
from functools import partial
from typing import Any
import json

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from util.error import show_warning


class GameConfiguration(QObject):
    """
    This class controls the layout and functionality of the top-most
    panel of the GUI, containing the paths to the ModsConfig.xml folder,
    workshop folder, and game executable folder. It is also responsible
    for initializing the storage feature, getting paths data out of
    the storage feature, and allowing for setting paths and writing those
    paths to the persistent storage.

    It Subclasses QObject to allow emitting signals.
    """

    # Signal emitter for this class
    configuration_signal = Signal(str)

    def __init__(self) -> None:
        """
        Initialize the game configuration.
        """
        super(GameConfiguration, self).__init__()

        # BASE LAYOUT
        self._panel = QVBoxLayout()
        # Represents spacing between edge and layout
        # Set to 0 on the bottom to maintain consistent spacing to the main content panel
        self._panel.setContentsMargins(7, 7, 7, 0)

        # CONTAINER LAYOUTS
        # self.client_settings_row = QHBoxLayout() # TODO: NOT IMPLEMENTED
        self.game_folder_row = QHBoxLayout()
        self.config_folder_row = QHBoxLayout()
        self.local_folder_row = QHBoxLayout()
        self.workshop_folder_row = QHBoxLayout()

        # INSTANTIATE WIDGETS
        self.game_folder_open_button = QPushButton("RimWorld App")
        self.game_folder_open_button.clicked.connect(
            partial(self.open_directory, self.get_game_folder_path)
        )
        self.game_folder_open_button.setObjectName("LeftButton")
        self.game_folder_line = QLineEdit()
        self.game_folder_line.setDisabled(True)
        self.game_folder_line.setPlaceholderText(
            "Unknown, please select the game folder"
        )
        self.game_folder_select_button = QPushButton("...")
        self.game_folder_select_button.clicked.connect(self.set_game_exe_folder)
        self.game_folder_select_button.setObjectName("RightButton")

        self.config_folder_open_button = QPushButton("Config File")
        self.config_folder_open_button.clicked.connect(
            partial(self.open_directory, self.get_config_folder_path)
        )
        self.config_folder_open_button.setObjectName("LeftButton")
        self.config_folder_line = QLineEdit()
        self.config_folder_line.setDisabled(True)
        self.config_folder_line.setPlaceholderText(
            "Unknown, please select the ModsConfig.xml folder"
        )
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
        self.workshop_folder_line.setPlaceholderText(
            "Unknown, please select the RimWorld workshop folder"
        )
        self.workshop_folder_select_button = QPushButton("...")
        self.workshop_folder_select_button.clicked.connect(self.set_workshop_folder)
        self.workshop_folder_select_button.setObjectName("RightButton")

        self.local_folder_open_button = QPushButton("Local Mods")
        self.local_folder_open_button.clicked.connect(
            partial(self.open_directory, self.get_local_folder_path)
        )
        self.local_folder_open_button.setObjectName("LeftButton")
        self.local_folder_line = QLineEdit()
        self.local_folder_line.setDisabled(True)
        self.local_folder_line.setPlaceholderText(
            "Unknown, please select the RimWorld local mods folder"
        )
        self.local_folder_select_button = QPushButton("...")
        self.local_folder_select_button.clicked.connect(self.set_local_folder)
        self.local_folder_select_button.setObjectName("RightButton")

        # WIDGETS INTO CONTAINER LAYOUTS
        self.game_folder_row.addWidget(self.game_folder_open_button)
        self.game_folder_row.addWidget(self.game_folder_line)
        self.game_folder_row.addWidget(self.game_folder_select_button)

        self.config_folder_row.addWidget(self.config_folder_open_button)
        self.config_folder_row.addWidget(self.config_folder_line)
        self.config_folder_row.addWidget(self.config_folder_select_button)

        self.workshop_folder_row.addWidget(self.workshop_folder_open_button)
        self.workshop_folder_row.addWidget(self.workshop_folder_line)
        self.workshop_folder_row.addWidget(self.workshop_folder_select_button)

        self.local_folder_row.addWidget(self.local_folder_open_button)
        self.local_folder_row.addWidget(self.local_folder_line)
        self.local_folder_row.addWidget(self.local_folder_select_button)

        # CONTAINER LAYOUTS INTO BASE LAYOUT
        # self._panel.addLayout(self.client_settings_row): TODO: NOT IMPLEMENTED
        self._panel.addLayout(self.game_folder_row)
        self._panel.addLayout(self.config_folder_row)
        self._panel.addLayout(self.workshop_folder_row)
        self._panel.addLayout(self.local_folder_row)

        # INITIALIZE WIDGETS / FEATURES
        self.initialize_storage()

    @property
    def panel(self):
        return self._panel

    def initialize_storage(self) -> None:
        """
        Initialize the app's storage feature.
        If the storage path or settings.json file do not exist,
        create them. If they do exist, set the path widgets
        to have paths written on the settings.json.
        """
        storage_path = QStandardPaths.writableLocation(
            QStandardPaths.AppLocalDataLocation
        )
        print(storage_path)
        if not os.path.exists(storage_path):
            os.makedirs(storage_path)
        settings_path = os.path.join(storage_path, "settings.json")
        if not os.path.exists(settings_path):
            init_settings = {}
            json_object = json.dumps(init_settings, indent=4)
            with open(settings_path, "w") as outfile:
                outfile.write(json_object)
        else:
            with open(settings_path) as infile:
                settings_data = json.load(infile)
                if settings_data.get("game_folder"):
                    self.game_folder_line.setText(settings_data["game_folder"])
                if settings_data.get("config_folder"):
                    self.config_folder_line.setText(settings_data["config_folder"])
                if settings_data.get("workshop_folder"):
                    self.workshop_folder_line.setText(settings_data["workshop_folder"])
                if settings_data.get("local_folder"):
                    self.local_folder_line.setText(settings_data["local_folder"])

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
            show_warning(f"The path '{path}' does not exist.\nPlease reset the path.")

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

    def set_game_exe_folder(self) -> None:
        """
        Open a file dialog to allow the user to select the game executable.
        """
        start_dir = ""
        if self.game_folder_line.text():
            possible_dir = self.game_folder_line.text()
            if os.path.exists(possible_dir):
                start_dir = possible_dir
        game_exe_folder_path = str(
            QFileDialog.getExistingDirectory(
                caption="Select Game Folder", dir=start_dir
            )
        )
        self.game_folder_line.setText(game_exe_folder_path)
        self.update_persistent_storage("game_folder", game_exe_folder_path)
        # TODO
        # If Local Mods folder is not already set, automatically discern this information here

    def set_config_folder(self) -> None:
        """
        Open a file dialog to allow the user to select the ModsConfig.xml directory.
        """
        start_dir = ""
        if self.config_folder_line.text():
            possible_dir = self.config_folder_line.text()
            if os.path.exists(possible_dir):
                start_dir = possible_dir
        config_folder_path = str(
            QFileDialog.getExistingDirectory(
                caption="Select Mods Config Folder", dir=start_dir
            )
        )
        self.config_folder_line.setText(config_folder_path)
        self.update_persistent_storage("config_folder", config_folder_path)
        # TODO refresh mods

    def set_workshop_folder(self) -> None:
        """
        Open a file dialog to allow the user to select a directory
        to set as the workshop folder.
        """
        start_dir = ""
        if self.workshop_folder_line.text():
            possible_dir = self.workshop_folder_line.text()
            if os.path.exists(possible_dir):
                start_dir = possible_dir
        workshop_path = str(
            QFileDialog.getExistingDirectory(
                caption="Select Workshop Folder", dir=start_dir
            )
        )
        self.workshop_folder_line.setText(workshop_path)
        self.update_persistent_storage("workshop_folder", workshop_path)
        # TODO refresh mods

    def set_local_folder(self) -> None:
        """
        Open a file dialog to allow the user to select a directory
        to set as the local mods folder.
        """
        start_dir = ""
        if self.local_folder_line.text():
            possible_dir = self.local_folder_line.text()
            if os.path.exists(possible_dir):
                start_dir = possible_dir
        local_path = str(
            QFileDialog.getExistingDirectory(
                caption="Select Local Mods Folder", dir=start_dir
            )
        )
        self.local_folder_line.setText(local_path)
        self.update_persistent_storage("local_folder", local_path)
        # TODO refresh mods

    def update_persistent_storage(self, key: str, value: str) -> None:
        """
        Given a key and value, write this key and value to the
        persistent settings.json.

        :param key: key to use
        :param value: value to replace
        """
        storage_path = QStandardPaths.writableLocation(
            QStandardPaths.AppLocalDataLocation
        )
        settings_path = os.path.join(storage_path, "settings.json")
        with open(settings_path) as infile:
            settings_data = json.load(infile)
            settings_data[key] = value
            json_object = json.dumps(settings_data, indent=4)
            with open(settings_path, "w") as outfile:
                outfile.write(json_object)

    def get_game_folder_path(self):
        return self.game_folder_line.text()

    def get_config_folder_path(self):
        return self.config_folder_line.text()

    def get_config_path(self):
        return os.path.join(self.get_config_folder_path(), "ModsConfig.xml")

    def get_workshop_folder_path(self):
        return self.workshop_folder_line.text()

    def get_local_folder_path(self):
        return self.local_folder_line.text()
