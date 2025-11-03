from collections import defaultdict
from dataclasses import dataclass
from functools import partial
from typing import Any, Dict, List, Optional

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QStandardItem
from PySide6.QtWidgets import QCheckBox, QHeaderView, QMenu, QPushButton, QToolButton

from app.utils.generic import format_time_display, platform_specific_open
from app.utils.metadata import MetadataManager, ModMetadata
from app.views import dialogue
from app.views.deletion_menu import ModDeletionMenu
from app.windows.base_mods_panel import BaseModsPanel, HeaderColumn


@dataclass
class ReplacementInfo:
    """
    Represents information about a replacement mod.

    Attributes:
        name: Name of the replacement mod.
        author: Author of the replacement mod.
        packageid: Package ID of the replacement mod.
        pfid: Published file ID of the replacement mod.
        supportedversions: Supported versions of the replacement mod.
    """

    name: str
    author: str
    packageid: str
    pfid: str
    supportedversions: Any


@dataclass
class ModGroupItem:
    """
    Represents a mod item in a group, containing metadata and identifiers.

    Attributes:
        mod_id: Unique identifier for the mod.
        metadata: Dictionary containing mod metadata.
        replacement: Optional replacement mod information.
    """

    mod_id: str
    metadata: Dict[str, Any]
    replacement: Optional[ReplacementInfo] = None


