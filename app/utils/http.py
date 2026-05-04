"""HTTP utility module providing request functions with default timeouts.

All HTTP requests in the application should use these functions instead of
calling requests.get/post/head directly, to ensure consistent timeout behavior.
"""

from typing import Any

import requests

DEFAULT_TIMEOUT: int | float = 15


# jscpd:ignore-start
def get(url: str, **kwargs: Any) -> requests.Response:
    """Perform a GET request with default timeout."""
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return requests.get(url, **kwargs)


def post(url: str, **kwargs: Any) -> requests.Response:
    """Perform a POST request with default timeout."""
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return requests.post(url, **kwargs)


def head(url: str, **kwargs: Any) -> requests.Response:
    """Perform a HEAD request with default timeout."""
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return requests.head(url, **kwargs)


# jscpd:ignore-end
