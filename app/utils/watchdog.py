import os
from functools import partial
from threading import Timer
from typing import Any
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

    def __init__(
        self, settings_controller: SettingsController, targets: list[str]
    ) -> None:
        """Initialize the WatchdogHandler.

        The WatchdogHandler is a subclass of :class:`watchdog.events.FileSystemEventHandler`
        and :class:`PySide6.QtCore.QObject`. It is used to monitor relevant mod files for changes.

        The :meth:`__init__` method initializes the WatchdogHandler by setting up the
        :class:`watchdog.observers.Observer` and :class:`watchdog.observers.PollingObserver`
        instances. It also sets up the signals that are emitted when a change is detected.

        :param settings_controller: The settings controller for the application
        :param targets: The list of target paths to monitor
        :type targets: list[str]

        :return: None
        """
        super().__init__()
        logger.info("Initializing WatchdogHandler")
        self.metadata_manager: MetadataManager = MetadataManager.instance()
        self.settings_controller: SettingsController = settings_controller
        # Mod directory monitoring
        self.watchdog_mods_observer: BaseObserver | None
        self.watchdog_mods_observer = Observer()
        # Keep track of cooldowns for each uuid
        self.cooldown_timers: dict[str, Any] = {}
        self.__add_mod_observers(self.settings_controller.get_mod_paths())

    def __add_mod_observers(self, targets: list[str]) -> None:
        """Add observers to the watchdog observer for all of our data source target paths.

        :param targets: The list of target paths to monitor.
        :type targets: list[str]

        :return: None
        """
        for path in targets:
            if path and os.path.exists(path) and os.path.isdir(path):
                if self.watchdog_mods_observer is not None:
                    logger.debug(f"Scheduling observer for mod source: {path}")
                    self.watchdog_mods_observer.schedule(
                        self,
                        path,
                        recursive=True,
                    )

    def __cooldown_uuid_change(
        self, callback: dict[str, str], delay: float = 3.0
    ) -> None:
        """Execute a callback after a cooldown period. A cooldown period is used
        to prevent rapid-fire events from triggering multiple callbacks.

        :param callback: A dictionary containing the operation, mod directory, and UUID to be passed to the callback.
        :type callback: dict[str, str]
        :param delay: The number of seconds to wait before executing the callback. Defaults to 3.0.
        :type delay: float

        :return: None
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
                delay,
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
                delay,
                partial(
                    getattr(self, f"mod_{operation}").emit,
                    data_source,
                    mod_directory,
                    uuid,
                ),
            )
        self.cooldown_timers[uuid].start()

    def on_created(self, event: FileSystemEvent) -> None:
        """A function called when a file or directory is created.

        :param event: The event object representing the file or directory creation event.
        :type event: FileSystemEvent

        :return: None
        """
        event_scr_path_str = str(event.src_path)
        # Try to resolve the mod's data source from the potential mod path
        data_source = self.settings_controller.resolve_data_source(event_scr_path_str)
        # Generate a UUID after confirming we don't already have one for this path
        uuid = (
            str(uuid4())
            if event.is_directory
            and not self.metadata_manager.mod_metadata_dir_mapper.get(
                event_scr_path_str
            )
            else None
        )
        # If we know the intent, and have a UUID generated, proceed to create the mod
        if data_source is not None and uuid is not None:
            logger.debug(f"Mod directory created: {event_scr_path_str}")
            logger.debug(f"Mod UUID created: {uuid}")
            logger.debug(f"Mod data source created: {data_source}")
            # Add the mod directory to our mapper
            self.metadata_manager.mod_metadata_dir_mapper[event_scr_path_str] = uuid
            # Signal mod creation
            self.__cooldown_uuid_change(
                callback={
                    "operation": "created",
                    "data_source": data_source,
                    "path": event_scr_path_str,
                    "uuid": uuid,
                }
            )

    def on_deleted(self, event: FileSystemEvent) -> None:
        """A function called when a file or directory is deleted.

        :param event: The event object representing the file or directory deletion event.
        :type event: FileSystemEvent

        :return: None
        """
        event_scr_path_str = str(event.src_path)
        # Try to resolve an existing UUID from our mod path -> UUID mapper
        uuid = (
            self.metadata_manager.mod_metadata_dir_mapper.get(event_scr_path_str)
            if event.is_directory
            else None
        )
        # If we have a UUID resolved, proceed to delete the mod
        if uuid is not None:
            # Remove the mod's metadata file from our mapper
            mod_metadata_file_path = self.metadata_manager.internal_local_metadata.get(
                uuid, {}
            ).get("metadata_file_path")
            self.metadata_manager.mod_metadata_file_mapper.pop(
                mod_metadata_file_path, None
            )
            # Remove the mod directory from our mod mapper
            self.metadata_manager.mod_metadata_dir_mapper.pop(event_scr_path_str, None)
            logger.debug(f"Mod directory deleted: {event_scr_path_str}")
            self.__cooldown_uuid_change(
                callback={
                    "operation": "deleted",
                    "path": event_scr_path_str,
                    "uuid": uuid,
                }
            )

    def on_modified(self, event: FileSystemEvent) -> None:
        """A function called when a file or directory is modified.

        :param event: The event object representing the file or directory modification event.
        :type event: FileSystemEvent

        :return: None
        """
        event_scr_path_str = str(event.src_path)
        # Try to resolve an existing UUID from our mod path -> UUID mapper
        uuid = (
            self.metadata_manager.mod_metadata_file_mapper.get(event_scr_path_str)
            if not event.is_directory
            else None
        )
        if uuid is not None:
            # Try to resolve a mod path from the from metadata
            mod_path = self.metadata_manager.internal_local_metadata.get(uuid, {}).get(
                "path"
            )
            # If we have a UUID and mod path resolved, proceed to update the mod
            logger.debug(f"Mod metadata modified: {event_scr_path_str}")
            self.__cooldown_uuid_change(
                callback={
                    "operation": "updated",
                    "path": mod_path,
                    "uuid": uuid,
                }
            )
        else:
            # logger.debug(
            #     "UUID resolution failed for mod modified event: "
            #     f"[event_scr_path_str: {event_scr_path_str}, uuid: {uuid}"
            # )
            return

    def on_moved(self, event: FileSystemEvent) -> None:
        """A function called when a file or directory is moved or renamed.

        :param event: The event object representing the file or directory move event.
        :type event: FileSystemEvent

        :return: None
        """
        # logger.debug(f"File moved: {event.src_path} to {event.dest_path}")

    def on_closed(self, event: FileSystemEvent) -> None:
        """A function called when a file or directory is closed.

        :param event: The event object representing the file or directory close event.
        :type event: FileSystemEvent

        :return: None
        """
        # logger.debug(f"File closed: {event.src_path}")

    def on_opened(self, event: FileSystemEvent) -> None:
        """A function called when a file or directory is opened.

        :param event: The event object representing the file or directory open event.
        :type event: FileSystemEvent

        :return: None
        """
        # logger.debug(f"File opened: {event.src_path}")
