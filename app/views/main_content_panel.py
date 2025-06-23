import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import webbrowser
import zipfile
from functools import partial
from io import BytesIO
from math import ceil
from multiprocessing import Pool, cpu_count
from pathlib import Path
from tempfile import gettempdir
from typing import Any, Callable, Self
from urllib.parse import urlparse
from zipfile import ZipFile

import requests
from loguru import logger
from PySide6.QtCore import (
    QEventLoop,
    QObject,
    QProcess,
    Qt,
    QThread,
    Signal,
    Slot,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import app.utils.constants as app_constants
import app.utils.metadata as metadata
import app.views.dialogue as dialogue
from app.controllers.sort_controller import Sorter
from app.models.animations import LoadingAnimation
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus
from app.utils.generic import (
    check_internet_connection,
    chunks,
    copy_to_clipboard_safely,
    launch_game_process,
    open_url_browser,
    platform_specific_open,
    upload_data_to_0x0_st,
)
from app.utils.metadata import MetadataManager, SettingsController
from app.utils.rentry.wrapper import RentryImport, RentryUpload
from app.utils.schema import generate_rimworld_mods_list
from app.utils.steam.browser import SteamBrowser
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.utils.steam.steamworks.wrapper import (
    SteamworksGameLaunch,
    SteamworksSubscriptionHandler,
)
from app.utils.steam.webapi.wrapper import (
    CollectionImport,
    ISteamRemoteStorage_GetPublishedFileDetails,
)
from app.utils.system_info import SystemInfo
from app.utils.todds.wrapper import ToddsInterface
from app.utils.xml import json_to_xml_write
from app.views.mod_info_panel import ModInfo
from app.views.mods_panel import ModListWidget, ModsPanel, ModsPanelSortKey
from app.windows.missing_dependencies_dialog import MissingDependenciesDialog
from app.windows.missing_mods_panel import MissingModsPrompt
from app.windows.rule_editor_panel import RuleEditor
from app.windows.runner_panel import RunnerPanel
from app.windows.use_this_instead_panel import UseThisInsteadPanel
from app.windows.workshop_mod_updater_panel import ModUpdaterPrompt


class MainContent(QObject):
    """
    This class controls the layout and functionality of the main content
    panel of the GUI, containing the mod information display, inactive and
    active mod lists, and the action button panel. Additionally, it acts
    as the main temporary datastore of the app, caching workshop mod information
    and their dependencies.
    """

    _instance: Self | None = None

    disable_enable_widgets_signal = Signal(bool)
    status_signal = Signal(str)
    stop_watchdog_signal = Signal()

    def __new__(cls, *args: Any, **kwargs: Any) -> "MainContent":
        if cls._instance is None:
            cls._instance = super(MainContent, cls).__new__(cls)
        return cls._instance

    def __init__(self, settings_controller: SettingsController) -> None:
        """
        Initialize the main content panel.

        :param settings_controller: the settings controller for the application
        """
        if not hasattr(self, "initialized"):
            super(MainContent, self).__init__()
            logger.debug("Initializing MainContent")

            self.settings_controller = settings_controller
            self.main_window = None  # Will be set by set_main_window

            EventBus().settings_have_changed.connect(self._on_settings_have_changed)
            EventBus().do_check_for_application_update.connect(
                self._do_check_for_update
            )
            EventBus().do_open_mod_list.connect(self._do_import_list_file_xml)
            EventBus().do_import_mod_list_from_rentry.connect(
                self._do_import_list_rentry
            )
            EventBus().do_import_mod_list_from_workshop_collection.connect(
                self._do_import_list_workshop_collection
            )
            EventBus().do_save_mod_list_as.connect(self._do_export_list_file_xml)
            EventBus().do_export_mod_list_to_clipboard.connect(
                self._do_export_list_clipboard
            )
            EventBus().do_export_mod_list_to_rentry.connect(self._do_upload_list_rentry)
            EventBus().do_upload_rimsort_log.connect(self._on_do_upload_rimsort_log)
            EventBus().do_upload_rimsort_old_log.connect(
                self._on_do_upload_rimsort_old_log
            )
            EventBus().do_upload_rimworld_log.connect(self._on_do_upload_rimworld_log)
            EventBus().do_download_all_mods_via_steamcmd.connect(
                self._on_do_download_all_mods_via_steamcmd
            )
            EventBus().do_download_all_mods_via_steam.connect(
                self._on_do_download_all_mods_via_steam
            )
            EventBus().do_compare_steam_workshop_databases.connect(
                self._do_generate_metadata_comparison_report
            )
            EventBus().do_merge_steam_workshop_databases.connect(
                self._do_merge_databases
            )
            EventBus().do_build_steam_workshop_database.connect(
                self._on_do_build_steam_workshop_database
            )
            EventBus().do_import_acf.connect(
                lambda: self.actions_slot("import_steamcmd_acf_data")
            )
            EventBus().do_delete_acf.connect(
                lambda: self.actions_slot("reset_steamcmd_acf_data")
            )
            EventBus().do_install_steamcmd.connect(self._do_setup_steamcmd)

            EventBus().do_refresh_mods_lists.connect(self._do_refresh)
            EventBus().do_clear_active_mods_list.connect(self._do_clear)
            EventBus().do_restore_active_mods_list.connect(self._do_restore)
            EventBus().do_sort_active_mods_list.connect(self._do_sort)
            EventBus().do_save_active_mods_list.connect(self._do_save)
            EventBus().do_run_game.connect(self._do_run_game)

            # Shortcuts submenu Eventbus
            EventBus().do_open_app_directory.connect(self._do_open_app_directory)
            EventBus().do_open_settings_directory.connect(
                self._do_open_settings_directory
            )
            EventBus().do_open_rimsort_logs_directory.connect(
                self._do_open_rimsort_logs_directory
            )
            EventBus().do_open_rimworld_directory.connect(
                self._do_open_rimworld_directory
            )
            EventBus().do_open_rimworld_config_directory.connect(
                self._do_open_rimworld_config_directory
            )
            EventBus().do_open_rimworld_logs_directory.connect(
                self._do_open_rimworld_logs_directory
            )
            EventBus().do_open_local_mods_directory.connect(
                self._do_open_local_mods_directory
            )
            EventBus().do_open_steam_mods_directory.connect(
                self._do_open_steam_mods_directory
            )

            EventBus().do_steamcmd_download.connect(
                self._do_download_mods_with_steamcmd
            )

            EventBus().do_steamworks_api_call.connect(
                self._do_steamworks_api_call_animated
            )

            # Edit Menu bar Eventbus
            EventBus().do_rule_editor.connect(
                lambda: self.actions_slot("open_community_rules_with_rule_editor")
            )

            # Download Menu bar Eventbus
            EventBus().do_add_zip_mod.connect(self._do_add_zip_mod)
            EventBus().do_browse_workshop.connect(self._do_browse_workshop)
            EventBus().do_check_for_workshop_updates.connect(
                self._do_check_for_workshop_updates
            )

            # Textures Menu bar Eventbus
            EventBus().do_optimize_textures.connect(
                lambda: self.actions_slot("optimize_textures")
            )
            EventBus().do_delete_dds_textures.connect(
                lambda: self.actions_slot("delete_textures")
            )

            # INITIALIZE WIDGETS
            # Initialize Steam(CMD) integrations
            self.steam_browser: SteamBrowser | None = None
            self.steamcmd_runner: RunnerPanel | None = None
            self.steamcmd_wrapper = SteamcmdInterface.instance()

            # Initialize MetadataManager
            self.metadata_manager = metadata.MetadataManager.instance()

            # BASE LAYOUT
            self.main_layout = QHBoxLayout()
            self.main_layout.setContentsMargins(
                5, 5, 5, 5
            )  # Space between widgets and Frame border
            self.main_layout.setSpacing(5)  # Space between mod lists and action buttons

            # FRAME REQUIRED - to allow for styling
            self.main_layout_frame = QFrame()
            self.main_layout_frame.setObjectName("MainPanel")
            self.main_layout_frame.setLayout(self.main_layout)

            # INSTANTIATE WIDGETS
            self.mod_info_panel = ModInfo()
            self.mods_panel = ModsPanel(
                settings_controller=self.settings_controller,
            )

            # WIDGETS INTO BASE LAYOUT
            self.main_layout.addLayout(self.mod_info_panel.panel, 50)
            self.main_layout.addLayout(self.mods_panel.panel, 50)

            # SIGNALS AND SLOTS
            self.metadata_manager.mod_created_signal.connect(
                self.mods_panel.on_mod_created  # Connect MetadataManager to ModPanel for mod creation
            )
            self.metadata_manager.mod_deleted_signal.connect(
                self.mods_panel.on_mod_deleted  # Connect MetadataManager to ModPanel for mod deletion
            )
            self.metadata_manager.mod_metadata_updated_signal.connect(
                self.mods_panel.on_mod_metadata_updated  # Connect MetadataManager to ModPanel for mod metadata updates
            )
            self.mods_panel.active_mods_list.key_press_signal.connect(
                self.__handle_active_mod_key_press
            )
            self.mods_panel.inactive_mods_list.key_press_signal.connect(
                self.__handle_inactive_mod_key_press
            )
            self.mods_panel.active_mods_list.mod_info_signal.connect(
                self.__mod_list_slot
            )
            self.mods_panel.inactive_mods_list.mod_info_signal.connect(
                self.__mod_list_slot
            )
            self.mods_panel.active_mods_list.item_added_signal.connect(
                self.mods_panel.inactive_mods_list.handle_other_list_row_added
            )
            self.mods_panel.inactive_mods_list.item_added_signal.connect(
                self.mods_panel.active_mods_list.handle_other_list_row_added
            )
            self.mods_panel.active_mods_list.edit_rules_signal.connect(
                self._do_open_rule_editor
            )
            self.mods_panel.inactive_mods_list.edit_rules_signal.connect(
                self._do_open_rule_editor
            )
            self.mods_panel.active_mods_list.steamcmd_downloader_signal.connect(
                self._do_download_mods_with_steamcmd
            )
            self.mods_panel.inactive_mods_list.steamcmd_downloader_signal.connect(
                self._do_download_mods_with_steamcmd
            )
            self.mods_panel.active_mods_list.steamworks_subscription_signal.connect(
                self._do_steamworks_api_call_animated
            )
            self.mods_panel.inactive_mods_list.steamworks_subscription_signal.connect(
                self._do_steamworks_api_call_animated
            )
            self.mods_panel.active_mods_list.steamdb_blacklist_signal.connect(
                self._do_blacklist_action_steamdb
            )
            self.mods_panel.inactive_mods_list.steamdb_blacklist_signal.connect(
                self._do_blacklist_action_steamdb
            )
            self.mods_panel.active_mods_list.refresh_signal.connect(self._do_refresh)
            self.mods_panel.inactive_mods_list.refresh_signal.connect(self._do_refresh)

            EventBus().use_this_instead_clicked.connect(self._use_this_instead_clicked)

            # Restore cache initially set to empty
            self.active_mods_uuids_last_save: list[str] = []
            self.active_mods_uuids_restore_state: list[str] = []
            self.inactive_mods_uuids_restore_state: list[str] = []

            # Store duplicate_mods for global access
            self.duplicate_mods: dict[str, Any] = {}

            # Instantiate query runner
            self.query_runner: RunnerPanel | None = None

            # Steamworks bool - use this to check any Steamworks processes you try to initialize
            self.steamworks_in_use = False

            # Instantiate todds runner
            self.todds_runner: RunnerPanel | None = None

            self.progress_window: ProgressWindow = ProgressWindow()
            self._extract_thread: ZipExtractThread | None = None

            logger.info("Finished MainContent initialization")
            self.initialized = True

    @classmethod
    def instance(cls, *args: Any, **kwargs: Any) -> "MainContent":
        if cls._instance is None:
            cls._instance = cls(*args, **kwargs)
        elif args or kwargs:
            raise ValueError("MainContent instance has already been initialized.")
        return cls._instance

    def check_if_essential_paths_are_set(self, prompt: bool = True) -> bool:
        """
        When the user starts the app for the first time, none
        of the paths will be set. We should check for this and
        not throw a fatal error trying to load mods until the
        user has had a chance to set paths.
        """
        current_instance = self.settings_controller.settings.current_instance
        game_folder_path = self.settings_controller.settings.instances[
            current_instance
        ].game_folder
        config_folder_path = self.settings_controller.settings.instances[
            current_instance
        ].config_folder
        logger.debug(f"Game folder: {game_folder_path}")
        logger.debug(f"Config folder: {config_folder_path}")
        if (
            game_folder_path
            and config_folder_path
            and os.path.exists(game_folder_path)
            and os.path.exists(config_folder_path)
        ):
            logger.info("Essential paths set!")
            return True
        else:
            logger.warning("Essential path(s) are invalid or not set!")
            answer = dialogue.show_dialogue_conditional(
                title=self.tr("Essential path(s)"),
                text=self.tr("Essential path(s) are invalid or not set!\n"),
                information=(
                    self.tr(
                        "RimSort requires, at the minimum, for the game install folder and the "
                        "config folder paths to be set, and that the paths both exist. Please set "
                        "both of these manually or by using the autodetect functionality.\n\n"
                        "Would you like to configure them now?"
                    )
                ),
            )
            if answer == "&Yes":
                self.settings_controller.show_settings_dialog("Locations")
            return False

    def ___get_relative_middle(self, some_list: ModListWidget) -> int:
        rect = some_list.contentsRect()
        top = some_list.indexAt(rect.topLeft())
        if top.isValid():
            bottom = some_list.indexAt(rect.bottomLeft())
            if not bottom.isValid():
                bottom = some_list.model().index(some_list.count() - 1, 0)
            return int((top.row() + bottom.row() + 1) / 2)
        return 0

    def __handle_active_mod_key_press(self, key: str) -> None:
        """
        If the Left Arrow key is pressed while the user is focused on the
        Active Mods List, the focus is shifted to the Inactive Mods List.
        If no Inactive Mod was previously selected, the middle (relative)
        one is selected. `__mod_list_slot` is also called to update the
        Mod Info Panel.

        If the Return or Space button is pressed the selected mods in the
        current list are deleted from the current list and inserted
        into the other list.
        """
        aml = self.mods_panel.active_mods_list
        iml = self.mods_panel.inactive_mods_list
        if key == "Left":
            iml.setFocus()
            if not iml.selectedIndexes():
                iml.setCurrentRow(self.___get_relative_middle(iml))
            data = iml.selectedItems()[0].data(Qt.ItemDataRole.UserRole)
            uuid = data["uuid"]
            self.__mod_list_slot(uuid)

        elif key == "Return" or key == "Space" or key == "DoubleClick":
            # TODO: graphical bug where if you hold down the key, items are
            # inserted too quickly and become empty items

            items_to_move = aml.selectedItems().copy()
            if items_to_move:
                first_selected = sorted(aml.row(i) for i in items_to_move)[0]

                # Remove items from current list
                for item in items_to_move:
                    data = item.data(Qt.ItemDataRole.UserRole)
                    uuid = data["uuid"]
                    aml.uuids.remove(uuid)
                    aml.takeItem(aml.row(item))
                if aml.count():
                    if aml.count() == first_selected:
                        aml.setCurrentRow(aml.count() - 1)
                    else:
                        aml.setCurrentRow(first_selected)

                # Insert items into other list
                if not iml.selectedIndexes():
                    count = self.___get_relative_middle(iml)
                else:
                    count = iml.row(iml.selectedItems()[-1]) + 1
                for item in items_to_move:
                    iml.insertItem(count, item)
                    count += 1
        # List error/warnings are automatically recalculated when a mod is inserted/removed from a list

    def __handle_inactive_mod_key_press(self, key: str) -> None:
        """
        If the Right Arrow key is pressed while the user is focused on the
        Inactive Mods List, the focus is shifted to the Active Mods List.
        If no Active Mod was previously selected, the middle (relative)
        one is selected. `__mod_list_slot` is also called to update the
        Mod Info Panel.

        If the Return or Space button is pressed the selected mods in the
        current list are deleted from the current list and inserted
        into the other list.
        """

        aml = self.mods_panel.active_mods_list
        iml = self.mods_panel.inactive_mods_list
        if key == "Right":
            aml.setFocus()
            if not aml.selectedIndexes():
                aml.setCurrentRow(self.___get_relative_middle(aml))
            data = aml.selectedItems()[0].data(Qt.ItemDataRole.UserRole)
            uuid = data["uuid"]
            self.__mod_list_slot(uuid)

        elif key == "Return" or key == "Space" or key == "DoubleClick":
            # TODO: graphical bug where if you hold down the key, items are
            # inserted too quickly and become empty items

            items_to_move = iml.selectedItems().copy()
            if items_to_move:
                first_selected = sorted(iml.row(i) for i in items_to_move)[0]

                # Remove items from current list
                for item in items_to_move:
                    data = item.data(Qt.ItemDataRole.UserRole)
                    uuid = data["uuid"]
                    iml.uuids.remove(uuid)
                    iml.takeItem(iml.row(item))
                if iml.count():
                    if iml.count() == first_selected:
                        iml.setCurrentRow(iml.count() - 1)
                    else:
                        iml.setCurrentRow(first_selected)

                # Insert items into other list
                if not aml.selectedIndexes():
                    count = self.___get_relative_middle(aml)
                else:
                    count = aml.row(aml.selectedItems()[-1]) + 1
                for item in items_to_move:
                    aml.insertItem(count, item)
                    count += 1
        # List error/warnings are automatically recalculated when a mod is inserted/removed from a list

    def __insert_data_into_lists(
        self, active_mods_uuids: list[str], inactive_mods_uuids: list[str]
    ) -> None:
        """
        Insert active mods and inactive mods into respective mod list widgets.

        :param active_mods_uuids: list of active mod uuids
        :param inactive_mods_uuids: list of inactive mod uuids
        """
        logger.info(
            f"Inserting mod data into active [{len(active_mods_uuids)}] and inactive [{len(inactive_mods_uuids)}] mod lists"
        )
        self.mods_panel.active_mods_list.recreate_mod_list(
            list_type="active", uuids=active_mods_uuids
        )
        self.mods_panel.inactive_mods_list.recreate_mod_list_and_sort(
            list_type="inactive",
            uuids=inactive_mods_uuids,
            key=ModsPanelSortKey.MODNAME,
        )
        logger.info(
            f"Finished inserting mod data into active [{len(active_mods_uuids)}] and inactive [{len(inactive_mods_uuids)}] mod lists"
        )
        # Recalculate warnings for both lists
        # self.mods_panel.active_mods_list.recalculate_warnings_signal.emit()
        # self.mods_panel.inactive_mods_list.recalculate_warnings_signal.emit()

    def __duplicate_mods_prompt(self) -> None:
        list_of_duplicate_mods = "\n".join(
            [f"* {mod}" for mod in self.duplicate_mods.keys()]
        )
        dialogue.show_warning(
            title=self.tr("Duplicate mod(s) found"),
            text=self.tr(
                "Duplicate mods(s) found for package ID(s) in your ModsConfig.xml (active mods list)"
            ),
            information=(
                self.tr(
                    "The following list of mods were set active in your ModsConfig.xml and "
                    "duplicate instances were found of these mods in your mod data sources. "
                    "The vanilla game will use the first 'local mod' of a particular package ID "
                    "that is found - so RimSort will also adhere to this logic."
                )
            ),
            details=list_of_duplicate_mods,
        )

    def __missing_mods_prompt(self) -> None:
        logger.debug(f"Could not find data for {len(self.missing_mods)} active mods")
        if (  # User configuration
            self.settings_controller.settings.try_download_missing_mods
            and self.metadata_manager.external_steam_metadata
        ):  # Do we even have metadata to lookup...?
            self.missing_mods_prompt = MissingModsPrompt(
                packageids=self.missing_mods,
            )
            self.missing_mods_prompt._populate_from_metadata()
            self.missing_mods_prompt.setWindowModality(
                Qt.WindowModality.ApplicationModal
            )
            self.missing_mods_prompt.show()
        else:
            list_of_missing_mods = "\n".join([f"* {mod}" for mod in self.missing_mods])
            dialogue.show_information(
                text=self.tr("Could not find data for some mods!"),
                information=(
                    self.tr(
                        "The following list of mods were set active in your mods list but "
                        "no data could be found for these mods in local/workshop mod paths. "
                        "\n\nAre your game configuration paths correct?"
                    )
                ),
                details=list_of_missing_mods,
            )

    def __mod_list_slot(self, uuid: str) -> None:
        """
        This slot method is triggered when the user clicks on an item
        on a mod list. It takes the internal uuid and gets the
        complete json mod info for that internal uuid. It passes
        this information to the mod info panel to display.

        :param uuid: uuid of mod
        """
        self.mod_info_panel.display_mod_info(
            uuid=uuid,
            render_unity_rt=self.settings_controller.settings.render_unity_rich_text,
        )

    def __repopulate_lists(self, is_initial: bool = False) -> None:
        """
        Get active and inactive mod lists based on the config path
        and write them to the list widgets. is_initial indicates if
        this function is running at app initialization. If is_initial is
        true, then write the active_mods_data and inactive_mods_data to
        restore variables.
        """
        logger.info("Repopulating mod lists")
        (
            active_mods_uuids,
            inactive_mods_uuids,
            self.duplicate_mods,
            self.missing_mods,
        ) = metadata.get_mods_from_list(
            mod_list=str(
                (
                    Path(
                        self.settings_controller.settings.instances[
                            self.settings_controller.settings.current_instance
                        ].config_folder
                    )
                    / "ModsConfig.xml"
                )
            )
        )
        self.active_mods_uuids_last_save = active_mods_uuids
        if is_initial:
            logger.info("Caching initial active/inactive mod lists")
            self.active_mods_uuids_restore_state = active_mods_uuids
            self.inactive_mods_uuids_restore_state = inactive_mods_uuids

        self.__insert_data_into_lists(active_mods_uuids, inactive_mods_uuids)

    #########
    # SLOTS # Can this be cleaned up & moved to own module...?
    #########

    # ACTIONS PANEL ACTIONS

    def actions_slot(self, action: str) -> None:
        """
        Slot for the `actions_signal` signals

        :param action: string indicating action
        """
        logger.info(f"USER ACTION: received action {action}")
        # game configuration panel actions
        if action == "check_for_update":
            self._do_check_for_update()
        # actions panel actions
        if action == "refresh":
            self._do_refresh()
        if action == "clear":
            self._do_clear()
        if action == "restore":
            self._do_restore()
        if action == "sort":
            self._do_sort()
        if "textures" in action:
            logger.debug("Initiating new todds operation...")
            # Setup Environment
            todds_txt_path = str((Path(gettempdir()) / "todds.txt"))
            if os.path.exists(todds_txt_path):
                os.remove(todds_txt_path)
            if not self.settings_controller.settings.todds_active_mods_target:
                local_mods_target = self.settings_controller.settings.instances[
                    self.settings_controller.settings.current_instance
                ].local_folder
                if local_mods_target and local_mods_target != "":
                    with open(todds_txt_path, "a", encoding="utf-8") as todds_txt_file:
                        todds_txt_file.write(os.path.abspath(local_mods_target) + "\n")
                workshop_mods_target = self.settings_controller.settings.instances[
                    self.settings_controller.settings.current_instance
                ].workshop_folder
                if workshop_mods_target and workshop_mods_target != "":
                    with open(todds_txt_path, "a", encoding="utf-8") as todds_txt_file:
                        todds_txt_file.write(
                            os.path.abspath(workshop_mods_target) + "\n"
                        )
            else:
                with open(todds_txt_path, "a", encoding="utf-8") as todds_txt_file:
                    for uuid in self.mods_panel.active_mods_list.uuids:
                        todds_txt_file.write(
                            os.path.abspath(
                                self.metadata_manager.internal_local_metadata[uuid][
                                    "path"
                                ]
                            )
                            + "\n"
                        )
            if action == "optimize_textures":
                self._do_optimize_textures(todds_txt_path)
            if action == "delete_textures":
                self._do_delete_dds_textures(todds_txt_path)
        if action == "browse_workshop":
            self._do_browse_workshop()
        if action == "import_steamcmd_acf_data":
            metadata.import_steamcmd_acf_data(
                rimsort_storage_path=str(AppInfo().app_storage_folder),
                steamcmd_appworkshop_acf_path=self.steamcmd_wrapper.steamcmd_appworkshop_acf_path,
            )
        if action == "reset_steamcmd_acf_data":
            if os.path.exists(self.steamcmd_wrapper.steamcmd_appworkshop_acf_path):
                logger.debug(
                    f"Deleting SteamCMD ACF data: {self.steamcmd_wrapper.steamcmd_appworkshop_acf_path}"
                )
                os.remove(self.steamcmd_wrapper.steamcmd_appworkshop_acf_path)
            else:
                logger.debug("SteamCMD ACF data does not exist. Skipping action.")
        if action == "update_workshop_mods":
            self._do_check_for_workshop_updates()
        if action == "import_list_file_xml":
            self._do_import_list_file_xml()
        if action == "import_list_rentry":
            self._do_import_list_rentry()
        if action == "export_list_file_xml":
            self._do_export_list_file_xml()
        if action == "export_list_clipboard":
            self._do_export_list_clipboard()
        if action == "upload_list_rentry":
            self._do_upload_list_rentry()
        if action == "save":
            self._do_save()
        # settings panel actions
        if action == "configure_steam_database_path":
            self._do_configure_steam_db_file_path()
        if action == "configure_steam_database_repo":
            self._do_configure_steam_database_repo()
        if action == "configure_community_rules_db_path":
            self._do_configure_community_rules_db_file_path()
        if action == "configure_community_rules_db_repo":
            self._do_configure_community_rules_db_repo()
        if action == "open_community_rules_with_rule_editor":
            self._do_open_rule_editor(compact=False, initial_mode="community_rules")
        if action == "build_steam_database_thread":
            self._do_build_database_thread()
        if "download_entire_workshop" in action:
            self._do_download_entire_workshop(action)
        if action == "merge_databases":
            self._do_merge_databases()
        if action == "set_database_expiry":
            self._do_set_database_expiry()
        if action == "edit_steam_webapi_key":
            self._do_edit_steam_webapi_key()
        if action == "comparison_report":
            self._do_generate_metadata_comparison_report()

    # GAME CONFIGURATION PANEL

    def _do_check_for_update(self) -> None:
        logger.debug("Checking for RimSort update...")
        # NOT NUITKA
        if "__compiled__" not in globals():
            logger.debug(
                "You are running from Python interpreter. Skipping update check..."
            )
            dialogue.show_warning(
                title=self.tr("Update skipped"),
                text=self.tr("You are running from Python interpreter."),
                information=self.tr("Skipping update check..."),
            )
            return
        # NUITKA
        logger.debug("Checking for RimSort update...")
        current_version = AppInfo().app_version
        try:
            json_response = self.__do_get_github_release_info()
        except Exception as e:
            logger.warning(
                f"Unable to retrieve latest release information due to exception: {e.__class__}"
            )
            dialogue.show_warning(
                title=self.tr("Unable to retrieve latest release information"),
                text=self.tr(
                    "Unable to retrieve latest release information due to exception: {e.__class__}"
                ).format(e=e),
            )
            return

        # Check if response is a dictionary and if 'tag_name' exists in the response
        if not isinstance(json_response, dict):
            logger.warning(
                f"Unexpected response type from GitHub API: {type(json_response)}"
            )
            logger.debug(f"Response received: {json_response}")
            self.show_update_error()
            return

        if "tag_name" not in json_response:
            logger.warning(
                "Unable to retrieve latest release information: 'tag_name' not found in response"
            )
            logger.debug(f"Response received: {json_response}")
            self.show_update_error()
            return

        tag_name = json_response["tag_name"]
        if tag_name is None:
            logger.warning("Unable to retrieve latest release information")
            self.show_update_error()
            return
        tag_name_updated = tag_name.replace("alpha", "Alpha")
        install_path = os.getcwd()
        logger.debug(f"Current RimSort github release found: {tag_name}")
        logger.debug(f"Current RimSort installed version found: {current_version}")
        if current_version != tag_name:
            answer = dialogue.show_dialogue_conditional(
                title=self.tr("RimSort update found"),
                text=self.tr(
                    "An update to RimSort has been released: {tag_name}"
                ).format(tag_name=tag_name),
                information=self.tr(
                    "You are running RimSort {current_version}\nDo you want to update now?"
                ).format(current_version=current_version),
            )
            if answer == "&Yes":
                logger.debug("User selected to update RimSort")
                open_url_browser("https://github.com/RimSort/RimSort/releases")
                return  # Remove this and above line to enable auto-update
                # TODO : Implement auto-update currenty disabled since it has issues on linux
                # Setup environment
                ARCH = platform.architecture()[0]
                CWD = os.getcwd()
                PROCESSOR = platform.processor()
                if PROCESSOR == "":
                    PROCESSOR = platform.machine()
                SYSTEM = platform.system()

                current_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

                if SYSTEM == "Darwin":
                    current_dir = os.path.split(
                        os.path.split(os.path.dirname(os.path.abspath(sys.argv[0])))[0]
                    )[0]
                    executable_name = "RimSort.app"
                    if PROCESSOR == "i386" or PROCESSOR == "arm":
                        logger.warning(
                            f"Darwin/MacOS system detected with a {ARCH} {PROCESSOR} CPU..."
                        )
                        target_archive = (
                            f"RimSort-{tag_name_updated}_{SYSTEM}_{PROCESSOR}.zip"
                        )
                    else:
                        logger.warning(
                            f"Unsupported processor {SYSTEM} {ARCH} {PROCESSOR}"
                        )
                        return
                elif SYSTEM == "Linux":
                    executable_name = "RimSort.bin"
                    logger.warning(
                        f"Linux system detected with a {ARCH} {PROCESSOR} CPU..."
                    )
                    target_archive = (
                        f"RimSort-{tag_name_updated}_{SYSTEM}_{PROCESSOR}.zip"
                    )
                elif SYSTEM == "Windows":
                    executable_name = "RimSort.exe"
                    logger.warning(
                        f"Windows system detected with a {ARCH} {PROCESSOR} CPU..."
                    )
                    target_archive = f"RimSort-{tag_name_updated}_{SYSTEM}.zip"
                else:
                    logger.warning(f"Unsupported system {SYSTEM} {ARCH} {PROCESSOR}")
                    return
                # Try to find a valid release from our generated archive name
                for asset in json_response["assets"]:
                    if asset["name"] == target_archive:
                        browser_download_url = asset["browser_download_url"]
                # If we don't have it from our query...
                if "browser_download_url" not in locals():
                    dialogue.show_warning(
                        title=self.tr("Unable to complete update"),
                        text=self.tr(
                            "Failed to find valid RimSort release for {SYSTEM} {ARCH} {PROCESSOR}"
                        ).format(SYSTEM=SYSTEM, ARCH=ARCH, PROCESSOR=PROCESSOR),
                    )
                    return
                target_archive_extracted = target_archive.replace(".zip", "")
                try:
                    logger.debug(
                        f"Downloading & extracting RimSort release from: {browser_download_url}"
                    )
                    self.do_threaded_loading_animation(
                        gif_path=str(
                            AppInfo().theme_data_folder
                            / "default-icons"
                            / "refresh.gif"
                        ),
                        target=partial(
                            self.__do_download_extract_release_to_tempdir,
                            url=browser_download_url,
                        ),
                        text=self.tr(
                            "RimSort update found. Downloading RimSort {tag_name_updated} release..."
                        ).format(tag_name_updated=tag_name_updated),
                    )
                    temp_dir = "RimSort" if SYSTEM != "Darwin" else "RimSort.app"
                    answer = dialogue.show_dialogue_conditional(
                        title=self.tr("Update downloaded"),
                        text=self.tr("Do you want to proceed with the update?"),
                        information=f"\nSuccessfully retrieved latest release. The update will be installed from: {os.path.join(gettempdir(), temp_dir)}",
                    )
                    if answer != "&Yes":
                        return
                except Exception:
                    stacktrace = traceback.format_exc()
                    dialogue.show_warning(
                        title=self.tr("Failed to download update"),
                        text=self.tr("Failed to download latest RimSort release!"),
                        information="Did the file/url change? "
                        + "Does your environment have access to the Internet?\n"
                        + f"URL: {browser_download_url}",
                        details=stacktrace,
                    )
                    return
                # Stop watchdog
                logger.info("Stopping watchdog Observer thread before update...")
                self.stop_watchdog_signal.emit()
                # https://stackoverflow.com/a/21805723
                if SYSTEM == "Darwin":  # MacOS
                    popen_args = [
                        "/bin/bash",
                        str((Path(current_dir) / "Contents" / "MacOS" / "update.sh")),
                    ]
                    p = subprocess.Popen(popen_args)
                else:
                    try:
                        subprocess.CREATE_NEW_PROCESS_GROUP
                    except AttributeError:  # not Windows, so assume POSIX; if not, we'll get a usable exception
                        popen_args = [
                            "/bin/bash",
                            str((AppInfo().application_folder / "update.sh")),
                        ]
                        p = subprocess.Popen(
                            popen_args,
                            start_new_session=True,
                        )
                    else:  # Windows
                        popen_args = [
                            "start",
                            "/wait",
                            "cmd",
                            "/c",
                            str(
                                (
                                    AppInfo.application_folder,
                                    "update.bat",
                                )
                            ),
                        ]
                        p = subprocess.Popen(
                            popen_args,
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                            shell=True,
                        )
                logger.debug(f"External updater script launched with PID: {p.pid}")
                logger.debug(f"Arguments used: {popen_args}")
                sys.exit()
        else:
            logger.debug("Up to date!")
            dialogue.show_information(
                title=self.tr("RimSort is up to date!"),
                text=self.tr(
                    "You are already running the latest release: {tag_name}"
                ).format(tag_name=tag_name),
            )

    def show_update_error(self) -> None:
        dialogue.show_warning(
            title=self.tr("Unable to retrieve latest release information"),
            text=self.tr(
                "Please check your internet connection and try again, You can also check 'https://github.com/RimSort/RimSort/releases' directly."
            ),
        )

    def __do_download_extract_release_to_tempdir(self, url: str) -> None:
        with ZipFile(BytesIO(requests.get(url).content)) as zipobj:
            zipobj.extractall(gettempdir())

    def __do_get_github_release_info(self) -> dict[str, Any]:
        # Parse latest release
        url = "https://api.github.com/repos/RimSort/RimSort/releases/latest"
        logger.debug(f"Requesting GitHub release info from: {url}")

        raw = requests.get(url, timeout=10)

        # Check for HTTP errors
        if raw.status_code != 200:
            logger.warning(f"GitHub API returned status code {raw.status_code}")
            if raw.status_code == 403:
                logger.warning("Possible rate limiting by GitHub API")
            raise Exception(
                f"GitHub API returned status code {raw.status_code}: {raw.text}"
            )

        # Try to parse JSON response
        try:
            response_json = raw.json()
            logger.debug("Successfully parsed GitHub API response")
            return response_json
        except Exception as e:
            logger.error(f"Failed to parse GitHub API response: {e}")
            logger.debug(f"Raw response: {raw.text}")
            raise

    # INFO PANEL ANIMATIONS

    def do_threaded_loading_animation(
        self, gif_path: str, target: Callable[..., Any], text: str | None = None
    ) -> Any:
        # Hide the info panel widgets
        self.mod_info_panel.info_panel_frame.hide()
        # Disable widgets while loading
        self.disable_enable_widgets_signal.emit(False)
        # Encapsulate mod parsing inside a nice lil animation
        loading_animation = LoadingAnimation(
            gif_path=gif_path,
            target=target,
        )
        self.mod_info_panel.panel.addWidget(loading_animation)
        # If any text message specified, pass it to the info panel as well
        loading_animation_text_label = None
        if text:
            loading_animation_text_label = QLabel(text)
            loading_animation_text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            loading_animation_text_label.setObjectName("loadingAnimationString")
            self.mod_info_panel.panel.addWidget(loading_animation_text_label)
        loop = QEventLoop()
        loading_animation.finished.connect(loop.quit)
        loop.exec_()
        data = loading_animation.data
        # Remove text label if it was passed
        if text and loading_animation_text_label is not None:
            self.mod_info_panel.panel.removeWidget(loading_animation_text_label)
            loading_animation_text_label.close()
        # Enable widgets again after loading
        self.disable_enable_widgets_signal.emit(True)
        # Show the info panel widgets
        self.mod_info_panel.info_panel_frame.show()
        logger.debug(f"Returning {type(data)}")
        return data

    # ACTIONS PANEL

    def _do_refresh(self, is_initial: bool = False) -> None:
        """
        Refresh expensive calculations & repopulate lists with that refreshed data
        """
        EventBus().refresh_started.emit()
        EventBus().do_save_button_animation_stop.emit()
        # If we are refreshing cache from user action
        if not is_initial:
            # Reset the data source filters to default and clear searches
            # Avoid recalculating warnings/errors when clearing search
            # Recalculation for each list will be triggered by mods being reinserted into inactive and active lists automatically
            self.mods_panel.active_mods_filter_data_source_index = len(
                self.mods_panel.data_source_filter_icons
            )
            self.mods_panel.signal_clear_search(
                list_type="Active", recalculate_list_errors_warnings=False
            )
            self.mods_panel.inactive_mods_filter_data_source_index = len(
                self.mods_panel.data_source_filter_icons
            )
            self.mods_panel.signal_clear_search(
                list_type="Inactive", recalculate_list_errors_warnings=False
            )
            self.mods_panel.active_mods_filter_data_source_index = len(
                self.mods_panel.data_source_filter_icons
            )
        # Check if paths are set
        if self.check_if_essential_paths_are_set(prompt=is_initial):
            # Run expensive calculations to set cache data
            self.do_threaded_loading_animation(
                gif_path=str(
                    AppInfo().theme_data_folder / "default-icons" / "rimsort.gif"
                ),
                target=partial(
                    self.metadata_manager.refresh_cache, is_initial=is_initial
                ),
                text=self.tr("Scanning mod sources and populating metadata..."),
            )

            # Insert mod data into list
            self.__repopulate_lists(is_initial=is_initial)

            # If we have duplicate mods, prompt user
            if (
                self.settings_controller.settings.duplicate_mods_warning
                and self.duplicate_mods
                and len(self.duplicate_mods) > 0
            ):
                self.__duplicate_mods_prompt()
            elif not self.settings_controller.settings.duplicate_mods_warning:
                logger.debug(
                    "User preference is not configured to display duplicate mods. Skipping..."
                )

            # If we have missing mods, prompt user
            if self.missing_mods and len(self.missing_mods) > 0:
                self.__missing_mods_prompt()

            # Check Workshop mods for updates if configured
            if (
                self.settings_controller.settings.steam_mods_update_check
            ):  # Check SteamCMD/Steam mods for updates if configured
                logger.info(
                    "User preference is configured to check Workshop mod for updates. Checking for Workshop mod updates..."
                )
                self._do_check_for_workshop_updates()
            else:
                logger.info(
                    "User preference is not configured to check Steam mods for updates. Skipping..."
                )
        else:
            self.__insert_data_into_lists([], [])
            logger.warning(
                "Essential paths have not been set. Passing refresh and resetting mod lists"
            )
            # Wait for settings dialog to be closed before continuing.
            # This is to ensure steamcmd check and other ops are done after the user has a chance to set paths
            if not self.settings_controller.settings_dialog.isHidden():
                loop = QEventLoop()
                self.settings_controller.settings_dialog.finished.connect(loop.quit)
                loop.exec_()
                logger.debug("Settings dialog closed. Continuing with refresh...")

        EventBus().refresh_finished.emit()

    def _do_clear(self) -> None:
        """
        Method to clear all the non-base, non-DLC mods from the active
        list widget and put them all into the inactive list widget.
        """
        self.mods_panel.active_mods_filter_data_source_index = len(
            self.mods_panel.data_source_filter_icons
        )
        self.mods_panel.signal_clear_search(list_type="Active")
        self.mods_panel.inactive_mods_filter_data_source_index = len(
            self.mods_panel.data_source_filter_icons
        )
        self.mods_panel.signal_clear_search(list_type="Inactive")
        # Metadata to insert
        active_mods_uuids: list[str] = []
        inactive_mods_uuids: list[str] = []
        logger.info("Clearing mods from active mod list")
        # Define the order of the DLC package IDs
        package_id_order = [
            app_constants.RIMWORLD_DLC_METADATA["294100"]["packageid"],
            app_constants.RIMWORLD_DLC_METADATA["1149640"]["packageid"],
            app_constants.RIMWORLD_DLC_METADATA["1392840"]["packageid"],
            app_constants.RIMWORLD_DLC_METADATA["1826140"]["packageid"],
            app_constants.RIMWORLD_DLC_METADATA["2380740"]["packageid"],
        ]
        # Create a set of all package IDs from mod_data
        package_ids_set = set(
            mod_data["packageid"]
            for mod_data in self.metadata_manager.internal_local_metadata.values()
        )
        # Iterate over the DLC package IDs in the correct order
        for package_id in package_id_order:
            if package_id in package_ids_set:
                # Append the UUIDs to active_mods_uuids if the package ID exists in mod_data
                active_mods_uuids.extend(
                    uuid
                    for uuid, mod_data in self.metadata_manager.internal_local_metadata.items()
                    if mod_data["data_source"] == "expansion"
                    and mod_data["packageid"] == package_id
                )
        # Append the remaining UUIDs to inactive_mods_uuids
        inactive_mods_uuids.extend(
            uuid
            for uuid in self.metadata_manager.internal_local_metadata.keys()
            if uuid not in active_mods_uuids
        )
        # Disable widgets while inserting
        self.disable_enable_widgets_signal.emit(False)
        # Insert data into lists
        self.__insert_data_into_lists(active_mods_uuids, inactive_mods_uuids)
        # Re-enable widgets after inserting
        self.disable_enable_widgets_signal.emit(True)

    def _do_sort(self, check_deps: bool = True) -> None:
        """
        Trigger sorting of all active mods using user-configured algorithm
        & all available & configured metadata
        """
        # Get the live list of active and inactive mods. This is because the user
        # will likely sort before saving.
        logger.debug("Starting sorting mods")
        self.mods_panel.signal_clear_search(list_type="Active")
        self.mods_panel.active_mods_filter_data_source_index = len(
            self.mods_panel.data_source_filter_icons
        )
        self.mods_panel.on_active_mods_search_data_source_filter()
        self.mods_panel.signal_clear_search(list_type="Inactive")
        self.mods_panel.inactive_mods_filter_data_source_index = len(
            self.mods_panel.data_source_filter_icons
        )
        self.mods_panel.on_inactive_mods_search_data_source_filter()

        # Get active mods
        active_mods = set(self.mods_panel.active_mods_list.uuids)

        # Check for missing dependencies if enabled in settings and check_deps is True
        if check_deps and self.settings_controller.settings.check_dependencies_on_sort:
            missing_deps = self.metadata_manager.get_missing_dependencies(active_mods)
            if missing_deps:
                dialog = MissingDependenciesDialog()
                selected_deps = dialog.show_dialog(missing_deps)

                if selected_deps:
                    # Add selected mods to active mods
                    for mod_id in selected_deps:
                        # Find the UUID for this package ID
                        for (
                            uuid,
                            mod_data,
                        ) in self.metadata_manager.internal_local_metadata.items():
                            if mod_data.get("packageid") == mod_id:
                                if uuid not in active_mods:
                                    active_mods.add(uuid)
                                break

        # Get package IDs for active mods
        active_package_ids = set()
        for uuid in active_mods:
            active_package_ids.add(
                self.metadata_manager.internal_local_metadata[uuid]["packageid"]
            )

        # Get the current order of active mods list and create a copy for comparison
        current_order = active_mods
        try:
            sorter = Sorter(
                self.settings_controller.settings.sorting_algorithm,
                active_package_ids=active_package_ids,
                active_uuids=active_mods,
                use_moddependencies_as_loadTheseBefore=self.settings_controller.settings.use_moddependencies_as_loadTheseBefore,
            )
        except NotImplementedError as e:
            dialogue.show_warning(
                title=self.tr("Sorting algorithm not implemented"),
                text=self.tr("The selected sorting algorithm is not implemented"),
                information=(
                    self.tr(
                        "This may be caused by malformed settings or improper migration between versions or different mod manager. "
                        "Try resetting your settings, selecting a different sorting algorithm, or "
                        "deleting your settings file. If the issue persists, please report it the developers."
                    )
                ),
                details=str(e),
            )
            logger.error(f"Sort failed. Sorting algorithm not implemented: {e}")
            return

        success, new_order = sorter.sort()

        # Log the sort result and the order
        logger.debug(f"Sort result: {success}, new order: {new_order}, current order: {current_order}")
        # Check if successful and orders differ
        if success and new_order != current_order:
            logger.info(
                "Finished combining all tiers of mods. Inserting into mod lists!"
            )
            # Disable widgets while inserting
            self.disable_enable_widgets_signal.emit(False)
            # Insert data into lists
            self.__insert_data_into_lists(
                new_order,
                [
                    uuid
                    for uuid in self.metadata_manager.internal_local_metadata
                    if uuid not in set(new_order)
                ],
            )
            # Enable widgets again after inserting
            self.disable_enable_widgets_signal.emit(True)
            logger.info("Insertion finished!")
        elif success and new_order == current_order:
            logger.info(
                "Sort completed, but the order of mods has not changed. No insertion needed."
            )
        elif not success:
            logger.warning("Failed to sort mods. Skipping insertion.")
        else:
            logger.warning("Unknown error occurred. Skipping insertion.")

    def _do_import_list_file_xml(self) -> None:
        """
        Open a user-selected XML file. Calculate
        and display active and inactive lists based on this file.
        """
        logger.info("Opening file dialog to select input file")
        file_path = dialogue.show_dialogue_file(
            mode="open",
            caption="Open RimWorld mod list",
            _dir=str(AppInfo().saved_modlists_folder),
            _filter="RimWorld mod list (*.rml *.rws *.xml)",
        )
        logger.info(f"Selected path: {file_path}")
        if file_path:
            self.mods_panel.signal_clear_search(list_type="Active")
            self.mods_panel.active_mods_filter_data_source_index = len(
                self.mods_panel.data_source_filter_icons
            )
            self.mods_panel.signal_search_source_filter(list_type="Active")
            self.mods_panel.signal_clear_search(list_type="Inactive")
            self.mods_panel.inactive_mods_filter_data_source_index = len(
                self.mods_panel.data_source_filter_icons
            )
            self.mods_panel.signal_search_source_filter(list_type="Inactive")
            logger.info(f"Trying to import mods list from XML: {file_path}")
            (
                active_mods_uuids,
                inactive_mods_uuids,
                self.duplicate_mods,
                self.missing_mods,
            ) = metadata.get_mods_from_list(mod_list=file_path)
            logger.info("Got new mods according to imported XML")
            self.__insert_data_into_lists(active_mods_uuids, inactive_mods_uuids)
            # If we have duplicate mods, prompt user
            if (
                self.settings_controller.settings.duplicate_mods_warning
                and self.duplicate_mods
                and len(self.duplicate_mods) > 0
            ):
                self.__duplicate_mods_prompt()
            elif not self.settings_controller.settings.duplicate_mods_warning:
                logger.debug(
                    "User preference is not configured to display duplicate mods. Skipping..."
                )
            # If we have missing mods, prompt user
            if self.missing_mods and len(self.missing_mods) >= 1:
                self.__missing_mods_prompt()
        else:
            logger.debug("USER ACTION: pressed cancel, passing")

    def _do_export_list_file_xml(self) -> None:
        """
        Export the current list of active mods to a user-designated
        file. The current list does not need to have been saved.
        """
        logger.info("Opening file dialog to specify output file")
        file_path = dialogue.show_dialogue_file(
            mode="save",
            caption="Save mod list",
            _dir=str(AppInfo().saved_modlists_folder),
            _filter="XML (*.xml)",
        )
        logger.info(f"Selected path: {file_path}")
        if file_path:
            logger.info("Exporting current active mods to ModsConfig.xml format")
            active_mods = []
            for uuid in self.mods_panel.active_mods_list.uuids:
                package_id = self.metadata_manager.internal_local_metadata[uuid][
                    "packageid"
                ]
                if package_id in active_mods:  # This should NOT be happening
                    logger.critical(
                        f"Tried to export more than 1 identical package ids to the same mod list. Skipping duplicate {package_id}"
                    )
                    continue
                else:  # Otherwise, proceed with adding the mod package_id
                    if (
                        package_id in self.duplicate_mods.keys()
                    ):  # Check if mod has duplicates
                        if (
                            self.metadata_manager.internal_local_metadata[uuid][
                                "data_source"
                            ]
                            == "workshop"
                        ):
                            active_mods.append(package_id + "_steam")
                            continue  # Append `_steam` suffix if Steam mod, continue to next mod
                    active_mods.append(package_id)
            logger.info(f"Collected {len(active_mods)} active mods for export")
            mods_config_data = generate_rimworld_mods_list(
                self.metadata_manager.game_version, active_mods
            )
            try:
                logger.info(
                    f"Saving generated ModsConfig.xml style list to selected path: {file_path}"
                )
                if not file_path.endswith(".xml"):
                    json_to_xml_write(mods_config_data, file_path + ".xml")
                else:
                    json_to_xml_write(mods_config_data, file_path)
            except Exception:
                dialogue.show_fatal_error(
                    title=self.tr("Failed to export to file"),
                    text=self.tr("Failed to export active mods to file:"),
                    information=f"{file_path}",
                    details=traceback.format_exc(),
                )
        else:
            logger.debug("USER ACTION: pressed cancel, passing")

    def _do_import_list_rentry(self) -> None:
        """
        Import a mod list from a Rentry.co link.

        This method:
        - Clears search and filter states on the mod lists.
        - Prompts the user to enter a Rentry.co link and fetches package IDs and publishedfileids.
        - Filters out publishedfileids that are already present locally.
        - If there are any missing mods, user will be asked to choose download method.
        - Use publishfieldid to download mods using Steamworks API or SteamCMD based on user selection.
        - Generates UUIDs based on existing mods, calculates duplicates, and missing mods.
        - Imports mods from package IDs if no downloads are needed.
        - Inserts active and inactive mods into the mod lists using package IDs.
        - If Prompts the user about duplicate or missing mods.
        """
        # Create an instance of RentryImport
        rentry_import = RentryImport(self.settings_controller)
        # Exit if user cancels or no package IDs
        if not rentry_import.package_ids:
            logger.debug("USER ACTION: pressed cancel or no package IDs, passing")
            return
        # Clear Active and Inactive search and data source filter
        self.mods_panel.signal_clear_search(list_type="Active")
        self.mods_panel.active_mods_filter_data_source_index = len(
            self.mods_panel.data_source_filter_icons
        )
        self.mods_panel.signal_search_source_filter(list_type="Active")
        self.mods_panel.signal_clear_search(list_type="Inactive")
        self.mods_panel.inactive_mods_filter_data_source_index = len(
            self.mods_panel.data_source_filter_icons
        )
        self.mods_panel.signal_search_source_filter(list_type="Inactive")

        if rentry_import.publishedfileids:
            # Get set of publishedfileids already present locally
            existing_publishedfileids = {
                mod_data.get("publishedfileid")
                for mod_data in self.metadata_manager.internal_local_metadata.values()
                if mod_data.get("publishedfileid") is not None
            }
            # Filter out publishedfileids that already exist locally
            filtered_publishedfileids = list(
                {
                    pfid
                    for pfid in rentry_import.publishedfileids
                    if pfid not in existing_publishedfileids
                }
            )

            def notify_user() -> None:
                """Notify user to redo Rentry Import after downloads complete."""
                dialogue.show_information(
                    title=self.tr("Important"),
                    text=self.tr(
                        "You will need to redo Rentry import again after downloads complete. "
                        "If there missing mods after download completes, they will be shown inside the missing mods panel. "
                        "If RimSort is still not able to download some mods, "
                        "It's due to the mod data not being available in both Rentry link and steam database."
                    ),
                )

            def dowmload_using_steamcmd() -> None:
                logger.info("Checking if SteamCMD is set up")
                steamcmd_wrapper = self.steamcmd_wrapper

                if not steamcmd_wrapper.setup:
                    # Setup SteamCMD if not already set up
                    self._do_setup_steamcmd()
                    if steamcmd_wrapper.setup:
                        logger.info("Using SteamCMD to download mods")
                        self._do_download_mods_with_steamcmd(filtered_publishedfileids)
                        # Notify user to redo Rentry Import
                        notify_user()
                else:
                    # SteamCMD is already set up, proceed with download
                    self._do_download_mods_with_steamcmd(filtered_publishedfileids)
                    # Notify user to redo Rentry Import
                    notify_user()

            def dowmload_using_steam() -> None:
                current_instance = self.settings_controller.settings.current_instance
                steam_client_integration = self.settings_controller.settings.instances[
                    current_instance
                ].steam_client_integration

                if steam_client_integration:
                    logger.info("Using Steamworks API to download mods")
                    self._do_steamworks_api_call_animated(
                        [
                            "subscribe",
                            [eval(str_pfid) for str_pfid in filtered_publishedfileids],
                        ]
                    )
                    # Notify user to redo Rentry Import
                    notify_user()
                    # do not process and wait for download to finish
                    return
                else:
                    # Steam Client Integration is not set up, proceed with download
                    dialogue.show_warning(
                        title=self.tr("Steam client integration not set up"),
                        text=self.tr(
                            "Steam client integration is not set up. Please set it up to download mods using Steam"
                        ),
                    )

            if filtered_publishedfileids:
                logger.info(
                    f"Trying to download {len(filtered_publishedfileids)} mods using publishedfileid: {filtered_publishedfileids}"
                )
                # Ask user how to download mods
                answer = dialogue.show_dialogue_conditional(
                    title=self.tr("Download Rentry Mods"),
                    text=self.tr("Please select a download method."),
                    information=self.tr(
                        "Select which method you want to use to download missing Rentry mods."
                    ),
                    button_text_override=[
                        "Steam",
                        "SteamCMD",
                    ],
                )
                if answer == "Steam":
                    # Download mods using Steamworks API
                    dowmload_using_steam()
                    # do not process and wait for download to finish
                    return
                if answer == "SteamCMD":
                    # Download mods using SteamCMD
                    dowmload_using_steamcmd()
                    # do not process and wait for download to finish
                    return
                if answer == "Cancel":
                    return

        # Log the attempt to import mods list from Rentry.co
        logger.info(
            f"Trying to import {len(rentry_import.package_ids)} mods from Rentry.co list"
        )

        # Generate uuids based on existing mods, calculate duplicates, and missing mods
        (
            active_mods_uuids,
            inactive_mods_uuids,
            self.duplicate_mods,
            self.missing_mods,
        ) = metadata.get_mods_from_list(mod_list=rentry_import.package_ids)

        # Insert data into lists
        self.__insert_data_into_lists(active_mods_uuids, inactive_mods_uuids)
        logger.info("Got new mods according to imported Rentry.co")

        # If we have duplicate mods and user preference is configured to display them, prompt user
        if (
            self.settings_controller.settings.duplicate_mods_warning
            and self.duplicate_mods
            and len(self.duplicate_mods) > 0
        ):
            self.__duplicate_mods_prompt()
        elif not self.settings_controller.settings.duplicate_mods_warning:
            logger.debug(
                "User preference is not configured to display duplicate mods. Skipping..."
            )

        # If we have missing mods, prompt the user
        if self.missing_mods and len(self.missing_mods) >= 1:
            self.__missing_mods_prompt()

    def _do_import_list_workshop_collection(self) -> None:
        # Create an instance of collection_import
        # This also triggers the import dialogue and gets result
        collection_import = CollectionImport(metadata_manager=self.metadata_manager)
        # Exit if user cancels or no package IDs
        if not collection_import.package_ids:
            logger.debug("USER ACTION: pressed cancel or no package IDs, passing")
            return
        # Clear Active and Inactive search and data source filter
        self.mods_panel.signal_clear_search(list_type="Active")
        self.mods_panel.active_mods_filter_data_source_index = len(
            self.mods_panel.data_source_filter_icons
        )
        self.mods_panel.signal_search_source_filter(list_type="Active")
        self.mods_panel.signal_clear_search(list_type="Inactive")
        self.mods_panel.inactive_mods_filter_data_source_index = len(
            self.mods_panel.data_source_filter_icons
        )
        self.mods_panel.signal_search_source_filter(list_type="Inactive")

        # Log the attempt to import mods list from Workshop collection
        logger.info(
            f"Trying to import {len(collection_import.package_ids)} mods from Workshop collection list"
        )

        # Generate uuids based on existing mods, calculate duplicates, and missing mods
        (
            active_mods_uuids,
            inactive_mods_uuids,
            self.duplicate_mods,
            self.missing_mods,
        ) = metadata.get_mods_from_list(mod_list=collection_import.package_ids)

        # Insert data into lists
        self.__insert_data_into_lists(active_mods_uuids, inactive_mods_uuids)
        logger.info("Got new mods according to imported Workshop collection")

        # If we have duplicate mods and user preference is configured to display them, prompt user
        if (
            self.settings_controller.settings.duplicate_mods_warning
            and self.duplicate_mods
            and len(self.duplicate_mods) > 0
        ):
            self.__duplicate_mods_prompt()
        elif not self.settings_controller.settings.duplicate_mods_warning:
            logger.debug(
                "User preference is not configured to display duplicate mods. Skipping..."
            )

        # If we have missing mods, prompt the user
        if self.missing_mods and len(self.missing_mods) >= 1:
            self.__missing_mods_prompt()

    def _do_export_list_clipboard(self) -> None:
        """
        Export the current list of active mods to the clipboard in a
        readable format. The current list does not need to have been saved.
        """
        logger.info("Generating report to export mod list to clipboard")
        # Build our lists
        active_mods = []
        active_mods_packageid_to_uuid = {}
        for uuid in self.mods_panel.active_mods_list.uuids:
            package_id = self.metadata_manager.internal_local_metadata[uuid][
                "packageid"
            ]
            if package_id in active_mods:  # This should NOT be happening
                logger.critical(
                    "Tried to export more than 1 identical package ids to the same mod list. "
                    + f"Skipping duplicate {package_id}"
                )
                continue
            else:  # Otherwise, proceed with adding the mod package_id
                active_mods.append(package_id)
                active_mods_packageid_to_uuid[package_id] = uuid
        logger.info(f"Collected {len(active_mods)} active mods for export")
        # Build our report
        active_mods_clipboard_report = (
            f"Created with RimSort {AppInfo().app_version}"
            + f"\nRimWorld game version this list was created for: {self.metadata_manager.game_version}"
            + f"\nTotal # of mods: {len(active_mods)}\n"
        )
        for package_id in active_mods:
            uuid = active_mods_packageid_to_uuid[package_id]
            if self.metadata_manager.internal_local_metadata[uuid].get("name"):
                name = self.metadata_manager.internal_local_metadata[uuid]["name"]
            else:
                name = "No name specified"
            if self.metadata_manager.internal_local_metadata[uuid].get("url"):
                url = self.metadata_manager.internal_local_metadata[uuid]["url"]
            elif self.metadata_manager.internal_local_metadata[uuid].get("steam_url"):
                url = self.metadata_manager.internal_local_metadata[uuid]["steam_url"]
            else:
                url = "No url specified"
            active_mods_clipboard_report = (
                active_mods_clipboard_report
                + f"\n{name} "
                + f"[{package_id}]"
                + f"[{url}]"
            )
        # Copy report to clipboard
        dialogue.show_information(
            title=self.tr("Export active mod list"),
            text=self.tr("Copied active mod list report to clipboard..."),
            information=self.tr('Click "Show Details" to see the full report!'),
            details=f"{active_mods_clipboard_report}",
        )
        copy_to_clipboard_safely(active_mods_clipboard_report)

    def _do_upload_list_rentry(self) -> None:
        """
        Export the current list of active mods to the clipboard in a
        readable format. The current list does not need to have been saved.
        """
        # Define our lists
        active_mods = []
        active_mods_packageid_to_uuid = {}
        active_steam_mods_packageid_to_pfid = {}
        active_steam_mods_pfid_to_preview_url = {}
        pfids = []
        # Build our lists
        for uuid in self.mods_panel.active_mods_list.uuids:
            package_id = MetadataManager.instance().internal_local_metadata[uuid][
                "packageid"
            ]
            if package_id in active_mods:  # This should NOT be happening
                logger.critical(
                    "Tried to export more than 1 identical package ids to the same mod list. "
                    + f"Skipping duplicate {package_id}"
                )
                continue
            else:  # Otherwise, proceed with adding the mod package_id
                active_mods.append(package_id)
                active_mods_packageid_to_uuid[package_id] = uuid
                if (
                    self.metadata_manager.internal_local_metadata[uuid].get("steamcmd")
                    or self.metadata_manager.internal_local_metadata[uuid][
                        "data_source"
                    ]
                    == "workshop"
                ) and self.metadata_manager.internal_local_metadata[uuid].get(
                    "publishedfileid"
                ):
                    publishedfileid = self.metadata_manager.internal_local_metadata[
                        uuid
                    ]["publishedfileid"]
                    active_steam_mods_packageid_to_pfid[package_id] = publishedfileid
                    pfids.append(publishedfileid)
        logger.info(f"Collected {len(active_mods)} active mods for export")
        if len(pfids) > 0:  # No empty queries...
            # Compile list of Steam Workshop publishing preview images that correspond
            # to a Steam mod in the active mod list
            webapi_response = ISteamRemoteStorage_GetPublishedFileDetails(pfids)
            if webapi_response is not None:
                for metadata in webapi_response:
                    pfid = metadata["publishedfileid"]
                    if metadata["result"] != 1:
                        logger.warning("Rentry.co export: Unable to get data for mod!")
                        logger.warning(
                            f"Invalid result returned from WebAPI for mod {pfid}"
                        )
                    else:
                        # Retrieve the preview image URL from the response
                        active_steam_mods_pfid_to_preview_url[pfid] = metadata[
                            "preview_url"
                        ]
        # Build our report
        active_mods_rentry_report = (
            "# RimWorld mod list       ![](https://github.com/RimSort/RimSort/blob/main/docs/rentry_preview.png?raw=true)"
            + f"\nCreated with RimSort {AppInfo().app_version}"
            + f"\nMod list was created for game version: `{self.metadata_manager.game_version}`"
            + "\n!!! info Local mods are marked as yellow labels with packageid in brackets."
            + f"\n\n\n\n!!! note Mod list length: `{len(active_mods)}`\n"
        )
        # Add a line for each mod
        for package_id in active_mods:
            count = active_mods.index(package_id) + 1
            uuid = active_mods_packageid_to_uuid[package_id]
            if self.metadata_manager.internal_local_metadata[uuid].get("name"):
                name = self.metadata_manager.internal_local_metadata[uuid]["name"]
            else:
                name = "No name specified"
            if (
                self.metadata_manager.internal_local_metadata[uuid].get("steamcmd")
                or self.metadata_manager.internal_local_metadata[uuid]["data_source"]
                == "workshop"
            ) and active_steam_mods_packageid_to_pfid.get(package_id):
                pfid = active_steam_mods_packageid_to_pfid[package_id]
                if active_steam_mods_pfid_to_preview_url.get(pfid):
                    preview_url = (
                        active_steam_mods_pfid_to_preview_url[pfid]
                        + "?imw=100&imh=100&impolicy=Letterbox"
                    )
                else:
                    preview_url = "https://github.com/RimSort/RimSort/blob/main/docs/rentry_steam_icon.png?raw=true"
                if self.metadata_manager.internal_local_metadata[uuid].get("steam_url"):
                    url = self.metadata_manager.internal_local_metadata[uuid][
                        "steam_url"
                    ]
                elif self.metadata_manager.internal_local_metadata[uuid].get("url"):
                    url = self.metadata_manager.internal_local_metadata[uuid]["url"]
                else:
                    url = None
                if url is None:
                    if package_id in active_steam_mods_packageid_to_pfid.keys():
                        active_mods_rentry_report = (
                            active_mods_rentry_report
                            + f"\n{str(count) + '.'} ![]({preview_url}) {name} packageid: {package_id}"
                        )
                else:
                    if package_id in active_steam_mods_packageid_to_pfid.keys():
                        active_mods_rentry_report = (
                            active_mods_rentry_report
                            + f"\n{str(count) + '.'} ![]({preview_url}) [{name}]({url} packageid: {package_id})"
                        )
            # if active_mods_json[uuid]["data_source"] == "expansion" or (
            #     active_mods_json[uuid]["data_source"] == "local"
            #     and not active_mods_json[uuid].get("steamcmd")
            # ):
            else:
                if self.metadata_manager.internal_local_metadata[uuid].get("url"):
                    url = self.metadata_manager.internal_local_metadata[uuid]["url"]
                elif self.metadata_manager.internal_local_metadata[uuid].get(
                    "steam_url"
                ):
                    url = self.metadata_manager.internal_local_metadata[uuid][
                        "steam_url"
                    ]
                else:
                    url = None
                if url is None:
                    active_mods_rentry_report = (
                        active_mods_rentry_report
                        + f"\n!!! warning {str(count) + '.'} {name} "
                        + "{"
                        + f"packageid: {package_id}"
                        + "} "
                    )
                else:
                    active_mods_rentry_report = (
                        active_mods_rentry_report
                        + f"\n!!! warning {str(count) + '.'} [{name}]({url}) "
                        + "{"
                        + f"packageid: {package_id}"
                        + "} "
                    )
        # Upload the report to Rentry.co
        rentry_uploader = RentryUpload(active_mods_rentry_report)
        successful = rentry_uploader.upload_success
        host = (
            urlparse(rentry_uploader.url).hostname
            if successful and (rentry_uploader.url is not None)
            else None
        )
        if rentry_uploader.url and host and host.endswith("rentry.co"):
            copy_to_clipboard_safely(rentry_uploader.url)
            dialogue.show_information(
                title=self.tr("Uploaded active mod list"),
                text=self.tr(
                    "Uploaded active mod list report to Rentry.co! The URL has been copied to your clipboard:\n\n{rentry_uploader.url}"
                ).format(rentry_uploader=rentry_uploader),
                information=self.tr('Click "Show Details" to see the full report!'),
                details=f"{active_mods_rentry_report}",
            )
        else:
            dialogue.show_warning(
                title=self.tr("Failed to upload"),
                text=self.tr("Failed to upload exported active mod list to Rentry.co"),
            )

    def _do_open_app_directory(self) -> None:
        app_directory = os.getcwd()
        logger.info(f"Opening app directory: {app_directory}")
        platform_specific_open(app_directory)

    def _do_open_settings_directory(self) -> None:
        settings_directory = AppInfo().app_storage_folder
        logger.info(f"Opening settings directory: {settings_directory}")
        platform_specific_open(settings_directory)

    def _do_open_rimsort_logs_directory(self) -> None:
        logs_directory = AppInfo().user_log_folder
        logger.info(f"Opening RimSort logs directory: {logs_directory}")
        platform_specific_open(logs_directory)

    def _do_open_rimworld_directory(self) -> None:
        self._open_directory("RimWorld game", "game_folder")

    def _do_open_rimworld_config_directory(self) -> None:
        self._open_directory("RimWorld config", "config_folder")

    def _do_open_rimworld_logs_directory(self) -> None:
        user_home = Path.home()
        logs_directory = None
        if SystemInfo().operating_system == SystemInfo.OperatingSystem.MACOS:
            logs_directory = (
                user_home / "Library/Logs/Ludeon Studios/RimWorld by Ludeon Studios"
            )
        elif SystemInfo().operating_system == SystemInfo.OperatingSystem.LINUX:
            logs_directory = (
                user_home / ".config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios"
            )
        elif SystemInfo().operating_system == SystemInfo.OperatingSystem.WINDOWS:
            logs_directory = (
                user_home / "AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios"
            )

        if logs_directory and logs_directory.exists():
            logger.info(f"Opening RimWorld logs directory: {logs_directory}")
            platform_specific_open(logs_directory)
        else:
            self.show_dialog_specify_paths("RimWorld logs")

    def _do_open_local_mods_directory(self) -> None:
        self._open_directory("Local mods", "local_folder")

    def _do_open_steam_mods_directory(self) -> None:
        self._open_directory("Steam mods", "workshop_folder")

    def _open_directory(self, directory_name: str, attribute: str) -> None:
        current_instance = self.settings_controller.settings.current_instance
        directory = getattr(
            self.settings_controller.settings.instances[current_instance],
            attribute,
            None,
        )
        if directory and os.path.exists(directory):
            logger.info(f"Opening {directory_name} directory: {directory}")
            platform_specific_open(directory)
        else:
            self.show_dialog_specify_paths(directory_name)

    def show_dialog_specify_paths(self, directory_name: str) -> None:
        logger.error(f"Could not open {directory_name} directory")
        answer = dialogue.show_dialogue_conditional(
            title=self.tr("Could not open directory"),
            text=self.tr("{directory_name} path does not exist or is not set.").format(
                directory_name=directory_name
            ),
            information=self.tr("Would you like to set the path now?"),
            button_text_override=[self.tr("Open settings")],
        )
        if "settings" in answer:
            self.settings_controller.show_settings_dialog()

    @Slot()
    def _on_do_upload_rimsort_log(self) -> None:
        self._upload_log(AppInfo().user_log_folder / "RimSort.log")

    @Slot()
    def _on_do_upload_rimsort_old_log(self) -> None:
        self._upload_log(AppInfo().user_log_folder / "RimSort.old.log")

    @Slot()
    def _on_do_upload_rimworld_log(self) -> None:
        player_log_path = (
            Path(
                self.settings_controller.settings.instances[
                    self.settings_controller.settings.current_instance
                ].config_folder
            ).parent
            / "Player.log"
        )

        self._upload_log(player_log_path)

    def _upload_log(self, path: Path) -> None:
        if not os.path.exists(path):
            dialogue.show_warning(
                title=self.tr("File not found"),
                text=self.tr("The file you are trying to upload does not exist."),
                information=self.tr("File: {path}").format(path=path),
            )
            return

        success, ret = self.do_threaded_loading_animation(
            gif_path=str(AppInfo().theme_data_folder / "default-icons" / "rimsort.gif"),
            target=partial(upload_data_to_0x0_st, str(path)),
            text=self.tr("Uploading {path.name} to 0x0.st...").format(path=path),
        )

        if success:
            copy_to_clipboard_safely(ret)
            dialogue.show_information(
                title=self.tr("Uploaded file"),
                text=self.tr("Uploaded {path.name} to http://0x0.st/").format(
                    path=path
                ),
                information=self.tr(
                    "The URL has been copied to your clipboard:\n\n{ret}"
                ).format(ret=ret),
            )
            webbrowser.open(ret)
        else:
            dialogue.show_warning(
                title=self.tr("Failed to upload file."),
                text=self.tr("Failed to upload the file to 0x0.st"),
                information=ret,
            )

    def _do_save(self) -> None:
        """
        Method to save the current list of active mods to the selected ModsConfig.xml
        """
        logger.info("Saving current active mods to ModsConfig.xml")
        active_mods = []
        for uuid in self.mods_panel.active_mods_list.uuids:
            package_id = self.metadata_manager.internal_local_metadata[uuid][
                "packageid"
            ]
            if package_id in active_mods:  # This should NOT be happening
                logger.critical(
                    f"Tried to export more than 1 identical package ids to the same mod list. Skipping duplicate {package_id}"
                )
                continue
            else:  # Otherwise, proceed with adding the mod package_id
                if (
                    package_id in self.duplicate_mods.keys()
                ):  # Check if mod has duplicates
                    if (
                        self.metadata_manager.internal_local_metadata[uuid][
                            "data_source"
                        ]
                        == "workshop"
                    ):
                        active_mods.append(package_id + "_steam")
                        continue  # Append `_steam` suffix if Steam mod, continue to next mod
                active_mods.append(package_id)
        active_mods_uuids, inactive_mods_uuids, _, _ = metadata.get_mods_from_list(
            mod_list=active_mods
        )
        self.active_mods_uuids_last_save = active_mods_uuids
        logger.info(f"Collected {len(active_mods)} active mods for saving")

        mods_config_data = generate_rimworld_mods_list(
            self.metadata_manager.game_version, active_mods
        )
        mods_config_path = str(
            Path(
                self.settings_controller.settings.instances[
                    self.settings_controller.settings.current_instance
                ].config_folder
            )
            / "ModsConfig.xml"
        )
        try:
            json_to_xml_write(mods_config_data, mods_config_path)
        except Exception:
            logger.error("Could not save active mods")
            dialogue.show_fatal_error(
                title=self.tr("Could not save active mods"),
                text=self.tr("Failed to save active mods to file:"),
                information=f"{mods_config_path}",
                details=traceback.format_exc(),
            )
        EventBus().do_save_button_animation_stop.emit()
        # Save current modlists to their respective restore states
        self.active_mods_uuids_restore_state = active_mods_uuids
        self.inactive_mods_uuids_restore_state = inactive_mods_uuids
        logger.info("Finished saving active mods")

    def _do_restore(self) -> None:
        """
        Method to restore the mod lists to the last saved state.
        TODO: restoring after clearing will cause a few harmless lines of
        'Inactive mod count changed to: 0' to appear.
        """
        if (
            self.active_mods_uuids_restore_state
            and self.inactive_mods_uuids_restore_state
        ):
            self.mods_panel.signal_clear_search("Active")
            self.mods_panel.active_mods_filter_data_source_index = len(
                self.mods_panel.data_source_filter_icons
            )
            self.mods_panel.on_active_mods_search_data_source_filter()
            self.mods_panel.signal_clear_search("Inactive")
            self.mods_panel.inactive_mods_filter_data_source_index = len(
                self.mods_panel.data_source_filter_icons
            )
            self.mods_panel.on_inactive_mods_search_data_source_filter()
            logger.info(
                f"Restoring cached mod lists with active list [{len(self.active_mods_uuids_restore_state)}] and inactive list [{len(self.inactive_mods_uuids_restore_state)}]"
            )
            # Disable widgets while inserting
            self.disable_enable_widgets_signal.emit(False)
            # Insert items into lists
            self.__insert_data_into_lists(
                self.active_mods_uuids_restore_state,
                self.inactive_mods_uuids_restore_state,
            )
            # Reenable widgets after inserting
            self.disable_enable_widgets_signal.emit(True)
        else:
            logger.warning(
                "Cached mod lists for restore function not set as client started improperly. Passing on restore"
            )

    # TODDS ACTIONS
    def _do_optimize_textures(self, todds_txt_path: str) -> None:
        # Setup environment
        todds_interface = ToddsInterface(
            preset=self.settings_controller.settings.todds_preset,
            dry_run=self.settings_controller.settings.todds_dry_run,
            overwrite=self.settings_controller.settings.todds_overwrite,
        )

        # UI
        self.todds_runner = RunnerPanel(
            todds_dry_run_support=self.settings_controller.settings.todds_dry_run
        )
        self.todds_runner.setWindowTitle("RimSort - todds texture encoder")
        self.todds_runner.show()

        todds_interface.execute_todds_cmd(todds_txt_path, self.todds_runner)

    def _do_delete_dds_textures(self, todds_txt_path: str) -> None:
        todds_interface = ToddsInterface(
            preset="clean",
            dry_run=self.settings_controller.settings.todds_dry_run,
        )

        # UI
        self.todds_runner = RunnerPanel(
            todds_dry_run_support=self.settings_controller.settings.todds_dry_run
        )
        self.todds_runner.setWindowTitle("RimSort - todds texture encoder")
        self.todds_runner.show()

        # Delete all .dds textures using todds
        todds_interface.execute_todds_cmd(todds_txt_path, self.todds_runner)

    # STEAM{CMD, WORKS} ACTIONS

    def _do_browse_workshop(self) -> None:
        self.steam_browser = SteamBrowser(
            "https://steamcommunity.com/app/294100/workshop/", self.metadata_manager
        )
        self.steam_browser.steamcmd_downloader_signal.connect(
            self._do_download_mods_with_steamcmd
        )
        self.steam_browser.steamworks_subscription_signal.connect(
            self._do_steamworks_api_call_animated
        )
        self.steam_browser.show()

    def _do_check_for_workshop_updates(self) -> None:
        # Check internet connection before attempting task
        if not check_internet_connection():
            dialogue.show_internet_connection_error()
            return
        # Query Workshop for update data
        updates_checked = self.do_threaded_loading_animation(
            gif_path=str(
                AppInfo().theme_data_folder / "default-icons" / "steam_api.gif"
            ),
            target=partial(
                metadata.query_workshop_update_data,
                mods=self.metadata_manager.internal_local_metadata,
            ),
            text=self.tr("Checking Steam Workshop mods for updates..."),
        )
        # If we failed to check for updates, skip the comparison(s) & UI prompt
        if updates_checked == "failed":
            dialogue.show_warning(
                title=self.tr("Unable to check for updates"),
                text=self.tr(
                    "RimSort was unable to query Steam WebAPI for update information!\n"
                ),
                information=self.tr("Are you connected to the Internet?"),
            )
            return
        workshop_mod_updater = ModUpdaterPrompt()
        workshop_mod_updater._populate_from_metadata()
        if workshop_mod_updater._row_count() > 0:
            logger.debug("Displaying potential Workshop mod updates")
            workshop_mod_updater.show()
        else:
            self.status_signal.emit(
                self.tr("All Workshop mods appear to be up to date!")
            )

    def _do_setup_steamcmd(self) -> None:
        if (
            self.steamcmd_runner
            and self.steamcmd_runner.process
            and self.steamcmd_runner.process.state() == QProcess.ProcessState.Running
        ):
            dialogue.show_warning(
                title=self.tr("RimSort - SteamCMD setup"),
                text=self.tr("Unable to create SteamCMD runner!"),
                information=self.tr("There is an active process already running!"),
                details=f"PID {self.steamcmd_runner.process.processId()} : "
                + self.steamcmd_runner.process.program(),
            )
            return
        local_mods_path = self.settings_controller.settings.instances[
            self.settings_controller.settings.current_instance
        ].local_folder
        if local_mods_path and os.path.exists(local_mods_path):
            self.steamcmd_runner = RunnerPanel()
            self.steamcmd_runner.setWindowTitle("RimSort - SteamCMD setup")
            self.steamcmd_runner.show()
            self.steamcmd_runner.message("Setting up steamcmd...")
            self.steamcmd_wrapper.setup_steamcmd(
                local_mods_path,
                False,
                self.steamcmd_runner,
            )
            RunnerPanel().process_complete()
        else:
            dialogue.show_warning(
                title=self.tr("RimSort - SteamCMD setup"),
                text=self.tr(
                    "Unable to initiate SteamCMD installation. Local mods path not set!"
                ),
                information=self.tr(
                    "Please configure local mods path in Settings before attempting to install."
                ),
            )

    def _do_download_mods_with_steamcmd(self, publishedfileids: list[str]) -> None:
        logger.debug(
            f"Attempting to download {len(publishedfileids)} mods with SteamCMD"
        )
        # Check for blacklisted mods
        if self.metadata_manager.external_steam_metadata is not None:
            publishedfileids = metadata.check_if_pfids_blacklisted(
                publishedfileids=publishedfileids,
                steamdb=self.metadata_manager.external_steam_metadata,
            )
        # No empty publishedfileids
        if len(publishedfileids) == 0:
            dialogue.show_warning(
                title=self.tr("RimSort"),
                text=self.tr("No PublishedFileIds were supplied in operation."),
                information=self.tr(
                    "Please add mods to list before attempting to download."
                ),
            )
            return
        # Check for existing steamcmd_runner process
        if (
            self.steamcmd_runner
            and self.steamcmd_runner.process
            and self.steamcmd_runner.process.state() == QProcess.ProcessState.Running
        ):
            dialogue.show_warning(
                title=self.tr("RimSort"),
                text=self.tr("Unable to create SteamCMD runner!"),
                information=self.tr("There is an active process already running!"),
                details=f"PID {self.steamcmd_runner.process.processId()} : "
                + self.steamcmd_runner.process.program(),
            )
            return
        # Check for SteamCMD executable
        if self.steamcmd_wrapper.steamcmd and os.path.exists(
            self.steamcmd_wrapper.steamcmd
        ):
            if self.steam_browser:
                self.steam_browser.close()
            steam_db = self.metadata_manager.external_steam_metadata
            if steam_db is None:
                steam_db = {}

            self.steamcmd_runner = RunnerPanel(
                steamcmd_download_tracking=publishedfileids,
                steam_db=steam_db,
            )
            self.steamcmd_runner.steamcmd_downloader_signal.connect(
                self._do_download_mods_with_steamcmd
            )
            self.steamcmd_runner.setWindowTitle("RimSort - SteamCMD downloader")
            self.steamcmd_runner.show()
            self.steamcmd_runner.message(
                f"Downloading {len(publishedfileids)} mods with SteamCMD..."
            )
            self.steamcmd_wrapper.download_mods(
                publishedfileids=publishedfileids,
                runner=self.steamcmd_runner,
                clear_cache=self.settings_controller.settings.instances[
                    self.settings_controller.settings.current_instance
                ].steamcmd_auto_clear_depot_cache,
            )
        else:
            dialogue.show_warning(
                title=self.tr("SteamCMD not found"),
                text=self.tr("SteamCMD executable was not found."),
                information=self.tr(
                    'Please setup an existing SteamCMD prefix, or setup a new prefix with "Setup SteamCMD".'
                ),
            )

    def _do_steamworks_api_call(self, instruction: list[Any]) -> None:
        """
        Create & launch Steamworks API process to handle instructions received from connected signals

        FOR subscription_actions[]...
        :param instruction: a list where:
            instruction[0] is a string that corresponds with the following supported_actions[]
            instruction[1] is an int that corresponds with a subscribed Steam mod's PublishedFileId
                        OR is a list of int that corresponds with multiple subscribed Steam mod's PublishedFileId
        FOR "launch_game_process"...
        :param instruction: a list where:
            instruction[0] is a string that corresponds with the following supported_actions[]
            instruction[1] is a list containing [game_folder_path: str, args: list] respectively
        """
        logger.info(f"Received Steamworks API instruction: {instruction}")
        if not self.steamworks_in_use:
            subscription_actions = ["resubscribe", "subscribe", "unsubscribe"]
            supported_actions = ["launch_game_process"]
            supported_actions.extend(subscription_actions)
            if (
                instruction[0] in supported_actions
            ):  # Actions can be added as multiprocessing.Process; implemented in util.steam.steamworks.wrapper
                if instruction[0] == "launch_game_process":  # SW API init + game launch
                    self.steamworks_in_use = True
                    steamworks_api_process = SteamworksGameLaunch(
                        game_install_path=instruction[1][0],
                        args=instruction[1][1],
                        _libs=str((AppInfo().application_folder / "libs")),
                    )
                    # Start the Steamworks API Process
                    steamworks_api_process.start()
                    logger.info(
                        f"Steamworks API process wrapper started with PID: {steamworks_api_process.pid}"
                    )
                    steamworks_api_process.join()
                    logger.info(
                        f"Steamworks API process wrapper completed for PID: {steamworks_api_process.pid}"
                    )
                    self.steamworks_in_use = False
                elif (
                    instruction[0] in subscription_actions and len(instruction[1]) >= 1
                ):  # ISteamUGC/{SubscribeItem/UnsubscribeItem}
                    logger.info(
                        f"Creating Steamworks API process with instruction {instruction}"
                    )
                    self.steamworks_in_use = True
                    # Maximum processes
                    num_processes = cpu_count()
                    # Chunk the publishedfileids
                    pfids_chunked = list(
                        chunks(
                            _list=instruction[1],
                            limit=ceil(len(instruction[1]) / num_processes),
                        )
                    )
                    # Create a pool of worker processes
                    with Pool(processes=num_processes) as pool:
                        # Create instances of SteamworksSubscriptionHandler for each chunk
                        actions = [
                            SteamworksSubscriptionHandler(
                                action=instruction[0],
                                pfid_or_pfids=chunk,
                                interval=1,
                                _libs=str((AppInfo().application_folder / "libs")),
                            )
                            for chunk in pfids_chunked
                        ]
                        # Map the execution of the subscription actions to the pool of processes
                        pool.map(SteamworksSubscriptionHandler.run, actions)
                    self.steamworks_in_use = False
                else:
                    logger.warning(
                        "Skipping Steamworks API call - only 1 Steamworks API initialization allowed at a time!!"
                    )
            else:
                logger.error(f"Unsupported instruction {instruction}")
                return
        else:
            logger.warning(
                "Steamworks API is already initialized! We do NOT want multiple interactions. Skipping instruction..."
            )

    def _do_steamworks_api_call_animated(
        self, instruction: list[list[str] | str]
    ) -> None:
        publishedfileids = instruction[1]
        logger.debug(f"Attempting to download {len(publishedfileids)} mods with Steam")
        steamdb = self.metadata_manager.external_steam_metadata
        if steamdb is None:
            steamdb = {}
        # Check for blacklisted mods for subscription actions
        if instruction[0] == "subscribe":
            assert isinstance(publishedfileids, list)
            publishedfileids = metadata.check_if_pfids_blacklisted(
                publishedfileids=publishedfileids,
                steamdb=steamdb,
            )
        # No empty publishedfileids
        if len(publishedfileids) == 0:
            dialogue.show_warning(
                title=self.tr("RimSort"),
                text=self.tr("No PublishedFileIds were supplied in operation."),
                information=self.tr(
                    "Please add mods to list before attempting to download."
                ),
            )
            return
        # Close browser if open
        if self.steam_browser:
            self.steam_browser.close()
        # Process API call
        self.do_threaded_loading_animation(
            gif_path=str(AppInfo().theme_data_folder / "default-icons" / "steam.gif"),
            target=partial(self._do_steamworks_api_call, instruction=instruction),
            text=self.tr(
                "Processing Steam subscription action(s) via Steamworks API..."
            ),
        )
        # self._do_refresh()

    # GIT MOD ACTIONS

    def _do_add_zip_mod(self) -> None:
        """
        Opens a QDialogInput that allows the user to select a ZIP file to add to the local mods directory.
        If the user selects "Download", the user will be prompted to enter a URL to download the ZIP file from.
        If the user selects "Select from local", the user will be prompted to select a ZIP file from their local machine.
        The selected ZIP file will be processed and added to the local mods directory.
        """

        # download or select from local
        answer = dialogue.show_dialogue_conditional(
            title=self.tr("Download or select from local"),
            text=self.tr(
                "Please select a ZIP file to add to the local mods directory."
            ),
            information=self.tr(
                "You can download a ZIP file from the internet, or select a file from your local machine."
            ),
            button_text_override=[
                "Download",
                "Select from local",
            ],
        )

        if answer == "Download":
            url, ok = dialogue.show_dialogue_input(
                title=self.tr("Enter zip file url"),
                label=self.tr(
                    "Enter a zip file url (http/https) to download to local mods:"
                ),
            )
            if url and ok:
                fd, temp_path = tempfile.mkstemp(suffix=".zip")
                os.close(fd)

                try:
                    logger.info(f"Downloading {url} to {temp_path}")
                    response = requests.get(url, stream=True)
                    response.raise_for_status()

                    with open(temp_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

                    self._extract_zip_file(temp_path, delete=True)

                except Exception as e:
                    logger.error(f"Failed to download zip file: {e}")
                    dialogue.show_warning(
                        title=self.tr("Failed to download zip file"),
                        text=self.tr("The zip file could not be downloaded."),
                        information=self.tr("File: {file_path}\nError: {e}").format(
                            file_path=temp_path, e=e
                        ),
                    )
        elif answer == "Select from local":
            file_path = dialogue.show_dialogue_file(
                mode="open",
                caption="Choose Zip File",
                _dir=str(AppInfo().app_storage_folder),
                _filter="Zip file (*.zip)",
            )
            if file_path:
                self._extract_zip_file(file_path)

    def _extract_zip_file(self, file_path: str, delete: bool = False) -> None:
        logger.info(f"Selected path: {file_path}")
        if not file_path:
            logger.debug("USER ACTION: cancelled selection!")
            return

        if not os.path.isfile(file_path):
            logger.error(f"ZIP file does not exist: {file_path}")
            dialogue.show_warning(
                title=self.tr("File not found"),
                text=self.tr("The selected file does not exist."),
                information=self.tr("File: {file_path}").format(file_path=file_path),
            )
            return

        base_path = str(
            self.settings_controller.settings.instances[
                self.settings_controller.settings.current_instance
            ].local_folder
        )

        try:
            self._do_extract_zip_to_path(base_path, file_path, delete)
        except NotImplementedError as e:
            logger.error(f"Unsupported compression method: {e}")
            dialogue.show_warning(
                title=self.tr("Unsupported Compression Method"),
                text=self.tr(
                    "This ZIP file uses a compression method that is not supported by this version."
                ),
                information=self.tr("File: {file_path}\nError: {e}").format(
                    file_path=file_path, e=e
                ),
            )
        except (zipfile.BadZipfile, ValueError, PermissionError, OSError) as e:
            logger.error(f"Failed to extract zip file: {e}")
            dialogue.show_warning(
                title=self.tr("Failed to extract zip file"),
                text=self.tr("The zip file could not be extracted."),
                information=self.tr("File: {file_path}\nError: {e}").format(
                    file_path=file_path, e=e
                ),
            )

    def _do_extract_zip_to_path(
        self, base_path: str, file_path: str, delete: bool = False
    ) -> None:
        with ZipFile(file_path) as zipobj:
            zip_contents = zipobj.namelist()
            conflicts = []
            non_conflicts = []

            top_level_dirs = set(p.split("/")[0] for p in zip_contents if "/" in p)
            is_bare_mod = "About" in top_level_dirs and not all(
                p.startswith(tuple(top_level_dirs - {"About"})) for p in zip_contents
            )

            if is_bare_mod or len(top_level_dirs) == 0:
                folder_name = Path(file_path).stem
                base_path = os.path.join(base_path, folder_name)
                os.makedirs(base_path, exist_ok=True)

            for item in zip_contents:
                target_path = os.path.join(base_path, item)
                if os.path.exists(target_path):
                    conflicts.append(item)
                else:
                    non_conflicts.append(item)

            overwrite = True
            if conflicts and not non_conflicts:
                answer = dialogue.show_dialogue_conditional(
                    title=self.tr("Existing files or directories found"),
                    text=self.tr(
                        "All files in the archive already exist in the target path."
                    ),
                    information=self.tr(
                        "How would you like to proceed?\n\n"
                        "1) Overwrite All — Replace all existing files and directories.\n"
                        "2) Cancel — Abort the operation."
                    ),
                    button_text_override=["Overwrite All"],
                )
                if answer != "Overwrite All":
                    return
                overwrite = True
            elif conflicts:
                answer = dialogue.show_dialogue_conditional(
                    title=self.tr("Existing files or directories found"),
                    text=self.tr(
                        "The following files or directories already exist in the target path:"
                    ),
                    information=self.tr(
                        "{conflicts_list}\n\n"
                        "How would you like to proceed?\n\n"
                        "1) Overwrite All — Replace all existing files and directories.\n"
                        "2) Skip Existing — Extract only new files and leave existing ones untouched.\n"
                        "3) Cancel — Abort the extraction."
                    ).format(
                        conflicts_list="<br/>".join(conflicts[:5])
                        + ("<br/>...<br/>" if len(conflicts) > 5 else "")
                    ),
                    button_text_override=["Overwrite All", "Skip Existing"],
                )
                if answer == "Cancel":
                    return
                overwrite = answer == "Overwrite All"

        self._extract_thread = ZipExtractThread(
            file_path, base_path, overwrite_all=overwrite, delete=delete
        )
        self._extract_thread.progress.connect(self._on_extract_progress)
        self._extract_thread.finished.connect(self._on_extract_finished)

        self.progress_window.progressBar.setValue(0)
        self.progress_window.cancel_button.clicked.connect(self._extract_thread.stop)

        self._extract_thread.start()

    def _on_extract_progress(self, percent: int) -> None:
        self.progress_window.setVisible(True)
        self.progress_window.progressBar.setValue(percent)

    def _on_extract_finished(self, success: bool, message: str) -> None:
        if success:
            dialogue.show_information(
                title=self.tr("Extraction completed"),
                text=self.tr("The ZIP file was successfully extracted!"),
                information=message,
            )
        else:
            dialogue.show_warning(
                title=self.tr("Extraction failed"),
                text=self.tr("An error occurred during extraction."),
                information=message,
            )
        self.progress_window.setVisible(False)

    def _do_notify_no_git(self) -> None:
        answer = dialogue.show_dialogue_conditional(  # We import last so we can use gui + utils
            title=self.tr("git not found"),
            text=self.tr("git executable was not found in $PATH!"),
            information=(
                self.tr(
                    "Git integration will not work without Git installed! Do you want to open download page for Git?\n\n"
                    "If you just installed Git, please restart RimSort for the PATH changes to take effect."
                )
            ),
        )
        if answer == "&Yes":
            open_url_browser("https://git-scm.com/downloads")

    def _do_open_rule_editor(
        self, compact: bool, initial_mode: str, packageid: str | None = None
    ) -> None:
        self.rule_editor = RuleEditor(
            # Initialization options
            compact=compact,
            edit_packageid=packageid,
            initial_mode=initial_mode,
        )
        self.rule_editor._populate_from_metadata()
        self.rule_editor.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.rule_editor.update_database_signal.connect(self._do_update_rules_database)
        self.rule_editor.show()

    def _do_configure_steam_db_file_path(self) -> None:
        # Input file
        logger.info("Opening file dialog to specify Steam DB")
        input_path = dialogue.show_dialogue_file(
            mode="open",
            caption="Choose Steam Workshop Database",
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path}")
        if input_path and os.path.exists(input_path):
            self.settings_controller.settings.external_steam_metadata_file_path = (
                input_path
            )
            self.settings_controller.settings.save()
        else:
            logger.debug("USER ACTION: cancelled selection!")
            return

    def _do_configure_community_rules_db_file_path(self) -> None:
        # Input file
        logger.info("Opening file dialog to specify Community Rules DB")
        input_path = dialogue.show_dialogue_file(
            mode="open",
            caption="Choose Community Rules DB",
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path}")
        if input_path and os.path.exists(input_path):
            self.settings_controller.settings.external_community_rules_file_path = (
                input_path
            )
            self.settings_controller.settings.save()
        else:
            logger.debug("USER ACTION: cancelled selection!")
            return

    def _do_configure_steam_database_repo(self) -> None:
        """
        Opens a QDialogInput that allows user to edit their Steam DB repo
        This URL is used for Steam DB repo related actions.
        """
        args, ok = dialogue.show_dialogue_input(
            title=self.tr("Edit Steam DB repo"),
            label=self.tr("Enter URL (https://github.com/AccountName/RepositoryName):"),
            text=self.settings_controller.settings.external_steam_metadata_repo,
        )
        if ok:
            self.settings_controller.settings.external_steam_metadata_repo = args
            self.settings_controller.settings.save()

    def _do_configure_community_rules_db_repo(self) -> None:
        """
        Opens a QDialogInput that allows user to edit their Community Rules
        DB repo. This URL is used for Steam DB repo related actions.
        """
        args, ok = dialogue.show_dialogue_input(
            title=self.tr("Edit Community Rules DB repo"),
            label=self.tr("Enter URL (https://github.com/AccountName/RepositoryName):"),
            text=self.settings_controller.settings.external_community_rules_repo,
        )
        if ok:
            self.settings_controller.settings.external_community_rules_repo = args
            self.settings_controller.settings.save()

    def _do_build_database_thread(self) -> None:
        # Prompt user file dialog to choose/create new DB
        logger.info("Opening file dialog to specify output file")
        output_path = dialogue.show_dialogue_file(
            mode="save",
            caption="Designate output path",
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        # Check file path and launch DB Builder with user configured mode
        if output_path:  # If output path was returned
            logger.info(f"Selected path: {output_path}")
            if not output_path.endswith(".json"):
                output_path += ".json"  # Handle file extension if needed
            # RimWorld Workshop contains 30,000+ PublishedFileIDs (mods) as of 2023!
            # "No": Produce accurate, complete DB by QueryFiles via WebAPI
            # Queries ALL available PublishedFileIDs (mods) it can find via Steam WebAPI.
            # Does not use metadata from locally available mods. This means no packageids!
            if self.settings_controller.settings.db_builder_include == "no_local":
                self.db_builder = metadata.SteamDatabaseBuilder(
                    apikey=self.settings_controller.settings.steam_apikey,
                    appid=294100,
                    database_expiry=self.settings_controller.settings.database_expiry,
                    mode=self.settings_controller.settings.db_builder_include,
                    output_database_path=output_path,
                    get_appid_deps=self.settings_controller.settings.build_steam_database_dlc_data,
                    update=self.settings_controller.settings.build_steam_database_update_toggle,
                )
            # "Yes": Produce accurate, possibly semi-incomplete DB without QueryFiles via API
            # CAN produce a complete DB! Only includes metadata parsed from mods you have downloaded.
            # Produces DB which contains metadata from locally available mods. Includes packageids!
            elif self.settings_controller.settings.db_builder_include == "all_mods":
                self.db_builder = metadata.SteamDatabaseBuilder(
                    apikey=self.settings_controller.settings.steam_apikey,
                    appid=294100,
                    database_expiry=self.settings_controller.settings.database_expiry,
                    mode=self.settings_controller.settings.db_builder_include,
                    output_database_path=output_path,
                    get_appid_deps=self.settings_controller.settings.build_steam_database_dlc_data,
                    mods=self.metadata_manager.internal_local_metadata,
                    update=self.settings_controller.settings.build_steam_database_update_toggle,
                )
            # Create query runner
            self.query_runner = RunnerPanel()
            self.query_runner.closing_signal.connect(self.db_builder.terminate)
            self.query_runner.setWindowTitle(
                f"RimSort - DB Builder ({self.settings_controller.settings.db_builder_include})"
            )
            self.query_runner.progress_bar.show()
            self.query_runner.show()
            # Connect message signal
            self.db_builder.db_builder_message_output_signal.connect(
                self.query_runner.message
            )
            # Start DB builder
            self.db_builder.start()
        else:
            logger.debug("USER ACTION: cancelled selection...")

    def _do_blacklist_action_steamdb(self, instruction: list[Any]) -> None:
        if (
            self.metadata_manager.external_steam_metadata_path
            and self.metadata_manager.external_steam_metadata
            and len(self.metadata_manager.external_steam_metadata.keys()) > 0
        ):
            logger.info(f"Updating SteamDB blacklist status for item: {instruction}")
            # Retrieve instruction passed from signal
            publishedfileid = instruction[0]
            blacklist = instruction[1]
            if blacklist:  # Only deal with comment if we are adding a mod to blacklist
                comment = instruction[2]
            else:
                comment = None
            # Check if our DB has an entry for the mod we are editing
            if not self.metadata_manager.external_steam_metadata.get(publishedfileid):
                self.metadata_manager.external_steam_metadata.setdefault(
                    publishedfileid, {}
                )
            # Edit our metadata
            if blacklist and comment:
                self.metadata_manager.external_steam_metadata[publishedfileid][
                    "blacklist"
                ] = {
                    "value": blacklist,
                    "comment": comment,
                }
            else:
                self.metadata_manager.external_steam_metadata[publishedfileid].pop(
                    "blacklist", None
                )
            logger.debug("Updating previous database with new metadata...\n")
            with open(
                self.metadata_manager.external_steam_metadata_path,
                "w",
                encoding="utf-8",
            ) as output:
                json.dump(
                    {
                        "version": int(
                            time.time()
                            + self.settings_controller.settings.database_expiry
                        ),
                        "database": self.metadata_manager.external_steam_metadata,
                    },
                    output,
                    indent=4,
                )
            self._do_refresh()

    def _do_download_entire_workshop(self, action: str) -> None:
        # DB Builder is used to run DQ and grab entirety of
        # any available Steam Workshop PublishedFileIDs
        self.db_builder = metadata.SteamDatabaseBuilder(
            apikey=self.settings_controller.settings.steam_apikey,
            appid=294100,
            database_expiry=self.settings_controller.settings.database_expiry,
            mode="pfids_by_appid",
        )
        # Create query runner
        self.query_runner = RunnerPanel()
        self.query_runner.closing_signal.connect(self.db_builder.terminate)
        self.query_runner.setWindowTitle("RimSort - DB Builder PublishedFileIDs query")
        self.query_runner.progress_bar.show()
        self.query_runner.show()
        # Connect message signal
        self.db_builder.db_builder_message_output_signal.connect(
            self.query_runner.message
        )
        # Start DB builder
        self.db_builder.start()
        loop = QEventLoop()
        self.db_builder.finished.connect(loop.quit)
        loop.exec_()
        if len(self.db_builder.publishedfileids) == 0:
            dialogue.show_warning(
                title=self.tr("No PublishedFileIDs"),
                text=self.tr("DB Builder query did not return any PublishedFileIDs!"),
                information=self.tr(
                    "This is typically caused by invalid/missing Steam WebAPI key, or a connectivity issue to the Steam WebAPI.\n"
                    + "PublishedFileIDs are needed to retrieve mods from Steam!"
                ),
            )
        else:
            self.query_runner.close()
            self.query_runner = None
            if "steamcmd" in action:
                # Filter out existing SteamCMD mods
                mod_pfid = None
                for (
                    metadata_values
                ) in self.metadata_manager.internal_local_metadata.values():
                    if metadata_values.get("steamcmd"):
                        mod_pfid = metadata_values.get("publishedfileid")
                    if mod_pfid and mod_pfid in self.db_builder.publishedfileids:
                        logger.debug(
                            f"Skipping download of existing SteamCMD mod: {mod_pfid}"
                        )
                        self.db_builder.publishedfileids.remove(mod_pfid)
                self._do_download_mods_with_steamcmd(self.db_builder.publishedfileids)
            elif "steamworks" in action:
                answer = dialogue.show_dialogue_conditional(
                    title=self.tr("Are you sure?"),
                    text=self.tr("Here be dragons."),
                    information=self.tr(
                        "WARNING: It is NOT recommended to subscribe to this many mods at once via Steam. "
                        + "Steam has limitations in place seemingly intentionally and unintentionally for API subscriptions. "
                        + "It is highly recommended that you instead download these mods to a SteamCMD prefix by using SteamCMD. "
                        + "This can take longer due to rate limits, but you can also re-use the script generated by RimSort with "
                        + "a separate, authenticated instance of SteamCMD, if you do not want to anonymously download via RimSort."
                    ),
                )
                if answer == "&Yes":
                    for (
                        metadata_values
                    ) in self.metadata_manager.internal_local_metadata.values():
                        mod_pfid = metadata_values.get("publishedfileid")
                        if (
                            metadata_values["data_source"] == "workshop"
                            and mod_pfid
                            and mod_pfid in self.db_builder.publishedfileids
                        ):
                            logger.warning(
                                f"Skipping download of existing Steam mod: {mod_pfid}"
                            )
                            self.db_builder.publishedfileids.remove(mod_pfid)
                    self._do_steamworks_api_call_animated(
                        [
                            "subscribe",
                            [
                                eval(str_pfid)
                                for str_pfid in self.db_builder.publishedfileids
                            ],
                        ]
                    )

    def _do_edit_steam_webapi_key(self) -> None:
        """
        Opens a QDialogInput that allows the user to edit their Steam API-key
        that are configured to be passed to the "Dynamic Query" feature for
        the Steam Workshop metadata needed for sorting
        """
        args, ok = dialogue.show_dialogue_input(
            title=self.tr("Edit Steam WebAPI key"),
            label=self.tr("Enter your personal 32 character Steam WebAPI key here:"),
            text=self.settings_controller.settings.steam_apikey,
        )
        if ok:
            self.settings_controller.settings.steam_apikey = args
            self.settings_controller.settings.save()

    def _do_generate_metadata_comparison_report(self) -> None:
        """
        Open a user-selected JSON file. Calculate and display discrepancies
        found between database and this file.
        """
        # TODO: Refactor this...
        discrepancies: list[str] = []
        database_a_deps: dict[str, Any] = {}
        database_b_deps: dict[str, Any] = {}
        # Notify user
        dialogue.show_information(
            title=self.tr("Steam DB Builder"),
            text=self.tr(
                "This operation will compare 2 databases, A & B, by checking dependencies from A with dependencies from B."
            ),
            information=self.tr(
                "- This will produce an accurate comparison of dependency data between 2 Steam DBs.\n"
                + "A report of discrepancies is generated. You will be prompted for these paths in order:\n"
                + "\n\t1) Select input A"
                + "\n\t2) Select input B",
            ),
        )
        # Input A
        logger.info("Opening file dialog to specify input file A")
        input_path_a = dialogue.show_dialogue_file(
            mode="open",
            caption='Input "to-be-updated" database, input A',
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path_a}")
        if input_path_a and os.path.exists(input_path_a):
            with open(input_path_a, encoding="utf-8") as f:
                json_string = f.read()
                logger.debug("Reading info...")
                db_input_a = json.loads(json_string)
                logger.debug("Retrieved database A...")
        else:
            logger.warning("Steam DB Builder: User cancelled selection...")
            return
        # Input B
        logger.info("Opening file dialog to specify input file B")
        input_path_b = dialogue.show_dialogue_file(
            mode="open",
            caption='Input "to-be-updated" database, input A',
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path_b}")
        if input_path_b and os.path.exists(input_path_b):
            with open(input_path_b, encoding="utf-8") as f:
                json_string = f.read()
                logger.debug("Reading info...")
                db_input_b = json.loads(json_string)
                logger.debug("Retrieved database B...")
        else:
            logger.debug("Steam DB Builder: User cancelled selection...")
            return
        for k, v in db_input_a["database"].items():
            # print(k, v['dependencies'])
            database_b_deps[k] = set()
            if v.get("dependencies"):
                for dep_key in v["dependencies"]:
                    database_b_deps[k].add(dep_key)
        for k, v in db_input_b["database"].items():
            # print(k, v['dependencies'])
            if k in database_b_deps:
                database_a_deps[k] = set()
                if v.get("dependencies"):
                    for dep_key in v["dependencies"]:
                        database_a_deps[k].add(dep_key)
        no_deps_str = "*no explicit dependencies listed*"
        database_a_total_deps = len(database_a_deps)
        database_b_total_deps = len(database_b_deps)
        report = (
            "\nSteam DB comparison report:\n"
            + "\nTotal # of deps from database A:\n"
            + f"{database_a_total_deps}"
            + "\nTotal # of deps from database B:\n"
            + f"{database_b_total_deps}"
            + f"\nTotal # of discrepancies:\n{len(discrepancies)}"
        )
        comparison_skipped = []
        for k, v in database_b_deps.items():
            if db_input_a["database"][k].get("unpublished"):
                comparison_skipped.append(k)
                # logger.debug(f"Skipping comparison for unpublished mod: {k}")
            else:
                # If the deps are different...
                if v != database_a_deps.get(k):
                    pp = database_a_deps.get(k)
                    if pp:
                        # Normalize here (get rid of core/dlc deps)
                        if v != pp:
                            discrepancies.append(k)
                            pp_total = len(pp)
                            v_total = len(v)
                            if v == set():
                                v = no_deps_str
                            if pp == set():
                                pp = no_deps_str
                            mod_name = db_input_b["database"][k]["name"]
                            report += f"\n\nDISCREPANCY FOUND for {k}:"
                            report += f"\nhttps://steamcommunity.com/sharedfiles/filedetails/?id={k}"
                            report += f"\nMod name: {mod_name}"
                            report += (
                                f"\n\nDatabase A:\n{v_total} dependencies found:\n{v}"
                            )
                            report += (
                                f"\n\nDatabase B:\n{pp_total} dependencies found:\n{pp}"
                            )
        logger.debug(
            f"Comparison skipped for {len(comparison_skipped)} unpublished mods: {comparison_skipped}"
        )
        dialogue.show_information(
            title=self.tr("Steam DB Builder"),
            text=self.tr("Steam DB comparison report: {len} found").format(
                len=len(discrepancies)
            ),
            information=self.tr("Click 'Show Details' to see the full report!"),
            details=report,
        )

    def _do_merge_databases(self) -> None:
        # Notify user
        dialogue.show_information(
            title=self.tr("Steam DB Builder"),
            text=self.tr(
                "This operation will merge 2 databases, A & B, by recursively updating A with B, barring exceptions."
            ),
            information=self.tr(
                "- This will effectively recursively overwrite A's key/value with B's key/value to the resultant database.\n"
                + "- Exceptions will not be recursively updated. Instead, they will be overwritten with B's key entirely.\n"
                + "- The following exceptions will be made:\n"
                + "\n\t{DB_BUILDER_RECURSE_EXCEPTIONS}\n\n"
                + "The resultant database, C, is saved to a user-specified path. You will be prompted for these paths in order:\n"
                + "\n\t1) Select input A (db to-be-updated)"
                + "\n\t2) Select input B (update source)"
                + "\n\t3) Select output C (resultant db)"
            ).format(
                DB_BUILDER_RECURSE_EXCEPTIONS=app_constants.DB_BUILDER_RECURSE_EXCEPTIONS
            ),
        )
        # Input A
        logger.info("Opening file dialog to specify input file A")
        input_path_a = dialogue.show_dialogue_file(
            mode="open",
            caption='Input "to-be-updated" database, input A',
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path_a}")
        if input_path_a and os.path.exists(input_path_a):
            with open(input_path_a, encoding="utf-8") as f:
                json_string = f.read()
                logger.debug("Reading info...")
                db_input_a = json.loads(json_string)
                logger.debug("Retrieved database A...")
        else:
            logger.warning("Steam DB Builder: User cancelled selection...")
            return
        # Input B
        logger.info("Opening file dialog to specify input file B")
        input_path_b = dialogue.show_dialogue_file(
            mode="open",
            caption='Input "update source" database, input B',
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path_b}")
        if input_path_b and os.path.exists(input_path_b):
            with open(input_path_b, encoding="utf-8") as f:
                json_string = f.read()
                logger.debug("Reading info...")
                db_input_b = json.loads(json_string)
                logger.debug("Retrieved database B...")
        else:
            logger.debug("Steam DB Builder: User cancelled selection...")
            return
        # Output C
        db_output_c = db_input_a.copy()
        metadata.recursively_update_dict(
            db_output_c,
            db_input_b,
            prune_exceptions=app_constants.DB_BUILDER_PRUNE_EXCEPTIONS,
            recurse_exceptions=app_constants.DB_BUILDER_RECURSE_EXCEPTIONS,
        )
        logger.info("Updated DB A with DB B!")
        logger.debug(db_output_c)
        logger.info("Opening file dialog to specify output file")
        output_path = dialogue.show_dialogue_file(
            mode="save",
            caption="Designate output path for resultant database:",
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {output_path}")
        if output_path:
            if not output_path.endswith(".json"):
                output_path += ".json"  # Handle file extension if needed
            with open(output_path, "w", encoding="utf-8") as output:
                json.dump(db_output_c, output, indent=4)
        else:
            logger.warning("Steam DB Builder: User cancelled selection...")
            return

    def _do_update_rules_database(self, instruction: list[Any]) -> None:
        rules_source = instruction[0]
        rules_data = instruction[1]
        # Get path based on rules source
        if (
            rules_source == "Community Rules"
            and self.metadata_manager.external_community_rules_path
        ):
            path = self.metadata_manager.external_community_rules_path
        elif rules_source == "User Rules" and str(
            AppInfo().databases_folder / "userRules.json"
        ):
            path = str(AppInfo().databases_folder / "userRules.json")
        else:
            logger.warning(
                f"No {rules_source} file path is set. There is no configured database to update!"
            )
            return
        # Retrieve original database
        try:
            with open(path, encoding="utf-8") as f:
                json_string = f.read()
                logger.debug("Reading info...")
                db_input_a = json.loads(json_string)
                logger.debug(
                    f"Retrieved copy of existing {rules_source} database to update."
                )
        except Exception:
            logger.error("Failed to read info from existing database")
            dialogue.show_warning(
                title=self.tr("Failed to read existing database"),
                text=self.tr("Failed to read the existing database!"),
                information=self.tr("Path: {path}").format(path=path),
            )
            return
        db_input_b = {"timestamp": int(time.time()), "rules": rules_data}
        db_output_c = db_input_a.copy()
        # Update database in place
        metadata.recursively_update_dict(
            db_output_c,
            db_input_b,
            prune_exceptions=app_constants.DB_BUILDER_PRUNE_EXCEPTIONS,
            recurse_exceptions=app_constants.DB_BUILDER_RECURSE_EXCEPTIONS,
        )
        # Overwrite rules database
        answer = dialogue.show_dialogue_conditional(
            title=self.tr("RimSort - DB Builder"),
            text=self.tr("Do you want to continue?"),
            information=self.tr(
                "This operation will overwrite the {rules_source} database located at the following path:\n\n{path}"
            ).format(rules_source=rules_source, path=path),
        )
        if answer == "&Yes":
            with open(path, "w", encoding="utf-8") as output:
                json.dump(db_output_c, output, indent=4)
            self._do_refresh()
        else:
            logger.debug("USER ACTION: declined to continue rules database update.")

    def _do_set_database_expiry(self) -> None:
        """
        Opens a QDialogInput that allows the user to edit their preferred
        WebAPI Query Expiry (in seconds)
        """
        args, ok = dialogue.show_dialogue_input(
            title=self.tr("Edit SteamDB expiry:"),
            label=self.tr(
                "Enter your preferred expiry duration in seconds (default 1 week/604800 sec):"
            ),
            text=str(self.settings_controller.settings.database_expiry),
        )
        if ok:
            try:
                self.settings_controller.settings.database_expiry = int(args)
                self.settings_controller.settings.save()
            except ValueError:
                dialogue.show_warning(
                    self.tr(
                        "Tried configuring Dynamic Query with a value that is not an integer."
                    ),
                    self.tr(
                        "Please reconfigure the expiry value with an integer in terms of the seconds from epoch you would like your query to expire."
                    ),
                )

    @Slot()
    def _on_settings_have_changed(self) -> None:
        instance = self.settings_controller.settings.instances.get(
            self.settings_controller.settings.current_instance
        )
        if not instance:
            logger.warning(
                f"Tried to access instance {self.settings_controller.settings.current_instance} that does not exist!"
            )
            return None

        steamcmd_prefix = instance.steamcmd_install_path

        if steamcmd_prefix:
            self.steamcmd_wrapper.initialize_prefix(
                steamcmd_prefix=str(steamcmd_prefix),
                validate=self.settings_controller.settings.steamcmd_validate_downloads,
            )
        self.steamcmd_wrapper.validate_downloads = (
            self.settings_controller.settings.steamcmd_validate_downloads
        )

    @Slot()
    def _on_do_upload_log(self) -> None:
        self._upload_log(AppInfo().user_log_folder / (AppInfo().app_name + ".log"))

    @Slot()
    def _on_do_download_all_mods_via_steamcmd(self) -> None:
        self._do_download_entire_workshop("download_entire_workshop_steamcmd")

    @Slot()
    def _on_do_download_all_mods_via_steam(self) -> None:
        self._do_download_entire_workshop("download_entire_workshop_steamworks")

    @Slot()
    def _on_do_build_steam_workshop_database(self) -> None:
        self._do_build_database_thread()

    @Slot()
    def _do_run_game(self) -> None:
        current_instance = self.settings_controller.settings.current_instance
        game_install_path = Path(
            self.settings_controller.settings.instances[current_instance].game_folder
        )
        # Run args is inconsistent and is sometimes a string and sometimes a list
        run_args: list[str] | str = self.settings_controller.settings.instances[
            current_instance
        ].run_args

        run_args = [run_args] if isinstance(run_args, str) else run_args

        steam_client_integration = self.settings_controller.settings.instances[
            current_instance
        ].steam_client_integration

        # If integration is enabled, check for file called "steam_appid.txt" in game folder.
        # in the game folder. If not, create one and add the Steam App ID to it.
        # The Steam App ID is "294100" for RimWorld.
        steam_appid_path = (
            # Checks if the platform is darwin(macOS) and moves us up one directory to get out of the app bundle.
            game_install_path.parent / "steam_appid.txt"
            if sys.platform == "darwin"
            # Else we go directly to the game install path.
            else game_install_path / "steam_appid.txt"
        )
        if steam_client_integration and not steam_appid_path.exists():
            with open(
                steam_appid_path, "w", encoding="utf-8"
            ) as f:
                f.write("294100")
        elif not steam_client_integration and steam_appid_path.exists():
            steam_appid_path.unlink()

        # Launch independent game process without Steamworks API
        launch_game_process(game_install_path=game_install_path, args=run_args)

    @Slot()
    def _use_this_instead_clicked(self) -> None:
        """
        When clicked, opens the Use This Instead panel.
        """
        self.use_this_instead_dialog = UseThisInsteadPanel(
            mod_metadata=self.metadata_manager.internal_local_metadata
        )
        self.use_this_instead_dialog._populate_from_metadata()
        if self.use_this_instead_dialog.editor_model.rowCount() > 0:
            self.use_this_instead_dialog.show()
        else:
            dialogue.show_information(
                title=self.tr("Use This Instead"),
                text=self.tr(
                    'No suggestions were found in the "Use This Instead" database.'
                ),
            )


class ZipExtractThread(QThread):
    progress = Signal(int)
    finished = Signal(bool, str)

    def __init__(
        self,
        zip_path: str,
        target_path: str,
        overwrite_all: bool = True,
        delete: bool = False,
    ):
        super().__init__()
        self.zip_path = zip_path
        self.target_path = target_path
        self.overwrite_all = overwrite_all
        self.delete = delete
        self._should_abort = False

    def run(self) -> None:
        start = time.perf_counter()

        with ZipFile(self.zip_path) as zipobj:
            file_list = zipobj.infolist()
            total_files = len(file_list)
            update_interval = max(1, total_files // 100)

            for i, zip_info in enumerate(file_list):
                if self._should_abort:
                    self.finished.emit(False, "Operation aborted")
                    return
                filename = zip_info.filename
                dst = os.path.join(self.target_path, filename)
                os.makedirs(os.path.dirname(dst), exist_ok=True)

                if zip_info.is_dir():
                    os.makedirs(dst, exist_ok=True)
                else:
                    if os.path.exists(dst) and not self.overwrite_all:
                        continue

                    with zipobj.open(zip_info) as src, open(dst, "wb") as out_file:
                        shutil.copyfileobj(src, out_file)

                if i % update_interval == 0 or i == total_files - 1:
                    self.progress.emit(int((i + 1) / total_files * 100))

        end = time.perf_counter()
        elapsed = end - start
        self.finished.emit(
            True,
            f"{self.zip_path} → {self.target_path}\nTime elapsed: {elapsed:.2f} seconds",
        )
        if self.delete:
            os.remove(self.zip_path)

    def stop(self) -> None:
        self._should_abort = True


class ProgressWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Extract Zip")
        self.resize(300, 100)

        self.progressBar = QProgressBar()
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(100)
        self.progressBar.setValue(0)
        self.progressBar.setVisible(True)

        self.cancel_button = QPushButton("Cancel")

        layout = QVBoxLayout()
        layout.addWidget(self.progressBar)
        self.setLayout(layout)
        layout.addWidget(self.cancel_button)
