from functools import partial

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


class Actions(QObject):
    """
    This class controls the layout and functionality for the action panel,
    the panel on the right side of the GUI (strip with the main
    functionality buttons). Subclasses QObject to allow emitting signals.
    """

    # Signal emitter for this class
    actions_signal = Signal(str)

    def __init__(self) -> None:
        """
        Initialize the actions panel. Construct the layout,
        add widgets, and emit signals where applicable.
        """
        super(Actions, self).__init__()

        # Create the main layout.
        self._panel = QVBoxLayout()

        # Create sub-layouts. There are three of these, each representing
        # a grouping of buttons.
        self.top_panel = QVBoxLayout()
        self.top_panel.setAlignment(Qt.AlignTop)

        self.middle_panel = QVBoxLayout()
        self.middle_panel.setAlignment(Qt.AlignBottom)

        self.bottom_panel = QVBoxLayout()
        self.bottom_panel.setAlignment(Qt.AlignBottom)

        self._panel.addLayout(self.top_panel, 50)
        self._panel.addLayout(self.middle_panel, 25)
        self._panel.addLayout(self.bottom_panel, 25)

        # Create button widgets. Each button, when clicked, emits a signal
        # with a string representing its action.
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("appButton")
        self.refresh_button.clicked.connect(partial(self.actions_signal.emit, "refresh"))

        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("appButton")
        self.clear_button.clicked.connect(partial(self.actions_signal.emit, "clear"))

        self.restore_button = QPushButton("Restore")
        self.restore_button.setObjectName("appButton")
        self.restore_button.clicked.connect(
            partial(self.actions_signal.emit, "restore")
        )

        self.sort_button = QPushButton("Sort")
        self.sort_button.setObjectName("appButton")
        self.sort_button.clicked.connect(partial(self.actions_signal.emit, "sort"))

        self.import_button = QPushButton("Import List")
        self.import_button.setObjectName("appButton")
        self.import_button.clicked.connect(partial(self.actions_signal.emit, "import"))

        self.export_button = QPushButton("Export List")
        self.export_button.setObjectName("appButton")
        self.export_button.clicked.connect(partial(self.actions_signal.emit, "export"))

        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("appButton")
        self.save_button.clicked.connect(partial(self.actions_signal.emit, "save"))

        self.run_button = QPushButton("Run")
        self.run_button.setObjectName("appButton")
        self.run_button.clicked.connect(partial(self.actions_signal.emit, "run"))

        # Add buttons to sub-layouts and sub-layouts to the main layout.
        self.top_panel.addWidget(self.refresh_button)
        self.top_panel.addWidget(self.clear_button)
        self.top_panel.addWidget(self.restore_button)
        self.top_panel.addWidget(self.sort_button)
        self.middle_panel.addWidget(self.import_button)
        self.middle_panel.addWidget(self.export_button)
        self.bottom_panel.addWidget(self.save_button)
        self.bottom_panel.addWidget(self.run_button)

    @property
    def panel(self):
        return self._panel
