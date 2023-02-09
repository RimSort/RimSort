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

    def __init__(self) -> None:
        """
        Initialize the class.
        Create a ListWidget using the dict of mods. This will
        create a row for every key-value pair in the dict.
        """

        # Base layout type
        self.panel = QVBoxLayout()

        # Instantiate widgets
        self.active_mods_list = ModListWidget()

        # Add widgets to base layout
        self.panel.addWidget(self.active_mods_list)
        