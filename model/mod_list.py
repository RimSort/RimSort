from logger_tt import logger
import os
import shutil
import webbrowser
from pathlib import Path
from time import sleep
from typing import Any, Optional

from PySide6.QtCore import Qt, QEvent, QModelIndex, QObject, Signal
from PySide6.QtGui import QAction, QDropEvent, QFocusEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QMenu,
)

from model.mod_list_item import ModListItemInner
from model.dialogue import show_warning
from util.generic import platform_specific_open


class ModListWidget(QListWidget):
    """
    Subclass for QListWidget. Used to store lists for
    active and inactive mods. Mods can be rearranged within
    their own lists or moved from one list to another.
    """

    item_added_signal = Signal(str)
    list_update_signal = Signal(str)
    mod_info_signal = Signal(str)
    refresh_signal = Signal(str)
    steamworks_subscription_signal = Signal(list)
    key_press_signal = Signal(str)

    def __init__(self) -> None:
        """
        Initialize the ListWidget with a dict of mods.
        Keys are the package ids and values are a dict of
        mod attributes. See tags:
        https://rimworldwiki.com/wiki/About.xml
        """
        logger.info("Starting ModListWidget initialization")

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
        self.local_icon_path = str(
            Path(
                os.path.join(os.path.dirname(__file__), "../data/local_icon.png")
            ).resolve()
        )
        self.steam_icon_path = str(
            Path(
                os.path.join(os.path.dirname(__file__), "../data/steam_icon.png")
            ).resolve()
        )
        self.ludeon_icon_path = str(
            Path(
                os.path.join(os.path.dirname(__file__), "../data/ludeon_icon.png")
            ).resolve()
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

        logger.info("Finished ModListWidget initialization")

    def eventFilter(self, source_object: QObject, event: QEvent) -> None:
        """
        https://doc.qt.io/qtforpython/overviews/eventsandfilters.html

        Takes source object and filters an event at the ListWidget level, executes
        an action based on a per-mod_list_item contextMenu

        :param object: the source object returned from the event
        :param event: the QEvent type
        """
        if event.type() == QEvent.ContextMenu and source_object is self:
            logger.info("USER ACTION: Open right-click mod_list_item contextMenu")
            contextMenu = QMenu()
            source_item = source_object.itemAt(
                event.pos()
            )  # Which QListWidgetItem was right clicked?
            if type(source_item) is QListWidgetItem:
                source_widget = self.itemWidget(source_item)
                widget_json_data = source_widget.json_data
                mod_data_source = widget_json_data.get("data_source")
                widget_package_id = widget_json_data["packageId"]
                mod_path = widget_json_data[
                    "path"
                ]  # Set local data folder path from metadata
                open_folder = contextMenu.addAction("Open folder")  # Open folder
                if widget_json_data.get("url") or widget_json_data.get("steam_url"):
                    url = self.get_mod_url(widget_json_data)
                    if url != "":
                        open_url_browser = contextMenu.addAction(
                            "Open URL in browser"
                        )  # Open URL in browser
                    else:
                        show_warning(
                            f"No URL was returned to open from mod metadata... Is the metadata correct? Result: {url}"
                        )
                if widget_json_data.get("steam_uri"):
                    steam_uri = widget_json_data.get("steam_uri")
                    open_mod_steam = contextMenu.addAction("Open mod in Steam")
                if mod_data_source == "workshop" and widget_json_data.get(
                    "publishedfileid"
                ):
                    mod_pfid = widget_json_data["publishedfileid"]
                    unsubscribe_delete_mod = contextMenu.addAction(
                        "Unsubscribe + delete mod"
                    )  # Unsubscribe + delete mod
                else:
                    delete_mod = contextMenu.addAction("Delete mod")  # Delete mod
                action = contextMenu.exec_(
                    self.mapToGlobal(event.pos())
                )  # Execute QMenu and return it's ACTION
                if action == open_folder:  # ACTION: Open folder
                    if os.path.exists(mod_path):  # If the path actually exists
                        logger.info(f"Opening folder: {mod_path}")
                        platform_specific_open(mod_path)  # Open it
                    else:  # Otherwise, warn & do nothing
                        show_warning(
                            "Cannot 'Open folder'!",
                            f"Failed to 'Open folder' for {widget_package_id}! ",
                            f"Path does not exist: {mod_path}",
                        )
                        logger.warning(
                            f"Failed to 'Open folder' for {widget_package_id}! "
                            + f"Path does not exist: {mod_path}"
                        )
                if (
                    "open_url_browser" in locals()
                ):  # This action is conditionally created
                    if action == open_url_browser:  # ACTION: Open URL in browser
                        logger.info(f"Opening url in browser: {url}")
                        self.open_mod_url(url)
                if "open_mod_steam" in locals():  # This action is conditionally created
                    if action == open_mod_steam:  # ACTION: Open steam:// uri in Steam
                        platform_specific_open(steam_uri)
                if "delete_mod" in locals():  # This action is conditionally created
                    if action == delete_mod:  # ACTION: Delete mod
                        logger.info(f"Deleting mod at: {mod_path}")
                        shutil.rmtree(mod_path)
                if (
                    "unsubscribe_delete_mod" in locals()
                ):  # This action is conditionally created
                    if (
                        action == unsubscribe_delete_mod
                    ):  # ACTION: Unsubscribe & delete mod
                        logger.info(f"Unsubscribing from mod: {mod_pfid}")
                        self.steamworks_subscription_signal.emit(
                            ["unsubscribe", int(mod_pfid)]
                        )
            return True
        return super().eventFilter(source_object, event)

    def recreate_mod_list(self, mods: dict[str, Any]) -> None:
        """
        Clear all mod items and add new ones from a dict.

        :param mods: dict of mod data
        """
        logger.info("Internally recreating mod list")
        self.clear()
        self.uuids = set()
        if mods:
            for mod_json_data in mods.values():
                list_item = QListWidgetItem(self)
                list_item.setData(Qt.UserRole, mod_json_data)
                self.addItem(list_item)

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
        has an inefficiency: it is only able to insert one at a time. This means
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
                    self.local_icon_path,
                    self.steam_icon_path,
                    self.ludeon_icon_path,
                )
                if data.get("invalid"):
                    widget.main_label.setStyleSheet("QLabel { color : red; }")
                item.setSizeHint(widget.sizeHint())
                self.setItemWidget(item, widget)
                self.uuids.add(data["uuid"])
                self.item_added_signal.emit(data["uuid"])

        if len(self.uuids) == self.count():
            self.list_update_signal.emit(str(self.count()))

    def handle_other_list_row_added(self, uuid: str) -> None:
        self.uuids.discard(uuid)

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

    def dropEvent(self, event: QDropEvent) -> None:
        ret = super().dropEvent(event)
        self.list_update_signal.emit("drop")
        return ret

    def get_item_widget_at_index(self, idx: int) -> Optional[ModListItemInner]:
        item = self.item(idx)
        if item:
            return self.itemWidget(item)
        return None

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

    def get_widgets_and_items(self) -> list[tuple[ModListItemInner, QListWidgetItem]]:
        return [
            (self.itemWidget(self.item(i)), self.item(i)) for i in range(self.count())
        ]

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

    def focusOutEvent(self, e: QFocusEvent) -> None:
        """
        Slot to handle unhighlighting any items in the
        previous list when clicking out of that list.
        """
        self.clearFocus()
        return super().focusOutEvent(e)

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

    def get_mod_url(self, widget_json_data) -> str:
        url = ""
        if (  # Workshop mod URL priority: steam_url > url
            widget_json_data["data_source"] == "workshop"
        ):  # If the mod was parsed from a Steam mods source
            if widget_json_data.get("steam_url") and isinstance(
                widget_json_data["steam_url"], str
            ):  # If the steam_url exists
                url = widget_json_data.get("steam_url")  # Use the Steam URL
            elif widget_json_data.get("url") and isinstance(
                widget_json_data["url"],
                str,
            ):  # Otherwise, check if local metadata url exists
                url = widget_json_data["url"]  # Use the local metadata url
            else:  # Otherwise, warn & do nothing
                logger.warning(
                    f"Unable to get url for mod {widget_package_id}"
                )  # TODO: Make warning visible
        elif (  # Local mod URL priority: url > steam_url
            widget_json_data["data_source"] == "local"
        ):  # If the mod was parsed from a local mods source
            if widget_json_data.get("url") and isinstance(
                widget_json_data["url"],
                str,
            ):  # If the local metadata url exists
                url = widget_json_data["url"]  # Use the local metadata url
            elif widget_json_data.get("steam_url") and isinstance(
                widget_json_data["steam_url"], str
            ):  # Otherwise, if the mod has steam_url
                url = widget_json_data.get("steam_url")  # Use the Steam URL
            else:  # Otherwise, warn & do nothing
                logger.warning(
                    f"Unable to get url for mod {widget_package_id}"
                )  # TODO: Make warning visible
        elif (  # Expansions don't have url - always use steam_url if available
            widget_json_data["data_source"] == "expansion"
        ):  # Otherwise, the mod MUST be an expansion
            if widget_json_data.get("steam_url") and isinstance(
                widget_json_data["steam_url"], str
            ):  # If the steam_url exists
                url = widget_json_data.get("steam_url")  # Use the Steam URL
            else:  # Otherwise, warn & do nothing
                logger.warning(
                    f"Unable to get url for mod {widget_package_id}"
                )  # TODO: Make warning visible
        else:  # ??? Not possible
            logger.debug(
                f"Tried to parse URL for a mod that does not have a data_source? Erroneous json data: {widget_json_data}"
            )
        return url

    def open_mod_url(self, url: str) -> None:
        """
        Open the url of a mod of a url in a user's default web browser
        """
        browser = webbrowser.get().name
        logger.info(f"USER ACTION: Opening mod url {url} in " + f"{browser}")
        webbrowser.open_new_tab(url)
