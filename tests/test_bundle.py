"""Offline tests for the consumer bundle projection (no network)."""

from __future__ import annotations

from intensive_dance.bundle import _project


def _offering(**over: object) -> dict:
    base: dict[str, object] = {
        "id": "prov/edition-2026",
        "title": "Summer Intensive 2026",
        "genres": ["classical"],
        "level": [],
        "ageRange": {"min": 10, "max": 18},
        "organization": {"name": "Provider Ballet", "slug": "prov"},
        "location": {"city": "Vienna", "country": "AT", "venue": "Studio 1"},
        "schedule": {
            "season": "2026",
            "start": "2026-07-01",
            "end": "2026-07-14",
            "sessions": [
                {"label": "Wk 1", "start": "2026-07-01", "end": "2026-07-07", "gender": "female"}
            ],
        },
        "application": {
            "url": "https://x/apply",
            "deadline": "2026-05-01",
            "requirements": [{"type": "photos"}, {"type": "video"}],
        },
        "prices": [
            {
                "amount": 500.0,
                "currency": "EUR",
                "label": "Tuition",
                "type": "tuition",
                "includes": ["tuition"],
            }
        ],
        "source": {"url": "https://x/intensive"},
    }
    base.update(over)
    return base


def test_project_flattens_and_joins_coords():
    coords = {"AT|Vienna": (48.2084, 16.3725)}
    r = _project(_offering(), coords)
    assert r["id"] == "prov/edition-2026"
    assert r["org"] == "Provider Ballet" and r["orgSlug"] == "prov"
    assert r["city"] == "Vienna" and r["country"] == "AT" and r["venue"] == "Studio 1"
    assert r["age"] == {"min": 10, "max": 18}
    assert r["season"] == "2026" and r["start"] == "2026-07-01"
    assert r["sessions"] == [
        {"label": "Wk 1", "start": "2026-07-01", "end": "2026-07-07", "gender": "female"}
    ]
    assert r["deadline"] == "2026-05-01" and r["appUrl"] == "https://x/apply"
    assert r["reqs"] == ["photos", "video"]
    assert r["prices"] == [
        {"amount": 500.0, "currency": "EUR", "label": "Tuition", "type": "tuition", "fee": False}
    ]
    assert r["price"] == {"amount": 500.0, "currency": "EUR", "label": "Tuition", "fee": False}
    assert r["url"] == "https://x/intensive"
    # coordinates joined from the gazetteer
    assert r["lat"] == 48.2084 and r["lon"] == 16.3725


def test_project_no_coords_when_city_absent_or_unlisted():
    # city present but not in the gazetteer → null coords (consumer's "unknown" group)
    r = _project(_offering(), coords={})
    assert r["lat"] is None and r["lon"] is None
    # city-less location → null coords, never crashes
    r2 = _project(_offering(location={"country": "AT", "online": None}), {"AT|Vienna": (1.0, 2.0)})
    assert r2["city"] is None and r2["lat"] is None


def test_project_online_offering():
    r = _project(_offering(location={"online": True}), {})
    assert r["online"] is True and r["lat"] is None


def test_headline_price_prefers_tuition_over_a_fee():
    o = _offering(
        prices=[
            {
                "amount": 29.0,
                "currency": "EUR",
                "label": "Registration fee",
                "type": "registration",
            },
            {"amount": 800.0, "currency": "EUR", "label": "Tuition", "type": "tuition"},
        ]
    )
    r = _project(o, {})
    assert r["price"] == {"amount": 800.0, "currency": "EUR", "label": "Tuition", "fee": False}
    # the category passes through to the feed; fee derives from it, regardless of order
    assert [p["type"] for p in r["prices"]] == ["registration", "tuition"]
    assert [p["fee"] for p in r["prices"]] == [True, False]


def test_headline_price_marks_a_fee_only_offering():
    o = _offering(
        prices=[{"amount": 29.0, "currency": "EUR", "label": "Registration fee", "includes": []}]
    )
    r = _project(o, {})
    assert r["price"] == {
        "amount": 29.0,
        "currency": "EUR",
        "label": "Registration fee",
        "fee": True,
    }


def test_headline_price_none_without_prices():
    r = _project(_offering(prices=[]), {})
    assert r["price"] is None and r["prices"] == []
