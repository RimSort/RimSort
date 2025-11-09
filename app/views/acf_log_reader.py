from __future__ import annotations

import csv
import os
import re
import shutil
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from functools import partial
from pathlib import Path
from threading import Semaphore
from typing import Any, Optional, cast

from loguru import logger
from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    QRunnable,
    QSortFilterProxyModel,
    Qt,
    QThread,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QFont,
    QKeySequence,
    QPainter,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QPushButton,
    QStatusBar,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.controllers.settings_controller import SettingsController
from app.utils.event_bus import EventBus
from app.utils.generic import (
    format_time_display,
    get_relative_time,
    platform_specific_open,
)
from app.utils.metadata import MetadataManager
from app.utils.mod_utils import (
    get_mod_name_from_pfid,
    get_mod_path_from_pfid,
)
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.utils.steam.steamfiles.wrapper import acf_to_dict
from app.views.dialogue import (
    show_dialogue_conditional,
    show_dialogue_file,
    show_fatal_error,
    show_information,
    show_warning,
)

UNKNOWN_STRING = "Unknown"


class ErrorMessages(str, Enum):
    """Common error messages."""

    INVALID_PFID = "Invalid PFID encountered: {pfid}"
    INVALID_MOD_SOURCE = "Invalid mod_source encountered"
    ACF_NOT_FOUND = "ACF file not found"
    EXPORT_PERMISSION_DENIED = (
        "Export failed: Permission denied - check file permissions"
    )
    EXPORT_FILESYSTEM_ERROR = "Export failed: File system error: {e}"
    EXPORT_UNKNOWN_ERROR = "Export failed due to an unknown error"
    STEAMCMD_INTERFACE_NOT_INITIALIZED = (
        "Export failed: SteamCMD interface not properly initialized"
    )
    ACF_FILE_NOT_FOUND = "ACF file not found: {acf_path}"
    ACF_FILE_NOT_FOUND_ERROR = "Export failed: ACF file not found: {acf_path}"
    ACF_FILE_NOT_FOUND_AT = "ACF file not found at: {acf_path}"
    INVALID_EXPORT_FILE_PATH = "Invalid file path provided for export: {file_path}"
    EXPORT_FAILED_UNKNOWN_EXCEPTION = "Export failed unknown exception occurred"
    LOAD_ACF_DATA_ERROR = "Error starting ACF data loading: {error}"
    FAILED_TO_LOAD_ACF_DATA = "Failed to load any ACF data from SteamCMD or Steam paths"
    INVALID_WORKSHOP_ITEMS_DATA_FORMAT = "Invalid workshop items data format"
    ERROR_GETTING_MOD_NAME = "Error getting mod name for PFID {pfid}: {error}"
    ERROR_GETTING_MOD_PATH = "Error getting mod path for PFID {pfid}: {error}"
    ERROR_FORMATTING_TIMESTAMP = "Error formatting timestamp for PFID {pfid}: {error}"


@dataclass
class AcfEntry:
    """Data class for ACF entry information."""

    published_file_id: str
    mod_source: str
    timeupdated: Optional[int] = None


