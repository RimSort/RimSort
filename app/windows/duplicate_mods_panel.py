from functools import partial
from typing import Dict, List

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QHeaderView, QPushButton, QToolButton

from app.controllers.settings_controller import SettingsController
from app.utils.generic import format_time_display, platform_specific_open
from app.utils.metadata import MetadataManager, ModMetadata
from app.views.deletion_menu import ModDeletionMenu
from app.windows.base_mods_panel import BaseModsPanel, HeaderColumn


class DuplicateModsPanel(BaseModsPanel):
    """
    A panel used when duplicate mods are detected, allowing users to choose which version to keep.

    This panel displays duplicate mods grouped by their package ID, showing detailed
    information for each mod version. Users can select which versions to keep and
    use the deletion menu to remove unwanted duplicates.

    Attributes:
        duplicate_mods (Dict[str, List[str]]): Dictionary mapping package IDs to lists of UUIDs
            of duplicate mods.
        settings_controller (SettingsController): Controller for application settings.
        mm (MetadataManager): Instance of the metadata manager for accessing mod data.
    """

    def __init__(
        self,
        duplicate_mods: Dict[str, List[str]],
        settings_controller: SettingsController,
    ) -> None:
        """
        Initialize the DuplicateModsPanel with duplicate mods data.

        Args:
            duplicate_mods: Dictionary mapping package IDs to lists of UUIDs of duplicate mods.
            settings_controller: Controller for managing application settings.
        """
        logger.debug("Initializing DuplicateModsPanel")
        self.duplicate_mods = duplicate_mods
        self.settings_controller = settings_controller
        self.mm = MetadataManager.instance()

        # Define table columns for displaying duplicate mod information
        additional_columns: list[HeaderColumn] = [
            self.tr("Mod Name"),
            self.tr("Author"),
            self.tr("Package ID"),
            self.tr("PublishedFileId"),
            self.tr("Source"),
            self.tr("Mod Downloaded"),
            self.tr("Path"),
            self.tr("Workshop Page"),
        ]

        super().__init__(
            object_name="duplicateModsPanel",
            window_title=self.tr("RimSort - Duplicate Mods Found"),
            title_text=self.tr("Duplicate mods detected!"),
            details_text=self.tr(
                "\nThe following table displays duplicate mods grouped by package ID. "
                "Select which versions to keep and choose an action."
            ),
            additional_columns=additional_columns,
        )

        # Set up the deletion button and menu for managing duplicate mods
        self._setup_deletion_button()

        # Populate the table with duplicate mod data
        self._populate_from_metadata()

        # Set all columns to Stretch
        for i in range(self.editor_model.columnCount()):
            self.editor_table_view.horizontalHeader().setSectionResizeMode(
                i, QHeaderView.ResizeMode.Stretch
            )
        # Set all rows to auto-resize to content
        self.editor_table_view.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )

        # Disable sorting to maintain mod grouping by package ID
        self.editor_table_view.setSortingEnabled(False)

        # TODO: let user configure window launch state and size from settings controller
        self.showNormal()

    def _setup_deletion_button(self) -> None:
        """
        Set up the deletion menu button for managing duplicate mods.

        Creates a tool button with a dropdown menu that provides various deletion
        options for selected duplicate mods, including unsubscribing from Steam
        Workshop items and refreshing the panel after deletion.
        """
        # Create the tool button for the deletion menu
        self.deletion_tool_button = QToolButton()
        self.deletion_tool_button.setText(self.tr("Delete"))

        # Create the deletion menu with specific options for duplicate mods
        self.deletion_menu = ModDeletionMenu(
            settings_controller=self.settings_controller,
            get_selected_mod_metadata=self._get_selected_mod_metadata,
            menu_title=self.tr("Delete Selected Duplicates..."),
            enable_delete_mod=True,  # Allow deleting the entire mod
            enable_delete_keep_dds=False,  # Not applicable for duplicates
            enable_delete_dds_only=False,  # Not applicable for duplicates
            enable_delete_and_unsubscribe=True,  # Allow unsubscribing from Workshop
            enable_delete_and_resubscribe=False,  # Not applicable for duplicates
            completion_callback=self._refresh_after_deletion,
        )

        # Configure the button to show the menu on click
        self.deletion_tool_button.setMenu(self.deletion_menu)
        self.deletion_tool_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )

        # Add the button to the panel's action layout
        self.editor_main_actions_layout.addWidget(self.deletion_tool_button)

    def _populate_from_metadata(self) -> None:
        """
        Populate the table with duplicate mod data, grouped by package ID.

        Iterates through the duplicate mods dictionary, creating header rows for each
        package ID group and individual rows for each mod version within the group.
        Each mod row displays comprehensive information including name, author,
        package ID, published file ID, source, download time, path, and workshop link.
        """
        # Clear existing table data
        self.editor_model.removeRows(0, self.editor_model.rowCount())

        # Process each package ID group
        for packageid, uuids in self.duplicate_mods.items():
            # Create header row for the current package ID group
            group_item = QStandardItem(packageid)
            group_item.setData(
                None, Qt.ItemDataRole.UserRole
            )  # No UUID for header rows

            # Add the header row with empty cells for other columns
            self.editor_model.appendRow(
                [
                    group_item,  # Package ID as group header
                    QStandardItem(""),  # Empty Mod Name
                    QStandardItem(""),  # Empty Author
                    QStandardItem(""),  # Empty Package ID
                    QStandardItem(""),  # Empty PublishedFileId
                    QStandardItem(""),  # Empty Source
                    QStandardItem(""),  # Empty Mod Downloaded
                    QStandardItem(""),  # Empty Path
                    QStandardItem(""),  # Empty Workshop Page
                ]
            )

            # Add individual mod rows for this package ID group
            for uuid in uuids:
                # Retrieve mod metadata using UUID
                mod_data = self.mm.internal_local_metadata.get(uuid)
                if not mod_data:
                    continue  # Skip if metadata is not available

                # Extract mod information from metadata
                name = mod_data.get("name", "")
                authors = mod_data.get("authors", "")
                path = mod_data.get("path", "")
                pfid = mod_data.get("publishedfileid", "")
                mod_source = "SteamCMD" if mod_data.get("steamcmd") else "Steam"

                # Format the download time for display
                touched_text, internal_time_touched = format_time_display(
                    mod_data.get("internal_time_touched")
                )

                # Create table items for each column
                name_item = QStandardItem(name)
                name_item.setData(
                    uuid, Qt.ItemDataRole.UserRole
                )  # Store UUID for selection
                authors_item = QStandardItem(authors)
                packageid_item = QStandardItem(packageid)
                pfid_item = QStandardItem(pfid)
                source_item = QStandardItem(mod_source)
                path_item = QStandardItem(path)
                downloaded_item = QStandardItem(touched_text)
                downloaded_item.setData(internal_time_touched)  # Store raw timestamp

                # Create workshop button for opening the mod's Steam Workshop page
                workshop_btn_item = QStandardItem(pfid)
                workshop_btn = self._create_workshop_button(
                    f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}",
                    "workshopButton",
                )

                # Add the complete mod row to the table
                self._add_row(
                    [
                        name_item,
                        authors_item,
                        packageid_item,
                        pfid_item,
                        source_item,
                        downloaded_item,
                        path_item,
                        workshop_btn_item,
                    ]
                )

                # Set the workshop button as the widget for the last column
                self.editor_table_view.setIndexWidget(
                    workshop_btn_item.index(), workshop_btn
                )

    def _create_workshop_button(self, url: str, object_name: str) -> QPushButton:
        """
        Create a button that opens the Steam Workshop page for a mod.

        Args:
            url: The full URL to the Steam Workshop page.
            object_name: The object name for the button widget.

        Returns:
            QPushButton: Configured button that opens the workshop page when clicked.
        """
        button = QPushButton()
        button.setObjectName(object_name)
        button.setText(self.tr("Open Workshop Page"))
        button.clicked.connect(partial(platform_specific_open, url))
        return button

    def _get_selected_mod_metadata(self) -> List[ModMetadata]:
        """
        Retrieve metadata for mods selected in the table via checkboxes.

        Iterates through all table rows, checking which ones are selected via
        the checkbox state. For selected rows, extracts the UUID from the Mod Name
        column and retrieves the corresponding metadata from the metadata manager.

        Returns:
            List[ModMetadata]: List of metadata objects for selected mods.
        """
        selected_mods = []
        for row in range(self.editor_model.rowCount()):
            if self._row_is_checked(row):
                # UUID is stored in the Mod Name column (index 1)
                uuid = self.editor_model.item(row, 1).data(Qt.ItemDataRole.UserRole)
                if uuid and uuid in self.mm.internal_local_metadata:
                    selected_mods.append(self.mm.internal_local_metadata[uuid])

        return selected_mods

    def _refresh_after_deletion(self) -> None:
        """
        Refresh the metadata cache and repopulate the table after deletion operations.

        This method is called as a callback after mods are deleted. It refreshes
        the metadata cache to reflect the changes and repopulates the table with
        the updated duplicate mod data.
        """
        logger.debug(
            "Refreshing mod list and closing DuplicateModsPanel after deletion"
        )
        # Refresh the metadata cache to reflect deletion changes
        self.mm.refresh_cache(is_initial=False)
        # Repopulate the table with updated data
        self._populate_from_metadata()
