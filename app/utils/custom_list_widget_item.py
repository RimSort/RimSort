from typing import Any

from loguru import logger
from PySide6.QtCore import (
    QObject,
    Qt,
)
from PySide6.QtWidgets import QListWidgetItem


class CustomListWidgetItem(QListWidgetItem):
    """
    A custom QListWidgetItem. To be always used in place of QListWidgetItem.
    """

    def __init__(self, *args: Any) -> None:
        self._qobject = QObject()
        QListWidgetItem.__init__(self, *args)

    def setData(self, role: int, value: Any, avoid_emit: bool = False) -> None:
        """
        Sets the data for the given role and emits the itemChanged signal if avoid_emit is False.

        Because we are using a custom class to store data for our QListWidgetItem,
        .setData does not cause the itemChanged signal to be emitted by ModListWidget like it usually would if using a dict.
        Here we manually emit this signal.

        :param role: int, the role of the data
        :param value: Any, the data to set
        :param avoid_emit: bool, whether to avoid emitting the itemChanged signal
        """
        # NOTE: This setData method seems to be also called when using setToolTip, setSizeHint etc.
        super().setData(role, value)
        # Emit signal
        if avoid_emit:
            return

        list_widget = self.listWidget()
        if list_widget:
            # This signal triggers handle_item_data_changed, which repolishes the widget if it has been lazy loaded
            list_widget.itemChanged.emit(self)
        else:
            # If the CustomListWidgetItem is not added to a QListWidget the signal will not be emitted
            logger.warning(
                "Could not emit itemChanged signal from CustomListWidgetItem, listWidget is None."
            )

    def toggle_warning(self) -> None:
        """
        Toggles the warning state for this mod item.
        """
        data = self.data(Qt.ItemDataRole.UserRole)
        if data:
            data["warning_toggled"] = not data.get("warning_toggled", False)
            self.setData(Qt.ItemDataRole.UserRole, data)
