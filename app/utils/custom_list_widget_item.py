from PySide6.QtWidgets import QListWidgetItem
from PySide6.QtCore import Qt, Signal, QObject
from app.utils.metadata import MetadataManager

class CustomListWidgetItem(QListWidgetItem, QObject):
    """
    
    """
    
    reset_warning_signal = Signal(str)

    def __init__(self, metadata, *args, **kwargs):
        QObject.__init__(self)
        QListWidgetItem.__init__(self, *args, **kwargs)
        self._metadata = metadata
        
        self.metadata_manager = MetadataManager.instance()
            
    def setData(self, role, value):
        """
        Because we are using a custom class to store data for our QListWidgetItem,
        setData does not emit the itemChanged signal like it usually would if using a dict.
        
        Here we manually emit the signal after .setData is used.
        """
        super().setData(role, value)
        
        # Emit signal
        # TODO: