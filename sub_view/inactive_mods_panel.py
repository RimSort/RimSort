import logging
from typing import Any, Dict, List

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from model.mod_list import ModListWidget

logger = logging.getLogger(__name__)


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
        logger.info("Starting InactiveModList initialization")

        # Base layout type
        self.panel = QVBoxLayout()

        # Instantiate widgets
        self.num_mods = QLabel("Inactive [0]")
        self.num_mods.setAlignment(Qt.AlignCenter)
        self.num_mods.setObjectName("summaryValue")

        self.inactive_mods_list = ModListWidget()

        self.inactive_mods_search = QLineEdit()
        self.inactive_mods_search.setClearButtonEnabled(True)
        self.inactive_mods_search.textChanged.connect(self.signal_inactive_mods_search(self.inactive_mods_search.text()))
        self.inactive_mods_search_clear_button = self.inactive_mods_search.findChild(
            QToolButton
        )
        self.inactive_mods_search_clear_button.setEnabled(True)
        self.inactive_mods_search_clear_button.clicked.connect(
            self.clear_inactive_mods_search
        )
        self.inactive_mods_search.setPlaceholderText("Search inactive mods...")

        # Add widgets to base layout
        self.panel.addWidget(self.num_mods)
        self.panel.addWidget(self.inactive_mods_search)
        self.panel.addWidget(self.inactive_mods_list)

        # Connect signals and slots
        self.inactive_mods_list.list_change_signal.connect(self.change_mod_num_display)

        logger.info("Finished InactiveModList initialization")

    def change_mod_num_display(self, count: str) -> None:
        logger.info(f"Inactive mod count changed to: {count}")
        self.num_mods.setText(f"Inactive [{count}]")

    def clear_inactive_mods_search(self):
        self.inactive_mods_search.setText("")
        for mod_item in self.inactive_mods_list.get_list_items():
            mod_item.show()

    def signal_inactive_mods_search(self, pattern: str) -> None:
        print("Signal inactive mods:")
        print(pattern)
        if pattern != "":
            for mod_item in self.inactive_mods_list.get_list_items():
                if not mod_item["name"].lower().contains(pattern.lower()):
                    mod_item.hide()