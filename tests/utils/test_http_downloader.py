import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from app.utils.http_downloader import (
    HTTP_CACHE_FILENAME,
    DownloadResult,
    HttpDatabaseDownloader,
)


def _create_fake_zip(
    tmp_path: Path, repo_name: str, branch: str, files: dict[str, str]
) -> bytes:
    """Create a zip archive mimicking GitHub's format: <repo>-<branch>/<files>."""
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, content in files.items():
            zf.writestr(f"{repo_name}-{branch}/{name}", content)
    return zip_path.read_bytes()


def _make_200_response(
    zip_bytes: bytes,
    etag: str = '"new_etag"',
    last_modified: str = "Wed, 21 May 2026 10:00:00 GMT",
) -> MagicMock:
    """Build a mock response for a 200 with streaming zip content."""
    headers_dict = {
        "ETag": etag,
        "Last-Modified": last_modified,
        "Content-Length": str(len(zip_bytes)),
    }
    response = MagicMock()
    response.status_code = 200
    # Use a real dict — it already has .get() and [] access
    response.headers = headers_dict
    response.iter_content = MagicMock(return_value=[zip_bytes])
    response.raise_for_status = MagicMock()
    return response


def _make_304_response() -> MagicMock:
    """Build a mock response for a 304 Not Modified."""
    response = MagicMock()
    response.status_code = 304
    response.raise_for_status = MagicMock()
    return response


class TestDownloadResult:
    def test_enum_members_exist(self) -> None:
        assert DownloadResult.UPDATED is not None
        assert DownloadResult.UP_TO_DATE is not None
        assert DownloadResult.FAILED is not None

    def test_enum_members_are_distinct(self) -> None:
        assert DownloadResult.UPDATED != DownloadResult.UP_TO_DATE
        assert DownloadResult.UPDATED != DownloadResult.FAILED
        assert DownloadResult.UP_TO_DATE != DownloadResult.FAILED


class TestHttpDatabaseDownloader304:
    """304 conditional response returns UP_TO_DATE."""

    @patch("app.utils.http_downloader.http.get")
    def test_returns_up_to_date_on_304(
        self, mock_get: MagicMock, tmp_path: Path
    ) -> None:
        mock_get.return_value = _make_304_response()

        # Pre-populate a repo dir with cache metadata so conditional headers are sent
        repo_dir = tmp_path / "TestRepo"
        repo_dir.mkdir()
        cache_file = repo_dir / HTTP_CACHE_FILENAME
        cache_file.write_text(
            json.dumps(
                {"etag": '"old_etag"', "last_modified": "Mon, 19 May 2026 08:00:00 GMT"}
            )
        )

        downloader = HttpDatabaseDownloader()
        result, error = downloader.download(
            "https://example.com/test.zip", tmp_path, "TestRepo"
        )

        assert result == DownloadResult.UP_TO_DATE
        assert error is None

    @patch("app.utils.http_downloader.http.get")
    def test_sends_conditional_headers_from_cache(
        self, mock_get: MagicMock, tmp_path: Path
    ) -> None:
        mock_get.return_value = _make_304_response()

        repo_dir = tmp_path / "TestRepo"
        repo_dir.mkdir()
        cache_file = repo_dir / HTTP_CACHE_FILENAME
        cache_file.write_text(
            json.dumps(
                {
                    "etag": '"cached_etag"',
                    "last_modified": "Mon, 19 May 2026 08:00:00 GMT",
                }
            )
        )

        downloader = HttpDatabaseDownloader()
        downloader.download("https://example.com/test.zip", tmp_path, "TestRepo")

        call_kwargs = mock_get.call_args
        sent_headers = call_kwargs.kwargs.get("headers", {})
        assert sent_headers.get("If-None-Match") == '"cached_etag"'
        assert sent_headers.get("If-Modified-Since") == "Mon, 19 May 2026 08:00:00 GMT"


