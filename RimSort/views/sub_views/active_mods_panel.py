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

from RimSort.controllers.settings_controller import SettingsController
from RimSort.models.mod_list import ModListWidget
from RimSort.models.mod_list_item import ModListItemInner
from RimSort.utils.constants import SEARCH_DATA_SOURCE_FILTER_INDEXES
from RimSort.utils.metadata import MetadataManager


class ActiveModList(QWidget):
    """
    This class controls the layout and functionality for the
    active mods list panel on the GUI.
    """

    list_updated_signal = Signal()

    def __init__(
        self, mod_type_filter_enable: bool, settings_controller: SettingsController
    ) -> None:
        """
        Initialize the class.
        Create a ListWidget using the dict of mods. This will
        create a row for every key-value pair in the dict.
        """
        super(ActiveModList, self).__init__()

        # Cache MetadataManager instance
        self.metadata_manager = MetadataManager.instance()

        logger.debug("Initializing ActiveModList")

        self.settings_controller = settings_controller

        self.list_updated = False
        self.mod_type_filter_enable = mod_type_filter_enable

        # Base layout type
        self.panel = QVBoxLayout()

        # Instantiate widgets
        self.num_mods = QLabel("Active [0]")
        self.num_mods.setAlignment(Qt.AlignCenter)
        self.num_mods.setObjectName("summaryValue")
        # Active mod list
        self.active_mods_list = ModListWidget(
            mod_type_filter_enable=self.mod_type_filter_enable,
            settings_controller=self.settings_controller,
        )

        # Search widgets
        self.active_mods_search_layout = QHBoxLayout()
        self.active_mods_filter_data_source_index = 0
        self.active_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.active_mods_filter_data_source_index
        ]
        self.active_mods_filter_data_source_icons = [
            QIcon(
                str(
                    Path(
                        os.path.join(
                            os.path.dirname(__file__), "../../../data/AppIcon_b.png"
                        )
                    ).resolve()
                )
            ),
            QIcon(self.active_mods_list.ludeon_icon_path),
            QIcon(self.active_mods_list.local_icon_path),
            QIcon(self.active_mods_list.git_icon_path),
            QIcon(self.active_mods_list.steamcmd_icon_path),
            QIcon(self.active_mods_list.steam_icon_path),
        ]
        self.active_mods_filter_data_source_button = QToolButton()
        self.active_mods_filter_data_source_button.setIcon(
            self.active_mods_filter_data_source_icons[
                self.active_mods_filter_data_source_index
            ]
        )
        self.active_mods_filter_data_source_button.clicked.connect(
            self.signal_active_mods_data_source_filter
        )
        self.active_mods_search_filter_state = True
        self.active_mods_search_mode_filter_icon = QIcon(
            str(
                Path(
                    os.path.join(os.path.dirname(__file__), "../../../data/filter.png")
                ).resolve()
            )
        )
        self.active_mods_search_mode_nofilter_icon = QIcon(
            str(
                Path(
                    os.path.join(
                        os.path.dirname(__file__), "../../../data/nofilter.png"
                    )
                ).resolve()
            )
        )
        self.active_mods_search_mode_filter_button = QToolButton()
        self.active_mods_search_mode_filter_button.setIcon(
            self.active_mods_search_mode_filter_icon
        )
        self.active_mods_search_mode_filter_button.clicked.connect(
            self.signal_active_mods_search_and_filters_filter_toggle
        )
        self.active_mods_search = QLineEdit()
        self.active_mods_search.setClearButtonEnabled(True)
        self.active_mods_search.textChanged.connect(
            self.signal_active_mods_search_and_filters
        )
        self.active_mods_search.inputRejected.connect(self.clear_active_mods_search)
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
            self.active_mods_filter_data_source_button
        )
        self.active_mods_search_layout.addWidget(
            self.active_mods_search_mode_filter_button
        )
        self.active_mods_search_layout.addWidget(self.active_mods_search, 45)
        self.active_mods_search_layout.addWidget(self.active_mods_search_filter, 70)

        # Errors/warnings
        self.errors_summary_frame = QFrame()
        self.errors_summary_frame.setObjectName("errorFrame")
        self.errors_summary_layout = QHBoxLayout()
        self.errors_summary_layout.setContentsMargins(0, 0, 0, 0)
        self.errors_summary_layout.setSpacing(2)
        self.warnings_icon = QLabel()
        self.warnings_icon.setPixmap(
            QIcon(self.active_mods_list.warning_icon_path).pixmap(QSize(20, 20))
        )
        self.warnings_text = QLabel("0 warnings(s)")
        self.warnings_text.setObjectName("summaryValue")
        self.errors_icon = QLabel()
        self.errors_icon.setPixmap(
            QIcon(self.active_mods_list.error_icon_path).pixmap(QSize(20, 20))
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

        # Connect signals and slots
        self.active_mods_list.list_update_signal.connect(
            self.handle_internal_mod_list_updated
        )
        logger.debug("Finished ActiveModList initialization")

    def recalculate_internal_list_errors(self) -> None:
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

    def handle_internal_mod_list_updated(self, count: str) -> None:
        # First time, and when Refreshing, the slot will evaluate false and do nothing.
        # The purpose of this is for the _do_save_animation slot in the main_content_panel
        self.list_updated_signal.emit()
        self.list_updated = True
        # 'drop' indicates that the update was just a drag and drop
        # within the list.
        if count != "drop":
            logger.info(f"Active mod count changed to: {count}")
            self.update_count(self.active_mods_list.get_widgets_and_items())

        self.recalculate_internal_list_errors()

    def clear_active_mods_search(self) -> None:
        self.active_mods_search.setText("")
        self.active_mods_search.clearFocus()

    def signal_active_mods_search_and_filters(self, pattern: str) -> None:
        def repolish_label(label: QLabel) -> None:
            label.style().unpolish(label)
            label.style().polish(label)

        wni = self.active_mods_list.get_widgets_and_items()

        if self.active_mods_search_filter.currentText() == "Name":
            search_filter = "name"
        elif self.active_mods_search_filter.currentText() == "PackageId":
            search_filter = "packageid"
        elif self.active_mods_search_filter.currentText() == "Author(s)":
            search_filter = "authors"
        elif self.active_mods_search_filter.currentText() == "PublishedFileId":
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
                if self.active_mods_search_filter_state:
                    item.setHidden(True)
                else:
                    widget.main_label.setObjectName("ListItemLabelFiltered")
                    repolish_label(label=widget.main_label)
            else:
                if self.active_mods_data_source_filter == "all":
                    if self.active_mods_search_filter_state:
                        item.setHidden(False)
                    else:
                        widget.main_label.setObjectName("ListItemLabel")
                        repolish_label(label=widget.main_label)
                elif self.active_mods_data_source_filter == "git_repo":
                    if not widget.git_icon:
                        if self.active_mods_search_filter_state:
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
                elif self.active_mods_data_source_filter == "steamcmd":
                    if not widget.steamcmd_icon:
                        if self.active_mods_search_filter_state:
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
                else:
                    if not widget.mod_source_icon or (
                        widget.mod_source_icon
                        and (
                            widget.mod_source_icon.objectName()
                            != self.active_mods_data_source_filter
                        )
                    ):
                        if self.active_mods_search_filter_state:
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

        self.update_count(wni)

    def signal_active_mods_data_source_filter(self) -> None:
        # Indexes by the icon
        if self.active_mods_filter_data_source_index < (
            len(self.active_mods_filter_data_source_icons) - 1
        ):
            self.active_mods_filter_data_source_index += 1
        else:
            self.active_mods_filter_data_source_index = 0
        self.active_mods_filter_data_source_button.setIcon(
            self.active_mods_filter_data_source_icons[
                self.active_mods_filter_data_source_index
            ]
        )
        self.active_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.active_mods_filter_data_source_index
        ]
        # Filter widgets by data source, while preserving any active search pattern
        self.signal_active_mods_search_and_filters(
            pattern=self.active_mods_search.text()
        )

    def signal_active_mods_search_and_filters_filter_toggle(self) -> None:
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
