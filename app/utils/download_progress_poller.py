"""
Download progress polling thread for real-time Steam Workshop download tracking.

This module provides a background thread that continuously polls GetItemDownloadInfo()
for active downloads, providing real-time progress updates without blocking the UI.
"""

from threading import Event, Thread
from typing import Optional

from loguru import logger

from app.models.download_state import DownloadItem, DownloadStatus
from app.utils.download_tracker import DownloadTracker
from app.utils.steam.steamworks.wrapper import SteamworksInterface


def _check_queued_item(
    steamworks: SteamworksInterface, tracker: DownloadTracker, item: DownloadItem
) -> None:
    """
    Check if queued item is already installed or has started downloading.

    :param steamworks: SteamworksInterface instance
    :type steamworks: SteamworksInterface
    :param tracker: DownloadTracker instance
    :type tracker: DownloadTracker
    :param item: Download item to check
    :type item: DownloadItem
    :return: None
    """
    # Check if already installed (skip download)
    install_info = steamworks.steamworks.Workshop.GetItemInstallInfo(item.pfid)
    if install_info and install_info.get("timestamp"):
        logger.info(f"Queued item {item.pfid} already installed, marking complete")
        tracker.update_item_status(item.pfid, DownloadStatus.COMPLETED)
        return

    # Check if download started
    download_info = steamworks.steamworks.Workshop.GetItemDownloadInfo(item.pfid)
    if download_info:
        bytes_downloaded = download_info.get("downloaded", 0)
        bytes_total = download_info.get("total", 0)

        if bytes_total > 0:
            # Download started! Update progress (auto-transitions to DOWNLOADING)
            tracker.update_item_progress(item.pfid, bytes_downloaded, bytes_total)


def _check_unsubscribing_item(
    steamworks: SteamworksInterface, tracker: DownloadTracker, item: DownloadItem
) -> None:
    """
    Verify unsubscribe operation completed for resubscribe workflow.

    :param steamworks: SteamworksInterface instance
    :type steamworks: SteamworksInterface
    :param tracker: DownloadTracker instance
    :type tracker: DownloadTracker
    :param item: Download item to check
    :type item: DownloadItem
    :return: None
    """
    # For resubscribe operations, we just wait for the subscription action to complete
    # The actual transition to SUBSCRIBING is handled by the resubscribe_to_mods workflow
    # We mainly log here for visibility
    logger.debug(f"Item {item.pfid} is unsubscribing (part of resubscribe workflow)")

    # Could optionally check GetItemState() here, but the subscription callback
    # will handle the transition. This is mainly for timeout detection in future.


def _check_downloading_item(
    steamworks: SteamworksInterface, tracker: DownloadTracker, item: DownloadItem
) -> None:
    """
    Check download progress for subscribing/downloading items.

    This is the existing logic, extracted into a helper function.

    :param steamworks: SteamworksInterface instance
    :type steamworks: SteamworksInterface
    :param tracker: DownloadTracker instance
    :type tracker: DownloadTracker
    :param item: Download item to check
    :type item: DownloadItem
    :return: None
    """
    # Query download info
    download_info = steamworks.steamworks.Workshop.GetItemDownloadInfo(item.pfid)

    if download_info:
        bytes_downloaded = download_info.get("downloaded", 0)
        bytes_total = download_info.get("total", 0)

        # Update progress
        tracker.update_item_progress(
            pfid=item.pfid,
            bytes_downloaded=bytes_downloaded,
            bytes_total=bytes_total,
        )

        # If near completion (>90%), proactively check if already installed
        if bytes_total > 0 and bytes_downloaded / bytes_total > 0.90:
            install_info = steamworks.steamworks.Workshop.GetItemInstallInfo(item.pfid)
            if install_info and install_info.get("timestamp"):
                logger.debug(
                    f"Detected installed mod at {int(bytes_downloaded / bytes_total * 100)}% progress: {item.pfid}"
                )
                if item.status != DownloadStatus.COMPLETED:
                    tracker.update_item_status(item.pfid, DownloadStatus.COMPLETED)
    else:
        # No download info - might be queued or installing
        install_info = steamworks.steamworks.Workshop.GetItemInstallInfo(item.pfid)
        if install_info and install_info.get("timestamp"):
            if item.status != DownloadStatus.COMPLETED:
                tracker.update_item_status(item.pfid, DownloadStatus.COMPLETED)


