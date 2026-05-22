"""
Steamworks API Worker Thread Module

Provides a QThread-based worker that owns the STEAMWORKS instance lifecycle.
Operations are submitted via a thread-safe queue; results are communicated
back via Qt Signals. The worker auto-unloads the Steamworks API after a
configurable idle timeout to avoid Steam reporting the game as running.

Key classes:
    SteamworksWorker: QThread worker owning STEAMWORKS lifecycle
    SteamworksOperation: Base dataclass for operation submission
    SubscribeOp, UnsubscribeOp, ResubscribeOp: Subscription operations
    AppDependenciesOp: DLC dependency query operation
    ForceDownloadOp: Direct download trigger operation

Reference:
    https://partner.steamgames.com/doc/api/ISteamUGC
    https://github.com/philippj/SteamworksPy
"""

import concurrent.futures
import sys
import threading
import time
from dataclasses import dataclass, field
from os import getcwd
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from loguru import logger
from PySide6.QtCore import QThread, Signal

from app.utils.generic import launch_game_process

# Ensure SteamworksPy module is in Python path when running from interpreter
if "__compiled__" not in globals():
    sys.path.append(str((Path(getcwd()) / "submodules" / "SteamworksPy")))

from steamworks import STEAMWORKS  # type: ignore

# Timing constants for subscription operations (preserved from original)
RESUBSCRIBE_UNSUBSCRIBE_WAIT = 4
RESUBSCRIBE_SUBSCRIBE_WAIT = 2
API_CALL_GAP = 0.5
SUBSCRIBE_UNSUBSCRIBE_INTERVAL = 0.5

# Worker loop interval (seconds) — controls callback pump rate (~10 Hz)
_LOOP_INTERVAL = 0.1


# --- Operation dataclasses ---


@dataclass
class SteamworksOperation:
    """Base class for all operations submitted to the worker."""


@dataclass
class SubscribeOp(SteamworksOperation):
    pfids: list[int] = field(default_factory=list)


@dataclass
class UnsubscribeOp(SteamworksOperation):
    pfids: list[int] = field(default_factory=list)


@dataclass
class ResubscribeOp(SteamworksOperation):
    pfids: list[int] = field(default_factory=list)


@dataclass
class ForceDownloadOp(SteamworksOperation):
    pfids: list[int] = field(default_factory=list)


@dataclass
class GameLaunchOp(SteamworksOperation):
    game_install_path: str = ""
    args: list[str] = field(default_factory=list)


@dataclass
class AppDependenciesOp(SteamworksOperation):
    pfids: list[int] = field(default_factory=list)
    result_future: concurrent.futures.Future[dict[int, Any] | None] = field(
        default_factory=concurrent.futures.Future
    )
    # NOTE: Always pass result_future explicitly via query_app_dependencies().
    # The default_factory exists only to satisfy dataclass field ordering.


# --- Worker thread ---


