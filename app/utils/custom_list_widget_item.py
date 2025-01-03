from loguru import logger
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QListWidgetItem


class CustomListWidgetItem(QListWidgetItem, QObject):
    """
    A custom QListWidgetItem. To be always used in place of QListWidgetItem.
    """

    reset_warning_signal = Signal(str)

    def __init__(self, *args) -> None:
        QObject.__init__(self)
        QListWidgetItem.__init__(self, *args)

    def setData(self, role: int, value: object) -> None:
        """
        Because we are using a custom class to store data for our QListWidgetItem,
        .setData does not cause the itemChanged signal to be emitted by ModListWidget like it usually would if using a dict.
        
        Here we manually emit this signal.
        
        :param role: int, the role of the data
        :param value: object, the data to set
        """
        super().setData(role, value)
        # Emit signal
        list_widget = self.listWidget()
        if list_widget:
            list_widget.itemChanged.emit(self)
        else:
            logger.warning("Could not emit itemChanged signal from CustomListWidgetItem, listWidget is None.")
