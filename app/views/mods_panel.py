from functools import partial
from loguru import logger
import os
from pathlib import Path
from shutil import copy2, copytree, rmtree
from traceback import format_exc
from typing import List, Optional

from pyperclip import copy as copy_to_clipboard
from PySide6.QtCore import QEvent, QModelIndex, QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QCursor,
    QDropEvent,
    QFocusEvent,
    QFontMetrics,
    QIcon,
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
    QListWidgetItem,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.controllers.settings_controller import SettingsController
from app.utils.app_info import AppInfo
from app.utils.constants import SEARCH_DATA_SOURCE_FILTER_INDEXES
from app.utils.generic import (
    delete_files_except_extension,
    handle_remove_read_only,
    open_url_browser,
    platform_specific_open,
    sanitize_filename,
)
from app.utils.metadata import MetadataManager
from app.models.dialogue import show_dialogue_conditional, show_dialogue_input


class ClickableQLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class ModListItemInner(QWidget):
    """
    Subclass for QWidget. Used to store data for a single
    mod and display relevant data on a mod list.
    """

    toggle_warning_signal = Signal(str)

    def __init__(
        self,
        settings_controller: SettingsController,
        uuid: str,
    ) -> None:
        """
        Initialize the QWidget with mod uuid. Metadata can be accessed via MetadataManager.

        All metadata tags are set to the corresponding field if it
        exists in the metadata dict. See tags:
        https://rimworldwiki.com/wiki/About.xml

        :param settings_controller: an instance of SettingsController for accessing settings
        :param uuid: str, the uuid of the mod which corresponds to a mod's metadata
        """

        super(ModListItemInner, self).__init__()

        # Cache MetadataManager instance
        self.metadata_manager = MetadataManager.instance()
        # Cache SettingsManager instance
        self.settings_controller = settings_controller

        # All data, including name, author, package id, dependencies,
        # whether the mod is a workshop mod or expansion, etc is encapsulated
        # in this variable. This is exactly equal to the dict value of a
        # single all_mods key-value
        self.uuid = uuid
        self.list_item_name = self.metadata_manager.internal_local_metadata[
            self.uuid
        ].get("name")
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
            if self.metadata_manager.internal_local_metadata[self.uuid].get("csharp"):
                self.csharp_icon = QLabel()
                self.csharp_icon.setPixmap(
                    ModListIcons.csharp_icon().pixmap(QSize(20, 20))
                )
                self.csharp_icon.setToolTip(
                    "Contains custom C# assemblies (custom code)"
                )
            else:
                self.xml_icon = QLabel()
                self.xml_icon.setPixmap(ModListIcons.xml_icon().pixmap(QSize(20, 20)))
                self.xml_icon.setToolTip("Contains custom content (textures / XML)")
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
            self.git_icon.setToolTip("Local mod that contains a git repository")
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
            self.steamcmd_icon.setToolTip("Local mod that can be used with SteamCMD")
        # Warning icon hidden by default
        self.warning_icon_label = ClickableQLabel()
        self.warning_icon_label.clicked.connect(
            partial(
                self.toggle_warning_signal.emit,
                self.metadata_manager.internal_local_metadata[self.uuid]["packageid"],
            )
        )
        self.warning_icon_label.setPixmap(
            ModListIcons.warning_icon().pixmap(QSize(20, 20))
        )
        self.warning_icon_label.setHidden(True)

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
                    "Official RimWorld content by Ludeon Studios"
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
                    self.mod_source_icon.setToolTip("Installed locally")
            elif data_source == "workshop":
                self.mod_source_icon.setObjectName("workshop")
                self.mod_source_icon.setToolTip("Subscribed via Steam")

        self.main_label.setObjectName("ListItemLabel")
        if self.git_icon:
            self.main_item_layout.addWidget(self.git_icon, Qt.AlignRight)
        if self.steamcmd_icon:
            self.main_item_layout.addWidget(self.steamcmd_icon, Qt.AlignRight)
        if self.mod_source_icon:
            self.main_item_layout.addWidget(self.mod_source_icon, Qt.AlignRight)
        if self.csharp_icon:
            self.main_item_layout.addWidget(self.csharp_icon, Qt.AlignRight)
        if self.xml_icon:
            self.main_item_layout.addWidget(self.xml_icon, Qt.AlignRight)
        self.main_item_layout.addWidget(self.main_label, Qt.AlignCenter)
        self.main_item_layout.addWidget(self.warning_icon_label, Qt.AlignRight)
        self.main_item_layout.addStretch()
        self.setLayout(self.main_item_layout)

    def count_icons(self, widget) -> int:
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
        name_line = f"Mod: {self.metadata_manager.internal_local_metadata[self.uuid].get('name')}\n"

        authors_tag = self.metadata_manager.internal_local_metadata[self.uuid].get(
            "authors"
        )

        if authors_tag and isinstance(authors_tag, dict) and authors_tag.get("li"):
            list_of_authors = authors_tag["li"]
            authors_text = ", ".join(list_of_authors)
            author_line = f"Authors: {authors_text}\n"
        else:
            author_line = f"Author: {authors_tag if authors_tag else 'Not specified'}\n"

        package_id_line = f"PackageID: {self.metadata_manager.internal_local_metadata[self.uuid].get('packageid')}\n"
        modversion_line = f"Mod Version: {self.metadata_manager.internal_local_metadata[self.uuid].get('modversion', 'Not specified')}\n"
        path_line = f"Path: {self.metadata_manager.internal_local_metadata[self.uuid].get('path')}"
        return name_line + author_line + package_id_line + modversion_line + path_line

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
                self.list_item_name, Qt.ElideRight, int(available_width)
            )
            self.main_label.setText(str(shortened_text))
        else:
            self.main_label.setText(self.list_item_name)
        return super().resizeEvent(event)


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

    _ludeon_icon: Optional[QIcon] = None
    _local_icon: Optional[QIcon] = None
    _steam_icon: Optional[QIcon] = None
    _csharp_icon: Optional[QIcon] = None
    _xml_icon: Optional[QIcon] = None
    _git_icon: Optional[QIcon] = None
    _steamcmd_icon: Optional[QIcon] = None
    _warning_icon: Optional[QIcon] = None
    _error_icon: Optional[QIcon] = None

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
    re_git_signal = Signal(list)
    steamdb_blacklist_signal = Signal(list)
    steamcmd_downloader_signal = Signal(list)
    steamworks_subscription_signal = Signal(list)

    def __init__(self, settings_controller: SettingsController) -> None:
        """
        Initialize the ListWidget with a dict of mods.
        Keys are the package ids and values are a dict of
        mod attributes. See tags:
        https://rimworldwiki.com/wiki/About.xml
        """
        logger.debug("Initializing ModListWidget")

        # Cache MetadataManager instance
        self.metadata_manager = MetadataManager.instance()

        self.settings_controller = settings_controller

        super(ModListWidget, self).__init__()

        # Allow for dragging and dropping between lists
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)

        # Allow for selecting and moving multiple items
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        # When an item is clicked, display the mod information
        self.currentItemChanged.connect(self.mod_clicked)

        # When an item is double clicked, move it to the opposite list
        self.itemDoubleClicked.connect(self.mod_double_clicked)

        # Add an eventFilter for per mod_list_item context menu
        self.installEventFilter(self)

        # Disable horizontal scroll bar
        self.horizontalScrollBar().setEnabled(False)
        self.horizontalScrollBar().setVisible(False)

        # Allow inserting custom list items
        self.model().rowsInserted.connect(
            self.handle_rows_inserted, Qt.QueuedConnection
        )

        # Handle removing items to update count
        self.model().rowsAboutToBeRemoved.connect(
            self.handle_rows_removed, Qt.QueuedConnection
        )

        # This set is used to keep track of mods that have been loaded
        # into widgets. Used for an optimization strategy for `handle_rows_inserted`
        self.uuids = list()
        self.ignore_warning_list = []
        logger.debug("Finished ModListWidget initialization")

    def dropEvent(self, event: QDropEvent) -> None:
        super().dropEvent(event)
        # Get the drop action
        drop_action = event.dropAction()
        # Check if the drop action is MoveAction
        if drop_action == Qt.MoveAction:
            # Get the new indexes of the dropped items
            new_indexes = [index.row() for index in self.selectedIndexes()]
            # Get the UUIDs of the dropped items
            uuids = [item.data(Qt.UserRole) for item in self.selectedItems()]
            # Insert the UUIDs at the respective new indexes
            for idx, uuid in zip(new_indexes, uuids):
                if uuid in self.uuids:  # Remove the uuid if it exists in the list
                    self.uuids.remove(uuid)
                # Reinsert uuid at it's new index
                self.uuids.insert(idx, uuid)
        # Update list signal
        self.list_update_signal.emit("drop")

    def eventFilter(self, source_object: QObject, event: QEvent) -> None:
        """
        https://doc.qt.io/qtforpython/overviews/eventsandfilters.html

        Takes source object and filters an event at the ListWidget level, executes
        an action based on a per-mod_list_item contextMenu

        :param object: the source object returned from the event
        :param event: the QEvent type
        """
        if event.type() == QEvent.ContextMenu and source_object is self:
            # Get the position of the right-click event
            pos = QCursor.pos()
            # Convert the global position to the list widget's coordinate system
            pos_local = self.mapFromGlobal(pos)
            # Get the item at the local position
            item = self.itemAt(pos_local)
            if not isinstance(item, QListWidgetItem):
                logger.debug("Mod list right-click non-QListWidgetItem")
                return super().eventFilter(source_object, event)

            # Otherwise, begin calculation
            logger.info("USER ACTION: Open right-click mod_list_item contextMenu")

            # GIT MOD PATHS
            # A list of git mod paths to update
            git_paths = []

            # LOCAL MOD CONVERSIONS
            # A dict to track local mod folder name -> publishedfileid
            local_steamcmd_name_to_publishedfileid = {}

            # STEAMCMD MOD PFIDS
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
            contextMenu = QMenu()
            # Open folder action
            open_folder_action = None
            # Open URL in browser action
            open_url_browser_action = None
            # Open URL in Steam
            open_mod_steam_action = None
            # Copy to clipboard actions
            copy_packageId_to_clipboard_action = None
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
            # Delete mod
            delete_mod_action = None
            # Delete mod (keep .dds)
            delete_mod_keep_dds_action = None

            # Get all selected QListWidgetItems
            selected_items = self.selectedItems()
            # Single item selected
            if len(selected_items) == 1:
                logger.debug(f"{len(selected_items)} items selected")
                source_item = selected_items[0]
                if type(source_item) is QListWidgetItem:
                    source_widget = self.itemWidget(source_item)
                    # Retrieve metadata
                    widget_json_data = self.metadata_manager.internal_local_metadata[
                        source_widget.uuid
                    ]
                    mod_data_source = widget_json_data.get("data_source")
                    # Open folder action text
                    open_folder_action = QAction()
                    open_folder_action.setText("Open folder")
                    # If we have a "url" or "steam_url"
                    if widget_json_data.get("url") or widget_json_data.get("steam_url"):
                        open_url_browser_action = QAction()
                        open_url_browser_action.setText("Open URL in browser")
                        copy_url_to_clipboard_action = QAction()
                        copy_url_to_clipboard_action.setText("Copy URL to clipboard")
                    # If we have a "steam_uri"
                    if widget_json_data.get("steam_uri"):
                        open_mod_steam_action = QAction()
                        open_mod_steam_action.setText("Open mod in Steam")
                    # Conversion options (SteamCMD <-> local) + re-download (local mods found in SteamDB and SteamCMD)
                    if mod_data_source == "local":
                        mod_name = widget_json_data.get("name")
                        mod_folder_name = widget_json_data["folder"]
                        mod_folder_path = widget_json_data["path"]
                        publishedfileid = widget_json_data.get("publishedfileid")
                        if not widget_json_data.get("steamcmd") and (
                            self.metadata_manager.external_steam_metadata
                            and publishedfileid
                            and publishedfileid
                            in self.metadata_manager.external_steam_metadata.keys()
                        ):
                            local_steamcmd_name_to_publishedfileid[
                                mod_folder_name
                            ] = publishedfileid
                            # Convert local mods -> steamcmd
                            convert_local_steamcmd_action = QAction()
                            convert_local_steamcmd_action.setText(
                                "Convert local mod to SteamCMD"
                            )
                        if widget_json_data.get("steamcmd"):
                            steamcmd_mod_paths.append(mod_folder_path)
                            steamcmd_publishedfileid_to_name[publishedfileid] = mod_name
                            # Convert steamcmd mods -> local
                            convert_steamcmd_local_action = QAction()
                            convert_steamcmd_local_action.setText(
                                "Convert SteamCMD mod to local"
                            )
                            # Re-download steamcmd mods
                            re_steamcmd_action = QAction()
                            re_steamcmd_action.setText("Re-download mod with SteamCMD")
                        # Update local mods that contain git repos that are not steamcmd mods
                        if not widget_json_data.get(
                            "steamcmd"
                        ) and widget_json_data.get("git_repo"):
                            git_paths.append(mod_folder_path)
                            re_git_action = QAction()
                            re_git_action.setText("Update mod with git")
                    # If Workshop, and pfid, allow Steam actions
                    if mod_data_source == "workshop" and widget_json_data.get(
                        "publishedfileid"
                    ):
                        mod_name = widget_json_data.get("name")
                        mod_folder_path = widget_json_data["path"]
                        publishedfileid = widget_json_data["publishedfileid"]
                        steam_mod_paths.append(mod_folder_path)
                        steam_publishedfileid_to_name[publishedfileid] = mod_name
                        # Convert steam mods -> local
                        convert_workshop_local_action = QAction()
                        convert_workshop_local_action.setText(
                            "Convert Steam mod to local"
                        )
                        # Re-subscribe steam mods
                        re_steam_action = QAction()
                        re_steam_action.setText("Re-subscribe mod with Steam")
                        # Unsubscribe steam mods
                        unsubscribe_mod_steam_action = QAction()
                        unsubscribe_mod_steam_action.setText(
                            "Unsubscribe mod with Steam"
                        )
                    # SteamDB blacklist options
                    if (
                        self.metadata_manager.external_steam_metadata
                        and widget_json_data.get("publishedfileid")
                    ):
                        publishedfileid = widget_json_data["publishedfileid"]
                        if self.metadata_manager.external_steam_metadata.get(
                            publishedfileid, {}
                        ).get("blacklist"):
                            steamdb_remove_blacklist = publishedfileid
                            remove_from_steamdb_blacklist_action = QAction()
                            remove_from_steamdb_blacklist_action.setText(
                                "Remove mod from SteamDB blacklist"
                            )
                        else:
                            steamdb_add_blacklist = publishedfileid
                            add_to_steamdb_blacklist_action = QAction()
                            add_to_steamdb_blacklist_action.setText(
                                "Add mod to SteamDB blacklist"
                            )
                    # Copy packageId to clipboard
                    copy_packageId_to_clipboard_action = QAction()
                    copy_packageId_to_clipboard_action.setText(
                        "Copy packageId to clipboard"
                    )
                    # Edit mod rules with Rule Editor (only for individual mods)
                    edit_mod_rules_action = QAction()
                    edit_mod_rules_action.setText("Edit mod with Rule Editor")
                    # Ignore error action
                    toggle_warning_action = QAction()
                    toggle_warning_action.setText("Toggle warning")
                    # Mod deletion actions
                    delete_mod_action = QAction()
                    delete_mod_action.setText("Delete mod")
                    delete_mod_keep_dds_action = QAction()
                    delete_mod_keep_dds_action.setText("Delete mod (keep .dds)")
            # Multiple items selected
            elif len(selected_items) > 1:  # Multiple items selected
                for source_item in selected_items:
                    if type(source_item) is QListWidgetItem:
                        source_widget = self.itemWidget(source_item)
                        # Retrieve metadata
                        widget_json_data = (
                            self.metadata_manager.internal_local_metadata[
                                source_widget.uuid
                            ]
                        )
                        mod_data_source = widget_json_data.get("data_source")
                        # Open folder action text
                        open_folder_action = QAction()
                        open_folder_action.setText("Open folder(s)")
                        # If we have a "url" or "steam_url"
                        if widget_json_data.get("url") or widget_json_data.get(
                            "steam_url"
                        ):
                            open_url_browser_action = QAction()
                            open_url_browser_action.setText("Open URL(s) in browser")
                        # Conversion options (local <-> SteamCMD)
                        if mod_data_source == "local":
                            mod_name = widget_json_data.get("name")
                            mod_folder_name = widget_json_data["folder"]
                            mod_folder_path = widget_json_data["path"]
                            publishedfileid = widget_json_data.get("publishedfileid")
                            if not widget_json_data.get("steamcmd") and (
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
                                        "Convert local mod(s) to SteamCMD"
                                    )
                            if widget_json_data.get("steamcmd"):
                                steamcmd_mod_paths.append(mod_folder_path)
                                steamcmd_publishedfileid_to_name[
                                    publishedfileid
                                ] = mod_name
                                # Convert steamcmd mods -> local
                                if not convert_steamcmd_local_action:
                                    convert_steamcmd_local_action = QAction()
                                    convert_steamcmd_local_action.setText(
                                        "Convert SteamCMD mod(s) to local"
                                    )
                                # Re-download steamcmd mods
                                if not re_steamcmd_action:
                                    re_steamcmd_action = QAction()
                                    re_steamcmd_action.setText(
                                        "Re-download mod(s) with SteamCMD"
                                    )
                            # Update git mods if local mod with git repo, but not steamcmd
                            if not widget_json_data.get(
                                "steamcmd"
                            ) and widget_json_data.get("git_repo"):
                                git_paths.append(mod_folder_path)
                                if not re_git_action:
                                    re_git_action = QAction()
                                    re_git_action.setText("Update mod(s) with git")
                        # No "Edit mod rules" when multiple selected
                        # Toggle warning
                        if not toggle_warning_action:
                            toggle_warning_action = QAction()
                            toggle_warning_action.setText("Toggle warning(s)")
                        # If Workshop, and pfid, allow Steam actions
                        if mod_data_source == "workshop" and widget_json_data.get(
                            "publishedfileid"
                        ):
                            mod_name = widget_json_data.get("name")
                            mod_folder_path = widget_json_data["path"]
                            publishedfileid = widget_json_data["publishedfileid"]
                            steam_mod_paths.append(mod_folder_path)
                            steam_publishedfileid_to_name[publishedfileid] = mod_name
                            # Convert steam mods -> local
                            if not convert_workshop_local_action:
                                convert_workshop_local_action = QAction()
                                convert_workshop_local_action.setText(
                                    "Convert Steam mod(s) to local"
                                )
                            # Re-subscribe steam mods
                            if not re_steam_action:
                                re_steam_action = QAction()
                                re_steam_action.setText(
                                    "Re-subscribe mod(s) with Steam"
                                )
                            # Unsubscribe steam mods
                            if not unsubscribe_mod_steam_action:
                                unsubscribe_mod_steam_action = QAction()
                                unsubscribe_mod_steam_action.setText(
                                    "Unsubscribe mod(s) with Steam"
                                )
                        # No SteamDB blacklist options when multiple selected
                        # Prohibit deletion of game files
                        if not delete_mod_action:
                            delete_mod_action = QAction()
                            # Delete mod action text
                            delete_mod_action.setText("Delete mod(s)")
                        if not delete_mod_keep_dds_action:
                            delete_mod_keep_dds_action = QAction()
                            # Delete mod action text
                            delete_mod_keep_dds_action.setText(
                                "Delete mod(s) (keep .dds)"
                            )
            # Put together our contextMenu
            if open_folder_action:
                contextMenu.addAction(open_folder_action)
            if open_url_browser_action:
                contextMenu.addAction(open_url_browser_action)
            if open_mod_steam_action:
                contextMenu.addAction(open_mod_steam_action)
            if toggle_warning_action:
                contextMenu.addAction(toggle_warning_action)
            if delete_mod_action or delete_mod_keep_dds_action:
                deletion_options_menu = QMenu(title="Deletion options")
                if delete_mod_action:
                    deletion_options_menu.addAction(delete_mod_action)
                if delete_mod_keep_dds_action:
                    deletion_options_menu.addAction(delete_mod_keep_dds_action)
                contextMenu.addMenu(deletion_options_menu)
            contextMenu.addSeparator()
            if (
                copy_packageId_to_clipboard_action
                or copy_url_to_clipboard_action
                or edit_mod_rules_action
                or re_git_action
            ):
                misc_options_menu = QMenu(title="Miscellaneous options")
                if copy_packageId_to_clipboard_action or copy_url_to_clipboard_action:
                    clipboard_options_menu = QMenu(title="Clipboard options")
                    clipboard_options_menu.addAction(copy_packageId_to_clipboard_action)
                    if copy_url_to_clipboard_action:
                        clipboard_options_menu.addAction(copy_url_to_clipboard_action)
                    misc_options_menu.addMenu(clipboard_options_menu)
                if edit_mod_rules_action:
                    misc_options_menu.addAction(edit_mod_rules_action)
                if re_git_action:
                    misc_options_menu.addAction(re_git_action)
                contextMenu.addMenu(misc_options_menu)
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
                workshop_actions_menu = QMenu(title="Workshop mods options")
                if (
                    self.settings_controller.settings.local_folder
                    and convert_local_steamcmd_action
                ):
                    workshop_actions_menu.addAction(convert_local_steamcmd_action)
                if (
                    self.settings_controller.settings.local_folder
                    and convert_steamcmd_local_action
                ):
                    workshop_actions_menu.addAction(convert_steamcmd_local_action)
                if (
                    self.settings_controller.settings.local_folder
                    and convert_workshop_local_action
                ):
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
                contextMenu.addMenu(workshop_actions_menu)
            # Execute QMenu and return it's ACTION
            action = contextMenu.exec_(self.mapToGlobal(event.pos()))
            if action:  # Handle the action for all selected items
                if (  # ACTION: Update git mod(s)
                    action == re_git_action and len(git_paths) > 0
                ):
                    # Prompt user
                    answer = show_dialogue_conditional(
                        title="Are you sure?",
                        text=f"You have selected {len(git_paths)} git mods to be updated.",
                        information="Do you want to proceed?",
                    )
                    if answer == "&Yes":
                        logger.debug(f"Updating {len(git_paths)} git mod(s)")
                        self.re_git_signal.emit(git_paths)
                    return True
                elif (  # ACTION: Convert local mod(s) -> SteamCMD
                    action == convert_local_steamcmd_action
                    and len(local_steamcmd_name_to_publishedfileid) > 0
                ):
                    for (
                        folder_name,
                        publishedfileid,
                    ) in local_steamcmd_name_to_publishedfileid.items():
                        original_mod_path = str(
                            (
                                Path(self.settings_controller.settings.local_folder)
                                / folder_name
                            )
                        )
                        renamed_mod_path = str(
                            (
                                Path(self.settings_controller.settings.local_folder)
                                / publishedfileid
                            )
                        )
                        if os.path.exists(original_mod_path):
                            if not os.path.exists(renamed_mod_path):
                                try:
                                    os.rename(original_mod_path, renamed_mod_path)
                                    logger.debug(
                                        f'Successfully "converted" local mod -> SteamCMD by renaming from {folder_name} -> {publishedfileid}'
                                    )
                                except:
                                    stacktrace = format_exc()
                                    logger.error(
                                        f"Failed to convert mod: {original_mod_path}"
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
                    for (
                        publishedfileid,
                        mod_name,
                    ) in steamcmd_publishedfileid_to_name.items():
                        mod_name = (
                            sanitize_filename(mod_name)
                            if mod_name
                            else f"{publishedfileid}_local"
                        )
                        original_mod_path = str(
                            (
                                Path(self.settings_controller.settings.local_folder)
                                / publishedfileid
                            )
                        )
                        renamed_mod_path = str(
                            (
                                Path(self.settings_controller.settings.local_folder)
                                / mod_name
                            )
                        )
                        if os.path.exists(original_mod_path):
                            if not os.path.exists(renamed_mod_path):
                                try:
                                    os.rename(original_mod_path, renamed_mod_path)
                                    logger.debug(
                                        f'Successfully "converted" SteamCMD mod by renaming from {publishedfileid} -> {mod_name}'
                                    )
                                except:
                                    stacktrace = format_exc()
                                    logger.error(
                                        f"Failed to convert mod: {original_mod_path}"
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
                    logger.debug(steamcmd_publishedfileid_to_name)
                    # Prompt user
                    answer = show_dialogue_conditional(
                        title="Are you sure?",
                        text=f"You have selected {len(steamcmd_publishedfileid_to_name.keys())} mods for deletion + re-download.",
                        information="\nThis operation will recursively delete all mod files, except for .dds textures found, "
                        + "and attempt to re-download the mods via SteamCMD. Do you want to proceed?",
                    )
                    if answer == "&Yes":
                        logger.debug(
                            f"Deleting + redownloading {len(steamcmd_publishedfileid_to_name.keys())} SteamCMD mod(s)"
                        )
                        for path in steamcmd_mod_paths:
                            delete_files_except_extension(
                                directory=path, extension=".dds"
                            )
                        self.steamcmd_downloader_signal.emit(
                            list(steamcmd_publishedfileid_to_name.keys())
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
                                Path(self.settings_controller.settings.local_folder)
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
                            except:
                                stacktrace = format_exc()
                                logger.error(f"Failed to convert mod: {path}")
                                logger.error(stacktrace)
                    self.refresh_signal.emit()
                    return True
                elif (  # ACTION: Re-subscribe to mod(s) with Steam
                    action == re_steam_action and len(steam_publishedfileid_to_name) > 0
                ):
                    publishedfileids = steam_publishedfileid_to_name.keys()
                    # Prompt user
                    answer = show_dialogue_conditional(
                        title="Are you sure?",
                        text=f"You have selected {len(publishedfileids)} mods for unsubscribe + re-subscribe.",
                        information="\nThis operation will potentially delete .dds textures leftover. Steam is unreliable for this. Do you want to proceed?",
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
                        title="Are you sure?",
                        text=f"You have selected {len(publishedfileids)} mods for unsubscribe.",
                        information="\nDo you want to proceed?",
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
                    args, ok = show_dialogue_input(
                        title="Add comment",
                        text=f"Enter a comment providing your reasoning for wanting to blacklist this mod: "
                        + f'{self.metadata_manager.external_steam_metadata.get(steamdb_add_blacklist, {}).get("steamName", steamdb_add_blacklist)}',
                    )
                    if ok:
                        self.steamdb_blacklist_signal.emit(
                            [steamdb_add_blacklist, True, args]
                        )
                    else:
                        show_warning(
                            title="Unable to add to blacklist",
                            text="Comment was not provided or entry was cancelled. Comments are REQUIRED for this action!",
                        )
                    return True
                elif (
                    action == remove_from_steamdb_blacklist_action
                ):  # ACTION: Blacklist workshop mod in SteamDB
                    answer = show_dialogue_conditional(
                        title="Are you sure?",
                        text=f"This will remove the selected mod, "
                        + f'{self.metadata_manager.external_steam_metadata.get(steamdb_remove_blacklist, {}).get("steamName", steamdb_remove_blacklist)}, '
                        + "from your configured Steam DB blacklist."
                        + "\nDo you want to proceed?",
                    )
                    if answer == "&Yes":
                        self.steamdb_blacklist_signal.emit(
                            [steamdb_remove_blacklist, False]
                        )
                    return True
                elif action == delete_mod_action:  # ACTION: Delete mods action
                    answer = show_dialogue_conditional(
                        title="Are you sure?",
                        text=f"You have selected {len(selected_items)} mods for deletion.",
                        information="\nThis operation delete a mod's directory from the filesystem."
                        + "\nDo you want to proceed?",
                    )
                    if answer == "&Yes":
                        for source_item in selected_items:
                            if type(source_item) is QListWidgetItem:
                                source_widget = self.itemWidget(source_item)
                                widget_json_data = (
                                    self.metadata_manager.internal_local_metadata[
                                        source_widget.uuid
                                    ]
                                )
                                if not widget_json_data[
                                    "data_source"  # Disallow Official Expansions
                                ] == "expansion" or not widget_json_data[
                                    "packageid"
                                ].startswith(
                                    "ludeon.rimworld"
                                ):
                                    self.uuids.remove(source_item.data(Qt.UserRole))
                                    self.takeItem(self.row(source_item))
                                    rmtree(
                                        widget_json_data["path"],
                                        ignore_errors=False,
                                        onerror=handle_remove_read_only,
                                    )
                    return True
                elif action == delete_mod_keep_dds_action:  # ACTION: Delete mods action
                    answer = show_dialogue_conditional(
                        title="Are you sure?",
                        text=f"You have selected {len(selected_items)} mods for deletion.",
                        information="\nThis operation will recursively delete all mod files, except for .dds textures found."
                        + "\nDo you want to proceed?",
                    )
                    if answer == "&Yes":
                        for source_item in selected_items:
                            if type(source_item) is QListWidgetItem:
                                source_widget = self.itemWidget(source_item)
                                widget_json_data = (
                                    self.metadata_manager.internal_local_metadata[
                                        source_widget.uuid
                                    ]
                                )
                                if not widget_json_data[
                                    "data_source"  # Disallow Official Expansions
                                ] == "expansion" or not widget_json_data[
                                    "packageid"
                                ].startswith(
                                    "ludeon.rimworld"
                                ):
                                    self.uuids.remove(source_item.data(Qt.UserRole))
                                    self.takeItem(self.row(source_item))
                                    delete_files_except_extension(
                                        directory=widget_json_data["path"],
                                        extension=".dds",
                                    )
                    return True
                # Execute action for each selected mod
                for source_item in selected_items:
                    if type(source_item) is QListWidgetItem:
                        source_widget = self.itemWidget(source_item)
                        # Retrieve metadata
                        widget_json_data = (
                            self.metadata_manager.internal_local_metadata[
                                source_widget.uuid
                            ]
                        )
                        mod_data_source = widget_json_data.get("data_source")
                        mod_path = widget_json_data["path"]
                        # Toggle warning action
                        if action == toggle_warning_action:
                            self.toggle_warning(widget_json_data["packageid"])
                        # Open folder action
                        elif action == open_folder_action:  # ACTION: Open folder
                            if os.path.exists(mod_path):  # If the path actually exists
                                logger.info(f"Opening folder: {mod_path}")
                                platform_specific_open(mod_path)
                        # Open url action
                        elif (
                            action == open_url_browser_action
                        ):  # ACTION: Open URL in browser
                            if widget_json_data.get("url") or widget_json_data.get(
                                "steam_url"
                            ):  # If we have some form of "url" to work with...
                                url = None
                                if (
                                    mod_data_source == "expansion"
                                    or widget_json_data.get("steamcmd")
                                    or mod_data_source == "workshop"
                                ):
                                    url = widget_json_data.get(
                                        "steam_url", widget_json_data.get("url")
                                    )
                                elif (
                                    mod_data_source == "local"
                                    and not widget_json_data.get("steamcmd")
                                ):
                                    url = widget_json_data.get(
                                        "url", widget_json_data.get("steam_url")
                                    )
                                if url:
                                    logger.info(f"Opening url in browser: {url}")
                                    open_url_browser(url)
                        # Open Steam URI with Steam action
                        elif (
                            action == open_mod_steam_action
                        ):  # ACTION: Open steam:// uri in Steam
                            if widget_json_data.get(
                                "steam_uri"
                            ):  # If we have steam_uri
                                platform_specific_open(widget_json_data["steam_uri"])
                        # Copy to clipboard actions
                        elif (
                            action == copy_packageId_to_clipboard_action
                        ):  # ACTION: Copy packageId to clipboard
                            copy_to_clipboard(widget_json_data["packageid"])
                        elif (
                            action == copy_url_to_clipboard_action
                        ):  # ACTION: Copy URL to clipboard
                            if widget_json_data.get("url") or widget_json_data.get(
                                "steam_url"
                            ):  # If we have some form of "url" to work with...
                                url = None
                                if (
                                    mod_data_source == "expansion"
                                    or widget_json_data.get("steamcmd")
                                    or mod_data_source == "workshop"
                                ):
                                    url = widget_json_data.get(
                                        "steam_url", widget_json_data.get("url")
                                    )
                                elif (
                                    mod_data_source == "local"
                                    and not widget_json_data.get("steamcmd")
                                ):
                                    url = widget_json_data.get(
                                        "url", widget_json_data.get("steam_url")
                                    )
                                if url:
                                    copy_to_clipboard(url)
                        # Edit mod rules action
                        elif action == edit_mod_rules_action:
                            self.edit_rules_signal.emit(
                                True, "user_rules", widget_json_data["packageid"]
                            )
            return True
        return super().eventFilter(source_object, event)

    def focusOutEvent(self, e: QFocusEvent) -> None:
        """
        Slot to handle unhighlighting any items in the
        previous list when clicking out of that list.
        """
        self.clearFocus()
        return super().focusOutEvent(e)

    def keyPressEvent(self, e):
        """
        This event occurs when the user presses a key while the mod
        list is in focus.
        """
        key_pressed = QKeySequence(e.key()).toString()
        if (
            key_pressed == "Left"
            or key_pressed == "Right"
            or key_pressed == "Return"
            or key_pressed == "Space"
        ):
            self.key_press_signal.emit(key_pressed)
        else:
            return super().keyPressEvent(e)

    def handle_other_list_row_added(self, uuid: str) -> None:
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
        for idx in range(first, last + 1):
            item = self.item(idx)
            if item is not None and self.itemWidget(item) is None:
                uuid = item.data(Qt.UserRole)
                widget = ModListItemInner(
                    settings_controller=self.settings_controller,
                    uuid=uuid,
                )
                widget.toggle_warning_signal.connect(self.toggle_warning)
                if self.metadata_manager.internal_local_metadata[uuid].get("invalid"):
                    widget.main_label.setObjectName("summaryValueInvalid")
                else:
                    widget.main_label.setObjectName("ListItemLabel")
                # widget.main_label.style().unpolish(widget.main_label)
                # widget.main_label.style().polish(widget.main_label)
                item.setSizeHint(widget.sizeHint())
                self.setItemWidget(item, widget)
                self.uuids.insert(idx, uuid)
                self.item_added_signal.emit(uuid)

        if len(self.uuids) == self.count():
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
        if len(self.uuids) == self.count():
            self.list_update_signal.emit(str(self.count()))

    def get_item_widget_at_index(self, idx: int) -> Optional[ModListItemInner]:
        item = self.item(idx)
        if item:
            return self.itemWidget(item)
        return None

    def get_widgets_and_items(self) -> list[tuple[ModListItemInner, QListWidgetItem]]:
        return [
            (self.itemWidget(self.item(i)), self.item(i)) for i in range(self.count())
        ]

    def mod_clicked(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        """
        Method to handle clicking on a row or navigating between rows with
        the keyboard. Look up the mod's data by uuid
        """
        if current is not None:
            self.mod_info_signal.emit(current.data(Qt.UserRole))

    def mod_double_clicked(self, item: QListWidgetItem):
        widget = ModListItemInner = self.itemWidget(item)
        self.key_press_signal.emit("DoubleClick")

    def recreate_mod_list(self, list_type: str, uuids: List[str]) -> None:
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
                list_item = QListWidgetItem(self)
                list_item.setData(Qt.UserRole, uuid_key)
                self.addItem(list_item)
        else:  # ...unless we don't have mods, at which point reenable updates and exit
            self.setUpdatesEnabled(True)
            return
        # Enable updates and repaint
        self.setUpdatesEnabled(True)
        self.repaint()

    def toggle_warning(self, packageid: str) -> None:
        if not (packageid in self.ignore_warning_list):
            self.ignore_warning_list.append(packageid)
        else:
            self.ignore_warning_list.remove(packageid)
        self.recalculate_warnings_signal.emit()


class ModsPanel(QWidget):
    """
    This class controls the layout and functionality for the
    active/inactive mods list panel on the GUI.
    """

    list_updated_signal = Signal()

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
        self.list_updated = False

        # Base layout horizontal, sub-layouts vertical
        self.panel = QHBoxLayout()
        self.active_panel = QVBoxLayout()
        self.inactive_panel = QVBoxLayout()
        # Add vertical layouts to it
        self.panel.addLayout(self.inactive_panel)
        self.panel.addLayout(self.active_panel)

        # Instantiate WIDGETS

        self.data_source_filter_icons = [
            QIcon(str(AppInfo().theme_data_folder / "default-icons" / "AppIcon_b.png")),
            ModListIcons.ludeon_icon(),
            ModListIcons.local_icon(),
            ModListIcons.git_icon(),
            ModListIcons.steamcmd_icon(),
            ModListIcons.steam_icon(),
        ]

        self.mode_filter_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "filter.png")
        )
        self.mode_nofilter_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "nofilter.png")
        )

        # ACTIVE mod list widget
        self.active_mods_label = QLabel("Active [0]")
        self.active_mods_label.setAlignment(Qt.AlignCenter)
        self.active_mods_label.setObjectName("summaryValue")
        self.active_mods_list = ModListWidget(
            settings_controller=self.settings_controller,
        )
        # Active mods search widgets
        self.active_mods_search_layout = QHBoxLayout()
        self.active_mods_filter_data_source_index = 0
        self.active_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.active_mods_filter_data_source_index
        ]
        self.active_mods_filter_data_source_button = QToolButton()
        self.active_mods_filter_data_source_button.setIcon(
            self.data_source_filter_icons[self.active_mods_filter_data_source_index]
        )
        self.active_mods_filter_data_source_button.clicked.connect(
            self.on_active_mods_search_data_source_filter
        )
        self.active_mods_search_filter_state = True
        self.active_mods_search_mode_filter_button = QToolButton()
        self.active_mods_search_mode_filter_button.setIcon(self.mode_filter_icon)
        self.active_mods_search_mode_filter_button.clicked.connect(
            self.on_active_mods_mode_filter_toggle
        )
        self.active_mods_search = QLineEdit()
        self.active_mods_search.setClearButtonEnabled(True)
        self.active_mods_search.textChanged.connect(self.on_active_mods_search)
        self.active_mods_search.inputRejected.connect(self.on_active_mods_search_clear)
        self.active_mods_search.setPlaceholderText("Search by...")
        self.active_mods_search_clear_button = self.active_mods_search.findChild(
            QToolButton
        )
        self.active_mods_search_clear_button.setEnabled(True)
        self.active_mods_search_clear_button.clicked.connect(
            self.on_active_mods_search_clear
        )
        self.active_mods_search_filter = QComboBox()
        self.active_mods_search_filter.setObjectName("MainUI")
        self.active_mods_search_filter.setMaximumWidth(125)
        self.active_mods_search_filter.addItems(
            ["Name", "PackageId", "Author(s)", "PublishedFileId"]
        )
        # Active mods search layouts
        self.active_mods_search_layout.addWidget(
            self.active_mods_filter_data_source_button
        )
        self.active_mods_search_layout.addWidget(
            self.active_mods_search_mode_filter_button
        )
        self.active_mods_search_layout.addWidget(self.active_mods_search, 45)
        self.active_mods_search_layout.addWidget(self.active_mods_search_filter, 70)
        # Active mods list Errors/warnings widgets
        self.errors_summary_frame = QFrame()
        self.errors_summary_frame.setObjectName("errorFrame")
        self.errors_summary_layout = QHBoxLayout()
        self.errors_summary_layout.setContentsMargins(0, 0, 0, 0)
        self.errors_summary_layout.setSpacing(2)
        self.warnings_icon = QLabel()
        self.warnings_icon.setPixmap(ModListIcons.warning_icon().pixmap(QSize(20, 20)))
        self.warnings_text = QLabel("0 warnings(s)")
        self.warnings_text.setObjectName("summaryValue")
        self.errors_icon = QLabel()
        self.errors_icon.setPixmap(ModListIcons.error_icon().pixmap(QSize(20, 20)))
        self.errors_text = QLabel("0 error(s)")
        self.errors_text.setObjectName("summaryValue")
        self.warnings_layout = QHBoxLayout()
        self.warnings_layout.addWidget(self.warnings_icon, 1)
        self.warnings_layout.addWidget(self.warnings_text, 99)
        self.errors_layout = QHBoxLayout()
        self.errors_layout.addWidget(self.errors_icon, 1)
        self.errors_layout.addWidget(self.errors_text, 99)
        self.errors_summary_layout.addLayout(self.warnings_layout, 50)
        self.errors_summary_layout.addLayout(self.errors_layout, 50)
        self.errors_summary_frame.setLayout(self.errors_summary_layout)
        self.errors_summary_frame.setHidden(True)
        # Add active mods widgets to layouts
        self.active_panel.addWidget(self.active_mods_label, 1)
        self.active_panel.addLayout(self.active_mods_search_layout, 1)
        self.active_panel.addWidget(self.active_mods_list, 97)
        self.active_panel.addWidget(self.errors_summary_frame, 1)

        # INACTIVE mod list widgets
        self.inactive_mods_label = QLabel("Inactive [0]")
        self.inactive_mods_label.setAlignment(Qt.AlignCenter)
        self.inactive_mods_label.setObjectName("summaryValue")
        self.inactive_mods_list = ModListWidget(
            settings_controller=self.settings_controller,
        )
        # Inactive mods search widgets
        self.inactive_mods_search_layout = QHBoxLayout()
        self.inactive_mods_filter_data_source_index = 0
        self.inactive_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.inactive_mods_filter_data_source_index
        ]
        self.inactive_mods_filter_data_source_button = QToolButton()
        self.inactive_mods_filter_data_source_button.setIcon(
            self.data_source_filter_icons[self.inactive_mods_filter_data_source_index]
        )
        self.inactive_mods_filter_data_source_button.clicked.connect(
            self.on_inactive_mods_search_data_source_filter
        )
        self.inactive_mods_search_filter_state = True
        self.inactive_mods_search_mode_filter_button = QToolButton()
        self.inactive_mods_search_mode_filter_button.setIcon(self.mode_filter_icon)
        self.inactive_mods_search_mode_filter_button.clicked.connect(
            self.on_inactive_mods_mode_filter_toggle
        )
        self.inactive_mods_search = QLineEdit()
        self.inactive_mods_search.setClearButtonEnabled(True)
        self.inactive_mods_search.textChanged.connect(self.on_inactive_mods_search)
        self.inactive_mods_search.inputRejected.connect(
            self.on_inactive_mods_search_clear
        )
        self.inactive_mods_search.setPlaceholderText("Search by...")
        self.inactive_mods_search_clear_button = self.inactive_mods_search.findChild(
            QToolButton
        )
        self.inactive_mods_search_clear_button.setEnabled(True)
        self.inactive_mods_search_clear_button.clicked.connect(
            self.on_inactive_mods_search_clear
        )
        self.inactive_mods_search_filter = QComboBox()
        self.inactive_mods_search_filter.setObjectName("MainUI")
        self.inactive_mods_search_filter.setMaximumWidth(140)
        self.inactive_mods_search_filter.addItems(
            ["Name", "PackageId", "Author(s)", "PublishedFileId"]
        )
        # Inactive mods search layouts
        self.inactive_mods_search_layout.addWidget(
            self.inactive_mods_filter_data_source_button
        )
        self.inactive_mods_search_layout.addWidget(
            self.inactive_mods_search_mode_filter_button
        )
        self.inactive_mods_search_layout.addWidget(self.inactive_mods_search, 45)
        self.inactive_mods_search_layout.addWidget(self.inactive_mods_search_filter, 70)
        # Add inactive mods widgets to layout
        self.inactive_panel.addWidget(self.inactive_mods_label)
        self.inactive_panel.addLayout(self.inactive_mods_search_layout)
        self.inactive_panel.addWidget(self.inactive_mods_list)

        # Adding Completer.
        # self.completer = QCompleter(self.active_mods_list.get_list_items())
        # self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        # self.active_mods_search.setCompleter(self.completer)
        # self.inactive_mods_search.setCompleter(self.completer)

        # Connect signals and slots
        self.active_mods_list.list_update_signal.connect(
            self.on_active_mods_list_updated
        )
        # Connect signals and slots
        self.inactive_mods_list.list_update_signal.connect(
            self.on_inactive_mods_list_updated
        )

        logger.debug("Finished ModsPanel initialization")

    def mod_list_updated(self, count: str, list_type: str) -> None:
        if list_type == "Active":
            # First time, and when Refreshing, the slot will evaluate false and do nothing.
            # The purpose of this is for the _do_save_animation slot in the main_content_panel
            self.list_updated_signal.emit()
            self.list_updated = True
        # 'drop' indicates that the update was just a drag and drop
        # within the list.
        if count != "drop":
            logger.info(f"{list_type} mod count changed to: {count}")
            self.update_count(list_type=list_type)
        if list_type == "Active":
            self.recalculate_active_mods()  # Recalculate active mod list errors/warnings

    def recalculate_active_mods(self) -> None:
        """
        Whenever the active mod list has items added to it,
        or has items removed from it, or has items rearranged around within it,
        calculate the internal list errors for the active mod list
        """
        logger.info("Recalculating internal list errors")

        internal_local_metadata = self.metadata_manager.internal_local_metadata
        game_version = self.metadata_manager.game_version
        info_from_steam = self.metadata_manager.info_from_steam_package_id_to_name

        packageid_to_uuid = {
            internal_local_metadata[uuid]["packageid"]: uuid
            for uuid in self.active_mods_list.uuids
        }
        package_ids_set = set(packageid_to_uuid.keys())

        package_id_to_errors = {
            uuid: {
                "missing_dependencies": set(),
                "conflicting_incompatibilities": set(),
                "load_before_violations": set(),
                "load_after_violations": set(),
                "version_mismatch": True,
            }
            for uuid in self.active_mods_list.uuids
        }

        num_warnings = 0
        total_warning_text = ""
        num_errors = 0
        total_error_text = ""

        for uuid, mod_errors in package_id_to_errors.items():
            current_mod_index = self.active_mods_list.uuids.index(uuid)
            mod_data = internal_local_metadata[uuid]

            # Check version for everything except Core
            if game_version and mod_data.get("supportedversions", {}).get("li"):
                supported_versions = mod_data["supportedversions"]["li"]
                if isinstance(supported_versions, str):
                    if game_version.startswith(supported_versions):
                        mod_errors["version_mismatch"] = False
                elif isinstance(supported_versions, list):
                    mod_errors["version_mismatch"] = (
                        not any(
                            [
                                ver
                                for ver in supported_versions
                                if game_version.startswith(ver)
                            ]
                        )
                        and mod_data["packageid"]
                        not in self.active_mods_list.ignore_warning_list
                    )
                else:
                    logger.error(
                        f"supportedversions value not str or list: {supported_versions}"
                    )

            if (
                mod_data.get("packageid")
                and mod_data["packageid"]
                not in self.active_mods_list.ignore_warning_list
            ):
                # Check dependencies
                mod_errors["missing_dependencies"] = {
                    dep
                    for dep in mod_data.get("dependencies", [])
                    if dep not in package_ids_set
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
                        <= self.active_mods_list.uuids.index(
                            packageid_to_uuid[load_this_before[0]]
                        )
                    ):
                        mod_errors["load_before_violations"].add(load_this_before[0])

                # Check loadTheseAfter
                for load_this_after in mod_data.get("loadTheseAfter", []):
                    if (
                        load_this_after[1]
                        and load_this_after[0] in packageid_to_uuid
                        and current_mod_index
                        >= self.active_mods_list.uuids.index(
                            packageid_to_uuid[load_this_after[0]]
                        )
                    ):
                        mod_errors["load_after_violations"].add(load_this_after[0])

            # Consolidate results
            self.ignore_error = self.active_mods_list.ignore_warning_list

            # Set icon if necessary
            item_widget_at_index = self.active_mods_list.get_item_widget_at_index(
                current_mod_index
            )
            if item_widget_at_index:
                tool_tip_text = ""
                for error_type, tooltip_header in [
                    ("missing_dependencies", "\nMissing Dependencies:"),
                    ("conflicting_incompatibilities", "\nIncompatibilities:"),
                    ("load_before_violations", "\nShould be Loaded After:"),
                    ("load_after_violations", "\nShould be Loaded Before:"),
                ]:
                    if mod_errors[error_type]:
                        tool_tip_text += tooltip_header
                        for key in mod_errors[error_type]:
                            name = internal_local_metadata.get(
                                packageid_to_uuid.get(key), {}
                            ).get("name", info_from_steam.get(key, key))
                            tool_tip_text += f"\n  * {name}"

                if mod_errors["version_mismatch"] and not self.ignore_error:
                    tool_tip_text += "\n\nMod and Game Version Mismatch"

                if tool_tip_text:
                    item_widget_at_index.warning_icon_label.setHidden(False)
                    item_widget_at_index.warning_icon_label.setToolTip(
                        tool_tip_text.lstrip()
                    )
                else:
                    item_widget_at_index.warning_icon_label.setHidden(True)
                    item_widget_at_index.warning_icon_label.setToolTip("")

                # Add to error/warnings summary if necessary
                if any(
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

                if any(
                    [
                        mod_errors[key]
                        for key in [
                            "load_before_violations",
                            "load_after_violations",
                            "version_mismatch",
                        ]
                    ]
                ):
                    num_warnings += 1
                    total_warning_text += f"\n\n{mod_data['name']}"
                    total_warning_text += "\n============================="
                    total_warning_text += tool_tip_text

        if total_error_text or total_warning_text or num_errors or num_warnings:
            self.errors_summary_frame.setHidden(False)
            self.warnings_text.setText(f"{num_warnings} warnings(s)")
            self.errors_text.setText(f"{num_errors} errors(s)")
            if total_error_text:
                self.errors_icon.setToolTip(total_error_text.lstrip())
            if total_warning_text:
                self.warnings_icon.setToolTip(total_warning_text.lstrip())
        else:
            self.errors_summary_frame.setHidden(True)
            self.warnings_text.setText("0 warnings(s)")
            self.errors_text.setText("0 errors(s)")
            self.errors_icon.setToolTip("")
            self.warnings_icon.setToolTip("")

        logger.info("Finished recalculating internal list errors")

    def on_active_mods_list_updated(self, count: str) -> None:
        self.mod_list_updated(count=count, list_type="Active")

    def on_active_mods_search(self, pattern: str) -> None:
        self.signal_search_and_filters(list_type="Active", pattern=pattern)

    def on_active_mods_search_clear(self) -> None:
        self.signal_clear_search(list_type="Active")

    def on_active_mods_search_data_source_filter(self) -> None:
        self.signal_search_source_filter(list_type="Active")

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

    def on_inactive_mods_mode_filter_toggle(self) -> None:
        self.signal_search_mode_filter(list_type="Inactive")

    def signal_clear_search(self, list_type: str) -> None:
        if list_type == "Active":
            self.active_mods_search.clear()
            self.signal_search_and_filters(list_type=list_type, pattern="")
            self.active_mods_search.clearFocus()
        elif list_type == "Inactive":
            self.inactive_mods_search.clear()
            self.signal_search_and_filters(list_type=list_type, pattern="")
            self.inactive_mods_search.clearFocus()

    def signal_search_and_filters(self, list_type: str, pattern: str) -> None:
        _filter = None
        filter_state = None
        source_filter = None
        uuids = None

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

        search_filter = None
        if _filter.currentText() == "Name":
            search_filter = "name"
        elif _filter.currentText() == "PackageId":
            search_filter = "packageid"
        elif _filter.currentText() == "Author(s)":
            search_filter = "authors"
        elif _filter.currentText() == "PublishedFileId":
            search_filter = "publishedfileid"

        for uuid in uuids:
            item = (
                self.active_mods_list.item(uuids.index(uuid))
                if list_type == "Active"
                else self.inactive_mods_list.item(uuids.index(uuid))
            )
            widget = (
                self.active_mods_list.itemWidget(item)
                if list_type == "Active"
                else self.inactive_mods_list.itemWidget(item)
            )

            metadata = self.metadata_manager.internal_local_metadata[uuid]
            invalid = metadata.get("invalid")
            if invalid:
                continue

            filtered = False

            if (
                pattern
                and metadata.get(search_filter)
                and pattern.lower() not in str(metadata.get(search_filter)).lower()
            ):
                filtered = True
            elif source_filter == "all":
                filtered = False
            elif source_filter == "git_repo":
                filtered = not metadata.get("git_repo")
            elif source_filter == "steamcmd":
                filtered = not metadata.get("steamcmd")
            elif source_filter != metadata.get("data_source"):
                filtered = True

            repolish = False

            if filter_state:
                item.setHidden(filtered)
                if widget.main_label.objectName() == "ListItemLabelFiltered":
                    widget.main_label.setObjectName("ListItemLabel")
                    repolish = True
            else:
                widget.main_label.setObjectName(
                    "ListItemLabelFiltered" if filtered else "ListItemLabel"
                )
                repolish = True
                if (
                    widget.main_label.objectName() == "ListItemLabelFiltered"
                    and item.isHidden()
                ):
                    item.setHidden(False)

            if repolish:
                widget.main_label.style().unpolish(widget.main_label)
                widget.main_label.style().polish(widget.main_label)

        self.update_count(list_type=list_type)

    def signal_search_mode_filter(self, list_type: str) -> None:
        filter_state = False
        icon = self.mode_nofilter_icon
        if list_type == "Active":
            filter_state = self.active_mods_search_filter_state
            self.active_mods_search_filter_state = not filter_state
            self.active_mods_search_mode_filter_button.setIcon(self.mode_filter_icon)
            pattern = self.active_mods_search.text()
        elif list_type == "Inactive":
            filter_state = self.inactive_mods_search_filter_state
            self.inactive_mods_search_filter_state = not filter_state
            self.inactive_mods_search_mode_filter_button.setIcon(self.mode_filter_icon)
            pattern = self.inactive_mods_search.text()

        self.signal_search_and_filters(list_type=list_type, pattern=pattern)

    def signal_search_source_filter(self, list_type: str) -> None:
        if list_type == "Active":
            button = self.active_mods_filter_data_source_button
            search = self.active_mods_search
            source_index = self.active_mods_filter_data_source_index
        elif list_type == "Inactive":
            button = self.inactive_mods_filter_data_source_button
            search = self.inactive_mods_search
            source_index = self.inactive_mods_filter_data_source_index
        # Indexes by the icon
        if source_index < (len(self.data_source_filter_icons) - 1):
            source_index += 1
        else:
            source_index = 0
        button.setIcon(self.data_source_filter_icons[source_index])
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
        # Filter widgets by data source, while preserving any active search pattern
        self.signal_search_and_filters(list_type=list_type, pattern=search.text())

    def update_count(self, list_type: str) -> None:
        # Calculate filtered items
        label = (
            self.active_mods_label
            if list_type == "Active"
            else self.inactive_mods_label
        )
        mods_list = (
            self.active_mods_list if list_type == "Active" else self.inactive_mods_list
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
            if (
                item.isHidden()
                or mods_list.itemWidget(item).main_label.objectName()
                == "ListItemLabelFiltered"
            ):
                num_filtered += 1
            else:
                num_unfiltered += 1
        if search.text():
            label.setText(
                f"{list_type} [{num_unfiltered}/{num_filtered + num_unfiltered}]"
            )
        else:
            label.setText(f"{list_type} [{num_filtered + num_unfiltered}]")
