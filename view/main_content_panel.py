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
            self.mod_info_panel.mod_list_slot
        )
        self.inactive_mods_panel.inactive_mods_list.mod_list_signal.connect(
            self.mod_info_panel.mod_list_slot
        )

        # INITIALIZE WIDGETS
        # Fetch paths dynamically from game configuration panel
        self.game_configuration = game_configuration

        # Run expensive calculations to set cache data
        self.refresh_mod_calculations()

        # Insert mod data into list
        self._insert_data_into_lists(
            self.static_active_mods_data, self.static_inactive_mods_data
        )

    @property
    def panel(self):
        return self._panel

    def refresh_mod_calculations(self) -> None:
        """
        This function contains expensive calculations for getting workshop
        mods, known expansions, community rules, and most importantly, calculating
        dependencies for all mods. It also gets a static version of active and inactive
        mods that does NOT reflect the live state of the mod lists, but can be used
        in certain cases like the "clear" action.

        This function should be called on app initialization
        and whenever the refresh button is pressed (may be after re-setting workshop
        path, mods config path, or downloading another mod).
        """
        # Get and cache workshop mods and base game / DLC data
        self.workshop_mods = get_workshop_mods(
            self.game_configuration.get_workshop_folder_path()
        )
        self.known_expansions = get_known_expansions_from_config(
            self.game_configuration.get_config_path()
        )
        for package_id in self.known_expansions.keys():
            populate_expansions_static_data(self.known_expansions, package_id)

        # Get and cache load order data
        self.community_rules = get_community_rules(self.workshop_mods)

        # Calculate and cache dependencies for ALL mods
        self.all_mods_with_dependencies = get_dependencies_for_mods(
            self.workshop_mods, self.known_expansions, self.community_rules
        )

        # Generate static list of mods
        (
            self.static_active_mods_data,
            self.static_inactive_mods_data,
        ) = get_active_inactive_mods(
            self.game_configuration.get_config_path(),
            self.all_mods_with_dependencies,
        )

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
        if action == "sort":  # User clicked on the sort button
            active_mods = self.active_mods_panel.active_mods_list.get_list_items()
            dependencies_graph = {}
            for mod in active_mods:
                dependencies_graph[mod.package_id] = set()
                if mod.dependencies:
                    for dependency in mod.dependencies:
                        dependencies_graph[mod.package_id].add(dependency)
                if mod.soft_dependencies:
                    for dependency in mod.soft_dependencies:
                        dependencies_graph[mod.package_id].add(dependency)
            # Get an ordered list of mods
            topo_result = toposort(dependencies_graph)
            # TODO: we're getting active mods twice, once in item form and once in json form.
            # Probably should just decide on one form and do processing on that.
            active_mods_json = (
                self.active_mods_panel.active_mods_list.get_list_items_by_dict()
            )
            inactive_mods_json = (
                self.inactive_mods_panel.inactive_mods_list.get_list_items_by_dict()
            )
            # Re-order active_mod_data before inserting into list
            reordered_active_mods_data = {}
            for (
                topo_level_set
            ) in (
                topo_result
            ):  # These are sets of items where dependency "level" is same
                temp_mod_dict = {}
                for item in topo_level_set:
                    if item in active_mods_json:
                        temp_mod_dict[item] = active_mods_json[item]
                # Sort by name
                sorted_temp_mod_dict = sorted(
                    temp_mod_dict.items(), key=lambda x: x[1]["name"]
                )
                for (
                    item
                ) in sorted_temp_mod_dict:  # item is tuple of (packageId, json_data)
                    reordered_active_mods_data[item[0]] = active_mods_json[item[0]]
            self._insert_data_into_lists(reordered_active_mods_data, inactive_mods_json)
        if action == "save":
            self._do_save()
        if action == "export":
            mods_config_data = xml_path_to_json(
                self.game_configuration.get_config_path()
            )
            active_mods = [
                x.package_id.lower()
                for x in self.active_mods_panel.active_mods_list.get_list_items()
            ]
            mods_config_data["ModsConfigData"]["activeMods"]["li"] = active_mods
            file_path = QFileDialog.getSaveFileName(
                caption="Save Mod List", selectedFilter="xml"
            )
            json_to_xml_write(mods_config_data, file_path[0])
        if action == "restore":
            active_mods_data, inactive_mods_data = get_active_inactive_mods(
                self.game_configuration.get_config_path(),
                self.all_mods_with_dependencies,
            )
            self._insert_data_into_lists(active_mods_data, inactive_mods_data)
        if action == "import":
            file_path = QFileDialog.getOpenFileName(
                caption="Open Mod List", filter="XML (*.xml)"
            )
            active_mods_data, inactive_mods_data = get_active_inactive_mods(
                file_path[0], self.all_mods_with_dependencies
            )
            self._insert_data_into_lists(active_mods_data, inactive_mods_data)

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
        known_expansions_ids = list(self.known_expansions.keys())
        active_mod_data = {}
        inactive_mod_data = {}
        for package_id, mod_data in self.static_active_mods_data.items():
            if package_id in known_expansions_ids:
                active_mod_data[package_id] = mod_data
            else:
                inactive_mod_data[package_id] = mod_data
        for package_id, mod_data in self.static_inactive_mods_data.items():
            if package_id in known_expansions_ids:
                active_mod_data[package_id] = mod_data
            else:
                inactive_mod_data[package_id] = mod_data
        self._insert_data_into_lists(active_mod_data, inactive_mod_data)

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
