from typing import Any, Dict, List

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from model.mod_list_item import ModListItemInner


class ModListWidget(QListWidget):
    """
    Subclass for QListWidget. Used to store lists for
    active and inactive mods. Mods can be rearranged within
    their own lists or moved from one list to another.
    """

    mod_list_signal = Signal(str)
    list_change_signal = Signal(str)

    def __init__(self) -> None:
        """
        Initialize the ListWidget with a dict of mods.
        Keys are the package ids and values are a dict of
        mod attributes. See tags:
        https://rimworldwiki.com/wiki/About.xml
        """

        super(ModListWidget, self).__init__()

        # Allow for dragging and dropping between lists
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)

        # Allow for selecting and moving multiple items
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        # When an item is clicked, display the mod information TODO
        self.itemClicked.connect(self.mod_clicked)

        # Allow inserting custom list items
        self.model().rowsInserted.connect(
            self.handle_rows_inserted, Qt.QueuedConnection
        )

        # Handle removing items to update count
        self.model().rowsAboutToBeRemoved.connect(
            self.handle_rows_removed, Qt.QueuedConnection
        )

    def recreate_mod_list(self, mods: Dict[str, Any]) -> None:
        """
        Clear all mod items and add new ones from a dict.

        :param mods: dict of mod data
        """
        self.clear()
        if mods:
            for mod_json_data in mods.values():
                list_item = QListWidgetItem(self)
                list_item.setData(Qt.UserRole, mod_json_data)
                self.addItem(list_item)

    def handle_rows_inserted(self, parent: QModelIndex, first: int, last: int) -> None:
        """
        This slot is called when rows are inserted.
        When row items are inserted, create a corresponding display widget
        and insert it into the row item. Can accommodate inserting
        multiple rows. First = last for single item inserts.

        :param parent: parent to get rows under (not used)
        :param first: index of first item inserted
        :param last: index of last item inserted
        """
        for idx in range(first, last + 1):
            item = self.item(idx)
            if item is not None and self.itemWidget(item) is None:
                data = item.data(Qt.UserRole)
                widget = ModListItemInner(data)
                item.setSizeHint(widget.sizeHint())
                self.setItemWidget(item, widget)
        self.list_change_signal.emit(str(self.count()))

    def handle_rows_removed(self, parent: QModelIndex, first: int, last: int) -> None:
        """
        This slot is called when rows are removed.
        Emit a signal with the count of objects remaining to update
        the count label.

        :param parent: parent to get rows under (not used)
        :param first: index of first item removed (not used)
        :param last: index of last item removed (not used)
        """
        self.list_change_signal.emit(str(self.count()))

    def get_list_items(self) -> List[ModListItemInner]:
        """
        Get a list of all row item's widgets. Note that widgets actually
        hold the mod data, not the list row items.

        :return: a list of mod item widgets
        """
        return [self.itemWidget(self.item(i)) for i in range(self.count())]

    def get_list_items_by_dict(self) -> Dict[str, Any]:
        """
        Get a dict of all row item's widgets data. Equal to `mods` in
        recreate mod list.

        :return: a dict of mod data
        """
        mod_dict = {}
        for i in range(self.count()):
            item = self.itemWidget(self.item(i)).json_data
            mod_dict[item["packageId"]] = item
        return mod_dict

    def focusOutEvent(self, e: QFocusEvent) -> None:
        """
        Slot to handle unhighlighting any items in the
        previous list when clicking out of that list.
        """
        self.clearFocus()
        return super().focusOutEvent(e)

    def mod_clicked(self, item: QListWidgetItem) -> None:
        """Method to handle clicking on a row"""
        self.mod_list_signal.emit(item.data(Qt.UserRole)["packageId"])
