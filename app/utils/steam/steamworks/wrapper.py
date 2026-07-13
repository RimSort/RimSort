"""
Steamworks API Wrapper Module

Provides Python wrappers for Steamworks API interactions including:
- Workshop mod subscription/unsubscription (ISteamUGC)
- Game launching with Steamworks integration
- App dependency queries
- Callback-based async event handling

Key features:
- Proper sequencing for resubscribe operations (unsub → 1s wait → sub → 1s wait → download)
- Batched processing with operation intervals (0.1s) for subscribe/unsubscribe
- Time-based completion waiting (callbacks unreliable for batch operations)
- Comprehensive logging for debugging and monitoring

Usage:
    - SteamworksSubscriptionHandler: Handle mod subscription operations
    - SteamworksGameLaunch: Launch RimWorld with Steamworks initialized
    - SteamworksAppDependenciesQuery: Query mod dependencies

Reference:
    https://partner.steamgames.com/doc/api/ISteamUGC
    https://github.com/philippj/SteamworksPy
    https://philippj.github.io/SteamworksPy
    https://github.com/philippj/SteamworksPy/issues/62
    https://github.com/philippj/SteamworksPy/issues/75
    https://github.com/philippj/SteamworksPy/pull/76
"""

from __future__ import annotations

import sys
from multiprocessing import Process
from multiprocessing.synchronize import Lock as MpLock
from os import getcwd
from pathlib import Path
from threading import Thread
from time import sleep, time
from typing import Any, Callable, Union

from loguru import logger

# If we're running from a Python interpreter, Ensure SteamworksPy module is in Python path, sys.path ($PYTHONPATH)
# Ensure that this is available by running via: git submodule update --init --recursive
# You can automatically ensure this is done by utilizing distribute.py
if "__compiled__" not in globals():
    sys.path.append(str((Path(getcwd()) / "submodules" / "SteamworksPy")))

from steamworks import STEAMWORKS  # type: ignore

from app.utils.generic import launch_game_process

# Timing constants for subscription operations
RESUBSCRIBE_STAGE_WAIT = 1  # Seconds to wait between resubscribe stages (unsub/sub)
OPERATION_INTERVAL = 0.1  # Seconds between API calls and callback polling
STEAMWORKS_TIMEOUT = (
    30  # Seconds to wait for Steamworks SDK initialization and operations
)


