from logger_tt import logger
import os
from pathlib import Path
from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from model.image_label import ImageLabel
from model.scroll_label import ScrollLabel


class ModInfo:
    """
    This class controls the layout and functionality for the
    mod information panel on the GUI.
    """

    def __init__(self) -> None:
        """
        Initialize the class.
        """
        logger.debug("Initializing ModInfo")

        # Base layout type
        self.panel = QVBoxLayout()

        # Child layouts
        self.image_layout = QHBoxLayout()
        self.image_layout.setAlignment(Qt.AlignCenter)
        self.mod_info_layout = QVBoxLayout()
        self.mod_info_name = QHBoxLayout()
        self.mod_info_package_id = QHBoxLayout()
        self.mod_info_authors = QHBoxLayout()
        self.mod_info_mod_version = QHBoxLayout()
        self.mod_info_path = QHBoxLayout()
        self.description_layout = QHBoxLayout()

        # Add child layouts to base
        self.panel.addLayout(self.image_layout, 50)
        self.panel.addLayout(self.mod_info_layout, 20)
        self.panel.addLayout(self.description_layout, 30)

        # Create widgets
        self.missing_image_path = str(
            Path(os.path.join(os.getcwd(), "data", "missing.png")).resolve()
        )
        self.preview_picture = ImageLabel()
        self.preview_picture.setAlignment(Qt.AlignCenter)
        self.preview_picture.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_picture.setMinimumSize(1, 1)
        self.preview_picture.setPixmap(
            QPixmap(self.missing_image_path).scaled(
                self.preview_picture.size(), Qt.KeepAspectRatio
            )
        )
        self.mod_info_name_label = QLabel("Name:")
        self.mod_info_name_label.setObjectName("summaryLabel")
        self.mod_info_name_value = QLabel()
        self.mod_info_name_value.setObjectName("summaryValue")
        self.mod_info_name_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.mod_info_name_value.setWordWrap(True)
        self.mod_info_package_id_label = QLabel("PackageID:")
        self.mod_info_package_id_label.setObjectName("summaryLabel")
        self.mod_info_package_id_value = QLabel()
        self.mod_info_package_id_value.setObjectName("summaryValue")
        self.mod_info_package_id_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.mod_info_package_id_value.setWordWrap(True)
        self.mod_info_author_label = QLabel("Authors:")
        self.mod_info_author_label.setObjectName("summaryLabel")
        self.mod_info_author_value = QLabel()
        self.mod_info_author_value.setObjectName("summaryValue")
        self.mod_info_author_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.mod_info_author_value.setWordWrap(True)
        self.mod_info_mod_version_label = QLabel("Mod version:")
        self.mod_info_mod_version_label.setObjectName("summaryLabel")
        self.mod_info_mod_version_value = QLabel()
        self.mod_info_mod_version_value.setObjectName("summaryValue")
        self.mod_info_mod_version_value.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self.mod_info_mod_version_value.setWordWrap(True)
        self.mod_info_path_label = QLabel("Path:")
        self.mod_info_path_label.setObjectName("summaryLabel")
        self.mod_info_path_value = QLabel()
        self.mod_info_path_value.setObjectName("summaryValue")
        self.mod_info_path_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
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
        self.mod_info_mod_version.addWidget(self.mod_info_mod_version_label, 20)
        self.mod_info_mod_version.addWidget(self.mod_info_mod_version_value, 80)
        self.mod_info_layout.addLayout(self.mod_info_name)
        self.mod_info_layout.addLayout(self.mod_info_package_id)
        self.mod_info_layout.addLayout(self.mod_info_authors)
        self.mod_info_layout.addLayout(self.mod_info_mod_version)
        self.mod_info_layout.addLayout(self.mod_info_path)
        self.description_layout.addWidget(self.description)

        logger.debug("Finished ModInfo initialization")

    def display_mod_info(self, mod_info: Dict[str, Any]) -> None:
        """
        This slot receives a the complete mod data json for
        the mod that was just clicked on. It will set the relevant
        information on the info panel.

        :param mod_info: complete json info for the mod
        """
        logger.debug(f"Starting display of mod info: {mod_info}")
        self.mod_info_name_value.setText(mod_info.get("name"))
        self.mod_info_package_id_value.setText(mod_info.get("packageId"))

        authors_tag = mod_info.get("author", mod_info.get("authors"))
        if authors_tag and isinstance(authors_tag, dict) and authors_tag.get("li"):
            list_of_authors = authors_tag["li"]
            authors_text = ", ".join(list_of_authors)
            self.mod_info_author_value.setText(authors_text)
        else:
            self.mod_info_author_value.setText(
                f"{authors_tag if authors_tag else 'UNKNOWN'}"
            )

        if mod_info.get("modVersion"):
            if isinstance(mod_info.get("modVersion"), str):
                self.mod_info_mod_version_value.setText(mod_info.get("modVersion"))
            elif isinstance(mod_info.get("modVersion"), dict):
                self.mod_info_mod_version_value.setText(mod_info["modVersion"]["#text"])
        else:
            self.mod_info_mod_version_value.setText("Not specified")
        self.mod_info_path_value.setText(mod_info.get("path"))

        # Set the scrolling description for the Mod Info Panel
        self.description.setText("")
        if "description" in mod_info:
            if mod_info["description"] is not None:
                if isinstance(mod_info["description"], str):
                    self.description.setText(mod_info["description"])
                else:
                    logger.error(
                        f"[description] tag is not a string: {mod_info['description']}"
                    )
        # It is OK for the description value to be None (was not provided)
        # It is OK for the description key to not be in mod_info

        # Get Preview.png
        if mod_info.get("path") and isinstance(mod_info["path"], str):
            workshop_folder_path = mod_info["path"]
            logger.info(f"Got mod path for preview image: {workshop_folder_path}")
            if os.path.exists(workshop_folder_path):
                about_folder_name = "About"
                about_folder_target_path = str(
                    Path(
                        os.path.join(workshop_folder_path, about_folder_name)
                    ).resolve()
                )
                if os.path.exists(about_folder_target_path):
                    # Look for a case-insensitive About folder
                    invalid_folder_path_found = True
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
                        str(
                            Path(
                                os.path.join(workshop_folder_path, about_folder_name)
                            ).resolve()
                        )
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
                        logger.info("No preview image found for the mod")
                        pixmap = QPixmap(self.missing_image_path)
                        self.preview_picture.setPixmap(
                            pixmap.scaled(
                                self.preview_picture.size(), Qt.KeepAspectRatio
                            )
                        )
                    else:
                        logger.info("Preview image found")
                        image_path = str(
                            Path(
                                os.path.join(
                                    workshop_folder_path,
                                    about_folder_name,
                                    preview_file_name,
                                )
                            ).resolve()
                        )
                        pixmap = QPixmap(image_path)
                        self.preview_picture.setPixmap(
                            pixmap.scaled(
                                self.preview_picture.size(), Qt.KeepAspectRatio
                            )
                        )
                else:
                    logger.error(
                        f"The local data for the mod {self.mod_info_package_id_value} was not found. Using cached metadata with missing Preview image."
                    )
                    pixmap = QPixmap(self.missing_image_path)
                    self.preview_picture.setPixmap(
                        pixmap.scaled(self.preview_picture.size(), Qt.KeepAspectRatio)
                    )

        else:
            logger.error(
                f"[path] tag does not exist in mod_info, is empty, or is not string: {mod_info.get('path')}"
            )
            pixmap = QPixmap(self.missing_image_path)
            self.preview_picture.setPixmap(
                pixmap.scaled(self.preview_picture.size(), Qt.KeepAspectRatio)
            )
        logger.debug("Finished displaying mod info")
