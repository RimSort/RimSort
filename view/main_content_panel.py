import logging
from multiprocessing import active_children, Process
import os
import platform
import re
import subprocess
from threading import Thread
from typing import Any, Dict

from PySide2.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLineEdit

from sort.dependencies import *
from sort.rimpy_sort import *
from sort.topo_sort import *
from sub_view.actions_panel import Actions
from sub_view.active_mods_panel import ActiveModList
from sub_view.inactive_mods_panel import InactiveModList
from sub_view.mod_info_panel import ModInfo
from util.mods import *
from util.schema import validate_mods_config_format
from util.steam.steamcmd.wrapper import SteamcmdInterface
from util.steam.steamworks.wrapper import (
    launch_game_process,
    steamworks_subscriptions_handler,
)
from util.steam.webapi.wrapper import AppIDQuery
from util.xml import json_to_xml_write, xml_path_to_json
from view.game_configuration_panel import GameConfiguration
from window.runner_panel import RunnerPanel
from window.web_content_panel import WebContentPanel

logger = logging.getLogger(__name__)


class MainContent:
    """
    This class controls the layout and functionality of the main content
    panel of the GUI, containing the mod information display, inactive and
    active mod lists, and the action button panel. Additionally, it acts
    as the main temporary datastore of the app, caching workshop mod information
    and their dependencies.
    """

    def __init__(self, game_configuration: GameConfiguration) -> None:
        """
        Initialize the main content panel.

        :param game_configuration: game configuration panel to get paths
        """
        logger.info("Starting MainContent initialization")

        # BASE LAYOUT
        self.main_layout = QHBoxLayout()
        self.main_layout.setContentsMargins(
            5, 5, 5, 5
        )  # Space between widgets and Frame border
        # Space beteen mod lists and action buttons
        self.main_layout.setSpacing(5)

        # FRAME REQUIRED - to allow for styling
        self.main_layout_frame = QFrame()
        self.main_layout_frame.setObjectName("MainPanel")
        self.main_layout_frame.setLayout(self.main_layout)

        # INSTANTIATE WIDGETS
        logger.info("Instantiating MainContent QWidget subclasses")
        self.mod_info_panel = ModInfo()
        self.active_mods_panel = ActiveModList()
        self.inactive_mods_panel = InactiveModList()
        self.actions_panel = Actions()
        logger.info("Finished instantiating MainContent QWidget subclasses")

        # WIDGETS INTO BASE LAYOUT
        self.main_layout.addLayout(self.mod_info_panel.panel, 50)
        self.main_layout.addLayout(self.inactive_mods_panel.panel, 20)
        self.main_layout.addLayout(self.active_mods_panel.panel, 20)
        self.main_layout.addLayout(self.actions_panel.panel, 10)

        # INITIALIZE WIDGETS
        # Fetch paths dynamically from game configuration panel
        logger.info("Loading GameConfiguration instance")
        self.game_configuration = game_configuration

        # SIGNALS AND SLOTS
        self.actions_panel.actions_signal.connect(self.actions_slot)  # Actions

        self.active_mods_panel.active_mods_list.mod_info_signal.connect(
            self.mod_list_slot
        )
        self.inactive_mods_panel.inactive_mods_list.mod_info_signal.connect(
            self.mod_list_slot
        )
        self.active_mods_panel.active_mods_list.item_added_signal.connect(
            self.inactive_mods_panel.inactive_mods_list.handle_other_list_row_added
        )
        self.inactive_mods_panel.inactive_mods_list.item_added_signal.connect(
            self.active_mods_panel.active_mods_list.handle_other_list_row_added
        )
        self.active_mods_panel.active_mods_list.steamworks_subscription_signal.connect(
            self._do_steamworks_api_call
        )
        self.inactive_mods_panel.inactive_mods_list.steamworks_subscription_signal.connect(
            self._do_steamworks_api_call
        )
        self.active_mods_panel.active_mods_list.refresh_signal.connect(
            self.actions_slot
        )
        self.inactive_mods_panel.inactive_mods_list.refresh_signal.connect(
            self.actions_slot
        )
        self.game_configuration.settings_panel.metadata_by_appid_signal.connect(
            self._do_generate_metadata_by_appid
        )
        self.game_configuration.settings_panel.metadata_comparison_signal.connect(
            self._do_generate_metadata_comparison_report
        )
        self.game_configuration.settings_panel.set_webapi_query_expiry_signal.connect(
            self._do_set_webapi_query_expiry
        )

        # Restore cache initially set to empty
        self.active_mods_data_restore_state: Dict[str, Any] = {}
        self.inactive_mods_data_restore_state: Dict[str, Any] = {}

        # Set cached Dynamic Query target path
        self.cached_dynamic_query_target_path = os.path.join(
            self.game_configuration.storage_path, "steam_metadata.json"
        )

        # Store duplicate_mods for global access
        self.duplicate_mods = {}

        # State used if appworkshop metadata is parsed from Steam workshop install
        self.appworkshop_acf_data_parsed = False

        # Empty game version string unless the data is populated
        self.game_version = ""

        # Check if paths have been set
        if self.game_configuration.check_if_essential_paths_are_set():
            # Run expensive calculations to set cache data
            self.refresh_cache_calculations()

            # Insert mod data into list (is_initial = True)
            self.repopulate_lists(True)

        # Instantiate steamcmd wrapper
        self.steamcmd_wrapper = SteamcmdInterface()

        # Steamworks bool - use this to check any Steamworks processes you try to initialize
        self.steamworks_initialized = False

        logger.info("Finished MainContent initialization")

    @property
    def panel(self):
        return self._panel

    def mod_list_slot(self, uuid: str) -> None:
        """
        This slot method is triggered when the user clicks on an item
        on a mod list. It takes the internal uuid and gets the
        complete json mod info for that internal uuid. It passes
        this information to the mod info panel to display.

        :param uuid: uuid of mod
        """
        logger.info(f"USER ACTION: clicked on a mod list item: {uuid}")
        for mod_uuid in self.all_mods_with_dependencies:
            if mod_uuid == uuid:
                self.mod_info_panel.display_mod_info(
                    self.all_mods_with_dependencies[uuid]
                )
            if self.all_mods_with_dependencies[uuid].get("invalid"):
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

    def refresh_cache_calculations(self) -> None:
        """
        This function contains expensive calculations for getting workshop
        mods, known expansions, community rules, and most importantly, calculating
        dependencies for all mods.

        This function should be called on app initialization
        and whenever the refresh button is pressed (mostly after changing the workshop
        somehow, e.g. re-setting workshop path, mods config path, or downloading another mod,
        but also after ModsConfig.xml path has been changed).
        """
        logger.info("Refreshing cache calculations")

        # Get & set Rimworld version string
        self.game_version = get_game_version(
            self.game_configuration.get_game_folder_path()
        )
        self.game_configuration.game_version_line.setText(self.game_version)
        self.active_mods_panel.game_version = self.game_version

        # Get and cache installed base game / DLC data
        self.expansions = get_installed_expansions(
            self.game_configuration.get_game_folder_path(), self.game_version
        )

        # Get and cache installed local/custom mods
        self.local_mods = get_local_mods(
            self.game_configuration.get_local_folder_path()
        )

        # Get and cache installed workshop mods
        self.workshop_mods = get_workshop_mods(
            self.game_configuration.get_workshop_folder_path()
        )
        # If we can find the appworkshop_294100.acf file based on Workshop mods path,
        # then we want to parse it and add desired information for later usage
        appworkshop_path = os.path.split(
            # This is just getting the path 2 directories up from content/294100,
            # so that we can find workshop/appworkshop_294100.acf
            os.path.split(
                self.game_configuration.get_workshop_folder_path())[0]
        )[0]
        appworkshop_acf_path = os.path.join(
            appworkshop_path, "appworkshop_294100.acf")
        # If the file we want to parse exists
        if os.path.exists(appworkshop_acf_path):
            get_workshop_acf_data(
                appworkshop_acf_path, self.workshop_mods
            )  # ... get data
            logger.info(
                f"Successfully parsed Steam client appworkshop_acf metadata: {appworkshop_acf_path}"
            )
            self.appworkshop_acf_data_parsed = True
        else:
            logger.info(
                f"Unable to parse Steam client appworkshop_acf metadata")

        # Set custom tags for each data source to be used with setIcon later
        for uuid in self.expansions:
            self.expansions[uuid]["data_source"] = "expansion"
        for uuid in self.workshop_mods:
            self.workshop_mods[uuid]["data_source"] = "workshop"
        for uuid in self.local_mods:
            self.local_mods[uuid]["data_source"] = "local"

        # One working Dictionary for ALL mods
        all_mods = merge_mod_data(
            self.expansions, self.local_mods, self.workshop_mods)
        logger.info(
            f"Combined {len(self.expansions)} expansions, {len(self.local_mods)} local mods, and {len(self.workshop_mods)}. Total elements to get dependencies for: {len(all_mods)}"
        )

        # Check mods verified working with newer game-versions than defined
        # https://steamcommunity.com/sharedfiles/filedetails/?id=2599504692
        package_id_to_uuid = {}
        for mod_uuid, modmetadata in all_mods.items():
            package_id_to_uuid[modmetadata["packageId"]] = mod_uuid
        if "mlie.noversionwarning" in package_id_to_uuid.keys():
            no_version_mod = all_mods[package_id_to_uuid["mlie.noversionwarning"]]
            logger.debug(
                f"[NoVersionWarning]: No version warning-mod found - {no_version_mod}")
            version_mod_path = no_version_mod["path"]
            for file in os.scandir(version_mod_path):
                # Only look in folders
                if not file.is_dir():
                    continue
                # Only look in version-folders
                if not re.match("\d+\.\d+", file.name):
                    continue
                current_supported_version = file.name
                supported_mod_ids = get_modids_from_noversionwarning_xml(file)
                if isinstance(supported_mod_ids, str):
                    mod_id = supported_mod_ids.lower()
                    if not mod_id in package_id_to_uuid.keys():
                        continue
                    mod_uuid = package_id_to_uuid[mod_id]
                    if mod_uuid in self.local_mods.keys():
                        self.local_mods[mod_uuid] = add_more_versions_to_mod(
                            self.local_mods[mod_uuid], current_supported_version)
                    if mod_uuid in self.workshop_mods.keys():
                        self.workshop_mods[mod_uuid] = add_more_versions_to_mod(
                            self.workshop_mods[mod_uuid], current_supported_version)
                    continue
                if not isinstance(supported_mod_ids, list):
                    logger.error(
                        f"[NoVersionWarning]: supported_mod_ids value not str or list: {supported_mod_ids}")
                    continue
                for mod_id in supported_mod_ids:
                    mod_id = mod_id.lower()
                    if not mod_id in package_id_to_uuid.keys():
                        continue
                    mod_uuid = package_id_to_uuid[mod_id]
                    if mod_uuid in self.local_mods.keys():
                        self.local_mods[mod_uuid] = add_more_versions_to_mod(
                            self.local_mods[mod_uuid], current_supported_version)
                    if mod_uuid in self.workshop_mods.keys():
                        self.workshop_mods[mod_uuid] = add_more_versions_to_mod(
                            self.workshop_mods[mod_uuid], current_supported_version)
                    continue

        self.steam_db_rules = {}
        self.community_rules = {}
        self.workshop_mods_potential_updates = {}

        # If there are mods at all, check for a mod DB.
        if all_mods:
            logger.info(
                "Looking for a load order / dependency rules contained within mods"
            )
            external_metadata_source = (
                self.game_configuration.settings_panel.external_metadata_cb.currentText()
            )
            if external_metadata_source == "RimPy Mod Manager Database":
                # Get and cache RimPy Steam db.json rules data for ALL mods
                # Get and cache RimPy Community Rules communityRules.json for ALL mods
                self.steam_db_rules, self.community_rules = get_rimpy_database_mod(
                    all_mods
                )
            else:
                self.steam_db_rules, self.community_rules = get_3rd_party_metadata(
                    self.game_configuration.steam_apikey,
                    self.game_configuration.webapi_query_expiry,
                    self.cached_dynamic_query_target_path,
                    all_mods,
                )
                self.workshop_mods_potential_updates = (
                    get_external_time_data_for_workshop_mods(
                        self.steam_db_rules, all_mods
                    )
                )
        else:
            logger.warning(
                "No LOCAL or WORKSHOP mods found at all. Are you playing Vanilla?"
            )

        # Calculate and cache dependencies for ALL mods
        (
            self.all_mods_with_dependencies,
            self.info_from_steam_package_id_to_name,
        ) = get_dependencies_for_mods(
            all_mods,
            self.steam_db_rules,
            self.community_rules,  # TODO add user defined customRules from future customRules.json
        )
        # If we parsed this data from Steam client appworkshop_294100.acf
        if self.appworkshop_acf_data_parsed:
            if (
                self.game_configuration.steam_mods_update_check_toggle
            ):  # ... and the user desires this information to be displayed
                if (
                    len(self.workshop_mods_potential_updates) > 0
                ):  # ... and we have potential updates to show
                    logger.info(
                        "User preference is configured to check Steam mods for updates. Displaying potential updates..."
                    )
                    list_of_potential_updates = ""
                    for time_data in self.workshop_mods_potential_updates.values():
                        list_of_potential_updates += time_data["ui_string"]
                    show_information(
                        text="RimSort Dynamic Query: The following list of Steam mods may have updates available!",
                        information=(
                            "This metadata was parsed directly from your Steam client's workshop data, and compared with the "
                            "'time updated' metadata returned from your most recent Dynamic Query."
                            # "\nDo you want the Steam client to do a verification check of your mods now?"
                        ),
                        details=list_of_potential_updates,
                    )
            else:
                logger.debug(
                    "User preference is not configured to check Steam mods for updates. Skipping..."
                )
        # Feed all_mods and Steam DB info to Active Mods list to surface
        # names instead of package_ids when able
        self.active_mods_panel.all_mods = self.all_mods_with_dependencies
        self.active_mods_panel.steam_package_id_to_name = (
            self.info_from_steam_package_id_to_name
        )

        logger.info("Finished refreshing cache calculations")

    def repopulate_lists(self, is_initial: bool = False) -> None:
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
        ) = get_active_inactive_mods(
            self.game_configuration.get_config_path(),
            self.all_mods_with_dependencies,
            self.game_configuration.duplicate_mods_warning_toggle,
        )
        if is_initial:
            logger.info(
                "Populating mod list data for the first time, so cache it for the restore function"
            )
            self.active_mods_data_restore_state = active_mods_data
            self.inactive_mods_data_restore_state = inactive_mods_data

        self._insert_data_into_lists(active_mods_data, inactive_mods_data)

    def actions_slot(self, action: str) -> None:
        """
        Slot for the `actions_signal` signal. Depending on the action,
        either restore mod lists to the last saved state, or allow the
        user to import a mod load order into the app.

        Save: current list of active mods is written to the mods config file
        Export: current list of active mods (may or may not be equal to the list of
            mods on the mods config file) is exported in a mods config format
            to an external file. Invalid mods are not loaded into the list and so
            will not be exported.
        Restore: regenerate active and inactive mods from ModsConfig
        Import: import a mod list from a file. Does not automatically save to ModsConfig

        :param action: string indicating action
        """
        logger.info(f"USER ACTION: received action {action}")
        if action == "refresh":
            self._do_refresh()
        if action == "edit_steam_apikey":
            self._do_edit_steam_apikey()
        if action == "clear":
            self._do_clear()
        if action == "restore":
            self._do_restore()
        if action == "sort":
            self._do_sort()
        if action == "browse_workshop":
            self._do_browse_workshop()
        if action == "setup_steamcmd":
            self._do_setup_steamcmd()
        if action == "import":
            self._do_import()
        if action == "export":
            self._do_export()
        if action == "save":
            self._do_save()
        if action == "run":
            self._do_steamworks_api_call(
                [
                    "launch_game_process",
                    [
                        self.game_configuration.get_game_folder_path(),
                        self.game_configuration.run_arguments,
                    ],
                ]
            )
        if action == "edit_run_args":
            self._do_edit_run_args()

    def _do_edit_run_args(self) -> None:
        """
        Opens a QDialogInput that allows the user to edit the run args
        that are configured to be passed to the Rimworld executable
        """
        args, ok = QInputDialog().getText(
            None,
            "Edit run arguments:",
            "Enter the arguments you would like to pass to the Rimworld executable:",
            QLineEdit.Normal,
            self.game_configuration.run_arguments,
        )
        if ok:
            self.game_configuration.run_arguments = args
            self.game_configuration.update_persistent_storage(
                "runArgs", self.game_configuration.run_arguments
            )

    def _do_edit_steam_apikey(self) -> None:
        """
        Opens a QDialogInput that allows the user to edit their Steam apikey
        that are configured to be passed to the "Dynamic Query" feature for
        the Steam Workshop metadata needed for sorting
        """
        args, ok = QInputDialog().getText(
            None,
            "Edit Steam apikey:",
            "Enter your personal 32 character Steam apikey here:",
            QLineEdit.Normal,
            self.game_configuration.steam_apikey,
        )
        if ok:
            self.game_configuration.steam_apikey = args
            self.game_configuration.update_persistent_storage(
                "steam_apikey", self.game_configuration.steam_apikey
            )

    def _do_generate_metadata_by_appid(self) -> None:
        appid = 294100
        logger.info(
            f"Initializing AppIDQuery with configured Steam API key for AppID: {appid}..."
        )
        appid_query = AppIDQuery(self.game_configuration.steam_apikey, appid)
        appid_query.all_mods_metadata = appid_query._all_mods_metadata_by_appid(
            self.game_configuration.webapi_query_expiry
        )
        db_output_path = os.path.join(
            self.game_configuration.storage_path, f"{appid}_AppIDQuery.json"
        )
        logger.info(f"Caching DynamicQuery result: {db_output_path}")
        with open(db_output_path, "w") as output:
            json.dump(appid_query.all_mods_metadata, output, indent=4)

    def _do_generate_metadata_comparison_report(self) -> None:
        mods = self.all_mods_with_dependencies
        rimpy_deps = {}
        rimsort_deps = {}
        if os.path.exists(self.cached_dynamic_query_target_path):
            with open(self.cached_dynamic_query_target_path, encoding="utf-8") as f:
                json_string = f.read()
                logger.info(
                    "Reading info from cached RimSort Dynamic Query steam_metadata.json"
                )
                rimsort_steam_data = json.loads(json_string)
        else:
            show_warning("The could not find a cached RimSort Dynamic Query!")
            return
        for uuid in mods:
            if (
                mods[uuid].get("packageId") == "rupal.rimpymodmanagerdatabase"
                or mods[uuid].get("publishedfileid") == "1847679158"
            ):
                rimpy_db_json_path = os.path.join(
                    mods[uuid]["path"], "db", "db.json")
                if os.path.exists(rimpy_db_json_path):
                    with open(rimpy_db_json_path, encoding="utf-8") as f:
                        json_string = f.read()
                        logger.info(
                            "Reading info from Rimpy Mod Manager Database db.json"
                        )
                        rimpy_steam_data = json.loads(json_string)
                else:
                    show_warning(
                        "The could not find RimPy Mod Manager Database mod!")
                    return
        count = 0
        for k, v in rimsort_steam_data["database"].items():
            # print(k, v['dependencies'])
            rimsort_deps[k] = set()
            if v.get("dependencies"):
                for dep_key in v["dependencies"]:
                    rimsort_deps[k].add(dep_key)
                    count += 1
        count = 0
        for k, v in rimpy_steam_data["database"].items():
            # print(k, v['dependencies'])
            if k in rimsort_deps:
                rimpy_deps[k] = set()
                if v.get("dependencies"):
                    for dep_key in v["dependencies"]:
                        rimpy_deps[k].add(dep_key)
                        count += 1
        no_deps_str = "*no explicit dependencies listed*"
        rimsort_total_dependencies = len(rimsort_deps)
        rimpy_total_dependencies = len(rimpy_deps)
        report = (
            "#######################\nExternal metadata comparison:\n#######################"
            # + f"\nTotal # of deps from Dynamic Query: {rimsort_total_dependencies}"
            # + f"\nTotal # of deps from RimPy db.json: {rimpy_total_dependencies}"
        )
        for k, v in rimsort_deps.items():
            # If the deps are different...
            if v != rimpy_deps.get(k):
                pp = rimpy_deps.get(k)
                if pp:
                    # Normalize here (get rid of core/dlc deps)
                    pp.discard("294100")
                    pp.discard("1149640")
                    pp.discard("1392840")
                    pp.discard("1826140")
                    if v != pp:
                        if v == set():
                            v = no_deps_str
                        if pp == set():
                            pp = no_deps_str
                        mod_name = rimpy_steam_data["database"][k]["name"]
                        report += "\n\n#################"
                        report += f"\nDISCREPANCY FOUND:"
                        report += "\n#################"
                        report += f"\nMod name: {mod_name}"
                        report += f"\n\nRimSort Dynamic Query dependencies:\n{v}"
                        report += f"\n\nRimPy's Steam DB data dependencies:\n{pp}"
        show_information(
            "External metadata comparison:",
            "Click 'Show Details' to see the full report!",
            report,
        )

    def _do_set_webapi_query_expiry(self) -> None:
        """
        Opens a QDialogInput that allows the user to edit their preferred
        WebAPI Query Expiry (in seconds)
        """
        args, ok = QInputDialog().getText(
            None,
            "Edit WebAPI Query Expiry:",
            "Enter your preferred expiry duration in seconds (default 30 min/1800 sec):",
            QLineEdit.Normal,
            str(self.game_configuration.webapi_query_expiry),
        )
        if ok:
            try:
                self.game_configuration.webapi_query_expiry = int(args)
                self.game_configuration.update_persistent_storage(
                    "webapi_query_expiry", self.game_configuration.webapi_query_expiry
                )
            except ValueError:
                show_warning(
                    "Tried configuring Dynamic Query with a value that is not an integer.",
                    "Please reconfigure the expiry value with an integer in terms of the seconds from epoch you would like your query to expire.",
                )

    def _do_steamworks_api_call(self, instruction: list):
        """
        Create & launch Steamworks API process to handle instructions received from connected signals

        FOR subscription_actions[]...
        :param instruction: a list where:
            instruction[0] is a string that corresponds with the following supported_actions[]
            instruction[1] is an int that corresponds with a subscribed Steam mod's PublishedFileId
        FOR "launch_game_process"...
        :param instruction: a list where:
            instruction[0] is a string that corresponds with the following supported_actions[]
            instruction[1] is a list containing [path: str, args: str] respectively
        """
        logger.info(f"Received Steamworks API instruction: {instruction}")
        if not self.steamworks_initialized:
            self.steamworks_initialized = True
            subscription_actions = ["subscribe", "unsubscribe"]
            supported_actions = ["launch_game_process"]
            supported_actions.extend(subscription_actions)
            if (
                instruction[0] in supported_actions
            ):  # Actions can be added as functions are implemented in util.steam.steamworks.wrapper
                if instruction[0] in subscription_actions:
                    logger.info(
                        f"Creating Steamworks API process with instruction {instruction}"
                    )
                    steamworks_api_process = Process(
                        target=steamworks_subscriptions_handler, args=(
                            instruction,)
                    )
                elif instruction[0] == "launch_game_process":
                    steamworks_api_process = Process(
                        target=launch_game_process,
                        args=(instruction[1],),
                    )
            else:
                logger.error(f"Unsupported instruction {instruction}")
                return
            # Start the Steamworks API Process
            steamworks_api_process.start()
            logger.info(
                f"Steamworks API process wrapper started with PID: {steamworks_api_process.pid}"
            )
            steamworks_api_process.join()
            logger.info(
                f"Steamworks API process wrapper completed for PID: {steamworks_api_process.pid}"
            )
            self.steamworks_initialized = False
        else:
            logger.warning(
                "Steamworks API is already initialized! We do NOT want multiple interactions. Skipping instruction..."
            )

    def _do_browse_workshop(self):
        self.browser = WebContentPanel(
            "https://steamcommunity.com/app/294100/workshop/"
        )
        self.browser.show()

    def _do_setup_steamcmd(self):
        self.runner = RunnerPanel()
        self.runner.show()
        self.runner.message("Setting up steamcmd...")
        self.steamcmd_wrapper.get_steamcmd(
            self.game_configuration.get_local_folder_path(), False, self.runner
        )

    def _insert_data_into_lists(
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
        self.active_mods_panel.active_mods_list.recreate_mod_list(active_mods)
        self.inactive_mods_panel.inactive_mods_list.recreate_mod_list(
            inactive_mods)

        logger.info(
            f"Finished inserting mod data into active [{len(active_mods)}] and inactive [{len(inactive_mods)}] mod lists"
        )

    def _do_refresh(self) -> None:
        """
        Refresh expensive calculations & repopulate lists with that refreshed data
        """
        self.active_mods_panel.clear_active_mods_search()
        self.inactive_mods_panel.clear_inactive_mods_search()
        if self.game_configuration.check_if_essential_paths_are_set():
            # Run expensive calculations to set cache data
            self.refresh_cache_calculations()

            # Insert mod data into list
            self.repopulate_lists()
        else:
            self._insert_data_into_lists({}, {})
            logger.warning(
                "Essential paths have not been set. Passing refresh and resetting mod lists"
            )

    def _do_clear(self) -> None:
        """
        Method to clear all the non-base, non-DLC mods from the active
        list widget and put them all into the inactive list widget.
        """
        self.active_mods_panel.clear_active_mods_search()
        self.inactive_mods_panel.clear_inactive_mods_search()
        (
            active_mods_data,
            inactive_mods_data,
            self.duplicate_mods,
        ) = get_active_inactive_mods(
            self.game_configuration.get_config_path(),
            self.all_mods_with_dependencies,
            self.game_configuration.duplicate_mods_warning_toggle,
        )
        expansions_uuids = list(self.expansions.keys())
        active_mod_data = {}
        inactive_mod_data = {}
        logger.info(
            "Moving non-base/expansion active mods to inactive mods list")
        for uuid, mod_data in active_mods_data.items():
            if uuid in expansions_uuids:
                active_mod_data[uuid] = mod_data
            else:
                inactive_mod_data[uuid] = mod_data
        logger.info("Moving base/expansion inactive mods to active mods list")
        for uuid, mod_data in inactive_mods_data.items():
            if uuid in expansions_uuids:
                active_mod_data[uuid] = mod_data
            else:
                inactive_mod_data[uuid] = mod_data
        logger.info("Finished re-organizing mods for clear")
        self._insert_data_into_lists(active_mod_data, inactive_mod_data)

    def _do_sort(self) -> None:
        """
        Trigger sorting of all active mods using user-configured algorithm
        & all available & configured metadata
        """
        # Get the live list of active and inactive mods. This is because the user
        # will likely sort before saving.
        logger.info("Starting sorting mods")
        self.active_mods_panel.clear_active_mods_search()
        self.inactive_mods_panel.clear_inactive_mods_search()
        active_mods = self.active_mods_panel.active_mods_list.get_list_items_by_dict()
        active_mod_ids = list()
        for mod_data in active_mods.values():
            active_mod_ids.append(mod_data["packageId"])
        inactive_mods = (
            self.inactive_mods_panel.inactive_mods_list.get_list_items_by_dict()
        )

        # Get all active mods and their dependencies (if also active mod)
        dependencies_graph = gen_deps_graph(active_mods, active_mod_ids)

        # Get all active mods and their reverse dependencies
        reverse_dependencies_graph = gen_rev_deps_graph(
            active_mods, active_mod_ids)

        # Get dependencies graph for tier one mods (load at top mods)
        tier_one_dependency_graph, tier_one_mods = gen_tier_one_deps_graph(
            dependencies_graph
        )

        # Get dependencies graph for tier three mods (load at bottom mods)
        tier_three_dependency_graph, tier_three_mods = gen_tier_three_deps_graph(
            dependencies_graph, reverse_dependencies_graph
        )

        # Get dependencies graph for tier two mods (load in middle)
        tier_two_dependency_graph = gen_tier_two_deps_graph(
            active_mods, active_mod_ids, tier_one_mods, tier_three_mods
        )

        # Depending on the selected algorithm, sort all tiers with RimPy
        # mimic algorithm or toposort
        sorting_algorithm = (
            self.game_configuration.settings_panel.sorting_algorithm_cb.currentText()
        )

        if sorting_algorithm == "RimPy":
            logger.info("RimPy sorting algorithm is selected")
            reordered_tier_one_sorted_with_data = do_rimpy_sort(
                tier_one_dependency_graph, active_mods
            )
            reordered_tier_three_sorted_with_data = do_rimpy_sort(
                tier_three_dependency_graph, active_mods
            )
            reordered_tier_two_sorted_with_data = do_rimpy_sort(
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

        logger.info(
            f"Sorted tier one mods: {len(reordered_tier_one_sorted_with_data)}")
        logger.info(
            f"Sorted tier two mods: {len(reordered_tier_two_sorted_with_data)}")
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

        logger.info(
            "Finished combining all tiers of mods. Inserting into mod lists")
        self._insert_data_into_lists(combined_mods, inactive_mods)

    def _do_import(self) -> None:
        """
        Open a user-selected XML file. Calculate
        and display active and inactive lists based on this file.
        """
        logger.info("Opening file dialog to select input file")
        file_path = QFileDialog.getOpenFileName(
            caption="Open Mod List",
            dir=os.path.join(self.game_configuration.storage_path, "ModLists"),
            filter="XML (*.xml)",
        )
        logger.info(f"Selected path: {file_path[0]}")
        if file_path[0]:
            self.active_mods_panel.clear_active_mods_search()
            self.inactive_mods_panel.clear_inactive_mods_search()
            logger.info(f"Trying to import mods list from XML: {file_path}")
            (
                active_mods_data,
                inactive_mods_data,
                self.duplicate_mods,
            ) = get_active_inactive_mods(
                file_path[0],
                self.all_mods_with_dependencies,
                self.game_configuration.duplicate_mods_warning_toggle,
            )
            logger.info("Got new mods according to imported XML")
            self._insert_data_into_lists(active_mods_data, inactive_mods_data)
        else:
            logger.info("User pressed cancel, passing")

    def _do_export(self) -> None:
        """
        Export the current list of active mods to a user-designated
        file. The current list does not need to have been saved.
        """
        logger.info("Opening file dialog to specify output file")
        file_path = QFileDialog.getSaveFileName(
            caption="Save Mod List",
            dir=os.path.join(self.game_configuration.storage_path, "ModLists"),
            filter="XML (*.xml)",
        )
        logger.info(f"Selected path: {file_path[0]}")
        if file_path[0]:
            logger.info(
                "Exporting current active mods to ModsConfig.xml format")
            active_mods_json = (
                self.active_mods_panel.active_mods_list.get_list_items_by_dict()
            )
            active_mods = []
            for mod_data in active_mods_json.values():
                package_id = mod_data["packageId"]
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
            logger.info(
                "Getting current ModsConfig.xml to use as a reference format")
            mods_config_data = xml_path_to_json(
                self.game_configuration.get_config_path()
            )
            if validate_mods_config_format(mods_config_data):
                logger.info(
                    "Successfully got ModsConfig.xml data. Overwriting with current active mods"
                )
                mods_config_data["ModsConfigData"]["activeMods"]["li"] = active_mods
                logger.info(
                    f"Saving generated ModsConfig.xml to selected path: {file_path[0]}"
                )
                json_to_xml_write(mods_config_data, file_path[0])
            else:
                logger.error("Could not export active mods")
        else:
            logger.info("User pressed cancel, passing")

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
            package_id = mod_data["packageId"]
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
        mods_config_data = xml_path_to_json(
            self.game_configuration.get_config_path())
        if validate_mods_config_format(mods_config_data):
            logger.info(
                "Successfully got ModsConfig.xml data. Overwriting with current active mods"
            )
            mods_config_data["ModsConfigData"]["activeMods"]["li"] = active_mods
            json_to_xml_write(
                mods_config_data, self.game_configuration.get_config_path()
            )
        else:
            logger.error("Could not save active mods")
        logger.info("Finished saving active mods")

    def _do_restore(self) -> None:
        """
        Method to restore the mod lists to the last saved state.
        TODO: restoring after clearing will cause a few harmless lines of
        'Inactive mod count changed to: 0' to appear.
        """
        if self.active_mods_data_restore_state and self.active_mods_data_restore_state:
            self.active_mods_panel.clear_active_mods_search()
            self.inactive_mods_panel.clear_inactive_mods_search()
            logger.info(
                f"Restoring cached mod lists with active list [{len(self.active_mods_data_restore_state)}] and inactive list [{len(self.inactive_mods_data_restore_state)}]"
            )
            self._insert_data_into_lists(
                self.active_mods_data_restore_state,
                self.inactive_mods_data_restore_state,
            )
        else:
            logger.warning(
                "Cached mod lists for restore function not set as client started improperly. Passing on restore"
            )
