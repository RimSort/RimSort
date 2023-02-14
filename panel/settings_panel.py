from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


class SettingsPanel(QDialog):
    def __init__(self) -> None:
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


        # Add widgets to layout
        self.layout.addWidget(self.sorting_algorithm_label)
        self.layout.addWidget(self.sorting_algorithm_cb)

        # Display items
        self.setLayout(self.layout)
