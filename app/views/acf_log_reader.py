"""
ACF Log Reader for displaying workshop items from Steam ACF files.

Inherits table infrastructure, column definitions, and action buttons from BaseModsPanel.
Displays all workshop items found in SteamCMD and Steam ACF data with features including:
- Real-time search filtering with column-specific search
- Active mod highlighting (mods currently in the game's load order)
- Clickable path links to open mod directories
- Workshop page buttons to open Steam Community pages
- CSV export functionality
- ACF file import/export
- Default sorting by download date (newest first)
"""

from __future__ import annotations

import time
from typing import Any, Optional, cast

from loguru import logger
from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QStandardItem
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from app.controllers.settings_controller import SettingsController
from app.utils.csv_export_utils import export_to_csv
from app.utils.event_bus import EventBus
from app.utils.generic import format_time_display
from app.utils.metadata import MetadataManager
from app.utils.mod_info import ModInfo
from app.windows.base_mods_panel import BaseModsPanel, ColumnIndex


class AcfLogReader(BaseModsPanel):
    """
    ACF Log Reader panel for displaying workshop items from Steam ACF files.

    Features:
    - Displays workshop items from both SteamCMD and Steam Workshop ACF data
    - Inherits table UI, columns, and buttons from BaseModsPanel
    - Real-time search with debouncing (300ms delay) and column-specific filtering
    - Active mod highlighting: cells with bold white text on dark green background
    - Interactive widgets: clickable path links and workshop page buttons
    - Automatic sorting by download date on initial load; user can change sort order
    - ACF file import/export and CSV export functionality
    """

    # Columns to search in the search bar
    SEARCHABLE_COLUMNS = [
        ColumnIndex.NAME.value,
        ColumnIndex.AUTHOR.value,
        ColumnIndex.PACKAGE_ID.value,
        ColumnIndex.PUBLISHED_FILE_ID.value,
    ]

    # Default sort column and order
    DEFAULT_SORT_COLUMN = ColumnIndex.MOD_DOWNLOADED.value
    DEFAULT_SORT_ORDER = Qt.SortOrder.DescendingOrder

    def __init__(
        self,
        settings_controller: SettingsController,
        active_mods_list: object | None = None,
    ) -> None:
        """
        Initialize ACF Log Reader using BaseModsPanel.

        Args:
            settings_controller: Settings controller instance
            active_mods_list: Optional active mods list for highlighting
        """
        self.settings_controller = settings_controller
        self.active_mods_list = active_mods_list
        self.metadata_manager = MetadataManager.instance()
        # Set of PFIDs that are currently active in the game
        self.active_pfids: set[str] = set()
        # Timer for debouncing search input (300ms delay)
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._perform_search)
        # Selected column index for filtering (-1 means all searchable columns)
        self.search_column_index = -1
        # Track if this is the first population (for initial sorting)
        self._is_first_population = True

        # Initialize BaseModsPanel with standard columns
        super().__init__(
            object_name="AcfLogReader",
            window_title="ACF Log Reader",
            title_text="Workshop Items from ACF Files",
            details_text="Displays all mods in your SteamCMD and Steam ACF data",
            additional_columns=self._get_standard_mod_columns(),
        )

        # Set up BaseModsPanel buttons (Refresh, etc.)
        button_configs = self._get_base_button_configs()
        self._extend_button_configs_with_steam_actions(button_configs)
        button_configs.append(
            self._create_delete_button_config(self.tr("Delete Selected Mods"))
        )
        self._setup_buttons_from_config(button_configs)

        # Set up custom ACF buttons above the table
        acf_buttons_layout = QHBoxLayout()

        self.import_acf_btn = QPushButton(self.tr("Import ACF Data"))
        self.import_acf_btn.clicked.connect(self._on_import_acf_clicked)
        acf_buttons_layout.addWidget(self.import_acf_btn)

        self.export_acf_btn = QPushButton(self.tr("Export ACF Data"))
        self.export_acf_btn.clicked.connect(self._on_export_acf_clicked)
        acf_buttons_layout.addWidget(self.export_acf_btn)

        self.export_csv_btn = QPushButton(self.tr("Export to CSV"))
        self.export_csv_btn.clicked.connect(self._on_export_to_csv_clicked)
        acf_buttons_layout.addWidget(self.export_csv_btn)

        # Add search bar
        acf_buttons_layout.addStretch()

        search_label = QLabel(self.tr("Search:"))
        acf_buttons_layout.addWidget(search_label)

        # Column filter dropdown
        self.search_column_filter = QComboBox()
        self.search_column_filter.addItem(self.tr("All Searchable Columns"), -1)
        for col_idx in self.SEARCHABLE_COLUMNS:
            col_name = ColumnIndex(col_idx).name.replace("_", " ").title()
            self.search_column_filter.addItem(col_name, col_idx)
        self.search_column_filter.currentIndexChanged.connect(
            self._on_search_column_changed
        )
        acf_buttons_layout.addWidget(self.search_column_filter)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            self.tr(
                "Searches selected column or all searchable columns if set to 'All'"
            )
        )
        self.search_input.textChanged.connect(self._on_search_text_changed)
        acf_buttons_layout.addWidget(self.search_input, 1)

        # Insert button layout above the table in editor_layout
        self.layouts.editor_layout.insertLayout(0, acf_buttons_layout)

        # Set up active mod delegate for highlighting active mods
        self.active_mod_delegate = ActiveModDelegate(parent=self)
        self.editor_table_view.setItemDelegate(self.active_mod_delegate)

        self.start_acf_reader()

    def start_acf_reader(self) -> None:
        """
        Populate ACF table when metadata refresh completes
        Ensures both metadata and active mods list are synchronized
        Ensures that acf reader is always refreshed when metadata is updated.
        Triggered by do_refresh method in main_content_panel.py
        """
        # TODO; need to find a better way to ensure this happens every time metadata is updated other than manual refresh
        EventBus().refresh_finished.connect(self._populate_from_metadata)

    def _batch_add_acf_rows(
        self,
        acf_entries: list[tuple[str, str, int | None]],
        pfid_to_mod: dict[str, tuple[str, dict[str, Any]]],
    ) -> None:
        """
        Batch add multiple ACF rows directly to the model without individual widget creation.

        Adds all items to the model in one operation, then adds checkboxes in batch.
        Also adds clickable path links and workshop page buttons.

        Args:
            acf_entries: List of (pfid, source, timeupdated) tuples
            pfid_to_mod: Pre-built map of PFID to (UUID, metadata) tuples
        """
        # Prepare all rows and track metadata for widget creation
        all_rows = []
        row_metadata = []  # Store (path, workshop_url) for each row

        for pfid, source, timeupdated in acf_entries:
            try:
                if pfid in pfid_to_mod:
                    uuid, metadata = pfid_to_mod[pfid]
                else:
                    uuid = None
                    metadata = {
                        "name": f"Unknown (PFID: {pfid})",
                        "authors": "",
                        "packageid": "",
                        "publishedfileid": pfid,
                        "supportedversions": "",
                        "path": "",
                    }

                name = metadata.get("name", f"Unknown (PFID: {pfid})")
                authors = metadata.get("authors", "")
                packageid = metadata.get("packageid", pfid)
                supported_versions = ModInfo._parse_supported_versions_static(
                    metadata.get("supportedversions")
                )
                path = metadata.get("path", "")

                # Format time displays
                downloaded_time_raw = metadata.get("internal_time_touched")
                downloaded_time = (
                    format_time_display(int(downloaded_time_raw))[0]
                    if downloaded_time_raw
                    else ""
                )

                # Use timeupdated from ACF if provided, otherwise use metadata
                update_time_raw = (
                    timeupdated
                    if timeupdated
                    else metadata.get("external_time_updated")
                )
                updated_time = (
                    format_time_display(int(update_time_raw))[0]
                    if update_time_raw
                    else ""
                )

                workshop_url = ModInfo._generate_workshop_url(pfid)

                # Create items directly
                # Note: Path and Workshop URL columns will be displayed via widgets,
                # so they are created as empty items to avoid duplicate display
                base_items = [
                    QStandardItem(name),
                    QStandardItem(authors),
                    QStandardItem(packageid),
                    QStandardItem(pfid),
                    QStandardItem(supported_versions),
                    QStandardItem(downloaded_time),
                    QStandardItem(updated_time),
                    QStandardItem(source),
                    QStandardItem(""),  # Path will be displayed via widget
                    QStandardItem(""),  # Workshop URL will be displayed via widget
                ]

                # Set UUID data on name item
                if uuid:
                    base_items[0].setData(uuid, Qt.ItemDataRole.UserRole)

                all_rows.append(base_items)
                row_metadata.append((path, workshop_url))
            except Exception as e:
                logger.error(f"Failed to prepare ACF entry {pfid}: {e}", exc_info=True)
                continue

        # Track starting row count before adding new rows
        start_row = self.editor_model.rowCount()

        # Add all rows to model (appendRow is called for each, which is unavoidable)
        for items in all_rows:
            # Add empty string to prevent "None" text from appearing when ActiveModDelegate paints active mod cells
            checkbox_item = QStandardItem("")
            row_items = [checkbox_item] + items
            self.editor_model.appendRow(row_items)

        # Add checkboxes and interactive widgets (path links and workshop buttons)
        for i, row_idx in enumerate(range(start_row, self.editor_model.rowCount())):
            # Add checkbox
            checkbox = QCheckBox()
            checkbox.setObjectName("selectCheckbox")
            checkbox_index = self.editor_model.item(row_idx, 0).index()
            self.editor_table_view.setIndexWidget(checkbox_index, checkbox)

            # Add path link if path exists
            path, workshop_url = row_metadata[i]
            if path and path.strip():
                path_link = self._create_path_link(path, "pathLink")
                path_index = self.editor_model.item(
                    row_idx, ColumnIndex.PATH.value
                ).index()
                self.editor_table_view.setIndexWidget(path_index, path_link)

            # Add workshop button if workshop URL exists
            if workshop_url:
                workshop_button = self._create_workshop_button(
                    workshop_url, "workshopButton"
                )
                workshop_index = self.editor_model.item(
                    row_idx, ColumnIndex.WORKSHOP_PAGE.value
                ).index()
                self.editor_table_view.setIndexWidget(workshop_index, workshop_button)

    def _apply_sort_and_enable(self) -> None:
        """
        Apply default sort indicator and enable sorting mode after initial table population.

        Sets the visual sort indicator on the "Mod Downloaded" column in descending order.
        Actual sorting is deferred to user clicks on column headers to avoid performance
        impact from string-based sorting of formatted timestamps.
        """
        # Enable user-triggered sorting via column header clicks
        self.editor_table_view.setSortingEnabled(True)

        # Set sort indicator on the header (rows are already in correct order)
        self.editor_table_view.horizontalHeader().setSortIndicator(
            self.DEFAULT_SORT_COLUMN, self.DEFAULT_SORT_ORDER
        )

    def _update_active_pfids(self) -> None:
        """
        Update the set of active PFIDs from active_mods_list.

        Extracts Published File IDs (PFIDs) from the UUIDs of mods currently active
        in the game's load order. These PFIDs are used by ActiveModDelegate to highlight
        matching rows in the table with bold white text on dark green background.

        Repaints the table viewport after updating to apply the highlighting changes.
        """
        self.active_pfids.clear()
        if not self.active_mods_list:
            return

        if not hasattr(self.active_mods_list, "uuids"):
            return

        uuids = getattr(self.active_mods_list, "uuids", [])
        for mod_uuid in uuids:
            metadata = self.metadata_manager.internal_local_metadata.get(mod_uuid)
            if metadata:
                pfid = metadata.get("publishedfileid")
                if pfid:
                    self.active_pfids.add(str(pfid))

        # Repaint table viewport to apply active mod highlighting
        self.editor_table_view.viewport().update()

    def _populate_from_metadata(self) -> None:
        """
        Populate the ACF table from MetadataManager's ACF and metadata.

        Reads steamcmd_acf_data and workshop_acf_data from MetadataManager and displays
        all workshop items in the table with the following process:
        1. Updates active PFID set for mod highlighting
        2. Extracts workshop entries from both ACF sources
        3. Batch adds rows with checkboxes, path links, and workshop buttons
        4. Enables sorting (sets default sort on first load, preserves user sort on refresh)

        Called automatically when EventBus().refresh_finished signal is emitted
        (triggered on app startup and after manual refresh).
        """
        logger.warning("Populating ACF Log Reader")
        overall_start = time.time()
        # Update active PFIDs from active mods list
        self._update_active_pfids()

        try:
            self._clear_table_model()

            # Get ACF data from MetadataManager
            steamcmd_acf_data = self.metadata_manager.steamcmd_acf_data
            workshop_acf_data = self.metadata_manager.workshop_acf_data

            logger.debug(
                f"SteamCMD ACF data loaded: {bool(steamcmd_acf_data)}, "
                f"Workshop ACF data loaded: {bool(workshop_acf_data)}, "
                f"Internal metadata count: {len(self.metadata_manager.internal_local_metadata)}"
            )

            # Extract workshop items from both sources
            acf_entries = self._extract_acf_entries(
                steamcmd_acf_data, workshop_acf_data
            )

            logger.info(f"ACF Log Reader: Populating with {len(acf_entries)} entries")

            # Build PFID to mod metadata map once for fast lookups during population
            map_start = time.time()
            acf_pfids = {pfid for pfid, _, _ in acf_entries}
            pfid_to_mod = self._get_acf_mods_from_metadata(acf_pfids)
            map_elapsed = time.time() - map_start
            logger.info(f"ACF Log Reader: PFID map built in {map_elapsed:.3f}s")

            # Disable sorting while populating to improve performance
            self.editor_table_view.setSortingEnabled(False)

            # Disable updates during bulk row addition
            self.editor_table_view.setUpdatesEnabled(False)

            # Batch add all rows to the table
            add_start = time.time()
            self._batch_add_acf_rows(acf_entries, pfid_to_mod)
            add_elapsed = time.time() - add_start
            logger.info(
                f"ACF Log Reader: Added {self.editor_model.rowCount()} rows in {add_elapsed:.3f}s"
            )

            # Re-enable updates
            self.editor_table_view.setUpdatesEnabled(True)

            total_elapsed = time.time() - overall_start
            logger.info(f"ACF Log Reader: Population completed in {total_elapsed:.3f}s")

            # Apply sorting only on initial load, then let user control sorting
            if self._is_first_population:
                QTimer.singleShot(0, self._apply_sort_and_enable)
                self._is_first_population = False
            else:
                # Just enable sorting, don't change sort order
                self.editor_table_view.setSortingEnabled(True)
        except Exception as e:
            logger.error(f"Failed to populate ACF Log Reader: {e}", exc_info=True)
            # Re-enable updates even on error
            self.editor_table_view.setUpdatesEnabled(True)
            self.editor_table_view.setSortingEnabled(True)
            raise

    def _extract_acf_entries(
        self,
        steamcmd_acf_data: dict[str, Any],
        workshop_acf_data: dict[str, Any],
    ) -> list[tuple[str, str, int | None]]:
        """
        Extract workshop item entries from ACF data.

        Args:
            steamcmd_acf_data: SteamCMD ACF data dictionary with AppWorkshop wrapper
            workshop_acf_data: Workshop ACF data dictionary with AppWorkshop wrapper

        Returns:
            List of (PFID, source, timeupdated) tuples
        """
        entries = []
        seen_pfids = set()

        # Extract from SteamCMD ACF
        if steamcmd_acf_data:
            steamcmd_items = (
                steamcmd_acf_data.get("AppWorkshop", {}).get(
                    "WorkshopItemsInstalled", {}
                )
                or {}
            )
            logger.debug(f"Found {len(steamcmd_items)} items in SteamCMD ACF")
            for pfid, item_data in steamcmd_items.items():
                if isinstance(item_data, dict):
                    timeupdated = item_data.get("timeupdated")
                    try:
                        timeupdated = int(timeupdated) if timeupdated else None
                    except (ValueError, TypeError):
                        timeupdated = None
                    entries.append((pfid, "SteamCMD", timeupdated))
                    seen_pfids.add(pfid)

        # Extract from Workshop ACF (avoid duplicates)
        if workshop_acf_data:
            workshop_items = (
                workshop_acf_data.get("AppWorkshop", {}).get(
                    "WorkshopItemsInstalled", {}
                )
                or {}
            )
            logger.debug(f"Found {len(workshop_items)} items in Workshop ACF")
            for pfid, item_data in workshop_items.items():
                if pfid not in seen_pfids:
                    if isinstance(item_data, dict):
                        timeupdated = item_data.get("timeupdated")
                        try:
                            timeupdated = int(timeupdated) if timeupdated else None
                        except (ValueError, TypeError):
                            timeupdated = None
                        entries.append((pfid, "Steam", timeupdated))
                        seen_pfids.add(pfid)

        return entries

    def _get_acf_mods_from_metadata(
        self, acf_pfids: set[str]
    ) -> dict[str, tuple[str, dict[str, Any]]]:
        """
        Extract mod metadata for ACF PFIDs.

        Builds a dictionary of PFID to (UUID, metadata) for fast lookup.

        Args:
            acf_pfids: Set of PFIDs from ACF files

        Returns:
            Dictionary mapping PFID to (UUID, metadata) tuple
        """
        pfid_to_mod: dict[str, tuple[str, dict[str, Any]]] = {}
        for uuid, metadata in self.metadata_manager.internal_local_metadata.items():
            pfid = metadata.get("publishedfileid")
            if pfid:
                pfid_str = str(pfid)
                if pfid_str in acf_pfids:
                    pfid_to_mod[pfid_str] = (uuid, metadata)
        return pfid_to_mod

    def _on_import_acf_clicked(self) -> None:
        """Handle import ACF data button click."""
        self.import_acf_data()

    def _on_export_acf_clicked(self) -> None:
        """Handle export ACF data button click."""
        self.export_acf_data()

    def _on_export_to_csv_clicked(self) -> None:
        """Handle export to CSV button click."""
        self.export_to_csv()

    def import_acf_data(self) -> None:
        """
        Trigger ACF file import via EventBus signal.

        The import dialog and logic are handled by MainContentPanel._do_import_steamcmd_acf_data.
        """
        EventBus().do_import_acf.emit()

    def export_acf_data(self) -> None:
        """
        Trigger ACF file export via EventBus signal.

        The export dialog and logic are handled by MainContentPanel._do_export_steamcmd_acf_data.
        """
        EventBus().do_export_acf.emit()

    def export_to_csv(self) -> None:
        """
        Export table data to CSV file.

        Uses csv_export_utils for consistent CSV export functionality.
        """
        export_to_csv(self)

    def _on_search_column_changed(self, index: int) -> None:
        """
        Handle search column filter dropdown change.

        Args:
            index: The index of the selected item in the dropdown.
        """
        self.search_column_index = self.search_column_filter.currentData()
        # Trigger search with current search text
        self._perform_search()

    def _on_search_text_changed(self, text: str) -> None:
        """
        Handle search text changes with debouncing.

        Uses a timer to delay search execution while user is typing to avoid
        performance issues with large datasets.

        Args:
            text: The search text from the search input field.
        """
        # Restart timer - if user types again within 300ms, this will be cancelled
        self.search_timer.stop()

        # If search is empty, clear filter immediately without delay
        if not text.strip():
            self._perform_search()
        else:
            # Start timer for delayed search (300ms)
            self.search_timer.start(300)

    def _perform_search(self) -> None:
        """
        Perform search filtering by reading directly from the model.

        Filters the table to show only rows where searchable columns
        (Name, Author, Package ID, Published File ID) contain the search text
        (case-insensitive).
        """
        search_text = self.search_input.text()
        self.apply_search_filter(search_text)

    def apply_search_filter(self, pattern: str) -> None:
        """
        Apply search filter to the ACF table.

        Filters rows to show only those where the selected column(s) contain the pattern
        (case-insensitive). If search_column_index is -1, searches all searchable columns.
        Otherwise, searches only the selected column.

        Args:
            pattern: The search pattern (empty string shows all rows)
        """
        pattern_lower = pattern.lower()

        # Determine which columns to search
        if self.search_column_index == -1:
            # Search all searchable columns
            columns_to_search = self.SEARCHABLE_COLUMNS
        else:
            # Search only the selected column
            columns_to_search = [self.search_column_index]

        # Disable updates during batch row hide/show operations
        self.editor_table_view.setUpdatesEnabled(False)
        try:
            row_count = self.editor_model.rowCount()
            for row_idx in range(row_count):
                if not pattern_lower:
                    # Empty search shows all rows
                    self.editor_table_view.setRowHidden(row_idx, False)
                else:
                    # Check if search text appears in selected column(s)
                    row_matches = False
                    for col_idx in columns_to_search:
                        index = self.editor_model.index(row_idx, col_idx)
                        cell_text = str(self.editor_model.data(index) or "")
                        if pattern_lower in cell_text.lower():
                            row_matches = True
                            break
                    self.editor_table_view.setRowHidden(row_idx, not row_matches)
        finally:
            self.editor_table_view.setUpdatesEnabled(True)


