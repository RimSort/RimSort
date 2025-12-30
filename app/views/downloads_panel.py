"""
Downloads panel view for displaying Steam Workshop download progress.

This module provides the UI for the Downloads tab, showing active and recent
downloads with progress bars, status updates, and control buttons.
"""

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)


class DownloadsPanel(QWidget):
    """
    View for displaying Steam Workshop download progress.

    Shows active and recent downloads with progress bars, status, and controls.
    Designed to be used as a tab in the main window.
    """

    def __init__(self) -> None:
        """Initialize the Downloads panel."""
        super().__init__()
        logger.info("Initializing DownloadsPanel")

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        self.setLayout(main_layout)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("Steam Workshop Downloads")
        header_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        header_layout.addWidget(header_label)

        header_layout.addStretch()

        # Clear completed button
        self.clear_completed_button = QPushButton("Clear Completed")
        self.clear_completed_button.setToolTip(
            "Remove completed downloads from the list"
        )
        header_layout.addWidget(self.clear_completed_button)

        main_layout.addLayout(header_layout)

        # Downloads table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Mod Name", "Operation", "Status", "Progress", "Size", "Actions"]
        )

        # Configure table
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        # Set column stretch
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Mod Name
        header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )  # Operation
        header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )  # Status
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)  # Progress
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Size
        header.setSectionResizeMode(
            5, QHeaderView.ResizeMode.ResizeToContents
        )  # Actions

        self.table.setColumnWidth(3, 200)  # Fixed width for progress bar

        main_layout.addWidget(self.table)

        # Status bar at bottom
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QHBoxLayout()
        status_frame.setLayout(status_layout)

        self.status_label = QLabel("No active downloads")
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        self.stats_label = QLabel("")
        status_layout.addWidget(self.stats_label)

        main_layout.addWidget(status_frame)

        logger.debug("Finished DownloadsPanel initialization")

    def get_row_for_pfid(self, pfid: int) -> int | None:
        """
        Find table row index for a given pfid.

        :param pfid: PublishedFileId to search for
        :type pfid: int
        :return: Row index or None if not found
        :rtype: int | None
        """
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)  # Mod name column
            if item and item.data(Qt.ItemDataRole.UserRole) == pfid:
                return row
        return None

    def update_status_label(self, text: str) -> None:
        """
        Update the status label at bottom of panel.

        :param text: Status text to display
        :type text: str
        :return: None
        """
        self.status_label.setText(text)

    def update_stats_label(self, active: int, completed: int, failed: int) -> None:
        """
        Update statistics label.

        :param active: Number of active downloads
        :type active: int
        :param completed: Number of completed downloads
        :type completed: int
        :param failed: Number of failed downloads
        :type failed: int
        :return: None
        """
        parts = []
        if active > 0:
            parts.append(f"{active} active")
        if completed > 0:
            parts.append(f"{completed} completed")
        if failed > 0:
            parts.append(f"{failed} failed")

        self.stats_label.setText(" | ".join(parts) if parts else "")
