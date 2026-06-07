"""Unit tests for the Fondazione Monreart scraper (WordPress, multi-location).

The pages flip between English and Italian (Varnish cache), so these pin that the
language-agnostic parsing gives the *same* result either way — dates (EN/IT month
names), ages ("between 9 and 19" vs "tra i 9 e i 19 anni"), the headline price,
and genres. They also pin the postponed-edition lifecycle (IDR-24), that the
refund boilerplate is not mistaken for a cancellation, the open-ended senior age
band (Winter School: "da 15 anni in su"), requirements parsing (NoneReq for no
selection, PhotosReq for "attaching photos"), and the registration deadline.
Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import NoneReq, PhotosReq
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


def test_ages_open_ended_senior_band():
    # Winter School live page: Junior 11-14 + Senior "da 15 anni in su" (open-ended).
    text = "Junior course: 11-14 years old Senior course: 15 years and older"
    result = mon._age_range(text)
    assert result is not None
    assert result["min"] == 11
    assert "max" not in result or result.get("max") is None


def test_ages_italian_open_ended():
    text = "Junior: 11-14 anni Senior: da 15 anni in su"
    result = mon._age_range(text)
    assert result is not None
    assert result["min"] == 11
    assert result.get("max") is None


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


def test_requirements_none_req_for_no_selection():
    text = "Selection: no photographic selection required."
    (req,) = mon._requirements(text)
    assert isinstance(req, NoneReq)


def test_requirements_photos_req_for_attaching_photos():
    text = "Submit application via online form attaching photos."
    (req,) = mon._requirements(text)
    assert isinstance(req, PhotosReq)
    assert req.specificity == "freeform"


def test_requirements_empty_when_not_stated():
    assert mon._requirements("No information available about requirements.") == []


def test_deadline_from_italian_text():
    text = "Le iscrizioni sono aperte fino al 31 luglio 2026."
    assert mon._deadline(text, 2026) == date(2026, 7, 31)


def test_deadline_from_english_text():
    text = "Registration is open until July 31, 2026."
    assert mon._deadline(text, 2026) == date(2026, 7, 31)


def test_deadline_absent():
    assert mon._deadline("Apply at any time.", 2026) is None
