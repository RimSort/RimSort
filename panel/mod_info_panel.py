from typing import Any, Dict, List

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


class ModInfo:
    """
    This class controls the layout and functionality for the
    mod information panel on the GUI.
    """

    def __init__(self) -> None:
        """
        Initialize the class.
        """

        # Base layout type
        self.panel = QVBoxLayout()

        # Child layouts
        self.image_layout = QHBoxLayout()
        self.image_layout.setAlignment(Qt.AlignCenter)
        self.mod_info_layout = QHBoxLayout()
        self.description_layout = QHBoxLayout()

        # Add child layouts to base
        self.panel.addLayout(self.image_layout, 55)
        self.panel.addLayout(self.mod_info_layout, 15)
        self.panel.addLayout(self.description_layout, 30)

        # Create widgets
        self.preview_picture = QLabel()
        self.mod_info = QFrame()
        self.description = QLabel()

        # Add widgets to child layouts
        self.image_layout.addWidget(self.preview_picture)
        self.mod_info_layout.addWidget(self.mod_info)
        self.description_layout.addWidget(self.description)
    
    def mod_list_slot(self, package_id: str) -> None:
        """
        This slot receives a mod `package_id` whenever a mod list item
        is clicked on either the active or inactive mod lists. It
        fetches information from the workshop folder based on this
        `package_id` and displays the information on the mod info panel.

        :param package_id: package_id of the mod that was clicked on
        """
        print(f"A mod was just clicked on: {package_id}")
        self.preview_picture.setText(package_id)
        
