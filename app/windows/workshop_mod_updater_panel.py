from functools import partial

from loguru import logger
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import (
    QPushButton,
)

from app.utils.generic import format_time_display, platform_specific_open
from app.utils.metadata import MetadataManager
from app.windows.base_mods_panel import BaseModsPanel


class WorkshopModUpdaterPanel(BaseModsPanel):
    """
    A panel used to prompt a user to update eligible Workshop mods.

    This panel displays a table of Workshop mods that have updates available,
    showing information like mod name, source, last local access time, and
    last update time on the Workshop. Users can select mods to update individually
    or update all at once. Each mod row includes a button to open the Workshop page.

    Attributes:
        mm (MetadataManager): Instance of MetadataManager for accessing mod metadata.
    """

    def __init__(self) -> None:
        """
        Initialize the WorkshopModUpdaterPanel.

        Sets up the panel with translated UI elements, buttons for updating mods,
        and loads ACF data for timestamp handling.
        """
        logger.debug("Initializing WorkshopModUpdaterPanel")
        self.mm = MetadataManager.instance()

        super().__init__(
            object_name="updateModsPanel",
            window_title=self.tr("RimSort - Updates found for Workshop mods"),
            title_text=self.tr("There updates available for Workshop mods!"),
            details_text=self.tr(
                "\nThe following table displays Workshop mods available for update from Steam."
            ),
            additional_columns=[
                self.tr("Name"),
                self.tr("PublishedFileID"),
                self.tr("Mod Source"),
                self.tr("Mod Downloaded"),
                self.tr("Updated on Workshop"),
                self.tr("Workshop Page"),
            ],
        )

        # EDITOR WIDGETS
        # Create buttons for updating mods
        self.editor_update_mods_button = QPushButton(self.tr("Update Selected Mods"))
        self.editor_update_mods_button.clicked.connect(
            partial(self._update_mods_from_table, 2, 3)
        )
        self.editor_update_all_button = QPushButton(self.tr("Update All Mods"))
        self.editor_update_all_button.clicked.connect(partial(self._update_all_mods))

        # Add buttons to the main actions layout
        self.editor_main_actions_layout.addWidget(self.editor_update_mods_button)
        self.editor_main_actions_layout.addWidget(self.editor_update_all_button)

    def _update_all_mods(self) -> None:
        """
        Update all mods in the table.

        Selects all checkboxes and triggers the update process for all mods.
        """
        self._set_all_checkbox_rows(True)
        self._update_mods_from_table(2, 3)

    def _populate_from_metadata(self) -> None:
        """
        Populate the table with mods that have available updates.

        Iterates through internal local metadata to find mods with updates available.
        For each eligible mod, creates table rows with mod information, timestamps,
        and workshop page buttons.
        """
        logger.debug("Starting to populate table with mods that have updates available")
        start_time = __import__("time").time()

        # Pre-filter eligible metadata to improve performance
        eligible_metadata = [
            metadata
            for metadata in self.mm.internal_local_metadata.values()
            if (
                (metadata.get("steamcmd") or metadata.get("data_source") == "workshop")
                and metadata.get("internal_time_touched")
                and metadata.get("external_time_updated")
                and metadata["external_time_updated"]
                > metadata["internal_time_touched"]
            )
        ]

        logger.debug(f"Found {len(eligible_metadata)} eligible mods for update")

        # Check our metadata for available updates, append row if found by data source
        for metadata in eligible_metadata:
            # Retrieve values from metadata
            name = metadata.get("name")
            publishedfileid = metadata.get("publishedfileid")
            mod_source = "SteamCMD" if metadata.get("steamcmd") else "Steam"

            # Use new format_time_display function
            touched_text, internal_time_touched = format_time_display(
                metadata.get("internal_time_touched")
            )
            updated_text, external_time_updated = format_time_display(
                metadata.get("external_time_updated")
            )

            # Create table items
            name_item = QStandardItem(name)
            name_item.setToolTip(name)
            pfid_item = QStandardItem(publishedfileid)
            source_item = QStandardItem(mod_source)
            touched_item = QStandardItem(touched_text)
            touched_item.setData(internal_time_touched)
            updated_item = QStandardItem(updated_text)
            updated_item.setData(external_time_updated)

            # Create workshop button item and button
            workshop_btn_item = QStandardItem(publishedfileid)
            workshop_btn = self._create_workshop_button(
                f"https://steamcommunity.com/sharedfiles/filedetails/?id={publishedfileid}",
                "workshopButton",
            )

            # Prepare items list for row addition
            items = [
                name_item,
                pfid_item,
                source_item,
                touched_item,
                updated_item,
                workshop_btn_item,
            ]
            # Add row to table
            self._add_row(items)

            # Set the workshop button as the widget for the last column
            self.editor_table_view.setIndexWidget(
                workshop_btn_item.index(), workshop_btn
            )

        end_time = __import__("time").time()
        logger.debug(f"Populated table in {end_time - start_time:.2f} seconds")

    def _create_workshop_button(self, url: str, object_name: str) -> QPushButton:
        """
        Create a QPushButton that opens a Steam Workshop page.

        Args:
            url (str): The URL of the Steam Workshop page to open.
            object_name (str): The object name for the button (for styling).

        Returns:
            QPushButton: The configured button that opens the workshop page when clicked.
        """
        button = QPushButton()
        button.setObjectName(object_name)
        button.setText(self.tr("Open Workshop Page"))
        button.clicked.connect(partial(platform_specific_open, url))
        return button
