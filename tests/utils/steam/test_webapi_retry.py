"""
Tests for Steam Web API retry logic.
"""

import time
from unittest.mock import Mock, patch

import pytest
import requests

from app.utils.steam.webapi.retry import (
    SteamWebAPIRetryConfig,
    retry_steam_api_call,
    should_retry_exception,
    steam_api_request_with_retry,
)


class TestShouldRetryException:
    """Tests for should_retry_exception function."""

    def test_retry_on_503(self) -> None:
        """Test that 503 Service Unavailable is retryable."""
        config = SteamWebAPIRetryConfig()
        response = Mock()
        response.status_code = 503
        exc = requests.HTTPError(response=response)

        assert should_retry_exception(exc, config) is True

    def test_retry_on_429(self) -> None:
        """Test that 429 Too Many Requests is retryable."""
        config = SteamWebAPIRetryConfig()
        response = Mock()
        response.status_code = 429
        exc = requests.HTTPError(response=response)

        assert should_retry_exception(exc, config) is True

    def test_retry_on_500(self) -> None:
        """Test that 500 Internal Server Error is retryable."""
        config = SteamWebAPIRetryConfig()
        response = Mock()
        response.status_code = 500
        exc = requests.HTTPError(response=response)

        assert should_retry_exception(exc, config) is True

    def test_no_retry_on_400(self) -> None:
        """Test that 400 Bad Request is not retryable."""
        config = SteamWebAPIRetryConfig()
        response = Mock()
        response.status_code = 400
        exc = requests.HTTPError(response=response)

        assert should_retry_exception(exc, config) is False

    def test_no_retry_on_404(self) -> None:
        """Test that 404 Not Found is not retryable."""
        config = SteamWebAPIRetryConfig()
        response = Mock()
        response.status_code = 404
        exc = requests.HTTPError(response=response)

        assert should_retry_exception(exc, config) is False

    def test_retry_on_timeout_when_enabled(self) -> None:
        """Test that timeout errors are retryable when enabled."""
        config = SteamWebAPIRetryConfig(retry_on_timeout=True)
        exc = requests.Timeout()

        assert should_retry_exception(exc, config) is True

    def test_no_retry_on_timeout_when_disabled(self) -> None:
        """Test that timeout errors are not retryable when disabled."""
        config = SteamWebAPIRetryConfig(retry_on_timeout=False)
        exc = requests.Timeout()

        assert should_retry_exception(exc, config) is False

    def test_retry_on_connection_error_when_enabled(self) -> None:
        """Test that connection errors are retryable when enabled."""
        config = SteamWebAPIRetryConfig(retry_on_connection_error=True)
        exc = requests.ConnectionError()

        assert should_retry_exception(exc, config) is True

    def test_no_retry_on_connection_error_when_disabled(self) -> None:
        """Test that connection errors are not retryable when disabled."""
        config = SteamWebAPIRetryConfig(retry_on_connection_error=False)
        exc = requests.ConnectionError()

        assert should_retry_exception(exc, config) is False


class TestRetryDecorator:
    """Tests for retry_steam_api_call decorator."""

    def test_successful_call_no_retry(self) -> None:
        """Test that successful calls don't trigger retries."""
        config = SteamWebAPIRetryConfig(max_retries=3)
        call_count = 0

        @retry_steam_api_call(config=config)
        def successful_function() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_function()

        assert result == "success"
        assert call_count == 1  # Called only once, no retries

    def test_transient_503_with_successful_retry(self) -> None:
        """Test that 503 error triggers retry and succeeds on retry."""
        config = SteamWebAPIRetryConfig(max_retries=3, backoff_factor=0.01)
        call_count = 0

        @retry_steam_api_call(config=config)
        def flaky_function() -> str:
            nonlocal call_count
            call_count += 1

            if call_count <= 2:
                # Fail twice with 503
                response = Mock()
                response.status_code = 503
                raise requests.HTTPError(response=response)

            # Succeed on third attempt
            return "success"

        result = flaky_function()

        assert result == "success"
        assert call_count == 3  # Initial + 2 retries

    def test_max_retries_exceeded(self) -> None:
        """Test that function fails after max_retries are exhausted."""
        config = SteamWebAPIRetryConfig(max_retries=2, backoff_factor=0.01)
        call_count = 0

        @retry_steam_api_call(config=config)
        def always_failing_function() -> str:
            nonlocal call_count
            call_count += 1

            # Always fail with 503
            response = Mock()
            response.status_code = 503
            raise requests.HTTPError(response=response)

        with pytest.raises(requests.HTTPError):
            always_failing_function()

        assert call_count == 3  # Initial + 2 retries

    def test_non_retryable_400_error_fails_immediately(self) -> None:
        """Test that 400 error fails immediately without retries."""
        config = SteamWebAPIRetryConfig(max_retries=3, backoff_factor=0.01)
        call_count = 0

        @retry_steam_api_call(config=config)
        def bad_request_function() -> str:
            nonlocal call_count
            call_count += 1

            # Fail with 400 (client error)
            response = Mock()
            response.status_code = 400
            raise requests.HTTPError(response=response)

        with pytest.raises(requests.HTTPError):
            bad_request_function()

        assert call_count == 1  # No retries, failed immediately

    def test_timeout_retry(self) -> None:
        """Test that timeout errors trigger retries."""
        config = SteamWebAPIRetryConfig(
            max_retries=2, backoff_factor=0.01, retry_on_timeout=True
        )
        call_count = 0

        @retry_steam_api_call(config=config)
        def timeout_then_success() -> str:
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                raise requests.Timeout()

            return "success"

        result = timeout_then_success()

        assert result == "success"
        assert call_count == 2  # Initial + 1 retry

    def test_connection_error_retry(self) -> None:
        """Test that connection errors trigger retries."""
        config = SteamWebAPIRetryConfig(
            max_retries=2, backoff_factor=0.01, retry_on_connection_error=True
        )
        call_count = 0

        @retry_steam_api_call(config=config)
        def connection_error_then_success() -> str:
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                raise requests.ConnectionError()

            return "success"

        result = connection_error_then_success()

        assert result == "success"
        assert call_count == 2  # Initial + 1 retry

    def test_exponential_backoff_timing(self) -> None:
        """Test that exponential backoff delays are correct."""
        config = SteamWebAPIRetryConfig(max_retries=2, backoff_factor=0.1)
        call_times: list[float] = []

        @retry_steam_api_call(config=config)
        def failing_function() -> str:
            call_times.append(time.time())

            # Always fail with 503
            response = Mock()
            response.status_code = 503
            raise requests.HTTPError(response=response)

        with pytest.raises(requests.HTTPError):
            failing_function()

        assert len(call_times) == 3  # Initial + 2 retries

        # Check delays between attempts
        # First retry delay: 0.1 * (2^0) = 0.1s
        delay1 = call_times[1] - call_times[0]
        assert 0.08 < delay1 < 0.15  # Allow some timing variance

        # Second retry delay: 0.1 * (2^1) = 0.2s
        delay2 = call_times[2] - call_times[1]
        assert 0.18 < delay2 < 0.25  # Allow some timing variance


