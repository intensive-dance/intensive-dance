"""Offline tests for the fetch-proxy transport (no network)."""

from __future__ import annotations

import httpx

import pytest

from intensive_dance.fetch import PROXY_PARAMS_HEADER, _RestProxyTransport, _RetryTransport


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


def _retry_transport(responses):
    """A retry transport whose inner returns/raises each item in `responses` in
    turn. Sleeps are swallowed so the test runs instantly."""
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        item = responses[calls["n"]]
        calls["n"] += 1
        if isinstance(item, Exception):
            raise item
        return httpx.Response(item)

    transport = _RetryTransport(httpx.MockTransport(handler), attempts=3, sleep=lambda _: None)
    return transport, calls


def test_retries_transient_524_then_succeeds():
    transport, calls = _retry_transport([524, 200])
    response = transport.handle_request(httpx.Request("GET", "https://site.example/"))
    assert response.status_code == 200
    assert calls["n"] == 2


def test_retries_challenge_403_then_succeeds():
    # A Cloudflare/StackProtect managed-challenge 403 clears non-deterministically,
    # so a re-send of the same request usually gets through (the scrape-failure spam
    # this guards against; see _RETRY_STATUS).
    transport, calls = _retry_transport([403, 200])
    response = transport.handle_request(httpx.Request("GET", "https://site.example/"))
    assert response.status_code == 200
    assert calls["n"] == 2


def test_retries_transport_timeout_then_succeeds():
    transport, calls = _retry_transport([httpx.ReadTimeout("slow proxy"), 200])
    response = transport.handle_request(httpx.Request("GET", "https://site.example/"))
    assert response.status_code == 200
    assert calls["n"] == 2


def test_non_transient_status_is_not_retried():
    transport, calls = _retry_transport([404, 200])
    response = transport.handle_request(httpx.Request("GET", "https://site.example/"))
    assert response.status_code == 404
    assert calls["n"] == 1


def test_exhausts_attempts_and_returns_last_transient_response():
    transport, calls = _retry_transport([524, 524, 524])
    response = transport.handle_request(httpx.Request("GET", "https://site.example/"))
    assert response.status_code == 524
    assert calls["n"] == 3


def test_exhausts_attempts_and_reraises_transport_error():
    transport, _ = _retry_transport([httpx.ConnectError("x")] * 3)
    with pytest.raises(httpx.TransportError):
        transport.handle_request(httpx.Request("GET", "https://site.example/"))
