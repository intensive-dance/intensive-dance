"""Tests for the Scuola di Ballo del Teatro di San Carlo scraper.

All offline — no network. Fixtures are trimmed from the live "Passi d'Estate in
Teatro" bando PDF (2024 edition) text, as `_pdf_text` yields it post-clean:
  - HAPPY: the real bando shape — single-month date range, three level bands with
    an open-topped "Over 16", the curriculum genre list, the per-package EUR
    fees (auditor "OPEN CARD" passes must be excluded), the deadline and faculty.
  - EDGES: a closed top age band (no "Over"); a bando with no parseable dates
    yields no Offering; the auditor passes after "OPEN CARD" are dropped.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers.teatro_san_carlo_scuola_ballo import (
    INFO_URL,
    _age_range,
    _build_offerings,
    _date_range,
    _deadline,
    _genres,
    _levels,
    _prices,
    _teachers,
)

# Trimmed but structurally faithful bando text (post-clean, one line as the PDF
# extractor flattens it).
BANDO = (
    "Nell'estate 2024 nasce la 1° edizione di \"Passi d'Estate in Teatro\", il "
    "workshop intensivo di danza presso la Scuola di Ballo del Teatro di San Carlo "
    "Dal 10 Luglio al 13 Luglio 2024, la Scuola di Ballo del Teatro di San Carlo "
    "apre le porte a allieve/i provenienti da tutte le scuole Italiane ed Estere. "
    "Gli allievi affronteranno lo studio della Danza Classica e Tecnica delle Punte, "
    "Repertorio, Fisiotecnica, Danza Contemporanea e Laboratorio coreografico. "
    "Livelli: - Principianti: 9/12 anni - Intermedio: 13/15 anni - Avanzato: Over 16 "
    "COSTI Livello Principianti 4 giorni di lezioni (2 lezioni al giorno per un "
    "totale di 8 lezioni): 250,00 euro Livello Intermedio/Avanzato - pacchetto solo "
    "danza classica 2 giorni di lezioni (3 lezioni al giorno per un totale di 6 "
    "lezioni): 250,00 euro 4 giorni di lezioni (2 lezioni al giorno per un totale di "
    "8 lezioni): 390,00 euro Livello Intermedio/Avanzato - pacchetto solo danza "
    "contemporanea (1 lezione al giorno per 2 giorni): 130,00 euro Livello "
    "Intermedio/Avanzato - pacchetto completo 4 giorni 10-11 luglio (3 lezioni al "
    "giorno focus danza classica per un totale di 6 lezioni) Totale di 12 lezioni: "
    "490,00 euro OPEN CARD - DOCENTI O UDITORI Vi è la possibilità per docenti "
    "accompagnatori e/o uditori di assistere alle lezioni: Livello principianti: "
    "90,00 euro Livello intermedio/avanzato: 110,00 euro L'iscrizione a Passi "
    "d'Estate 2024 avviene inviando la domanda di partecipazione via email entro e "
    "non oltre il 1° luglio 2024. DOCENTI Stéphane Fournial (Direttore Scuola di "
    "Ballo Teatro di San Carlo) Rossella Lo Sapio (Docente Danza Classica) Assunta "
    "Anatrella (Docente Danza Classica Corsi Inferiori) Emma Cianchi (Docente Danza "
    "Contemporanea)"
)

# A variant whose top band is closed ("16/19") rather than open "Over 16".
BANDO_CLOSED = BANDO.replace("Avanzato: Over 16", "Avanzato: 16/19 anni")


# --- _date_range --------------------------------------------------------------


def test_date_range_single_month() -> None:
    assert _date_range(BANDO) == (date(2024, 7, 10), date(2024, 7, 13))


def test_date_range_missing_returns_none() -> None:
    assert _date_range("nessuna data qui") == (None, None)


# --- _age_range ---------------------------------------------------------------


def test_age_range_open_topped_over_band() -> None:
    # Principianti 9/12, Intermedio 13/15, Avanzato "Over 16" → min 9, no max.
    assert _age_range(BANDO) == {"min": 9}


def test_age_range_closed_top_band() -> None:
    assert _age_range(BANDO_CLOSED) == {"min": 9, "max": 19}


def test_age_range_absent() -> None:
    assert _age_range("nessuna età") is None


# --- _genres / _levels --------------------------------------------------------


def test_genres_from_curriculum_list() -> None:
    # Fisiotecnica / Laboratorio coreografico are not register genres.
    assert _genres(BANDO) == ["classical", "pointe", "repertoire", "contemporary"]


def test_levels_three_bands() -> None:
    assert _levels(BANDO) == ["beginner", "intermediate", "advanced"]


# --- _prices ------------------------------------------------------------------


def test_prices_exclude_auditor_open_card() -> None:
    prices = _prices(BANDO)
    amounts = sorted(p.amount for p in prices)
    # The five student packages; the 90/110 € auditor passes are excluded.
    assert amounts == [130.0, 250.0, 250.0, 390.0, 490.0]
    assert all(p.currency == "EUR" for p in prices)
    assert all(p.includes == ["tuition"] for p in prices)
    # The two distinct 250 € packages keep different labels.
    labels = {p.label for p in prices if p.amount == 250.0}
    assert len(labels) == 2


def test_prices_absent_without_costi() -> None:
    assert _prices("nessun costo pubblicato") == []


# --- _deadline ----------------------------------------------------------------


def test_deadline_entro_e_non_oltre() -> None:
    assert _deadline(BANDO) == date(2024, 7, 1)


def test_deadline_absent() -> None:
    assert _deadline("nessuna scadenza") is None


# --- _teachers ----------------------------------------------------------------


def test_teachers_roster_with_director() -> None:
    teachers = _teachers(BANDO)
    names = [t.name for t in teachers]
    assert names == [
        "Stéphane Fournial",
        "Rossella Lo Sapio",
        "Assunta Anatrella",
        "Emma Cianchi",
    ]
    assert teachers[0].role == "Direttore Scuola di Ballo"


def test_teachers_absent_when_not_named() -> None:
    assert _teachers("nessun docente elencato") == []


# --- whole-offering shape -----------------------------------------------------


def test_build_offering_full_shape() -> None:
    offerings = _build_offerings(BANDO)
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "teatro-san-carlo-scuola-ballo/passi-d-estate-2024"
    assert o.title == "Passi d'Estate in Teatro 2024"
    assert o.source.url == INFO_URL
    assert o.organization.slug == "teatro-san-carlo-scuola-ballo"
    assert o.location is not None
    assert o.location.city == "Naples"
    assert o.location.country == "IT"
    assert o.schedule.season == "2024"
    assert o.schedule.start == date(2024, 7, 10)
    assert o.schedule.end == date(2024, 7, 13)
    assert o.schedule.timezone == "Europe/Rome"
    assert o.genres == ["classical", "pointe", "repertoire", "contemporary"]
    assert o.level == ["beginner", "intermediate", "advanced"]
    assert o.age_range == {"min": 9}
    assert len(o.prices) == 5
    assert len(o.teachers) == 4
    assert o.application.deadline == date(2024, 7, 1)
    # Open to all levels, no audition/photo/video selection → explicitly nothing.
    assert [r.type for r in o.application.requirements] == ["none"]


def test_build_offering_no_dates_yields_nothing() -> None:
    assert _build_offerings("workshop senza date né anno") == []
