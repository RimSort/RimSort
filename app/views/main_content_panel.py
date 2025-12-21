import json
import os
import sys
import tempfile
import time
import traceback
import webbrowser
from functools import partial
from pathlib import Path
from tempfile import gettempdir
from typing import Any, Callable, Optional, cast
from urllib.parse import urlparse

import requests
from loguru import logger
from PySide6.QtCore import (
    QEventLoop,
    QObject,
    QProcess,
    QRunnable,
    Qt,
    QThreadPool,
    Signal,
    Slot,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QSplitter,
    QWidget,
)

import app.utils.constants as app_constants
import app.utils.metadata as metadata
import app.views.dialogue as dialogue
from app.controllers.sort_controller import Sorter
from app.models.animations import LoadingAnimation
from app.sort.mod_sorting import ModsPanelSortKey
from app.utils.app_info import AppInfo
from app.utils.custom_list_widget_item import CustomListWidgetItem
from app.utils.event_bus import EventBus
from app.utils.files import create_backup_in_thread
from app.utils.generic import (
    check_internet_connection,
    copy_to_clipboard_safely,
    launch_game_process,
    launch_process,
    open_url_browser,
    platform_specific_open,
    upload_data_to_0x0_st,
)
from app.utils.ignore_manager import IgnoreManager
from app.utils.metadata import MetadataManager, SettingsController
from app.utils.rentry.wrapper import RentryImport, RentryUpload
from app.utils.schema import generate_rimworld_mods_list
from app.utils.steam.steambrowser.browser import SteamBrowser
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.utils.steam.steamworks.wrapper import steamworks_game_launch_worker
from app.utils.steam.webapi.wrapper import (
    CollectionImport,
    ISteamRemoteStorage_GetPublishedFileDetails,
)
from app.utils.system_info import SystemInfo
from app.utils.todds.wrapper import ToddsInterface
from app.utils.update_utils import UpdateManager
from app.utils.xml import json_to_xml_write
from app.utils.zip_extractor import (
    BadZipFile,
    ZipExtractThread,
    get_zip_contents,
)
from app.views.mod_info_panel import ModInfoPanel
from app.views.mods_panel import (
    ModListWidget,
    ModsPanel,
)
from app.views.task_progress_window import TaskProgressWindow
from app.windows.duplicate_mods_panel import DuplicateModsPanel
from app.windows.ignore_json_editor import IgnoreJsonEditor
from app.windows.missing_dependencies_dialog import MissingDependenciesDialog
from app.windows.missing_mod_properties_panel import MissingModPropertiesPanel
from app.windows.missing_mods_panel import MissingModsPrompt
from app.windows.rule_editor_panel import RuleEditor
from app.windows.runner_panel import RunnerPanel
from app.windows.use_this_instead_panel import UseThisInsteadPanel
from app.windows.workshop_mod_updater_panel import WorkshopModUpdaterPanel


class SteamSubscriptionRunnable(QRunnable):
    """
    Runnable for executing Steam Workshop subscription operations in Qt thread pool.

    This ensures subscription requests are made from the main process context,
    allowing Steam client to properly receive and act on them.
    """

    def __init__(self, action: str, pfids: list[int]) -> None:
        """
        Initialize the runnable.

        :param action: "subscribe", "unsubscribe", or "resubscribe"
        :param pfids: List of PublishedFileIds to process
        """
        super().__init__()
        self.action = action
        self.pfids = pfids

    @Slot()
    def run(self) -> None:
        """Execute the subscription action in a thread."""
        from app.utils.steam.steamworks.wrapper import SteamworksInterface

        logger.info(
            f"[STEAM_THREAD] Executing {self.action} for {len(self.pfids)} mods"
        )

        steamworks_interface = SteamworksInterface.instance(
            _libs=str((AppInfo().application_folder / "libs"))
        )

        if self.action == "subscribe":
            steamworks_interface.subscribe_to_mods(self.pfids, interval=1)
        elif self.action == "unsubscribe":
            steamworks_interface.unsubscribe_from_mods(self.pfids, interval=1)
        elif self.action == "resubscribe":
            steamworks_interface.resubscribe_to_mods(self.pfids, interval=1)
        else:
            logger.error(f"Unknown subscription action: {self.action}")

        logger.info(
            f"[STEAM_THREAD] Completed {self.action} for {len(self.pfids)} mods"
        )


