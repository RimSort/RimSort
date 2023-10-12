# Need rework

from logger_tt import logger
import os
import shutil
from pathlib import Path
from time import sleep
import traceback
from typing import Any, List, Optional

from pyperclip import copy as copy_to_clipboard
from PySide6.QtCore import Qt, QEvent, QModelIndex, QObject, Signal
from PySide6.QtGui import QAction, QCursor, QDropEvent, QFocusEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QMenu,
)

from model.mod_list_item import ModListItemInner
from model.dialogue import show_dialogue_conditional, show_dialogue_input, show_warning
from util.generic import (
    delete_files_except_extension,
    handle_remove_read_only,
    open_url_browser,
    platform_specific_open,
    sanitize_filename,
)
from util.metadata import MetadataManager
from util.steam.steamcmd.wrapper import SteamcmdInterface
from view.game_configuration_panel import GameConfiguration


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

    def __init__(self, mod_type_filter_enable: bool) -> None:
        """
        Initialize the ListWidget with a dict of mods.
        Keys are the package ids and values are a dict of
        mod attributes. See tags:
        https://rimworldwiki.com/wiki/About.xml
        """
        logger.debug("Initializing ModListWidget")

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

        # Store icon paths
        self.mod_type_filter_enable = mod_type_filter_enable
        self.csharp_icon_path = str(
            Path(
                os.path.join(os.path.dirname(__file__), "../data/csharp.png")
            ).resolve()
        )
        self.xml_icon_path = str(
            Path(os.path.join(os.path.dirname(__file__), "../data/xml.png")).resolve()
        )
        self.git_icon_path = str(
            Path(os.path.join(os.path.dirname(__file__), "../data/git.png")).resolve()
        )
        self.local_icon_path = str(
            Path(
                os.path.join(os.path.dirname(__file__), "../data/local_icon.png")
            ).resolve()
        )
        self.ludeon_icon_path = str(
            Path(
                os.path.join(os.path.dirname(__file__), "../data/ludeon_icon.png")
            ).resolve()
        )
        self.steamcmd_icon_path = str(
            Path(
                os.path.join(os.path.dirname(__file__), "../data/steamcmd_icon.png")
            ).resolve()
        )
        self.steam_icon_path = str(
            Path(
                os.path.join(os.path.dirname(__file__), "../data/steam_icon.png")
            ).resolve()
        )
        self.warning_icon_path = str(
            Path(
                os.path.join(os.path.dirname(__file__), "../data/warning.png")
            ).resolve()
        )
        self.error_icon_path = str(
            Path(os.path.join(os.path.dirname(__file__), "../data/error.png")).resolve()
        )

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
        self.uuids = set()
        self.ignore_warning_list = []
        logger.debug("Finished ModListWidget initialization")

    def dropEvent(self, event: QDropEvent) -> None:
        ret = super().dropEvent(event)
        self.list_update_signal.emit("drop")
        return ret

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
                    widget_json_data = source_widget.json_data
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
                            MetadataManager.instance().external_steam_metadata
                            and publishedfileid
                            and publishedfileid
                            in MetadataManager.instance().external_steam_metadata.keys()
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
                        MetadataManager.instance().external_steam_metadata
                        and widget_json_data.get("publishedfileid")
                    ):
                        publishedfileid = widget_json_data["publishedfileid"]
                        if (
                            MetadataManager.instance()
                            .external_steam_metadata.get(publishedfileid, {})
                            .get("blacklist")
                        ):
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
                        widget_json_data = source_widget.json_data
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
                                MetadataManager.instance().external_steam_metadata
                                and publishedfileid
                                and publishedfileid
                                in MetadataManager.instance().external_steam_metadata.keys()
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
                    GameConfiguration.instance().local_folder_line.text()
                    and convert_local_steamcmd_action
                ):
                    workshop_actions_menu.addAction(convert_local_steamcmd_action)
                if (
                    GameConfiguration.instance().local_folder_line.text()
                    and convert_steamcmd_local_action
                ):
                    workshop_actions_menu.addAction(convert_steamcmd_local_action)
                if (
                    GameConfiguration.instance().local_folder_line.text()
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
                            Path(
                                os.path.join(
                                    GameConfiguration.instance().local_folder_line.text(),
                                    folder_name,
                                )
                            ).resolve()
                        )
                        renamed_mod_path = str(
                            Path(
                                os.path.join(
                                    GameConfiguration.instance().local_folder_line.text(),
                                    publishedfileid,
                                )
                            ).resolve()
                        )
                        if os.path.exists(original_mod_path):
                            if not os.path.exists(renamed_mod_path):
                                try:
                                    os.rename(original_mod_path, renamed_mod_path)
                                    logger.debug(
                                        f'Successfully "converted" local mod -> SteamCMD by renaming from {folder_name} -> {publishedfileid}'
                                    )
                                except:
                                    stacktrace = traceback.format_exc()
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
                            Path(
                                os.path.join(
                                    GameConfiguration.instance().local_folder_line.text(),
                                    publishedfileid,
                                )
                            ).resolve()
                        )
                        renamed_mod_path = str(
                            Path(
                                os.path.join(
                                    GameConfiguration.instance().local_folder_line.text(),
                                    mod_name,
                                )
                            ).resolve()
                        )
                        if os.path.exists(original_mod_path):
                            if not os.path.exists(renamed_mod_path):
                                try:
                                    os.rename(original_mod_path, renamed_mod_path)
                                    logger.debug(
                                        f'Successfully "converted" SteamCMD mod by renaming from {publishedfileid} -> {mod_name}'
                                    )
                                except:
                                    stacktrace = traceback.format_exc()
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
                            Path(
                                os.path.join(
                                    GameConfiguration.instance().local_folder_line.text(),
                                    mod_name
                                    if mod_name
                                    else publishedfileid_from_folder_name,
                                )
                            ).resolve()
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
                                    shutil.copytree(path, renamed_mod_path)
                                except FileExistsError:
                                    for root, dirs, files in os.walk(path):
                                        dest_dir = root.replace(path, renamed_mod_path)
                                        if not os.path.isdir(dest_dir):
                                            os.makedirs(dest_dir)
                                        for file in files:
                                            src_file = os.path.join(root, file)
                                            dst_file = os.path.join(dest_dir, file)
                                            shutil.copy2(src_file, dst_file)
                                logger.debug(
                                    f'Successfully "converted" Steam mod by copying {publishedfileid_from_folder_name} -> {mod_name} and migrating mod to local mods directory'
                                )
                            except:
                                stacktrace = traceback.format_exc()
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
                        + f'{MetadataManager.instance().external_steam_metadata.get(steamdb_add_blacklist, {}).get("steamName", steamdb_add_blacklist)}',
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
                        + f'{MetadataManager.instance().external_steam_metadata.get(steamdb_remove_blacklist, {}).get("steamName", steamdb_remove_blacklist)}, '
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
                                widget_json_data = source_widget.json_data
                                if not widget_json_data[
                                    "data_source"  # Disallow Official Expansions
                                ] == "expansion" or not widget_json_data[
                                    "packageid"
                                ].startswith(
                                    "ludeon.rimworld"
                                ):
                                    self.takeItem(self.row(source_item))
                                    shutil.rmtree(
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
                                widget_json_data = source_widget.json_data
                                if not widget_json_data[
                                    "data_source"  # Disallow Official Expansions
                                ] == "expansion" or not widget_json_data[
                                    "packageid"
                                ].startswith(
                                    "ludeon.rimworld"
                                ):
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
                        widget_json_data = source_widget.json_data
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
        self.uuids.discard(uuid)

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
        through a set of package_ids (this is imperfect, we will need to switch
        this to using UUID keys TODO). This way, we easily compare `self.count()`
        to the length of the set.

        :param parent: parent to get rows under (not used)
        :param first: index of first item inserted
        :param last: index of last item inserted
        """
        for idx in range(first, last + 1):
            item = self.item(idx)
            if item is not None and self.itemWidget(item) is None:
                data = item.data(Qt.UserRole)
                widget = ModListItemInner(
                    data,
                    mod_type_filter_enable=self.mod_type_filter_enable,
                    csharp_icon_path=self.csharp_icon_path,
                    xml_icon_path=self.xml_icon_path,
                    git_icon_path=self.git_icon_path,
                    local_icon_path=self.local_icon_path,
                    ludeon_icon_path=self.ludeon_icon_path,
                    steamcmd_icon_path=self.steamcmd_icon_path,
                    steam_icon_path=self.steam_icon_path,
                    warning_icon_path=self.warning_icon_path,
                )
                widget.toggle_warning_signal.connect(self.toggle_warning)
                if data.get("invalid"):
                    widget.main_label.setStyleSheet("QLabel { color : red; }")
                item.setSizeHint(widget.sizeHint())
                self.setItemWidget(item, widget)
                self.uuids.add(data["uuid"])
                self.item_added_signal.emit(data["uuid"])

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

    def get_list_items_by_dict(self) -> dict[str, Any]:
        """
        Get a dict of all row item's widgets data. Equal to `mods` in
        recreate mod list.

        :return: a dict of mod data
        """
        logger.info("Returning a list of all mod items by json data")
        mod_dict = {}
        for i in range(self.count()):
            item = self.itemWidget(self.item(i))
            if item:
                # Assume uuid always there, as this should be added when the list item's json data is populated
                mod_dict[item.json_data["uuid"]] = item.json_data
        logger.info(f"Collected json data for {len(mod_dict)} mods")
        return mod_dict

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
            self.mod_info_signal.emit(current.data(Qt.UserRole)["uuid"])

    def mod_double_clicked(self, item: QListWidgetItem):
        widget = ModListItemInner = self.itemWidget(item)
        self.key_press_signal.emit("DoubleClick")

    def recreate_mod_list(self, list_type: str, mods: dict[str, Any]) -> None:
        """
        Clear all mod items and add new ones from a dict.

        :param mods: dict of mod data
        """
        logger.info(f"Internally recreating {list_type} mod list")
        # Disable updates
        self.setUpdatesEnabled(False)
        # Clear list
        self.clear()
        self.uuids = set()
        if mods:  # Insert data...
            for mod_json_data in mods.values():
                list_item = QListWidgetItem(self)
                list_item.setData(Qt.UserRole, mod_json_data)
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
