from loguru import logger
import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.controllers.settings_controller import SettingsController
from app.models.mod_list import ModListWidget
from app.models.mod_list_item import ModListItemInner, ModListIcons
from app.utils.app_info import AppInfo
from app.utils.constants import SEARCH_DATA_SOURCE_FILTER_INDEXES
from app.utils.metadata import MetadataManager


class ModsPanel(QWidget):
    """
    This class controls the layout and functionality for the
    active/inactive mods list panel on the GUI.
    """

    list_updated_signal = Signal()

    def __init__(self, settings_controller: SettingsController) -> None:
        """
        Initialize the class.
        Create a ListWidget using the dict of mods. This will
        create a row for every key-value pair in the dict.
        """
        super(ModsPanel, self).__init__()

        # Cache MetadataManager instance and initialize panel
        logger.debug("Initializing ModsPanel")
        self.metadata_manager = MetadataManager.instance()
        self.settings_controller = settings_controller
        self.list_updated = False

        # Base layout horizontal, sub-layouts vertical
        self.panel = QHBoxLayout()
        self.active_panel = QVBoxLayout()
        self.inactive_panel = QVBoxLayout()
        # Add vertical layouts to it
        self.panel.addLayout(self.inactive_panel)
        self.panel.addLayout(self.active_panel)

        # Instantiate WIDGETS

        self.data_source_filter_icons = [
            QIcon(str(AppInfo().theme_data_folder / "default-icons" / "AppIcon_b.png")),
            ModListIcons.ludeon_icon(),
            ModListIcons.local_icon(),
            ModListIcons.git_icon(),
            ModListIcons.steamcmd_icon(),
            ModListIcons.steam_icon(),
        ]

        self.mode_filter_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "filter.png")
        )
        self.mode_nofilter_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "nofilter.png")
        )

        # ACTIVE mod list widget
        self.active_mods_label = QLabel("Active [0]")
        self.active_mods_label.setAlignment(Qt.AlignCenter)
        self.active_mods_label.setObjectName("summaryValue")
        self.active_mods_list = ModListWidget(
            settings_controller=self.settings_controller,
        )
        # Active mods search widgets
        self.active_mods_search_layout = QHBoxLayout()
        self.active_mods_filter_data_source_index = 0
        self.active_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.active_mods_filter_data_source_index
        ]
        self.active_mods_filter_data_source_button = QToolButton()
        self.active_mods_filter_data_source_button.setIcon(
            self.data_source_filter_icons[self.active_mods_filter_data_source_index]
        )
        self.active_mods_filter_data_source_button.clicked.connect(
            self.on_active_mods_search_data_source_filter
        )
        self.active_mods_search_filter_state = True
        self.active_mods_search_mode_filter_button = QToolButton()
        self.active_mods_search_mode_filter_button.setIcon(self.mode_filter_icon)
        self.active_mods_search_mode_filter_button.clicked.connect(
            self.on_active_mods_mode_filter_toggle
        )
        self.active_mods_search = QLineEdit()
        self.active_mods_search.setClearButtonEnabled(True)
        self.active_mods_search.textChanged.connect(self.on_active_mods_search)
        self.active_mods_search.inputRejected.connect(self.on_active_mods_search_clear)
        self.active_mods_search.setPlaceholderText("Search by...")
        self.active_mods_search_clear_button = self.active_mods_search.findChild(
            QToolButton
        )
        self.active_mods_search_clear_button.setEnabled(True)
        self.active_mods_search_clear_button.clicked.connect(
            self.on_active_mods_search_clear
        )
        self.active_mods_search_filter = QComboBox()
        self.active_mods_search_filter.setObjectName("MainUI")
        self.active_mods_search_filter.setMaximumWidth(125)
        self.active_mods_search_filter.addItems(
            ["Name", "PackageId", "Author(s)", "PublishedFileId"]
        )
        # Active mods search layouts
        self.active_mods_search_layout.addWidget(
            self.active_mods_filter_data_source_button
        )
        self.active_mods_search_layout.addWidget(
            self.active_mods_search_mode_filter_button
        )
        self.active_mods_search_layout.addWidget(self.active_mods_search, 45)
        self.active_mods_search_layout.addWidget(self.active_mods_search_filter, 70)
        # Active mods list Errors/warnings widgets
        self.errors_summary_frame = QFrame()
        self.errors_summary_frame.setObjectName("errorFrame")
        self.errors_summary_layout = QHBoxLayout()
        self.errors_summary_layout.setContentsMargins(0, 0, 0, 0)
        self.errors_summary_layout.setSpacing(2)
        self.warnings_icon = QLabel()
        self.warnings_icon.setPixmap(ModListIcons.warning_icon().pixmap(QSize(20, 20)))
        self.warnings_text = QLabel("0 warnings(s)")
        self.warnings_text.setObjectName("summaryValue")
        self.errors_icon = QLabel()
        self.errors_icon.setPixmap(ModListIcons.error_icon().pixmap(QSize(20, 20)))
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
        # Add active mods widgets to layouts
        self.active_panel.addWidget(self.active_mods_label, 1)
        self.active_panel.addLayout(self.active_mods_search_layout, 1)
        self.active_panel.addWidget(self.active_mods_list, 97)
        self.active_panel.addWidget(self.errors_summary_frame, 1)

        # INACTIVE mod list widgets
        self.inactive_mods_label = QLabel("Inactive [0]")
        self.inactive_mods_label.setAlignment(Qt.AlignCenter)
        self.inactive_mods_label.setObjectName("summaryValue")
        self.inactive_mods_list = ModListWidget(
            settings_controller=self.settings_controller,
        )
        # Inactive mods search widgets
        self.inactive_mods_search_layout = QHBoxLayout()
        self.inactive_mods_filter_data_source_index = 0
        self.inactive_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.inactive_mods_filter_data_source_index
        ]
        self.inactive_mods_filter_data_source_button = QToolButton()
        self.inactive_mods_filter_data_source_button.setIcon(
            self.data_source_filter_icons[self.inactive_mods_filter_data_source_index]
        )
        self.inactive_mods_filter_data_source_button.clicked.connect(
            self.on_inactive_mods_search_data_source_filter
        )
        self.inactive_mods_search_filter_state = True
        self.inactive_mods_search_mode_filter_button = QToolButton()
        self.inactive_mods_search_mode_filter_button.setIcon(self.mode_nofilter_icon)
        self.inactive_mods_search_mode_filter_button.clicked.connect(
            self.on_inactive_mods_mode_filter_toggle
        )
        self.inactive_mods_search = QLineEdit()
        self.inactive_mods_search.setClearButtonEnabled(True)
        self.inactive_mods_search.textChanged.connect(self.on_inactive_mods_search)
        self.inactive_mods_search.inputRejected.connect(
            self.on_inactive_mods_search_clear
        )
        self.inactive_mods_search.setPlaceholderText("Search by...")
        self.inactive_mods_search_clear_button = self.inactive_mods_search.findChild(
            QToolButton
        )
        self.inactive_mods_search_clear_button.setEnabled(True)
        self.inactive_mods_search_clear_button.clicked.connect(
            self.on_inactive_mods_search_clear
        )
        self.inactive_mods_search_filter = QComboBox()
        self.inactive_mods_search_filter.setObjectName("MainUI")
        self.inactive_mods_search_filter.setMaximumWidth(140)
        self.inactive_mods_search_filter.addItems(
            ["Name", "PackageId", "Author(s)", "PublishedFileId"]
        )
        # Inactive mods search layouts
        self.inactive_mods_search_layout.addWidget(
            self.inactive_mods_filter_data_source_button
        )
        self.inactive_mods_search_layout.addWidget(
            self.inactive_mods_search_mode_filter_button
        )
        self.inactive_mods_search_layout.addWidget(self.inactive_mods_search, 45)
        self.inactive_mods_search_layout.addWidget(self.inactive_mods_search_filter, 70)
        # Add inactive mods widgets to layout
        self.inactive_panel.addWidget(self.inactive_mods_label)
        self.inactive_panel.addLayout(self.inactive_mods_search_layout)
        self.inactive_panel.addWidget(self.inactive_mods_list)

        # Adding Completer.
        # self.completer = QCompleter(self.active_mods_list.get_list_items())
        # self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        # self.active_mods_search.setCompleter(self.completer)
        # self.inactive_mods_search.setCompleter(self.completer)

        # Connect signals and slots
        self.active_mods_list.list_update_signal.connect(
            self.on_active_mods_list_updated
        )
        # Connect signals and slots
        self.inactive_mods_list.list_update_signal.connect(
            self.on_inactive_mods_list_updated
        )

        logger.debug("Finished ModsPanel initialization")

    def mod_list_updated(self, count: str, list_type: str) -> None:
        if list_type == "Active":
            # First time, and when Refreshing, the slot will evaluate false and do nothing.
            # The purpose of this is for the _do_save_animation slot in the main_content_panel
            self.list_updated_signal.emit()
            self.list_updated = True
        # 'drop' indicates that the update was just a drag and drop
        # within the list.
        if count != "drop":
            logger.info(f"{list_type} mod count changed to: {count}")
            self.update_count(
                list_type=list_type,
                widgets_and_items=self.active_mods_list.get_widgets_and_items(),
            )
        if list_type == "Active":
            self.recalculate_active_mods()

    def recalculate_active_mods(self) -> None:
        """
        Whenever the active mod list has items added to it,
        or has items removed from it, or has items rearranged around within it,
        calculate the internal list errors for the active mod list
        """
        logger.info("Recalculating internal list errors")

        internal_local_metadata = self.metadata_manager.internal_local_metadata
        game_version = self.metadata_manager.game_version
        info_from_steam = self.metadata_manager.info_from_steam_package_id_to_name

        packageid_to_uuid = {
            internal_local_metadata[uuid]["packageid"]: uuid
            for uuid in self.active_mods_list.uuids
        }
        package_ids_set = set(packageid_to_uuid.keys())

        package_id_to_errors = {
            uuid: {
                "missing_dependencies": set(),
                "conflicting_incompatibilities": set(),
                "load_before_violations": set(),
                "load_after_violations": set(),
                "version_mismatch": True,
            }
            for uuid in self.active_mods_list.uuids
        }

        num_warnings = 0
        total_warning_text = ""
        num_errors = 0
        total_error_text = ""

        for uuid, mod_errors in package_id_to_errors.items():
            current_mod_index = self.active_mods_list.uuids.index(uuid)
            mod_data = internal_local_metadata[uuid]

            # Check version for everything except Core
            if game_version and mod_data.get("supportedversions", {}).get("li"):
                supported_versions = mod_data["supportedversions"]["li"]
                if isinstance(supported_versions, str):
                    if game_version.startswith(supported_versions):
                        mod_errors["version_mismatch"] = False
                elif isinstance(supported_versions, list):
                    mod_errors["version_mismatch"] = (
                        not any(
                            [
                                ver
                                for ver in supported_versions
                                if game_version.startswith(ver)
                            ]
                        )
                        and mod_data["packageid"]
                        not in self.active_mods_list.ignore_warning_list
                    )
                else:
                    logger.error(
                        f"supportedversions value not str or list: {supported_versions}"
                    )

            if (
                mod_data.get("packageid")
                and mod_data["packageid"]
                not in self.active_mods_list.ignore_warning_list
            ):
                # Check dependencies
                mod_errors["missing_dependencies"] = {
                    dep
                    for dep in mod_data.get("dependencies", [])
                    if dep not in package_ids_set
                }

                # Check incompatibilities
                mod_errors["conflicting_incompatibilities"] = {
                    incomp
                    for incomp in mod_data.get("incompatibilities", [])
                    if incomp in package_ids_set
                }

                # Check loadTheseBefore
                for load_this_before in mod_data.get("loadTheseBefore", []):
                    if (
                        load_this_before[1]
                        and load_this_before[0] in packageid_to_uuid
                        and current_mod_index
                        <= self.active_mods_list.uuids.index(
                            packageid_to_uuid[load_this_before[0]]
                        )
                    ):
                        mod_errors["load_before_violations"].add(load_this_before[0])

                # Check loadTheseAfter
                for load_this_after in mod_data.get("loadTheseAfter", []):
                    if (
                        load_this_after[1]
                        and load_this_after[0] in packageid_to_uuid
                        and current_mod_index
                        >= self.active_mods_list.uuids.index(
                            packageid_to_uuid[load_this_after[0]]
                        )
                    ):
                        mod_errors["load_after_violations"].add(load_this_after[0])

            # Consolidate results
            self.ignore_error = self.active_mods_list.ignore_warning_list

            # Set icon if necessary
            item_widget_at_index = self.active_mods_list.get_item_widget_at_index(
                current_mod_index
            )
            if item_widget_at_index:
                tool_tip_text = ""
                for error_type, tooltip_header in [
                    ("missing_dependencies", "\nMissing Dependencies:"),
                    ("conflicting_incompatibilities", "\nIncompatibilities:"),
                    ("load_before_violations", "\nShould be Loaded After:"),
                    ("load_after_violations", "\nShould be Loaded Before:"),
                ]:
                    if mod_errors[error_type]:
                        tool_tip_text += tooltip_header
                        for key in mod_errors[error_type]:
                            name = internal_local_metadata.get(
                                packageid_to_uuid.get(key), {}
                            ).get("name", info_from_steam.get(key, key))
                            tool_tip_text += f"\n  * {name}"

                if mod_errors["version_mismatch"] and not self.ignore_error:
                    tool_tip_text += "\n\nMod and Game Version Mismatch"

                if tool_tip_text:
                    item_widget_at_index.warning_icon_label.setHidden(False)
                    item_widget_at_index.warning_icon_label.setToolTip(
                        tool_tip_text.lstrip()
                    )
                else:
                    item_widget_at_index.warning_icon_label.setHidden(True)
                    item_widget_at_index.warning_icon_label.setToolTip("")

                # Add to error/warnings summary if necessary
                if any(
                    [
                        mod_errors[key]
                        for key in [
                            "missing_dependencies",
                            "conflicting_incompatibilities",
                        ]
                    ]
                ):
                    num_errors += 1
                    total_error_text += f"\n\n{mod_data['name']}"
                    total_error_text += "\n" + "=" * len(mod_data["name"])
                    total_error_text += tool_tip_text

                if any(
                    [
                        mod_errors[key]
                        for key in [
                            "load_before_violations",
                            "load_after_violations",
                            "version_mismatch",
                        ]
                    ]
                ):
                    num_warnings += 1
                    total_warning_text += f"\n\n{mod_data['name']}"
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
            self.errors_icon.setToolTip("")
            self.warnings_icon.setToolTip("")

        logger.info("Finished recalculating internal list errors")

    def on_active_mods_list_updated(self, count: str) -> None:
        self.mod_list_updated(count=count, list_type="Active")

    def on_active_mods_search(self) -> None:
        self.signal_search_and_filters(
            list_type="Active", pattern=self.active_mods_search.text()
        )

    def on_active_mods_search_clear(self) -> None:
        self.signal_clear_search(list_type="Active")

    def on_active_mods_search_data_source_filter(self) -> None:
        self.signal_data_source_filter(list_type="Active")

    def on_active_mods_mode_filter_toggle(self) -> None:
        self.signal_search_mode_filter(list_type="Active")

    def on_inactive_mods_list_updated(self, count: str) -> None:
        self.mod_list_updated(count=count, list_type="Inactive")

    def on_inactive_mods_search(self) -> None:
        self.signal_search_and_filters(
            list_type="Inactive", pattern=self.inactive_mods_search.text()
        )

    def on_inactive_mods_search_clear(self) -> None:
        self.signal_clear_search(list_type="Inactive")

    def on_inactive_mods_search_data_source_filter(self) -> None:
        self.signal_data_source_filter(list_type="Inactive")

    def on_inactive_mods_mode_filter_toggle(self) -> None:
        self.signal_search_mode_filter(list_type="Inactive")

    def signal_clear_search(self, list_type: str) -> None:
        if list_type == "Active":
            search = self.active_mods_search
        elif list_type == "Inactive":
            search = self.inactive_mods_search
        search.setText("")
        search.clearFocus()

    def signal_search_and_filters(self, list_type: str, pattern: str) -> None:
        def repolish_label(label: QLabel) -> None:
            label.style().unpolish(label)
            label.style().polish(label)

        if list_type == "Active":
            _filter = self.active_mods_search_filter
            filter_state = self.active_mods_search_filter_state
            source_filter = self.active_mods_data_source_filter
            search = self.active_mods_search
            wni = self.active_mods_list.get_widgets_and_items()
        elif list_type == "Inactive":
            _filter = self.inactive_mods_search_filter
            filter_state = self.inactive_mods_search_filter_state
            source_filter = self.inactive_mods_data_source_filter
            search = self.inactive_mods_search
            wni = self.inactive_mods_list.get_widgets_and_items()

        if _filter.currentText() == "Name":
            search_filter = "name"
        elif _filter.currentText() == "PackageId":
            search_filter = "packageid"
        elif _filter.currentText() == "Author(s)":
            search_filter = "authors"
        elif _filter.currentText() == "PublishedFileId":
            search_filter = "publishedfileid"

        for widget, item in wni:
            if (
                pattern
                and self.metadata_manager.internal_local_metadata[widget.uuid].get(
                    search_filter
                )
                and not pattern.lower()
                in str(
                    self.metadata_manager.internal_local_metadata[widget.uuid].get(
                        search_filter
                    )
                ).lower()
            ):
                if filter_state:
                    item.setHidden(True)
                else:
                    widget.main_label.setObjectName("ListItemLabelFiltered")
                    repolish_label(label=widget.main_label)
            else:
                if _filter == "all":
                    if filter_state:
                        item.setHidden(False)
                    else:
                        widget.main_label.setObjectName("ListItemLabel")
                        repolish_label(label=widget.main_label)
                elif _filter == "git_repo":
                    if not widget.git_icon:
                        if filter_state:
                            item.setHidden(True)
                        else:
                            widget.main_label.setObjectName("ListItemLabelFiltered")
                            repolish_label(label=widget.main_label)
                    else:
                        if filter_state:
                            item.setHidden(False)
                        else:
                            widget.main_label.setObjectName("ListItemLabel")
                            repolish_label(label=widget.main_label)
                elif _filter == "steamcmd":
                    if not widget.steamcmd_icon:
                        if filter_state:
                            item.setHidden(True)
                        else:
                            widget.main_label.setObjectName("ListItemLabelFiltered")
                            repolish_label(label=widget.main_label)
                    else:
                        if filter_state:
                            item.setHidden(False)
                        else:
                            widget.main_label.setObjectName("ListItemLabel")
                            repolish_label(label=widget.main_label)
                else:
                    if not widget.mod_source_icon or (
                        widget.mod_source_icon
                        and (widget.mod_source_icon.objectName() != _filter)
                    ):
                        if filter_state:
                            item.setHidden(True)
                        else:
                            widget.main_label.setObjectName("ListItemLabelFiltered")
                            repolish_label(label=widget.main_label)
                    else:
                        if self.active_mods_search_filter_state:
                            item.setHidden(False)
                        else:
                            widget.main_label.setObjectName("ListItemLabel")
                            repolish_label(label=widget.main_label)

        self.update_count(list_type=list_type, wni=wni)

    def signal_data_source_filter(self, list_type: str) -> None:
        if list_type == "Active":
            button = self.active_mods_filter_data_source_button
            search = self.active_mods_search
            source_filter = self.active_mods_data_source_filter
            source_index = self.active_mods_filter_data_source_index
        elif list_type == "Inactive":
            button = self.inactive_mods_filter_data_source_button
            search = self.inactive_mods_search
            source_filter = self.inactive_mods_data_source_filter
            source_index = self.inactive_mods_filter_data_source_index
        # Indexes by the icon
        if source_index < (len(self.data_source_filter_icons) - 1):
            source_index += 1
        else:
            source_index = 0
        button.setIcon(self.data_source_filter_icons[source_index])
        source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[source_index]
        # Filter widgets by data source, while preserving any active search pattern
        self.signal_search_and_filters(list_type=list_type, pattern=search.text())

    def signal_search_mode_filter(self, list_type: str) -> None:
        if list_type == "Active":
            button = self.active_mods_filter_data_source_button
            _filter = self.active_mods_search_filter
            filter_state = self.active_mods_search_filter_state
            search = self.active_mods_search
        elif list_type == "Inactive":
            button = self.inactive_mods_filter_data_source_button
            _filter = self.inactive_mods_search_filter
            filter_state = self.inactive_mods_search_filter_state
            search = self.inactive_mods_search
        buffer = search.text()
        self.signal_clear_search(list_type=list_type)
        if filter_state:
            filter_state = False
            button.setIcon(self.mode_nofilter_icon)
        else:
            filter_state = True
            button.setIcon(self.mode_filter_icon)
        search.setFocus()
        search.setText(buffer)
        search.textChanged.emit(buffer)

    def update_count(
        self,
        list_type: str,
        widgets_and_items: list[tuple[ModListItemInner, QListWidgetItem]],
    ) -> None:
        if list_type == "Active":
            search = self.active_mods_search
            label = self.active_mods_label
        elif list_type == "Inactive":
            search = self.inactive_mods_search
            label = self.inactive_mods_label
        else:
            raise ValueError(f"Invalid list type: {list_type}")
            return
        num_hidden = 0
        num_visible = 0
        for w, i in widgets_and_items:
            if i.isHidden():
                num_hidden += 1
            else:
                num_visible += 1
        if search.text():
            label.setText(f"{list_type} [{num_visible}/{num_hidden + num_visible}]")
        else:
            label.setText(f"{list_type} [{num_hidden + num_visible}]")