class SteamworksWorker(QThread):
    """
    QThread worker that owns the STEAMWORKS instance lifecycle.

    Operations are submitted via a thread-safe queue. The worker pumps
    Steamworks callbacks in its run loop and auto-unloads the API after
    an idle timeout (default 15s) to prevent Steam from showing the game
    as running while RimSort is open.

    Signals:
        operation_complete: (op_type: str, success: bool)
        steam_not_running: Emitted when STEAMWORKS.initialize() fails
        steam_operation_failed: (pfid: str, reason: str)
        item_subscribed: (pfid: str)
        item_unsubscribed: (pfid: str)
    """

    operation_complete = Signal(str, bool)
    steam_not_running = Signal()
    steam_operation_failed = Signal(str, str)
    item_subscribed = Signal(str)
    item_unsubscribed = Signal(str)

    def __init__(self, idle_timeout: int = 15, libs_path: str | None = None) -> None:
        super().__init__()
        self._queue: Queue[SteamworksOperation] = Queue()
        self._steamworks: STEAMWORKS | None = None
        self._idle_timeout = idle_timeout
        self._libs_path = libs_path
        self._last_activity = time.monotonic()
        self._pending_callbacks = 0
        self._callback_generation = 0
        self._shutdown_event = threading.Event()

    def run(self) -> None:
        """Main loop: dequeue ops, pump callbacks, check idle timeout."""
        logger.info("SteamworksWorker thread started")
        while not self._shutdown_event.is_set():
            # 1. Check queue for new operations
            try:
                op = self._queue.get(timeout=_LOOP_INTERVAL)
                self._last_activity = time.monotonic()
                self._execute_operation(op)
            except Empty:
                pass

            # 2. Pump callbacks if Steamworks is loaded
            self._pump_callbacks()

            # 3. Check idle timeout (only when no pending work)
            if (
                self._steamworks is not None
                and self._pending_callbacks <= 0
                and self._queue.empty()
                and time.monotonic() - self._last_activity > self._idle_timeout
            ):
                logger.info("Idle timeout reached, unloading Steamworks API")
                self._unload()

        # Drain pending callbacks before final unload (max 5s grace period)
        if self._steamworks is not None:
            if self._pending_callbacks > 0:
                logger.info(
                    f"Draining {self._pending_callbacks} pending callback(s) before shutdown..."
                )
                deadline = time.monotonic() + 5.0
                while self._pending_callbacks > 0 and time.monotonic() < deadline:
                    self._pump_callbacks()
                    time.sleep(_LOOP_INTERVAL)
            self._unload()
        logger.info("SteamworksWorker thread stopped")

    def submit(self, op: SteamworksOperation) -> None:
        """Thread-safe enqueue from any thread."""
        self._queue.put(op)

    def shutdown(self) -> None:
        """Signal shutdown and wait for the thread to finish."""
        logger.info("SteamworksWorker shutdown requested")
        self._shutdown_event.set()
        self.wait(10000)

    def update_idle_timeout(self, timeout: int) -> None:
        self._idle_timeout = timeout

    # --- Convenience methods (submit typed operations) ---

    def subscribe(self, pfids: list[int]) -> None:
        self.submit(SubscribeOp(pfids=pfids))

    def unsubscribe(self, pfids: list[int]) -> None:
        self.submit(UnsubscribeOp(pfids=pfids))

    def resubscribe(self, pfids: list[int]) -> None:
        self.submit(ResubscribeOp(pfids=pfids))

    def force_download(self, pfids: list[int]) -> None:
        self.submit(ForceDownloadOp(pfids=pfids))

    def launch_game(self, game_install_path: str, args: list[str]) -> None:
        self.submit(GameLaunchOp(game_install_path=game_install_path, args=args))

    def query_app_dependencies(
        self, pfids: list[int]
    ) -> concurrent.futures.Future[dict[int, Any] | None]:
        future: concurrent.futures.Future[dict[int, Any] | None] = (
            concurrent.futures.Future()
        )
        self.submit(AppDependenciesOp(pfids=pfids, result_future=future))
        return future

    # --- Query methods (called cross-thread) ---
    # These read _steamworks without synchronization. Safe under CPython's
    # GIL for simple attribute reads; the try/except guards against TOCTOU
    # races if _unload() sets _steamworks to None between the check and call.
    # If PR 7 needs heavy use of these, route through the operation queue.

    def health_check(self) -> bool:
        return self._steamworks is not None and self._steamworks.loaded()

    def get_item_state(self, pfid: int) -> int | None:
        if self._steamworks is None or not self._steamworks.loaded():
            return None
        try:
            return int(self._steamworks.Workshop.GetItemState(pfid))
        except Exception:
            return None

    def get_item_download_info(self, pfid: int) -> dict[str, Any] | None:
        if self._steamworks is None or not self._steamworks.loaded():
            return None
        try:
            return self._steamworks.Workshop.GetItemDownloadInfo(pfid)  # type: ignore[no-any-return]
        except Exception:
            return None

    # --- Internal methods (run on worker thread only) ---

    def _ensure_initialized(self) -> bool:
        if self._steamworks is not None and self._steamworks.loaded():
            return True

        try:
            self._steamworks = STEAMWORKS(_libs=self._libs_path)
            self._steamworks.initialize()
            logger.info("Steamworks API initialized")
            return True
        except Exception as e:
            logger.warning(
                f"Unable to initialize Steamworks API: {e.__class__.__name__}: {e}"
            )
            self.steam_not_running.emit()
            self._steamworks = None
            return False

    def _unload(self) -> None:
        if self._steamworks is not None:
            self._callback_generation += 1
            try:
                self._steamworks.unload()
            except Exception as e:
                logger.warning(f"Error unloading Steamworks: {e}")
            self._steamworks = None
            self._pending_callbacks = 0
            logger.info("Steamworks API unloaded")

    def _pump_callbacks(self) -> None:
        if self._steamworks is not None and self._steamworks.loaded():
            try:
                self._steamworks.run_callbacks()
            except Exception as e:
                logger.debug(f"run_callbacks error: {e}")

    def _wait_for_pending_callbacks(self, timeout: float) -> bool:
        """Wait for _pending_callbacks to reach zero while pumping callbacks.

        :return: True if all callbacks completed, False if timed out.
        """
        deadline = time.monotonic() + timeout
        while (
            self._pending_callbacks > 0
            and not self._shutdown_event.is_set()
            and time.monotonic() < deadline
        ):
            self._pump_callbacks()
            time.sleep(_LOOP_INTERVAL)
        if self._pending_callbacks > 0:
            logger.warning(
                f"Callback wait timed out with {self._pending_callbacks} pending"
            )
            return False
        return True

    def _wait_with_callbacks(self, duration: float) -> None:
        """Wait for a duration while continuing to pump callbacks."""
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline and not self._shutdown_event.is_set():
            self._pump_callbacks()
            time.sleep(_LOOP_INTERVAL)

    def _execute_operation(self, op: SteamworksOperation) -> None:
        if isinstance(op, SubscribeOp):
            self._handle_subscribe(op)
        elif isinstance(op, UnsubscribeOp):
            self._handle_unsubscribe(op)
        elif isinstance(op, ResubscribeOp):
            self._handle_resubscribe(op)
        elif isinstance(op, ForceDownloadOp):
            self._handle_force_download(op)
        elif isinstance(op, GameLaunchOp):
            self._handle_game_launch(op)
        elif isinstance(op, AppDependenciesOp):
            self._handle_app_dependencies(op)
        else:
            logger.error(f"Unknown operation type: {type(op)}")

    def _handle_subscribe(self, op: SubscribeOp) -> None:
        if not op.pfids:
            self.operation_complete.emit("subscribe", True)
            return
        logger.info(f"SUBSCRIBE: {len(op.pfids)} mod(s)")
        if not self._ensure_initialized():
            self.operation_complete.emit("subscribe", False)
            return

        self._callback_generation += 1
        gen = self._callback_generation
        self._pending_callbacks = len(op.pfids)

        def on_subscribed(*args: Any, **kwargs: Any) -> None:
            if gen != self._callback_generation:
                return
            self._pending_callbacks = max(0, self._pending_callbacks - 1)
            self._last_activity = time.monotonic()
            try:
                pfid = args[0].publishedFileId
                result = args[0].result
                if result == 1:
                    logger.info(f"Subscribe succeeded for {pfid}")
                    self.item_subscribed.emit(str(pfid))
                else:
                    logger.error(f"Subscribe failed for {pfid}: result={result}")
                    self.steam_operation_failed.emit(str(pfid), "subscribe failed")
            except Exception as e:
                logger.error(f"Error in subscribe callback: {e}")

        self._steamworks.Workshop.SetItemSubscribedCallback(on_subscribed)

        for idx, pfid in enumerate(op.pfids):
            logger.debug(f"SubscribeItem({pfid})")
            self._steamworks.Workshop.SubscribeItem(pfid)
            if idx < len(op.pfids) - 1:
                time.sleep(SUBSCRIBE_UNSUBSCRIBE_INTERVAL)

        success = self._wait_for_pending_callbacks(timeout=30)
        self.operation_complete.emit("subscribe", success)

    def _handle_unsubscribe(self, op: UnsubscribeOp) -> None:
        if not op.pfids:
            self.operation_complete.emit("unsubscribe", True)
            return
        logger.info(f"UNSUBSCRIBE: {len(op.pfids)} mod(s)")
        if not self._ensure_initialized():
            self.operation_complete.emit("unsubscribe", False)
            return

        self._callback_generation += 1
        gen = self._callback_generation
        self._pending_callbacks = len(op.pfids)

        def on_unsubscribed(*args: Any, **kwargs: Any) -> None:
            if gen != self._callback_generation:
                return
            self._pending_callbacks = max(0, self._pending_callbacks - 1)
            self._last_activity = time.monotonic()
            try:
                pfid = args[0].publishedFileId
                result = args[0].result
                if result == 1:
                    logger.info(f"Unsubscribe succeeded for {pfid}")
                    self.item_unsubscribed.emit(str(pfid))
                else:
                    logger.error(f"Unsubscribe failed for {pfid}: result={result}")
                    self.steam_operation_failed.emit(str(pfid), "unsubscribe failed")
            except Exception as e:
                logger.error(f"Error in unsubscribe callback: {e}")

        self._steamworks.Workshop.SetItemUnsubscribedCallback(on_unsubscribed)

        for idx, pfid in enumerate(op.pfids):
            logger.debug(f"UnsubscribeItem({pfid})")
            self._steamworks.Workshop.UnsubscribeItem(pfid)
            if idx < len(op.pfids) - 1:
                time.sleep(SUBSCRIBE_UNSUBSCRIBE_INTERVAL)

        success = self._wait_for_pending_callbacks(timeout=30)
        self.operation_complete.emit("unsubscribe", success)

    def _handle_resubscribe(self, op: ResubscribeOp) -> None:
        """
        Batched resubscribe preserving the timing from PR #1719:
        Stage 1: UnsubscribeItem all → Stage 2: wait 4s →
        Stage 3: SubscribeItem all → Stage 4: wait 2s →
        Stage 5: DownloadItem all (if available)
        """
        if not op.pfids:
            self.operation_complete.emit("resubscribe", True)
            return
        logger.info(f"RESUBSCRIBE: {len(op.pfids)} mod(s)")
        if not self._ensure_initialized():
            self.operation_complete.emit("resubscribe", False)
            return

        # 2 callbacks per pfid: 1 unsub + 1 sub (download callbacks unreliable)
        self._callback_generation += 1
        gen = self._callback_generation
        self._pending_callbacks = len(op.pfids) * 2

        def on_unsubscribed(*args: Any, **kwargs: Any) -> None:
            if gen != self._callback_generation:
                return
            self._pending_callbacks = max(0, self._pending_callbacks - 1)
            self._last_activity = time.monotonic()
            try:
                pfid = args[0].publishedFileId
                result = args[0].result
                if result == 1:
                    logger.info(f"Resubscribe unsub succeeded for {pfid}")
                else:
                    logger.error(
                        f"Resubscribe unsub failed for {pfid}: result={result}"
                    )
                    self.steam_operation_failed.emit(
                        str(pfid), "resubscribe unsub failed"
                    )
            except Exception as e:
                logger.error(f"Error in resubscribe unsub callback: {e}")

        def on_subscribed(*args: Any, **kwargs: Any) -> None:
            if gen != self._callback_generation:
                return
            self._pending_callbacks = max(0, self._pending_callbacks - 1)
            self._last_activity = time.monotonic()
            try:
                pfid = args[0].publishedFileId
                result = args[0].result
                if result == 1:
                    logger.info(f"Resubscribe sub succeeded for {pfid}")
                    self.item_subscribed.emit(str(pfid))
                else:
                    logger.error(f"Resubscribe sub failed for {pfid}: result={result}")
                    self.steam_operation_failed.emit(
                        str(pfid), "resubscribe sub failed"
                    )
            except Exception as e:
                logger.error(f"Error in resubscribe sub callback: {e}")

        self._steamworks.Workshop.SetItemUnsubscribedCallback(on_unsubscribed)
        self._steamworks.Workshop.SetItemSubscribedCallback(on_subscribed)

        # Stage 1: Unsubscribe ALL
        logger.info(f"RESUBSCRIBE Stage 1: Unsubscribing {len(op.pfids)} mod(s)")
        for idx, pfid in enumerate(op.pfids):
            self._steamworks.Workshop.UnsubscribeItem(pfid)
            if idx < len(op.pfids) - 1:
                time.sleep(API_CALL_GAP)

        # Stage 2: Wait for Steam to uninstall files
        logger.info(f"RESUBSCRIBE Stage 2: Waiting {RESUBSCRIBE_UNSUBSCRIBE_WAIT}s")
        self._wait_with_callbacks(RESUBSCRIBE_UNSUBSCRIBE_WAIT)

        # Stage 3: Subscribe ALL
        logger.info(f"RESUBSCRIBE Stage 3: Subscribing {len(op.pfids)} mod(s)")
        for idx, pfid in enumerate(op.pfids):
            self._steamworks.Workshop.SubscribeItem(pfid)
            if idx < len(op.pfids) - 1:
                time.sleep(API_CALL_GAP)

        # Stage 4: Wait for Steam to register subscriptions
        logger.info(f"RESUBSCRIBE Stage 4: Waiting {RESUBSCRIBE_SUBSCRIBE_WAIT}s")
        self._wait_with_callbacks(RESUBSCRIBE_SUBSCRIBE_WAIT)

        # Stage 5: Force download ALL (preserving PR #1918 hasattr guard)
        logger.info(f"RESUBSCRIBE Stage 5: Downloading {len(op.pfids)} mod(s)")
        if hasattr(self._steamworks.Workshop, "DownloadItem"):
            for pfid in op.pfids:
                try:
                    self._steamworks.Workshop.DownloadItem(
                        pfid,
                        high_priority=True,
                        callback=lambda *a, **kw: None,
                        override_callback=True,
                    )
                except Exception as e:
                    logger.error(f"Failed to trigger download for {pfid}: {e}")
        else:
            logger.warning(
                "DownloadItem skipped: not supported by SteamworksPy library."
            )

        success = self._wait_for_pending_callbacks(timeout=60)
        self.operation_complete.emit("resubscribe", success)

    def _handle_force_download(self, op: ForceDownloadOp) -> None:
        if not op.pfids:
            self.operation_complete.emit("force_download", True)
            return
        logger.info(f"FORCE DOWNLOAD: {len(op.pfids)} mod(s)")
        if not self._ensure_initialized():
            self.operation_complete.emit("force_download", False)
            return

        if not hasattr(self._steamworks.Workshop, "DownloadItem"):
            logger.warning("DownloadItem not supported by SteamworksPy library.")
            self.operation_complete.emit("force_download", False)
            return

        for pfid in op.pfids:
            try:
                self._steamworks.Workshop.DownloadItem(
                    pfid,
                    high_priority=True,
                    callback=lambda *a, **kw: None,
                    override_callback=True,
                )
            except Exception as e:
                logger.error(f"Failed to trigger download for {pfid}: {e}")
                self.steam_operation_failed.emit(str(pfid), f"download failed: {e}")

        # No callback counting — download callbacks are unreliable
        self.operation_complete.emit("force_download", True)

    def _handle_game_launch(self, op: GameLaunchOp) -> None:
        """Initialize Steamworks for Steam overlay, launch the game, then unload."""
        logger.info("GAME LAUNCH: initializing Steamworks before launch")
        self._ensure_initialized()
        launch_game_process(game_install_path=Path(op.game_install_path), args=op.args)
        # Unload immediately — don't hold the handle while the game runs
        self._unload()
        self.operation_complete.emit("game_launch", True)

    def _handle_app_dependencies(self, op: AppDependenciesOp) -> None:
        if not op.pfids:
            op.result_future.set_result({})
            return
        logger.info(f"APP DEPENDENCIES: querying {len(op.pfids)} mod(s)")
        if not self._ensure_initialized():
            op.result_future.set_result(None)
            return

        self._callback_generation += 1
        gen = self._callback_generation
        self._pending_callbacks = len(op.pfids)
        results: dict[int, Any] = {}

        def on_result(*args: Any, **kwargs: Any) -> None:
            if gen != self._callback_generation:
                return
            self._pending_callbacks = max(0, self._pending_callbacks - 1)
            self._last_activity = time.monotonic()
            try:
                pfid = args[0].publishedFileId
                app_dependencies_list = args[0].get_app_dependencies_list()
                logger.debug(
                    f"AppDependencies callback: pfid={pfid}, "
                    f"deps={app_dependencies_list}"
                )
                if len(app_dependencies_list) > 0:
                    results[pfid] = app_dependencies_list
            except Exception as e:
                logger.error(f"Error in AppDependencies callback: {e}")

        self._steamworks.Workshop.SetGetAppDependenciesResultCallback(on_result)

        for idx, pfid in enumerate(op.pfids):
            logger.debug(f"GetAppDependencies({pfid})")
            self._steamworks.Workshop.GetAppDependencies(pfid)
            if idx < len(op.pfids) - 1:
                time.sleep(1)

        self._wait_for_pending_callbacks(timeout=60)
        op.result_future.set_result(results)
