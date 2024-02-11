from PySide6.QtCore import QObject, Signal
from loguru import logger
from watchdog.events import FileSystemEventHandler


class RSFileSystemEventHandler(FileSystemEventHandler, QObject):
    """
    Custom file system event handler that emits signals on file changes.

    This class inherits from both `FileSystemEventHandler` and `QObject` to enable signals and slots mechanism.
    It emits a signal whenever a file system event occurs.

    Signals:
        file_changes_signal: Signal emitted when a file system event occurs.

    Methods:
        on_created: Called when a file or directory is created.
        on_deleted: Called when a file or directory is deleted.
        on_modified: Called when a file is modified.
        on_moved: Called when a file or directory is moved or renamed.
        on_closed: Called when a file or directory is closed.
        on_opened: Called when a file or directory is opened.
    """

    # Define a signal to emit file changes
    file_changes_signal = Signal(str)

    def __init__(self):
        super().__init__()

    def on_created(self, event):
        """
        Called when a file or directory is created.
        Emits a signal with the path of the created file or directory.
        """
        self.file_changes_signal.emit(event.src_path)
        logger.debug(f"FILE CREATED: {event}")

    def on_deleted(self, event):
        """
        Called when a file or directory is deleted.
        Emits a signal with the path of the deleted file or directory.
        """
        self.file_changes_signal.emit(event.src_path)
        logger.debug(f"FILE DELETED: {event}")

    def on_modified(self, event):
        """
        Called when a file is modified.
        Emits a signal with the path of the modified file.
        """
        self.file_changes_signal.emit(event.src_path)
        logger.debug(f"FILE MODIFIED: {event}")

    def on_moved(self, event):
        """
        Called when a file or directory is moved or renamed.
        Emits a signal with the path of the moved file or directory.
        """
        self.file_changes_signal.emit(event.src_path)
        logger.debug(f"FILE MOVED: {event}")

    def on_closed(self, event):
        """
        Called when a file or directory is closed.
        """
        logger.debug(f"FILE CLOSED: {event}")
        return

    def on_opened(self, event):
        """
        Called when a file or directory is opened.
        """
        logger.debug(f"FILE OPENED: {event}")
        return
