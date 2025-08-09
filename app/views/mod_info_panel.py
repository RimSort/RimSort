import os
from pathlib import Path
from re import match

from loguru import logger
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.models.image_label import ImageLabel
from app.utils.app_info import AppInfo
from app.utils.custom_list_widget_item import CustomListWidgetItem
from app.utils.generic import platform_specific_open
from app.utils.metadata import MetadataManager
from app.views.description_widget import DescriptionWidget


class ClickablePathLabel(QLabel):
    """
    A clickable QLabel that opens the folder in the file manager when clicked.
    Inherits text color from the application's theme system.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.clickable = True
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("text-decoration: underline;")
        self.path = ""

    def setPath(self, path: str | None) -> None:
        """Set the path and update the display text."""
        if path:
            self.path = path
            self.setText(path)
            self.setToolTip(f"Click to open folder: {path}")
        else:
            self.path = ""
            self.setText("")
            self.setToolTip("")

    def setClickable(self, clickable: bool) -> None:
        """Set whether the label is clickable, updating cursor accordingly."""
        self.clickable = clickable
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse click to open the folder if clickable."""
        if event.button() == Qt.MouseButton.LeftButton and self.path and self.clickable:
            try:
                path_obj = Path(self.path)
                if path_obj.exists():
                    if path_obj.is_dir():
                        platform_specific_open(self.path)
                        logger.info(f"Opening mod folder: {self.path}")
                    else:
                        logger.warning(f"Path is not a directory: {self.path}")
                else:
                    logger.warning(f"Mod folder does not exist: {self.path}")
            except Exception as e:
                logger.error(f"Failed to open mod folder {self.path}: {e}")
        super().mousePressEvent(event)


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

        # Cache MetadataManager instance
        self.metadata_manager = MetadataManager.instance()

        # Used to keep track of which mod items notes we are viewing/editing
        # This is set when a mod is clicked on
        self.current_mod_item: CustomListWidgetItem | None = None

        # Base layout type
        self.panel = QVBoxLayout()
        self.info_panel_frame = QFrame()

        # Child layouts
        self.info_layout = QVBoxLayout()
        self.image_layout = QHBoxLayout()
        self.image_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mod_info_layout = QVBoxLayout()
        self.mod_info_name = QHBoxLayout()
        self.scenario_info_summary = QHBoxLayout()
        self.mod_info_package_id = QHBoxLayout()
        self.mod_info_authors = QHBoxLayout()
        self.mod_info_mod_version = QHBoxLayout()
        self.mod_info_supported_versions = QHBoxLayout()
        self.mod_info_path = QHBoxLayout()
        self.description_layout = QHBoxLayout()
        self.notes_layout = QHBoxLayout()

        # Add child layouts to base
        self.info_layout.addLayout(self.image_layout, 35)
        self.info_layout.addLayout(self.mod_info_layout, 20)
        self.info_layout.addLayout(self.notes_layout, 15)
        self.info_layout.addLayout(self.description_layout, 30)
        self.info_panel_frame.setLayout(self.info_layout)
        self.panel.addWidget(self.info_panel_frame)

        # Create widgets
        self.missing_image_path = str(
            AppInfo().theme_data_folder / "default-icons" / "missing.png"
        )
        self.rimsort_image_a_path = str(
            AppInfo().theme_data_folder / "default-icons" / "AppIcon_a.png"
        )
        self.rimsort_image_b_path = str(
            AppInfo().theme_data_folder / "default-icons" / "AppIcon_b.png"
        )
        self.scenario_image_path = str(
            AppInfo().theme_data_folder / "default-icons" / "rimworld.png"
        )
        self.preview_picture = ImageLabel()
        self.preview_picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_picture.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.preview_picture.setMinimumSize(1, 1)
        self.preview_picture.setPixmap(
            QPixmap(self.rimsort_image_a_path).scaled(
                self.preview_picture.size(), Qt.AspectRatioMode.KeepAspectRatio
            )
        )
        self.mod_info_name_label = QLabel(self.tr("Name:"))
        self.mod_info_name_label.setObjectName("summaryLabel")
        self.mod_info_name_value = QLabel()
        self.mod_info_name_value.setObjectName("summaryValue")
        self.mod_info_name_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.mod_info_name_value.setWordWrap(True)
        self.scenario_info_summary_label = QLabel(self.tr("Summary:"))
        self.scenario_info_summary_label.setObjectName("summaryLabel")
        self.scenario_info_summary_value = QLabel()
        self.scenario_info_summary_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.scenario_info_summary_value.setWordWrap(True)
        self.mod_info_package_id_label = QLabel(self.tr("PackageID:"))
        self.mod_info_package_id_label.setObjectName("summaryLabel")
        self.mod_info_package_id_value = QLabel()
        self.mod_info_package_id_value.setObjectName("summaryValue")
        self.mod_info_package_id_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.mod_info_package_id_value.setWordWrap(True)
        self.mod_info_author_label = QLabel(self.tr("Authors:"))
        self.mod_info_author_label.setObjectName("summaryLabel")
        self.mod_info_author_value = QLabel()
        self.mod_info_author_value.setObjectName("summaryValue")
        self.mod_info_author_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.mod_info_author_value.setWordWrap(True)
        self.mod_info_mod_version_label = QLabel(self.tr("Mod Version:"))
        self.mod_info_mod_version_label.setObjectName("summaryLabel")
        self.mod_info_mod_version_value = QLabel()
        self.mod_info_mod_version_value.setObjectName("summaryValue")
        self.mod_info_mod_version_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.mod_info_mod_version_value.setWordWrap(True)
        self.mod_info_supported_versions_label = QLabel(self.tr("Supported Version:"))
        self.mod_info_supported_versions_label.setObjectName("summaryLabel")
        self.mod_info_supported_versions_value = QLabel()
        self.mod_info_supported_versions_value.setObjectName("summaryValue")
        self.mod_info_path_label = QLabel(self.tr("Path:"))
        self.mod_info_path_label.setObjectName("summaryLabel")
        self.mod_info_path_value = ClickablePathLabel()
        self.mod_info_path_value.setObjectName("summaryValue")
        self.mod_info_path_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.mod_info_path_value.setWordWrap(True)
        self.description = DescriptionWidget()
        self.description_text = self.tr("Welcome to RimSort!")
        self.description.setText(
            f"<br><br><br><center>{self.description_text}<h3></h3></center>",
            convert=False,
        )
        self.notes = QTextEdit()  # TODO: Custom QTextEdit to allow clickable hyperlinks?
        self.notes.setObjectName("userModNotes")
        self.notes.setPlaceholderText("Put your personal mod notes here!")
        self.notes.textChanged.connect(self.update_user_mod_notes)
        self.notes.setVisible(False)  # Only shows when a mod is selected
        # Add widgets to child layouts
        self.image_layout.addWidget(self.preview_picture)
        self.mod_info_name.addWidget(self.mod_info_name_label, 20)
        self.mod_info_name.addWidget(self.mod_info_name_value, 80)
        self.mod_info_path.addWidget(self.mod_info_path_label, 20)
        self.mod_info_path.addWidget(self.mod_info_path_value, 80)
        self.scenario_info_summary.addWidget(self.scenario_info_summary_label, 20)
        self.scenario_info_summary.addWidget(self.scenario_info_summary_value, 80)
        self.mod_info_package_id.addWidget(self.mod_info_package_id_label, 20)
        self.mod_info_package_id.addWidget(self.mod_info_package_id_value, 80)
        self.mod_info_authors.addWidget(self.mod_info_author_label, 20)
        self.mod_info_authors.addWidget(self.mod_info_author_value, 80)
        self.mod_info_mod_version.addWidget(self.mod_info_mod_version_label, 20)
        self.mod_info_mod_version.addWidget(self.mod_info_mod_version_value, 80)
        self.mod_info_supported_versions.addWidget(
            self.mod_info_supported_versions_label, 20
        )
        self.mod_info_supported_versions.addWidget(
            self.mod_info_supported_versions_value, 80
        )
        self.mod_info_layout.addLayout(self.mod_info_name)
        self.mod_info_layout.addLayout(self.scenario_info_summary)
        self.mod_info_layout.addLayout(self.mod_info_package_id)
        self.mod_info_layout.addLayout(self.mod_info_authors)
        self.mod_info_layout.addLayout(self.mod_info_mod_version)
        self.mod_info_layout.addLayout(self.mod_info_supported_versions)
        self.mod_info_layout.addLayout(self.mod_info_path)
        self.notes_layout.addWidget(self.notes)
        self.description_layout.addWidget(self.description)

        # Hide label/value by default
        self.essential_info_widgets = [
            self.mod_info_name_label,
            self.mod_info_name_value,
            self.mod_info_path_label,
            self.mod_info_path_value,
        ]

        self.base_mod_info_widgets = [
            self.mod_info_package_id_label,
            self.mod_info_package_id_value,
            self.mod_info_author_label,
            self.mod_info_author_value,
            self.mod_info_mod_version_label,
            self.mod_info_mod_version_value,
            self.mod_info_supported_versions_label,
            self.mod_info_supported_versions_value,
        ]

        self.scenario_info_widgets = [
            self.scenario_info_summary_label,
            self.scenario_info_summary_value,
        ]

        # Hide all widgets by default
        for widget in (
            self.essential_info_widgets
            + self.base_mod_info_widgets
            + self.scenario_info_widgets
        ):
            widget.hide()

        logger.debug("Finished ModInfo initialization")

    def update_user_mod_notes(self) -> None:
        if self.current_mod_item is None:
            return
        new_notes = self.notes.toPlainText()
        mod_data = self.current_mod_item.data(Qt.ItemDataRole.UserRole)
        mod_data["user_notes"] = new_notes
        logger.debug(f"Finished updating notes for UUID: {mod_data["uuid"]}")

    def show_user_mod_notes(self, item: CustomListWidgetItem) -> None:
        # Only show notes tab when a mod is selected
        self.notes.setVisible(True)
        self.current_mod_item = item
        mod_data = item.data(Qt.ItemDataRole.UserRole)
        mod_notes = mod_data["user_notes"]
        self.notes.setText(mod_notes)
        logger.debug(f"Finished setting notes for UUID: {mod_data["uuid"]}")

    @staticmethod
    def tr(text: str) -> str:
        return QCoreApplication.translate("ModInfo", text)

    def display_mod_info(self, uuid: str, render_unity_rt: bool) -> None:
        """
        This slot receives a the complete mod data json for
        the mod that was just clicked on. It will set the relevant
        information on the info panel.

        :param mod_info: complete json info for the mod
        """
        mod_info = self.metadata_manager.internal_local_metadata.get(uuid, {})
        # Style summary values based on validity
        if mod_info and mod_info.get("invalid"):
            # Set invalid value style
            for widget in (
                self.mod_info_name_value,
                self.mod_info_author_value,
                self.mod_info_package_id_value,
            ):
                widget.setObjectName("summaryValueInvalid")
                widget.style().unpolish(widget)
                widget.style().polish(widget)
            # Set invalid path style (red color, no clickable styling)
            self.mod_info_path_value.setStyleSheet(
                "color: #cc0000; text-decoration: none;"
            )
            self.mod_info_path_value.setClickable(False)
        else:
            # Set valid value style
            for widget in (
                self.mod_info_name_value,
                self.mod_info_author_value,
                self.mod_info_package_id_value,
            ):
                widget.setObjectName("summaryValue")
                widget.style().unpolish(widget)
                widget.style().polish(widget)
            # Set valid path style (inherits theme color, clickable styling)
            self.mod_info_path_value.setStyleSheet("text-decoration: underline;")
            self.mod_info_path_value.setClickable(True)
        # Set name value
        name_value = mod_info.get("name", "Not specified")
        if isinstance(name_value, dict):
            # Convert dict to string representation or fallback
            name_value = str(name_value)
        self.mod_info_name_value.setText(name_value)
        # Show essential info widgets
        for widget in self.essential_info_widgets:
            if not widget.isVisible():
                widget.show()
        # If it's not invalid, and it's not a scenario, it must be a mod!
        if not mod_info.get("invalid") and not mod_info.get("scenario"):
            # Show valid-mod-specific fields, hide scenario summary
            for widget in self.base_mod_info_widgets:
                widget.show()

            for widget in self.scenario_info_widgets:
                widget.hide()

            # Populate values from metadata

            # Set package ID
            self.mod_info_package_id_value.setText(
                mod_info.get("packageid", "Not specified")
            )

            # Set authors
            authors_tag = mod_info.get("authors", "Not specified")
            if isinstance(authors_tag, dict) and authors_tag.get("li"):
                list_of_authors = authors_tag["li"]
                authors_text = ", ".join(list_of_authors)
                self.mod_info_author_value.setText(authors_text)
            elif isinstance(authors_tag, str):
                self.mod_info_author_value.setText(
                    authors_tag if authors_tag else "Not specified"
                )
            else:
                self.mod_info_author_value.setText("Not specified")

            # Set mod version
            mod_version = mod_info.get("modversion", {})
            if isinstance(mod_version, dict):
                self.mod_info_mod_version_value.setText(
                    mod_version.get("#text", "Not specified")
                )
            else:
                self.mod_info_mod_version_value.setText(mod_version)

            # Set supported versions
            supported_versions_tag = mod_info.get("supportedversions", {})
            supported_versions_list = supported_versions_tag.get("li")
            if isinstance(supported_versions_list, list):
                supported_versions_text = ", ".join(supported_versions_list)
                self.mod_info_supported_versions_value.setText(supported_versions_text)
            else:
                self.mod_info_supported_versions_value.setText(
                    supported_versions_list
                    if supported_versions_list
                    else "Not specified"
                )
        elif mod_info.get("scenario"):  # Hide mod-specific widgets, show scenario
            for widget in self.base_mod_info_widgets:
                widget.hide()

            for widget in self.scenario_info_widgets:
                widget.show()

            self.scenario_info_summary_value.setText(
                mod_info.get("summary", "Not specified")
            )
        elif mod_info.get("invalid"):  # Hide all except bare minimum if invalid
            for widget in self.base_mod_info_widgets + self.scenario_info_widgets:
                widget.hide()

        self.mod_info_path_value.setPath(mod_info.get("path"))
        # Set the scrolling description for the Mod Info Panel
        self.description.setText("")
        if "description" in mod_info:
            if mod_info["description"] is not None:
                if isinstance(mod_info["description"], str):
                    self.description.setText(mod_info["description"], render_unity_rt)
                else:
                    logger.error(
                        f"[description] tag is not a string: {mod_info['description']}"
                    )
        elif "descriptionsbyversion" in mod_info and isinstance(
            mod_info["descriptionsbyversion"], dict
        ):
            major, minor = self.metadata_manager.game_version.split(".")[
                :2
            ]  # Split the version and take the first two parts
            version_regex = rf"v{major}\.{minor}"  # Construct the regex to match both major and minor versions
            for version, description_by_ver in mod_info[
                "descriptionsbyversion"
            ].items():
                if match(version_regex, version):
                    if isinstance(description_by_ver, str):
                        self.description.setText(description_by_ver, render_unity_rt)
                    else:
                        logger.error(
                            f"[descriptionbyversion] value for {version} is not a string: {description_by_ver}"
                        )
        # It is OK for the description value to be None (was not provided)
        # It is OK for the description key to not be in mod_info
        if mod_info.get("scenario"):
            pixmap = QPixmap(self.scenario_image_path)
            self.preview_picture.setPixmap(
                pixmap.scaled(
                    self.preview_picture.size(), Qt.AspectRatioMode.KeepAspectRatio
                )
            )
        else:
            # Get Preview.png
            workshop_folder_path = mod_info.get("path", "")
            logger.debug(
                f"Retrieved mod path to parse preview image: {workshop_folder_path}"
            )
            if os.path.exists(workshop_folder_path):
                about_folder_name = "About"
                about_folder_target_path = str(
                    (Path(workshop_folder_path) / about_folder_name)
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
                        str((Path(workshop_folder_path) / about_folder_name))
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
                        logger.debug("No preview image found for the mod")
                        pixmap = QPixmap(self.missing_image_path)
                        self.preview_picture.setPixmap(
                            pixmap.scaled(
                                self.preview_picture.size(),
                                Qt.AspectRatioMode.KeepAspectRatio,
                            )
                        )
                    else:
                        logger.debug("Preview image found")
                        image_path = str(
                            (
                                Path(workshop_folder_path)
                                / about_folder_name
                                / preview_file_name
                            )
                        )
                        pixmap = QPixmap(image_path)
                        self.preview_picture.setPixmap(
                            pixmap.scaled(
                                self.preview_picture.size(),
                                Qt.AspectRatioMode.KeepAspectRatio,
                            )
                        )
                else:
                    pixmap = QPixmap(self.missing_image_path)
                    self.preview_picture.setPixmap(
                        pixmap.scaled(
                            self.preview_picture.size(),
                            Qt.AspectRatioMode.KeepAspectRatio,
                        )
                    )
        logger.debug("Finished displaying mod info")
