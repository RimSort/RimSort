import os
from functools import partial
from pathlib import Path
from threading import Timer
from typing import Any

from loguru import logger
from PySide6.QtCore import QObject, Signal
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver
from watchdog.observers.polling import PollingObserver

from app.controllers.metadata_controller import MetadataController
from app.models.instance import Instance
from app.services.mod_path_service import get_mod_paths, resolve_data_source


class WatchdogHandler(FileSystemEventHandler, QObject):
    acf_changed = Signal(bool, bool)
    mod_created = Signal(str, str)
    mod_deleted = Signal(str, str)
    mod_updated = Signal(str, str)

    def __init__(self, instance: Instance) -> None:
        """Initialize the WatchdogHandler.

        The WatchdogHandler is a subclass of :class:`watchdog.events.FileSystemEventHandler`
        and :class:`PySide6.QtCore.QObject`. It is used to monitor relevant mod files for changes.

        :param instance: The active game instance

        :return: None
        """
        super().__init__()
        logger.info("Initializing WatchdogHandler")
        self.metadata_controller: MetadataController = MetadataController.instance()
        workshop_acf = self.metadata_controller.workshop_acf_path
        self.workshop_acf_path: str | None = (
            str(workshop_acf) if workshop_acf is not None else None
        )
        self.steamcmd_appworkshop_acf_path = self.metadata_controller.steamcmd_acf_path
        self._instance = instance
        # Steam .acf file monitoring
        self.watchdog_acf_observer: BaseObserver | None
        self.watchdog_acf_observer = PollingObserver()
        # Mod directory monitoring
        self.watchdog_mods_observer: BaseObserver | None
        self.watchdog_mods_observer = Observer()
        # Keep track of cooldowns for each mod path
        self.cooldown_timers: dict[str, Any] = {}
        self.__add_acf_observers()
        self.__add_mod_observers(get_mod_paths(self._instance))

    def start(self) -> None:
        """Start all configured observers.

        Each observer is only started if it exists and is not already alive.
        Logs a warning if an observer is None or already running.
        """
        try:
            if self.watchdog_acf_observer is not None:
                if self.watchdog_acf_observer.is_alive():
                    logger.warning("Watchdog Steam .acf Observer is already running.")
                else:
                    self.watchdog_acf_observer.start()
            else:
                logger.warning("Watchdog Steam .acf Observer is None. Unable to start.")
            if self.watchdog_mods_observer is not None:
                if self.watchdog_mods_observer.is_alive():
                    logger.warning("Watchdog Mods Observer is already running.")
                else:
                    self.watchdog_mods_observer.start()
            else:
                logger.warning("Watchdog Mods Observer is None. Unable to start.")
        except Exception as e:
            logger.warning(
                f"Unable to start Watchdog Observer(s) due to exception: {str(e)}"
            )

    def stop(self) -> None:
        """Stop all observers and cancel pending cooldown timers."""
        if self.watchdog_acf_observer is not None:
            if self.watchdog_acf_observer.is_alive():
                self.watchdog_acf_observer.stop()
                self.watchdog_acf_observer.join()
            self.watchdog_acf_observer = None
        if self.watchdog_mods_observer is not None:
            if self.watchdog_mods_observer.is_alive():
                self.watchdog_mods_observer.stop()
                self.watchdog_mods_observer.join()
            self.watchdog_mods_observer = None
        timers = list(self.cooldown_timers.values())
        self.cooldown_timers.clear()
        for timer in timers:
            timer.cancel()

    def __add_acf_observers(self) -> None:
        """Add observers to the watchdog observer for applicable Steam .acf files.

        :return: None
        """
        # Get all applicable Steam .acf paths if set and existing
        acf_targets: set[str] = {
            path
            for path in (
                self.workshop_acf_path,
                self.steamcmd_appworkshop_acf_path,
            )
            if path and os.path.exists(path)
        }
        # Loop through applicable targets and schedule observers for them
        if self.watchdog_acf_observer is not None:
            for target in acf_targets:
                logger.debug(f"Scheduling observer for Steam .acf metadata: {target}")
                self.watchdog_acf_observer.schedule(self, target, recursive=False)

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

    def __check_acf_file(self, event: FileSystemEvent, event_scr_path: Path) -> bool:
        """Check if the file created is an .acf file that we track metadata from.

        :param event: The event object representing the file event.
        :type event: FileSystemEvent
        :param event_scr_path: The path of the file created.
        :type event_scr_path: Path

        :return: True if the file is an .acf file that we track metadata from.
        :rtype: bool
        """

        # Normalize the paths that are being compared
        event_scr_path = event_scr_path.resolve()
        workshop_acf_resolved = (
            Path(self.workshop_acf_path).resolve()
            if self.workshop_acf_path is not None
            else None
        )
        steamcmd_appworkshop_acf_path = Path(
            self.steamcmd_appworkshop_acf_path
        ).resolve()
        # Explicitly check if the file created is an .acf file that we track metadata from
        if (
            not event.is_directory
            and event_scr_path.suffix == ".acf"
            and (
                event_scr_path == workshop_acf_resolved
                or event_scr_path == steamcmd_appworkshop_acf_path
            )
        ):
            logger.debug(f"ACF file change detected: {event_scr_path}")
            logger.debug(f"Event: {event}")
            # The bools that are signalled here correspond with whether it is Steam client or SteamCMD
            steamclient = event_scr_path == workshop_acf_resolved
            steamcmd = event_scr_path == steamcmd_appworkshop_acf_path
            self.acf_changed.emit(steamclient, steamcmd)
            return True
        return False

    def __cooldown_mod_change(
        self, callback: dict[str, str], delay: float = 3.0
    ) -> None:
        """Execute a callback after a cooldown period. A cooldown period is used
        to prevent rapid-fire events from triggering multiple callbacks.

        :param callback: A dictionary containing the operation, data_source, and mod path.
        :type callback: dict[str, str]
        :param delay: The number of seconds to wait before executing the callback. Defaults to 3.0.
        :type delay: float

        :return: None
        """
        operation = callback["operation"]
        mod_path = callback["path"]
        data_source = callback.get("data_source", "")

        # Cancel any existing timers for this key
        timer = self.cooldown_timers.get(mod_path)
        if timer:
            timer.cancel()
        # Construct cooldown timer for the given operation from the callback and start it
        self.cooldown_timers[mod_path] = Timer(
            delay,
            partial(
                getattr(self, f"mod_{operation}").emit,
                data_source,
                mod_path,
            ),
        )
        self.cooldown_timers[mod_path].start()

    def on_created(self, event: FileSystemEvent) -> None:
        """A function called when a file or directory is created.

        :param event: The event object representing the file or directory creation event.
        :type event: FileSystemEvent

        :return: None
        """
        event_scr_path_str = str(event.src_path)
        # Explicitly check if the file created is an .acf file that we track metadata from
        if self.__check_acf_file(event, Path(event_scr_path_str)):
            return
        # If we are still here, assume we need to try to resolve the mod's data source from the potential mod path
        data_source = resolve_data_source(self._instance, event_scr_path_str)
        # Check if this is a new mod directory (not already tracked)
        is_new_mod_dir = (
            event.is_directory
            and data_source is not None
            and event_scr_path_str not in self.metadata_controller.mods_metadata
        )
        # If we know the intent, and this is a new mod directory, proceed to create the mod
        if is_new_mod_dir:
            logger.debug(f"Mod directory created: {event_scr_path_str}")
            logger.debug(f"Mod data source: {data_source}")
            # Signal mod creation
            self.__cooldown_mod_change(
                callback={
                    "operation": "created",
                    "data_source": data_source or "",
                    "path": event_scr_path_str,
                }
            )

    def on_deleted(self, event: FileSystemEvent) -> None:
        """A function called when a file or directory is deleted.

        :param event: The event object representing the file or directory deletion event.
        :type event: FileSystemEvent

        :return: None
        """
        event_scr_path_str = str(event.src_path)
        # Explicitly check if the file created is an .acf file that we track metadata from
        if self.__check_acf_file(event, Path(event_scr_path_str)):
            return
        # Check if this is a known mod directory
        is_known_mod = (
            event.is_directory
            and event_scr_path_str in self.metadata_controller.mods_metadata
        )
        if is_known_mod:
            logger.debug(f"Mod directory deleted: {event_scr_path_str}")
            self.__cooldown_mod_change(
                callback={
                    "operation": "deleted",
                    "path": event_scr_path_str,
                }
            )

    def on_modified(self, event: FileSystemEvent) -> None:
        """A function called when a file or directory is modified.

        :param event: The event object representing the file or directory modification event.
        :type event: FileSystemEvent

        :return: None
        """
        event_scr_path_str = str(event.src_path)
        # Explicitly check if the file created is an .acf file that we track metadata from
        if self.__check_acf_file(event, Path(event_scr_path_str)):
            return
        # For file modifications, resolve the mod path from the file path
        if not event.is_directory:
            # Try to resolve About.xml changes to their parent mod path
            mod_path = self.metadata_controller.resolve_about_xml_to_mod_path(
                event_scr_path_str
            )
            if mod_path is not None:
                logger.debug(f"Mod metadata modified: {event_scr_path_str}")
                self.__cooldown_mod_change(
                    callback={
                        "operation": "updated",
                        "path": mod_path,
                    }
                )
