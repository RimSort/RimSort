from loguru import logger
from functools import partial
from PySide6.QtCore import (
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models.multibutton import MultiButton


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
        self.refresh_button.clicked.connect(
            partial(self.actions_signal.emit, "refresh")
        )
        # Refresh button flashing animation
        self.refresh_button_flashing_animation = QTimer()
        self.refresh_button_flashing_animation.timeout.connect(
            partial(self.__flash_button, button=self.refresh_button)
        )

        # CLEAR BUTTON
        self.clear_button = QPushButton("Clear active mods")
        self.clear_button.clicked.connect(partial(self.actions_signal.emit, "clear"))

        # RESTORE BUTTON
        self.restore_button = QPushButton("Restore active state")
        self.restore_button.clicked.connect(
            partial(self.actions_signal.emit, "restore")
        )
        self.restore_button.setToolTip(
            "Attempts to restore an active mods list state that was\n"
            + "cached on RimSort startup."
        )

        # SORT BUTTON
        self.sort_button = QPushButton("Sort active mods")
        self.sort_button.clicked.connect(partial(self.actions_signal.emit, "sort"))

        # TODDS LABEL
        self.todds_label = QLabel("DDS encoder (todds)")
        self.todds_label.setObjectName("summaryValue")
        self.todds_label.setAlignment(Qt.AlignCenter)

        # OPTIMIZE TEXTURES BUTTON
        self.optimize_textures_button = MultiButton(
            actions_signal=self.actions_signal,
            main_action="Optimize textures",
            main_action_tooltip="Quality presets configurable in settings!\nUse menu to delete .dds textures",
            context_menu_content={
                "delete_textures": "Delete .dds Textures",
            },
        )

        self.optimize_textures_button.main_action.clicked.connect(
            partial(self.actions_signal.emit, "optimize_textures")
        )

        # STEAM LABEL
        self.add_mods_label = QLabel("Download mods")
        self.add_mods_label.setObjectName("summaryValue")
        self.add_mods_label.setAlignment(Qt.AlignCenter)

        # ADD GIT MOD BUTTON
        self.add_git_mod_button = QPushButton("Add git mods")
        self.add_git_mod_button.setToolTip("Clone a mod git repo to your local mods")
        self.add_git_mod_button.clicked.connect(
            partial(self.actions_signal.emit, "add_git_mod")
        )

        # setup_steamcmd button
        self.setup_steamcmd_button = MultiButton(
            actions_signal=self.actions_signal,
            main_action="Setup SteamCMD",
            main_action_tooltip="Install & setup SteamCMD for use with RimSort at the configured prefix.\n"
            "This defaults to RimSort storage dir. Use menu to configure the installed SteamCMD prefix\n",
            context_menu_content={
                "set_steamcmd_path": "Configure SteamCMD prefix",
                "import_steamcmd_acf_data": "Import SteamCMD acf data",
                "reset_steamcmd_acf_data": "Delete SteamCMD acf data",
            },
        )
        self.setup_steamcmd_button.main_action.clicked.connect(
            partial(self.actions_signal.emit, "setup_steamcmd")
        )

        # BROWSE WORKSHOP BUTTON
        self.browse_workshop_button = QPushButton("Browse Workshop")
        self.browse_workshop_button.setToolTip(
            "Download mods anonymously with SteamCMD, or subscribe with Steam!\n"
            + "No Steam account required to use SteamCMD!"
        )
        self.browse_workshop_button.clicked.connect(
            partial(self.actions_signal.emit, "browse_workshop")
        )

        # UPDATE WORKSHOP MODS BUTTON
        self.update_workshop_mods_button = QPushButton("Update Workshop mods")
        self.update_workshop_mods_button.setToolTip(
            "Query Steam WebAPI for mod update data and check against installed Workshop mods\n"
            + "Supports mods sourced via SteamCMD or Steam client"
        )
        self.update_workshop_mods_button.clicked.connect(
            partial(self.actions_signal.emit, "update_workshop_mods")
        )

        # RIMWORLD LABEL
        self.rimworld_label = QLabel("RimWorld options")
        self.rimworld_label.setObjectName("summaryValue")
        self.rimworld_label.setAlignment(Qt.AlignCenter)

        # RUN BUTTON
        self.run_button = MultiButton(
            actions_signal=self.actions_signal,
            main_action="Run game",
            main_action_tooltip="Use menu to edit game arguments that RimSort will pass to RimWorld",
            context_menu_content={
                "edit_run_args": "Edit run arguments",
            },
        )
        self.run_button.main_action.clicked.connect(
            partial(self.actions_signal.emit, "run")
        )

        # SAVE BUTTON
        self.save_button = QPushButton("Save mod list")
        self.save_button.clicked.connect(partial(self.actions_signal.emit, "save"))
        # Save button flashing animation
        self.save_button_flashing_animation = QTimer()
        self.save_button_flashing_animation.timeout.connect(
            partial(self.__flash_button, button=self.save_button)
        )

        # UPLOAD LOG BUTTON
        self.upload_rwlog_button = QPushButton("Upload logfile")
        self.upload_rwlog_button.setToolTip("Upload RimWorld log to 0x0.st")
        self.upload_rwlog_button.clicked.connect(
            partial(self.actions_signal.emit, "upload_rw_log")
        )

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
        self.bottom_panel.addWidget(self.run_button)
        self.bottom_panel.addWidget(self.save_button)
        self.bottom_panel.addWidget(self.upload_rwlog_button)

        logger.debug("Finished Actions initialization")

    def __flash_button(self, button: QPushButton) -> None:
        button.setObjectName(
            "%s" % ("" if button.objectName() == "indicator" else "indicator")
        )
        button.style().unpolish(button)
        button.style().polish(button)

    @property
    def panel(self) -> QVBoxLayout:
        return self._panel
