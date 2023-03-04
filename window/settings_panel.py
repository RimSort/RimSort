import logging
from functools import partial

from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import QComboBox, QDialog, QLabel, QPushButton, QVBoxLayout

logger = logging.getLogger(__name__)


class SettingsPanel(QDialog):
    settings_signal = Signal(str)

    def __init__(self) -> None:
        logger.info("Starting SettingsPanel initialization")
        super(SettingsPanel, self).__init__()

        # Create window
        self.setFixedSize(400, 400)
        self.setWindowTitle("Settings")

        # Allow for styling
        self.setObjectName("settingsPanel")

        # Create main layout
        self.layout = QVBoxLayout()
        self.layout.setAlignment(Qt.AlignTop)

        # Create widgets
        self.sorting_algorithm_label = QLabel("Sorting Algorithm")
        self.sorting_algorithm_label.setObjectName("summaryValue")
        self.sorting_algorithm_cb = QComboBox()
        self.sorting_algorithm_cb.addItems(["RimPy", "Topological"])
        self.clear_paths_button = QPushButton("Clear Paths")
        self.clear_paths_button.clicked.connect(
            partial(self.settings_signal.emit, "clear_paths")
        )

        # Add widgets to layout
        self.layout.addWidget(self.sorting_algorithm_label)
        self.layout.addWidget(self.sorting_algorithm_cb)
        self.layout.addWidget(self.clear_paths_button)

        # Display items
        self.setLayout(self.layout)

        logger.info("Finished SettingsPanel initialization")
