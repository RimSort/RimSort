from functools import partial
from time import localtime, strftime

from loguru import logger
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import (
    QPushButton,
)


from app.utils.generic import check_if_steam_running
from app.views.dialogue import show_information, show_warning
from app.windows.base_mods_panel import BaseModsPanel



class ModUpdaterPrompt(BaseModsPanel):
    """
    A generic panel used to prompt a user to update eligible Workshop mods
    """

    def __init__(self) -> None:
        logger.debug("Initializing ModUpdaterPrompt")
        self.updates_found = False

        self.installEventFilter(self)

        self.internal_mod_metadata = internal_mod_metadata
        self.setObjectName("missingModsPanel")
        # MOD LABEL
        self.updates_available_label = QLabel(
            "There are updates available for Workshop mods!"
        )
        self.updates_available_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        super().__init__(
            object_name="updateModsPanel",
            window_title="RimSort - Updates found for Workshop mods",
            title_text="There updates available for Workshop mods!",
            details_text="\nThe following table displays Workshop mods available for update from Steam.",
            additional_columns=[
                "Name",
                "PublishedFileID",
                "Mod source",
                "Mod last touched",
                "Mod last updated",
                # "Open page",
            ],
        )

        # EDITOR WIDGETS

        self.editor_update_mods_button = QPushButton("Update mods")
        self.editor_update_mods_button.clicked.connect(
            partial(self._update_mods_from_table, 2, 3)
        )
        self.editor_update_all_button = QPushButton("Update all")
        self.editor_update_all_button.clicked.connect(partial(self._update_all_mods))

        self.editor_main_actions_layout.addWidget(self.editor_update_mods_button)
        self.editor_main_actions_layout.addWidget(self.editor_update_all_button)

        return super().eventFilter(obj, event)

    def _add_row(
        self,
        name: str,
        publishedfileid: str,
        mod_source: str,
        internal_time_touched: str,
        external_time_updated: str,
    ) -> None:
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
                assert isinstance(checkbox, QCheckBox)
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
                assert isinstance(checkbox, QCheckBox)
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
            # First check if steam is running
            if not check_if_steam_running():
                logger.warning("Steam is not running. Cannot resubscribe to Steam mods.")
                show_warning(
                    title="Steam not running",
                    text="Unable to resubscribe to Steam mods. Ensure Steam is running and try again.",
                )
                return

            self.steamworks_subscription_signal.emit(
                [
                    "resubscribe",
                    [eval(str_pfid) for str_pfid in steam_publishedfileids],
                ]
            )
            show_information(
                title="Finished Updating Steam Mods",
                text="Updates may require running Steam Validation to be reflected.",
            )
        self.close()

    def _update_all(self) -> None:
        self._deselect_select_all_rows(True)
        self._update_mods_from_table()

    def _update_all_mods(self) -> None:
        self._set_all_checkbox_rows(True)
        self._update_mods_from_table(2, 3)


    def _populate_from_metadata(self) -> None:
        # Check our metadata for available updates, append row if found by data source
        for metadata in self.metadata_manager.internal_local_metadata.values():
            if (
                (metadata.get("steamcmd") or metadata.get("data_source") == "workshop")
                and metadata.get("internal_time_touched")
                and metadata.get("external_time_updated")
                and metadata["external_time_updated"]
                > metadata["internal_time_touched"]
            ):
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
                name_item = QStandardItem(name)
                name_item.setToolTip(name)
                items = [
                    name_item,
                    QStandardItem(publishedfileid),
                    QStandardItem(mod_source),
                    QStandardItem(internal_time_touched),
                    QStandardItem(external_time_updated),
                ]
                # Add row to table
                self._add_row(items)
