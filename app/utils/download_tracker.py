"""
Download tracking singleton for managing Steam Workshop download operations.

This module provides a thread-safe singleton that tracks the state of all Steam
Workshop subscription operations, replacing ACF file polling with event-driven
state management.
"""

from datetime import datetime
from threading import RLock
from typing import Optional
from uuid import uuid4

from loguru import logger

from app.models.download_state import DownloadBatch, DownloadItem, DownloadStatus
from app.utils.event_bus import EventBus


class DownloadTracker:
    """
    Singleton to track Steam Workshop download operations.

    Maintains state of all subscription/download operations, emitting signals
    for UI updates via EventBus. Thread-safe for concurrent access.
    """

    _instance: Optional["DownloadTracker"] = None

    def __new__(cls) -> "DownloadTracker":
        """
        Create or return singleton instance.

        :return: The singleton instance
        :rtype: DownloadTracker
        """
        if cls._instance is None:
            cls._instance = super(DownloadTracker, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the DownloadTracker singleton."""
        if hasattr(self, "initialized"):
            return

        self._lock = RLock()
        self._batches: dict[str, DownloadBatch] = {}  # batch_id -> DownloadBatch
        self._pfid_to_batch: dict[int, str] = {}  # pfid -> batch_id (for lookup)

        self.initialized = True
        logger.info("DownloadTracker initialized")

    def create_batch(
        self, operation: str, pfids: list[int], mod_names: dict[int, str]
    ) -> str:
        """
        Create a new download batch.

        :param operation: "subscribe", "unsubscribe", or "resubscribe"
        :type operation: str
        :param pfids: List of PublishedFileIds
        :type pfids: list[int]
        :param mod_names: Mapping of pfid -> mod name
        :type mod_names: dict[int, str]
        :return: Unique batch identifier
        :rtype: str
        """
        with self._lock:
            batch_id = str(uuid4())

            items = [
                DownloadItem(
                    pfid=pfid,
                    name=mod_names.get(pfid, f"Unknown Mod {pfid}"),
                    operation=operation,
                )
                for pfid in pfids
            ]

            batch = DownloadBatch(
                batch_id=batch_id,
                operation=operation,
                items=items,
            )

            self._batches[batch_id] = batch

            # Map pfids to batch for callback lookup
            for pfid in pfids:
                self._pfid_to_batch[pfid] = batch_id

            logger.info(
                f"Created download batch {batch_id}: {operation} for {len(pfids)} mods"
            )

            # Emit signal for UI update
            EventBus().download_batch_created.emit(batch_id)

            return batch_id

    def update_item_status(
        self, pfid: int, status: DownloadStatus, error: Optional[str] = None
    ) -> None:
        """
        Update status for a specific item.

        :param pfid: PublishedFileId
        :type pfid: int
        :param status: New status
        :type status: DownloadStatus
        :param error: Optional error message
        :type error: Optional[str]
        :return: None
        """
        with self._lock:
            batch_id = self._pfid_to_batch.get(pfid)
            if not batch_id:
                logger.warning(f"No batch found for pfid {pfid}")
                return

            batch = self._batches.get(batch_id)
            if not batch:
                logger.warning(f"Batch {batch_id} not found")
                return

            # Find item in batch
            item = next((i for i in batch.items if i.pfid == pfid), None)
            if not item:
                logger.warning(f"Item {pfid} not found in batch {batch_id}")
                return

            # Update status
            old_status = item.status
            item.status = status

            if error:
                item.error_message = error

            if status == DownloadStatus.SUBSCRIBING and not item.started_at:
                item.started_at = datetime.now()

            if item.is_complete and not item.completed_at:
                item.completed_at = datetime.now()

            logger.debug(
                f"Updated {pfid} ({item.name}): {old_status.value} -> {status.value}"
            )

            # Emit signal for UI update (convert pfid to string for 64-bit Steam IDs)
            EventBus().download_item_updated.emit(batch_id, str(pfid))

            # If batch is complete, emit batch complete signal
            if batch.is_complete:
                EventBus().download_batch_completed.emit(batch_id)

    def update_item_progress(
        self, pfid: int, bytes_downloaded: int, bytes_total: int
    ) -> None:
        """
        Update download progress for an item.

        :param pfid: PublishedFileId
        :type pfid: int
        :param bytes_downloaded: Bytes downloaded so far
        :type bytes_downloaded: int
        :param bytes_total: Total bytes to download
        :type bytes_total: int
        :return: None
        """
        with self._lock:
            batch_id = self._pfid_to_batch.get(pfid)
            if not batch_id:
                return

            batch = self._batches.get(batch_id)
            if not batch:
                return

            item = next((i for i in batch.items if i.pfid == pfid), None)
            if not item:
                return

            # Update progress
            item.bytes_downloaded = bytes_downloaded
            item.bytes_total = bytes_total

            # Auto-update status to DOWNLOADING if we have progress
            if bytes_total > 0 and item.status == DownloadStatus.SUBSCRIBING:
                item.status = DownloadStatus.DOWNLOADING

            # If download reaches 100% (or very close due to rounding), transition to INSTALLING
            # (callback or poller will update to COMPLETED when installation finishes)
            if (
                bytes_total > 0
                and bytes_downloaded >= bytes_total * 0.99  # 99%+ counts as complete
                and item.status == DownloadStatus.DOWNLOADING
            ):
                progress_pct = int(bytes_downloaded / bytes_total * 100)
                logger.debug(
                    f"Download {progress_pct}% for {pfid}, transitioning to INSTALLING"
                )
                item.status = DownloadStatus.INSTALLING
                EventBus().download_item_updated.emit(batch_id, str(pfid))

            # Emit signal for UI progress update (convert pfid to string for 64-bit Steam IDs)
            EventBus().download_item_progress.emit(batch_id, str(pfid))

    def get_batch(self, batch_id: str) -> Optional[DownloadBatch]:
        """
        Get a batch by ID.

        :param batch_id: Unique batch identifier
        :type batch_id: str
        :return: DownloadBatch if found, None otherwise
        :rtype: Optional[DownloadBatch]
        """
        with self._lock:
            return self._batches.get(batch_id)

    def get_all_batches(self) -> list[DownloadBatch]:
        """
        Get all batches (most recent first).

        :return: List of all download batches
        :rtype: list[DownloadBatch]
        """
        with self._lock:
            return sorted(
                self._batches.values(),
                key=lambda b: b.created_at,
                reverse=True,
            )

    def get_active_batches(self) -> list[DownloadBatch]:
        """
        Get all batches with active downloads.

        :return: List of batches with incomplete items
        :rtype: list[DownloadBatch]
        """
        with self._lock:
            return [b for b in self._batches.values() if not b.is_complete]

    def remove_batch(self, batch_id: str) -> None:
        """
        Remove a completed batch from tracking.

        :param batch_id: Unique batch identifier
        :type batch_id: str
        :return: None
        """
        with self._lock:
            batch = self._batches.pop(batch_id, None)
            if batch:
                # Clean up pfid mappings
                for item in batch.items:
                    self._pfid_to_batch.pop(item.pfid, None)

                logger.info(f"Removed batch {batch_id}")
                EventBus().download_batch_removed.emit(batch_id)
