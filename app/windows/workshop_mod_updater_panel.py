from functools import partial
from time import localtime, strftime
from typing import Any, Dict

from PySide6.QtCore import Qt, QEvent, QSize, Signal
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
)
from loguru import logger


class ModUpdaterPrompt(QWidget):
    """
    A generic panel used to prompt a user to update eligible Workshop mods
    """

    steamcmd_downloader_signal = Signal(list)
    steamworks_subscription_signal = Signal(list)

    def __init__(self, internal_mod_metadata: Dict[str, Any]):
        super().__init__()
        logger.debug("Initializing ModUpdaterPrompt")
        self.updates_found = None

        self.installEventFilter(self)

        self.internal_mod_metadata = internal_mod_metadata
        self.setObjectName("missingModsPanel")
        # MOD LABEL
        self.updates_available_label = QLabel(
            "There updates available for Workshop mods!"
        )
        self.updates_available_label.setAlignment(Qt.AlignCenter)

        # CONTAINER LAYOUTS
        self.upper_layout = QVBoxLayout()
        self.lower_layout = QVBoxLayout()
        self.layout = QVBoxLayout()

        # SUB LAYOUTS
        self.details_layout = QVBoxLayout()
        self.editor_layout = QVBoxLayout()
        self.editor_actions_layout = QHBoxLayout()

        # DETAILS WIDGETS
        self.details_label = QLabel(
            "\nThe following table displays Workshop mods available for update from Steam."
        )
        self.details_label.setAlignment(Qt.AlignCenter)

        # EDITOR WIDGETS
        # Create the model and set column headers
        self.editor_model = QStandardItemModel(0, 5)
        self.editor_model.setHorizontalHeaderLabels(
            [
                "✔",
                "Name",
                "PublishedFileID",
                "Mod source",
                "Mod last touched",
                "Mod last updated",
                # "Open page",
            ]
        )
        # Create the table view and set the model
        self.editor_table_view = QTableView()
        self.editor_table_view.setModel(self.editor_model)
        self.editor_table_view.setSortingEnabled(True)  # Enable sorting on the columns
        self.editor_table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.editor_table_view.setSelectionMode(QAbstractItemView.NoSelection)
        # Set default stretch for each column
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeToContents
        )
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeToContents
        )
        self.editor_deselect_all_button = QPushButton("Deselect all")
        self.editor_deselect_all_button.clicked.connect(
            partial(self._deselect_select_all_rows, False)
        )
        self.editor_select_all_button = QPushButton("Select all")
        self.editor_select_all_button.clicked.connect(
            partial(self._deselect_select_all_rows, True)
        )
        self.editor_cancel_button = QPushButton("Do nothing and exit")
        self.editor_cancel_button.clicked.connect(self.close)
        self.editor_update_mods_button = QPushButton("Update mods")
        self.editor_update_mods_button.clicked.connect(
            partial(
                self._update_mods_from_table,
            )
        )
        self.editor_update_all_button = QPushButton("Update all")
        self.editor_update_all_button.clicked.connect(partial(self._update_all))
        self.editor_actions_layout.addWidget(self.editor_deselect_all_button)
        self.editor_actions_layout.addWidget(self.editor_select_all_button)
        self.editor_actions_layout.addStretch(100)
        self.editor_actions_layout.addWidget(self.editor_cancel_button)
        self.editor_actions_layout.addWidget(self.editor_update_mods_button)
        self.editor_actions_layout.addWidget(self.editor_update_all_button)

        # Build the details layout
        self.details_layout.addWidget(self.details_label)

        # Build the editor layouts
        self.editor_layout.addWidget(self.editor_table_view)
        self.editor_layout.addLayout(self.editor_actions_layout)

        # Add our widget layouts to the containers
        self.upper_layout.addLayout(self.details_layout)
        self.lower_layout.addLayout(self.editor_layout)

        # Add our layouts to the main layout
        self.layout.addWidget(self.updates_available_label)
        self.layout.addLayout(self.upper_layout)
        self.layout.addLayout(self.lower_layout)

        # Put it all together
        self.setWindowTitle("RimSort - Updates found for Workshop mods")
        self.setLayout(self.layout)
        self.setMinimumSize(QSize(900, 600))

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.close()
            return True

        return super().eventFilter(obj, event)

    def _add_row(
        self,
        name: str,
        publishedfileid: str,
        mod_source: str,
        internal_time_touched: str,
        external_time_updated: str,
    ):
        # Create a new row
        items = [
            QStandardItem(),
            QStandardItem(name),
            QStandardItem(publishedfileid),
            QStandardItem(mod_source),
            QStandardItem(internal_time_touched),
            QStandardItem(external_time_updated),
        ]
        self.editor_model.appendRow(items)
        # Add our combo box to the row's column 5 and connect to update signal
        checkbox_index = items[0].index()
        checkbox = QCheckBox()
        checkbox.setObjectName("summaryValue")
        checkbox.setChecked(False)
        # Set the checkbox as the index widget
        self.editor_table_view.setIndexWidget(checkbox_index, checkbox)

    def _deselect_select_all_rows(self, value: bool) -> None:
        # Iterate through the editor's rows
        for row in range(self.editor_model.rowCount()):
            if self.editor_model.item(row):  # If there is a row at current index
                # If an existing row is found, setChecked the value
                checkbox = self.editor_table_view.indexWidget(
                    self.editor_model.item(row, 0).index()
                )
                checkbox.setChecked(value)

    def _update_mods_from_table(self) -> None:
        steamcmd_publishedfileids = []
        steam_publishedfileids = []
        # Iterate through the editor's rows
        for row in range(self.editor_model.rowCount()):
            if self.editor_model.item(row):  # If there is a row at current index
                # If an existing row is found, is it selected?
                checkbox = self.editor_table_view.indexWidget(
                    self.editor_model.item(row, 0).index()
                )
                if checkbox.isChecked():
                    publishedfileid = self.editor_model.item(row, 2).text()
                    if self.editor_model.item(row, 3).text() == "SteamCMD":
                        steamcmd_publishedfileids.append(publishedfileid)
                    elif self.editor_model.item(row, 3).text() == "Steam":
                        steam_publishedfileids.append(publishedfileid)
        # If we have any SteamCMD mods designated to be updated
        if len(steamcmd_publishedfileids) > 0:
            self.steamcmd_downloader_signal.emit(steamcmd_publishedfileids)
        # If we have any Steam mods designated to be updated
        if len(steam_publishedfileids) > 0:
            self.steamworks_subscription_signal.emit(
                [
                    "resubscribe",
                    [eval(str_pfid) for str_pfid in steam_publishedfileids],
                ]
            )
        self.close()

    def _update_all(self) -> None:
        self._deselect_select_all_rows(True)
        self._update_mods_from_table()

    def _populate_from_metadata(self) -> None:
        # Check our metadata for available updates, append row if found by data source
        for metadata in self.internal_mod_metadata.values():
            if (
                (metadata.get("steamcmd") or metadata.get("data_source") == "workshop")
                and metadata.get("internal_time_touched")
                and metadata.get("external_time_updated")
                and metadata["external_time_updated"]
                > metadata["internal_time_touched"]
            ):
                if not self.updates_found:
                    self.updates_found = True
                # Retrieve values from metadata
                name = metadata.get("name")
                publishedfileid = metadata.get("publishedfileid")
                mod_source = "SteamCMD" if metadata.get("steamcmd") else "Steam"
                internal_time_touched = strftime(
                    "%Y-%m-%d %H:%M:%S",
                    localtime(metadata["internal_time_touched"]),
                )
                external_time_updated = strftime(
                    "%Y-%m-%d %H:%M:%S",
                    localtime(metadata["external_time_updated"]),
                )
                # Add row to table
                self._add_row(
                    name=name,
                    publishedfileid=publishedfileid,
                    mod_source=mod_source,
                    internal_time_touched=internal_time_touched,
                    external_time_updated=external_time_updated,
                )
