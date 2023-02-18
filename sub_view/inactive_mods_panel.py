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
        self.inactive_mods_search.textChanged.connect(self.signal_inactive_mods_search)
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

        # Tracking mod list
        self.tracking_active_mods = {}

        # Adding Completer.
        # self.completer = QCompleter(self.inactive_mods_list.get_list_items())
        # self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        # self.inactive_mods_search.setCompleter(self.completer)

        # Connect signals and slots
        self.inactive_mods_list.list_update_signal.connect(self.change_mod_num_display)

        logger.info("Finished InactiveModList initialization")
    
    def recreate_mod_list(self, mods: Dict[str, Any]) -> None:
        """
        Indicates that a new tracking mod list dist should
        be created and attached to this class. This tracking dict
        should keep track of: the mods that are included in the
        actual child mod list, in ORDER. Directly supports the search
        function as a fall-back 'full' mod list.
        
        However, note that the inactive mod list doesn't really need
        to use order for anything since dependencies/incompatibilities etc
        aren't shown for the inactive mods panel.

        Then, calls function on child mod list to actually clear mods
        and add new ones from the dict.

        :param mods: dict of mod data
        """
        logger.info("Externally re-creating inactive tracking mod list")
        self.tracking_active_mods = mods
        self.inactive_mods_list.recreate_mod_list(mods)

    def change_mod_num_display(self, count: str) -> None:
        if count != "drop":
            logger.info(f"Inactive mod count changed to: {count}")
            self.num_mods.setText(f"Inactive [{count}]")

    def clear_inactive_mods_search(self):
         print("cleared")
        # self.inactive_mods_search.setText("")
        # for mod_item in self.inactive_mods_list.get_list_items():
        #     mod_item.show()

    def signal_inactive_mods_search(self, pattern: str) -> None:
        print(pattern)
        # if pattern == "":
        #     self.clear_inactive_mods_search()
        # else:
        #     for mod_item in self.inactive_mods_list.get_list_items():
        #         if not pattern.lower() in mod_item.name.lower():
        #             mod_item.hide()
