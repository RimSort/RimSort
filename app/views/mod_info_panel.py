import os
from datetime import datetime
from pathlib import Path
from re import match
from typing import Any

from loguru import logger
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.controllers.metadata_controller import MetadataController
from app.controllers.metadata_db_controller import AuxMetadataController
from app.models.image_label import ImageLabel
from app.models.metadata.metadata_db import Base
from app.models.metadata.metadata_structure import AboutXmlMod, ListedMod, ScenarioMod
from app.models.settings import Settings
from app.sort.mod_sorting import path_to_folder_size
from app.utils.app_info import AppInfo
from app.utils.aux_db_utils import auxdb_get_mod_tags
from app.utils.custom_list_widget_item import CustomListWidgetItem
from app.utils.event_bus import EventBus
from app.utils.generic import format_file_size, platform_specific_open, scanpath
from app.utils.github.models import CacheBase, GitHubModEntry, GitHubReleaseCache
from app.utils.github.provider import GitHubProvider, _releases_from_json
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
        """Handle mouse click to open the folder or URL if clickable."""
        if event.button() == Qt.MouseButton.LeftButton and self.path and self.clickable:
            # If path looks like a URL, open in browser
            if self.path.startswith("http://") or self.path.startswith("https://"):
                import webbrowser

                try:
                    webbrowser.open(self.path)
                    logger.info(f"Opening URL: {self.path}")
                except Exception as e:
                    logger.error(f"Failed to open URL {self.path}: {e}")
            else:
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

    def __init__(
        self, settings: Settings, metadata_controller: MetadataController | None = None
    ) -> None:
        """
        Initialize the class.
        """
        logger.debug("Initializing ModInfo")

        # Cache MetadataController instance
        self.metadata_controller = metadata_controller or MetadataController.instance()
        self.settings = settings

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
        self.mod_info_tags = QHBoxLayout()
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

        self.mod_info_tags_label = QLabel(self.tr("Tags:"))
        self.mod_info_tags_label.setObjectName("summaryLabel")
        self.mod_info_tags_value = QLabel()
        self.mod_info_tags_value.setObjectName("summaryValue")
        self.mod_info_tags_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.mod_info_tags_value.setWordWrap(True)

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
        # Add Steam URL label and value
        self.mod_info_steam_url_label = QLabel(self.tr("Steam URL:"))
        self.mod_info_steam_url_label.setObjectName("summaryLabel")
        self.mod_info_steam_url_value = ClickablePathLabel()
        self.mod_info_steam_url_value.setObjectName("summaryValue")
        self.mod_info_steam_url_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.mod_info_steam_url_value.setWordWrap(True)
        # GitHub source and version
        self.mod_info_github_source_label = QLabel(self.tr("GitHub:"))
        self.mod_info_github_source_label.setObjectName("summaryLabel")
        self.mod_info_github_source_value = QLabel()
        self.mod_info_github_source_value.setObjectName("summaryValue")
        self.mod_info_github_source_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.mod_info_github_source_value.setWordWrap(True)

        self.mod_info_github_version_label = QLabel(self.tr("Version:"))
        self.mod_info_github_version_label.setObjectName("summaryLabel")
        self.mod_info_github_version_combo = QComboBox()
        self.mod_info_github_version_combo.setObjectName("githubVersionCombo")
        self.mod_info_github_version_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )

        self.mod_info_github_update_label = QLabel()
        self.mod_info_github_update_label.setObjectName("githubUpdateBadge")
        self.mod_info_github_update_label.hide()
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
        self.mod_info_tags.addWidget(self.mod_info_tags_label, NAME_LABEL_RATIO)
        self.mod_info_tags.addWidget(self.mod_info_tags_value, NAME_VALUE_RATIO)
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
        self.mod_info_layout.addLayout(self.mod_info_tags)
        self.mod_info_layout.addLayout(self.mod_info_mod_version)
        self.mod_info_layout.addLayout(self.mod_info_supported_versions)
        self.mod_info_layout.addLayout(self.mod_info_folder_size)
        self.mod_info_layout.addLayout(self.mod_info_path)
        self.mod_info_steam_url_layout = QHBoxLayout()
        self.mod_info_steam_url_layout.addWidget(self.mod_info_steam_url_label, 20)
        self.mod_info_steam_url_layout.addWidget(self.mod_info_steam_url_value, 80)
        self.mod_info_layout.addLayout(self.mod_info_steam_url_layout)
        self.mod_info_github_source_row = QHBoxLayout()
        self.mod_info_github_source_row.addWidget(
            self.mod_info_github_source_label, NAME_LABEL_RATIO
        )
        self.mod_info_github_source_row.addWidget(
            self.mod_info_github_source_value, NAME_VALUE_RATIO
        )
        self.mod_info_layout.addLayout(self.mod_info_github_source_row)
        self.mod_info_github_version_row = QHBoxLayout()
        self.mod_info_github_version_row.addWidget(
            self.mod_info_github_version_label, NAME_LABEL_RATIO
        )
        self.mod_info_github_version_row.addWidget(
            self.mod_info_github_version_combo, NAME_VALUE_RATIO
        )
        self.mod_info_github_version_row.addWidget(self.mod_info_github_update_label)
        self.mod_info_layout.addLayout(self.mod_info_github_version_row)
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
            self.mod_info_steam_url_label,
            self.mod_info_steam_url_value,
        ]

        self.base_mod_info_widgets = [
            self.mod_info_package_id_label,
            self.mod_info_package_id_value,
            self.mod_info_author_label,
            self.mod_info_author_value,
            self.mod_info_tags_label,
            self.mod_info_tags_value,
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

        self.hide_github_info()

        EventBus().do_refresh_mods_lists.connect(self._refresh_github_info)

        logger.debug("Finished ModInfo initialization")

    def show_github_info(
        self,
        owner_repo: str,
        installed_version: str,
        available_versions: list[str],
        update_available: bool,
        mod_path: str = "",
    ) -> None:
        """Show GitHub source info for a GitHub-tracked mod."""
        self._github_owner_repo = owner_repo
        self._github_installed_version = installed_version
        self._github_mod_path = mod_path

        self.mod_info_github_source_value.setText(owner_repo)

        try:
            self.mod_info_github_version_combo.activated.disconnect()
        except RuntimeError:
            pass  # No prior connection exists; safe to ignore

        self.mod_info_github_version_combo.clear()
        self.mod_info_github_version_combo.addItems(available_versions)
        idx = self.mod_info_github_version_combo.findText(installed_version)
        if idx >= 0:
            self.mod_info_github_version_combo.setCurrentIndex(idx)

        self.mod_info_github_version_combo.activated.connect(
            self._on_github_version_selected
        )

        if update_available:
            self.mod_info_github_update_label.setText(self.tr("(Update available)"))
            self.mod_info_github_update_label.show()
        else:
            self.mod_info_github_update_label.hide()

        self._set_github_row_visible(True)

    def _on_github_version_selected(self, index: int) -> None:
        """Handle user selecting a different version in the combo box."""
        selected = self.mod_info_github_version_combo.itemText(index)
        if selected == self._github_installed_version:
            return

        EventBus().github_version_switch_requested.emit(self._github_mod_path, selected)

    def hide_github_info(self) -> None:
        """Hide GitHub info row for non-GitHub mods."""
        self._set_github_row_visible(False)

    def _set_github_row_visible(self, visible: bool) -> None:
        self.mod_info_github_source_label.setVisible(visible)
        self.mod_info_github_source_value.setVisible(visible)
        self.mod_info_github_version_label.setVisible(visible)
        self.mod_info_github_version_combo.setVisible(visible)
        self.mod_info_github_update_label.setVisible(visible)

    def _refresh_github_info(self) -> None:
        """Re-check GitHub info for the currently displayed mod after a version switch."""
        try:
            mod_path = getattr(self, "_github_mod_path", None)
            if mod_path:
                self._update_github_info(mod_path)
        except Exception:
            logger.debug("Could not refresh GitHub info for current mod")

    def _update_github_info(self, mod_path: str | None) -> None:
        """Check if mod is GitHub-tracked and show/hide info accordingly."""
        if not mod_path:
            self.hide_github_info()
            return

        try:
            aux_controller = AuxMetadataController.get_or_create_cached_instance(
                self.settings.aux_db_path
            )
            Base.metadata.create_all(aux_controller.engine)

            with aux_controller.Session() as session:
                entry = (
                    session.query(GitHubModEntry).filter_by(mod_path=mod_path).first()
                )
                if entry is None:
                    self.hide_github_info()
                    return

                owner_repo = entry.owner_repo
                installed_version = entry.installed_version

            versions = [installed_version]
            update_available = False

            try:
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker as sa_sessionmaker

                cache_db = AppInfo().app_storage_folder / "github_release_cache.db"
                cache_engine = create_engine(f"sqlite+pysqlite:///{cache_db}")
                CacheBase.metadata.create_all(cache_engine)
                cache_session = sa_sessionmaker(bind=cache_engine)()
                try:
                    cached = (
                        cache_session.query(GitHubReleaseCache)
                        .filter_by(owner_repo=owner_repo)
                        .first()
                    )
                    if cached is not None:
                        releases = _releases_from_json(cached.releases_json)
                        if releases:
                            versions = [r.tag for r in releases]
                            versions.append("HEAD (latest commit)")
                            latest = GitHubProvider.get_latest_stable_release(releases)
                            if latest and installed_version != "HEAD":
                                installed_rel = next(
                                    (r for r in releases if r.tag == installed_version),
                                    None,
                                )
                                if (
                                    installed_rel
                                    and latest.published_at > installed_rel.published_at
                                ):
                                    update_available = True
                            elif latest and installed_version == "HEAD":
                                update_available = True
                finally:
                    cache_session.close()
            except Exception:
                logger.debug("Could not load cached releases for {}", owner_repo)

            self.show_github_info(
                owner_repo=owner_repo,
                installed_version=installed_version,
                available_versions=versions,
                update_available=update_available,
                mod_path=mod_path,
            )
        except Exception:
            logger.debug("Could not check GitHub mod status for {}", mod_path)
            self.hide_github_info()

    def update_user_mod_notes(self) -> None:
        if self.current_mod_item is None:
            return
        new_notes = self.notes.toPlainText()
        mod_data = self.current_mod_item.data(Qt.ItemDataRole.UserRole)
        mod_data["user_notes"] = new_notes
        # Update Aux DB
        path = mod_data["path"]
        if not path:
            logger.error("Unable to retrieve path when saving user notes to Aux DB.")
            return
        mod = self.metadata_controller.get_mod(path)
        if mod is None:
            logger.error(f"Mod not found for path {path} when saving user notes.")
            return
        mod_path = str(mod.mod_path) if mod.mod_path else path
        aux_metadata_controller = self.metadata_controller.metadata_db_controller
        with aux_metadata_controller.Session() as aux_metadata_session:
            aux_metadata_controller.update(
                aux_metadata_session,
                mod_path,
                user_notes=new_notes,
            )
        logger.debug(f"Finished updating notes for path: {mod_data['path']}")

    def show_user_mod_notes(self, item: CustomListWidgetItem) -> None:
        # Only show notes tab when a mod is selected
        self.notes.setVisible(True)
        self.current_mod_item = item
        mod_data = item.data(Qt.ItemDataRole.UserRole)
        mod_notes = mod_data["user_notes"]
        self.notes.blockSignals(True)
        self.notes.setText(mod_notes)
        self.notes.blockSignals(False)
        logger.debug(f"Finished setting notes for path: {mod_data['path']}")

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

    def _set_mod_tags_info(self, uuid: str) -> None:
        """Set user-defined tags information."""
        try:
            tags = auxdb_get_mod_tags(self.settings, uuid)
        except Exception as e:
            logger.debug(f"Failed to load tags for mod info panel UUID {uuid}: {e}")
            tags = []

        if tags:
            tags_text = ", ".join(f"[{tag}]" for tag in tags)
            self.mod_info_tags_value.setText(tags_text)
            self.mod_info_tags_value.setToolTip(tags_text)
        else:
            self.mod_info_tags_value.setText(self.tr("None"))
            self.mod_info_tags_value.setToolTip("")

    def _set_folder_size_info(self, uuid: str) -> None:
        """Set folder size information using optimized calculation."""
        try:
            size_bytes = path_to_folder_size(uuid)
            self.mod_info_folder_size_value.setText(format_file_size(size_bytes))
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
        if mod_path and os.path.exists(mod_path):
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
        self._set_mod_tags_info(uuid)
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
        self.mod_info_path_value.setPath(mod_metadata.get("path"))
        # Set Steam URL value
        steam_url: str | None = None
        pfid = mod_metadata.get("pfid")
        if isinstance(pfid, str) and pfid:
            steam_url = "https://steamcommunity.com/sharedfiles/filedetails/?id=" + pfid
        else:
            steam_url_candidate = mod_metadata.get("steam_url") or mod_metadata.get(
                "url"
            )
            if isinstance(steam_url_candidate, str) and steam_url_candidate:
                steam_url = steam_url_candidate
        self.mod_info_steam_url_value.setPath(steam_url)

        if steam_url:
            self.mod_info_steam_url_value.setToolTip(
                f"Click to open Steam Workshop: {steam_url}"
            )
        else:
            self.mod_info_steam_url_value.setToolTip("")
        # Set the scrolling description for the Mod Info Panel
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
            major, minor = self.metadata_controller.game_version.split(".")[
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
        This slot receives the UUID (path) of the mod that was just clicked on.
        It will set the relevant information on the info panel.

        :param uuid: UUID (path) of the mod to display
        :param render_unity_rt: Whether to render Unity rich text in descriptions
        """
        mod = self.metadata_controller.get_mod(uuid)
        if mod is None:
            return

        is_invalid = not isinstance(mod, AboutXmlMod)
        is_scenario = isinstance(mod, ScenarioMod)

        # Build a compatibility dict for helpers that still expect dict format
        mod_metadata = self._build_mod_metadata_dict(uuid, mod)

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
        mod_path = str(mod.mod_path) if mod.mod_path else None
        self.mod_info_path_value.setPath(mod_path)

        # Show or hide GitHub info based on whether this mod is tracked
        self._update_github_info(mod_path)

        # Set description
        self._set_description(mod_metadata, render_unity_rt)

        # Load preview image
        self._load_preview_image(mod_metadata, is_scenario)

        logger.debug("Finished displaying mod info")

    def _build_mod_metadata_dict(self, uuid: str, mod: ListedMod) -> dict[str, Any]:
        """Build a backward-compatible metadata dict from a ListedMod.

        This bridges the gap between the typed ListedMod API and helpers
        that still expect dict-based metadata. Intended to be removed once
        all helpers are fully migrated.
        """
        mod_path = str(mod.mod_path) if mod.mod_path else ""
        metadata: dict[str, Any] = {
            "uuid": uuid,
            "name": mod.name,
            "path": mod_path,
            "description": mod.description,
            "supportedversions": mod.supported_versions,
            "publishedfileid": mod.published_file_id,
            "internal_time_touched": mod.internal_time_touched,
        }
        if isinstance(mod, AboutXmlMod):
            metadata["packageid"] = str(mod.package_id)
            metadata["authors"] = mod.authors
            metadata["modversion"] = mod.mod_version
            metadata["url"] = mod.url
        else:
            metadata["packageid"] = mod.published_file_id or "unknown"
            metadata["invalid"] = True
        if isinstance(mod, ScenarioMod):
            metadata["scenario"] = True
            metadata["summary"] = mod.summary

        # Derive steam_url from published_file_id
        pfid = mod.published_file_id
        if pfid:
            metadata["pfid"] = pfid
            metadata["steam_url"] = (
                f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"
            )

        # Get external timestamps from aux DB
        _, aux_entry = self.metadata_controller.get_metadata_with_path(uuid)
        if aux_entry is not None:
            metadata["external_time_created"] = getattr(
                aux_entry, "external_time_created", None
            )
            metadata["external_time_updated"] = getattr(
                aux_entry, "external_time_updated", None
            )
            metadata["internal_time_updated"] = getattr(
                aux_entry, "internal_time_updated", None
            )

        return metadata
