"""
Steam Web API retry logic with exponential backoff.

This module provides retry functionality for Steam Web API calls to handle
transient failures like 503 Service Unavailable, timeouts, and connection errors.
"""

import time
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, TypeVar

import requests
from loguru import logger

# Type variable for generic decorator
F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class SteamWebAPIRetryConfig:
    """
    Configuration for Steam Web API retry behavior.

    :param max_retries: Maximum number of retry attempts (default: 3)
    :param backoff_factor: Exponential backoff multiplier (default: 1.0).
                          Delay calculated as: backoff_factor * (2 ** attempt)
    :param retry_on_timeout: Whether to retry on timeout errors (default: True)
    :param retry_on_connection_error: Whether to retry on connection errors (default: True)
    """

    max_retries: int = 3
    backoff_factor: float = 1.0
    retry_on_timeout: bool = True
    retry_on_connection_error: bool = True


def should_retry_exception(exc: Exception, config: SteamWebAPIRetryConfig) -> bool:
    """
    Determine if an exception warrants a retry attempt.

    Retryable errors include:
    - HTTP 429 (Too Many Requests - rate limiting)
    - HTTP 500, 502, 503, 504 (server errors)
    - Timeout errors (if enabled in config)
    - Connection errors (if enabled in config)

    Non-retryable errors include:
    - HTTP 4xx (except 429) - client errors won't be fixed by retrying
    - Parsing errors
    - Authentication errors

    :param exc: The exception to evaluate
    :param config: Retry configuration
    :return: True if the error should be retried, False otherwise
    """
    # Handle HTTP errors with status codes
    if isinstance(exc, requests.HTTPError):
        if exc.response is not None:
            status_code = exc.response.status_code
            # Retry on server errors and rate limiting
            if status_code in {429, 500, 502, 503, 504}:
                return True
            # Don't retry on client errors (4xx except 429)
            if 400 <= status_code < 500:
                return False
        # If we can't determine status code, don't retry
        return False

    # Handle timeout errors
    if isinstance(exc, requests.Timeout):
        return config.retry_on_timeout

    # Handle connection errors
    if isinstance(exc, requests.ConnectionError):
        return config.retry_on_connection_error

    # Don't retry other exception types (parsing errors, etc.)
    return False


def retry_steam_api_call(config: SteamWebAPIRetryConfig) -> Callable[[F], F]:
    """
    Decorator to add retry logic with exponential backoff to a function.

    Usage:
        @retry_steam_api_call(config=SteamWebAPIRetryConfig(max_retries=3))
        def my_api_call():
            return requests.get("https://api.steampowered.com/...")

    :param config: Retry configuration
    :return: Decorated function with retry logic
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None

            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # Check if we should retry this exception
                    if not should_retry_exception(e, config):
                        logger.debug(
                            f"{func.__name__} failed with non-retryable error: "
                            f"{e.__class__.__name__}"
                        )
                        raise

                    # Check if we've exhausted retries
                    if attempt >= config.max_retries:
                        logger.warning(
                            f"{func.__name__} failed after {config.max_retries} retry attempts: "
                            f"{e.__class__.__name__}"
                        )
                        raise

                    # Calculate backoff delay
                    delay = config.backoff_factor * (2**attempt)
                    logger.info(
                        f"{func.__name__} attempt {attempt + 1}/{config.max_retries + 1} failed "
                        f"({e.__class__.__name__}), retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)

            # This should never be reached, but satisfy type checker
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry logic failed unexpectedly")

        return wrapper  # type: ignore

    return decorator


def steam_api_request_with_retry(
    method: str,
    url: str,
    data: dict[str, str] | None = None,
    config: SteamWebAPIRetryConfig | None = None,
) -> requests.Response:
    """
    Make an HTTP request to Steam Web API with retry logic.

    This is a convenience function that wraps requests.post/get with retry logic.
    Automatically calls raise_for_status() to trigger retries on bad status codes.

    Usage:
        response = steam_api_request_with_retry(
            method="POST",
            url="https://api.steampowered.com/...",
            data={"key": "value"},
            config=SteamWebAPIRetryConfig(max_retries=3)
        )

    :param method: HTTP method ("POST" or "GET")
    :param url: URL to request
    :param data: Optional data dict for POST requests
    :param config: Retry configuration (uses defaults if None)
    :return: Response object from requests library
    :raises requests.HTTPError: On non-retryable HTTP errors or after max retries
    :raises requests.RequestException: On other request failures after max retries
    """
    if config is None:
        config = SteamWebAPIRetryConfig()

    @retry_steam_api_call(config=config)
    def _make_request() -> requests.Response:
        if method.upper() == "POST":
            response = requests.post(url, data=data)
        elif method.upper() == "GET":
            response = requests.get(url, params=data)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        # Raise HTTPError for bad status codes (triggers retry logic)
        response.raise_for_status()
        return response

    return _make_request()
