import datetime
import json
import os
import platform
import subprocess
import sys
import time
import traceback
import webbrowser
from functools import partial
from gc import collect
from io import BytesIO
from math import ceil
from multiprocessing import Pool, cpu_count
from pathlib import Path
from tempfile import gettempdir
from typing import Any, Callable, Self
from urllib.parse import urlparse
from zipfile import ZipFile

from loguru import logger

from app.utils.generic import platform_specific_open
from app.utils.system_info import SystemInfo

# GitPython depends on git executable being available in PATH
try:
    from git import Repo
    from git.exc import GitCommandError

    GIT_EXISTS = True
except ImportError:
    logger.warning(
        "git not detected in your PATH! Do you have git installed...? git integration will be disabled! You may need to restart the app if you installed it."
    )
    GIT_EXISTS = False

from github import Github
from PySide6.QtCore import (
    QEventLoop,
    QObject,
    QProcess,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel
from requests import get as requests_get

import app.utils.constants as app_constants
import app.utils.metadata as metadata
import app.views.dialogue as dialogue
from app.controllers.sort_controller import Sorter
from app.models.animations import LoadingAnimation
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus
from app.utils.generic import (
    chunks,
    copy_to_clipboard_safely,
    delete_files_except_extension,
    launch_game_process,
    open_url_browser,
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
from app.utils.todds.wrapper import ToddsInterface
from app.utils.xml import json_to_xml_write
from app.views.mod_info_panel import ModInfo
from app.views.mods_panel import ModListWidget, ModsPanel, ModsPanelSortKey
from app.windows.missing_mods_panel import MissingModsPrompt
from app.windows.rule_editor_panel import RuleEditor
from app.windows.runner_panel import RunnerPanel
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

    def __init__(
        self, settings_controller: SettingsController
    ) -> None:
        """
        Initialize the main content panel.

        :param settings_controller: the settings controller for the application
        """
        if not hasattr(self, "initialized"):
            super(MainContent, self).__init__()
            logger.debug("Initializing MainContent")

            self.settings_controller = settings_controller

            EventBus().settings_have_changed.connect(self._on_settings_have_changed)
            EventBus().do_check_for_application_update.connect(
                self._do_check_for_update
            )
            EventBus().do_validate_steam_client.connect(self._do_validate_steam_client)
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
            EventBus().do_upload_community_rules_db_to_github.connect(
                self._on_do_upload_community_db_to_github
            )
            EventBus().do_download_community_rules_db_from_github.connect(
                self._on_do_download_community_db_from_github
            )
            EventBus().do_upload_steam_workshop_db_to_github.connect(
                self._on_do_upload_steam_workshop_db_to_github
            )
            EventBus().do_download_steam_workshop_db_from_github.connect(
                self._on_do_download_steam_workshop_db_from_github
            )
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
            EventBus().do_open_rimworld_logs_directory.connect(
                self._do_open_rimworld_logs_directory
            )

            # Edit Menu bar Eventbus
            EventBus().do_rule_editor.connect(
                lambda: self.actions_slot("open_community_rules_with_rule_editor")
            )

            # Download Menu bar Eventbus
            EventBus().do_add_git_mod.connect(self._do_add_git_mod)
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
            self.mods_panel.active_mods_list.update_git_mods_signal.connect(
                self._check_git_repos_for_update
            )
            self.mods_panel.inactive_mods_list.update_git_mods_signal.connect(
                self._check_git_repos_for_update
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
                title="Essential path(s)",
                text="Essential path(s) are invalid or not set!\n",
                information=(
                    "RimSort requires, at the minimum, for the game install folder and the "
                    "config folder paths to be set, and that the paths both exist. Please set "
                    "both of these manually or by using the autodetect functionality.\n\n"
                    "Would you like to configure them now?"
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
            self.mods_panel.active_mods_list.recalculate_warnings_signal.emit()
            self.mods_panel.inactive_mods_list.recalculate_warnings_signal.emit()

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
            self.mods_panel.active_mods_list.recalculate_warnings_signal.emit()
            self.mods_panel.inactive_mods_list.recalculate_warnings_signal.emit()

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
            title="Duplicate mod(s) found",
            text="Duplicate mods(s) found for package ID(s) in your ModsConfig.xml (active mods list)",
            information=(
                "The following list of mods were set active in your ModsConfig.xml and "
                "duplicate instances were found of these mods in your mod data sources. "
                "The vanilla game will use the first 'local mod' of a particular package ID "
                "that is found - so RimSort will also adhere to this logic."
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
                steam_workshop_metadata=self.metadata_manager.external_steam_metadata,
            )
            self.missing_mods_prompt._populate_from_metadata()
            self.missing_mods_prompt.steamcmd_downloader_signal.connect(
                self._do_download_mods_with_steamcmd
            )
            self.missing_mods_prompt.steamworks_subscription_signal.connect(
                self._do_steamworks_api_call_animated
            )
            self.missing_mods_prompt.setWindowModality(
                Qt.WindowModality.ApplicationModal
            )
            self.missing_mods_prompt.show()
        else:
            list_of_missing_mods = "\n".join([f"* {mod}" for mod in self.missing_mods])
            dialogue.show_information(
                text="Could not find data for some mods!",
                information=(
                    "The following list of mods were set active in your mods list but "
                    "no data could be found for these mods in local/workshop mod paths. "
                    "\n\nAre your game configuration paths correct?"
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
        self.mod_info_panel.display_mod_info(uuid=uuid)

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
                        todds_txt_file.write(local_mods_target + "\n")
                workshop_mods_target = self.settings_controller.settings.instances[
                    self.settings_controller.settings.current_instance
                ].workshop_folder
                if workshop_mods_target and workshop_mods_target != "":
                    with open(todds_txt_path, "a", encoding="utf-8") as todds_txt_file:
                        todds_txt_file.write(workshop_mods_target + "\n")
            else:
                with open(todds_txt_path, "a", encoding="utf-8") as todds_txt_file:
                    for uuid in self.mods_panel.active_mods_list.uuids:
                        todds_txt_file.write(
                            self.metadata_manager.internal_local_metadata[uuid]["path"]
                            + "\n"
                        )
            if action == "optimize_textures":
                self._do_optimize_textures(todds_txt_path)
            if action == "delete_textures":
                self._do_delete_dds_textures(todds_txt_path)
        if action == "add_git_mod":
            self._do_add_git_mod()
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
        if action == "configure_github_identity":
            self._do_configure_github_identity()
        if action == "configure_steam_database_path":
            self._do_configure_steam_db_file_path()
        if action == "configure_steam_database_repo":
            self._do_configure_steam_database_repo()
        if action == "download_steam_database":
            if GIT_EXISTS:
                self._do_clone_repo_to_path(
                    base_path=str(AppInfo().databases_folder),
                    repo_url=self.settings_controller.settings.external_steam_metadata_repo,
                )
            else:
                self._do_notify_no_git()
        if action == "upload_steam_database":
            if GIT_EXISTS:
                self._do_upload_db_to_repo(
                    repo_url=self.settings_controller.settings.external_steam_metadata_repo,
                    file_name="steamDB.json",
                )
            else:
                self._do_notify_no_git()
        if action == "configure_community_rules_db_path":
            self._do_configure_community_rules_db_file_path()
        if action == "configure_community_rules_db_repo":
            self._do_configure_community_rules_db_repo()
        if action == "download_community_rules_database":
            if GIT_EXISTS:
                self._do_clone_repo_to_path(
                    base_path=str(AppInfo().databases_folder),
                    repo_url=self.settings_controller.settings.external_community_rules_repo,
                )
            else:
                self._do_notify_no_git()
        if action == "open_community_rules_with_rule_editor":
            self._do_open_rule_editor(compact=False, initial_mode="community_rules")
        if action == "upload_community_rules_database":
            if GIT_EXISTS:
                self._do_upload_db_to_repo(
                    repo_url=self.settings_controller.settings.external_community_rules_repo,
                    file_name="communityRules.json",
                )
            else:
                self._do_notify_no_git()
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
        logger.debug("Skipping update check...")
        return
        # NOT NUITKA
        if "__compiled__" not in globals():
            logger.debug(
                "You are running from Python interpreter. Skipping update check..."
            )
            dialogue.show_warning(
                title="Update skipped",
                text="You are running from Python interpreter.",
                information="Skipping update check...",
            )
            return
        # NUITKA
        logger.debug("Checking for RimSort update...")
        current_version = self.metadata_manager.game_version
        try:
            json_response = self.__do_get_github_release_info()
        except Exception as e:
            logger.warning(
                f"Unable to retrieve latest release information due to exception: {e.__class__}"
            )
            return
        tag_name = json_response["tag_name"]
        tag_name_updated = tag_name.replace("alpha", "Alpha")
        install_path = os.getcwd()
        logger.debug(f"Current RimSort release found: {tag_name}")
        logger.debug(f"Current RimSort version found: {current_version}")
        if current_version != tag_name:
            answer = dialogue.show_dialogue_conditional(
                title="RimSort update found",
                text=f"An update to RimSort has been released: {tag_name}",
                information=f"You are running RimSort {current_version}\nDo you want to update now?",
            )
            if answer == "&Yes":
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
                        title="Unable to complete update",
                        text=f"Failed to find valid RimSort release for {SYSTEM} {ARCH} {PROCESSOR}",
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
                        text=f"RimSort update found. Downloading RimSort {tag_name_updated} release...",
                    )
                    temp_dir = "RimSort" if not SYSTEM == "Darwin" else "RimSort.app"
                    answer = dialogue.show_dialogue_conditional(
                        title="Update downloaded",
                        text="Do you want to proceed with the update?",
                        information=f"\nSuccessfully retrieved latest release. The update will be installed from: {os.path.join(gettempdir(), temp_dir)}",
                    )
                    if not answer == "&Yes":
                        return
                except Exception:
                    stacktrace = traceback.format_exc()
                    dialogue.show_warning(
                        title="Failed to download update",
                        text="Failed to download latest RimSort release!",
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
                title="RimSort is up to date!",
                text=f"You are already running the latest release: {tag_name}",
            )

    def _do_validate_steam_client(self) -> None:
        platform_specific_open("steam://validate/294100")

    def __do_download_extract_release_to_tempdir(self, url: str) -> None:
        with ZipFile(BytesIO(requests_get(url).content)) as zipobj:
            zipobj.extractall(gettempdir())

    def __do_get_github_release_info(self) -> dict[str, Any]:
        # Parse latest release
        raw = requests_get(
            "https://api.github.com/repos/RimSort/RimSort/releases/latest"
        )
        return raw.json()

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
        if text:
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
            self.mods_panel.active_mods_filter_data_source_index = len(
                self.mods_panel.data_source_filter_icons
            )
            self.mods_panel.signal_clear_search(list_type="Active")
            self.mods_panel.inactive_mods_filter_data_source_index = len(
                self.mods_panel.data_source_filter_icons
            )
            self.mods_panel.signal_clear_search(list_type="Inactive")
            self.mods_panel.active_mods_filter_data_source_index = len(
                self.mods_panel.data_source_filter_icons
            )
            self.mods_panel.signal_clear_search(list_type="Active")
            self.mods_panel.inactive_mods_filter_data_source_index = len(
                self.mods_panel.data_source_filter_icons
            )
            self.mods_panel.signal_clear_search(list_type="Inactive")
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
                text="Scanning mod sources and populating metadata...",
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

    def _do_sort(self) -> None:
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
        active_package_ids = set()
        for uuid in self.mods_panel.active_mods_list.uuids:
            active_package_ids.add(
                self.metadata_manager.internal_local_metadata[uuid]["packageid"]
            )

        # Get the current order of active mods list
        current_order = self.mods_panel.active_mods_list.uuids.copy()

        sorter = Sorter(
            self.settings_controller.settings.sorting_algorithm,
            active_package_ids=active_package_ids,
            active_uuids=set(self.mods_panel.active_mods_list.uuids),
        )

        success, new_order = sorter.sort()

        # Check if the order has changed
        if success and new_order == current_order:
            logger.info(
                "The order of mods in List has not changed. Skipping insertion."
            )
        elif success:
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
            _dir=str(AppInfo().app_storage_folder),
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
            _dir=str(AppInfo().app_storage_folder),
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
                    title="Failed to export to file",
                    text="Failed to export active mods to file:",
                    information=f"{file_path}",
                    details=traceback.format_exc(),
                )
        else:
            logger.debug("USER ACTION: pressed cancel, passing")

    def _do_import_list_rentry(self) -> None:
        # Create an instance of RentryImport
        rentry_import = RentryImport()
        # Open the RentryImport dialogue
        rentry_import.import_rentry_link()
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
        collection_import = CollectionImport(metadata_manager=self.metadata_manager)

        # Trigger the import dialogue and get the result
        collection_import.import_collection_link()

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
            title="Export active mod list",
            text="Copied active mod list report to clipboard...",
            information='Click "Show Details" to see the full report!',
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
                    url is None
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
        host = urlparse(rentry_uploader.url).hostname if successful else None
        if rentry_uploader.url and host and host.endswith("rentry.co"):  # type: ignore
            copy_to_clipboard_safely(rentry_uploader.url)
            dialogue.show_information(
                title="Uploaded active mod list",
                text=f"Uploaded active mod list report to Rentry.co! The URL has been copied to your clipboard:\n\n{rentry_uploader.url}",
                information='Click "Show Details" to see the full report!',
                details=f"{active_mods_rentry_report}",
            )
        else:
            dialogue.show_warning(
                title="Failed to upload",
                text="Failed to upload exported active mod list to Rentry.co",
            )

    def _do_open_app_directory(self) -> None:
        app_directory = os.getcwd()
        logger.info(f"Opening app directory: {app_directory}")
        platform_specific_open(os.getcwd())

    def _do_open_settings_directory(self) -> None:
        settings_directory = AppInfo().app_storage_folder
        logger.info(f"Opening settings directory: {settings_directory}")
        platform_specific_open(settings_directory)

    def _do_open_rimsort_logs_directory(self) -> None:
        logs_directory = AppInfo().user_log_folder
        logger.info(f"Opening RimSort logs directory: {logs_directory}")
        platform_specific_open(logs_directory)

    def _do_open_rimworld_logs_directory(self) -> None:
        user_home = Path.home()
        logs_directory = None
        if SystemInfo().operating_system == SystemInfo.OperatingSystem.MACOS:
            logs_directory = (
                f"/{user_home}/Library/Logs/Ludeon Studios/RimWorld by Ludeon Studios"
            )
            platform_specific_open(Path(logs_directory))
        elif SystemInfo().operating_system == SystemInfo.OperatingSystem.LINUX:
            logs_directory = (
                f"{user_home}/.config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios"
            )
            platform_specific_open(Path(logs_directory))
        elif SystemInfo().operating_system == SystemInfo.OperatingSystem.WINDOWS:
            logs_directory = f"{user_home}/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios"
            platform_specific_open(Path(logs_directory).resolve())

        if logs_directory:
            logger.info(f"Opening RimWorld logs directory: {logs_directory}")
        else:
            logger.error("Could not open RimWorld logs directory on an unknown system")

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
                title="File not found",
                text="The file you are trying to upload does not exist.",
                information=f"File: {path}",
            )
            return

        success, ret = self.do_threaded_loading_animation(
            gif_path=str(AppInfo().theme_data_folder / "default-icons" / "rimsort.gif"),
            target=partial(upload_data_to_0x0_st, str(path)),
            text=f"Uploading {path.name} to 0x0.st...",
        )

        if success:
            copy_to_clipboard_safely(ret)
            dialogue.show_information(
                title="Uploaded file",
                text=f"Uploaded {path.name} to http://0x0.st/",
                information=f"The URL has been copied to your clipboard:\n\n{ret}",
            )
            webbrowser.open(ret)
        else:
            dialogue.show_warning(
                title="Failed to upload file.",
                text="Failed to upload the file to 0x0.st",
                information=ret,
            )

    def _do_save(self) -> None:
        """
        Method save the current list of active mods to the selected ModsConfig.xml
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
                title="Could not save active mods",
                text="Failed to save active mods to file:",
                information=f"{mods_config_path}",
                details=traceback.format_exc(),
            )
        EventBus().do_save_button_animation_stop.emit()
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
            "https://steamcommunity.com/app/294100/workshop/"
        )
        self.steam_browser.steamcmd_downloader_signal.connect(
            self._do_download_mods_with_steamcmd
        )
        self.steam_browser.steamworks_subscription_signal.connect(
            self._do_steamworks_api_call_animated
        )
        self.steam_browser.show()

    def _do_check_for_workshop_updates(self) -> None:
        # Query Workshop for update data
        updates_checked = self.do_threaded_loading_animation(
            gif_path=str(
                AppInfo().theme_data_folder / "default-icons" / "steam_api.gif"
            ),
            target=partial(
                metadata.query_workshop_update_data,
                mods=self.metadata_manager.internal_local_metadata,
            ),
            text="Checking Steam Workshop mods for updates...",
        )
        # If we failed to check for updates, skip the comparison(s) & UI prompt
        if updates_checked == "failed":
            dialogue.show_warning(
                title="Unable to check for updates",
                text="RimSort was unable to query Steam WebAPI for update information!\n",
                information="Are you connected to the Internet?",
            )
            return
        workshop_mod_updater = ModUpdaterPrompt(
            internal_mod_metadata=self.metadata_manager.internal_local_metadata
        )
        workshop_mod_updater._populate_from_metadata()
        if workshop_mod_updater.updates_found:
            logger.debug("Displaying potential Workshop mod updates")
            workshop_mod_updater.steamcmd_downloader_signal.connect(
                self._do_download_mods_with_steamcmd
            )
            workshop_mod_updater.steamworks_subscription_signal.connect(
                self._do_steamworks_api_call_animated
            )
            workshop_mod_updater.show()
        else:
            self.status_signal.emit("All Workshop mods appear to be up to date!")

    def _do_setup_steamcmd(self) -> None:
        if (
            self.steamcmd_runner
            and self.steamcmd_runner.process
            and self.steamcmd_runner.process.state() == QProcess.ProcessState.Running
        ):
            dialogue.show_warning(
                title="RimSort - SteamCMD setup",
                text="Unable to create SteamCMD runner!",
                information="There is an active process already running!",
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
        else:
            dialogue.show_warning(
                title="RimSort - SteamCMD setup",
                text="Unable to initiate SteamCMD installation. Local mods path not set!",
                information="Please configure local mods path in Settings before attempting to install.",
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
        if not len(publishedfileids) > 0:
            dialogue.show_warning(
                title="RimSort",
                text="No PublishedFileIds were supplied in operation.",
                information="Please add mods to list before attempting to download.",
            )
            return
        # Check for existing steamcmd_runner process
        if (
            self.steamcmd_runner
            and self.steamcmd_runner.process
            and self.steamcmd_runner.process.state() == QProcess.ProcessState.Running
        ):
            dialogue.show_warning(
                title="RimSort",
                text="Unable to create SteamCMD runner!",
                information="There is an active process already running!",
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
                publishedfileids=publishedfileids, runner=self.steamcmd_runner
            )
        else:
            dialogue.show_warning(
                title="SteamCMD not found",
                text="SteamCMD executable was not found.",
                information='Please setup an existing SteamCMD prefix, or setup a new prefix with "Setup SteamCMD".',
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
                    instruction[0] in subscription_actions
                    and not len(instruction[1]) < 1
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
        if not len(publishedfileids) > 0:
            dialogue.show_warning(
                title="RimSort",
                text="No PublishedFileIds were supplied in operation.",
                information="Please add mods to list before attempting to download.",
            )
            return
        # Close browser if open
        if self.steam_browser:
            self.steam_browser.close()
        # Process API call
        self.do_threaded_loading_animation(
            gif_path=str(AppInfo().theme_data_folder / "default-icons" / "steam.gif"),
            target=partial(self._do_steamworks_api_call, instruction=instruction),
            text="Processing Steam subscription action(s) via Steamworks API...",
        )
        # self._do_refresh()

    # GIT MOD ACTIONS

    def _do_add_git_mod(self) -> None:
        """
        Opens a QDialogInput that allows the user to edit the run args
        that are configured to be passed to the Rimworld executable
        """
        args, ok = dialogue.show_dialogue_input(
            title="Enter git repo",
            label="Enter a git repository url (http/https) to clone to local mods:",
        )
        if ok:
            self._do_clone_repo_to_path(
                base_path=self.settings_controller.settings.instances[
                    self.settings_controller.settings.current_instance
                ].local_folder,
                repo_url=args,
            )
        else:
            logger.debug("Cancelling operation.")

    # EXTERNAL METADATA ACTIONS

    def _do_configure_github_identity(self) -> None:
        """
        Opens a QDialogInput that allows user to edit their Github token
        This token is used for DB repo related actions, as well as any
        "Github mod" related actions
        """
        args, ok = dialogue.show_dialogue_input(
            title="Edit username",
            label="Enter your Github username:",
            text=self.settings_controller.settings.github_username,
        )
        if ok:
            self.settings_controller.settings.github_username = args
            self.settings_controller.settings.save()
        else:
            logger.debug("USER ACTION: cancelled input!")
            return
        args, ok = dialogue.show_dialogue_input(
            title="Edit token",
            label="Enter your Github personal access token here (ghp_*):",
            text=self.settings_controller.settings.github_token,
        )
        if ok:
            self.settings_controller.settings.github_token = args
            self.settings_controller.settings.save()
        else:
            logger.debug("USER ACTION: cancelled input!")
            return

    def _do_cleanup_gitpython(self, repo: "Repo") -> None:
        # Cleanup GitPython
        collect()
        repo.git.clear_cache()
        del repo

    def _check_git_repos_for_update(self, repo_paths: list[str]) -> None:
        if GIT_EXISTS:
            # Track summary of repo updates
            updates_summary = {}
            for repo_path in repo_paths:
                logger.info(f"Checking git repository for updates at: {repo_path}")
                if os.path.exists(repo_path):
                    repo = Repo(repo_path)
                    try:
                        # Fetch the latest changes from the remote
                        origin = repo.remote(name="origin")
                        origin.fetch()

                        # Get the local and remote refs
                        local_ref = repo.head.reference
                        refs = repo.refs()
                        remote_ref = refs[f"origin/{local_ref.name}"]

                        # Check if the local branch is behind the remote branch
                        if local_ref.commit != remote_ref.commit:
                            local_name = local_ref.name
                            remote_name = remote_ref.name
                            logger.info(
                                f"Local branch {local_name} is not up-to-date with remote branch {remote_name}. Updating forcefully."
                            )
                            # Create a summary of the changes that will be made for the repo to be updated
                            updates_summary[repo_path] = {
                                "HEAD~1": local_ref.commit.hexsha[:7],
                            }
                            # Force pull the latest changes
                            repo.git.reset("--hard", remote_ref.name)
                            repo.git.clean("-fdx")  # Remove untracked files
                            origin.pull(local_ref.name, rebase=True)
                            updates_summary[repo_path].update(
                                {
                                    "HEAD": remote_ref.commit.hexsha[:7],
                                    "message": remote_ref.commit.message,
                                }
                            )
                        else:
                            logger.info("The local repository is already up-to-date.")
                    except GitCommandError:
                        stacktrace = traceback.format_exc()
                        dialogue.show_warning(
                            title="Failed to update repo!",
                            text=f"The repository supplied at [{repo_path}] failed to update!\n"
                            + "Are you connected to the Internet? "
                            + "Is the repo valid?",
                            information=(
                                f"Supplied repository: {repo.remotes.origin.url}"
                                if repo
                                and repo.remotes
                                and repo.remotes.origin
                                and repo.remotes.origin.url
                                else None
                            ),
                            details=stacktrace,
                        )
                    finally:
                        self._do_cleanup_gitpython(repo)
            # If any updates were found, notify the user
            if updates_summary:
                repos_updated = "\n".join(
                    list(os.path.split(k)[1] for k in updates_summary.keys())
                )
                updates_summarized = "\n".join(
                    [
                        f"[{os.path.split(k)[1]}]: {v['HEAD~1']  + '...' + v['HEAD']}\n"
                        + f"{v['message']}\n"
                        for k, v in updates_summary.items()
                    ]
                )
                dialogue.show_information(
                    title="Git repo(s) updated",
                    text="The following repo(s) had updates pulled from the remote:",
                    information=repos_updated,
                    details=updates_summarized,
                )
            else:
                dialogue.show_information(
                    title="Git repo(s) not updated",
                    text="No updates were found.",
                )
        else:
            self._do_notify_no_git()

    def _do_clone_repo_to_path(self, base_path: str, repo_url: str) -> None:
        """
        Checks validity of configured git repo, as well as if it exists
        Handles possible existing repo, and prompts (re)download of repo
        Otherwise it just clones the repo and notifies user
        """
        # Check if git is installed
        if not GIT_EXISTS:
            self._do_notify_no_git()
            return

        if (
            repo_url
            and repo_url != ""
            and repo_url.startswith("http://")
            or repo_url.startswith("https://")
        ):
            # Calculate folder name from provided URL
            repo_folder_name = os.path.split(repo_url)[1]
            # Calculate path from generated folder name
            repo_path = str((Path(base_path) / repo_folder_name))
            if os.path.exists(repo_path):  # If local repo does exist
                # Prompt to user to handle
                answer = dialogue.show_dialogue_conditional(
                    title="Existing repository found",
                    text="An existing local repo that matches this repository was found:",
                    information=(
                        f"{repo_path}\n\n"
                        + "How would you like to handle? Choose option:\n"
                        + "\n1) Clone new repository (deletes existing and replaces)"
                        + "\n2) Update existing repository (in-place force-update)"
                    ),
                    button_text_override=[
                        "Clone new",
                        "Update existing",
                    ],
                )
                if answer == "Cancel":
                    logger.debug(
                        f"User cancelled prompt. Skipping any {repo_folder_name} repository actions."
                    )
                    return
                elif answer == "Clone new":
                    logger.info(f"Deleting local git repo at: {repo_path}")
                    delete_files_except_extension(directory=repo_path, extension=".dds")
                elif answer == "Update existing":
                    self._do_force_update_existing_repo(
                        base_path=base_path, repo_url=repo_url
                    )
                    return
            # Clone the repo to storage path and notify user
            logger.info(f"Cloning {repo_url} to: {repo_path}")
            try:
                Repo.clone_from(repo_url, repo_path)
                dialogue.show_information(
                    title="Repo retrieved",
                    text="The configured repository was cloned!",
                    information=f"{repo_url} ->\n" + f"{repo_path}",
                )
            except GitCommandError:
                try:
                    # Initialize a new Git repository
                    repo = Repo.init(repo_path)
                    # Add the origin remote
                    origin_remote = repo.create_remote("origin", repo_url)
                    # Fetch the remote branches
                    origin_remote.fetch()
                    # Determine the target branch name
                    target_branch = None
                    for ref in repo.remotes.origin.refs:
                        if ref.remote_head in ("main", "master"):
                            target_branch = ref.remote_head
                            break

                    if target_branch:
                        # Checkout the target branch
                        repo.git.checkout(
                            f"origin/{target_branch}", b=target_branch, force=True
                        )
                    else:
                        # Handle the case when the target branch is not found
                        logger.warning("Target branch not found.")
                    dialogue.show_information(
                        title="Repo retrieved",
                        text="The configured repository was reinitialized with existing files! (likely leftover .dds textures)",
                        information=f"{repo_url} ->\n" + f"{repo_path}",
                    )
                except GitCommandError:
                    stacktrace = traceback.format_exc()
                    dialogue.show_warning(
                        title="Failed to clone repo!",
                        text="The configured repo failed to clone/initialize! "
                        + "Are you connected to the Internet? "
                        + "Is your configured repo valid?",
                        information=f"Configured repository: {repo_url}",
                        details=stacktrace,
                    )
        else:
            # Warn the user so they know to configure in settings
            dialogue.show_warning(
                title="Invalid repository",
                text="An invalid repository was detected!",
                information="Please reconfigure a repository in settings!\n"
                + "A valid repository is a repository URL which is not\n"
                + 'empty and is prefixed with "http://" or "https://"',
            )

    def _do_force_update_existing_repo(self, base_path: str, repo_url: str) -> None:
        """
        Checks validity of configured git repo, as well as if it exists
        Handles possible existing repo, and prompts (re)download of repo
        Otherwise it just clones the repo and notifies user
        """
        if (
            repo_url
            and repo_url != ""
            and repo_url.startswith("http://")
            or repo_url.startswith("https://")
        ):
            # Calculate folder name from provided URL
            repo_folder_name = os.path.split(repo_url)[1]
            # Calculate path from generated folder name
            repo_path = str((Path(base_path) / repo_folder_name))
            if os.path.exists(repo_path):  # If local repo does exists
                # Clone the repo to storage path and notify user
                logger.info(f"Force updating git repository at: {repo_path}")
                try:
                    # Open repo
                    repo = Repo(repo_path)
                    # Determine the target branch name
                    target_branch = None
                    for ref in repo.remotes.origin.refs:
                        if ref.remote_head in ("main", "master"):
                            target_branch = ref.remote_head
                            break
                    if target_branch:
                        # Checkout the target branch
                        repo.git.checkout(target_branch)
                    else:
                        # Handle the case when the target branch is not found
                        logger.warning("Target branch not found.")
                    # Reset the repository to HEAD in case of changes not committed
                    repo.head.reset(index=True, working_tree=True)
                    # Perform a pull with rebase
                    origin = repo.remotes.origin
                    origin.pull(rebase=True)
                    # Notify user
                    dialogue.show_information(
                        title="Repo force updated",
                        text="The configured repository was updated!",
                        information=f"{repo_path} ->\n "
                        + f"{repo.head.commit.message.decode() if isinstance(repo.head.commit.message, bytes) else repo.head.commit.message}",
                    )
                    # Cleanup
                    self._do_cleanup_gitpython(repo=repo)
                except GitCommandError:
                    stacktrace = traceback.format_exc()
                    dialogue.show_warning(
                        title="Failed to update repo!",
                        text="The configured repo failed to update! "
                        + "Are you connected to the Internet? "
                        + "Is your configured repo valid?",
                        information=f"Configured repository: {repo_url}",
                        details=stacktrace,
                    )
            else:
                answer = dialogue.show_dialogue_conditional(
                    title="Repository does not exist",
                    text="Tried to update a git repository that does not exist!",
                    information="Would you like to clone a new copy of this repository?",
                )
                if answer == "&Yes":
                    if GIT_EXISTS:
                        self._do_clone_repo_to_path(
                            base_path=base_path,
                            repo_url=repo_url,
                        )
                    else:
                        self._do_notify_no_git()
        else:
            # Warn the user so they know to configure in settings
            dialogue.show_warning(
                title="Invalid repository",
                text="An invalid repository was detected!",
                information="Please reconfigure a repository in settings!\n"
                + "A valid repository is a repository URL which is not\n"
                + 'empty and is prefixed with "http://" or "https://"',
            )

    def _do_upload_db_to_repo(self, repo_url: str, file_name: str) -> None:
        """
        Checks validity of configured git repo, as well as if it exists
        Commits file & submits PR based on version tag found in DB
        """
        if (
            repo_url
            and repo_url != ""
            and (repo_url.startswith("http://") or repo_url.startswith("https://"))
        ):
            # Calculate folder name from provided URL
            repo_user_or_org = os.path.split(os.path.split(repo_url)[0])[1]
            repo_folder_name = os.path.split(repo_url)[1]
            # Calculate path from generated folder name
            repo_path = str((AppInfo().databases_folder / repo_folder_name))
            if os.path.exists(repo_path):  # If local repo exists
                # Update the file, commit + PR to repo
                logger.info(
                    f"Attempting to commit changes to {file_name} in git repository: {repo_path}"
                )
                try:
                    # Specify the file path relative to the local repository
                    file_full_path = str((Path(repo_path) / file_name))
                    if os.path.exists(file_full_path):
                        # Load JSON data
                        with open(file_full_path, encoding="utf-8") as f:
                            json_string = f.read()
                            logger.debug("Reading info...")
                            database = json.loads(json_string)
                            logger.debug("Retrieved database...")
                        if database.get("version"):
                            database_version = (
                                database["version"]
                                - self.settings_controller.settings.database_expiry
                            )
                        elif database.get("timestamp"):
                            database_version = database["timestamp"]
                        else:
                            logger.error(
                                "Unable to parse version or timestamp from database. Cancelling upload."
                            )
                        # Get the abbreviated timezone
                        timezone_abbreviation = (
                            datetime.datetime.now(datetime.timezone.utc)
                            .astimezone()
                            .tzinfo
                        )
                        database_version_human_readable = (
                            time.strftime(
                                "%Y-%m-%d %H:%M:%S", time.localtime(database_version)
                            )
                            + f" {timezone_abbreviation}"
                        )
                    else:
                        dialogue.show_warning(
                            title="File does not exist",
                            text="Please ensure the file exists and then try to upload again!",
                            information=f"File not found:\n{file_full_path}\nRepository:\n{repo_url}",
                        )
                        return

                    # Create a GitHub instance
                    g = Github(
                        self.settings_controller.settings.github_username,
                        self.settings_controller.settings.github_token,
                    )

                    # Specify the repository
                    repo = g.get_repo(f"{repo_user_or_org}/{repo_folder_name}")

                    # Specify the branch names
                    base_branch = "main"
                    new_branch_name = f"{database_version}"

                    # Specify commit message
                    commit_message = f"DB Update: {database_version_human_readable}"

                    # Specify the Pull Request fields
                    pull_request_title = f"DB update {database_version}"
                    pull_request_body = f"Steam Workshop {commit_message}"

                    # Open repo
                    local_repo = Repo(repo_path)

                    # Create our new branch and checkout
                    new_branch = local_repo.create_head(new_branch_name)
                    local_repo.head.set_reference(ref=new_branch)

                    # Add the file to the index on our new branch
                    local_repo.index.add([file_full_path])

                    # Commit changes to the new branch
                    local_repo.index.commit(commit_message)
                    try:
                        # Push the changes to the remote repository and create a pull request from new_branch
                        origin = local_repo.remote()
                        origin.push(new_branch)
                    except Exception:
                        stacktrace = traceback.format_exc()
                        dialogue.show_warning(
                            title="Failed to push new branch to repo!",
                            text=f"Failed to push a new branch {new_branch_name} to {repo_folder_name}! Try to see "
                            + "if you can manually push + Pull Request. Otherwise, checkout main and try again!",
                            information=f"Configured repository: {repo_url}",
                            details=stacktrace,
                        )
                    try:
                        # Create the pull request
                        pull_request = repo.create_pull(
                            title=pull_request_title,
                            body=pull_request_body,
                            base=base_branch,
                            head=f"{repo_user_or_org}:{new_branch_name}",
                        )
                        pull_request_url = pull_request.html_url
                    except Exception:
                        stacktrace = traceback.format_exc()
                        dialogue.show_warning(
                            title="Failed to create pull request!",
                            text=f"Failed to create a pull request for branch {base_branch} <- {new_branch_name}!\n"
                            + "The branch should be pushed. Check on Github to see if you can manually"
                            + " make a Pull Request there! Otherwise, checkout main and try again!",
                            information=f"Configured repository: {repo_url}",
                            details=stacktrace,
                        )
                    # Cleanup
                    self._do_cleanup_gitpython(repo=local_repo)
                    # Notify the pull request URL
                    answer = dialogue.show_dialogue_conditional(
                        title="Pull request created",
                        text="Successfully created pull request!",
                        information="Do you want to try to open it in your web browser?\n\n"
                        + f"URL: {pull_request_url}",
                    )
                    if answer == "&Yes":
                        # Open the url in user's web browser
                        open_url_browser(url=pull_request_url)
                except Exception:
                    stacktrace = traceback.format_exc()
                    dialogue.show_warning(
                        title="Failed to update repo!",
                        text=f"The configured repo failed to update!\nFile name: {file_name}",
                        information=f"Configured repository: {repo_url}",
                        details=stacktrace,
                    )
            else:
                answer = dialogue.show_dialogue_conditional(
                    title="Repository does not exist",
                    text="Tried to update a git repository that does not exist!",
                    information="Would you like to clone a new copy of this repository?",
                )
                if answer == "&Yes":
                    if GIT_EXISTS:
                        self._do_clone_repo_to_path(
                            base_path=str(AppInfo().databases_folder),
                            repo_url=repo_url,
                        )
                    else:
                        self._do_notify_no_git()
        else:
            # Warn the user so they know to configure in settings
            dialogue.show_warning(
                title="Invalid repository",
                text="An invalid repository was detected!",
                information="Please reconfigure a repository in settings!\n"
                + 'A valid repository is a repository URL which is not empty and is prefixed with "http://" or "https://"',
            )

    def _do_notify_no_git(self) -> None:
        answer = dialogue.show_dialogue_conditional(  # We import last so we can use gui + utils
            title="git not found",
            text="git executable was not found in $PATH!",
            information=(
                "Git integration will not work without Git installed! Do you want to open download page for Git?\n\n"
                "If you just installed Git, please restart RimSort for the PATH changes to take effect."
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
            title="Edit Steam DB repo",
            label="Enter URL (https://github.com/AccountName/RepositoryName):",
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
            title="Edit Community Rules DB repo",
            label="Enter URL (https://github.com/AccountName/RepositoryName):",
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
        if not len(self.db_builder.publishedfileids) > 0:
            dialogue.show_warning(
                title="No PublishedFileIDs",
                text="DB Builder query did not return any PublishedFileIDs!",
                information="This is typically caused by invalid/missing Steam WebAPI key, or a connectivity issue to the Steam WebAPI.\n"
                + "PublishedFileIDs are needed to retrieve mods from Steam!",
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
                    title="Are you sure?",
                    text="Here be dragons.",
                    information="WARNING: It is NOT recommended to subscribe to this many mods at once via Steam. "
                    + "Steam has limitations in place seemingly intentionally and unintentionally for API subscriptions. "
                    + "It is highly recommended that you instead download these mods to a SteamCMD prefix by using SteamCMD. "
                    + "This can take longer due to rate limits, but you can also re-use the script generated by RimSort with "
                    + "a separate, authenticated instance of SteamCMD, if you do not want to anonymously download via RimSort.",
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
            title="Edit Steam WebAPI key",
            label="Enter your personal 32 character Steam WebAPI key here:",
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
            title="Steam DB Builder",
            text="This operation will compare 2 databases, A & B, by checking dependencies from A with dependencies from B.",
            information="- This will produce an accurate comparison of dependency data between 2 Steam DBs.\n"
            + "A report of discrepancies is generated. You will be prompted for these paths in order:\n"
            + "\n\t1) Select input A"
            + "\n\t2) Select input B",
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
            title="Steam DB Builder",
            text=f"Steam DB comparison report: {len(discrepancies)} found",
            information="Click 'Show Details' to see the full report!",
            details=report,
        )

    def _do_merge_databases(self) -> None:
        # Notify user
        dialogue.show_information(
            title="Steam DB Builder",
            text="This operation will merge 2 databases, A & B, by recursively updating A with B, barring exceptions.",
            information="- This will effectively recursively overwrite A's key/value with B's key/value to the resultant database.\n"
            + "- Exceptions will not be recursively updated. Instead, they will be overwritten with B's key entirely.\n"
            + "- The following exceptions will be made:\n"
            + f"\n\t{app_constants.DB_BUILDER_RECURSE_EXCEPTIONS}\n\n"
            + "The resultant database, C, is saved to a user-specified path. You will be prompted for these paths in order:\n"
            + "\n\t1) Select input A (db to-be-updated)"
            + "\n\t2) Select input B (update source)"
            + "\n\t3) Select output C (resultant db)",
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
            title="RimSort - DB Builder",
            text="Do you want to continue?",
            information=f"This operation will overwrite the {rules_source} database located at the following path:\n\n{path}",
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
            title="Edit SteamDB expiry:",
            label="Enter your preferred expiry duration in seconds (default 1 week/604800 sec):",
            text=str(self.settings_controller.settings.database_expiry),
        )
        if ok:
            try:
                self.settings_controller.settings.database_expiry = int(args)
                self.settings_controller.settings.save()
            except ValueError:
                dialogue.show_warning(
                    "Tried configuring Dynamic Query with a value that is not an integer.",
                    "Please reconfigure the expiry value with an integer in terms of the seconds from epoch you would like your query to expire.",
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
    def _on_do_upload_community_db_to_github(self) -> None:
        self._do_upload_db_to_repo(
            repo_url=self.settings_controller.settings.external_community_rules_repo,
            file_name="communityRules.json",
        )

    @Slot()
    def _on_do_download_community_db_from_github(self) -> None:
        if GIT_EXISTS:
            self._do_clone_repo_to_path(
                base_path=str(AppInfo().databases_folder),
                repo_url=self.settings_controller.settings.external_community_rules_repo,
            )
        else:
            self._do_notify_no_git()

    @Slot()
    def _on_do_upload_steam_workshop_db_to_github(self) -> None:
        self._do_upload_db_to_repo(
            repo_url=self.settings_controller.settings.external_steam_metadata_repo,
            file_name="steamDB.json",
        )

    @Slot()
    def _on_do_download_steam_workshop_db_from_github(self) -> None:
        self._do_clone_repo_to_path(
            base_path=str(AppInfo().databases_folder),
            repo_url=self.settings_controller.settings.external_steam_metadata_repo,
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
        steam_appid_file_exists = os.path.exists(game_install_path / "steam_appid.txt")
        if steam_client_integration and not steam_appid_file_exists:
            with open(
                game_install_path / "steam_appid.txt", "w", encoding="utf-8"
            ) as f:
                f.write("294100")
        elif not steam_client_integration and steam_appid_file_exists:
            os.remove(game_install_path / "steam_appid.txt")

        # Launch independent game process without Steamworks API
        launch_game_process(game_install_path=game_install_path, args=run_args)
