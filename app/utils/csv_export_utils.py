"""
CSV export utility for BaseModsPanel and subclasses.

Provides functionality to export table data to CSV files with:
- Automatic filename generation with timestamps
- Metadata headers (export date, total items, source ACF path)
- Column descriptions
- Progress logging
- Comprehensive error handling and user feedback
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger
from PySide6.QtCore import Qt

from app.views.dialogue import show_dialogue_file, show_information, show_warning
from app.windows.base_mods_panel import BaseModsPanel

# Error message templates
INVALID_EXPORT_FILE_PATH = "Invalid file path provided for export: {file_path}"
EXPORT_PERMISSION_DENIED = "Export failed: Permission denied - check file permissions"
EXPORT_FILESYSTEM_ERROR = "Export failed: File system error: {e}"
EXPORT_UNKNOWN_ERROR = "Export failed due to an unknown error"


def export_to_csv(panel: BaseModsPanel) -> None:
    """
    Export table data to CSV file with metadata and error handling.

    Orchestrates the complete CSV export workflow:
    1. User selects file path via save dialog
    2. File path is validated
    3. CSV is written with metadata, headers, and data rows
    4. User is notified of success or failure

    Args:
        panel: The panel instance (BaseModsPanel or subclass) containing the table to export.

    Error handling:
        - ValueError: Invalid file path - shown in error dialog
        - PermissionError: Insufficient write permissions - shown in error dialog
        - OSError: File system errors - shown in error dialog
        - Exception: Any other errors - shown in error dialog with details
    """
    try:
        file_path = _prepare_csv_export(panel)
        if not file_path:
            return

        _write_csv_data(panel, file_path)
        _finalize_csv_export(panel, file_path)
    except ValueError as e:
        _handle_csv_export_error(panel, str(e), "Invalid File Path")
    except PermissionError:
        _handle_csv_export_error(
            panel,
            EXPORT_PERMISSION_DENIED,
            "Export Permission Denied",
        )
    except OSError as e:
        _handle_csv_export_error(
            panel,
            EXPORT_FILESYSTEM_ERROR.format(e=str(e)),
            "Export File System Error",
        )
    except Exception as e:
        _handle_csv_export_error(
            panel,
            EXPORT_UNKNOWN_ERROR,
            "Export Unknown Error",
            str(e),
        )


def _prepare_csv_export(panel: BaseModsPanel) -> Optional[str]:
    """
    Prepare CSV export by prompting user for file path and validating it.

    Steps:
    1. Shows file save dialog with default filename (timestamped)
    2. Validates that the file path is syntactically correct
    3. Tests that the file can be opened for writing

    Args:
        panel: The panel instance (BaseModsPanel or subclass).

    Returns:
        The selected file path if valid, None if user canceled the dialog.

    Raises:
        ValueError: If the file path is invalid or cannot be resolved.
        PermissionError: If the file cannot be written due to permission issues.
        OSError: If other file system errors occur.
    """
    file_path = show_dialogue_file(
        mode="save",
        caption="Export to CSV",
        _dir=f"workshop_items_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        _filter="CSV Files (*.csv)",
    )
    if not file_path:
        logger.debug("User cancelled CSV export")
        return None

    # Validate the file path syntax
    try:
        Path(file_path).resolve(strict=False)
    except (OSError, ValueError) as e:
        raise ValueError(INVALID_EXPORT_FILE_PATH.format(file_path=file_path)) from e

    # Test that we can write to the file (catches permission and path issues)
    try:
        with open(file_path, "w", newline="", encoding="utf-8"):
            pass  # Just test file opening, don't write anything
    except PermissionError:
        raise
    except OSError:
        raise

    return file_path


def _write_csv_data(panel: BaseModsPanel, file_path: str) -> None:
    """
    Write complete CSV data to file including metadata, headers, and table rows.

    CSV structure:
    - Header section: Title, export date, row count, optional source ACF path
    - Column headers and descriptions
    - Blank separator row
    - Data rows from the table (one row per iteration)

    Progress is logged every 50 rows for large datasets.

    Args:
        panel: The panel instance containing the table model to export.
        file_path: The file path to write the CSV to.
    """
    logger.debug(f"Starting CSV export to {file_path}")
    model = _get_table_model(panel)

    with open(file_path, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.writer(csvfile)

        _write_csv_metadata(panel, writer)
        _write_csv_headers(panel, writer)

        # Write data rows with progress logging
        row_count = model.rowCount()
        for row in range(row_count):
            row_data = []
            for col in range(model.columnCount()):
                item = model.data(
                    model.index(row, col),
                    Qt.ItemDataRole.DisplayRole,
                )
                row_data.append(item if item else "")
            writer.writerow(row_data)

            if row % 50 == 0 and row > 0:  # Log progress every 50 rows (skip row 0)
                logger.debug(f"Exported {row} / {row_count} rows")


def _write_csv_metadata(panel: BaseModsPanel, writer: Any) -> None:
    """
    Write metadata headers to the CSV file.

    Metadata includes:
    - Export title
    - Export timestamp
    - Total number of rows exported
    - Source ACF file path (if available in panel)

    Args:
        panel: The panel instance (BaseModsPanel or subclass).
        writer: The CSV writer object.
    """
    model = _get_table_model(panel)

    writer.writerow(["RimSort Workshop Items Export"])
    writer.writerow([f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([f"Total Items: {model.rowCount()}"])

    # Add SteamCMD ACF path if available (AcfLogReader has this)
    acf_path = None
    if hasattr(panel, "metadata_manager") and hasattr(
        panel.metadata_manager, "steamcmd_wrapper"
    ):
        acf_path = getattr(
            panel.metadata_manager.steamcmd_wrapper,
            "steamcmd_appworkshop_acf_path",
            None,
        )

    if acf_path:
        writer.writerow([f"Source ACF: {acf_path}"])
    writer.writerow([])  # Blank separator


def _write_csv_headers(panel: BaseModsPanel, writer: Any) -> None:
    """
    Write column headers and descriptions to the CSV file.

    Writes two rows: one for column headers, one for descriptions.

    Args:
        panel: The panel instance (BaseModsPanel or subclass).
        writer: The CSV writer object.
    """
    model = _get_table_model(panel)

    headers = []
    descriptions = []
    for col in range(model.columnCount()):
        header = (
            model.headerData(
                col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
            )
            or ""
        )
        headers.append(header)
        descriptions.append(_get_column_description(panel, col))

    writer.writerow(headers)
    writer.writerow(descriptions)
    writer.writerow([])  # Blank separator


def _finalize_csv_export(panel: BaseModsPanel, file_path: str) -> None:
    """
    Finalize the CSV export by logging success and showing confirmation dialog.

    Args:
        panel: The panel instance (BaseModsPanel or subclass).
        file_path: The path of the exported CSV file.
    """
    model = _get_table_model(panel)
    row_count = model.rowCount()

    logger.info(f"Successfully exported {row_count} items to {file_path}")
    show_information(
        title=panel.tr("Export Success"),
        text=panel.tr("Successfully exported {count} items to {file_path}").format(
            count=row_count, file_path=file_path
        ),
    )


def _handle_csv_export_error(
    panel: BaseModsPanel,
    message: str,
    title: str,
    details: Optional[str] = None,
) -> None:
    """
    Handle CSV export errors with logging and user notification.

    Logs the error with full stack trace and shows an error dialog to the user.

    Args:
        panel: The panel instance (BaseModsPanel or subclass).
        message: The error message to display to the user.
        title: The dialog title.
        details: Optional additional details (technical info) to show in the dialog.
    """
    logger.error(f"CSV Export error: {message}", exc_info=True)
    show_warning(
        title=panel.tr(title),
        text=message,
        information=details,
    )


def _get_table_model(panel: BaseModsPanel) -> Any:
    """
    Get the table model from the panel.

    Handles both direct attribute access (editor_model) and property-based access
    (table_view.model()), making this utility compatible with various panel implementations.

    Args:
        panel: The panel instance (BaseModsPanel or subclass).

    Returns:
        The table model object.
    """
    return (
        panel.editor_model
        if hasattr(panel, "editor_model")
        else panel.table_view.model()  # type: ignore[attr-defined]
    )


def _get_column_description(panel: BaseModsPanel, col: int) -> str:
    """
    Get description for a table column (currently returns the column header).

    This is a placeholder for future column-specific descriptions.
    Currently, it returns the same as the header.

    Args:
        panel: The panel instance (BaseModsPanel or subclass).
        col: The column index.

    Returns:
        The column header/description string.
    """
    model = _get_table_model(panel)
    header = (
        model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        or ""
    )
    return header
