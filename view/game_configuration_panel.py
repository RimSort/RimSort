import getpass
import json
import os
from os.path import expanduser
import platform
import subprocess
import webbrowser
from functools import partial
from typing import Any

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from panel.settings_panel import SettingsPanel
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
        self.client_settings_row = QHBoxLayout()
        self.client_settings_row.setContentsMargins(0, 0, 0, 2)
        self.client_settings_row.setSpacing(0)
        self.game_folder_row = QHBoxLayout()
        self.game_folder_row.setContentsMargins(0, 0, 0, 2)
        self.game_folder_row.setSpacing(0)
        self.config_folder_row = QHBoxLayout()
        self.config_folder_row.setContentsMargins(0, 0, 0, 2)
        self.config_folder_row.setSpacing(0)
        self.workshop_folder_row = QHBoxLayout()
        self.workshop_folder_row.setContentsMargins(0, 0, 0, 2)
        self.workshop_folder_row.setSpacing(0)
        self.local_folder_row = QHBoxLayout()
        self.local_folder_row.setContentsMargins(0, 0, 0, 0)
        self.local_folder_row.setSpacing(0)

        # INSTANTIATE WIDGETS
        self.client_settings_button = QPushButton("Settings")
        self.client_settings_button.clicked.connect(self.open_settings_panel)
        self.client_settings_button.setObjectName("LeftButton")
        self.auto_detect_paths_button = QPushButton("Autodetect Paths")
        self.auto_detect_paths_button.clicked.connect(self.do_autodetect)
        self.auto_detect_paths_button.setObjectName("LeftButton")
        self.game_version_label = QLabel("Game Version:")
        self.game_version_label.setObjectName("gameVersion")
        self.game_version_line = QLineEdit()
        self.game_version_line.setDisabled(True)
        self.game_version_line.setPlaceholderText("Unknown")
        self.wiki_button = QPushButton("Wiki")
        self.wiki_button.clicked.connect(self.open_wiki_webbrowser)
        self.wiki_button.setObjectName("RightButton")
        self.github_button = QPushButton("GitHub")
        self.github_button.clicked.connect(self.open_github_webbrowser)
        self.github_button.setObjectName("RightButton")

        self.game_folder_open_button = QPushButton("Game Folder")
        self.game_folder_open_button.clicked.connect(
            partial(self.open_directory, self.get_game_folder_path)
        )
        self.game_folder_open_button.setObjectName("LeftButton")
        self.game_folder_open_button.setToolTip("Open the game installation directory")
        self.game_folder_line = QLineEdit()
        self.game_folder_line.setDisabled(True)
        self.game_folder_line.setPlaceholderText("Unknown")
        self.game_folder_line.setToolTip(
            "The game installation directory contains the game executable.\n"
            "Set the game installation directory with the button on the right."
        )
        self.game_folder_select_button = QPushButton("...")
        self.game_folder_select_button.clicked.connect(self.set_game_exe_folder)
        self.game_folder_select_button.setObjectName("RightButton")
        self.game_folder_select_button.setToolTip("Set the game installation directory")

        self.config_folder_open_button = QPushButton("Config File")
        self.config_folder_open_button.clicked.connect(
            partial(self.open_directory, self.get_config_folder_path)
        )
        self.config_folder_open_button.setObjectName("LeftButton")
        self.config_folder_open_button.setToolTip("Open the ModsConfig.xml directory")
        self.config_folder_line = QLineEdit()
        self.config_folder_line.setDisabled(True)
        self.config_folder_line.setPlaceholderText("Unknown")
        self.config_folder_line.setToolTip(
            "The this directory contains the ModsConfig.xml file, which\n"
            "shows your active mods and their load order."
            "Set the ModsConfig.xml directory with the button on the right."
        )
        self.config_folder_select_button = QPushButton("...")
        self.config_folder_select_button.clicked.connect(self.set_config_folder)
        self.config_folder_select_button.setObjectName("RightButton")
        self.config_folder_select_button.setToolTip("Set the ModsConfig.xml directory")

        self.workshop_folder_open_button = QPushButton("Steam Mods")
        self.workshop_folder_open_button.clicked.connect(
            partial(self.open_directory, self.get_workshop_folder_path)
        )
        self.workshop_folder_open_button.setObjectName("LeftButton")
        self.workshop_folder_open_button.setToolTip(
            "Open the Steam Workshop Mods directory"
        )
        self.workshop_folder_line = QLineEdit()
        self.workshop_folder_line.setDisabled(True)
        self.workshop_folder_line.setPlaceholderText("Unknown")
        self.workshop_folder_line.setToolTip(
            "The Steam Workshop Mods directory contains mods downloaded from Steam.\n"
            "Set the Steam Workshop Mods directory with the button on the right."
        )
        self.workshop_folder_select_button = QPushButton("...")
        self.workshop_folder_select_button.clicked.connect(self.set_workshop_folder)
        self.workshop_folder_select_button.setObjectName("RightButton")
        self.workshop_folder_select_button.setToolTip(
            "Set the Steam Workshop Mods directory"
        )

        self.local_folder_open_button = QPushButton("Local Mods")
        self.local_folder_open_button.clicked.connect(
            partial(self.open_directory, self.get_local_folder_path)
        )
        self.local_folder_open_button.setObjectName("LeftButton")
        self.local_folder_open_button.setToolTip("Open the Local Mods directory")
        self.local_folder_line = QLineEdit()
        self.local_folder_line.setDisabled(True)
        self.local_folder_line.setPlaceholderText("Unknown")
        self.local_folder_line.setToolTip(
            "The Local Mods directory contains downloaded mod folders.\n"
            "By default, this folder is located in the game install directory.\n"
            "Set the Local Mods directory with the button on the right."
        )
        self.local_folder_select_button = QPushButton("...")
        self.local_folder_select_button.clicked.connect(self.set_local_folder)
        self.local_folder_select_button.setObjectName("RightButton")
        self.local_folder_select_button.setToolTip(
            "Set the Local Mods directory.\n"
            "On Mac, set this to the game install directory to use the\n"
            "default game install directory's Mods folder."
        )

        # WIDGETS INTO CONTAINER LAYOUTS
        self.client_settings_row.addWidget(self.client_settings_button)
        self.client_settings_row.addWidget(self.auto_detect_paths_button)
        self.client_settings_row.addWidget(self.game_version_label)
        self.client_settings_row.addWidget(self.game_version_line)
        self.client_settings_row.addWidget(self.wiki_button)
        self.client_settings_row.addWidget(self.github_button)

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
        self.client_settings_frame = QFrame()
        self.client_settings_frame.setObjectName("configLine")
        self.client_settings_frame.setLayout(self.client_settings_row)
        self.game_folder_frame = QFrame()
        self.game_folder_frame.setObjectName("configLine")
        self.game_folder_frame.setLayout(self.game_folder_row)
        self.config_folder_frame = QFrame()
        self.config_folder_frame.setObjectName("configLine")
        self.config_folder_frame.setLayout(self.config_folder_row)
        self.workshop_folder_frame = QFrame()
        self.workshop_folder_frame.setObjectName("configLine")
        self.workshop_folder_frame.setLayout(self.workshop_folder_row)
        self.local_folder_frame = QFrame()
        self.local_folder_frame.setObjectName("configLine")
        self.local_folder_frame.setLayout(self.local_folder_row)

        self._panel.addWidget(self.client_settings_frame)
        self._panel.addWidget(self.game_folder_frame)
        self._panel.addWidget(self.config_folder_frame)
        self._panel.addWidget(self.workshop_folder_frame)
        self._panel.addWidget(self.local_folder_frame)

        # INITIALIZE WIDGETS / FEATURES
        self.initialize_settings_panel()
        self.initialize_storage()

        # SIGNALS AND SLOTS
        self.settings_panel.settings_signal.connect(self.delete_all_paths_data)  # Actionsdelete_all_paths_data

    @property
    def panel(self):
        return self._panel

    def check_if_essential_paths_are_set(self) -> None:
        """
        When the user starts the app for the first time, none
        of the paths will be set. We should check for this and
        not throw a fatal error trying to load mods until the
        user has had a chance to set paths.
        """
        if (
            not self.game_folder_line.text()
            or not self.config_folder_line.text()
            or not self.workshop_folder_line.text()
        ):
            return False
        return True

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
                if settings_data.get("sorting_algorithm"):
                    self.settings_panel.sorting_algorithm_cb.setCurrentText(
                        settings_data["sorting_algorithm"]
                    )

    def initialize_settings_panel(self) -> None:
        """
        Initializes the app's settings popup dialog, but does
        not show it. The settings panel allows the user to
        tweak certain settings of RimSort, like which sorting
        algorithm to use, or what theme to use.
        Widndow modality is set so the user cannot interact with
        the rest of the application while the settings panel is open.
        """
        self.settings_panel = SettingsPanel()
        self.settings_panel.setWindowModality(Qt.ApplicationModal)
        self.settings_panel.finished.connect(self.on_settings_close)

    def on_settings_close(self) -> None:
        self.settings_panel.close()
        self.update_persistent_storage(
            "sorting_algorithm", self.settings_panel.sorting_algorithm_cb.currentText()
        )

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
    
    def delete_all_paths_data(self) -> None:
        folders = [
            "workshop_folder",
            "game_folder",
            "config_folder",
            "local_folder"
        ]
        for folder in folders:
            self.update_persistent_storage(folder, "")
        self.game_folder_line.setText("")
        self.config_folder_line.setText("")
        self.workshop_folder_line.setText("")
        self.local_folder_line.setText("")
        self.game_version_line.setText("")

    def autodetect_paths_by_platform(self) -> None:
        """
        This function tries to autodetect Rimworld paths based on the
        defaults typically found per-platform, and set them in the client.
        """
        os_paths = []
        darwin_paths = [
            f"/Users/{getpass.getuser()}/Library/Application Support/Steam/steamapps/common/Rimworld/RimWorldMac.app",
            f"/Users/{getpass.getuser()}/Library/Application Support/Rimworld/Config",
            f"/Users/{getpass.getuser()}/Library/Application Support/Steam/steamapps/workshop/content/294100/"
            ]
        linux_paths = [
            f"{expanduser('~')}/.steam/debian-installation/steamapps/common/RimWorld",
            f"{expanduser('~')}/.config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/Config",
            f"{expanduser('~')}/.steam/debian-installation/steamapps/workshop/content/294100"
        ]
        windows_paths = [
            os.path.join("C:" + os.sep, "Program Files (x86)", "Steam", "steamapps", "common", "Rimworld"),
            os.path.join("C:" + os.sep, "Users", getpass.getuser(), "AppData", "LocalLow", "Ludeon Studios", "RimWorld by Ludeon Studios", "Config"),
            os.path.join("C:" + os.sep, "Program Files (x86)", "Steam", "steamapps", "workshop", "content", "294100")
        ]
        system_name = platform.system()

        if system_name == "Darwin":
            os_paths = darwin_paths
        elif system_name == "Linux":
            os_paths = linux_paths
        elif system_name == "Windows":
            os_paths = windows_paths
        else:
            print("Unknown System")  # TODO
        if os.path.exists(os_paths[0]):
            self.game_folder_line.setText(os_paths[0])
            self.update_persistent_storage("game_folder", os_paths[0])
        if os.path.exists(os_paths[1]):
            self.config_folder_line.setText(os_paths[1])
            self.update_persistent_storage("config_folder", os_paths[1])
        if os.path.exists(os_paths[2]):
            self.workshop_folder_line.setText(os_paths[2])
            self.update_persistent_storage("workshop_folder", os_paths[2])
        if os.path.exists(os.path.join(os_paths[0], "Mods")):
            self.local_folder_line.setText(os.path.join(os_paths[0], "Mods"))
            self.update_persistent_storage("local_folder", os.path.join(os_paths[0], "Mods"))


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

    def open_settings_panel(self):
        """
        Opens the settings panel (as a modal window), blocking
        access to the rest of the application until it is closed.
        Do NOT use exec here: https://doc.qt.io/qt-6/qdialog.html#exec
        For some reason, open() does not work for making this a modal
        window.
        """
        self.settings_panel.show()

    def do_autodetect(self):
        self.autodetect_paths_by_platform()

    def open_wiki_webbrowser(self):
        webbrowser.open("https://github.com/oceancabbage/RimSort/wiki")

    def open_github_webbrowser(self):
        webbrowser.open("https://github.com/oceancabbage/RimSort")