class SteamworksInterface:
    """
    Low-level Steamworks API interface wrapper.

    Manages Steamworks SDK initialization, callback threading, and lifecycle.
    Provides callback-based async event handling for Steam operations.

    Attributes:
        callbacks (bool): Whether to enable callback-based event handling
        callbacks_count (int): Number of callbacks received so far
        callbacks_total (int | None): Total callbacks expected (for AppDependencies queries)
        multiple_queries (bool): Whether multiple AppDependencies queries are in flight
        end_callbacks (bool): Signal to end the callback thread
        steam_not_running (bool): Whether Steam was unavailable during init
        steamworks: STEAMWORKS SDK instance
        steamworks_thread (Thread | None): Background thread running callback loop (if callbacks enabled)
        get_app_deps_query_result (dict): Cached AppDependencies query results

    Reference:
    https://partner.steamgames.com/doc/api/ISteamUGC
    https://github.com/philippj/SteamworksPy
    https://philippj.github.io/SteamworksPy
    https://github.com/philippj/SteamworksPy/issues/62
    https://github.com/philippj/SteamworksPy/issues/75
    https://github.com/philippj/SteamworksPy/pull/76
    """

    def __init__(
        self,
        callbacks: bool,
        callbacks_total: int | None = None,
        _libs: str | None = None,
    ) -> None:
        """
        Initialize Steamworks API interface.

        Args:
            callbacks: Enable callback-based async event handling
            callbacks_total: Expected number of callbacks (for AppDependencies queries)
            _libs: Optional path to prebuilt Steamworks libraries
        """
        logger.info("SteamworksInterface initializing...")
        self.callbacks = callbacks
        self.callbacks_count = 0
        self.callbacks_total = callbacks_total
        if self.callbacks:
            logger.debug("Callbacks enabled!")
            self.end_callbacks = False  # Signal used to end the _callbacks Thread
            if (
                self.callbacks_total
            ):  # Pass this if you want to do multiple actions with 1 initialization
                logger.debug(f"Callbacks total : {self.callbacks_total}")
                self.multiple_queries = True
            else:
                self.multiple_queries = False
        # Used for GetAppDependencies data
        self.get_app_deps_query_result: dict[int, Any] = {}
        self.steam_not_running = False  # Skip action if True. Log occurrences.
        self.steamworks = STEAMWORKS(_libs=_libs)
        try:
            self.steamworks.initialize()  # Init the Steamworks API
        except Exception as e:
            logger.warning(
                f"Unable to initialize Steamworks API due to exception: {e.__class__.__name__}"
            )
            logger.warning(
                "If you are a Steam user, please check that Steam running and that you are logged in..."
            )
            self.steam_not_running = True
        if not self.steam_not_running:  # Skip if True
            if self.callbacks:
                # Start the thread
                logger.debug("Starting thread")
                self.steamworks_thread = self._daemon()
                self.steamworks_thread.start()

    def _callbacks(self) -> None:
        """
        Background thread target for processing Steamworks callbacks.

        Runs in a daemon thread, calling steamworks.run_callbacks() repeatedly
        until self.end_callbacks is set. Callbacks fire asynchronously and
        invoke handlers registered via SetItemSubscribedCallback, etc.
        """
        logger.debug("Starting _callbacks")
        # Wait for Steamworks to be fully loaded
        while not self.steamworks.loaded():
            logger.warning("Waiting for Steamworks...")
        else:
            logger.info("Steamworks loaded!")

        # Main callback loop - process events every 100ms until signaled to stop
        while not self.end_callbacks:
            self.steamworks.run_callbacks()
            sleep(0.1)
        else:
            logger.info(
                f"{self.callbacks_count} callback(s) received. Ending thread..."
            )

    # TODO: Rework this for proper static type checking
    def _cb_app_dependencies_result_callback(self, *args: Any, **kwargs: Any) -> None:
        """
        Executes upon Steamworks API callback response
        """
        # Add to callbacks count
        self.callbacks_count = self.callbacks_count + 1
        # Debug prints
        logger.debug(f"GetAppDependencies query callback: {args}, {kwargs}")
        logger.debug(f"result : {args[0].result}")
        pfid = args[0].publishedFileId
        logger.debug(f"publishedFileId : {pfid}")
        app_dependencies_list = args[0].get_app_dependencies_list()
        logger.debug(f"app_dependencies_list : {app_dependencies_list}")
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

    def _daemon(self) -> Thread:
        """
        Returns a Thread pointing to our _callbacks daemon
        """
        return Thread(target=self._callbacks, daemon=True)

    def _wait_for_callbacks(self, timeout: int) -> bool:
        """
        Waits for the Steamworks API callbacks to complete within a specified time interval.

        Args:
            timeout (int): Maximum time to wait in seconds.

        Returns:
            bool: True if all callbacks completed normally, False if timeout occurred.
        """
        start_time = time()
        logger.debug(f"Waiting {timeout} seconds for Steamworks API callbacks...")
        while not self.end_callbacks and self.steamworks_thread.is_alive():
            elapsed_time = time() - start_time
            if elapsed_time >= timeout:
                logger.warning(
                    f"Callback timeout after {timeout}s (received {self.callbacks_count}/{self.callbacks_total})"
                )
                self.end_callbacks = True
                return False
            if self.callbacks_total and self.callbacks_count >= self.callbacks_total:
                return True
            sleep(OPERATION_INTERVAL)
        return True