class MainContent(QObject):
    """
    This class controls the layout and functionality of the main content
    panel of the GUI, containing the mod information display, inactive and
    active mod lists, and the action button panel. Additionally, it acts
    as the main temporary datastore of the app, caching workshop mod information
    and their dependencies.
    """

    _instance: Optional["MainContent"] = None

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
            EventBus().do_import_mod_list_from_save_file.connect(
                self._do_import_list_from_save_file
            )
            EventBus().do_save_mod_list_as.connect(self._do_export_list_file_xml)
            EventBus().do_export_mod_list_to_clipboard.connect(
                self._do_export_list_clipboard
            )
            EventBus().do_export_mod_list_to_rentry.connect(self._do_upload_list_rentry)
            EventBus().do_upload_log.connect(self._upload_file)
            EventBus().do_open_default_editor.connect(self._open_in_default_editor)
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
            EventBus().do_import_acf.connect(self._do_import_steamcmd_acf_data)
            EventBus().do_delete_acf.connect(self._do_reset_steamcmd_acf_data)
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
                lambda: self._do_open_rule_editor(
                    compact=False, initial_mode="community_rules"
                )
            )
            EventBus().do_ignore_json_editor.connect(self._do_open_ignore_json_editor)
            EventBus().do_check_missing_mod_properties.connect(
                self.__check_and_warn_missing_mod_properties
            )

            # Download Menu bar Eventbus
            EventBus().do_add_zip_mod.connect(self._do_add_zip_mod)
            EventBus().do_browse_workshop.connect(self._do_browse_workshop)
            EventBus().do_check_for_workshop_updates.connect(
                self._do_check_for_workshop_updates
            )

            # Textures Menu bar Eventbus
            EventBus().do_optimize_textures.connect(self._do_optimize_textures)
            EventBus().do_delete_dds_textures.connect(self._do_delete_dds_textures)

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

            self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
            self.main_splitter.setChildrenCollapsible(False)

            # FRAME REQUIRED - to allow for styling
            self.main_layout_frame = QFrame()
            self.main_layout_frame.setObjectName("MainPanel")
            self.main_layout_frame.setLayout(self.main_layout)

            # INSTANTIATE WIDGETS
            self.mod_info_panel = ModInfoPanel(
                settings_controller=self.settings_controller,
            )
            self.mods_panel = ModsPanel(
                settings_controller=self.settings_controller,
            )

            self.mod_info_container = QWidget()
            self.mod_info_container.setLayout(self.mod_info_panel.panel)

            self.mods_panel_container = QWidget()
            self.mods_panel_container.setLayout(self.mods_panel.panel)

            self.main_splitter.addWidget(self.mod_info_container)
            self.main_splitter.addWidget(self.mods_panel_container)

            self.main_splitter.setHandleWidth(1)

            self.mod_info_container.setMinimumWidth(280)
            # WIDGETS INTO BASE LAYOUT
            self.main_layout.addWidget(self.main_splitter)

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
            self.mods_panel.active_mods_list.steamdb_blacklist_signal.connect(
                self._do_blacklist_action_steamdb
            )
            self.mods_panel.inactive_mods_list.steamdb_blacklist_signal.connect(
                self._do_blacklist_action_steamdb
            )
            self.mods_panel.active_mods_list.refresh_signal.connect(self._do_refresh)
            self.mods_panel.inactive_mods_list.refresh_signal.connect(self._do_refresh)

            EventBus().use_this_instead_clicked.connect(self._use_this_instead_clicked)

            EventBus().do_threaded_loading_animation.connect(
                self.do_threaded_loading_animation
            )

            EventBus().do_metadata_refresh_cache.connect(self.do_metadata_refresh_cache)

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

            # Progress widget for extraction operations
            self._extract_progress_widget: Optional[TaskProgressWindow] = None

            logger.info("Finished MainContent initialization")
            self.initialized = True

    @classmethod
    def instance(cls, *args: Any, **kwargs: Any) -> "MainContent":
        if cls._instance is None:
            cls._instance = cls(*args, **kwargs)
        elif args or kwargs:
            raise ValueError("MainContent instance has already been initialized.")
        return cls._instance

    def do_metadata_refresh_cache(self) -> None:
        """Force Refresh metadata cache"""
        self.metadata_manager.refresh_cache()

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
            if answer == QMessageBox.StandardButton.Yes:
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
            item = iml.selectedItems()[0]
            data = item.data(Qt.ItemDataRole.UserRole)
            uuid = data["uuid"]
            self.__mod_list_slot(uuid, cast(CustomListWidgetItem, item))

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
            item = aml.selectedItems()[0]
            data = item.data(Qt.ItemDataRole.UserRole)
            uuid = data["uuid"]
            self.__mod_list_slot(uuid, cast(CustomListWidgetItem, item))

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

    def _insert_data_into_lists(
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
        # Determine sort key and descending for inactive mods
        if self.settings_controller.settings.inactive_mods_sorting:
            # Use current UI state from the combobox and button
            sort_key = ModsPanelSortKey[self.mods_panel.inactive_mods_sort_key]
            descending = self.mods_panel.inactive_sort_descending
        else:
            sort_key = ModsPanelSortKey.FILESYSTEM_MODIFIED_TIME
            descending = True
        self.mods_panel.inactive_mods_list.recreate_mod_list_and_sort(
            list_type="inactive",
            uuids=inactive_mods_uuids,
            key=sort_key,
            descending=descending,
        )
        logger.info(
            f"Finished inserting mod data into active [{len(active_mods_uuids)}] and inactive [{len(inactive_mods_uuids)}] mod lists"
        )
        # Recalculate warnings for both lists
        # self.mods_panel.active_mods_list.recalculate_warnings_signal.emit()
        # self.mods_panel.inactive_mods_list.recalculate_warnings_signal.emit()

    def __duplicate_mods_prompt(self) -> None:
        """
        Opens the DuplicateModsPanel to allow user to resolve duplicate mods.
        """
        if not self.settings_controller.settings.duplicate_mods_warning:
            logger.warning(
                "User preference is not configured to display duplicate mods. Skipping..."
            )
            return
        elif (
            self.settings_controller.settings.duplicate_mods_warning
            and self.duplicate_mods
            and len(self.duplicate_mods) > 0
        ):
            duplicate_mods_count = len(self.duplicate_mods)
            logger.info(
                f"Found {duplicate_mods_count} duplicate mods. Opening DuplicateModsPanel..."
            )
            duplicate_mods_panel = DuplicateModsPanel(
                self.duplicate_mods, self.settings_controller
            )
            duplicate_mods_panel.setWindowModality(Qt.WindowModality.ApplicationModal)
            duplicate_mods_panel.show()
        else:
            logger.info("No duplicate mods found. Skipping...")

    def __missing_mods_prompt(self) -> None:
        """Open the MissingModsPrompt to allow user to download missing mods."""
        if not self.settings_controller.settings.try_download_missing_mods:
            logger.warning(
                "User preference is not configured to attempt downloading missing mods. Skipping..."
            )
            return
        elif (
            self.settings_controller.settings.try_download_missing_mods
            and self.missing_mods
            and len(self.missing_mods) > 0
        ):
            missing_mods_count = len(self.missing_mods)
            logger.info(
                f"Found {missing_mods_count} missing mods. Opening MissingModsPrompt..."
            )
            # Always open the MissingModsPrompt panel, allowing manual entry if Steam database is unavailable
            self.missing_mods_prompt = MissingModsPrompt(packageids=self.missing_mods)
            self.missing_mods_prompt._populate_from_metadata()
            self.missing_mods_prompt.setWindowModality(
                Qt.WindowModality.ApplicationModal
            )
            self.missing_mods_prompt.show()
        else:
            logger.info("No missing mods found. Skipping...")

    def _get_missing_packageid_uuids(self) -> list[str]:
        """
        Identify mods lacking a valid Package ID in their About.xml.

        A missing or invalid Package ID can cause dependency resolution issues
        and prevent proper mod identification. Mods are marked with a default
        placeholder value when no valid Package ID is found.

        :return: List of internal UUIDs for mods with missing Package ID.
        """
        return [
            uuid
            for uuid, mod_metadata in self.metadata_manager.internal_local_metadata.items()
            if mod_metadata.get("packageid") == app_constants.DEFAULT_MISSING_PACKAGEID
        ]

    def _get_missing_publishfieldid_uuids(self) -> list[str]:
        """
        Identify mods lacking a Publish Field ID (Steam Workshop ID).

        Workshop mods without a Publish Field ID cannot support automatic
        redownloads or update checking. This check intentionally excludes
        RimWorld core content and DLC since they are not published mods.

        :return: List of internal UUIDs for mods with missing Publish Field ID.
        """
        ignored_mods = IgnoreManager.load_ignored_mods()
        return [
            uuid
            for uuid, mod_metadata in self.metadata_manager.internal_local_metadata.items()
            if mod_metadata.get("publishedfileid") is None
            and mod_metadata.get("packageid") not in app_constants.RIMWORLD_PACKAGE_IDS
            and mod_metadata.get("packageid") not in ignored_mods
        ]

    def __check_and_warn_missing_mod_properties(self) -> None:
        """
        Scan for mods with missing critical properties and notify the user.

        This method checks all loaded mods for two critical properties:
        1. Package ID (required for proper mod identification and dependencies)
        2. Publish Field ID (required for Workshop mods to support updates)

        If any mods are missing these properties, a dedicated panel is displayed
        allowing the user to review the affected mods and contact authors.

        The method handles all exceptions gracefully to prevent disrupting
        the main application flow.
        """
        try:
            # Identify mods with missing critical properties
            missing_packageid_uuids = self._get_missing_packageid_uuids()
            missing_publishfieldid_uuids = self._get_missing_publishfieldid_uuids()

            # If no mods have missing properties, log and return early
            if not missing_packageid_uuids and not missing_publishfieldid_uuids:
                logger.info("No mods with missing properties found. Skipping...")
                return

            # Log summary statistics for debugging
            missing_packageid_count = len(missing_packageid_uuids)
            missing_publishfieldid_count = len(missing_publishfieldid_uuids)

            logger.info(
                f"Found {missing_packageid_count} mod(s) with missing Package ID and "
                f"{missing_publishfieldid_count} mod(s) with missing Publish Field ID. "
                f"Opening MissingModPropertiesPanel..."
            )

            # Display a unified panel showing all mods with missing properties,
            # grouped by property type for better user comprehension
            missing_mod_properties_panel = MissingModPropertiesPanel(
                missing_packageid_mods=missing_packageid_uuids,
                missing_publishfieldid_mods=missing_publishfieldid_uuids,
                settings_controller=self.settings_controller,
            )
            # Make the panel modal to ensure user acknowledges the issues
            missing_mod_properties_panel.setWindowModality(
                Qt.WindowModality.ApplicationModal
            )
            missing_mod_properties_panel.show()
        except Exception as e:
            logger.error(f"Error checking mod properties: {e}")

    def __mod_list_slot(self, uuid: str, item: CustomListWidgetItem) -> None:
        """
        This slot method is triggered when the user clicks on an item
        on a mod list.

        It takes the internal uuid and gets the
        complete json mod info for that internal uuid. It passes
        this information to the mod info panel to display.

        It also takes the selected mod (CustomListWidgetItem) and passes
        this to the mod info panel to display that mod's notes.

        :param uuid: uuid of mod
        :param item: selected CustomListWidgetItem
        """
        self.mod_info_panel.display_mod_info(
            uuid=uuid,
            render_unity_rt=self.settings_controller.settings.render_unity_rich_text,
        )
        self.mod_info_panel.show_user_mod_notes(item)

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

        self._insert_data_into_lists(active_mods_uuids, inactive_mods_uuids)

    def _do_check_for_update(self) -> None:
        """
        Check for RimSort updates using UpdateManager.
        """
        update_manager = UpdateManager(
            self.settings_controller, self, self.mod_info_panel
        )
        update_manager.do_check_for_update()

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

    @Slot(str, object, str)
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
                list_type="Active",
            )
            self.mods_panel.inactive_mods_filter_data_source_index = len(
                self.mods_panel.data_source_filter_icons
            )
            self.mods_panel.signal_clear_search(
                list_type="Inactive",
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

            # check if we have duplicate mods, prompt user
            self.__duplicate_mods_prompt()

            # check if we have missing mods, prompt user
            self.__missing_mods_prompt()

            # Check if we have mods with missing properties (Package ID and/or Publish Field ID)
            self.__check_and_warn_missing_mod_properties()

            # Check Workshop mods for updates if configured
            if self.settings_controller.settings.steam_mods_update_check:
                logger.info("Checking Workshop mods for updates...")
                self._do_check_for_workshop_updates()
            else:
                logger.info(
                    "User preference is not configured to check Workshop mod for updates. Skipping.."
                )
        else:
            self._insert_data_into_lists([], [])
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
            app_constants.RIMWORLD_DLC_METADATA["3022790"]["packageid"],
        ]
        # If user wants Clear to also move DLC, only keep the base game in Active
        if self.settings_controller.settings.clear_moves_dlc and package_id_order:
            package_ids_to_keep_active = [package_id_order[0]]  # Base game only
        else:
            package_ids_to_keep_active = package_id_order
        # Create a set of all package IDs from mod_data
        package_ids_set = set(
            mod_data["packageid"]
            for mod_data in self.metadata_manager.internal_local_metadata.values()
        )
        # Iterate over the package IDs we want to keep active
        for package_id in package_ids_to_keep_active:
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
        self._insert_data_into_lists(active_mods_uuids, inactive_mods_uuids)
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

        # Compile metadata for active mods so newly-added ones have dependency info
        self.metadata_manager.compile_metadata(uuids=list(active_mods))

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
        logger.debug(
            f"Sort result: {success}, new order: {new_order}, current order: {current_order}"
        )
        # Check if successful and orders differ
        if success and new_order != current_order:
            logger.info(
                "Finished combining all tiers of mods. Inserting into mod lists!"
            )
            # Disable widgets while inserting
            self.disable_enable_widgets_signal.emit(False)
            # Insert data into lists
            self._insert_data_into_lists(
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
            self._insert_data_into_lists(active_mods_uuids, inactive_mods_uuids)

            # check if we have duplicate mods, prompt user
            self.__duplicate_mods_prompt()

            # check if we have missing mods, prompt user
            self.__missing_mods_prompt()
        else:
            logger.info("USER ACTION: pressed cancel, passing")

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
        self._insert_data_into_lists(active_mods_uuids, inactive_mods_uuids)
        logger.info("Got new mods according to imported Rentry.co")

        # check if we have duplicate mods, prompt user
        self.__duplicate_mods_prompt()

        # check if we have missing mods, prompt user
        self.__missing_mods_prompt()

    def _do_import_list_workshop_collection(self) -> None:
        # Check internet connection before attempting task
        if not check_internet_connection():
            return
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
        self._insert_data_into_lists(active_mods_uuids, inactive_mods_uuids)
        logger.info("Got new mods according to imported Workshop collection")

        # check if we have duplicate mods, prompt user
        self.__duplicate_mods_prompt()

        # check if we have missing mods, prompt user
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

    def _build_rentry_report(
        self,
        mods: list[str],
        active_mods_packageid_to_uuid: dict[str, str],
        active_steam_mods_packageid_to_pfid: dict[str, str],
        active_steam_mods_pfid_to_preview_url: dict[str, str],
        truncated: bool = False,
    ) -> str:
        truncated_note = " (truncated)" if truncated else ""
        active_mods_rentry_report = (
            "# RimWorld mod list       ![](https://github.com/RimSort/RimSort/blob/main/docs/rentry_preview.png?raw=true)"
            + f"\nCreated with RimSort {AppInfo().app_version}"
            + f"\nMod list was created for game version: `{self.metadata_manager.game_version}`"
            + "\n!!! info Local mods are marked as yellow labels with packageid in brackets."
            + f"\n\n\n\n!!! note Mod list length: `{len(mods)}`{truncated_note}\n"
        )
        # Add a line for each mod
        for package_id in mods:
            count = mods.index(package_id) + 1
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
        return active_mods_rentry_report

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
        # Build our report using the helper method
        active_mods_rentry_report = self._build_rentry_report(
            active_mods,
            active_mods_packageid_to_uuid,
            active_steam_mods_packageid_to_pfid,
            active_steam_mods_pfid_to_preview_url,
        )
        # Check report length and offer truncation if necessary
        if len(active_mods_rentry_report) > 200000:
            # Calculate the maximum number of mods that can fit within 200,000 characters
            max_mods = 0
            for i in range(1, len(active_mods) + 1):
                test_mods = active_mods[:i]
                test_report = self._build_rentry_report(
                    test_mods,
                    active_mods_packageid_to_uuid,
                    active_steam_mods_packageid_to_pfid,
                    active_steam_mods_pfid_to_preview_url,
                    truncated=True,
                )
                if len(test_report) > 200000:
                    max_mods = i - 1
                    break
                max_mods = i
            if max_mods == 0:
                dialogue.show_warning(
                    title=self.tr("Report too long"),
                    text=self.tr(
                        "Even the first mod exceeds the 200,000 character limit."
                    ),
                    information=self.tr("Cannot upload this report to Rentry.co."),
                )
                return
            answer = dialogue.show_dialogue_conditional(
                title=self.tr("Report too long"),
                text=self.tr("The mod list report exceeds 200,000 characters."),
                information=self.tr(
                    "Rentry.co may reject uploads that are too long. Would you like to truncate the report to the first {max_mods} mods or cancel the upload?"
                ).format(max_mods=max_mods),
                button_text_override=[
                    self.tr("Truncate to the first {max_mods} mods").format(
                        max_mods=max_mods
                    )
                ],
            )
            if answer == self.tr("Truncate to the first {max_mods} mods").format(
                max_mods=max_mods
            ):
                # Rebuild report with the maximum number of mods that fit
                truncated_mods = active_mods[:max_mods]
                active_mods_rentry_report = self._build_rentry_report(
                    truncated_mods,
                    active_mods_packageid_to_uuid,
                    active_steam_mods_packageid_to_pfid,
                    active_steam_mods_pfid_to_preview_url,
                    truncated=True,
                )
            else:
                logger.info("USER ACTION: cancelled truncation, passing")
                return
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

    def _do_import_list_from_save_file(self) -> None:
        """
        Import a mod list from a RimWorld save (.rws) file.

        Opens a file dialog defaulting to the RimWorld Saves directory and
        reuses the existing XML import flow to populate the lists.
        """
        logger.info("Opening file dialog to select RimWorld save (.rws)")
        # Default to the instance's Saves directory (sibling of Config)
        saves_dir = str(
            Path(
                self.settings_controller.settings.instances[
                    self.settings_controller.settings.current_instance
                ].config_folder
            ).parent
            / "Saves"
        )
        file_path = dialogue.show_dialogue_file(
            mode="open",
            caption=self.tr("Import from RimWorld Save File"),
            _dir=saves_dir,
            _filter=self.tr("RimWorld save (*.rws);;All files (*.*)"),
        )
        logger.info(f"Selected save path: {file_path}")
        if not file_path:
            logger.debug("USER ACTION: pressed cancel, passing")
            return

        # Clear searches and data source filters just like XML import
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

        logger.info(f"Trying to import mods list from save file: {file_path}")
        (
            active_mods_uuids,
            inactive_mods_uuids,
            self.duplicate_mods,
            self.missing_mods,
        ) = metadata.get_mods_from_list(mod_list=file_path)
        logger.info("Got new mods according to imported save file")

        self._insert_data_into_lists(active_mods_uuids, inactive_mods_uuids)

        # check if we have duplicate mods, prompt user
        self.__duplicate_mods_prompt()

        # check if we have missing mods, prompt user
        self.__missing_mods_prompt()

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
        answer_str = str(answer)
        download_text = self.tr("Open settings")
        if download_text in answer_str:
            self.settings_controller.show_settings_dialog()

    def _upload_file(self, path: Path | None) -> None:
        if not path or not os.path.exists(path):
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
                text=self.tr("Uploaded {path.name} to https://0x0.st/").format(
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

    def _open_in_default_editor(self, path: Path | None) -> None:
        if path and path.exists():
            logger.info(f"Opening file in default editor: {path}")
            launch_process(
                self.settings_controller.settings.text_editor_location,
                self.settings_controller.settings.text_editor_folder_arg.split(" ")
                + [str(path)],
                str(AppInfo().application_folder),
            )
        else:
            dialogue.show_warning(
                title=self.tr("Failed to open file."),
                text=self.tr(
                    "Failed to open the file with default text editor. It may not exist."
                ),
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
            self._insert_data_into_lists(
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
    def _do_generate_todds_txt(self) -> str:
        logger.info("Generating todds.txt...")
        # Create or overwrite todds.txt in temp directory
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
                    todds_txt_file.write(os.path.abspath(workshop_mods_target) + "\n")
        else:
            with open(todds_txt_path, "a", encoding="utf-8") as todds_txt_file:
                for uuid in self.mods_panel.active_mods_list.uuids:
                    todds_txt_file.write(
                        os.path.abspath(
                            self.metadata_manager.internal_local_metadata[uuid]["path"]
                        )
                        + "\n"
                    )
        logger.info(f"Generated todds.txt at: {todds_txt_path}")
        return todds_txt_path

    def _do_optimize_textures(self) -> None:
        logger.info("Optimizing textures with todds...")
        todds_txt_path = self._do_generate_todds_txt()
        # Initialize todds interface
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

    def _do_delete_dds_textures(self) -> None:
        logger.info("Deleting .dds textures with todds...")
        todds_txt_path = self._do_generate_todds_txt()
        # Initialize todds interface
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
    def _do_import_steamcmd_acf_data(self) -> None:
        logger.info("Importing SteamCMD ACF data...")
        metadata.import_steamcmd_acf_data(
            rimsort_storage_path=str(AppInfo().app_storage_folder),
            steamcmd_appworkshop_acf_path=self.steamcmd_wrapper.steamcmd_appworkshop_acf_path,
        )

    def _do_reset_steamcmd_acf_data(self) -> None:
        answer = dialogue.show_dialogue_conditional(
            title=self.tr("Reset SteamCMD ACF data file"),
            text=self.tr("Are you sure you want to reset SteamCMD ACF data file?"),
            information=self.tr(
                "This file is created and used by steamcmd to track mod informaton, This action cannot be undone."
            ),
        )
        if answer == QMessageBox.StandardButton.Yes:
            logger.info("Resetting SteamCMD ACF data file")
            steamcmd_appworkshop_acf_path = (
                self.steamcmd_wrapper.steamcmd_appworkshop_acf_path
            )
            if os.path.exists(steamcmd_appworkshop_acf_path):
                logger.debug(
                    f"Deleting SteamCMD ACF data file: {steamcmd_appworkshop_acf_path}"
                )
                os.remove(steamcmd_appworkshop_acf_path)
                dialogue.show_information(
                    title=self.tr("Reset SteamCMD ACF data file"),
                    text=self.tr(
                        f"Successfully deleted SteamCMD ACF data file: {steamcmd_appworkshop_acf_path}"
                    ),
                    information=self.tr(
                        "ACF data file will be recreated when you download mods using steamcmd next time."
                    ),
                )
                # Do a full refresh of metadata and UI
                self._do_refresh()
            else:
                logger.debug("SteamCMD ACF data does not exist. Skipping deletion.")
                dialogue.show_warning(
                    title=self.tr("SteamCMD ACF data file does not exist"),
                    text=self.tr(
                        "ACf file does not exist. It will be created when you download mods using steamcmd."
                    ),
                )
        else:
            logger.debug("user cancelled reset of SteamCMD ACF data file")
            return

    def _do_browse_workshop(self) -> None:
        self.steam_browser = SteamBrowser(
            "https://steamcommunity.com/app/294100/workshop/",
            self.metadata_manager,
            self.settings_controller,
        )
        self.steam_browser.show()

    def _do_check_for_workshop_updates(self) -> None:
        # Check internet connection before attempting task
        if not check_internet_connection():
            return
        # REFRESH TIMESTAMPS: Query Steam directly for current installation timestamps
        # This ensures we compare against Steam's live state, not stale ACF data
        self.metadata_manager.refresh_workshop_timestamps_via_steamworks()
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
        workshop_mod_updater = WorkshopModUpdaterPanel()
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

                    # Create Process with worker function
                    from multiprocessing import Process

                    def _launch_game() -> None:
                        steamworks_game_launch_worker(
                            game_install_path=instruction[1][0],
                            args=instruction[1][1],
                            _libs=str((AppInfo().application_folder / "libs")),
                        )

                    steamworks_api_process = Process(target=_launch_game)
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
                        f"Creating Steamworks subscription task with instruction {instruction}"
                    )
                    self.steamworks_in_use = True

                    # instruction[1] already contains int pfids from EventBus
                    pfids = instruction[1]

                    # Create and execute runnable in Qt thread pool
                    runnable = SteamSubscriptionRunnable(instruction[0], pfids)
                    QThreadPool.globalInstance().start(runnable)

                    # Wait for thread to complete
                    logger.debug("Waiting for subscription thread to complete...")
                    QThreadPool.globalInstance().waitForDone()
                    logger.info("Subscription thread completed")

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
        # Do a full refresh of metadata and UI
        # self._do_refresh()
        # TODO  check if this is necessary
        """       
        Disabled refresh since steam downloads are not instant and in the background in its own time
        Refreshing metadata and UI here could tag mods as invalid or cause crashes due to key errors etc
        """

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
            url, ok = QInputDialog.getText(
                None,
                self.tr("Enter zip file url"),
                self.tr("Enter a zip file url (http/https) to download to local mods:"),
            )
            if url and ok:
                # Check internet connection before attempting task
                if not check_internet_connection():
                    return
                # Create temporary directory for downloading
                file_download, temp_path = tempfile.mkstemp(suffix=".zip")
                os.close(file_download)

                # Hide the mod info panel and show progress in the panel instead
                self.mod_info_panel.info_panel_frame.hide()
                self.disable_enable_widgets_signal.emit(False)

                # Create and show download progress in panel
                progress_widget = TaskProgressWindow(
                    title="Downloading ZIP File",
                    show_message=True,
                    show_percent=True,
                )
                self.mod_info_panel.panel.addWidget(progress_widget)

                # Flag to track if download was cancelled
                download_cancelled = False

                def on_cancel_requested() -> None:
                    nonlocal download_cancelled
                    download_cancelled = True
                    logger.info("User cancelled download")

                progress_widget.cancel_requested.connect(on_cancel_requested)

                try:
                    logger.info(f"Downloading {url} to {temp_path}")
                    response = requests.get(url, stream=True, timeout=30)
                    response.raise_for_status()

                    # Get total file size
                    total_size = int(response.headers.get("content-length", 0))
                    downloaded_size = 0

                    with open(temp_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            # Check if download was cancelled
                            if download_cancelled:
                                logger.warning("Download cancelled by user")
                                break

                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)

                                # Update progress
                                if total_size > 0:
                                    percent = int((downloaded_size / total_size) * 100)
                                    size_mb = downloaded_size / (1024 * 1024)
                                    total_mb = total_size / (1024 * 1024)
                                    message = f"Downloading: {size_mb:.2f} / {total_mb:.2f} MB"
                                else:
                                    percent = -1  # Indeterminate progress
                                    size_mb = downloaded_size / (1024 * 1024)
                                    message = f"Downloading: {size_mb:.2f} MB"

                                progress_widget.update_progress(percent, message)

                                # Process events to allow UI updates and cancel clicks
                                QApplication.processEvents()

                    # Clean up progress widget
                    self.mod_info_panel.panel.removeWidget(progress_widget)
                    progress_widget.close()

                    # Only extract if download completed successfully
                    if not download_cancelled:
                        self._extract_zip_file(temp_path, delete=True)
                    else:
                        # Clean up cancelled download
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        logger.info("Download cancelled, cleaned up temporary file")

                except Exception as e:
                    # Clean up progress widget
                    self.mod_info_panel.panel.removeWidget(progress_widget)
                    progress_widget.close()
                    logger.error(f"Failed to download zip file: {e}")
                    dialogue.show_warning(
                        title=self.tr("Failed to download zip file"),
                        text=self.tr("The zip file could not be downloaded."),
                        information=self.tr("File: {file_path}\nError: {e}").format(
                            file_path=temp_path, e=e
                        ),
                    )
                    # Clean up on error
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

                # Restore mod info panel
                self.mod_info_panel.info_panel_frame.show()
                self.disable_enable_widgets_signal.emit(True)
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
        except (BadZipFile, ValueError, PermissionError, OSError) as e:
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
        zip_contents = get_zip_contents(file_path)
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

        # Hide the mod info panel and show progress in the panel instead
        self.mod_info_panel.info_panel_frame.hide()
        self.disable_enable_widgets_signal.emit(False)

        # Create and show extraction progress in panel
        progress_widget = TaskProgressWindow(
            title="Extracting ZIP File",
            show_message=True,
            show_percent=True,
        )
        self.mod_info_panel.panel.addWidget(progress_widget)

        # Store reference for signal connections
        self._extract_progress_widget = progress_widget

        self._extract_thread = ZipExtractThread(
            file_path, base_path, overwrite_all=overwrite, delete=delete
        )
        self._extract_thread.progress.connect(self._on_extract_progress)
        self._extract_thread.finished.connect(self._on_extract_finished)
        progress_widget.cancel_requested.connect(self._extract_thread.stop)

        self._extract_thread.start()

    def _on_extract_progress(self, percent: int, message: str) -> None:
        """Update progress bar during extraction."""
        if hasattr(self, "_extract_progress_widget") and self._extract_progress_widget:
            self._extract_progress_widget.update_progress(percent, message)

    def _on_extract_finished(self, success: bool, message: str) -> None:
        """Handle extraction completion."""
        try:
            # Clean up progress widget
            if (
                hasattr(self, "_extract_progress_widget")
                and self._extract_progress_widget
            ):
                self.mod_info_panel.panel.removeWidget(self._extract_progress_widget)
                self._extract_progress_widget.close()
                self._extract_progress_widget = None

            # Show completion dialog
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

        finally:
            # Always restore mod info panel (like download does)
            self.mod_info_panel.info_panel_frame.show()
            self.disable_enable_widgets_signal.emit(True)

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
        if answer == QMessageBox.StandardButton.Yes:
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

    def _do_open_ignore_json_editor(self) -> None:
        """Open the Ignore JSON Editor dialog."""
        self.ignore_json_editor = IgnoreJsonEditor()
        self.ignore_json_editor.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.ignore_json_editor.show()

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
        args, ok = QInputDialog.getText(
            None,
            self.tr("Edit Steam DB repo"),
            self.tr("Enter URL (https://github.com/AccountName/RepositoryName):"),
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
        args, ok = QInputDialog.getText(
            None,
            self.tr("Edit Community Rules DB repo"),
            self.tr("Enter URL (https://github.com/AccountName/RepositoryName):"),
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
            # Do a full refresh of metadata and UI
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
                if answer == QMessageBox.StandardButton.Yes:
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
        args, ok = QInputDialog.getText(
            None,
            self.tr("Edit Steam WebAPI key"),
            self.tr("Enter your personal 32 character Steam WebAPI key here:"),
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
        if answer == QMessageBox.StandardButton.Yes:
            with open(path, "w", encoding="utf-8") as output:
                json.dump(db_output_c, output, indent=4)
            # Do a full refresh of metadata and UI
            self._do_refresh()
        else:
            logger.debug("USER ACTION: declined to continue rules database update.")

    def _do_set_database_expiry(self) -> None:
        """
        Opens a QDialogInput that allows the user to edit their preferred
        WebAPI Query Expiry (in seconds)
        """
        args, ok = QInputDialog.getText(
            None,
            self.tr("Edit SteamDB expiry:"),
            self.tr(
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
        if not self.check_if_essential_paths_are_set(prompt=True):
            return

        create_backup_in_thread(self.settings_controller.settings)

        if self.mods_panel.active_mods_list.uuids != self.active_mods_uuids_last_save:
            answer = dialogue.show_dialogue_conditional(
                title=self.tr("Unsaved Changes"),
                text=self.tr("You have unsaved changes. What would you like to do?"),
                button_text_override=[self.tr("Save and Run"), self.tr("Run Anyway")],
            )
            if answer == self.tr("Save and Run"):
                logger.info(
                    "User chose to save before proceeding with running the game."
                )
                self._do_save()
            elif answer == self.tr("Run Anyway"):
                logger.info(
                    "User chose to ignore unsaved changes and proceed with running the game anyway."
                )
                pass
            elif answer == QMessageBox.StandardButton.Cancel:
                logger.info("User chose to cancel.")
                return

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
            with open(steam_appid_path, "w", encoding="utf-8") as f:
                f.write("294100")
        elif not steam_client_integration and steam_appid_path.exists():
            steam_appid_path.unlink()

        # Launch independent game process without Steamworks API
        logger.info("Launching game process without Steamworks API...")
        launch_game_process(game_install_path=game_install_path, args=run_args)

    @Slot()
    def _use_this_instead_clicked(self) -> None:
        """
        When clicked, opens the Use This Instead panel.
        """
        if (
            self.settings_controller.settings.external_use_this_instead_metadata_source
            == "None"
        ):
            dialogue.show_warning(
                title=self.tr("Use This Instead"),
                text=self.tr(
                    'Please configure "Use This Instead" database in settings.'
                ),
            )
            return

        self.use_this_instead_dialog = UseThisInsteadPanel(
            mod_metadata=self.metadata_manager.internal_local_metadata
        )
        if not self.use_this_instead_dialog.show_if_has_alternatives():
            dialogue.show_information(
                title=self.tr("Use This Instead"),
                text=self.tr(
                    'No suggestions were found in the "Use This Instead" database.'
                ),
            )
