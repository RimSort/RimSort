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

    def __init__(self) -> None:
        """
        Initialize the class.
        Create a ListWidget using the dict of mods. This will
        create a row for every key-value pair in the dict.
        """

        # Base layout type
        self.panel = QVBoxLayout()

        # Instantiate widgets
        self.num_mods = QLabel("Inactive [0]")
        self.num_mods.setAlignment(Qt.AlignCenter)
        self.num_mods.setObjectName("summaryValue")
        self.inactive_mods_list = ModListWidget()

        # Add widgets to base layout
        self.panel.addWidget(self.num_mods)
        self.panel.addWidget(self.inactive_mods_list)

        # Connect signals and slots
        self.inactive_mods_list.list_change_signal.connect(self.change_mod_num_display)

    def change_mod_num_display(self, count: str) -> None:
        self.num_mods.setText(f"Inactive [{count}]")
