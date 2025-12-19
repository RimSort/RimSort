"""Task progress window for downloads, extractions, and other long-running operations."""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget


class TaskProgressWindow(QWidget):
    """
    Progress window for task-based operations (downloads, extractions, backups).

    Provides consistent UI and signal-based API for monitoring long-running operations.

    Signals:
        cancel_requested: Emitted when user clicks cancel button
        finished: Emitted with (success, message) when operation completes
    """

    cancel_requested = Signal()
    finished = Signal(bool, str)  # success, error_message

    def __init__(
        self,
        title: str = "Processing",
        show_message: bool = True,
        show_percent: bool = True,
    ) -> None:
        """
        Initialize the task progress window.

        Args:
            title: Window title
            show_message: Whether to display status message label
            show_percent: Whether to display percentage in progress bar
        """
        super().__init__()
        self.setWindowTitle(title)
        self.show_message_enabled = show_message
        self.show_percent_enabled = show_percent

        # Calculate initial height based on visible elements
        height = 120  # Base: progress bar + cancel button
        if show_message:
            height += 30  # Add space for message label

        self.resize(400, height)

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Optional status message label
        self.message_label: Optional[QLabel] = None
        if show_message:
            self.message_label = QLabel("")
            self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.message_label.setWordWrap(True)
            layout.addWidget(self.message_label)

        # Progress bar with optional percentage display
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(show_percent)
        layout.addWidget(self.progress_bar)

        # Cancel button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        layout.addWidget(self.cancel_button)

        self.setLayout(layout)

    def update_progress(self, percent: int, message: str = "") -> None:
        """
        Update progress bar and optional message.

        Args:
            percent: Progress percentage (0-100). Use -1 for indeterminate progress.
            message: Optional status message to display
        """
        # Handle indeterminate progress
        if percent < 0:
            if self.progress_bar.maximum() != 0:
                self.progress_bar.setRange(0, 0)  # Indeterminate mode
        else:
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 100)  # Back to determinate mode
            if 0 <= percent <= 100:
                self.progress_bar.setValue(percent)

        # Update message if provided
        if message and self.message_label:
            self.message_label.setText(message)

    def set_message(self, message: str) -> None:
        """
        Update the status message label.

        Args:
            message: New status message to display
        """
        if self.message_label:
            self.message_label.setText(message)

    def set_cancel_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the cancel button.

        Args:
            enabled: Whether cancel button should be enabled
        """
        self.cancel_button.setEnabled(enabled)

    def complete(self, success: bool, message: str = "") -> None:
        """
        Mark operation as complete and emit finished signal.

        Args:
            success: Whether operation completed successfully
            message: Completion message to display
        """
        self.progress_bar.setValue(100 if success else 0)
        if message:
            self.set_message(message)
        self.finished.emit(success, message)

    def _on_cancel_clicked(self) -> None:
        """Handle cancel button click."""
        self.cancel_requested.emit()
