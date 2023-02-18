import logging
from typing import Any, Dict

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from sortedcontainers import SortedList

from model.mod_list import ModListWidget

logger = logging.getLogger(__name__)


class ActiveModList:
    """
    This class controls the layout and functionality for the
    active mods list panel on the GUI.
    """

    def __init__(self) -> None:
        """
        Initialize the class.
        Create a ListWidget using the dict of mods. This will
        create a row for every key-value pair in the dict.
        """
        logger.info("Starting ActiveModList initialization")

        # Base layout type
        self.panel = QVBoxLayout()

        # Instantiate widgets
        self.num_mods = QLabel("Active [0]")
        self.num_mods.setAlignment(Qt.AlignCenter)
        self.num_mods.setObjectName("summaryValue")

        self.active_mods_list = ModListWidget()

        self.active_mods_search = QLineEdit()
        self.active_mods_search.setClearButtonEnabled(True)
        self.active_mods_search.textChanged.connect(self.signal_active_mods_search)
        self.active_mods_search_clear_button = self.active_mods_search.findChild(
            QToolButton
        )
        self.active_mods_search_clear_button.setEnabled(True)
        self.active_mods_search_clear_button.clicked.connect(
            self.clear_active_mods_search
        )
        self.active_mods_search.setPlaceholderText("Search active mods...")

        # Add widgets to base layout
        self.panel.addWidget(self.num_mods)
        self.panel.addWidget(self.active_mods_search)
        self.panel.addWidget(self.active_mods_list)

        # Tracking mod list
        self.tracking_active_mods = {}

        # Adding Completer.
        # self.completer = QCompleter(self.active_mods_list.get_list_items())
        # self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        # self.active_mods_search.setCompleter(self.completer)

        # Connect signals and slots
        self.active_mods_list.list_update_signal.connect(
            self.handle_internal_mod_list_updated
        )

        logger.info("Finished ActiveModList initialization")

    def recreate_mod_list(self, mods: Dict[str, Any]) -> None:
        """
        Indicates that a new tracking mod list dist should
        be created and attached to this class. This tracking dict
        should keep track of: the mods that are included in the
        actual child mod list, in ORDER. Directly supports the search
        function as a fall-back 'full' mod list.

        Then, calls function on child mod list to actually clear mods
        and add new ones from the dict.

        :param mods: dict of mod data
        """
        logger.info("Externally re-creating active tracking mod list")
        self.tracking_active_mods = mods  # TODO unused at the moment, maybe don't need
        self.active_mods_list.recreate_mod_list(mods)

    def recalculate_internal_list_errors(self):
        # TODO: resume
        # TODO: optimization needed. This function is called n times for
        # inserting n mods (e.g. refresh action). It's also called twice when
        # moving a mod from inactive to active.
        # TODO: need to test and commit
        mods = self.active_mods_list.get_list_items_by_dict()
        package_ids_set = set(mods.keys())  # set of package_ids to use for calculations
        package_id_to_index = {}  # package_id <-> the position it is in
        package_id_to_errors = {}  # package_id <-> live errors it has
        count = 0
        for package_id in mods:
            package_id_to_index[package_id] = count
            print(package_id, count)
            count = count + 1
        print()

        for package_id, mod_data in mods.items():
            # Instantiate empty key value
            package_id_to_errors[package_id] = {
                "missing_dependencies": set(),
                "conflicting_incompatibilities": set(),
                "load_before_violations": set(),
                "load_after_violations": set(),
            }

            # Check dependencies
            if mod_data.get("dependencies"):
                for dependency in mod_data["dependencies"]:
                    if dependency not in package_ids_set:
                        package_id_to_errors[package_id]["missing_dependencies"].add(
                            dependency
                        )

            # Check incompatibilities
            if mod_data.get("incompatibilities"):
                for incompatibility in mod_data["incompatibilities"]:
                    if incompatibility in package_ids_set:
                        package_id_to_errors[package_id][
                            "conflicting_incompatibilities"
                        ].add(incompatibility)

            # Check loadTheseBefore
            if mod_data.get("loadTheseBefore"):
                current_mod_index = package_id_to_index[package_id]
                for load_this_before in mod_data["loadTheseBefore"]:
                    # Note: we cannot use package_id_to_index.get(load_this_before) as 0 is falsy but valid
                    if load_this_before in package_id_to_index:
                        if current_mod_index <= package_id_to_index[load_this_before]:
                            package_id_to_errors[package_id][
                                "load_before_violations"
                            ].add(load_this_before)

            # Check loadTheseAfter
            if mod_data.get("loadTheseAfter"):
                current_mod_index = package_id_to_index[package_id]
                for load_this_after in mod_data["loadTheseAfter"]:
                    if load_this_after in package_id_to_index:
                        if current_mod_index >= package_id_to_index[load_this_after]:
                            package_id_to_errors[package_id][
                                "load_after_violations"
                            ].add(load_this_after)
            print(package_id_to_errors[package_id], package_id)
        print()



    def handle_internal_mod_list_updated(self, count: str) -> None:
        # 'drop' indicates that the update was just a drag and drop
        # within the list.
        if count != "drop":
            logger.info(f"Active mod count changed to: {count}")
            self.num_mods.setText(f"Active [{count}]")

        self.recalculate_internal_list_errors()

    def clear_active_mods_search(self):
        print("cleared")
        # self.active_mods_search.setText("")
        # for mod_item in self.active_mods_list.get_list_items():
        #     mod_item.show()

    def signal_active_mods_search(self, pattern: str) -> None:
        print(pattern)
        # if pattern == "":
        #     self.clear_active_mods_search()
        # else:
        #     for mod_item in self.active_mods_list.get_list_items():
        #         if not pattern.lower() in mod_item.name.lower():
        #             mod_item.hide()
