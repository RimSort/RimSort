from typing import Any, Dict

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from model.mod_list import ModListWidget



class ActiveModList:
    """
    This class controls the layout and functionality for the
    active mods list panel on the GUI.
    """

    def __init__(self, mods: Dict[str, Any], mods_config_path: str) -> None:
        """
        Initialize the class.
        Create a ListWidget using the dict of mods. This will
        create a row for every key-value pair in the dict.

        :param mods: a dict of mod data
        :param mods_config_path: path to the ModsConfig.xml
        """

        self.mods_config_path = mods_config_path

        # Base layout type
        self.panel = QVBoxLayout()

        # Instantiate widgets
        self.active_mods_list = ModListWidget(mods)

        # Add widgets to base layout
        self.panel.addWidget(self.active_mods_list)

    def actions_slot(self, action: str) -> None:
        """
        Slot connecting to the action panel's `actions_signal`.
        Responsible for controlling save and export functionality.

        :param action: the specific action being triggered
        """
        
