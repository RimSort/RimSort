from functools import partial
from typing import Any, Dict

from PySide6.QtCore import Qt, QEvent, QSize, Signal
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
)
from loguru import logger

from app.utils.constants import RIMWORLD_DLC_METADATA


class MissingModsPrompt(QWidget):
    """
    A generic panel used to prompt a user to download missing mods
    """

    steamcmd_downloader_signal = Signal(list)
    steamworks_subscription_signal = Signal(list)

    def __init__(
        self,
        packageids: list,
        steam_workshop_metadata: Dict[str, Any],
    ):
        super().__init__()
        logger.debug("Initializing MissingModsPrompt")

        self.installEventFilter(self)

        self.data_by_variants = {}
        self.DEPENDENCY_TAG = "_-_DEPENDENCY_-_"
        self.packageids = packageids
        self.steam_workshop_metadata = steam_workshop_metadata
        self.setObjectName("missingModsPanel")
        # MOD LABEL
        self.missing_mods_label = QLabel(
            "There are mods missing from the active mods list!"
        )
        self.missing_mods_label.setAlignment(Qt.AlignCenter)

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
            "\nUser-configured SteamDB database was queried. The following table displays mods available for download from Steam. "
            + '\n\nRimworld mods on Steam Workshop that share a packageId are "variants". Please keep this in mind before downloading. '
            + "\n\nPlease select your preferred mod variant in the table below. You can also open each variant in Steam/Web browser to verify."
        )
        self.details_label.setAlignment(Qt.AlignCenter)

        # EDITOR WIDGETS
        # Create the model and set column headers
        self.editor_model = QStandardItemModel(0, 5)
        self.editor_model.setHorizontalHeaderLabels(
            [
                "Name",
                "PackageId",
                "Game Versions",
                "# Variants",
                "PublishedFileID",
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
            0, QHeaderView.Stretch
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
        self.editor_cancel_button = QPushButton("Do nothing and exit")
        self.editor_cancel_button.clicked.connect(self.close)
        self.editor_download_steamcmd_button = QPushButton("Download with SteamCMD")
        self.editor_download_steamcmd_button.clicked.connect(
            partial(self._download_list_from_table, mode="steamcmd")
        )
        self.editor_download_steamworks_button = QPushButton(
            "Download with Steam client"
        )
        self.editor_download_steamworks_button.clicked.connect(
            partial(self._download_list_from_table, mode="steamworks")
        )
        self.editor_actions_layout.addWidget(self.editor_cancel_button)
        self.editor_actions_layout.addWidget(self.editor_download_steamcmd_button)
        self.editor_actions_layout.addWidget(self.editor_download_steamworks_button)

        # Build the details layout
        self.details_layout.addWidget(self.details_label)

        # Build the editor layouts
        self.editor_layout.addWidget(self.editor_table_view)
        self.editor_layout.addLayout(self.editor_actions_layout)

        # Add our widget layouts to the containers
        self.upper_layout.addLayout(self.details_layout)
        self.lower_layout.addLayout(self.editor_layout)

        # Add our layouts to the main layout
        self.layout.addWidget(self.missing_mods_label)
        self.layout.addLayout(self.upper_layout)
        self.layout.addLayout(self.lower_layout)

        # Put it all together
        self.setWindowTitle("RimSort - Missing mods found")
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
        packageid: str,
        gameVersions: list,
        mod_variants: str,
        publishedfileid: str,
    ):
        # Check if a row with the given packageid already exists
        for row in range(self.editor_model.rowCount()):
            if self.editor_model.item(row, 1).text() == packageid:
                # If an existing row is found, add the new publishedfileid
                existing_item = self.editor_model.item(row, 4)
                combo_box = self.editor_table_view.indexWidget(existing_item.index())
                combo_box.addItem(publishedfileid)
                return  # Return here to exit function
        # If we're still here, we need to actually create a new row
        items = [
            QStandardItem(name),
            QStandardItem(packageid),
            QStandardItem(str(gameVersions)),
            QStandardItem(mod_variants if publishedfileid != "" else "0"),
            QStandardItem(),
        ]
        self.editor_model.appendRow(items)
        # Add our combo box to the row's column 5 and connect to update signal
        combo_box_index = items[4].index()
        combo_box = QComboBox()
        combo_box.setEditable(True)
        combo_box.setObjectName("missing_mods_variant_cb")
        combo_box.addItem(publishedfileid)
        # Connect the currentTextChanged signal
        combo_box.currentTextChanged.connect(self._update_mod_info)
        # Set the combo_box as the index widget
        self.editor_table_view.setIndexWidget(combo_box_index, combo_box)

    def _download_list_from_table(self, mode: str) -> None:
        publishedfileids = []
        # Iterate through the editor's rows
        for row in range(self.editor_model.rowCount()):
            if self.editor_model.item(row):  # If there is a row at current index
                # If an existing row is found, get the combo box
                combo_box = self.editor_table_view.indexWidget(
                    self.editor_model.item(row, 4).index()
                )
                # Get the publishedfileid and append to our list
                publishedfileid = combo_box.currentText()
                if publishedfileid != "":
                    publishedfileids.append(publishedfileid)
        self.close()
        if mode == "steamcmd":
            self.steamcmd_downloader_signal.emit(publishedfileids)
        elif mode == "steamworks":
            self.steamworks_subscription_signal.emit(
                [
                    "subscribe",
                    [eval(str_pfid) for str_pfid in publishedfileids],
                ]
            )

    def _populate_from_metadata(self) -> None:
        # Build a dict of missing mod variant(s)
        if (
            self.steam_workshop_metadata
            and len(self.steam_workshop_metadata.keys()) > 0
        ):
            # Generate a list of all missing mods + any missing mod dependencies listed
            # in the user-configured Steam metadata.
            for publishedfileid, metadata in self.steam_workshop_metadata.items():
                name = metadata.get("steamName", metadata.get("name", "Not found"))
                packageid = metadata.get("packageId", "None").lower()
                gameVersions = metadata.get("gameVersions", ["None listed"])

                # Remove AppId dependencies from this dict. They cannot be subscribed like mods.
                dependencies = {
                    key: value
                    for key, value in metadata.get("dependencies", {}).items()
                    if key not in RIMWORLD_DLC_METADATA.keys()
                }

                # Populate data_by_variants dict
                if packageid in self.packageids:
                    variants = self.data_by_variants.setdefault(packageid, {})
                    variants[publishedfileid] = {
                        "name": name,
                        "gameVersions": gameVersions,
                        "dependencies": dependencies,
                    }

            # If we couldn't find any from Steam metadata, we still want to populate a blank row for user input
            for packageid in self.packageids:
                if packageid not in self.data_by_variants.keys():
                    self.data_by_variants[packageid] = {
                        "": {
                            "name": "Not found",
                            "gameVersions": ["None listed"],
                        }
                    }

            # Add a row for each mod variant
            for packageid, variants in self.data_by_variants.items():
                for publishedfileid, variant_data in variants.items():
                    self._add_row(
                        name=variant_data["name"],
                        packageid=packageid,
                        gameVersions=variant_data["gameVersions"],
                        mod_variants=str(len(variants.keys())),
                        publishedfileid=publishedfileid,
                    )

    def _update_mod_info(self, publishedfileid: str):
        combo_box = self.sender()
        index = self.editor_table_view.indexAt(combo_box.pos())
        if index.isValid():
            row = index.row()
            packageid = self.editor_model.item(row, 1).text()
            self.editor_model.item(row, 0).setText(
                self.data_by_variants.get(packageid)
                .get(publishedfileid, {})
                .get("name", "No variant found!")
            )
            self.editor_model.item(row, 2).setText(
                str(
                    self.data_by_variants.get(packageid)
                    .get(publishedfileid, {})
                    .get("gameVersions", "No variant found!")
                )
            )
