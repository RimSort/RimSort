from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from loguru import logger
from PySide6.QtCore import Qt

from app.views.dialogue import show_dialogue_file, show_information, show_warning

if TYPE_CHECKING:
    from app.views.acf_log_reader import AcfLogReader

# Error messages for CSV export
INVALID_EXPORT_FILE_PATH = "Invalid file path provided for export: {file_path}"
EXPORT_PERMISSION_DENIED = "Export failed: Permission denied - check file permissions"
EXPORT_FILESYSTEM_ERROR = "Export failed: File system error: {e}"
EXPORT_UNKNOWN_ERROR = "Export failed due to an unknown error"


def export_to_csv(acf_log_reader: "AcfLogReader") -> None:
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
    acf_log_reader._set_buttons_enabled(False)
    try:
        file_path = _prepare_csv_export(acf_log_reader)
        if not file_path:
            return

        _write_csv_data(acf_log_reader, file_path)
        _finalize_csv_export(acf_log_reader, file_path)
    except ValueError as e:
        _handle_csv_export_error(acf_log_reader, str(e), "Invalid File Path")
    except PermissionError:
        _handle_csv_export_error(
            acf_log_reader,
            EXPORT_PERMISSION_DENIED,
            "Export Permission Denied",
        )
    except OSError as e:
        _handle_csv_export_error(
            acf_log_reader,
            EXPORT_FILESYSTEM_ERROR.format(e=str(e)),
            "Export File System Error",
        )
    except Exception as e:
        _handle_csv_export_error(
            acf_log_reader,
            EXPORT_UNKNOWN_ERROR,
            "Export Unknown Error",
            str(e),
        )
    finally:
        acf_log_reader._set_buttons_enabled(True)


def _prepare_csv_export(acf_log_reader: "AcfLogReader") -> Optional[str]:
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
        acf_log_reader.status_bar.showMessage(
            acf_log_reader.tr("Export canceled by user.")
        )
        return None

    # Validate user-provided path
    try:
        Path(file_path).resolve(strict=False)  # Check if path is valid
    except (OSError, ValueError) as e:
        raise ValueError(INVALID_EXPORT_FILE_PATH.format(file_path=file_path)) from e

    # Check file can be opened before proceeding
    try:
        with open(file_path, "w", newline="", encoding="utf-8"):
            pass  # Just testing file opening, no need for the file object
    except PermissionError:
        raise
    except OSError:
        raise

    return file_path


def _write_csv_data(acf_log_reader: "AcfLogReader", file_path: str) -> None:
    """
    Write CSV data to the specified file path.

    Args:
        acf_log_reader: The AcfLogReader instance.
        file_path: The path to write the CSV file to.
    """
    acf_log_reader.status_bar.showMessage(acf_log_reader.tr("Exporting to CSV..."))

    with open(file_path, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.writer(csvfile)

        _write_csv_metadata(acf_log_reader, writer)
        _write_csv_headers(acf_log_reader, writer)

        # Write data rows with progress feedback
        for row in range(acf_log_reader.table_view.model().rowCount()):
            row_data = []
            for col in range(acf_log_reader.table_view.model().columnCount()):
                item = acf_log_reader.table_view.model().data(
                    acf_log_reader.table_view.model().index(row, col),
                    Qt.ItemDataRole.DisplayRole,
                )
                row_data.append(item if item else "")
            writer.writerow(row_data)

            if row % 50 == 0:  # Update progress every 50 rows
                acf_log_reader.status_bar.showMessage(
                    f"Exporting row {row + 1} of {acf_log_reader.table_view.model().rowCount()}..."
                )


def _write_csv_metadata(acf_log_reader: "AcfLogReader", writer: Any) -> None:
    """
    Write metadata headers to the CSV file.

    Args:
        acf_log_reader: The AcfLogReader instance.
        writer: The CSV writer object.
    """
    writer.writerow(["RimSort Workshop Items Export"])
    writer.writerow([f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([f"Total Items: {acf_log_reader.table_view.model().rowCount()}"])
    writer.writerow(
        [
            f"Source ACF: {acf_log_reader.steamcmd_interface.steamcmd_appworkshop_acf_path}"
        ]
    )
    writer.writerow([])


def _write_csv_headers(acf_log_reader: "AcfLogReader", writer: Any) -> None:
    """
    Write column headers and descriptions to the CSV file.

    Args:
        acf_log_reader: The AcfLogReader instance.
        writer: The CSV writer object.
    """
    headers = []
    descriptions = []
    for col in range(acf_log_reader.table_view.model().columnCount()):
        header = (
            acf_log_reader.table_model.headerData(
                col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
            )
            or ""
        )
        headers.append(header)
        descriptions.append(_get_column_description(acf_log_reader, col))
    writer.writerow(headers)
    writer.writerow(descriptions)
    writer.writerow([])


def _finalize_csv_export(acf_log_reader: "AcfLogReader", file_path: str) -> None:
    """
    Finalize the CSV export by updating status and showing success message.

    Args:
        acf_log_reader: The AcfLogReader instance.
        file_path: The path of the exported file.
    """
    acf_log_reader.status_bar.showMessage(
        f"Successfully exported {acf_log_reader.table_view.model().rowCount()} items to {file_path}"
    )
    show_information(
        title=acf_log_reader.tr("Export Success"),
        text=acf_log_reader.tr(
            "Successfully exported {count} items to {file_path}"
        ).format(
            count=acf_log_reader.table_view.model().rowCount(), file_path=file_path
        ),
    )


def _handle_csv_export_error(
    acf_log_reader: "AcfLogReader",
    message: str,
    title: str,
    details: Optional[str] = None,
) -> None:
    """
    Handle CSV export errors by logging, updating status, and showing dialog.

    Args:
        acf_log_reader: The AcfLogReader instance.
        message: The error message.
        title: The dialog title.
        details: Optional additional details.
    """
    acf_log_reader.status_bar.showMessage(message)
    logger.error(f"CSV Export error: {message}", exc_info=True)
    show_warning(
        title=acf_log_reader.tr(title),
        text=message,
        information=details,
    )


def _get_column_description(acf_log_reader: "AcfLogReader", col: int) -> str:
    """Get description for a table column."""
    try:
        column = acf_log_reader.TableColumn(col)
        return column.description
    except ValueError:
        return ""
