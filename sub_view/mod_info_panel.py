import logging
import os
from typing import Any, Dict

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from model.scroll_label import ScrollLabel

logger = logging.getLogger(__name__)


class ModInfo:
    """
    This class controls the layout and functionality for the
    mod information panel on the GUI.
    """

    def __init__(self) -> None:
        """
        Initialize the class.
        """
        logger.info("Starting ModInfo initialization")

        # Base layout type
        self.panel = QVBoxLayout()

        # Child layouts
        self.image_layout = QHBoxLayout()
        self.image_layout.setAlignment(Qt.AlignCenter)
        self.mod_info_layout = QVBoxLayout()
        self.mod_info_name = QHBoxLayout()
        self.mod_info_package_id = QHBoxLayout()
        self.mod_info_authors = QHBoxLayout()
        self.mod_info_path = QHBoxLayout()
        self.description_layout = QHBoxLayout()

        # Add child layouts to base
        self.panel.addLayout(self.image_layout, 50)
        self.panel.addLayout(self.mod_info_layout, 20)
        self.panel.addLayout(self.description_layout, 30)

        # Create widgets
        self.preview_picture = QLabel()
        self.preview_picture.setAlignment(Qt.AlignCenter)
        self.preview_picture.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.mod_info_name_label = QLabel("Name:")
        self.mod_info_name_label.setObjectName("summaryLabel")
        self.mod_info_name_value = QLabel()
        self.mod_info_name_value.setObjectName("summaryValue")
        self.mod_info_package_id_label = QLabel("PackageID:")
        self.mod_info_package_id_label.setObjectName("summaryLabel")
        self.mod_info_package_id_value = QLabel()
        self.mod_info_package_id_value.setObjectName("summaryValue")
        self.mod_info_author_label = QLabel("Authors:")
        self.mod_info_author_label.setObjectName("summaryLabel")
        self.mod_info_author_value = QLabel()
        self.mod_info_author_value.setObjectName("summaryValue")
        self.mod_info_path_label = QLabel("Path:")
        self.mod_info_path_label.setObjectName("summaryLabel")
        self.mod_info_path_value = QLabel()
        self.mod_info_path_value.setObjectName("summaryValue")
        self.mod_info_path_value.setWordWrap(True)
        self.description = ScrollLabel()

        # Add widgets to child layouts
        self.image_layout.addWidget(self.preview_picture)
        self.mod_info_name.addWidget(self.mod_info_name_label, 20)
        self.mod_info_name.addWidget(self.mod_info_name_value, 80)
        self.mod_info_path.addWidget(self.mod_info_path_label, 20)
        self.mod_info_path.addWidget(self.mod_info_path_value, 80)
        self.mod_info_package_id.addWidget(self.mod_info_package_id_label, 20)
        self.mod_info_package_id.addWidget(self.mod_info_package_id_value, 80)
        self.mod_info_authors.addWidget(self.mod_info_author_label, 20)
        self.mod_info_authors.addWidget(self.mod_info_author_value, 80)
        self.mod_info_layout.addLayout(self.mod_info_name)
        self.mod_info_layout.addLayout(self.mod_info_package_id)
        self.mod_info_layout.addLayout(self.mod_info_authors)
        self.mod_info_layout.addLayout(self.mod_info_path)
        self.description_layout.addWidget(self.description)

        logger.info("Finished ModInfo initialization")

    def display_mod_info(self, mod_info: Dict[str, Any]) -> None:
        """
        This slot receives a the complete mod data json for
        the mod that was just clicked on. It will set the relevant
        information on the info panel.

        :param mod_info: complete json info for the mod
        """
        self.mod_info_name_value.setText(mod_info.get("name"))
        self.mod_info_package_id_value.setText(mod_info.get("packageId"))
        if mod_info.get("authors"):
            list_of_authors = mod_info.get("authors")["li"]
            authors_text = ", ".join(list_of_authors)
            self.mod_info_author_value.setText(authors_text)
        else:
            self.mod_info_author_value.setText(mod_info.get("author"))
        self.mod_info_path_value.setText(mod_info.get("path"))
        self.description.setText(mod_info.get("description"))
        # Get Preview.png
        if mod_info.get("path"):
            workshop_folder_path = mod_info.get("path")
            # Look for a case-insensitive About folder
            invalid_folder_path_found = True
            about_folder_name = "About"
            for temp_file in os.scandir(workshop_folder_path):
                if (
                    temp_file.name.lower() == about_folder_name.lower()
                    and temp_file.is_dir()
                ):
                    about_folder_name = temp_file.name
                    invalid_folder_path_found = False
                    break
            # Look for a case-insensitive "Preview.png" file
            invalid_file_path_found = True
            preview_file_name = "Preview.png"
            for temp_file in os.scandir(
                os.path.join(workshop_folder_path, about_folder_name)
            ):
                if (
                    temp_file.name.lower() == preview_file_name.lower()
                    and temp_file.is_file()
                ):
                    preview_file_name = temp_file.name
                    invalid_file_path_found = False
                    break
            # If there was an issue getting the expected path, track and exit
            if invalid_folder_path_found or invalid_file_path_found:
                self.preview_picture.setPixmap(None)
            else:
                image_path = os.path.join(
                    workshop_folder_path, about_folder_name, preview_file_name
                )
                pixmap = QPixmap(image_path)
                self.preview_picture.setPixmap(
                    pixmap.scaled(self.preview_picture.size(), Qt.KeepAspectRatio)
                )
        else:
            self.preview_picture.setPixmap(None)
