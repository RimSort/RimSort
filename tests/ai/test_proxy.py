from unittest.mock import MagicMock, patch

import pytest

from app.ai.gemini_provider import GeminiProvider
from app.ai.proxy import (
    ProxyParseError,
    ProxyUnavailableError,
    build_requests_proxies,
    clear_proxy_cache,
    parse_proxy,
    resolve_working_proxy,
)


class TestParseProxy:
    def test_empty_returns_none(self) -> None:
        assert parse_proxy("") is None
        assert parse_proxy("   ") is None

    def test_host_port(self) -> None:
        endpoint = parse_proxy("127.0.0.1:8080")
        assert endpoint is not None
        assert endpoint.host == "127.0.0.1"
        assert endpoint.port == 8080
        assert endpoint.username is None

    def test_user_pass_at_host_port(self) -> None:
        endpoint = parse_proxy("alice:secret@proxy.example.com:3128")
        assert endpoint is not None
        assert endpoint.username == "alice"
        assert endpoint.password == "secret"
        assert endpoint.host == "proxy.example.com"
        assert endpoint.port == 3128

    def test_user_pass_host_port_colon_form(self) -> None:
        endpoint = parse_proxy("alice:secret:proxy.example.com:3128")
        assert endpoint is not None
        assert endpoint.username == "alice"
        assert endpoint.password == "secret"
        assert endpoint.host == "proxy.example.com"
        assert endpoint.port == 3128

    def test_host_port_user_pass_colon_form(self) -> None:
        endpoint = parse_proxy("proxy.example.com:3128:alice:secret")
        assert endpoint is not None
        assert endpoint.username == "alice"
        assert endpoint.password == "secret"
        assert endpoint.host == "proxy.example.com"
        assert endpoint.port == 3128

    def test_explicit_socks5_url(self) -> None:
        endpoint = parse_proxy("socks5://alice:secret@127.0.0.1:1080")
        assert endpoint is not None
        assert endpoint.preferred_scheme == "socks5"
        assert endpoint.host == "127.0.0.1"
        assert endpoint.port == 1080

    def test_invalid_raises(self) -> None:
        with pytest.raises(ProxyParseError):
            parse_proxy("not-a-proxy")


class TestResolveWorkingProxy:
    def setup_method(self) -> None:
        clear_proxy_cache()

    @patch("app.ai.proxy._probe_proxy")
    def test_prefers_http_then_socks5(self, mock_probe: MagicMock) -> None:
        mock_probe.side_effect = [False, True]
        result = resolve_working_proxy("127.0.0.1:1080")
        assert result is not None
        proxies, scheme = result
        assert scheme == "socks5"
        assert proxies["https"].startswith("socks5://127.0.0.1:1080")
        assert mock_probe.call_count == 2

    @patch("app.ai.proxy._probe_proxy")
    def test_uses_cache(self, mock_probe: MagicMock) -> None:
        mock_probe.return_value = True
        first = resolve_working_proxy("127.0.0.1:8080")
        second = resolve_working_proxy("127.0.0.1:8080")
        assert first == second
        assert mock_probe.call_count == 1

    @patch("app.ai.proxy._probe_proxy", return_value=False)
    def test_unavailable_raises(self, _mock_probe: MagicMock) -> None:
        with pytest.raises(ProxyUnavailableError):
            resolve_working_proxy("127.0.0.1:8080")


class TestBuildRequestsProxies:
    def test_with_auth(self) -> None:
        endpoint = parse_proxy("alice:secret@127.0.0.1:8080")
        assert endpoint is not None
        proxies = build_requests_proxies(endpoint, "http")
        assert proxies["https"] == "http://alice:secret@127.0.0.1:8080"


class TestGeminiProvider:
    @patch("app.ai.gemini_provider.http.post")
    def test_complete_parses_response(self, mock_post: MagicMock) -> None:
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Hello from Gemini"}]}}]
        }

        provider = GeminiProvider("test-key")
        result = provider.complete([{"role": "user", "content": "Hi"}])
        assert result == "Hello from Gemini"
        assert "gemini-3.5-flash-lite" in mock_post.call_args.args[0]

    @patch("app.ai.gemini_provider.http.post")
    def test_quota_error_suggests_other_models(self, mock_post: MagicMock) -> None:
        mock_post.return_value.ok = False
        mock_post.return_value.status_code = 429
        mock_post.return_value.json.return_value = {
            "error": {
                "message": "You exceeded your current quota, please check your plan."
            }
        }

        provider = GeminiProvider("test-key", model="gemini-3.5-flash")
        with pytest.raises(ValueError, match="gemini-3.5-flash-lite"):
            provider.complete([{"role": "user", "content": "Hi"}])

    @patch("app.ai.gemini_provider.resolve_working_proxy")
    @patch("app.ai.gemini_provider.http.post")
    def test_complete_passes_proxies(
        self, mock_post: MagicMock, mock_resolve: MagicMock
    ) -> None:
        mock_resolve.return_value = (
            {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"},
            "http",
        )
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
        }

        provider = GeminiProvider("test-key", proxy="127.0.0.1:8080")
        provider.complete([{"role": "user", "content": "Hi"}])
        assert mock_post.call_args.kwargs["proxies"]["https"] == "http://127.0.0.1:8080"

    @patch("app.ai.gemini_provider.http.post")
    def test_geo_error_message(self, mock_post: MagicMock) -> None:
        mock_post.return_value.ok = False
        mock_post.return_value.status_code = 400
        mock_post.return_value.json.return_value = {
            "error": {"message": "User location is not supported for the API use."}
        }

        provider = GeminiProvider("test-key")
        with pytest.raises(ValueError, match="region"):
            provider.complete([{"role": "user", "content": "Hi"}])

    @patch("app.ai.gemini_provider.http.post")
    def test_complete_runs_tool_call_loop(self, mock_post: MagicMock) -> None:
        tool_response = MagicMock()
        tool_response.ok = True
        tool_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "describe_mod",
                                    "args": {"package_id": "test.mod"},
                                }
                            }
                        ],
                    }
                }
            ]
        }
        text_response = MagicMock()
        text_response.ok = True
        text_response.json.return_value = {
            "candidates": [
                {"content": {"parts": [{"text": "Mod details loaded."}]}}
            ]
        }
        mock_post.side_effect = [tool_response, text_response]

        def tool_executor(name: str, args: dict) -> dict:
            assert name == "describe_mod"
            return {"found": True, "name": "Test Mod"}

        provider = GeminiProvider("test-key")
        result = provider.complete(
            [{"role": "user", "content": "Tell me about test.mod"}],
            tools=[{"name": "describe_mod"}],
            tool_executor=tool_executor,
        )
        assert result == "Mod details loaded."
        assert mock_post.call_count == 2
        second_body = mock_post.call_args_list[1].kwargs["json"]
        assert second_body["contents"][-1]["parts"][0]["functionResponse"]["name"] == (
            "describe_mod"
        )