# Per-process shared SteamworksInterface (set by _pool_init_worker, reused across chunks)
WORKER_INTERFACE: list["SteamworksInterface | None"] = [None]


def _pool_init_worker(project_root: str, libs_path: str, init_lock: MpLock) -> None:
    """Initialize worker process: set env, chdir, create shared SteamworksInterface.

    Acquires *init_lock* before calling SteamInit() so that only one worker
    process initializes at a time. This prevents the Steam client from being
    overwhelmed by N concurrent pipe registrations (``pipes.cpp`` stall).
    """
    import os

    os.environ["SWPY_PATH"] = libs_path
    os.chdir(project_root)
    with init_lock:
        si = SteamworksInterface(callbacks=True, callbacks_total=0, _libs=libs_path)
        if not si.steam_not_running:
            WORKER_INTERFACE[0] = si
        else:
            si.steamworks.unload()


class SteamworksAppDependenciesQuery:
    """Query PublishedFileIDs for AppID dependency data using Steamworks API."""

    def __init__(
        self,
        pfid_or_pfids: Union[int, list[int]],
        interval: float = 1,
        _libs: str | None = None,
    ) -> None:
        self._libs = _libs
        self.interval = interval
        self.pfid_or_pfids = (
            pfid_or_pfids if isinstance(pfid_or_pfids, list) else [pfid_or_pfids]
        )

    def run(self) -> None | dict[int, Any]:
        """
        Execute the AppDependencies query against Steamworks.

        Uses the per-worker shared SteamworksInterface (set by _pool_init_worker),
        firing GetAppDependencies() sequentially and pumping callbacks between
        each query to work around CCallResult's single-pending-call limitation.
        """
        total = len(self.pfid_or_pfids)
        logger.info(
            f"GetAppDependencies handling {total} pfid(s): {self.pfid_or_pfids}"
        )

        # Prefer the per-worker shared interface (set once by _pool_init_worker)
        # Fall back to a fresh one if the shared interface is stuck/dead
        si = WORKER_INTERFACE[0]
        fresh_interface = False
        if si is not None and not si.steam_not_running and si.end_callbacks:
            # Shared interface had a prior timeout — try to recover
            si.steamworks_thread.join(timeout=1)
            if si.steamworks_thread.is_alive():
                # Thread stuck — create fresh interface for this chunk
                si = SteamworksInterface(
                    callbacks=True, callbacks_total=total, _libs=self._libs
                )
                if si.steam_not_running:
                    si.steamworks.unload()
                    return None
                fresh_interface = True
            else:
                # Thread exited cleanly — restart for this batch
                si.end_callbacks = False
                si.multiple_queries = True
                si.callbacks_count = 0
                si.callbacks_total = total
                si.get_app_deps_query_result = {}
                si.steamworks_thread = si._daemon()
                si.steamworks_thread.start()
        elif si is None or si.steam_not_running:
            si = SteamworksInterface(
                callbacks=True, callbacks_total=total, _libs=self._libs
            )
            if si.steam_not_running:
                si.steamworks.unload()
                return None
            fresh_interface = True
        else:
            # Reuse shared interface — reset callback counters
            si.callbacks_count = 0
            si.multiple_queries = True
            si.callbacks_total = total
            si.get_app_deps_query_result = {}
            si.end_callbacks = False

        si.steamworks.Workshop.SetGetAppDependenciesResultCallback(
            si._cb_app_dependencies_result_callback
        )

        # Drain any residual callbacks from a previous chunk before starting
        si.steamworks.run_callbacks()

        # Fire queries sequentially, waiting for each pfid's callback before
        # issuing the next query.  CCallResult can only track ONE pending call
        # at a time — each new GetAppDependencies() unregisters the previous
        # CCallResult, silently dropping its callback.  By pumping callbacks
        # between queries until the expected callback count is reached, we
        # ensure every CCallResult completes before being replaced.
        PROGRESS_LOG_INTERVAL = 100
        WAIT_TIMEOUT = 100  # 100 * self.interval = 100 * 0.1 = 10s per pfid
        for idx, pfid in enumerate(self.pfid_or_pfids):
            si.steamworks.Workshop.GetAppDependencies(pfid)
            # Wait for THIS pfid's callback to be dispatched
            target = si.callbacks_count + 1
            for _ in range(WAIT_TIMEOUT):
                si.steamworks.run_callbacks()
                if si.callbacks_count >= target:
                    break
                sleep(self.interval)
            if (idx + 1) % PROGRESS_LOG_INTERVAL == 0:
                logger.info(f"GetAppDependencies progress: {idx + 1}/{total}")

        # Wait for callbacks to complete
        si._wait_for_callbacks(timeout=60)
        if si.steamworks_thread.is_alive() and si.end_callbacks:
            si.steamworks_thread.join(timeout=5)

        new_results = si.get_app_deps_query_result
        received = len(new_results.keys())
        logger.info(f"GetAppDependencies complete: {received}/{total} results received")

        if fresh_interface:
            si.steamworks.unload()
        return new_results


