"""Tests for GitHub rate-limit handling in the update check (#2337).

The updater used to call the GitHub API unauthenticated and report every
failure as a connection error, so an exhausted rate limit (60 requests/hour
per IP) looked like a broken network with no remedy offered.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.utils import update_utils
from app.utils.update_utils import (
    is_github_rate_limit_error,
    rate_limit_reset_clock,
)

_RATE_LIMIT_BODY = (
    '{"message": "API rate limit exceeded for 203.0.113.5. '
    'Authenticated requests get a higher rate limit."}'
)


def _http_error(status: int, body: str = "") -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    response._content = body.encode()
    error = requests.HTTPError(
        f"{status} Client Error: for url: https://api.github.com"
    )
    error.response = response
    return error


class TestIsGithubRateLimitError:
    def test_403_with_rate_limit_body(self) -> None:
        assert is_github_rate_limit_error(_http_error(403, _RATE_LIMIT_BODY)) is True

    def test_429_is_always_a_rate_limit(self) -> None:
        assert is_github_rate_limit_error(_http_error(429)) is True

    def test_secondary_rate_limit(self) -> None:
        body = '{"message": "You have exceeded a secondary rate limit"}'
        assert is_github_rate_limit_error(_http_error(403, body)) is True

    def test_unrelated_403_is_not_a_rate_limit(self) -> None:
        body = '{"message": "Repository access blocked"}'
        assert is_github_rate_limit_error(_http_error(403, body)) is False

    def test_403_without_body_is_not_a_rate_limit(self) -> None:
        assert is_github_rate_limit_error(_http_error(403)) is False

    def test_other_status_codes_are_not_rate_limits(self) -> None:
        assert is_github_rate_limit_error(_http_error(404)) is False
        assert is_github_rate_limit_error(_http_error(500)) is False

    def test_error_without_response(self) -> None:
        assert is_github_rate_limit_error(requests.HTTPError("boom")) is False


class TestRateLimitResetClock:
    def test_formats_reset_header_as_clock_time(self) -> None:
        response = MagicMock()
        response.headers = {"X-RateLimit-Reset": "1767225600"}

        clock = rate_limit_reset_clock(response)

        assert len(clock) == 5 and clock[2] == ":"

    def test_missing_header_returns_empty(self) -> None:
        response = MagicMock()
        response.headers = {}

        assert rate_limit_reset_clock(response) == ""

    def test_none_response_returns_empty(self) -> None:
        assert rate_limit_reset_clock(None) == ""

    def test_unparseable_header_returns_empty(self) -> None:
        response = MagicMock()
        response.headers = {"X-RateLimit-Reset": "not-a-number"}

        assert rate_limit_reset_clock(response) == ""

    def test_response_without_headers_returns_empty(self) -> None:
        assert rate_limit_reset_clock(object()) == ""


class TestUpdateCheckUsesToken:
    @pytest.fixture(autouse=True)
    def _identity_translate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Keep source strings untranslated without a QApplication."""
        monkeypatch.setattr(
            update_utils.UpdateManager,
            "tr",
            lambda _self, text: text,
            raising=False,
        )

    def _manager(self, token: str) -> Any:
        manager = update_utils.UpdateManager.__new__(update_utils.UpdateManager)
        manager.settings = MagicMock()
        manager.settings.github_token = token
        return manager

    def _response(self) -> Any:
        response = MagicMock()
        response.json.return_value = {"tag_name": "v1.0.0", "assets": []}
        response.raise_for_status.return_value = None
        return response

    def test_token_is_sent_as_bearer(self) -> None:
        manager = self._manager("ghp_secret")

        with (
            patch.object(
                update_utils.http, "get", return_value=self._response()
            ) as get,
            patch.object(update_utils.dialogue, "show_warning"),
        ):
            manager._get_latest_release_info()

        headers = get.call_args.kwargs.get("headers", {})
        assert headers == {"Authorization": "Bearer ghp_secret"}

    def test_no_token_means_no_auth_header(self) -> None:
        manager = self._manager("")

        with (
            patch.object(
                update_utils.http, "get", return_value=self._response()
            ) as get,
            patch.object(update_utils.dialogue, "show_warning"),
        ):
            manager._get_latest_release_info()

        assert get.call_args.kwargs.get("headers", {}) == {}

    def test_rate_limit_shows_actionable_dialog(self) -> None:
        manager = self._manager("")
        response = MagicMock()
        response.json.return_value = {}
        response.raise_for_status.side_effect = _http_error(403, _RATE_LIMIT_BODY)
        response.headers = {}

        with (
            patch.object(update_utils.http, "get", return_value=response),
            patch.object(update_utils.dialogue, "show_warning") as warn,
        ):
            assert manager._get_latest_release_info() is None

        warn.assert_called_once()
        kwargs = warn.call_args.kwargs
        assert kwargs["text"] == "GitHub's API rate limit has been reached"
        assert "Settings - Advanced" in kwargs["information"]

    def test_other_errors_keep_generic_message(self) -> None:
        manager = self._manager("")
        response = MagicMock()
        response.raise_for_status.side_effect = _http_error(404)

        with (
            patch.object(update_utils.http, "get", return_value=response),
            patch.object(update_utils.dialogue, "show_warning") as warn,
        ):
            assert manager._get_latest_release_info() is None

        kwargs = warn.call_args.kwargs
        assert "Failed to connect to GitHub API" in kwargs["text"]
        assert kwargs["title"] == update_utils.ERR_API_CONNECTION_TITLE
