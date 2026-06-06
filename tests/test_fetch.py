"""Offline tests for the fetch-proxy transport (no network)."""

from __future__ import annotations

import httpx

from intensive_dance.fetch import PROXY_PARAMS_HEADER, _RestProxyTransport


def _capture(request: httpx.Request) -> httpx.Request:
    """Run the request through the proxy transport with a mocked inner transport,
    returning the request it would have sent to the proxy."""
    seen: dict[str, httpx.Request] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["req"] = req
        return httpx.Response(200)

    transport = _RestProxyTransport(
        "https://proxy.example/", token="tok", inner=httpx.MockTransport(handler)
    )
    transport.handle_request(request)
    return seen["req"]


def test_target_url_becomes_proxy_url_param():
    sent = _capture(httpx.Request("GET", "https://site.example/page?a=1"))
    assert sent.url.host == "proxy.example"
    assert sent.url.params.get("url") == "https://site.example/page?a=1"
    assert sent.headers["Authorization"] == "Bearer tok"


def test_proxy_params_header_merges_escalation_and_is_not_forwarded():
    request = httpx.Request(
        "GET", "https://site.example/", headers={PROXY_PARAMS_HEADER: "solve=1"}
    )
    sent = _capture(request)
    assert sent.url.params.get("solve") == "1"
    assert sent.url.params.get("url") == "https://site.example/"
    # the reserved header steers the proxy; it must not be forwarded upstream
    assert PROXY_PARAMS_HEADER not in sent.headers


def test_no_proxy_params_header_means_no_extra_params():
    sent = _capture(httpx.Request("GET", "https://site.example/"))
    assert "solve" not in sent.url.params
