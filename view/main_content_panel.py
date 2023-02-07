from typing import Any, Dict

from toposort import toposort_flatten

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from util.data import (
    get_default_game_executable_path,
    get_default_mods_config_path,
    get_default_workshop_path,
)
from util.mods import get_active_inactive_mods
from util.xml import json_to_xml_write, xml_path_to_json
from view.actions_panel import Actions
from view.active_mods_panel import ActiveModList
from view.game_configuration_panel import GameConfiguration
from view.inactive_mods_panel import InactiveModList
from view.mod_info_panel import ModInfo


class MainContent:
    """
    This class controls the layout and functionality of the main content
    panel of the GUI, containing the mod information display, inactive and
    active mod lists, and the action button panel.
    """

    def __init__(self, game_configuration: GameConfiguration) -> None:
        """
        Initialize the main content panel.
        Construct the layout and add widgets.

        :param game_configuration: game configuration panel to get paths
        """
        self.game_configuration = game_configuration

        # Get default paths
        self.default_game_executable_path = get_default_game_executable_path()
        self.default_mods_config_path = get_default_mods_config_path()
        self.default_workshop_path = get_default_workshop_path()

        # Set default paths as placeholders
        self.game_configuration.game_folder_line.setPlaceholderText(
            self.default_game_executable_path
        )
        self.game_configuration.config_folder_line.setPlaceholderText(
            self.default_mods_config_path
        )
        self.game_configuration.workshop_folder_line.setPlaceholderText(
            self.default_workshop_path
        )

        # Get initial mods
        active_mods_data, inactive_mods_data = get_active_inactive_mods(
            self.game_configuration.get_mods_config_path(),
            self.game_configuration.get_workshop_folder_path(),
        )

        # Frame contains base layout to allow for styling
        self.main_layout_frame = QFrame()
        self.main_layout_frame.setObjectName("MainPanel")

        # Base layout
        self.main_layout = QHBoxLayout()
        self.main_layout.setContentsMargins(
            5, 5, 5, 5
        )  # Space between widgets and Frame border
        self.main_layout.setSpacing(5)  # Space beteen mod lists and action buttons

        # Adding layout to frame
        self.main_layout_frame.setLayout(self.main_layout)

        # Instantiate widgets
        self.mod_info_panel = ModInfo()
        self.active_mods_panel = ActiveModList(
            active_mods_data, self.game_configuration.get_mods_config_path()
        )
        self.inactive_mods_panel = InactiveModList(inactive_mods_data)
        self.actions_panel = Actions()

        # Add widgets to base layout
        self.main_layout.addLayout(self.mod_info_panel.panel, 50)
        self.main_layout.addLayout(self.inactive_mods_panel.panel, 20)
        self.main_layout.addLayout(self.active_mods_panel.panel, 20)
        self.main_layout.addLayout(self.actions_panel.panel, 10)

        # Connect signals and slots
        self.actions_panel.actions_signal.connect(self.actions_slot)
        self.actions_panel.actions_signal.connect(self.active_mods_panel.actions_slot)

    @property
    def panel(self):
        return self._panel

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
            print("clearing")
        if action == "sort":  # User clicked on the sort button
            active_mods = self.active_mods_panel.active_mods_list.get_list_items()
            dependencies = dict(
                [
                    (active_mod.package_id.lower(), set())
                    for active_mod in active_mods
                ]
            )
            for mod in active_mods:
                if mod.load_after:
                    print(mod.load_after.get("li"))
        if action == "save":
            mods_config_data = xml_path_to_json(
                self.game_configuration.get_mods_config_path()
            )
            new_active_mods_list = [
                x.package_id.lower()
                for x in self.active_mods_panel.active_mods_list.get_list_items()
            ]
            mods_config_data["ModsConfigData"]["activeMods"][
                "li"
            ] = new_active_mods_list
            json_to_xml_write(
                mods_config_data, self.game_configuration.get_mods_config_path()
            )
        if action == "export":
            mods_config_data = xml_path_to_json(
                self.game_configuration.get_mods_config_path()
            )
            new_active_mods_list = [
                x.package_id.lower()
                for x in self.active_mods_panel.active_mods_list.get_list_items()
            ]
            mods_config_data["ModsConfigData"]["activeMods"][
                "li"
            ] = new_active_mods_list
            file_path = QFileDialog.getSaveFileName(
                caption="Save Mod List", selectedFilter="xml"
            )
            json_to_xml_write(mods_config_data, file_path[0])
        if action == "restore":
            active_mods_data, inactive_mods_data = get_active_inactive_mods(
                self.game_configuration.get_mods_config_path(),
                self.game_configuration.get_workshop_folder_path(),
            )
            self._insert_data_into_lists(active_mods_data, inactive_mods_data)
        if action == "import":
            file_path = QFileDialog.getOpenFileName(
                caption="Open Mod List", filter="XML (*.xml)"
            )
            active_mods_data, inactive_mods_data = get_active_inactive_mods(
                file_path[0], self.game_configuration.get_workshop_folder_path()
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
