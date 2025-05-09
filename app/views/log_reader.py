import csv
import os
import re
import shutil
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Union

from loguru import logger
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QProgressDialog,
    QPushButton,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.controllers.settings_controller import SettingsController
from app.utils.event_bus import EventBus
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


class LogReader(QDialog):
    from enum import IntEnum

    class TableColumn(IntEnum):
        """Enumeration of table columns with descriptions."""

        PFID = 0
        LAST_UPDATED = 1
        RELATIVE_TIME = 2
        TYPE = 3
        MOD_NAME = 4
        MOD_PATH = 5

        @property
        def description(self) -> str:
            """Get human-readable description of the column."""
            return {
                self.PFID: "Steam Workshop Published File ID",
                self.LAST_UPDATED: "Last update timestamp (UTC)",
                self.RELATIVE_TIME: "Time since last update",
                self.TYPE: "Item type (workshop/local)",
                self.MOD_NAME: "Mod name from Steam metadata",
                self.MOD_PATH: "Filesystem path to mod",
            }[self]

    # Maintain backward compatibility with old constant names
    COL_PFID = TableColumn.PFID
    COL_LAST_UPDATED = TableColumn.LAST_UPDATED
    COL_RELATIVE_TIME = TableColumn.RELATIVE_TIME
    COL_TYPE = TableColumn.TYPE
    COL_MOD_NAME = TableColumn.MOD_NAME
    COL_MOD_PATH = TableColumn.MOD_PATH

    def __init__(self, settings_controller: SettingsController) -> None:
        super().__init__()
        self.setWindowTitle("Log Reader")
        self.settings_controller = settings_controller
        self._metadata_cache: dict[str, dict[str, Any]] = {}

        self.entries: list[dict[str, Union[str, int, None]]] = []

        # Track sources for which empty ACF data warning has been logged
        self._logged_empty_acf_sources: set[str] = set()

        # Setup auto-refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.setInterval(15000)  # 15 seconds
        self.refresh_timer.timeout.connect(self.load_acf_data)

        # Main layout
        main_layout = QVBoxLayout()

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Ready")

        # Top controls layout
        controls_layout = QHBoxLayout()

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search...")
        self.search_box.textChanged.connect(self._debounced_filter_table)
        controls_layout.addWidget(self.search_box)

        # Refresh button
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        controls_layout.addWidget(self.refresh_btn)

        # Import ACF Data button
        self.import_acf_btn = QPushButton("Import ACF Data")
        self.import_acf_btn.clicked.connect(self._on_import_acf_clicked)
        controls_layout.addWidget(self.import_acf_btn)

        # Export ACF Data button
        self.export_acf_btn = QPushButton("Export ACF Data")
        self.export_acf_btn.clicked.connect(self._on_export_acf_clicked)
        controls_layout.addWidget(self.export_acf_btn)

        # Export button
        self.export_btn = QPushButton("Export to CSV")
        self.export_btn.clicked.connect(self._on_export_to_csv_clicked)
        controls_layout.addWidget(self.export_btn)

        main_layout.addLayout(controls_layout)

        # Table widget
        self.table_widget = QTableWidget()
        self.table_widget.setSortingEnabled(True)
        main_layout.addWidget(self.table_widget)

        main_layout.addWidget(self.status_bar)
        self.setLayout(main_layout)

        # Remove immediate load; rely on timer to trigger after 15 seconds
        # Initialize last modification times for ACF files
        self._last_steamcmd_acf_mtime: float | None = None
        self._last_steam_acf_mtime: float | None = None

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
                    f"Loaded {count} items | Last updated: {datetime.now().strftime('%H:%M:%S')}"
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
                logger.warning(
                    "Steam ACF path is None, skipping log_acf_load_result call"
                )

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
                f"Loaded {len(entries)} items | Last updated: {datetime.now().strftime('%H:%M:%S')}"
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
            self.status_bar.showMessage("Export canceled by user.")
            self._set_buttons_enabled(True)
            return

        try:
            # Check file can be opened before proceeding
            with open(file_path, "w", newline="", encoding="utf-8"):
                pass  # Just testing file opening, no need for the file object
        except PermissionError as e:
            error_msg = "Export failed: Permission denied - check file permissions"
            self.status_bar.showMessage(error_msg)
            logger.error(f"Export permission error: {str(e)} - file: {file_path}")
            show_warning(
                title="Export Error",
                text="Export failed: Permission denied - check file permissions",
                information=f"{error_msg}",
            )
            self._set_buttons_enabled(True)
            return
        except OSError as e:
            error_msg = f"Export failed: File system error - {str(e)}"
            self.status_bar.showMessage(error_msg)
            logger.error(f"Export filesystem error: {str(e)} - file: {file_path}")
            show_warning(
                title="Export Error",
                text="Export failed: File system error",
                information=f"{error_msg}",
            )
            self._set_buttons_enabled(True)
            return

        try:
            self.status_bar.showMessage("Exporting to CSV...")

            progress = QProgressDialog(
                "Exporting rows...", "Cancel", 0, self.table_widget.rowCount(), self
            )
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.show()

            with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
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
                        self.status_bar.showMessage("Export canceled by user.")
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
                title="Export Error",
                text="Export failed due to an unknown error",
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
                view_in_steam = menu.addAction("View in Steam Workshop")
                view_in_steam.triggered.connect(
                    lambda: webbrowser.open(
                        f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"
                    )
                )

                # Add open folder action
                path_item = self.table_widget.item(selected_row, 5)
                mod_path = path_item.text() if path_item else None
                if mod_path and Path(mod_path).exists():
                    open_folder = menu.addAction("Open Mod Folder")
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
                    "Published File ID",
                    "Last Updated",
                    "Relative Time",
                    "Type",
                    "Mod Name",
                    "Mod Path",
                ]
            )

            self.table_widget.setSortingEnabled(False)
            self._metadata_cache.clear()

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

                items = [
                    QTableWidgetItem(pfid),  # COL_PFID
                    None,  # COL_LAST_UPDATED placeholder
                    None,  # COL_RELATIVE_TIME placeholder
                    QTableWidgetItem(str(entry.get("type", "unknown"))),  # COL_TYPE
                    QTableWidgetItem(mod_name),  # COL_MOD_NAME
                    QTableWidgetItem(mod_path),  # COL_MOD_PATH
                ]

                # Handle timestamp columns
                timeupdated = self.timeupdated_data.get(pfid)
                if timeupdated:
                    try:
                        dt = datetime.fromtimestamp(int(timeupdated))
                        time_item = QTableWidgetItem(dt.strftime("%Y-%m-%d %H:%M:%S"))
                        time_item.setData(Qt.ItemDataRole.UserRole, int(timeupdated))
                        items[self.COL_LAST_UPDATED] = time_item
                        items[self.COL_RELATIVE_TIME] = QTableWidgetItem(
                            self.get_relative_time(timeupdated)
                        )
                    except (ValueError, TypeError):
                        items[self.COL_LAST_UPDATED] = QTableWidgetItem(
                            "Invalid timestamp"
                        )
                        items[self.COL_RELATIVE_TIME] = QTableWidgetItem(
                            "Invalid timestamp"
                        )
                else:
                    items[self.COL_LAST_UPDATED] = QTableWidgetItem("Unknown")
                    items[self.COL_RELATIVE_TIME] = QTableWidgetItem("Unknown")

                # Set all items at once
                for col, item in enumerate(items):
                    if item is not None:
                        self.table_widget.setItem(row_index, col, item)

            self.table_widget.setSortingEnabled(True)
            self.table_widget.resizeColumnsToContents()
        finally:
            self.table_widget.setUpdatesEnabled(True)

    def import_acf_data(self) -> None:
        answer = show_dialogue_conditional(
            title="Conform acf import",
            text="This will replace your current steamcmd .acf file",
            information="Are you sure you want to import .acf? THis only works for steamcmd",
            button_text_override=[
                "Import .acf",
            ],
        )
        # Import .acf if user wants to import
        if "Import" in answer:
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
                title="Export Error",
                text="SteamCMD interface not properly initialized",
            )
            return

        acf_path = steamcmd.steamcmd_appworkshop_acf_path
        if not os.path.isfile(acf_path):
            self.status_bar.showMessage(f"ACF file not found: {acf_path}")
            logger.error(f"Export failed: ACF file not found: {acf_path}")
            show_warning(
                title="Export Error", text=f"ACF file not found at: {acf_path}"
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
                title="Export Error",
                text="Invalid file path provided for export: {file_path}",
            )
            return

        try:
            shutil.copy(acf_path, file_path)
            self.status_bar.showMessage(f"Successfully exported ACF to {file_path}")
            logger.debug(f"Successfully exported ACF to {file_path}")
            show_information(
                title="Export Success",
                text=f"Successfully exported ACF to {file_path}",
            )
        except PermissionError:
            error_msg = "Export failed: Permission denied - check file permissions"
            logger.error(f"Export failed due to Permission: {error_msg}")
            show_warning(title="Export Error", text=error_msg)
        except Exception as e:
            error_msg = f"Export failed: {str(e)}"
            logger.error(f"Export failed {error_msg}")
            show_fatal_error(
                title="Export failed",
                text="Exportfailed unknown exception occurred",
                details=error_msg,
            )
