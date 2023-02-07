from typing import Any, Dict, List

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from model.mod_list import ModListWidget


class InactiveModList:
    """
    This class controls the layout and functionality for the
    inactive mods list panel on the GUI.
    """

    def __init__(self, mods: Dict[str, Any]) -> None:
        """
        Initialize the class.
        Create a ListWidget using the dict of mods. This will
        create a row for every key-value pair in the dict.

        :param mods: a dict of mod data
        """

        # Base layout type
        self.panel = QVBoxLayout()

        # Instantiate widgets
        self.inactive_mods_list = ModListWidget(mods)

        # Add widgets to base layout
        self.panel.addWidget(self.inactive_mods_list)
