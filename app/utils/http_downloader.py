"""HTTP-based database downloader with conditional requests and zip extraction.

Downloads zip archives from HTTP URLs (e.g. GitHub release/archive endpoints),
extracts them to a target directory, and caches ETag/Last-Modified headers for
conditional GET requests on subsequent runs.
"""

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from typing import Callable

import requests
from loguru import logger
from PySide6.QtCore import QThread, Signal

from app.utils import http

DOWNLOAD_CHUNK_SIZE = 131072  # 128KB
HTTP_CACHE_FILENAME = ".http_cache.json"


class DownloadResult(Enum):
    """Outcome of an HTTP database download attempt."""

    UPDATED = auto()
    UP_TO_DATE = auto()
    FAILED = auto()


class HttpDatabaseDownloader:
    """Downloads and extracts zip archives with conditional HTTP caching.

    Stores ETag/Last-Modified metadata in a sidecar JSON file so subsequent
    downloads can use conditional GET headers (``If-None-Match`` /
    ``If-Modified-Since``) to avoid re-downloading unchanged content.

    GitHub zip archives extract to ``<repo>-<branch>/`` — the extractor
    automatically unwraps this single top-level directory.
    """

    def _read_cache_metadata(self, repo_dir: Path) -> dict[str, str]:
        """Read cached ETag/Last-Modified from the sidecar file.

        :param repo_dir: Directory containing the cache sidecar
        :return: Cached metadata dict, or empty dict if missing/corrupt
        """
        cache_file = repo_dir / HTTP_CACHE_FILENAME
        if not cache_file.exists():
            return {}
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Could not read HTTP cache metadata: {e}")
            return {}

    def _write_cache_metadata(
        self, repo_dir: Path, etag: str | None, last_modified: str | None
    ) -> None:
        """Write ETag/Last-Modified to the sidecar cache file.

        :param repo_dir: Directory to write the cache sidecar into
        :param etag: ETag header value from the server response
        :param last_modified: Last-Modified header value from the server response
        """
        cache_data: dict[str, str] = {
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }
        if etag:
            cache_data["etag"] = etag
        if last_modified:
            cache_data["last_modified"] = last_modified
        cache_file = repo_dir / HTTP_CACHE_FILENAME
        cache_file.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")

    def _build_conditional_headers(self, cache: dict[str, str]) -> dict[str, str]:
        """Build conditional GET headers from cached metadata.

        :param cache: Previously cached metadata dict
        :return: Headers dict with If-None-Match/If-Modified-Since as available
        """
        headers: dict[str, str] = {}
        if "etag" in cache:
            headers["If-None-Match"] = cache["etag"]
        if "last_modified" in cache:
            headers["If-Modified-Since"] = cache["last_modified"]
        return headers

    def _extract_zip_to_dir(
        self, zip_path: Path, target_dir: Path, repo_name: str
    ) -> Path:
        """Extract a zip archive into the target directory.

        GitHub zips contain a single top-level ``<repo>-<branch>/`` directory.
        This method detects that pattern and unwraps it so extracted files land
        directly in ``target_dir/repo_name/``.

        Replacement is atomic-ish: the old directory is renamed to ``.bak``,
        the new one is moved in, then the backup is deleted.

        :param zip_path: Path to the downloaded zip file
        :param target_dir: Parent directory for extraction
        :param repo_name: Name of the subdirectory to create/replace
        :return: Path to the final extracted directory
        """
        extracted_dir = target_dir / repo_name
        temp_extract = target_dir / f".{repo_name}_extracting"

        if temp_extract.exists():
            shutil.rmtree(temp_extract)
        temp_extract.mkdir(parents=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_extract)

        # GitHub zips extract to <repo>-<branch>/ — unwrap if single top-level dir
        children = list(temp_extract.iterdir())
        final_dir = target_dir / f".{repo_name}_new"
        if final_dir.exists():
            shutil.rmtree(final_dir)

        if len(children) == 1 and children[0].is_dir():
            children[0].rename(final_dir)
            shutil.rmtree(temp_extract)
        else:
            temp_extract.rename(final_dir)

        # Atomic-ish replacement: old -> .bak, new -> target, delete .bak
        backup_dir = target_dir / f"{repo_name}.bak"
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        if extracted_dir.exists():
            extracted_dir.rename(backup_dir)
        final_dir.rename(extracted_dir)
        if backup_dir.exists():
            try:
                shutil.rmtree(backup_dir)
            except OSError as e:
                logger.warning(f"Failed to remove backup dir {backup_dir}: {e}")

        return extracted_dir

    def download(
        self,
        url: str,
        target_dir: Path,
        repo_name: str,
        progress_callback: Callable[[int, int | None], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> tuple[DownloadResult, str | None]:
        """Download and extract a zip archive from a URL.

        Uses conditional GET headers when cached metadata exists. On a 304
        response the existing files are left untouched. On a 200 response the
        zip is streamed to a temp file, extracted, and the target directory is
        replaced atomically.

        :param url: URL of the zip archive to download
        :param target_dir: Parent directory where ``repo_name/`` will be created
        :param repo_name: Subdirectory name for the extracted content
        :param progress_callback: Optional ``(downloaded_bytes, total_bytes)`` callback
        :param cancel_check: Optional callable returning True to abort the download
        :return: Tuple of (result, error_message_or_none)
        """
        repo_dir = target_dir / repo_name
        cache = self._read_cache_metadata(repo_dir) if repo_dir.exists() else {}
        headers = self._build_conditional_headers(cache)

        try:
            response = http.get(url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()

            if response.status_code == 304:
                logger.info(f"{repo_name}: already up to date (304)")
                return DownloadResult.UP_TO_DATE, None

            total_size_str = response.headers.get("Content-Length")
            total_size = int(total_size_str) if total_size_str else None

            target_dir.mkdir(parents=True, exist_ok=True)
            temp_fd = tempfile.NamedTemporaryFile(
                dir=str(target_dir), suffix=".zip", delete=False
            )
            temp_path = Path(temp_fd.name)

            try:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    if cancel_check and cancel_check():
                        raise _DownloadCancelled()
                    if chunk:
                        temp_fd.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total_size)
                temp_fd.close()

                extracted = self._extract_zip_to_dir(temp_path, target_dir, repo_name)

                new_etag = response.headers.get("ETag")
                new_last_modified = response.headers.get("Last-Modified")
                self._write_cache_metadata(extracted, new_etag, new_last_modified)

                logger.info(f"{repo_name}: downloaded and extracted successfully")
                return DownloadResult.UPDATED, None

            finally:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass

        except _DownloadCancelled:
            logger.info(f"{repo_name}: download cancelled")
            return DownloadResult.FAILED, "Download cancelled"
        except requests.RequestException as e:
            error_msg = f"Failed to download {repo_name}: {e}"
            logger.warning(error_msg)
            return DownloadResult.FAILED, error_msg
        except (zipfile.BadZipFile, OSError) as e:
            error_msg = f"Failed to extract {repo_name}: {e}"
            logger.warning(error_msg)
            return DownloadResult.FAILED, error_msg


@dataclass
class DatabaseDownloadTask:
    """Describes a single database archive to download and extract."""

    url: str
    target_dir: Path
    repo_name: str
    display_name: str


class _DownloadCancelled(Exception):
    """Raised internally when a download is cancelled via the worker's cancel flag."""


class HttpDownloadWorker(QThread):
    progress = Signal(str)
    download_finished = Signal(dict)

    def __init__(self, tasks: list[DatabaseDownloadTask]) -> None:
        super().__init__()
        self._tasks = tasks
        self._downloader = HttpDatabaseDownloader()
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation of the current download batch."""
        self._cancelled = True

    def run(self) -> None:
        results: dict[str, DownloadResult] = {}

        for task in self._tasks:
            if self._cancelled:
                results[task.repo_name] = DownloadResult.FAILED
                continue

            self.progress.emit(f"Downloading {task.display_name}...")
            result, error_msg = self._downloader.download(
                url=task.url,
                target_dir=task.target_dir,
                repo_name=task.repo_name,
                progress_callback=None,
                cancel_check=lambda: self._cancelled,
            )
            results[task.repo_name] = result

            if result == DownloadResult.UPDATED:
                self.progress.emit(f"{task.display_name}: updated")
            elif result == DownloadResult.UP_TO_DATE:
                self.progress.emit(f"{task.display_name}: already up to date")
            elif result == DownloadResult.FAILED:
                self.progress.emit(f"{task.display_name}: failed — {error_msg}")

        self.download_finished.emit(results)
