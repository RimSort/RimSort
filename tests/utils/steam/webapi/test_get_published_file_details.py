from typing import Any
from unittest.mock import MagicMock, patch

import requests

from app.utils.steam.webapi.wrapper import (
    ISteamRemoteStorage_GetPublishedFileDetails,
)

PFIDS = ["111", "222", "333"]

VALID_RESPONSE_JSON = {
    "response": {
        "result": 1,
        "resultcount": 3,
        "publishedfiledetails": [
            {"publishedfileid": "111", "time_created": 100, "time_updated": 200},
            {"publishedfileid": "222", "time_created": 100, "time_updated": 300},
            {"publishedfileid": "333", "time_created": 100, "time_updated": 400},
        ],
    }
}


def _make_mock_response(
    status_code: int = 200, json_data: dict[str, Any] | None = None
) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = requests.exceptions.JSONDecodeError(
            "Expecting value", "", 0
        )
    return resp


class TestGetPublishedFileDetailsReturn:
    """Verify the function returns (metadata, failed_pfids, errors) tuple."""

    @patch("app.utils.steam.webapi.wrapper.http.post")
    def test_success_returns_three_tuple(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _make_mock_response(200, VALID_RESPONSE_JSON)
        result = ISteamRemoteStorage_GetPublishedFileDetails(PFIDS)
        assert isinstance(result, tuple)
        assert len(result) == 3
        metadata, failed_pfids, errors = result
        assert len(metadata) == 3
        assert failed_pfids == []
        assert errors == []

    @patch("app.utils.steam.webapi.wrapper.http.post")
    def test_empty_pfids_returns_empty_tuple(self, mock_post: MagicMock) -> None:
        metadata, failed_pfids, errors = ISteamRemoteStorage_GetPublishedFileDetails([])
        assert metadata == []
        assert failed_pfids == []
        assert errors == []
        mock_post.assert_not_called()


class TestGetPublishedFileDetailsRetry:
    """Verify per-chunk retry with exponential backoff."""

    @patch("app.utils.steam.webapi.wrapper.sleep")
    @patch("app.utils.steam.webapi.wrapper.http.post")
    def test_retries_on_timeout_then_succeeds(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """First attempt times out, second succeeds → full metadata, no failures."""
        mock_post.side_effect = [
            requests.exceptions.Timeout("Connection timed out"),
            _make_mock_response(200, VALID_RESPONSE_JSON),
        ]
        metadata, failed_pfids, errors = ISteamRemoteStorage_GetPublishedFileDetails(
            PFIDS
        )
        assert len(metadata) == 3
        assert failed_pfids == []
        assert errors == []
        assert mock_post.call_count == 2
        mock_sleep.assert_called_once_with(1)  # 2^0 = 1s backoff

    @patch("app.utils.steam.webapi.wrapper.sleep")
    @patch("app.utils.steam.webapi.wrapper.http.post")
    def test_retries_on_connection_error_then_succeeds(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_post.side_effect = [
            requests.exceptions.ConnectionError("Connection refused"),
            _make_mock_response(200, VALID_RESPONSE_JSON),
        ]
        metadata, failed_pfids, errors = ISteamRemoteStorage_GetPublishedFileDetails(
            PFIDS
        )
        assert len(metadata) == 3
        assert failed_pfids == []

    @patch("app.utils.steam.webapi.wrapper.sleep")
    @patch("app.utils.steam.webapi.wrapper.http.post")
    def test_retries_on_http_503_then_succeeds(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_post.side_effect = [
            _make_mock_response(503),
            _make_mock_response(200, VALID_RESPONSE_JSON),
        ]
        metadata, failed_pfids, errors = ISteamRemoteStorage_GetPublishedFileDetails(
            PFIDS
        )
        assert len(metadata) == 3
        assert failed_pfids == []

    @patch("app.utils.steam.webapi.wrapper.sleep")
    @patch("app.utils.steam.webapi.wrapper.http.post")
    def test_retries_on_http_429_then_succeeds(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_post.side_effect = [
            _make_mock_response(429),
            _make_mock_response(200, VALID_RESPONSE_JSON),
        ]
        metadata, failed_pfids, errors = ISteamRemoteStorage_GetPublishedFileDetails(
            PFIDS
        )
        assert len(metadata) == 3
        assert failed_pfids == []

    @patch("app.utils.steam.webapi.wrapper.sleep")
    @patch("app.utils.steam.webapi.wrapper.http.post")
    def test_exhausted_retries_records_failure(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ) -> None:
        """All 3 attempts fail → pfids tracked as failed with error message."""
        mock_post.side_effect = requests.exceptions.Timeout("timed out")
        metadata, failed_pfids, errors = ISteamRemoteStorage_GetPublishedFileDetails(
            PFIDS
        )
        assert metadata == []
        assert set(failed_pfids) == set(PFIDS)
        assert len(errors) == 1
        assert "3 attempts" in errors[0]
        assert mock_post.call_count == 3
        # Backoff: 1s then 2s
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)


class TestGetPublishedFileDetailsNonRetryable:
    """Verify non-retryable errors fail immediately without retry."""

    @patch("app.utils.steam.webapi.wrapper.sleep")
    @patch("app.utils.steam.webapi.wrapper.http.post")
    def test_json_decode_error_no_retry(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_post.return_value = _make_mock_response(200, json_data=None)
        metadata, failed_pfids, errors = ISteamRemoteStorage_GetPublishedFileDetails(
            PFIDS
        )
        assert metadata == []
        assert set(failed_pfids) == set(PFIDS)
        assert len(errors) == 1
        assert mock_post.call_count == 1  # no retry
        mock_sleep.assert_not_called()

    @patch("app.utils.steam.webapi.wrapper.sleep")
    @patch("app.utils.steam.webapi.wrapper.http.post")
    def test_http_400_no_retry(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_post.return_value = _make_mock_response(400)
        metadata, failed_pfids, errors = ISteamRemoteStorage_GetPublishedFileDetails(
            PFIDS
        )
        assert metadata == []
        assert set(failed_pfids) == set(PFIDS)
        assert mock_post.call_count == 1
        mock_sleep.assert_not_called()
