from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

import requests

ProxyScheme = Literal["http", "socks5"]

GEMINI_PROBE_URL = "https://generativelanguage.googleapis.com/"
DEFAULT_PROBE_TIMEOUT = 10.0

_cache: dict[str, tuple[dict[str, str], ProxyScheme]] = {}


@dataclass(frozen=True)
class ProxyEndpoint:
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    preferred_scheme: ProxyScheme | None = None


class ProxyParseError(ValueError):
    pass


class ProxyUnavailableError(ValueError):
    pass


def parse_proxy(raw: str) -> ProxyEndpoint | None:
    text = raw.strip()
    if not text:
        return None

    preferred_scheme: ProxyScheme | None = None
    if "://" in text:
        parsed = urlparse(text)
        if parsed.scheme in ("http", "https"):
            preferred_scheme = "http"
        elif parsed.scheme == "socks5":
            preferred_scheme = "socks5"
        else:
            raise ProxyParseError(
                f"Unsupported proxy scheme '{parsed.scheme}'. Use http or socks5."
            )
        if not parsed.hostname or parsed.port is None:
            raise ProxyParseError("Could not parse proxy host and port.")
        return ProxyEndpoint(
            host=parsed.hostname,
            port=parsed.port,
            username=parsed.username,
            password=parsed.password,
            preferred_scheme=preferred_scheme,
        )

    if "@" in text:
        auth, hostport = text.rsplit("@", 1)
        username: str | None
        password: str | None
        if ":" in auth:
            username, password = auth.split(":", 1)
        else:
            username, password = auth, None
        if ":" not in hostport:
            raise ProxyParseError(
                "Expected host:port after '@' (e.g. user:pass@host:port)."
            )
        host, port_str = hostport.rsplit(":", 1)
        return ProxyEndpoint(
            host=host,
            port=int(port_str),
            username=username or None,
            password=password or None,
            preferred_scheme=preferred_scheme,
        )

    parts = text.split(":")
    if len(parts) == 2:
        return ProxyEndpoint(host=parts[0], port=int(parts[1]))
    if len(parts) == 4:
        if parts[1].isdigit():
            return ProxyEndpoint(
                host=parts[0],
                port=int(parts[1]),
                username=parts[2],
                password=parts[3],
            )
        if parts[3].isdigit():
            return ProxyEndpoint(
                host=parts[2],
                port=int(parts[3]),
                username=parts[0],
                password=parts[1],
            )
        raise ProxyParseError(
            "Could not parse proxy. Use host:port, user:pass@host:port, "
            "user:pass:host:port, or host:port:user:pass."
        )
    raise ProxyParseError(
        "Could not parse proxy. Use host:port, user:pass@host:port, "
        "user:pass:host:port, or host:port:user:pass."
    )


def build_requests_proxies(
    endpoint: ProxyEndpoint, scheme: ProxyScheme
) -> dict[str, str]:
    auth = ""
    if endpoint.username:
        password = endpoint.password or ""
        auth = f"{endpoint.username}:{password}@"
    url = f"{scheme}://{auth}{endpoint.host}:{endpoint.port}"
    return {"http": url, "https": url}


def _probe_proxy(
    proxies: dict[str, str],
    test_url: str,
    timeout: float,
) -> bool:
    try:
        with requests.Session() as session:
            session.head(
                test_url,
                proxies=proxies,
                timeout=timeout,
                allow_redirects=True,
            )
        return True
    except (
        requests.exceptions.ProxyError,
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.InvalidSchema,
    ):
        return False


def resolve_working_proxy(
    raw: str,
    *,
    test_url: str = GEMINI_PROBE_URL,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
) -> tuple[dict[str, str], ProxyScheme] | None:
    text = raw.strip()
    if not text:
        return None

    cached = _cache.get(text)
    if cached is not None:
        return cached

    try:
        endpoint = parse_proxy(text)
    except ProxyParseError:
        raise
    if endpoint is None:
        return None

    schemes: list[ProxyScheme] = []
    if endpoint.preferred_scheme:
        schemes.append(endpoint.preferred_scheme)
        fallback: ProxyScheme = (
            "socks5" if endpoint.preferred_scheme == "http" else "http"
        )
        if fallback not in schemes:
            schemes.append(fallback)
    else:
        schemes = ["http", "socks5"]

    for scheme in schemes:
        proxies = build_requests_proxies(endpoint, scheme)
        if _probe_proxy(proxies, test_url, timeout):
            _cache[text] = (proxies, scheme)
            return proxies, scheme

    raise ProxyUnavailableError(
        "Proxy is unreachable. Check host, port, credentials, and type (HTTP/SOCKS5)."
    )


def clear_proxy_cache() -> None:
    _cache.clear()
