"""
Steamworks API Wrapper Module

Provides Python wrappers for Steamworks API interactions including:
- Workshop mod subscription/unsubscription (ISteamUGC)
- Game launching with Steamworks integration
- App dependency queries
- Callback-based async event handling

Key features:
- Proper sequencing for resubscribe operations (unsub → wait → sub → download)
- Sequential processing for subscribe/unsubscribe operations
- Thread-safe callback handling with timeout management
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

import sys
from multiprocessing import Process
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

from app.utils.generic import launch_game_process
from steamworks import STEAMWORKS  # type: ignore

# Timing constants for subscription operations
RESUBSCRIBE_UNSUBSCRIBE_WAIT = 4  # Seconds to wait for Steam to uninstall files
RESUBSCRIBE_SUBSCRIBE_WAIT = 2  # Seconds to wait for Steam to register subscriptions
API_CALL_GAP = 0.5  # Seconds between API calls to space them out
SUBSCRIBE_UNSUBSCRIBE_INTERVAL = (
    0.5  # Seconds between operations in subscribe/unsubscribe
)


class SteamworksInterface:
    """
    Low-level Steamworks API interface wrapper.

    Manages Steamworks SDK initialization, callback threading, and lifecycle.
    Provides callback-based async event handling for Steam operations.

    Attributes:
        callbacks (bool): Whether to enable callback-based event handling
        callbacks_count (int): Number of callbacks received so far
        callbacks_total (int | None): Total callbacks expected (for multi-operation batches)
        multiple_queries (bool): Whether multiple async operations are in flight
        end_callbacks (bool): Signal to end the callback thread
        steam_not_running (bool): Whether Steam was unavailable during init
        steamworks: STEAMWORKS SDK instance
        steamworks_thread (Thread): Background thread running callback loop
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
            callbacks_total: Expected number of callbacks (for multi-op batches)
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

    def _wait_for_callbacks(self, timeout: int) -> None:
        """
        Waits for the Steamworks API callbacks to complete within a specified time interval.

        Args:
            timeout (int): Maximum time to wait in seconds.

        Returns:
            None
        """
        start_time = time()
        logger.debug(f"Waiting {timeout} seconds for Steamworks API callbacks...")
        while self.steamworks_thread.is_alive():
            elapsed_time = time() - start_time
            if elapsed_time >= timeout:
                self.end_callbacks = True
                break
            sleep(1)


class SteamworksAppDependenciesQuery:
    def __init__(
        self,
        pfid_or_pfids: Union[int, list[int]],
        interval: int = 1,
        _libs: str | None = None,
    ) -> None:
        self._libs = _libs
        self.interval = interval
        self.pfid_or_pfids = pfid_or_pfids

    def run(self) -> None | dict[int, Any]:
        """
        Query PublishedFileIDs for AppID dependency data
        :param pfid_or_pfids: is an int that corresponds with a subscribed Steam mod's PublishedFileId
                            OR is a list of int that corresponds with multiple Steam mod PublishedFileIds
        :param interval: time in seconds to sleep between multiple subsequent API calls
        """
        logger.info(
            f"Creating SteamworksInterface and passing PublishedFileID(s) {self.pfid_or_pfids}"
        )
        # If the chunk passed is a single int, convert it into a list in an effort to simplify procedure
        if isinstance(self.pfid_or_pfids, int):
            self.pfid_or_pfids = [self.pfid_or_pfids]
        # Create our Steamworks interface and initialize Steamworks API
        steamworks_interface = SteamworksInterface(
            callbacks=True, callbacks_total=len(self.pfid_or_pfids), _libs=self._libs
        )
        if not steamworks_interface.steam_not_running:  # Skip if True
            while not steamworks_interface.steamworks.loaded():  # Ensure that Steamworks API is initialized before attempting any instruction
                break
            else:
                for pfid in self.pfid_or_pfids:
                    logger.debug(f"ISteamUGC/GetAppDependencies Query: {pfid}")
                    steamworks_interface.steamworks.Workshop.SetGetAppDependenciesResultCallback(
                        steamworks_interface._cb_app_dependencies_result_callback
                    )
                    steamworks_interface.steamworks.Workshop.GetAppDependencies(pfid)
                    # Sleep for the interval if we have more than one pfid to action on
                    if len(self.pfid_or_pfids) > 1:
                        sleep(self.interval)
                # Patience, but don't wait forever
                steamworks_interface._wait_for_callbacks(timeout=60)
                # This means that the callbacks thread has ended. We are done with Steamworks API now, so we dispose of everything.
                logger.info("Thread completed. Unloading Steamworks...")
                steamworks_interface.steamworks_thread.join()
                # Grab the data and return it
                logger.warning(
                    f"Returning {len(steamworks_interface.get_app_deps_query_result.keys())} results..."
                )
                return steamworks_interface.get_app_deps_query_result
        else:
            steamworks_interface.steamworks.unload()

        return None


