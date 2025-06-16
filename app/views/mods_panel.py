import json
import os
from enum import Enum
from functools import partial
from pathlib import Path
from shutil import copy2, copytree
from traceback import format_exc
from typing import cast

from loguru import logger
from PySide6.QtCore import QEvent, QModelIndex, QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QCursor,
    QDropEvent,
    QFocusEvent,
    QFontMetrics,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.controllers.settings_controller import SettingsController
from app.utils.app_info import AppInfo
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
    open_url_browser,
    platform_specific_open,
    sanitize_filename,
)
from app.utils.metadata import MetadataManager, ModMetadata
from app.views.deletion_menu import ModDeletionMenu
from app.views.dialogue import (
    show_dialogue_conditional,
    show_dialogue_input,
    show_warning,
)


def uuid_no_key(uuid: str) -> str:
    """
    Returns the UUID of the mod.
    Args:
        uuid (str): The UUID of the mod.
    Returns:
        str: The UUID of the mod.
    """
    return uuid


def uuid_to_mod_name(uuid: str) -> str:
    """
    Converts a UUID to the corresponding mod name.
    Args:
        uuid (str): The UUID of the mod.
    Returns:
        str: If mod name not None, returns mod name in lowercase. Otherwise, returns "# unnamed mod".
    """
    name = MetadataManager.instance().internal_local_metadata[uuid]["name"]
    return name.lower() if name is not None else "# unnamed mod"


class ModsPanelSortKey(Enum):
    """
    Enum class representing different sorting keys for mods.
    """

    NOKEY = 0
    MODNAME = 1


