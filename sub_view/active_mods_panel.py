from logger_tt import logger
import os
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from model.mod_list import ModListWidget
from model.mod_list_item import ModListItemInner


class ActiveModList(QWidget):
    """
    This class controls the layout and functionality for the
    active mods list panel on the GUI.
    """

    list_updated_signal = Signal()

    def __init__(self) -> None:
        """
        Initialize the class.
        Create a ListWidget using the dict of mods. This will
        create a row for every key-value pair in the dict.
        """
        logger.info("Starting ActiveModList initialization")
        self.list_updated = False

        super(ActiveModList, self).__init__()

        # Base layout type
        self.panel = QVBoxLayout()

        # Instantiate widgets
        self.num_mods = QLabel("Active [0]")
        self.num_mods.setAlignment(Qt.AlignCenter)
        self.num_mods.setObjectName("summaryValue")

        # Search widgets
        self.active_mods_search_layout = QHBoxLayout()
        self.active_mods_search_filter_state = True
        self.active_mods_search_mode_filter_icon = QIcon(
            os.path.join(os.path.dirname(__file__), "../data/filter.png")
        )
        self.active_mods_search_mode_nofilter_icon = QIcon(
            os.path.join(os.path.dirname(__file__), "../data/nofilter.png")
        )
        self.active_mods_search_mode_filter_button = QToolButton()
        self.active_mods_search_mode_filter_button.setIcon(
            self.active_mods_search_mode_filter_icon
        )
        self.active_mods_search = QLineEdit()
        self.active_mods_search.setClearButtonEnabled(True)
        self.active_mods_search.textChanged.connect(self.signal_active_mods_search)
        self.active_mods_search_mode_filter_button.clicked.connect(
            self.signal_active_mods_search_filter_toggle
        )
        self.active_mods_search.setPlaceholderText("Search by...")
        self.active_mods_search_clear_button = self.active_mods_search.findChild(
            QToolButton
        )
        self.active_mods_search_clear_button.setEnabled(True)
        self.active_mods_search_clear_button.clicked.connect(
            self.clear_active_mods_search
        )
        self.active_mods_search_filter = QComboBox()
        self.active_mods_search_filter.setObjectName("MainUI")
        self.active_mods_search_filter.setMaximumWidth(125)
        self.active_mods_search_filter.addItems(
            ["Name", "PackageId", "Author(s)", "PublishedFileId"]
        )
        self.active_mods_search_layout.addWidget(
            self.active_mods_search_mode_filter_button
        )
        self.active_mods_search_layout.addWidget(self.active_mods_search, 35)
        self.active_mods_search_layout.addWidget(self.active_mods_search_filter, 70)

        # Active mod list
        self.active_mods_list = ModListWidget()

        # Errors/warnings
        self.errors_summary_frame = QFrame()
        self.errors_summary_frame.setObjectName("errorFrame")
        self.errors_summary_layout = QHBoxLayout()
        self.errors_summary_layout.setContentsMargins(0, 0, 0, 0)
        self.errors_summary_layout.setSpacing(2)
        self.warnings_icon = QLabel()
        self.warnings_icon.setPixmap(
            self.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(QSize(20, 20))
        )
        self.warnings_text = QLabel("0 warnings(s)")
        self.warnings_text.setObjectName("summaryValue")
        self.errors_icon = QLabel()
        self.errors_icon.setPixmap(
            self.style()
            .standardIcon(QStyle.SP_MessageBoxCritical)
            .pixmap(QSize(20, 20))
        )
        self.errors_text = QLabel("0 error(s)")
        self.errors_text.setObjectName("summaryValue")

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
        self.panel.addLayout(self.active_mods_search_layout, 1)
        self.panel.addWidget(self.active_mods_list, 97)
        self.panel.addWidget(self.errors_summary_frame, 1)

        # Adding Completer.
        # self.completer = QCompleter(self.active_mods_list.get_list_items())
        # self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        # self.active_mods_search.setCompleter(self.completer)

        self.game_version = ""
        self.all_mods: dict[str, Any] = {}
        self.steam_package_id_to_name: dict[str, Any] = {}

        # Connect signals and slots
        self.active_mods_list.list_update_signal.connect(
            self.handle_internal_mod_list_updated
        )
        logger.info("Finished ActiveModList initialization")

    def recalculate_internal_list_errors(self) -> None:
        """
        Whenever the active mod list has items added to it,
        or has items removed from it, or has items rearranged around within it,
        calculate, for every mod contained within the list, their
        """
        # TODO: optimization needed. This function is called n times for
        # inserting n mods (e.g. refresh action). It's also called twice when
        # moving a mod from inactive to active.
        logger.info("Recalculating internal list errors")
        active_mods = self.active_mods_list.get_list_items_by_dict()
        packageId_to_uuid = {}  # uuid <-> the unique mod's packageId
        uuid_to_index = {}  # uuid <-> the position it is in
        count = 0
        package_id_to_errors = {}  # package_id <-> live errors it has
        package_ids_set = set()  # empty set for package_ids to use for calculations

        for (
            uuid,
            mod_data,
        ) in active_mods.items():  # add package_id from active mod data
            package_id = mod_data["packageId"]
            package_ids_set.add(package_id)
            packageId_to_uuid[package_id] = uuid
            uuid_to_index[uuid] = count
            count = count + 1

        # For every active mod, find its various errors
        # At the end of every loop, also determine whether the mod
        # has issues, and if so, set the appropriate icon. Keep track
        # of how many mods have issues for the summary widget.
        num_warnings = 0
        total_warning_text = ""
        num_errors = 0
        total_error_text = ""
        for uuid, mod_data in active_mods.items():
            # Instantiate empty key value
            package_id_to_errors[uuid] = {
                "missing_dependencies": set(),
                "conflicting_incompatibilities": set(),
                "load_before_violations": set(),
                "load_after_violations": set(),
                "version_mismatch": True,
            }

            # Check version
            if self.game_version:
                if "supportedVersions" in mod_data:
                    if "li" in mod_data["supportedVersions"]:
                        supported_versions = mod_data["supportedVersions"]["li"]
                        # supported_versions is either a string or list of strings
                        if isinstance(supported_versions, str):
                            if self.game_version.startswith(supported_versions):
                                package_id_to_errors[uuid]["version_mismatch"] = False
                        elif isinstance(supported_versions, list):
                            is_supported = False
                            for supported_version in supported_versions:
                                if isinstance(supported_version, str):
                                    if self.game_version.startswith(supported_version):
                                        is_supported = True
                                else:
                                    logger.error(
                                        f"supportedVersion in list is not str: {supported_versions}"
                                    )
                            if (
                                is_supported
                                or mod_data["packageId"]
                                in self.active_mods_list.ignore_warning_list
                            ):
                                package_id_to_errors[uuid]["version_mismatch"] = False
                        else:
                            logger.error(
                                f"supportedVersions value not str or list: {supported_versions}"
                            )
                    else:
                        logger.error(
                            f"No li tag found in supportedVersions value: {mod_data['supportedVersions']}"
                        )
                else:
                    logger.error(
                        f"No supportedVersions key found in mod data: {mod_data}"
                    )
            if (
                mod_data.get("packageId")
                and not mod_data["packageId"]
                in self.active_mods_list.ignore_warning_list
            ):
                # Check dependencies
                if mod_data.get("dependencies"):
                    for dependency in mod_data["dependencies"]:
                        if dependency not in package_ids_set:
                            package_id_to_errors[uuid]["missing_dependencies"].add(
                                dependency
                            )

                # Check dependencies
                if mod_data.get("dependencies"):
                    for dependency in mod_data["dependencies"]:
                        if dependency not in package_ids_set:
                            package_id_to_errors[uuid]["missing_dependencies"].add(
                                dependency
                            )

                # Check incompatibilities
                if mod_data.get("incompatibilities"):
                    for incompatibility in mod_data["incompatibilities"]:
                        if incompatibility in package_ids_set:
                            package_id_to_errors[uuid][
                                "conflicting_incompatibilities"
                            ].add(incompatibility)

                # Check loadTheseBefore
                if mod_data.get("loadTheseBefore"):
                    current_mod_index = uuid_to_index[uuid]
                    for load_this_before in mod_data["loadTheseBefore"]:
                        if not isinstance(load_this_before, tuple):
                            logger.error(
                                f"Expected load order rule to be a tuple: [{load_this_before}]"
                            )
                        # Only if explict_bool = True then we show error
                        if load_this_before[1]:
                            # Note: we cannot use uuid_to_index.get(load_this_before) as 0 is falsy but valid
                            if load_this_before[0] in packageId_to_uuid:
                                if (
                                    current_mod_index
                                    <= uuid_to_index[
                                        packageId_to_uuid[load_this_before[0]]
                                    ]
                                ):
                                    package_id_to_errors[uuid][
                                        "load_before_violations"
                                    ].add(load_this_before[0])

                # Check loadTheseAfter
                if mod_data.get("loadTheseAfter"):
                    current_mod_index = uuid_to_index[uuid]
                    for load_this_after in mod_data["loadTheseAfter"]:
                        if not isinstance(load_this_after, tuple):
                            logger.error(
                                f"Expected load order rule to be a tuple: [{load_this_after}]"
                            )
                        # Only if explict_bool = True then we show error
                        if load_this_after[1]:
                            if load_this_after[0] in packageId_to_uuid:
                                if (
                                    current_mod_index
                                    >= uuid_to_index[
                                        packageId_to_uuid[load_this_after[0]]
                                    ]
                                ):
                                    package_id_to_errors[uuid][
                                        "load_after_violations"
                                    ].add(load_this_after[0])

            # Consolidate results
            self.ignore_error = self.active_mods_list.ignore_warning_list
            error_tool_tip_text = ""
            warning_tool_tip_text = ""
            missing_dependencies = package_id_to_errors[uuid]["missing_dependencies"]
            if missing_dependencies:
                error_tool_tip_text += "\n\nMissing Dependencies:"
                for dependency_id in missing_dependencies:
                    # If dependency is installed, we can get its name
                    if dependency_id in mod_data["packageId"]:
                        error_tool_tip_text += f"\n  * {self.all_mods[uuid]['name']}"
                    # Otherwise, we might be able to get it from RimPy Steam DB
                    elif dependency_id in self.steam_package_id_to_name:
                        error_tool_tip_text += (
                            f"\n  * {self.steam_package_id_to_name[dependency_id]}"
                        )
                    # Other-otherwise, just use the id
                    else:
                        error_tool_tip_text += f"\n  * {dependency_id}"

            conflicting_incompatibilities = package_id_to_errors[uuid][
                "conflicting_incompatibilities"
            ]
            if conflicting_incompatibilities:
                error_tool_tip_text += "\n\nIncompatibilities:"
                for incompatibility_id in conflicting_incompatibilities:
                    incompatibility_uuid = packageId_to_uuid[incompatibility_id]
                    incompatibility_name = active_mods[incompatibility_uuid]["name"]
                    error_tool_tip_text += f"\n  * {incompatibility_name}"

            load_before_violations = package_id_to_errors[uuid][
                "load_before_violations"
            ]
            if load_before_violations:
                warning_tool_tip_text += "\n\nShould be Loaded After:"
                for load_before_id in load_before_violations:
                    load_before_uuid = packageId_to_uuid[load_before_id]
                    load_before_name = active_mods[load_before_uuid]["name"]
                    warning_tool_tip_text += f"\n  * {load_before_name}"

            load_after_violations = package_id_to_errors[uuid]["load_after_violations"]
            if load_after_violations:
                warning_tool_tip_text += "\n\nShould be Loaded Before:"
                for load_after_id in load_after_violations:
                    load_after_uuid = packageId_to_uuid[load_after_id]
                    load_after_name = active_mods[load_after_uuid]["name"]
                    warning_tool_tip_text += f"\n  * {load_after_name}"

            version_mismatch = package_id_to_errors[uuid]["version_mismatch"]
            if version_mismatch and not self.ignore_error:
                warning_tool_tip_text += "\n\nMod and Game Version Mismatch"

            # Set icon if necessary
            current_package_index = uuid_to_index[uuid]
            item_widget_at_index = self.active_mods_list.get_item_widget_at_index(
                current_package_index
            )
            # Set icon tooltip
            if item_widget_at_index is not None:
                if warning_tool_tip_text or error_tool_tip_text:
                    item_widget_at_index.warning_icon_label.setHidden(False)
                    tool_tip_text = error_tool_tip_text + warning_tool_tip_text
                    item_widget_at_index.warning_icon_label.setToolTip(
                        tool_tip_text.lstrip()
                    )
                else:
                    item_widget_at_index.warning_icon_label.setHidden(True)
                    item_widget_at_index.warning_icon_label.setToolTip("")

            # Add to error/warnings summary if necessary
            if missing_dependencies or conflicting_incompatibilities:
                num_errors += 1
                total_error_text += f"\n\n{active_mods[uuid]['name']}"
                total_error_text += "\n============================="
                total_error_text += error_tool_tip_text.replace("\n\n", "\n")
            if load_before_violations or load_after_violations or version_mismatch:
                num_warnings += 1
                total_warning_text += f"\n\n{active_mods[uuid]['name']}"
                total_warning_text += "\n============================="
                total_warning_text += warning_tool_tip_text.replace("\n\n", "\n")

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
        logger.info("Finished recalculating internal list errors")

    def handle_internal_mod_list_updated(self, count: str) -> None:
        # First time, and when Refreshing, the slot will evaluate false and do nothing.
        # The purpose of this is for the _do_save_animation slot in the main_content_panel
        self.list_updated_signal.emit()
        self.list_updated = True
        # 'drop' indicates that the update was just a drag and drop
        # within the list.
        if count != "drop":
            logger.info(f"Active mod count changed to: {count}")
            # self.num_mods.setText(f"Active [{count}]")
            self.update_count(self.active_mods_list.get_widgets_and_items())

        self.recalculate_internal_list_errors()

    def clear_active_mods_search(self) -> None:
        self.active_mods_search.setText("")
        self.active_mods_search.clearFocus()

    def signal_active_mods_search(self, pattern: str) -> None:
        wni = self.active_mods_list.get_widgets_and_items()
        filtered_qlabel_stylesheet = "QLabel { color : grey; }"
        unfiltered_qlabel_stylesheet = "QLabel { color : white; }"
        # Use the configured search filter
        if self.active_mods_search_filter.currentText() == "Name":
            search_filter = "name"
        elif self.active_mods_search_filter.currentText() == "PackageId":
            search_filter = "packageId"
        elif self.active_mods_search_filter.currentText() == "Author(s)":
            search_filter = "author"
        elif self.active_mods_search_filter.currentText() == "PublishedFileId":
            search_filter = "publishedfileid"
        for widget, item in wni:
            if (
                pattern
                and widget.json_data.get(search_filter)
                and not pattern.lower() in widget.json_data[search_filter].lower()
            ):
                if self.active_mods_search_filter_state:
                    item.setHidden(True)
                elif not self.active_mods_search_filter_state:
                    widget.findChild(QLabel, "ListItemLabel").setStyleSheet(
                        filtered_qlabel_stylesheet
                    )
            else:
                if self.active_mods_search_filter_state:
                    item.setHidden(False)
                elif not self.active_mods_search_filter_state:
                    widget.findChild(QLabel, "ListItemLabel").setStyleSheet(
                        unfiltered_qlabel_stylesheet
                    )
        self.update_count(wni)

    def signal_active_mods_search_filter_toggle(self) -> None:
        buffer = self.active_mods_search.text()
        self.clear_active_mods_search()
        if self.active_mods_search_filter_state:
            self.active_mods_search_filter_state = False
            self.active_mods_search_mode_filter_button.setIcon(
                self.active_mods_search_mode_nofilter_icon
            )
        else:
            self.active_mods_search_filter_state = True
            self.active_mods_search_mode_filter_button.setIcon(
                self.active_mods_search_mode_filter_icon
            )
        self.active_mods_search.setFocus()
        self.active_mods_search.setText(buffer)
        self.active_mods_search.textChanged.emit(buffer)

    def update_count(
        self, widgets_and_items: list[tuple[ModListItemInner, QListWidgetItem]]
    ) -> None:
        num_hidden = 0
        num_visible = 0
        for w, i in widgets_and_items:
            if i.isHidden():
                num_hidden += 1
            else:
                num_visible += 1
        if self.active_mods_search.text():
            self.num_mods.setText(f"Active [{num_visible}/{num_hidden + num_visible}]")
        else:
            self.num_mods.setText(f"Active [{num_hidden + num_visible}]")