class SteamworksGameLaunch(Process):
    def __init__(
        self, game_install_path: str, args: list[str], _libs: str | None = None
    ) -> None:
        Process.__init__(self)
        self._libs = _libs
        self.game_install_path = game_install_path
        self.args = args

    def run(self) -> None:
        """
        Handle SW game launch; instructions received from connected signals

        :param game_install_path: is a string path to the game folder
        :param args: is a string representing the args to pass to the generated executable path
        """
        logger.info("Creating SteamworksInterface and launching game executable")
        # Try to initialize the SteamWorks API, but allow game to launch if Steam not found
        steamworks_interface = SteamworksInterface(callbacks=False, _libs=self._libs)

        # Launch the game
        launch_game_process(
            game_install_path=Path(self.game_install_path), args=self.args
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
    2. Wait 4 seconds → Steam uninstalls mod files
    3. SubscribeItem() → Steam marks as subscribed
    4. Wait 2 seconds → Steam registers subscription
    5. DownloadItem(high_priority=True) → Forces Steam to queue re-download

    Without proper spacing, Steam can queue operations in wrong order,
    resulting in mods being subscribed but not downloaded.

    Uses callback-based async event handling with configurable timeouts.

    Attributes:
        action (str): Operation to perform
        pfid_or_pfids (list[int]): Published file IDs (Steam Workshop mod IDs)
        interval (float): Delay in seconds between processing multiple mods
        _libs (str | None): Optional path to prebuilt Steamworks libraries
    """

    def __init__(
        self,
        action: str,
        pfid_or_pfids: Union[int, list[int]],
        interval: float = SUBSCRIBE_UNSUBSCRIBE_INTERVAL,
        _libs: str | None = None,
    ):
        """
        Initialize subscription handler.

        Args:
            action: Operation type ("subscribe", "unsubscribe", or "resubscribe")
            pfid_or_pfids: Single mod ID or list of mod IDs to process
            interval: Seconds to wait between operations (only used for subscribe/unsubscribe)
            _libs: Optional custom path to Steamworks libraries
        """
        Process.__init__(self)
        self._libs = _libs
        self.action = action
        # Normalize to list for consistent handling
        self.pfid_or_pfids = (
            pfid_or_pfids if isinstance(pfid_or_pfids, list) else [pfid_or_pfids]
        )
        self.interval = interval

    def run(self) -> None:
        """
        Main entry point for handling subscription operations.

        Initializes Steamworks API, sets up callbacks, executes the operation
        (subscribe/unsubscribe/resubscribe), and waits for all callbacks.

        Expected callbacks:
        - resubscribe: 2 per mod (unsub + resub)
        - subscribe: 1 per mod
        - unsubscribe: 1 per mod

        Timeouts:
        - resubscribe: 60 seconds (due to 4s + 2s + 3s delays)
        - subscribe/unsubscribe: 30 seconds
        """
        logger.warning(
            f"=== SteamworksSubscriptionHandler START: action={self.action}, mods={len(self.pfid_or_pfids)} ==="
        )

        # Calculate expected callbacks - used to know when all operations complete
        if self.action == "resubscribe":
            # Each mod: 1 unsub callback + 1 resub callback = 2
            # Note: DownloadItem callback unreliable, not counted
            callbacks_total = len(self.pfid_or_pfids) * 2
        else:
            # subscribe/unsubscribe: Each mod gets exactly one callback
            callbacks_total = len(self.pfid_or_pfids)

        logger.warning(f"Expected {callbacks_total} callback(s)")

        steamworks_interface = SteamworksInterface(
            callbacks=True, callbacks_total=callbacks_total, _libs=self._libs
        )

        if steamworks_interface.steam_not_running:
            logger.error("Steam is not running. Aborting subscription handler.")
            steamworks_interface.steamworks.unload()
            return

        # Wait for Steamworks to be ready
        logger.warning("Waiting for Steamworks to load...")
        while not steamworks_interface.steamworks.loaded():
            sleep(0.1)
        logger.warning("Steamworks loaded and ready")

        try:
            if self.action == "resubscribe":
                self._handle_resubscribe(steamworks_interface)
            elif self.action == "subscribe":
                self._handle_subscribe(steamworks_interface)
            elif self.action == "unsubscribe":
                self._handle_unsubscribe(steamworks_interface)
            else:
                logger.error(f"Unknown action: {self.action}")
                return

            # Wait for all callbacks to complete
            # Resubscribe may take longer due to unsub + resub per mod
            timeout = 60 if self.action == "resubscribe" else 30
            logger.warning(
                f"Waiting up to {timeout}s for callbacks to complete (expecting {callbacks_total})..."
            )
            steamworks_interface._wait_for_callbacks(timeout=timeout)
            logger.warning(
                f"✓ All callbacks completed! ({steamworks_interface.callbacks_count}/{callbacks_total})"
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
            if (
                hasattr(steamworks_interface, "steamworks_thread")
                and steamworks_interface.steamworks_thread.is_alive()
            ):
                steamworks_interface.steamworks_thread.join(timeout=5)
            steamworks_interface.steamworks.unload()

    def _handle_resubscribe(self, steamworks_interface: SteamworksInterface) -> None:
        """
        Resubscribe to mods with batched sequencing (fixes GitHub issue #1460).

        Process all mods in three stages to ensure proper Steam sequencing:

        Stage 1: Unsubscribe ALL mods (small delays between API calls)
        Stage 2: Wait 4 seconds (let Steam uninstall all mod files)
        Stage 3: Subscribe ALL mods (small delays between API calls)
        Stage 4: Wait 2 seconds (let Steam register all subscriptions)
        Stage 5: Download ALL mods (force Steam to queue downloads)

        This batched approach is more efficient than per-mod sequencing:
        - Faster: Reduces total time from 27+ seconds (per-mod) to ~6 seconds (batched)
        - More stable: All unsubs complete before any subs start
        - Clearer: Better matches Steam's async queue expectations

        Without proper staging, Steam may queue subscribe before unsubscribe
        completes, resulting in mods subscribed but not downloaded.
        """
        logger.warning(
            f">>> RESUBSCRIBE: Starting for {len(self.pfid_or_pfids)} mod(s)"
        )

        # Register callbacks for all unsub/resub operations
        # These fire asynchronously as Steam processes each operation
        steamworks_interface.steamworks.Workshop.SetItemUnsubscribedCallback(
            self._create_unsub_callback(steamworks_interface)
        )
        steamworks_interface.steamworks.Workshop.SetItemSubscribedCallback(
            self._create_resub_callback(steamworks_interface)
        )
        logger.warning("Callbacks registered for unsub and resub")

        # STAGE 1: Unsubscribe ALL mods
        logger.warning(f">>> STAGE 1: Unsubscribing {len(self.pfid_or_pfids)} mod(s)")
        for idx, pfid in enumerate(self.pfid_or_pfids, 1):
            logger.warning(f"  [{idx}] Unsubscribing: {pfid}")
            steamworks_interface.steamworks.Workshop.UnsubscribeItem(pfid)
            # Small gap between API calls to space them out
            if len(self.pfid_or_pfids) > 1 and idx < len(self.pfid_or_pfids):
                sleep(API_CALL_GAP)

        # STAGE 2: Wait for Steam to uninstall all mod files
        logger.warning(
            f"  Waiting {RESUBSCRIBE_UNSUBSCRIBE_WAIT}s for all unsubscribes to complete..."
        )
        sleep(RESUBSCRIBE_UNSUBSCRIBE_WAIT)

        # STAGE 3: Subscribe ALL mods
        logger.warning(f">>> STAGE 2: Subscribing {len(self.pfid_or_pfids)} mod(s)")
        for idx, pfid in enumerate(self.pfid_or_pfids, 1):
            logger.warning(f"  [{idx}] Subscribing: {pfid}")
            steamworks_interface.steamworks.Workshop.SubscribeItem(pfid)
            # Small gap between API calls to space them out
            if len(self.pfid_or_pfids) > 1 and idx < len(self.pfid_or_pfids):
                sleep(API_CALL_GAP)

        # STAGE 4: Wait for Steam to register all subscriptions
        logger.warning(
            f"  Waiting {RESUBSCRIBE_SUBSCRIBE_WAIT}s for all subscribes to register..."
        )
        sleep(RESUBSCRIBE_SUBSCRIBE_WAIT)

        # STAGE 5: Force download ALL mods with high priority
        logger.warning(
            f">>> STAGE 3: Initiating downloads for {len(self.pfid_or_pfids)} mod(s)"
        )
        for idx, pfid in enumerate(self.pfid_or_pfids, 1):
            try:
                logger.warning(f"  [{idx}] Download: {pfid}")
                # Call DownloadItem to force Steam to queue the mod for download
                # high_priority=True makes Steam skip other queued downloads
                # Note: callback may not fire, but the download is still queued
                steamworks_interface.steamworks.Workshop.DownloadItem(
                    pfid,
                    high_priority=True,
                    callback=self._create_download_callback(steamworks_interface),
                    override_callback=True,
                )
            except Exception as e:
                logger.error(f"Failed to trigger download for {pfid}: {e}")

        logger.warning(">>> All mods queued. Waiting for callbacks...")

    def _handle_subscribe(self, steamworks_interface: SteamworksInterface) -> None:
        """
        Subscribe to mods
        """
        logger.warning(f">>> SUBSCRIBE: Starting for {len(self.pfid_or_pfids)} mod(s)")

        steamworks_interface.steamworks.Workshop.SetItemSubscribedCallback(
            self._create_resub_callback(steamworks_interface)
        )
        logger.warning("Callback registered for subscribe")

        for idx, pfid in enumerate(self.pfid_or_pfids, 1):
            logger.warning(
                f">>> Subscribing to mod {idx}/{len(self.pfid_or_pfids)}: {pfid}"
            )
            steamworks_interface.steamworks.Workshop.SubscribeItem(pfid)

            if len(self.pfid_or_pfids) > 1 and idx < len(self.pfid_or_pfids):
                logger.warning(f"Waiting {self.interval}s before next mod...")
                sleep(self.interval)

        logger.warning(">>> All mods queued. Waiting for callbacks...")

    def _handle_unsubscribe(self, steamworks_interface: SteamworksInterface) -> None:
        """
        Unsubscribe from mods
        """
        logger.warning(
            f">>> UNSUBSCRIBE: Starting for {len(self.pfid_or_pfids)} mod(s)"
        )

        steamworks_interface.steamworks.Workshop.SetItemUnsubscribedCallback(
            self._create_unsub_callback(steamworks_interface)
        )
        logger.warning("Callback registered for unsubscribe")

        for idx, pfid in enumerate(self.pfid_or_pfids, 1):
            logger.warning(
                f">>> Unsubscribing from mod {idx}/{len(self.pfid_or_pfids)}: {pfid}"
            )
            steamworks_interface.steamworks.Workshop.UnsubscribeItem(pfid)

            if len(self.pfid_or_pfids) > 1 and idx < len(self.pfid_or_pfids):
                logger.warning(f"Waiting {self.interval}s before next mod...")
                sleep(self.interval)

        logger.warning(">>> All mods queued. Waiting for callbacks...")

    def _create_unsub_callback(
        self, steamworks_interface: SteamworksInterface
    ) -> Callable[[Any, Any], None]:
        """
        Create unsubscribe callback handler.

        Returns a callable that increments callback count and signals
        completion when all expected callbacks have fired.
        """

        def callback(*args: Any, **kwargs: Any) -> None:
            steamworks_interface.callbacks_count += 1
            result = args[0].result
            pfid = args[0].publishedFileId

            if result == 1:
                logger.warning(f"✓ Unsubscribe succeeded for {pfid}")
            else:
                logger.error(f"✗ Unsubscribe failed for {pfid}: result={result}")

            # Check if all expected callbacks have completed
            if (
                steamworks_interface.multiple_queries
                and steamworks_interface.callbacks_total is not None
                and steamworks_interface.callbacks_count
                >= steamworks_interface.callbacks_total
            ):
                steamworks_interface.end_callbacks = True
            elif not steamworks_interface.multiple_queries:
                steamworks_interface.end_callbacks = True

        return callback

    def _create_resub_callback(
        self, steamworks_interface: SteamworksInterface
    ) -> Callable[[Any, Any], None]:
        """
        Create subscribe callback handler.

        Returns a callable that increments callback count and signals
        completion when all expected callbacks have fired.
        """

        def callback(*args: Any, **kwargs: Any) -> None:
            steamworks_interface.callbacks_count += 1
            result = args[0].result
            pfid = args[0].publishedFileId

            if result == 1:
                logger.warning(f"✓ Subscribe succeeded for {pfid}")
            else:
                logger.error(f"✗ Subscribe failed for {pfid}: result={result}")

            # Check if all expected callbacks have completed
            if (
                steamworks_interface.multiple_queries
                and steamworks_interface.callbacks_total is not None
                and steamworks_interface.callbacks_count
                >= steamworks_interface.callbacks_total
            ):
                steamworks_interface.end_callbacks = True
            elif not steamworks_interface.multiple_queries:
                steamworks_interface.end_callbacks = True

        return callback

    def _create_download_callback(
        self, steamworks_interface: SteamworksInterface
    ) -> Callable[[Any, Any], None]:
        """
        Create download callback handler.

        Returns a callable that increments callback count and signals
        completion when all expected callbacks have fired.

        Note: DownloadItem callbacks are unreliable and may not fire,
        so this is primarily used for logging purposes.
        """

        def callback(*args: Any, **kwargs: Any) -> None:
            steamworks_interface.callbacks_count += 1
            result = args[0].result
            pfid = args[0].publishedFileId

            if result == 1:
                logger.warning(f"✓ Download succeeded for {pfid}")
            else:
                logger.error(f"✗ Download failed for {pfid}: result={result}")

            # Check if all expected callbacks have completed
            if (
                steamworks_interface.multiple_queries
                and steamworks_interface.callbacks_total is not None
                and steamworks_interface.callbacks_count
                >= steamworks_interface.callbacks_total
            ):
                steamworks_interface.end_callbacks = True
            elif not steamworks_interface.multiple_queries:
                steamworks_interface.end_callbacks = True

        return callback


if __name__ == "__main__":
    sys.exit()
