from functools import partial
from gc import collect
from pathlib import Path
import platform
from typing import Callable
import subprocess
import sys
import datetime
from io import BytesIO
from math import ceil
from multiprocessing import cpu_count, current_process, Pool
from stat import S_IEXEC
from shutil import copytree
from tempfile import gettempdir
from time import time
from zipfile import ZipFile

from logger_tt import logger

# GitPython depends on git executable being available in PATH
try:
    from git import Repo
    from git.exc import GitCommandError

    GIT_EXISTS = True
except ImportError:
    logger.warning(
        "git not detected in your PATH! Do you have git installed...? git integration will be disabled!"
    )
    GIT_EXISTS = False

from github import Github

from pyperclip import copy as copy_to_clipboard
from requests import get as requests_get

from model.dialogue import (
    show_dialogue_conditional,
    show_dialogue_file,
    show_dialogue_input,
)
from model.animations import LoadingAnimation

from util.constants import RIMWORLD_DLC_METADATA
from util.generic import (
    chunks,
    delete_files_except_extension,
    handle_remove_read_only,
    open_url_browser,
    platform_specific_open,
    upload_data_to_0x0_st,
)
from util.rentry.wrapper import RentryUpload
from util.steam.browser import SteamBrowser
from util.steam.webapi.wrapper import ISteamRemoteStorage_GetPublishedFileDetails

from PySide6.QtCore import QEventLoop, QObject, QProcess, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QToolButton,
)

from sort.dependencies import *
from sort.alphabetical_sort import *
from sort.topo_sort import *
from sub_view.actions_panel import Actions
from sub_view.active_mods_panel import ActiveModList
from sub_view.inactive_mods_panel import InactiveModList
from sub_view.mod_info_panel import ModInfo
from util.constants import DEFAULT_USER_RULES
from util.generic import launch_game_process
from util.metadata import *
from util.schema import validate_mods_config_format
from util.steam.steamcmd.wrapper import SteamcmdInterface
from util.steam.steamworks.wrapper import (
    SteamworksGameLaunch,
    SteamworksSubscriptionHandler,
)
from util.todds.wrapper import ToddsInterface
from util.xml import json_to_xml_write, xml_path_to_json
from view.game_configuration_panel import GameConfiguration
from window.missing_mods_panel import MissingModsPrompt
from window.rule_editor_panel import RuleEditor
from window.runner_panel import RunnerPanel
from window.workshop_mod_updater_panel import ModUpdaterPrompt


