from functools import partial
from typing import Any

from loguru import logger
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import (
    QComboBox,
    QPushButton,
)

from app.utils.constants import RIMWORLD_DLC_METADATA
from app.utils.generic import check_if_steam_running
from app.views.dialogue import show_warning
from app.windows.base_mods_panel import BaseModsPanel


class MissingModsPrompt(BaseModsPanel):
    """
    A generic panel used to prompt a user to download missing mods
    """

    def __init__(
        self,
        packageids: list[str],
    ):
        logger.debug("Initializing MissingModsPrompt")

        super().__init__(
            object_name="missingModsPanel",
            window_title="RimSort - Missing mods found",
            title_text="There are mods missing from the active mods list!",
            details_text="\nUser-configured SteamDB database was queried. The following table displays mods available for download from Steam. "
            + '\n\nRimworld mods on Steam Workshop that share a packageId are "variants". Please keep this in mind before downloading. '
            + "\n\nPlease select your preferred mod variant in the table below. You can also open each variant in Steam/Web browser to verify.",
            additional_columns=[
                "Name",
                "PackageId",
                "Game Versions",
                "# Variants",
                "PublishedFileID",
                # "Open page",
            ],
        )

        self.data_by_variants: dict[str, Any] = {}
        self.DEPENDENCY_TAG = "_-_DEPENDENCY_-_"
        self.packageids = packageids

        self.editor_download_steamcmd_button = QPushButton("Download with SteamCMD")
        self.editor_download_steamcmd_button.clicked.connect(
            partial(
                self._update_mods_from_table,
                pfid_column=5,
                mode="SteamCMD",
            )
        )
        self.editor_download_steamworks_button = QPushButton(
            "Download with Steam client"
        )
        self.editor_download_steamworks_button.clicked.connect(
            partial(
                self._update_mods_from_table,
                pfid_column=5,
                mode="Steam",
            )
        )
        self.editor_main_actions_layout.addWidget(self.editor_download_steamcmd_button)
        self.editor_main_actions_layout.addWidget(
            self.editor_download_steamworks_button
        )

    def _mm_add_row(
        self,
        name: str,
        packageid: str,
        game_versions: list[str],
        mod_variants: str,
        publishedfileid: str,
    ) -> None:
        # Check if a row with the given packageid already exists
        for row in range(self.editor_model.rowCount()):
            if self.editor_model.item(row, 2).text() == packageid:
                # If an existing row is found, add the new publishedfileid
                existing_item = self.editor_model.item(row, 5)
                combo_box = self.editor_table_view.indexWidget(existing_item.index())
                if not isinstance(combo_box, QComboBox):
                    raise Exception(f"Combo box is not a QComboBox!: {combo_box}")

                combo_box.addItem(publishedfileid)
                return  # Return here to exit function
        # If we're still here, we need to actually create a new row
        name_item = QStandardItem(name)
        name_item.setToolTip(name)
        items = [
            name_item,
            QStandardItem(packageid),
            QStandardItem(str(game_versions)),
            QStandardItem(mod_variants if publishedfileid != "" else "0"),
            QStandardItem(),
        ]
        self._add_row(items)
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
                if not isinstance(combo_box, QComboBox):
                    logger.critical("Combo box is not a QComboBox! assuming empty text")
                    publishedfileid = ""
                else:
                    publishedfileid = combo_box.currentText()

                if publishedfileid != "":
                    publishedfileids.append(publishedfileid)
        self.close()
        if mode == "steamcmd":
            self.steamcmd_downloader_signal.emit(publishedfileids)
        elif mode == "steamworks":
            # Check if steam is running
            if not check_if_steam_running():
                logger.warning("Steam is not running. Cannot subscribe to mods using Steam.")
                show_warning(
                    title="Steam not running",
                    text="Unable to subscribe to Steam mods. Ensure Steam is running and try again.",
                )
                return
            self.steamworks_subscription_signal.emit(
                [
                    "subscribe",
                    [eval(str_pfid) for str_pfid in publishedfileids],
                ]
            )

    def _populate_from_metadata(self) -> None:
        # Build a dict of missing mod variant(s)
        steam_metadata = self.metadata_manager.external_steam_metadata
        if steam_metadata and len(steam_metadata.keys()) > 0:
            # Generate a list of all missing mods + any missing mod dependencies listed
            # in the user-configured Steam metadata.
            for publishedfileid, metadata in steam_metadata.items():
                name = metadata.get("steamName", metadata.get("name", "Not found"))
                packageid = metadata.get("packageId", "None").lower()
                game_versions = metadata.get("gameVersions", ["None listed"])

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
                        "gameVersions": game_versions,
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
                    self._mm_add_row(
                        name=variant_data["name"],
                        packageid=packageid,
                        game_versions=variant_data["gameVersions"],
                        mod_variants=str(len(variants.keys())),
                        publishedfileid=publishedfileid,
                    )

    def _update_mod_info(self, publishedfileid: str) -> None:
        combo_box = self.sender()
        if not isinstance(combo_box, QComboBox):
            raise ValueError(f"Sender is not a QComboBox!: {combo_box}")
        index = self.editor_table_view.indexAt(combo_box.pos())
        if index.isValid():
            row = index.row()
            packageid = self.editor_model.item(row, 1).text()
            self.editor_model.item(row, 0).setText(
                self.data_by_variants.get(packageid, {})
                .get(publishedfileid, {})
                .get("name", "No variant found!")
            )
            self.editor_model.item(row, 2).setText(
                str(
                    self.data_by_variants.get(packageid, {})
                    .get(publishedfileid, {})
                    .get("gameVersions", "No variant found!")
                )
            )