class TestHttpDatabaseDownloader200:
    """200 response extracts zip and returns UPDATED."""

    @patch("app.utils.http_downloader.http.get")
    def test_returns_updated_on_200(self, mock_get: MagicMock, tmp_path: Path) -> None:
        zip_bytes = _create_fake_zip(
            tmp_path, "TestRepo", "main", {"data.json": '{"key": "value"}'}
        )
        mock_get.return_value = _make_200_response(zip_bytes)

        downloader = HttpDatabaseDownloader()
        result, error = downloader.download(
            "https://example.com/test.zip", tmp_path, "TestRepo"
        )

        assert result == DownloadResult.UPDATED
        assert error is None

    @patch("app.utils.http_downloader.http.get")
    def test_extracts_zip_contents(self, mock_get: MagicMock, tmp_path: Path) -> None:
        zip_bytes = _create_fake_zip(
            tmp_path, "TestRepo", "main", {"data.json": '{"key": "value"}'}
        )
        mock_get.return_value = _make_200_response(zip_bytes)

        downloader = HttpDatabaseDownloader()
        downloader.download("https://example.com/test.zip", tmp_path, "TestRepo")

        extracted = tmp_path / "TestRepo" / "data.json"
        assert extracted.exists()
        assert json.loads(extracted.read_text()) == {"key": "value"}

    @patch("app.utils.http_downloader.http.get")
    def test_writes_cache_metadata(self, mock_get: MagicMock, tmp_path: Path) -> None:
        zip_bytes = _create_fake_zip(tmp_path, "TestRepo", "main", {"data.json": "{}"})
        mock_get.return_value = _make_200_response(
            zip_bytes,
            etag='"fresh_etag"',
            last_modified="Thu, 22 May 2026 12:00:00 GMT",
        )

        downloader = HttpDatabaseDownloader()
        downloader.download("https://example.com/test.zip", tmp_path, "TestRepo")

        cache_file = tmp_path / "TestRepo" / HTTP_CACHE_FILENAME
        assert cache_file.exists()
        cache = json.loads(cache_file.read_text())
        assert cache["etag"] == '"fresh_etag"'
        assert cache["last_modified"] == "Thu, 22 May 2026 12:00:00 GMT"
        assert "downloaded_at" in cache

    @patch("app.utils.http_downloader.http.get")
    def test_replaces_existing_repo_dir(
        self, mock_get: MagicMock, tmp_path: Path
    ) -> None:
        """Updating should replace the existing dir without leaving stale files."""
        repo_dir = tmp_path / "TestRepo"
        repo_dir.mkdir()
        (repo_dir / "old_file.txt").write_text("stale")

        zip_bytes = _create_fake_zip(
            tmp_path, "TestRepo", "main", {"new_file.txt": "fresh"}
        )
        mock_get.return_value = _make_200_response(zip_bytes)

        downloader = HttpDatabaseDownloader()
        downloader.download("https://example.com/test.zip", tmp_path, "TestRepo")

        assert (tmp_path / "TestRepo" / "new_file.txt").read_text() == "fresh"
        assert not (tmp_path / "TestRepo" / "old_file.txt").exists()


