import logging
from typing import Any, Dict

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from sortedcontainers import SortedList

from model.mod_list import ModListWidget

logger = logging.getLogger(__name__)


class ActiveModList(QWidget):
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

        super(ActiveModList, self).__init__()

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

        self.errors_summary_frame = QFrame()
        self.errors_summary_frame.setObjectName("errorFrame")
        self.errors_summary_layout = QHBoxLayout()
        self.errors_summary_layout.setContentsMargins(0,0,0,0)
        self.errors_summary_layout.setSpacing(2)
        self.warnings_icon = QLabel()
        self.warnings_icon.setPixmap(
            self.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(QSize(20, 20))
        )
        self.warnings_text = QLabel("0 warnings(s)")
        self.errors_icon = QLabel()
        self.errors_icon.setPixmap(
            self.style().standardIcon(QStyle.SP_MessageBoxCritical).pixmap(QSize(20, 20))
        )
        self.errors_text = QLabel("0 error(s)")

        self.warnings_layout = QHBoxLayout()
        self.warnings_layout.addWidget(self.warnings_icon, 1)
        self.warnings_layout.addWidget(self.warnings_text, 99)

        self.errors_layout = QHBoxLayout()
        self.errors_layout.addWidget(self.errors_icon, 1)
        self.errors_layout.addWidget(self.errors_text, 99)

        self.errors_summary_layout.addLayout(self.warnings_layout, 50)
        self.errors_summary_layout.addLayout(self.errors_layout, 50)

        self.errors_summary_frame.setLayout(self.errors_summary_layout)
        self.errors_summary_frame.setHidden(True)

        # Add widgets to base layout
        self.panel.addWidget(self.num_mods, 1)
        self.panel.addWidget(self.active_mods_search, 1)
        self.panel.addWidget(self.active_mods_list, 97)
        self.panel.addWidget(self.errors_summary_frame, 1)

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
        """
        Whenever the active mod list has items added to it,
        or has items removed from it, or has items rearranged around within it,
        calculate, for every mod contained within the list, their
        """
        # TODO: optimization needed. This function is called n times for
        # inserting n mods (e.g. refresh action). It's also called twice when
        # moving a mod from inactive to active.
        active_mods = self.active_mods_list.get_list_items_by_dict()
        package_ids_set = set(
            active_mods.keys()
        )  # set of package_ids to use for calculations
        package_id_to_index = {}  # package_id <-> the position it is in
        package_id_to_errors = {}  # package_id <-> live errors it has
        count = 0
        for package_id in active_mods:
            package_id_to_index[package_id] = count
            count = count + 1

        # For every active mod, find its various errors
        # At the end of every loop, also determine whether the mod
        # has issues, and if so, set the appropriate icon. Keep track
        # of how many mods have issues for the summary widget.
        num_warnings = 0
        total_warning_text = ""
        num_errors = 0
        total_error_text = ""
        for package_id, mod_data in active_mods.items():
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

            # Consolidate results
            tool_tip_text = ""
            missing_dependencies = package_id_to_errors[package_id][
                "missing_dependencies"
            ]
            if missing_dependencies:
                tool_tip_text += "\nMissing Dependencies:"
                for dependency_id in missing_dependencies:
                    tool_tip_text += f"\n  * {dependency_id}"

            conflicting_incompatibilities = package_id_to_errors[package_id][
                "conflicting_incompatibilities"
            ]
            if conflicting_incompatibilities:
                tool_tip_text += "\nIncompatibilities:"
                for incompatibility_id in conflicting_incompatibilities:
                    incompatibility_name = active_mods[incompatibility_id]["name"]
                    tool_tip_text += f"\n  * {incompatibility_name}"

            load_before_violations = package_id_to_errors[package_id][
                "load_before_violations"
            ]
            if load_before_violations:
                tool_tip_text += "\nShould be Loaded After:"
                for load_before_id in load_before_violations:
                    load_before_name = active_mods[load_before_id]["name"]
                    tool_tip_text += f"\n  * {load_before_name}"

            load_after_violations = package_id_to_errors[package_id][
                "load_after_violations"
            ]
            if load_after_violations:
                tool_tip_text += "\nShould be Loaded Before:"
                for load_after_id in load_after_violations:
                    load_after_name = active_mods[load_after_id]["name"]
                    tool_tip_text += f"\n  * {load_after_name}"
            
            # Set icon if necessary
            current_package_index = package_id_to_index[package_id]
            item_widget_at_index = self.active_mods_list.get_item_widget_at_index(
                current_package_index
            )
            if item_widget_at_index:
                if tool_tip_text:
                    item_widget_at_index.warning_icon_label.setHidden(False)
                    item_widget_at_index.warning_icon_label.setToolTip(
                        tool_tip_text.lstrip()
                    )
                else:
                    item_widget_at_index.warning_icon_label.setHidden(True)
                    item_widget_at_index.warning_icon_label.setToolTip("")
            
            # Add to error/warnings summary if necessary
            if missing_dependencies or conflicting_incompatibilities:
                num_errors += 1
                total_error_text += f"\n\n{active_mods[package_id]['name']}"
                total_error_text += "\n============================="
                total_error_text += tool_tip_text
            elif load_before_violations or load_after_violations:
                num_warnings += 1
                total_warning_text += f"\n\n{active_mods[package_id]['name']}"
                total_warning_text += "\n============================="
                total_warning_text += tool_tip_text
        
        if total_error_text or total_warning_text or num_errors or num_warnings:
            self.errors_summary_frame.setHidden(False)
            self.warnings_text.setText(f"{num_warnings} warnings(s)")
            self.errors_text.setText(f"{num_errors} errors(s)")
            if total_error_text:
                self.errors_icon.setToolTip(total_error_text.lstrip())
            if total_warning_text:
                self.warnings_icon.setToolTip(total_warning_text.lstrip())
        else:
            self.errors_summary_frame.setHidden(True)
            self.warnings_text.setText("0 warnings(s)")
            self.errors_text.setText("0 errors(s)")
            if total_error_text:
                self.errors_icon.setToolTip("")
            if total_warning_text:
                self.warnings_icon.setToolTip("")

            

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
