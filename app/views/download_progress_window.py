from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget


class DownloadProgressWindow(QWidget):
    cancel_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Download Progress")
        self.resize(350, 120)

        self.progressBar = QProgressBar()
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(100)
        self.progressBar.setValue(0)
        self.progressBar.setTextVisible(True)

        self.progressLabel = QLabel("Starting download...")
        self.progressLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel_clicked)

        layout = QVBoxLayout()
        layout.addWidget(self.progressLabel)
        layout.addWidget(self.progressBar)
        layout.addWidget(self.cancel_button)

        self.setLayout(layout)

    def update_progress(self, percent: int, message: str) -> None:
        if percent < 0:
            if self.progressBar.maximum() != 0:
                self.progressBar.setRange(0, 0)
        else:
            if self.progressBar.maximum() == 0:
                self.progressBar.setRange(0, 100)
            if 0 <= percent <= 100:
                self.progressBar.setValue(percent)
        if message:
            self.progressLabel.setText(message)

    def _on_cancel_clicked(self) -> None:
        self.cancel_requested.emit()
