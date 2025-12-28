from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from os import getcwd
from pathlib import Path
from queue import Queue
from threading import RLock, Thread
from time import sleep, time
from typing import Any, Callable

import psutil
from loguru import logger

# If we're running from a Python interpreter, makesure steamworks module is in our sys.path ($PYTHONPATH)
# Ensure that this is available by running `git submodule update --init --recursive`
# You can automatically ensure this is done by utilizing distribute.py
if "__compiled__" not in globals():
    sys.path.append(str((Path(getcwd()) / "submodules" / "SteamworksPy")))

from app.utils.generic import launch_game_process
from steamworks import STEAMWORKS  # type: ignore
from steamworks.structs import (  # type: ignore
    DownloadItemResult_t,
    GetAppDependenciesResult_t,
    ItemInstalled_t,
    SubscriptionResult,
)


def _find_steam_executable() -> Path | None:
    """
    Find Steam executable path for current platform.

    Returns platform-specific Steam executable path or None if not found.

    :return: Path to Steam executable or None
    :rtype: Path | None
    """
    if sys.platform == "win32":
        try:
            from app.utils.win_find_steam import find_steam_folder

            steam_path, found = find_steam_folder()
            if not found:
                return None
            return Path(steam_path) / "steam.exe"
        except Exception as e:
            logger.warning(f"Failed to find Steam on Windows: {e}")
            return None
    elif sys.platform == "darwin":
        steam_path = Path("/Applications/Steam.app/Contents/MacOS/steam_osx")
        return steam_path if steam_path.exists() else None
    elif sys.platform.startswith("linux"):
        possible_paths = [
            Path.home() / ".steam" / "steam" / "steam.sh",
            Path("/usr/bin/steam"),
            Path("/usr/local/bin/steam"),
        ]
        for path in possible_paths:
            if path.exists():
                return path
        return None
    else:
        logger.warning(f"Unsupported platform for Steam detection: {sys.platform}")
        return None


def _is_steam_running() -> bool:
    """
    Check if Steam is currently running by looking for Steam processes.

    Uses psutil to scan for platform-specific Steam process names.

    :return: True if Steam is running, False otherwise
    :rtype: bool
    """
    try:
        # Platform-specific Steam process indicators
        if sys.platform == "win32":
            steam_indicators = [
                "steam.exe",
                "steamservice.exe",
                "steamwebhelper.exe",
            ]
        elif sys.platform == "darwin":
            steam_indicators = [
                "steam_osx",
                "steamwebhelper",
            ]
        elif sys.platform.startswith("linux"):
            steam_indicators = [
                "steam",
                "steamwebhelper",
            ]
        else:
            logger.warning(f"Unsupported platform for Steam detection: {sys.platform}")
            return False

        # Scan for Steam processes
        for process in psutil.process_iter(attrs=["name"]):
            try:
                name = process.info["name"]
                if name and name.lower() in [s.lower() for s in steam_indicators]:
                    logger.debug(f"Found Steam process: {name}")
                    return True
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue

        logger.debug("No Steam processes found")
        return False
    except Exception as e:
        logger.warning(f"Error checking if Steam is running: {e}")
        return False


def _launch_steam(_libs: str | None = None) -> bool:
    """
    Launch Steam if it's not running and wait for it to become available.

    Attempts to launch Steam using platform-specific executable path,
    then polls Steamworks API for up to 45 seconds to verify availability.

    :param _libs: Optional path to Steamworks library directory
    :type _libs: str | None
    :return: True if Steam was launched successfully, False otherwise
    :rtype: bool
    """
    try:
        steam_exe = _find_steam_executable()
        if steam_exe is None or not steam_exe.exists():
            logger.warning("Steam executable not found, cannot launch")
            return False

        logger.info(f"Launching Steam from: {steam_exe}")

        # Launch Steam
        if sys.platform == "win32":
            subprocess.Popen([str(steam_exe)], shell=True)
        else:
            subprocess.Popen([str(steam_exe)])

        # Give Steam initial time to start up before checking
        logger.debug("Waiting 15 seconds for initial Steam startup...")
        sleep(15)

        # Wait for Steam to start (up to 45 seconds total, including initial delay)
        for attempt in range(45):
            sleep(1)
            try:
                # Try to create a temporary Steamworks instance to test if Steam is ready
                test_steamworks = STEAMWORKS(lib_path=_libs)
                test_steamworks.initialize()
                test_steamworks.unload()
                logger.info("Steam launched and API initialized successfully")
                # Give Steam a bit more time to fully initialize
                sleep(5)
                return True
            except Exception as e:
                logger.debug(f"Steam API not ready yet (attempt {attempt + 1}/45): {e}")
                continue

        logger.warning("Steam failed to start within timeout (45 seconds)")
        return False

    except Exception as e:
        logger.error(f"Error launching Steam: {e}")
        return False


