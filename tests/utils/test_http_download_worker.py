from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.utils.http_downloader import (
    DatabaseDownloadTask,
    DownloadResult,
    HttpDownloadWorker,
)


class TestDatabaseDownloadTask:
    def test_dataclass_fields(self) -> None:
        task = DatabaseDownloadTask(
            url="https://example.com/archive.zip",
            target_dir=Path("/tmp/dbs"),
            repo_name="TestRepo",
            display_name="Test Repository",
        )
        assert task.url == "https://example.com/archive.zip"
        assert task.target_dir == Path("/tmp/dbs")
        assert task.repo_name == "TestRepo"
        assert task.display_name == "Test Repository"


@pytest.fixture
def two_task_batch() -> list[DatabaseDownloadTask]:
    return [
        DatabaseDownloadTask(
            url="https://example.com/a.zip",
            target_dir=Path("/tmp"),
            repo_name="RepoA",
            display_name="Repo A",
        ),
        DatabaseDownloadTask(
            url="https://example.com/b.zip",
            target_dir=Path("/tmp"),
            repo_name="RepoB",
            display_name="Repo B",
        ),
    ]


class TestHttpDownloadWorker:
    @patch("app.utils.http_downloader.HttpDatabaseDownloader.download")
    def test_worker_processes_all_tasks(
        self, mock_download: MagicMock, two_task_batch: list[DatabaseDownloadTask]
    ) -> None:
        mock_download.return_value = (DownloadResult.UPDATED, None)

        worker = HttpDownloadWorker(two_task_batch)
        results: list[dict[str, DownloadResult]] = []
        worker.download_finished.connect(lambda r: results.append(r))
        worker.run()

        assert mock_download.call_count == 2
        assert len(results) == 1
        assert results[0]["RepoA"] == DownloadResult.UPDATED
        assert results[0]["RepoB"] == DownloadResult.UPDATED

    @patch("app.utils.http_downloader.HttpDatabaseDownloader.download")
    def test_single_failure_does_not_abort_batch(
        self, mock_download: MagicMock, two_task_batch: list[DatabaseDownloadTask]
    ) -> None:
        mock_download.side_effect = [
            (DownloadResult.FAILED, "timeout"),
            (DownloadResult.UPDATED, None),
        ]

        worker = HttpDownloadWorker(two_task_batch)
        results: list[dict[str, DownloadResult]] = []
        worker.download_finished.connect(lambda r: results.append(r))
        worker.run()

        assert mock_download.call_count == 2
        assert results[0]["RepoA"] == DownloadResult.FAILED
        assert results[0]["RepoB"] == DownloadResult.UPDATED

    @patch("app.utils.http_downloader.HttpDatabaseDownloader.download")
    def test_progress_signals_emitted(self, mock_download: MagicMock) -> None:
        mock_download.return_value = (DownloadResult.UP_TO_DATE, None)

        tasks = [
            DatabaseDownloadTask(
                url="https://example.com/a.zip",
                target_dir=Path("/tmp"),
                repo_name="RepoA",
                display_name="Repo A",
            ),
        ]

        worker = HttpDownloadWorker(tasks)
        progress_messages: list[str] = []
        worker.progress.connect(lambda msg: progress_messages.append(msg))
        worker.run()

        assert len(progress_messages) >= 1