def _check_installing_item(
    steamworks: SteamworksInterface, tracker: DownloadTracker, item: DownloadItem
) -> None:
    """
    Verify installation completion for items in INSTALLING status.

    :param steamworks: SteamworksInterface instance
    :type steamworks: SteamworksInterface
    :param tracker: DownloadTracker instance
    :type tracker: DownloadTracker
    :param item: Download item to check
    :type item: DownloadItem
    :return: None
    """
    install_info = steamworks.steamworks.Workshop.GetItemInstallInfo(item.pfid)

    if install_info and install_info.get("timestamp"):
        # Installation complete!
        logger.debug(f"Installation verified for pfid {item.pfid}")
        if item.status != DownloadStatus.COMPLETED:
            tracker.update_item_status(item.pfid, DownloadStatus.COMPLETED)
    else:
        # Still installing, log for visibility
        logger.debug(f"Item {item.pfid} still installing...")


class DownloadProgressPoller:
    """
    Background thread that polls GetItemDownloadInfo() for active downloads.

    This complements ItemInstalled_t callbacks by providing real-time progress
    updates during downloads. Runs as a daemon thread that can be started and
    stopped as needed.
    """

    _instance: Optional["DownloadProgressPoller"] = None

    def __new__(cls) -> "DownloadProgressPoller":
        """
        Create or return singleton instance.

        :return: The singleton instance
        :rtype: DownloadProgressPoller
        """
        if cls._instance is None:
            cls._instance = super(DownloadProgressPoller, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the poller."""
        if hasattr(self, "initialized"):
            return

        self._thread: Optional[Thread] = None
        self._stop_event = Event()
        self._poll_interval = (
            2.0  # Poll every 2 seconds (less aggressive to avoid Steam IPC timeouts)
        )

        self.initialized = True
        logger.info("DownloadProgressPoller initialized")

    def start(self) -> None:
        """
        Start the polling thread.

        :return: None
        """
        if self._thread and self._thread.is_alive():
            logger.warning("DownloadProgressPoller already running")
            return

        self._stop_event.clear()
        self._thread = Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("DownloadProgressPoller started")

    def stop(self) -> None:
        """
        Stop the polling thread.

        :return: None
        """
        if not self._thread or not self._thread.is_alive():
            return

        self._stop_event.set()
        self._thread.join(timeout=5)
        logger.info("DownloadProgressPoller stopped")

    def _poll_loop(self) -> None:
        """
        Main polling loop (runs in background thread).

        Continuously checks active downloads and updates their progress
        via DownloadTracker.

        :return: None
        """
        tracker = DownloadTracker()
        steamworks = SteamworksInterface.instance()

        while not self._stop_event.is_set():
            try:
                # Skip if Steam not running
                if steamworks.steam_not_running or not steamworks.steamworks.loaded():
                    logger.debug("[POLLER] Steam not loaded, skipping poll")
                    self._stop_event.wait(self._poll_interval)
                    continue

                # Get all active batches
                active_batches = tracker.get_active_batches()
                if active_batches:
                    logger.debug(
                        f"[POLLER] Found {len(active_batches)} active batch(es)"
                    )

                for batch in active_batches:
                    for item in batch.active_items:
                        # Poll items that are in non-terminal states
                        if item.status not in {
                            DownloadStatus.QUEUED,
                            DownloadStatus.UNSUBSCRIBING,
                            DownloadStatus.SUBSCRIBING,
                            DownloadStatus.DOWNLOADING,
                            DownloadStatus.INSTALLING,
                        }:
                            continue

                        try:
                            # Dispatch to appropriate status checker
                            if item.status == DownloadStatus.QUEUED:
                                _check_queued_item(steamworks, tracker, item)
                            elif item.status == DownloadStatus.UNSUBSCRIBING:
                                _check_unsubscribing_item(steamworks, tracker, item)
                            elif item.status in {
                                DownloadStatus.SUBSCRIBING,
                                DownloadStatus.DOWNLOADING,
                            }:
                                _check_downloading_item(steamworks, tracker, item)
                            elif item.status == DownloadStatus.INSTALLING:
                                _check_installing_item(steamworks, tracker, item)

                        except Exception as e:
                            logger.error(
                                f"Error checking status for pfid {item.pfid} ({item.status}): {e}"
                            )

            except Exception as e:
                logger.error(f"Error in download progress poller: {e}")

            # Sleep before next poll
            self._stop_event.wait(self._poll_interval)