class MainContent(QObject):
    """
    This class controls the layout and functionality of the main content
    panel of the GUI, containing the mod information display, inactive and
    active mod lists, and the action button panel. Additionally, it acts
    as the main temporary datastore of the app, caching workshop mod information
    and their dependencies.
    """

    _instance: Optional["MainContent"] = None

    status_signal = Signal(str)
    stop_watchdog_signal = Signal()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MainContent, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """
        Initialize the main content panel.

        :param game_configuration: game configuration panel to get paths
        """
        if not hasattr(self, "initialized"):
            super(MainContent, self).__init__()
            logger.debug("Initializing MainContent")

            # INITIALIZE WIDGETS
            # Initialize Steam(CMD) integraations
            self.steam_browser = SteamcmdDownloader = None
            self.steamcmd_runner = RunnerPanel = None
            self.steamcmd_wrapper = SteamcmdInterface.instance(
                GameConfiguration.instance().steamcmd_install_path,
                GameConfiguration.instance().steamcmd_validate_downloads_toggle,
            )

            # Initialize MetadataManager
            self.metadata_manager = MetadataManager.instance()
            self.metadata_manager.update_game_configuration_signal.connect(
                self.__update_game_configuration
            )

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
            self.active_mods_panel = ActiveModList(
                mod_type_filter_enable=GameConfiguration.instance().mod_type_filter_toggle
            )
            self.inactive_mods_panel = InactiveModList(
                mod_type_filter_enable=GameConfiguration.instance().mod_type_filter_toggle
            )
            self.actions_panel = Actions()

            # WIDGETS INTO BASE LAYOUT
            self.main_layout.addLayout(self.mod_info_panel.panel, 50)
            self.main_layout.addLayout(self.inactive_mods_panel.panel, 25)
            self.main_layout.addLayout(self.active_mods_panel.panel, 25)
            self.main_layout.addLayout(self.actions_panel.panel)

            # SIGNALS AND SLOTS
            self.actions_panel.actions_signal.connect(self.actions_slot)  # Actions
            GameConfiguration.instance().configuration_signal.connect(self.actions_slot)
            GameConfiguration.instance().settings_panel.actions_signal.connect(
                self.actions_slot
            )  # Settings
            self.active_mods_panel.list_updated_signal.connect(
                self._do_save_animation
            )  # Save btn animation
            self.active_mods_panel.active_mods_list.key_press_signal.connect(
                self.__handle_active_mod_key_press
            )
            self.inactive_mods_panel.inactive_mods_list.key_press_signal.connect(
                self.__handle_inactive_mod_key_press
            )
            self.active_mods_panel.active_mods_list.mod_info_signal.connect(
                self.__mod_list_slot
            )
            self.inactive_mods_panel.inactive_mods_list.mod_info_signal.connect(
                self.__mod_list_slot
            )
            self.active_mods_panel.active_mods_list.item_added_signal.connect(
                self.inactive_mods_panel.inactive_mods_list.handle_other_list_row_added
            )
            self.inactive_mods_panel.inactive_mods_list.item_added_signal.connect(
                self.active_mods_panel.active_mods_list.handle_other_list_row_added
            )
            self.active_mods_panel.active_mods_list.recalculate_warnings_signal.connect(
                self.active_mods_panel.recalculate_internal_list_errors
            )
            self.active_mods_panel.active_mods_list.edit_rules_signal.connect(
                self._do_open_rule_editor
            )
            self.inactive_mods_panel.inactive_mods_list.edit_rules_signal.connect(
                self._do_open_rule_editor
            )
            self.active_mods_panel.active_mods_list.re_git_signal.connect(
                self._do_re_git
            )
            self.inactive_mods_panel.inactive_mods_list.re_git_signal.connect(
                self._do_re_git
            )
            self.active_mods_panel.active_mods_list.steamcmd_downloader_signal.connect(
                self._do_download_mods_with_steamcmd
            )
            self.inactive_mods_panel.inactive_mods_list.steamcmd_downloader_signal.connect(
                self._do_download_mods_with_steamcmd
            )
            self.active_mods_panel.active_mods_list.steamworks_subscription_signal.connect(
                self._do_steamworks_api_call_animated
            )
            self.inactive_mods_panel.inactive_mods_list.steamworks_subscription_signal.connect(
                self._do_steamworks_api_call_animated
            )
            self.active_mods_panel.active_mods_list.steamdb_blacklist_signal.connect(
                self._do_blacklist_action_steamdb
            )
            self.inactive_mods_panel.inactive_mods_list.steamdb_blacklist_signal.connect(
                self._do_blacklist_action_steamdb
            )
            self.active_mods_panel.active_mods_list.refresh_signal.connect(
                self._do_refresh
            )
            self.inactive_mods_panel.inactive_mods_list.refresh_signal.connect(
                self._do_refresh
            )
            # Restore cache initially set to empty
            self.active_mods_data_restore_state: Dict[str, Any] = {}
            self.inactive_mods_data_restore_state: Dict[str, Any] = {}

            # Store duplicate_mods for global access
            self.duplicate_mods = {}

            # Instantiate query runner
            self.query_runner = RunnerPanel = None

            # Steamworks bool - use this to check any Steamworks processes you try to initialize
            self.steamworks_in_use = False

            # Instantiate todds runner
            self.todds_runner = RunnerPanel = None

            logger.info("Finished MainContent initialization")
            self.initialized = True

    @classmethod
    def instance(cls, *args: Any, **kwargs: Any) -> "MainContent":
        if cls._instance is None:
            cls._instance = cls(*args, **kwargs)
        elif args or kwargs:
            raise ValueError("MainContent instance has already been initialized.")
        return cls._instance

    def ___get_relative_middle(self, some_list):
        rect = some_list.contentsRect()
        top = some_list.indexAt(rect.topLeft())
        if top.isValid():
            bottom = some_list.indexAt(rect.bottomLeft())
            if not bottom.isValid():
                bottom = some_list.model().index(some_list.count() - 1)
            return (top.row() + bottom.row() + 1) / 2
        return 0

    def __handle_active_mod_key_press(self, key) -> None:
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
        aml = self.active_mods_panel.active_mods_list
        iml = self.inactive_mods_panel.inactive_mods_list
        if key == "Left":
            iml.setFocus()
            if not iml.selectedIndexes():
                iml.setCurrentRow(self.___get_relative_middle(iml))
            self.__mod_list_slot(iml.selectedItems()[0].data(Qt.UserRole)["uuid"])

        elif key == "Return" or key == "Space" or key == "DoubleClick":
            # TODO: graphical bug where if you hold down the key, items are
            # inserted too quickly and become empty items

            items_to_move = aml.selectedItems().copy()
            if items_to_move:
                first_selected = sorted(aml.row(i) for i in items_to_move)[0]

                # Remove items from current list
                for item in items_to_move:
                    aml.takeItem(aml.row(item))
                    aml.uuids.discard(item.data(Qt.UserRole)["uuid"])
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

                # If the other list is the active mod list, recalculate errors
                self.active_mods_panel.recalculate_internal_list_errors()

    def __handle_inactive_mod_key_press(self, key) -> None:
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

        aml = self.active_mods_panel.active_mods_list
        iml = self.inactive_mods_panel.inactive_mods_list
        if key == "Right":
            aml.setFocus()
            if not aml.selectedIndexes():
                aml.setCurrentRow(self.___get_relative_middle(aml))
            self.__mod_list_slot(aml.selectedItems()[0].data(Qt.UserRole)["uuid"])

        elif key == "Return" or key == "Space" or key == "DoubleClick":
            # TODO: graphical bug where if you hold down the key, items are
            # inserted too quickly and become empty items

            items_to_move = iml.selectedItems().copy()
            if items_to_move:
                first_selected = sorted(iml.row(i) for i in items_to_move)[0]

                # Remove items from current list
                for item in items_to_move:
                    iml.takeItem(iml.row(item))
                    iml.uuids.discard(item.data(Qt.UserRole)["uuid"])
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

                # If the other list is the active mod list, recalculate errors
                self.active_mods_panel.recalculate_internal_list_errors()

    def __insert_data_into_lists(
        self, active_mods: Dict[str, Any], inactive_mods: Dict[str, Any]
    ) -> None:
        """
        Insert active mods and inactive mods into respective mod list widgets.

        :param active_mods: dict of active mods
        :param inactive_mods: dict of inactive mods
        """
        logger.info(
            f"Inserting mod data into active [{len(active_mods)}] and inactive [{len(inactive_mods)}] mod lists"
        )
        self.active_mods_panel.active_mods_list.recreate_mod_list(
            list_type="active", mods=active_mods
        )
        self.inactive_mods_panel.inactive_mods_list.recreate_mod_list(
            list_type="inactive", mods=inactive_mods
        )

        logger.info(
            f"Finished inserting mod data into active [{len(active_mods)}] and inactive [{len(inactive_mods)}] mod lists"
        )

    def __duplicate_mods_prompt(self) -> None:
        list_of_duplicate_mods = "\n".join(
            [f"* {mod}" for mod in self.duplicate_mods.keys()]
        )
        show_warning(
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
            GameConfiguration.instance().try_download_missing_mods_toggle
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
            self.missing_mods_prompt.setWindowModality(Qt.ApplicationModal)
            self.missing_mods_prompt.show()
        else:
            list_of_missing_mods = "\n".join([f"* {mod}" for mod in self.missing_mods])
            show_information(
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
        logger.info(f"USER ACTION: clicked on a mod list item: {uuid}")
        if uuid in self.metadata_manager.all_mods_compiled:
            self.mod_info_panel.display_mod_info(
                self.metadata_manager.all_mods_compiled[uuid]
            )
            if self.metadata_manager.all_mods_compiled[uuid].get("invalid"):
                # Set label color to red if mod is invalid
                invalid_qlabel_stylesheet = "QLabel { color : red; }"
                self.mod_info_panel.mod_info_name_value.setStyleSheet(
                    invalid_qlabel_stylesheet
                )
                self.mod_info_panel.mod_info_path_value.setStyleSheet(
                    invalid_qlabel_stylesheet
                )
                self.mod_info_panel.mod_info_author_value.setStyleSheet(
                    invalid_qlabel_stylesheet
                )
                self.mod_info_panel.mod_info_package_id_value.setStyleSheet(
                    invalid_qlabel_stylesheet
                )
            else:
                # Set label color to white if mod is valid
                invalid_qlabel_stylesheet = "QLabel { color : white; }"
                self.mod_info_panel.mod_info_name_value.setStyleSheet(
                    invalid_qlabel_stylesheet
                )
                self.mod_info_panel.mod_info_path_value.setStyleSheet(
                    invalid_qlabel_stylesheet
                )
                self.mod_info_panel.mod_info_author_value.setStyleSheet(
                    invalid_qlabel_stylesheet
                )
                self.mod_info_panel.mod_info_package_id_value.setStyleSheet(
                    invalid_qlabel_stylesheet
                )

    def __update_game_configuration(self) -> None:
        self.metadata_manager.community_rules_repo = (
            GameConfiguration.instance().community_rules_repo
        )
        self.metadata_manager.database_expiry = (
            GameConfiguration.instance().database_expiry
        )
        self.metadata_manager.dbs_path = GameConfiguration.instance().dbs_path
        self.metadata_manager.external_community_rules_metadata_source = (
            GameConfiguration.instance().settings_panel.external_community_rules_metadata_cb.currentText()
        )
        self.metadata_manager.external_community_rules_file_path = (
            GameConfiguration.instance().community_rules_file_path
        )
        self.metadata_manager.external_steam_metadata_file_path = (
            GameConfiguration.instance().steam_db_file_path
        )
        self.metadata_manager.external_steam_metadata_source = (
            GameConfiguration.instance().settings_panel.external_steam_metadata_cb.currentText()
        )
        self.metadata_manager.game_path = (
            GameConfiguration.instance().game_folder_line.text()
        )
        self.metadata_manager.local_path = (
            GameConfiguration.instance().local_folder_line.text()
        )
        self.metadata_manager.steamcmd_acf_path = (
            self.steamcmd_wrapper.steamcmd_appworkshop_acf_path
        )
        self.metadata_manager.steam_db_repo = GameConfiguration.instance().steam_db_repo
        self.metadata_manager.user_rules_file_path = (
            GameConfiguration.instance().user_rules_file_path
        )
        self.metadata_manager.workshop_path = (
            GameConfiguration.instance().workshop_folder_line.text()
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
            active_mods_data,
            inactive_mods_data,
            self.duplicate_mods,
            self.missing_mods,
        ) = get_active_inactive_mods(
            str(
                Path(
                    os.path.join(
                        GameConfiguration.instance().config_folder_line.text(),
                        "ModsConfig.xml",
                    )
                ).resolve()
            ),
            self.metadata_manager.all_mods_compiled,
        )
        if is_initial:
            logger.info("Caching initial active/inactive mod lists")
            self.active_mods_data_restore_state = active_mods_data
            self.inactive_mods_data_restore_state = inactive_mods_data

        self.__insert_data_into_lists(active_mods_data, inactive_mods_data)

    @property
    def panel(self):
        return self._panel

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
        if action == "update_mod_type_filter_toggle":
            self.active_mods_panel.active_mods_list.mod_type_filter_enable = (
                GameConfiguration.instance().mod_type_filter_toggle
            )
            self.inactive_mods_panel.inactive_mods_list.mod_type_filter_enable = (
                GameConfiguration.instance().mod_type_filter_toggle
            )
        if action == "update_steamcmd_validate_toggle":
            self.steamcmd_wrapper.validate_downloads = (
                GameConfiguration.instance().steamcmd_validate_downloads_toggle
            )
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
            todds_txt_path = str(
                Path(os.path.join(gettempdir(), "todds.txt")).resolve()
            )
            if os.path.exists(todds_txt_path):
                os.remove(todds_txt_path)
            if not GameConfiguration.instance().todds_active_mods_target_toggle:
                local_mods_target = (
                    GameConfiguration.instance().local_folder_line.text()
                )
                if local_mods_target and local_mods_target != "":
                    with open(todds_txt_path, "a") as todds_txt_file:
                        todds_txt_file.write(local_mods_target + "\n")
                workshop_mods_target = (
                    GameConfiguration.instance().workshop_folder_line.text()
                )
                if workshop_mods_target and workshop_mods_target != "":
                    with open(todds_txt_path, "a") as todds_txt_file:
                        todds_txt_file.write(workshop_mods_target + "\n")
            else:
                with open(todds_txt_path, "a") as todds_txt_file:
                    for (
                        json_data
                    ) in (
                        self.active_mods_panel.active_mods_list.get_list_items_by_dict().values()
                    ):
                        todds_txt_file.write(json_data["path"] + "\n")
            if action == "optimize_textures":
                self._do_optimize_textures(todds_txt_path)
            if action == "delete_textures":
                self._do_delete_dds_textures(todds_txt_path)
        if action == "add_git_mod":
            self._do_add_git_mod()
        if action == "browse_workshop":
            self._do_browse_workshop()
        if action == "setup_steamcmd":
            self._do_setup_steamcmd()
        if action == "import_steamcmd_acf_data":
            import_steamcmd_acf_data(
                rimsort_storage_path=GameConfiguration.instance().storage_path,
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
        if action == "set_steamcmd_path":
            self._do_set_steamcmd_path()
        if action == "update_workshop_mods":
            self._do_check_for_workshop_updates()
        if action == "import_list_file_xml":
            self._do_import_list_file_xml()
        if action == "export_list_file_xml":
            self._do_export_list_file_xml()
        if action == "export_list_clipboard":
            self._do_export_list_clipboard()
        if action == "upload_list_rentry":
            self._do_upload_list_rentry()
        if action == "upload_rs_log":
            self._upload_rs_log()
        if action == "upload_rs_old_log":
            self._upload_rs_old_log()
        if action == "save":
            self._do_save()
        if action == "run":
            self._do_steamworks_api_call(
                [
                    "launch_game_process",
                    [
                        GameConfiguration.instance().game_folder_line.text(),
                        GameConfiguration.instance().run_arguments,
                    ],
                ]
            )
        if action == "edit_run_args":
            self._do_edit_run_args()

        # settings panel actions
        if action == "upload_rw_log":
            self._do_upload_rw_log()
        if action == "configure_github_identity":
            self._do_configure_github_identity()
        if action == "configure_steam_database_path":
            self._do_configure_steam_db_file_path()
        if action == "configure_steam_database_repo":
            self._do_configure_steam_database_repo()
        if action == "download_steam_database":
            if GIT_EXISTS:
                self._do_clone_repo_to_path(
                    base_path=GameConfiguration.instance().dbs_path,
                    repo_url=GameConfiguration.instance().steam_db_repo,
                )
            else:
                self._do_notify_no_git()
        if action == "upload_steam_database":
            if GIT_EXISTS:
                self._do_upload_db_to_repo(
                    repo_url=GameConfiguration.instance().steam_db_repo,
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
                    base_path=GameConfiguration.instance().dbs_path,
                    repo_url=GameConfiguration.instance().community_rules_repo,
                )
            else:
                self._do_notify_no_git()
        if action == "open_community_rules_with_rule_editor":
            self._do_open_rule_editor(compact=False, initial_mode="community_rules")
        if action == "upload_community_rules_database":
            if GIT_EXISTS:
                self._do_upload_db_to_repo(
                    repo_url=GameConfiguration.instance().community_rules_repo,
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
        # NOT NUITKA
        if not "__compiled__" in globals():
            logger.debug(
                "You are running from Python interpreter. Skipping update check..."
            )
            show_warning(
                title="Update skipped",
                text="You are running from Python interpreter.",
                information="Skipping update check...",
            )
            return
        # NUITKA
        logger.debug("Checking for RimSort update...")
        current_version = GameConfiguration.instance().rimsort_version.lower()
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
            answer = show_dialogue_conditional(
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
                if not "browser_download_url" in locals():
                    show_warning(
                        title="Unable to complete update",
                        text=f"Failed to find valid RimSort release for {SYSTEM} {ARCH} {PROCESSOR}",
                    )
                    return
                target_archive_extracted = target_archive.replace(".zip", "")
                try:
                    logger.debug(
                        f"Downloading & extracting RimSort release from: {browser_download_url}"
                    )
                    self._do_threaded_loading_animation(
                        gif_path=str(
                            Path(
                                os.path.join(
                                    os.path.dirname(__file__), "../data/refresh.gif"
                                )
                            ).resolve()
                        ),
                        target=partial(
                            self.__do_download_extract_release_to_tempdir,
                            url=browser_download_url,
                        ),
                        text=f"RimSort update found. Downloading RimSort {tag_name_updated} release...",
                    )
                    temp_dir = "RimSort" if not SYSTEM == "Darwin" else "RimSort.app"
                    answer = show_dialogue_conditional(
                        title="Update downloaded",
                        text="Do you want to proceed with the update?",
                        information=f"\nSuccessfully retrieved latest release. The update will be installed from: {os.path.join(gettempdir(), temp_dir)}",
                    )
                    if not answer == "&Yes":
                        return
                except:
                    stacktrace = traceback.format_exc()
                    show_warning(
                        title="Failed to download update",
                        text="Failed to download latest RimSort release!",
                        information=f"Did the file/url change? "
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
                        str(
                            Path(
                                os.path.join(
                                    current_dir,
                                    "Contents",
                                    "MacOS",
                                    "update.sh",
                                )
                            ).resolve()
                        ),
                    ]
                    p = subprocess.Popen(popen_args)
                else:
                    try:
                        subprocess.CREATE_NEW_PROCESS_GROUP
                    except (
                        AttributeError
                    ):  # not Windows, so assume POSIX; if not, we'll get a usable exception
                        popen_args = [
                            "/bin/bash",
                            str(
                                Path(
                                    os.path.join(
                                        os.path.dirname(__file__),
                                        f"../update.sh",
                                    )
                                ).resolve()
                            ),
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
                                Path(
                                    os.path.join(
                                        os.path.dirname(__file__),
                                        f"../update.bat",
                                    )
                                ).resolve()
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
            show_information(
                title="RimSort is up to date!",
                text=f"You are already running the latest release: {tag_name}",
            )

    def __do_download_extract_release_to_tempdir(self, url: str) -> None:
        with ZipFile(BytesIO(requests_get(url).content)) as zipobj:
            zipobj.extractall(gettempdir())

    def __do_get_github_release_info(self) -> Dict[str, Any]:
        # Parse latest release
        raw = requests_get(
            "https://api.github.com/repos/RimSort/RimSort/releases/latest"
        )
        return raw.json()

    # INFO PANEL ANIMATIONS

    def _do_threaded_loading_animation(
        self, gif_path: str, target: Callable, text=None
    ) -> Any:
        loading_animation_text_label = None
        # Hide the info panel widgets
        self.mod_info_panel.info_panel_frame.hide()
        # Disable widgets
        for widget in QApplication.instance().allWidgets():
            widget.setEnabled(False)
        # Encapsulate mod parsing inside a nice lil animation
        loading_animation = LoadingAnimation(
            gif_path=gif_path,
            target=target,
        )
        self.mod_info_panel.panel.addWidget(loading_animation)
        # If any text message specified, pass it to the info panel as well
        if text:
            loading_animation_text_label = QLabel(text)
            loading_animation_text_label.setAlignment(Qt.AlignCenter)
            loading_animation_text_label.setStyleSheet("font-size: 18 px")
            self.mod_info_panel.panel.addWidget(loading_animation_text_label)
        loop = QEventLoop()
        loading_animation.finished.connect(loop.quit)
        loop.exec_()
        data = loading_animation.data
        # Remove text label if it was passed
        if text:
            self.mod_info_panel.panel.removeWidget(loading_animation_text_label)
            loading_animation_text_label.close()
        # Enable widgets
        for widget in QApplication.instance().allWidgets():
            widget.setEnabled(True)
        # Show the info panel widgets
        self.mod_info_panel.info_panel_frame.show()
        logger.debug(f"Returning {type(data)}")
        return data

    # ACTIONS PANEL

    def _do_refresh(self, is_initial=None) -> None:
        """
        Refresh expensive calculations & repopulate lists with that refreshed data
        """
        # If we are refreshing cache from user action
        if not is_initial:
            self.active_mods_panel.list_updated = False
            # Stop the refresh button from blinking if it is blinking
            if self.actions_panel.refresh_button_flashing_animation.isActive():
                self.actions_panel.refresh_button_flashing_animation.stop()
                self.actions_panel.refresh_button.setStyleSheet(
                    """
                    QPushButton {
                        color: white;
                        background-color: #455364;
                        border-style: solid;
                        border-width: 0px;
                        border-radius: 5px;
                        /* border-color: beige; */
                        /* font: bold 14px; */
                        min-width: 6em;
                        padding: 1px;
                    }

                    QPushButton:hover {
                        background-color: #54687a;
                    }

                    QPushButton:pressed {
                        background-color: #3e4a52;
                        border-style: inset;
                    }
                    """
                )
            # Stop the save button from blinking if it is blinking
            if self.actions_panel.save_button_flashing_animation.isActive():
                self.actions_panel.save_button_flashing_animation.stop()
                self.actions_panel.save_button.setStyleSheet(
                    """
                    QPushButton {
                        color: white;
                        background-color: #455364;
                        border-style: solid;
                        border-width: 0px;
                        border-radius: 5px;
                        /* border-color: beige; */
                        /* font: bold 14px; */
                        min-width: 6em;
                        padding: 1px;
                    }

                    QPushButton:hover {
                        background-color: #54687a;
                    }

                    QPushButton:pressed {
                        background-color: #3e4a52;
                        border-style: inset;
                    }
                    """
                )
            self.active_mods_panel.active_mods_filter_data_source_index = len(
                self.active_mods_panel.active_mods_filter_data_source_icons
            )
            self.active_mods_panel.clear_active_mods_search()
            self.inactive_mods_panel.inactive_mods_filter_data_source_index = len(
                self.inactive_mods_panel.inactive_mods_filter_data_source_icons
            )
            self.inactive_mods_panel.clear_inactive_mods_search()
        # Check if paths are set
        if GameConfiguration.instance().check_if_essential_paths_are_set():
            # Run expensive calculations to set cache data
            loading_gif_path = str(
                Path(
                    os.path.join(os.path.dirname(__file__), "../data/rimsort.gif")
                ).resolve()
            )
            self._do_threaded_loading_animation(
                gif_path=loading_gif_path,
                target=partial(
                    self.metadata_manager.refresh_cache, is_initial=is_initial
                ),
                text="Scanning mod sources and populating metadata...",
            )

            # Set the game version string in the UI and pass it to the active_mods_panel
            GameConfiguration.instance().game_version_line.setText(
                self.metadata_manager.game_version
            )
            # Insert mod data into list
            self.__repopulate_lists(is_initial=is_initial)

            # If we have duplicate mods, prompt user
            if (
                GameConfiguration.instance().duplicate_mods_warning_toggle
                and self.duplicate_mods
                and len(self.duplicate_mods) > 0
            ):
                self.__duplicate_mods_prompt()
            elif not GameConfiguration.instance().duplicate_mods_warning_toggle:
                logger.debug(
                    "User preference is not configured to display duplicate mods. Skipping..."
                )

            # If we have missing mods, prompt user
            if self.missing_mods and len(self.missing_mods) > 0:
                self.__missing_mods_prompt()

            # Check Workshop mods for updates if configured
            if (
                GameConfiguration.instance().steam_mods_update_check_toggle
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
            self.__insert_data_into_lists({}, {})
            logger.debug(
                "Essential paths have not been set. Passing refresh and resetting mod lists"
            )
        # Set the game version string in the UI and pass it to the active_mods_panel
        GameConfiguration.instance().game_version_line.setText(
            self.metadata_manager.game_version
        )
        self.active_mods_panel.game_version = self.metadata_manager.game_version
        # Feed all_mods and Steam DB info to Active Mods list to surface
        # names instead of package_ids when able
        self.active_mods_panel.all_mods = self.metadata_manager.all_mods_compiled
        self.active_mods_panel.steam_package_id_to_name = (
            self.metadata_manager.info_from_steam_package_id_to_name
        )

    def _do_refresh_animation(self, path: str) -> None:
        logger.debug(f"File change detected: {path}")
        if not self.actions_panel.refresh_button_flashing_animation.isActive():
            logger.debug("Starting refresh button animation")
            self.actions_panel.refresh_button_flashing_animation.start(
                500
            )  # blink every 500 milliseconds

    def _do_clear(self) -> None:
        """
        Method to clear all the non-base, non-DLC mods from the active
        list widget and put them all into the inactive list widget.
        """
        self.active_mods_panel.active_mods_filter_data_source_index = len(
            self.active_mods_panel.active_mods_filter_data_source_icons
        )
        self.active_mods_panel.clear_active_mods_search()
        self.inactive_mods_panel.inactive_mods_filter_data_source_index = len(
            self.inactive_mods_panel.inactive_mods_filter_data_source_icons
        )
        self.inactive_mods_panel.clear_inactive_mods_search()

        # Metadata from official modules, stored so they can be inserted in proper order
        core_data = None
        royalty_data = None
        ideology_data = None
        biotech_data = None
        # Metadata to insert
        active_mod_data = {}
        inactive_mod_data = {}
        logger.info("Clearing mods from active mod list")
        for uuid, mod_data in self.metadata_manager.all_mods_compiled.items():
            if mod_data["data_source"] == "expansion":
                if (
                    mod_data["packageid"]
                    == RIMWORLD_DLC_METADATA["294100"]["packageid"]
                ):
                    core_data = mod_data
                elif (
                    mod_data["packageid"]
                    == RIMWORLD_DLC_METADATA["1149640"]["packageid"]
                ):
                    royalty_data = mod_data
                elif (
                    mod_data["packageid"]
                    == RIMWORLD_DLC_METADATA["1392840"]["packageid"]
                ):
                    ideology_data = mod_data
                elif (
                    mod_data["packageid"]
                    == RIMWORLD_DLC_METADATA["1826140"]["packageid"]
                ):
                    biotech_data = mod_data
            else:
                inactive_mod_data[uuid] = mod_data
        if core_data:
            active_mod_data[core_data["uuid"]] = core_data
        if royalty_data:
            active_mod_data[royalty_data["uuid"]] = royalty_data
        if ideology_data:
            active_mod_data[ideology_data["uuid"]] = ideology_data
        if biotech_data:
            active_mod_data[biotech_data["uuid"]] = biotech_data
        self.__insert_data_into_lists(active_mod_data, inactive_mod_data)

    def _do_sort(self) -> None:
        """
        Trigger sorting of all active mods using user-configured algorithm
        & all available & configured metadata
        """
        # Get the live list of active and inactive mods. This is because the user
        # will likely sort before saving.
        logger.debug("Starting sorting mods")
        self.active_mods_panel.clear_active_mods_search()
        self.active_mods_panel.active_mods_filter_data_source_index = len(
            self.active_mods_panel.active_mods_filter_data_source_icons
        )
        self.active_mods_panel.signal_active_mods_data_source_filter()
        self.inactive_mods_panel.clear_inactive_mods_search()
        self.inactive_mods_panel.inactive_mods_filter_data_source_index = len(
            self.inactive_mods_panel.inactive_mods_filter_data_source_icons
        )
        self.inactive_mods_panel.signal_inactive_mods_data_source_filter()
        active_mods = self.active_mods_panel.active_mods_list.get_list_items_by_dict()
        active_mod_ids = list()
        for mod_data in active_mods.values():
            active_mod_ids.append(mod_data["packageid"])
        inactive_mods = (
            self.inactive_mods_panel.inactive_mods_list.get_list_items_by_dict()
        )

        # Get all active mods and their dependencies (if also active mod)
        dependencies_graph = gen_deps_graph(active_mods, active_mod_ids)

        # Get all active mods and their reverse dependencies
        reverse_dependencies_graph = gen_rev_deps_graph(active_mods, active_mod_ids)

        # Get dependencies graph for tier one mods (load at top mods)
        tier_one_dependency_graph, tier_one_mods = gen_tier_one_deps_graph(
            dependencies_graph
        )

        # Get dependencies graph for tier three mods (load at bottom mods)
        tier_three_dependency_graph, tier_three_mods = gen_tier_three_deps_graph(
            dependencies_graph, reverse_dependencies_graph, active_mods
        )

        # Get dependencies graph for tier two mods (load in middle)
        tier_two_dependency_graph = gen_tier_two_deps_graph(
            active_mods, active_mod_ids, tier_one_mods, tier_three_mods
        )

        # Depending on the selected algorithm, sort all tiers with Alphabetical
        # mimic algorithm or toposort
        sorting_algorithm = (
            GameConfiguration.instance().settings_panel.sorting_algorithm_cb.currentText()
        )

        if sorting_algorithm == "Alphabetical":
            logger.info("Alphabetical sorting algorithm is selected")
            reordered_tier_one_sorted_with_data = do_alphabetical_sort(
                tier_one_dependency_graph, active_mods
            )
            reordered_tier_three_sorted_with_data = do_alphabetical_sort(
                tier_three_dependency_graph, active_mods
            )
            reordered_tier_two_sorted_with_data = do_alphabetical_sort(
                tier_two_dependency_graph, active_mods
            )
        else:
            logger.info("Topological sorting algorithm is selected")
            # Sort tier one mods
            reordered_tier_one_sorted_with_data = do_topo_sort(
                tier_one_dependency_graph, active_mods
            )
            # Sort tier three mods
            reordered_tier_three_sorted_with_data = do_topo_sort(
                tier_three_dependency_graph, active_mods
            )
            # Sort tier two mods
            reordered_tier_two_sorted_with_data = do_topo_sort(
                tier_two_dependency_graph, active_mods
            )

        logger.info(f"Sorted tier one mods: {len(reordered_tier_one_sorted_with_data)}")
        logger.info(f"Sorted tier two mods: {len(reordered_tier_two_sorted_with_data)}")
        logger.info(
            f"Sorted tier three mods: {len(reordered_tier_three_sorted_with_data)}"
        )

        # Add Tier 1, 2, 3 in order
        combined_mods = {}
        for uuid, mod_data in reordered_tier_one_sorted_with_data.items():
            combined_mods[uuid] = mod_data
        for uuid, mod_data in reordered_tier_two_sorted_with_data.items():
            combined_mods[uuid] = mod_data
        for uuid, mod_data in reordered_tier_three_sorted_with_data.items():
            combined_mods[uuid] = mod_data

        logger.info("Finished combining all tiers of mods. Inserting into mod lists!")
        self.__insert_data_into_lists(combined_mods, inactive_mods)

    def _do_import_list_file_xml(self) -> None:
        """
        Open a user-selected XML file. Calculate
        and display active and inactive lists based on this file.
        """
        logger.info("Opening file dialog to select input file")
        file_path = show_dialogue_file(
            mode="open",
            caption="Open mod list",
            _dir=str(
                Path(os.path.join(GameConfiguration.instance().storage_path)).resolve()
            ),
            _filter="XML (*.xml)",
        )
        logger.info(f"Selected path: {file_path}")
        if file_path:
            self.active_mods_panel.clear_active_mods_search()
            self.active_mods_panel.active_mods_filter_data_source_index = len(
                self.active_mods_panel.active_mods_filter_data_source_icons
            )
            self.active_mods_panel.signal_active_mods_data_source_filter()
            self.inactive_mods_panel.clear_inactive_mods_search()
            self.inactive_mods_panel.inactive_mods_filter_data_source_index = len(
                self.inactive_mods_panel.inactive_mods_filter_data_source_icons
            )
            self.inactive_mods_panel.signal_inactive_mods_data_source_filter()
            logger.info(f"Trying to import mods list from XML: {file_path}")
            (
                active_mods_data,
                inactive_mods_data,
                self.duplicate_mods,
                self.missing_mods,
            ) = get_active_inactive_mods(
                file_path,
                self.metadata_manager.all_mods_compiled,
            )
            logger.info("Got new mods according to imported XML")
            self.__insert_data_into_lists(active_mods_data, inactive_mods_data)
            # If we have duplicate mods, prompt user
            if (
                GameConfiguration.instance().duplicate_mods_warning_toggle
                and self.duplicate_mods
                and len(self.duplicate_mods) > 0
            ):
                self.__duplicate_mods_prompt()
            elif not GameConfiguration.instance().duplicate_mods_warning_toggle:
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
        file_path = show_dialogue_file(
            mode="save",
            caption="Save mod list",
            _dir=str(
                Path(os.path.join(GameConfiguration.instance().storage_path)).resolve()
            ),
            _filter="XML (*.xml)",
        )
        logger.info(f"Selected path: {file_path}")
        if file_path:
            logger.info("Exporting current active mods to ModsConfig.xml format")
            active_mods_json = (
                self.active_mods_panel.active_mods_list.get_list_items_by_dict()
            )
            active_mods = []
            for mod_data in active_mods_json.values():
                package_id = mod_data["packageid"]
                if package_id in active_mods:  # This should NOT be happening
                    logger.critical(
                        f"Tried to export more than 1 identical package ids to the same mod list. Skipping duplicate {package_id}"
                    )
                    continue
                else:  # Otherwise, proceed with adding the mod package_id
                    if (
                        package_id in self.duplicate_mods.keys()
                    ):  # Check if mod has duplicates
                        if mod_data["data_source"] == "workshop":
                            active_mods.append(package_id + "_steam")
                            continue  # Append `_steam` suffix if Steam mod, continue to next mod
                    active_mods.append(package_id)
            logger.info(f"Collected {len(active_mods)} active mods for export")
            logger.info("Getting current ModsConfig.xml to use as a reference format")
            mods_config_data = xml_path_to_json(
                str(
                    Path(
                        os.path.join(
                            GameConfiguration.instance().config_folder_line.text(),
                            "ModsConfig.xml",
                        )
                    ).resolve()
                )
            )
            if validate_mods_config_format(mods_config_data):
                logger.info(
                    "Successfully got ModsConfig.xml data. Overwriting with current active mods"
                )
                mods_config_data["ModsConfigData"]["activeMods"]["li"] = active_mods
                logger.info(
                    f"Saving generated ModsConfig.xml to selected path: {file_path}"
                )
                if not file_path.endswith(".xml"):
                    json_to_xml_write(mods_config_data, file_path + ".xml")
                else:
                    json_to_xml_write(mods_config_data, file_path)
            else:
                logger.error("Could not export active mods")
        else:
            logger.debug("USER ACTION: pressed cancel, passing")

    def _do_export_list_clipboard(self) -> None:
        """
        Export the current list of active mods to the clipboard in a
        readable format. The current list does not need to have been saved.
        """
        logger.info("Generating report to export mod list to clipboard")
        # Build our lists
        active_mods = []
        active_mods_json = (
            self.active_mods_panel.active_mods_list.get_list_items_by_dict()
        )
        active_mods_packageid_to_uuid = {}
        for uuid, mod_data in active_mods_json.items():
            package_id = mod_data["packageid"]
            if package_id in active_mods:  # This should NOT be happening
                logger.critical(
                    f"Tried to export more than 1 identical package ids to the same mod list. "
                    + f"Skipping duplicate {package_id}"
                )
                continue
            else:  # Otherwise, proceed with adding the mod package_id
                active_mods.append(package_id)
                active_mods_packageid_to_uuid[package_id] = uuid
        logger.info(f"Collected {len(active_mods)} active mods for export")
        # Build our report
        active_mods_clipboard_report = (
            f"Created with RimSort {GameConfiguration.instance().rimsort_version}"
            + f"\nRimWorld game version this list was created for: {self.metadata_manager.game_version}"
            + f"\nTotal # of mods: {len(active_mods)}\n"
        )
        for package_id in active_mods:
            uuid = active_mods_packageid_to_uuid[package_id]
            if active_mods_json[uuid].get("name"):
                name = active_mods_json[uuid]["name"]
            else:
                name = "No name specified"
            if active_mods_json[uuid].get("url"):
                url = active_mods_json[uuid]["url"]
            elif active_mods_json[uuid].get("steam_url"):
                url = active_mods_json[uuid]["steam_url"]
            else:
                url = "No url specified"
            active_mods_clipboard_report = (
                active_mods_clipboard_report
                + f"\n{name} "
                + f"[{package_id}]"
                + f"[{url}]"
            )
        # Copy report to clipboard
        show_information(
            title="Export active mod list",
            text=f"Copied active mod list report to clipboard...",
            information='Click "Show Details" to see the full report!',
            details=f"{active_mods_clipboard_report}",
        )
        copy_to_clipboard(active_mods_clipboard_report)

    def _do_upload_list_rentry(self) -> None:
        """
        Export the current list of active mods to the clipboard in a
        readable format. The current list does not need to have been saved.
        """
        # Define our lists
        active_mods = []
        active_mods_json = (
            self.active_mods_panel.active_mods_list.get_list_items_by_dict()
        )
        active_mods_packageid_to_uuid = {}
        active_steam_mods_packageid_to_pfid = {}
        active_steam_mods_pfid_to_preview_url = {}
        pfids = []
        # Build our lists
        for uuid, mod_data in active_mods_json.items():
            package_id = mod_data["packageid"]
            if package_id in active_mods:  # This should NOT be happening
                logger.critical(
                    f"Tried to export more than 1 identical package ids to the same mod list. "
                    + f"Skipping duplicate {package_id}"
                )
                continue
            else:  # Otherwise, proceed with adding the mod package_id
                active_mods.append(package_id)
                active_mods_packageid_to_uuid[package_id] = uuid
                if (
                    mod_data.get("steamcmd") or mod_data["data_source"] == "workshop"
                ) and mod_data.get("publishedfileid"):
                    publishedfileid = mod_data["publishedfileid"]
                    active_steam_mods_packageid_to_pfid[package_id] = publishedfileid
                    pfids.append(publishedfileid)
        logger.info(f"Collected {len(active_mods)} active mods for export")
        if len(pfids) > 0:  # No empty queries...
            # Compile list of Steam Workshop publishing preview images that correspond
            # to a Steam mod in the active mod list
            webapi_response = ISteamRemoteStorage_GetPublishedFileDetails(pfids)
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
            f"# RimWorld mod list       ![](https://github.com/RimSort/RimSort/blob/main/rentry_preview.png?raw=true)"
            + f"\nCreated with RimSort {GameConfiguration.instance().rimsort_version}"
            + f"\nMod list was created for game version: `{self.metadata_manager.game_version}`"
            + f"\n!!! info Local mods are marked as yellow labels with packageid in brackets."
            + f"\n\n\n\n!!! note Mod list length: `{len(active_mods)}`\n"
        )
        # Add a line for each mod
        for package_id in active_mods:
            count = active_mods.index(package_id) + 1
            uuid = active_mods_packageid_to_uuid[package_id]
            if active_mods_json[uuid].get("name"):
                name = active_mods_json[uuid]["name"]
            else:
                name = "No name specified"
            if (
                active_mods_json[uuid].get("steamcmd")
                or active_mods_json[uuid]["data_source"] == "workshop"
            ) and active_steam_mods_packageid_to_pfid.get(package_id):
                pfid = active_steam_mods_packageid_to_pfid[package_id]
                if active_steam_mods_pfid_to_preview_url.get(pfid):
                    preview_url = (
                        active_steam_mods_pfid_to_preview_url[pfid]
                        + "?imw=100&imh=100&impolicy=Letterbox"
                    )
                else:
                    preview_url = "https://github.com/RimSort/RimSort/blob/main/rentry_steam_icon.png?raw=true"
                if active_mods_json[uuid].get("steam_url"):
                    url = active_mods_json[uuid]["steam_url"]
                elif active_mods_json[uuid].get("url"):
                    url = active_mods_json[uuid]["url"]
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
                if active_mods_json[uuid].get("url"):
                    url = active_mods_json[uuid]["url"]
                elif active_mods_json[uuid].get("steam_url"):
                    url = active_mods_json[uuid]["steam_url"]
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
        if (
            rentry_uploader.upload_success
            and rentry_uploader.url != None
            and "https://rentry.co/" in rentry_uploader.url
        ):
            copy_to_clipboard(rentry_uploader.url)
            show_information(
                title="Uploaded active mod list",
                text=f"Uploaded active mod list report to Rentry.co! The URL has been copied to your clipboard:\n\n{rentry_uploader.url}",
                information='Click "Show Details" to see the full report!',
                details=f"{active_mods_rentry_report}",
            )
        else:
            show_warning(
                title="Failed to upload",
                text="Failed to upload exported active mod list to Rentry.co",
            )

    def _do_upload_rw_log(self):
        player_log_path = str(
            Path(
                os.path.join(
                    GameConfiguration.instance().config_folder_line.text()
                    + "/../Player.log"
                )
            ).resolve()
        )
        if os.path.exists(player_log_path):
            ret = upload_data_to_0x0_st(player_log_path)
            if ret:
                copy_to_clipboard(ret)
                show_information(
                    title="Uploaded file",
                    text=f"Uploaded RimWorld log to http://0x0.st/",
                    information=f"The URL has been copied to your clipboard:\n\n{ret}",
                )

    def _upload_rs_log(self):
        ret = upload_data_to_0x0_st(
            str(Path(os.path.join(gettempdir(), "RimSort.log")).resolve())
        )
        if ret:
            copy_to_clipboard(ret)
            show_information(
                title="Uploaded file",
                text=f"Uploaded RimSort.log to http://0x0.st/",
                information=f"The URL has been copied to your clipboard:\n\n{ret}",
            )

    def _upload_rs_old_log(self):
        ret = upload_data_to_0x0_st(
            str(Path(os.path.join(gettempdir(), "RimSort.old.log")).resolve())
        )
        if ret:
            copy_to_clipboard(ret)
            show_information(
                title="Uploaded file",
                text=f"Uploaded RimSort.old.log to http://0x0.st/",
                information=f"The URL has been copied to your clipboard:\n\n{ret}",
            )

    def _do_save(self) -> None:
        """
        Method save the current list of active mods to the selected ModsConfig.xml
        """
        logger.info("Saving current active mods to ModsConfig.xml")
        active_mods_json = (
            self.active_mods_panel.active_mods_list.get_list_items_by_dict()
        )
        active_mods = []
        for mod_data in active_mods_json.values():
            package_id = mod_data["packageid"]
            if package_id in active_mods:  # This should NOT be happening
                logger.critical(
                    f"Tried to export more than 1 identical package ids to the same mod list. Skipping duplicate {package_id}"
                )
                continue
            else:  # Otherwise, proceed with adding the mod package_id
                if (
                    package_id in self.duplicate_mods.keys()
                ):  # Check if mod has duplicates
                    if mod_data["data_source"] == "workshop":
                        active_mods.append(package_id + "_steam")
                        continue  # Append `_steam` suffix if Steam mod, continue to next mod
                active_mods.append(package_id)
        logger.info(f"Collected {len(active_mods)} active mods for saving")
        mods_config_path = str(
            Path(
                os.path.join(
                    GameConfiguration.instance().config_folder_line.text(),
                    "ModsConfig.xml",
                )
            ).resolve()
        )
        mods_config_data = xml_path_to_json(mods_config_path)
        if validate_mods_config_format(mods_config_data):
            logger.info(
                "Successfully got ModsConfig.xml data. Overwriting with current active mods"
            )
            mods_config_data["ModsConfigData"]["activeMods"]["li"] = active_mods
            json_to_xml_write(mods_config_data, mods_config_path)
        else:
            logger.error("Could not save active mods")
        # Stop the save button from blinking if it is blinking
        if self.actions_panel.save_button_flashing_animation.isActive():
            self.actions_panel.save_button_flashing_animation.stop()
            self.actions_panel.save_button.setStyleSheet(
                """
                QPushButton {
                    color: white;
                    background-color: #455364;
                    border-style: solid;
                    border-width: 0px;
                    border-radius: 5px;
                    /* border-color: beige; */
                    /* font: bold 14px; */
                    min-width: 6em;
                    padding: 1px;
                }

                QPushButton:hover {
                    background-color: #54687a;
                }

                QPushButton:pressed {
                    background-color: #3e4a52;
                    border-style: inset;
                }
                """
            )
        logger.info("Finished saving active mods")

    def _do_save_animation(self) -> None:
        logger.debug("Active mods list updated")
        if (
            self.active_mods_panel.list_updated  # This will only evaluate True if this is initialization, or _do_refresh()
            and not self.actions_panel.save_button_flashing_animation.isActive()  # No need to re-enable if it's already blinking
        ):
            logger.debug("Starting save button animation")
            self.actions_panel.save_button_flashing_animation.start(
                500
            )  # Blink every 500 milliseconds

    def _do_restore(self) -> None:
        """
        Method to restore the mod lists to the last saved state.
        TODO: restoring after clearing will cause a few harmless lines of
        'Inactive mod count changed to: 0' to appear.
        """
        if self.active_mods_data_restore_state and self.active_mods_data_restore_state:
            self.active_mods_panel.clear_active_mods_search()
            self.active_mods_panel.active_mods_filter_data_source_index = len(
                self.active_mods_panel.active_mods_filter_data_source_icons
            )
            self.active_mods_panel.signal_active_mods_data_source_filter()
            self.inactive_mods_panel.clear_inactive_mods_search()
            self.inactive_mods_panel.inactive_mods_filter_data_source_index = len(
                self.inactive_mods_panel.inactive_mods_filter_data_source_icons
            )
            self.inactive_mods_panel.signal_inactive_mods_data_source_filter()
            logger.info(
                f"Restoring cached mod lists with active list [{len(self.active_mods_data_restore_state)}] and inactive list [{len(self.inactive_mods_data_restore_state)}]"
            )
            self.__insert_data_into_lists(
                self.active_mods_data_restore_state,
                self.inactive_mods_data_restore_state,
            )
        else:
            logger.warning(
                "Cached mod lists for restore function not set as client started improperly. Passing on restore"
            )

    def _do_edit_run_args(self) -> None:
        """
        Opens a QDialogInput that allows the user to edit the run args
        that are configured to be passed to the Rimworld executable
        """
        args, ok = show_dialogue_input(
            title="Edit run arguments",
            text="Enter a comma separated list of arguments to pass to the Rimworld executable\n\n"
            + "Example: \n-popupwindow,-logfile,/path/to/file.log",
            value=",".join(GameConfiguration.instance().run_arguments),
        )
        if ok:
            GameConfiguration.instance().run_arguments = args.split(",")
            GameConfiguration.instance()._update_persistent_storage(
                {"runArgs": GameConfiguration.instance().run_arguments}
            )

    # TODDS ACTIONS

    def _do_optimize_textures(self, todds_txt_path: str) -> None:
        # Setup environment
        todds_interface = ToddsInterface(
            preset=GameConfiguration.instance().todds_preset,
            dry_run=GameConfiguration.instance().todds_dry_run_toggle,
            overwrite=GameConfiguration.instance().todds_overwrite_toggle,
        )

        # UI
        self.todds_runner = RunnerPanel(
            todds_dry_run_support=GameConfiguration.instance().todds_dry_run_toggle
        )
        self.todds_runner.setWindowTitle("RimSort - todds texture encoder")
        self.todds_runner.show()

        todds_interface.execute_todds_cmd(todds_txt_path, self.todds_runner)

    def _do_delete_dds_textures(self, todds_txt_path: str) -> None:
        todds_interface = ToddsInterface(
            preset="clean",
            dry_run=GameConfiguration.instance().todds_dry_run_toggle,
        )

        # UI
        self.todds_runner = RunnerPanel(
            todds_dry_run_support=GameConfiguration.instance().todds_dry_run_toggle
        )
        self.todds_runner.setWindowTitle("RimSort - todds texture encoder")
        self.todds_runner.show()

        # Delete all .dds textures using todds
        todds_interface.execute_todds_cmd(todds_txt_path, self.todds_runner)

    # STEAM{CMD, WORKS} ACTIONS

    def _do_browse_workshop(self):
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
        updates_checked = self._do_threaded_loading_animation(
            gif_path=str(
                Path(
                    os.path.join(os.path.dirname(__file__), "../data/steam_api.gif")
                ).resolve()
            ),
            target=partial(
                query_workshop_update_data, mods=self.metadata_manager.all_mods_compiled
            ),
            text="Checking Steam Workshop mods for updates...",
        )
        # If we failed to check for updates, skip the comparison(s) & UI prompt
        if updates_checked == "failed":
            show_warning(
                title="Unable to check for updates",
                text="RimSort was unable to query Steam WebAPI for update information!\n",
                information="Are you connected to the Internet?",
            )
            return
        self.workshop_mod_updater = ModUpdaterPrompt(
            internal_mod_metadata=self.metadata_manager.all_mods_compiled
        )
        self.workshop_mod_updater._populate_from_metadata()
        if self.workshop_mod_updater.updates_found:
            logger.debug("Displaying potential Workshop mod updates")
            self.workshop_mod_updater.steamcmd_downloader_signal.connect(
                self._do_download_mods_with_steamcmd
            )
            self.workshop_mod_updater.steamworks_subscription_signal.connect(
                self._do_steamworks_api_call_animated
            )
            self.workshop_mod_updater.show()
        else:
            self.status_signal.emit("All Workshop mods appear to be up to date!")
            self.workshop_mod_updater = None

    def _do_setup_steamcmd(self):
        if (
            self.steamcmd_runner
            and self.steamcmd_runner.process
            and self.steamcmd_runner.process.state() == QProcess.Running
        ):
            show_warning(
                title="RimSort",
                text="Unable to create SteamCMD runner!",
                information="There is an active process already running!",
                details=f"PID {self.steamcmd_runner.process.processId()} : "
                + self.steamcmd_runner.process.program(),
            )
            return
        self.steamcmd_runner = RunnerPanel()
        self.steamcmd_runner.setWindowTitle("RimSort - SteamCMD setup")
        self.steamcmd_runner.show()
        self.steamcmd_runner.message("Setting up steamcmd...")
        self.steamcmd_wrapper.setup_steamcmd(
            GameConfiguration.instance().local_folder_line.text(),
            False,
            self.steamcmd_runner,
        )

    def _do_download_mods_with_steamcmd(self, publishedfileids: list):
        logger.debug(
            f"Attempting to download {len(publishedfileids)} mods with SteamCMD"
        )
        # Check for blacklisted mods
        if self.metadata_manager.external_steam_metadata is not None:
            publishedfileids = check_if_pfids_blacklisted(
                publishedfileids=publishedfileids,
                steamdb=self.metadata_manager.external_steam_metadata,
            )
        # No empty publishedfileids
        if not len(publishedfileids) > 0:
            show_warning(
                title="RimSort",
                text="No PublishedFileIds were supplied in operation.",
                information="Please add mods to list before attempting to download.",
            )
            return
        # Check for existing steamcmd_runner process
        if (
            self.steamcmd_runner
            and self.steamcmd_runner.process
            and self.steamcmd_runner.process.state() == QProcess.Running
        ):
            show_warning(
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
            self.steamcmd_runner = RunnerPanel(
                steamcmd_download_tracking=publishedfileids,
                steam_db=self.metadata_manager.external_steam_metadata,
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
            show_warning(
                title="SteamCMD not found",
                text="SteamCMD executable was not found.",
                information='Please setup an existing SteamCMD prefix, or setup a new prefix with "Setup SteamCMD".',
            )

    def _do_set_steamcmd_path(self):
        """
        Open a file dialog to allow the user to select the game executable.
        """
        logger.info("USER ACTION: set the steamcmd folder")
        steamcmd_folder = show_dialogue_file(
            mode="open_dir",
            caption="Select steamcmd folder",
            _dir=os.path.expanduser("~"),
        )
        if steamcmd_folder:
            logger.info(f"Selected path: {steamcmd_folder}")
            logger.info(
                f"steamcmd install folder chosen. Updating storage with new path: {steamcmd_folder}"
            )
            GameConfiguration.instance().steamcmd_install_path = steamcmd_folder
            GameConfiguration.instance()._update_persistent_storage(
                {"steamcmd_install_path": steamcmd_folder}
            )
            self.steamcmd_wrapper = SteamcmdInterface.instance(
                GameConfiguration.instance().steamcmd_install_path,
                GameConfiguration.instance().steamcmd_validate_downloads_toggle,
            )
            self.active_mods_panel.active_mods_list.steamcmd_appworkshop_acf_path = (
                self.steamcmd_wrapper.steamcmd_appworkshop_acf_path
            )
            self.inactive_mods_panel.inactive_mods_list.steamcmd_appworkshop_acf_path = (
                self.steamcmd_wrapper.steamcmd_appworkshop_acf_path
            )
        else:
            logger.debug("USER ACTION: pressed cancel, passing")

    def _do_steamworks_api_call(self, instruction: list):
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
                        game_install_path=instruction[1][0], args=instruction[1][1]
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
                                action=instruction[0], pfid_or_pfids=chunk, interval=1
                            )
                            for chunk in pfids_chunked
                        ]
                        # Map the execution of the subscription actions to the pool of processes
                        pool.map(SteamworksSubscriptionHandler.run, actions)
                    platform_specific_open("steam://validate/294100")
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

    def _do_steamworks_api_call_animated(self, instruction: list):
        publishedfileids = instruction[1]
        logger.debug(f"Attempting to download {len(publishedfileids)} mods with Steam")
        # Check for blacklisted mods for subscription actions
        if instruction[0] == "subscribe":
            publishedfileids = check_if_pfids_blacklisted(
                publishedfileids=publishedfileids,
                steamdb=self.metadata_manager.external_steam_metadata,
            )
        # No empty publishedfileids
        if not len(publishedfileids) > 0:
            show_warning(
                title="RimSort",
                text="No PublishedFileIds were supplied in operation.",
                information="Please add mods to list before attempting to download.",
            )
            return
        # Close browser if open
        if self.steam_browser:
            self.steam_browser.close()
        # Process API call
        self._do_threaded_loading_animation(
            gif_path=str(
                Path(
                    os.path.join(os.path.dirname(__file__), "../data/steam.gif")
                ).resolve()
            ),
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
        args, ok = show_dialogue_input(
            title="Enter git repo",
            text="Enter a git repository url (http/https) to clone to local mods:",
        )
        if ok:
            self._do_clone_repo_to_path(
                base_path=GameConfiguration.instance().local_folder_line.text(),
                repo_url=args,
            )
        else:
            logger.debug("Cancelling operation.")

    def _do_re_git(self, repo_paths: list) -> None:
        if GIT_EXISTS:
            for path in repo_paths:
                try:
                    repo = Repo(path)
                    origin_url = repo.remote("origin").url
                except Exception as e:
                    show_warning(
                        title="Unable to open repository",
                        text="RimSort failed to open the git repository inside this mod. Please re-download the mod.",
                    )
                self._do_clone_repo_to_path(
                    base_path=os.path.split(path)[0], repo_url=origin_url
                )
                self._do_cleanup_gitpython(repo)
        else:
            self._do_notify_no_git()

    # EXTERNAL METADATA ACTIONS

    def _do_configure_github_identity(self) -> None:
        """
        Opens a QDialogInput that allows user to edit their Github token
        This token is used for DB repo related actions, as well as any
        "Github mod" related actions
        """
        args, ok = show_dialogue_input(
            title="Edit username",
            text="Enter your Github username:",
            value=GameConfiguration.instance().github_username,
        )
        if ok:
            GameConfiguration.instance().github_username = args
            GameConfiguration.instance()._update_persistent_storage(
                {"github_username": GameConfiguration.instance().github_username}
            )
        else:
            logger.debug("USER ACTION: cancelled input!")
            return
        args, ok = show_dialogue_input(
            title="Edit token",
            text="Enter your Github personal access token here (ghp_*):",
            value=GameConfiguration.instance().github_token,
        )
        if ok:
            GameConfiguration.instance().github_token = args
            GameConfiguration.instance()._update_persistent_storage(
                {"github_token": GameConfiguration.instance().github_token}
            )
        else:
            logger.debug("USER ACTION: cancelled input!")
            return

    def _do_cleanup_gitpython(self, repo) -> None:
        # Cleanup GitPython
        collect()
        repo.git.clear_cache()
        del repo

    def _do_clone_repo_to_path(self, base_path: str, repo_url: str) -> None:
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
            repo_path = str(
                Path(
                    os.path.join(
                        base_path,
                        repo_folder_name,
                    )
                ).resolve()
            )
            if os.path.exists(repo_path):  # If local repo does exists
                # Prompt to user to handle
                answer = show_dialogue_conditional(
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
                if answer == "&Cancel":
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
                show_information(
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
                    show_information(
                        title="Repo retrieved",
                        text="The configured repository was reinitialized with existing files! (likely leftover .dds textures)",
                        information=f"{repo_url} ->\n" + f"{repo_path}",
                    )
                except GitCommandError:
                    stacktrace = traceback.format_exc()
                    show_warning(
                        title="Failed to clone repo!",
                        text="The configured repo failed to clone/initialize! "
                        + "Are you connected to the Internet? "
                        + "Is your configured repo valid?",
                        information=f"Configured repository: {repo_url}",
                        details=stacktrace,
                    )
        else:
            # Warn the user so they know to configure in settings
            show_warning(
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
            repo_path = str(
                Path(
                    os.path.join(
                        base_path,
                        repo_folder_name,
                    )
                ).resolve()
            )
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
                    show_information(
                        title="Repo force updated",
                        text="The configured repository was updated!",
                        information=f"{repo_path} ->\n "
                        + f"{repo.head.commit.message}",
                    )
                    # Cleanup
                    self._do_cleanup_gitpython(repo=repo)
                except GitCommandError:
                    stacktrace = traceback.format_exc()
                    show_warning(
                        title="Failed to update repo!",
                        text="The configured repo failed to update! "
                        + "Are you connected to the Internet? "
                        + "Is your configured repo valid?",
                        information=f"Configured repository: {repo_url}",
                        details=stacktrace,
                    )
            else:
                answer = show_dialogue_conditional(
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
            show_warning(
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
            repo_path = str(
                Path(
                    os.path.join(
                        GameConfiguration.instance().storage_path,
                        GameConfiguration.instance().dbs_path,
                        repo_folder_name,
                    )
                ).resolve()
            )
            if os.path.exists(repo_path):  # If local repo exists
                # Update the file, commit + PR to repo
                logger.info(
                    f"Attempting to commit changes to {file_name} in git repository: {repo_path}"
                )
                try:
                    # Specify the file path relative to the local repository
                    file_full_path = str(
                        Path(os.path.join(repo_path, file_name)).resolve()
                    )
                    if os.path.exists(file_full_path):
                        # Load JSON data
                        with open(file_full_path, encoding="utf-8") as f:
                            json_string = f.read()
                            logger.debug(f"Reading info...")
                            database = json.loads(json_string)
                            logger.debug("Retrieved database...")
                        if database.get("version"):
                            database_version = (
                                database["version"]
                                - GameConfiguration.instance().database_expiry
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
                            strftime("%Y-%m-%d %H:%M:%S", localtime(database_version))
                            + f" {timezone_abbreviation}"
                        )
                    else:
                        show_warning(
                            title="File does not exist",
                            text="Please ensure the file exists and then try to upload again!",
                            information=f"File not found:\n{file_full_path}\nRepository:\n{repo_url}",
                        )
                        return

                    # Create a GitHub instance
                    g = Github(
                        GameConfiguration.instance().github_username,
                        GameConfiguration.instance().github_token,
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
                    local_repo.head.reference = new_branch

                    # Add the file to the index on our new branch
                    local_repo.index.add([file_full_path])

                    # Commit changes to the new branch
                    local_repo.index.commit(commit_message)
                    try:
                        # Push the changes to the remote repository and create a pull request from new_branch
                        origin = local_repo.remote()
                        origin.push(new_branch)
                    except:
                        stacktrace = traceback.format_exc()
                        show_warning(
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
                    except:
                        stacktrace = traceback.format_exc()
                        show_warning(
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
                    answer = show_dialogue_conditional(
                        title="Pull request created",
                        text="Successfully created pull request!",
                        information="Do you want to try to open it in your web browser?\n\n"
                        + f"URL: {pull_request_url}",
                    )
                    if answer == "&Yes":
                        # Open the url in user's web browser
                        open_url_browser(url=pull_request_url)
                except:
                    stacktrace = traceback.format_exc()
                    show_warning(
                        title="Failed to update repo!",
                        text=f"The configured repo failed to update!\nFile name: {file_name}",
                        information=f"Configured repository: {repo_url}",
                        details=stacktrace,
                    )
            else:
                answer = show_dialogue_conditional(
                    title="Repository does not exist",
                    text="Tried to update a git repository that does not exist!",
                    information="Would you like to clone a new copy of this repository?",
                )
                if answer == "&Yes":
                    if GIT_EXISTS:
                        self._do_clone_repo_to_path(
                            base_path=GameConfiguration.instance().dbs_path,
                            repo_url=repo_url,
                        )
                    else:
                        self._do_notify_no_git()
        else:
            # Warn the user so they know to configure in settings
            show_warning(
                title="Invalid repository",
                text="An invalid repository was detected!",
                information="Please reconfigure a repository in settings!\n"
                + 'A valid repository is a repository URL which is not empty and is prefixed with "http://" or "https://"',
            )

    def _do_notify_no_git(self) -> None:
        answer = show_dialogue_conditional(  # We import last so we can use gui + utils
            title="git not found",
            text="git executable was not found in $PATH!",
            information="git integration will not work without git installed! Do you want to open download page for git?",
        )
        if answer == "&Yes":
            open_url_browser("https://git-scm.com/downloads")

    def _do_open_rule_editor(
        self, compact: bool, initial_mode=str, packageid=None
    ) -> None:
        if GameConfiguration.instance().settings_panel.isVisible():
            GameConfiguration.instance().settings_panel.close()  # Close this if we came from game configuration
        self.rule_editor = RuleEditor(
            # Initialization options
            compact=compact,
            edit_packageid=packageid,
            initial_mode=initial_mode,
        )
        self.rule_editor._populate_from_metadata()
        self.rule_editor.setWindowModality(Qt.ApplicationModal)
        self.rule_editor.update_database_signal.connect(self._do_update_rules_database)
        self.rule_editor.show()

    def _do_configure_steam_db_file_path(self) -> None:
        # Input file
        logger.info("Opening file dialog to specify Steam DB")
        input_path = show_dialogue_file(
            mode="open",
            caption="Choose Steam Workshop Database",
            _dir=str(
                Path(os.path.join(GameConfiguration.instance().storage_path)).resolve()
            ),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path}")
        if input_path and os.path.exists(input_path):
            GameConfiguration.instance()._update_persistent_storage(
                {"external_steam_metadata_file_path": input_path}
            )
            GameConfiguration.instance().steam_db_file_path = input_path
        else:
            logger.debug("USER ACTION: cancelled selection!")
            return

    def _do_configure_community_rules_db_file_path(self) -> None:
        # Input file
        logger.info("Opening file dialog to specify Community Rules DB")
        input_path = show_dialogue_file(
            mode="open",
            caption="Choose Community Rules DB",
            _dir=str(
                Path(os.path.join(GameConfiguration.instance().storage_path)).resolve()
            ),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path}")
        if input_path and os.path.exists(input_path):
            GameConfiguration.instance()._update_persistent_storage(
                {"external_community_rules_file_path": input_path}
            )
            GameConfiguration.instance().community_rules_file_path = input_path
        else:
            logger.debug("USER ACTION: cancelled selection!")
            return

    def _do_configure_steam_database_repo(self) -> None:
        """
        Opens a QDialogInput that allows user to edit their Steam DB repo
        This URL is used for Steam DB repo related actions.
        """
        args, ok = show_dialogue_input(
            title="Edit Steam DB repo",
            text="Enter URL (https://github.com/AccountName/RepositoryName):",
            value=GameConfiguration.instance().steam_db_repo,
        )
        if ok:
            GameConfiguration.instance().steam_db_repo = args
            GameConfiguration.instance()._update_persistent_storage(
                {
                    "external_steam_metadata_repo": GameConfiguration.instance().steam_db_repo
                }
            )

    def _do_configure_community_rules_db_repo(self) -> None:
        """
        Opens a QDialogInput that allows user to edit their Community Rules
        DB repo. This URL is used for Steam DB repo related actions.
        """
        args, ok = show_dialogue_input(
            title="Edit Community Rules DB repo",
            text="Enter URL (https://github.com/AccountName/RepositoryName):",
            value=GameConfiguration.instance().community_rules_repo,
        )
        if ok:
            GameConfiguration.instance().community_rules_repo = args
            GameConfiguration.instance()._update_persistent_storage(
                {
                    "external_community_rules_repo": GameConfiguration.instance().community_rules_repo
                }
            )

    def _do_build_database_thread(self) -> None:
        # If settings panel is still open, close it.
        if GameConfiguration.instance().settings_panel.isVisible():
            GameConfiguration.instance().settings_panel.close()
        # Prompt user file dialog to choose/create new DB
        logger.info("Opening file dialog to specify output file")
        output_path = show_dialogue_file(
            mode="save",
            caption="Designate output path",
            _dir=str(
                Path(os.path.join(GameConfiguration.instance().storage_path)).resolve()
            ),
            _filter="JSON (*.json)",
        )
        # Check file path and launch DB Builder with user configured mode
        if output_path:  # If output path was returned
            logger.info(f"Selected path: {output_path}")
            if not output_path.endswith(".json"):
                output_path += ".json"  # Handle file extension if needed
            # RimWorld Workshop contains 30,000+ PublishedFileIDs (mods) as of 2023!
            # "No local data": Produce accurate, complete DB by QueryFiles via WebAPI
            # Queries ALL available PublishedFileIDs (mods) it can find via Steam WebAPI.
            # Does not use metadata from locally available mods. This means no packageids!
            if GameConfiguration.instance().db_builder_include == "no_local":
                self.db_builder = SteamDatabaseBuilder(
                    apikey=GameConfiguration.instance().steam_apikey,
                    appid=294100,
                    database_expiry=GameConfiguration.instance().database_expiry,
                    mode=GameConfiguration.instance().db_builder_include,
                    output_database_path=output_path,
                    get_appid_deps=GameConfiguration.instance().build_steam_database_dlc_data_toggle,
                    update=GameConfiguration.instance().build_steam_database_update_toggle,
                )
            # "All Mods": Produce accurate, possibly semi-incomplete DB without QueryFiles via API
            # CAN produce a complete DB! Only includes metadata parsed from mods you have downloaded.
            # Produces DB which contains metadata from locally available mods. Includes packageids!
            elif GameConfiguration.instance().db_builder_include == "all_mods":
                self.db_builder = SteamDatabaseBuilder(
                    apikey=GameConfiguration.instance().steam_apikey,
                    appid=294100,
                    database_expiry=GameConfiguration.instance().database_expiry,
                    mode=GameConfiguration.instance().db_builder_include,
                    output_database_path=output_path,
                    get_appid_deps=GameConfiguration.instance().build_steam_database_dlc_data_toggle,
                    mods=self.metadata_manager.all_mods_compiled,
                    update=GameConfiguration.instance().build_steam_database_update_toggle,
                )
            # Create query runner
            self.query_runner = RunnerPanel()
            self.query_runner.closing_signal.connect(self.db_builder.terminate)
            self.query_runner.setWindowTitle(
                f"RimSort - DB Builder ({GameConfiguration.instance().db_builder_include})"
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

    def _do_blacklist_action_steamdb(self, instruction: list) -> None:
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
                self.metadata_manager.external_steam_metadata_path, "w"
            ) as output:
                json.dump(
                    {
                        "version": int(
                            time() + GameConfiguration.instance().database_expiry
                        ),
                        "database": self.metadata_manager.external_steam_metadata,
                    },
                    output,
                    indent=4,
                )
            self._do_refresh()

    def _do_download_entire_workshop(self, action: str) -> None:
        # If settings panel is still open, close it.
        if GameConfiguration.instance().settings_panel.isVisible():
            GameConfiguration.instance().settings_panel.close()
        # DB Builder is used to run DQ and grab entirety of
        # any available Steam Workshop PublishedFileIDs
        self.db_builder = SteamDatabaseBuilder(
            apikey=GameConfiguration.instance().steam_apikey,
            appid=294100,
            database_expiry=GameConfiguration.instance().database_expiry,
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
            show_warning(
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
                for metadata in self.metadata_manager.all_mods_compiled.values():
                    if metadata.get("steamcmd"):
                        mod_pfid = metadata.get("publishedfileid")
                    if mod_pfid and mod_pfid in self.db_builder.publishedfileids:
                        logger.warning(
                            f"Skipping download of existing SteamCMD mod: {mod_pfid}"
                        )
                        self.db_builder.publishedfileids.remove(mod_pfid)
                self._do_download_mods_with_steamcmd(self.db_builder.publishedfileids)
            elif "steamworks" in action:
                answer = show_dialogue_conditional(
                    title="Are you sure?",
                    text="Here be dragons.",
                    information="WARNING: It is NOT recommended to subscribe to this many mods at once via Steam. "
                    + "Steam has limitations in place seemingly intentionally and unintentionally for API subscriptions. "
                    + "It is highly recommended that you instead download these mods to a SteamCMD prefix by using SteamCMD. "
                    + "This can take longer due to rate limits, but you can also re-use the script generated by RimSort with "
                    + "a separate, authenticated instance of SteamCMD, if you do not want to anonymously download via RimSort.",
                )
                if answer == "&Yes":
                    for metadata in self.metadata_manager.all_mods_compiled.values():
                        mod_pfid = metadata.get("publishedfileid")
                        if (
                            metadata["data_source"] == "workshop"
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
        args, ok = show_dialogue_input(
            title="Edit Steam WebAPI key",
            text="Enter your personal 32 character Steam WebAPI key here:",
            value=GameConfiguration.instance().steam_apikey,
        )
        if ok:
            GameConfiguration.instance().steam_apikey = args
            GameConfiguration.instance()._update_persistent_storage(
                {"steam_apikey": GameConfiguration.instance().steam_apikey}
            )

    def _do_generate_metadata_comparison_report(self) -> None:
        """
        Open a user-selected JSON file. Calculate and display discrepencies
        found between database and this file.
        """
        # TODO: Refactor this...
        discrepancies = []
        mods = self.metadata_manager.all_mods_compiled
        database_a_deps = {}
        database_b_deps = {}
        # Notify user
        show_information(
            title="Steam DB Builder",
            text="This operation will compare 2 databases, A & B, by checking dependencies from A with dependencies from B.",
            information="- This will produce an accurate comparison of dependency data between 2 Steam DBs.\n"
            + "A report of discrepancies is generated. You will be prompted for these paths in order:\n"
            + "\n\t1) Select input A"
            + "\n\t2) Select input B",
        )
        # Input A
        logger.info("Opening file dialog to specify input file A")
        input_path_a = show_dialogue_file(
            mode="open",
            caption='Input "to-be-updated" database, input A',
            _dir=str(
                Path(os.path.join(GameConfiguration.instance().storage_path)).resolve()
            ),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path_a}")
        if input_path_a and os.path.exists(input_path_a):
            with open(input_path_a, encoding="utf-8") as f:
                json_string = f.read()
                logger.debug(f"Reading info...")
                db_input_a = json.loads(json_string)
                logger.debug("Retrieved database A...")
        else:
            logger.warning("Steam DB Builder: User cancelled selection...")
            return
        # Input B
        logger.info("Opening file dialog to specify input file B")
        input_path_b = show_dialogue_file(
            mode="open",
            caption='Input "to-be-updated" database, input A',
            _dir=str(
                Path(os.path.join(GameConfiguration.instance().storage_path)).resolve()
            ),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path_b}")
        if input_path_b and os.path.exists(input_path_b):
            with open(input_path_b, encoding="utf-8") as f:
                json_string = f.read()
                logger.debug(f"Reading info...")
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
            + f"\nTotal # of deps from database A:\n"
            + f"{database_a_total_deps}"
            + f"\nTotal # of deps from database B:\n"
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
        show_information(
            title="Steam DB Builder",
            text=f"Steam DB comparison report: {len(discrepancies)} found",
            information="Click 'Show Details' to see the full report!",
            details=report,
        )

    def _do_merge_databases(self) -> None:
        # Notify user
        show_information(
            title="Steam DB Builder",
            text="This operation will merge 2 databases, A & B, by recursively updating A with B, barring exceptions.",
            information="- This will effectively recursively overwrite A's key/value with B's key/value to the resultant database.\n"
            + "- Exceptions will not be recursively updated. Instead, they will be overwritten with B's key entirely.\n"
            + "- The following exceptions will be made:\n"
            + f"\n\t{DB_BUILDER_RECURSE_EXCEPTIONS}\n\n"
            + "The resultant database, C, is saved to a user-specified path. You will be prompted for these paths in order:\n"
            + "\n\t1) Select input A (db to-be-updated)"
            + "\n\t2) Select input B (update source)"
            + "\n\t3) Select output C (resultant db)",
        )
        # Input A
        logger.info("Opening file dialog to specify input file A")
        input_path_a = show_dialogue_file(
            mode="open",
            caption='Input "to-be-updated" database, input A',
            _dir=str(
                Path(os.path.join(GameConfiguration.instance().storage_path)).resolve()
            ),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path_a}")
        if input_path_a and os.path.exists(input_path_a):
            with open(input_path_a, encoding="utf-8") as f:
                json_string = f.read()
                logger.debug(f"Reading info...")
                db_input_a = json.loads(json_string)
                logger.debug("Retrieved database A...")
        else:
            logger.warning("Steam DB Builder: User cancelled selection...")
            return
        # Input B
        logger.info("Opening file dialog to specify input file B")
        input_path_b = show_dialogue_file(
            mode="open",
            caption='Input "to-be-updated" database, input A',
            _dir=str(
                Path(os.path.join(GameConfiguration.instance().storage_path)).resolve()
            ),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path_b}")
        if input_path_b and os.path.exists(input_path_b):
            with open(input_path_b, encoding="utf-8") as f:
                json_string = f.read()
                logger.debug(f"Reading info...")
                db_input_b = json.loads(json_string)
                logger.debug("Retrieved database B...")
        else:
            logger.debug("Steam DB Builder: User cancelled selection...")
            return
        # Output C
        db_output_c = db_input_a.copy()
        recursively_update_dict(
            db_output_c,
            db_input_b,
            prune_exceptions=DB_BUILDER_PRUNE_EXCEPTIONS,
            recurse_exceptions=DB_BUILDER_RECURSE_EXCEPTIONS,
        )
        logger.info("Updated DB A with DB B!")
        logger.debug(db_output_c)
        logger.info("Opening file dialog to specify output file")
        output_path = show_dialogue_file(
            mode="save",
            caption="Designate output path for resultant database:",
            _dir=str(
                Path(os.path.join(GameConfiguration.instance().storage_path)).resolve()
            ),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {output_path}")
        if output_path:
            if not output_path.endswith(".json"):
                path += ".json"  # Handle file extension if needed
            with open(output_path, "w", encoding="utf-8") as output:
                json.dump(db_output_c, output, indent=4)
        else:
            logger.warning("Steam DB Builder: User cancelled selection...")
            return

    def _do_update_rules_database(self, instruction: list) -> None:
        rules_source = instruction[0]
        rules_data = instruction[1]
        # Get path based on rules source
        if (
            rules_source == "Community Rules"
            and self.metadata_manager.external_community_rules_path
        ):
            path = self.metadata_manager.external_community_rules_path
        elif (
            rules_source == "User Rules"
            and GameConfiguration.instance().user_rules_file_path
        ):
            path = GameConfiguration.instance().user_rules_file_path
        else:
            logger.warning(
                f"No {rules_source} file path is set. There is no configured database to update!"
            )
            return
        # Retrieve original database
        try:
            with open(path, encoding="utf-8") as f:
                json_string = f.read()
                logger.debug(f"Reading info...")
                db_input_a = json.loads(json_string)
                logger.debug(
                    f"Retrieved copy of existing {rules_source} database to update."
                )
        except:
            logger.error("Failed to read info from existing database")
        db_input_b = {"timestamp": int(time()), "rules": rules_data}
        db_output_c = db_input_a.copy()
        # Update database in place
        recursively_update_dict(
            db_output_c,
            db_input_b,
            prune_exceptions=DB_BUILDER_PRUNE_EXCEPTIONS,
            recurse_exceptions=DB_BUILDER_RECURSE_EXCEPTIONS,
        )
        # Overwrite rules database
        answer = show_dialogue_conditional(
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
        args, ok = show_dialogue_input(
            title="Edit SteamDB expiry:",
            text="Enter your preferred expiry duration in seconds (default 1 week/604800 sec):",
            value=str(GameConfiguration.instance().database_expiry),
        )
        if ok:
            try:
                GameConfiguration.instance().database_expiry = int(args)
                GameConfiguration.instance()._update_persistent_storage(
                    {"database_expiry": GameConfiguration.instance().database_expiry}
                )
            except ValueError:
                show_warning(
                    "Tried configuring Dynamic Query with a value that is not an integer.",
                    "Please reconfigure the expiry value with an integer in terms of the seconds from epoch you would like your query to expire.",
                )
