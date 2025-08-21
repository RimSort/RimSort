import os
from datetime import datetime
from pathlib import Path
from re import match
from typing import Any, Callable

from loguru import logger
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QAction, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.orm import Session

from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController
from app.models.image_label import ImageLabel
from app.models.metadata.metadata_db import AuxMetadataEntry
from app.utils.app_info import AppInfo
from app.utils.custom_list_widget_item import CustomListWidgetItem
from app.utils.generic import platform_specific_open
from app.utils.metadata import MetadataManager
from app.views.description_widget import DescriptionWidget
from app.views.dialogue import show_dialogue_input
from app.views.mods_panel import format_file_size, uuid_to_folder_size


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
        self.mod_info_tags = QHBoxLayout()
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
        # Tags widgets
        self.mod_info_tags_label = QLabel(self.tr("Tags:"))
        self.mod_info_tags_label.setObjectName("summaryLabel")
        self.mod_info_tags_container = QWidget()
        self.mod_info_tags_layout_inner = QHBoxLayout(self.mod_info_tags_container)
        self.mod_info_tags_layout_inner.setContentsMargins(0, 0, 0, 0)
        self.mod_info_tags_layout_inner.setSpacing(6)
        self.mod_info_tags_add_btn = QToolButton()
        self.mod_info_tags_add_btn.setText(self.tr("Add"))
        self.mod_info_tags_add_btn.setObjectName("MainUI")
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
        # Tags row
        self.mod_info_tags.addWidget(self.mod_info_tags_label, 20)
        # inner layout (tags chips) will be added dynamically; add add-button at the end
        self.mod_info_tags.addWidget(self.mod_info_tags_container, 70)
        self.mod_info_tags.addWidget(self.mod_info_tags_add_btn, 10)
        self.mod_info_folder_size.addWidget(self.mod_info_folder_size_label, 20)
        self.mod_info_folder_size.addWidget(self.mod_info_folder_size_value, 80)
        self.mod_info_last_touched.addWidget(self.mod_info_last_touched_label, 20)
        self.mod_info_last_touched.addWidget(self.mod_info_last_touched_value, 80)
        self.mod_info_filesystem_time.addWidget(self.mod_info_filesystem_time_label, 20)
        self.mod_info_filesystem_time.addWidget(self.mod_info_filesystem_time_value, 80)
        self.mod_info_external_times.addWidget(self.mod_info_external_times_label, 20)
        self.mod_info_external_times.addWidget(self.mod_info_external_times_value, 80)
        self.mod_info_layout.addLayout(self.mod_info_name)
        self.mod_info_layout.addLayout(self.scenario_info_summary)
        self.mod_info_layout.addLayout(self.mod_info_package_id)
        self.mod_info_layout.addLayout(self.mod_info_authors)
        self.mod_info_layout.addLayout(self.mod_info_mod_version)
        self.mod_info_layout.addLayout(self.mod_info_supported_versions)
        self.mod_info_layout.addLayout(self.mod_info_tags)
        self.mod_info_layout.addLayout(self.mod_info_folder_size)
        self.mod_info_layout.addLayout(self.mod_info_path)
        self.notes_layout.addWidget(self.notes)
        self.mod_info_layout.addLayout(self.mod_info_last_touched)
        self.mod_info_layout.addLayout(self.mod_info_filesystem_time)
        self.mod_info_layout.addLayout(self.mod_info_external_times)
        self.description_layout.addWidget(self.description)

        # Hide label/value by default
        self.essential_info_widgets: list[QWidget] = [
            self.mod_info_name_label,
            self.mod_info_name_value,
            self.mod_info_path_label,
            self.mod_info_path_value,
        ]

        self.base_mod_info_widgets: list[QWidget] = [
            self.mod_info_package_id_label,
            self.mod_info_package_id_value,
            self.mod_info_author_label,
            self.mod_info_author_value,
            self.mod_info_mod_version_label,
            self.mod_info_mod_version_value,
            self.mod_info_supported_versions_label,
            self.mod_info_supported_versions_value,
            self.mod_info_tags_label,
            self.mod_info_tags_container,
            self.mod_info_tags_add_btn,
            self.mod_info_folder_size_label,
            self.mod_info_folder_size_value,
            self.mod_info_last_touched_label,
            self.mod_info_last_touched_value,
            self.mod_info_filesystem_time_label,
            self.mod_info_filesystem_time_value,
            self.mod_info_external_times_label,
            self.mod_info_external_times_value,
        ]

        self.scenario_info_widgets: list[QWidget] = [
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

        # Wire add button
        self.mod_info_tags_add_btn.clicked.connect(self._on_add_tag_clicked)

    def _get_aux_controller_and_session(self) -> AuxMetadataController:
        """Get auxiliary metadata controller and create a new session context manager."""
        instance_path = Path(self.settings_controller.settings.current_instance_path)
        aux_metadata_controller = AuxMetadataController.get_or_create_cached_instance(
            instance_path / "aux_metadata.db"
        )
        return aux_metadata_controller

    def _get_mod_entry(self, aux_metadata_controller: AuxMetadataController, session: Session, uuid: str) -> AuxMetadataEntry | None:
        """Get the metadata entry for a mod by UUID."""
        return aux_metadata_controller.get(
            session, self.metadata_manager.internal_local_metadata[uuid]["path"]
        )

    def _perform_database_tag_operation(self, uuid: str, tag_text: str, operation_func: Callable[[Any, Any, str, Any], None]) -> None:
        """Perform a database tag operation with consistent session management."""
        aux_metadata_controller = self._get_aux_controller_and_session()
        from app.models.metadata.metadata_db import TagsEntry
        with aux_metadata_controller.Session() as session:
            entry = self._get_mod_entry(aux_metadata_controller, session, uuid)
            if entry:
                operation_func(entry, session, tag_text, TagsEntry)
                session.commit()

    def _update_mod_item_tags(self, uuid: str, tag_text: str, is_add: bool) -> None:
        """Update in-memory tags for the current mod item."""
        try:
            if self.current_mod_item is not None:
                item_data = self.current_mod_item.data(Qt.ItemDataRole.UserRole)
                tags = list(getattr(item_data, "tags", []))
                if is_add and tag_text not in tags:
                    tags.append(tag_text)
                elif not is_add and tag_text in tags:
                    tags.remove(tag_text)
                item_data["tags"] = sorted(tags, key=lambda s: s.lower())
                self.current_mod_item.setData(Qt.ItemDataRole.UserRole, item_data)
        except Exception:
            action = "add" if is_add else "removal"
            logger.exception(f"Failed to update in-memory tags after {action}")

    def _rebuild_tags_row(self, uuid: str) -> None:
        # Clear existing tag chips
        while self.mod_info_tags_layout_inner.count():
            item = self.mod_info_tags_layout_inner.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        # Load tags from Aux DB
        aux_metadata_controller = self._get_aux_controller_and_session()
        tags: list[str] = []
        with aux_metadata_controller.Session() as session:
            entry = self._get_mod_entry(aux_metadata_controller, session, uuid)
            if entry and entry.tags:
                tags = sorted([t.tag for t in entry.tags if isinstance(t.tag, str)], key=lambda s: s.lower())
        # Create a chip (label + remove) for each tag
        for tag in tags:
            chip = QWidget(self.mod_info_tags_container)
            lay = QHBoxLayout(chip)
            lay.setContentsMargins(4, 0, 4, 0)
            lay.setSpacing(4)
            lbl = QLabel(tag)
            lbl.setObjectName("summaryValue")
            rm = QToolButton()
            rm.setText("×")
            rm.setToolTip(self.tr("Remove tag"))
            rm.clicked.connect(lambda _=None, t=tag: self._remove_tag(uuid, t))
            lay.addWidget(lbl)
            lay.addWidget(rm)
            chip.setLayout(lay)
            self.mod_info_tags_layout_inner.addWidget(chip)
        self.mod_info_tags_layout_inner.addStretch(1)

    def _remove_tag(self, uuid: str, tag_text: str) -> None:
        def remove_operation(entry: Any, session: Any, tag_text: str, TagsEntry: Any) -> None:
            try:
                entry.tags.remove(TagsEntry(tag=tag_text))
            except ValueError:
                pass
        
        self._perform_database_tag_operation(uuid, tag_text, remove_operation)
        self._update_mod_item_tags(uuid, tag_text, is_add=False)
        self._rebuild_tags_row(uuid)

    def _on_add_tag_clicked(self) -> None:
        if self.current_mod_item is None:
            return
        mod_data = self.current_mod_item.data(Qt.ItemDataRole.UserRole)
        uuid = mod_data["uuid"]
        if not uuid:
            return
        # Build menu with existing tags + actions
        menu = QMenu()
        # Existing tags
        aux_metadata_controller = self._get_aux_controller_and_session()
        from app.models.metadata.metadata_db import TagsEntry
        existing_tags: list[str] = []
        with aux_metadata_controller.Session() as session:
            for t in session.query(TagsEntry).all():
                if isinstance(t.tag, str) and t.tag.strip():
                    existing_tags.append(t.tag)
        for tag_text in sorted(existing_tags, key=lambda s: s.lower()):
            act = QAction(tag_text, menu)
            act.triggered.connect(lambda _=None, tag=tag_text: self._add_tag(uuid, tag))
            menu.addAction(act)
        if existing_tags:
            menu.addSeparator()
        # New tag action
        new_act = QAction(self.tr("New…"), menu)
        def _new_tag() -> None:
            tag_text, ok = show_dialogue_input(title=self.tr("Tag"), label=self.tr("Enter new tag"), text="")
            if ok:
                tag_text = (tag_text or "").strip()
                if tag_text:
                    self._add_tag(uuid, tag_text)
        new_act.triggered.connect(_new_tag)
        menu.addAction(new_act)
        # Popup near button
        menu.exec_(self.mod_info_tags_add_btn.mapToGlobal(self.mod_info_tags_add_btn.rect().bottomLeft()))

    def _add_tag(self, uuid: str, tag_text: str) -> None:
        def add_operation(entry: Any, session: Any, tag_text: str, TagsEntry: Any) -> None:
            current = [t.tag for t in (entry.tags or [])]
            if tag_text not in current:
                existing = (
                    session.query(TagsEntry).filter(TagsEntry.tag == tag_text).first()
                )
                entry.tags.append(existing or TagsEntry(tag=tag_text))
        
        self._perform_database_tag_operation(uuid, tag_text, add_operation)
        self._update_mod_item_tags(uuid, tag_text, is_add=True)
        self._rebuild_tags_row(uuid)

    def update_user_mod_notes(self) -> None:
        if self.current_mod_item is None:
            return
        new_notes = self.notes.toPlainText()
        mod_data = self.current_mod_item.data(Qt.ItemDataRole.UserRole)
        mod_data["user_notes"] = new_notes
        # Update Aux DB
        instance_path = Path(self.settings_controller.settings.current_instance_path)
        aux_metadata_controller = AuxMetadataController.get_or_create_cached_instance(
            instance_path / "aux_metadata.db"
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
        w: QWidget  # Type annotation for widget loop variable
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
        # Build/update tags row
        try:
            self._rebuild_tags_row(uuid)
        except Exception:
            logger.exception("Failed to rebuild tags row")
        # Show essential info widgets
        for w in self.essential_info_widgets:
            if not w.isVisible():
                w.show()
        # If it's not invalid, and it's not a scenario, it must be a mod!
        if not mod_info.get("invalid") and not mod_info.get("scenario"):
            # Show valid-mod-specific fields, hide scenario summary
            for w in self.base_mod_info_widgets:
                w.show()

            for w in self.scenario_info_widgets:
                w.hide()

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

            # Set folder size
            try:
                if self.settings_controller.settings.enable_advanced_filtering:
                    size_bytes = uuid_to_folder_size(uuid)
                    self.mod_info_folder_size_value.setText(
                        format_file_size(size_bytes)
                    )
                else:
                    self.mod_info_folder_size_value.setText("Not available")
            except Exception:
                self.mod_info_folder_size_value.setText("Not available")

            # Set last touched
            internal_time_touched = mod_info.get("internal_time_touched")
            if internal_time_touched and internal_time_touched != 0:
                try:
                    dt_touched = datetime.fromtimestamp(int(internal_time_touched))
                    formatted_time = dt_touched.strftime("%Y-%m-%d %H:%M:%S")
                    self.mod_info_last_touched_value.setText(formatted_time)
                except (ValueError, OSError, OverflowError) as e:
                    logger.error(f"Error formatting internal_time_touched: {e}")
                    self.mod_info_last_touched_value.setText("Invalid timestamp")
            else:
                self.mod_info_last_touched_value.setText("Not available")

            # Set filesystem modification time
            mod_path = mod_info.get("path")
            if (
                self.settings_controller.settings.enable_advanced_filtering
                and mod_path
                and os.path.exists(mod_path)
            ):
                try:
                    fs_time = int(os.path.getmtime(mod_path))
                    dt_fs = datetime.fromtimestamp(fs_time)
                    formatted_fs_time = dt_fs.strftime("%Y-%m-%d %H:%M:%S")
                    self.mod_info_filesystem_time_value.setText(formatted_fs_time)
                except (ValueError, OSError, OverflowError) as e:
                    logger.error(f"Error formatting filesystem time: {e}")
                    self.mod_info_filesystem_time_value.setText("Invalid timestamp")
            else:
                self.mod_info_filesystem_time_value.setText("Not available")

            # Set external workshop times
            external_times = []
            external_time_created = mod_info.get("external_time_created")
            external_time_updated = mod_info.get("external_time_updated")
            internal_time_updated = mod_info.get("internal_time_updated")

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
        elif mod_info.get("scenario"):  # Hide mod-specific widgets, show scenario
            for w in self.base_mod_info_widgets:
                w.hide()

            for w in self.scenario_info_widgets:
                w.show()

            self.scenario_info_summary_value.setText(
                mod_info.get("summary", "Not specified")
            )
        elif mod_info.get("invalid"):  # Hide all except bare minimum if invalid
            for w in self.base_mod_info_widgets + self.scenario_info_widgets:
                w.hide()

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