def sort_uuids(uuids: list[str], key: ModsPanelSortKey) -> list[str]:
    """
    Sort the list of UUIDs based on the provided key.
    Args:
        key (ModsPanelSortKey): The key to sort the list by.
    Returns:
        None
    """
    # Sort the list of UUIDs based on the provided key
    if key == ModsPanelSortKey.MODNAME:
        key_function = uuid_to_mod_name
    else:
        return sorted(uuids, key=lambda x: x)
    return sorted(uuids, key=key_function)


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
    ) -> None:
        """
        Initialize the QWidget with mod uuid. Metadata can be accessed via MetadataManager.

        All metadata tags are set to the corresponding field if it
        exists in the metadata dict. See tags:
        https://rimworldwiki.com/wiki/About.xml

        :param errors_warnings: a string of errors and warnings
        :param errors: a string of errors for the notification tooltip
        :param warnings: a string of warnings for the notification tooltip
        :param filtered: a bool representing whether the widget's item is filtered
        :param invalid: a bool representing whether the widget's item is an invalid mod
        :param mismatch: a bool representing whether the widget's item has a version mismatch
        :param alternative: a bool representing whether the widget's item has a recommended alternative mod
        :param settings_controller: an instance of SettingsController for accessing settings
        :param uuid: str, the uuid of the mod which corresponds to a mod's metadata
        """

        super(ModListItemInner, self).__init__()

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

        # All data, including name, author, package id, dependencies,
        # whether the mod is a workshop mod or expansion, etc is encapsulated
        # in this variable. This is exactly equal to the dict value of a
        # single all_mods key-value
        self.uuid = uuid
        self.list_item_name = (
            self.metadata_manager.internal_local_metadata.get(self.uuid, {}).get("name")
            or "METADATA ERROR"
        )
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
        if self.settings_controller.settings.mod_type_filter_toggle:
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
        self.warning_icon_label.clicked.connect(
            partial(
                self.toggle_warning_signal.emit,
                self.metadata_manager.internal_local_metadata[self.uuid]["packageid"],
                self.uuid,
            )
        )
        self.warning_icon_label.setPixmap(
            ModListIcons.warning_icon().pixmap(QSize(20, 20))
        )
        # Default to hidden to avoid showing early
        self.warning_icon_label.setHidden(True)
        # Error icon hidden by default
        self.error_icon_label = ClickableQLabel()
        self.error_icon_label.clicked.connect(
            partial(
                self.toggle_error_signal.emit,
                self.metadata_manager.internal_local_metadata[self.uuid]["packageid"],
                self.uuid,
            )
        )
        self.error_icon_label.setPixmap(ModListIcons.error_icon().pixmap(QSize(20, 20)))
        # Default to hidden to avoid showing early
        self.error_icon_label.setHidden(True)
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
        # Set label color if mod has errors/warnings
        if self.filtered:
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

    def count_icons(self, widget: QObject) -> int:
        count = 0
        if isinstance(widget, QLabel):
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
        path_line = f"Path: {path}"

        return "".join(
            [
                name_line,
                author_line,
                package_id_line,
                modversion_line,
                supported_versions_line,
                path_line,
            ]
        )

    def get_icon(self) -> QIcon:  # type: ignore
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

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        When the label is resized (as the window is resized),
        also elide the label if needed.

        :param event: the resize event
        """

        # Count the number of QLabel widgets with QIcon and calculate total icon width
        icon_count = self.count_icons(self)
        icon_width = icon_count * 20
        self.item_width = super().width()
        text_width_needed = QRectF(
            self.font_metrics.boundingRect(self.list_item_name)
        ).width()
        if text_width_needed > self.item_width - icon_width:
            available_width = self.item_width - icon_width
            shortened_text = self.font_metrics.elidedText(
                self.list_item_name, Qt.TextElideMode.ElideRight, int(available_width)
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
        # Recalculate the widget label's styling based on item data
        widget_object_name = self.main_label.objectName()
        if item_data["filtered"]:
            new_widget_object_name = "ListItemLabelFiltered"
        elif error_tooltip or warning_tooltip:
            new_widget_object_name = "ListItemLabelInvalid"
        else:
            new_widget_object_name = "ListItemLabel"
        if widget_object_name != new_widget_object_name:
            logger.debug("Repolishing: " + new_widget_object_name)
            self.main_label.setObjectName(new_widget_object_name)
            self.main_label.style().unpolish(self.main_label)
            self.main_label.style().polish(self.main_label)


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

    _ludeon_icon: QIcon | None = None
    _local_icon: QIcon | None = None
    _steam_icon: QIcon | None = None
    _csharp_icon: QIcon | None = None
    _xml_icon: QIcon | None = None
    _git_icon: QIcon | None = None
    _steamcmd_icon: QIcon | None = None
    _warning_icon: QIcon | None = None
    _error_icon: QIcon | None = None

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


class ModListWidget(QListWidget):
    """
    Subclass for QListWidget. Used to store lists for
    active and inactive mods. Mods can be rearranged within
    their own lists or moved from one list to another.
    """

    edit_rules_signal = Signal(bool, str, str)
    item_added_signal = Signal(str)
    key_press_signal = Signal(str)
    list_update_signal = Signal(str)
    mod_info_signal = Signal(str)
    recalculate_warnings_signal = Signal()
    refresh_signal = Signal()
    update_git_mods_signal = Signal(list)
    steamdb_blacklist_signal = Signal(list)
    steamcmd_downloader_signal = Signal(list)
    steamworks_subscription_signal = Signal(list)

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
        self.model().rowsInserted.connect(
            self.handle_rows_inserted, Qt.ConnectionType.QueuedConnection
        )

        # Handle removing items to update count
        self.model().rowsAboutToBeRemoved.connect(
            self.handle_rows_removed, Qt.ConnectionType.QueuedConnection
        )

        # Lazy load ModListItemInner
        self.verticalScrollBar().valueChanged.connect(self.check_widgets_visible)

        # This set is used to keep track of mods that have been loaded
        # into widgets. Used for an optimization strategy for `handle_rows_inserted`
        self.uuids: list[str] = []
        self.ignore_warning_list: list[str] = []

        self.deletion_sub_menu = ModDeletionMenu(
            self._get_selected_metadata,
            self.uuids,
        )  # TDOD: should we enable items conditionally? For now use all
        logger.debug("Finished ModListW`idget initialization")

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
        # Find the newly dropped items and convert to CustomListWidgetItem
        # TODO: Optimize this by only converting the dropped items (Figure out how to get their indexes)
        for i in range(self.count()):
            item = self.item(i)
            if not isinstance(item, CustomListWidgetItem):
                # Convert to CustomListWidgetItem
                item = CustomListWidgetItem(item)
                self.replaceItemAtIndex(i, item)
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
                metadata.append(
                    self.metadata_manager.internal_local_metadata[item_data["uuid"]]
                )
        return metadata

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
            # Unsubscribe + delete mod
            unsubscribe_mod_steam_action = None

            # Get all selected CustomListWidgetItems
            selected_items = self.selectedItems()
            # Single item selected
            if len(selected_items) == 1:
                logger.debug(f"{len(selected_items)} items selected")
                source_item = selected_items[0]
                if type(source_item) is CustomListWidgetItem:
                    item_data = source_item.data(Qt.ItemDataRole.UserRole)
                    uuid = item_data["uuid"]
                    # Retrieve metadata
                    mod_metadata = self.metadata_manager.internal_local_metadata[uuid]
                    mod_data_source = mod_metadata.get("data_source")
                    # Open folder action text
                    open_folder_action = QAction()
                    open_folder_action.setText(self.tr("Open folder"))
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
            # Multiple items selected
            elif len(selected_items) > 1:  # Multiple items selected
                for source_item in selected_items:
                    if type(source_item) is CustomListWidgetItem:
                        item_data = source_item.data(Qt.ItemDataRole.UserRole)
                        uuid = item_data["uuid"]
                        # Retrieve metadata
                        mod_metadata = self.metadata_manager.internal_local_metadata[
                            uuid
                        ]
                        mod_data_source = mod_metadata.get("data_source")
                        # Open folder action text
                        open_folder_action = QAction()
                        open_folder_action.setText(self.tr("Open folder(s)"))
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
                        if not toggle_warning_action:
                            toggle_warning_action = QAction()
                            toggle_warning_action.setText(self.tr("Toggle warning(s)"))
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
            if open_url_browser_action:
                context_menu.addAction(open_url_browser_action)
            if open_mod_steam_action:
                context_menu.addAction(open_mod_steam_action)
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
            # Execute QMenu and return it's ACTION
            action = context_menu.exec_(self.mapToGlobal(pos_local))
            if action:  # Handle the action for all selected items
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
                    if answer == "&Yes":
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
                    if answer == "&Yes":
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
                        # Purge any deleted SteamCMD mods from acf metadata
                        if steamcmd_acf_pfid_purge:
                            self.metadata_manager.steamcmd_purge_mods(
                                publishedfileids=steamcmd_acf_pfid_purge
                            )
                        # Emit signal to steamcmd downloader to re-download
                        logger.debug(
                            f"Emitting steamcmd_downloader_signal for {list(steamcmd_publishedfileid_to_redownload)}"
                        )
                        self.steamcmd_downloader_signal.emit(
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
                            "You have selected {len} mods for unsubscribe + re-subscribe."
                        ).format(len=len(publishedfileids)),
                        information=self.tr(
                            "\nThis operation will potentially delete .dds textures leftover. Steam is unreliable for this. Do you want to proceed?"
                        ),
                    )
                    if answer == "&Yes":
                        logger.debug(
                            f"Unsubscribing + re-subscribing to {len(publishedfileids)} mod(s)"
                        )
                        for path in steam_mod_paths:
                            delete_files_except_extension(
                                directory=path, extension=".dds"
                            )
                        self.steamworks_subscription_signal.emit(
                            [
                                "resubscribe",
                                [eval(str_pfid) for str_pfid in publishedfileids],
                            ]
                        )
                    return True
                elif (  # ACTION: Unsubscribe & delete mod(s) with steam
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
                    if answer == "&Yes":
                        logger.debug(
                            f"Unsubscribing from {len(publishedfileids)} mod(s)"
                        )
                        self.steamworks_subscription_signal.emit(
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

                    args, ok = show_dialogue_input(
                        title=self.tr("Add comment"),
                        label=self.tr(
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
                    if answer == "&Yes":
                        self.steamdb_blacklist_signal.emit(
                            [steamdb_remove_blacklist, False]
                        )
                    return True
                # Execute action for each selected mod
                for source_item in selected_items:
                    if type(source_item) is CustomListWidgetItem:
                        item_data = source_item.data(Qt.ItemDataRole.UserRole)
                        uuid = item_data["uuid"]
                        # Retrieve metadata
                        mod_metadata = self.metadata_manager.internal_local_metadata[
                            uuid
                        ]
                        mod_data_source = mod_metadata.get("data_source")
                        mod_path = mod_metadata["path"]
                        # Toggle warning action
                        if action == toggle_warning_action:
                            self.toggle_warning(mod_metadata["packageid"], uuid)
                        # Open folder action
                        elif action == open_folder_action:  # ACTION: Open folder
                            if os.path.exists(mod_path):  # If the path actually exists
                                logger.info(f"Opening folder: {mod_path}")
                                platform_specific_open(mod_path)
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

    def append_new_item(self, uuid: str) -> None:
        data = CustomListWidgetItemMetadata(uuid=uuid)
        item = CustomListWidgetItem(self)
        item.setData(Qt.ItemDataRole.UserRole, data)
        self.addItem(item)

    def get_all_mod_list_items(self) -> list[CustomListWidgetItem]:
        """
        This gets all modlist items.

        :return: List of all modlist items as CustomListWidgetItem
        """
        mod_list_items = []
        for index in range(self.count()):
            item = self.item(index)
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

    def get_all_loaded_and_toggled_mod_list_items(self) -> list[CustomListWidgetItem]:
        """
        This returns all modlist items that have their warnings toggled.

        :return: List of all toggled modlist items as CustomListWidgetItem
        """
        mod_list_items = []
        for index in range(self.count()):
            item = self.item(index)
            item_data = item.data(Qt.ItemDataRole.UserRole)
            if item_data["warning_toggled"]:
                mod_list_items.append(item)
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
        errors_warnings = data["errors_warnings"]
        errors = data["errors"]
        warnings = data["warnings"]
        filtered = data["filtered"]
        invalid = data["invalid"]
        mismatch = data["mismatch"]
        alternative = data["alternative"]
        uuid = data["uuid"]
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
            )
            widget.toggle_warning_signal.connect(self.toggle_warning)
            widget.toggle_error_signal.connect(self.toggle_warning)
            item.setSizeHint(widget.sizeHint())
            self.setItemWidget(item, widget)

    def check_widgets_visible(self) -> None:
        # This function checks the visibility of each item and creates a widget if the item is visible and not already setup.
        for idx in range(self.count()):
            item = self.item(idx)
            # Check for visible item without a widget set
            if item and self.check_item_visible(item) and self.itemWidget(item) is None:
                self.create_widget_for_item(item)

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
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data is None:
                    logger.debug(f"Attempted to insert item with None data. Idx: {idx}")
                    continue
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

    def mod_changed_to(
        self, current: CustomListWidgetItem, previous: CustomListWidgetItem
    ) -> None:
        """
        Method to handle clicking on a row or navigating between rows with
        the keyboard. Look up the mod's data by uuid
        """
        if current is not None:
            data = current.data(Qt.ItemDataRole.UserRole)
            self.mod_info_signal.emit(data["uuid"])

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
            self.mod_info_signal.emit(data["uuid"])
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
        # widget = ModListItemInner = self.itemWidget(item)
        self.key_press_signal.emit("DoubleClick")

    def rebuild_item_widget_from_uuid(self, uuid: str) -> None:
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
            self.mod_info_signal.emit(uuid)

    def recalculate_internal_errors_warnings(self) -> tuple[str, str, int, int]:
        """
        Whenever the respective mod list has items added to it, or has
        items removed from it, or has items rearranged around within it,
        calculate the internal list errors / warnings for the mod list
        """
        logger.info(f"Recalculating {self.list_type} list errors / warnings")

        internal_local_metadata = self.metadata_manager.internal_local_metadata

        packageid_to_uuid = {
            internal_local_metadata[uuid]["packageid"]: uuid for uuid in self.uuids
        }
        package_ids_set = set(packageid_to_uuid.keys())

        package_id_to_errors: dict[str, dict[str, None | set[str] | bool]] = {
            uuid: {
                "missing_dependencies": set() if self.list_type == "Active" else None,
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
            for uuid in self.uuids
        }

        num_warnings = 0
        total_warning_text = ""
        num_errors = 0
        total_error_text = ""

        for uuid, mod_errors in package_id_to_errors.items():
            current_mod_index = self.uuids.index(uuid)
            current_item = self.item(current_mod_index)
            if current_item is None:
                continue
            current_item_data = current_item.data(Qt.ItemDataRole.UserRole)
            current_item_data["mismatch"] = False
            current_item_data["errors"] = ""
            current_item_data["warnings"] = ""
            mod_data = internal_local_metadata[uuid]
            # Check mod supportedversions against currently loaded version of game
            mod_errors["version_mismatch"] = self.metadata_manager.is_version_mismatch(
                uuid
            )
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
                # Check dependencies (and replacements for dependencies)
                # Note: dependency replacements are NOT assumed to be subject
                # to the same load order rules as the orignal mods!
                mod_errors["missing_dependencies"] = {
                    dep
                    for dep in mod_data.get("dependencies", [])
                    if dep not in package_ids_set
                    and not self._has_replacement(
                        mod_data["packageid"], dep, package_ids_set
                    )
                }

                # Check incompatibilities
                mod_errors["conflicting_incompatibilities"] = {
                    incomp
                    for incomp in mod_data.get("incompatibilities", [])
                    if incomp in package_ids_set
                }

                # Check loadTheseBefore
                for load_this_before in mod_data.get("loadTheseBefore", []):
                    if (
                        load_this_before[1]
                        and load_this_before[0] in packageid_to_uuid
                        and current_mod_index
                        <= self.uuids.index(packageid_to_uuid[load_this_before[0]])
                    ):
                        assert isinstance(mod_errors["load_before_violations"], set)
                        mod_errors["load_before_violations"].add(load_this_before[0])

                # Check loadTheseAfter
                for load_this_after in mod_data.get("loadTheseAfter", []):
                    if (
                        load_this_after[1]
                        and load_this_after[0] in packageid_to_uuid
                        and current_mod_index
                        >= self.uuids.index(packageid_to_uuid[load_this_after[0]])
                    ):
                        assert isinstance(mod_errors["load_after_violations"], set)
                        mod_errors["load_after_violations"].add(load_this_after[0])
            # Calculate any needed string for errors
            tool_tip_text = ""
            for error_type, tooltip_header in [
                ("missing_dependencies", self.tr("\nMissing Dependencies:")),
                ("conflicting_incompatibilities", self.tr("\nIncompatibilities:")),
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
            # If missing dependency and/or incompatibility, add tooltip to errors
            current_item_data["errors"] = tool_tip_text
            # Calculate any needed string for warnings
            for error_type, tooltip_header in [
                ("load_before_violations", "\nShould be Loaded After:"),
                ("load_after_violations", "\nShould be Loaded Before:"),
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
                tool_tip_text += "\nMod and Game Version Mismatch"
            # Handle "use this instead" behavior
            if (
                current_item_data["alternative"]
                and mod_data["packageid"] not in self.ignore_warning_list
            ):
                tool_tip_text += f"\nAn alternative updated mod is recommended:\n{current_item_data['alternative']}"
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
        key: ModsPanelSortKey = ModsPanelSortKey.NOKEY,
    ) -> None:
        """
        Reconstructs and sorts a mod list based on provided UUIDs and a sorting key.

        This method takes a list of mod UUIDs, sorts them according to the specified
        sorting key, and then recreates the mod list of the given type with the sorted order.

        Args:
            list_type (str): The type of mod list to recreate. ("Active", "Inactive")
            uuids (List[str]): The list of UUIDs representing the mods.
            key (ModsPanelSortKey, optional): An enumeration value that determines the
                                              sorting criterion for the mods. Defaults to
                                              `ModsPanelSortKey.NOKEY`, which implies sorting by uuids.

        Returns:
            None
        """
        sorted_uuids = sort_uuids(uuids, key=key)
        self.recreate_mod_list(list_type, sorted_uuids)

    def recreate_mod_list(self, list_type: str, uuids: list[str]) -> None:
        """
        Clear all mod items and add new ones from a dict.

        :param mods: dict of mod data
        """
        logger.info(f"Internally recreating {list_type} mod list")
        # Disable updates
        self.setUpdatesEnabled(False)
        # Clear list
        self.clear()
        self.uuids = list()
        if uuids:  # Insert data...
            for uuid_key in uuids:
                list_item = CustomListWidgetItem(self)
                data = CustomListWidgetItemMetadata(uuid=uuid_key)
                list_item.setData(Qt.ItemDataRole.UserRole, data)
                self.addItem(list_item)
        else:  # ...unless we don't have mods, at which point reenable updates and exit
            self.setUpdatesEnabled(True)
            return
        # Enable updates and repaint
        self.setUpdatesEnabled(True)
        self.repaint()

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
        item.setData(Qt.ItemDataRole.UserRole, item_data)
        self.recalculate_warnings_signal.emit()

    def replaceItemAtIndex(self, index: int, item: CustomListWidgetItem) -> None:
        """
        IMPORTANT: This is used to replace an item without triggering the rowsInserted signal.

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

        # Perform the replacement
        self.takeItem(index)
        self.insertItem(index, item)

        # Reconnect to ALL slots
        self.model().rowsInserted.connect(
            self.handle_rows_inserted, Qt.ConnectionType.QueuedConnection
        )


