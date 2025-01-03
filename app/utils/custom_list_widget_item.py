from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QListWidgetItem

from app.utils.metadata import MetadataManager


class CustomListWidgetItem(QListWidgetItem, QObject):
    """
    
    """
    
    reset_warning_signal = Signal(str)

    def __init__(self, *args, **kwargs):
        QObject.__init__(self)
        QListWidgetItem.__init__(self, *args, **kwargs)
        
        self.metadata_manager = MetadataManager.instance()
            
    def setData(self, role, value):
        """
        Because we are using a custom class to store data for our QListWidgetItem,
        .setData does not cause the itemChanged signal to be emitted by ModListWidget like it usually would if using a dict.
        
        Here we manually emit this signal.
        """
        super().setData(role, value)
        
        # Emit signal
        list_widget = self.listWidget()
        list_widget.itemChanged.emit(self)
