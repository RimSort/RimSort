import unittest.mock as mock

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.utils import http


def _get_retry_for_url(url: str) -> Retry:
    adapter = http._new_session().get_adapter(url)
    assert isinstance(adapter, HTTPAdapter)
    retry = adapter.max_retries
    assert isinstance(retry, Retry)
    return retry


class TestRequestWrappers:
    """The get/post/head wrappers dispatch correctly and apply a timeout."""

    def test_get_sets_default_timeout(self) -> None:
        with mock.patch.object(requests.Session, "request") as request:
            http.get("https://example.com")
        method, url = request.call_args.args
        assert method == "GET"
        assert url == "https://example.com"
        assert request.call_args.kwargs["timeout"] == http.DEFAULT_TIMEOUT

    def test_explicit_timeout_is_preserved(self) -> None:
        with mock.patch.object(requests.Session, "request") as request:
            http.get("https://example.com", timeout=5)
        assert request.call_args.kwargs["timeout"] == 5

    def test_post_and_head_dispatch_to_correct_method(self) -> None:
        with mock.patch.object(requests.Session, "request") as request:
            http.post("https://example.com")
            http.head("https://example.com")
        methods = [call.args[0] for call in request.call_args_list]
        assert methods == ["POST", "HEAD"]


class TestRetryConfiguration:
    """A retry-enabled adapter is mounted for both HTTP and HTTPS."""

    def test_adapter_is_mounted_with_retries(self) -> None:
        session = http._new_session()
        for scheme in ("http://", "https://"):
            adapter = session.get_adapter(scheme)
            assert isinstance(adapter, HTTPAdapter)
            retry = adapter.max_retries
            assert isinstance(retry, Retry)
            assert http.DEFAULT_RETRIES == 4
            assert retry.total == http.DEFAULT_RETRIES
            assert retry.backoff_factor == http.DEFAULT_BACKOFF_FACTOR

    def test_retries_only_idempotent_methods_by_default(self) -> None:
        retry = _get_retry_for_url("https://example.com")
        assert retry.allowed_methods == frozenset(["GET", "HEAD"])

    def test_read_errors_are_not_retried(self) -> None:
        retry = _get_retry_for_url("https://example.com")
        assert retry.read == 0

    def test_transient_status_codes_are_retried(self) -> None:
        retry = _get_retry_for_url("https://example.com")
        assert retry.status_forcelist is not None
        for code in (429, 500, 502, 503, 504):
            assert code in retry.status_forcelist

    def test_retry_after_headers_are_respected(self) -> None:
        retry = _get_retry_for_url("https://example.com")
        assert retry.respect_retry_after_header is True

    def test_final_status_is_returned_not_raised(self) -> None:
        # raise_on_status=False keeps the existing contract: callers decide
        # whether to call response.raise_for_status().
        retry = _get_retry_for_url("https://example.com")
        assert retry.raise_on_status is False
