import json
from pathlib import Path
import os
from threading import Timer
from uuid import uuid4

from PySide6.QtCore import QObject, Signal
from loguru import logger
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers.api import BaseObserver

# Needed earlier for the following condition
from app.controllers.settings_controller import SettingsController
from app.utils.system_info import SystemInfo

SYSTEM_INFO = SystemInfo()

if SYSTEM_INFO.operating_system == SystemInfo.OperatingSystem.WINDOWS:
    from watchdog.observers.polling import PollingObserver
else:
    from watchdog.observers import Observer

from app.utils.metadata import MetadataManager


# WATCHDOG


class WatchdogHandler(FileSystemEventHandler, QObject):

    mod_created = Signal(dict)
    mod_deleted = Signal(dict)
    mod_modified = Signal(dict)

    def __init__(self, settings_controller: SettingsController, targets: list[str]):
        """
        Initialize the WatchdogHandler.

        Parameters:
            targets (list[str]): The list of target paths to monitor.

        Returns:
            None
        """
        super().__init__()
        logger.info("Initializing WatchdogHandler")
        self.metadata_manager = MetadataManager.instance()
        self.settings_controller = settings_controller
        self.targets = targets
        self.watchdog_observer: Optional[BaseObserver]
        if SYSTEM_INFO.operating_system == SystemInfo.OperatingSystem.WINDOWS:
            self.watchdog_observer = PollingObserver()
        else:
            self.watchdog_observer = Observer()
        # Go through mod source paths to schedule Observer
        for path in self.targets:
            if path and path != "" and os.path.exists(path):
                self.watchdog_observer.schedule(self, path, recursive=True)
        # Keep track of cooldowns for each uuid
        self.cooldown_timers = {}
        # Map mod uuid to metadata file path
        self.mod_file_mapper = {
            **{
                metadata.get(
                    "metadata_file_path"
                ): uuid  # We watch the mod's parent directory for changes, so we need to map to the mod's uuid
                for uuid, metadata in self.metadata_manager.internal_local_metadata.items()
            },
            **{
                metadata.get(
                    "path"
                ): uuid  # We watch the mod's parent directory for changes, so we need to map to the mod's uuid
                for uuid, metadata in self.metadata_manager.internal_local_metadata.items()
            },
        }

    def __cooldown(self, callback: dict[str, str]) -> None:
        """
        Start the cooldown timer for the given value.

        Parameters:
            operation (str): The operation that triggered the cooldown.
            value (str): The string value related to the file operation.
                         This is either path or UUID depending on the op.

        Returns:
            None
        """
        data_source = callback.get("data_source")
        operation = callback.get("operation")
        path = callback.get("path")
        uuid = callback.get("uuid")
        key = uuid or path
        # Cancel any existing timers for this key
        if key in self.cooldown_timers:
            self.cooldown_timers[key].cancel()
        # Construct cooldown timer for the given operation from the callback
        if operation == "created":
            self.cooldown_timers[key] = Timer(
                1.0, self.mod_created.emit, args=(callback,)
            )
        elif operation == "deleted":
            self.cooldown_timers[key] = Timer(
                1.0, self.mod_deleted.emit, args=(callback,)
            )
        elif operation == "update":
            self.cooldown_timers[key] = Timer(
                1.0,
                self.mod_modified.emit,
                args=(callback,),
            )
        self.cooldown_timers[key].start()

    def __check_for_mod_dir(self, path: str) -> None:
        """
        A helper function to create a new mod. This will determine if the file constitues
        a "mod directory" that needs to be scanned. This will check if the path is a directory
        contained directly within one of our mod data sources.

        Can be expansion, local, or workshop. Will only create if it is not already mapped.

        Parameters:
        path (str): The path to the new mod.

        Returns: A string representing the data_source of the mod
        """
        # Pathlib our str path
        path = Path(path)
        # Ignore temporary files
        if path.name.startswith(".temp_write_"):
            return False
        # Grab paths from Settings
        expansions_path = Path(self.settings_controller.settings.game_folder) / "Data"
        local_path = Path(self.settings_controller.settings.local_folder)
        workshop_path = Path(self.settings_controller.settings.workshop_folder)
        # Validate data source, then emit if path is valid and not mapped
        if path.parent == expansions_path:
            return "expansion"
        elif path.parent == local_path:
            return "local"
        elif path.parent == workshop_path:
            return "workshop"
        else:
            return ""

    def on_created(self, event: FileSystemEvent):
        """
        A callback function called when a file is moved.

        We want to signal any changes to a mods' About.xml file.

        Parameters:
        event: The event object representing the file deletion event.

        Returns: None
        """
        data_source = self.__check_for_mod_dir(event.src_path)
        uuid = self.mod_file_mapper.get(event.src_path)
        if data_source and not uuid:
            logger.debug(f"Mod directory created: {event.src_path}")
            uuid = str(uuid4())
            # Add the mod directory to our mapper
            self.mod_file_mapper[event.src_path] = uuid
            # Signal mod creation
            self.__cooldown(
                callback={
                    "data_source": data_source,
                    "operation": "created",
                    "path": event.src_path,
                    "uuid": uuid,
                }
            )

    def on_deleted(self, event):
        """
        A callback function called when a file is deleted.

        Parameters:
        event: The event object representing the file deletion event.

        Returns: None
        """
        data_source = self.__check_for_mod_dir(event.src_path)
        uuid = self.mod_file_mapper.get(event.src_path)
        if data_source and uuid:
            del self.mod_file_mapper[event.src_path]
            logger.debug(f"Mod directory deleted: {event.src_path}")
            self.__cooldown(
                callback={
                    "data_source": data_source,
                    "operation": "deleted",
                    "path": event.src_path,
                    "uuid": uuid,
                }
            )

    def on_modified(self, event):
        """
        A callback function called when a file is modified.

        Parameters:
        event: The event object representing the file modified event.

        Returns: None
        """
        uuid = self.mod_file_mapper.get(event.src_path)
        mod_path = self.metadata_manager.internal_local_metadata.get(uuid, {}).get(
            "path"
        )
        data_source = self.__check_for_mod_dir(mod_path) if mod_path else None
        if data_source and uuid:
            logger.debug(f"Mod metadata modified: {event.src_path}")
            self.__cooldown(
                callback={
                    "data_source": data_source,
                    "operation": "update",
                    "path": mod_path,
                    "uuid": uuid,
                }
            )

    def on_moved(self, event: FileSystemEvent):
        """
        A callback function called when a file is moved.

        Parameters:
        event: The event object representing the file moved event.

        Returns: None
        """
        # logger.debug(f"File moved: {event.src_path} to {event.dest_path}")

    def on_closed(self, event: FileSystemEvent):
        """
        A callback function called when a file is closed.

        Parameters:
            event: The event object associated with the file closed event.

        Returns: None
        """
        # logger.debug(f"File closed: {event.src_path}")

    def on_opened(self, event: FileSystemEvent):
        """
        A callback function called when a file is opened.

        Parameters:
            event: The event object associated with the file opened event.

        Returns: None
        """
        # logger.debug(f"File opened: {event.src_path}")
