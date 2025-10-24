import os
from functools import partial
from pathlib import Path
from shutil import copytree, rmtree
from traceback import format_exc
from typing import Any

from loguru import logger
from PySide6.QtCore import QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.controllers.file_search_controller import FileSearchController
from app.controllers.instance_controller import (
    InstanceController,
    InvalidArchivePathError,
)
from app.controllers.main_content_controller import MainContentController
from app.controllers.menu_bar_controller import MenuBarController
from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.mods_panel_controller import ModsPanelController
from app.controllers.settings_controller import SettingsController
from app.controllers.troubleshooting_controller import TroubleshootingController
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus
from app.utils.generic import handle_remove_read_only
from app.utils.gui_info import GUIInfo
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.utils.watchdog import WatchdogHandler
from app.views.acf_log_reader import AcfLogReader
from app.views.dialogue import (
    BinaryChoiceDialog,
    show_dialogue_conditional,
    show_dialogue_file,
    show_dialogue_input,
    show_fatal_error,
    show_warning,
)
from app.views.file_search_dialog import FileSearchDialog
from app.views.main_content_panel import MainContent
from app.views.menu_bar import MenuBar
from app.views.player_log_tab import PlayerLogTab
from app.views.status_panel import Status
from app.views.troubleshooting_dialog import TroubleshootingDialog


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

        # Watchdog
        self.watchdog_event_handler: WatchdogHandler | None = None
        # Set up the window
        current_instance = self.settings_controller.settings.current_instance
        self.__set_window_title(current_instance)

        # Create the window layout
        app_layout = QVBoxLayout()
        app_layout.setContentsMargins(0, 0, 0, 0)  # Space from main layout to border
        app_layout.setSpacing(0)  # Space between widgets

        # Create a tab widget
        self.tab_widget = QTabWidget()
        app_layout.addWidget(self.tab_widget)

        # Create various panels on the application GUI
        self.main_content_panel: MainContent = MainContent(
            settings_controller=self.settings_controller
        )
        self.main_content_panel.disable_enable_widgets_signal.connect(
            self.__disable_enable_widgets
        )
        self.bottom_panel = Status()

        # Create and add the Main Content panel tab
        self.main_content_tab = QWidget()
        self.main_content_layout = QVBoxLayout()
        self.main_content_tab.setLayout(self.main_content_layout)

        # Add the MainContent panel to the tab
        self.main_content_layout.addWidget(self.main_content_panel.main_layout_frame)

        # Create button layout and add it to the main content layout
        button_layout = QHBoxLayout()
        self.main_content_layout.addLayout(button_layout)

        self.game_version_label = QLabel()
        self.game_version_label.setFont(GUIInfo().smaller_font)
        self.game_version_label.setEnabled(False)
        button_layout.addWidget(self.game_version_label)

        button_layout.addStretch()

        # Define button attributes
        self.refresh_button = QPushButton(self.tr("Refresh"))
        self.clear_button = QPushButton(self.tr("Clear"))
        self.restore_button = QPushButton(self.tr("Restore"))
        self.sort_button = QPushButton(self.tr("Sort"))
        self.save_button = QPushButton(self.tr("Save"))
        self.run_button = QPushButton(self.tr("Run"))

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

        self.tab_widget.addTab(self.main_content_tab, self.tr("Main Content"))

        # Create and add the ACF Data tab
        self.acf_log_reader_tab = QWidget()
        self.acf_log_reader_layout = QVBoxLayout()
        self.acf_log_reader_tab.setLayout(self.acf_log_reader_layout)

        # Instantiate the AcfDataWindow and add it to the tab
        self.acf_log_reader = AcfLogReader(
            settings_controller,
            active_mods_list=self.main_content_panel.mods_panel.active_mods_list,
        )
        self.acf_log_reader_layout.addWidget(self.acf_log_reader)

        self.tab_widget.addTab(self.acf_log_reader_tab, self.tr("ACF Log Reader"))

        # Create and add the Player Log tab
        self.player_log_widget = PlayerLogTab(self.settings_controller)
        self.tab_widget.addTab(self.player_log_widget, self.tr("Player Log"))

        # Create and add the Search tab
        self.file_search_tab = QWidget()
        self.file_search_layout = QVBoxLayout()
        self.file_search_tab.setLayout(self.file_search_layout)

        # Instantiate the SearchWindow and add it to the tab
        self.file_search_dialog = FileSearchDialog()
        self.file_search_controller = FileSearchController(
            settings=self.settings_controller.settings,
            settings_controller=self.settings_controller,
            dialog=self.file_search_dialog,
        )
        self.file_search_layout.addWidget(self.file_search_dialog)

        self.tab_widget.addTab(self.file_search_tab, self.tr("File Search"))

        # Create and add the Troubleshooting tab
        self.troubleshooting_tab = QWidget()
        self.troubleshooting_layout = QVBoxLayout()
        self.troubleshooting_tab.setLayout(self.troubleshooting_layout)

        # Instantiate the TroubleshootingDialog and add it to the tab
        self.troubleshooting_dialog = TroubleshootingDialog()
        self.troubleshooting_controller = TroubleshootingController(
            settings=self.settings_controller.settings,
            dialog=self.troubleshooting_dialog,
        )
        self.troubleshooting_layout.addWidget(self.troubleshooting_dialog)
        self.tab_widget.addTab(self.troubleshooting_tab, self.tr("Troubleshooting"))

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

        self.mods_panel_controller = ModsPanelController(
            view=self.main_content_panel.mods_panel,
            settings_controller=self.settings_controller,
        )

        self.menu_bar = MenuBar(
            menu_bar=self.menuBar(), settings_controller=self.settings_controller
        )
        self.menu_bar_controller = MenuBarController(
            view=self.menu_bar,
            settings_controller=self.settings_controller,
        )

        self.main_content_controller = MainContentController(
            view=self.main_content_panel,
            settings_controller=self.settings_controller,
        )

        # Connect Instances Menu Bar signals
        EventBus().do_activate_current_instance.connect(self.__switch_to_instance)
        EventBus().do_backup_existing_instance.connect(self.__backup_existing_instance)
        EventBus().do_clone_existing_instance.connect(self.__clone_existing_instance)
        EventBus().do_create_new_instance.connect(self.__create_new_instance)
        EventBus().do_delete_current_instance.connect(self.__delete_current_instance)
        EventBus().do_restore_instance_from_archive.connect(
            self.__restore_instance_from_archive
        )

        # launch the main window
        self._launch_main_window()
        logger.debug("Finished MainWindow initialization")

    def _launch_main_window(self) -> None:
        """Apply main window launch state from settings"""
        from app.utils.window_launch_state import apply_window_launch_state

        main_window_launch_state = (
            self.settings_controller.settings.main_window_launch_state
        )
        custom_width = self.settings_controller.settings.main_window_custom_width
        custom_height = self.settings_controller.settings.main_window_custom_height

        apply_window_launch_state(
            self, main_window_launch_state, custom_width, custom_height
        )
        logger.info(
            f"Main window started with launch state: {main_window_launch_state}"
        )

    def __disable_enable_widgets(self, enable: bool) -> None:
        # Disable widgets
        q_app = QApplication.instance()
        if not isinstance(q_app, QApplication):
            return
        for widget in q_app.allWidgets():
            widget.setEnabled(enable)

    def showEvent(self, event: QShowEvent) -> None:
        # Call the original showEvent handler
        super().showEvent(event)

    def initialize_content(self, is_initial: bool = True) -> None:
        # Set all items as outdated in aux DB
        EventBus().do_set_all_entries_in_aux_db_as_outdated.emit()
        # POPULATE INSTANCES SUBMENU
        self.menu_bar_controller._on_instances_submenu_population(
            instance_names=list(self.settings_controller.settings.instances.keys())
        )
        self.menu_bar_controller._on_set_current_instance(
            self.settings_controller.settings.current_instance
        )
        # REFRESH CONFIGURED METADATA
        self.main_content_panel._do_refresh(is_initial=is_initial)
        # CHECK FOR STEAMCMD SETUP
        if not os.path.exists(
            self.steamcmd_wrapper.steamcmd_prefix
        ) or not self.steamcmd_wrapper.check_for_steamcmd(
            prefix=self.steamcmd_wrapper.steamcmd_prefix
        ):
            if not self.settings_controller.active_instance.steamcmd_ignore:
                self.steamcmd_wrapper.on_steamcmd_not_found(
                    ask_ignore=True, settings_controller=self.settings_controller
                )
        else:
            self.steamcmd_wrapper.setup = True

        # UPDATE DATABASES ON STARTUP IF ENABLED
        # This is called here after all controllers are initialized and signals are connected
        if is_initial:
            self.main_content_controller._update_databases_on_startup_if_enabled_silent()

        # CHECK USER PREFERENCE FOR WATCHDOG
        if self.settings_controller.settings.watchdog_toggle:
            # Setup watchdog
            self.initialize_watchdog()

        self.__check_steam_integration()

        # Force initial setup to False and save settings
        if self.settings_controller.active_instance.initial_setup:
            self.settings_controller.active_instance.initial_setup = False
            self.settings_controller.settings.save()
        # IF CHECK FOR UPDATE ON STARTUP...
        if self.settings_controller.settings.check_for_update_startup:
            EventBus().do_check_for_application_update.emit()
        # Delete outdated entries in aux DB
        EventBus().do_delete_outdated_entries_in_aux_db.emit()

    def __check_steam_integration(self) -> None:
        """Ask the user if they would like to enable Steam Client Integration for the active instance if it is the first time they are setting up RimSort."""
        instance = self.settings_controller.active_instance

        if instance.initial_setup and not instance.steam_client_integration:
            diag = BinaryChoiceDialog(
                title=self.tr("Steam Client Integration"),
                text=self.tr(
                    "<h3>Would you like to enable Steam Client Integration for this instance?</h3>"
                ),
                information=self.tr("""This will allow you to use RimSort features that require the Steam Client. This includes, among other things, unsubscribing from workshop mods and opening workshop links via the Steam Client. 
                <br><br>
                You can change this in the settings under the Advanced tab."""),
                negative_text="No",
            )
            if diag.exec_is_positive():
                instance.steam_client_integration = True
                self.settings_controller.set_instance(instance)

        return

    def __ask_for_new_instance_name(self) -> str | None:
        instance_name, ok = show_dialogue_input(
            title=self.tr("Create new instance"),
            label=self.tr(
                "Input a unique name of new instance that is not already used:"
            ),
        )
        return instance_name.strip() if ok else None

    def __ask_for_non_default_instance_name(self) -> str | None:
        while True:
            instance_name, ok = show_dialogue_input(
                title=self.tr("Provide instance name"),
                label=self.tr(
                    'Input a unique name for the backed up instance that is not "Default"'
                ),
            )
            if ok and instance_name.lower() != "default":
                return instance_name
            else:
                return None

    def __ask_how_to_workshop_mods(
        self, existing_instance_name: str, existing_instance_workshop_folder: str
    ) -> str:
        answer = show_dialogue_conditional(
            title=self.tr("Clone instance [{existing_instance_name}]").format(
                existing_instance_name=existing_instance_name
            ),
            text=(
                self.tr(
                    "What would you like to do with the configured Workshop mods folder?"
                )
            ),
            information=(
                self.tr(
                    "Workshop folder: {existing_instance_workshop_folder}\n\n"
                    + "RimSort can copy all of your Workshop mods to the new instance's local mods folder. This will effectively "
                    + " convert any existing Steam client mods to SteamCMD mods that you can then  manage inside the new instance.\n\n"
                    + "Alternatively, you may keep your old Steam workshop folder preference. You can always change this later in the settings.\n\n"
                    + "How would you like to proceed?"
                ).format(
                    existing_instance_workshop_folder=existing_instance_workshop_folder
                )
            ),
            button_text_override=[
                self.tr("Convert to SteamCMD"),
                self.tr("Keep Workshop Folder"),
            ],
        )
        answer_str = str(answer)
        cancelled_str = self.tr("Cancelled")
        return answer_str or cancelled_str

    def __backup_existing_instance(self, instance_name: str) -> None:
        # Get instance data from Settings
        instance = self.settings_controller.settings.instances.get(instance_name)

        # If the instance_name is "Default", prompt the user for a new instance name.
        if instance_name == "Default":
            new_instance_name = self.__ask_for_non_default_instance_name()
            if not new_instance_name:
                logger.info("User cancelled operation")
                return
            instance_name = new_instance_name

        # Determine instance data to save
        if instance is None:
            logger.error(f"Instance [{instance_name}] not found in Settings")
            return

        instance_controller = InstanceController(instance)
        # Prompt user to select output path for instance archive
        output_path = show_dialogue_file(
            mode="save",
            caption="Select output path for instance archive",
            _dir=str(AppInfo().app_storage_folder),
            _filter="Zip files (*.zip)",
        )
        logger.info(f"Selected path: {output_path}")
        if output_path:
            try:
                EventBus().do_threaded_loading_animation.emit(
                    str(AppInfo().theme_data_folder / "default-icons" / "rimsort.gif"),
                    partial(
                        instance_controller.compress_to_archive,
                        output_path,
                    ),
                    self.tr(
                        "Compressing [{instance_name}] instance folder to archive..."
                    ).format(instance_name=instance_name),
                )
            except Exception as e:
                show_fatal_error(
                    title=self.tr("Error compressing instance"),
                    text=self.tr(
                        "An error occurred while compressing instance folder: {e}"
                    ).format(e=e),
                    information=self.tr("Please check the logs for more information."),
                    details=format_exc(),
                )
        else:
            logger.warning("Backup cancelled: User cancelled selection...")
            return

    def __restore_instance_from_archive(self) -> None:
        # Prompt user to select input path for instance archive
        input_path = show_dialogue_file(
            mode="open",
            caption="Select input path for instance archive",
            _dir=str(AppInfo().app_storage_folder),
            _filter="Zip files (*.zip)",
        )

        if input_path is None:
            logger.info("User cancelled operation. Input path was None")
            return
        logger.info(f"Selected path: {input_path}")

        if not os.path.exists(input_path):
            logger.error(f"Archive not found at path: {input_path}")
            show_warning(
                title=self.tr("Error restoring instance"),
                text=self.tr("Archive not found at path: {input_path}").format(
                    input_path=input_path
                ),
            )
            return

        # Grab the instance name from the archive's "instance.json" file and extract archive
        try:
            instance_controller = InstanceController(input_path)
        except InvalidArchivePathError as _:
            # Handled in controller. Gracefully fail.
            return
        except Exception as e:
            logger.error(f"An error occurred while reading instance archive: {e}")
            show_fatal_error(
                title=self.tr("Error restoring instance"),
                text=self.tr("An error occurred while reading instance archive: {e}"),
                details=format_exc(),
            )
            return

        if os.path.exists(instance_controller.instance_folder_path):
            answer = show_dialogue_conditional(
                title=self.tr("Instance folder exists"),
                text=self.tr(
                    "Instance folder already exists: {instance_folder_path}"
                ).format(instance_folder_path=instance_controller.instance_folder_path),
                information=self.tr(
                    "Do you want to continue and replace the existing instance folder?"
                ),
                button_text_override=[
                    self.tr("Replace"),
                ],
            )

            if answer != self.tr("Replace"):
                logger.info("User cancelled instance extraction.")
                return

        EventBus().do_threaded_loading_animation.emit(
            str(AppInfo().theme_data_folder / "default-icons" / "rimsort.gif"),
            partial(
                instance_controller.extract_from_archive,
                input_path,
            ),
            self.tr("Restoring instance [{name}] from archive...").format(
                name=instance_controller.instance.name
            ),
        )

        # Check that the instance folder exists. If it does, update Settings with the instance data
        if os.path.exists(instance_controller.instance_folder_path):
            cleared_paths = instance_controller.validate_paths()
            if cleared_paths:
                logger.warning(
                    f"Instance folder paths not found: {', '.join(cleared_paths)}"
                )
                show_warning(
                    title=self.tr("Invalid instance folder paths"),
                    text=self.tr("Invalid instance folder paths"),
                    information=self.tr(
                        "Some folder paths from the restored instance are invalid and were cleared. Please reconfigure them in the settings"
                    ),
                    details=self.tr("Invalid paths: {path}").format(
                        path=", ".join(cleared_paths)
                    ),
                )

            steamcmd_link_path = str(
                Path(instance_controller.instance.steamcmd_install_path)
                / "steam"
                / "steamapps"
                / "workshop"
                / "content"
                / "294100"
            )

            if (
                os.path.exists(steamcmd_link_path)
                and instance_controller.instance.local_folder != ""
            ):
                logger.info("Restoring steamcmd symlink...")
                self.steamcmd_wrapper.create_symlink(
                    instance_controller.instance.local_folder,
                    steamcmd_link_path,
                    show_dialogues=False,
                    force=True,
                )
            elif not os.path.exists(steamcmd_link_path):
                logger.info("Skipping steamcmd symlink restoration")
            else:
                show_warning(
                    title=self.tr("Couldn't restore steamcmd symlink/junction"),
                    text=self.tr("Couldn't restore steamcmd symlink/junction"),
                    information=self.tr(
                        "The steamcmd symlink/junction could not be restored as the local folder is not set or invalid. The symlink/junction will need to be manually recreated."
                    ),
                )
                logger.warning(
                    "Skipping steamcmd symlink restoration: Local folder not set. The symlink will need to be manually updated."
                )

            self.settings_controller.set_instance(instance_controller.instance)
            self.__switch_to_instance(instance_controller.instance.name)
        else:
            show_warning(
                title=self.tr("Error restoring instance"),
                text=self.tr(
                    "An error occurred while restoring instance [{name}]."
                ).format(name=instance_controller.instance.name),
                information=self.tr(
                    "The instance folder was not found after extracting the archive. Perhaps the archive is corrupt or the instance name is invalid."
                ),
            )

            logger.warning(
                "Restore cancelled: Instance folder not found after extraction..."
            )

    def __clone_existing_instance(self, existing_instance_name: str) -> None:
        def copy_game_folder(
            existing_instance_game_folder: str, target_game_folder: str
        ) -> None:
            try:
                if os.path.exists(target_game_folder) and os.path.isdir(
                    target_game_folder
                ):
                    logger.info(
                        f"Replacing existing game folder at {target_game_folder}"
                    )
                    rmtree(
                        target_game_folder,
                        ignore_errors=False,
                        onerror=handle_remove_read_only,
                    )
                logger.info(
                    f"Copying game folder from {existing_instance_game_folder} to {target_game_folder}"
                )
                copytree(
                    existing_instance_game_folder, target_game_folder, symlinks=True
                )
            except Exception as e:
                logger.error(f"An error occurred while copying game folder: {e}")

        def copy_config_folder(
            existing_instance_config_folder: str, target_config_folder: str
        ) -> None:
            try:
                if os.path.exists(target_config_folder) and os.path.isdir(
                    target_config_folder
                ):
                    logger.info(
                        f"Replacing existing config folder at {target_config_folder}"
                    )
                    rmtree(
                        target_config_folder,
                        ignore_errors=False,
                        onerror=handle_remove_read_only,
                    )
                logger.info(
                    f"Copying config folder from {existing_instance_config_folder} to {target_config_folder}"
                )
                copytree(
                    existing_instance_config_folder,
                    target_config_folder,
                    symlinks=True,
                )
            except Exception as e:
                logger.error(f"An error occurred while copying config folder: {e}")

        def copy_local_folder(
            existing_instance_local_folder: str, target_local_folder: str
        ) -> None:
            try:
                if os.path.exists(target_local_folder) and os.path.isdir(
                    target_local_folder
                ):
                    logger.info(
                        f"Replacing existing local folder at {target_local_folder}"
                    )
                    rmtree(
                        target_local_folder,
                        ignore_errors=False,
                        onerror=handle_remove_read_only,
                    )
                logger.info(
                    f"Copying local folder from {existing_instance_local_folder} to {target_local_folder}"
                )
                copytree(
                    existing_instance_local_folder,
                    target_local_folder,
                    symlinks=True,
                )
            except Exception as e:
                logger.error(f"An error occurred while copying local folder: {e}")

        def copy_workshop_mods_to_local(
            existing_instance_workshop_folder: str, target_local_folder: str
        ) -> None:
            try:
                if not os.path.exists(target_local_folder):
                    os.mkdir(target_local_folder)
                logger.info(
                    f"Cloning Workshop mods from {existing_instance_workshop_folder} to {target_local_folder}"
                )
                # Copy each subdirectory of the existing Workshop folder to the new local mods folder
                for subdir in os.listdir(existing_instance_workshop_folder):
                    if os.path.isdir(
                        os.path.join(existing_instance_workshop_folder, subdir)
                    ):
                        logger.debug(f"Cloning Workshop mod: {subdir}")
                        copytree(
                            os.path.join(existing_instance_workshop_folder, subdir),
                            os.path.join(target_local_folder, subdir),
                            symlinks=True,
                        )
            except Exception as e:
                logger.error(f"An error occurred while cloning Workshop mods: {e}")

        def clone_essential_paths(
            existing_instance_game_folder: str,
            target_game_folder: str,
            existing_instance_config_folder: str,
            target_config_folder: str,
        ) -> None:
            # Clone the existing game_folder to the new instance
            if os.path.exists(existing_instance_game_folder) and os.path.isdir(
                existing_instance_game_folder
            ):
                copy_game_folder(existing_instance_game_folder, target_game_folder)
            # Clone the existing config_folder to the new instance
            if os.path.exists(existing_instance_config_folder) and os.path.isdir(
                existing_instance_config_folder
            ):
                copy_config_folder(
                    existing_instance_config_folder, target_config_folder
                )

        # Check if paths are set. We can't clone if they aren't set
        if not self.main_content_panel.check_if_essential_paths_are_set(prompt=True):
            return
        # Get instance data from Settings
        current_instances = list(self.settings_controller.settings.instances.keys())
        existing_instance_game_folder = self.settings_controller.settings.instances[
            existing_instance_name
        ].game_folder
        game_folder_name = os.path.split(existing_instance_game_folder)[1]
        existing_instance_local_folder = self.settings_controller.settings.instances[
            existing_instance_name
        ].local_folder
        local_folder_name = os.path.split(existing_instance_local_folder)[1]
        existing_instance_workshop_folder = self.settings_controller.settings.instances[
            existing_instance_name
        ].workshop_folder
        existing_instance_config_folder = self.settings_controller.settings.instances[
            existing_instance_name
        ].config_folder
        existing_instance_run_args = self.settings_controller.settings.instances[
            existing_instance_name
        ].run_args
        existing_instance_steamcmd_install_path = (
            self.settings_controller.settings.instances[
                existing_instance_name
            ].steamcmd_install_path
        )
        existing_instance_steam_client_integration = (
            self.settings_controller.settings.instances[
                existing_instance_name
            ].steam_client_integration
        )
        # Sanitize the input so that it does not produce any KeyError down the road
        new_instance_name = self.__ask_for_new_instance_name()
        if (
            new_instance_name
            and new_instance_name != "Default"
            and new_instance_name not in current_instances
        ):
            new_instance_path = str(
                Path(AppInfo().app_storage_folder) / "instances" / new_instance_name
            )
            # Prompt user with the existing instance configuration and confirm that they would like to clone it
            answer = BinaryChoiceDialog(
                title=f"Clone instance [{existing_instance_name}]",
                text=f"Would you like to clone instance [{existing_instance_name}] to create new instance [{new_instance_name}]?\n"
                + "This will clone the instance's data!"
                + "\n\n",
                information=f"Game folder:\n{existing_instance_game_folder if existing_instance_game_folder else '<None>'}\n"
                + f"\nLocal folder:\n{existing_instance_local_folder if existing_instance_local_folder else '<None>'}\n"
                + f"\nWorkshop folder:\n{existing_instance_workshop_folder if existing_instance_workshop_folder else '<None>'}\n"
                + f"\nConfig folder:\n{existing_instance_config_folder if existing_instance_config_folder else '<None>'}\n"
                + f"\nRun args:\n{'[' + ' '.join(existing_instance_run_args) + ']' if existing_instance_run_args else '<None>'}\n"
                + "\nSteamCMD install path (steamcmd + steam folders will be cloned):"
                + f"\n{existing_instance_steamcmd_install_path if existing_instance_steamcmd_install_path else '<None>'}\n",
            )
            if answer.exec_is_positive():
                # Clone the RimWorld game_folder to the new instance
                target_game_folder = str(Path(new_instance_path) / game_folder_name)
                target_local_folder = str(
                    Path(new_instance_path) / game_folder_name / local_folder_name
                )
                target_workshop_folder = ""
                target_config_folder = str(
                    Path(new_instance_path) / "InstanceData" / "Config"
                )
                EventBus().do_threaded_loading_animation.emit(
                    str(AppInfo().theme_data_folder / "default-icons" / "rimworld.gif"),
                    partial(
                        clone_essential_paths,
                        existing_instance_game_folder,
                        target_game_folder,
                        existing_instance_config_folder,
                        target_config_folder,
                    ),
                    f"Cloning RimWorld game / config folders from [{existing_instance_name}] to [{new_instance_name}] instance...",
                )
                # Clone the existing local_folder to the new instance
                if existing_instance_local_folder:
                    if os.path.exists(existing_instance_local_folder) and os.path.isdir(
                        existing_instance_local_folder
                    ):
                        EventBus().do_threaded_loading_animation.emit(
                            str(
                                AppInfo().theme_data_folder
                                / "default-icons"
                                / "rimworld.gif"
                            ),
                            partial(
                                copy_local_folder,
                                existing_instance_local_folder,
                                target_local_folder,
                            ),
                            f"Cloning local mods folder from [{existing_instance_name}] instance to [{new_instance_name}] instance...",
                        )
                # Clone the existing workshop_folder to the new instance's local mods folder
                if existing_instance_workshop_folder:
                    # Prompt user to confirm before initiating the procedure
                    answer_workshop_mods: str = self.__ask_how_to_workshop_mods(
                        existing_instance_name=existing_instance_name,
                        existing_instance_workshop_folder=existing_instance_workshop_folder,
                    )
                    if answer_workshop_mods == self.tr("Convert to SteamCMD"):
                        if os.path.exists(
                            existing_instance_workshop_folder
                        ) and os.path.isdir(existing_instance_workshop_folder):
                            EventBus().do_threaded_loading_animation.emit(
                                str(
                                    AppInfo().theme_data_folder
                                    / "default-icons"
                                    / "steam_api.gif"
                                ),
                                partial(
                                    copy_workshop_mods_to_local,
                                    existing_instance_workshop_folder,
                                    target_local_folder,
                                ),
                                f"Cloning Workshop mods from [{existing_instance_name}] instance to [{new_instance_name}] instance's local mods...",
                            )
                        else:
                            show_warning(
                                title=self.tr("Workshop mods not found"),
                                text=self.tr(
                                    "Workshop mods folder at [{existing_instance_workshop_folder}] not found."
                                ).format(
                                    existing_instance_workshop_folder=existing_instance_workshop_folder
                                ),
                            )
                    elif answer_workshop_mods == self.tr("Keep Workshop Folder"):
                        target_workshop_folder = str(existing_instance_workshop_folder)
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
                        rmtree(
                            target_steamcmd_install_path,
                            ignore_errors=False,
                            onerror=handle_remove_read_only,
                        )
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
                        rmtree(
                            target_steam_install_path,
                            ignore_errors=False,
                            onerror=handle_remove_read_only,
                        )
                    logger.info(
                        f"Copying steam folder from {steam_install_path} to {target_steam_install_path}"
                    )
                    # Copy the directory, but omit the symlink path
                    copytree(
                        steam_install_path,
                        target_steam_install_path,
                        symlinks=True,
                        ignore=lambda d, names: ["steamapps/workshop/content/294100"]
                        if d == steam_install_path
                        else [],
                    )
                    # Unlink steam/workshop/content/294100 symlink if it exists, and relink it to our new target local mods folder
                    link_path = str(
                        Path(target_steam_install_path)
                        / "steamapps"
                        / "workshop"
                        / "content"
                        / "294100"
                    )
                    self.steamcmd_wrapper.create_symlink(
                        target_local_folder, link_path, show_dialogues=False, force=True
                    )
                # Create the new instance for our cloned instance
                self.__create_new_instance(
                    instance_name=new_instance_name,
                    instance_data={
                        "game_folder": target_game_folder,
                        "local_folder": target_local_folder,
                        "workshop_folder": target_workshop_folder,
                        "config_folder": target_config_folder,
                        "run_args": existing_instance_run_args or [],
                        "steamcmd_install_path": str(
                            AppInfo().app_storage_folder
                            / "instances"
                            / new_instance_name
                        ),
                        "steam_client_integration": existing_instance_steam_client_integration,
                    },
                )
        elif new_instance_name:
            show_warning(
                title=self.tr("Error cloning instance"),
                text=self.tr("Unable to clone instance."),
                information=self.tr(
                    "Please enter a valid, unique instance name. It cannot be 'Default' or empty."
                ),
            )
        else:
            logger.debug("User cancelled clone operation")

    def __create_new_instance(
        self, instance_name: str = "", instance_data: dict[str, Any] = {}
    ) -> None:
        if not instance_name:
            # Sanitize the input so that it does not produce any KeyError down the road
            new_instance_name = self.__ask_for_new_instance_name()
            if not new_instance_name:
                logger.info("User cancelled operation")
                return
            instance_name = new_instance_name
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
            # Get run args from instance data, autogenerate additional config items if desired
            run_args = []
            generated_instance_run_args = []
            if instance_data.get("game_folder") and instance_data.get("config_folder"):
                # Prompt the user if they would like to automatically generate run args for the instance
                answer = show_dialogue_conditional(
                    title=self.tr("Create new instance [{instance_name}]"),
                    text=self.tr(
                        "Would you like to automatically generate run args for the new instance?"
                    ),
                    information=self.tr(
                        "This will try to generate run args for the new instance based on the configured Game/Config folders."
                    ),
                )
                if answer == QMessageBox.StandardButton.Yes:
                    # Append new run args to the existing run args
                    generated_instance_run_args = [
                        "-logfile",
                        str(Path(instance_path) / "RimWorld.log"),
                        f"-savedatafolder={str(Path(instance_path) / 'InstanceData')}",
                    ]
                run_args.extend(generated_instance_run_args)
                run_args.extend(instance_data.get("run_args", []))
            # Add new instance to Settings
            self.settings_controller.create_instance(
                instance_name=instance_name,
                game_folder=instance_data.get("game_folder", ""),
                local_folder=instance_data.get("local_folder", ""),
                workshop_folder=instance_data.get("workshop_folder", ""),
                config_folder=instance_data.get("config_folder", ""),
                run_args=run_args,
                steamcmd_install_path=instance_path,
                steam_client_integration=instance_data.get(
                    "steam_client_integration", False
                ),
            )

            # Save settings
            self.settings_controller.settings.save()
            # Switch to new instance and initialize content
            self.__switch_to_instance(instance_name)
        else:
            show_warning(
                title=self.tr("Error creating instance"),
                text=self.tr("Unable to create new instance."),
                information=self.tr(
                    "Please enter a valid, unique instance name. It cannot be 'Default' or empty."
                ),
            )

    def __delete_current_instance(self) -> None:
        if self.settings_controller.settings.current_instance == "Default":
            show_warning(
                title=self.tr("Problem deleting instance"),
                text=self.tr("Unable to delete instance {current_instance}.").format(
                    current_instance=self.settings_controller.settings.current_instance
                ),
                information=self.tr("The default instance cannot be deleted."),
            )
            return
        elif not self.settings_controller.settings.instances.get(
            self.settings_controller.settings.current_instance
        ):
            show_fatal_error(
                title=self.tr("Error deleting instance"),
                text=self.tr("Unable to delete instance {current_instance}.").format(
                    current_instance=self.settings_controller.settings.current_instance
                ),
                information=self.tr("The selected instance does not exist."),
            )
            return
        else:
            answer = BinaryChoiceDialog(
                title=self.tr("Delete instance {current_instance}").format(
                    current_instance=self.settings_controller.settings.current_instance
                ),
                text=self.tr(
                    "Are you sure you want to delete the selected instance and all of its data?"
                ),
                information=self.tr("This action cannot be undone."),
            )
            if answer.exec_is_positive():
                aux_metadata_controller = (
                    AuxMetadataController.get_or_create_cached_instance(
                        self.settings_controller.settings.aux_db_path
                    )
                )
                aux_metadata_controller.engine.dispose()
                try:
                    rmtree(
                        str(
                            Path(
                                AppInfo().app_storage_folder
                                / "instances"
                                / self.settings_controller.settings.current_instance
                            )
                        ),
                        ignore_errors=False,
                        onerror=handle_remove_read_only,
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
        instance_path = str(Path(AppInfo().app_storage_folder) / "instances" / instance)
        self.settings_controller.settings.current_instance_path = instance_path
        # Update window title with current instance
        self.__set_window_title(instance)
        # Save settings
        self.settings_controller.settings.save()
        # Clear mod lists
        self.main_content_panel._insert_data_into_lists([], [])
        # Initialize content
        self.initialize_content(is_initial=False)

    def __set_window_title(self, instance: str) -> None:
        """
        Sets the window title with the name of the instance being used.

        :param instance: Name of the instance currently being used.
        """
        self.setWindowTitle(f"RimSort {AppInfo().app_version} | {instance} Instance")

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
                        self.settings_controller.settings.instances[
                            current_instance
                        ].game_folder
                    )
                    / "Data"
                ),
                self.settings_controller.settings.instances[
                    current_instance
                ].local_folder,
                self.settings_controller.settings.instances[
                    current_instance
                ].workshop_folder,
            ],
        )
        # Connect watchdog to MetadataManager
        self.watchdog_event_handler.acf_changed.connect(
            self.main_content_panel.metadata_manager.refresh_acf_metadata
        )
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
            if self.watchdog_event_handler.watchdog_acf_observer is not None:
                self.watchdog_event_handler.watchdog_acf_observer.start()
            else:
                logger.warning("Watchdog Steam .acf Observer is None. Unable to start.")
            if self.watchdog_event_handler.watchdog_mods_observer is not None:
                self.watchdog_event_handler.watchdog_mods_observer.start()
            else:
                logger.warning("Watchdog Mods Observer is None. Unable to start.")
        except Exception as e:
            logger.warning(
                f"Unable to initialize Watchdog Observer(s) due to exception: {str(e)}"
            )

    def stop_watchdog_if_running(self) -> None:
        # STOP WATCHDOG IF IT IS ALREADY RUNNING
        if self.watchdog_event_handler is not None:
            if self.watchdog_event_handler.watchdog_acf_observer is not None or (
                self.watchdog_event_handler.watchdog_mods_observer is not None
            ):
                self.shutdown_watchdog()

    def shutdown_watchdog(self) -> None:
        if (
            self.watchdog_event_handler is not None
            and self.watchdog_event_handler.watchdog_acf_observer is not None
            and self.watchdog_event_handler.watchdog_mods_observer is not None
        ):
            # Handle Steam .acf Observer shutdown
            if self.watchdog_event_handler.watchdog_acf_observer.is_alive():
                self.watchdog_event_handler.watchdog_acf_observer.stop()
                self.watchdog_event_handler.watchdog_acf_observer.join()
                self.watchdog_event_handler.watchdog_acf_observer = None
            # Handle Mod Directory Observer shutdown
            elif self.watchdog_event_handler.watchdog_mods_observer.is_alive():
                self.watchdog_event_handler.watchdog_mods_observer.stop()
                self.watchdog_event_handler.watchdog_mods_observer.join()
                self.watchdog_event_handler.watchdog_mods_observer = None
                for timer in self.watchdog_event_handler.cooldown_timers.values():
                    timer.cancel()
            self.watchdog_event_handler = None
