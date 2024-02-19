from PySide6.QtCore import QObject, Signal
from loguru import logger
from watchdog.events import FileSystemEventHandler


# WATCHDOG


class RSFileSystemEventHandler(FileSystemEventHandler, QObject):
    file_changes_signal = Signal(str)

    def __init__(self):
        super().__init__()

    def on_created(self, event):
        self.file_changes_signal.emit(event.src_path)
        logger.debug(f"FILE CREATED: {event}")

    def on_deleted(self, event):
        self.file_changes_signal.emit(event.src_path)
        logger.debug(f"FILE DELETED: {event}")

    def on_modified(self, event):
        self.file_changes_signal.emit(event.src_path)
        logger.debug(f"FILE MODIFIED: {event}")

    def on_moved(self, event):
        self.file_changes_signal.emit(event.src_path)
        logger.debug(f"FILE MOVED: {event}")

    def on_closed(self, event):
        logger.debug(f"FILE CLOSED: {event}")
        return

    def on_opened(self, event):
        logger.debug(f"FILE OPENED: {event}")
        return