class TestSteamAPIRequestWithRetry:
    """Tests for steam_api_request_with_retry helper function."""

    @patch("app.utils.steam.webapi.retry.requests.post")
    def test_successful_post_request(self, mock_post: Mock) -> None:
        """Test successful POST request without retries."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        config = SteamWebAPIRetryConfig(max_retries=3)
        response = steam_api_request_with_retry(
            method="POST",
            url="https://api.steampowered.com/test",
            data={"key": "value"},
            config=config,
        )

        assert response.status_code == 200
        assert mock_post.call_count == 1

    @patch("app.utils.steam.webapi.retry.requests.post")
    def test_503_retry_then_success(self, mock_post: Mock) -> None:
        """Test that 503 error triggers retry and succeeds."""
        # First response: 503 error
        fail_response = Mock()
        fail_response.status_code = 503
        fail_response.raise_for_status.side_effect = requests.HTTPError(
            response=fail_response
        )

        # Second response: success
        success_response = Mock()
        success_response.status_code = 200
        success_response.raise_for_status.return_value = None

        mock_post.side_effect = [fail_response, success_response]

        config = SteamWebAPIRetryConfig(max_retries=3, backoff_factor=0.01)
        response = steam_api_request_with_retry(
            method="POST",
            url="https://api.steampowered.com/test",
            data={"test": "data"},
            config=config,
        )

        assert response.status_code == 200
        assert mock_post.call_count == 2  # Initial + 1 retry

    @patch("app.utils.steam.webapi.retry.requests.post")
    def test_400_fails_immediately(self, mock_post: Mock) -> None:
        """Test that 400 error fails immediately without retry."""
        fail_response = Mock()
        fail_response.status_code = 400
        fail_response.raise_for_status.side_effect = requests.HTTPError(
            response=fail_response
        )

        mock_post.return_value = fail_response

        config = SteamWebAPIRetryConfig(max_retries=3, backoff_factor=0.01)

        with pytest.raises(requests.HTTPError):
            steam_api_request_with_retry(
                method="POST",
                url="https://api.steampowered.com/test",
                data={"test": "data"},
                config=config,
            )

        assert mock_post.call_count == 1  # No retries

    @patch("app.utils.steam.webapi.retry.requests.get")
    def test_get_request(self, mock_get: Mock) -> None:
        """Test GET request method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        config = SteamWebAPIRetryConfig(max_retries=3)
        response = steam_api_request_with_retry(
            method="GET",
            url="https://api.steampowered.com/test",
            data={"param": "value"},
            config=config,
        )

        assert response.status_code == 200
        assert mock_get.call_count == 1

    def test_invalid_http_method(self) -> None:
        """Test that invalid HTTP method raises ValueError."""
        config = SteamWebAPIRetryConfig(max_retries=3)

        with pytest.raises(ValueError, match="Unsupported HTTP method"):
            steam_api_request_with_retry(
                method="DELETE",
                url="https://api.steampowered.com/test",
                data=None,
                config=config,
            )

    @patch("app.utils.steam.webapi.retry.requests.post")
    def test_uses_default_config_when_none(self, mock_post: Mock) -> None:
        """Test that default config is used when config=None."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        # Call without config parameter
        response = steam_api_request_with_retry(
            method="POST",
            url="https://api.steampowered.com/test",
            data={"key": "value"},
        )

        assert response.status_code == 200
        assert mock_post.call_count == 1
