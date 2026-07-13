"""HTTP utility module providing request functions with retries and timeouts.

All HTTP requests in the application should use these functions instead of
calling requests.get/post/head directly, to ensure consistent timeout behavior.

Transient failures (connection errors and the status codes in
RETRY_STATUS_CODES) are retried automatically for idempotent methods using
exponential backoff. A fresh Session is created per request so no state is
shared between threads.
"""

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_TIMEOUT: int | float = 15

# Maximum number of retry attempts for transient failures.
DEFAULT_RETRIES: int = 4
# Backoff factor (seconds); urllib3 uses this for exponential backoff between
# retries.
DEFAULT_BACKOFF_FACTOR: float = 1
# Status codes treated as transient and retried (rate limit + server errors).
RETRY_STATUS_CODES: tuple[int, ...] = (429, 500, 502, 503, 504)


def _new_session() -> requests.Session:
    """Create a Session with retry/backoff mounted for HTTP and HTTPS."""
    retry = Retry(
        total=DEFAULT_RETRIES,
        read=0,
        backoff_factor=DEFAULT_BACKOFF_FACTOR,
        status_forcelist=RETRY_STATUS_CODES,
        allowed_methods=frozenset(["GET", "HEAD"]),
        respect_retry_after_header=True,
        # Return the final response instead of raising so callers keep using
        # response.raise_for_status() as before.
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _request(method: str, url: str, **kwargs: Any) -> requests.Response:
    """Send a request through a Session with a default timeout."""
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    with _new_session() as session:
        return session.request(method, url, **kwargs)


# jscpd:ignore-start
def get(url: str, **kwargs: Any) -> requests.Response:
    """Perform a GET request with retries and default timeout."""
    return _request("GET", url, **kwargs)


def post(url: str, **kwargs: Any) -> requests.Response:
    """Perform a POST request with a default timeout."""
    return _request("POST", url, **kwargs)


def head(url: str, **kwargs: Any) -> requests.Response:
    """Perform a HEAD request with retries and default timeout."""
    return _request("HEAD", url, **kwargs)


# jscpd:ignore-end
