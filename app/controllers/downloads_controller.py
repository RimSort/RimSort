"""
Downloads panel controller for managing download tracking and UI updates.

This module provides the controller that connects the DownloadsPanel view
to the DownloadTracker state and EventBus signals.
"""

from loguru import logger
from PySide6.QtCore import QObject, Qt, Slot
from PySide6.QtWidgets import QProgressBar, QTableWidgetItem

from app.models.download_state import DownloadStatus
from app.utils.download_tracker import DownloadTracker
from app.utils.event_bus import EventBus
from app.utils.generic import format_file_size
from app.views.downloads_panel import DownloadsPanel


class DownloadsController(QObject):
    """
    Controller for the Downloads panel.

    Manages download tracking and UI updates via DownloadTracker and EventBus.
    Connects signals to view update methods and maintains table state.
    """

    def __init__(self, view: DownloadsPanel) -> None:
        """
        Initialize the Downloads controller.

        :param view: DownloadsPanel view instance
        :type view: DownloadsPanel
        """
        super().__init__()
        logger.info("Initializing DownloadsController")

        self.view = view
        self.tracker = DownloadTracker()

        # Connect EventBus signals
        EventBus().download_batch_created.connect(self._on_batch_created)
        EventBus().download_batch_completed.connect(self._on_batch_completed)
        EventBus().download_batch_removed.connect(self._on_batch_removed)
        EventBus().download_item_updated.connect(self._on_item_updated)
        EventBus().download_item_progress.connect(self._on_item_progress)

        # Connect view signals
        self.view.clear_completed_button.clicked.connect(self._clear_completed)

        # Initialize view with existing batches (if any)
        self._refresh_view()

        logger.debug("Finished DownloadsController initialization")

    @Slot(str)
    def _on_batch_created(self, batch_id: str) -> None:
        """
        Handle new batch creation.

        :param batch_id: Unique batch identifier
        :type batch_id: str
        :return: None
        """
        logger.debug(f"Batch created: {batch_id}")
        batch = self.tracker.get_batch(batch_id)
        if not batch:
            return

        # Add all items from batch to table
        for item in batch.items:
            self._add_item_to_table(batch_id, item.pfid)

        self._update_status()

    @Slot(str)
    def _on_batch_completed(self, batch_id: str) -> None:
        """
        Handle batch completion.

        :param batch_id: Unique batch identifier
        :type batch_id: str
        :return: None
        """
        logger.info(f"Batch completed: {batch_id}")
        self._update_status()

    @Slot(str)
    def _on_batch_removed(self, batch_id: str) -> None:
        """
        Handle batch removal.

        :param batch_id: Unique batch identifier
        :type batch_id: str
        :return: None
        """
        logger.debug(f"Batch removed: {batch_id}")

        # Remove all items from this batch from table
        batch = self.tracker.get_batch(batch_id)
        if batch:
            for item in batch.items:
                row = self.view.get_row_for_pfid(item.pfid)
                if row is not None:
                    self.view.table.removeRow(row)

        self._update_status()

    @Slot(str, str)
    def _on_item_updated(self, batch_id: str, pfid_str: str) -> None:
        """
        Handle item status update.

        :param batch_id: Unique batch identifier
        :type batch_id: str
        :param pfid_str: PublishedFileId as string (to handle 64-bit Steam IDs)
        :type pfid_str: str
        :return: None
        """
        pfid = int(pfid_str)
        batch = self.tracker.get_batch(batch_id)
        if not batch:
            return

        item = next((i for i in batch.items if i.pfid == pfid), None)
        if not item:
            return

        # Find row in table
        row = self.view.get_row_for_pfid(pfid)
        if row is None:
            # Item not in table yet, add it
            self._add_item_to_table(batch_id, pfid)
            return

        # Update status column
        status_item = self.view.table.item(row, 2)
        if status_item:
            status_item.setText(self._format_status(item.status))

            # Color code by status
            if item.status == DownloadStatus.COMPLETED:
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            elif item.status == DownloadStatus.FAILED:
                status_item.setForeground(Qt.GlobalColor.red)
            elif item.status in (DownloadStatus.DOWNLOADING, DownloadStatus.INSTALLING):
                status_item.setForeground(Qt.GlobalColor.blue)

        # Update progress bar
        progress_widget = self.view.table.cellWidget(row, 3)
        if isinstance(progress_widget, QProgressBar):
            # Show 100% for INSTALLING or COMPLETED
            if item.status in (DownloadStatus.INSTALLING, DownloadStatus.COMPLETED):
                progress_widget.setValue(100)
            elif item.bytes_total > 0:
                progress_widget.setValue(int(item.progress_percent))

        # Update size column
        size_item = self.view.table.item(row, 4)
        if size_item and item.bytes_total > 0:
            size_text = f"{format_file_size(item.bytes_downloaded)} / {format_file_size(item.bytes_total)}"
            size_item.setText(size_text)

        self._update_status()

    @Slot(str, str)
    def _on_item_progress(self, batch_id: str, pfid_str: str) -> None:
        """
        Handle item progress update.

        :param batch_id: Unique batch identifier
        :type batch_id: str
        :param pfid_str: PublishedFileId as string (to handle 64-bit Steam IDs)
        :type pfid_str: str
        :return: None
        """
        pfid = int(pfid_str)
        batch = self.tracker.get_batch(batch_id)
        if not batch:
            return

        item = next((i for i in batch.items if i.pfid == pfid), None)
        if not item:
            return

        row = self.view.get_row_for_pfid(pfid)
        if row is None:
            return

        # Update progress bar
        progress_widget = self.view.table.cellWidget(row, 3)
        if isinstance(progress_widget, QProgressBar):
            if item.bytes_total > 0:
                progress_widget.setValue(int(item.progress_percent))

        # Update size
        size_item = self.view.table.item(row, 4)
        if size_item and item.bytes_total > 0:
            size_text = f"{format_file_size(item.bytes_downloaded)} / {format_file_size(item.bytes_total)}"
            size_item.setText(size_text)

    def _add_item_to_table(self, batch_id: str, pfid: int) -> None:
        """
        Add a download item to the table.

        :param batch_id: Unique batch identifier
        :type batch_id: str
        :param pfid: PublishedFileId
        :type pfid: int
        :return: None
        """
        batch = self.tracker.get_batch(batch_id)
        if not batch:
            return

        item = next((i for i in batch.items if i.pfid == pfid), None)
        if not item:
            return

        # Check if already exists
        if self.view.get_row_for_pfid(pfid) is not None:
            return

        row = self.view.table.rowCount()
        self.view.table.insertRow(row)

        # Mod Name (store pfid in UserRole)
        name_item = QTableWidgetItem(item.name)
        name_item.setData(Qt.ItemDataRole.UserRole, pfid)
        self.view.table.setItem(row, 0, name_item)

        # Operation
        op_item = QTableWidgetItem(item.operation.capitalize())
        self.view.table.setItem(row, 1, op_item)

        # Status
        status_item = QTableWidgetItem(self._format_status(item.status))
        self.view.table.setItem(row, 2, status_item)

        # Progress bar
        progress_bar = QProgressBar()
        progress_bar.setMinimum(0)
        progress_bar.setMaximum(100)
        progress_bar.setValue(0)
        progress_bar.setTextVisible(True)
        self.view.table.setCellWidget(row, 3, progress_bar)

        # Size
        size_item = QTableWidgetItem("--")
        self.view.table.setItem(row, 4, size_item)

        # Actions (future: cancel button, etc.)
        action_item = QTableWidgetItem("")
        self.view.table.setItem(row, 5, action_item)

    def _format_status(self, status: DownloadStatus) -> str:
        """
        Format status enum for display.

        :param status: Download status enum value
        :type status: DownloadStatus
        :return: Formatted status string
        :rtype: str
        """
        return status.value.replace("_", " ").title()

    def _update_status(self) -> None:
        """
        Update status bar with current stats.

        :return: None
        """
        batches = self.tracker.get_all_batches()

        total_active = 0
        total_completed = 0
        total_failed = 0

        for batch in batches:
            for item in batch.items:
                if item.is_active:
                    total_active += 1
                elif item.status == DownloadStatus.COMPLETED:
                    total_completed += 1
                elif item.status == DownloadStatus.FAILED:
                    total_failed += 1

        # Update status label
        if total_active > 0:
            self.view.update_status_label(
                f"Downloading {total_active} mod{'s' if total_active != 1 else ''}..."
            )
        else:
            self.view.update_status_label("No active downloads")

        # Update stats
        self.view.update_stats_label(total_active, total_completed, total_failed)

    def _clear_completed(self) -> None:
        """
        Remove completed batches from tracker and view.

        :return: None
        """
        batches = self.tracker.get_all_batches()
        removed_count = 0

        for batch in batches:
            if batch.is_complete:
                self.tracker.remove_batch(batch.batch_id)
                removed_count += 1

        if removed_count > 0:
            logger.info(f"Cleared {removed_count} completed batch(es)")

        self._refresh_view()

    def _refresh_view(self) -> None:
        """
        Refresh entire view from tracker state.

        :return: None
        """
        # Clear table
        self.view.table.setRowCount(0)

        # Repopulate from all batches
        for batch in self.tracker.get_all_batches():
            for item in batch.items:
                self._add_item_to_table(batch.batch_id, item.pfid)
                # Trigger update to set correct status/progress
                self._on_item_updated(batch.batch_id, item.pfid)

        self._update_status()
