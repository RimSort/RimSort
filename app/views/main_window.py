from functools import partial
import os
from pathlib import Path
from shutil import copytree, rmtree
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
from app.models.dialogue import (
    show_dialogue_conditional,
    show_dialogue_confirmation,
    show_dialogue_input,
    show_fatal_error,
    show_warning,
)
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
        # SteamCMDInterface
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
        EventBus().do_clone_existing_instance.connect(self.__clone_existing_instance)
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

    def initialize_content(self, is_initial: bool = True) -> None:
        # POPULATE INSTANCES SUBMENU
        self.menu_bar_controller._on_instances_submenu_population(
            instance_names=list(self.settings_controller.settings.instances.keys())
        )
        self.menu_bar_controller._on_set_current_instance(
            self.settings_controller.settings.current_instance
        )
        # IF CHECK FOR UPDATE ON STARTUP...
        if self.settings_controller.settings.check_for_update_startup:
            self.main_content_panel.actions_slot("check_for_update")
        # CHECK FOR STEAMCMD SETUP
        if not os.path.exists(
            self.steamcmd_wrapper.steamcmd_prefix
        ) or not self.steamcmd_wrapper.check_for_steamcmd(
            prefix=self.steamcmd_wrapper.steamcmd_prefix
        ):
            self.steamcmd_wrapper.on_steamcmd_not_found()
        else:
            self.steamcmd_wrapper.setup = True
        # REFRESH CONFIGURED METADATA
        self.main_content_panel._do_refresh(is_initial=is_initial)
        # CHECK USER PREFERENCE FOR WATCHDOG
        if self.settings_controller.settings.watchdog_toggle:
            # Setup watchdog
            self.initialize_watchdog()

    def __ask_for_new_instance_name(self) -> str:
        instance_name, cancelled = show_dialogue_input(
            title="Create new instance",
            text="Input a unique name of new instance that is not already used:",
        )
        return instance_name if not cancelled else None

    def __clone_existing_instance(self, existing_instance_name: str) -> None:
        # Check if paths are set. We can't clone if they aren't set
        if not self.main_content_panel.check_if_essential_paths_are_set(prompt=True):
            return
        # Get instance data from Settings
        current_instances = list(self.settings_controller.settings.instances.keys())
        existing_instance_game_folder = self.settings_controller.settings.instances[
            existing_instance_name
        ]["game_folder"]
        game_folder_name = os.path.split(existing_instance_game_folder)[1]
        existing_instance_local_folder = self.settings_controller.settings.instances[
            existing_instance_name
        ]["local_folder"]
        local_folder_name = os.path.split(existing_instance_local_folder)[1]
        existing_instance_workshop_folder = self.settings_controller.settings.instances[
            existing_instance_name
        ]["workshop_folder"]
        workshop_folder_name = os.path.split(existing_instance_workshop_folder)[1]
        existing_instance_config_folder = self.settings_controller.settings.instances[
            existing_instance_name
        ]["config_folder"]
        config_folder_name = os.path.split(existing_instance_config_folder)[1]
        existing_instance_run_args = self.settings_controller.settings.instances.get(
            existing_instance_name, {}
        ).get("run_args", [])
        existing_instance_steamcmd_install_path = (
            self.settings_controller.settings.instances[existing_instance_name][
                "steamcmd_install_path"
            ]
        )
        # Sanitize the input so that it does not produce any KeyError down the road
        new_instance_name = self.__ask_for_new_instance_name().strip()
        if (
            new_instance_name
            and new_instance_name != "Default"
            and new_instance_name not in current_instances
        ):
            new_instance_path = str(
                Path(AppInfo().app_storage_folder) / "instances" / new_instance_name
            )
            # Prompt user with the existing instance configuration and confirm that they would like to clone it
            answer = show_dialogue_confirmation(
                title=f"Clone instance {existing_instance_name}",
                text=f"Would you like to clone instance {existing_instance_name} to create new instance {new_instance_name}?"
                + "\n\n",
                information=f"Game folder: {existing_instance_game_folder if existing_instance_game_folder else '<None>'}\n"
                + f"Local folder: {existing_instance_local_folder if existing_instance_local_folder else '<None>'}\n"
                + f"Workshop folder: {existing_instance_workshop_folder if existing_instance_workshop_folder else '<None>'}\n"
                + f"Config folder: {existing_instance_config_folder if existing_instance_config_folder else '<None>'}\n"
                + f"Run args: {existing_instance_run_args if existing_instance_run_args else '<None>'}\n"
                + f"SteamCMD install path: {existing_instance_steamcmd_install_path if existing_instance_steamcmd_install_path else '<None>'}\n",
            )
            if answer == "&Yes":
                target_game_folder = str(Path(new_instance_path) / game_folder_name)
                target_local_folder = str(
                    Path(new_instance_path) / game_folder_name / local_folder_name
                )
                # target_workshop_folder = str(
                #     Path(new_instance_path) / workshop_folder_name
                # )
                target_workshop_folder = ""
                target_config_folder = str(Path(new_instance_path) / config_folder_name)
                # Clone the existing game_folder to the new instance
                if os.path.exists(existing_instance_game_folder) and os.path.isdir(
                    existing_instance_game_folder
                ):
                    if os.path.exists(target_game_folder) and os.path.isdir(
                        target_game_folder
                    ):
                        logger.info(
                            f"Replacing existing game folder at {target_game_folder}"
                        )
                        rmtree(target_game_folder)
                    logger.info(
                        f"Copying game folder from {existing_instance_game_folder} to {target_game_folder}"
                    )
                    copytree(
                        existing_instance_game_folder, target_game_folder, symlinks=True
                    )
                # Clone the existing config_folder to the new instance
                if os.path.exists(existing_instance_config_folder) and os.path.isdir(
                    existing_instance_config_folder
                ):
                    if os.path.exists(target_config_folder) and os.path.isdir(
                        target_config_folder
                    ):
                        logger.info(
                            f"Replacing existing config folder at {target_config_folder}"
                        )
                        rmtree(target_config_folder)
                    logger.info(
                        f"Copying config folder from {existing_instance_config_folder} to {target_config_folder}"
                    )
                    copytree(
                        existing_instance_config_folder,
                        target_config_folder,
                        symlinks=True,
                    )
                # Clone the existing local_folder to the new instance
                if existing_instance_local_folder:
                    if os.path.exists(existing_instance_local_folder) and os.path.isdir(
                        existing_instance_local_folder
                    ):
                        if os.path.exists(target_local_folder) and os.path.isdir(
                            target_local_folder
                        ):
                            logger.info(
                                f"Replacing existing local folder at {target_local_folder}"
                            )
                            rmtree(target_local_folder)
                        logger.info(
                            f"Copying local folder from {existing_instance_local_folder} to {target_local_folder}"
                        )
                        copytree(
                            existing_instance_local_folder,
                            target_local_folder,
                            symlinks=True,
                        )
                # Clone the existing workshop_folder to the new instance's local mods folder
                if existing_instance_workshop_folder:
                    # Prompt user to confirm before initiating the procedure
                    answer = show_dialogue_conditional(
                        title=f"Clone instance workshop folder {existing_instance_name}",
                        text=(
                            "Would you like to clone the existing instance's Workshop mods the new instance's local mods folder?"
                        ),
                    )
                    if answer == "&Yes":
                        if os.path.exists(
                            existing_instance_workshop_folder
                        ) and os.path.isdir(existing_instance_workshop_folder):
                            if not os.path.exists(target_local_folder):
                                os.mkdir(target_local_folder)
                            logger.info(
                                f"Cloning Workshop mods from {existing_instance_workshop_folder} to {target_local_folder}"
                            )
                            # Copy each subdirectory of the existing Workshop folder to the new local mods folder
                            for subdir in os.listdir(existing_instance_workshop_folder):
                                if os.path.isdir(
                                    os.path.join(
                                        existing_instance_workshop_folder, subdir
                                    )
                                ):
                                    copytree(
                                        os.path.join(
                                            existing_instance_workshop_folder, subdir
                                        ),
                                        os.path.join(target_local_folder, subdir),
                                        symlinks=True,
                                    )
                # If the instance has a 'steamcmd' folder, clone it to the new instance
                steamcmd_install_path = str(
                    Path(existing_instance_steamcmd_install_path) / "steamcmd"
                )
                if os.path.exists(steamcmd_install_path) and os.path.isdir(
                    steamcmd_install_path
                ):
                    target_steamcmd_install_path = str(
                        Path(new_instance_path) / "steamcmd"
                    )
                    if os.path.exists(target_steamcmd_install_path) and os.path.isdir(
                        target_steamcmd_install_path
                    ):
                        logger.info(
                            f"Replacing existing steamcmd folder at {target_steamcmd_install_path}"
                        )
                        rmtree(target_steamcmd_install_path)
                    logger.info(
                        f"Copying steamcmd folder from {steamcmd_install_path} to {target_steamcmd_install_path}"
                    )
                    copytree(
                        steamcmd_install_path,
                        target_steamcmd_install_path,
                        symlinks=True,
                    )
                # If the instance has a 'steam' folder, clone it to the new instance
                steam_install_path = str(
                    Path(existing_instance_steamcmd_install_path) / "steam"
                )
                if os.path.exists(steam_install_path) and os.path.isdir(
                    steam_install_path
                ):
                    target_steam_install_path = str(Path(new_instance_path) / "steam")
                    if os.path.exists(target_steam_install_path) and os.path.isdir(
                        target_steam_install_path
                    ):
                        logger.info(
                            f"Replacing existing steam folder at {target_steam_install_path}"
                        )
                        rmtree(target_steam_install_path)
                    logger.info(
                        f"Copying steam folder from {steam_install_path} to {target_steam_install_path}"
                    )
                    copytree(
                        steam_install_path, target_steam_install_path, symlinks=True
                    )
                    # Unlink steam/workshop/content/294100 symlink if it exists, and relink it to our new target local mods folder
                    link_path = str(
                        Path(target_steam_install_path)
                        / "workshop"
                        / "content"
                        / "294100"
                    )
                    if os.path.islink(link_path) or os.path.ismount(link_path):
                        logger.debug(
                            f"Unlinking {link_path} and relinking to {target_local_folder}"
                        )
                        os.remove(link_path)
                        if self.system != "Windows":
                            os.symlink(
                                target_local_folder,
                                link_path,
                                target_is_directory=True,
                            )
                        else:
                            from _winapi import CreateJunction

                            CreateJunction(target_local_folder, link_path)
                # Create the new instance for our cloned instance
                self.__create_new_instance(
                    instance_name=new_instance_name,
                    instance_data={
                        "game_folder": target_game_folder,
                        "local_folder": target_local_folder,
                        "workshop_folder": target_workshop_folder,
                        "config_folder": target_config_folder,
                        "run_args": existing_instance_run_args or [],
                    },
                )

    def __create_new_instance(
        self, instance_name: str = None, instance_data: dict = None
    ) -> None:
        if not instance_name:
            # Sanitize the input so that it does not produce any KeyError down the road
            instance_name = self.__ask_for_new_instance_name().strip()
        current_instances = list(self.settings_controller.settings.instances.keys())
        if (
            instance_name
            and instance_name != "Default"
            and instance_name not in current_instances
        ):
            if not instance_data:
                instance_data = {}
            # Create new instance folder if it does not exist
            instance_path = str(
                Path(AppInfo().app_storage_folder) / "instances" / instance_name
            )
            if not os.path.exists(instance_path):
                os.makedirs(instance_path)
            # Append new run args to the existing run args
            run_args = [
                "-logfile",
                str(Path(instance_path) / "RimWorld.log"),
                "-savedatafolder",
                instance_data.get("config_folder", ""),
            ]
            run_args.extend(instance_data.get("run_args", []))
            # Add new instance to Settings
            self.settings_controller.settings.instances[instance_name] = {
                "game_folder": instance_data.get("game_folder", ""),
                "local_folder": instance_data.get("local_folder", ""),
                "workshop_folder": instance_data.get("workshop_folder", ""),
                "config_folder": instance_data.get("config_folder", ""),
                "run_args": run_args,
                "steamcmd_install_path": instance_path,
            }
            # Save settings
            self.settings_controller.settings.save()
            # Switch to new instance and initialize content
            self.__switch_to_instance(instance_name)
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
            answer = show_dialogue_confirmation(
                title=f"Delete instance {self.settings_controller.settings.current_instance}",
                text="Are you sure you want to delete the selected instance and all of its data?",
                information="This action cannot be undone.",
            )
            if answer == "&Yes":
                try:
                    rmtree(
                        str(
                            Path(
                                AppInfo().app_storage_folder
                                / "instances"
                                / self.settings_controller.settings.current_instance
                            )
                        )
                    )
                except Exception as e:
                    logger.error(f"Error deleting instance: {e}")
                # Remove instance from settings and reset to Default
                self.settings_controller.settings.instances.pop(
                    self.settings_controller.settings.current_instance
                )
                self.__switch_to_instance("Default")

    def __switch_to_instance(self, instance: str) -> None:
        self.stop_watchdog_if_running()
        # Set current instance
        self.settings_controller.settings.current_instance = instance
        # Save settings
        self.settings_controller.settings.save()
        # Initialize content
        self.initialize_content(is_initial=False)

    def initialize_watchdog(self) -> None:
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

    def stop_watchdog_if_running(self) -> None:
        # STOP WATCHDOG IF IT IS ALREADY RUNNING
        if (
            self.watchdog_event_handler
            and self.watchdog_event_handler.watchdog_observer
            and self.watchdog_event_handler.watchdog_observer.is_alive()
        ):
            self.shutdown_watchdog()

    def shutdown_watchdog(self) -> None:
        if (
            self.watchdog_event_handler
            and self.watchdog_event_handler.watchdog_observer
            and self.watchdog_event_handler.watchdog_observer.is_alive()
        ):
            self.watchdog_event_handler.watchdog_observer.stop()
            self.watchdog_event_handler.watchdog_observer.join()
            self.watchdog_event_handler.watchdog_observer = None
            for timer in self.watchdog_event_handler.cooldown_timers.values():
                timer.cancel()
            self.watchdog_event_handler = None
