import json
import os
from datetime import datetime
from difflib import SequenceMatcher
from functools import partial
from pathlib import Path
from shutil import copy2, copytree
from traceback import format_exc
from typing import Any, Dict, Optional, cast

from loguru import logger
from platformdirs import PlatformDirs
from PySide6.QtCore import (
    QEvent,
    QItemSelection,
    QModelIndex,
    QObject,
    QRectF,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QDropEvent,
    QEnterEvent,
    QFocusEvent,
    QFontMetrics,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QColorDialog,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from rapidfuzz import fuzz
from sqlalchemy import text

from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController
from app.models.divider import DividerData, generate_divider_uuid, is_divider_uuid
from app.sort.mod_sorting import (
    _FOLDER_SIZE_CACHE,
    FolderSizeWorker,
    ModsPanelSortKey,
    sort_uuids,
)
from app.utils.acf_utils import steamcmd_purge_mods
from app.utils.app_info import AppInfo
from app.utils.aux_db_utils import (
    auxdb_update_all_mod_colors,
    auxdb_update_all_mod_font_colors,
    auxdb_update_mod_color,
    auxdb_update_mod_font_color,
)
from app.utils.constants import (
    KNOWN_MOD_REPLACEMENTS,
    SEARCH_DATA_SOURCE_FILTER_INDEXES,
)
from app.utils.custom_list_widget_item import CustomListWidgetItem
from app.utils.custom_list_widget_item_metadata import CustomListWidgetItemMetadata
from app.utils.custom_qlabels import AdvancedClickableQLabel, ClickableQLabel
from app.utils.event_bus import EventBus
from app.utils.generic import (
    copy_to_clipboard_safely,
    delete_files_except_extension,
    flatten_to_list,
    format_file_size,
    launch_process,
    open_url_browser,
    platform_specific_open,
    sanitize_filename,
)
from app.utils.metadata import MetadataManager, ModMetadata
from app.utils.xml import extract_xml_package_ids, fast_rimworld_xml_save_validation
from app.views.deletion_menu import ModDeletionMenu
from app.views.dialogue import (
    show_dialogue_conditional,
    show_warning,
)
from app.views.divider_widget import DividerItemInner


class ModListItemInner(QWidget):
    """
    Subclass for QWidget. Used to store data for a single
    mod and display relevant data on a mod list.
    """

    toggle_warning_signal = Signal(str, str)
    toggle_error_signal = Signal(str, str)

    def __init__(
        self,
        errors_warnings: str,
        errors: str,
        warnings: str,
        filtered: bool,
        invalid: bool,
        mismatch: bool,
        alternative: bool,
        settings_controller: SettingsController,
        uuid: str,
        mod_color: QColor,
        mod_font_color: QColor | None = None,
    ) -> None:
        """
        Initialize the QWidget with mod uuid. Metadata can be accessed via MetadataManager.

        All metadata tags are set to the corresponding field if it
        exists in the metadata dict. See tags:
        https://rimworldwiki.com/wiki/About.xml
        """

        super(ModListItemInner, self).__init__()

        # Used to handle hover, select etc. behavior for this custom widget
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self._selected = False
        self._hovered = False

        # Cache MetadataManager instance
        self.metadata_manager = MetadataManager.instance()

        # Cache error and warning strings for tooltips
        self.errors_warnings = errors_warnings
        self.errors = errors
        self.warnings = warnings
        # Cache filtered state of widget's item - used to determine styling of widget
        self.filtered = filtered
        # Cache invalid state of widget's item - used to determine styling of widget
        self.invalid = invalid
        # Cache mismatch state of widget's item - used to determine warning icon visibility
        self.mismatch = mismatch
        # Cache alternative state of widget's item - used to determine warning icon visibility
        self.alternative = alternative
        # Cache SettingsManager instance
        self.settings_controller = settings_controller
        self.mod_color: QColor | None = mod_color
        self.mod_font_color: QColor | None = mod_font_color

        # All data, including name, author, package id, dependencies,
        # whether the mod is a workshop mod or expansion, etc is encapsulated
        # in this variable. This is exactly equal to the dict value of a
        # single all_mods key-value
        self.uuid = uuid
        name_value = self.metadata_manager.internal_local_metadata.get(
            self.uuid, {}
        ).get("name")
        if not isinstance(name_value, str):
            name_value = "name error in mod about.xml"
        self.list_item_name = name_value
        self.main_label = QLabel()

        # Visuals
        self.setToolTip(self.get_tool_tip_text())
        self.main_item_layout = QHBoxLayout()
        self.main_item_layout.setContentsMargins(0, 0, 0, 0)
        self.main_item_layout.setSpacing(0)
        self.font_metrics = QFontMetrics(self.font())

        # Icons that are conditional
        self.csharp_icon = None
        self.xml_icon = None
        if self.settings_controller.settings.mod_type_filter:
            if (
                self.metadata_manager.internal_local_metadata.get(self.uuid, {}).get(
                    "csharp"
                )
            ) is not None:
                self.csharp_icon = QLabel()
                self.csharp_icon.setPixmap(
                    ModListIcons.csharp_icon().pixmap(QSize(20, 20))
                )
                self.csharp_icon.setToolTip(
                    self.tr("Contains custom C# assemblies (custom code)")
                )
            else:
                self.xml_icon = QLabel()
                self.xml_icon.setPixmap(ModListIcons.xml_icon().pixmap(QSize(20, 20)))
                self.xml_icon.setToolTip(
                    self.tr("Contains custom content (textures / XML)")
                )
        self.git_icon = None
        if (
            self.metadata_manager.internal_local_metadata[self.uuid]["data_source"]
            == "local"
            and self.metadata_manager.internal_local_metadata[self.uuid].get("git_repo")
            and not self.metadata_manager.internal_local_metadata[self.uuid].get(
                "steamcmd"
            )
        ):
            self.git_icon = QLabel()
            self.git_icon.setPixmap(ModListIcons.git_icon().pixmap(QSize(20, 20)))
            self.git_icon.setToolTip(
                self.tr("Local mod that contains a git repository")
            )
        self.steamcmd_icon = None
        if self.metadata_manager.internal_local_metadata[self.uuid][
            "data_source"
        ] == "local" and self.metadata_manager.internal_local_metadata[self.uuid].get(
            "steamcmd"
        ):
            self.steamcmd_icon = QLabel()
            self.steamcmd_icon.setPixmap(
                ModListIcons.steamcmd_icon().pixmap(QSize(20, 20))
            )
            self.steamcmd_icon.setToolTip(
                self.tr("Local mod that can be used with SteamCMD")
            )
        # Warning icon hidden by default
        self.warning_icon_label = ClickableQLabel()
        self.warning_icon_label.clicked.connect(self.__on_warning_icon_clicked)
        self.warning_icon_label.setPixmap(
            ModListIcons.warning_icon().pixmap(QSize(20, 20))
        )
        # Default to hidden to avoid showing early
        self.warning_icon_label.setHidden(True)
        # New icon hidden by default
        self.new_icon_label = QLabel()
        self.new_icon_label.setPixmap(ModListIcons.new_icon().pixmap(QSize(20, 20)))
        self.new_icon_label.setToolTip(self.tr("Not in latest save"))
        # Default to hidden to avoid showing early
        self.new_icon_label.setHidden(True)
        # In-save icon (for inactive list items): hidden by default
        self.in_save_icon_label = QLabel()
        self.in_save_icon_label.setPixmap(
            ModListIcons.clear_icon().pixmap(QSize(20, 20))
        )
        self.in_save_icon_label.setToolTip(self.tr("In latest save"))
        self.in_save_icon_label.setHidden(True)
        # Error icon hidden by default
        self.error_icon_label = ClickableQLabel()
        self.error_icon_label.clicked.connect(self.__on_error_icon_clicked)
        self.error_icon_label.setPixmap(ModListIcons.error_icon().pixmap(QSize(20, 20)))
        # Default to hidden to avoid showing early
        self.error_icon_label.setHidden(True)
        # Translation status label
        self.translation_status_label = QLabel()
        self.translation_status_label.setHidden(True)
        # Icons by mod source
        self.mod_source_icon = None
        if not self.git_icon and not self.steamcmd_icon:
            self.mod_source_icon = QLabel()
            self.mod_source_icon.setPixmap(self.get_icon().pixmap(QSize(20, 20)))
            # Set tooltip based on mod source
            data_source = self.metadata_manager.internal_local_metadata[self.uuid].get(
                "data_source"
            )
            if data_source == "expansion":
                self.mod_source_icon.setObjectName("expansion")
                self.mod_source_icon.setToolTip(
                    self.tr("Official RimWorld content by Ludeon Studios")
                )
            elif data_source == "local":
                if self.metadata_manager.internal_local_metadata[self.uuid].get(
                    "git_repo"
                ):
                    self.mod_source_icon.setObjectName("git_repo")
                elif self.metadata_manager.internal_local_metadata[self.uuid].get(
                    "steamcmd"
                ):
                    self.mod_source_icon.setObjectName("steamcmd")
                else:
                    self.mod_source_icon.setObjectName("local")
                    self.mod_source_icon.setToolTip(self.tr("Installed locally"))
            elif data_source == "workshop":
                self.mod_source_icon.setObjectName("workshop")
                self.mod_source_icon.setToolTip(self.tr("Subscribed via Steam"))
        if self.mod_color is not None or self.mod_font_color is not None:
            self.main_label.setObjectName("ListItemLabelCustomColor")
            self.handle_mod_color_change(init=True)
        elif self.filtered:
            self.main_label.setObjectName("ListItemLabelFiltered")
        elif errors_warnings:
            self.main_label.setObjectName("ListItemLabelInvalid")
        else:
            self.main_label.setObjectName("ListItemLabel")
        # Add icons
        if self.git_icon:
            self.main_item_layout.addWidget(self.git_icon, Qt.AlignmentFlag.AlignRight)
        if self.steamcmd_icon:
            self.main_item_layout.addWidget(
                self.steamcmd_icon, Qt.AlignmentFlag.AlignRight
            )
        if self.mod_source_icon:
            self.main_item_layout.addWidget(
                self.mod_source_icon, Qt.AlignmentFlag.AlignRight
            )
        if self.csharp_icon:
            self.main_item_layout.addWidget(
                self.csharp_icon, Qt.AlignmentFlag.AlignRight
            )
        if self.xml_icon:
            self.main_item_layout.addWidget(self.xml_icon, Qt.AlignmentFlag.AlignRight)
        # Compose the layout of our widget and set it to the main layout
        self.main_item_layout.addWidget(self.main_label, Qt.AlignmentFlag.AlignCenter)
        if self.settings_controller.settings.show_save_comparison_indicators:
            self.main_item_layout.addWidget(
                self.in_save_icon_label, Qt.AlignmentFlag.AlignRight
            )
            self.main_item_layout.addWidget(
                self.new_icon_label, Qt.AlignmentFlag.AlignRight
            )

        self.main_item_layout.addWidget(
            self.translation_status_label, Qt.AlignmentFlag.AlignRight
        )
        self.main_item_layout.addWidget(
            self.warning_icon_label, Qt.AlignmentFlag.AlignRight
        )
        self.main_item_layout.addWidget(
            self.error_icon_label, Qt.AlignmentFlag.AlignRight
        )
        self.main_item_layout.addStretch()
        self.setLayout(self.main_item_layout)

        # Reveal if errors or warnings exist
        if self.warnings:
            self.warning_icon_label.setToolTip(self.warnings)
            self.warning_icon_label.setHidden(False)
        if self.errors:
            self.error_icon_label.setToolTip(self.errors)
            self.error_icon_label.setHidden(False)

        self._last_icon_count = self.count_icons(self)

    def __on_error_icon_clicked(self) -> None:
        self.toggle_error_signal.emit(
            self.metadata_manager.internal_local_metadata[self.uuid]["packageid"],
            self.uuid,
        )

    def __on_warning_icon_clicked(self) -> None:
        self.toggle_warning_signal.emit(
            self.metadata_manager.internal_local_metadata[self.uuid]["packageid"],
            self.uuid,
        )

    def _resize_text_after_icon_toggle(self, icon_count: int = -1) -> None:
        event = QResizeEvent(self.size(), self.size())
        self.resizeEvent(event, icon_count=icon_count)

    def update_translation_status(self, is_translated: bool) -> None:
        if is_translated:
            self.translation_status_label.setText("🟢")
            self.translation_status_label.setToolTip(self.tr("Translation available - This mod has a translation or is already localized"))
        else:
            self.translation_status_label.setText("🔴")
            self.translation_status_label.setToolTip(self.tr("No translation found - This mod does not have a translation installed"))
        self.translation_status_label.setHidden(False)
        self._resize_text_after_icon_toggle()

    def hide_translation_status(self) -> None:
        self.translation_status_label.setHidden(True)
        self._resize_text_after_icon_toggle()

    def enterEvent(self, event: QEnterEvent) -> None:
        self._hovered = True
        if self._selected:
            return
        self.setStyleSheet("")
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hovered = False
        if self._selected:
            return
        if self.mod_color is None and self.mod_font_color is None:
            self.setStyleSheet("")
        else:
            self.handle_mod_color_change(init=True)
        super().leaveEvent(event)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.handle_selected()

    def handle_selected(self) -> None:
        if self._selected:
            self.setStyleSheet("")
        elif not self._selected:
            if self.mod_color or self.mod_font_color:
                self.handle_mod_color_change(init=True)
            else:
                self.setStyleSheet("")

    def count_icons(self, widget: QObject) -> int:
        count = 0
        if isinstance(widget, QLabel):
            try:
                if widget.isHidden():
                    return 0
            except Exception:
                pass
            pixmap = widget.pixmap()
            if pixmap and not pixmap.isNull():
                count += 1

        if isinstance(widget, QWidget):
            for child in widget.children():
                count += self.count_icons(child)

        return count

    def get_tool_tip_text(self) -> str:
        """
        Compose a mod_list_item's tool_tip_text

        :return: string containing the tool_tip_text
        """
        metadata = self.metadata_manager.internal_local_metadata.get(self.uuid, {})

        name_line = f"Mod: {metadata.get('name', 'Not specified')}\n"

        authors_tag = metadata.get("authors")
        authors_text = (
            ", ".join(authors_tag.get("li", ["Not specified"]))
            if isinstance(authors_tag, dict)
            else authors_tag or "Not specified"
        )
        author_line = f"Authors: {authors_text}\n"

        package_id = metadata.get("packageid", "Not specified")
        package_id_line = f"PackageID: {package_id}\n"

        mod_version = metadata.get("modversion", "Not specified")
        modversion_line = f"Mod Version: {mod_version}\n"

        supported_versions_tag = metadata.get("supportedversions", {})
        supported_versions_list = supported_versions_tag.get("li")
        supported_versions_text = (
            ", ".join(supported_versions_list)
            if isinstance(supported_versions_list, list)
            else supported_versions_list or "Not specified"
        )
        supported_versions_line = f"Supported Versions: {supported_versions_text}\n"

        path = metadata.get("path", "Not specified")
        path_line = f"Path: {path}\n"

        # Add folder size and filesystem modification time information without heavy IO on hover
        mod_path = metadata.get("path")
        # Folder size: read from in-memory cache only; avoid computing on tooltip
        folder_size_line = "Folder Size: Not available\n"
        if self.settings_controller.settings.inactive_mods_sorting:
            if isinstance(mod_path, str):
                cached = _FOLDER_SIZE_CACHE.get(mod_path)
                if cached:
                    folder_size_line = f"Folder Size: {format_file_size(cached[1])}\n"

        # Filesystem modified time: prefer cached metadata value
        fs_time_val = metadata.get("internal_time_touched")
        if isinstance(fs_time_val, int) and fs_time_val > 0:
            try:
                dt_fs = datetime.fromtimestamp(fs_time_val)
                formatted_time = dt_fs.strftime("%Y-%m-%d %H:%M:%S")
                last_touched_line = f"Filesystem Modified: {formatted_time}"
            except (ValueError, OSError, OverflowError):
                last_touched_line = "Filesystem Modified: Invalid timestamp"
        else:
            last_touched_line = "Filesystem Modified: Not available"

        return "".join(
            [
                name_line,
                author_line,
                package_id_line,
                modversion_line,
                folder_size_line,
                supported_versions_line,
                path_line,
                last_touched_line,
            ]
        )

    def get_icon(self) -> QIcon:
        """
        Check custom tags added to mod metadata upon initialization, and return the corresponding
        QIcon for the mod's source type (expansion, workshop, or local mod?)

        :return: QIcon object set to the path of the corresponding icon image
        """
        if (
            self.metadata_manager.internal_local_metadata[self.uuid].get("data_source")
            == "expansion"
        ):
            return ModListIcons.ludeon_icon()
        elif (
            self.metadata_manager.internal_local_metadata[self.uuid].get("data_source")
            == "local"
        ):
            return ModListIcons.local_icon()
        elif (
            self.metadata_manager.internal_local_metadata[self.uuid].get("data_source")
            == "workshop"
        ):
            return ModListIcons.steam_icon()
        else:
            logger.error(
                f"No type found for ModListItemInner with package id {self.metadata_manager.internal_local_metadata[self.uuid].get('packageid')}"
            )
            return ModListIcons.local_icon()

    def resizeEvent(self, event: QResizeEvent, icon_count: int = -1) -> None:
        """
        When the label is resized (as the window is resized),
        also elide the label if needed.

        :param event: the resize event
        :param icon_count: int, the number of icons to consider for width calculation. If -1, icon count will be calculated
        """
        if icon_count == -1:
            # Count the number of QLabel widgets with QIcon and calculate total icon width
            icon_count = self.count_icons(self)
        icon_width = icon_count * 20
        if not self.translation_status_label.isHidden():
            icon_width += self.translation_status_label.fontMetrics().boundingRect(self.translation_status_label.text()).width() + 6
        # If only 2 icons (On the left, eg. c#/xml/steam/local etc.) No need for padding.
        padding = 6 if icon_count > 2 else 0
        self.item_width = super().width()
        text_width_needed = QRectF(
            self.font_metrics.boundingRect(self.list_item_name)
        ).width()
        if text_width_needed > self.item_width - icon_width - padding:
            available_width = max(0, int(self.item_width - icon_width - padding))
            shortened_text = self.font_metrics.elidedText(
                self.list_item_name, Qt.TextElideMode.ElideRight, available_width
            )
            self.main_label.setText(str(shortened_text))
        else:
            self.main_label.setText(self.list_item_name)
        return super().resizeEvent(event)

    def repolish(self, item: CustomListWidgetItem) -> None:
        """
        Repolish the widget items
        """
        item_data = item.data(Qt.ItemDataRole.UserRole)
        error_tooltip = item_data["errors"]
        warning_tooltip = item_data["warnings"]
        # If an error exists we show an error icon with error tooltip
        # If a warning exists we show a warning icon with warning tooltip
        if error_tooltip:
            self.error_icon_label.setHidden(False)
            self.error_icon_label.setToolTip(error_tooltip)
        else:  # Hide the error icon if no error tool tip text
            self.error_icon_label.setHidden(True)
            self.error_icon_label.setToolTip("")
        if warning_tooltip:
            self.warning_icon_label.setHidden(False)
            self.warning_icon_label.setToolTip(warning_tooltip)
        else:  # Hide the warning icon if no warning tool tip text
            self.warning_icon_label.setHidden(True)
            self.warning_icon_label.setToolTip("")
        # New / In-save icon visibility depends on list type and user setting
        is_new = bool(item_data.__dict__.get("is_new", False))
        in_save = bool(item_data.__dict__.get("in_save", False))
        # Read list_type from persisted item metadata instead of Qt widget to satisfy static typing
        list_type = cast(str | None, item_data.__dict__.get("list_type"))
        # Respect setting toggle
        show_indicators = (
            self.settings_controller.settings.show_save_comparison_indicators
        )
        if not show_indicators:
            self.new_icon_label.setHidden(True)
            self.in_save_icon_label.setHidden(True)
        elif list_type == "Active":
            self.new_icon_label.setHidden(not is_new)
            self.in_save_icon_label.setHidden(True)
        elif list_type == "Inactive":
            self.new_icon_label.setHidden(True)
            self.in_save_icon_label.setHidden(not in_save)
        else:
            self.new_icon_label.setHidden(True)
            self.in_save_icon_label.setHidden(True)
        # Recalculate the widget label's styling based on item data
        widget_object_name = self.main_label.objectName()
        if item_data["mod_color"] is not None or item_data["mod_font_color"] is not None:
            self.handle_mod_color_change(item)
            new_widget_object_name = "ListItemLabelCustomColor"
        elif item_data["filtered"]:
            new_widget_object_name = "ListItemLabelFiltered"
            self.handle_mod_color_reset()
        elif error_tooltip or warning_tooltip:
            new_widget_object_name = "ListItemLabelInvalid"
            self.handle_mod_color_reset()
        else:
            new_widget_object_name = "ListItemLabel"
            self.handle_mod_color_reset()
        if widget_object_name != new_widget_object_name:
            logger.debug("Repolishing: " + new_widget_object_name)
            self.main_label.setObjectName(new_widget_object_name)
            self.main_label.style().unpolish(self.main_label)
            self.main_label.style().polish(self.main_label)

        new_icon_count = self.count_icons(self)
        if new_icon_count != self._last_icon_count:
            self._resize_text_after_icon_toggle(icon_count=new_icon_count)
            self._last_icon_count = new_icon_count

    def handle_mod_color_change(
        self, item: CustomListWidgetItem | None = None, init: bool = False
    ) -> None:
        """Apply background and/or font color to this widget."""
        if not init and item:
            item_data = item.data(Qt.ItemDataRole.UserRole)
            self.mod_color = item_data["mod_color"]
            self.mod_font_color = item_data["mod_font_color"]
        parts: list[str] = []
        if self.mod_color:
            parts.append(f"background: {self.mod_color.name()};")
        if self.mod_font_color:
            parts.append(f"color: {self.mod_font_color.name()};")
        self.setStyleSheet(" ".join(parts))

    def handle_mod_color_reset(self) -> None:
        self.setStyleSheet("")
        self.mod_color = None
        self.mod_font_color = None


class ModListIcons:
    _data_path: Path = AppInfo().theme_data_folder / "default-icons"
    _ludeon_icon_path: str = str(_data_path / "ludeon_icon.png")
    _local_icon_path: str = str(_data_path / "local_icon.png")
    _steam_icon_path: str = str(_data_path / "steam_icon.png")
    _csharp_icon_path: str = str(_data_path / "csharp.png")
    _xml_icon_path: str = str(_data_path / "xml.png")
    _git_icon_path: str = str(_data_path / "git.png")
    _steamcmd_icon_path: str = str(_data_path / "steamcmd_icon.png")
    _warning_icon_path: str = str(_data_path / "warning.png")
    _error_icon_path: str = str(_data_path / "error.png")
    _new_icon_path: str = str(_data_path / "new.png")
    _clear_icon_path: str = str(_data_path / "clear.png")

    _ludeon_icon: QIcon | None = None
    _local_icon: QIcon | None = None
    _steam_icon: QIcon | None = None
    _csharp_icon: QIcon | None = None
    _xml_icon: QIcon | None = None
    _git_icon: QIcon | None = None
    _steamcmd_icon: QIcon | None = None
    _warning_icon: QIcon | None = None
    _error_icon: QIcon | None = None
    _new_icon: QIcon | None = None
    _clear_icon: QIcon | None = None

    @classmethod
    def ludeon_icon(cls) -> QIcon:
        if cls._ludeon_icon is None:
            cls._ludeon_icon = QIcon(cls._ludeon_icon_path)
        return cls._ludeon_icon

    @classmethod
    def local_icon(cls) -> QIcon:
        if cls._local_icon is None:
            cls._local_icon = QIcon(cls._local_icon_path)
        return cls._local_icon

    @classmethod
    def steam_icon(cls) -> QIcon:
        if cls._steam_icon is None:
            cls._steam_icon = QIcon(cls._steam_icon_path)
        return cls._steam_icon

    @classmethod
    def csharp_icon(cls) -> QIcon:
        if cls._csharp_icon is None:
            cls._csharp_icon = QIcon(cls._csharp_icon_path)
        return cls._csharp_icon

    @classmethod
    def xml_icon(cls) -> QIcon:
        if cls._xml_icon is None:
            cls._xml_icon = QIcon(cls._xml_icon_path)
        return cls._xml_icon

    @classmethod
    def git_icon(cls) -> QIcon:
        if cls._git_icon is None:
            cls._git_icon = QIcon(cls._git_icon_path)
        return cls._git_icon

    @classmethod
    def steamcmd_icon(cls) -> QIcon:
        if cls._steamcmd_icon is None:
            cls._steamcmd_icon = QIcon(cls._steamcmd_icon_path)
        return cls._steamcmd_icon

    @classmethod
    def warning_icon(cls) -> QIcon:
        if cls._warning_icon is None:
            cls._warning_icon = QIcon(cls._warning_icon_path)
        return cls._warning_icon

    @classmethod
    def error_icon(cls) -> QIcon:
        if cls._error_icon is None:
            cls._error_icon = QIcon(cls._error_icon_path)
        return cls._error_icon

    @classmethod
    def new_icon(cls) -> QIcon:
        if cls._new_icon is None:
            # Reuse an existing icon if new.png is not present
            cls._new_icon = (
                QIcon(cls._new_icon_path)
                if Path(cls._new_icon_path).exists()
                else QIcon(str(cls._data_path / "AppIcon_b.png"))
            )
        return cls._new_icon

    @classmethod
    def clear_icon(cls) -> QIcon:
        if cls._clear_icon is None:
            cls._clear_icon = (
                QIcon(cls._clear_icon_path)
                if Path(cls._clear_icon_path).exists()
                else QIcon(str(cls._data_path / "AppIcon_b.png"))
            )
        return cls._clear_icon


class ModListWidget(QListWidget):
    """
    Subclass for QListWidget. Used to store lists for
    active and inactive mods. Mods can be rearranged within
    their own lists or moved from one list to another.
    """

    SORT_TEXT_TO_KEY_MAP = {
        "Name": ModsPanelSortKey.MODNAME,
        "Author": ModsPanelSortKey.AUTHOR,
        "Modified Time": ModsPanelSortKey.FILESYSTEM_MODIFIED_TIME,
        "Folder Size": ModsPanelSortKey.FOLDER_SIZE,
        "Version": ModsPanelSortKey.VERSION,
        "PackageId": ModsPanelSortKey.PACKAGEID,
        "Color": ModsPanelSortKey.MOD_COLOR,
    }

    @staticmethod
    def _text_to_sort_key(text: str) -> ModsPanelSortKey:
        return ModListWidget.SORT_TEXT_TO_KEY_MAP.get(text, ModsPanelSortKey.MODNAME)

    edit_rules_signal = Signal(bool, str, str)
    item_added_signal = Signal(str)
    key_press_signal = Signal(str)
    list_update_signal = Signal(str)
    mod_info_signal = Signal(str, CustomListWidgetItem)
    recalculate_warnings_signal = Signal()
    refresh_signal = Signal()
    update_git_mods_signal = Signal(list)
    steamdb_blacklist_signal = Signal(list)

    def __init__(self, list_type: str, settings_controller: SettingsController) -> None:
        """
        Initialize the ListWidget with a dict of mods.
        Keys are the package ids and values are a dict of
        mod attributes. See tags:
        https://rimworldwiki.com/wiki/About.xml
        """
        logger.debug("Initializing ModListWidget")

        # Cache list_type for later use
        self.list_type = list_type

        # Cache MetadataManager instance
        self.metadata_manager = MetadataManager.instance()

        self.settings_controller = settings_controller

        super(ModListWidget, self).__init__()

        # Track when a custom widget (ModListItemInner) is selected/not selected
        self.selectionModel().selectionChanged.connect(self.on_selection_changed)

        # Allow for dragging and dropping between lists
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)

        # Allow for selecting and moving multiple items
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        # When an item is clicked, display the mod information
        self.currentItemChanged.connect(self.mod_changed_to)
        self.itemClicked.connect(self.mod_clicked)

        # When an item is double clicked, move it to the opposite list
        self.itemDoubleClicked.connect(self.mod_double_clicked)

        # Add an eventFilter for per mod_list_item context menu
        self.installEventFilter(self)

        # Disable horizontal scroll bar
        self.horizontalScrollBar().setEnabled(False)
        self.horizontalScrollBar().setVisible(False)

        # Optimizes performance
        # self.setUniformItemSizes(True)

        # Slot to handle item widgets when itemChanged()
        self.itemChanged.connect(self.handle_item_data_changed)

        # Allow inserting custom list items
        self.model().rowsInserted.connect(self.handle_rows_inserted, Qt.ConnectionType.QueuedConnection)

        # Handle removing items to update count
        self.model().rowsAboutToBeRemoved.connect(self.handle_rows_removed, Qt.ConnectionType.QueuedConnection)

        # Lazy load ModListItemInner
        self.verticalScrollBar().valueChanged.connect(self.check_widgets_visible)

        # This set is used to keep track of mods that have been loaded
        # into widgets. Used for an optimization strategy for `handle_rows_inserted`
        self.uuids: list[str] = []
        self.ignore_warning_list: list[str] = []
        # Cache of latest save package ids to check new mods
        self._latest_save_package_ids: set[str] | None = None
        
        # Translation status
        self.show_translation_status: bool = False
        self.translation_lookup: set[str] = set()

        self.deletion_sub_menu = ModDeletionMenu(
            self.settings_controller,
            self._get_selected_metadata,
            self.uuids,
        )  # TODO: should we enable items conditionally? For now use all
        logger.debug("Finished ModListW`idget initialization")

    def on_selection_changed(
        self, selected: QItemSelection, deselected: QItemSelection
    ) -> None:
        """
        Used to indicate when the custom widget is selected/not selected.
        """
        for index in selected.indexes():
            item = self.item(index.row())
            widget = self.itemWidget(item)
            if widget and hasattr(widget, "set_selected"):
                widget.set_selected(True)

        for index in deselected.indexes():
            item = self.item(index.row())
            widget = self.itemWidget(item)
            if widget and hasattr(widget, "set_selected"):
                widget.set_selected(False)

    def item(self, row: int) -> CustomListWidgetItem:
        """
        Return the currently selected item.

        It should always be a CustomListWidgetItem.*
        """
        widget = super().item(row)
        # This fixes mypy linter errors
        # * The only scenario of where the item is QListWidgetItem is in dropEvent, where it's dropped from one list to another.
        # * This is handled in dropEvent directly and it converts this item to CustomListWidgetItem.
        return cast(CustomListWidgetItem, widget)

    def dropEvent(self, event: QDropEvent) -> None:
        super().dropEvent(event)
        # Get source widget of dropEvent
        source_widget = event.source()
        # Get the drop action
        drop_action = event.dropAction()
        # Check if the drop action is MoveAction
        if drop_action == Qt.DropAction.MoveAction:
            # Get the new indexes of the dropped items
            new_indexes = [index.row() for index in self.selectedIndexes()]
            # Get the UUIDs of the dropped items
            uuids = [
                item.data(Qt.ItemDataRole.UserRole)["uuid"]
                for item in self.selectedItems()
            ]
            # Insert the UUIDs at the respective new indexes
            for idx, uuid in zip(new_indexes, uuids):
                if uuid in self.uuids:  # Remove the uuid if it exists in the list
                    self.uuids.remove(uuid)
                # Reinsert uuid at it's new index
                self.uuids.insert(idx, uuid)
        # Re-apply divider collapse states after reorder
        self.apply_collapse_states()
        # Update list signal
        logger.debug(
            f"Emitting {self.list_type} list update signal after rows dropped [{self.count()}]"
        )
        # Only emit "drop" signal if a mod was dragged and dropped within the same modlist
        if source_widget == self:
            self.list_update_signal.emit("drop")

    def _get_selected_metadata(self) -> list[ModMetadata]:
        selected_items = self.selectedItems()
        metadata: list[ModMetadata] = []
        for source_item in selected_items:
            if type(source_item) is CustomListWidgetItem:
                item_data = source_item.data(Qt.ItemDataRole.UserRole)
                if getattr(item_data, "is_divider", False):
                    continue
                metadata.append(
                    self.metadata_manager.internal_local_metadata[item_data["uuid"]]
                )
        return metadata

    def _calculate_translation_similarity(self, mod_name: str, trans_name: str) -> float:
        """
        Calculate similarity score between original mod name and translation mod name.
        
        Uses multiple heuristics:
        1. Direct substring matching (original mod name in translation)
        2. Sequence matching ratio (difflib)
        3. Keyword matching (translation keywords presence)
        
        :param mod_name: Original mod name
        :param trans_name: Translation mod name
        :return: Similarity score between 0.0 and 1.0
        """
        if not mod_name or not trans_name:
            return 0.0
        
        # Normalize names for comparison
        mod_lower = mod_name.lower().strip()
        trans_lower = trans_name.lower().strip()
        
        # Check for common translation keywords
        translation_keywords = [
            "translation", "translate", "中文", "chinese", "简体", "繁體",
            "한국어", "korean", "日本語", "japanese", "русский", "russian",
            "français", "french", "deutsch", "german", "español", "spanish",
            "português", "portuguese", "italiano", "italian", "polski", "polish",
            "türkçe", "turkish", "中文翻译", "汉化", "翻译"
        ]
        
        has_translation_keyword = any(keyword in trans_lower for keyword in translation_keywords)
        
        # Bonus if translation keywords are present
        keyword_bonus = 0.2 if has_translation_keyword else 0.0
        
        # Check if original mod name is a substring of translation name
        if mod_lower in trans_lower:
            substring_score = 0.8
        else:
            # Try removing common prefixes/suffixes and check again
            cleaned_mod = mod_lower.replace("[", "").replace("]", "").replace("(", "").replace(")", "").strip()
            cleaned_trans = trans_lower.replace("[", "").replace("]", "").replace("(", "").replace(")", "").strip()
            
            if cleaned_mod in cleaned_trans:
                substring_score = 0.7
            else:
                # Use sequence matcher for partial matching
                substring_score = SequenceMatcher(None, mod_lower, trans_lower).ratio() * 0.6
        
        # Combine scores
        final_score = min(1.0, substring_score + keyword_bonus)
        
        return final_score

    def _find_and_open_translations(
        self, package_id: str, mod_metadata: dict[str, Any]
    ) -> None:
        """
        Find and open translation mods for the specified mod.
        
        Searches the Steam Workshop metadata database for mods that:
        1. Depend on the target mod OR have the target mod in their loadAfter
        2. Have a "Translation" tag
        3. Match the same game version tag (e.g., "1.6")
        4. Have sufficient name similarity to the original mod
        
        Opens found translation mods in the browser.
        
        :param package_id: The packageId of the mod to find translations for
        :param mod_metadata: The metadata of the mod
        """
        if not self.metadata_manager.external_steam_metadata:
            logger.warning("Steam Workshop metadata database is not loaded")
            show_warning(
                title=self.tr("Database not available"),
                text=self.tr(
                    "Steam Workshop metadata database is not loaded. "
                    "Please build the database first using the Database Builder."
                ),
            )
            return

        # Get the mod's version tags from Steam metadata
        mod_pfid = mod_metadata.get("publishedfileid")
        current_pfid = mod_pfid  # Store for dependency checking
        mod_version_tags = set()
        
        if mod_pfid and mod_pfid in self.metadata_manager.external_steam_metadata:
            steam_data = self.metadata_manager.external_steam_metadata[mod_pfid]
            tags = steam_data.get("tags", [])
            for tag_item in tags:
                tag = tag_item.get("tag", "")
                # Version tags are typically like "1.6", "1.5", etc.
                if tag and tag.replace(".", "").isdigit():
                    mod_version_tags.add(tag)

        logger.info(
            f"Searching for translations of mod with packageId: {package_id}, "
            f"version tags: {mod_version_tags}"
        )

        # Search for translation mods
        translation_mods = []
        
        # Optimized: iterate through Steam metadata only once and extract all needed data
        for pfid, steam_mod_data in self.metadata_manager.external_steam_metadata.items():
            tags = steam_mod_data.get("tags", [])
            if not tags:
                continue
            
            # Build tag set once for faster lookups - O(n) instead of O(n*m)
            tag_set = {tag_item.get("tag", "").lower() for tag_item in tags}
            
            # Fast check: must have "translation" tag
            if "translation" not in tag_set:
                continue
            
            # Extract version tags in a single pass
            translation_version_tags = set()
            for tag_item in tags:
                tag = tag_item.get("tag", "")
                # Cache the string processing result
                if tag and tag.replace(".", "").isdigit():
                    translation_version_tags.add(tag)
            
            # Check if version tags match (if we have version tags)
            if mod_version_tags and translation_version_tags:
                if not mod_version_tags.intersection(translation_version_tags):
                    continue
            
            # Check if this mod has the target mod as a dependency
            # Fast check with 'in' operator on dict instead of .get()
            dependencies = steam_mod_data.get("dependencies", {})
            if current_pfid not in dependencies:
                continue
            
            # Calculate name similarity to filter out false positives
            trans_name = steam_mod_data.get("steamName", "")
            mod_name = mod_metadata.get("name", "")
            
            # Calculate similarity score
            similarity = self._calculate_translation_similarity(mod_name, trans_name)
            
            # Only build the result dict if all checks pass
            translation_mods.append(
                {
                    "pfid": pfid,
                    "name": trans_name or f"Unknown ({pfid})",
                    "url": steam_mod_data.get("url", f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"),
                    "similarity": similarity,
                }
            )

        if not translation_mods:
            logger.info(f"No translations found for mod: {package_id}")
            show_warning(
                title=self.tr("No translations found"),
                text=self.tr(
                    "No translation mods were found for this mod in the Steam Workshop database."
                ),
            )
            return

        # Sort by similarity score (highest first) to show most relevant translations first
        translation_mods.sort(key=lambda x: x["similarity"], reverse=True)
        
        # Filter out translations with very low similarity (likely false positives)
        # Keep at least one result even if similarity is low
        SIMILARITY_THRESHOLD = 0.3
        filtered_mods = [m for m in translation_mods if m["similarity"] >= SIMILARITY_THRESHOLD]
        if not filtered_mods and translation_mods:
            # If all mods filtered out, keep the best match
            filtered_mods = [translation_mods[0]]
        translation_mods = filtered_mods
        
        # Log found translations
        logger.info(
            f"Found {len(translation_mods)} translation(s) for {package_id} "
            f"(filtered by similarity >= {SIMILARITY_THRESHOLD})"
        )
        
        # If only one translation, open it directly
        if len(translation_mods) == 1:
            trans_mod = translation_mods[0]
            logger.info(f"Opening translation: {trans_mod['name']} - {trans_mod['url']}")
            open_url_browser(trans_mod["url"])
            return
        
        # If multiple translations, let user choose
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Select Translation"))
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(400)
        
        layout = QVBoxLayout()
        
        # Add label
        label = QLabel(self.tr(f"Found {len(translation_mods)} translation(s). Select one to open:"))
        layout.addWidget(label)
        
        # Add list widget
        list_widget = QListWidget()
        list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        
        for trans_mod in translation_mods:
            item = QListWidgetItem(trans_mod['name'])
            item.setData(Qt.ItemDataRole.UserRole, trans_mod['url'])
            list_widget.addItem(item)
        
        # Select first item by default
        list_widget.setCurrentRow(0)
        
        # Enable double-click to open
        def on_double_click(item: QListWidgetItem) -> None:
            url = item.data(Qt.ItemDataRole.UserRole)
            logger.info(f"Opening translation: {item.text()} - {url}")
            open_url_browser(url)
            dialog.accept()
        
        list_widget.itemDoubleClicked.connect(on_double_click)
        layout.addWidget(list_widget)
        
        # Add buttons
        button_layout = QHBoxLayout()
        open_button = QPushButton(self.tr("Open"))
        cancel_button = QPushButton(self.tr("Cancel"))
        
        def on_open() -> None:
            current_item = list_widget.currentItem()
            if current_item:
                url = current_item.data(Qt.ItemDataRole.UserRole)
                logger.info(f"Opening translation: {current_item.text()} - {url}")
                open_url_browser(url)
                dialog.accept()
        
        open_button.clicked.connect(on_open)
        cancel_button.clicked.connect(dialog.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(open_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        dialog.exec()

    def eventFilter(self, object: QObject, event: QEvent) -> bool:
        """
        https://doc.qt.io/qtforpython/overviews/eventsandfilters.html

        Takes source object and filters an event at the ListWidget level, executes
        an action based on a per-mod_list_item contextMenu

        :param object: the source object returned from the event
        :param event: the QEvent type
        """
        if event.type() == QEvent.Type.ContextMenu and object is self:
            # Get the position of the right-click event
            pos = QCursor.pos()
            # Convert the global position to the list widget's coordinate system
            pos_local = self.mapFromGlobal(pos)
            # Get the item at the local position
            item = self.itemAt(pos_local)
            if not isinstance(item, CustomListWidgetItem):
                logger.debug("Mod list right-click non-QListWidgetItem")
                return super().eventFilter(object, event)

            # Handle divider-specific context menu
            item_data = item.data(Qt.ItemDataRole.UserRole)
            if getattr(item_data, "is_divider", False):
                return self._show_divider_context_menu(item, item_data, pos_local)

            # Otherwise, begin calculation
            logger.info("USER ACTION: Open right-click mod_list_item contextMenu")

            # GIT MOD PATHS
            # A list of git mod paths to update
            git_paths = []

            # LOCAL MOD CONVERSIONS
            # A dict to track local mod folder name -> publishedfileid
            local_steamcmd_name_to_publishedfileid = {}

            # STEAMCMD MOD PFIDS
            # A set to track any SteamCMD pfids to purge from acf data
            steamcmd_acf_pfid_purge: set[str] = set()
            # A list to track any SteamCMD mod paths
            steamcmd_mod_paths = []
            # A dict to track any SteamCMD mod publishedfileids -> name
            steamcmd_publishedfileid_to_name = {}

            # STEAM SUBSCRIBE/UNSUBSCRIBE
            # A list to track any workshop mod paths
            steam_mod_paths = []
            # A list to track any workshop mod publishedfileids
            steam_publishedfileid_to_name = {}

            # STEAMDB BLACKLIST
            # A list to track any publishedfileids we want to blacklist / remove from blacklist
            steamdb_add_blacklist = None
            steamdb_remove_blacklist = None

            # Define our QMenu & QActions
            context_menu = QMenu()
            # Open folder action
            open_folder_action = None
            # Open folder in text editor action
            open_folder_text_editor_action = None 
            # Open URL in browser action
            open_url_browser_action = None
            # Open URL in Steam
            open_mod_steam_action = None
            # Copy to clipboard actions
            copy_packageid_to_clipboard_action = None
            copy_url_to_clipboard_action = None
            # Edit mod rules
            edit_mod_rules_action = None
            # Toggle warning action
            toggle_warning_action = None
            # Blacklist SteamDB options
            add_to_steamdb_blacklist_action = None
            remove_from_steamdb_blacklist_action = None
            # Convert SteamCMD -> local
            convert_steamcmd_local_action = None
            # Convert local -> SteamCMD
            convert_local_steamcmd_action = None
            # Convert Workshop -> local
            convert_workshop_local_action = None
            # Update/Re-download/re-subscribe git/steamcmd/steam mods
            re_git_action = None
            re_steamcmd_action = None
            re_steam_action = None
            # Unsubscribe mod
            unsubscribe_mod_steam_action = None
            change_mod_color_action = None
            change_mod_font_color_action = None
            reset_mod_colors_action = None
            # Find translation mods
            find_translation_action = None
            # Disable all warnings by default
            all_warnings_toggled = False
            # Get all selected CustomListWidgetItems
            selected_items = self.selectedItems()
            # Track all uuids selected
            all_selected_uuids: Dict[int, str] = {}
            # Single item selected
            if len(selected_items) == 1:
                logger.debug(f"{len(selected_items)} items selected")
                source_item = selected_items[0]
                if type(source_item) is CustomListWidgetItem:
                    item_data = source_item.data(Qt.ItemDataRole.UserRole)
                    uuid = item_data["uuid"]
                    all_selected_uuids[0] = uuid
                    # Retrieve metadata
                    mod_metadata = self.metadata_manager.internal_local_metadata[uuid]
                    mod_data_source = mod_metadata.get("data_source")
                    # Open folder action text
                    open_folder_action = QAction()
                    open_folder_action.setText(self.tr("Open folder"))
                    # Open folder in text editor text
                    if self.settings_controller.settings.text_editor_location:
                        open_folder_text_editor_action = QAction()
                        open_folder_text_editor_action.setText(
                            self.tr("Open folder in text editor")
                        )
                    change_mod_color_action = QAction()
                    change_mod_color_action.setText(self.tr("Change background color"))
                    change_mod_font_color_action = QAction()
                    change_mod_font_color_action.setText(self.tr("Change font color"))
                    reset_mod_colors_action = QAction()
                    reset_mod_colors_action.setText(self.tr("Reset mod colors"))
                    # If we have a "url" or "steam_url"
                    if mod_metadata.get("url") or mod_metadata.get("steam_url"):
                        open_url_browser_action = QAction()
                        open_url_browser_action.setText(self.tr("Open URL in browser"))
                        copy_url_to_clipboard_action = QAction()
                        copy_url_to_clipboard_action.setText(
                            self.tr("Copy URL to clipboard")
                        )
                    # If we have a "steam_uri"
                    if (
                        mod_metadata.get("steam_uri")
                        and self.settings_controller.settings.instances[
                            self.settings_controller.settings.current_instance
                        ].steam_client_integration
                    ):
                        open_mod_steam_action = QAction()
                        open_mod_steam_action.setText(self.tr("Open mod in Steam"))
                    # Conversion options (SteamCMD <-> local) + re-download (local mods found in SteamDB and SteamCMD)
                    if mod_data_source == "local":
                        mod_name = mod_metadata.get("name")
                        mod_folder_name = mod_metadata["folder"]
                        mod_folder_path = mod_metadata["path"]
                        publishedfileid = mod_metadata.get("publishedfileid", "")
                        if not isinstance(publishedfileid, str):
                            logger.error(
                                f"Invalid publishedfileid type: {publishedfileid} for {mod_name}"
                            )
                            publishedfileid = ""

                        if not mod_metadata.get("steamcmd") and (
                            self.metadata_manager.external_steam_metadata
                            and publishedfileid
                            and publishedfileid
                            in self.metadata_manager.external_steam_metadata.keys()
                        ):
                            local_steamcmd_name_to_publishedfileid[mod_folder_name] = (
                                publishedfileid
                            )
                            # Convert local mods -> steamcmd
                            convert_local_steamcmd_action = QAction()
                            convert_local_steamcmd_action.setText(
                                self.tr("Convert local mod to SteamCMD")
                            )
                        if mod_metadata.get("steamcmd"):
                            steamcmd_mod_paths.append(mod_folder_path)
                            steamcmd_publishedfileid_to_name[publishedfileid] = mod_name
                            # Convert steamcmd mods -> local
                            convert_steamcmd_local_action = QAction()
                            convert_steamcmd_local_action.setText(
                                self.tr("Convert SteamCMD mod to local")
                            )
                            # Re-download steamcmd mods
                            re_steamcmd_action = QAction()
                            re_steamcmd_action.setText(
                                self.tr("Re-download mod with SteamCMD")
                            )
                        # Update local mods that contain git repos that are not steamcmd mods
                        if not mod_metadata.get("steamcmd") and mod_metadata.get(
                            "git_repo"
                        ):
                            git_paths.append(mod_folder_path)
                            re_git_action = QAction()
                            re_git_action.setText(self.tr("Update mod with git"))
                    # If Workshop, and pfid, allow Steam actions
                    if mod_data_source == "workshop" and mod_metadata.get(
                        "publishedfileid"
                    ):
                        mod_name = mod_metadata.get("name")
                        mod_folder_path = mod_metadata["path"]
                        publishedfileid = mod_metadata["publishedfileid"]
                        steam_mod_paths.append(mod_folder_path)
                        steam_publishedfileid_to_name[publishedfileid] = mod_name
                        # Convert steam mods -> local
                        convert_workshop_local_action = QAction()
                        convert_workshop_local_action.setText(
                            self.tr("Convert Steam mod to local")
                        )
                        # Only enable subscription actions if user has enabled Steam client integration
                        if self.settings_controller.settings.instances[
                            self.settings_controller.settings.current_instance
                        ].steam_client_integration:
                            # Re-subscribe steam mods
                            re_steam_action = QAction()
                            re_steam_action.setText(
                                self.tr("Re-subscribe mod with Steam")
                            )
                            # Unsubscribe steam mods
                            unsubscribe_mod_steam_action = QAction()
                            unsubscribe_mod_steam_action.setText(
                                self.tr("Unsubscribe mod with Steam")
                            )
                    # SteamDB blacklist options
                    if (
                        self.metadata_manager.external_steam_metadata
                        and mod_metadata.get("publishedfileid")
                    ):
                        publishedfileid = mod_metadata["publishedfileid"]
                        if self.metadata_manager.external_steam_metadata.get(
                            publishedfileid, {}
                        ).get("blacklist"):
                            steamdb_remove_blacklist = publishedfileid
                            remove_from_steamdb_blacklist_action = QAction()
                            remove_from_steamdb_blacklist_action.setText(
                                self.tr("Remove mod from SteamDB blacklist")
                            )
                        else:
                            steamdb_add_blacklist = publishedfileid
                            add_to_steamdb_blacklist_action = QAction()
                            add_to_steamdb_blacklist_action.setText(
                                self.tr("Add mod to SteamDB blacklist")
                            )
                    # Copy packageId to clipboard
                    copy_packageid_to_clipboard_action = QAction()
                    copy_packageid_to_clipboard_action.setText(
                        self.tr("Copy packageId to clipboard")
                    )
                    # Edit mod rules with Rule Editor (only for individual mods)
                    edit_mod_rules_action = QAction()
                    edit_mod_rules_action.setText(self.tr("Edit mod with Rule Editor"))
                    # Ignore error action
                    toggle_warning_action = QAction()
                    toggle_warning_action.setText(self.tr("Toggle warning"))
                    package_id = mod_metadata.get("packageid")
                    if package_id and package_id in self.ignore_warning_list:
                        toggle_warning_action.setCheckable(True)
                        toggle_warning_action.setChecked(True)
                    # Find translation action (only for single mod selection)
                    if package_id:
                        find_translation_action = QAction()
                        find_translation_action.setText(self.tr("Find translations"))
            # Multiple items selected
            elif len(selected_items) > 1:  # Multiple items selected
                all_warnings_toggled = True
                for item_idx, source_item in enumerate(selected_items):
                    if type(source_item) is CustomListWidgetItem:
                        item_data = source_item.data(Qt.ItemDataRole.UserRole)
                        if getattr(item_data, "is_divider", False):
                            continue
                        uuid = item_data["uuid"]
                        all_selected_uuids[item_idx] = uuid
                        # Retrieve metadata
                        mod_metadata = self.metadata_manager.internal_local_metadata[
                            uuid
                        ]
                        if all_warnings_toggled:
                            package_id = mod_metadata.get("packageid")
                            if (
                                package_id
                                and package_id not in self.ignore_warning_list
                            ):
                                all_warnings_toggled = False
                        mod_data_source = mod_metadata.get("data_source")
                        # Open folder action text
                        open_folder_action = QAction()
                        open_folder_action.setText(self.tr("Open folder(s)"))
                        if self.settings_controller.settings.text_editor_location:
                            open_folder_text_editor_action = QAction()
                            open_folder_text_editor_action.setText(
                                self.tr("Open folder(s) in text editor")
                            )
                        change_mod_color_action = QAction()
                        change_mod_color_action.setText("Change background colors")
                        change_mod_font_color_action = QAction()
                        change_mod_font_color_action.setText("Change font colors")
                        reset_mod_colors_action = QAction()
                        reset_mod_colors_action.setText("Reset mod colors")
                        # If we have a "url" or "steam_url"
                        if mod_metadata.get("url") or mod_metadata.get("steam_url"):
                            open_url_browser_action = QAction()
                            open_url_browser_action.setText(
                                self.tr("Open URL(s) in browser")
                            )
                        # Conversion options (local <-> SteamCMD)
                        if mod_data_source == "local":
                            mod_name = mod_metadata.get("name")
                            mod_folder_name = mod_metadata["folder"]
                            mod_folder_path = mod_metadata["path"]
                            publishedfileid = mod_metadata.get("publishedfileid")
                            if not mod_metadata.get("steamcmd") and (
                                self.metadata_manager.external_steam_metadata
                                and publishedfileid
                                and publishedfileid
                                in self.metadata_manager.external_steam_metadata.keys()
                            ):
                                local_steamcmd_name_to_publishedfileid[
                                    mod_folder_name
                                ] = publishedfileid
                                # Convert local mods -> steamcmd
                                if not convert_local_steamcmd_action:
                                    convert_local_steamcmd_action = QAction()
                                    convert_local_steamcmd_action.setText(
                                        self.tr("Convert local mod(s) to SteamCMD")
                                    )
                            if mod_metadata.get("steamcmd"):
                                steamcmd_mod_paths.append(mod_folder_path)
                                steamcmd_publishedfileid_to_name[publishedfileid] = (
                                    mod_name
                                )
                                # Convert steamcmd mods -> local
                                if not convert_steamcmd_local_action:
                                    convert_steamcmd_local_action = QAction()
                                    convert_steamcmd_local_action.setText(
                                        self.tr("Convert SteamCMD mod(s) to local")
                                    )
                                # Re-download steamcmd mods
                                if not re_steamcmd_action:
                                    re_steamcmd_action = QAction()
                                    re_steamcmd_action.setText(
                                        self.tr("Re-download mod(s) with SteamCMD")
                                    )
                            # Update git mods if local mod with git repo, but not steamcmd
                            if not mod_metadata.get("steamcmd") and mod_metadata.get(
                                "git_repo"
                            ):
                                git_paths.append(mod_folder_path)
                                if not re_git_action:
                                    re_git_action = QAction()
                                    re_git_action.setText(
                                        self.tr("Update mod(s) with git")
                                    )
                        # No "Edit mod rules" when multiple selected
                        # Toggle warning
                        if item_idx == len(selected_items) - 1:
                            toggle_warning_action = QAction()
                            toggle_warning_action.setText(self.tr("Toggle warning(s)"))
                            toggle_warning_action.setCheckable(True)
                            toggle_warning_action.setChecked(all_warnings_toggled)
                        # If Workshop, and pfid, allow Steam actions
                        if mod_data_source == "workshop" and mod_metadata.get(
                            "publishedfileid"
                        ):
                            mod_name = mod_metadata.get("name")
                            mod_folder_path = mod_metadata["path"]
                            publishedfileid = mod_metadata["publishedfileid"]
                            steam_mod_paths.append(mod_folder_path)
                            steam_publishedfileid_to_name[publishedfileid] = mod_name
                            # Convert steam mods -> local
                            if not convert_workshop_local_action:
                                convert_workshop_local_action = QAction()
                                convert_workshop_local_action.setText(
                                    self.tr("Convert Steam mod(s) to local")
                                )
                            # Only enable subscription actions if user has enabled Steam client integration
                            if self.settings_controller.settings.instances[
                                self.settings_controller.settings.current_instance
                            ].steam_client_integration:
                                # Re-subscribe steam mods
                                if not re_steam_action:
                                    re_steam_action = QAction()
                                    re_steam_action.setText(
                                        self.tr("Re-subscribe mod(s) with Steam")
                                    )
                                # Unsubscribe steam mods
                                if not unsubscribe_mod_steam_action:
                                    unsubscribe_mod_steam_action = QAction()
                                    unsubscribe_mod_steam_action.setText(
                                        self.tr("Unsubscribe mod(s) with Steam")
                                    )
                        # No SteamDB blacklist options when multiple selected
            # Put together our contextMenu
            if open_folder_action:
                context_menu.addAction(open_folder_action)
            if open_folder_text_editor_action:
                context_menu.addAction(open_folder_text_editor_action)
            if change_mod_color_action:
                context_menu.addAction(change_mod_color_action)
            if change_mod_font_color_action:
                context_menu.addAction(change_mod_font_color_action)
            if reset_mod_colors_action:
                context_menu.addAction(reset_mod_colors_action)
            if open_url_browser_action:
                context_menu.addAction(open_url_browser_action)
            if open_mod_steam_action:
                context_menu.addAction(open_mod_steam_action)
            if find_translation_action:
                context_menu.addAction(find_translation_action)
            if toggle_warning_action:
                context_menu.addAction(toggle_warning_action)

            context_menu.addMenu(self.deletion_sub_menu)
            context_menu.addSeparator()
            if (
                copy_packageid_to_clipboard_action
                or copy_url_to_clipboard_action
                or edit_mod_rules_action
                or re_git_action
            ):
                misc_options_menu = QMenu(title=self.tr("Miscellaneous options"))
                if copy_packageid_to_clipboard_action:
                    clipboard_options_menu = QMenu(title=self.tr("Clipboard options"))
                    clipboard_options_menu.addAction(copy_packageid_to_clipboard_action)
                    if copy_url_to_clipboard_action:
                        clipboard_options_menu.addAction(copy_url_to_clipboard_action)
                    misc_options_menu.addMenu(clipboard_options_menu)
                if edit_mod_rules_action:
                    misc_options_menu.addAction(edit_mod_rules_action)
                if re_git_action:
                    misc_options_menu.addAction(re_git_action)
                context_menu.addMenu(misc_options_menu)
            if (
                convert_local_steamcmd_action
                or convert_steamcmd_local_action
                or convert_workshop_local_action
                or re_steamcmd_action
                or re_steam_action
                or unsubscribe_mod_steam_action
                or add_to_steamdb_blacklist_action
                or remove_from_steamdb_blacklist_action
            ):
                local_folder = self.settings_controller.settings.instances[
                    self.settings_controller.settings.current_instance
                ].local_folder
                workshop_actions_menu = QMenu(title=self.tr("Workshop mods options"))
                if local_folder and convert_local_steamcmd_action:
                    workshop_actions_menu.addAction(convert_local_steamcmd_action)
                if local_folder and convert_steamcmd_local_action:
                    workshop_actions_menu.addAction(convert_steamcmd_local_action)
                if local_folder and convert_workshop_local_action:
                    workshop_actions_menu.addAction(convert_workshop_local_action)
                if re_steamcmd_action:
                    workshop_actions_menu.addAction(re_steamcmd_action)
                if re_steam_action:
                    workshop_actions_menu.addAction(re_steam_action)
                if unsubscribe_mod_steam_action:
                    workshop_actions_menu.addAction(unsubscribe_mod_steam_action)
                if (
                    add_to_steamdb_blacklist_action
                    or remove_from_steamdb_blacklist_action
                ):
                    workshop_actions_menu.addSeparator()
                if add_to_steamdb_blacklist_action:
                    workshop_actions_menu.addAction(add_to_steamdb_blacklist_action)
                if remove_from_steamdb_blacklist_action:
                    workshop_actions_menu.addAction(
                        remove_from_steamdb_blacklist_action
                    )
                context_menu.addMenu(workshop_actions_menu)
            # Divider option (active list only)
            add_divider_action = None
            if self.list_type == "Active":
                context_menu.addSeparator()
                add_divider_action = QAction()
                add_divider_action.setText(self.tr("Add divider here"))
                context_menu.addAction(add_divider_action)
            # Execute QMenu and return it's ACTION
            action = context_menu.exec_(self.mapToGlobal(pos_local))
            if action:  # Handle the action for all selected items
                if action == add_divider_action:
                    row = self.row(item)
                    name, ok = QInputDialog.getText(
                        self,
                        self.tr("Add Divider"),
                        self.tr("Divider name:"),
                    )
                    if ok and name.strip():
                        self.add_divider(row, name.strip())
                    return True
                if (  # ACTION: Update git mod(s)
                    action == re_git_action and len(git_paths) > 0
                ):
                    # Prompt user
                    answer = show_dialogue_conditional(
                        title=self.tr("Are you sure?"),
                        text=self.tr(
                            "You have selected {len} git mods to be updated."
                        ).format(len=len(git_paths)),
                        information=self.tr("Do you want to proceed?"),
                    )
                    if answer == QMessageBox.StandardButton.Yes:
                        logger.debug(f"Updating {len(git_paths)} git mod(s)")
                        self.update_git_mods_signal.emit(git_paths)
                    return True
                elif (  # ACTION: Convert local mod(s) -> SteamCMD
                    action == convert_local_steamcmd_action
                    and len(local_steamcmd_name_to_publishedfileid) > 0
                ):
                    local_folder = self.settings_controller.settings.instances[
                        self.settings_controller.settings.current_instance
                    ].local_folder
                    for (
                        folder_name,
                        publishedfileid,
                    ) in local_steamcmd_name_to_publishedfileid.items():
                        original_mod_path = str((Path(local_folder) / folder_name))
                        renamed_mod_path = str((Path(local_folder) / publishedfileid))
                        if os.path.exists(original_mod_path):
                            if not os.path.exists(renamed_mod_path):
                                try:
                                    os.rename(original_mod_path, renamed_mod_path)
                                    logger.debug(
                                        f'Successfully "converted" local mod -> SteamCMD by renaming from {folder_name} -> {publishedfileid}'
                                    )
                                except Exception as e:
                                    stacktrace = format_exc()
                                    logger.error(
                                        f"Failed to convert mod: {original_mod_path} - {e}"
                                    )
                                    logger.error(stacktrace)
                            else:
                                logger.warning(
                                    f"Failed to convert mod! Destination already exists: {renamed_mod_path}"
                                )
                    self.refresh_signal.emit()
                    return True
                elif (  # ACTION: Convert SteamCMD mod(s) -> local
                    action == convert_steamcmd_local_action
                    and len(steamcmd_publishedfileid_to_name) > 0
                ):
                    local_folder = self.settings_controller.settings.instances[
                        self.settings_controller.settings.current_instance
                    ].local_folder
                    for (
                        publishedfileid,
                        mod_name,
                    ) in steamcmd_publishedfileid_to_name.items():
                        mod_name = (
                            sanitize_filename(mod_name)
                            if mod_name
                            else f"{publishedfileid}_local"
                        )
                        original_mod_path = str((Path(local_folder) / publishedfileid))
                        renamed_mod_path = str((Path(local_folder) / mod_name))
                        if os.path.exists(original_mod_path):
                            if not os.path.exists(renamed_mod_path):
                                try:
                                    os.rename(original_mod_path, renamed_mod_path)
                                    logger.debug(
                                        f'Successfully "converted" SteamCMD mod by renaming from {publishedfileid} -> {mod_name}'
                                    )
                                except Exception as e:
                                    stacktrace = format_exc()
                                    logger.error(
                                        f"Failed to convert mod: {original_mod_path} - {e}"
                                    )
                                    logger.error(stacktrace)
                            else:
                                logger.warning(
                                    f"Failed to convert mod! Destination already exists: {renamed_mod_path}"
                                )
                    self.refresh_signal.emit()
                    return True
                elif (  # ACTION: Re-download SteamCMD mod(s)
                    action == re_steamcmd_action
                    and len(steamcmd_publishedfileid_to_name.keys()) > 0
                ):
                    logger.debug(
                        f"Selected mods for deleting + redownloading: {steamcmd_publishedfileid_to_name}"
                    )
                    steamcmd_publishedfileid_to_redownload = (
                        steamcmd_publishedfileid_to_name.keys()
                    )
                    logger.debug(
                        f"Selected publishedfileid for deleting + redownloading: {steamcmd_publishedfileid_to_redownload}"
                    )
                    # Prompt user
                    answer = show_dialogue_conditional(
                        title=self.tr("Are you sure?"),
                        text=self.tr(
                            "You have selected {len} mods for deletion + re-download."
                        ).format(len=len(steamcmd_publishedfileid_to_redownload)),
                        information=self.tr(
                            "\nThis operation will recursively delete all mod files, except for .dds textures found, "
                            + "and attempt to re-download the mods via SteamCMD. Do you want to proceed?"
                        ),
                    )
                    if answer == QMessageBox.StandardButton.Yes:
                        logger.debug(
                            f"Deleting + redownloading {len(steamcmd_publishedfileid_to_redownload)} SteamCMD mod(s)"
                        )
                        for path in steamcmd_mod_paths:
                            # Delete all files except .dds
                            delete_files_except_extension(
                                directory=path, extension=".dds"
                            )
                            # Calculate SteamCMD mod publishedfileids to purge from acf metadata
                            steamcmd_acf_pfid_purge = set(
                                steamcmd_publishedfileid_to_redownload
                            )
                        # Purge any deleted SteamCMD mods from acf metadata (only if auto-clear depot cache is enabled)
                        if steamcmd_acf_pfid_purge:
                            steamcmd_purge_mods(
                                metadata_manager=self.metadata_manager,
                                publishedfileids=steamcmd_acf_pfid_purge,
                                auto_clear_enabled=self.settings_controller.settings.instances[
                                    self.settings_controller.settings.current_instance
                                ].steamcmd_auto_clear_depot_cache,
                            )
                        # Emit signal to steamcmd downloader to re-download
                        logger.debug(
                            f"Emitting do_steamcmd_download for {list(steamcmd_publishedfileid_to_redownload)}"
                        )
                        EventBus().do_steamcmd_download.emit(
                            list(steamcmd_publishedfileid_to_redownload)
                        )
                    return True
                elif (  # ACTION: Convert Steam mod(s) -> local
                    action == convert_workshop_local_action
                    and len(steam_mod_paths) > 0
                    and len(steam_publishedfileid_to_name) > 0
                ):
                    for path in steam_mod_paths:
                        publishedfileid_from_folder_name = os.path.split(path)[1]
                        mod_name = steam_publishedfileid_to_name.get(
                            publishedfileid_from_folder_name
                        )
                        if mod_name:
                            mod_name = sanitize_filename(mod_name)
                        renamed_mod_path = str(
                            (
                                Path(
                                    self.settings_controller.settings.instances[
                                        self.settings_controller.settings.current_instance
                                    ].local_folder
                                )
                                / (
                                    mod_name
                                    if mod_name
                                    else publishedfileid_from_folder_name
                                )
                            )
                        )
                        if os.path.exists(path):
                            try:
                                if os.path.exists(renamed_mod_path):
                                    logger.warning(
                                        "Destination exists. Removing all files except for .dds textures first..."
                                    )
                                    delete_files_except_extension(
                                        directory=renamed_mod_path, extension=".dds"
                                    )
                                try:
                                    copytree(path, renamed_mod_path)
                                except FileExistsError:
                                    for root, dirs, files in os.walk(path):
                                        dest_dir = root.replace(path, renamed_mod_path)
                                        if not os.path.isdir(dest_dir):
                                            os.makedirs(dest_dir)
                                        for file in files:
                                            src_file = os.path.join(root, file)
                                            dst_file = os.path.join(dest_dir, file)
                                            copy2(src_file, dst_file)
                                logger.debug(
                                    f'Successfully "converted" Steam mod by copying {publishedfileid_from_folder_name} -> {mod_name} and migrating mod to local mods directory'
                                )
                            except Exception as e:
                                stacktrace = format_exc()
                                logger.error(f"Failed to convert mod: {path} - {e}")
                                logger.error(stacktrace)
                    self.refresh_signal.emit()
                    return True
                elif (  # ACTION: Re-subscribe to mod(s) with Steam
                    action == re_steam_action and len(steam_publishedfileid_to_name) > 0
                ):
                    publishedfileids = steam_publishedfileid_to_name.keys()
                    # Prompt user
                    answer = show_dialogue_conditional(
                        title=self.tr("Are you sure?"),
                        text=self.tr(
                            "You have selected {len} mods for resubscribe:(unsubscribe + subscribe)."
                        ).format(len=len(publishedfileids)),
                        information=self.tr(
                            "\nThis operation will potentially delete .dds textures leftover. Steam is unreliable for this. Do you want to proceed?"
                        ),
                    )
                    if answer == QMessageBox.StandardButton.Yes:
                        logger.warning(
                            f"re-subscribing: (Unsubscribing + subscribing) to {len(publishedfileids)} mod(s)"
                        )
                        for path in steam_mod_paths:
                            delete_files_except_extension(
                                directory=path, extension=".dds"
                            )
                        EventBus().do_steamworks_api_call.emit(
                            [
                                "resubscribe",
                                [eval(str_pfid) for str_pfid in publishedfileids],
                            ]
                        )
                    return True
                elif (  # ACTION: Unsubscribe mod(s) with steam
                    action == unsubscribe_mod_steam_action
                    and len(steam_publishedfileid_to_name) > 0
                ):
                    publishedfileids = steam_publishedfileid_to_name.keys()
                    # Prompt user
                    answer = show_dialogue_conditional(
                        title=self.tr("Are you sure?"),
                        text=self.tr(
                            "You have selected {len} mods for unsubscribe."
                        ).format(len=len(publishedfileids)),
                        information=self.tr("\nDo you want to proceed?"),
                    )
                    if answer == QMessageBox.StandardButton.Yes:
                        logger.debug(
                            f"Unsubscribing from {len(publishedfileids)} mod(s)"
                        )
                        EventBus().do_steamworks_api_call.emit(
                            [
                                "unsubscribe",
                                [eval(str_pfid) for str_pfid in publishedfileids],
                            ]
                        )
                    return True
                elif (
                    action == add_to_steamdb_blacklist_action
                ):  # ACTION: Blacklist workshop mod in SteamDB
                    if (
                        self.metadata_manager.external_steam_metadata is None
                        or steamdb_add_blacklist is None
                    ):
                        logger.error(
                            f"Unable to add mod to SteamDB blacklist: {steamdb_remove_blacklist}"
                        )
                        show_warning(
                            "Warning",
                            "Unable to add mod to SteamDB blacklist",
                            "Metadata manager or steamdb_add_blacklist was None type",
                            parent=self,
                        )
                        return False

                    args, ok = QInputDialog.getText(
                        self,
                        self.tr("Add comment"),
                        self.tr(
                            "Enter a comment providing your reasoning for wanting to blacklist this mod: "
                        )
                        + f"{self.metadata_manager.external_steam_metadata.get(steamdb_add_blacklist, {}).get('steamName', steamdb_add_blacklist)}",
                    )
                    if ok:
                        self.steamdb_blacklist_signal.emit(
                            [steamdb_add_blacklist, True, args]
                        )
                    else:
                        show_warning(
                            title=self.tr("Unable to add to blacklist"),
                            text=self.tr(
                                "Comment was not provided or entry was cancelled. Comments are REQUIRED for this action!"
                            ),
                        )
                    return True
                elif (
                    action == remove_from_steamdb_blacklist_action
                ):  # ACTION: Blacklist workshop mod in SteamDB
                    if (
                        self.metadata_manager.external_steam_metadata is None
                        or steamdb_remove_blacklist is None
                    ):
                        logger.error(
                            f"Unable to remove mod from SteamDB blacklist: {steamdb_remove_blacklist}"
                        )
                        show_warning(
                            "Warning",
                            "Unable to remove mod from SteamDB blacklist",
                            "Metadata manager or steamdb_remove_blacklist was None type",
                            parent=self,
                        )
                        return False

                    answer = show_dialogue_conditional(
                        title=self.tr("Are you sure?"),
                        text=self.tr("This will remove the selected mod, ")
                        + f"{self.metadata_manager.external_steam_metadata.get(steamdb_remove_blacklist, {}).get('steamName', steamdb_remove_blacklist)}, "
                        + "from your configured Steam DB blacklist."
                        + "\nDo you want to proceed?",
                    )
                    if answer == QMessageBox.StandardButton.Yes:
                        self.steamdb_blacklist_signal.emit(
                            [steamdb_remove_blacklist, False]
                        )
                    return True
                # If user is changing mod color, display color picker once no matter how many mods are selected
                invalid_color = True
                new_color = QColor()
                if action == change_mod_color_action:
                    color_dlg = QColorDialog(
                        options=QColorDialog.ColorDialogOption.DontUseNativeDialog
                    )
                    self.SetUserCustomColors(color_dlg)
                    new_color = color_dlg.getColor()
                    self.SaveUserCustomColors(color_dlg)
                    invalid_color = not new_color.isValid()
                invalid_font_color = True
                new_font_color = QColor()
                if action == change_mod_font_color_action:
                    color_dlg = QColorDialog(
                        options=QColorDialog.ColorDialogOption.DontUseNativeDialog
                    )
                    self.SetUserCustomColors(color_dlg)
                    new_font_color = color_dlg.getColor()
                    self.SaveUserCustomColors(color_dlg)
                    invalid_font_color = not new_font_color.isValid()
                if action in self.deletion_sub_menu.actions():
                    # Deletion menu handles whatever action it was, exit now
                    return True
                # Execute action for each selected mod
                for item_idx, source_item in enumerate(selected_items):
                    if type(source_item) is CustomListWidgetItem:
                        item_data = source_item.data(Qt.ItemDataRole.UserRole)
                        if getattr(item_data, "is_divider", False):
                            continue
                        uuid = all_selected_uuids[item_idx]
                        # Retrieve metadata
                        mod_metadata = self.metadata_manager.internal_local_metadata[
                            uuid
                        ]
                        mod_data_source = mod_metadata.get("data_source")
                        mod_path = mod_metadata["path"]
                        # Toggle warning action
                        if action == toggle_warning_action:
                            if len(selected_items) > 1:
                                # If toggling multiple items, if all of them are already toggled off then toggle back on.
                                # Otherwise if they are all off or a mix, toggled them all on.
                                if all_warnings_toggled:
                                    self.toggle_warning(mod_metadata["packageid"], uuid)
                                else:
                                    if not item_data["warning_toggled"]:
                                        self.toggle_warning(
                                            mod_metadata["packageid"], uuid
                                        )
                            else:
                                self.toggle_warning(mod_metadata["packageid"], uuid)
                        elif action == change_mod_color_action and not invalid_color:
                            if len(selected_items) > 1 and item_idx == len(selected_items) - 1:
                                self.change_all_mod_colors(list(all_selected_uuids.values()), new_color)
                            elif len(selected_items) == 1:
                                self.change_mod_color(uuid, new_color)
                        elif action == change_mod_font_color_action and not invalid_font_color:
                            if len(selected_items) > 1 and item_idx == len(selected_items) - 1:
                                self.change_all_mod_font_colors(list(all_selected_uuids.values()), new_font_color)
                            elif len(selected_items) == 1:
                                self.change_mod_font_color(uuid, new_font_color)
                        elif action == reset_mod_colors_action:
                            if len(selected_items) > 1 and item_idx == len(selected_items) - 1:
                                all_uuids = list(all_selected_uuids.values())
                                self.reset_all_mod_colors(all_uuids)
                                self.reset_all_mod_font_colors(all_uuids)
                            elif len(selected_items) == 1:
                                self.reset_mod_color(uuid)
                                self.reset_mod_font_color(uuid)
                        elif action == open_folder_action:  # ACTION: Open folder
                            if os.path.exists(mod_path):  # If the path actually exists
                                logger.info(f"Opening folder: {mod_path}")
                                platform_specific_open(mod_path)
                        elif (
                            action == open_folder_text_editor_action
                        ):  # ACTION: Open folder in text editor
                            if os.path.exists(mod_path):
                                logger.info(
                                    f"Opening folder in text editor: {mod_path}"
                                )
                                launch_process(
                                    self.settings_controller.settings.text_editor_location,
                                    self.settings_controller.settings.text_editor_folder_arg.split(
                                        " "
                                    )
                                    + [mod_path],
                                    str(AppInfo().application_folder),
                                )

                        # Open url action
                        elif (
                            action == open_url_browser_action
                        ):  # ACTION: Open URL in browser
                            if mod_metadata.get("url") or mod_metadata.get(
                                "steam_url"
                            ):  # If we have some form of "url" to work with...
                                url = None
                                if (
                                    mod_data_source == "expansion"
                                    or mod_metadata.get("steamcmd")
                                    or mod_data_source == "workshop"
                                ):
                                    url = mod_metadata.get(
                                        "steam_url", mod_metadata.get("url")
                                    )
                                elif (
                                    mod_data_source == "local"
                                    and not mod_metadata.get("steamcmd")
                                ):
                                    url = mod_metadata.get(
                                        "url", mod_metadata.get("steam_url")
                                    )
                                if url:
                                    logger.info(f"Opening url in browser: {url}")
                                    open_url_browser(url)
                        # Open Steam URI with Steam action
                        elif (
                            action == open_mod_steam_action
                        ):  # ACTION: Open steam:// uri in Steam
                            if mod_metadata.get("steam_uri"):  # If we have steam_uri
                                platform_specific_open(mod_metadata["steam_uri"])
                        # Find translation mods action
                        elif (
                            action == find_translation_action
                        ):  # ACTION: Find translation mods
                            package_id = mod_metadata.get("packageid")
                            if package_id:
                                self._find_and_open_translations(package_id, mod_metadata)
                        # Copy to clipboard actions
                        elif (
                            action == copy_packageid_to_clipboard_action
                        ):  # ACTION: Copy packageId to clipboard
                            copy_to_clipboard_safely(mod_metadata["packageid"])
                        elif (
                            action == copy_url_to_clipboard_action
                        ):  # ACTION: Copy URL to clipboard
                            if mod_metadata.get("url") or mod_metadata.get(
                                "steam_url"
                            ):  # If we have some form of "url" to work with...
                                url = None
                                if (
                                    mod_data_source == "expansion"
                                    or mod_metadata.get("steamcmd")
                                    or mod_data_source == "workshop"
                                ):
                                    url = mod_metadata.get(
                                        "steam_url", mod_metadata.get("url")
                                    )
                                elif (
                                    mod_data_source == "local"
                                    and not mod_metadata.get("steamcmd")
                                ):
                                    url = mod_metadata.get(
                                        "url", mod_metadata.get("steam_url")
                                    )
                                if url:
                                    copy_to_clipboard_safely(url)
                        # Edit mod rules action
                        elif action == edit_mod_rules_action:
                            self.edit_rules_signal.emit(
                                True, "user_rules", mod_metadata["packageid"]
                            )
            return True
        return super().eventFilter(object, event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        """
        Slot to handle unhighlighting any items in the
        previous list when clicking out of that list.
        """
        self.clearFocus()
        return super().focusOutEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """
        This event occurs when the user presses a key while the mod
        list is in focus.
        """
        if (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and event.key() == Qt.Key.Key_Return
        ):
            self.key_press_signal.emit("Ctrl+Return")
        else:
            key_pressed = QKeySequence(event.key()).toString()
            if (
                key_pressed == "Left"
                or key_pressed == "Right"
                or key_pressed == "Return"
                or key_pressed == "Space"
            ):
                self.key_press_signal.emit(key_pressed)
            else:
                return super().keyPressEvent(event)

    def resizeEvent(self, e: QResizeEvent) -> None:
        """
        When the list widget is resized (as the window is resized),
        ensure that all visible items have widgets loaded.

        :param event: the resize event
        """
        self.check_widgets_visible()
        return super().resizeEvent(e)

    def SetUserCustomColors(self, color_dlg: QColorDialog) -> None:
        """
        Sets the user's custom colors in the QColorDialog from settings.json.
        """
        settings = self.settings_controller.settings
        colors = settings.color_picker_custom_colors
        if len(colors) != 16:
            return
        for i in range(16):
            color_dlg.setCustomColor(i, colors[i])

    def SaveUserCustomColors(self, color_dlg: QColorDialog) -> None:
        """
        Saves the user's custom colors from the QColorDialog to settings.json as list of hex strings.
        """
        settings = self.settings_controller.settings
        colors = []
        for i in range(16):
            color = color_dlg.customColor(i)
            colors.append(color.name())  # Store as hex string
        settings.color_picker_custom_colors = colors
        settings.save()

    def append_new_item(self, uuid: str) -> None:
        mod_path = self.metadata_manager.internal_local_metadata[uuid]["path"]
        aux_metadata_controller = AuxMetadataController.get_or_create_cached_instance(
            self.settings_controller.settings.aux_db_path
        )
        with aux_metadata_controller.Session() as aux_metadata_session:
            aux_metadata_controller.get_or_create(aux_metadata_session, mod_path)
            aux_metadata_controller.update(
                aux_metadata_session, mod_path, outdated=False
            )
            data = CustomListWidgetItemMetadata(
                uuid=uuid,
                list_type=self.list_type,
                aux_metadata_controller=aux_metadata_controller,
                aux_metadata_session=aux_metadata_session,
                settings_controller=self.settings_controller,
            )
        item = CustomListWidgetItem(self)
        item.setData(Qt.ItemDataRole.UserRole, data)
        self.addItem(item)
        self.uuids.append(uuid)  # Append for new item

    def get_all_mod_list_items(self) -> list[CustomListWidgetItem]:
        """
        This gets all modlist items (excludes dividers).

        :return: List of all modlist items as CustomListWidgetItem
        """
        mod_list_items = []
        for index in range(self.count()):
            item = self.item(index)
            data = item.data(Qt.ItemDataRole.UserRole)
            if getattr(data, "is_divider", False):
                continue
            mod_list_items.append(item)
        return mod_list_items

    def get_all_loaded_mod_list_items(self) -> list[ModListItemInner]:
        """
        This gets all modlist items as ModListItemInner.
        Mods that have not been loaded or lazy loaded will not be returned.

        :return: List of all modlist items as ModListItemInner
        """
        mod_list_items = []
        for index in range(self.count()):
            item = self.item(index)
            widget = self.itemWidget(item)
            if isinstance(widget, ModListItemInner):
                mod_list_items.append(widget)
        return mod_list_items

    def get_all_toggled_mod_list_items(self) -> list[CustomListWidgetItem]:
        """
        This returns all modlist items that have their warnings toggled.

        :return: List of all toggled modlist items as CustomListWidgetItem
        """
        mod_list_items = []
        for index in range(self.count()):
            item = self.item(index)
            item_data = item.data(Qt.ItemDataRole.UserRole)
            if getattr(item_data, "is_divider", False):
                continue
            if item_data["warning_toggled"]:
                mod_list_items.append(item)
        return mod_list_items

    def get_all_loaded_and_toggled_mod_list_items(self) -> list[ModListItemInner]:
        """
        This returns all modlist items that have their warnings toggled.
        Mods that have not been loaded or lazy loaded will not be returned.

        :return: List of all toggled modlist items as ModListItemInner
        """
        mod_list_items = []
        for index in range(self.count()):
            item = self.item(index)
            item_data = item.data(Qt.ItemDataRole.UserRole)
            if getattr(item_data, "is_divider", False):
                continue
            if item_data["warning_toggled"]:
                widget = self.itemWidget(item)
                if isinstance(widget, ModListItemInner):
                    mod_list_items.append(widget)
        return mod_list_items

    def check_item_visible(self, item: CustomListWidgetItem) -> bool:
        # Determines if the item is currently visible in the viewport.
        rect = self.visualItemRect(item)
        return rect.top() < self.viewport().height() and rect.bottom() > 0

    def create_widget_for_item(self, item: CustomListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is None:
            logger.debug("Attempted to create widget for item with None data")
            return

        if getattr(data, "is_divider", False):
            widget = DividerItemInner(
                uuid=data.uuid, name=data.name, collapsed=data.collapsed
            )
            widget.toggle_signal.connect(self.toggle_divider_collapse)
            item.setSizeHint(widget.sizeHint())
            self.setItemWidget(item, widget)
            self._update_single_divider_mod_count(item)
            return

        errors_warnings = data["errors_warnings"]
        errors = data["errors"]
        warnings = data["warnings"]
        filtered = data["filtered"]
        invalid = data["invalid"]
        mismatch = data["mismatch"]
        alternative = data["alternative"]
        uuid = data["uuid"]
        mod_color = data["mod_color"]
        mod_font_color = data["mod_font_color"]
        if uuid:
            widget = ModListItemInner(
                errors_warnings=errors_warnings,
                errors=errors,
                warnings=warnings,
                filtered=filtered,
                invalid=invalid,
                mismatch=mismatch,
                alternative=alternative,
                settings_controller=self.settings_controller,
                uuid=uuid,
                mod_color=mod_color,
                mod_font_color=mod_font_color,
            )
            widget.toggle_warning_signal.connect(self.toggle_warning)
            widget.toggle_error_signal.connect(self.toggle_warning)
            item.setSizeHint(widget.sizeHint())
            self.setItemWidget(item, widget)
            
            # Apply translation status if enabled
            if self.show_translation_status:
                pkg_id = self.metadata_manager.internal_local_metadata[uuid].get("packageid")
                has_translation = pkg_id in self.translation_lookup
                widget.update_translation_status(has_translation)

            # Ensure initial icon states reflect current item data
            widget.repolish(item)

    def check_widgets_visible(self) -> None:
        # This function checks the visibility of each item and creates a widget if the item is visible and not already setup.
        indexes = self.get_visible_indexes()
        for idx in indexes:
            item = self.item(idx)
            # Check for visible item without a widget set
            if item and self.itemWidget(item) is None:
                self.create_widget_for_item(item)

    def get_visible_indexes(self) -> set[int]:
        """This function returns the set of indexes for items that are currently visible in the viewport."""
        indexes: set[int] = set()

        top_index = self.indexAt(self.viewport().rect().topLeft())
        if not top_index.isValid():
            return indexes

        row = top_index.row()
        model = self.model()

        while row < model.rowCount():
            idx = model.index(row, 0)
            rect = self.visualRect(idx)
            if rect.top() > self.viewport().height():
                break
            elif rect.bottom() >= 0:
                indexes.add(row)

            row += 1

        return indexes
    
    def handle_item_data_changed(self, item: CustomListWidgetItem) -> None:
        """
        This slot is called when an item's data changes
        """
        widget = self.itemWidget(item)
        if widget is not None and isinstance(widget, ModListItemInner):
            widget.repolish(item)

    def handle_other_list_row_added(self, uuid: str) -> None:
        """
        When a mod is moved from Inactive->Active, the uuid is removed from the Inactive list.

        When a mod is moved from Active->Inactive, the uuid is removed from the Active list.
        """
        if uuid in self.uuids:
            self.uuids.remove(uuid)

    def handle_rows_inserted(self, parent: QModelIndex, first: int, last: int) -> None:
        """
        This slot is called when rows are inserted.

        When mods are inserted into the mod list, either through the
        `recreate_mod_list` method above or automatically through dragging
        and dropping on the UI, this function is called. For single-item
        inserts, which happens through the above method or through dragging
        and dropping individual mods, `first` equals `last` and the below
        loop is just run once. In this loop, a custom widget is created,
        which displays the text, icons, etc, and is added to the list item.

        For dragging and dropping multiple items, the loop is run multiple
        times. Importantly, even for multiple items, the number of list items
        is set BEFORE the loop starts running, e.g. if we were dragging 3 mods
        onto a list of 100 mods, this method is called once and by the start
        of this method, `self.count()` is already 103; there are 3 "empty"
        list items that do not have widgets assigned to them.

        However, inserting the initial `n` mods with `recreate_mod_list` has
        an inefficiency: it is only able to insert one at a time. This means
        this method is called `n` times for the first `n` mods.
        One optimization here (saving about 1 second with a 200 mod list) is
        to not emit the list update signal until the number of widgets is
        equal to the number of items. If widgets < items, that means
        widgets are still being added. Only when widgets == items does it mean
        we are done with adding the initial set of mods. We can do this
        by keeping track of the number of widgets currently loaded in the list
        through a set of UUIDs which we can compare to the number of items
        directly, as this set will equate to the items in the list.

        :param parent: parent to get rows under (not used)
        :param first: index of first item inserted
        :param last: index of last item inserted
        """
        # Loop through the indexes of inserted items, load widgets if not
        # already loaded. Each item index corresponds to a UUID index.
        for idx in range(first, last + 1):
            item = self.item(idx)
            if not isinstance(item, CustomListWidgetItem):
                # Convert to CustomListWidgetItem
                item = CustomListWidgetItem(item)
                self.replaceItemAtIndex(idx, item)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data is None:
                    logger.debug(f"Attempted to insert item with None data. Idx: {idx}")
                    continue
                if getattr(data, "is_divider", False):
                    uuid = data["uuid"]
                    if uuid in self.uuids:
                        self.uuids.remove(uuid)
                    self.uuids.insert(idx, uuid)
                    self.create_widget_for_item(item)
                    continue
                # Ensure the item's persisted list_type matches the destination list after insertion
                try:
                    data["list_type"] = self.list_type
                    item.setData(Qt.ItemDataRole.UserRole, data)
                except Exception:
                    pass
                uuid = data["uuid"]
                self.uuids.insert(idx, uuid)
                self.item_added_signal.emit(uuid)
        # Update list signal if all items are loaded
        if len(self.uuids) == self.count():
            # Update list with the number of items
            logger.debug(
                f"Emitting {self.list_type} list update signal after rows inserted [{self.count()}]"
            )
            self.list_update_signal.emit(str(self.count()))

    def handle_rows_removed(self, parent: QModelIndex, first: int, last: int) -> None:
        """
        This slot is called when rows are removed.
        Emit a signal with the count of objects remaining to update
        the count label. For some reason this seems to call twice on
        dragging and dropping multiple mods.

        The condition is required because when we `do_clear` or `do_import`,
        the existing list needs to be "wiped", and this counts as `n`
        calls to this function. When this happens, `self.uuids` is
        cleared and `self.count()` remains at the previous number, so we can
        just check for equality here.

        :param parent: parent to get rows under (not used)
        :param first: index of first item removed (not used)
        :param last: index of last item removed (not used)
        """
        # Update list signal if all items are loaded
        if len(self.uuids) == self.count():
            # Update list with the number of items
            logger.debug(
                f"Emitting {self.list_type} list update signal after rows removed [{self.count()}]"
            )
            self.list_update_signal.emit(str(self.count()))

    def get_item_widget_at_index(self, idx: int) -> QWidget | None:
        item = self.item(idx)
        if item:
            return self.itemWidget(item)
        return None

    # ── Divider helpers ──────────────────────────────────────────────

    def _show_divider_context_menu(
        self,
        item: CustomListWidgetItem,
        data: DividerData,
        pos_local: Any,
    ) -> bool:
        menu = QMenu()
        rename_action = menu.addAction(self.tr("Rename divider"))
        toggle_action = menu.addAction(
            self.tr("Expand") if data.collapsed else self.tr("Collapse")
        )
        menu.addSeparator()
        delete_action = menu.addAction(self.tr("Delete divider"))
        action = menu.exec_(self.mapToGlobal(pos_local))
        if action == rename_action:
            new_name, ok = QInputDialog.getText(
                self,
                self.tr("Rename Divider"),
                self.tr("New name:"),
                text=data.name,
            )
            if ok and new_name.strip():
                self.rename_divider(data.uuid, new_name.strip())
        elif action == toggle_action:
            self.toggle_divider_collapse(data.uuid)
        elif action == delete_action:
            self.remove_divider(data.uuid)
        return True

    def add_divider(self, index: int, name: str) -> None:
        uuid = generate_divider_uuid()
        data = DividerData(uuid=uuid, name=name)
        item = CustomListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, data, avoid_emit=True)
        try:
            self.model().rowsInserted.disconnect(self.handle_rows_inserted)
        except TypeError:
            pass
        self.insertItem(index, item)
        self.uuids.insert(index, uuid)
        self.create_widget_for_item(item)
        self.model().rowsInserted.connect(
            self.handle_rows_inserted, Qt.ConnectionType.QueuedConnection
        )
        self.apply_collapse_states()
        self.list_update_signal.emit(str(self.count()))

    def remove_divider(self, uuid: str) -> None:
        if uuid not in self.uuids:
            return
        idx = self.uuids.index(uuid)
        # Expand hidden items first so they become visible
        next_div = self._find_next_divider_index(idx + 1)
        for i in range(idx + 1, next_div):
            self.item(i).setHidden(False)
        self.uuids.pop(idx)
        self.takeItem(idx)
        self._update_divider_mod_counts()
        self.list_update_signal.emit(str(self.count()))

    def rename_divider(self, uuid: str, new_name: str) -> None:
        if uuid not in self.uuids:
            return
        idx = self.uuids.index(uuid)
        item = self.item(idx)
        data = item.data(Qt.ItemDataRole.UserRole)
        data.name = new_name
        item.setData(Qt.ItemDataRole.UserRole, data, avoid_emit=True)
        widget = self.itemWidget(item)
        if isinstance(widget, DividerItemInner):
            widget.set_name(new_name)

    def toggle_divider_collapse(self, uuid: str) -> None:
        if uuid not in self.uuids:
            return
        idx = self.uuids.index(uuid)
        item = self.item(idx)
        data = item.data(Qt.ItemDataRole.UserRole)
        if not getattr(data, "is_divider", False):
            return
        data.collapsed = not data.collapsed
        item.setData(Qt.ItemDataRole.UserRole, data, avoid_emit=True)
        widget = self.itemWidget(item)
        if isinstance(widget, DividerItemInner):
            widget.set_collapsed(data.collapsed)
        next_div = self._find_next_divider_index(idx + 1)
        for i in range(idx + 1, next_div):
            self.item(i).setHidden(data.collapsed)
        self._update_single_divider_mod_count(item)

    def _find_next_divider_index(self, start: int) -> int:
        for i in range(start, self.count()):
            d = self.item(i).data(Qt.ItemDataRole.UserRole)
            if getattr(d, "is_divider", False):
                return i
        return self.count()

    def _update_single_divider_mod_count(self, item: CustomListWidgetItem) -> None:
        idx = self.row(item)
        if idx < 0:
            return
        next_div = self._find_next_divider_index(idx + 1)
        count = next_div - idx - 1
        widget = self.itemWidget(item)
        if isinstance(widget, DividerItemInner):
            widget.set_mod_count(count)

    def _update_divider_mod_counts(self) -> None:
        for i in range(self.count()):
            item = self.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if getattr(data, "is_divider", False):
                self._update_single_divider_mod_count(item)

    def apply_collapse_states(self) -> None:
        """Hide/show items according to their preceding divider's collapsed state."""
        collapsed = False
        for i in range(self.count()):
            item = self.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if getattr(data, "is_divider", False):
                collapsed = data.collapsed
                widget = self.itemWidget(item)
                if isinstance(widget, DividerItemInner):
                    widget.set_collapsed(collapsed)
            else:
                item.setHidden(collapsed)
        self._update_divider_mod_counts()

    def get_dividers_data(self) -> list[dict]:
        """Return serialisable divider info for persistence."""
        result = []
        for i in range(self.count()):
            item = self.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if getattr(data, "is_divider", False):
                result.append(
                    {
                        "uuid": data.uuid,
                        "name": data.name,
                        "collapsed": data.collapsed,
                        "index": i,
                    }
                )
        return result

    def restore_dividers(self, dividers: list[dict]) -> None:
        """Re-insert dividers at saved positions after a list rebuild."""
        if not dividers:
            return
        # Disconnect model signals to avoid handle_rows_inserted duplicating uuids
        try:
            self.model().rowsInserted.disconnect(self.handle_rows_inserted)
        except TypeError:
            pass
        sorted_dividers = sorted(dividers, key=lambda d: d.get("index", 0))
        for div in sorted_dividers:
            idx = min(div.get("index", 0), self.count())
            uuid = div.get("uuid", generate_divider_uuid())
            data = DividerData(
                uuid=uuid,
                name=div.get("name", ""),
                collapsed=div.get("collapsed", False),
            )
            item = CustomListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, data, avoid_emit=True)
            self.insertItem(idx, item)
            self.uuids.insert(idx, uuid)
        # Reconnect model signals
        self.model().rowsInserted.connect(
            self.handle_rows_inserted, Qt.ConnectionType.QueuedConnection
        )
        self.check_widgets_visible()
        self.apply_collapse_states()

    # ── End divider helpers ──────────────────────────────────────────

    def mod_changed_to(
        self, current: CustomListWidgetItem, previous: CustomListWidgetItem
    ) -> None:
        """
        Method to handle clicking on a row or navigating between rows with
        the keyboard. Look up the mod's data by uuid
        """
        if current is not None:
            data = current.data(Qt.ItemDataRole.UserRole)
            if getattr(data, "is_divider", False):
                return
            self.mod_info_signal.emit(data["uuid"], current)

    def mod_clicked(self, current: CustomListWidgetItem) -> None:
        """
        Method to handle clicking on a row. Necessary because `mod_changed_to` does not
        properly handle clicking on a previous selected item after clicking on an item
        in another list. For example, clicking on item 1 in the inactive list, then on item 2
        in the active list, then back to item 1 in the inactive list-- this method makes
        it so that mod info is updated as expected.
        """
        if current is not None:
            data = current.data(Qt.ItemDataRole.UserRole)
            if getattr(data, "is_divider", False):
                return
            self.mod_info_signal.emit(data["uuid"], current)
            mod_info = self.metadata_manager.internal_local_metadata[data["uuid"]]
            mod_info = flatten_to_list(mod_info)
            mod_info_pretty = json.dumps(mod_info, indent=4)
            logger.debug(
                f"USER ACTION: mod was clicked: [{data['uuid']}] {mod_info_pretty}"
            )

    def mod_double_clicked(self, item: CustomListWidgetItem) -> None:
        """
        Method to handle double clicking on a row.
        """
        data = item.data(Qt.ItemDataRole.UserRole)
        if getattr(data, "is_divider", False):
            self.toggle_divider_collapse(data.uuid)
            return
        self.key_press_signal.emit("DoubleClick")

    def rebuild_item_widget_from_uuid(self, uuid: str) -> None:
        if is_divider_uuid(uuid):
            return
        item_index = self.uuids.index(uuid)
        item = self.item(item_index)
        logger.debug(f"Rebuilding widget for item {uuid} at index {item_index}")
        # Destroy the item's previous widget immediately. Recreate if the item is visible.
        widget = self.itemWidget(item)
        if widget:
            self.removeItemWidget(item)
        # If it is visible, create a new widget. Otherwise, allow lazy loading to handle this.
        if self.check_item_visible(item):
            self.create_widget_for_item(item)
        # If the current item is selected, update the info panel
        if self.currentItem() == item:
            self.mod_info_signal.emit(uuid, item)

    def _check_missing_dependencies(
        self, mod_data: ModMetadata, package_ids_set: set[str]
    ) -> tuple[set[str], set[str]]:
        """Check for missing dependencies and alternative dependencies."""
        missing_deps: set[str] = set()
        alternative_deps: set[str] = set()
        consider_alternatives = self.metadata_manager.settings_controller.settings.use_alternative_package_ids_as_satisfying_dependencies
        for dep_entry in mod_data.get("dependencies", []):
            alt_ids: set[str] = set()
            if isinstance(dep_entry, tuple):
                dep_id = dep_entry[0]
                if (
                    len(dep_entry) > 1
                    and isinstance(dep_entry[1], dict)
                    and isinstance(dep_entry[1].get("alternatives"), set)
                ):
                    alt_ids = dep_entry[1]["alternatives"]
            else:
                dep_id = dep_entry

            satisfied = dep_id in package_ids_set
            if not satisfied and consider_alternatives:
                satisfied = any(alt in package_ids_set for alt in alt_ids)
            if not satisfied and self._has_replacement(
                mod_data["packageid"], dep_id, package_ids_set
            ):
                satisfied = True

            if not satisfied:
                missing_deps.add(dep_id)
                if consider_alternatives:
                    alt_candidates = {a for a in alt_ids if a not in package_ids_set}
                    alternative_deps.update(
                        alt_candidates if alt_candidates else alt_ids
                    )
        return missing_deps, alternative_deps

    def _check_incompatibilities(
        self, mod_data: ModMetadata, package_ids_set: set[str]
    ) -> set[str]:
        """Check for conflicting incompatibilities."""
        return {
            incomp
            for incomp in mod_data.get("incompatibilities", [])
            if incomp in package_ids_set
        }

    def _check_load_order_violations(
        self,
        mod_data: ModMetadata,
        packageid_to_uuid: dict[str, str],
        current_mod_index: int,
    ) -> tuple[set[str], set[str]]:
        """Check for load order violations."""
        load_before_violations: set[str] = set()
        load_after_violations: set[str] = set()
        for load_this_before in mod_data.get("loadTheseBefore", []):
            if (
                load_this_before[1]
                and load_this_before[0] in packageid_to_uuid
                and current_mod_index
                <= self.uuids.index(packageid_to_uuid[load_this_before[0]])
            ):
                load_before_violations.add(load_this_before[0])
        for load_this_after in mod_data.get("loadTheseAfter", []):
            if (
                load_this_after[1]
                and load_this_after[0] in packageid_to_uuid
                and current_mod_index
                >= self.uuids.index(packageid_to_uuid[load_this_after[0]])
            ):
                load_after_violations.add(load_this_after[0])
        return load_before_violations, load_after_violations

    def _check_version_mismatch(self, uuid: str) -> bool:
        """Check if mod has version mismatch."""
        return self.metadata_manager.is_version_mismatch(uuid)

    def _check_use_this_instead(self, current_item_data: dict[str, Any]) -> bool:
        """Check if use_this_instead is applicable."""
        return bool(current_item_data["alternative"])

    def recalculate_internal_errors_warnings(self) -> tuple[str, str, int, int]:
        """
        Whenever the respective mod list has items added to it, or has
        items removed from it, or has items rearranged around within it,
        calculate the internal list errors / warnings for the mod list
        """
        logger.info(f"Recalculating {self.list_type} list errors / warnings")

        internal_local_metadata = self.metadata_manager.internal_local_metadata

        mod_uuids = [u for u in self.uuids if not is_divider_uuid(u)]
        packageid_to_uuid = {
            internal_local_metadata[uuid]["packageid"]: uuid for uuid in mod_uuids
        }
        package_ids_set = set(packageid_to_uuid.keys())

        package_id_to_errors: dict[str, dict[str, None | set[str] | bool]] = {
            uuid: {
                "missing_dependencies": set() if self.list_type == "Active" else None,
                "alternative_dependencies": set()
                if self.list_type == "Active"
                else None,
                "conflicting_incompatibilities": (
                    set() if self.list_type == "Active" else None
                ),
                "load_before_violations": set() if self.list_type == "Active" else None,
                "load_after_violations": set() if self.list_type == "Active" else None,
                "version_mismatch": True,
                "use_this_instead": set()
                if self.settings_controller.settings.external_use_this_instead_metadata_source
                != "None"
                else None,
            }
            for uuid in mod_uuids
        }

        num_warnings = 0
        total_warning_text = ""
        num_errors = 0
        total_error_text = ""

        # Load latest save package ids once for this run, only if feature enabled
        save_compare_enabled: bool = (
            self.settings_controller.settings.show_save_comparison_indicators
        )
        if save_compare_enabled:
            latest_save_ids = self._get_latest_save_package_ids()
        else:
            latest_save_ids = None

        for uuid, mod_errors in package_id_to_errors.items():
            current_mod_index = self.uuids.index(uuid)
            current_item = self.item(current_mod_index)
            if current_item is None:
                continue
            current_item_data = current_item.data(Qt.ItemDataRole.UserRole)
            if getattr(current_item_data, "is_divider", False):
                continue
            current_item_data["mismatch"] = False
            current_item_data["errors"] = ""
            current_item_data["warnings"] = ""
            # Mark active as new if not present in latest save; mark inactive as in_save if present in save
            if save_compare_enabled:
                try:
                    pkg_id = internal_local_metadata[uuid]["packageid"]
                    is_in_save = (
                        pkg_id in latest_save_ids
                        if latest_save_ids is not None
                        else False
                    )
                    if self.list_type == "Active":
                        current_item_data.__dict__["is_new"] = not is_in_save
                        current_item_data.__dict__["in_save"] = False
                    else:
                        current_item_data.__dict__["is_new"] = False
                        current_item_data.__dict__["in_save"] = is_in_save
                except Exception:
                    current_item_data.__dict__["is_new"] = False
                    current_item_data.__dict__["in_save"] = False
            else:
                current_item_data.__dict__["is_new"] = False
                current_item_data.__dict__["in_save"] = False
            mod_data = internal_local_metadata[uuid]
            # Check mod supportedversions against currently loaded version of game
            mod_errors["version_mismatch"] = self._check_version_mismatch(uuid)
            # Set an item's validity dynamically based on the version mismatch value
            if (
                mod_data["packageid"] not in self.ignore_warning_list
                and not current_item_data["warning_toggled"]
            ):
                current_item_data["mismatch"] = mod_errors["version_mismatch"]
            else:
                # If a mod has been moved for eg. inactive -> active. We keep ignoring the warnings.
                # This makes sure to add the mod to the ignore list of the new modlist.
                # TODO: Check if toggle_warning method can add a mod to the ignore list
                # of both ModListWidgets (Active and Inactive) at the same time. Then we can remove some of this confusing code...
                if not current_item_data["warning_toggled"]:
                    if mod_data["packageid"] in self.ignore_warning_list:
                        self.ignore_warning_list.remove(mod_data["packageid"])
                elif mod_data["packageid"] not in self.ignore_warning_list:
                    self.ignore_warning_list.append(mod_data.get("packageid"))
            # Check for "Active" mod list specific errors and warnings
            if (
                self.list_type == "Active"
                and mod_data.get("packageid")
                and mod_data["packageid"] not in self.ignore_warning_list
            ):
                # Use helper functions
                (
                    mod_errors["missing_dependencies"],
                    mod_errors["alternative_dependencies"],
                ) = self._check_missing_dependencies(mod_data, package_ids_set)
                mod_errors["conflicting_incompatibilities"] = (
                    self._check_incompatibilities(mod_data, package_ids_set)
                )
                (
                    mod_errors["load_before_violations"],
                    mod_errors["load_after_violations"],
                ) = self._check_load_order_violations(
                    mod_data, packageid_to_uuid, current_mod_index
                )
            # Calculate any needed string for errors
            tool_tip_text = ""
            # Build tooltip sections, conditionally include alternatives
            tooltip_sections = [
                ("missing_dependencies", self.tr("\nMissing Dependencies:")),
                ("conflicting_incompatibilities", self.tr("\nIncompatibilities:")),
            ]
            if self.metadata_manager.settings_controller.settings.use_alternative_package_ids_as_satisfying_dependencies:
                tooltip_sections.insert(
                    1,
                    (
                        "alternative_dependencies",
                        self.tr("\nAlternative Dependencies:"),
                    ),
                )

            for error_type, tooltip_header in tooltip_sections:
                if mod_errors[error_type]:
                    tool_tip_text += tooltip_header
                    errors = mod_errors[error_type]
                    assert isinstance(errors, set)
                    for key in errors:
                        name = internal_local_metadata.get(
                            packageid_to_uuid.get(key, ""), {}
                        ).get(
                            "name",
                            self.metadata_manager.steamdb_packageid_to_name.get(
                                key, key
                            ),
                        )
                        tool_tip_text += f"\n  * {name}"
            # If missing dependency and/or incompatibility, add tooltip to errors
            current_item_data["errors"] = tool_tip_text
            # Calculate any needed string for warnings
            for error_type, tooltip_header in [
                ("load_before_violations", self.tr("\nShould be Loaded After:")),
                ("load_after_violations", self.tr("\nShould be Loaded Before:")),
            ]:
                if mod_errors[error_type]:
                    tool_tip_text += tooltip_header
                    errors = mod_errors[error_type]
                    assert isinstance(errors, set)
                    for key in errors:
                        name = internal_local_metadata.get(
                            packageid_to_uuid.get(key, ""), {}
                        ).get(
                            "name",
                            self.metadata_manager.steamdb_packageid_to_name.get(
                                key, key
                            ),
                        )
                        tool_tip_text += f"\n  * {name}"
            # Handle version mismatch behavior
            if (
                mod_errors["version_mismatch"]
                and mod_data["packageid"] not in self.ignore_warning_list
            ):
                # Add tool tip to indicate mod and game version mismatch
                tool_tip_text += self.tr("\nMod and Game Version Mismatch")
            # Handle "use this instead" behavior
            if (
                self._check_use_this_instead(current_item_data)
                and mod_data["packageid"] not in self.ignore_warning_list
            ):
                mod_errors["use_this_instead"] = True
                tool_tip_text += self.tr(
                    "\nAn alternative updated mod is recommended:\n{alternative}"
                ).format(alternative=current_item_data["alternative"])
            # Add to error summary if any missing dependencies or incompatibilities
            if self.list_type == "Active" and any(
                [
                    mod_errors[key]
                    for key in [
                        "missing_dependencies",
                        "conflicting_incompatibilities",
                    ]
                ]
            ):
                num_errors += 1
                total_error_text += f"\n\n{mod_data['name']}"
                total_error_text += "\n" + "=" * len(mod_data["name"])
                total_error_text += tool_tip_text

            # Add to warning summary if any loadBefore or loadAfter violations, or version mismatch
            # Version mismatch is determined earlier without checking if the mod is in ignore_warning_list
            # so we have to check it again here in order to not display a faulty, empty version warning
            if (
                self.list_type == "Active"
                and mod_data["packageid"] not in self.ignore_warning_list
                and any(
                    [
                        mod_errors[key]
                        for key in [
                            "load_before_violations",
                            "load_after_violations",
                            "version_mismatch",
                            "use_this_instead",
                        ]
                    ]
                )
            ):
                num_warnings += 1
                total_warning_text += f"\n\n{mod_data['name']}"
                total_warning_text += "\n============================="
                total_warning_text += tool_tip_text
            # Add tooltip to item data and set the data back to the item
            current_item_data["errors_warnings"] = tool_tip_text.strip()
            current_item_data["warnings"] = tool_tip_text[
                len(current_item_data["errors"]) :
            ].strip()
            current_item_data["errors"] = current_item_data["errors"].strip()
            current_item.setData(Qt.ItemDataRole.UserRole, current_item_data)
        logger.info(f"Finished recalculating {self.list_type} list errors and warnings")
        return total_error_text, total_warning_text, num_errors, num_warnings

    def _get_latest_save_package_ids(self) -> set[str] | None:
        """Attempt to find the latest RimWorld save file in the configured instance and extract modIds.

        Returns a set of packageIds in the save, or None on failure. Cached per list instance.
        """
        # Respect setting: fully disable feature to avoid performance impact
        if not self.settings_controller.settings.show_save_comparison_indicators:
            return None
        if self._latest_save_package_ids is not None:
            return self._latest_save_package_ids

        try:
            # Config path typically points to the RimWorld config folder; Saves is sibling folder
            cfg_path = self.settings_controller.settings.instances[
                self.settings_controller.settings.current_instance
            ].config_folder
            if not cfg_path:
                return None
            saves_dir = Path(cfg_path).parent / "Saves"
            if not saves_dir.exists():
                # Try common default path
                pd = PlatformDirs(appname="RimWorld by Ludeon Studios", appauthor=False)
                candidate = Path(pd.user_data_dir).parent / "Saves"
                saves_dir = candidate if candidate.exists() else saves_dir

            if not saves_dir.exists():
                return None

            # Find latest .rws by modified time
            latest: Path | None = None
            latest_mtime = -1.0
            for p in saves_dir.glob("*.rws"):
                m = p.stat().st_mtime
                if m > latest_mtime:
                    latest_mtime = m
                    latest = p
            if latest is None:
                return None

            if fast_rimworld_xml_save_validation(str(latest)):
                ids_set = extract_xml_package_ids(str(latest))
            else:
                ids_set = set("Ludeon.RimWorld")
            # Normalize to lowercase
            self._latest_save_package_ids = {str(i).lower() for i in ids_set}
            return self._latest_save_package_ids
        except Exception:
            return None

    def _has_replacement(
        self, package_id: str, dep: str, package_ids_set: set[str]
    ) -> bool:
        # Get a list of mods that can replace this mod
        replacements = KNOWN_MOD_REPLACEMENTS.get(dep, set())
        # Return true if any of the above mods (replacements) are in the mod list
        # If no replacements exist for dep, returns false
        for replacement in replacements:
            if replacement in package_ids_set:
                logger.debug(
                    f"Missing dependency [{dep}] for [{package_id}] replaced with [{replacement}]"
                )
                return True
        return False

    def recreate_mod_list_and_sort(
        self,
        list_type: str,
        uuids: list[str],
        key: ModsPanelSortKey,
        descending: bool = False,
    ) -> None:
        """
        Reconstructs and sorts a mod list based on provided UUIDs and a sorting key.

        This method takes a list of mod UUIDs, sorts them according to the specified
        sorting key, and then recreates the mod list of the given type with the sorted order.

        Args:
            list_type (str): The type of mod list to recreate. ("Active", "Inactive")
            uuids (List[str]): The list of UUIDs representing the mods.
            key (ModsPanelSortKey): An enumeration value that determines the
                                     sorting criterion for the mods.
            descending (bool, optional): Whether to sort in descending order. Defaults to False.

        Returns:
            None
        """
        filtering = self.settings_controller.settings.inactive_mods_sorting

        if filtering:
            sorted_uuids = sort_uuids(
                uuids,
                key=key,
                descending=descending,
                settings_controller=self.settings_controller,
            )
            self.recreate_mod_list(list_type, sorted_uuids, filtering=filtering)
        else:
            self.recreate_mod_list(list_type, uuids)

    def recreate_mod_list(
        self, list_type: str, uuids: list[str], filtering: bool = False
    ) -> None:
        """
        Clear all mod items and add new ones from a dict.

        :param mods: dict of mod data
        :param filtering: if True, UUIDs are already sorted; skip sorting
        """
        logger.info(f"Internally recreating {list_type} mod list")
        # Skip sorting if UUIDs are already filtered/sorted (filtering=True)
        if not filtering:
            if (
                list_type == "Inactive"
                and self.settings_controller.settings.inactive_mods_sorting
            ):
                sort_key = ModsPanelSortKey[
                    self.settings_controller.settings.inactive_mods_sort_key
                ]
                descending = (
                    self.settings_controller.settings.inactive_mods_sort_descending
                )
                uuids = sort_uuids(
                    uuids,
                    key=sort_key,
                    descending=descending,
                    settings_controller=self.settings_controller,
                )
            elif list_type == "Inactive":
                uuids = sort_uuids(
                    uuids,
                    key=ModsPanelSortKey.FILESYSTEM_MODIFIED_TIME,
                    descending=True,
                    settings_controller=self.settings_controller,
                )
        # Disable updates and disconnect model signals during rebuild
        self.setUpdatesEnabled(False)
        # Temporarily disconnect model signals to avoid cascading updates and duplicate items
        try:
            self.model().rowsInserted.disconnect(self.handle_rows_inserted)
        except TypeError:
            pass  # Signal not connected
        try:
            self.model().rowsAboutToBeRemoved.disconnect(self.handle_rows_removed)
        except TypeError:
            pass  # Signal not connected

        self.clear()
        self.uuids = list()
        if uuids:  # Insert data...
            for uuid_key in uuids:
                if is_divider_uuid(uuid_key):
                    continue
                mod_path = self.metadata_manager.internal_local_metadata[uuid_key][
                    "path"
                ]
                aux_metadata_controller = (
                    AuxMetadataController.get_or_create_cached_instance(
                        self.settings_controller.settings.aux_db_path
                    )
                )
                with aux_metadata_controller.Session() as aux_metadata_session:
                    aux_metadata_controller.get_or_create(
                        aux_metadata_session, mod_path
                    )
                    aux_metadata_controller.update(
                        aux_metadata_session, mod_path, outdated=False
                    )
                    list_item = CustomListWidgetItem(self)
                    data = CustomListWidgetItemMetadata(
                        uuid=uuid_key,
                        list_type=self.list_type,
                        aux_metadata_controller=aux_metadata_controller,
                        aux_metadata_session=aux_metadata_session,
                        settings_controller=self.settings_controller,
                    )
                list_item.setData(Qt.ItemDataRole.UserRole, data)
                self.addItem(list_item)
                # When refreshing, update entry if needed?
            # Set uuids list to match the widget after all items are added
            self.uuids = list(uuids)

        else:  # ...unless we don't have mods, at which point reenable updates and exit
            self.setUpdatesEnabled(True)
            # Reconnect model signals
            self.model().rowsInserted.connect(self.handle_rows_inserted, Qt.ConnectionType.QueuedConnection)
            self.model().rowsAboutToBeRemoved.connect(self.handle_rows_removed, Qt.ConnectionType.QueuedConnection)
            return

        # Reconnect model signals
        self.model().rowsInserted.connect(self.handle_rows_inserted, Qt.ConnectionType.QueuedConnection)
        self.model().rowsAboutToBeRemoved.connect(self.handle_rows_removed, Qt.ConnectionType.QueuedConnection)
        # Enable updates and repaint
        self.setUpdatesEnabled(True)
        self.repaint()
        # Load visible widgets after rebuild completes
        self.check_widgets_visible()
        # Emit signal to update counts and errors/warnings
        self.list_update_signal.emit(str(self.count()))

    def toggle_warning(self, packageid: str, uuid: str) -> None:
        logger.debug(f"Toggled warning icon for: {packageid}")
        current_mod_index = self.uuids.index(uuid)
        item = self.item(current_mod_index)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        if packageid not in self.ignore_warning_list:
            self.ignore_warning_list.append(packageid)
            item_data["warning_toggled"] = True
        else:
            self.ignore_warning_list.remove(packageid)
            item_data["warning_toggled"] = False
        # Update Aux DB
        aux_metadata_controller = AuxMetadataController.get_or_create_cached_instance(
            self.settings_controller.settings.aux_db_path
        )
        uuid = item_data["uuid"]
        if not uuid:
            logger.error(
                "Unable to retrieve uuid when saving toggle_warning to Aux DB."
            )
            return
        with aux_metadata_controller.Session() as aux_metadata_session:
            mod_path = self.metadata_manager.internal_local_metadata[uuid]["path"]
            aux_metadata_controller.update(
                aux_metadata_session,
                mod_path,
                ignore_warnings=item_data["warning_toggled"],
            )
        item.setData(Qt.ItemDataRole.UserRole, item_data)
        self.recalculate_warnings_signal.emit()

    def change_mod_color(self, uuid: str, new_color: QColor) -> None:
        current_mod_index = self.uuids.index(uuid)
        item = self.item(current_mod_index)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        item_data["mod_color"] = new_color
        item.setData(Qt.ItemDataRole.UserRole, item_data)
        auxdb_update_mod_color(self.settings_controller, uuid, new_color)

    def change_all_mod_colors(self, uuids: list[str], new_color: QColor) -> None:
        uuid_to_color: dict[str, QColor | None] = {}
        for uuid in uuids:
            current_mod_index = self.uuids.index(uuid)
            item = self.item(current_mod_index)
            item_data = item.data(Qt.ItemDataRole.UserRole)
            item_data["mod_color"] = new_color
            item.setData(Qt.ItemDataRole.UserRole, item_data)
            uuid_to_color[uuid] = new_color
        auxdb_update_all_mod_colors(self.settings_controller, uuid_to_color)

    def reset_mod_color(self, uuid: str) -> None:
        current_mod_index = self.uuids.index(uuid)
        item = self.item(current_mod_index)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        item_data["mod_color"] = None
        item.setData(Qt.ItemDataRole.UserRole, item_data)
        auxdb_update_mod_color(self.settings_controller, uuid, None)

    def reset_all_mod_colors(self, uuids: list[str]) -> None:
        uuid_to_color: dict[str, QColor | None] = {}
        for uuid in uuids:
            current_mod_index = self.uuids.index(uuid)
            item = self.item(current_mod_index)
            item_data = item.data(Qt.ItemDataRole.UserRole)
            item_data["mod_color"] = None
            item.setData(Qt.ItemDataRole.UserRole, item_data)
            uuid_to_color[uuid] = None
        auxdb_update_all_mod_colors(self.settings_controller, uuid_to_color)

    def change_mod_font_color(self, uuid: str, new_color: QColor) -> None:
        current_mod_index = self.uuids.index(uuid)
        item = self.item(current_mod_index)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        item_data["mod_font_color"] = new_color
        item.setData(Qt.ItemDataRole.UserRole, item_data)
        auxdb_update_mod_font_color(self.settings_controller, uuid, new_color)

    def change_all_mod_font_colors(self, uuids: list[str], new_color: QColor) -> None:
        uuid_to_color: dict[str, QColor | None] = {}
        for uuid in uuids:
            current_mod_index = self.uuids.index(uuid)
            item = self.item(current_mod_index)
            item_data = item.data(Qt.ItemDataRole.UserRole)
            item_data["mod_font_color"] = new_color
            item.setData(Qt.ItemDataRole.UserRole, item_data)
            uuid_to_color[uuid] = new_color
        auxdb_update_all_mod_font_colors(self.settings_controller, uuid_to_color)

    def reset_mod_font_color(self, uuid: str) -> None:
        current_mod_index = self.uuids.index(uuid)
        item = self.item(current_mod_index)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        item_data["mod_font_color"] = None
        item.setData(Qt.ItemDataRole.UserRole, item_data)
        auxdb_update_mod_font_color(self.settings_controller, uuid, None)

    def reset_all_mod_font_colors(self, uuids: list[str]) -> None:
        uuid_to_color: dict[str, QColor | None] = {}
        for uuid in uuids:
            current_mod_index = self.uuids.index(uuid)
            item = self.item(current_mod_index)
            item_data = item.data(Qt.ItemDataRole.UserRole)
            item_data["mod_font_color"] = None
            item.setData(Qt.ItemDataRole.UserRole, item_data)
            uuid_to_color[uuid] = None
        auxdb_update_all_mod_font_colors(self.settings_controller, uuid_to_color)

    def replaceItemAtIndex(self, index: int, item: CustomListWidgetItem) -> None:
        """
        IMPORTANT: This is used to replace an item without triggering the rowsInserted signal and rowsAboutToBeRemoved signal.
        :param index: The index of the item to replace.
        :param item: The new item that will replace the old one.
        """
        # The rowsInserted signal should be removed from ALL slots and then reconnected to ALL slots.
        # This will have to be manually done below, unless we start tracking which slots that signal is connected to.

        # Check if the signal is connected before disconnecting
        try:
            self.model().rowsInserted.disconnect(self.handle_rows_inserted)
        except TypeError:
            pass  # Signal was not connected
        try:
            self.model().rowsAboutToBeRemoved.disconnect(self.handle_rows_removed)
        except TypeError:
            pass  # Signal was not connected

        # Perform the replacement
        self.takeItem(index)
        self.insertItem(index, item)
        # Ensure the item's metadata reflects this list's type after replacement
        try:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data is not None:
                data["list_type"] = self.list_type
                item.setData(Qt.ItemDataRole.UserRole, data)
        except Exception:
            pass

        # Reconnect to ALL slots
        self.model().rowsInserted.connect(
            self.handle_rows_inserted, Qt.ConnectionType.QueuedConnection
        )
        self.model().rowsAboutToBeRemoved.connect(
            self.handle_rows_removed, Qt.ConnectionType.QueuedConnection
        )


class ModsPanel(QWidget):
    """
    This class controls the layout and functionality for the
    active/inactive mods list panel on the GUI.
    """

    list_updated_signal = Signal()
    save_btn_animation_signal = Signal()
    check_dependencies_signal = Signal()

    # OPTIMIZATION: Class-level constant for sort text to enum mapping
    # Centralizes the text->enum conversion logic
    SORT_TEXT_TO_KEY_MAP = {
        "Name": ModsPanelSortKey.MODNAME,
        "Author": ModsPanelSortKey.AUTHOR,
        "Modified Time": ModsPanelSortKey.FILESYSTEM_MODIFIED_TIME,
        "Folder Size": ModsPanelSortKey.FOLDER_SIZE,
        "Version": ModsPanelSortKey.VERSION,
        "PackageId": ModsPanelSortKey.PACKAGEID,
        "Color": ModsPanelSortKey.MOD_COLOR,
    }

    def update_sort_ui_from_settings(self) -> None:
        """
        Update the inactive mods sort UI elements from settings.

        Restores the saved sort key and direction to the UI combobox and button.
        """
        self.inactive_mods_sort_key = (
            self.settings_controller.settings.inactive_mods_sort_key
        )
        self.inactive_mods_sort_descending = (
            self.settings_controller.settings.inactive_mods_sort_descending
        )
        # Map enum names to translated text for setting combo box selection
        key_to_text = {
            "MODNAME": self.tr("Name"),
            "AUTHOR": self.tr("Author"),
            "FILESYSTEM_MODIFIED_TIME": self.tr("Modified Time"),
            "FOLDER_SIZE": self.tr("Folder Size"),
            "VERSION": self.tr("Version"),
            "PACKAGEID": self.tr("PackageId"),
            "MOD_COLOR": self.tr("Color"),
        }
        # Set combo box selection based on loaded settings
        self.inactive_mods_sort_combobox.setCurrentText(
            key_to_text.get(self.inactive_mods_sort_key, self.tr("Modified Time"))
        )
        # Update sort order button text
        self.inactive_mods_sort_order_button.setText(
            self.tr("Desc") if self.inactive_mods_sort_descending else self.tr("Asc")
        )

    def __init__(self, settings_controller: SettingsController) -> None:
        """
        Initialize the class.
        Create a ListWidget using the dict of mods. This will
        create a row for every key-value pair in the dict.
        """
        super(ModsPanel, self).__init__()

        # Cache MetadataManager instance and initialize panel
        logger.debug("Initializing ModsPanel")
        self.metadata_manager = MetadataManager.instance()
        self.settings_controller = settings_controller

        # Load inactive mods sort settings
        self.inactive_mods_sort_key = (
            self.settings_controller.settings.inactive_mods_sort_key
        )
        self.inactive_mods_sort_descending = (
            self.settings_controller.settings.inactive_mods_sort_descending
        )

        # Background folder-size sorting state
        self._size_progress_dialog: Optional[QProgressDialog] = None
        self._size_thread: Optional[QThread] = None
        self._size_worker: Optional[FolderSizeWorker] = None
        self._size_current_uuids: list[str] = []

        # Debounce timer for non-heavy sort operations
        self._sort_debounce_timer = QTimer()
        self._sort_debounce_timer.setSingleShot(True)
        self._sort_debounce_timer.timeout.connect(self._execute_pending_sort)
        self._pending_sort_params: Optional[
            tuple[str, list[str], ModsPanelSortKey, bool]
        ] = None

        # Base layout with a splitter for resizable mod lists
        self.panel = QVBoxLayout()
        self.lists_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.lists_splitter.setChildrenCollapsible(False)
        self.lists_splitter.setHandleWidth(4)
        self.active_panel = QVBoxLayout()
        self.inactive_panel = QVBoxLayout()
        self.inactive_container = QWidget()
        self.inactive_container.setLayout(self.inactive_panel)
        self.active_container = QWidget()
        self.active_container.setLayout(self.active_panel)
        self.lists_splitter.addWidget(self.inactive_container)
        self.lists_splitter.addWidget(self.active_container)
        self.lists_splitter.setStretchFactor(0, 1)
        self.lists_splitter.setStretchFactor(1, 1)
        self.panel.addWidget(self.lists_splitter, 1)

        # Create the buttons layout
        self.button_panel = QHBoxLayout()
        # Create buttons frame
        self.button_panel_frame: QFrame = QFrame()
        self.button_panel_frame.setObjectName("MainWindowButtons")

        # Create and add Use This Instead button
        self.use_this_instead_button = QPushButton(
            self.tr('Check "Use This Instead" Database')
        )
        self.use_this_instead_button.setObjectName("UseThisInsteadButton")
        self.use_this_instead_button.clicked.connect(
            EventBus().use_this_instead_clicked.emit
        )
        self.button_panel.addWidget(self.use_this_instead_button)

        # Create and add Check Dependencies button
        self.check_dependencies_button: QPushButton = QPushButton(
            self.tr("Check Dependencies")
        )
        self.check_dependencies_button.setObjectName("CheckDependenciesButton")
        self.button_panel.addWidget(self.check_dependencies_button)
        self.check_dependencies_button.clicked.connect(
            self.check_dependencies_signal.emit
        )
        self.button_panel_frame.setLayout(self.button_panel)

        # Add the buttons frame below the lists panel
        self.panel.addWidget(self.button_panel_frame, 0)

        # Filter icons and tooltips
        self.data_source_filter_icons = [
            QIcon(str(AppInfo().theme_data_folder / "default-icons" / "AppIcon_b.png")),
            ModListIcons.ludeon_icon(),
            ModListIcons.local_icon(),
            ModListIcons.git_icon(),
            ModListIcons.steamcmd_icon(),
            ModListIcons.steam_icon(),
        ]
        self.data_source_filter_tooltips = [
            self.tr("Showing All Mods"),
            self.tr("Showing Core and DLC"),
            self.tr("Showing Local Mods"),
            self.tr("Showing Git Mods"),
            self.tr("Showing SteamCMD Mods"),
            self.tr("Showing Steam Mods"),
        ]
        self.data_source_filter_type_icons = [
            QIcon(str(AppInfo().theme_data_folder / "default-icons" / "AppIcon_b.png")),
            ModListIcons.csharp_icon(),
            ModListIcons.xml_icon(),
        ]
        self.data_source_filter_type_tooltips = [
            self.tr("Showing All Mod Types"),
            self.tr("Showing C# Mods"),
            self.tr("Showing XML Mods"),
        ]

        self.mode_filter_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "filter.png")
        )
        self.mode_filter_tooltip = self.tr("Hide Filter Disabled")
        self.mode_nofilter_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "nofilter.png")
        )
        self.mode_nofilter_tooltip = self.tr("Hide Filter Enabled")

        # ACTIVE mod list widget
        self.active_mods_label = QLabel(self.tr("Active [0]"))
        self.active_mods_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.active_mods_label.setObjectName("summaryValue")
        self.active_mods_list = ModListWidget(
            list_type="Active",
            settings_controller=self.settings_controller,
        )
        # Active mods search widgets
        self.active_mods_search_layout = QHBoxLayout()
        self.initialize_active_mods_search_widgets()

        # Add active mods widgets to layout
        self.active_panel.addWidget(self.active_mods_label)
        self.active_panel.addLayout(self.active_mods_search_layout)
        self.active_panel.addWidget(self.active_mods_list)

        # Add the errors summary frame below the active mods list
        self.active_panel.addWidget(self.errors_summary_frame)

        # Initialize inactive mods widgets
        self.inactive_mods_label = QLabel(self.tr("Inactive [0]"))
        self.inactive_mods_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inactive_mods_label.setObjectName("summaryValue")
        self.inactive_mods_list = ModListWidget(
            list_type="Inactive",
            settings_controller=self.settings_controller,
        )

        self.inactive_mods_search_layout = QVBoxLayout()
        self.inactive_mods_search_layout.setSpacing(2)
        self.initialize_inactive_mods_search_widgets()

        # Add inactive mods widgets to layout
        self.inactive_panel.addWidget(self.inactive_mods_label)
        self.inactive_panel.addLayout(self.inactive_mods_search_layout)
        self.inactive_panel.addWidget(self.inactive_mods_list)

        # Connect signals and slots
        self.connect_signals()

        # Connect to settings changed to update sort UI
        EventBus().settings_have_changed.connect(self.update_sort_ui_from_settings)

        # Set the main layout for the widget
        self.setLayout(self.panel)

        logger.debug("Finished ModsPanel initialization")

    def initialize_active_mods_search_widgets(self) -> None:
        """Initialize widgets for active mods search layout."""
        self.active_mods_filter_data_source_index = (
            self.settings_controller.settings.active_mods_data_source_filter_index
        )
        self.active_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.active_mods_filter_data_source_index
        ]
        self.active_mods_filter_data_source_button = QToolButton()
        self.active_mods_filter_data_source_button.setIcon(
            self.data_source_filter_icons[self.active_mods_filter_data_source_index]
        )
        self.active_mods_filter_data_source_button.setToolTip(
            self.data_source_filter_tooltips[self.active_mods_filter_data_source_index]
        )
        self.active_mods_filter_data_source_button.clicked.connect(
            self.on_active_mods_search_data_source_filter
        )
        self.active_data_source_filter_type_index = 0
        self.active_mods_data_source_filter_type = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.active_data_source_filter_type_index
        ]
        self.active_data_source_filter_type_button = QToolButton()
        self.active_data_source_filter_type_button.setIcon(
            self.data_source_filter_type_icons[
                self.active_data_source_filter_type_index
            ]
        )
        self.active_data_source_filter_type_button.setToolTip(
            self.data_source_filter_type_tooltips[
                self.active_data_source_filter_type_index
            ]
        )
        self.active_data_source_filter_type_button.clicked.connect(
            self.on_active_mods_search_data_source_filter_type
        )
        self.active_mods_search_filter_state = True
        self.active_mods_search_mode_filter_button = QToolButton()
        self.active_mods_search_mode_filter_button.setIcon(self.mode_filter_icon)
        self.active_mods_search_mode_filter_button.setToolTip(self.mode_filter_tooltip)
        self.active_mods_search_mode_filter_button.clicked.connect(
            self.on_active_mods_mode_filter_toggle
        )
        self.active_mods_search = QLineEdit()
        self.active_mods_search.setClearButtonEnabled(True)
        self.active_mods_search.textChanged.connect(self.on_active_mods_search)
        self.active_mods_search.inputRejected.connect(self.on_active_mods_search_clear)
        self.active_mods_search.setPlaceholderText(self.tr("Search by..."))
        self.active_mods_search.setMaximumWidth(150)
        # Add explicit type annotation to help mypy
        self.active_mods_search_clear_button = cast(
            QToolButton, self.active_mods_search.findChild(QToolButton)
        )
        if not isinstance(self.active_mods_search_clear_button, QToolButton):
            raise TypeError("Could not find QToolButton in QLineEdit")
        self.active_mods_search_clear_button.setEnabled(True)
        self.active_mods_search_clear_button.clicked.connect(
            self.on_active_mods_search_clear
        )
        self.active_mods_search_filter: QComboBox = QComboBox()
        self.active_mods_search_filter.setObjectName("MainUI")
        self.active_mods_search_filter.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.active_mods_search_filter.addItems(
            [
                self.tr("Name"),
                self.tr("Notes"),
                self.tr("PackageId"),
                self.tr("Author(s)"),
                self.tr("PublishedFileId"),
                self.tr("Version"),
            ]
        )
        # Active mods toolbar: search on left, Sort button on right
        self.active_mods_search_layout.addWidget(
            self.active_mods_filter_data_source_button
        )
        if self.settings_controller.settings.mod_type_filter:
            self.active_mods_search_layout.addWidget(
                self.active_data_source_filter_type_button
            )
        self.active_mods_search_layout.addWidget(
            self.active_mods_search_mode_filter_button
        )
        self.active_mods_search_layout.addWidget(self.active_mods_search, 0)
        self.active_mods_search_layout.addWidget(self.active_mods_search_filter, 0)
        self.active_mods_search_layout.addStretch(1)
        # Active mods list Errors/warnings widgets
        self.errors_summary_frame: QFrame = QFrame()
        self.errors_summary_frame.setObjectName("errorFrame")
        self.errors_summary_layout = QVBoxLayout()
        self.errors_summary_layout.setContentsMargins(0, 0, 0, 0)
        self.errors_summary_layout.setSpacing(2)
        # Create horizontal layout for warnings and errors
        self.warnings_errors_layout = QHBoxLayout()
        self.warnings_errors_layout.setSpacing(2)
        self.warnings_icon: QLabel = QLabel()
        self.warnings_icon.setPixmap(ModListIcons.warning_icon().pixmap(QSize(20, 20)))
        self.warnings_text: AdvancedClickableQLabel = AdvancedClickableQLabel(
            self.tr("0 warnings")
        )
        self.warnings_text.setObjectName("summaryValue")
        self.warnings_text.setToolTip(self.tr("Click to only show mods with warnings"))
        self.errors_icon: QLabel = QLabel()
        self.errors_icon.setPixmap(ModListIcons.error_icon().pixmap(QSize(20, 20)))
        self.errors_text: AdvancedClickableQLabel = AdvancedClickableQLabel("0 errors")
        self.errors_text.setObjectName("summaryValue")
        self.errors_text.setToolTip(self.tr("Click to only show mods with errors"))
        self.warnings_layout = QHBoxLayout()
        self.warnings_layout.addWidget(self.warnings_icon, 1)
        self.warnings_layout.addWidget(self.warnings_text, 99)
        self.errors_layout = QHBoxLayout()
        self.errors_layout.addWidget(self.errors_icon, 1)
        self.errors_layout.addWidget(self.errors_text, 99)
        self.warnings_errors_layout.addLayout(self.warnings_layout, 50)
        self.warnings_errors_layout.addLayout(self.errors_layout, 50)

        # Add warnings/errors layout to main vertical layout
        self.errors_summary_layout.addLayout(self.warnings_errors_layout)

        # Add to the outer frame
        self.errors_summary_frame.setLayout(self.errors_summary_layout)
        self.errors_summary_frame.setHidden(True)
        # New mods label (next to warnings/errors)
        self.news_layout = QHBoxLayout()
        self.new_icon: QLabel = QLabel()
        self.new_icon.setPixmap(
            QIcon(
                str(AppInfo().theme_data_folder / "default-icons" / "new.png")
            ).pixmap(QSize(20, 20))
        )
        self.new_text: AdvancedClickableQLabel = AdvancedClickableQLabel(
            self.tr("0 new")
        )
        self.new_text.setObjectName("summaryValue")
        self.new_text.setToolTip(
            self.tr("Click to only show active mods not in latest save")
        )
        self.news_layout.addWidget(self.new_icon, 1)
        self.news_layout.addWidget(self.new_text, 99)
        self.warnings_errors_layout.addLayout(self.news_layout, 50)

    def initialize_inactive_mods_search_widgets(self) -> None:
        """Initialize widgets for inactive mods search layout."""
        self.inactive_mods_filter_data_source_index = (
            self.settings_controller.settings.inactive_mods_data_source_filter_index
        )
        self.inactive_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.inactive_mods_filter_data_source_index
        ]
        self.inactive_mods_filter_data_source_button = QToolButton()
        self.inactive_mods_filter_data_source_button.setIcon(
            self.data_source_filter_icons[self.inactive_mods_filter_data_source_index]
        )
        self.inactive_mods_filter_data_source_button.setToolTip(
            self.data_source_filter_tooltips[
                self.inactive_mods_filter_data_source_index
            ]
        )
        self.inactive_mods_filter_data_source_button.clicked.connect(
            self.on_inactive_mods_search_data_source_filter
        )
        self.inactive_data_source_filter_type_index = 0
        self.inactive_mods_data_source_filter_type = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.inactive_data_source_filter_type_index
        ]
        self.inactive_data_source_filter_type_button = QToolButton()
        self.inactive_data_source_filter_type_button.setIcon(
            self.data_source_filter_type_icons[
                self.inactive_data_source_filter_type_index
            ]
        )
        self.inactive_data_source_filter_type_button.setToolTip(
            self.data_source_filter_type_tooltips[
                self.inactive_data_source_filter_type_index
            ]
        )
        self.inactive_data_source_filter_type_button.clicked.connect(
            self.on_inactive_mods_search_data_source_filter_type
        )
        self.inactive_mods_search_filter_state = True
        self.inactive_mods_search_mode_filter_button = QToolButton()
        self.inactive_mods_search_mode_filter_button.setIcon(self.mode_filter_icon)
        self.inactive_mods_search_mode_filter_button.setToolTip(
            self.mode_filter_tooltip
        )
        self.inactive_mods_search_mode_filter_button.clicked.connect(
            self.on_inactive_mods_mode_filter_toggle
        )
        self.inactive_mods_search = QLineEdit()
        self.inactive_mods_search.setClearButtonEnabled(True)
        self.inactive_mods_search.textChanged.connect(self.on_inactive_mods_search)
        self.inactive_mods_search.inputRejected.connect(
            self.on_inactive_mods_search_clear
        )
        self.inactive_mods_search.setPlaceholderText(self.tr("Search by..."))
        self.inactive_mods_search.setMaximumWidth(150)
        # Add explicit type annotation to help mypy
        self.inactive_mods_search_clear_button = cast(
            QToolButton, self.inactive_mods_search.findChild(QToolButton)
        )
        if not isinstance(self.inactive_mods_search_clear_button, QToolButton):
            raise TypeError("Could not find QToolButton in QLineEdit")
        self.inactive_mods_search_clear_button.setEnabled(True)
        self.inactive_mods_search_clear_button.clicked.connect(
            self.on_inactive_mods_search_clear
        )
        self.inactive_mods_search_filter: QComboBox = QComboBox()
        self.inactive_mods_search_filter.setParent(self)
        self.inactive_mods_search_filter.setObjectName("MainUI")
        self.inactive_mods_search_filter.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.inactive_mods_search_filter.addItems(
            [
                self.tr("Name"),
                self.tr("Notes"),
                self.tr("PackageId"),
                self.tr("Author(s)"),
                self.tr("PublishedFileId"),
                self.tr("Version"),
            ]
        )
        self.inactive_mods_sort_combobox: QComboBox = QComboBox()
        self.inactive_mods_sort_combobox.setParent(self)
        self.inactive_mods_sort_combobox.setObjectName("MainUI")
        self.inactive_mods_sort_combobox.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.inactive_mods_sort_combobox.setToolTip(self.tr("Sort inactive mods by"))
        self.inactive_mods_sort_combobox.addItems(
            [
                self.tr("Name"),
                self.tr("Author"),
                self.tr("Modified Time"),
                self.tr("Folder Size"),
                self.tr("Version"),
                self.tr("PackageId"),
                self.tr("Color"),
            ]
        )
        # Map enum names to translated text for setting initial combo box selection
        key_to_text = {
            "MODNAME": self.tr("Name"),
            "AUTHOR": self.tr("Author"),
            "FILESYSTEM_MODIFIED_TIME": self.tr("Modified Time"),
            "FOLDER_SIZE": self.tr("Folder Size"),
            "VERSION": self.tr("Version"),
            "PACKAGEID": self.tr("PackageId"),
            "MOD_COLOR": self.tr("Color"),
        }
        # Set initial combo box selection based on loaded settings
        self.inactive_mods_sort_combobox.setCurrentText(
            key_to_text.get(self.inactive_mods_sort_key, self.tr("Modified Time"))
        )
        # Sort order toggle (Asc/Desc)
        self.inactive_sort_descending: bool = self.inactive_mods_sort_descending
        self.inactive_mods_sort_order_button: QToolButton = QToolButton()
        self.inactive_mods_sort_order_button.setParent(self)
        self.inactive_mods_sort_order_button.setObjectName("MainUI")
        self.inactive_mods_sort_order_button.setMaximumWidth(60)
        self.inactive_mods_sort_order_button.setToolTip(self.tr("Toggle sort order"))
        self.inactive_mods_sort_order_button.setText(
            self.tr("Desc") if self.inactive_mods_sort_descending else self.tr("Asc")
        )
        # Single row: search on the left, sort on the right
        toolbar_row = QHBoxLayout()
        toolbar_row.addWidget(self.inactive_mods_filter_data_source_button)
        if self.settings_controller.settings.mod_type_filter:
            toolbar_row.addWidget(self.inactive_data_source_filter_type_button)
        toolbar_row.addWidget(self.inactive_mods_search_mode_filter_button)
        toolbar_row.addWidget(self.inactive_mods_search, 0)
        toolbar_row.addWidget(self.inactive_mods_search_filter, 0)
        toolbar_row.addStretch(1)
        sort_label = QLabel(self.tr("Sort by:"))
        sort_label.setObjectName("MainUI")
        toolbar_row.addWidget(sort_label)
        toolbar_row.addWidget(self.inactive_mods_sort_combobox)
        toolbar_row.addWidget(self.inactive_mods_sort_order_button)
        self.inactive_mods_search_layout.addLayout(toolbar_row)

        # Adding Completer.
        # self.completer = QCompleter(self.active_mods_list.get_list_items())
        # self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        # self.active_mods_search.setCompleter(self.completer)
        # self.inactive_mods_search.setCompleter(self.completer)

        # Connect signals and slots

    def connect_signals(self) -> None:
        self.active_mods_list.list_update_signal.connect(
            self.on_active_mods_list_updated
        )
        self.inactive_mods_list.list_update_signal.connect(
            self.on_inactive_mods_list_updated
        )
        self.active_mods_list.recalculate_warnings_signal.connect(
            partial(self.recalculate_list_errors_warnings, list_type="Active")
        )
        self.inactive_mods_list.recalculate_warnings_signal.connect(
            partial(self.recalculate_list_errors_warnings, list_type="Inactive")
        )
        self.inactive_mods_sort_combobox.currentTextChanged.connect(
            self.on_inactive_mods_sort_changed
        )
        self.inactive_mods_sort_order_button.clicked.connect(
            self.on_inactive_mods_sort_order_toggled
        )

    def on_inactive_mods_sort_order_toggled(self) -> None:
        """
        Handle the Asc/Desc toggle button click for inactive mods sorting.

        Toggles the sort direction, updates the button label, saves the state
        if enabled, and re-sorts the list with the new direction.
        """
        # Toggle state and update button label
        self.inactive_sort_descending = not self.inactive_sort_descending
        self.inactive_mods_sort_order_button.setText(
            self.tr("Desc") if self.inactive_sort_descending else self.tr("Asc")
        )

        # Always persist the sort direction
        self.settings_controller.settings.inactive_mods_sort_descending = (
            self.inactive_sort_descending
        )
        self.settings_controller.settings.save()

        # Apply updated sort direction - re-sort with new descending flag
        if self.settings_controller.settings.inactive_mods_sorting:
            current_text = self.inactive_mods_sort_combobox.currentText()
            # Re-sort list with updated descending flag
            self.on_inactive_mods_sort_changed(current_text)

    @Slot(int, int)
    def _on_folder_size_progress(self, current: int, total: int) -> None:
        """
        Update the progress dialog during folder size calculation.

        Slot for FolderSizeWorker.progress signal. Updates the progress dialog
        with the current progress (current/total items processed).

        Args:
            current: Current number of items processed
            total: Total number of items to process
        """
        if hasattr(self, "_size_progress_dialog") and self._size_progress_dialog:
            self._size_progress_dialog.setMaximum(total)
            self._size_progress_dialog.setValue(current)

    @Slot(dict)
    def _on_folder_size_finished(self, sizes: dict[str, int]) -> None:
        """
        Handle completion of folder size calculation.

        Slot for FolderSizeWorker.finished signal. Sorts the inactive mods list
        by computed folder sizes, rebuilds the UI with the sorted order,
        and cleans up the background worker and progress dialog.

        Args:
            sizes: Dictionary mapping mod UUID -> folder size in bytes
        """
        try:
            # Sort and rebuild with visible progress to avoid post-close pause
            current_uuids: list[str] = getattr(self, "_size_current_uuids", [])
            sorted_uuids = sorted(
                current_uuids,
                key=lambda u: sizes.get(u, 0),
                reverse=self.inactive_sort_descending,
            )
            if hasattr(self, "_size_progress_dialog") and self._size_progress_dialog:
                self._size_progress_dialog.setLabelText(self.tr("Rebuilding list..."))
                self._size_progress_dialog.setRange(0, len(sorted_uuids))
                self._size_progress_dialog.setValue(0)

            lw = self.inactive_mods_list
            # Disconnect model signals during rebuild to prevent cascading updates and duplicate items
            lw.setUpdatesEnabled(False)
            try:
                lw.model().rowsInserted.disconnect(lw.handle_rows_inserted)
            except TypeError:
                pass  # Signal not connected
            try:
                lw.model().rowsAboutToBeRemoved.disconnect(lw.handle_rows_removed)
            except TypeError:
                pass  # Signal not connected

            lw.clear()
            lw.uuids = list()

            # Get aux controller once for performance
            aux_metadata_controller = (
                AuxMetadataController.get_or_create_cached_instance(
                    self.settings_controller.settings.aux_db_path
                )
            )

            # OPTIMIZATION 1: Single DB session for all mods instead of per-mod
            with aux_metadata_controller.Session() as aux_metadata_session:
                for idx, uuid_key in enumerate(sorted_uuids, start=1):
                    list_item = CustomListWidgetItem(lw)
                    # Create metadata with aux controller to reduce lookups
                    data = CustomListWidgetItemMetadata(
                        uuid=uuid_key,
                        list_type=lw.list_type,
                        settings_controller=self.settings_controller,
                        aux_metadata_controller=aux_metadata_controller,
                        aux_metadata_session=aux_metadata_session,
                    )
                    list_item.setData(Qt.ItemDataRole.UserRole, data)
                    lw.addItem(list_item)
                    if (
                        hasattr(self, "_size_progress_dialog")
                        and self._size_progress_dialog
                    ):
                        self._size_progress_dialog.setValue(idx)
            lw.uuids = sorted_uuids

            # Reconnect model signals
            lw.model().rowsInserted.connect(
                lw.handle_rows_inserted, Qt.ConnectionType.QueuedConnection
            )
            lw.model().rowsAboutToBeRemoved.connect(
                lw.handle_rows_removed, Qt.ConnectionType.QueuedConnection
            )
            lw.setUpdatesEnabled(True)
            lw.repaint()
            # Load visible widgets after rebuild completes
            lw.check_widgets_visible()
            # Emit signal to update counts and errors/warnings
            lw.list_update_signal.emit(str(lw.count()))
        finally:
            if hasattr(self, "_size_progress_dialog") and self._size_progress_dialog:
                self._size_progress_dialog.close()
                self._size_progress_dialog = None
            QApplication.restoreOverrideCursor()
            if hasattr(self, "_size_thread") and self._size_thread:
                # Let the thread finish asynchronously and clean up safely
                self._size_thread.quit()
                self._size_thread.deleteLater()
                self._size_thread = None
            if hasattr(self, "_size_worker") and self._size_worker:
                try:
                    self._size_worker.deleteLater()
                except Exception:
                    pass
                self._size_worker = None

    def _execute_pending_sort(self) -> None:
        """
        Execute the pending sort operation after debounce timer expires.

        Non-heavy sorts (Name, Author, etc.) are debounced to prevent rapid
        rebuilds. This method executes the actual sort after the debounce delay.

        Uses _pending_sort_params stored by on_inactive_mods_sort_changed.
        """
        if self._pending_sort_params:
            list_type, uuids, key, descending = self._pending_sort_params
            self._pending_sort_params = None
            # Get the appropriate list widget and call recreate_mod_list_and_sort
            mod_list = (
                self.active_mods_list
                if list_type == "Active"
                else self.inactive_mods_list
            )
            mod_list.recreate_mod_list_and_sort(list_type, uuids, key, descending)

    @staticmethod
    def _text_to_sort_key(text: str) -> ModsPanelSortKey:
        """
        Convert combobox text to sort key enum.

        Uses SORT_TEXT_TO_KEY_MAP constant for centralized text-to-enum mapping.
        Falls back to FILESYSTEM_MODIFIED_TIME if text is not found.

        Args:
            text: The selected sort option text from the combobox
                 (e.g., "Name", "Author", "Folder Size")

        Returns:
            ModsPanelSortKey enum corresponding to the text, or
            FILESYSTEM_MODIFIED_TIME if not found
        """
        return ModsPanel.SORT_TEXT_TO_KEY_MAP.get(
            text,
            ModsPanelSortKey.FILESYSTEM_MODIFIED_TIME,  # Default fallback
        )

    def on_inactive_mods_sort_changed(self, text: str) -> None:
        """
        Handle selection change in the inactive mods sort combobox.

        Determines whether to use background calculation (for folder size sorting)
        or debounced fast sorting (for other sorts). Folder size sorting requires
        filesystem I/O and is calculated in the background. Other sorts are fast
        data-only lookups and use debouncing to prevent rapid rebuilds.

        Args:
            text: The selected sort option text from the combobox
        """
        # Check if inactive mods sorting is enabled
        if not self.settings_controller.settings.inactive_mods_sorting:
            return

        # Convert combobox text to sort key enum
        sort_key = self._text_to_sort_key(text)

        # Get current list of UUIDs to sort
        current_uuids = self.inactive_mods_list.uuids.copy()
        if current_uuids:
            # Folder size sorting requires background calculation
            # Other sorts are fast data lookups using debounce
            is_heavy = sort_key == ModsPanelSortKey.FOLDER_SIZE
            if is_heavy:
                # Background calculation required for folder size sorting
                dlg = QProgressDialog(self)
                dlg.setLabelText(self.tr("Calculating folder sizes..."))
                # Set up dialog without cancel button (calculation cannot be interrupted)
                dlg.setCancelButton(None)
                dlg.setRange(0, len(current_uuids))
                dlg.setWindowModality(Qt.WindowModality.WindowModal)
                dlg.setMinimumDuration(0)
                dlg.setAutoClose(True)
                dlg.setAutoReset(True)
                dlg.setValue(0)
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                # Start worker thread
                thr = QThread(self)
                self._size_thread = thr
                self._size_current_uuids = current_uuids
                worker = FolderSizeWorker(current_uuids)
                self._size_worker = worker
                worker.moveToThread(thr)
                worker.progress.connect(self._on_folder_size_progress)
                worker.finished.connect(self._on_folder_size_finished)
                thr.started.connect(worker.run)
                thr.start()
                self._size_progress_dialog = dlg
                dlg.show()
            else:
                # Non-heavy sorts use debouncing to prevent rapid rebuilds
                # Store pending sort parameters
                self._pending_sort_params = (
                    "Inactive",
                    current_uuids,
                    sort_key,
                    self.inactive_sort_descending,
                )

                # Cancel pending sort and start new timer (200ms debounce delay)
                self._sort_debounce_timer.stop()
                self._sort_debounce_timer.start(200)

                # Always persist the sort key
                self.settings_controller.settings.inactive_mods_sort_key = (
                    sort_key.name
                )
                self.settings_controller.settings.save()
                self.inactive_mods_sort_key = sort_key.name

    def mod_list_updated(
        self, count: str, list_type: str, recalculate_list_errors_warnings: bool = True
    ) -> None:
        # If count is 'drop', it indicates that the update was just a drag and drop within the list
        if count != "drop":
            logger.info(f"{list_type} mod count changed to: {count}")
            self.update_count(list_type=list_type)
        # Signal save button animation
        self.save_btn_animation_signal.emit()
        if recalculate_list_errors_warnings:
            # Update the mod list widget errors and warnings
            self.recalculate_list_errors_warnings(list_type=list_type)

    def on_active_mods_list_updated(self, count: str) -> None:
        self.mod_list_updated(count=count, list_type="Active")

    def on_active_mods_search(self, pattern: str) -> None:
        self.signal_search_and_filters(
            list_type="Active",
            pattern=pattern,
        )

    def on_active_mods_search_clear(self) -> None:
        self.signal_clear_search(
            list_type="Active",
        )

    def on_active_mods_search_data_source_filter(self) -> None:
        self.signal_search_source_filter(list_type="Active")

    def on_active_mods_search_data_source_filter_type(self) -> None:
        self.apply_mods_filter_type(list_type="Active")

    def on_active_mods_mode_filter_toggle(self) -> None:
        self.signal_search_mode_filter(list_type="Active")

    def on_inactive_mods_list_updated(self, count: str) -> None:
        self.mod_list_updated(count=count, list_type="Inactive")

    def on_inactive_mods_search(self, pattern: str) -> None:
        self.signal_search_and_filters(
            list_type="Inactive",
            pattern=pattern,
        )

    def on_inactive_mods_search_clear(self) -> None:
        self.signal_clear_search(
            list_type="Inactive",
        )

    def on_inactive_mods_search_data_source_filter(self) -> None:
        self.signal_search_source_filter(list_type="Inactive")

    def on_inactive_mods_search_data_source_filter_type(self) -> None:
        self.apply_mods_filter_type(list_type="Inactive")

    def on_inactive_mods_mode_filter_toggle(self) -> None:
        self.signal_search_mode_filter(list_type="Inactive")

    def on_mod_created(self, uuid: str) -> None:
        self.inactive_mods_list.append_new_item(uuid)

    def apply_mods_filter_type(self, list_type: str) -> None:
        # Define the mod types
        mod_types = ["csharp", "xml"]
        source_filter_index: int = (
            self.active_data_source_filter_type_index
            or self.inactive_data_source_filter_type_index
        )

        if list_type == "Active":
            button = self.active_data_source_filter_type_button
            search = self.active_mods_search
            source_index = source_filter_index
        elif list_type == "Inactive":
            button = self.inactive_data_source_filter_type_button
            search = self.inactive_mods_search
            source_index = source_filter_index
        else:
            raise NotImplementedError(f"Unknown list type: {list_type}")

        # Update the filter index
        if source_index < (len(self.data_source_filter_type_icons) - 1):
            source_index += 1
        else:
            source_index = 0

        button.setIcon(self.data_source_filter_type_icons[source_index])
        button.setToolTip(self.data_source_filter_type_tooltips[source_index])

        # Update the relevant index for the list type
        if list_type == "Active":
            self.active_data_source_filter_type_index = source_index
            self.active_mods_data_source_filter_type = (
                SEARCH_DATA_SOURCE_FILTER_INDEXES[source_index]
            )
        elif list_type == "Inactive":
            self.inactive_data_source_filter_type_index = source_index
            self.inactive_mods_data_source_filter_type = (
                SEARCH_DATA_SOURCE_FILTER_INDEXES[source_index]
            )

        mod_list = (
            self.active_mods_list if list_type == "Active" else self.inactive_mods_list
        )

        # Apply filtering based on the selected type
        for idx, uuid in enumerate(mod_list.uuids):
            if is_divider_uuid(uuid):
                continue
            item = mod_list.item(idx)
            item_data = item.data(Qt.ItemDataRole.UserRole)

            # Determine the mod type
            mod_type = (
                "csharp"
                if self.metadata_manager.internal_local_metadata.get(uuid, {}).get(
                    "csharp"
                )
                else "xml"
            )
            if mod_type and mod_types:
                item.setData(Qt.ItemDataRole.UserRole, item_data)

        if source_index == 0:
            filters_active = False
        else:
            filters_active = True
        # Trigger search and filters
        self.signal_search_and_filters(
            list_type=list_type,
            pattern=search.text(),
            filters_active=filters_active,
        )

    def on_mod_deleted(self, uuid: str) -> None:
        if uuid in self.active_mods_list.uuids:
            index = self.active_mods_list.uuids.index(uuid)
            self.active_mods_list.takeItem(index)
            self.active_mods_list.uuids.pop(index)
            self.update_count(list_type="Active")
        elif uuid in self.inactive_mods_list.uuids:
            index = self.inactive_mods_list.uuids.index(uuid)
            self.inactive_mods_list.takeItem(index)
            self.inactive_mods_list.uuids.pop(index)
            self.update_count(list_type="Inactive")

    def on_mod_metadata_updated(self, uuid: str) -> None:
        if uuid in self.active_mods_list.uuids:
            self.active_mods_list.rebuild_item_widget_from_uuid(uuid=uuid)
        elif uuid in self.inactive_mods_list.uuids:
            self.inactive_mods_list.rebuild_item_widget_from_uuid(uuid=uuid)

    def recalculate_list_errors_warnings(self, list_type: str) -> None:
        """
        Update the errors/warnings summary frame with current mod list status.

        For Active mods: displays errors, warnings, and new mods count.
        For Inactive mods: only recalculates internal state (no display update).

        Args:
            list_type: "Active" or "Inactive" to specify which list to process
        """
        if list_type == "Active":
            # Ensure all visible items have their widgets properly loaded
            self.active_mods_list.check_widgets_visible()
            
            # Calculate internal errors and warnings for all mods in the list
            total_error_text, total_warning_text, num_errors, num_warnings = (
                self.active_mods_list.recalculate_internal_errors_warnings()
            )

            # Count new mods (not in latest save). Only if save comparison is enabled
            new_count = 0
            if self.settings_controller.settings.show_save_comparison_indicators:
                try:
                    for item in self.active_mods_list.get_all_mod_list_items():
                        if item.data(Qt.ItemDataRole.UserRole).__dict__.get(
                            "is_new", False
                        ):
                            new_count += 1
                except Exception:
                    pass

            padding = " "
            has_errors_warnings = (
                total_error_text or total_warning_text or num_errors or num_warnings
            )

            # Show summary frame only if there are errors, warnings, or new mods to display
            self.errors_summary_frame.setHidden(
                not (has_errors_warnings or new_count > 0)
            )

            # Update error and warning counts/tooltips (show 0 if none exist)
            self.warnings_text.setText(
                self.tr("{padding}{num} warning(s)").format(
                    padding=padding, num=num_warnings
                )
            )
            self.errors_text.setText(
                self.tr("{padding}{num} error(s)").format(
                    padding=padding, num=num_errors
                )
            )
            self.errors_icon.setToolTip(
                total_error_text.lstrip() if total_error_text else ""
            )
            self.warnings_icon.setToolTip(
                total_warning_text.lstrip() if total_warning_text else ""
            )

            # Update new mods display (icon and count)
            # Hide icon and text if no new mods, otherwise show with count
            self.new_icon.setHidden(new_count == 0)
            self.new_text.setHidden(new_count == 0)
            self.new_text.setText(
                self.tr("{padding}{count} new").format(padding=padding, count=new_count)
                if new_count > 0
                else self.tr("0 new")
            )

            # First time and refresh: the slot will evaluate false and do nothing.
            # Purpose: triggers the _do_save_animation slot in main_content_panel
            EventBus().list_updated_signal.emit()
        else:
            # For Inactive list: only update internal state, no display updates
            self.inactive_mods_list.check_widgets_visible()
            self.inactive_mods_list.recalculate_internal_errors_warnings()

    def signal_clear_search(
        self,
        list_type: str,
    ) -> None:
        if list_type == "Active":
            self.active_mods_search.clear()
            self.signal_search_and_filters(
                list_type=list_type,
                pattern="",
            )
            self.active_mods_search.clearFocus()
        elif list_type == "Inactive":
            self.inactive_mods_search.clear()
            self.signal_search_and_filters(
                list_type=list_type,
                pattern="",
            )
            self.inactive_mods_search.clearFocus()

    def search_mod_notes(self, pattern: str, limit: int = 5000) -> set[str]:
        """Searches mod notes using fuzzy search, returning mod paths matching search pattern."""
        if not pattern.strip():
            return set()

        pattern = pattern.strip().lower()
        SEARCH_SQL = text("""
            SELECT path, user_notes
            FROM auxiliary_metadata
            LIMIT :limit;
        """)

        aux_metadata_controller = (
            AuxMetadataController.get_or_create_cached_instance(
                self.settings_controller.settings.aux_db_path
            )
        )
        with aux_metadata_controller.engine.connect() as conn:
            result = conn.execute(SEARCH_SQL, {"limit": limit})
            rows = result.fetchall()

        #TODO: Allow user to set fuzzy threshold?
        fuzz_threshold = 80 if len(pattern) > 5 else 70
        matching_paths = set()
        for path, note in rows:
            note = (note or "").lower()

            score = fuzz.partial_ratio(pattern, note)
            if score >= fuzz_threshold:
                matching_paths.add(path)

        return matching_paths

    def signal_search_and_filters(
        self,
        list_type: str,
        pattern: str,
        filters_active: bool = False,
    ) -> None:
        """
        Performs a search and/or applies filters based on the given parameters.

        Called anytime the search bar text changes or the filters change.

        Args:
            list_type (str): The type of list to search within (Active or Inactive).
            pattern (str): The pattern to search for.
            filters_active (bool): If any filter is active (inc. pattern search).
        """
        _filter = None
        filter_state = None  # The 'Hide Filter' state
        source_filter = None
        uuids = None
        # Notify controller when search bar text or any filters change
        if list_type == "Active":
            EventBus().filters_changed_in_active_modlist.emit()
        elif list_type == "Inactive":
            EventBus().filters_changed_in_inactive_modlist.emit()
        # Determine which list to filter
        if list_type == "Active":
            _filter = self.active_mods_search_filter
            filter_state = self.active_mods_search_filter_state
            source_filter = self.active_mods_data_source_filter
            uuids = self.active_mods_list.uuids
        elif list_type == "Inactive":
            _filter = self.inactive_mods_search_filter
            filter_state = self.inactive_mods_search_filter_state
            source_filter = self.inactive_mods_data_source_filter
            uuids = self.inactive_mods_list.uuids
        else:
            raise NotImplementedError(f"Unknown list type: {list_type}")
        # Evaluate the search filter state for the list
        # consider using currentData() instead of currentText()
        search_filter = None
        if _filter.currentText() == self.tr("Name"):
            search_filter = "name"
        if _filter.currentText() == self.tr("Notes"):
            search_filter = "notes"
        elif _filter.currentText() == self.tr("PackageId"):
            search_filter = "packageid"
        elif _filter.currentText() == self.tr("Author(s)"):
            search_filter = "authors"
        elif _filter.currentText() == self.tr("PublishedFileId"):
            search_filter = "publishedfileid"
        elif _filter.currentText() == self.tr("Version"):
            search_filter = "version"
        # Filter the list using any search and filter state
        num_filtered = 0
        num_unfiltered = 0
        if pattern.strip() and (
            search_filter == "notes" or
            (search_filter == "name" and self.settings_controller.settings.include_mod_notes_in_mod_name_filter)):
            matches = self.search_mod_notes(pattern)
        for idx, uuid in enumerate(uuids):
            item = (
                self.active_mods_list.item(idx)
                if list_type == "Active"
                else self.inactive_mods_list.item(idx)
            )
            if item is None:
                continue
            if is_divider_uuid(uuid):
                continue
            item_data = item.data(Qt.ItemDataRole.UserRole)
            if getattr(item_data, "is_divider", False):
                continue
            # Check if UUID exists in metadata before accessing
            if uuid not in self.metadata_manager.internal_local_metadata:
                continue
            metadata = self.metadata_manager.internal_local_metadata[uuid]
            if pattern != "":
                filters_active = True
            # Hide invalid items if enabled in settings
            if self.settings_controller.settings.hide_invalid_mods_when_filtering:
                invalid = item_data["invalid"]
                if invalid and filters_active:
                    item_data["filtered"] = True
                    item.setHidden(True)
                    continue
                elif invalid and not filters_active:
                    item_data["filtered"] = False
                    item.setHidden(False)
            # Check if the item is filtered
            item_filtered = item_data["filtered"]
            # Check if the item should be filtered or not based on search filter
            if search_filter == "version" and pattern:
                versions = metadata.get("supportedversions", {}).get("li", [])
                if isinstance(versions, str):
                    versions = [versions]
                if not versions or not any(
                    pattern.lower() in v.lower() for v in versions
                ):
                    item_filtered = True
            elif search_filter == "notes":
                if not pattern.strip():
                    item_filtered = False
                else:
                    mod_path = metadata.get("path", "")
                    item_filtered = mod_path not in matches
            # Filter by name and mod notes
            elif search_filter == "name" and self.settings_controller.settings.include_mod_notes_in_mod_name_filter:
                if not pattern.strip():
                    item_filtered = False
                elif (
                    pattern
                    and metadata.get(search_filter)
                    and pattern.lower() in str(metadata.get(search_filter)).lower()
                ):
                    item_filtered = False
                else:
                    mod_path = metadata.get("path", "")
                    item_filtered = mod_path not in matches
            elif (
                pattern
                and metadata.get(search_filter)
                and pattern.lower() not in str(metadata.get(search_filter)).lower()
            ):
                item_filtered = True
            elif source_filter == "all":  # or data source
                item_filtered = False
            elif source_filter == "git_repo":
                item_filtered = not metadata.get("git_repo")
            elif source_filter == "steamcmd":
                item_filtered = not metadata.get("steamcmd")
            elif source_filter != metadata.get("data_source"):
                item_filtered = True

            type_filter_index = (
                self.active_data_source_filter_type_index
                if list_type == "Active"
                else self.inactive_data_source_filter_type_index
            )

            if type_filter_index == 1 and not metadata.get("csharp"):
                item_filtered = True
            elif type_filter_index == 2 and metadata.get("csharp"):
                item_filtered = True

            # Check if the item should be filtered or hidden based on filter state
            if filter_state:
                item.setHidden(item_filtered)
                if item_filtered:
                    item_data["hidden_by_filter"] = True
                    item_filtered = False
                    num_filtered += 1
                else:
                    item_data["hidden_by_filter"] = False
                    num_unfiltered += 1
            else:
                if item_filtered and item.isHidden():
                    item.setHidden(False)
                    item_data["hidden_by_filter"] = False
                    num_unfiltered += 1

            # Update item data
            item_data["filtered"] = item_filtered
            item.setData(Qt.ItemDataRole.UserRole, item_data)

        self.direct_update_count(list_type, num_filtered, num_unfiltered)
        if list_type == "Active":
            self.active_mods_list.check_widgets_visible()
            self.active_mods_list.apply_collapse_states()
        else:
            self.inactive_mods_list.check_widgets_visible()

    def signal_search_mode_filter(self, list_type: str) -> None:
        if list_type == "Active":
            # Toggle the mode filter state
            self.active_mods_search_filter_state = (
                not self.active_mods_search_filter_state
            )
            # Update the icon based on the current state
            if self.active_mods_search_filter_state:
                self.active_mods_search_mode_filter_button.setIcon(
                    self.mode_filter_icon
                )  # Active state icon
                self.active_mods_search_mode_filter_button.setToolTip(
                    self.mode_filter_tooltip
                )  # Active state tooltip
            else:
                self.active_mods_search_mode_filter_button.setIcon(
                    self.mode_nofilter_icon
                )  # Inactive state icon
                self.active_mods_search_mode_filter_button.setToolTip(
                    self.mode_nofilter_tooltip
                )  # Inactive state tooltip
            pattern = self.active_mods_search.text()
        elif list_type == "Inactive":
            # Toggle the mode filter state
            self.inactive_mods_search_filter_state = (
                not self.inactive_mods_search_filter_state
            )
            # Update the icon based on the current state
            if self.inactive_mods_search_filter_state:
                self.inactive_mods_search_mode_filter_button.setIcon(
                    self.mode_filter_icon
                )  # Active state icon
                self.inactive_mods_search_mode_filter_button.setToolTip(
                    self.mode_filter_tooltip
                )  # Active state tooltip
            else:
                self.inactive_mods_search_mode_filter_button.setIcon(
                    self.mode_nofilter_icon
                )  # Inactive state icon
                self.inactive_mods_search_mode_filter_button.setToolTip(
                    self.mode_nofilter_tooltip
                )  # Inactive state tooltip
            pattern = self.inactive_mods_search.text()
        else:
            raise NotImplementedError(f"Unknown list type: {list_type}")

        self.signal_search_and_filters(list_type=list_type, pattern=pattern)

    def signal_search_source_filter(self, list_type: str) -> None:
        if list_type == "Active":
            button = self.active_mods_filter_data_source_button
            search = self.active_mods_search
            source_index: int = self.active_mods_filter_data_source_index
        elif list_type == "Inactive":
            button = self.inactive_mods_filter_data_source_button
            search = self.inactive_mods_search
            source_index = self.inactive_mods_filter_data_source_index
        else:
            raise NotImplementedError(f"Unknown list type: {list_type}")
        # Indexes by the icon
        if source_index < (len(self.data_source_filter_icons) - 1):
            source_index += 1
        else:
            source_index = 0
        button.setIcon(self.data_source_filter_icons[source_index])
        button.setToolTip(self.data_source_filter_tooltips[source_index])
        if list_type == "Active":
            self.active_mods_filter_data_source_index = source_index
            self.active_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
                source_index
            ]
            self.settings_controller.settings.active_mods_data_source_filter_index = (
                source_index
            )
        elif list_type == "Inactive":
            self.inactive_mods_filter_data_source_index = source_index
            self.inactive_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
                source_index
            ]
            self.settings_controller.settings.inactive_mods_data_source_filter_index = (
                source_index
            )
        self.settings_controller.settings.save()
        if source_index == 0:
            filters_active = False
        else:
            filters_active = True
        # Filter widgets by data source, while preserving any active search pattern
        self.signal_search_and_filters(
            list_type=list_type, pattern=search.text(), filters_active=filters_active
        )

    def direct_update_count(
        self, list_type: str, filtered: int, unfiltered: int
    ) -> None:
        """
        This version of update_count allows you to pass in direct values.

        It does not calculate anything, only updates the label.
        """
        if filtered > 0:
            # If any filter is active, show how many mods are displayed out of total
            list_type_label = (
                self.tr("Active") if list_type == "Active" else self.tr("Inactive")
            )
            label = (
                self.active_mods_label
                if list_type == "Active"
                else self.inactive_mods_label
            )
            label.setText(f"{list_type_label} [{unfiltered}/{filtered + unfiltered}]")
        else:
            list_type_label = (
                self.tr("Active") if list_type == "Active" else self.tr("Inactive")
            )
            label = (
                self.active_mods_label
                if list_type == "Active"
                else self.inactive_mods_label
            )
            label.setText(f"{list_type_label} [{filtered + unfiltered}]")

    def update_count(self, list_type: str) -> None:
        # Calculate filtered items
        list_type_label = (
            self.tr("Active") if list_type == "Active" else self.tr("Inactive")
        )
        label = (
            self.active_mods_label
            if list_type == "Active"
            else self.inactive_mods_label
        )
        search = (
            self.active_mods_search
            if list_type == "Active"
            else self.inactive_mods_search
        )
        uuids = (
            self.active_mods_list.uuids
            if list_type == "Active"
            else self.inactive_mods_list.uuids
        )
        num_filtered = 0
        num_unfiltered = 0
        for idx in range(len(uuids)):
            if is_divider_uuid(uuids[idx]):
                continue
            item = (
                self.active_mods_list.item(idx)
                if list_type == "Active"
                else self.inactive_mods_list.item(idx)
            )
            if item is None:
                continue
            item_data = item.data(Qt.ItemDataRole.UserRole)
            if getattr(item_data, "is_divider", False):
                continue
            item_filtered = item_data["filtered"]

            if item.isHidden() or item_filtered:
                num_filtered += 1
            else:
                num_unfiltered += 1
        if search.text():
            label.setText(
                f"{list_type_label} [{num_unfiltered}/{num_filtered + num_unfiltered}]"
            )
        elif num_filtered > 0:
            # If any filter is active, show how many mods are displayed out of total
            label.setText(
                f"{list_type_label} [{num_unfiltered}/{num_filtered + num_unfiltered}]"
            )
        else:
            label.setText(f"{list_type_label} [{num_filtered + num_unfiltered}]")

    def _on_toggle_translation_status(self, enabled: bool) -> None:
        """
        Toggle the visibility of translation status indicators on mod list items.

        Args:
            enabled (bool): Whether to show or hide the indicators.
        """
        logger.info(f"Toggling translation status: {enabled}")

        # Update state on list widgets
        self.active_mods_list.show_translation_status = enabled
        self.inactive_mods_list.show_translation_status = enabled

        if enabled:
            # Build translation lookup table (packageId -> bool)
            # Find which mods have translations installed
            translation_lookup = self._build_translation_lookup()
            self.active_mods_list.translation_lookup = translation_lookup
            self.inactive_mods_list.translation_lookup = translation_lookup
        else:
            self.active_mods_list.translation_lookup = set()
            self.inactive_mods_list.translation_lookup = set()

        # Update visible items
        for mod_list in [self.active_mods_list, self.inactive_mods_list]:
            for i in range(mod_list.count()):
                item = mod_list.item(i)
                widget = mod_list.itemWidget(item)
                if isinstance(widget, ModListItemInner):
                    if enabled:
                        uuid = widget.uuid  # widget has uuid
                        meta = self.metadata_manager.internal_local_metadata[uuid]
                        pkg_id = meta.get("packageid")
                        data_source = meta.get("data_source")
                        
                        # Official expansions/DLCs have multilingual support built-in
                        is_official_expansion = data_source == "expansion"
                        
                        # Check if this mod itself is a translation mod
                        is_translation_mod = False
                        pfid = meta.get("publishedfileid")
                        if pfid and self.metadata_manager.external_steam_metadata:
                            steam_data = self.metadata_manager.external_steam_metadata.get(pfid, {})
                            tags = steam_data.get("tags", [])
                            tag_set = {tag_item.get("tag", "").lower() for tag_item in tags}
                            is_translation_mod = "translation" in tag_set
                        
                        # Mark as localized if:
                        # 1. Official expansion/DLC (has built-in multilingual support)
                        # 2. Translation mod itself
                        # 3. Has an installed translation
                        has_translation = (
                            is_official_expansion 
                            or is_translation_mod 
                            or (pkg_id in self.active_mods_list.translation_lookup)
                        )
                        widget.update_translation_status(has_translation)
                    else:
                        widget.hide_translation_status()

    def _build_translation_lookup(self) -> set[str]:
        """
        Identify mods that have installed translations.
        
        Uses the same logic as _find_and_open_translations to check Steam Workshop metadata
        for installed translation mods based on:
        1. Translation tag in steamDB
        2. Dependency relationship via publishedfileid

        Returns:
            set[str]: A set of packageIds that have at least one translation mod installed.
        """
        translated_pkg_ids: set[str] = set()

        # Check if Steam metadata is available
        if not self.metadata_manager.external_steam_metadata:
            logger.warning("Steam Workshop metadata database is not loaded for translation lookup")
            return translated_pkg_ids

        # Get all installed mods' publishedfileids
        all_local_metadata = self.metadata_manager.internal_local_metadata
        
        # Build a mapping: pfid -> packageId for all installed mods
        pfid_to_packageid: dict[str, str] = {}
        for uuid, meta in all_local_metadata.items():
            pfid = meta.get("publishedfileid")
            packageid = meta.get("packageid", "")
            if pfid and packageid:
                pfid_to_packageid[pfid] = packageid.lower()
        
        # Iterate through all installed mods to find translations
        for uuid, meta in all_local_metadata.items():
            pfid = meta.get("publishedfileid")
            
            # Skip if this mod doesn't have a publishedfileid (local-only mod)
            if not pfid:
                continue
                
            # Check if this mod exists in Steam metadata
            if pfid not in self.metadata_manager.external_steam_metadata:
                continue
            
            steam_data = self.metadata_manager.external_steam_metadata[pfid]
            tags = steam_data.get("tags", [])
            
            # Build tag set for fast lookups
            tag_set = {tag_item.get("tag", "").lower() for tag_item in tags}
            
            # Check if this mod has "translation" tag
            if "translation" not in tag_set:
                continue
            
            # Check dependencies to find target mods
            dependencies = steam_data.get("dependencies", {})
            
            # For each dependency, if it's an installed mod, mark it as having a translation
            for dep_pfid in dependencies.keys():
                # Check if the dependency is an installed mod
                if dep_pfid in pfid_to_packageid:
                    target_packageid = pfid_to_packageid[dep_pfid]
                    translated_pkg_ids.add(target_packageid)
                    logger.debug(f"Found translation {meta.get('name')} for mod with packageId {target_packageid}")
                
        return translated_pkg_ids

    def _on_auto_add_translations(self) -> None:
        """
        Automatically find and add translation mods for active mods.
        Uses Steam Workshop metadata to reliably identify translations.
        """
        logger.info("Auto-adding translation mods...")
        
        # Check if Steam metadata is available
        if not self.metadata_manager.external_steam_metadata:
            logger.warning("Steam Workshop metadata database is not loaded for auto-add translations")
            show_warning(
                self.tr("Database not available"),
                self.tr(
                    "Steam Workshop metadata database is not loaded. "
                    "Please build the database first using the Database Builder."
                ),
            )
            return
        
        active_uuids = [
            u for u in self.active_mods_list.uuids if not is_divider_uuid(u)
        ]
        all_local_metadata = self.metadata_manager.internal_local_metadata
        
        # Build a mapping: pfid -> uuid for all installed mods
        pfid_to_uuid: dict[str, str] = {}
        for uuid, meta in all_local_metadata.items():
            pfid = meta.get("publishedfileid")
            if pfid:
                pfid_to_uuid[pfid] = uuid
        
        # Get active mods' publishedfileids
        active_pfids = set()
        for uuid in active_uuids:
            pfid = all_local_metadata[uuid].get("publishedfileid")
            if pfid:
                active_pfids.add(pfid)
        
        mods_to_add: list[str] = []
        
        # Find translations for active mods
        for uuid, meta in all_local_metadata.items():
            if uuid in active_uuids:
                continue  # Already active
            
            pfid = meta.get("publishedfileid")
            
            # Skip if this mod doesn't have a publishedfileid (local-only mod)
            if not pfid:
                continue
            
            # Check if this mod exists in Steam metadata
            if pfid not in self.metadata_manager.external_steam_metadata:
                continue
            
            steam_data = self.metadata_manager.external_steam_metadata[pfid]
            tags = steam_data.get("tags", [])
            
            # Build tag set for fast lookups
            tag_set = {tag_item.get("tag", "").lower() for tag_item in tags}
            
            # Check if this mod has "translation" tag
            if "translation" not in tag_set:
                continue
            
            # Check if any of its dependencies are active mods
            dependencies = steam_data.get("dependencies", {})
            
            # Check if this translation targets any active mod
            targets_active_mod = False
            target_mod_name = ""
            for dep_pfid in dependencies.keys():
                if dep_pfid in active_pfids:
                    targets_active_mod = True
                    # Get the target mod's name for similarity check
                    target_uuid = pfid_to_uuid.get(dep_pfid)
                    if target_uuid and target_uuid in all_local_metadata:
                        target_mod_name = all_local_metadata[target_uuid].get("name", "")
                    logger.debug(f"Found translation {meta.get('name')} for active mod with pfid {dep_pfid}")
                    break
            
            if targets_active_mod:
                # Calculate similarity score to filter out false positives
                trans_name = meta.get("name", "")
                similarity = self.active_mods_list._calculate_translation_similarity(
                    target_mod_name, trans_name
                )
                
                SIMILARITY_THRESHOLD = 0.5
                if similarity >= SIMILARITY_THRESHOLD:
                    mods_to_add.append(uuid)
                    logger.debug(
                        f"Translation '{trans_name}' passed similarity check "
                        f"(score: {similarity:.2f}) for mod '{target_mod_name}'"
                    )
                else:
                    logger.debug(
                        f"Filtered out translation '{trans_name}' due to low similarity "
                        f"(score: {similarity:.2f}) with mod '{target_mod_name}'"
                    )
        
        if not mods_to_add:
            show_warning(
                self.tr("No Translations Found"), 
                self.tr("No applicable translation mods were found for your active mod list.")
            )
            return
        
        # Add found mods to active list
        count = 0
        added_uuids: list[str] = []
        for uuid in mods_to_add:
            if uuid not in self.active_mods_list.uuids:
                # Need to find the item in inactive list
                if uuid in self.inactive_mods_list.uuids:
                    index = self.inactive_mods_list.uuids.index(uuid)
                    item = self.inactive_mods_list.takeItem(index)  # This removes from list widget
                    self.inactive_mods_list.uuids.pop(index)
                    
                    self.active_mods_list.addItem(item)
                    # self.active_mods_list.uuids is updated via handle_rows_inserted signal
                    
                    # Ensure item data is updated (list_type)
                    data = item.data(Qt.ItemDataRole.UserRole)
                    if data:
                        data["list_type"] = "Active"
                        item.setData(Qt.ItemDataRole.UserRole, data)
                    
                    count += 1
                    added_uuids.append(uuid)
        
        if count > 0:
            logger.info(f"Added {count} translation mods.")
            show_warning(
                self.tr("Translations Added"), 
                self.tr(f"Successfully added {count} translation mods to the active list.")
            )
            
            # Also update translation status indicators if enabled
            if self.active_mods_list.show_translation_status:
                self._on_toggle_translation_status(True)
        else:
            logger.info("No new translation mods added (maybe already active).")
            show_warning(
                self.tr("No New Translations"), 
                self.tr("All found translation mods are already active.")
            )
