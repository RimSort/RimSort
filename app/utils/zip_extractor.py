"""ZIP file operations module for extraction, validation, and backup creation.

This module provides:
- ZipExtractThread: Threaded ZIP extraction with progress reporting
- Utility functions: validate_zip_integrity, get_zip_contents, create_zip_backup
"""

import os
import shutil
import time
from pathlib import Path
from typing import Callable, Optional
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from loguru import logger
from PySide6.QtCore import QThread, Signal

# Export for use in other modules
__all__ = [
    "ZipExtractThread",
    "validate_zip_integrity",
    "get_zip_contents",
    "create_zip_backup",
    "BadZipFile",
]


# ============================================================================
# ZIP Extraction Thread
# ============================================================================


class ZipExtractThread(QThread):
    """Extract ZIP files in a separate thread with progress reporting.

    Signals:
        progress: Emitted with (percentage, message) during extraction
        finished: Emitted when extraction completes with (success, message)
    """

    progress = Signal(int, str)  # percentage, message
    finished = Signal(bool, str)

    def __init__(
        self,
        zip_path: str,
        target_path: str,
        overwrite_all: bool = True,
        delete: bool = False,
    ) -> None:
        """Initialize the extraction thread.

        Args:
            zip_path: Path to ZIP file to extract
            target_path: Destination directory for extraction
            overwrite_all: Whether to overwrite existing files (default: True)
            delete: Whether to delete ZIP file after extraction (default: False)
        """
        super().__init__()
        self.zip_path = zip_path
        self.target_path = target_path
        self.overwrite_all = overwrite_all
        self.delete = delete
        self._should_abort = False

    def run(self) -> None:
        """Extract ZIP file with progress reporting.

        Emits progress signals during extraction and finished signal when complete.
        If delete=True, removes ZIP file after successful extraction.
        """
        start = time.perf_counter()

        try:
            with ZipFile(self.zip_path) as zipobj:
                file_list = zipobj.infolist()
                total_files = len(file_list)
                update_interval = max(1, total_files // 100)

                for i, zip_info in enumerate(file_list):
                    if self._should_abort:
                        self.finished.emit(False, "Operation aborted")
                        return

                    filename = zip_info.filename
                    dst = os.path.join(self.target_path, filename)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)

                    if zip_info.is_dir():
                        os.makedirs(dst, exist_ok=True)
                    else:
                        if os.path.exists(dst) and not self.overwrite_all:
                            continue

                        with zipobj.open(zip_info) as src, open(dst, "wb") as out_file:
                            shutil.copyfileobj(src, out_file)

                    if i % update_interval == 0 or i == total_files - 1:
                        percent = int((i + 1) / total_files * 100)
                        message = f"Extracting: {i + 1} / {total_files} files"
                        self.progress.emit(percent, message)

            end = time.perf_counter()
            elapsed = end - start
            self.finished.emit(
                True,
                f"{self.zip_path} → {self.target_path}\nTime elapsed: {elapsed:.2f} seconds",
            )

            if self.delete:
                os.remove(self.zip_path)

        except Exception as e:
            logger.error(f"ZIP extraction failed: {e}")
            self.finished.emit(False, f"Extraction error: {str(e)}")

    def stop(self) -> None:
        """Signal the thread to abort extraction on next iteration."""
        self._should_abort = True


# ============================================================================
# ZIP Utility Functions
# ============================================================================


def validate_zip_integrity(zip_path: str | Path) -> tuple[bool, str]:
    """Validate ZIP file integrity.

    Tests the ZIP file for corruption and checks if it's a valid archive.

    Args:
        zip_path: Path to ZIP file to validate

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.

    Example:
        >>> is_valid, error = validate_zip_integrity("archive.zip")
        >>> if not is_valid:
        ...     print(f"ZIP validation failed: {error}")
    """
    try:
        with ZipFile(zip_path) as zipobj:
            corruption_info = zipobj.testzip()
            if corruption_info is not None:
                return False, f"ZIP file corrupted at: {corruption_info}"
        logger.info(f"ZIP file validated successfully: {zip_path}")
        return True, ""
    except BadZipFile as e:
        logger.error(f"Invalid ZIP file: {e}")
        return False, f"Invalid ZIP file: {str(e)}"
    except Exception as e:
        logger.error(f"Failed to validate ZIP: {e}")
        return False, f"Error validating ZIP: {str(e)}"


def get_zip_contents(zip_path: str | Path) -> list[str]:
    """Get list of all files/directories in a ZIP archive.

    Args:
        zip_path: Path to ZIP file

    Returns:
        List of file/directory names in archive (with forward slashes)

    Raises:
        BadZipFile: If ZIP file is invalid or cannot be read

    Example:
        >>> contents = get_zip_contents("archive.zip")
        >>> print(f"Archive contains {len(contents)} items")
    """
    try:
        with ZipFile(zip_path) as zipobj:
            return zipobj.namelist()
    except BadZipFile:
        raise
    except Exception as e:
        logger.error(f"Failed to read ZIP contents: {e}")
        raise BadZipFile(f"Failed to read ZIP contents: {str(e)}") from e


def create_zip_backup(
    source_dir: str | Path,
    backup_path: str | Path,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> None:
    """Create a compressed ZIP backup of a directory.

    Recursively archives all files in source_dir to a single ZIP file
    with compression. Empty directories are not included.

    Args:
        source_dir: Source directory to backup
        backup_path: Destination ZIP file path
        progress_callback: Optional callback function(current, total) for progress updates

    Raises:
        OSError: If source directory doesn't exist or backup can't be written
        Exception: If compression/archiving fails

    Example:
        >>> create_zip_backup("/app/data", "/backups/data.zip")
    """
    source_path = Path(source_dir)
    backup_file = Path(backup_path)

    if not source_path.exists():
        logger.error(f"Source directory does not exist: {source_path}")
        raise OSError(f"Source directory does not exist: {source_path}")

    # Ensure backup directory exists
    backup_file.parent.mkdir(parents=True, exist_ok=True)

    # First pass: collect all files and count total for progress reporting
    logger.info(f"Scanning {source_path} for files to backup...")
    file_list = []
    for root, dirs, files in os.walk(source_path):
        for file in files:
            file_path = Path(root) / file
            arcname = file_path.relative_to(source_path)
            file_list.append((file_path, arcname))

    total_files = len(file_list)
    logger.info(f"Found {total_files} files to backup")

    # Second pass: write files to ZIP with progress updates
    with ZipFile(backup_file, "w", ZIP_DEFLATED) as zipf:
        for current_file, (file_path, arcname) in enumerate(file_list, 1):
            try:
                zipf.write(file_path, arcname)
                # Update progress
                if progress_callback:
                    progress_callback(current_file, total_files)
            except Exception as e:
                logger.error(f"Failed to add {file_path} to backup: {e}")

    logger.info(f"Created backup: {backup_file}")
