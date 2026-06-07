"""
Steamworks API Wrapper Module

Provides Python wrappers for Steamworks API interactions including:
- Workshop mod subscription/unsubscription (ISteamUGC)
- Game launching with Steamworks integration
- App dependency queries
- Callback-based async event handling

Key features:
- Proper sequencing for resubscribe operations (unsub -> wait -> sub -> download)
- Sequential processing for subscribe/unsubscribe operations
- Thread-safe callback handling with timeout management
- Comprehensive logging for debugging and monitoring

Usage:
    - SteamworksSubscriptionHandler: Handle mod subscription operations
    - SteamworksGameLaunch: Launch RimWorld with Steamworks initialized
    - SteamworksAppDependenciesQuery: Query mod dependencies

Reference:
    https://partner.steamgames.com/doc/api/ISteamUGC
"""

import sys
from multiprocessing import Process
from pathlib import Path
from threading import Thread
from time import sleep
from typing import Any, Callable, Union

from loguru import logger

from app.utils.generic import launch_game_process
from app.utils.steam.steamworks import bindings
from app.utils.steam.steamworks.callback_tracker import CallbackTracker

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

    Manages SDK initialization, callback threading, and lifecycle.
    """

    def __init__(
        self,
        callbacks: bool,
        callbacks_total: int | None = None,
    ) -> None:
        logger.info("SteamworksInterface initializing...")
        self.steam_not_running = False
        self._shutdown_done = False
        self.get_app_deps_query_result: dict[int, Any] = {}
        self._tracker = CallbackTracker(expected=callbacks_total if callbacks else 0)

        if bindings._lib is None:
            logger.warning("rimsort_steam native library not available")
            self.steam_not_running = True
            return

        init_result = bindings._lib.RS_SteamAPI_Init()
        if init_result != 0:
            error_messages = {
                1: "Steamworks API initialization failed",
                2: "Steam client not found -- is Steam installed?",
                3: "No Steam connection -- is Steam running and are you logged in?",
            }
            msg = error_messages.get(init_result, f"Unknown init error: {init_result}")
            logger.warning(f"Unable to initialize Steamworks API: {msg}")
            self.steam_not_running = True
            return

        if callbacks:
            logger.debug("Starting callback thread")
            self._callback_thread = self._daemon()
            self._callback_thread.start()

    def _run_callbacks_loop(self) -> None:
        logger.debug("Callback loop started")
        while not self._tracker.is_done:
            if bindings._lib is not None:
                bindings._lib.RS_SteamAPI_RunCallbacks()
            sleep(0.1)
        logger.info(f"{self._tracker.count} callback(s) received. Ending thread...")

    def _daemon(self) -> Thread:
        return Thread(target=self._run_callbacks_loop, daemon=True)

    def wait_for_callbacks(self, timeout: int) -> bool:
        """Wait for all expected callbacks. Returns True if completed, False on timeout."""
        logger.debug(f"Waiting {timeout} seconds for Steamworks API callbacks...")
        completed = self._tracker.wait(timeout=float(timeout))
        if not completed:
            logger.warning(
                f"Timed out after {timeout}s ({self._tracker.count} callbacks received)"
            )
            self._tracker.cancel()
        return completed

    def shutdown(self) -> None:
        """Shut down the Steamworks API and stop callback thread."""
        if self._shutdown_done:
            return
        self._shutdown_done = True
        if hasattr(self, "_callback_thread") and self._callback_thread.is_alive():
            self._tracker.cancel()
            self._callback_thread.join(timeout=5)
        if bindings._lib is not None and not self.steam_not_running:
            bindings._lib.RS_SteamAPI_Shutdown()

    def cb_app_dependencies_result(self, *args: Any, **kwargs: Any) -> None:
        self._tracker.record()
        logger.debug(f"GetAppDependencies callback: {args}, {kwargs}")
        logger.debug(f"result: {args[0].result}")
        pfid = args[0].published_file_id
        logger.debug(f"published_file_id: {pfid}")
        app_dependencies_list = args[0].get_app_dependencies_list()
        logger.debug(f"app_dependencies_list: {app_dependencies_list}")
        if len(app_dependencies_list) > 0:
            self.get_app_deps_query_result[pfid] = app_dependencies_list


class SteamworksAppDependenciesQuery:
    def __init__(
        self,
        pfid_or_pfids: Union[int, list[int]],
        interval: int = 1,
    ) -> None:
        self.interval = interval
        self.pfid_or_pfids = pfid_or_pfids

    def run(self) -> None | dict[int, Any]:
        """
        Query PublishedFileIDs for AppID dependency data.

        :param pfid_or_pfids: is an int that corresponds with a subscribed Steam mod's PublishedFileId
                            OR is a list of int that corresponds with multiple Steam mod PublishedFileIds
        :param interval: time in seconds to sleep between multiple subsequent API calls
        """
        logger.info(
            f"Creating SteamworksInterface and passing PublishedFileID(s) {self.pfid_or_pfids}"
        )
        # If the chunk passed is a single int, convert it into a list
        if isinstance(self.pfid_or_pfids, int):
            self.pfid_or_pfids = [self.pfid_or_pfids]
        # Create our Steamworks interface and initialize Steamworks API
        interface = SteamworksInterface(
            callbacks=True, callbacks_total=len(self.pfid_or_pfids)
        )
        if not interface.steam_not_running:
            # Register callback and issue queries
            if bindings._lib is not None:
                bindings._lib.RS_Workshop_SetGetAppDependenciesResultCallback(
                    bindings.AppDepsCallback(interface.cb_app_dependencies_result)
                )
            for pfid in self.pfid_or_pfids:
                logger.debug(f"ISteamUGC/GetAppDependencies Query: {pfid}")
                if bindings._lib is not None:
                    bindings._lib.RS_Workshop_GetAppDependencies(pfid)
                # Sleep for the interval if we have more than one pfid to action on
                if len(self.pfid_or_pfids) > 1:
                    sleep(self.interval)
            # Patience, but don't wait forever
            interface.wait_for_callbacks(timeout=60)
            # Grab the data and return it
            logger.warning(
                f"Returning {len(interface.get_app_deps_query_result.keys())} results..."
            )
            result = interface.get_app_deps_query_result
            interface.shutdown()
            return result
        else:
            interface.shutdown()

        return None


class SteamworksGameLaunch(Process):
    def __init__(self, game_install_path: str, run_args: str = "") -> None:
        Process.__init__(self)
        self.game_install_path = game_install_path
        self.run_args = run_args

    def run(self) -> None:
        """
        Handle SW game launch; instructions received from connected signals.

        :param game_install_path: is a string path to the game folder
        :param run_args: is a string representing the args to pass to the generated executable path
        """
        logger.info("Creating SteamworksInterface and launching game executable")
        # Try to initialize the SteamWorks API, but allow game to launch if Steam not found
        steamworks_interface = SteamworksInterface(callbacks=False)

        # Launch the game
        launch_game_process(
            game_install_path=Path(self.game_install_path),
            run_args=self.run_args,
        )
        # If we had an API initialization, try to shut it down
        steamworks_interface.shutdown()


class SteamworksSubscriptionHandler(Process):
    """
    Handles Steam Workshop mod subscription operations.

    Supports three operations:
    - "subscribe": Subscribe to mods (ISteamUGC::SubscribeItem)
    - "unsubscribe": Unsubscribe from mods (ISteamUGC::UnsubscribeItem)
    - "resubscribe": Unsub then resub with proper delays (forces Steam to re-download)

    Resubscribe timing is critical for fixing GitHub issue #1460 (missing mods):
    1. UnsubscribeItem() -> Steam marks as unsubscribed
    2. Wait 4 seconds -> Steam uninstalls mod files
    3. SubscribeItem() -> Steam marks as subscribed
    4. Wait 2 seconds -> Steam registers subscription
    5. DownloadItem(high_priority=True) -> Forces Steam to queue re-download

    Without proper spacing, Steam can queue operations in wrong order,
    resulting in mods being subscribed but not downloaded.

    Uses callback-based async event handling with configurable timeouts.

    Attributes:
        action (str): Operation to perform
        pfid_or_pfids (list[int]): Published file IDs (Steam Workshop mod IDs)
        interval (float): Delay in seconds between processing multiple mods
    """

    def __init__(
        self,
        action: str,
        pfid_or_pfids: Union[int, list[int]],
        interval: float = SUBSCRIBE_UNSUBSCRIBE_INTERVAL,
    ):
        """
        Initialize subscription handler.

        :param action: Operation type ("subscribe", "unsubscribe", or "resubscribe")
        :param pfid_or_pfids: Single mod ID or list of mod IDs to process
        :param interval: Seconds to wait between operations (only used for subscribe/unsubscribe)
        """
        Process.__init__(self)
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
            f"SteamworksSubscriptionHandler START: action={self.action}, mods={len(self.pfid_or_pfids)}"
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
            callbacks=True, callbacks_total=callbacks_total
        )

        if steamworks_interface.steam_not_running:
            logger.error("Steam is not running. Aborting subscription handler.")
            steamworks_interface.shutdown()
            return

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
            steamworks_interface.wait_for_callbacks(timeout=timeout)
            logger.warning(
                f"All callbacks completed ({steamworks_interface._tracker.count}/{callbacks_total})"
            )

        except Exception as e:
            logger.error(
                f"Error during subscription action {self.action}: {e}",
                exc_info=True,
            )
        finally:
            # Cleanup
            logger.warning(
                "SteamworksSubscriptionHandler END: Shutting down Steamworks"
            )
            steamworks_interface.shutdown()

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
        logger.warning(f"RESUBSCRIBE: Starting for {len(self.pfid_or_pfids)} mod(s)")

        if bindings._lib is None:
            logger.error("Cannot resubscribe: native library not available")
            return

        # Register callbacks for all unsub/resub operations
        # These fire asynchronously as Steam processes each operation
        unsub_cb = self._create_callback(
            "Unsubscribe", tracker=steamworks_interface._tracker
        )
        sub_cb = self._create_callback(
            "Subscribe", tracker=steamworks_interface._tracker
        )
        dl_cb = self._create_callback("Download", tracker=None)

        bindings._lib.RS_Workshop_SetItemUnsubscribedCallback(
            bindings.SubscriptionCallback(unsub_cb)
        )
        bindings._lib.RS_Workshop_SetItemSubscribedCallback(
            bindings.SubscriptionCallback(sub_cb)
        )
        bindings._lib.RS_Workshop_SetDownloadItemResultCallback(
            bindings.DownloadItemResultCallback(dl_cb)
        )
        logger.warning("Callbacks registered for unsub, resub, and download")

        # STAGE 1: Unsubscribe ALL mods
        logger.warning(f"STAGE 1: Unsubscribing {len(self.pfid_or_pfids)} mod(s)")
        for idx, pfid in enumerate(self.pfid_or_pfids, 1):
            logger.warning(f"  [{idx}] Unsubscribing: {pfid}")
            bindings._lib.RS_Workshop_UnsubscribeItem(pfid)
            # Small gap between API calls to space them out
            if len(self.pfid_or_pfids) > 1 and idx < len(self.pfid_or_pfids):
                sleep(API_CALL_GAP)

        # STAGE 2: Wait for Steam to uninstall all mod files
        logger.warning(
            f"  Waiting {RESUBSCRIBE_UNSUBSCRIBE_WAIT}s for all unsubscribes to complete..."
        )
        sleep(RESUBSCRIBE_UNSUBSCRIBE_WAIT)

        # STAGE 3: Subscribe ALL mods
        logger.warning(f"STAGE 2: Subscribing {len(self.pfid_or_pfids)} mod(s)")
        for idx, pfid in enumerate(self.pfid_or_pfids, 1):
            logger.warning(f"  [{idx}] Subscribing: {pfid}")
            bindings._lib.RS_Workshop_SubscribeItem(pfid)
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
            f"STAGE 3: Initiating downloads for {len(self.pfid_or_pfids)} mod(s)"
        )
        for idx, pfid in enumerate(self.pfid_or_pfids, 1):
            try:
                logger.warning(f"  [{idx}] Download: {pfid}")
                bindings._lib.RS_Workshop_DownloadItem(pfid, True)
            except Exception as e:
                logger.error(f"Failed to trigger download for {pfid}: {e}")

        logger.warning("All mods queued. Waiting for callbacks...")

    def _handle_subscribe(self, steamworks_interface: SteamworksInterface) -> None:
        """Subscribe to mods."""
        logger.warning(f"SUBSCRIBE: Starting for {len(self.pfid_or_pfids)} mod(s)")

        if bindings._lib is None:
            logger.error("Cannot subscribe: native library not available")
            return

        sub_cb = self._create_callback(
            "Subscribe", tracker=steamworks_interface._tracker
        )
        bindings._lib.RS_Workshop_SetItemSubscribedCallback(
            bindings.SubscriptionCallback(sub_cb)
        )
        logger.warning("Callback registered for subscribe")

        for idx, pfid in enumerate(self.pfid_or_pfids, 1):
            logger.warning(
                f"Subscribing to mod {idx}/{len(self.pfid_or_pfids)}: {pfid}"
            )
            bindings._lib.RS_Workshop_SubscribeItem(pfid)

            if len(self.pfid_or_pfids) > 1 and idx < len(self.pfid_or_pfids):
                logger.warning(f"Waiting {self.interval}s before next mod...")
                sleep(self.interval)

        logger.warning("All mods queued. Waiting for callbacks...")

    def _handle_unsubscribe(self, steamworks_interface: SteamworksInterface) -> None:
        """Unsubscribe from mods."""
        logger.warning(f"UNSUBSCRIBE: Starting for {len(self.pfid_or_pfids)} mod(s)")

        if bindings._lib is None:
            logger.error("Cannot unsubscribe: native library not available")
            return

        unsub_cb = self._create_callback(
            "Unsubscribe", tracker=steamworks_interface._tracker
        )
        bindings._lib.RS_Workshop_SetItemUnsubscribedCallback(
            bindings.SubscriptionCallback(unsub_cb)
        )
        logger.warning("Callback registered for unsubscribe")

        for idx, pfid in enumerate(self.pfid_or_pfids, 1):
            logger.warning(
                f"Unsubscribing from mod {idx}/{len(self.pfid_or_pfids)}: {pfid}"
            )
            bindings._lib.RS_Workshop_UnsubscribeItem(pfid)

            if len(self.pfid_or_pfids) > 1 and idx < len(self.pfid_or_pfids):
                logger.warning(f"Waiting {self.interval}s before next mod...")
                sleep(self.interval)

        logger.warning("All mods queued. Waiting for callbacks...")

    @staticmethod
    def _create_callback(
        label: str, tracker: CallbackTracker | None = None
    ) -> Callable[[Any], None]:
        def callback(result: Any) -> None:
            pfid = result.published_file_id
            if result.result == 1:
                logger.warning(f"{label} succeeded for {pfid}")
            else:
                logger.error(f"{label} failed for {pfid}: result={result.result}")
            if tracker is not None:
                tracker.record()

        return callback


if __name__ == "__main__":
    sys.exit()
