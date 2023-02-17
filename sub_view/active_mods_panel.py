import logging

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from model.mod_list import ModListWidget

logger = logging.getLogger(__name__)


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
        logger.info("Starting ActiveModList initialization")

        # Base layout type
        self.panel = QVBoxLayout()

        # Instantiate widgets
        self.num_mods = QLabel("Active [0]")
        self.num_mods.setAlignment(Qt.AlignCenter)
        self.num_mods.setObjectName("summaryValue")

        self.active_mods_list = ModListWidget()

        self.active_mods_search = QLineEdit()
        self.active_mods_search.setClearButtonEnabled(True)
        self.active_mods_search.textChanged.connect(self.signal_active_mods_search(self.active_mods_search.text()))
        self.active_mods_search_clear_button = self.active_mods_search.findChild(
            QToolButton
        )
        self.active_mods_search_clear_button.setEnabled(True)
        self.active_mods_search_clear_button.clicked.connect(
            self.clear_active_mods_search
        )
        self.active_mods_search.setPlaceholderText("Search active mods...")

        # Add widgets to base layout
        self.panel.addWidget(self.num_mods)
        self.panel.addWidget(self.active_mods_search)
        self.panel.addWidget(self.active_mods_list)

        # Connect signals and slots
        self.active_mods_list.list_change_signal.connect(self.change_mod_num_display)

        logger.info("Finished ActiveModList initialization")

    def change_mod_num_display(self, count: str) -> None:
        logger.info(f"Active mod count changed to: {count}")
        self.num_mods.setText(f"Active [{count}]")

    def clear_active_mods_search(self):
        self.active_mods_search.setText("")

    def signal_active_mods_search(self, pattern: str) -> None:
        print("Signal active mods:")
        print(pattern)
        if pattern != "":
            for mod_item in self.inactive_mods_list.get_list_items():
                if not mod_item["name"].lower().contains(pattern.lower()):
                    mod_item.hide()