@dataclass
class QueuedOperation:
    """Represents a queued Steamworks operation."""

    name: str  # "subscribe", "download", etc.
    execute: Callable[[], None]  # Function to execute
    batch_id: str | None = None


class SteamworksInterface:
    """
    A class object to handle our interactions with SteamworksPy

    https://github.com/philippj/SteamworksPy
    https://philippj.github.io/SteamworksPy/
    https://github.com/philippj/SteamworksPy/issues/62
    https://github.com/philippj/SteamworksPy/issues/75
    https://github.com/philippj/SteamworksPy/pull/76

    Thanks to Paladin for the example
    """

    _instance: "SteamworksInterface" | None = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "SteamworksInterface":
        """
        Create a new instance or return the existing singleton instance.

        :return: The singleton instance of SteamworksInterface
        """
        if cls._instance is None:
            cls._instance = super(SteamworksInterface, cls).__new__(cls)
        return cls._instance

    def __init__(self, _libs: str | None = None) -> None:
        """
        Initialize the SteamworksInterface singleton.

        :param _libs: Optional path to Steamworks libraries
        """
        # Prevent re-initialization
        if hasattr(self, "initialized"):
            return

        # If _libs not provided, use default path
        if _libs is None:
            from app.utils.app_info import AppInfo

            _libs = str(AppInfo().application_folder / "libs")

        logger.info("SteamworksInterface initializing...")

        # One-time initialization
        self._libs = _libs
        self.steam_not_running = False
        self.steamworks = STEAMWORKS(lib_path=self._libs)

        # Thread safety lock for operation state
        self._operation_lock = RLock()
        self._current_operation: str | None = None

        try:
            self.steamworks.initialize()  # Init the Steamworks API
            logger.info("Steamworks API initialized successfully")
        except Exception as e:
            logger.warning(
                f"Unable to initialize Steamworks API due to exception: {e.__class__.__name__}"
            )
            logger.warning(
                "If you are a Steam user, please check that Steam is running and that you are logged in..."
            )
            self.steam_not_running = True

            # Notify UI that Steam is not available
            from app.utils.event_bus import EventBus

            EventBus().steam_not_running.emit()

        # Initialize per-operation state
        self._reset_operation_state()

        # ItemInstalled callback tracking
        self._item_installed_callback_active = False
        self._current_batch_id: str | None = None

        # Operation queue for serializing concurrent requests
        self._operation_queue: Queue[QueuedOperation] = Queue()
        self._processing_queue = False

        self.initialized = True

    def _reset_operation_state(self) -> None:
        """Reset per-operation state between operations. Must be called with lock held."""
        self._current_operation = None
        self.callbacks = False
        self.callbacks_count = 0
        self.callbacks_total: int | None = None
        self.end_callbacks = False
        self.multiple_queries = False
        self.get_app_deps_query_result: dict[int, Any] = {}
        self.steamworks_thread: Thread | None = None

    @classmethod
    def instance(cls, _libs: str | None = None) -> "SteamworksInterface":
        """
        Get or create singleton instance.

        :param _libs: Optional path to Steamworks libraries
        :return: The singleton instance of SteamworksInterface
        :raises ValueError: If instance already initialized with different _libs
        """
        # If _libs not provided, use default path
        if _libs is None:
            from app.utils.app_info import AppInfo

            _libs = str(AppInfo().application_folder / "libs")

        if cls._instance is None:
            cls._instance = cls(_libs=_libs)
        elif _libs != cls._instance._libs:
            raise ValueError(
                f"SteamworksInterface already initialized with different _libs. "
                f"Existing: {cls._instance._libs}, Requested: {_libs}"
            )
        return cls._instance

    def _check_steam_available(self, operation_name: str) -> bool:
        """
        Check if Steam client is available for operations.

        Emits steam_operation_failed signal if Steam is not running.

        :param operation_name: Human-readable operation name for error messages
        :type operation_name: str
        :return: True if Steam is available, False otherwise
        :rtype: bool
        """
        if self.steam_not_running or not self.steamworks.loaded():
            logger.warning(f"Cannot {operation_name}: Steam client not running")

            from app.utils.event_bus import EventBus

            EventBus().steam_operation_failed.emit(
                f"Cannot {operation_name}: Steam client is not running. "
                f"Please start Steam and try again."
            )
            return False
        return True

    def query_app_dependencies(
        self, pfid_or_pfids: int | list[int], interval: int = 1
    ) -> dict[int, Any] | None:
        """
        Query Steam Workshop mod(s) for DLC/AppID dependency information.

        :param pfid_or_pfids: Single PublishedFileId or list of PublishedFileIds
        :param interval: Sleep interval between API calls (seconds)
        :return: Dict mapping PublishedFileId to app dependencies, or None
        """
        start_time = time()
        logger.info(f"Querying PublishedFileID(s) {pfid_or_pfids} for app dependencies")

        # Normalize to list
        pfids = [pfid_or_pfids] if isinstance(pfid_or_pfids, int) else pfid_or_pfids

        if not self._check_steam_available("query app dependencies"):
            return None

        try:
            self._begin_callbacks("query_app_dependencies", callbacks_total=len(pfids))

            for pfid in pfids:
                logger.debug(f"ISteamUGC/GetAppDependencies Query: {pfid}")
                self.steamworks.Workshop.SetGetAppDependenciesResultCallback(
                    self._cb_app_dependencies_result_callback
                )
                self.steamworks.Workshop.GetAppDependencies(pfid)
                if len(pfids) > 1:
                    sleep(interval)

            logger.info(
                f"Returning {len(self.get_app_deps_query_result.keys())} results..."
            )
            return self.get_app_deps_query_result
        finally:
            self._finish_callbacks(timeout=60)
            elapsed = time() - start_time
            logger.info(f"query_app_dependencies operation completed in {elapsed:.2f}s")

    def subscribe_to_mods(
        self,
        pfid_or_pfids: int | list[int],
        interval: int = 1,
        batch_id: str | None = None,
    ) -> None:
        """
        Subscribe to Steam Workshop mod(s).

        :param pfid_or_pfids: Single PublishedFileId or list of PublishedFileIds
        :type pfid_or_pfids: int | list[int]
        :param interval: Sleep interval between API calls (seconds)
        :type interval: int
        :param batch_id: Optional batch ID from DownloadTracker for progress tracking
        :type batch_id: str | None
        :return: None
        """
        logger.info("Subscribing to Steam Workshop mod(s)")

        pfids = [pfid_or_pfids] if isinstance(pfid_or_pfids, int) else pfid_or_pfids

        if not self._check_steam_available("subscribe to mods"):
            return

        # Define execution function
        def execute() -> None:
            self._subscribe_to_mods_impl(pfids, interval, batch_id)

        # Queue or execute
        self._enqueue_or_execute("subscribe", execute, batch_id)

    def unsubscribe_from_mods(
        self,
        pfid_or_pfids: int | list[int],
        interval: int = 1,
        batch_id: str | None = None,
    ) -> None:
        """
        Unsubscribe from Steam Workshop mod(s).

        :param pfid_or_pfids: Single PublishedFileId or list of PublishedFileIds
        :type pfid_or_pfids: int | list[int]
        :param interval: Sleep interval between API calls (seconds)
        :type interval: int
        :param batch_id: Optional batch ID from DownloadTracker for progress tracking
        :type batch_id: str | None
        :return: None
        """
        logger.info("Unsubscribing from Steam Workshop mod(s)")

        pfids = [pfid_or_pfids] if isinstance(pfid_or_pfids, int) else pfid_or_pfids

        if not self._check_steam_available("unsubscribe from mods"):
            return

        # Define execution function
        def execute() -> None:
            self._unsubscribe_from_mods_impl(pfids, interval, batch_id)

        # Queue or execute
        self._enqueue_or_execute("unsubscribe", execute, batch_id)

    def resubscribe_to_mods(
        self,
        pfid_or_pfids: int | list[int],
        interval: int = 1,
        batch_id: str | None = None,
    ) -> None:
        """
        Resubscribe to Steam Workshop mod(s) (unsub then sub).

        :param pfid_or_pfids: Single PublishedFileId or list of PublishedFileIds
        :type pfid_or_pfids: int | list[int]
        :param interval: Sleep interval between API calls (seconds)
        :type interval: int
        :param batch_id: Optional batch ID from DownloadTracker for progress tracking
        :type batch_id: str | None
        :return: None
        """
        logger.info("Resubscribing to Steam Workshop mod(s)")

        pfids = [pfid_or_pfids] if isinstance(pfid_or_pfids, int) else pfid_or_pfids

        if not self._check_steam_available("resubscribe to mods"):
            return

        # Define execution function
        def execute() -> None:
            self._resubscribe_to_mods_impl(pfids, interval, batch_id)

        # Queue or execute
        self._enqueue_or_execute("resubscribe", execute, batch_id)

    def download_items(
        self,
        pfid_or_pfids: int | list[int],
        interval: int = 1,
        batch_id: str | None = None,
    ) -> None:
        """
        Force download/update Steam Workshop items using DownloadItem API.

        Does NOT unsubscribe - uses native Steamworks DownloadItem() to force revalidation.

        :param pfid_or_pfids: Single PublishedFileId or list of PublishedFileIds
        :type pfid_or_pfids: int | list[int]
        :param interval: Sleep interval between API calls (seconds)
        :type interval: int
        :param batch_id: Optional batch ID from DownloadTracker for progress tracking
        :type batch_id: str | None
        :return: None
        """
        logger.info("Forcing download of Steam Workshop items")

        pfids = [pfid_or_pfids] if isinstance(pfid_or_pfids, int) else pfid_or_pfids

        if not self._check_steam_available("download items"):
            return

        # Define execution function
        def execute() -> None:
            self._download_items_impl(pfids, interval, batch_id)

        # Queue or execute
        self._enqueue_or_execute("download", execute, batch_id)

    def _download_items_impl(
        self, pfids: list[int], interval: int, batch_id: str | None
    ) -> None:
        """
        Internal implementation of download_items (for queuing).

        :param pfids: List of PublishedFileIds
        :type pfids: list[int]
        :param interval: Sleep interval between API calls (seconds)
        :type interval: int
        :param batch_id: Optional batch ID from DownloadTracker for progress tracking
        :type batch_id: str | None
        :return: None
        """
        start_time = time()
        logger.debug(f"Starting download operation for {len(pfids)} item(s)")

        # Store batch_id for callback correlation
        self._current_batch_id = batch_id
        if batch_id:
            logger.debug(f"Operation associated with batch_id: {batch_id}")

        # Enable ItemInstalled callbacks for download tracking
        if batch_id:
            self.enable_item_installed_callbacks()

        callbacks_total = len(pfids)

        try:
            self._begin_callbacks("download", callbacks_total=callbacks_total)

            for pfid in pfids:
                logger.debug(f"ISteamUGC/DownloadItem: {pfid}")

                # Update tracker: SUBSCRIBING (reusing existing status)
                if batch_id:
                    from app.models.download_state import DownloadStatus
                    from app.utils.download_tracker import DownloadTracker

                    DownloadTracker().update_item_status(
                        pfid, DownloadStatus.SUBSCRIBING
                    )

                # Upstream API: callback is REQUIRED, returns bool
                try:
                    success = self.steamworks.Workshop.DownloadItem(
                        pfid, high_priority=True, callback=self._cb_download_item_result
                    )
                    if not success:
                        logger.warning(f"DownloadItem returned False for pfid={pfid}")
                except ValueError as e:
                    logger.error(f"DownloadItem failed for pfid={pfid}: {e}")

                sleep(interval)

        finally:
            self._finish_callbacks()
            elapsed = time() - start_time
            logger.info(f"download operation completed in {elapsed:.2f}s")

    def _subscribe_to_mods_impl(
        self, pfids: list[int], interval: int, batch_id: str | None
    ) -> None:
        """
        Internal implementation of subscribe_to_mods (for queuing).

        :param pfids: List of PublishedFileIds
        :type pfids: list[int]
        :param interval: Sleep interval between API calls (seconds)
        :type interval: int
        :param batch_id: Optional batch ID from DownloadTracker for progress tracking
        :type batch_id: str | None
        :return: None
        """
        start_time = time()
        logger.debug(f"Starting subscribe operation for {len(pfids)} item(s)")

        # Store batch_id for callback correlation
        self._current_batch_id = batch_id
        if batch_id:
            logger.debug(f"Operation associated with batch_id: {batch_id}")

        # Enable ItemInstalled callbacks for download tracking
        if batch_id:
            self.enable_item_installed_callbacks()

        callbacks_total = len(pfids)

        try:
            self._begin_callbacks("subscribe", callbacks_total=callbacks_total)

            for pfid in pfids:
                logger.debug(f"ISteamUGC/SubscribeItem: {pfid}")

                # Update tracker: SUBSCRIBING
                if batch_id:
                    from app.models.download_state import DownloadStatus
                    from app.utils.download_tracker import DownloadTracker

                    DownloadTracker().update_item_status(
                        pfid, DownloadStatus.SUBSCRIBING
                    )

                self.steamworks.Workshop.SetItemSubscribedCallback(
                    self._cb_subscription_action
                )
                self.steamworks.Workshop.SubscribeItem(pfid)
                if len(pfids) > 1:
                    sleep(interval)

        finally:
            # ItemInstalled callbacks will signal completion
            self._finish_callbacks(timeout=60)

            # Clear batch_id
            if self._current_batch_id:
                logger.debug(f"Cleared batch_id: {self._current_batch_id}")
            self._current_batch_id = None

            elapsed = time() - start_time
            logger.info(f"subscribe operation completed in {elapsed:.2f}s")

    def _unsubscribe_from_mods_impl(
        self, pfids: list[int], interval: int, batch_id: str | None
    ) -> None:
        """
        Internal implementation of unsubscribe_from_mods (for queuing).

        :param pfids: List of PublishedFileIds
        :type pfids: list[int]
        :param interval: Sleep interval between API calls (seconds)
        :type interval: int
        :param batch_id: Optional batch ID from DownloadTracker for progress tracking
        :type batch_id: str | None
        :return: None
        """
        start_time = time()
        logger.debug(f"Starting unsubscribe operation for {len(pfids)} item(s)")

        # Store batch_id for callback correlation
        self._current_batch_id = batch_id
        if batch_id:
            logger.debug(f"Operation associated with batch_id: {batch_id}")

        # Enable ItemInstalled callbacks for download tracking
        if batch_id:
            self.enable_item_installed_callbacks()

        callbacks_total = len(pfids)

        try:
            self._begin_callbacks("unsubscribe", callbacks_total=callbacks_total)

            for pfid in pfids:
                logger.debug(f"ISteamUGC/UnsubscribeItem: {pfid}")
                self.steamworks.Workshop.SetItemUnsubscribedCallback(
                    self._cb_subscription_action
                )
                self.steamworks.Workshop.UnsubscribeItem(pfid)
                if len(pfids) > 1:
                    sleep(interval)

        finally:
            # For unsubscribe, use short timeout
            self._finish_callbacks(timeout=10)

            # Clear batch_id
            if self._current_batch_id:
                logger.debug(f"Cleared batch_id: {self._current_batch_id}")
            self._current_batch_id = None

            elapsed = time() - start_time
            logger.info(f"unsubscribe operation completed in {elapsed:.2f}s")

    def _resubscribe_to_mods_impl(
        self, pfids: list[int], interval: int, batch_id: str | None
    ) -> None:
        """
        Internal implementation of resubscribe_to_mods (for queuing).

        :param pfids: List of PublishedFileIds
        :type pfids: list[int]
        :param interval: Sleep interval between API calls (seconds)
        :type interval: int
        :param batch_id: Optional batch ID from DownloadTracker for progress tracking
        :type batch_id: str | None
        :return: None
        """
        start_time = time()
        logger.debug(f"Starting resubscribe operation for {len(pfids)} item(s)")

        # Store batch_id for callback correlation
        self._current_batch_id = batch_id
        if batch_id:
            logger.debug(f"Operation associated with batch_id: {batch_id}")

        # Enable ItemInstalled callbacks for download tracking
        if batch_id:
            self.enable_item_installed_callbacks()

        callbacks_total = len(pfids) * 2  # Unsub + sub for each item

        try:
            self._begin_callbacks("resubscribe", callbacks_total=callbacks_total)

            for pfid in pfids:
                logger.debug(f"ISteamUGC/UnsubscribeItem + SubscribeItem: {pfid}")

                # Update tracker: UNSUBSCRIBING
                if batch_id:
                    from app.models.download_state import DownloadStatus
                    from app.utils.download_tracker import DownloadTracker

                    DownloadTracker().update_item_status(
                        pfid, DownloadStatus.UNSUBSCRIBING
                    )

                self.steamworks.Workshop.SetItemUnsubscribedCallback(
                    self._cb_subscription_action
                )
                self.steamworks.Workshop.SetItemSubscribedCallback(
                    self._cb_subscription_action
                )
                self.steamworks.Workshop.UnsubscribeItem(pfid)
                sleep(interval)

                # Update tracker: SUBSCRIBING
                if batch_id:
                    from app.models.download_state import DownloadStatus
                    from app.utils.download_tracker import DownloadTracker

                    DownloadTracker().update_item_status(
                        pfid, DownloadStatus.SUBSCRIBING
                    )

                self.steamworks.Workshop.SubscribeItem(pfid)
                if len(pfids) > 1:
                    sleep(interval)

        finally:
            # ItemInstalled callbacks will signal completion
            self._finish_callbacks(timeout=60)

            # Clear batch_id
            if self._current_batch_id:
                logger.debug(f"Cleared batch_id: {self._current_batch_id}")
            self._current_batch_id = None

            elapsed = time() - start_time
            logger.info(f"resubscribe operation completed in {elapsed:.2f}s")

    def launch_game(self, game_install_path: str, args: list[str]) -> None:
        """
        Initialize Steamworks API and launch the game.

        :param game_install_path: Path to game installation folder
        :param args: Launch arguments for the game
        """
        logger.info("Launching game with Steamworks API")

        # API already initialized in __init__, just launch game
        launch_game_process(game_install_path=Path(game_install_path), args=args)

    def check_steam_availability(self) -> bool:
        """
        Check if Steam client is currently available.

        Verifies Steam is actually running and attempts to re-initialize
        Steamworks if it was previously unavailable.
        Updates internal state and emits signals as appropriate.

        Use this to check if Steam state has changed since initial startup
        (e.g., user started Steam after starting RimSort, or Steam was closed).

        :return: True if Steam is available, False otherwise
        """
        # If we think Steam is available, verify it's actually running
        if not self.steam_not_running and self.steamworks.IsSteamRunning():
            logger.debug("Steam client is available")
            return True

        # Try to re-initialize
        logger.info("Attempting to re-initialize Steamworks API...")
        try:
            self.steamworks.initialize()
            logger.info("Steamworks API re-initialized successfully")
            self.steam_not_running = False
            return True
        except Exception as e:
            logger.warning(
                f"Unable to re-initialize Steamworks API: {e.__class__.__name__}"
            )
            self.steam_not_running = True

            # Emit signal for UI notification
            from app.utils.event_bus import EventBus

            EventBus().steam_not_running.emit()
            return False

    def _begin_callbacks(
        self, operation_name: str, callbacks_total: int | None = None
    ) -> None:
        """
        Start callback thread for current operation. INTERNAL USE ONLY.
        Thread-safe: Acquires operation lock to prevent concurrent operations.

        :param operation_name: Name of operation starting (for logging/debugging)
        :param callbacks_total: Total number of callbacks expected for this operation
        :raises RuntimeError: If callbacks are already in progress
        """
        if self.steam_not_running:
            return

        with self._operation_lock:
            # Prevent concurrent operations from interfering with each other
            if self.callbacks:
                logger.error(
                    f"Cannot start new operation '{operation_name}' - "
                    f"operation '{self._current_operation}' already in progress! "
                    f"(queue_size: {self._operation_queue.qsize()})"
                )
                raise RuntimeError(
                    f"SteamworksInterface operation already in progress: {self._current_operation}. "
                    "Wait for current operation to complete before starting a new one."
                )

            self._reset_operation_state()
            self._current_operation = operation_name
            self.callbacks = True
            self.callbacks_total = callbacks_total
            self.multiple_queries = bool(callbacks_total)
            self.end_callbacks = False

            logger.debug(f"Starting callback thread for operation: {operation_name}")
            self.steamworks_thread = self._daemon()
            self.steamworks_thread.start()

    def _enqueue_or_execute(
        self,
        operation_name: str,
        execute_fn: Callable[[], None],
        batch_id: str | None = None,
    ) -> None:
        """
        Queue operation if busy, otherwise execute immediately.

        :param operation_name: Name of operation for logging
        :type operation_name: str
        :param execute_fn: Function to execute
        :type execute_fn: Callable[[], None]
        :param batch_id: Optional batch ID for tracking
        :type batch_id: str | None
        :return: None
        """
        with self._operation_lock:
            # Check if operation already in progress
            if self.callbacks:
                self._operation_queue.put(
                    QueuedOperation(
                        name=operation_name, execute=execute_fn, batch_id=batch_id
                    )
                )
                logger.info(
                    f"Operation '{operation_name}' queued (current: '{self._current_operation}', queue_size: {self._operation_queue.qsize()})"
                )
                return

        # No operation in progress - execute immediately
        logger.debug(f"Executing '{operation_name}' immediately")
        execute_fn()

    def _process_next_queued_operation(self) -> None:
        """
        Process next operation from queue if any. Must be called with lock held.

        :return: None
        """
        if self._operation_queue.empty():
            logger.debug("Queue empty, no operations to process")
            return

        if self._processing_queue:
            logger.debug(
                "Queue processing already in progress, skipping (re-entrancy prevention)"
            )
            return  # Avoid re-entrancy

        self._processing_queue = True

        try:
            # Get next operation (non-blocking)
            operation = self._operation_queue.get_nowait()
            logger.info(
                f"Processing queued operation: {operation.name} (remaining: {self._operation_queue.qsize()})"
            )

            # Release lock before executing (avoid deadlock)
            # The operation will re-acquire lock in _begin_callbacks
            self._operation_lock.release()
            try:
                operation.execute()
            except Exception as e:
                # Log error but continue processing queue
                logger.error(
                    f"Queued operation '{operation.name}' failed: {e} "
                    f"(batch_id: {operation.batch_id}, queue_remaining: {self._operation_queue.qsize()})",
                    exc_info=True,
                )
            finally:
                self._operation_lock.acquire()
        except Exception as e:
            logger.error(f"Error in queue processing: {e}", exc_info=True)
        finally:
            self._processing_queue = False
            try:
                self._operation_queue.task_done()
            except ValueError:
                pass  # Queue empty

    def _finish_callbacks(self, timeout: int = 60) -> None:
        """
        Wait for callbacks to complete and join thread. INTERNAL USE ONLY.
        Thread-safe: Acquires lock to update state.

        :param timeout: Maximum time to wait for callbacks in seconds
        """
        # Capture thread reference to avoid race condition
        thread = self.steamworks_thread

        # Check without lock first (optimization)
        if not self.callbacks or thread is None:
            return

        self._wait_for_callbacks(timeout)

        # Re-capture in case it changed during wait
        thread = self.steamworks_thread
        if thread is not None and thread.is_alive():
            logger.warning("Callback thread timeout, forcing end")
            with self._operation_lock:
                self.end_callbacks = True

        if thread is not None:
            thread.join(timeout=5)

        with self._operation_lock:
            operation_name = self._current_operation
            logger.info(f"Callback thread completed for operation: {operation_name}")
            self._reset_operation_state()

            # Process next queued operation if any
            self._process_next_queued_operation()

            # Log queue state
            if self._operation_queue.empty():
                logger.debug("All queued operations processed")
            else:
                logger.info(
                    f"Queue has {self._operation_queue.qsize()} operation(s) remaining"
                )

    def shutdown(self) -> None:
        """Shutdown Steamworks API. Called at app shutdown."""
        if hasattr(self, "steamworks") and self.steamworks:
            try:
                if self.steamworks.loaded():
                    logger.info("Shutting down Steamworks API")
                    self.steamworks.unload()
            except Exception as e:
                logger.error(f"Error during Steamworks shutdown: {e}")

    def _callbacks(self) -> None:
        logger.debug("Starting _callbacks")
        while (
            not self.steamworks.loaded()
        ):  # This should not execute as long as Steamworks API init went OK
            logger.warning("Waiting for Steamworks...")
        else:
            logger.info("Steamworks loaded!")
        while not self.end_callbacks:
            self.steamworks.run_callbacks()
            sleep(0.1)
        else:
            logger.info(
                f"{self.callbacks_count} callback(s) received. Ending thread..."
            )

    def _cb_app_dependencies_result_callback(
        self, result: GetAppDependenciesResult_t
    ) -> None:
        """
        Callback handler for GetAppDependencies Steamworks API response.

        Receives structured result from Steamworks with:
        - result: Result code (EResult enum)
        - publishedFileId: Workshop item ID
        - array_app_dependencies: Pointer to array of AppIDs
        - array_num_app_dependencies: Number of dependencies in array
        - total_num_app_dependencies: Total dependencies (may be > array size)

        :param result: GetAppDependenciesResult_t containing query results
        """
        with self._operation_lock:
            # Add to callbacks count
            self.callbacks_count = self.callbacks_count + 1
            # Debug prints
            logger.debug("GetAppDependencies query callback")
            logger.debug(f"result: {result.result}")
            pfid = result.publishedFileId
            logger.debug(f"publishedFileId: {pfid}")
            app_dependencies_list = result.get_app_dependencies_list()
            logger.debug(f"app_dependencies_list: {app_dependencies_list}")
            # Collect data for our query if dependencies were returned
            if len(app_dependencies_list) > 0:
                self.get_app_deps_query_result[pfid] = app_dependencies_list
            # Check for multiple actions
            if self.multiple_queries and self.callbacks_count == self.callbacks_total:
                # Set flag so that _callbacks cease
                self.end_callbacks = True
            elif not self.multiple_queries:
                # Set flag so that _callbacks cease
                self.end_callbacks = True

    def _cb_subscription_action(self, result: SubscriptionResult) -> None:
        """
        Callback handler for subscription action (subscribe/unsubscribe) responses.

        Receives structured result from Steamworks with:
        - result: Result code (EResult enum)
        - publishedFileId: Workshop item ID that was subscribed/unsubscribed

        :param result: SubscriptionResult containing action result
        """
        with self._operation_lock:
            # Add to callbacks count
            self.callbacks_count = self.callbacks_count + 1
            # Debug prints
            logger.debug("Subscription action callback")
            logger.debug(f"result: {result.result}")
            logger.debug(f"PublishedFileId: {result.publishedFileId}")
            # Uncomment to see steam client install info of the mod
            # logger.info(
            #     self.steamworks.Workshop.GetItemInstallInfo(result.publishedFileId)
            # )
            # Check for multiple actions
            if self.multiple_queries and self.callbacks_count == self.callbacks_total:
                # Set flag so that _callbacks cease
                self.end_callbacks = True
            elif not self.multiple_queries:
                # Set flag so that _callbacks cease
                self.end_callbacks = True

    def _cb_download_item_result(self, result: DownloadItemResult_t) -> None:
        """
        Callback for DownloadItem API result.

        :param result: DownloadItemResult_t from Steamworks
        :type result: DownloadItemResult_t
        :return: None
        """
        # Use upstream field names: appID, publishedFileId, result
        pfid = result.publishedFileId  # NOT m_nPublishedFileId
        eresult = result.result  # NOT m_eResult
        app_id = result.appID  # NOT m_unAppID

        logger.debug(
            f"DownloadItem callback: pfid={pfid}, result={eresult}, appID={app_id}"
        )

        # Decrement callbacks
        with self._operation_lock:
            self.callbacks_count += 1
            logger.debug(
                f"Download callbacks: {self.callbacks_count}/{self.callbacks_total}"
            )

            # Check if download initiated successfully
            if eresult == 1:  # k_EResultOK
                logger.info(f"Download started successfully for pfid={pfid}")

                # Update tracker: DOWNLOADING
                if self._current_batch_id:
                    from app.models.download_state import DownloadStatus
                    from app.utils.download_tracker import DownloadTracker

                    DownloadTracker().update_item_status(
                        pfid, DownloadStatus.DOWNLOADING
                    )

                    # Check if download is actually needed
                    # If mod is already up-to-date, Steam may not download anything
                    download_info = self.steamworks.Workshop.GetItemDownloadInfo(pfid)

                    # If no download info or 0 bytes, check if already installed
                    if not download_info or (
                        download_info.get("downloaded", 0) == 0
                        and download_info.get("total", 0) == 0
                    ):
                        install_info = self.steamworks.Workshop.GetItemInstallInfo(pfid)
                        if install_info and install_info.get("timestamp"):
                            logger.info(
                                f"Item {pfid} already up-to-date, marking COMPLETED"
                            )
                            DownloadTracker().update_item_status(
                                pfid, DownloadStatus.COMPLETED
                            )
            else:
                logger.error(
                    f"Download failed for pfid={pfid}, EResult={eresult} "
                    f"(batch_id: {self._current_batch_id})"
                )

                # Update tracker: FAILED
                if self._current_batch_id:
                    from app.models.download_state import DownloadStatus
                    from app.utils.download_tracker import DownloadTracker

                    DownloadTracker().update_item_status(
                        pfid, DownloadStatus.FAILED, error=f"EResult={eresult}"
                    )

            # Check for multiple actions
            if self.multiple_queries and self.callbacks_count == self.callbacks_total:
                # Set flag so that _callbacks cease
                self.end_callbacks = True
            elif not self.multiple_queries:
                # Set flag so that _callbacks cease
                self.end_callbacks = True

    def _cb_item_installed(self, result: ItemInstalled_t) -> None:
        """
        Callback handler for ItemInstalled_t - fires when mod download completes.

        This callback fires when Steam completes downloading and installing
        a Workshop item. Use this instead of ACF polling to detect installation.

        :param result: ItemInstalled_t containing appId and publishedFileId
        :type result: ItemInstalled_t
        :return: None
        """
        pfid = result.publishedFileId
        logger.info(
            f"ItemInstalled_t callback fired: pfid={pfid}, appId={result.appId}"
        )

        # Update download tracker
        from app.models.download_state import DownloadStatus
        from app.utils.download_tracker import DownloadTracker
        from app.utils.event_bus import EventBus

        tracker = DownloadTracker()
        logger.debug(f"Updating status to COMPLETED for pfid={pfid}")
        tracker.update_item_status(pfid, DownloadStatus.COMPLETED)

        # Emit signal for metadata refresh (for this specific mod, convert to string for 64-bit Steam IDs)
        logger.debug(f"Emitting workshop_item_installed signal for pfid={pfid}")
        EventBus().workshop_item_installed.emit(str(pfid))

    def enable_item_installed_callbacks(self) -> None:
        """
        Enable ItemInstalled_t callbacks for download tracking.

        :return: None
        """
        if not self.steam_not_running and self.steamworks.loaded():
            if not self._item_installed_callback_active:
                self.steamworks.Workshop.SetItemInstalledCallback(
                    self._cb_item_installed
                )
                self._item_installed_callback_active = True
                logger.info("ItemInstalled callbacks enabled")

    def disable_item_installed_callbacks(self) -> None:
        """
        Disable ItemInstalled_t callbacks.

        :return: None
        """
        if self._item_installed_callback_active:
            self.steamworks.Workshop.ClearItemInstalledCallback()
            self._item_installed_callback_active = False
            logger.info("ItemInstalled callbacks disabled")

    def _daemon(self) -> Thread:
        """
        Returns a Thread pointing to our _callbacks daemon
        """
        return Thread(target=self._callbacks, daemon=True)

    def _wait_for_callbacks(self, timeout: int) -> None:
        """
        Waits for the Steamworks API callbacks to complete within a specified time interval.

        Args:
            timeout (int): Maximum time to wait in seconds.

        Returns:
            None
        """
        # Capture thread reference to avoid race condition
        thread = self.steamworks_thread
        if thread is None:
            return

        start_time = time()
        logger.debug(f"Waiting {timeout} seconds for Steamworks API callbacks...")
        while thread.is_alive():
            elapsed_time = time() - start_time
            if elapsed_time >= timeout:
                self.end_callbacks = True
                break
            sleep(1)