class ActiveModDelegate(QStyledItemDelegate):
    """
    Custom cell delegate for highlighting active mods in the ACF table.

    Renders cells with bold white text on dark green background (#006400) for any mod
    whose Published File ID (PFID) is present in the parent AcfLogReader's active_pfids set.
    Active mods are those currently in the game's load order.

    For non-active mods, delegates to default painting.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the delegate.

        Args:
            parent: Parent AcfLogReader widget for accessing active_pfids set.
        """
        super().__init__(parent)
        self.acf_log_reader: Optional[AcfLogReader] = cast("AcfLogReader", parent)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """
        Paint cell with custom styling for active mods.

        Checks if the mod's PFID is in the active_pfids set. If so, renders with
        bold white text (#FFFFFF) on dark green background (#006400).
        Otherwise, delegates to the default QStyledItemDelegate painting.
        """
        acf_log_reader = self.acf_log_reader
        if acf_log_reader is None:
            super().paint(painter, option, index)
            return

        # Get PFID from model to check if mod is active
        pfid_index = index.sibling(index.row(), ColumnIndex.PUBLISHED_FILE_ID.value)
        pfid = acf_log_reader.editor_model.data(pfid_index, Qt.ItemDataRole.DisplayRole)

        # Highlight if this mod's PFID is in the active set
        if pfid and pfid in acf_log_reader.active_pfids:
            painter.save()
            rect = option.rect  # type: ignore[attr-defined]
            font = option.font  # type: ignore[attr-defined]

            # Dark green background for active mods
            painter.fillRect(rect, QColor(0, 100, 0))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))

            # Get cell text
            cell_data = acf_log_reader.editor_model.data(index)
            painter.drawText(
                rect.adjusted(5, 0, 0, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                str(cell_data),
            )
            painter.restore()
        else:
            super().paint(painter, option, index)


__all__ = ["AcfLogReader", "ActiveModDelegate"]
