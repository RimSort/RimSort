from logger_tt import logger
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QToolButton,
    QVBoxLayout,
)

from model.mod_list import ModListWidget
from model.mod_list_item import ModListItemInner
from util.constants import SEARCH_DATA_SOURCE_FILTER_INDEXES


class InactiveModList:
    """
    This class controls the layout and functionality for the
    inactive mods list panel on the GUI.
    """

    def __init__(self, mod_type_filter_enable: bool) -> None:
        """
        Initialize the class.
        Create a ListWidget using the dict of mods. This will
        create a row for every key-value pair in the dict.
        """
        logger.debug("Initializing InactiveModList")

        self.mod_type_filter_enable = mod_type_filter_enable
        self.searching = None

        # Base layout type
        self.panel = QVBoxLayout()

        # Instantiate widgets
        self.num_mods = QLabel("Inactive [0]")
        self.num_mods.setAlignment(Qt.AlignCenter)
        self.num_mods.setObjectName("summaryValue")

        # Inactive mod list
        self.inactive_mods_list = ModListWidget(
            mod_type_filter_enable=self.mod_type_filter_enable
        )

        # Search widgets
        self.inactive_mods_search_layout = QHBoxLayout()
        self.inactive_mods_filter_data_source_index = 0
        self.inactive_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.inactive_mods_filter_data_source_index
        ]
        self.inactive_mods_filter_data_source_icons = [
            QIcon(
                str(
                    Path(
                        os.path.join(os.path.dirname(__file__), "../data/AppIcon_b.png")
                    ).resolve()
                )
            ),
            QIcon(self.inactive_mods_list.ludeon_icon_path),
            QIcon(self.inactive_mods_list.local_icon_path),
            QIcon(self.inactive_mods_list.git_icon_path),
            QIcon(self.inactive_mods_list.steamcmd_icon_path),
            QIcon(self.inactive_mods_list.steam_icon_path),
        ]
        self.inactive_mods_filter_data_source_button = QToolButton()
        self.inactive_mods_filter_data_source_button.setIcon(
            self.inactive_mods_filter_data_source_icons[
                self.inactive_mods_filter_data_source_index
            ]
        )
        self.inactive_mods_filter_data_source_button.clicked.connect(
            self.signal_inactive_mods_data_source_filter
        )
        self.inactive_mods_search_filter_state = True
        self.inactive_mods_search_mode_filter_icon = QIcon(
            str(
                Path(
                    os.path.join(os.path.dirname(__file__), "../data/filter.png")
                ).resolve()
            )
        )
        self.inactive_mods_search_mode_nofilter_icon = QIcon(
            str(
                Path(
                    os.path.join(os.path.dirname(__file__), "../data/nofilter.png")
                ).resolve()
            )
        )
        self.inactive_mods_search_mode_filter_button = QToolButton()
        self.inactive_mods_search_mode_filter_button.setIcon(
            self.inactive_mods_search_mode_filter_icon
        )
        self.inactive_mods_search_mode_filter_button.clicked.connect(
            self.signal_inactive_mods_search_and_filters_filter_toggle
        )
        self.inactive_mods_search = QLineEdit()
        self.inactive_mods_search.setClearButtonEnabled(True)
        self.inactive_mods_search.textChanged.connect(
            self.signal_inactive_mods_search_and_filters
        )
        self.inactive_mods_search.inputRejected.connect(self.clear_inactive_mods_search)
        self.inactive_mods_search.setPlaceholderText("Search by...")
        self.inactive_mods_search_clear_button = self.inactive_mods_search.findChild(
            QToolButton
        )
        self.inactive_mods_search_clear_button.setEnabled(True)
        self.inactive_mods_search_clear_button.clicked.connect(
            self.clear_inactive_mods_search
        )
        self.inactive_mods_search_filter = QComboBox()
        self.inactive_mods_search_filter.setObjectName("MainUI")
        self.inactive_mods_search_filter.setMaximumWidth(140)
        self.inactive_mods_search_filter.addItems(
            ["Name", "PackageId", "Author(s)", "PublishedFileId"]
        )
        self.inactive_mods_search_layout.addWidget(
            self.inactive_mods_filter_data_source_button
        )
        self.inactive_mods_search_layout.addWidget(
            self.inactive_mods_search_mode_filter_button
        )
        self.inactive_mods_search_layout.addWidget(self.inactive_mods_search, 45)
        self.inactive_mods_search_layout.addWidget(self.inactive_mods_search_filter, 70)

        # Add widgets to base layout
        self.panel.addWidget(self.num_mods)
        self.panel.addLayout(self.inactive_mods_search_layout)
        self.panel.addWidget(self.inactive_mods_list)

        # Adding Completer.
        # self.completer = QCompleter(self.inactive_mods_list.get_list_items())
        # self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        # self.inactive_mods_search.setCompleter(self.completer)

        # Connect signals and slots
        self.inactive_mods_list.list_update_signal.connect(self.change_mod_num_display)

        logger.debug("Finished InactiveModList initialization")

    def change_mod_num_display(self, count: str) -> None:
        if count != "drop":
            logger.info(f"Inactive mod count changed to: {count}")
            self.update_count(self.inactive_mods_list.get_widgets_and_items())

    def clear_inactive_mods_search(self) -> None:
        self.inactive_mods_search.setText("")
        self.inactive_mods_search.clearFocus()

    def signal_inactive_mods_search_and_filters(self, pattern: str) -> None:
        wni = self.inactive_mods_list.get_widgets_and_items()
        filtered_qlabel_stylesheet = "QLabel { color : grey; }"
        unfiltered_qlabel_stylesheet = "QLabel { color : white; }"

        if self.inactive_mods_search_filter.currentText() == "Name":
            search_filter = "name"
        elif self.inactive_mods_search_filter.currentText() == "PackageId":
            search_filter = "packageid"
        elif self.inactive_mods_search_filter.currentText() == "Author(s)":
            search_filter = "authors"
        elif self.inactive_mods_search_filter.currentText() == "PublishedFileId":
            search_filter = "publishedfileid"

        for widget, item in wni:
            if not self.searching:
                self.searching = True
                if (
                    pattern
                    and widget.json_data.get(search_filter)
                    and not pattern.lower()
                    in str(widget.json_data[search_filter]).lower()
                ):
                    if self.inactive_mods_search_filter_state:
                        item.setHidden(True)
                    else:
                        widget.findChild(QLabel, "ListItemLabel").setStyleSheet(
                            filtered_qlabel_stylesheet
                        )
                else:
                    if self.inactive_mods_data_source_filter == "all":
                        if self.inactive_mods_search_filter_state:
                            item.setHidden(False)
                        else:
                            widget.findChild(QLabel, "ListItemLabel").setStyleSheet(
                                unfiltered_qlabel_stylesheet
                            )
                    elif self.inactive_mods_data_source_filter == "git_repo":
                        if not widget.git_icon:
                            if self.inactive_mods_search_filter_state:
                                item.setHidden(True)
                            else:
                                widget.findChild(QLabel, "ListItemLabel").setStyleSheet(
                                    filtered_qlabel_stylesheet
                                )
                        else:
                            if self.inactive_mods_search_filter_state:
                                item.setHidden(False)
                            else:
                                widget.findChild(QLabel, "ListItemLabel").setStyleSheet(
                                    unfiltered_qlabel_stylesheet
                                )
                    elif self.inactive_mods_data_source_filter == "steamcmd":
                        if not widget.steamcmd_icon:
                            if self.inactive_mods_search_filter_state:
                                item.setHidden(True)
                            else:
                                widget.findChild(QLabel, "ListItemLabel").setStyleSheet(
                                    filtered_qlabel_stylesheet
                                )
                        else:
                            if self.inactive_mods_search_filter_state:
                                item.setHidden(False)
                            else:
                                widget.findChild(QLabel, "ListItemLabel").setStyleSheet(
                                    unfiltered_qlabel_stylesheet
                                )
                    else:
                        if not widget.mod_source_icon or (
                            widget.mod_source_icon
                            and (
                                widget.mod_source_icon.objectName()
                                != self.inactive_mods_data_source_filter
                            )
                        ):
                            if self.inactive_mods_search_filter_state:
                                item.setHidden(True)
                            else:
                                widget.findChild(QLabel, "ListItemLabel").setStyleSheet(
                                    filtered_qlabel_stylesheet
                                )
                        else:
                            if self.inactive_mods_search_filter_state:
                                item.setHidden(False)
                            else:
                                widget.findChild(QLabel, "ListItemLabel").setStyleSheet(
                                    unfiltered_qlabel_stylesheet
                                )

            self.update_count(wni)
            self.searching = False

    def signal_inactive_mods_data_source_filter(self) -> None:
        # Indexes by the icon
        if self.inactive_mods_filter_data_source_index < (
            len(self.inactive_mods_filter_data_source_icons) - 1
        ):
            self.inactive_mods_filter_data_source_index += 1
        else:
            self.inactive_mods_filter_data_source_index = 0
        self.inactive_mods_filter_data_source_button.setIcon(
            self.inactive_mods_filter_data_source_icons[
                self.inactive_mods_filter_data_source_index
            ]
        )
        self.inactive_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.inactive_mods_filter_data_source_index
        ]
        # Filter widgets by data source, while preserving any active search pattern
        self.signal_inactive_mods_search_and_filters(
            pattern=self.inactive_mods_search.text()
        )

    def signal_inactive_mods_search_and_filters_filter_toggle(self) -> None:
        buffer = self.inactive_mods_search.text()
        self.clear_inactive_mods_search()
        if self.inactive_mods_search_filter_state:
            self.inactive_mods_search_filter_state = False
            self.inactive_mods_search_mode_filter_button.setIcon(
                self.inactive_mods_search_mode_nofilter_icon
            )
        else:
            self.inactive_mods_search_filter_state = True
            self.inactive_mods_search_mode_filter_button.setIcon(
                self.inactive_mods_search_mode_filter_icon
            )
        self.inactive_mods_search.setFocus()
        self.inactive_mods_search.setText(buffer)
        self.inactive_mods_search.textChanged.emit(buffer)

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
        if self.inactive_mods_search.text():
            self.num_mods.setText(
                f"Inactive [{num_visible}/{num_hidden + num_visible}]"
            )
        else:
            self.num_mods.setText(f"Inactive [{num_hidden + num_visible}]")
