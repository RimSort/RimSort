import csv
import os
import re
import shutil
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union, cast

from loguru import logger
from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QProgressDialog,
    QPushButton,
    QStatusBar,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controllers.settings_controller import SettingsController
from app.utils.event_bus import EventBus
from app.utils.metadata import MetadataManager
from app.utils.mod_utils import (
    get_mod_name_from_pfid,
    get_mod_path_from_pfid,
)
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.utils.steam.steamfiles.wrapper import acf_to_dict
from app.views.dialogue import (
    show_dialogue_conditional,
    show_fatal_error,
    show_information,
    show_warning,
)


class AcfLogReader(QDialog):
    from enum import IntEnum

    class TableColumn(IntEnum):
        """Enumeration of table columns with descriptions."""

        PFID = 0
        MOD_DOWNLOADED = 1
        UPDATED_ON_WORKSHOP = 2
        TYPE = 3
        MOD_NAME = 4
        MOD_PATH = 5

        @property
        def description(self) -> str:
            """Get human-readable description of the column."""
            return {
                self.PFID: "Steam Workshop Published File ID",
                self.MOD_DOWNLOADED: "Mod downloaded",
                self.UPDATED_ON_WORKSHOP: "Last update timestamp (UTC) / Relative Time",
                self.TYPE: "Item type (workshop/local)",
                self.MOD_NAME: "Mod name from Steam metadata",
                self.MOD_PATH: "Filesystem path to mod",
            }[self]

    # Maintain backward compatibility with old constant names
    COL_PFID = TableColumn.PFID
    COL_MOD_DOWNLOADED = TableColumn.MOD_DOWNLOADED
    COL_UPDATED_ON_WORKSHOP = TableColumn.UPDATED_ON_WORKSHOP
    COL_TYPE = TableColumn.TYPE
    COL_MOD_NAME = TableColumn.MOD_NAME
    COL_MOD_PATH = TableColumn.MOD_PATH

    def __init__(
        self,
        settings_controller: SettingsController,
        active_mods_list: Optional[object] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Log Reader")
        self.settings_controller = settings_controller
        self.active_mods_list = active_mods_list
        self._metadata_cache: dict[str, dict[str, Any]] = {}

        self.entries: list[dict[str, Union[str, int, None]]] = []

        # Track sources for which empty ACF data warning has been logged
        self._logged_empty_acf_sources: set[str] = set()

        # Setup auto-refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.setInterval(15000)  # 15 seconds
        self.refresh_timer.timeout.connect(self.load_acf_data)

        # Add attribute to track time display mode: True for absolute, False for relative
        self.show_absolute_time = True

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

        # Table widget
        self.table_widget = QTableWidget()
        self.table_widget.setSortingEnabled(True)
        # Ensure columns fit window width but allow manual resizing
        from PySide6.QtWidgets import QHeaderView

        self.table_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        header = self.table_widget.horizontalHeader()
        if isinstance(header, QHeaderView):
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setMinimumSectionSize(40)
        # Track proportional column widths to keep full-width fit
        self._table_col_weights: list[float] = []
        self.table_widget.horizontalHeader().sectionResized.connect(
            self._on_table_section_resized
        )
        main_layout.addWidget(self.table_widget)

        main_layout.addWidget(self.status_bar)
        self.setLayout(main_layout)

        # Set up custom context menu for table widget
        self.table_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self.show_context_menu)

        # Remove immediate load; rely on timer to trigger after 15 seconds
        # Initialize last modification times for ACF files
        self._last_steamcmd_acf_mtime: Optional[float] = None
        self._last_steam_acf_mtime: Optional[float] = None

        # Set the check for initial application load.
        self.is_initial_load = True

        # Start the refresh timer to trigger load_acf_data after 15 seconds
        self.refresh_timer.start()

    def _debounced_filter_table(self) -> None:
        """Debounce filter_table calls to improve performance on rapid input."""
        if hasattr(self, "_filter_timer") and self._filter_timer.isActive():
            self._filter_timer.stop()
        else:
            self._filter_timer: QTimer = QTimer()
            self._filter_timer.setSingleShot(True)
            self._filter_timer.timeout.connect(self.filter_table)
        self._filter_timer.start(20)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable buttons during long operations."""
        self.refresh_btn.setEnabled(enabled)
        self.import_acf_btn.setEnabled(enabled)
        self.export_acf_btn.setEnabled(enabled)
        self.export_btn.setEnabled(enabled)

    def _on_refresh_clicked(self) -> None:
        self._set_buttons_enabled(False)
        try:
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

    # ----- Table width management (manual resize + full-width fit) -----
    def _viewport_width(self) -> int:
        try:
            return max(0, int(self.table_widget.viewport().width()))
        except Exception:
            return max(0, int(self.table_widget.width()))

    def _init_or_sync_column_weights(self) -> None:
        """Ensure column weights exist and match current column count."""
        col_count = self.table_widget.columnCount()
        if col_count <= 0:
            return
        if not getattr(self, "_table_col_weights", None) or len(self._table_col_weights) != col_count:
            # Initialize equal weights
            self._table_col_weights = [1.0 / col_count for _ in range(col_count)]

    def _recalculate_weights_from_current_widths(self) -> None:
        col_count = self.table_widget.columnCount()
        if col_count <= 0:
            return
        header = self.table_widget.horizontalHeader()
        sizes = [header.sectionSize(i) for i in range(col_count)]
        total = sum(sizes) or 1
        self._table_col_weights = [s / total for s in sizes]

    def _apply_table_widths_to_viewport(self) -> None:
        col_count = self.table_widget.columnCount()
        if col_count <= 0:
            return
        self._init_or_sync_column_weights()
        vpw = self._viewport_width()
        if vpw <= 0:
            return
        header = self.table_widget.horizontalHeader()
        # Compute widths from weights, clamp min, fix rounding on the last
        min_w = max(40, int(vpw * 0.05 / col_count))
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

    def _on_table_section_resized(self, index: int, old: int, new: int) -> None:  # noqa: ARG002
        if getattr(self, "_suppress_section_resize_updates", False):
            return
        # Update weights and normalize to viewport width immediately
        self._recalculate_weights_from_current_widths()
        self._apply_table_widths_to_viewport()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_table_widths_to_viewport()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # Defer width application until after layout is finalized
        QTimer.singleShot(0, self._apply_table_widths_to_viewport)

    def load_acf_data(self) -> None:
        """
        Load workshop item data from SteamCMD and Steam ACF files, then populate the table.

        Raises:
            RuntimeError: If neither ACF file can be loaded or data format is invalid.
            FileNotFoundError: If the ACF files do not exist.
            Exception: For other errors during loading or parsing.
        """
        self.status_bar.showMessage("Loading ACF data...")
        self._set_buttons_enabled(False)

        try:
            # Check modification times of ACF files to avoid unnecessary reloads
            steamcmd = SteamcmdInterface.instance()
            steamcmd_acf_path = (
                Path(steamcmd.steamcmd_appworkshop_acf_path)
                if steamcmd and hasattr(steamcmd, "steamcmd_appworkshop_acf_path")
                else None
            )
            current_instance = self.settings_controller.settings.current_instance
            workshop_acf_path = (
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
                workshop_acf_path.stat().st_mtime
                if workshop_acf_path.exists()
                else None
            )

            # If modification times unchanged, skip reload
            if (
                steamcmd_acf_mtime == self._last_steamcmd_acf_mtime
                and steam_acf_mtime == self._last_steam_acf_mtime
            ):
                count = 0
                if hasattr(self, "entries") and isinstance(self.entries, list):
                    count = len(self.entries)
                self.status_bar.showMessage(
                    self.tr("Loaded {count} items | Last updated: {time}").format(
                        count=count,
                        time=datetime.now().strftime("%H:%M:%S"),
                    )
                )
                return

            # Update stored modification times
            self._last_steamcmd_acf_mtime = steamcmd_acf_mtime
            self._last_steam_acf_mtime = steam_acf_mtime

            combined_acf_data: dict[str, Any] = {}

            # Load SteamCMD ACF data
            steamcmd_acf_data = {}
            if steamcmd_acf_path and steamcmd_acf_path.exists():
                try:
                    steamcmd_acf_data = acf_to_dict(str(steamcmd_acf_path))
                except Exception as e:
                    logger.error(
                        f"Failed to parse ACF file at {steamcmd_acf_path}: {str(e)}"
                    )
            if steamcmd_acf_path is not None:
                self._log_acf_load_result(
                    "SteamCMD", steamcmd_acf_path, steamcmd_acf_data
                )
            else:
                if self.is_initial_load:
                    logger.warning(
                        "SteamCMD ACF path is None, skipping log_acf_load_result call"
                    )

            # Load Steam ACF data
            steam_acf_data = {}
            if workshop_acf_path.exists():
                try:
                    steam_acf_data = acf_to_dict(str(workshop_acf_path))
                except Exception as e:
                    logger.error(
                        f"Failed to parse ACF file at {workshop_acf_path}: {str(e)}"
                    )
            if workshop_acf_path is not None:
                self._log_acf_load_result("Steam", workshop_acf_path, steam_acf_data)
            else:
                if self.is_initial_load:
                    logger.warning(
                        "Steam ACF path is None, skipping log_acf_load_result call"
                    )

            # set the inital load flag to False
            self.is_initial_load = False

            # Merge AppWorkshop data carefully to avoid overwriting
            combined_acf_data = {}
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

            if not combined_acf_data:
                raise RuntimeError(
                    "Failed to load any ACF data from SteamCMD or Steam paths"
                )

            workshop_items = combined_acf_data.get("AppWorkshop", {}).get(
                "WorkshopItemsInstalled", {}
            )
            if not isinstance(workshop_items, dict):
                raise RuntimeError("Invalid workshop items data format")

            entries: list[dict[str, Union[str, int, None]]] = []
            self.timeupdated_data: dict[str, Union[int, None]] = {}

            for pfid, item in workshop_items.items():
                if not isinstance(item, dict):
                    continue

                pfid_str = str(pfid)
                entries.append(
                    {
                        "published_file_id": pfid_str,
                        "type": "workshop",
                        "path": str(item.get("manifest", "")),
                        "timeupdated": item.get("timeupdated"),
                    }
                )

                if "timeupdated" in item:
                    self.timeupdated_data[pfid_str] = item["timeupdated"]

            self.populate_table(entries)
            self.status_bar.showMessage(
                self.tr("Loaded {count} items | Last updated: {time}").format(
                    count=len(entries),
                    time=datetime.now().strftime("%H:%M:%S"),
                )
            )
            self.entries = entries

            if not self.refresh_timer.isActive():
                self.refresh_timer.start()

        except Exception as e:
            logger.error(f"Error loading ACF data: {str(e)}")
            error_msg = f"{str(e)}"
            self.status_bar.showMessage(error_msg)
        finally:
            self._set_buttons_enabled(True)

    _logged_warnings: set[tuple[str, str]] = set()

    def _log_acf_load_result(
        self, source_name: str, path: Path, data: dict[str, Any]
    ) -> None:
        if data:
            logger.info(f"Loaded ACF data from {source_name} at {path}")
        else:
            key = (source_name, str(path))
            if key not in self._logged_warnings:
                logger.warning(f"No ACF data loaded from {source_name} at {path}")
                self._logged_warnings.add(key)

    def filter_table(self) -> None:
        """
        Filter table rows based on search text with regex and multi-column support.

        Searches visible columns (PFID, Mod Name, Mod Path) using case-insensitive regex.
        If regex is invalid, falls back to simple substring search.
        If search text is empty, all rows are shown.
        """
        search_text = self.search_box.text()
        if not search_text:
            # Show all rows if search is empty
            for row in range(self.table_widget.rowCount()):
                self.table_widget.setRowHidden(row, False)
            return

        # Compile regex pattern for case-insensitive search
        try:
            pattern = re.compile(search_text, re.IGNORECASE)
            use_regex = True
        except re.error:
            pattern = None
            use_regex = False

        # Only search visible columns that are likely to contain searchable text
        search_columns = {self.COL_PFID, self.COL_MOD_NAME, self.COL_MOD_PATH}

        for row in range(self.table_widget.rowCount()):
            match = False
            for col in search_columns:
                item = self.table_widget.item(row, col)
                if item and isinstance(item, QTableWidgetItem):
                    item_text = item.text() or ""
                    if use_regex and pattern is not None:
                        try:
                            if pattern.search(item_text):
                                match = True
                                break
                        except re.error:
                            # If regex fails during search, fallback to substring
                            if search_text.lower() in item_text.lower():
                                match = True
                                break
                    else:
                        if search_text.lower() in item_text.lower():
                            match = True
                            break
            self.table_widget.setRowHidden(row, not match)

    def export_to_csv(self) -> None:
        """
        Export table data to CSV file with enhanced error handling and metadata.

        Errors are shown in the status bar and logged with full stack traces.
        Includes detailed metadata headers in the CSV file.
        """
        self._set_buttons_enabled(False)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export to CSV",
            f"workshop_items_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)",
        )
        if not file_path:
            self.status_bar.showMessage(self.tr("Export canceled by user."))
            self._set_buttons_enabled(True)
            return

        try:
            # Check file can be opened before proceeding
            with open(file_path, "w", newline="", encoding="utf-8"):
                pass  # Just testing file opening, no need for the file object
        except PermissionError as e:
            error_msg = self.tr(
                "Export failed: Permission denied - check file permissions"
            )
            self.status_bar.showMessage(error_msg)
            logger.error(f"Export permission error: {str(e)} - file: {file_path}")
            show_warning(
                title=self.tr("Export Error"),
                text=self.tr(
                    "Export failed: Permission denied - check file permissions"
                ),
                information=f"{error_msg}",
            )
            self._set_buttons_enabled(True)
            return
        except OSError as e:
            error_msg = self.tr("Export failed: File system error - {e}").format(
                e=str(e)
            )
            self.status_bar.showMessage(error_msg)
            logger.error(f"Export filesystem error: {str(e)} - file: {file_path}")
            show_warning(
                title=self.tr("Export Error"),
                text=self.tr("Export failed: File system error"),
                information=f"{error_msg}",
            )
            self._set_buttons_enabled(True)
            return

        try:
            self.status_bar.showMessage(self.tr("Exporting to CSV..."))

            progress = QProgressDialog(
                self.tr("Exporting rows..."),
                self.tr("Cancel"),
                0,
                self.table_widget.rowCount(),
            )
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.show()

            with open(file_path, "w", newline="", encoding="utf-8-sig") as csvfile:
                writer = csv.writer(csvfile)

                # Enhanced metadata header
                writer.writerow(["RimSort Workshop Items Export"])
                writer.writerow(
                    [f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]
                )
                writer.writerow([f"Total Items: {self.table_widget.rowCount()}"])
                writer.writerow(
                    [
                        f"Source ACF: {SteamcmdInterface.instance().steamcmd_appworkshop_acf_path}"
                    ]
                )
                writer.writerow([])

                # Write column headers with descriptions
                headers = []
                descriptions = []
                for col in range(self.table_widget.columnCount()):
                    header_item = self.table_widget.horizontalHeaderItem(col)
                    headers.append(header_item.text() if header_item else "")
                    descriptions.append(self._get_column_description(col))
                writer.writerow(headers)
                writer.writerow(descriptions)
                writer.writerow([])

                # Write data rows with progress feedback
                for row in range(self.table_widget.rowCount()):
                    if progress.wasCanceled():
                        self.status_bar.showMessage(self.tr("Export canceled by user."))
                        self._set_buttons_enabled(True)
                        return

                    row_data = []
                    for col in range(self.table_widget.columnCount()):
                        item = self.table_widget.item(row, col)
                        row_data.append(item.text() if item else "")
                    writer.writerow(row_data)

                    if row % 50 == 0:  # Update progress every 50 rows
                        progress.setValue(row)
                        self.status_bar.showMessage(
                            f"Exporting row {row + 1} of {self.table_widget.rowCount()}..."
                        )

            progress.setValue(self.table_widget.rowCount())
            self.status_bar.showMessage(
                f"Successfully exported {self.table_widget.rowCount()} items to {file_path}"
            )
        except Exception as e:
            error_msg = f"Export failed: {str(e)}"
            self.status_bar.showMessage(error_msg)
            logger.error(f"Export error: {str(e)}", exc_info=True)
            show_warning(
                title=self.tr("Export Error"),
                text=self.tr("Export failed due to an unknown error"),
                information=f"{error_msg}",
            )
        finally:
            self._set_buttons_enabled(True)

    def _get_column_description(self, col: int) -> str:
        """Get description for a table column."""
        try:
            column = self.TableColumn(col)
            return column.description
        except ValueError:
            return ""

    def get_relative_time(self, timestamp: Union[str, int, None]) -> str:
        """
        Convert a timestamp to a relative time string (e.g. "2 days ago").
        Returns "Invalid timestamp" if the input cannot be parsed.
        """
        if timestamp is None:
            return "Unknown"
        try:
            dt = datetime.fromtimestamp(int(timestamp))
            now = datetime.now()
            delta = now - dt

            if delta.days > 365:
                return f"{delta.days // 365} years ago"
            elif delta.days > 30:
                return f"{delta.days // 30} months ago"
            elif delta.days > 0:
                return f"{delta.days} days ago"
            elif delta.seconds > 3600:
                return f"{delta.seconds // 3600} hours ago"
            elif delta.seconds > 60:
                return f"{delta.seconds // 60} minutes ago"
            else:
                return "Just now"
        except (ValueError, TypeError):
            return "Invalid timestamp"

    def show_context_menu(self, position: QPoint) -> None:
        menu = QMenu()

        # Get selected row
        selected_row = self.table_widget.rowAt(position.y())
        if selected_row >= 0:
            pfid_item = self.table_widget.item(selected_row, 0)
            pfid = pfid_item.text() if pfid_item else None

            if pfid:
                # Add view in Steam action
                view_in_steam = menu.addAction(self.tr("View in Steam Workshop"))
                view_in_steam.triggered.connect(
                    lambda: webbrowser.open(
                        f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"
                    )
                )

                """ Disabled for now will remove it if  no fyture use case
                # Add open URL in browser action
                def open_mod_url() -> None:
                    metadata_manager = MetadataManager.instance()
                    mod_metadata = None
                    # Find mod metadata by matching publishedfileid
                    for (
                        uuid,
                        metadata,
                    ) in metadata_manager.internal_local_metadata.items():
                        if metadata.get("publishedfileid") == pfid:
                            mod_metadata = metadata
                            break
                    if mod_metadata:
                        url = mod_metadata.get("url") or mod_metadata.get("steam_url")
                        if url:
                            logger.info(f"Opening mod URL in browser: {url}")
                            open_url_browser(url)
                        else:
                            logger.warning(f"No URL found for mod with PFID {pfid}")
                    else:
                        logger.warning(f"No metadata found for mod with PFID {pfid}")

                open_url_action = menu.addAction(self.tr("Open URL in browser"))
                open_url_action.triggered.connect(open_mod_url)
                """

                # Add open folder action
                path_item = self.table_widget.item(selected_row, 4)
                mod_path = path_item.text() if path_item else None
                if mod_path and Path(mod_path).exists():
                    open_folder = menu.addAction(self.tr("Open Mod Folder"))
                    open_folder.triggered.connect(
                        lambda: webbrowser.open(f"file://{mod_path}")
                    )

        menu.exec_(self.table_widget.viewport().mapToGlobal(position))

    def populate_table(self, entries: list[dict[str, Any]]) -> None:
        """
        Populate the table widget with ACF data entries.

        Args:
            entries: List of dictionaries containing ACF data with keys:
                - published_file_id: The mod's PublishedFileID
                - type: The mod type (e.g. "workshop")
                - path: The mod's filesystem path
                - timeupdated: Last update timestamp
        """
        self.table_widget.setUpdatesEnabled(False)
        try:
            self.table_widget.clear()
            self.table_widget.setRowCount(len(entries))
            self.table_widget.setColumnCount(6)
            self.table_widget.setHorizontalHeaderLabels(
                [
                    self.tr("Published File ID"),
                    self.tr("Mod downloaded"),
                    self.tr("Updated on Workshop"),
                    self.tr("Type"),
                    self.tr("Mod Name"),
                    self.tr("Mod Path"),
                ]
            )

            self.table_widget.setSortingEnabled(False)
            self._metadata_cache.clear()

            # Build set of active PFIDs if active_mods_list is provided
            self.active_pfids = set()
            if self.active_mods_list is not None:
                metadata_manager = MetadataManager.instance()
                uuids = getattr(self.active_mods_list, "uuids", None)
                if uuids is not None:
                    for uuid in uuids:
                        mod_data = metadata_manager.internal_local_metadata.get(uuid)
                        if mod_data and "publishedfileid" in mod_data:
                            self.active_pfids.add(mod_data["publishedfileid"])
            logger.debug(f"Active PFIDs: {self.active_pfids}")

            for row_index, entry in enumerate(entries):
                # Ensure pfid is a valid string before passing to get_mod_name_from_pfid
                pfid = str(entry.get("published_file_id", "")).strip()
                if not pfid.isdigit():
                    logger.warning(f"Invalid PFID encountered: {pfid}")
                    pfid = "Unknown"

                # Use the validated pfid to fetch the mod name and path
                try:
                    mod_name = get_mod_name_from_pfid(pfid)
                    mod_path = get_mod_path_from_pfid(pfid)
                except Exception as e:
                    logger.error(f"Error getting mod info for PFID {pfid}: {str(e)}")
                    mod_name = f"Error retrieving name: {pfid}"
                    mod_path = f"Error retrieving path: {pfid}"

                # Get internal_time_touched from MetadataManager by matching pfid
                internal_time_touched_str = "Unknown"
                try:
                    metadata_manager = MetadataManager.instance()
                    for metadata in metadata_manager.internal_local_metadata.values():
                        if metadata.get("publishedfileid") == pfid:
                            internal_time_touched = metadata.get(
                                "internal_time_touched"
                            )
                            if internal_time_touched:
                                dt_touched = datetime.fromtimestamp(
                                    int(internal_time_touched)
                                )
                                internal_time_touched_str = dt_touched.strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                )
                                rel_time = self.get_relative_time(internal_time_touched)
                                internal_time_touched_str = (
                                    f"{internal_time_touched_str} | {rel_time}"
                                )
                            break
                except Exception as e:
                    logger.error(
                        f"Error getting internal_time_touched for PFID {pfid}: {str(e)}"
                    )

                items = [
                    QTableWidgetItem(pfid),  # COL_PFID
                    QTableWidgetItem(internal_time_touched_str),  # COL_MOD_DOWNLOADED
                    None,  # COL_LAST_UPDATED placeholder
                    QTableWidgetItem(str(entry.get("type", "unknown"))),  # COL_TYPE
                    QTableWidgetItem(mod_name),  # COL_MOD_NAME
                    QTableWidgetItem(mod_path),  # COL_MOD_PATH
                ]

                # Handle timestamp column with toggle display
                timeupdated = self.timeupdated_data.get(pfid)
                if timeupdated:
                    try:
                        dt = datetime.fromtimestamp(int(timeupdated))
                        abs_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                        rel_time = self.get_relative_time(timeupdated)
                        combined_text = f"{abs_time} | {rel_time}"
                        time_item = QTableWidgetItem(combined_text)
                        time_item.setData(Qt.ItemDataRole.UserRole, int(timeupdated))
                        items[self.COL_UPDATED_ON_WORKSHOP] = time_item
                    except (ValueError, TypeError):
                        items[self.COL_UPDATED_ON_WORKSHOP] = QTableWidgetItem(
                            "Invalid timestamp"
                        )
                else:
                    items[self.COL_UPDATED_ON_WORKSHOP] = QTableWidgetItem("Unknown")

                # Set all items at once
                for col, item in enumerate(items):
                    if item is not None:
                        self.table_widget.setItem(row_index, col, item)

            # Set custom delegate for row coloring
            self.table_widget.setItemDelegate(ActiveModDelegate(self))

            self.table_widget.setSortingEnabled(True)
            # Auto sort by Last Updated column descending on load
            self.table_widget.sortItems(
                self.COL_MOD_DOWNLOADED, order=Qt.SortOrder.DescendingOrder
            )
            # Initialize/sync column weights after columns are defined
            self._init_or_sync_column_weights()
            # Apply weights to fit viewport width
            self._apply_table_widths_to_viewport()
        finally:
            self.table_widget.setUpdatesEnabled(True)

    def import_acf_data(self) -> None:
        answer = show_dialogue_conditional(
            title=self.tr("Conform acf import"),
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

        steamcmd = SteamcmdInterface.instance()
        if not steamcmd or not hasattr(steamcmd, "steamcmd_appworkshop_acf_path"):
            logger.warning("Export failed: SteamCMD interface not properly initialized")
            show_warning(
                title=self.tr("Export Error"),
                text=self.tr("SteamCMD interface not properly initialized"),
            )
            return

        acf_path = steamcmd.steamcmd_appworkshop_acf_path
        if not os.path.isfile(acf_path):
            self.status_bar.showMessage(
                self.tr("ACF file not found: {acf_path}").format(acf_path=acf_path)
            )
            logger.error(f"Export failed: ACF file not found: {acf_path}")
            show_warning(
                title=self.tr("Export Error"),
                text=self.tr("ACF file not found at: {acf_path}").format(
                    acf_path=acf_path
                ),
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export ACF File",
            "appworkshop_294100.acf",
            "ACF Files (*.acf);;All Files (*)",
        )
        if not file_path:
            show_warning(
                title=self.tr("Export Error"),
                text=self.tr(
                    "Invalid file path provided for export: {file_path}"
                ).format(file_path=file_path),
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
                text=self.tr("Exportfailed unknown exception occurred"),
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
        pfid_item = acf_log_reader.table_widget.item(
            pfid_index.row(), pfid_index.column()
        )
        pfid: Optional[str] = pfid_item.text() if pfid_item else None

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
