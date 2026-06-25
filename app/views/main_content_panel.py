import json
import os
import shutil
import sys
import tempfile
import time
import traceback
import webbrowser
from functools import partial
from pathlib import Path
from typing import Any, Callable, Literal, Optional, cast, overload

from loguru import logger
from PySide6.QtCore import (
    QEventLoop,
    QObject,
    QProcess,
    Qt,
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
import app.views.dialogue as dialogue
from app.controllers.metadata_controller import MetadataController
from app.controllers.sort_controller import Sorter
from app.controllers.todds_controller import ToddsController
from app.models.animations import LoadingAnimation
from app.models.divider import is_divider_uuid
from app.models.metadata.metadata_structure import AboutXmlMod, ModType
from app.models.settings import Settings
from app.services.import_export_service import ImportExportService
from app.services.window_manager import WindowManager
from app.sort.mod_sorting import ModsPanelSortKey
from app.utils import http
from app.utils.app_info import AppInfo
from app.utils.custom_list_widget_item import CustomListWidgetItem
from app.utils.db_builder import DatabaseBuilder
from app.utils.dict_utils import recursively_update_dict
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
from app.utils.json_utils import atomic_json_dump
from app.utils.rentry.wrapper import RentryImport
from app.utils.steam.availability import check_steam_available
from app.utils.steam.steambrowser.browser import SteamBrowser
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.utils.steam.steamworks.wrapper import (
    SteamworksGameLaunch,
    SteamworksSubscriptionHandler,
)
from app.utils.steam.webapi.wrapper import CollectionImport
from app.utils.steam.workshop_utils import (
    WorkshopUpdateResult,
    check_if_pfids_blacklisted,
    import_steamcmd_acf_data,
    query_workshop_update_data,
)
from app.utils.system_info import SystemInfo
from app.utils.update_utils import UpdateManager
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
from app.views.settings_dialog import SettingsDialog
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

    def __init__(
        self,
        settings: Settings,
        metadata_controller: MetadataController,
        show_settings_dialog: Callable[..., None] | None = None,
        settings_dialog: SettingsDialog | None = None,
    ) -> None:
        if not hasattr(self, "initialized"):
            super().__init__()
            logger.debug("Initializing MainContent")
            self.settings = settings
            self._show_settings_dialog = show_settings_dialog
            self._settings_dialog = settings_dialog
            self.metadata_controller = metadata_controller
            self._init_services()
            self._init_widgets()
            self._setup_layout()
            self._connect_signals()
            self._init_state()
            logger.info("Finished MainContent initialization")
            self.initialized = True

    def _init_services(self) -> None:
        self.db_builder = DatabaseBuilder(self.settings)
        self.steam_browser: SteamBrowser | None = None
        self.steamcmd_runner: RunnerPanel | None = None
        self.steamcmd_wrapper = SteamcmdInterface.instance()
        self._import_export_service = ImportExportService(
            self.metadata_controller, self.settings
        )
        self.query_runner: RunnerPanel | None = None
        self.steamworks_in_use = False
        self.todds_runner: RunnerPanel | None = None
        self.todds_controller: ToddsController

    def _init_widgets(self) -> None:
        self.mod_info_panel = ModInfoPanel(
            settings=self.settings,
            metadata_controller=self.metadata_controller,
        )
        self.mods_panel = ModsPanel(
            settings=self.settings,
            metadata_controller=self.metadata_controller,
        )
        self.mod_info_container = QWidget()
        self.mod_info_container.setLayout(self.mod_info_panel.panel)
        self.mods_panel_container = QWidget()
        self.mods_panel_container.setLayout(self.mods_panel.panel)

    def _setup_layout(self) -> None:
        self.main_layout = QHBoxLayout()
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_layout_frame = QFrame()
        self.main_layout_frame.setObjectName("MainPanel")
        self.main_layout_frame.setLayout(self.main_layout)
        self.main_splitter.addWidget(self.mod_info_container)
        self.main_splitter.addWidget(self.mods_panel_container)
        self.main_splitter.setHandleWidth(1)
        self.mod_info_container.setMinimumWidth(280)
        self.main_layout.addWidget(self.main_splitter)

    def _connect_signals(self) -> None:
        EventBus().settings_have_changed.connect(self._on_settings_have_changed)
        EventBus().do_check_for_application_update.connect(self._do_check_for_update)
        EventBus().do_open_mod_list.connect(self._do_import_list_file_xml)
        EventBus().do_import_mod_list_from_rentry.connect(self._do_import_list_rentry)
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
            self.db_builder._on_do_download_all_mods_via_steamcmd
        )
        EventBus().do_download_all_mods_via_steam.connect(
            self.db_builder._on_do_download_all_mods_via_steam
        )
        EventBus().do_compare_steam_workshop_databases.connect(
            self.db_builder._do_generate_metadata_comparison_report
        )
        EventBus().do_merge_steam_workshop_databases.connect(
            self.db_builder._do_merge_databases
        )
        EventBus().do_build_steam_workshop_database.connect(
            self.db_builder._do_build_database_thread
        )
        EventBus().do_import_acf.connect(self._do_import_steamcmd_acf_data)
        EventBus().do_export_acf.connect(self._do_export_steamcmd_acf_data)
        EventBus().do_delete_acf.connect(self._do_reset_steamcmd_acf_data)
        EventBus().do_install_steamcmd.connect(self._do_setup_steamcmd)

        EventBus().do_refresh_mods_lists.connect(self._do_refresh)
        EventBus().do_clear_active_mods_list.connect(self._do_clear)
        EventBus().do_restore_active_mods_list.connect(self._do_restore)
        EventBus().do_sort_active_mods_list.connect(self._do_sort)
        EventBus().do_save_active_mods_list.connect(self._do_save)
        EventBus().do_run_game.connect(self._do_run_game)

        EventBus().do_open_app_directory.connect(self._do_open_app_directory)
        EventBus().do_open_settings_directory.connect(self._do_open_settings_directory)
        EventBus().do_open_rimsort_logs_directory.connect(
            self._do_open_rimsort_logs_directory
        )
        EventBus().do_open_rimworld_directory.connect(self._do_open_rimworld_directory)
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

        EventBus().do_steamcmd_download.connect(self._do_download_mods_with_steamcmd)

        EventBus().do_steamworks_api_call.connect(self._do_steamworks_api_call_animated)

        EventBus().do_rule_editor.connect(
            lambda: self._do_open_rule_editor(
                compact=False, initial_mode="community_rules"
            )
        )
        EventBus().do_ignore_json_editor.connect(self._do_open_ignore_json_editor)
        EventBus().do_check_missing_mod_properties.connect(
            self.__check_and_warn_missing_mod_properties
        )

        EventBus().do_add_zip_mod.connect(self._do_add_zip_mod)
        EventBus().do_browse_workshop.connect(self._do_browse_workshop)
        EventBus().do_check_for_workshop_updates.connect(
            self._do_check_for_workshop_updates
        )
        EventBus().do_steam_verify_game_files.connect(self.do_steam_verify_game_files)

        EventBus().do_optimize_textures.connect(self._do_optimize_textures)
        EventBus().do_delete_dds_textures.connect(self._do_delete_dds_textures)

        self.metadata_controller.mod_created_signal.connect(
            self.mods_panel.on_mod_created
        )
        self.metadata_controller.mod_deleted_signal.connect(
            self.mods_panel.on_mod_deleted
        )
        self.metadata_controller.mod_metadata_updated_signal.connect(
            self.mods_panel.on_mod_metadata_updated
        )
        self.metadata_controller.metadata_refreshed.connect(self._on_metadata_refreshed)
        self.mods_panel.active_mods_list.key_press_signal.connect(
            self.__handle_active_mod_key_press
        )
        self.mods_panel.inactive_mods_list.key_press_signal.connect(
            self.__handle_inactive_mod_key_press
        )
        self.mods_panel.active_mods_list.mod_info_signal.connect(self.__mod_list_slot)
        self.mods_panel.inactive_mods_list.mod_info_signal.connect(self.__mod_list_slot)
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

    def _init_state(self) -> None:
        self.active_mods_uuids_last_save: list[str] = []
        self.active_mods_dividers_last_save: list[dict[str, Any]] = []
        self.active_mods_uuids_restore_state: list[str] = []
        self.inactive_mods_uuids_restore_state: list[str] = []
        self.duplicate_mods: dict[str, Any] = {}
        self._extract_progress_widget: Optional[TaskProgressWindow] = None
        self.window_manager = WindowManager(self.metadata_controller)
        self._active_loading_loop: QEventLoop | None = None
        self._refresh_in_progress: bool = False

    @classmethod
    def instance(cls, *args: Any, **kwargs: Any) -> "MainContent":
        if cls._instance is None:
            cls._instance = cls(*args, **kwargs)
        elif args or kwargs:
            raise ValueError("MainContent instance has already been initialized.")
        return cls._instance

    @Slot()
    def _on_metadata_refreshed(self) -> None:
        """Handle metadata refreshes triggered outside the main refresh flow.

        When ``_refresh_in_progress`` is True, the main ``_do_refresh`` flow is
        already handling repopulation explicitly (so this is a no-op).
        When False — e.g. from ``do_metadata_refresh_cache`` — we repopulate
        the mod lists here so the UI reflects the updated metadata.
        """
        if self._refresh_in_progress:
            return
        self.__repopulate_lists()
        self.mods_panel.refresh_all_tag_filter_selectors()

    def abort_loading(self) -> None:
        """Abort any in-progress loading animation by quitting its nested event loop.

        Called from MainWindow.closeEvent to unblock the startup scanning so
        the process can exit cleanly.
        """
        if self._active_loading_loop is not None:
            self._active_loading_loop.quit()

    def close_child_windows(self) -> None:
        """Close all tracked child windows.

        Called when the main window is closing to ensure no orphan
        windows remain on screen.
        """
        self.window_manager.close_all()

    def do_metadata_refresh_cache(self) -> None:
        """Force Refresh metadata cache"""
        self.metadata_controller.refresh_metadata()

    def check_if_essential_paths_are_set(self, prompt: bool = True) -> bool:
        """
        When the user starts the app for the first time, none
        of the paths will be set. We should check for this and
        not throw a fatal error trying to load mods until the
        user has had a chance to set paths.
        """
        current_instance = self.settings.current_instance
        game_folder_path = self.settings.instances[current_instance].game_folder
        config_folder_path = self.settings.instances[current_instance].config_folder
        local_mods_folder_path = self.settings.instances[current_instance].local_folder
        logger.info(f"Game folder: {game_folder_path}")
        logger.info(f"Config folder: {config_folder_path}")
        logger.info(f"Local mods folder: {local_mods_folder_path}")
        if (
            game_folder_path
            and config_folder_path
            and local_mods_folder_path
            and os.path.exists(game_folder_path)
            and os.path.exists(config_folder_path)
            and os.path.exists(local_mods_folder_path)
        ):
            logger.info("Essential paths set!")
            return True
        else:
            logger.warning("Essential path(s) are invalid or not set!")
            answer = dialogue.show_dialogue_conditional(
                title=self.tr("Essential path(s)"),
                text=self.tr("Essential path(s) are invalid or not set!"),
                information=(
                    self.tr(
                        "RimSort requires the below paths to be set.<br/><br/>"
                        "1) Game folder (Folder where RimWorld is installed).<br/><br/>"
                        "2) Config folder (Folder where ModsConfig.xml is located)<br/><br/>"
                        "3) Local mods folder (Mods folder inside the RimWorld installation).<br/><br/>"
                        "4) Steam mods folder (Only set if you use Steam user also enable Steam Client Integration)<br/><br/>"
                        "Try Using the autodetect functionality to set all paths automatically.<br/><br/>"
                        "Would you like to open the settings to configure them now?"
                    )
                ),
            )
            if (
                answer == QMessageBox.StandardButton.Yes
                and self._show_settings_dialog is not None
            ):
                self._show_settings_dialog("Locations")
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
            selected_items = iml.selectedItems()
            if not selected_items:
                return
            item = selected_items[0]
            data = item.data(Qt.ItemDataRole.UserRole)
            uuid = data["path"]
            self.__mod_list_slot(uuid, cast(CustomListWidgetItem, item))

        elif key == "Return" or key == "Space" or key == "DoubleClick":
            # TODO: graphical bug where if you hold down the key, items are
            # inserted too quickly and become empty items

            items_to_move = [
                i
                for i in aml.selectedItems().copy()
                if not getattr(i.data(Qt.ItemDataRole.UserRole), "is_divider", False)
            ]
            if items_to_move:
                first_selected = sorted(aml.row(i) for i in items_to_move)[0]

                # Remove items from current list
                for item in items_to_move:
                    data = item.data(Qt.ItemDataRole.UserRole)
                    uuid = data["path"]
                    aml.paths.remove(uuid)
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
            uuid = data["path"]
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
                    uuid = data["path"]
                    iml.paths.remove(uuid)
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
        # Snapshot live divider state before the list is cleared
        live_dividers = self.mods_panel.active_mods_list.get_dividers_data()
        if live_dividers:
            self.settings.active_mods_dividers = live_dividers
        saved_dividers = self.settings.active_mods_dividers
        self.mods_panel.active_mods_list.recreate_mod_list(
            list_type="active", uuids=active_mods_uuids
        )
        # Restore dividers into the active list
        if saved_dividers:
            self.mods_panel.active_mods_list.restore_dividers(saved_dividers)
        # Use current UI state from the combobox and button for inactive mods.
        sort_key = ModsPanelSortKey[self.mods_panel.inactive_mods_sort_key]
        descending = self.mods_panel.inactive_sort_descending
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
        if not self.settings.duplicate_mods_warning:
            logger.warning(
                "User preference is not configured to display duplicate mods. Skipping..."
            )
            return
        elif (
            self.settings.duplicate_mods_warning
            and self.duplicate_mods
            and len(self.duplicate_mods) > 0
        ):
            duplicate_mods_count = len(self.duplicate_mods)
            logger.info(
                f"Found {duplicate_mods_count} duplicate mods. Opening DuplicateModsPanel..."
            )
            duplicate_mods_panel = DuplicateModsPanel(
                self.duplicate_mods, metadata_controller=self.metadata_controller
            )
            self.window_manager.register(duplicate_mods_panel)
            duplicate_mods_panel.setWindowModality(Qt.WindowModality.ApplicationModal)
            duplicate_mods_panel.show()
        else:
            logger.info("No duplicate mods found. Skipping...")

    def __missing_mods_prompt(self) -> None:
        """Open the MissingModsPrompt to allow user to download missing mods."""
        if not self.settings.try_download_missing_mods:
            logger.warning(
                "User preference is not configured to attempt downloading missing mods. Skipping..."
            )
            return
        elif (
            self.settings.try_download_missing_mods
            and self.missing_mods
            and len(self.missing_mods) > 0
        ):
            missing_mods_count = len(self.missing_mods)
            logger.info(
                f"Found {missing_mods_count} missing mods. Opening MissingModsPrompt..."
            )
            # Always open the MissingModsPrompt panel, allowing manual entry if Steam database is unavailable
            self.missing_mods_prompt = MissingModsPrompt(
                packageids=self.missing_mods,
                metadata_controller=self.metadata_controller,
            )
            self.window_manager.register_attr(self, "missing_mods_prompt")
            self.missing_mods_prompt._populate_from_metadata()
            self.missing_mods_prompt.setWindowModality(
                Qt.WindowModality.ApplicationModal
            )
            self.missing_mods_prompt.show()
        else:
            logger.info("No missing mods found. Skipping...")

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
            missing_packageid_paths = self.window_manager.get_missing_packageid_paths()
            missing_publishfieldid_paths = (
                self.window_manager.get_missing_publishfieldid_paths()
            )

            # If no mods have missing properties, log and return early
            if not missing_packageid_paths and not missing_publishfieldid_paths:
                logger.info("No mods with missing properties found. Skipping...")
                return

            # Log summary statistics for debugging
            missing_packageid_count = len(missing_packageid_paths)
            missing_publishfieldid_count = len(missing_publishfieldid_paths)

            logger.info(
                f"Found {missing_packageid_count} mod(s) with missing Package ID and "
                f"{missing_publishfieldid_count} mod(s) with missing Publish Field ID. "
                f"Opening MissingModPropertiesPanel..."
            )

            # Display a unified panel showing all mods with missing properties,
            # grouped by property type for better user comprehension
            missing_mod_properties_panel = MissingModPropertiesPanel(
                missing_packageid_mods=missing_packageid_paths,
                missing_publishfieldid_mods=missing_publishfieldid_paths,
                metadata_controller=self.metadata_controller,
            )
            self.window_manager.register(missing_mod_properties_panel)
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
            render_unity_rt=self.settings.render_unity_rich_text,
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
        ) = self.metadata_controller.get_mods_from_list(
            mod_list=str(
                (
                    Path(
                        self.settings.instances[
                            self.settings.current_instance
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
        update_manager = UpdateManager(self.settings, self, self.mod_info_panel)
        update_manager.do_check_for_update()

    def __do_get_github_release_info(self) -> dict[str, Any]:
        # Parse latest release
        url = "https://api.github.com/repos/RimSort/RimSort/releases/latest"
        logger.debug(f"Requesting GitHub release info from: {url}")

        raw = http.get(url, timeout=10)

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
        # Store ref so closeEvent can break out of this loop
        self._active_loading_loop = loop
        loop.exec_()
        self._active_loading_loop = None
        # If the loop was quit externally (e.g. window close), skip UI cleanup
        if not loading_animation.animation_finished:
            return None
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
            self.mods_panel.reset_all_filters_and_search("Active")
            self.mods_panel.reset_all_filters_and_search("Inactive")
        # Check if paths are set
        if self.check_if_essential_paths_are_set(prompt=is_initial):
            # Run expensive calculations to set cache data
            self._refresh_in_progress = True
            result = self.do_threaded_loading_animation(
                gif_path=str(
                    AppInfo().theme_data_folder / "default-icons" / "rimsort.gif"
                ),
                target=partial(
                    self.metadata_controller.refresh_metadata,
                ),
                text=self.tr("Scanning mod sources and populating metadata..."),
            )
            self._refresh_in_progress = False

            # If loading was aborted (e.g. window closed during scan), skip remaining work
            if result is None and self.metadata_controller.is_abort_requested:
                return

            # Insert mod data into list
            self.__repopulate_lists(is_initial=is_initial)
            self.mods_panel.refresh_all_tag_filter_selectors()

            # check if we have duplicate mods, prompt user
            self.__duplicate_mods_prompt()

            # check if we have missing mods, prompt user
            self.__missing_mods_prompt()

            # Check if we have mods with missing properties (Package ID and/or Publish Field ID)
            self.__check_and_warn_missing_mod_properties()

            # Check Workshop mods for updates if configured
            if self.settings.steam_mods_update_check:
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
            if (
                self._settings_dialog is not None
                and not self._settings_dialog.isHidden()
            ):
                loop = QEventLoop()
                self._settings_dialog.finished.connect(loop.quit)
                loop.exec_()
                logger.debug("Settings dialog closed. Continuing with refresh...")

        EventBus().refresh_finished.emit()

    def _do_clear(self) -> None:
        """
        Method to clear all the non-base, non-DLC mods from the active
        list widget and put them all into the inactive list widget.
        """
        self.mods_panel.reset_all_filters_and_search("Active")
        self.mods_panel.reset_all_filters_and_search("Inactive")
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
        if self.settings.clear_moves_dlc and package_id_order:
            package_ids_to_keep_active = [package_id_order[0]]  # Base game only
        else:
            package_ids_to_keep_active = package_id_order
        # Create a set of all package IDs from mod_data
        package_ids_set = set(
            str(mod_data.package_id)
            for mod_data in self.metadata_controller.mods_metadata.values()
            if isinstance(mod_data, AboutXmlMod)
        )
        # Iterate over the package IDs we want to keep active
        for package_id in package_ids_to_keep_active:
            if package_id in package_ids_set:
                # Append the UUIDs to active_mods_uuids if the package ID exists in mod_data
                active_mods_uuids.extend(
                    uuid
                    for uuid, mod_data in self.metadata_controller.mods_metadata.items()
                    if isinstance(mod_data, AboutXmlMod)
                    and mod_data.mod_type == ModType.LUDEON
                    and str(mod_data.package_id) == package_id
                )
        # Append the remaining UUIDs to inactive_mods_uuids
        inactive_mods_uuids.extend(
            uuid
            for uuid in self.metadata_controller.mods_metadata.keys()
            if uuid not in active_mods_uuids
        )
        # Clear dividers on list clear
        self.settings.active_mods_dividers = []
        self.settings.save()
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
        self.mods_panel.reset_all_filters_and_search("Active")
        self.mods_panel.reset_all_filters_and_search("Inactive")

        # Get active mods (exclude dividers)
        active_mods = {
            u for u in self.mods_panel.active_mods_list.paths if not is_divider_uuid(u)
        }

        # Compile metadata for active mods so newly-added ones have dependency info
        self.metadata_controller.compile()

        # Check for missing dependencies if enabled in settings and check_deps is True
        if check_deps and self.settings.check_dependencies_on_sort:
            missing_deps = self.metadata_controller.get_missing_dependencies(
                active_mods
            )
            if missing_deps:
                dialog = MissingDependenciesDialog(
                    metadata_controller=self.metadata_controller
                )
                self.window_manager.register(dialog)

                # Build a deps_summary from the missing deps for the dialog display
                deps_summary: dict[str, dict[str, set[str]]] = {}
                for mod_id, deps in missing_deps.items():
                    deps_summary[mod_id] = {
                        "satisfied": set(),
                        "local": set(),
                        "download": deps,
                    }

                selected_deps = dialog.show_dialog(deps_summary, missing_deps)

                if selected_deps:
                    # Add selected mods to active mods
                    for mod_id in selected_deps:
                        # Find the UUID for this package ID
                        for (
                            uuid,
                            mod_data,
                        ) in self.metadata_controller.mods_metadata.items():
                            if (
                                isinstance(mod_data, AboutXmlMod)
                                and str(mod_data.package_id) == mod_id
                            ):
                                if uuid not in active_mods:
                                    active_mods.add(uuid)
                                break

        # Compile dependency data from MetadataController
        try:
            compiled_data = self.metadata_controller.compile(
                use_moddependencies_as_loadTheseBefore=self.settings.use_moddependencies_as_loadTheseBefore,
                use_alternative_package_ids=self.settings.use_alternative_package_ids_as_satisfying_dependencies,
            )
        except ValueError:
            dialogue.show_warning(
                title=self.tr("Metadata not loaded"),
                text=self.tr(
                    "Mod metadata has not finished loading. Please wait and try again."
                ),
            )
            return

        # Bridge: translate old UUIDs to paths for the new sort system
        active_mod_paths: set[str] = set()
        for uuid in active_mods:
            mod_entry = self.metadata_controller.mods_metadata.get(uuid)
            if mod_entry and mod_entry.mod_path:
                active_mod_paths.add(str(mod_entry.mod_path))

        # Get the current order of active mods list and create a copy for comparison
        current_order = active_mods
        try:
            sorter = Sorter(
                self.settings.sorting_algorithm,
                compiled_data=compiled_data,
                mods_metadata=self.metadata_controller.mods_metadata,
                active_mod_paths=active_mod_paths,
            )
        except NotImplementedError as e:
            dialogue.show_warning(
                title=self.tr("Sorting algorithm not implemented"),
                text=self.tr("The selected sorting algorithm is not implemented"),
                information=(
                    self.tr(
                        "This may be caused by malformed settings or improper migration between versions or different mod manager.<br><br>"
                        "Try resetting your settings, selecting a different sorting algorithm, or "
                        "deleting your settings file.<br><br>"
                        "If the issue persists, please report it to the developers."
                    )
                ),
                details=str(e),
            )
            logger.error(f"Sort failed. Sorting algorithm not implemented: {e}")
            return

        success, new_order_paths = sorter.sort()

        # Bridge: translate paths back to UUIDs for the list widget
        path_to_uuid: dict[str, str] = {}
        for uuid, mod_data in self.metadata_controller.mods_metadata.items():
            if mod_data.mod_path:
                path_to_uuid[str(mod_data.mod_path)] = uuid
        new_order = [path_to_uuid[p] for p in new_order_paths if p in path_to_uuid]

        # Log the sort result and the order
        logger.debug(
            f"Sort result: {success}, new order: {new_order}, current order: {current_order}"
        )
        # Check if successful and orders differ
        if success and new_order != current_order:
            logger.info(
                "Finished combining all tiers of mods. Inserting into mod lists!"
            )
            # Move all dividers to the bottom after sort so the user
            # can reposition them.  Reset collapsed state so they are visible.
            saved_dividers = self.mods_panel.active_mods_list.get_dividers_data()
            bottom = len(new_order)
            for i, div in enumerate(saved_dividers):
                div["index"] = bottom + i
                div["collapsed"] = False
            self.settings.active_mods_dividers = saved_dividers
            self.settings.save()
            # Disable widgets while inserting
            self.disable_enable_widgets_signal.emit(False)
            # Insert data into lists
            self._insert_data_into_lists(
                new_order,
                [
                    uuid
                    for uuid in self.metadata_controller.mods_metadata
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
            self.mods_panel.reset_all_filters_and_search("Active")
            self.mods_panel.reset_all_filters_and_search("Inactive")
            logger.info(f"Trying to import mods list from XML: {file_path}")
            (
                active_mods_uuids,
                inactive_mods_uuids,
                self.duplicate_mods,
                self.missing_mods,
            ) = self.metadata_controller.get_mods_from_list(mod_list=file_path)
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
            data = self._import_export_service.collect_active_mods(
                self.mods_panel.active_mods_list.paths, self.duplicate_mods
            )
            try:
                self._import_export_service.export_to_xml(data.active_mods, file_path)
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
        rentry_import = RentryImport(self.settings)
        # Exit if user cancels or no package IDs
        if not rentry_import.package_ids:
            logger.debug("USER ACTION: pressed cancel or no package IDs, passing")
            return
        # Clear Active and Inactive search and data source filter
        self.mods_panel.reset_all_filters_and_search("Active")
        self.mods_panel.reset_all_filters_and_search("Inactive")

        if rentry_import.publishedfileids:
            # Get set of publishedfileids already present locally
            existing_publishedfileids = {
                mod_data.published_file_id
                for mod_data in self.metadata_controller.mods_metadata.values()
                if mod_data.published_file_id is not None
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
                        "You will need to redo Rentry import again after downloads complete.<br><br>"
                        "If there missing mods after download completes, they will be shown inside the missing mods panel.<br><br>"
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
                current_instance = self.settings.current_instance
                steam_client_integration = self.settings.instances[
                    current_instance
                ].steam_client_integration

                if steam_client_integration:
                    logger.info("Using Steamworks API to download mods")
                    self._do_steamworks_api_call_animated(
                        [
                            "subscribe",
                            [
                                str(int(str_pfid))
                                for str_pfid in filtered_publishedfileids
                            ],
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
        ) = self.metadata_controller.get_mods_from_list(
            mod_list=rentry_import.package_ids
        )

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
        collection_import = CollectionImport(
            metadata_controller=self.metadata_controller
        )
        # Exit if user cancels or no package IDs
        if not collection_import.package_ids:
            logger.debug("USER ACTION: pressed cancel or no package IDs, passing")
            return
        # Clear Active and Inactive search and data source filter
        self.mods_panel.reset_all_filters_and_search("Active")
        self.mods_panel.reset_all_filters_and_search("Inactive")

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
        ) = self.metadata_controller.get_mods_from_list(
            mod_list=collection_import.package_ids
        )

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
        data = self._import_export_service.collect_active_mods(
            self.mods_panel.active_mods_list.paths, self.duplicate_mods
        )
        report = self._import_export_service.build_clipboard_report(
            data.active_mods, data.packageid_to_uuid
        )
        dialogue.show_information(
            title=self.tr("Export active mod list"),
            text=self.tr("Copied active mod list report to clipboard..."),
            information=self.tr('Click "Show Details" to see the full report!'),
            details=report,
        )
        copy_to_clipboard_safely(report)

    def _do_upload_list_rentry(self) -> None:
        """
        Export the current list of active mods to the clipboard in a
        readable format. The current list does not need to have been saved.
        """

        data = self._import_export_service.collect_active_mods(
            self.mods_panel.active_mods_list.paths, self.duplicate_mods
        )
        data.pfid_to_preview_url = self._import_export_service.fetch_steam_preview_urls(
            data.pfids
        )
        report = self._import_export_service.build_rentry_report(
            data.active_mods,
            data.packageid_to_uuid,
            data.steam_packageid_to_pfid,
            data.pfid_to_preview_url,
        )
        # Check report length and offer truncation if necessary
        if len(report) > 200000:
            max_mods = self._import_export_service.calculate_rentry_max_mods(
                data.active_mods,
                data.packageid_to_uuid,
                data.steam_packageid_to_pfid,
                data.pfid_to_preview_url,
            )
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
                truncated_mods = data.active_mods[:max_mods]
                report = self._import_export_service.build_rentry_report(
                    truncated_mods,
                    data.packageid_to_uuid,
                    data.steam_packageid_to_pfid,
                    data.pfid_to_preview_url,
                    truncated=True,
                )
            else:
                logger.info("USER ACTION: cancelled truncation, passing")
                return
        # Upload the report to Rentry.co
        success, url = self._import_export_service.upload_rentry_report(report)
        if success and url:
            copy_to_clipboard_safely(url)
            dialogue.show_information(
                title=self.tr("Uploaded active mod list"),
                text=self.tr(
                    "Uploaded active mod list report to Rentry.co! The URL has been copied to your clipboard:<br><br>{url}"
                ).format(url=url),
                information=self.tr('Click "Show Details" to see the full report!'),
                details=report,
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
                self.settings.instances[self.settings.current_instance].config_folder
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
        self.mods_panel.reset_all_filters_and_search("Active")
        self.mods_panel.reset_all_filters_and_search("Inactive")

        logger.info(f"Trying to import mods list from save file: {file_path}")
        (
            active_mods_uuids,
            inactive_mods_uuids,
            self.duplicate_mods,
            self.missing_mods,
        ) = self.metadata_controller.get_mods_from_list(mod_list=file_path)
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
        current_instance = self.settings.current_instance
        directory = getattr(
            self.settings.instances[current_instance],
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
        if download_text in answer_str and self._show_settings_dialog is not None:
            self._show_settings_dialog()

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
                    "The URL has been copied to your clipboard:<br><br>{ret}"
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
                self.settings.text_editor_location,
                self.settings.text_editor_folder_arg.split(" ") + [str(path)],
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
        # Persist divider data before saving
        self.settings.active_mods_dividers = (
            self.mods_panel.active_mods_list.get_dividers_data()
        )
        self.settings.save()

        data = self._import_export_service.collect_active_mods(
            self.mods_panel.active_mods_list.paths, self.duplicate_mods
        )
        active_mods_uuids, inactive_mods_uuids, _, _ = (
            self.metadata_controller.get_mods_from_list(mod_list=data.active_mods)
        )
        self.active_mods_uuids_last_save = active_mods_uuids
        logger.info(f"Collected {len(data.active_mods)} active mods for saving")

        try:
            self._import_export_service.save_to_mods_config(data.active_mods)
        except Exception:
            logger.error("Could not save active mods")
            dialogue.show_fatal_error(
                title=self.tr("Could not save active mods"),
                text=self.tr("Failed to save active mods to file:"),
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
            self.mods_panel.reset_all_filters_and_search("Active")
            self.mods_panel.reset_all_filters_and_search("Inactive")
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
    def _create_todds_runner(self, is_pre_launch: bool) -> RunnerPanel:
        runner = RunnerPanel(
            todds_dry_run_support=self.settings.todds_dry_run,
            auto_close_on_complete=is_pre_launch,
        )

        base_title = "RimSort - todds texture encoder"
        suffix = " (pre-launch)" if is_pre_launch else ""
        runner.setWindowTitle(f"{base_title}{suffix}")

        if not is_pre_launch:
            self.todds_runner = runner
            self.window_manager.register_attr(self, "todds_runner")

        runner.show()
        return runner

    @overload
    def _do_optimize_textures(
        self, block_until_complete: Literal[True]
    ) -> tuple[bool, int]: ...

    @overload
    def _do_optimize_textures(self) -> None: ...

    def _do_optimize_textures(
        self, block_until_complete: bool = False
    ) -> tuple[bool, int] | None:
        logger.info("Optimizing textures with todds...")
        todds_runner = self._create_todds_runner(block_until_complete)
        active_uuids = list(self.mods_panel.active_mods_list.paths)

        started = self.todds_controller.optimize_textures(
            runner=todds_runner,
            active_mod_paths=active_uuids,
        )

        if not started:
            todds_runner.close()
            self._show_todds_no_paths_warning()
            return (False, -1) if block_until_complete else None

        if block_until_complete:
            loop = QEventLoop()
            todds_runner.process.finished.connect(loop.quit)
            loop.exec_()
            exit_code = todds_runner.process.exitCode()
            success = exit_code == 0
            if success:
                logger.info("todds process completed successfully")
            else:
                logger.warning(f"todds process failed with exit code: {exit_code}")
            return success, exit_code

        return None

    def _do_delete_dds_textures(self) -> None:
        answer = dialogue.show_dialogue_conditional(
            title=self.tr("Confirm texture deletion"),
            text=self.tr(
                "This will delete all optimized .dds textures from your active mods"
            ),
            information=self.tr(
                "Are you sure you want to delete all .dds textures? "
                "You can re-optimize them later if needed."
            ),
            button_text_override=[
                self.tr("Delete textures"),
            ],
        )
        if self.tr("Delete textures") not in str(answer):
            return

        logger.info("Deleting .dds textures with todds...")
        todds_runner = self._create_todds_runner(is_pre_launch=False)
        active_uuids = list(self.mods_panel.active_mods_list.paths)

        started = self.todds_controller.delete_dds_textures(
            runner=todds_runner,
            active_mod_paths=active_uuids,
        )

        if not started:
            todds_runner.close()
            self._show_todds_no_paths_warning()

    def _show_todds_no_paths_warning(self) -> None:
        dialogue.show_warning(
            title=self.tr("No valid paths for todds"),
            text=self.tr("todds could not find any valid mod folders to process."),
            information=self.tr(
                "None of the configured mod folder paths exist on disk.<br><br>"
                "Please verify your Local Mods and Workshop folders are correctly "
                "set in Settings, then try again."
            ),
        )

    # STEAM{CMD, WORKS} ACTIONS
    def _do_import_steamcmd_acf_data(self) -> None:
        """
        Import an ACF file to replace the current SteamCMD ACF data.

        Shows confirmation dialog and imports the file if user confirms.
        """
        answer = dialogue.show_dialogue_conditional(
            title=self.tr("Confirm ACF import"),
            text=self.tr("This will replace your current steamcmd .acf file"),
            information=self.tr(
                "Are you sure you want to import .acf? This only works for steamcmd"
            ),
            button_text_override=[
                self.tr("Import .acf"),
            ],
        )
        # Import .acf if user confirms
        answer_str = str(answer)
        import_text = self.tr("Import .acf")
        if import_text in answer_str:
            logger.debug("User confirmed ACF import")
            logger.info("Importing SteamCMD ACF data...")
            import_steamcmd_acf_data(
                rimsort_storage_path=str(AppInfo().app_storage_folder),
                steamcmd_appworkshop_acf_path=self.steamcmd_wrapper.steamcmd_appworkshop_acf_path,
            )

    def _do_export_steamcmd_acf_data(self) -> None:
        """
        Export the raw ACF file to a user-defined location by copying the file.

        Shows file save dialog and status messages with error handling for file not found
        or permission errors.
        """
        # Get SteamCMD ACF path from steamcmd_wrapper
        steamcmd_acf_path = Path(self.steamcmd_wrapper.steamcmd_appworkshop_acf_path)

        if not steamcmd_acf_path or not steamcmd_acf_path.is_file():
            acf_path_str = str(steamcmd_acf_path) if steamcmd_acf_path else "None"
            logger.error(f"Export failed: ACF file not found: {acf_path_str}")
            dialogue.show_warning(
                title=self.tr("Export Error"),
                text=self.tr("ACF file not found at: {acf_path}").format(
                    acf_path=acf_path_str
                ),
            )
            return

        file_path = dialogue.show_dialogue_file(
            mode="save",
            caption="Export ACF File",
            _dir="appworkshop_294100.acf",
            _filter="ACF Files (*.acf);;All Files (*)",
        )
        if not file_path:
            logger.debug("User canceled export ACF")
            return

        try:
            shutil.copy(str(steamcmd_acf_path), file_path)
            logger.debug(f"Successfully exported ACF to {file_path}")
            dialogue.show_information(
                title=self.tr("Export Success"),
                text=self.tr("Successfully exported ACF to {file_path}").format(
                    file_path=file_path
                ),
            )
        except PermissionError:
            error_msg = self.tr(
                "Export failed: Permission denied - check file permissions"
            )
            logger.error(f"Export failed due to Permission: {error_msg}")
            dialogue.show_warning(title=self.tr("Export Error"), text=error_msg)
        except Exception as e:
            error_msg = self.tr("Export failed: {e}").format(e=str(e))
            logger.error(f"Export failed: {error_msg}")
            dialogue.show_warning(title=self.tr("Export Error"), text=error_msg)

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
        # Clean up previous instance if it still exists
        if self.steam_browser:
            self.steam_browser.close()
            self.steam_browser.deleteLater()

        self.steam_browser = SteamBrowser(
            "https://steamcommunity.com/app/294100/workshop/",
            self.metadata_controller,
            self.settings,
        )
        self.window_manager.register_attr(self, "steam_browser")

        # Automatically null the reference when browser is destroyed
        self.steam_browser.destroyed.connect(
            lambda: setattr(self, "steam_browser", None)
        )
        self.steam_browser.show()

    def _do_check_for_workshop_updates(self) -> None:
        if not check_internet_connection():
            return
        result: WorkshopUpdateResult = self.do_threaded_loading_animation(
            gif_path=str(
                AppInfo().theme_data_folder / "default-icons" / "steam_api.gif"
            ),
            target=partial(
                query_workshop_update_data,
                mods=self.metadata_controller.mods_metadata,
                metadata_controller=self.metadata_controller,
            ),
            text=self.tr("Checking Steam Workshop mods for updates..."),
        )

        if result.status == "no_workshop_mods":
            self.status_signal.emit(self.tr("No Workshop mods to check for updates"))
            return

        if result.status == "failed":
            dialogue.show_warning(
                title=self.tr("Unable to check for updates"),
                text=self.tr(
                    "RimSort was unable to check your Workshop mods for updates."
                ),
                details="<br>".join(result.errors) if result.errors else None,
            )
            return

        if result.status == "partial":
            dialogue.show_warning(
                title=self.tr("Update check partially completed"),
                text=self.tr(
                    "{failed} out of {total} Workshop mods could not be checked for updates."
                ).format(
                    failed=len(result.failed_pfids),
                    total=result.mods_checked,
                ),
                details="<br>".join(result.errors) if result.errors else None,
            )

        # For both "success" and "partial", show the updater panel
        workshop_mod_updater = WorkshopModUpdaterPanel(
            metadata_controller=self.metadata_controller
        )
        self.window_manager.register(workshop_mod_updater)
        if workshop_mod_updater._row_count() > 0:
            logger.debug("Displaying potential Workshop mod updates")
            workshop_mod_updater.show()
        else:
            self.status_signal.emit(
                self.tr("All Workshop mods appear to be up to date!")
            )

    def do_steam_verify_game_files(self) -> None:
        """Verify RimWorld game files through Steam."""
        # Retrieve settings for the current RimWorld instance
        steam_client_integration_enabled = self.settings.instances[
            self.settings.current_instance
        ].steam_client_integration

        # Check if Steam Client Integration is enabled
        if not steam_client_integration_enabled:
            # Inform user that feature requires Steam Client Integration
            logger.warning(
                "Steam Client Integration is disabled. Cannot verify game files."
            )
            dialogue.show_warning(
                title=self.tr("Steam Client Integration is disabled"),
                text=self.tr(
                    "This feature requires Steam Client Integration to be enabled in Settings.<br><br>"
                    "Please enable Steam Client Integration if you own the game on Steam."
                ),
            )
            return

        # Validate internet connectivity before proceeding
        if not check_internet_connection():
            return

        logger.info("Verifying game files through Steam.")
        logger.info("Steam Client Integration enabled. Opening Steam URI protocol.")
        # Open Steam's game file verification dialog using URI protocol
        # RimWorld's Steam app ID is 294100
        platform_specific_open("steam://validate/294100")

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
        local_mods_path = self.settings.instances[
            self.settings.current_instance
        ].local_folder
        if local_mods_path and os.path.exists(local_mods_path):
            self.steamcmd_runner = RunnerPanel()
            self.window_manager.register_attr(self, "steamcmd_runner")
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
        steam_db_schema = self.metadata_controller.steam_db
        steam_db = steam_db_schema.database if steam_db_schema else {}
        if steam_db:
            publishedfileids = check_if_pfids_blacklisted(
                publishedfileids=publishedfileids,
                steamdb=steam_db,
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

            self.steamcmd_runner = RunnerPanel(
                steamcmd_download_tracking=publishedfileids,
                steam_db=steam_db,
            )
            self.window_manager.register_attr(self, "steamcmd_runner")
            self.steamcmd_runner.setWindowTitle("RimSort - SteamCMD downloader")
            self.steamcmd_runner.show()
            self.steamcmd_runner.message(
                f"Downloading {len(publishedfileids)} mods with SteamCMD..."
            )
            self.steamcmd_wrapper.download_mods(
                publishedfileids=publishedfileids,
                runner=self.steamcmd_runner,
                clear_cache=self.settings.instances[
                    self.settings.current_instance
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

    def _handle_steamworks_resubscribe(self, instruction: list[Any]) -> None:
        """
        Handle mod revalidation by forcing Steam to validate and redownload mods.

        This bypasses the Steamworks API because the native resubscribe process is broken.
        Instead, we use the Steam URI protocol to trigger validation directly.
        This approach is more efficient than the Steamworks API implementation, which
        would unsubscribe then subscribe again.

        :param instruction: List where instruction[0] = "resubscribe" and
                           instruction[1] = list of PublishedFileIds (int)
        """
        logger.info(f"Validating mods with instruction: {instruction}")
        # Steam URI protocol: steam://validate/{APP_ID}/{PublishedFileIds}
        # APP_ID 294100 is RimWorld
        platform_specific_open(f"steam://validate/294100/{instruction[1]}")

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
        # use prebuilt libs path
        libs_path = str(AppInfo().libs_folder)
        if not self.steamworks_in_use:
            if not check_steam_available(_libs=libs_path):
                logger.error("Steam is not available, skipping Steamworks API call")
                return
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
                        run_args=instruction[1][1],
                        _libs=libs_path,
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
                    # Process all mods in a single handler to ensure proper sequencing and avoid parallel processing issues
                    logger.debug(
                        f"Processing {instruction[0]} sequentially for {len(instruction[1])} mod(s)"
                    )
                    handler = SteamworksSubscriptionHandler(
                        action=instruction[0],
                        pfid_or_pfids=instruction[1],
                        _libs=libs_path,
                    )
                    handler.start()
                    handler.join()
                    # Clean up after processing
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
        steam_db_schema = self.metadata_controller.steam_db
        steamdb = steam_db_schema.database if steam_db_schema else {}
        # Check for blacklisted mods for subscription actions
        if instruction[0] == "subscribe":
            assert isinstance(publishedfileids, list)
            publishedfileids = check_if_pfids_blacklisted(
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
                    response = http.get(url, stream=True, timeout=30)
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
                        information=self.tr("File: {file_path}<br>Error: {e}").format(
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
            self.settings.instances[self.settings.current_instance].local_folder
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
                information=self.tr("File: {file_path}<br>Error: {e}").format(
                    file_path=file_path, e=e
                ),
            )
        except (BadZipFile, ValueError, PermissionError, OSError) as e:
            logger.error(f"Failed to extract zip file: {e}")
            dialogue.show_warning(
                title=self.tr("Failed to extract zip file"),
                text=self.tr("The zip file could not be extracted."),
                information=self.tr("File: {file_path}<br>Error: {e}").format(
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
                    "How would you like to proceed?<br><br>"
                    "1) Overwrite All — Replace all existing files and directories.<br>"
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
                    "{conflicts_list}<br><br>"
                    "How would you like to proceed?<br><br>"
                    "1) Overwrite All — Replace all existing files and directories.<br>"
                    "2) Skip Existing — Extract only new files and leave existing ones untouched.<br>"
                    "3) Cancel — Abort the extraction."
                ).format(
                    conflicts_list="<br/>".join(conflicts[:5])
                    + ("<br/>...<br/>" if len(conflicts) > 5 else "")
                ),
                button_text_override=["Overwrite All", "Skip Existing"],
            )
            if answer == QMessageBox.StandardButton.Cancel:
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
                    "Git integration will not work without Git installed! Do you want to open download page for Git?<br><br>"
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
            metadata_controller=self.metadata_controller,
            compact=compact,
            edit_packageid=packageid,
            initial_mode=initial_mode,
        )
        self.window_manager.register_attr(self, "rule_editor")
        self.rule_editor._populate_from_metadata()
        self.rule_editor.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.rule_editor.update_database_signal.connect(self._do_update_rules_database)
        self.rule_editor.show()

    def _do_open_ignore_json_editor(self) -> None:
        """Open the Ignore JSON Editor dialog."""
        self.ignore_json_editor = IgnoreJsonEditor()
        self.window_manager.register_attr(self, "ignore_json_editor")
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
            self.settings.external_steam_metadata_file_path = input_path
            self.settings.save()
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
            self.settings.external_community_rules_file_path = input_path
            self.settings.save()
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
            text=self.settings.external_steam_metadata_repo,
        )
        if ok:
            self.settings.external_steam_metadata_repo = args
            self.settings.save()

    def _do_configure_community_rules_db_repo(self) -> None:
        """
        Opens a QDialogInput that allows user to edit their Community Rules
        DB repo. This URL is used for Steam DB repo related actions.
        """
        args, ok = QInputDialog.getText(
            None,
            self.tr("Edit Community Rules DB repo"),
            self.tr("Enter URL (https://github.com/AccountName/RepositoryName):"),
            text=self.settings.external_community_rules_repo,
        )
        if ok:
            self.settings.external_community_rules_repo = args
            self.settings.save()

    def _do_blacklist_action_steamdb(self, instruction: list[Any]) -> None:
        logger.info(f"Updating SteamDB blacklist status for item: {instruction}")
        # Retrieve instruction passed from signal
        publishedfileid = instruction[0]
        blacklist = instruction[1]
        comment = instruction[2] if blacklist else ""
        # Delegate to MetadataController
        success = self.metadata_controller.set_steam_db_blacklist(
            published_file_id=publishedfileid,
            blacklisted=blacklist,
            comment=comment or "",
        )
        if success:
            # Do a full refresh of metadata and UI
            self._do_refresh()
        else:
            logger.warning(
                "Could not update SteamDB blacklist: no Steam database loaded"
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
            text=self.settings.steam_apikey,
        )
        if ok:
            self.settings.steam_apikey = args
            self.settings.save()

    def _do_update_rules_database(self, instruction: list[Any]) -> None:
        rules_source = instruction[0]
        rules_data = instruction[1]
        # Get path based on rules source
        cr_path = self.metadata_controller.community_rules_path
        if rules_source == "Community Rules" and cr_path:
            path = str(cr_path)
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
        recursively_update_dict(
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
                "This operation will overwrite the {rules_source} database located at the following path:<br><br>{path}"
            ).format(rules_source=rules_source, path=path),
        )
        if answer == QMessageBox.StandardButton.Yes:
            atomic_json_dump(db_output_c, path, indent=4)
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
            text=str(self.settings.database_expiry),
        )
        if ok:
            try:
                self.settings.database_expiry = int(args)
                self.settings.save()
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
        instance = self.settings.instances.get(self.settings.current_instance)
        if not instance:
            logger.warning(
                f"Tried to access instance {self.settings.current_instance} that does not exist!"
            )
            return None

        steamcmd_prefix = instance.steamcmd_install_path

        if steamcmd_prefix:
            self.steamcmd_wrapper.initialize_prefix(
                steamcmd_prefix=str(steamcmd_prefix),
                validate=self.settings.steamcmd_validate_downloads,
            )
        self.steamcmd_wrapper.validate_downloads = (
            self.settings.steamcmd_validate_downloads
        )

    @Slot()
    def _do_run_game(self) -> None:
        """
        Prepare and launch the RimWorld game process.

        This method handles the complete game launch workflow:
        1. Validates essential paths are configured
        2. Creates backup of settings and mod list
        3. Prompts user about unsaved mod list changes
        4. Optionally runs todds texture optimization
        5. Manages steam_appid.txt for Steam integration
        6. Launches game via Steam protocol (with overlay) or direct executable

        The launch method depends on user configuration:
        - If "launch_via_steam_protocol" is enabled: uses steam://rungameid/294100 URI
          (requires Steam Client Integration enabled, ignores custom run arguments)
        - Otherwise: launches executable directly with custom run arguments

        Note: Steam_appid.txt is created/removed based on steam_client_integration setting
        regardless of launch method, for compatibility.
        """
        if not self.check_if_essential_paths_are_set(prompt=True):
            return

        create_backup_in_thread(self.settings)

        # Check for unsaved mod list changes and prompt user
        current_mod_uuids = [
            u for u in self.mods_panel.active_mods_list.paths if not is_divider_uuid(u)
        ]
        if current_mod_uuids != self.active_mods_uuids_last_save:
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

        # Run todds before launch if auto-run is enabled
        if self.settings.auto_run_todds_before_launch:
            success, exit_code = self._do_optimize_textures(block_until_complete=True)

            # Show error message if todds failed, but continue to launch game
            if not success:
                dialogue.show_warning(
                    title=self.tr("todds Optimization Failed"),
                    text=self.tr(
                        "todds texture optimization failed (exit code: {exit_code}), but the game will launch anyway."
                    ).format(exit_code=exit_code),
                    information=self.tr(
                        "You may experience longer loading times or higher memory usage.<br><br>"
                        "Check the todds output window for details."
                    ),
                )

        # Retrieve instance configuration
        current_instance = self.settings.current_instance
        game_install_path = Path(self.settings.instances[current_instance].game_folder)
        run_args = self.settings.instances[current_instance].run_args

        # Retrieve Steam-related settings for this instance
        steam_client_integration = self.settings.instances[
            current_instance
        ].steam_client_integration

        launch_via_steam_protocol = self.settings.instances[
            current_instance
        ].launch_via_steam_protocol

        # Manage steam_appid.txt file for Steam integration
        # If Steam integration is enabled, Steam requires this file with the app ID in the game folder
        # The Steam App ID is "294100" for RimWorld.
        steam_appid_path = (
            # On macOS, steam_appid.txt should be outside the app bundle
            game_install_path.parent / "steam_appid.txt"
            if sys.platform == "darwin"
            # On Windows and Linux, place it directly in the game folder
            else game_install_path / "steam_appid.txt"
        )
        if steam_client_integration and not steam_appid_path.exists():
            with open(steam_appid_path, "w", encoding="utf-8") as f:
                f.write("294100")
        elif not steam_client_integration and steam_appid_path.exists():
            steam_appid_path.unlink()

        # Launch the game using the configured method
        if launch_via_steam_protocol:
            # Validate Steam Client Integration is enabled before using Steam protocol
            if not steam_client_integration:
                logger.warning(
                    "Steam protocol launch requested but Steam Client Integration is disabled."
                )
                dialogue.show_warning(
                    title=self.tr("Steam Client Integration is disabled"),
                    text=self.tr(
                        "Steam protocol launch requires Steam Client Integration to be enabled."
                    ),
                    information=self.tr(
                        "Please enable Steam Client Integration in Settings → Steam to use this feature."
                    ),
                )
                return

            # Launch via Steam protocol URI
            # This allows Steam to manage the game launch and enables the Steam overlay
            # Custom run arguments are ignored when using this method
            logger.info(
                "Launching game via Steam protocol URI (steam://rungameid/294100)..."
            )
            platform_specific_open("steam://rungameid/294100")
        else:
            # Launch game executable directly
            # This method ignores Steam overlay but respects custom run arguments
            logger.info("Launching game process without Steamworks API...")
            launch_game_process(game_install_path=game_install_path, run_args=run_args)

    @Slot()
    def _use_this_instead_clicked(self) -> None:
        """
        When clicked, opens the Use This Instead panel.
        """
        if self.settings.external_use_this_instead_metadata_source == "None":
            dialogue.show_warning(
                title=self.tr("Use This Instead"),
                text=self.tr(
                    'Please configure "Use This Instead" database in settings.'
                ),
            )
            return

        self.use_this_instead_dialog = UseThisInsteadPanel(
            mod_metadata=self.metadata_controller.mods_metadata,
            metadata_controller=self.metadata_controller,
        )
        self.window_manager.register_attr(self, "use_this_instead_dialog")
        if not self.use_this_instead_dialog.show_if_has_alternatives():
            dialogue.show_information(
                title=self.tr("Use This Instead"),
                text=self.tr(
                    'No suggestions were found in the "Use This Instead" database.'
                ),
            )
