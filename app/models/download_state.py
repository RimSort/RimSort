"""
Download state models for tracking Steam Workshop subscription operations.

This module defines the data models used to track download progress and state
for Steam Workshop items, replacing ACF file polling with event-driven tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class DownloadStatus(Enum):
    """Status of a Steam Workshop download operation."""

    QUEUED = "queued"  # Operation queued, not started
    UNSUBSCRIBING = "unsubscribing"  # Unsubscribe in progress (for resubscribe)
    SUBSCRIBING = "subscribing"  # Subscribe API call made
    DOWNLOADING = "downloading"  # Download in progress
    INSTALLING = "installing"  # Download complete, installing
    COMPLETED = "completed"  # Successfully installed
    FAILED = "failed"  # Operation failed
    CANCELLED = "cancelled"  # User cancelled


@dataclass
class DownloadItem:
    """
    Represents a single Steam Workshop download/subscription operation.

    Tracks the complete lifecycle of a mod download from queue to completion,
    including progress, timing, and error state.
    """

    pfid: int  # PublishedFileId
    name: str  # Mod name (from metadata)
    operation: str  # "subscribe", "unsubscribe", "resubscribe"
    status: DownloadStatus = DownloadStatus.QUEUED

    # Progress tracking
    bytes_downloaded: int = 0
    bytes_total: int = 0

    # Timing
    queued_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Error tracking
    error_message: Optional[str] = None

    @property
    def progress_percent(self) -> float:
        """
        Calculate download progress as percentage (0-100).

        :return: Progress percentage (0.0-100.0)
        :rtype: float
        """
        if self.bytes_total <= 0:
            return 0.0
        return (self.bytes_downloaded / self.bytes_total) * 100.0

    @property
    def is_active(self) -> bool:
        """
        Check if this download is currently active.

        :return: True if download is in progress
        :rtype: bool
        """
        return self.status in {
            DownloadStatus.QUEUED,
            DownloadStatus.UNSUBSCRIBING,
            DownloadStatus.SUBSCRIBING,
            DownloadStatus.DOWNLOADING,
            DownloadStatus.INSTALLING,
        }

    @property
    def is_complete(self) -> bool:
        """
        Check if this download is finished (success or failure).

        :return: True if download has completed
        :rtype: bool
        """
        return self.status in {
            DownloadStatus.COMPLETED,
            DownloadStatus.FAILED,
            DownloadStatus.CANCELLED,
        }


@dataclass
class DownloadBatch:
    """
    Represents a batch of downloads triggered together.

    Groups related download operations that were initiated from a single
    user action (e.g., "Update All Mods").
    """

    batch_id: str  # Unique identifier
    operation: str  # "subscribe", "unsubscribe", "resubscribe"
    items: list[DownloadItem] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def total_items(self) -> int:
        """
        Get total number of items in this batch.

        :return: Total item count
        :rtype: int
        """
        return len(self.items)

    @property
    def active_items(self) -> list[DownloadItem]:
        """
        Get items currently in progress.

        :return: List of active download items
        :rtype: list[DownloadItem]
        """
        return [item for item in self.items if item.is_active]

    @property
    def completed_items(self) -> list[DownloadItem]:
        """
        Get items that have finished (successfully or with errors).

        :return: List of completed download items
        :rtype: list[DownloadItem]
        """
        return [item for item in self.items if item.is_complete]

    @property
    def is_complete(self) -> bool:
        """
        Check if all items in this batch are finished.

        :return: True if all items completed
        :rtype: bool
        """
        return len(self.completed_items) == self.total_items
