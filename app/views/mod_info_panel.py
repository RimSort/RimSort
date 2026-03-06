import os
from datetime import datetime
from pathlib import Path
from re import match
from typing import Any

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

from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController
from app.models.image_label import ImageLabel
from app.sort.mod_sorting import uuid_to_folder_size
from app.utils.app_info import AppInfo
from app.utils.custom_list_widget_item import CustomListWidgetItem
from app.utils.generic import format_file_size, platform_specific_open, scanpath
from app.utils.metadata import MetadataManager
from app.utils.mod_info import UNKNOWN, ModInfo
from app.views.description_widget import DescriptionWidget

# Constants for layout proportions
NAME_LABEL_RATIO = 20
NAME_VALUE_RATIO = 80
IMAGE_LAYOUT_STRETCH = 35
MOD_INFO_LAYOUT_STRETCH = 20
NOTES_LAYOUT_STRETCH = 15
DESCRIPTION_LAYOUT_STRETCH = 30


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


class ModInfoPanel:
    """
    This class controls the layout and functionality for the
    mod information panel on the GUI.
    """

    def __init__(self, settings_controller: SettingsController) -> None:
        """
        Initialize the class.
        """
        logger.debug("Initializing ModInfo")

        # Cache MetadataManager instance
        self.metadata_manager = MetadataManager.instance()
        self.settings_controller = settings_controller

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
        self.mod_info_folder_size = QHBoxLayout()
        self.mod_info_path = QHBoxLayout()
        self.mod_info_last_touched = QHBoxLayout()
        self.mod_info_filesystem_time = QHBoxLayout()
        self.mod_info_external_times = QHBoxLayout()
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
        self.mod_info_folder_size_label = QLabel(self.tr("Folder Size:"))
        self.mod_info_folder_size_label.setObjectName("summaryLabel")
        self.mod_info_folder_size_value = QLabel()
        self.mod_info_folder_size_value.setObjectName("summaryValue")
        self.mod_info_path_label = QLabel(self.tr("Path:"))
        self.mod_info_path_label.setObjectName("summaryLabel")
        self.mod_info_path_value = ClickablePathLabel()
        self.mod_info_path_value.setObjectName("summaryValue")
        self.mod_info_path_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.mod_info_path_value.setWordWrap(True)
        self.mod_info_last_touched_label = QLabel(self.tr("Last Touched:"))
        self.mod_info_last_touched_label.setObjectName("summaryLabel")
        self.mod_info_last_touched_value = QLabel()
        self.mod_info_last_touched_value.setObjectName("summaryValue")
        self.mod_info_last_touched_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.mod_info_last_touched_value.setWordWrap(True)
        self.mod_info_filesystem_time_label = QLabel(self.tr("Filesystem Modified:"))
        self.mod_info_filesystem_time_label.setObjectName("summaryLabel")
        self.mod_info_filesystem_time_value = QLabel()
        self.mod_info_filesystem_time_value.setObjectName("summaryValue")
        self.mod_info_filesystem_time_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.mod_info_filesystem_time_value.setWordWrap(True)
        self.mod_info_external_times_label = QLabel(self.tr("Workshop Times:"))
        self.mod_info_external_times_label.setObjectName("summaryLabel")
        self.mod_info_external_times_value = QLabel()
        self.mod_info_external_times_value.setObjectName("summaryValue")
        self.mod_info_external_times_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.mod_info_external_times_value.setWordWrap(True)
        self.description = DescriptionWidget()
        self.description_text = self.tr("Welcome to RimSort!")
        self.description.setText(
            f"<br><br><br><center>{self.description_text}<h3></h3></center>",
            convert=False,
        )
        self.notes = QTextEdit()  # TODO: Custom QTextEdit to allow markdown and clickable hyperlinks? Also make collapsible?
        self.notes.setObjectName("userModNotes")
        self.notes.setPlaceholderText(self.tr("Put your personal mod notes here!"))
        self.notes.textChanged.connect(self.update_user_mod_notes)
        self.notes.setVisible(False)  # Only shows when a mod is selected
        # Add widgets to child layouts
        self.image_layout.addWidget(self.preview_picture)
        self.mod_info_name.addWidget(self.mod_info_name_label, NAME_LABEL_RATIO)
        self.mod_info_name.addWidget(self.mod_info_name_value, NAME_VALUE_RATIO)
        self.mod_info_path.addWidget(self.mod_info_path_label, NAME_LABEL_RATIO)
        self.mod_info_path.addWidget(self.mod_info_path_value, NAME_VALUE_RATIO)
        self.scenario_info_summary.addWidget(
            self.scenario_info_summary_label, NAME_LABEL_RATIO
        )
        self.scenario_info_summary.addWidget(
            self.scenario_info_summary_value, NAME_VALUE_RATIO
        )
        self.mod_info_package_id.addWidget(
            self.mod_info_package_id_label, NAME_LABEL_RATIO
        )
        self.mod_info_package_id.addWidget(
            self.mod_info_package_id_value, NAME_VALUE_RATIO
        )
        self.mod_info_authors.addWidget(self.mod_info_author_label, NAME_LABEL_RATIO)
        self.mod_info_authors.addWidget(self.mod_info_author_value, NAME_VALUE_RATIO)
        self.mod_info_mod_version.addWidget(
            self.mod_info_mod_version_label, NAME_LABEL_RATIO
        )
        self.mod_info_mod_version.addWidget(
            self.mod_info_mod_version_value, NAME_VALUE_RATIO
        )
        self.mod_info_supported_versions.addWidget(
            self.mod_info_supported_versions_label, NAME_LABEL_RATIO
        )
        self.mod_info_supported_versions.addWidget(
            self.mod_info_supported_versions_value, NAME_VALUE_RATIO
        )
        self.mod_info_folder_size.addWidget(
            self.mod_info_folder_size_label, NAME_LABEL_RATIO
        )
        self.mod_info_folder_size.addWidget(
            self.mod_info_folder_size_value, NAME_VALUE_RATIO
        )
        self.mod_info_last_touched.addWidget(
            self.mod_info_last_touched_label, NAME_LABEL_RATIO
        )
        self.mod_info_last_touched.addWidget(
            self.mod_info_last_touched_value, NAME_VALUE_RATIO
        )
        self.mod_info_filesystem_time.addWidget(
            self.mod_info_filesystem_time_label, NAME_LABEL_RATIO
        )
        self.mod_info_filesystem_time.addWidget(
            self.mod_info_filesystem_time_value, NAME_VALUE_RATIO
        )
        self.mod_info_external_times.addWidget(
            self.mod_info_external_times_label, NAME_LABEL_RATIO
        )
        self.mod_info_external_times.addWidget(
            self.mod_info_external_times_value, NAME_VALUE_RATIO
        )
        self.mod_info_layout.addLayout(self.mod_info_name)
        self.mod_info_layout.addLayout(self.scenario_info_summary)
        self.mod_info_layout.addLayout(self.mod_info_package_id)
        self.mod_info_layout.addLayout(self.mod_info_authors)
        self.mod_info_layout.addLayout(self.mod_info_mod_version)
        self.mod_info_layout.addLayout(self.mod_info_supported_versions)
        self.mod_info_layout.addLayout(self.mod_info_folder_size)
        self.mod_info_layout.addLayout(self.mod_info_path)
        self.notes_layout.addWidget(self.notes)
        self.mod_info_layout.addLayout(self.mod_info_last_touched)
        self.mod_info_layout.addLayout(self.mod_info_filesystem_time)
        self.mod_info_layout.addLayout(self.mod_info_external_times)
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
            self.mod_info_folder_size_label,
            self.mod_info_folder_size_value,
            self.mod_info_last_touched_label,
            self.mod_info_last_touched_value,
            self.mod_info_filesystem_time_label,
            self.mod_info_filesystem_time_value,
            self.mod_info_external_times_label,
            self.mod_info_external_times_value,
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
        # Update Aux DB
        aux_metadata_controller = AuxMetadataController.get_or_create_cached_instance(
            self.settings_controller.settings.aux_db_path
        )
        uuid = mod_data["uuid"]
        if not uuid:
            logger.error("Unable to retrieve uuid when saving user notes to Aux DB.")
            return
        with aux_metadata_controller.Session() as aux_metadata_session:
            mod_path = self.metadata_manager.internal_local_metadata[uuid]["path"]
            aux_metadata_controller.update(
                aux_metadata_session,
                mod_path,
                user_notes=new_notes,
            )
        logger.debug(f"Finished updating notes for UUID: {mod_data['uuid']}")

    def show_user_mod_notes(self, item: CustomListWidgetItem) -> None:
        # Only show notes tab when a mod is selected
        self.notes.setVisible(True)
        self.current_mod_item = item
        mod_data = item.data(Qt.ItemDataRole.UserRole)
        mod_notes = mod_data["user_notes"]
        self.notes.blockSignals(True)
        self.notes.setText(mod_notes)
        self.notes.blockSignals(False)
        logger.debug(f"Finished setting notes for UUID: {mod_data['uuid']}")

    def _add_label_value_to_layout(
        self, layout: QHBoxLayout, label: QLabel, value: QLabel
    ) -> None:
        """Helper method to add label-value pairs to layouts with consistent ratios."""
        layout.addWidget(label, NAME_LABEL_RATIO)
        layout.addWidget(value, NAME_VALUE_RATIO)

    @staticmethod
    def tr(text: str) -> str:
        return QCoreApplication.translate("ModInfo", text)

    def _set_widget_styling(self, is_invalid: bool) -> None:
        """Set widget styling based on mod validity."""
        if is_invalid:
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

    def _set_mod_version_info(self, mod_metadata: dict[str, Any]) -> None:
        """Set mod version information with error handling."""
        mod_version = mod_metadata.get("modversion", {})
        if isinstance(mod_version, dict):
            self.mod_info_mod_version_value.setText(mod_version.get("#text", UNKNOWN))
        else:
            self.mod_info_mod_version_value.setText(
                mod_version if mod_version else UNKNOWN
            )

    def _set_folder_size_info(self, uuid: str) -> None:
        """Set folder size information using optimized calculation."""
        try:
            if self.settings_controller.settings.inactive_mods_sorting:
                size_bytes = uuid_to_folder_size(uuid)
                self.mod_info_folder_size_value.setText(format_file_size(size_bytes))
            else:
                self.mod_info_folder_size_value.setText("Not available")
        except Exception as e:
            logger.error(f"Error calculating folder size for UUID {uuid}: {e}")
            self.mod_info_folder_size_value.setText("Not available")

    def _set_timestamp_info(
        self, timestamp: int | None, label: QLabel, field_name: str
    ) -> None:
        """Set timestamp information with consistent error handling."""
        if timestamp and timestamp != 0:
            try:
                dt = datetime.fromtimestamp(int(timestamp))
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                label.setText(formatted_time)
            except (ValueError, OSError, OverflowError) as e:
                logger.error(f"Error formatting {field_name}: {e}")
                label.setText("Invalid timestamp")
        else:
            label.setText("Not available")

    def _set_filesystem_time_info(self, mod_path: str | None) -> None:
        """Set filesystem modification time information."""
        if (
            self.settings_controller.settings.inactive_mods_sorting
            and mod_path
            and os.path.exists(mod_path)
        ):
            try:
                fs_time = int(os.path.getmtime(mod_path))
                self._set_timestamp_info(
                    fs_time, self.mod_info_filesystem_time_value, "filesystem time"
                )
            except (ValueError, OSError, OverflowError) as e:
                logger.error(f"Error formatting filesystem time: {e}")
                self.mod_info_filesystem_time_value.setText("Invalid timestamp")
        else:
            self.mod_info_filesystem_time_value.setText("Not available")

    def _set_external_times_info(self, mod_metadata: dict[str, Any]) -> None:
        """Set external workshop times information."""
        external_times = []
        external_time_created = mod_metadata.get("external_time_created")
        external_time_updated = mod_metadata.get("external_time_updated")
        internal_time_updated = mod_metadata.get("internal_time_updated")

        if external_time_created:
            try:
                dt_created = datetime.fromtimestamp(int(external_time_created))
                external_times.append(
                    f"Created: {dt_created.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except (ValueError, OSError, OverflowError):
                external_times.append("Created: Invalid")

        if external_time_updated:
            try:
                dt_updated = datetime.fromtimestamp(int(external_time_updated))
                external_times.append(
                    f"Updated: {dt_updated.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except (ValueError, OSError, OverflowError):
                external_times.append("Updated: Invalid")

        if internal_time_updated:
            try:
                dt_int_updated = datetime.fromtimestamp(int(internal_time_updated))
                external_times.append(
                    f"Steam Updated: {dt_int_updated.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except (ValueError, OSError, OverflowError):
                external_times.append("Steam Updated: Invalid")

        if external_times:
            self.mod_info_external_times_value.setText("\n".join(external_times))
        else:
            self.mod_info_external_times_value.setText("Not available")

    def _set_mod_info_fields(
        self, mod_metadata: dict[str, Any], mod_info: ModInfo, uuid: str
    ) -> None:
        """Set information fields for valid mods."""
        # Show valid-mod-specific fields, hide scenario summary
        for widget in self.base_mod_info_widgets:
            widget.show()
        for widget in self.scenario_info_widgets:
            widget.hide()

        # Populate values from ModInfo - all edge cases already handled
        self.mod_info_package_id_value.setText(mod_info.packageid)
        self.mod_info_author_value.setText(mod_info.authors)
        self.mod_info_supported_versions_value.setText(mod_info.supported_versions)

        # Set mod version
        self._set_mod_version_info(mod_metadata)

        # Set folder size
        self._set_folder_size_info(uuid)

        # Set last touched
        self._set_timestamp_info(
            mod_metadata.get("internal_time_touched"),
            self.mod_info_last_touched_value,
            "internal_time_touched",
        )

        # Set filesystem modification time
        self._set_filesystem_time_info(mod_metadata.get("path"))

        # Set external workshop times
        self._set_external_times_info(mod_metadata)

    def _set_scenario_info_fields(self, mod_metadata: dict[str, Any]) -> None:
        """Set information fields for scenarios."""
        # Hide mod-specific widgets, show scenario
        for widget in self.base_mod_info_widgets:
            widget.hide()
        for widget in self.scenario_info_widgets:
            widget.show()

        self.scenario_info_summary_value.setText(
            mod_metadata.get("summary", "Not specified")
        )

    def _set_invalid_info_fields(self) -> None:
        """Set information fields for invalid mods."""
        # Hide all except bare minimum if invalid
        for widget in self.base_mod_info_widgets + self.scenario_info_widgets:
            widget.hide()

    def _set_description(
        self, mod_metadata: dict[str, Any], render_unity_rt: bool
    ) -> None:
        """Set the mod description with version-specific handling."""
        self.description.setText("")
        if "description" in mod_metadata:
            if mod_metadata["description"] is not None:
                if isinstance(mod_metadata["description"], str):
                    self.description.setText(
                        mod_metadata["description"], render_unity_rt
                    )
                else:
                    logger.error(
                        f"[description] tag is not a string: {mod_metadata['description']}"
                    )
        elif "descriptionsbyversion" in mod_metadata and isinstance(
            mod_metadata["descriptionsbyversion"], dict
        ):
            major, minor = self.metadata_manager.game_version.split(".")[
                :2
            ]  # Split the version and take the first two parts
            version_regex = rf"v{major}\.{minor}"  # Construct the regex to match both major and minor versions
            for version, description_by_ver in mod_metadata[
                "descriptionsbyversion"
            ].items():
                if match(version_regex, version):
                    if isinstance(description_by_ver, str):
                        self.description.setText(description_by_ver, render_unity_rt)
                    else:
                        logger.error(
                            f"[descriptionbyversion] value for {version} is not a string: {description_by_ver}"
                        )

    def _load_preview_image(
        self, mod_metadata: dict[str, Any], is_scenario: bool
    ) -> None:
        """Load and set the preview image for the mod."""
        if is_scenario:
            pixmap = QPixmap(self.scenario_image_path)
            self.preview_picture.setPixmap(
                pixmap.scaled(
                    self.preview_picture.size(), Qt.AspectRatioMode.KeepAspectRatio
                )
            )
        else:
            # Get Preview.png
            workshop_folder_path = mod_metadata.get("path", "")
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
                    for temp_file in scanpath(workshop_folder_path):
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
                    for temp_file in scanpath(
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

    def display_mod_info(self, uuid: str, render_unity_rt: bool) -> None:
        """
        This slot receives a the complete mod data json for
        the mod that was just clicked on. It will set the relevant
        information on the info panel.

        :param uuid: UUID of the mod to display
        """
        mod_metadata = self.metadata_manager.internal_local_metadata.get(uuid, {})
        is_invalid = mod_metadata and mod_metadata.get("invalid")
        is_scenario = mod_metadata and mod_metadata.get("scenario")

        # Create ModInfo object - it handles all edge cases and formatting
        mod_info = ModInfo.from_metadata(uuid, mod_metadata)

        # Set widget styling based on validity
        self._set_widget_styling(is_invalid)

        # Set name value using ModInfo (which handles formatting and "Unknown")
        self.mod_info_name_value.setText(mod_info.name)

        # Show essential info widgets
        for widget in self.essential_info_widgets:
            if not widget.isVisible():
                widget.show()

        # Set fields based on mod type
        if not is_invalid and not is_scenario:
            self._set_mod_info_fields(mod_metadata, mod_info, uuid)
        elif is_scenario:
            self._set_scenario_info_fields(mod_metadata)
        elif is_invalid:
            self._set_invalid_info_fields()

        # Set path
        self.mod_info_path_value.setPath(mod_metadata.get("path"))

        # Set description
        self._set_description(mod_metadata, render_unity_rt)

        # Load preview image
        self._load_preview_image(mod_metadata, is_scenario)

        logger.debug("Finished displaying mod info")
