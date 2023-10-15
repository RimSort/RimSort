from logger_tt import logger
from functools import partial
from PySide6.QtCore import (
    Qt,
    QPoint,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class MultiButton(QWidget):
    clicked = Signal()  # Define a custom signal

    def __init__(self, main_action_name: str, tooltip: str, context_menu_content: list):
        super().__init__()

        # Create a horizontal layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create a QPushButton for the main action
        self.main_action = QPushButton(main_action_name, self)
        self.main_action.clicked.connect(self.emitClicked)
        self.main_action.setToolTip(tooltip)
        layout.addWidget(self.main_action)

        # Create a QToolButton with a menu for the secondary action
        self.secondary_action = QToolButton(self)
        self.secondary_action.setIcon(QIcon(""))
        self.secondary_action.setPopupMode(QToolButton.InstantPopup)
        layout.addWidget(self.secondary_action)

        # Create the context menu
        self.createContextMenu(context_menu_content, self.secondary_action)

        self.setLayout(layout)

    def emitClicked(self):
        # Emit the custom signal when the main action button is clicked
        self.clicked.emit()

    def createContextMenu(self, context_menu_content, widget):
        context_menu = QMenu(self)
        for item in context_menu_content:
            action = context_menu.addAction(item["text"])
            action.triggered.connect(
                lambda triggered_action=item[
                    "triggered_argument"
                ]: self.actions_signal.emit(triggered_action)
            )
        widget.setMenu(context_menu)


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
        logger.debug("Initializing Actions")
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

        self._panel.addLayout(self.top_panel, 33)
        self._panel.addLayout(self.middle_panel, 33)
        self._panel.addLayout(self.bottom_panel, 33)

        # LIST OPTIONS LABEL
        self.list_options_label = QLabel("List Options")
        self.list_options_label.setObjectName("summaryValue")
        self.list_options_label.setAlignment(Qt.AlignCenter)

        # REFRESH BUTTON
        self.refresh_button = QPushButton("Refresh mods")
        self.refresh_button.setAutoFillBackground(True)
        # Set tooltip and connect signal
        self.refresh_button.setToolTip(
            "Recalculate the heavy stuff and refresh RimSort"
        )
        self.connectButtonToSignal(self.refresh_button, "refresh")
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
        self.clear_button = QPushButton("Clear active mods")
        self.connectButtonToSignal(self.clear_button, "clear")

        # RESTORE BUTTON
        self.restore_button = QPushButton("Restore active state")
        self.connectButtonToSignal(self.restore_button, "restore")
        self.restore_button.setToolTip(
            "Attempts to restore an active mods list state that was\n"
            + "cached on RimSort startup."
        )

        # SORT BUTTON
        self.sort_button = QPushButton("Sort active mods")
        self.connectButtonToSignal(self.sort_button, "sort")

        # TODDS LABEL
        self.todds_label = QLabel("DDS encoder (todds)")
        self.todds_label.setObjectName("summaryValue")
        self.todds_label.setAlignment(Qt.AlignCenter)

        # OPTIMIZE TEXTURES BUTTON
        self.optimize_textures_button = self.createMultiButton(
            "Optimize textures",
            "Use Menu to delete .dds textures",
            context_menu_content=[
                {
                    "text": "Delete .dds Textures",
                    "triggered_argument": "delete_textures",
                },
            ],
        )

        self.connectButtonToSignal(self.optimize_textures_button, "optimize_textures")

        # STEAM LABEL
        self.add_mods_label = QLabel("Download mods")
        self.add_mods_label.setObjectName("summaryValue")
        self.add_mods_label.setAlignment(Qt.AlignCenter)

        # ADD GIT MOD BUTTON
        self.add_git_mod_button = QPushButton("Add git mods")
        self.add_git_mod_button.setToolTip("Clone a mod git repo to your local mods")
        self.connectButtonToSignal(self.add_git_mod_button, "add_git_mod")

        # setup_steamcmd button
        self.setup_steamcmd_button = self.createMultiButton(
            "Setup SteamCMD",
            "Setup SteamCMD change/configure the installed SteamCMD prefix\n"
            'Set to the folder you would like to contain the "SteamCMD" folder',
            context_menu_content=[
                {
                    "text": "Configure SteamCMD prefix",
                    "triggered_argument": "set_steamcmd_path",
                },
                {
                    "text": "Import SteamCMD acf data",
                    "triggered_argument": "import_steamcmd_acf_data",
                },
                {
                    "text": "Delete SteamCMD acf data",
                    "triggered_argument": "reset_steamcmd_acf_data",
                },
            ],
        )

        self.connectButtonToSignal(
            self.setup_steamcmd_button.main_action, "setup_steamcmd"
        )

        # BROWSE WORKSHOP BUTTON
        self.browse_workshop_button = QPushButton("Browse Workshop")
        self.browse_workshop_button.setToolTip(
            "Download mods anonymously with SteamCMD, or subscribe with Steam!\n"
            + "No Steam account required to use SteamCMD!"
        )
        self.connectButtonToSignal(self.browse_workshop_button, "browse_workshop")

        # UPDATE WORKSHOP MODS BUTTON
        self.update_workshop_mods_button = QPushButton("Update Workshop mods")
        self.update_workshop_mods_button.setToolTip(
            "Query Steam WebAPI for mod update data and check against installed Workshop mods\n"
            + "Supports mods sourced via SteamCMD or Steam client"
        )
        self.connectButtonToSignal(
            self.update_workshop_mods_button, "update_workshop_mods"
        )

        # RIMWORLD LABEL
        self.rimworld_label = QLabel("RimWorld options")
        self.rimworld_label.setObjectName("summaryValue")
        self.rimworld_label.setAlignment(Qt.AlignCenter)

        # IMPORT BUTTON
        self.import_button = QPushButton("Import mod list")
        self.connectButtonToSignal(self.import_button, "import_list_file_xml")

        # EXPORT BUTTON
        self.export_button = self.createMultiButton(
            "Export mod list",
            "Export mod list to xml file",
            context_menu_content=[
                {
                    "text": "Export mod list to clipboard",
                    "triggered_argument": "export_list_clipboard",
                },
                {
                    "text": "Upload mod list with Rentry.co",
                    "triggered_argument": "upload_list_rentry",
                },
            ],
        )
        self.connectButtonToSignal(
            self.export_button.main_action, "export_list_file_xml"
        )

        # RUN BUTTON
        self.run_button = self.createMultiButton(
            "Run game",
            "Use Menu to 'Edit run arguments' to sets RimWorld game arguments!",
            context_menu_content=[
                {
                    "text": "Edit run arguments",
                    "triggered_argument": "edit_run_args",
                },
            ],
        )

        self.connectButtonToSignal(self.run_button.main_action, "run")

        # SAVE BUTTON
        self.save_button = QPushButton("Save mod list")
        self.connectButtonToSignal(self.save_button, "save")
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

        # UPLOAD LOG BUTTON
        self.upload_rwlog_button = QPushButton("Upload logfile")
        self.upload_rwlog_button.setToolTip("Upload RimWorld log to 0x0.st")
        self.connectButtonToSignal(self.upload_rwlog_button, "upload_rw_log")

        # Add buttons to sub-layouts and sub-layouts to the main layout
        self.top_panel.addWidget(self.list_options_label)
        self.top_panel.addWidget(self.refresh_button)
        self.top_panel.addWidget(self.clear_button)
        self.top_panel.addWidget(self.restore_button)
        self.top_panel.addWidget(self.sort_button)
        self.top_panel.addWidget(self.todds_label)
        self.top_panel.addWidget(self.optimize_textures_button)
        self.middle_panel.addWidget(self.add_mods_label)
        self.middle_panel.addWidget(self.add_git_mod_button)
        self.middle_panel.addWidget(self.browse_workshop_button)
        self.middle_panel.addWidget(self.setup_steamcmd_button)
        self.middle_panel.addWidget(self.update_workshop_mods_button)
        self.bottom_panel.addWidget(self.rimworld_label)
        self.bottom_panel.addWidget(self.import_button)
        self.bottom_panel.addWidget(self.export_button)
        self.bottom_panel.addWidget(self.run_button)
        self.bottom_panel.addWidget(self.save_button)
        self.bottom_panel.addWidget(self.upload_rwlog_button)

        logger.debug("Finished Actions initialization")

    @property
    def panel(self) -> QVBoxLayout:
        return self._panel

    def createMultiButton(self, main_action_name, tooltip, context_menu_content):
        multi_button = MultiButton(main_action_name, tooltip, context_menu_content)
        self.connectButtonToSignal(multi_button.main_action, main_action_name)
        self.createContextMenu(
            context_menu_content, multi_button.secondary_action, self.actions_signal
        )
        return multi_button

    def createContextMenu(self, context_menu_content, widget, signal_handler):
        context_menu = QMenu(self)
        for item in context_menu_content:
            action = context_menu.addAction(item["text"])
            action.triggered.connect(
                partial(signal_handler.emit, item["triggered_argument"])
            )
        widget.setMenu(context_menu)

    def connectButtonToSignal(self, button, signal_name):
        button.clicked.connect(partial(self.actions_signal.emit, signal_name))
