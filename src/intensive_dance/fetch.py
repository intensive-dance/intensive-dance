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

import httpx

USER_AGENT = "intensive.dance scraper (+https://github.com/boredland/intensive-dance)"


class _RestProxyTransport(httpx.BaseTransport):
    """Route every request through the fetch-proxy's REST `?url=` endpoint.

    The original request URL becomes the `url` query param; method and body are
    preserved so form POSTs still work. The proxy fetches the target itself, so
    client-side TLS verification only ever applies to the proxy hop (a valid
    cert); the odd provider with a broken chain is handled server-side.
    """

    def __init__(self, base_url: str, token: str | None) -> None:
        self._base = httpx.URL(base_url)
        self._token = token
        self._inner = httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        proxied_url = self._base.copy_merge_params({"url": str(request.url)})
        headers = httpx.Headers({"User-Agent": USER_AGENT})
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        content = request.read()
        if content and (content_type := request.headers.get("content-type")):
            headers["content-type"] = content_type
        proxied = httpx.Request(
            request.method, proxied_url, headers=headers, content=content or None
        )
        return self._inner.handle_request(proxied)


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
        transport = _RestProxyTransport(proxy_url, token)
        return httpx.Client(
            headers=headers, transport=transport, timeout=30.0, follow_redirects=True
        )

    return httpx.Client(headers=headers, timeout=30.0, follow_redirects=True, verify=verify)
