"""HTTP client factory.

A real User-Agent plus an optional fetch-proxy (set FETCH_PROXY_URL /
FETCH_PROXY_TOKEN) for when a site blocks the CI runner's datacenter IP or
serves a broken TLS chain. Proxy is off unless the env vars are present.

The proxy is **not** an HTTP forward proxy — it exposes a REST interface
(`GET {base}?url=<target>` with `Authorization: Bearer <token>`) that fetches the
target server-side with a Chrome UA and TLS verification off. We bridge that to
the usual httpx surface with a small transport so scrapers keep calling
`client.get(real_url)` and never have to know the proxy is there.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from urllib.parse import parse_qsl

import httpx

USER_AGENT = "intensive.dance scraper (+https://github.com/boredland/intensive-dance)"

# Transient gateway/timeout statuses worth retrying. The fetch proxy is
# Cloudflare-fronted and, under load, intermittently returns 524 (origin
# timeout) / 502 / 503 — a single blip otherwise fails the whole scraper, and the
# hourly rotation then spams the scrape-failure tracker with a different random
# set of (correct) scrapers each run. 500/501 are left out: a real server error
# isn't cleared by retrying.
_RETRY_STATUS = frozenset({429, 502, 503, 504, 520, 522, 524})
_MAX_ATTEMPTS = 3

# A scraper sets this request header (e.g. "solve=1") to force a proxy escalation
# tier per-request — the transport strips it and merges it into the proxy query
# string. Needed for hosts whose block the proxy's auto-heuristic doesn't catch
# (e.g. a Cloudflare challenge that only the FlareSolverr `solve=1` tier defeats —
# see bolshoi_summer_intensive_tokyo). Inert when no proxy is configured (it's
# just an unknown header on a direct fetch).
PROXY_PARAMS_HEADER = "x-fetch-proxy-params"


class _RestProxyTransport(httpx.BaseTransport):
    """Route every request through the fetch-proxy's REST `?url=` endpoint.

    The original request URL becomes the `url` query param; method and body are
    preserved so form POSTs still work. The proxy fetches the target itself, so
    client-side TLS verification only ever applies to the proxy hop (a valid
    cert); the odd provider with a broken chain is handled server-side.
    """

    def __init__(
        self, base_url: str, token: str | None, inner: httpx.BaseTransport | None = None
    ) -> None:
        self._base = httpx.URL(base_url)
        self._token = token
        self._inner = inner or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        params = {"url": str(request.url)}
        if extra := request.headers.get(PROXY_PARAMS_HEADER):
            params.update(dict(parse_qsl(extra)))
        proxied_url = self._base.copy_merge_params(params)
        headers = httpx.Headers({"User-Agent": USER_AGENT})
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        # Forward Accept-Language so a scraper can pin the proxy's render locale
        # (the proxy serves the page in this language); default unchanged otherwise.
        if accept_language := request.headers.get("accept-language"):
            headers["Accept-Language"] = accept_language
        content = request.read()
        if content and (content_type := request.headers.get("content-type")):
            headers["content-type"] = content_type
        proxied = httpx.Request(
            request.method, proxied_url, headers=headers, content=content or None
        )
        return self._inner.handle_request(proxied)


class _RetryTransport(httpx.BaseTransport):
    """Retry transient gateway failures (proxy 524/502/… and transport timeouts).

    Wraps any inner transport. Read-only GETs (and the odd form POST) are safe to
    re-send, so we retry up to `attempts` times with linear backoff before giving
    up and surfacing the last response/exception. `sleep` is injectable for tests.
    """

    def __init__(
        self,
        inner: httpx.BaseTransport,
        *,
        attempts: int = _MAX_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._inner = inner
        self._attempts = attempts
        self._sleep = sleep

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        for attempt in range(1, self._attempts + 1):
            last = attempt == self._attempts
            try:
                response = self._inner.handle_request(request)
            except httpx.TransportError:
                if last:
                    raise
            else:
                if last or response.status_code not in _RETRY_STATUS:
                    return response
                response.close()
            self._sleep(attempt)  # linear backoff: 1s, 2s, …
        raise RuntimeError(
            "unreachable: retry loop exhausted without returning"
        )  # pragma: no cover


def make_client(*, verify: bool = True, use_proxy: bool = True) -> httpx.Client:
    """An httpx client with our UA and optional fetch-proxy.

    `verify=False` disables TLS certificate verification on **direct** fetches —
    needed only for the odd provider that serves an incomplete certificate chain
    (a server-side misconfiguration). When the proxy is active that concern moves
    server-side, so `verify` is irrelevant to the proxy hop. We read public
    pages, so the MITM risk is negligible; a scraper that needs it documents why.

    `use_proxy=False` forces a direct fetch even when the proxy env is set — for
    a provider that the proxy's fetch fingerprint gets blocked on but a plain
    httpx request is not (see `mosa_ballet_school`).
    """
    headers = {"User-Agent": USER_AGENT}

    proxy_url = os.environ.get("FETCH_PROXY_URL") if use_proxy else None
    if proxy_url:
        token = os.environ.get("FETCH_PROXY_TOKEN")
        transport: httpx.BaseTransport = _RetryTransport(_RestProxyTransport(proxy_url, token))
        return httpx.Client(
            headers=headers, transport=transport, timeout=30.0, follow_redirects=True
        )

    transport = _RetryTransport(httpx.HTTPTransport(verify=verify))
    return httpx.Client(headers=headers, transport=transport, timeout=30.0, follow_redirects=True)
