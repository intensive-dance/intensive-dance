"""Unit tests for the Fondazione Monreart scraper (WordPress, multi-location).

The pages flip between English and Italian (Varnish cache), so these pin that the
language-agnostic parsing gives the *same* result either way — dates (EN/IT month
names), ages ("between 9 and 19" vs "tra i 9 e i 19 anni"), the headline price,
and genres. They also pin the postponed-edition lifecycle (IDR-24) and that the
refund boilerplate is not mistaken for a cancellation. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import fondazione_monreart as mon


def test_dates_english_and_italian():
    assert mon._date_range("CYPRUS 20 - 25 July 2026 Limassol") == (
        date(2026, 7, 20),
        date(2026, 7, 25),
    )
    assert mon._date_range("VERONA 27 - 31 Dicembre 2025 Verona") == (
        date(2025, 12, 27),
        date(2025, 12, 31),
    )


def test_ages_english_and_italian_match():
    en = mon._age_range("for dancers aged between 9 and 19 years")
    it = mon._age_range("rivolto a danzatori di età compresa tra i 9 e i 19 anni")
    assert en == it == {"min": 9, "max": 19}


def test_ages_bare_junior_senior_bands():
    # Winter School lists "Junior: 11-14 anni" and "Senior: 15-19 anni".
    assert mon._age_range("Corso Junior: 11-14 anni Corso Senior: 15-19 anni") == {
        "min": 11,
        "max": 19,
    }


def test_lifecycle_postponed_banner():
    assert mon._lifecycle("... Cookie Policy The event has been postponed to 2027 English") == (
        "postponed",
        "Postponed to 2027.",
    )
    # Italian wording for the same banner.
    assert mon._lifecycle("L'evento è stato rimandato al 2027")[0] == "postponed"


def test_lifecycle_refund_boilerplate_is_not_cancellation():
    text = "The registration fee will be refunded only in case of cancellation of the event."
    assert mon._lifecycle(text) == ("scheduled", None)


def test_lifecycle_explicit_cancellation():
    assert mon._lifecycle("The event has been cancelled")[0] == "cancelled"


def test_price_headline_either_currency_form():
    assert [(p.amount, p.currency) for p in mon._prices("The course costs 450€")] == [
        (450.0, "EUR")
    ]
    assert [(p.amount, p.currency) for p in mon._prices("Il costo del corso è di euro 400")] == [
        (400.0, "EUR")
    ]


def test_genres_english_and_italian():
    assert mon._genres("classical and contemporary dance") == ["classical", "contemporary"]
    assert mon._genres("danza classica e contemporanea") == ["classical", "contemporary"]


def test_place_table():
    assert mon._PLACE["international-summer-school-cyprus"] == ("Limassol", "CY")
    assert mon._PLACE["international-spring-school-italia"] == ("Verona", "IT")
    assert mon._PLACE.get("brand-new-unmapped-event", (None, None)) == (None, None)
