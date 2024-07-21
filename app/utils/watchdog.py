import os
from functools import partial
from threading import Timer
from typing import Any, Optional
from uuid import uuid4

from loguru import logger
from PySide6.QtCore import QObject, Signal
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from app.controllers.settings_controller import SettingsController
from app.utils.metadata import MetadataManager


class WatchdogHandler(FileSystemEventHandler, QObject):
    mod_created = Signal(str, str, str)
    mod_deleted = Signal(str, str, str)
    mod_updated = Signal(bool, bool, str, str, str)

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
        self.metadata_manager: MetadataManager = MetadataManager.instance()
        self.settings_controller: SettingsController = settings_controller
        self.watchdog_observer: Optional[BaseObserver]
        self.watchdog_observer = Observer()
        # Keep track of cooldowns for each uuid
        self.cooldown_timers: dict[str, Any] = {}
        self.__add_observers(self.settings_controller.get_mod_paths())

    def __add_observers(self, targets: list[str]) -> None:
        """
        Add observers to the watchdog observer for all of our data source target paths.

        Parameters:
            None
        """
        for path in targets:
            if path and os.path.exists(path) and os.path.isdir(path):
                if self.watchdog_observer is not None:
                    self.watchdog_observer.schedule(  # type: ignore # Lib doesn't have proper return type
                        self,
                        path,
                        recursive=True,
                    )

    def __cooldown_uuid_change(self, callback: dict[str, str]) -> None:
        """
        Start the cooldown timer for the given value.

        Parameters:
            operation (str): The operation that triggered the cooldown.
            value (str): The string value related to the file operation.
                         This is either path or UUID depending on the op.

        Returns:
            None
        """
        operation = callback["operation"]
        mod_directory = callback["path"]
        uuid = callback["uuid"]
        data_source = (
            callback.get(
                "data_source"  # This is resolved upon new mod creation, or we use the existing value for
            )
            or self.metadata_manager.internal_local_metadata.get(
                uuid, {}
            ).get(  # an existing mod
                "data_source"
            )
        )
        # Cancel any existing timers for this key
        timer = self.cooldown_timers.get(uuid)
        if timer:
            timer.cancel()
        # Construct cooldown timer for the given operation from the callback and start it
        if operation == "updated":
            self.cooldown_timers[uuid] = Timer(
                1.0,
                partial(
                    self.mod_updated.emit,
                    False,
                    True,
                    data_source,
                    mod_directory,
                    uuid,
                ),
            )
        else:
            self.cooldown_timers[uuid] = Timer(
                1.0,
                partial(
                    getattr(self, f"mod_{operation}").emit,
                    data_source,
                    mod_directory,
                    uuid,
                ),
            )
        self.cooldown_timers[uuid].start()

    def on_created(self, event: FileSystemEvent) -> None:
        """
        A callback function called when a file is created.

        We want to signal any changes to a mods' About.xml file.

        Parameters:
        event: The event object representing the file deletion event.

        Returns: None
        """
        # Resolve the data source from the path
        data_source = self.settings_controller.resolve_data_source(event.src_path)
        # Generate a UUID after confirming we don't already have one for this path
        uuid = (
            str(uuid4())
            if event.is_directory
            and not self.metadata_manager.mod_metadata_dir_mapper.get(event.src_path)
            else None
        )
        # If we know the intent, and have a UUID generated, proceed to create the mod
        if data_source and uuid:
            logger.debug(f"Mod directory created: {event.src_path}")
            logger.debug(f"Mod UUID created: {uuid}")
            logger.debug(f"Mod data source created: {data_source}")
            # Add the mod directory to our mapper
            self.metadata_manager.mod_metadata_dir_mapper[event.src_path] = uuid
            # Signal mod creation
            self.__cooldown_uuid_change(
                callback={
                    "operation": "created",
                    "data_source": data_source,
                    "path": event.src_path,
                    "uuid": uuid,
                }
            )

    def on_deleted(self, event: FileSystemEvent) -> None:
        """
        A callback function called when a file is deleted.

        Parameters:
        event: The event object representing the file deletion event.

        Returns: None
        """
        # Resolve an existing UUID from our mapper
        uuid = self.metadata_manager.mod_metadata_dir_mapper.get(event.src_path)
        # If we have a UUID resolved, proceed to delete the mod
        if uuid:
            # Remove the mod's metadata file from our mapper
            mod_metadata_file_path = self.metadata_manager.internal_local_metadata.get(
                uuid, {}
            ).get("metadata_file_path")
            self.metadata_manager.mod_metadata_file_mapper.pop(
                mod_metadata_file_path, None
            )
            # Remove the mod directory from our mapper
            self.metadata_manager.mod_metadata_dir_mapper.pop(event.src_path, None)
            logger.debug(f"Mod directory deleted: {event.src_path}")
            self.__cooldown_uuid_change(
                callback={
                    "operation": "deleted",
                    "path": event.src_path,
                    "uuid": uuid,
                }
            )

    def on_modified(self, event: FileSystemEvent) -> None:
        """
        A callback function called when a file is modified.

        Parameters:
        event: The event object representing the file modified event.

        Returns: None
        """
        # Resolve an existing UUID from our mapper
        uuid = self.metadata_manager.mod_metadata_file_mapper.get(event.src_path)

        if not uuid:
            logger.debug(f"No UUID found for modification event: {event.src_path}")
            return

        # Try to resolve a mod path from the from metadata
        mod_path = self.metadata_manager.internal_local_metadata.get(uuid, {}).get(
            "path"
        )
        # If we have a UUID and mod path resolved, proceed to update the mod
        if not mod_path:
            logger.debug(
                f"UUID found for modification event, but no mod path. Event src_path: {event.src_path} UUID: {uuid}"
            )

        logger.debug(f"Mod metadata modified: {event.src_path}")
        self.__cooldown_uuid_change(
            callback={
                "operation": "updated",
                "path": mod_path,
                "uuid": uuid,
            }
        )

    def on_moved(self, event: FileSystemEvent) -> None:
        """
        A callback function called when a file is moved.

        Parameters:
        event: The event object representing the file moved event.

        Returns: None
        """
        # logger.debug(f"File moved: {event.src_path} to {event.dest_path}")

    def on_closed(self, event: FileSystemEvent) -> None:
        """
        A callback function called when a file is closed.

        Parameters:
            event: The event object associated with the file closed event.

        Returns: None
        """
        # logger.debug(f"File closed: {event.src_path}")

    def on_opened(self, event: FileSystemEvent) -> None:
        """
        A callback function called when a file is opened.

        Parameters:
            event: The event object associated with the file opened event.

        Returns: None
        """
        # logger.debug(f"File opened: {event.src_path}")
