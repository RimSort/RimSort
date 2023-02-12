from typing import Any, Dict

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
from toposort import toposort

from panel.actions_panel import Actions
from panel.active_mods_panel import ActiveModList
from panel.inactive_mods_panel import InactiveModList
from panel.mod_info_panel import ModInfo
from util.mods import *
from util.xml import json_to_xml_write, xml_path_to_json
from view.game_configuration_panel import GameConfiguration

import json

class MainContent:
    """
    This class controls the layout and functionality of the main content
    panel of the GUI, containing the mod information display, inactive and
    active mod lists, and the action button panel. Additionally, it acts
    as the main temporary datastore of the app, caching workshop mod information
    and their dependencies. <-- TODO (strip functionality from util files)
    """

    def __init__(self, game_configuration: GameConfiguration) -> None:
        """
        Initialize the main content panel.

        :param game_configuration: game configuration panel to get paths
        """
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
        self.mod_info_panel = ModInfo()
        self.active_mods_panel = ActiveModList()
        self.inactive_mods_panel = InactiveModList()
        self.actions_panel = Actions()

        # WIDGETS INTO BASE LAYOUT
        self.main_layout.addLayout(self.mod_info_panel.panel, 50)
        self.main_layout.addLayout(self.inactive_mods_panel.panel, 20)
        self.main_layout.addLayout(self.active_mods_panel.panel, 20)
        self.main_layout.addLayout(self.actions_panel.panel, 10)

        # SIGNALS AND SLOTS
        self.actions_panel.actions_signal.connect(self.actions_slot)  # Actions
        self.active_mods_panel.active_mods_list.mod_list_signal.connect(
            self.mod_list_slot
        )
        self.inactive_mods_panel.inactive_mods_list.mod_list_signal.connect(
            self.mod_list_slot
        )

        # INITIALIZE WIDGETS
        # Fetch paths dynamically from game configuration panel
        self.game_configuration = game_configuration

        # Run expensive calculations to set cache data
        self.refresh_cache_calculations()

        # Insert mod data into list
        self.repopulate_lists()

    @property
    def panel(self):
        return self._panel

    def mod_list_slot(self, package_id: str) -> None:
        """
        This slot method is triggered when the user clicks on an item
        on a mod list. It takes the package_id and gets the
        complete json mod info for that package_id. It passes
        this information to the mod info panel to display.

        :param package_id: package id of mod
        """
        print(self.all_mods_with_dependencies[package_id])
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
        # Get and cache installed base game / DLC data
        self.expansions = get_installed_expansions(
            self.game_configuration.get_game_folder_path()
        )

        for package_id in self.expansions.keys(): # hardcode names into official expansions
            if package_id == "ludeon.rimworld":
                self.expansions[package_id]["name"] = "Core (Base game)"
            if package_id == "ludeon.rimworld.royalty":
                self.expansions[package_id]["name"] = "Royalty (DLC #1)"
            if package_id == "ludeon.rimworld.ideology":
                self.expansions[package_id]["name"] = "Ideology (DLC #2)"
            if package_id == "ludeon.rimworld.biotech":
                self.expansions[package_id]["name"] = "Biotech (DLC #3)"

        # Get and cache installed local/workshop mods
        self.local_mods = get_local_mods(
            self.game_configuration.get_local_folder_path()
        )

        self.workshop_mods = get_workshop_mods(
            self.game_configuration.get_workshop_folder_path()
        )

        # One working Dictionary for ALL mods
        mods = merge_mod_data(
            self.local_mods,
            self.workshop_mods
        )

        # Get and cache steam db rules data for ALL mods
        self.steam_db_rules = get_steam_db_rules(mods)

        # Get and cache community rules data for ALL mods
        self.community_rules = get_community_rules(mods)

        # Calculate and cache dependencies for ALL mods
        self.all_mods_with_dependencies = get_dependencies_for_mods(
            self.expansions, mods, self.steam_db_rules, self.community_rules # TODO add user defined customRules from future customRules.json
        )

    def repopulate_lists(self) -> None:
        """
        Get active and inactive mod lists based on the config path
        and write them to the list widgets.
        """
        active_mods_data, inactive_mods_data = get_active_inactive_mods(
            self.game_configuration.get_config_path(),
            self.all_mods_with_dependencies,
        )
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
            print("RUN")

    def _insert_data_into_lists(
        self, active_mods: Dict[str, Any], inactive_mods: Dict[str, Any]
    ) -> None:
        """
        Insert active mods and inactive mods into respective mod list widgets.

        :param active_mods: dict of active mods
        :param inactive_mods: dict of inactive mods
        """
        self.active_mods_panel.active_mods_list.recreate_mod_list(active_mods)
        self.inactive_mods_panel.inactive_mods_list.recreate_mod_list(inactive_mods)

    def _do_clear(self) -> None:
        """
        Method to clear all the non-base, non-DLC mods from the active
        list widget and put them all into the inactive list widget.
        """
        active_mods_data, inactive_mods_data = get_active_inactive_mods(
            self.game_configuration.get_config_path(),
            self.all_mods_with_dependencies,
        )
        expansions_ids = list(self.expansions.keys())
        active_mod_data = {}
        inactive_mod_data = {}
        for package_id, mod_data in active_mods_data.items():
            if package_id in expansions_ids:
                active_mod_data[package_id] = mod_data
            else:
                inactive_mod_data[package_id] = mod_data
        for package_id, mod_data in inactive_mods_data.items():
            if package_id in expansions_ids:
                active_mod_data[package_id] = mod_data
            else:
                inactive_mod_data[package_id] = mod_data
        self._insert_data_into_lists(active_mod_data, inactive_mod_data)

    def _do_sort(self) -> None:
        """
        Sort the active mods list by dependencies and prioritizing alphabetical
        order within topological levels.

        TODO: we are getting mod items in two forms, one with its class definitions,
            and once again but only its json data. This is semi redundant and a waste of
            space. Consider refactoring so that each mod item just uses json data.
        """
        # Get the live list of active and inactive mods. This is because the user
        # will likely sort before saving. This is not meant to be used until later
        # but is useful for getting the ids of the active mods.
        active_mods_json = (
            self.active_mods_panel.active_mods_list.get_list_items_by_dict()
        )
        inactive_mods_json = (
            self.inactive_mods_panel.inactive_mods_list.get_list_items_by_dict()
        )

        # Get all active mods and their dependencies
        dependencies_graph = {}  # Schema: {item: {dependency1, dependency2, ...}}
        active_mods = self.active_mods_panel.active_mods_list.get_list_items()
        active_mod_ids = list(active_mods_json.keys())
        for mod in active_mods:
            dependencies_graph[mod.package_id] = set()
            if mod.dependencies:  # Will either be None, or a set
                for dependency in mod.dependencies:
                    # Only add a dependency if dependency exists in active_mods
                    # (related to comment about stripping dependencies)
                    if dependency in active_mod_ids:
                        dependencies_graph[mod.package_id].add(dependency)

        print(dependencies_graph)

        # Run topological sort
        # The result is a list of sets; each set contains topologically-equivalent items
        topo_result = toposort(dependencies_graph)

        print(topo_result)

        # Reorder active mods alphabetically by their topological level before
        # submitting the list back into the widget
        reordered_active_mods_data = {}
        for level in topo_result:
            temp_mod_dict = {}
            for package_id in level:
                # Previously, this was needed because the toposort produces elements for
                # all package ids referenced in the dependencies graph. However, now
                # we're stripping dependencies not in active mods
                # -- if package_id in active_mods_json: --
                temp_mod_dict[package_id] = active_mods_json[package_id]
            # Sort packages in this topological level by name
            sorted_temp_mod_dict = sorted(
                temp_mod_dict.items(), key=lambda x: x[1]["name"], reverse=False
            )
            # sorted_mod is tuple of (packageId, json_data)
            # Add into reordered_active_mods_data (dicts are ordered now)
            for sorted_mod in sorted_temp_mod_dict:
                reordered_active_mods_data[sorted_mod[0]] = active_mods_json[
                    sorted_mod[0]
                ]
        self._insert_data_into_lists(reordered_active_mods_data, inactive_mods_json)

    def _do_import(self) -> None:
        """
        Open a user-selected XML file. Calculate
        and display active and inactive lists based on this file.
        """
        file_path = QFileDialog.getOpenFileName(
            caption="Open Mod List", filter="XML (*.xml)"
        )
        active_mods_data, inactive_mods_data = get_active_inactive_mods(
            file_path[0], self.all_mods_with_dependencies
        )
        self._insert_data_into_lists(active_mods_data, inactive_mods_data)

    def _do_export(self) -> None:
        """
        Export the current list of active mods to a user-designated
        file. The current list does not need to have been saved.
        """
        active_mods = [
            mod_item.package_id.lower()
            for mod_item in self.active_mods_panel.active_mods_list.get_list_items()
        ]
        mods_config_data = xml_path_to_json(self.game_configuration.get_config_path())
        mods_config_data["ModsConfigData"]["activeMods"]["li"] = active_mods
        file_path = QFileDialog.getSaveFileName(
            caption="Save Mod List", selectedFilter="xml"
        )
        json_to_xml_write(mods_config_data, file_path[0])

    def _do_save(self) -> None:
        """
        Method save the current list of active mods to the selected ModsConfig.xml
        """
        active_mods = [
            mod_item.package_id.lower()
            for mod_item in self.active_mods_panel.active_mods_list.get_list_items()
        ]
        mods_config_data = xml_path_to_json(self.game_configuration.get_config_path())
        mods_config_data["ModsConfigData"]["activeMods"]["li"] = active_mods
        json_to_xml_write(mods_config_data, self.game_configuration.get_config_path())

    def _do_restore(self) -> None:
        """
        Method to restore the mod lists to the last saved state.
        """
        self.repopulate_lists()