class UseThisInsteadPanel(BaseModsPanel):
    """
    Panel for displaying Workshop mods with suggested replacements from the "Use This Instead" database.
    Groups mods by replacement mod and provides actions for subscription, unsubscription, and deletion.
    """

    def __init__(self, mod_metadata: Dict[str, Any]) -> None:
        """
        Initialize the UseThisInsteadPanel with mod metadata.

        Args:
            mod_metadata: Dictionary of mod metadata keyed by mod identifier.
        """
        logger.debug("Initializing UseThisInsteadPanel")
        self.mod_metadata = mod_metadata
        self.mm = MetadataManager.instance()

        # Define table columns for displaying mod information
        additional_columns: list[HeaderColumn] = [
            self.tr("Mod Name"),
            self.tr("Author"),
            self.tr("Package ID"),
            self.tr("PublishedFileId"),
            self.tr("Supported Versions"),
            self.tr("Source"),
            self.tr("Mod Downloaded"),
            self.tr("Path"),
            self.tr("Workshop Page"),
        ]

        super().__init__(
            object_name="useThisInsteadModsPanel",
            window_title=self.tr("RimSort - Replacements found for Workshop mods"),
            title_text=self.tr("There are replacements available for Workshop mods!"),
            details_text=self.tr(
                "The following table displays Workshop mods with suggested replacements "
                'according to the "Use This Instead" database, grouped by replacement mod.'
            ),
            additional_columns=additional_columns,
        )

        self._setup_buttons()
        self._populate_from_metadata()

        # Set all rows to auto-resize to content
        self.editor_table_view.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )

        # Disable sorting to maintain mod grouping by package ID
        self.editor_table_view.setSortingEnabled(False)

        # TODO: let user configure window launch state and size from settings controller
        self.showNormal()

    def _setup_buttons(self) -> None:
        """Set up action buttons for the panel."""
        self._add_select_buttons()
        self._add_refresh_button()
        self._add_steamcmd_button()
        self._add_subscribe_button()
        self._add_unsubscribe_button()
        self._add_deletion_button()

    def _add_select_buttons(self) -> None:
        """Add select buttons for originals and replacements."""
        button = QToolButton()
        button.setText(self.tr("Select"))
        menu = QMenu(button)

        # Select all originals
        action = QAction(self.tr("Select all Originals"), self)
        action.triggered.connect(self._select_all_originals)
        menu.addAction(action)

        # Select all replacements
        action = QAction(self.tr("Select all Replacements"), self)
        action.triggered.connect(self._select_all_replacements)
        menu.addAction(action)

        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.editor_main_actions_layout.addWidget(button)

    def _add_refresh_button(self) -> None:
        """Add refresh button."""
        self.refresh_button = QPushButton()
        self.refresh_button.setText(self.tr("Refresh"))
        self.refresh_button.clicked.connect(self._refresh_use_this_instead_panel)
        self.editor_main_actions_layout.addWidget(self.refresh_button)

    def _add_steamcmd_button(self) -> None:
        """Add SteamCMD button with menu options."""
        button = QToolButton()
        button.setText(self.tr("SteamCMD"))
        menu = QMenu(button)

        # Download selected mods with SteamCMD
        action = QAction(self.tr("Download selected with SteamCMD"), self)
        action.triggered.connect(
            partial(
                self._update_mods_from_table,
                4,  # COL_PUBLISHED_FILE_ID
                "SteamCMD",
            )
        )
        menu.addAction(action)

        # Download all replacements with SteamCMD
        action = QAction(self.tr("Download all replacements with SteamCMD"), self)
        action.triggered.connect(
            partial(
                self._steamcmd_for_all_replacements,
                4,  # COL_PUBLISHED_FILE_ID
            )
        )
        menu.addAction(action)

        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.editor_main_actions_layout.addWidget(button)

    def _add_subscribe_button(self) -> None:
        """Add subscribe button with menu options."""
        button = QToolButton()
        button.setText(self.tr("Subscribe"))
        menu = QMenu(button)

        # Subscribe selected mods
        action = QAction(self.tr("Subscribe selected"), self)
        action.triggered.connect(
            partial(
                self._update_mods_from_table,
                4,  # COL_PUBLISHED_FILE_ID
                "Steam",
                completed=lambda self: self._on_mod_action_completed(
                    "subscribe", self._get_selected_count()
                ),
            )
        )
        menu.addAction(action)

        # Subscribe all replacements
        action = QAction(self.tr("Subscribe all replacements"), self)
        action.triggered.connect(self._subscribe_all_replacements)
        menu.addAction(action)

        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.editor_main_actions_layout.addWidget(button)

    def _add_unsubscribe_button(self) -> None:
        """Add unsubscribe button with menu options."""
        button = QToolButton()
        button.setText(self.tr("Unsubscribe"))
        menu = QMenu(button)

        # Unsubscribe selected mods
        action = QAction(self.tr("Unsubscribe selected"), self)
        action.triggered.connect(
            partial(
                self._update_mods_from_table,
                4,  # COL_PUBLISHED_FILE_ID
                "Steam",
                "unsubscribe",
                completed=lambda self: self._on_mod_action_completed(
                    "unsubscribe", self._get_selected_count()
                ),
            )
        )
        menu.addAction(action)

        # Unsubscribe all original mods
        action = QAction(self.tr("Unsubscribe all originals"), self)
        action.triggered.connect(self._unsubscribe_all_originals)
        menu.addAction(action)

        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.editor_main_actions_layout.addWidget(button)

    def _add_deletion_button(self) -> None:
        """Add deletion button with menu."""
        self.deletion_tool_button = QToolButton()
        self.deletion_tool_button.setText(self.tr("Delete"))
        self.deletion_menu = ModDeletionMenu(
            settings_controller=self.settings_controller,
            get_selected_mod_metadata=self._get_selected_mod_metadata,
            menu_title=self.tr("Delete Selected Original Mods..."),
            enable_delete_mod=True,
            enable_delete_keep_dds=False,
            enable_delete_dds_only=False,
            enable_delete_and_unsubscribe=True,
            enable_delete_and_resubscribe=False,
            completion_callback=self._refresh_use_this_instead_panel,
        )
        self.deletion_tool_button.setMenu(self.deletion_menu)
        self.deletion_tool_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.editor_main_actions_layout.addWidget(self.deletion_tool_button)

    def _on_mod_action_completed(self, action: str, count: int) -> None:
        """Handle successful mod action completion."""
        dialogue.show_information(
            self.tr("Use This Instead"),
            self.tr(f"Successfully {action}d {count} mods"),
        )

    def _get_selected_count(self) -> int:
        """Get the count of selected mods."""
        count = 0
        for row in range(self.editor_model.rowCount()):
            if self._row_is_checked(row):
                count += 1
        return count

    def _populate_from_metadata(self) -> None:
        """
        Populate the table with mod data grouped by replacement mod.

        This method clears the existing table, computes mod groups based on
        replacement suggestions, and populates the table with headers, original
        mods, and replacement mods.
        """
        # Clear the existing table content
        self.editor_model.removeRows(0, self.editor_model.rowCount())
        mm = MetadataManager.instance()

        # Pre-filter alternatives to avoid repeated database lookups
        # This creates a cache of mod alternatives for efficient access
        alternatives: Dict[str, Any] = {}
        for mod in self.mod_metadata:
            alt = mm.has_alternative_mod(mod)
            if alt is not None:
                alternatives[mod] = alt

        # Precompute groups: group mods by their package_id, each group contains
        # original mods that can be replaced by the same replacement mod
        groups = defaultdict(list)
        for mod, mv in self.mod_metadata.items():
            mr = alternatives.get(mod)
            if mr is None or mv is None:
                continue
            package_id: str = mv.get("packageid", "")
            groups[package_id].append(ModGroupItem(mod, mv, mr))

        # Initialize row index trackers for bulk selection operations
        self._original_rows: List[int] = []
        self._replacement_rows: List[int] = []
        current_row: int = 0

        # Process each group: add header, originals, and replacement
        group_counter: int = 1
        for package_id, originals in groups.items():
            # Add group header row
            self._add_group_header(group_counter, current_row)
            current_row += 1

            # Add all original mods in this group
            self._add_original_mods(originals, package_id, current_row)
            current_row += len(originals)

            # Add the replacement mod for this group
            self._add_replacement_mod(originals[0].replacement, package_id, current_row)
            current_row += 1

            group_counter += 1

    def _add_group_header(self, group_number: int, current_row: int) -> None:
        """
        Add a group header row to the table.

        Args:
            group_number: The number of the group.
            current_row: The current row index.
        """
        header_item = QStandardItem("")
        header_item.setData(None, Qt.ItemDataRole.UserRole)
        group_name_item = QStandardItem(f"Group {group_number}")
        self.editor_model.appendRow(
            [
                header_item,
                group_name_item,
                QStandardItem(""),
                QStandardItem(""),
                QStandardItem(""),
                QStandardItem(""),
                QStandardItem(""),
                QStandardItem(""),
                QStandardItem(""),
                QStandardItem(""),
            ]
        )

    def _add_original_mods(
        self, originals: List[ModGroupItem], package_id: str, current_row: int
    ) -> None:
        """
        Add original mods to the table.

        Args:
            originals: List of original mod group items.
            package_id: The package ID for the group.
            current_row: The starting row index for adding mods.
        """
        for i, original in enumerate(originals):
            mod = original.mod_id
            mv = original.metadata
            name = self._get_string_from_metadata(mv, "name", mod)
            authors = self._get_string_from_metadata(mv, "authors", mod)

            # Retrieve UUID for the mod from the directory mapper
            path = mv.get("path")
            uuid = (
                self.mm.mod_metadata_dir_mapper.get(path)
                if isinstance(path, str)
                else None
            )

            # Create table items for each column
            name_item = QStandardItem(f"[Original] {name}")
            name_item.setData(uuid, Qt.ItemDataRole.UserRole)

            author_item = QStandardItem(authors)
            packageid_item = QStandardItem(package_id)
            pfid_item = QStandardItem(mv["publishedfileid"])

            supported_versions = self._parse_supported_versions(
                mv.get("supportedversions")
            )
            supported_versions_item = QStandardItem(supported_versions)

            workshop_item = QStandardItem("")
            source_item = QStandardItem("SteamCMD" if mv.get("steamcmd") else "Steam")

            touched_text, _ = format_time_display(mv.get("internal_time_touched"))
            downloaded_item = QStandardItem(touched_text)
            path_item = QStandardItem(mv.get("path", ""))

            # Add the row to the table
            items = [
                name_item,
                author_item,
                packageid_item,
                pfid_item,
                supported_versions_item,
                source_item,
                downloaded_item,
                path_item,
                workshop_item,
            ]
            self._add_row(items)
            self._original_rows.append(current_row + i)

            # Add workshop button to the last column
            workshop_button = self._create_workshop_button(
                f"https://steamcommunity.com/sharedfiles/filedetails/?id={mv['publishedfileid']}",
                "originalWorkshopButton",
            )
            self.editor_table_view.setIndexWidget(
                workshop_item.index(), workshop_button
            )

    def _add_replacement_mod(self, mr: Any, package_id: str, current_row: int) -> None:
        """
        Add a replacement mod to the table.

        Args:
            mr: The replacement mod information.
            package_id: The package ID for the group.
            current_row: The row index for adding the mod.
        """
        # Check if the replacement mod already exists locally by comparing published file IDs
        exists_locally = any(
            mod.get("publishedfileid") == mr.pfid
            for mod in self.mm.internal_local_metadata.values()
        )
        status_indicator = " [Installed]" if exists_locally else ""

        # Retrieve UUID for the replacement mod if it exists locally
        uuid = None
        if exists_locally:
            for mod_uuid, mod_metadata in self.mm.internal_local_metadata.items():
                if mod_metadata.get("publishedfileid") == mr.pfid:
                    uuid = mod_uuid
                    break

        # Create table items for each column
        name_item = QStandardItem(f"[Replacement]{status_indicator} {mr.name}")
        name_item.setData(uuid, Qt.ItemDataRole.UserRole)

        author_item = QStandardItem(mr.author)
        packageid_item = QStandardItem(mr.packageid)
        pfid_item = QStandardItem(mr.pfid)

        # Parse supported versions into a string
        supported_versions = (
            mr.supportedversions
            if isinstance(mr.supportedversions, str)
            else ", ".join(mr.supportedversions.keys())
            if isinstance(mr.supportedversions, dict) and mr.supportedversions
            else ""
        )
        supported_versions_item = QStandardItem(supported_versions)

        workshop_item = QStandardItem("")

        # Populate source, downloaded, and path columns if the replacement is installed locally
        if exists_locally and uuid:
            local_metadata = self.mm.internal_local_metadata[uuid]
            source_item = QStandardItem(
                "SteamCMD" if local_metadata.get("steamcmd") else "Steam"
            )
            touched_text, _ = format_time_display(
                local_metadata.get("internal_time_touched")
            )
            downloaded_item = QStandardItem(touched_text)
            path_item = QStandardItem(local_metadata.get("path", ""))
        else:
            source_item = QStandardItem("")
            downloaded_item = QStandardItem("")
            path_item = QStandardItem("")

        # Add the row to the table
        items = [
            name_item,
            author_item,
            packageid_item,
            pfid_item,
            supported_versions_item,
            source_item,
            downloaded_item,
            path_item,
            workshop_item,
        ]
        self._add_row(items)
        self._replacement_rows.append(current_row)

        # Add workshop button to the last column
        workshop_button = self._create_workshop_button(
            f"https://steamcommunity.com/sharedfiles/filedetails/?id={mr.pfid}",
            "replacementWorkshopButton",
        )
        self.editor_table_view.setIndexWidget(workshop_item.index(), workshop_button)

    def _create_workshop_button(self, url: str, object_name: str) -> QPushButton:
        """
        Create a button to open a Steam Workshop page.

        Args:
            url: The URL to open.
            object_name: Object name for the button.

        Returns:
            Configured QPushButton.
        """
        button = QPushButton()
        button.setObjectName(object_name)
        button.setText(self.tr("Open Workshop Page"))
        button.clicked.connect(partial(platform_specific_open, url))
        return button

    def _get_string_from_metadata(
        self, metadata: Dict[str, Any], key: str, mod: str
    ) -> str:
        """
        Extract a string value from metadata, handling different types.

        Args:
            metadata: Metadata dictionary.
            key: Key to extract.
            mod: Mod identifier for error logging.

        Returns:
            String representation of the value.
        """
        value = metadata.get(key)
        if value is None:
            logger.error(f"Missing '{key}' key in metadata for mod: {mod}")
            return f"Unknown {key.capitalize()}"
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return str(value)

    def _parse_supported_versions(self, supported_versions: Any) -> str:
        """
        Parse supported versions from metadata into a string.

        Args:
            supported_versions: The supported versions data from metadata.

        Returns:
            A string representation of supported versions.
        """
        if supported_versions is None:
            return ""
        if isinstance(supported_versions, dict) and "li" in supported_versions:
            return ", ".join(supported_versions["li"])
        return ""

    def _get_selected_mod_metadata(self) -> List[ModMetadata]:
        """
        Get metadata for selected mods in the table based on checkbox states.
        """
        selected_mods = []
        for row in range(self.editor_model.rowCount()):
            if self._row_is_checked(row):
                uuid = self.editor_model.item(row, 1).data(Qt.ItemDataRole.UserRole)
                if uuid and uuid in self.mm.internal_local_metadata:
                    selected_mods.append(self.mm.internal_local_metadata[uuid])

        return selected_mods

    def _clear_all_checkboxes(self) -> None:
        """Clear all checkboxes in the table."""
        for row in range(self.editor_model.rowCount()):
            widget = self.editor_table_view.indexWidget(
                self.editor_model.item(row, 0).index()
            )
            if isinstance(widget, QCheckBox):
                widget.setChecked(False)

    def _select_all_originals(self) -> None:
        """Select all original mods in the table."""
        # Clear all checkboxes first
        self._clear_all_checkboxes()
        # Then select all originals
        for row in self._original_rows:
            checkbox = self.editor_table_view.indexWidget(
                self.editor_model.item(row, 0).index()
            )
            if isinstance(checkbox, QCheckBox):
                checkbox.setChecked(True)

    def _select_all_replacements(self) -> None:
        """Select all replacement mods in the table."""
        # Clear all checkboxes first
        self._clear_all_checkboxes()
        # Then select all replacements
        for row in self._replacement_rows:
            widget = self.editor_table_view.indexWidget(
                self.editor_model.item(row, 0).index()
            )
            if isinstance(widget, QCheckBox):
                widget.setChecked(True)

    def _steamcmd_for_all_replacements(self, pfid_column: int) -> None:
        """Download all replacement mods with SteamCMD."""
        self._select_all_replacements()
        self._update_mods_from_table(pfid_column, "SteamCMD")

    def _subscribe_all_replacements(self) -> None:
        """Subscribe to all replacement mods."""
        self._select_all_replacements()
        self._update_mods_from_table(
            4,  # COL_PUBLISHED_FILE_ID
            "Steam",
            completed=lambda self: self._on_mod_action_completed(
                "subscribe", self._get_selected_count()
            ),
        )

    def _unsubscribe_all_originals(self) -> None:
        """Unsubscribe from all original mods."""
        self._select_all_originals()
        self._update_mods_from_table(
            4,  # COL_PUBLISHED_FILE_ID
            "Steam",
            "unsubscribe",
            completed=lambda self: self._on_mod_action_completed(
                "unsubscribe", self._get_selected_count()
            ),
        )

    def _refresh_use_this_instead_panel(self) -> None:
        """
        Refresh metadata cache and use this instead panel after deletion operations.
        """
        logger.debug("Refreshing UseThisInsteadPanel after deletion")
        # Refresh internal metadata to reflect deletions
        self.mm = MetadataManager.instance()
        self.mm.refresh_cache(is_initial=False)
        # Repopulate the table with updated metadata
        self._populate_from_metadata()