class AcfLoadWorker(QThread):
    """
    Background worker thread for loading and processing ACF data from SteamCMD and Steam paths.

    This worker loads ACF files, merges workshop item data, and creates AcfEntry objects
    for display in the table model. It emits signals for completion or errors.
    """

    finished = Signal(list, dict, dict)  # entries, steamcmd_acf_data, steam_acf_data
    error = Signal(str)

    def __init__(
        self, steamcmd_acf_path: Optional[Path], steam_acf_path: Optional[Path]
    ) -> None:
        """
        Initialize the ACF load worker.

        Args:
            steamcmd_acf_path: Path to the SteamCMD ACF file, or None if not available.
            steam_acf_path: Path to the Steam ACF file, or None if not available.
        """
        super().__init__()
        self.steamcmd_acf_path = steamcmd_acf_path
        self.steam_acf_path = steam_acf_path

    def _load_steamcmd_acf(self) -> dict[str, Any]:
        """Load ACF data from SteamCMD path."""
        steamcmd_acf_data = {}
        if self.steamcmd_acf_path and self.steamcmd_acf_path.exists():
            try:
                steamcmd_acf_data = acf_to_dict(str(self.steamcmd_acf_path))
                logger.info(
                    f"Loaded ACF data from SteamCMD at {self.steamcmd_acf_path}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to parse ACF file at {self.steamcmd_acf_path}: {str(e)}"
                )
        return steamcmd_acf_data

    def _load_steam_acf(self) -> dict[str, Any]:
        """Load ACF data from Steam path."""
        steam_acf_data = {}
        if self.steam_acf_path and self.steam_acf_path.exists():
            try:
                steam_acf_data = acf_to_dict(str(self.steam_acf_path))
                logger.info(f"Loaded ACF data from Steam at {self.steam_acf_path}")
            except Exception as e:
                logger.error(
                    f"Failed to parse ACF file at {self.steam_acf_path}: {str(e)}"
                )
        return steam_acf_data

    def _merge_acf_data(
        self, steamcmd_acf_data: dict[str, Any], steam_acf_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge ACF data from SteamCMD and Steam sources."""
        combined_acf_data: dict[str, Any] = {}
        for source_data in (steamcmd_acf_data, steam_acf_data):
            for key, value in source_data.items():
                if key == "AppWorkshop" and key in combined_acf_data:
                    # Merge WorkshopItemsInstalled dictionaries
                    existing_items = combined_acf_data[key].get(
                        "WorkshopItemsInstalled", {}
                    )
                    new_items = value.get("WorkshopItemsInstalled", {})
                    merged_items = {**existing_items, **new_items}
                    combined_acf_data[key]["WorkshopItemsInstalled"] = merged_items
                else:
                    combined_acf_data[key] = value
        return combined_acf_data

    def _create_entries(
        self,
        combined_acf_data: dict[str, Any],
        steamcmd_pfids: set[str],
        steam_pfids: set[str],
    ) -> list[AcfEntry]:
        """Create AcfEntry objects from combined ACF data."""
        workshop_items = combined_acf_data.get("AppWorkshop", {}).get(
            "WorkshopItemsInstalled", {}
        )
        if not isinstance(workshop_items, dict):
            raise ValueError("Invalid workshop items data format")

        entries: list[AcfEntry] = []

        for pfid, item in workshop_items.items():
            if not isinstance(item, dict):
                continue

            pfid_str = str(pfid)
            if pfid_str in steamcmd_pfids:
                mod_source = "SteamCMD"
            elif pfid_str in steam_pfids:
                mod_source = "Steam"
            else:
                mod_source = "Local"
            timeupdated_raw = item.get("timeupdated")
            timeupdated_int = None
            if timeupdated_raw is not None:
                try:
                    timeupdated_int = int(timeupdated_raw)
                except (ValueError, TypeError):
                    logger.warning(
                        f"Invalid timeupdated for PFID {pfid_str}: {timeupdated_raw}"
                    )
            entries.append(
                AcfEntry(
                    published_file_id=pfid_str,
                    mod_source=mod_source,
                    timeupdated=timeupdated_int,
                )
            )

        return entries

    def run(self) -> None:
        try:
            # Load ACF data using helper methods
            steamcmd_acf_data = self._load_steamcmd_acf()
            steam_acf_data = self._load_steam_acf()

            # Merge ACF data
            combined_acf_data = self._merge_acf_data(steamcmd_acf_data, steam_acf_data)

            if not combined_acf_data:
                self.error.emit(
                    "Failed to load any ACF data from SteamCMD or Steam paths"
                )
                return

            workshop_items = combined_acf_data.get("AppWorkshop", {}).get(
                "WorkshopItemsInstalled", {}
            )
            if not isinstance(workshop_items, dict):
                self.error.emit("Invalid workshop items data format")
                return

            # Determine source for each PFID
            steamcmd_pfids = set()
            if steamcmd_acf_data:
                steamcmd_items = steamcmd_acf_data.get("AppWorkshop", {}).get(
                    "WorkshopItemsInstalled", {}
                )
                steamcmd_pfids = set(str(pfid) for pfid in steamcmd_items.keys())

            steam_pfids = set()
            if steam_acf_data:
                steam_items = steam_acf_data.get("AppWorkshop", {}).get(
                    "WorkshopItemsInstalled", {}
                )
                steam_pfids = set(str(pfid) for pfid in steam_items.keys())

            entries = self._create_entries(
                combined_acf_data, steamcmd_pfids, steam_pfids
            )

            self.finished.emit(entries, steamcmd_acf_data, steam_acf_data)

        except (FileNotFoundError, PermissionError, ValueError, TypeError) as e:
            logger.error(f"Error in AcfLoadWorker: {str(e)}")
            self.error.emit(str(e))
        except Exception as e:
            logger.error(f"Unexpected error in AcfLoadWorker: {str(e)}")
            self.error.emit(f"Unexpected error: {str(e)}")


class TableResizer:
    """Handles table width management for proportional resizing and full-width fit."""

    def __init__(self, table_view: QTableView, min_column_width: int):
        self.table_view = table_view
        self.min_column_width = min_column_width
        self._table_col_weights: list[float] = []
        self._suppress_section_resize_updates = False
        # Connect signal
        header = self.table_view.horizontalHeader()
        if isinstance(header, QHeaderView):
            header.sectionResized.connect(self._on_table_section_resized)

    def _viewport_width(self) -> int:
        try:
            return max(0, int(self.table_view.viewport().width()))
        except Exception:
            return max(0, int(self.table_view.width()))

    def _init_or_sync_column_weights(self: "TableResizer") -> None:
        """Ensure column weights exist and match current column count."""
        model = self.table_view.model()
        if not model:
            return
        col_count = model.columnCount()
        if col_count <= 0:
            return
        if (
            not getattr(self, "_table_col_weights", None)
            or len(self._table_col_weights) != col_count
        ):
            # Initialize equal weights
            self._table_col_weights = [1.0 / col_count for _ in range(col_count)]

    def _recalculate_weights_from_current_widths(self: "TableResizer") -> None:
        model = self.table_view.model()
        if not model:
            return
        col_count = model.columnCount()
        if col_count <= 0:
            return
        header = self.table_view.horizontalHeader()
        sizes = [header.sectionSize(i) for i in range(col_count)]
        total = sum(sizes) or 1
        self._table_col_weights = [s / total for s in sizes]

    def _apply_table_widths_to_viewport(self: "TableResizer") -> None:
        model = self.table_view.model()
        if not model:
            return
        col_count = model.columnCount()
        if col_count <= 0:
            return
        self._init_or_sync_column_weights()
        vpw = self._viewport_width()
        if vpw <= 0:
            return
        header = self.table_view.horizontalHeader()
        # Compute widths from weights, clamp min, fix rounding on the last
        min_w = max(self.min_column_width, int(vpw * 0.05 / col_count))
        widths = [max(min_w, int(round(w * vpw))) for w in self._table_col_weights]
        # Adjust last section to fill exact viewport width
        diff = vpw - sum(widths)
        widths[-1] = max(min_w, widths[-1] + diff)
        # Apply sizes
        self._suppress_section_resize_updates = True
        try:
            for i, w in enumerate(widths):
                header.resizeSection(i, w)
        finally:
            self._suppress_section_resize_updates = False

    def _on_table_section_resized(
        self: "TableResizer", index: int, old: int, new: int
    ) -> None:
        if self._suppress_section_resize_updates:
            return
        # Update weights and normalize to viewport width immediately
        self._recalculate_weights_from_current_widths()
        self._apply_table_widths_to_viewport()

    def handle_resize_event(self: "TableResizer", event: QResizeEvent) -> None:
        """Handle resize event by applying widths."""
        self._apply_table_widths_to_viewport()

    def handle_show_event(self: "TableResizer", event: QShowEvent) -> None:
        """Handle show event by deferring width application."""
        QTimer.singleShot(0, self._apply_table_widths_to_viewport)


class MetadataLoadTask(QRunnable):
    def __init__(
        self,
        pfids: list[str],
        data_type: str,
        model: "AcfTableModel",
        priority: int = 0,
    ) -> None:
        super().__init__()
        self.pfids = pfids
        self.data_type = data_type
        self.model = model
        self.priority = priority

    def run(self) -> None:
        for pfid in self.pfids:
            try:
                if self.data_type == "name":
                    name = get_mod_name_from_pfid(pfid)
                    self.model._mod_name_cache[pfid] = name
                    self.model._limit_cache_size(self.model._mod_name_cache)
                    logger.info(f"Loaded mod name for PFID {pfid}: {name}")
                elif self.data_type == "path":
                    path = get_mod_path_from_pfid(pfid)
                    self.model._mod_path_cache[pfid] = path
                    self.model._limit_cache_size(self.model._mod_path_cache)
                    logger.info(f"Loaded mod path for PFID {pfid}: {path}")
                # Collect updates for batch emission
                self.model._pending_updates.add(pfid)
                # Schedule batch emission
                self.model.start_update_timer.emit()
            except Exception as e:
                logger.error(
                    f"Error loading {self.data_type} for PFID {pfid}: {str(e)}"
                )


class AcfTableModel(QAbstractTableModel):
    """Custom table model for ACF data with virtual scrolling support."""

    # Signal to start timer from main thread
    start_update_timer = Signal()

    PAGE_SIZE = 1000  # Number of rows to load per page for virtual scrolling

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._parent = parent
        self.entries: list[AcfEntry] = []
        self._all_entries: list[AcfEntry] = []  # Full list of all entries
        self._loaded_count = 0  # Number of entries currently loaded
        self._mod_name_cache: OrderedDict[str, str] = OrderedDict()
        self._mod_path_cache: OrderedDict[str, str] = OrderedDict()
        self._metadata_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.max_cache_size = 5000
        self._thread_pool = QThreadPool.globalInstance()
        self._thread_pool.setMaxThreadCount(
            min(8, os.cpu_count() or 4)
        )  # Dynamic thread count
        self._semaphore = Semaphore(10)  # Limit concurrent metadata fetches
        self._pending_updates: set[str] = set()
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._emit_pending_updates)
        self.start_update_timer.connect(self._start_timer_slot)
        self._pending_name_pfids: set[str] = set()
        self._pending_path_pfids: set[str] = set()
        self._batch_timer = QTimer(self)
        self._batch_timer.setSingleShot(True)
        self._batch_timer.timeout.connect(self._process_batch_metadata)

    def _start_timer_slot(self) -> None:
        """Slot to start the update timer from the main thread."""
        if not self._update_timer.isActive():
            self._update_timer.start(100)

    def _limit_cache_size(self, cache: OrderedDict[str, Any]) -> None:
        while len(cache) > self.max_cache_size:
            cache.popitem(last=False)

    def _emit_pending_updates(self) -> None:
        """Emit dataChanged for pending updates, batched for efficiency."""
        if not self._pending_updates:
            return
        # Collect all pending updates and clear immediately to avoid concurrent modification
        pending = self._pending_updates.copy()
        self._pending_updates.clear()
        # Collect all affected rows
        affected_rows = set()
        for pfid in pending:
            for row in range(len(self.entries)):
                if str(self.entries[row].published_file_id) == pfid:
                    affected_rows.add(row)
                    break
        if affected_rows:
            min_row = min(affected_rows)
            max_row = max(affected_rows)
            # Emit single dataChanged for the range, affecting columns 0 and 5
            self.dataChanged.emit(self.index(min_row, 0), self.index(max_row, 5))

    def canFetchMore(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> bool:
        return self._loaded_count < len(self._all_entries)

    def fetchMore(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> None:
        if not self.canFetchMore(parent):
            return

        # Calculate how many more to load
        remaining = len(self._all_entries) - self._loaded_count
        fetch_count = min(self.PAGE_SIZE, remaining)

        # Get the next batch of entries
        start_index = self._loaded_count
        end_index = start_index + fetch_count
        new_entries = self._all_entries[start_index:end_index]

        # Insert the new entries into the current entries list
        self.beginInsertRows(
            QModelIndex(), self._loaded_count, self._loaded_count + fetch_count - 1
        )
        self.entries.extend(new_entries)
        self._loaded_count += fetch_count
        self.endInsertRows()

        logger.info(
            f"Fetched {fetch_count} more entries, total loaded: {self._loaded_count}"
        )

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> int:
        return len(self.entries)

    def columnCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> int:
        return 6

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            headers = [
                "Mod Name",
                "Published File ID",
                "Mod Source",
                "Mod downloaded",
                "Updated on Workshop",
                "Mod Path",
            ]
            return headers[section] if section < len(headers) else ""
        return super().headerData(section, orientation, role)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self.entries)):
            return None

        entry = self.entries[index.row()]
        pfid = str(entry.published_file_id)

        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:  # Mod Name
                return self._get_mod_name(pfid)
            elif index.column() == 1:  # PFID
                return pfid
            elif index.column() == 2:  # Mod Source
                return entry.mod_source
            elif index.column() == 3:  # Mod Downloaded
                return self._get_mod_downloaded_time(entry, pfid)
            elif index.column() == 4:  # Updated on Workshop
                return self._get_updated_time(entry.timeupdated, pfid)
            elif index.column() == 5:  # Mod Path
                return self._get_mod_path(pfid)

        return None

    def _get_mod_name(self, pfid: str) -> str:
        """Get mod name with lazy loading."""
        if pfid in self._mod_name_cache:
            self._mod_name_cache.move_to_end(pfid)  # LRU: move to end on access
            self._limit_cache_size(self._mod_name_cache)
            return self._mod_name_cache[pfid]
        # Trigger background loading if not cached
        self._load_metadata_async(pfid, "name")
        return UNKNOWN_STRING

    def _get_mod_path(self, pfid: str) -> str:
        """Get mod path with lazy loading."""
        if pfid in self._mod_path_cache:
            self._mod_path_cache.move_to_end(pfid)
            self._limit_cache_size(self._mod_path_cache)
            return self._mod_path_cache[pfid]
        # Trigger background loading if not cached
        self._load_metadata_async(pfid, "path")
        return UNKNOWN_STRING

    def _get_mod_downloaded_time(self, entry: AcfEntry, pfid: str) -> str:
        """Get mod downloaded time."""
        if pfid in self._metadata_cache:
            metadata = self._metadata_cache[pfid]
            internal_time_touched = metadata.get("internal_time_touched")
            if internal_time_touched:
                time_str, _ = format_time_display(internal_time_touched)
                return time_str
        # Fallback to ACF timeupdated
        time_str, _ = format_time_display(entry.timeupdated)
        return time_str

    def _get_updated_time(self, timeupdated: Optional[int], pfid: str) -> str:
        """Format updated on workshop time."""
        if not timeupdated:
            return ""
        try:
            timestamp_int = int(timeupdated)
            dt = datetime.fromtimestamp(timestamp_int)
            abs_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            rel_time = get_relative_time(timestamp_int)
            return f"{abs_time} | {rel_time}"
        except Exception as e:
            logger.error(f"Error formatting timestamp for PFID {pfid}: {str(e)}")
            return UNKNOWN_STRING

    def _load_metadata_async(self, pfid: str, data_type: str) -> None:
        """Load metadata asynchronously using thread pool."""
        if not pfid.isdigit():
            return

        if data_type == "name":
            self._pending_name_pfids.add(pfid)
        elif data_type == "path":
            self._pending_path_pfids.add(pfid)

        if not self._batch_timer.isActive():
            self._batch_timer.start(100)

    def _process_batch_metadata(self) -> None:
        batch_size = 20
        name_batch = list(self._pending_name_pfids)[:batch_size]
        path_batch = list(self._pending_path_pfids)[:batch_size]
        self._pending_name_pfids -= set(name_batch)
        self._pending_path_pfids -= set(path_batch)
        if name_batch:
            task = MetadataLoadTask(name_batch, "name", self)
            self._thread_pool.start(task)
        if path_batch:
            task = MetadataLoadTask(path_batch, "path", self)
            self._thread_pool.start(task)
        if self._pending_name_pfids or self._pending_path_pfids:
            self._batch_timer.start(100)

    def set_entries(self, entries: list[AcfEntry]) -> None:
        """Set new entries and reset caches."""
        self.beginResetModel()
        self._all_entries = entries  # Full list of all entries
        self.entries = []  # Currently loaded entries
        self._loaded_count = 0  # Number of entries currently loaded
        self._mod_name_cache.clear()
        self._mod_path_cache.clear()
        self._metadata_cache.clear()
        self._pending_updates.clear()
        if self._update_timer.isActive():
            self._update_timer.stop()
        self.endResetModel()
        # Preload metadata for all entries in background, prioritizing the first page for immediate display
        first_page_entries = self._all_entries[: self.PAGE_SIZE]
        remaining_entries = self._all_entries[self.PAGE_SIZE :]
        self._pending_name_pfids.update(
            str(entry.published_file_id) for entry in first_page_entries
        )
        self._pending_path_pfids.update(
            str(entry.published_file_id) for entry in first_page_entries
        )
        self._pending_name_pfids.update(
            str(entry.published_file_id) for entry in remaining_entries
        )
        self._pending_path_pfids.update(
            str(entry.published_file_id) for entry in remaining_entries
        )
        if not self._batch_timer.isActive():
            self._batch_timer.start(100)

    def update_metadata_cache(
        self,
        mod_name_cache: dict[str, str],
        mod_path_cache: dict[str, str],
        pfid_to_metadata: dict[str, dict[str, Any]],
    ) -> None:
        """Update metadata caches and emit dataChanged for affected rows."""
        self._mod_name_cache.update(mod_name_cache)
        self._mod_path_cache.update(mod_path_cache)
        self._metadata_cache.update(pfid_to_metadata)
        self._limit_cache_size(self._mod_name_cache)
        self._limit_cache_size(self._mod_path_cache)
        self._limit_cache_size(self._metadata_cache)

        # Emit dataChanged for all rows since metadata may affect multiple columns
        if self.entries:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self.entries) - 1, self.columnCount() - 1),
            )


class AcfSortFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.search_text = ""
        self.use_regex = False
        self.pattern: Optional[re.Pattern[str]] = None
        self._pattern_cache: dict[str, Optional[re.Pattern[str]]] = {}

    def setFilterText(self, text: str) -> None:
        self.search_text = text
        self.filter_disabled = False
        if text in self._pattern_cache:
            self.pattern = self._pattern_cache[text]
            self.use_regex = self.pattern is not None
        else:
            if not text:
                self.pattern = None
                self.use_regex = False
            else:
                try:
                    self.pattern = re.compile(text, re.IGNORECASE)
                    self.use_regex = True
                except re.error:
                    self.pattern = None
                    self.use_regex = False
                    self.filter_disabled = True
            self._pattern_cache[text] = self.pattern
        self.invalidate()

    def filterAcceptsRow(
        self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex
    ) -> bool:
        if not self.search_text or self.filter_disabled:
            return True
        model = self.sourceModel()
        # Search visible columns that are likely to contain searchable text
        search_columns = {
            AcfLogReader.COL_PFID,
            AcfLogReader.COL_MOD_NAME,
            AcfLogReader.COL_MOD_PATH,
            AcfLogReader.COL_MOD_SOURCE,
        }
        for col in search_columns:
            index = model.index(source_row, col, source_parent)
            item_text = model.data(index, Qt.ItemDataRole.DisplayRole) or ""
            if self.use_regex and self.pattern:
                try:
                    if self.pattern.search(item_text):
                        return True
                except re.error:
                    if self.search_text.lower() in item_text.lower():
                        return True
            else:
                if self.search_text.lower() in item_text.lower():
                    return True
        return False


class AcfLogReader(QWidget):
    from enum import IntEnum

    class TableColumn(IntEnum):
        """Enumeration of table columns with descriptions."""

        MOD_NAME = 0
        PFID = 1
        MOD_SOURCE = 2
        MOD_DOWNLOADED = 3
        UPDATED_ON_WORKSHOP = 4
        MOD_PATH = 5

        @property
        def description(self) -> str:
            """Get human-readable description of the column."""
            return {
                self.PFID: "Steam Workshop Published File ID",
                self.MOD_DOWNLOADED: "Mod downloaded",
                self.UPDATED_ON_WORKSHOP: "Last update timestamp (UTC) / Relative Time",
                self.MOD_SOURCE: "Mod source (SteamCMD/Steam/Local)",
                self.MOD_NAME: "Mod name from Steam metadata",
                self.MOD_PATH: "Filesystem path to mod",
            }[self]

    class ModSource(str, Enum):
        """Enumeration for mod sources."""

        STEAMCMD = "SteamCMD"
        STEAM = "Steam"
        LOCAL = "Local"

    # Maintain backward compatibility with old constant names
    COL_PFID = TableColumn.PFID
    COL_MOD_DOWNLOADED = TableColumn.MOD_DOWNLOADED
    COL_UPDATED_ON_WORKSHOP = TableColumn.UPDATED_ON_WORKSHOP
    COL_MOD_SOURCE = TableColumn.MOD_SOURCE
    COL_MOD_NAME = TableColumn.MOD_NAME
    COL_MOD_PATH = TableColumn.MOD_PATH

    # Constants for performance and configuration
    REFRESH_INTERVAL_MS = 30000  # 30 seconds
    DEBOUNCE_DELAY_MS = 300  # Debounce delay for search
    MIN_COLUMN_WIDTH = 40  # Minimum column width
    CACHE_MAX_SIZE = 5000  # Maximum cache size for LRU (increased for large datasets)
    METADATA_BATCH_SIZE = 20  # Batch size for metadata updates (reduced for batching)
    EXPORT_BATCH_SIZE = 1000  # Batch size for CSV export
    PAGE_SIZE = 1000  # Number of rows to load per page for virtual scrolling

    def __init__(
        self,
        settings_controller: SettingsController,
        active_mods_list: Optional[object] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Log Reader")
        self.settings_controller = settings_controller
        self.active_mods_list = active_mods_list
        self.steamcmd_interface = SteamcmdInterface.instance()
        self.metadata_manager = MetadataManager.instance()

        # Background workers
        self.acf_load_worker: Optional[AcfLoadWorker] = None

        self.entries: list[AcfEntry] = []

        # Main layout
        main_layout = QVBoxLayout()

        # Status bar
        self.status_bar = QStatusBar()
        # Improve readability: make status text white
        self.status_bar.setStyleSheet("QStatusBar, QStatusBar QLabel { color: white; }")
        self.status_bar.showMessage(self.tr("Ready"))

        # Top controls layout
        controls_layout = QHBoxLayout()

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(self.tr("Search..."))
        self.search_box.textChanged.connect(self._debounced_filter_table)
        controls_layout.addWidget(self.search_box)

        # Refresh button
        self.refresh_btn = QPushButton(self.tr("Refresh"))
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        controls_layout.addWidget(self.refresh_btn)

        # Import ACF Data button
        self.import_acf_btn = QPushButton(self.tr("Import ACF Data"))
        self.import_acf_btn.clicked.connect(self._on_import_acf_clicked)
        controls_layout.addWidget(self.import_acf_btn)

        # Export ACF Data button
        self.export_acf_btn = QPushButton(self.tr("Export ACF Data"))
        self.export_acf_btn.clicked.connect(self._on_export_acf_clicked)
        controls_layout.addWidget(self.export_acf_btn)

        # Export button
        self.export_btn = QPushButton(self.tr("Export to CSV"))
        self.export_btn.clicked.connect(self._on_export_to_csv_clicked)
        controls_layout.addWidget(self.export_btn)

        main_layout.addLayout(controls_layout)

        # Table view with model
        self.table_view = QTableView()
        # Ensure columns fit window width but allow manual resizing
        self.table_view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        header = self.table_view.horizontalHeader()
        if isinstance(header, QHeaderView):
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setMinimumSectionSize(self.MIN_COLUMN_WIDTH)

        main_layout.addWidget(self.table_view)

        # Initialize table model and proxy model for filtering
        self.table_model = AcfTableModel()
        self.proxy_model = AcfSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.table_model)
        self.table_view.setModel(self.proxy_model)
        self.table_view.setItemDelegate(ActiveModDelegate(self))

        # Enable column sorting
        self.table_view.setSortingEnabled(True)
        # Sort by MOD_DOWNLOADED column descending (most recent first)
        self.table_view.sortByColumn(
            self.COL_MOD_DOWNLOADED, Qt.SortOrder.DescendingOrder
        )

        # Initialize helper classes after table_view is created
        self.table_resizer = TableResizer(self.table_view, self.MIN_COLUMN_WIDTH)

        main_layout.addWidget(self.status_bar)
        self.setLayout(main_layout)

        # Set up custom context menu for table view
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_context_menu)

        # Set up keyboard shortcuts

        # Add keyboard shortcuts for buttons using QAction
        self.refresh_action = QAction("Refresh", self)
        self.refresh_action.setShortcut(QKeySequence("F5"))
        self.refresh_action.triggered.connect(self._on_refresh_clicked)
        self.addAction(self.refresh_action)

        self.import_acf_action = QAction("Import ACF Data", self)
        self.import_acf_action.setShortcut(QKeySequence("Ctrl+I"))
        self.import_acf_action.triggered.connect(self._on_import_acf_clicked)
        self.addAction(self.import_acf_action)

        self.export_acf_action = QAction("Export ACF Data", self)
        self.export_acf_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        self.export_acf_action.triggered.connect(self._on_export_acf_clicked)
        self.addAction(self.export_acf_action)

        self.export_csv_action = QAction("Export to CSV", self)
        self.export_csv_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_csv_action.triggered.connect(self._on_export_to_csv_clicked)
        self.addAction(self.export_csv_action)

        self.search_action = QAction("Search", self)
        self.search_action.setShortcut(QKeySequence("Ctrl+F"))
        self.search_action.triggered.connect(self.search_box.setFocus)
        self.addAction(self.search_action)

        # Initialize last modification times for ACF files
        self._last_steamcmd_acf_mtime: Optional[float] = None
        self._last_steam_acf_mtime: Optional[float] = None

        # Connect to MetadataManager signals for cache invalidation
        self.metadata_manager.mod_created_signal.connect(self._on_mod_change)
        self.metadata_manager.mod_deleted_signal.connect(self._on_mod_change)
        self.metadata_manager.mod_metadata_updated_signal.connect(self._on_mod_change)

        # Wait for refresh signal before starting refresh loop
        EventBus().refresh_finished.connect(self.load_acf_data)
        logger.info("Waiting for initial refresh to complete.")

        # Flag to track if application is quitting
        self._app_quitting = False
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self._on_app_quitting)

        # Ensure the dialog remains visible
        self.visibility_timer = QTimer(self)
        self.visibility_timer.timeout.connect(self._check_visibility)
        self.visibility_timer.start(1000)  # Check every 1 second

        # Start refresh timer once initial refresh completes
        self._start_refresh_timer()

    def _on_app_quitting(self) -> None:
        """Handle application quitting."""
        self._app_quitting = True
        self.visibility_timer.stop()

    def _check_visibility(self) -> None:
        """Ensure the dialog remains visible at all times."""
        if not self._app_quitting and not self.isVisible():
            self.show()

    def _on_mod_change(self) -> None:
        """Handle mod creation, deletion, or metadata update by clearing caches."""
        logger.debug("Clearing caches due to mod change event")
        self.table_model._mod_name_cache.clear()
        self.table_model._mod_path_cache.clear()
        self.table_model._metadata_cache.clear()

    def _start_refresh_timer(self) -> None:
        """Start a timer to periodically refresh the view."""
        self.refresh_timer = QTimer(self)  # Setup auto-refresh timer
        self.refresh_timer.setInterval(self.REFRESH_INTERVAL_MS)  # 30 seconds
        self.refresh_timer.timeout.connect(self.load_acf_data)

    def _apply_filter(self) -> None:
        """Apply filter to the proxy model."""
        self.proxy_model.setFilterText(self.search_box.text())
        # Update status bar with search result count
        total_rows = self.table_model.rowCount()
        filtered_rows = self.proxy_model.rowCount()
        if self.search_box.text():
            self.status_bar.showMessage(
                self.tr("Showing {filtered} of {total} items (filtered)").format(
                    filtered=filtered_rows, total=total_rows
                )
            )
        else:
            self.status_bar.showMessage(
                self.tr("Showing {total} items").format(total=total_rows)
            )

    def _show_searching_status(self) -> None:
        """Show 'Searching...' status during debounce."""
        self.status_bar.showMessage(self.tr("Searching..."))

    def _debounced_filter_table(self) -> None:
        """Debounce filter application to improve performance on rapid input."""
        if hasattr(self, "_filter_timer") and self._filter_timer.isActive():
            self._filter_timer.stop()
        else:
            self._filter_timer: QTimer = QTimer(self)
            self._filter_timer.setSingleShot(True)
            self._filter_timer.timeout.connect(self._apply_filter)
        self._filter_timer.start(self.DEBOUNCE_DELAY_MS)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable buttons during long operations."""
        self.refresh_btn.setEnabled(enabled)
        self.import_acf_btn.setEnabled(enabled)
        self.export_acf_btn.setEnabled(enabled)
        self.export_btn.setEnabled(enabled)

    def _on_refresh_clicked(self) -> None:
        self._set_buttons_enabled(False)
        try:
            # Force refresh: clear all caches and reset modification times to force ACF reload
            self.table_model._mod_name_cache.clear()
            self.table_model._mod_path_cache.clear()
            self.table_model._metadata_cache.clear()
            self._last_steamcmd_acf_mtime = None
            self._last_steam_acf_mtime = None
            self.load_acf_data()
        finally:
            self._set_buttons_enabled(True)

    def _on_import_acf_clicked(self) -> None:
        self._set_buttons_enabled(False)
        try:
            self.import_acf_data()
        finally:
            self._set_buttons_enabled(True)

    def _on_export_acf_clicked(self) -> None:
        self._set_buttons_enabled(False)
        try:
            self.export_acf_data()
        finally:
            self._set_buttons_enabled(True)

    def _on_export_to_csv_clicked(self) -> None:
        self._set_buttons_enabled(False)
        try:
            self.export_to_csv()
        finally:
            self._set_buttons_enabled(True)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.table_resizer.handle_resize_event(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.table_resizer.handle_show_event(event)

    def _start_acf_load_worker(
        self, steamcmd_acf_path: Optional[Path], steam_acf_path: Optional[Path]
    ) -> None:
        """Start background worker to load ACF data."""
        if self.acf_load_worker is not None and self.acf_load_worker.isRunning():
            return
        self.acf_load_worker = AcfLoadWorker(steamcmd_acf_path, steam_acf_path)
        self.acf_load_worker.finished.connect(self._on_acf_load_worker_finished)
        self.acf_load_worker.error.connect(self._on_acf_load_worker_error)
        self.acf_load_worker.start()

    def _on_acf_load_worker_finished(
        self,
        entries: list[AcfEntry],
        steamcmd_acf_data: dict[str, Any],
        steam_acf_data: dict[str, Any],
    ) -> None:
        """Handle completion of ACF load worker."""
        self.entries = entries
        self.populate_table(entries)
        self.status_bar.showMessage(
            self.tr("Loaded {count} items | Last updated: {time}").format(
                count=len(entries),
                time=datetime.now().strftime("%H:%M:%S"),
            )
        )
        if not self.refresh_timer.isActive():
            self.refresh_timer.start()
        self._set_buttons_enabled(True)

    def _handle_worker_error(self, error_msg: str, title: str = "Error") -> None:
        """Handle errors from background workers."""
        logger.error(f"{title}: {error_msg}")
        self.status_bar.showMessage(error_msg)
        self._set_buttons_enabled(True)
        self._show_error_dialog(title, error_msg)

    def _show_error_dialog(
        self, title: str, message: str, details: Optional[str] = None
    ) -> None:
        """Show error dialog with optional details."""
        show_warning(
            title=self.tr(title),
            text=message,
            information=details,
        )

    def _on_acf_load_worker_error(self, error_msg: str) -> None:
        """Handle error from ACF load worker."""
        self._handle_worker_error(error_msg, "ACF Load Error")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Prevent the dialog from closing since AcfLogReader should always remain open."""
        event.ignore()

    def _get_acf_info(
        self,
    ) -> tuple[Optional[Path], Path, Optional[float], Optional[float]]:
        """Get paths to ACF files and their modification times."""
        steamcmd = self.steamcmd_interface
        steamcmd_acf_path = None
        if (
            steamcmd
            and hasattr(steamcmd, "steamcmd_appworkshop_acf_path")
            and steamcmd.steamcmd_appworkshop_acf_path
        ):
            steamcmd_acf_path = Path(steamcmd.steamcmd_appworkshop_acf_path)
        current_instance = self.settings_controller.settings.current_instance
        steam_acf_path = (
            Path(
                self.settings_controller.settings.instances[
                    current_instance
                ].workshop_folder
            ).parent.parent
            / "appworkshop_294100.acf"
        )
        steamcmd_acf_mtime = (
            steamcmd_acf_path.stat().st_mtime
            if steamcmd_acf_path and steamcmd_acf_path.exists()
            else None
        )
        steam_acf_mtime = (
            steam_acf_path.stat().st_mtime if steam_acf_path.exists() else None
        )
        return steamcmd_acf_path, steam_acf_path, steamcmd_acf_mtime, steam_acf_mtime

    def _check_skip_reload(
        self, steamcmd_acf_mtime: Optional[float], steam_acf_mtime: Optional[float]
    ) -> bool:
        """Check if reload can be skipped based on modification times."""
        if (
            steamcmd_acf_mtime == self._last_steamcmd_acf_mtime
            and steam_acf_mtime == self._last_steam_acf_mtime
        ):
            count = len(self.entries) if hasattr(self, "entries") else 0
            self.status_bar.showMessage(
                self.tr("Loaded {count} items | Last updated: {time}").format(
                    count=count,
                    time=datetime.now().strftime("%H:%M:%S"),
                )
            )
            self._set_buttons_enabled(True)
            return True
        return False

    def _update_modification_times(
        self, steamcmd_acf_mtime: Optional[float], steam_acf_mtime: Optional[float]
    ) -> None:
        """Update stored modification times."""
        self._last_steamcmd_acf_mtime = steamcmd_acf_mtime
        self._last_steam_acf_mtime = steam_acf_mtime

    def load_acf_data(self) -> None:
        """
        Load workshop item data from SteamCMD and Steam ACF files using background thread.

        Raises:
            RuntimeError: If neither ACF file can be loaded or data format is invalid.
            FileNotFoundError: If the ACF files do not exist.
            Exception: For other errors during loading or parsing.
        """
        logger.info("Starting ACF data loading.")
        self.status_bar.showMessage("Loading ACF data...")
        self._set_buttons_enabled(False)

        try:
            steamcmd_acf_path, steam_acf_path, steamcmd_acf_mtime, steam_acf_mtime = (
                self._get_acf_info()
            )

            if self._check_skip_reload(steamcmd_acf_mtime, steam_acf_mtime):
                return

            self._update_modification_times(steamcmd_acf_mtime, steam_acf_mtime)
            self._start_acf_load_worker(steamcmd_acf_path, steam_acf_path)

        except Exception as e:
            logger.error(f"Error starting ACF data loading: {str(e)}")
            error_msg = f"{str(e)}"
            self.status_bar.showMessage(error_msg)
            self._set_buttons_enabled(True)

    def export_to_csv(self) -> None:
        """
        Export table data to CSV file with enhanced error handling and metadata.

        Errors are shown in the status bar and logged with full stack traces.
        Includes detailed metadata headers in the CSV file.

        Raises:
            ValueError: If file path is invalid.
            PermissionError: If file cannot be written due to permissions.
            OSError: For other file system errors.
            Exception: For unexpected errors during export.
        """
        self._set_buttons_enabled(False)
        try:
            file_path = self._prepare_csv_export()
            if not file_path:
                return

            self._write_csv_data(file_path)
            self._finalize_csv_export(file_path)
        except ValueError as e:
            self._handle_csv_export_error(str(e), "Invalid File Path")
        except PermissionError:
            self._handle_csv_export_error(
                ErrorMessages.EXPORT_PERMISSION_DENIED.value,
                "Export Permission Denied",
            )
        except OSError as e:
            self._handle_csv_export_error(
                ErrorMessages.EXPORT_FILESYSTEM_ERROR.value.format(e=str(e)),
                "Export File System Error",
            )
        except Exception as e:
            self._handle_csv_export_error(
                ErrorMessages.EXPORT_UNKNOWN_ERROR.value,
                "Export Unknown Error",
                str(e),
            )
        finally:
            self._set_buttons_enabled(True)

    def _prepare_csv_export(self) -> Optional[str]:
        """
        Prepare CSV export by selecting file path and validating it.

        Returns:
            The selected file path, or None if canceled or invalid.
        """
        file_path = show_dialogue_file(
            mode="save",
            caption="Export to CSV",
            _dir=f"workshop_items_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            _filter="CSV Files (*.csv)",
        )
        if not file_path:
            self.status_bar.showMessage(self.tr("Export canceled by user."))
            return None

        # Validate user-provided path
        try:
            Path(file_path).resolve(strict=False)  # Check if path is valid
        except (OSError, ValueError) as e:
            raise ValueError(
                ErrorMessages.INVALID_EXPORT_FILE_PATH.value.format(file_path=file_path)
            ) from e

        # Check file can be opened before proceeding
        try:
            with open(file_path, "w", newline="", encoding="utf-8"):
                pass  # Just testing file opening, no need for the file object
        except PermissionError:
            raise
        except OSError:
            raise

        return file_path

    def _write_csv_data(self, file_path: str) -> None:
        """
        Write CSV data to the specified file path.

        Args:
            file_path: The path to write the CSV file to.
        """
        self.status_bar.showMessage(self.tr("Exporting to CSV..."))

        with open(file_path, "w", newline="", encoding="utf-8-sig") as csvfile:
            writer = csv.writer(csvfile)

            self._write_csv_metadata(writer)
            self._write_csv_headers(writer)

            # Write data rows with progress feedback
            for row in range(self.table_view.model().rowCount()):
                row_data = []
                for col in range(self.table_view.model().columnCount()):
                    item = self.table_view.model().data(
                        self.table_view.model().index(row, col),
                        Qt.ItemDataRole.DisplayRole,
                    )
                    row_data.append(item if item else "")
                writer.writerow(row_data)

                if row % 50 == 0:  # Update progress every 50 rows
                    self.status_bar.showMessage(
                        f"Exporting row {row + 1} of {self.table_view.model().rowCount()}..."
                    )

    def _write_csv_metadata(self, writer: Any) -> None:
        """
        Write metadata headers to the CSV file.

        Args:
            writer: The CSV writer object.
        """
        writer.writerow(["RimSort Workshop Items Export"])
        writer.writerow(
            [f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]
        )
        writer.writerow([f"Total Items: {self.table_view.model().rowCount()}"])
        writer.writerow(
            [f"Source ACF: {self.steamcmd_interface.steamcmd_appworkshop_acf_path}"]
        )
        writer.writerow([])

    def _write_csv_headers(self, writer: Any) -> None:
        """
        Write column headers and descriptions to the CSV file.

        Args:
            writer: The CSV writer object.
        """
        headers = []
        descriptions = []
        for col in range(self.table_view.model().columnCount()):
            header = (
                self.table_model.headerData(
                    col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
                )
                or ""
            )
            headers.append(header)
            descriptions.append(self._get_column_description(col))
        writer.writerow(headers)
        writer.writerow(descriptions)
        writer.writerow([])

    def _finalize_csv_export(self, file_path: str) -> None:
        """
        Finalize the CSV export by updating status and showing success message.

        Args:
            file_path: The path of the exported file.
        """
        self.status_bar.showMessage(
            f"Successfully exported {self.table_view.model().rowCount()} items to {file_path}"
        )
        show_information(
            title=self.tr("Export Success"),
            text=self.tr("Successfully exported {count} items to {file_path}").format(
                count=self.table_view.model().rowCount(), file_path=file_path
            ),
        )

    def _handle_csv_export_error(
        self, message: str, title: str, details: Optional[str] = None
    ) -> None:
        """
        Handle CSV export errors by logging, updating status, and showing dialog.

        Args:
            message: The error message.
            title: The dialog title.
            details: Optional additional details.
        """
        self.status_bar.showMessage(message)
        logger.error(f"CSV Export error: {message}", exc_info=True)
        show_warning(
            title=self.tr(title),
            text=message,
            information=details,
        )

    def _get_column_description(self, col: int) -> str:
        """Get description for a table column."""
        try:
            column = self.TableColumn(col)
            return column.description
        except ValueError:
            return ""

    def show_context_menu(self, position: QPoint) -> None:
        menu = QMenu()

        # Get selected row
        index = self.table_view.indexAt(position)
        if index.isValid():
            # Map to source model
            source_index = self.proxy_model.mapToSource(index)
            row = source_index.row()
            pfid = self.table_model.data(self.table_model.index(row, self.COL_PFID))

            if pfid:
                # Add view in Steam action
                view_in_steam = menu.addAction(self.tr("Open Mod URL"))
                view_in_steam.setIcon(
                    self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
                )
                url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"
                view_in_steam.triggered.connect(partial(platform_specific_open, url))

                # Add copy PFID action
                copy_pfid = menu.addAction(self.tr("Copy PFID"))
                copy_pfid.setIcon(
                    self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
                )
                copy_pfid.triggered.connect(
                    partial(QApplication.clipboard().setText, pfid)
                )

                # Add view mod details action
                view_details = menu.addAction(self.tr("View Mod Details"))
                view_details.setIcon(
                    self.style().standardIcon(
                        QStyle.StandardPixmap.SP_FileDialogInfoView
                    )
                )
                view_details.triggered.connect(partial(self._view_mod_details, pfid))

                # Add open folder action
                mod_path = self.table_model.data(
                    self.table_model.index(row, self.COL_MOD_PATH)
                )
                if mod_path and Path(mod_path).exists():
                    open_folder = menu.addAction(self.tr("Open Mod Folder"))
                    open_folder.setIcon(
                        self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
                    )
                    open_folder.triggered.connect(
                        partial(platform_specific_open, mod_path)
                    )

        menu.exec_(self.table_view.viewport().mapToGlobal(position))

    def _view_mod_details(self, pfid: str) -> None:
        """Show mod details in a dialog."""
        name = get_mod_name_from_pfid(pfid)
        path = get_mod_path_from_pfid(pfid)
        details = f"PFID: {pfid}\nName: {name}\nPath: {path}"
        show_information(title=self.tr("Mod Details"), text=details)

    def _build_active_pfids(self) -> None:
        """Build set of active PFIDs from active_mods_list."""
        self.active_pfids = set()
        if self.active_mods_list is not None:
            uuids = getattr(self.active_mods_list, "uuids", None)
            if uuids is not None:
                for uuid in uuids:
                    mod_data = self.metadata_manager.internal_local_metadata.get(uuid)
                    if mod_data and "publishedfileid" in mod_data:
                        self.active_pfids.add(mod_data["publishedfileid"])
        logger.debug(f"Active PFIDs: {self.active_pfids}")

    def populate_table(self, entries: list[AcfEntry]) -> None:
        """
        Populate the table model with ACF data entries.

        Args:
            entries: List of AcfEntry objects containing ACF data.
        """
        self.entries = entries
        self.table_model.set_entries(entries)
        self._build_active_pfids()

    def import_acf_data(self) -> None:
        answer = show_dialogue_conditional(
            title=self.tr("Confirm ACF import"),
            text=self.tr("This will replace your current steamcmd .acf file"),
            information=self.tr(
                "Are you sure you want to import .acf? THis only works for steamcmd"
            ),
            button_text_override=[
                self.tr("Import .acf"),
            ],
        )
        # Import .acf if user wants to import
        answer_str = str(answer)
        download_text = self.tr("Import .acf")
        if download_text in answer_str:
            EventBus().do_import_acf.emit()
            self.load_acf_data()

    def export_acf_data(self) -> None:
        """
        Export the raw ACF file to a user-defined location by copying the file.

        Shows status messages and error handling for file not found or permission errors.
        """

        steamcmd = self.steamcmd_interface
        if not steamcmd or not hasattr(steamcmd, "steamcmd_appworkshop_acf_path"):
            logger.warning("Export failed: SteamCMD interface not properly initialized")
            show_warning(
                title=self.tr("Export Error"),
                text=self.tr("SteamCMD interface not properly initialized"),
            )
            return

        acf_path = steamcmd.steamcmd_appworkshop_acf_path
        if not acf_path or not os.path.isfile(acf_path):
            acf_path_str = acf_path or "None"
            self.status_bar.showMessage(
                self.tr("ACF file not found: {acf_path}").format(acf_path=acf_path_str)
            )
            logger.error(f"Export failed: ACF file not found: {acf_path_str}")
            show_warning(
                title=self.tr("Export Error"),
                text=self.tr("ACF file not found at: {acf_path}").format(
                    acf_path=acf_path_str
                ),
            )
            return

        file_path = show_dialogue_file(
            mode="save",
            caption="Export ACF File",
            _dir="appworkshop_294100.acf",
            _filter="ACF Files (*.acf);;All Files (*)",
        )
        if not file_path:
            show_warning(
                title=self.tr("Export Error"),
                text=self.tr("Export canceled by user."),
            )
            return

        try:
            shutil.copy(acf_path, file_path)
            self.status_bar.showMessage(
                self.tr("Successfully exported ACF to {file_path}").format(
                    file_path=file_path
                )
            )
            logger.debug(f"Successfully exported ACF to {file_path}")
            show_information(
                title=self.tr("Export Success"),
                text=self.tr("Successfully exported ACF to {file_path}").format(
                    file_path=file_path
                ),
            )
        except PermissionError:
            error_msg = self.tr(
                "Export failed: Permission denied - check file permissions"
            )
            logger.error(f"Export failed due to Permission: {error_msg}")
            show_warning(title=self.tr("Export Error"), text=error_msg)
        except Exception as e:
            error_msg = self.tr("Export failed: {e}").format(e=str(e))
            logger.error(f"Export failed {error_msg}")
            show_fatal_error(
                title=self.tr("Export failed"),
                text=self.tr("Export failed unknown exception occurred"),
                details=error_msg,
            )


class ActiveModDelegate(QStyledItemDelegate):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.acf_log_reader: Optional["AcfLogReader"] = cast("AcfLogReader", parent)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        acf_log_reader = self.acf_log_reader
        if acf_log_reader is None:
            super().paint(painter, option, index)
            return

        pfid_index: QModelIndex = index.sibling(index.row(), acf_log_reader.COL_PFID)
        pfid: Optional[str] = acf_log_reader.table_model.data(
            pfid_index, Qt.ItemDataRole.DisplayRole
        )

        if pfid and pfid in getattr(acf_log_reader, "active_pfids", set()):
            painter.save()

            rect = option.rect  # type: ignore[attr-defined]
            font: QFont = option.font  # type: ignore[attr-defined]

            painter.fillRect(rect, QColor(0, 100, 0))  # Dark green background
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))  # White text
            painter.drawText(
                rect.adjusted(5, 0, 0, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                index.data(),
            )
            painter.restore()
        else:
            super().paint(painter, option, index)
