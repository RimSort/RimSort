from functools import partial
from time import localtime, strftime

from loguru import logger
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import (
    QPushButton,
)

from app.windows.base_mods_panel import BaseModsPanel


class ModUpdaterPrompt(BaseModsPanel):
    """
    A generic panel used to prompt a user to update eligible Workshop mods
    """

    def __init__(self) -> None:
        logger.debug("Initializing ModUpdaterPrompt")

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
