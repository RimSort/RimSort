from logger_tt import logger
from functools import partial

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QMenu, QPushButton, QVBoxLayout, QWidget


class Actions(QWidget):
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
        logger.info("Starting Actions initialization")
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
        self.refresh_button.setToolTip(
            "Right-click to configure Steam Apikey with DynamicQuery!"
        )
        self.refresh_button.clicked.connect(
            partial(self.actions_signal.emit, "refresh")
        )
        self.refresh_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.refresh_button.customContextMenuRequested.connect(
            self.steamApikeyContextMenuEvent
        )

        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(partial(self.actions_signal.emit, "clear"))

        self.restore_button = QPushButton("Restore")
        self.restore_button.clicked.connect(
            partial(self.actions_signal.emit, "restore")
        )

        self.sort_button = QPushButton("Sort")
        self.sort_button.clicked.connect(partial(self.actions_signal.emit, "sort"))

        self.import_button = QPushButton("Import List")
        self.import_button.clicked.connect(partial(self.actions_signal.emit, "import"))

        self.export_button = QPushButton("Export List")
        self.export_button.clicked.connect(partial(self.actions_signal.emit, "export"))

        self.optimize_textures_button = QPushButton("Optimize textures")
        self.optimize_textures_button.setToolTip(
            "Quality presets configurable in settings!\nRight-click to delete .dds textures"
        )
        self.optimize_textures_button.clicked.connect(
            partial(self.actions_signal.emit, "optimize_textures")
        )
        self.optimize_textures_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.optimize_textures_button.customContextMenuRequested.connect(
            self.optimizeTexContextMenuEvent
        )

        self.browse_workshop_button = QPushButton("Browse workshop")
        self.browse_workshop_button.setToolTip(
            "Download mods anonymously with steamcmd\n" + "No Steam account required!"
        )
        self.browse_workshop_button.clicked.connect(
            partial(self.actions_signal.emit, "browse_workshop")
        )

        self.setup_steamcmd_button = QPushButton("Setup steamcmd")
        self.setup_steamcmd_button.setToolTip("Requires an internet connection!")
        self.setup_steamcmd_button.clicked.connect(
            partial(self.actions_signal.emit, "setup_steamcmd")
        )

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(partial(self.actions_signal.emit, "save"))

        self.run_button = QPushButton("Run")
        self.run_button.setToolTip("Right-click to set RimWorld game arguments!")
        self.run_button.clicked.connect(partial(self.actions_signal.emit, "run"))
        self.run_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.run_button.customContextMenuRequested.connect(self.runArgsContextMenuEvent)

        # Add buttons to sub-layouts and sub-layouts to the main layout.
        self.top_panel.addWidget(self.refresh_button)
        self.top_panel.addWidget(self.clear_button)
        self.top_panel.addWidget(self.restore_button)
        self.top_panel.addWidget(self.sort_button)
        self.middle_panel.addWidget(self.optimize_textures_button)
        self.middle_panel.addWidget(self.browse_workshop_button)
        self.middle_panel.addWidget(self.setup_steamcmd_button)
        self.bottom_panel.addWidget(self.import_button)
        self.bottom_panel.addWidget(self.export_button)
        self.bottom_panel.addWidget(self.save_button)
        self.bottom_panel.addWidget(self.run_button)

        logger.info("Finished Actions initialization")

    @property
    def panel(self) -> QVBoxLayout:
        return self._panel

    def optimizeTexContextMenuEvent(self, point: QPoint) -> None:
        contextMenu = QMenu(self)  # Actions Panel context menu event
        delete_dds_tex_action = contextMenu.addAction(
            "Delete optimized textures"
        )  # delete .dds
        delete_dds_tex_action.triggered.connect(
            partial(self.actions_signal.emit, "delete_textures")
        )
        action = contextMenu.exec_(self.optimize_textures_button.mapToGlobal(point))

    def runArgsContextMenuEvent(self, point: QPoint) -> None:
        contextMenu = QMenu(self)  # Actions Panel context menu event
        set_run_args = contextMenu.addAction("Edit Run Args")  # runArgs
        set_run_args.triggered.connect(
            partial(self.actions_signal.emit, "edit_run_args")
        )
        action = contextMenu.exec_(self.run_button.mapToGlobal(point))

    def steamApikeyContextMenuEvent(self, point: QPoint) -> None:
        contextMenu = QMenu(self)  # Actions Panel context menu event
        set_steam_apikey = contextMenu.addAction("Edit Steam Apikey")  # steam_apikey
        set_steam_apikey.triggered.connect(
            partial(self.actions_signal.emit, "edit_steam_apikey")
        )
        action = contextMenu.exec_(self.refresh_button.mapToGlobal(point))
