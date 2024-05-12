from functools import partial
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from loguru import logger

from app.controllers.menu_bar_controller import MenuBarController
from app.controllers.settings_controller import SettingsController
from app.models.dialogue import show_dialogue_input, show_fatal_error, show_warning
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus
from app.utils.gui_info import GUIInfo
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.utils.system_info import SystemInfo
from app.utils.watchdog import WatchdogHandler
from app.views.main_content_panel import MainContent
from app.views.menu_bar import MenuBar
from app.views.status_panel import Status


class MainWindow(QMainWindow):
    """
    Subclass QMainWindow to customize the main application window.
    """

    def __init__(
        self, settings_controller: SettingsController, debug_mode: bool = False
    ) -> None:
        """
        Initialize the main application window. Construct the layout,
        add the three main views, and set up relevant signals and slots.
        """
        logger.info("Initializing MainWindow")
        super(MainWindow, self).__init__()

        self.settings_controller = settings_controller

        # Create the main application window
        self.DEBUG_MODE = debug_mode
        # SteamCMD wrapper
        self.steamcmd_wrapper = SteamcmdInterface.instance()
        # Content initialization should only fire on startup. Otherwise, this is handled by Refresh button
        self.version_string = "Alpha-v1.0.6.2-hf"

        # Check for SHA and append to version string if found
        sha_file = str(AppInfo().application_folder / "SHA")
        if os.path.exists(sha_file):
            with open(sha_file, encoding="utf-8") as f:
                sha = f.read().strip()
            self.version_string += f" [Edge {sha}]"

        # Watchdog
        self.watchdog_event_handler: Optional[WatchdogHandler] = None

        # Set up the window
        self.setWindowTitle(f"RimSort {self.version_string}")
        self.setMinimumSize(QSize(1024, 768))

        # Create the window layout
        app_layout = QVBoxLayout()
        app_layout.setContentsMargins(0, 0, 0, 0)  # Space from main layout to border
        app_layout.setSpacing(0)  # Space between widgets

        # Create various panels on the application GUI
        self.main_content_panel = MainContent(
            settings_controller=self.settings_controller,
            version_string=self.version_string,
        )
        self.main_content_panel.disable_enable_widgets_signal.connect(
            self.__disable_enable_widgets
        )
        self.bottom_panel = Status()

        # Arrange all panels vertically on the main window layout
        app_layout.addWidget(self.main_content_panel.main_layout_frame)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(12, 12, 12, 12)
        button_layout.setSpacing(12)
        app_layout.addLayout(button_layout)

        self.game_version_label = QLabel()
        self.game_version_label.setFont(GUIInfo().smaller_font)
        self.game_version_label.setEnabled(False)
        button_layout.addWidget(self.game_version_label)

        button_layout.addStretch()

        # Define button attributes
        self.refresh_button = QPushButton("Refresh")
        self.clear_button = QPushButton("Clear")
        self.restore_button = QPushButton("Restore")
        self.sort_button = QPushButton("Sort")
        self.save_button = QPushButton("Save")
        self.run_button = QPushButton("Run")

        buttons = [
            self.refresh_button,
            self.clear_button,
            self.restore_button,
            self.sort_button,
            self.save_button,
            self.run_button,
        ]

        for button in buttons:
            button.setMinimumWidth(100)
            button_layout.addWidget(button)

        # Save button flashing animation
        self.save_button_flashing_animation = QTimer()
        self.save_button_flashing_animation.timeout.connect(
            partial(EventBus().do_button_animation.emit, self.save_button)
        )

        # Create the bottom panel
        app_layout.addWidget(self.bottom_panel.frame)

        # Display all items
        widget = QWidget()
        widget.setLayout(app_layout)
        self.setCentralWidget(widget)

        self.menu_bar = MenuBar(menu_bar=self.menuBar())
        self.menu_bar_controller = MenuBarController(
            view=self.menu_bar, settings_controller=self.settings_controller
        )
        # Connect Instances Menu Bar signals
        EventBus().do_activate_current_instance.connect(self.__switch_to_instance)
        EventBus().do_create_new_instance.connect(self.__create_new_instance)
        EventBus().do_delete_current_instance.connect(self.__delete_current_instance)

        self.setWindowTitle(f"RimSort {self.version_string}")
        self.setGeometry(100, 100, 1024, 768)
        logger.debug("Finished MainWindow initialization")

    def __disable_enable_widgets(self, enable: bool) -> None:
        # Disable widgets
        for widget in QApplication.instance().allWidgets():
            widget.setEnabled(enable)

    def showEvent(self, event: QShowEvent) -> None:
        # Call the original showEvent handler
        super().showEvent(event)

    def initialize_content(self) -> None:

        # POPULATE INSTANCES SUBMENU
        self.menu_bar_controller._on_instances_submenu_population(
            instance_names=list(self.settings_controller.settings.instances.keys())
        )
        self.menu_bar_controller._on_set_current_instance(
            self.settings_controller.settings.current_instance
        )

        # LOAD ANY CONFIGURED STEAMCMD PREFIX
        steamcmd_prefix = self.settings_controller.settings.instances[
            self.settings_controller.settings.current_instance
        ]["steamcmd_install_path"]
        if steamcmd_prefix and self.steamcmd_wrapper.check_for_steamcmd(
            steamcmd_prefix
        ):
            self.steamcmd_wrapper.initialize_prefix(
                steamcmd_prefix=steamcmd_prefix,
                validate=self.settings_controller.settings.steamcmd_validate_downloads,
            )
        else:
            self.steamcmd_wrapper.on_steamcmd_not_found()

        # IF CHECK FOR UPDATE ON STARTUP...
        if self.settings_controller.settings.check_for_update_startup:
            self.main_content_panel.actions_slot("check_for_update")

        # REFRESH CONFIGURED METADATA
        self.main_content_panel._do_refresh(is_initial=True)

        # CHECK USER PREFERENCE FOR WATCHDOG
        if self.settings_controller.settings.watchdog_toggle:
            # Check if watchdog is already running, restart if it is
            if (
                self.watchdog_event_handler is not None
                and self.watchdog_event_handler.watchdog_observer is not None
                and self.watchdog_event_handler.watchdog_observer.is_alive()
            ):
                self.shutdown_watchdog()
            # Setup watchdog
            self.__initialize_watchdog()

    def __initialize_watchdog(self) -> None:
        logger.info("Initializing watchdog FS Observer")
        # INITIALIZE WATCHDOG - WE WAIT TO START UNTIL DONE PARSING MOD LIST
        # Instantiate event handler
        # Pass a mapper of metadata-containing About.xml or Scenario.rsc files to their mod uuids
        current_instance = self.settings_controller.settings.current_instance
        self.watchdog_event_handler = WatchdogHandler(
            settings_controller=self.settings_controller,
            targets=[
                str(
                    Path(
                        self.settings_controller.settings.instances[current_instance][
                            "game_folder"
                        ]
                    )
                    / "Data"
                ),
                self.settings_controller.settings.instances[current_instance],
                self.settings_controller.settings.instances[current_instance][
                    "workshop_folder"
                ],
            ],
        )
        # Connect watchdog to MetadataManager
        self.watchdog_event_handler.mod_created.connect(
            self.main_content_panel.metadata_manager.process_creation
        )
        self.watchdog_event_handler.mod_deleted.connect(
            self.main_content_panel.metadata_manager.process_deletion
        )
        self.watchdog_event_handler.mod_updated.connect(
            self.main_content_panel.metadata_manager.process_update
        )
        # Connect main content signal so it can stop watchdog
        self.main_content_panel.stop_watchdog_signal.connect(self.shutdown_watchdog)
        # Start watchdog
        try:
            self.watchdog_event_handler.watchdog_observer.start()
        except Exception as e:
            logger.warning(
                f"Unable to initialize watchdog Observer due to exception: {str(e)}"
            )

    def __create_new_instance(self) -> None:
        instance_name, ok = show_dialogue_input(
            title="Create new instance",
            text="Enter name of new instance:",
        )
        current_instances = list(self.settings_controller.settings.instances.keys())
        if (
            ok
            and instance_name
            and instance_name != "Default"
            and instance_name not in current_instances
        ):
            self.settings_controller.settings.current_instance = instance_name
            self.settings_controller.settings.instances[instance_name] = {
                "game_folder": "",
                "local_folder": "",
                "workshop_folder": "",
                "config_folder": "",
                "run_args": [],
                "steamcmd_install_path": "",
            }
            # Save settings
            self.settings_controller.settings.save()
            # Initialize content
            self.initialize_content()
        else:
            show_warning(
                title="Error creating instance",
                text="Unable to create new instance.",
                information="Please enter a valid, unique instance name. It cannot be 'Default' or empty.",
            )

    def __delete_current_instance(self) -> None:
        if self.settings_controller.settings.current_instance == "Default":
            show_warning(
                title="Problem deleting instance",
                text=f"Unable to delete instance {self.settings_controller.settings.current_instance}.",
                information="The default instance cannot be deleted.",
            )
            return
        elif not self.settings_controller.settings.instances.get(
            self.settings_controller.settings.current_instance
        ):
            show_fatal_error(
                title="Error deleting instance",
                text=f"Unable to delete instance {self.settings_controller.settings.current_instance}.",
                information="The selected instance does not exist.",
            )
            return
        else:
            # Remove instance from settings and reset to Default
            self.settings_controller.settings.instances.pop(
                self.settings_controller.settings.current_instance
            )
            self.settings_controller.settings.current_instance = "Default"
            # Save settings
            self.settings_controller.settings.save()
            # Initialize content
            self.initialize_content()

    def __switch_to_instance(self, instance: str) -> None:
        # Set current instance
        self.settings_controller.settings.current_instance = instance
        # Save settings
        self.settings_controller.settings.save()
        # Initialize content
        self.initialize_content()

    def shutdown_watchdog(self) -> None:
        if (
            self.watchdog_event_handler
            and self.watchdog_event_handler.watchdog_observer
            and self.watchdog_event_handler.watchdog_observer.is_alive()
        ):
            self.watchdog_event_handler.watchdog_observer.stop()
            self.watchdog_event_handler.watchdog_observer.join()
            self.watchdog_event_handler.watchdog_observer = None
