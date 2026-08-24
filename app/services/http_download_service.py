"""Service for downloading database archives via HTTP in a background thread."""

from loguru import logger
from PySide6.QtCore import QObject, Signal

from app.utils.app_info import AppInfo
from app.utils.generic import extract_git_dir_name
from app.utils.http_downloader import (
    DatabaseDownloadTask,
    DownloadResult,
    HttpDownloadWorker,
)
from app.views.dialogue import show_warning


class HttpDownloadService(QObject):
    """Downloads database zip archives in a background QThread.

    Manages the lifecycle of a single ``HttpDownloadWorker`` and emits
    ``download_finished`` with a dict mapping repo names to ``DownloadResult``
    values.
    """

    download_finished = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self._worker: HttpDownloadWorker | None = None

    def start_download(self, url: str, repo_url: str, display_name: str) -> None:
        """Download a database archive in a background thread.

        :param url: Direct download URL (zip archive)
        :param repo_url: Repository URL used to derive the local folder name
        :param display_name: Human-readable name for status messages
        """
        if not url:
            show_warning(
                title="No URL configured",
                text=f"No URL is configured for {display_name}.",
                information="Please enter a URL in the text field.",
            )
            return

        repo_name = (
            extract_git_dir_name(repo_url)
            if repo_url
            else display_name.replace(" ", "-")
        )
        task = DatabaseDownloadTask(
            url=url,
            target_dir=AppInfo().databases_folder,
            repo_name=repo_name,
            display_name=display_name,
        )

        self._cleanup_worker()

        self._worker = HttpDownloadWorker([task])
        self._worker.download_finished.connect(self._on_worker_finished)
        self._worker.start()

    def _cleanup_worker(self) -> None:
        """Disconnect signals and shut down the existing worker if any."""
        if self._worker is not None:
            try:
                self._worker.download_finished.disconnect()
                self._worker.quit()
                self._worker.wait()
            except Exception as e:
                logger.debug(f"Error during HTTP worker cleanup: {e}")
            self._worker = None

    def _on_worker_finished(self, results: dict[str, DownloadResult]) -> None:
        """Handle worker completion, show summary, and clean up."""
        updated = [name for name, r in results.items() if r == DownloadResult.UPDATED]
        up_to_date = [
            name for name, r in results.items() if r == DownloadResult.UP_TO_DATE
        ]
        failed = [name for name, r in results.items() if r == DownloadResult.FAILED]

        if failed:
            show_warning(
                title="Download failed",
                text=f"Failed to download: {', '.join(failed)}",
                information="Please check your internet connection and the configured URL.",
            )
        elif updated:
            show_warning(
                title="Download complete",
                text=f"Downloaded successfully: {', '.join(updated)}",
            )
        elif up_to_date:
            show_warning(
                title="Already up to date",
                text=f"Already up to date: {', '.join(up_to_date)}",
            )

        if self._worker:
            try:
                self._worker.download_finished.disconnect()
            except Exception as e:
                logger.debug(f"Error during HTTP worker cleanup: {e}")
            self._worker = None

        self.download_finished.emit(results)