class TestHttpDatabaseDownloaderFailure:
    """Network error returns FAILED and preserves existing files."""

    @patch("app.utils.http_downloader.http.get")
    def test_network_error_returns_failed(
        self, mock_get: MagicMock, tmp_path: Path
    ) -> None:
        mock_get.side_effect = requests.ConnectionError("Connection refused")

        downloader = HttpDatabaseDownloader()
        result, error = downloader.download(
            "https://example.com/test.zip", tmp_path, "TestRepo"
        )

        assert result == DownloadResult.FAILED
        assert error is not None
        assert "TestRepo" in error

    @patch("app.utils.http_downloader.http.get")
    def test_network_error_preserves_existing_files(
        self, mock_get: MagicMock, tmp_path: Path
    ) -> None:
        repo_dir = tmp_path / "TestRepo"
        repo_dir.mkdir()
        existing_file = repo_dir / "data.json"
        existing_file.write_text('{"existing": true}')

        mock_get.side_effect = requests.ConnectionError("Connection refused")

        downloader = HttpDatabaseDownloader()
        downloader.download("https://example.com/test.zip", tmp_path, "TestRepo")

        assert existing_file.exists()
        assert json.loads(existing_file.read_text()) == {"existing": True}

    @patch("app.utils.http_downloader.http.get")
    def test_http_error_returns_failed(
        self, mock_get: MagicMock, tmp_path: Path
    ) -> None:
        response = MagicMock()
        response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = response

        downloader = HttpDatabaseDownloader()
        result, error = downloader.download(
            "https://example.com/test.zip", tmp_path, "TestRepo"
        )

        assert result == DownloadResult.FAILED
        assert error is not None

    @patch("app.utils.http_downloader.http.get")
    def test_bad_zip_returns_failed_preserves_existing(
        self, mock_get: MagicMock, tmp_path: Path
    ) -> None:
        repo_dir = tmp_path / "TestRepo"
        repo_dir.mkdir()
        existing_file = repo_dir / "data.json"
        existing_file.write_text('{"existing": true}')

        response = MagicMock()
        response.status_code = 200
        response.headers = {"Content-Length": "10"}
        response.iter_content = MagicMock(return_value=[b"not a zip file"])
        response.raise_for_status = MagicMock()
        mock_get.return_value = response

        downloader = HttpDatabaseDownloader()
        result, error = downloader.download(
            "https://example.com/test.zip", tmp_path, "TestRepo"
        )

        assert result == DownloadResult.FAILED
        assert error is not None
        # Existing files must survive
        assert existing_file.exists()
        assert json.loads(existing_file.read_text()) == {"existing": True}


class TestHttpDatabaseDownloaderProgress:
    """Progress callback is called during download."""

    @patch("app.utils.http_downloader.http.get")
    def test_progress_callback_called(
        self, mock_get: MagicMock, tmp_path: Path
    ) -> None:
        zip_bytes = _create_fake_zip(tmp_path, "TestRepo", "main", {"data.json": "{}"})
        mock_get.return_value = _make_200_response(zip_bytes)

        progress_calls: list[tuple[int, int | None]] = []

        def on_progress(downloaded: int, total: int | None) -> None:
            progress_calls.append((downloaded, total))

        downloader = HttpDatabaseDownloader()
        downloader.download(
            "https://example.com/test.zip",
            tmp_path,
            "TestRepo",
            progress_callback=on_progress,
        )

        assert len(progress_calls) > 0
        last_downloaded, last_total = progress_calls[-1]
        assert last_downloaded == len(zip_bytes)
        assert last_total == len(zip_bytes)

    @patch("app.utils.http_downloader.http.get")
    def test_no_callback_does_not_error(
        self, mock_get: MagicMock, tmp_path: Path
    ) -> None:
        zip_bytes = _create_fake_zip(tmp_path, "TestRepo", "main", {"data.json": "{}"})
        mock_get.return_value = _make_200_response(zip_bytes)

        downloader = HttpDatabaseDownloader()
        result, error = downloader.download(
            "https://example.com/test.zip", tmp_path, "TestRepo"
        )

        assert result == DownloadResult.UPDATED
        assert error is None


class TestHttpDatabaseDownloaderNoCache:
    """When no cache exists, no conditional headers are sent."""

    @patch("app.utils.http_downloader.http.get")
    def test_no_conditional_headers_without_cache(
        self, mock_get: MagicMock, tmp_path: Path
    ) -> None:
        zip_bytes = _create_fake_zip(tmp_path, "TestRepo", "main", {"data.json": "{}"})
        mock_get.return_value = _make_200_response(zip_bytes)

        downloader = HttpDatabaseDownloader()
        downloader.download("https://example.com/test.zip", tmp_path, "TestRepo")

        call_kwargs = mock_get.call_args
        sent_headers = call_kwargs.kwargs.get("headers", {})
        assert "If-None-Match" not in sent_headers
        assert "If-Modified-Since" not in sent_headers