class ModsPanel(QWidget):
    """
    This class controls the layout and functionality for the
    active/inactive mods list panel on the GUI.
    """

    list_updated_signal = Signal()
    save_btn_animation_signal = Signal()
    check_dependencies_signal = Signal()

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

        # Base layout horizontal, sub-layouts vertical
        self.panel = QHBoxLayout()
        self.active_panel = QVBoxLayout()
        self.inactive_panel = QVBoxLayout()
        # Add vertical layouts to it
        self.panel.addLayout(self.inactive_panel)
        self.panel.addLayout(self.active_panel)

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

        # Inactive mods search layout
        self.inactive_mods_search_layout = QHBoxLayout()
        self.initialize_inactive_mods_search_widgets()

        # Add inactive mods widgets to layout
        self.inactive_panel.addWidget(self.inactive_mods_label)
        self.inactive_panel.addLayout(self.inactive_mods_search_layout)
        self.inactive_panel.addWidget(self.inactive_mods_list)

        # Connect signals and slots
        self.connect_signals()

        logger.debug("Finished ModsPanel initialization")

    def initialize_active_mods_search_widgets(self) -> None:
        """Initialize widgets for active mods search layout."""
        self.active_mods_filter_data_source_index = 0
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
        self.active_mods_search_filter.setMaximumWidth(125)
        self.active_mods_search_filter.addItems(
            [
                self.tr("Name"),
                self.tr("PackageId"),
                self.tr("Author(s)"),
                self.tr("PublishedFileId"),
                self.tr("Version"),
            ]
        )
        # Active mods search layouts
        self.active_mods_search_layout.addWidget(
            self.active_mods_filter_data_source_button
        )
        if self.settings_controller.settings.mod_type_filter_toggle:
            self.active_mods_search_layout.addWidget(
                self.active_data_source_filter_type_button
            )
        self.active_mods_search_layout.addWidget(
            self.active_mods_search_mode_filter_button
        )
        self.active_mods_search_layout.addWidget(self.active_mods_search, 45)
        self.active_mods_search_layout.addWidget(self.active_mods_search_filter, 70)
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

        # Create and add Use This Instead button
        self.use_this_instead_button = QPushButton(
            self.tr('Check "Use This Instead" Database')
        )
        self.use_this_instead_button.setObjectName("useThisInsteadButton")
        self.use_this_instead_button.clicked.connect(
            EventBus().use_this_instead_clicked.emit
        )
        self.errors_summary_layout.addWidget(self.use_this_instead_button)

        # Create and add Check Dependencies button
        self.check_dependencies_button: QPushButton = QPushButton(
            self.tr("Check Dependencies")
        )
        self.check_dependencies_button.setObjectName("MainUI")
        self.errors_summary_layout.addWidget(self.check_dependencies_button)
        self.check_dependencies_button.clicked.connect(
            self.check_dependencies_signal.emit
        )

        # Add to the outer frame
        self.errors_summary_frame.setLayout(self.errors_summary_layout)
        self.errors_summary_frame.setHidden(True)

    def initialize_inactive_mods_search_widgets(self) -> None:
        """Initialize widgets for inactive mods search layout."""
        self.inactive_mods_filter_data_source_index = 0
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
        self.inactive_mods_search_filter.setObjectName("MainUI")
        self.inactive_mods_search_filter.setMaximumWidth(140)
        self.inactive_mods_search_filter.addItems(
            [
                self.tr("Name"),
                self.tr("PackageId"),
                self.tr("Author(s)"),
                self.tr("PublishedFileId"),
                self.tr("Version"),
            ]
        )
        self.inactive_mods_search_layout.addWidget(
            self.inactive_mods_filter_data_source_button
        )
        if self.settings_controller.settings.mod_type_filter_toggle:
            self.inactive_mods_search_layout.addWidget(
                self.inactive_data_source_filter_type_button
            )
        self.inactive_mods_search_layout.addWidget(
            self.inactive_mods_search_mode_filter_button
        )
        self.inactive_mods_search_layout.addWidget(self.inactive_mods_search, 45)
        self.inactive_mods_search_layout.addWidget(self.inactive_mods_search_filter, 70)

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
        self.signal_search_and_filters(list_type="Active", pattern=pattern)

    def on_active_mods_search_clear(self) -> None:
        self.signal_clear_search(list_type="Active")

    def on_active_mods_search_data_source_filter(self) -> None:
        self.signal_search_source_filter(list_type="Active")

    def on_active_mods_search_data_source_filter_type(self) -> None:
        self.apply_mods_filter_type(list_type="Active")

    def on_active_mods_mode_filter_toggle(self) -> None:
        self.signal_search_mode_filter(list_type="Active")

    def on_inactive_mods_list_updated(self, count: str) -> None:
        self.mod_list_updated(count=count, list_type="Inactive")

    def on_inactive_mods_search(self, pattern: str) -> None:
        self.signal_search_and_filters(list_type="Inactive", pattern=pattern)

    def on_inactive_mods_search_clear(self) -> None:
        self.signal_clear_search(list_type="Inactive")

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
        for uuid in mod_list.uuids:
            item = mod_list.item(mod_list.uuids.index(uuid))
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
        if list_type == "Active":
            # Check if all visible items have their widgets loaded
            self.active_mods_list.check_widgets_visible()
            # Calculate internal errors and warnings for all mods in the respective mod list
            total_error_text, total_warning_text, num_errors, num_warnings = (
                self.active_mods_list.recalculate_internal_errors_warnings()
            )
            # Calculate total errors and warnings and set the text and tool tip for the summary
            if total_error_text or total_warning_text or num_errors or num_warnings:
                self.errors_summary_frame.setHidden(False)
                padding = " "
                self.warnings_text.setText(
                    self.tr("{padding}{num_warnings} warning(s)").format(
                        padding=padding, num_warnings=num_warnings
                    )
                )
                self.errors_text.setText(
                    self.tr("{padding}{num_errors} error(s)").format(
                        padding=padding, num_errors=num_errors
                    )
                )
                self.errors_icon.setToolTip(
                    total_error_text.lstrip() if total_error_text else ""
                )
                self.warnings_icon.setToolTip(
                    total_warning_text.lstrip() if total_warning_text else ""
                )
            else:  # Hide the summary if there are no errors or warnings
                self.errors_summary_frame.setHidden(True)
                self.warnings_text.setText(self.tr("0 warnings"))
                self.errors_text.setText(self.tr("0 errors"))
                self.errors_icon.setToolTip("")
                self.warnings_icon.setToolTip("")
            # First time, and when Refreshing, the slot will evaluate false and do nothing.
            # The purpose of this is for the _do_save_animation slot in the main_content_panel
            EventBus().list_updated_signal.emit()
        else:
            # Check if all visible items have their widgets loaded
            self.inactive_mods_list.check_widgets_visible()
            # Calculate internal errors and warnings for all mods in the respective mod list
            self.inactive_mods_list.recalculate_internal_errors_warnings()

    def signal_clear_search(
        self, list_type: str, recalculate_list_errors_warnings: bool = True
    ) -> None:
        if list_type == "Active":
            self.active_mods_search.clear()
            self.signal_search_and_filters(
                list_type=list_type,
                pattern="",
                recalculate_list_errors_warnings=recalculate_list_errors_warnings,
            )
            self.active_mods_search.clearFocus()
        elif list_type == "Inactive":
            self.inactive_mods_search.clear()
            self.signal_search_and_filters(
                list_type=list_type,
                pattern="",
                recalculate_list_errors_warnings=recalculate_list_errors_warnings,
            )
            self.inactive_mods_search.clearFocus()

    def signal_search_and_filters(
        self,
        list_type: str,
        pattern: str,
        filters_active: bool = False,
        recalculate_list_errors_warnings: bool = True,
    ) -> None:
        """
        Performs a search and/or applies filters based on the given parameters.

        Called anytime the search bar text changes or the filters change.

        Args:
            list_type (str): The type of list to search within (Active or Inactive).
            pattern (str): The pattern to search for.
            filters_active (bool): If any filter is active (inc. pattern search).
            recalculate_list_errors_warnings (bool): If the list errors and warnings should be recalculated, defaults to True.
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
        elif _filter.currentText() == self.tr("PackageId"):
            search_filter = "packageid"
        elif _filter.currentText() == self.tr("Author(s)"):
            search_filter = "authors"
        elif _filter.currentText() == self.tr("PublishedFileId"):
            search_filter = "publishedfileid"
        elif _filter.currentText() == self.tr("Version"):
            search_filter = "version"
        # Filter the list using any search and filter state
        for uuid in uuids:
            item = (
                self.active_mods_list.item(uuids.index(uuid))
                if list_type == "Active"
                else self.inactive_mods_list.item(uuids.index(uuid))
            )
            if item is None:
                continue
            item_data = item.data(Qt.ItemDataRole.UserRole)
            metadata = self.metadata_manager.internal_local_metadata[uuid]
            if pattern != "":
                filters_active = True
            # Hide invalid items if enabled in settings
            if self.settings_controller.settings.hide_invalid_mods_when_filtering_toggle:
                invalid = item_data["invalid"]
                # TODO: I dont think filtered should be set at all for invalid items... I misunderstood what it represents
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
                else:
                    item_data["hidden_by_filter"] = False
            else:
                if item_filtered and item.isHidden():
                    item.setHidden(False)
                    item_data["hidden_by_filter"] = False
            # Update item data
            item_data["filtered"] = item_filtered
            item.setData(Qt.ItemDataRole.UserRole, item_data)
        self.mod_list_updated(
            str(len(uuids)),
            list_type,
            recalculate_list_errors_warnings=recalculate_list_errors_warnings,
        )

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
        elif list_type == "Inactive":
            self.inactive_mods_filter_data_source_index = source_index
            self.inactive_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
                source_index
            ]
        if source_index == 0:
            filters_active = False
        else:
            filters_active = True
        # Filter widgets by data source, while preserving any active search pattern
        self.signal_search_and_filters(
            list_type=list_type, pattern=search.text(), filters_active=filters_active
        )

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
        for uuid in uuids:
            item = (
                self.active_mods_list.item(uuids.index(uuid))
                if list_type == "Active"
                else self.inactive_mods_list.item(uuids.index(uuid))
            )
            if item is None:
                continue
            item_data = item.data(Qt.ItemDataRole.UserRole)
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
