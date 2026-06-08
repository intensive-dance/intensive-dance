"""Tests for the Balletto di Roma scraper.

All offline — no network. The fixtures are trimmed from the live IT pages
captured 2026-06-08:
  - Summer School: cross-month range + three open-ended level bands; its public
    page states only "danza classica" (contemporary lives only on the gated
    brochure, so the public Offering is classical-only — faithful, not inflated).
  - Campus Estivo Monterotondo: start-only date + closed age band + an
    out-of-scope "urban" genre that must NOT appear.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers.balletto_di_roma import (
    CAMPUS_URL,
    SUMMER_SCHOOL_URL,
    _age_range,
    _campus,
    _date_range,
    _genres,
    _levels,
    _single_date,
    _summer_school,
)

# Trimmed but structurally faithful page text (post-clean, as `_page_text` yields).
SUMMER_TEXT = (
    "Summer School Lo studio con i protagonisti europei della danza "
    "14° edizione | 6 luglio – 5 settembre 2026 Scarica la Brochure 2025 "
    "Giunta ormai al suo quattordicesimo anno, la Summer School del Balletto "
    "di Roma offre studio della danza classica con i protagonisti europei. "
    "Chi può partecipare “Summer School” è aperta ad allieve e allievi come "
    "segue: Principianti: dagli 8 anni; Intermedio: dai 12 anni; Avanzato: "
    "dai 15 anni in su. Borse di Studio per allievi meritevoli. "
    "Le lezioni sono a numero chiuso."
)

CAMPUS_TEXT = (
    "Campus estivo Balletto di Roma Monterotondo LA SCUOLA CONTINUA "
    "I° edizione Dal 6 luglio prende il via la prima edizione di La Scuola "
    "Continua, il campus estivo dedicato a bambini e ragazzi dai 6 ai 18 anni "
    "presso la sede di Monterotondo. Il campus accoglie allievi di livello "
    "principiante, intermedio e avanzato, con attività differenziate tra danza "
    "classica, contemporanea e urban. Il programma si sviluppa per quattro "
    "settimane. Copyright © 2026 Balletto di Roma"
)


# --- _date_range / _single_date ----------------------------------------------


def test_date_range_cross_month() -> None:
    start, end = _date_range(SUMMER_TEXT)
    assert start == date(2026, 7, 6)
    assert end == date(2026, 9, 5)


def test_date_range_missing_returns_none() -> None:
    start, end = _date_range("nessuna data qui")
    assert start is None
    assert end is None


def test_single_date_reads_year_from_page() -> None:
    assert _single_date(CAMPUS_TEXT) == date(2026, 7, 6)


def test_single_date_without_year_returns_none() -> None:
    assert _single_date("Dal 6 luglio prende il via") is None


# --- _age_range ---------------------------------------------------------------


def test_age_range_open_ended_top_band() -> None:
    # Beginners 8+, advanced "dai 15 anni in su" → min 8, no max.
    assert _age_range(SUMMER_TEXT) == {"min": 8}


def test_age_range_closed_band() -> None:
    assert _age_range(CAMPUS_TEXT) == {"min": 6, "max": 18}


def test_age_range_absent() -> None:
    assert _age_range("no ages mentioned") is None


# --- _genres / _levels --------------------------------------------------------


def test_summer_genres_classical_only() -> None:
    # The public page states only "danza classica"; contemporary is gated.
    assert _genres(SUMMER_TEXT) == ["classical"]


def test_campus_genres_drop_out_of_scope_urban() -> None:
    # "urban" is out of scope for a ballet register — only classical+contemporary.
    assert _genres(CAMPUS_TEXT) == ["classical", "contemporary"]


def test_levels_three_bands() -> None:
    assert _levels(SUMMER_TEXT) == ["beginner", "intermediate", "advanced"]


# --- whole-offering shape -----------------------------------------------------


def test_summer_school_offering() -> None:
    o = _summer_school(SUMMER_TEXT)
    assert o.id == "balletto-di-roma/summer-school-2026"
    assert o.title == "Summer School 2026"
    assert o.source.url == SUMMER_SCHOOL_URL
    assert o.organization.slug == "balletto-di-roma"
    assert o.location is not None
    assert o.location.city == "Rome"
    assert o.location.country == "IT"
    assert o.schedule.season == "2026"
    assert o.schedule.start == date(2026, 7, 6)
    assert o.schedule.end == date(2026, 9, 5)
    assert o.schedule.timezone == "Europe/Rome"
    assert o.genres == ["classical"]
    assert o.level == ["beginner", "intermediate", "advanced"]
    assert o.age_range == {"min": 8}
    assert o.prices == []  # gated behind a brochure form — not stated


def test_campus_offering() -> None:
    o = _campus(CAMPUS_TEXT)
    assert o.id == "balletto-di-roma/campus-estivo-monterotondo-2026"
    assert o.title == "Campus Estivo Monterotondo 2026"
    assert o.source.url == CAMPUS_URL
    assert o.location is not None
    assert o.location.city == "Monterotondo"
    assert o.location.country == "IT"
    assert o.schedule.start == date(2026, 7, 6)
    assert o.schedule.end is None  # only a start + "four weeks" stated
    assert o.genres == ["classical", "contemporary"]
    assert o.age_range == {"min": 6, "max": 18}
    assert o.prices == []
