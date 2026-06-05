"""HTTP client factory.

Mirrors museumsufer: a real User-Agent plus an optional pass-through proxy
(set FETCH_PROXY_URL / FETCH_PROXY_TOKEN) for when a site blocks the CI
runner's datacenter IP. Proxy is off unless the env vars are present.
"""

from __future__ import annotations

import os

import httpx

USER_AGENT = "intensive.dance scraper (+https://github.com/boredland/intensive-dance)"


def make_client(*, verify: bool = True) -> httpx.Client:
    """An httpx client with our UA and optional pass-through proxy.

    `verify=False` disables TLS certificate verification — needed only for the
    odd provider that serves an incomplete certificate chain (a server-side
    misconfiguration). We read public pages, so the MITM risk is negligible; a
    scraper that needs it documents why.
    """
    headers = {"User-Agent": USER_AGENT}

    proxy_url = os.environ.get("FETCH_PROXY_URL")
    if proxy_url:
        token = os.environ.get("FETCH_PROXY_TOKEN")
        if token:
            headers["Proxy-Authorization"] = f"Bearer {token}"
        return httpx.Client(headers=headers, proxy=proxy_url, timeout=30.0, follow_redirects=True, verify=verify)

    return httpx.Client(headers=headers, timeout=30.0, follow_redirects=True, verify=verify)
