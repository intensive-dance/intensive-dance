"""Unit tests for the Brussels International Ballet scraper (single Wix page).

These pin the regex parsing of the one Summer Intensive page — the course date
range (shared trailing year), the open-ended age band, the curriculum-driven
genres, registration status, and the residential-window schedule note. Inline
strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import brussels_international_ballet as bib


def test_date_range_shared_year():
    assert bib._date_range("2 Weeks: 20 July – 01 August 2026 (Includes Gala)") == (
        date(2026, 7, 20),
        date(2026, 8, 1),
    )


def test_date_range_absent():
    assert bib._date_range("no dated edition announced yet") == (None, None)


def test_age_range_open_ended_min_only():
    # "12 and over", groups "12–14" and "15-17+" → lower bound 12, no upper bound.
    text = "For ages 12 and over | Multiple groups available (ages 12-14, 15-17+)"
    assert bib._age_range(text) == {"min": 12}


def test_age_range_absent():
    assert bib._age_range("a two-week summer programme") is None


def test_genres_from_curriculum():
    text = "Ballet Technique, Pointe Work, Classical Repertoire including variations, Contemporary Technique"
    assert bib._genres(text) == ["classical", "pointe", "repertoire", "contemporary"]


def test_status_registration_closed():
    assert bib._status("Summer Intensive Program 2026 Registration is now closed.") == "closed"


def test_status_open_when_stated():
    assert bib._status("Registration is now open — register now") == "open"


def test_status_none_when_unstated():
    assert bib._status("20 July – 01 August 2026") is None


def test_schedule_note_residential_window():
    text = "Package 1: Residential (Recommended) Dates: Sunday 19 July – Sunday 02 August Includes:"
    assert bib._schedule_note(text) == "Residential package: Sunday 19 July – Sunday 02 August"


def test_prices_registration_fee():
    text = "A non-refundable registration fee of €29 is required."
    prices = bib._prices(text)
    assert len(prices) == 1
    assert prices[0].amount == 29.0
    assert prices[0].currency == "EUR"
    assert prices[0].label == "Registration fee"


def test_requirements_headshot_and_photos():
    text = "You must attach your proof of payment and a headshot. Attire follows these guidelines."
    reqs = bib._requirements(text)
    assert len(reqs) == 2
    assert any(r.type == "headshot" for r in reqs)
    assert any(r.type == "photos" and r.specificity == "defined-poses" for r in reqs)
