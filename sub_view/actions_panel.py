from logger_tt import logger
from functools import partial

from PySide6.QtCore import (
    QPoint,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


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

        # LIST OPTIONS LABEL
        self.list_options_label = QLabel("List Options")
        self.list_options_label.setObjectName("summaryValue")
        self.list_options_label.setAlignment(Qt.AlignCenter)

        # REFRESH BUTTON
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setAutoFillBackground(True)
        # Set tooltip and connect signal
        self.refresh_button.setToolTip(
            "Recalculate the heavy stuff and refresh RimSort"
        )
        self.refresh_button.clicked.connect(
            partial(self.actions_signal.emit, "refresh")
        )
        # Refresh button flashing animation
        self.refresh_button_flashing_animation = QTimer()
        self.refresh_button_flashing_animation.timeout.connect(
            lambda: self.refresh_button.setStyleSheet(
                "QPushButton { background-color: %s; }"
                % (
                    "#455364"
                    if self.refresh_button.styleSheet()
                    == "QPushButton { background-color: #54687a; }"
                    else "#54687a"
                )
            )
        )

        # CLEAR BUTTON
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(partial(self.actions_signal.emit, "clear"))

        # RESTORE BUTTON
        self.restore_button = QPushButton("Restore")
        self.restore_button.clicked.connect(
            partial(self.actions_signal.emit, "restore")
        )
        self.restore_button.setToolTip(
            "Attempts to restore an active mods list state that was\n"
            + "cached on RimSort startup."
        )

        # SORT BUTTON
        self.sort_button = QPushButton("Sort")
        self.sort_button.clicked.connect(partial(self.actions_signal.emit, "sort"))

        # IMPORT BUTTON
        self.import_button = QPushButton("Import List")
        self.import_button.clicked.connect(
            partial(self.actions_signal.emit, "import_list_file_xml")
        )

        # EXPORT BUTTON
        self.export_button = QPushButton("Export List")
        self.export_button.clicked.connect(
            partial(self.actions_signal.emit, "export_list_file_xml")
        )
        self.export_button.setToolTip("Right-click for additional sharing options")
        # Set context menu policy and connect custom context menu event
        self.export_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.export_button.customContextMenuRequested.connect(
            self.exportButtonAddionalOptions
        )

        # TODDS LABEL
        self.todds_label = QLabel("todds")
        self.todds_label.setObjectName("summaryValue")
        self.todds_label.setAlignment(Qt.AlignCenter)

        # OPTIMIZE TEXTURES BUTTON
        self.optimize_textures_button = QPushButton("Optimize textures")
        self.optimize_textures_button.setToolTip(
            "Quality presets configurable in settings!\nRight-click to delete .dds textures"
        )
        self.optimize_textures_button.clicked.connect(
            partial(self.actions_signal.emit, "optimize_textures")
        )
        # Set context menu policy and connect custom context menu event
        self.optimize_textures_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.optimize_textures_button.customContextMenuRequested.connect(
            self.optimizeTexContextMenuEvent
        )

        # STEAMCMD LABEL
        self.steamcmd_label = QLabel("SteamCMD")
        self.steamcmd_label.setObjectName("summaryValue")
        self.steamcmd_label.setAlignment(Qt.AlignCenter)

        # BROWSE WORKSHOP BUTTON
        self.browse_workshop_button = QPushButton("Browse workshop")
        self.browse_workshop_button.setToolTip(
            "Download mods anonymously with SteamCMD\n" + "No Steam account required!"
        )
        self.browse_workshop_button.clicked.connect(
            partial(self.actions_signal.emit, "browse_workshop")
        )

        # SETUP STEAMCMD BUTTON
        self.setup_steamcmd_button = QPushButton("Setup SteamCMD")
        self.setup_steamcmd_button.setToolTip(
            "Right-click to change/configure the installed SteamCMD prefix\n"
            + 'Set to the folder you would like to contain the "SteamCMD" folder'
        )
        self.setup_steamcmd_button.clicked.connect(
            partial(self.actions_signal.emit, "setup_steamcmd")
        )
        # Set context menu policy and connect custom context menu event
        self.setup_steamcmd_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setup_steamcmd_button.customContextMenuRequested.connect(
            self.setupSteamcmdContextMenuEvent
        )

        # SHOW STEAMCMD WORKSHOP MODS STATUS
        self.show_steamcmd_status_button = QPushButton("SteamCMD status")
        self.show_steamcmd_status_button.setToolTip(
            "Shows steamcmd workshop mod status for the detected prefix"
        )
        self.show_steamcmd_status_button.clicked.connect(
            partial(self.actions_signal.emit, "show_steamcmd_status")
        )

        # RIMWORLD LABEL
        self.rimworld_label = QLabel("RimWorld")
        self.rimworld_label.setObjectName("summaryValue")
        self.rimworld_label.setAlignment(Qt.AlignCenter)

        # RUN BUTTON
        self.run_button = QPushButton("Run")
        self.run_button.setToolTip("Right-click to set RimWorld game arguments!")
        self.run_button.clicked.connect(partial(self.actions_signal.emit, "run"))
        # Set context menu policy and connect custom context menu event
        self.run_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.run_button.customContextMenuRequested.connect(self.runArgsContextMenuEvent)

        # SAVE BUTTON
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(partial(self.actions_signal.emit, "save"))
        # Save button flashing animation
        self.save_button_flashing_animation = QTimer()
        self.save_button_flashing_animation.timeout.connect(
            lambda: self.save_button.setStyleSheet(
                "QPushButton { background-color: %s; }"
                % (
                    "#455364"
                    if self.save_button.styleSheet()
                    == "QPushButton { background-color: #54687a; }"
                    else "#54687a"
                )
            )
        )

        # Add buttons to sub-layouts and sub-layouts to the main layout
        self.top_panel.addWidget(self.list_options_label)
        self.top_panel.addWidget(self.refresh_button)
        self.top_panel.addWidget(self.clear_button)
        self.top_panel.addWidget(self.restore_button)
        self.top_panel.addWidget(self.sort_button)
        self.middle_panel.addWidget(self.todds_label)
        self.middle_panel.addWidget(self.optimize_textures_button)
        self.middle_panel.addWidget(self.steamcmd_label)
        self.middle_panel.addWidget(self.browse_workshop_button)
        self.middle_panel.addWidget(self.setup_steamcmd_button)
        self.middle_panel.addWidget(self.show_steamcmd_status_button)
        self.bottom_panel.addWidget(self.rimworld_label)
        self.bottom_panel.addWidget(self.import_button)
        self.bottom_panel.addWidget(self.export_button)
        self.bottom_panel.addWidget(self.run_button)
        self.bottom_panel.addWidget(self.save_button)

        logger.info("Finished Actions initialization")

    @property
    def panel(self) -> QVBoxLayout:
        return self._panel

    def exportButtonAddionalOptions(self, point: QPoint) -> None:
        contextMenu = QMenu(self)  # Actions Panel context menu event
        export_list_clipboard_action = contextMenu.addAction(
            "Export list to clipboard"
        )  # rentry
        export_list_clipboard_action.triggered.connect(
            partial(self.actions_signal.emit, "export_list_clipboard")
        )
        export_list_rentry_action = contextMenu.addAction(
            "Upload list with Rentry.co"
        )  # rentry
        export_list_rentry_action.triggered.connect(
            partial(self.actions_signal.emit, "upload_list_rentry")
        )
        action = contextMenu.exec_(self.export_button.mapToGlobal(point))

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

    def setupSteamcmdContextMenuEvent(self, point: QPoint) -> None:
        contextMenu = QMenu(self)  # Actions Panel context menu event
        set_steamcmd_path = contextMenu.addAction(
            "Configure steamcmd prefix"
        )  # steamcmd path
        set_steamcmd_path.triggered.connect(
            partial(self.actions_signal.emit, "set_steamcmd_path")
        )
        action = contextMenu.exec_(self.setup_steamcmd_button.mapToGlobal(point))