class SteamworksGameLaunch(Process):
    def __init__(
        self, game_install_path: str, run_args: str = "", _libs: str | None = None
    ) -> None:
        Process.__init__(self)
        self._libs = _libs
        self.game_install_path = game_install_path
        self.run_args = run_args

    def run(self) -> None:
        """
        Handle SW game launch; instructions received from connected signals

        :param game_install_path: is a string path to the game folder
        :param run_args: is a string representing the args to pass to the generated executable path
        """
        logger.info("Creating SteamworksInterface and launching game executable")
        # Try to initialize the SteamWorks API, but allow game to launch if Steam not found
        steamworks_interface = SteamworksInterface(callbacks=False, _libs=self._libs)

        # Launch the game
        launch_game_process(
            game_install_path=Path(self.game_install_path), run_args=self.run_args
        )
        # If we had an API initialization, try to unload it
        if (
            not steamworks_interface.steam_not_running
            and steamworks_interface.steamworks
        ):
            # Unload Steamworks API
            steamworks_interface.steamworks.unload()


class SteamworksSubscriptionHandler(Process):
    """
    Handles Steam Workshop mod subscription operations.

    Supports three operations:
    - "subscribe": Subscribe to mods (ISteamUGC::SubscribeItem)
    - "unsubscribe": Unsubscribe from mods (ISteamUGC::UnsubscribeItem)
    - "resubscribe": Unsub then resub with proper delays (forces Steam to re-download)

    Resubscribe timing is critical for fixing GitHub issue #1460 (missing mods):
    1. UnsubscribeItem() → Steam marks as unsubscribed
    2. Wait 1 second → Steam uninstalls mod files
    3. SubscribeItem() → Steam marks as subscribed
    4. Wait 1 second → Steam registers subscription and queues download
    5. DownloadItem(high_priority=True) → Forces Steam to prioritize re-download

    Without proper spacing, Steam can queue operations in wrong order,
    resulting in mods being subscribed but not downloaded.

    Uses time-based completion waiting with configurable timeouts.

    Attributes:
        action (str): Operation to perform
        pfid_or_pfids (list[int]): Published file IDs (Steam Workshop mod IDs)
        _libs (str | None): Optional path to prebuilt Steamworks libraries
    """

    def __init__(
        self,
        action: str,
        pfid_or_pfids: Union[int, list[int]],
        _libs: str | None = None,
    ):
        """
        Initialize subscription handler.

        Args:
            action: Operation type ("subscribe", "unsubscribe", or "resubscribe")
            pfid_or_pfids: Single mod ID or list of mod IDs to process
            _libs: Optional custom path to Steamworks libraries

        Raises:
            ValueError: If action is not one of the valid types
        """
        Process.__init__(self)

        # Validate action type
        valid_actions = {"subscribe", "unsubscribe", "resubscribe"}
        if action not in valid_actions:
            raise ValueError(
                f"Invalid action '{action}'. Must be one of {valid_actions}"
            )

        self._libs = _libs
        self.action = action
        # Normalize to list for consistent handling
        self.pfid_or_pfids = (
            pfid_or_pfids if isinstance(pfid_or_pfids, list) else [pfid_or_pfids]
        )

    def run(self) -> None:
        """
        Main entry point for handling subscription operations.

        Initializes Steamworks API, sets up callbacks, executes the operation
        (subscribe/unsubscribe/resubscribe), and waits for Steam to process.

        Note: Steam's subscription callbacks are unreliable for batch operations.
        Operations are queued and completion is determined by time-based waiting, not callbacks.

        Timeout (time-based, not callback-based):
        - All operations: 30 seconds (covers Steamworks initialization and operations)
        """
        logger.warning(
            f"=== SteamworksSubscriptionHandler START: action={self.action}, mods={len(self.pfid_or_pfids)} ==="
        )

        # We don't set a strict callback count since Steam may not fire callbacks reliably
        # Instead, we queue operations, wait for processing, and trust Steam handled them
        callbacks_total = None
        logger.warning(f"Queuing {len(self.pfid_or_pfids)} mod(s) for {self.action}")

        steamworks_interface = SteamworksInterface(
            callbacks=True, callbacks_total=callbacks_total, _libs=self._libs
        )

        if steamworks_interface.steam_not_running:
            logger.error("Steam is not running. Aborting subscription handler.")
            if steamworks_interface.steamworks:
                steamworks_interface.steamworks.unload()
            return

        # Wait for Steamworks to be ready
        logger.warning("Waiting for Steamworks to load...")
        start_time = time()
        while not steamworks_interface.steamworks.loaded():
            if time() - start_time > STEAMWORKS_TIMEOUT:
                logger.error(
                    f"Timeout waiting for Steamworks to load (>{STEAMWORKS_TIMEOUT}s)"
                )
                return
            sleep(OPERATION_INTERVAL)
        logger.warning("Steamworks loaded and ready")

        try:
            if self.action == "resubscribe":
                self._handle_resubscribe(steamworks_interface)
            elif self.action == "subscribe":
                self._handle_subscribe(steamworks_interface)
            elif self.action == "unsubscribe":
                self._handle_unsubscribe(steamworks_interface)

            # Wait for Steam to process operations
            # Callbacks are unreliable, so we use time-based waiting instead
            logger.warning(
                f"Waiting up to {STEAMWORKS_TIMEOUT}s for Steam to process operations..."
            )
            completed = steamworks_interface._wait_for_callbacks(
                timeout=STEAMWORKS_TIMEOUT
            )

            if completed:
                logger.warning(
                    f"✓ Operations completed! (callbacks received: {steamworks_interface.callbacks_count})"
                )
            else:
                logger.warning(
                    f"⚠ Timeout after {STEAMWORKS_TIMEOUT}s (callbacks: {steamworks_interface.callbacks_count}). Operations queued - Steam will process in background."
                )

        except Exception as e:
            logger.error(
                f"✗ Error during subscription action {self.action}: {e}", exc_info=True
            )
        finally:
            # Cleanup
            logger.warning(
                "=== SteamworksSubscriptionHandler END: Unloading Steamworks ==="
            )
            if "steamworks_interface" in locals():
                if (
                    hasattr(steamworks_interface, "steamworks_thread")
                    and steamworks_interface.steamworks_thread.is_alive()
                ):
                    steamworks_interface.steamworks_thread.join(timeout=5)
                if steamworks_interface.steamworks:
                    steamworks_interface.steamworks.unload()

    def _queue_operations(
        self,
        steamworks_interface: SteamworksInterface,
        operation: str,
        pfids: list[int],
    ) -> None:
        """
        Queue multiple operations with spacing between API calls.

        Args:
            steamworks_interface: Steamworks interface instance
            operation: Operation type ("subscribe" or "unsubscribe")
            pfids: List of published file IDs to process
        """
        operation_map = {
            "subscribe": steamworks_interface.steamworks.Workshop.SubscribeItem,
            "unsubscribe": steamworks_interface.steamworks.Workshop.UnsubscribeItem,
        }

        for idx, pfid in enumerate(pfids, 1):
            logger.warning(f"  [{idx}/{len(pfids)}] {operation.capitalize()}: {pfid}")
            if operation in operation_map:
                operation_map[operation](pfid)

            # Small gap between API calls to space them out (except after the last one)
            if idx < len(pfids):
                sleep(OPERATION_INTERVAL)

    def _register_callbacks(
        self, steamworks_interface: SteamworksInterface, actions: set[str]
    ) -> None:
        """
        Register callbacks for specified actions.

        Args:
            steamworks_interface: Steamworks interface instance
            actions: Set of actions to register callbacks for ("subscribe", "unsubscribe")

        Note: Callbacks are registered for logging purposes. Reliability is not guaranteed
        for batch operations, so operation completion is time-based rather than callback-based.
        """
        if "unsubscribe" in actions:
            steamworks_interface.steamworks.Workshop.SetItemUnsubscribedCallback(
                self._create_callback(steamworks_interface, "unsubscribe")
            )
            logger.debug("Unsubscribe callback registered")

        if "subscribe" in actions:
            steamworks_interface.steamworks.Workshop.SetItemSubscribedCallback(
                self._create_callback(steamworks_interface, "subscribe")
            )
            logger.debug("Subscribe callback registered")

    def _handle_resubscribe(self, steamworks_interface: SteamworksInterface) -> None:
        """
        Resubscribe to mods with batched sequencing (fixes GitHub issue #1460).

        Process all mods in five stages to ensure proper Steam sequencing:

        Stage 1: Unsubscribe ALL mods (small delays between API calls)
        Stage 2: Wait 1 second (let Steam uninstall all mod files)
        Stage 3: Subscribe ALL mods (small delays between API calls)
        Stage 4: Wait 1 second (let Steam register all subscriptions)
        Stage 5: Download ALL mods (force Steam to queue downloads)

        This batched approach is more efficient than per-mod sequencing:
        - Faster: Reduces total time from 27+ seconds (per-mod) to ~4 seconds (batched)
        - More stable: All unsubs complete before any subs start
        - Clearer: Better matches Steam's async queue expectations

        Without proper staging, Steam may queue subscribe before unsubscribe
        completes, resulting in mods subscribed but not downloaded.
        """
        logger.warning(
            f">>> RESUBSCRIBE: Starting for {len(self.pfid_or_pfids)} mod(s)"
        )

        # Register callback for subscription changes
        self._register_callbacks(steamworks_interface, {"unsubscribe", "subscribe"})

        # STAGE 1: Unsubscribe ALL mods
        logger.warning(f">>> STAGE 1: Unsubscribing {len(self.pfid_or_pfids)} mod(s)")
        self._queue_operations(steamworks_interface, "unsubscribe", self.pfid_or_pfids)

        # STAGE 2: Wait for Steam to uninstall all mod files
        logger.warning(
            f"  Waiting {RESUBSCRIBE_STAGE_WAIT}s for all unsubscribes to complete..."
        )
        sleep(RESUBSCRIBE_STAGE_WAIT)

        # STAGE 3: Subscribe ALL mods
        logger.warning(f">>> STAGE 3: Subscribing {len(self.pfid_or_pfids)} mod(s)")
        self._queue_operations(steamworks_interface, "subscribe", self.pfid_or_pfids)

        # STAGE 4: Wait for Steam to register all subscriptions
        logger.warning(
            f"  Waiting {RESUBSCRIBE_STAGE_WAIT}s for all subscribes to register..."
        )
        sleep(RESUBSCRIBE_STAGE_WAIT)

        # STAGE 5: Force download ALL mods with high priority
        logger.warning(
            f">>> STAGE 5: Initiating downloads for {len(self.pfid_or_pfids)} mod(s)"
        )
        for idx, pfid in enumerate(self.pfid_or_pfids, 1):
            try:
                logger.warning(f"  [{idx}/{len(self.pfid_or_pfids)}] Download: {pfid}")
                # Call DownloadItem to force Steam to queue the mod for download
                # high_priority=True makes Steam skip other queued downloads
                # Note: callback may not fire, but the download is still queued
                if hasattr(steamworks_interface.steamworks.Workshop, "DownloadItem"):
                    steamworks_interface.steamworks.Workshop.DownloadItem(
                        pfid,
                        high_priority=True,
                        callback=self._create_download_callback(steamworks_interface),
                        override_callback=True,
                    )
                else:
                    logger.warning(
                        "DownloadItem skipped: not supported by SteamworksPy library."
                    )
            except Exception as e:
                logger.error(
                    f"Failed to trigger download for {pfid}: {e}", exc_info=True
                )

        logger.warning(">>> All mods queued. Waiting for operations to complete...")

    def _handle_subscribe(self, steamworks_interface: SteamworksInterface) -> None:
        """
        Subscribe to mods in batches
        """
        logger.warning(f">>> SUBSCRIBE: Starting for {len(self.pfid_or_pfids)} mod(s)")

        self._register_callbacks(steamworks_interface, {"subscribe"})

        # Queue all subscribe operations immediately with small gaps
        self._queue_operations(steamworks_interface, "subscribe", self.pfid_or_pfids)

    def _handle_unsubscribe(self, steamworks_interface: SteamworksInterface) -> None:
        """
        Unsubscribe from mods in batches
        """
        logger.warning(
            f">>> UNSUBSCRIBE: Starting for {len(self.pfid_or_pfids)} mod(s)"
        )

        self._register_callbacks(steamworks_interface, {"unsubscribe"})

        # Queue all unsubscribe operations immediately with small gaps
        self._queue_operations(steamworks_interface, "unsubscribe", self.pfid_or_pfids)

    def _create_callback(
        self, steamworks_interface: SteamworksInterface, operation: str
    ) -> Callable[[Any], None]:
        """
        Create a generic callback handler for logging purposes.

        Since Steam's subscription callbacks are unreliable for batch operations,
        this handler only logs the callback event and increments the counter.
        Completion is determined by time-based waiting, not callback counts.
        """

        def callback(*args: Any, **kwargs: Any) -> None:
            steamworks_interface.callbacks_count += 1
            try:
                if args and hasattr(args[0], "publishedFileId"):
                    pfid = args[0].publishedFileId
                    result = getattr(args[0], "result", None)
                    logger.debug(
                        f"✓ {operation.capitalize()} callback: {pfid} (result={result})"
                    )
                else:
                    logger.debug(f"✓ {operation.capitalize()} callback fired")
            except Exception as e:
                logger.debug(f"{operation.capitalize()} callback: {e}")

        return callback

    def _create_download_callback(
        self, steamworks_interface: SteamworksInterface
    ) -> Callable[[Any], None]:
        """
        Create download callback handler.

        Returns a callable that logs download results. Note that DownloadItem
        callbacks are unreliable and may not fire, so this is primarily used
        for logging purposes and does not affect operation completion.
        """

        def callback(*args: Any, **kwargs: Any) -> None:
            try:
                result = args[0].result
                pfid = args[0].publishedFileId

                if result == 1:
                    logger.debug(f"✓ Download initiated for {pfid}")
                else:
                    logger.warning(f"⚠ Download callback result={result} for {pfid}")
            except (IndexError, AttributeError) as e:
                logger.warning(f"Failed to parse download callback: {e}")

        return callback


if __name__ == "__main__":
    sys.exit()