# Worker functions for background processing


def steamworks_app_dependencies_worker(
    pfid_or_pfids: int | list[int],
    interval: int = 1,
    _libs: str | None = None,
) -> dict[int, Any] | None:
    """
    Worker for querying app dependencies.

    Called from QThreadPool worker (AppDependenciesWorker) to query Steam Workshop
    mod app dependencies via Steamworks API.

    :param pfid_or_pfids: Single PublishedFileId or list of PublishedFileIds
    :param interval: Sleep interval between API calls (seconds)
    :param _libs: Optional path to Steamworks libraries
    :return: Dict mapping PublishedFileId to app dependencies, or None
    """
    steamworks_interface = SteamworksInterface.instance(_libs=_libs)
    return steamworks_interface.query_app_dependencies(pfid_or_pfids, interval)


def steamworks_game_launch_worker(
    game_install_path: str,
    args: list[str],
    _libs: str | None = None,
) -> None:
    """
    Worker for launching game in separate process.

    :param game_install_path: Path to game installation folder
    :param args: Launch arguments for the game
    :param _libs: Optional path to Steamworks libraries
    """
    steamworks_interface = SteamworksInterface.instance(_libs=_libs)
    steamworks_interface.launch_game(game_install_path, args)


if __name__ == "__main__":
    sys.exit()
