import logging
import os
import platform
import subprocess
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
from util.xml import json_to_xml_write, xml_path_to_json
from view.game_configuration_panel import GameConfiguration

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
        self.main_layout.setSpacing(5)  # Space beteen mod lists and action buttons

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

        # SIGNALS AND SLOTS
        self.actions_panel.actions_signal.connect(self.actions_slot)  # Actions

        self.active_mods_panel.active_mods_list.mod_info_signal.connect(
            self.mod_list_slot
        )
        self.inactive_mods_panel.inactive_mods_list.mod_info_signal.connect(
            self.mod_list_slot
        )

        # INITIALIZE WIDGETS
        # Fetch paths dynamically from game configuration panel
        logger.info("Loading GameConfiguration instance")
        self.game_configuration = game_configuration

        # Restore cache initially set to empty
        self.active_mods_data_restore_state: Dict[str, Any] = {}
        self.inactive_mods_data_restore_state: Dict[str, Any] = {}

        self.game_version = ""

        # Check if paths have been set
        if self.game_configuration.check_if_essential_paths_are_set():
            # Run expensive calculations to set cache data
            self.refresh_cache_calculations()

            # Insert mod data into list
            self.repopulate_lists(True)

        logger.info("Finished MainContent initialization")

    def mod_list_slot(self, package_id: str) -> None:
        """
        This slot method is triggered when the user clicks on an item
        on a mod list. It takes the package_id and gets the
        complete json mod info for that package_id. It passes
        this information to the mod info panel to display.

        :param package_id: package id of mod
        """
        logger.info(f"USER ACTION: clicked on a mod list item: {package_id}")
        self.mod_info_panel.display_mod_info(
            self.all_mods_with_dependencies[package_id]
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

        # Set custom tags for each data source to be used with setIcon later
        for package_id in self.expansions:
            self.expansions[package_id]["isExpansion"] = True
        for package_id in self.workshop_mods:
            self.workshop_mods[package_id]["isWorkshop"] = True
        for package_id in self.local_mods:
            self.local_mods[package_id]["isLocal"] = True

        # One working Dictionary for ALL mods
        mods = merge_mod_data(self.local_mods, self.workshop_mods)

        self.steam_db_rules = {}
        self.community_rules = {}

        # If there are mods at all, check for a mod DB.
        if mods:
            logger.info(
                "Looking for a load order / dependency rules contained within mods"
            )
            # Get and cache steam db rules data for ALL mods
            self.steam_db_rules = get_steam_db_rules(mods)
            # Get and cache community rules data for ALL mods
            self.community_rules = get_community_rules(mods)
        else:
            logger.warning(
                "No LOCAL or WORKSHOP mods found at all. Are you playing Vanilla?"
            )

        # Calculate and cache dependencies for ALL mods
        (
            self.all_mods_with_dependencies,
            self.info_from_steam_package_id_to_name,
        ) = get_dependencies_for_mods(
            self.expansions,
            mods,
            self.steam_db_rules,
            self.community_rules,  # TODO add user defined customRules from future customRules.json
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
        active_mods_data, inactive_mods_data = get_active_inactive_mods(
            self.game_configuration.get_config_path(),
            self.all_mods_with_dependencies,
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
        if action == "clear":
            self._do_clear()
        if action == "sort":
            self._do_sort()
        if action == "save":
            self._do_save()
        if action == "export":
            self._do_export()
        if action == "restore":
            self._do_restore()
        if action == "import":
            self._do_import()
        if action == "run":
            self._do_platform_specific_game_launch(
                self.game_configuration.run_arguments
            )
        if action == "edit_run_args":
            self._do_edit_run_args()

    def _do_edit_run_args(self) -> None:
        """
        Opens a QDialogInput that allows the user to edit the run args
        that are configured to be passed to the Rimworld executable

        :param path: path to open
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

    def _do_platform_specific_game_launch(self, args: str) -> None:
        """
        This function starts the Rimworld game process in it's own subprocess,
        by launching the executable found in the configured game directory.

        :param game_path: path to Rimworld game
        """
        logger.info("USER ACTION: launching the game")
        game_path = self.game_configuration.get_game_folder_path()
        logger.info(f"Attempting to find the game in the game folder {game_path}")
        if game_path:
            system_name = platform.system()
            if system_name == "Darwin":
                executable_path = os.path.join(game_path, "RimWorldMac.app")
                logger.info(
                    f"Path to game executable for MacOS generated: {executable_path}"
                )
                if os.path.exists(executable_path):
                    logger.info(
                        "Launching the game with subprocess Popen: `"
                        + executable_path
                        + "` with args: `"
                        + args
                        + "`"
                    )
                    subprocess.Popen(["open", executable_path, "--args", args])
                else:
                    logger.warning("The game executable path does not exist")
                    show_warning(
                        text="Error Starting the Game",
                        information=(
                            "RimSort could not start RimWorld as the game executable does "
                            f"not exist at the specified path: {executable_path}. Please check "
                            "that this directory is correct and the RimWorld game executable "
                            "exists in it."
                        ),
                    )
            elif system_name == "Linux" or "Windows":
                try:
                    logger.warn("Trying to create a new subprocess process group")
                    subprocess.CREATE_NEW_PROCESS_GROUP
                except AttributeError:
                    # not Windows, so assume POSIX; if not, we'll get a usable exception
                    executable_path = os.path.join(game_path, "RimWorldLinux")
                    logger.info(
                        f"Path to game executable for Linux generated: {executable_path}"
                    )
                    if os.path.exists(executable_path):
                        logger.info(
                            "Launching the game with subprocess Popen: `"
                            + executable_path
                            + "` with args: `"
                            + args
                            + "`"
                        )
                        p = subprocess.Popen(
                            [executable_path, args], start_new_session=True
                        )
                    else:
                        logger.warning("The game executable path does not exist")
                        show_warning(
                            text="Error Starting the Game",
                            information=(
                                "RimSort could not start RimWorld as the game executable does "
                                f"not exist at the specified path: {executable_path}. Please check "
                                "that this directory is correct and the RimWorld game executable "
                                "exists in it."
                            ),
                        )
                else:
                    # Windows
                    executable_path = os.path.join(game_path, "RimWorldWin64.exe")
                    logger.info(
                        f"Path to game executable for Windows generated: {executable_path}"
                    )
                    if os.path.exists(executable_path):
                        logger.info(
                            "Launching the game with subprocess Popen: `"
                            + executable_path
                            + "` with args: `"
                            + args
                            + "`"
                        )
                        p = subprocess.Popen(
                            [executable_path, args],
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                        )
                    else:
                        logger.warning("The game executable path does not exist")
                        show_warning(
                            text="Error Starting the Game",
                            information=(
                                "RimSort could not start RimWorld as the game executable does "
                                f"not exist at the specified path: {executable_path}. Please check "
                                "that this directory is correct and the RimWorld game executable "
                                "exists in it."
                            ),
                        )
            else:
                logger.error("Unable to launch the game on an unknown system")
        else:
            logger.error("The path to the game folder is empty")
            show_warning(
                text="Error Starting the Game",
                information=(
                    "RimSort could not start RimWorld as the game folder is empty or invalid: [{game_path}] "
                    "Please check that the game folder is properly set and that the RimWorld executable "
                    "exists in it."
                ),
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
        self.inactive_mods_panel.inactive_mods_list.recreate_mod_list(inactive_mods)

        logger.info(
            f"Finished inserting mod data into active [{len(active_mods)}] and inactive [{len(inactive_mods)}] mod lists"
        )

    def _do_refresh(self) -> None:
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
        active_mods_data, inactive_mods_data = get_active_inactive_mods(
            self.game_configuration.get_config_path(),
            self.all_mods_with_dependencies,
        )
        expansions_ids = list(self.expansions.keys())
        active_mod_data = {}
        inactive_mod_data = {}
        logger.info("Moving non-base/expansion active mods to inactive mods list")
        for package_id, mod_data in active_mods_data.items():
            if package_id in expansions_ids:
                active_mod_data[package_id] = mod_data
            else:
                inactive_mod_data[package_id] = mod_data
        logger.info("Moving base/expansion inactive mods to active mods list")
        for package_id, mod_data in inactive_mods_data.items():
            if package_id in expansions_ids:
                active_mod_data[package_id] = mod_data
            else:
                inactive_mod_data[package_id] = mod_data
        logger.info("Finished re-organizing mods for clear")
        self._insert_data_into_lists(active_mod_data, inactive_mod_data)

    def _do_sort(self) -> None:
        # Get the live list of active and inactive mods. This is because the user
        # will likely sort before saving.
        logger.info("Starting sorting mods")
        self.active_mods_panel.clear_active_mods_search()
        self.inactive_mods_panel.clear_inactive_mods_search()
        active_mods = self.active_mods_panel.active_mods_list.get_list_items_by_dict()
        active_mod_ids = list(active_mods.keys())
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

        logger.info(f"Sorted tier one mods: {len(reordered_tier_one_sorted_with_data)}")
        logger.info(f"Sorted tier two mods: {len(reordered_tier_two_sorted_with_data)}")
        logger.info(
            f"Sorted tier three mods: {len(reordered_tier_three_sorted_with_data)}"
        )

        # Add Tier 1, 2, 3 in order
        combined_mods = {}
        for package_id, mod_data in reordered_tier_one_sorted_with_data.items():
            combined_mods[package_id] = mod_data
        for package_id, mod_data in reordered_tier_two_sorted_with_data.items():
            combined_mods[package_id] = mod_data
        for package_id, mod_data in reordered_tier_three_sorted_with_data.items():
            combined_mods[package_id] = mod_data

        logger.info("Finished combining all tiers of mods. Inserting into mod lists")
        self._insert_data_into_lists(combined_mods, inactive_mods)

    def _do_import(self) -> None:
        """
        Open a user-selected XML file. Calculate
        and display active and inactive lists based on this file.
        """
        logger.info("Opening file dialog to select input file")
        file_path = QFileDialog.getOpenFileName(
            caption="Open Mod List", filter="XML (*.xml)"
        )
        logger.info(f"Selected path: {file_path[0]}")
        if file_path[0]:
            self.active_mods_panel.clear_active_mods_search()
            self.inactive_mods_panel.clear_inactive_mods_search()
            logger.info(f"Trying to import mods list from XML: {file_path}")
            active_mods_data, inactive_mods_data = get_active_inactive_mods(
                file_path[0], self.all_mods_with_dependencies
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
            caption="Save Mod List", selectedFilter="xml"
        )
        logger.info(f"Selected path: {file_path[0]}")
        if file_path[0]:
            logger.info("Exporting current active mods to ModsConfig.xml format")
            active_mods = [
                package_id
                for package_id in self.active_mods_panel.active_mods_list.get_list_items_by_dict()
            ]
            logger.info(f"Collected {len(active_mods)} active mods for export")
            logger.info("Getting current ModsConfig.xml to use as a reference format")
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
        active_mods = [
            package_id
            for package_id in self.active_mods_panel.active_mods_list.get_list_items_by_dict()
        ]
        logger.info(f"Collected {len(active_mods)} active mods for saving")
        mods_config_data = xml_path_to_json(self.game_configuration.get_config_path())
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
