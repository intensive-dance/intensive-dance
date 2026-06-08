"""Unit tests for the Corella Dance Academy scraper.

Tests cover: Spanish-language date parsing, genre detection from curriculum
text, price extraction, teacher filtering, and the full _build_offerings
path with a minimal HTML snippet (happy path + no-dates edge case).
No network calls.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import corella_dance_academy as cda


# --- _date_range --------------------------------------------------------------


def test_date_range_july():
    text = "Del 6 al 11 de julio de 2026"
    assert cda._date_range(text) == (date(2026, 7, 6), date(2026, 7, 11))


def test_date_range_august():
    text = "Del 11 al 16 de agosto de 2026"
    assert cda._date_range(text) == (date(2026, 8, 11), date(2026, 8, 16))


def test_date_range_absent():
    assert cda._date_range("no dates yet, próximamente") == (None, None)


def test_date_range_case_insensitive():
    # lowercase "del" should still match
    text = "del 6 al 11 de julio de 2026"
    assert cda._date_range(text) == (date(2026, 7, 6), date(2026, 7, 11))


# --- _genres ------------------------------------------------------------------


def test_genres_classical_and_repertoire():
    text = "Técnica de ballet\nPuntas\nRepertorio clásico\nTaller coreográfico"
    genres = cda._genres(text)
    assert "classical" in genres
    assert "repertoire" in genres


def test_genres_includes_contemporary_when_moderno():
    text = "Técnica de ballet\nModerno\nRepertorio clásico"
    genres = cda._genres(text)
    assert "contemporary" in genres


def test_genres_default_classical_no_keywords():
    # Prose without curriculum keywords → fallback to classical
    genres = cda._genres("descripción general del programa sin palabras clave")
    assert genres == ["classical"]


# --- _prices ------------------------------------------------------------------


def test_prices_training_and_housing():
    text = "training\n1.100€\n(1 semana)\nhousing\n770€\n(1 semana)"
    prices = cda._prices(text)
    assert len(prices) == 2
    training = next(p for p in prices if p.label == "Training")
    housing = next(p for p in prices if p.label == "Housing")
    assert training.amount == 1100.0
    assert training.currency == "EUR"
    assert "tuition" in training.includes
    assert housing.amount == 770.0
    assert "accommodation" in housing.includes
    assert "meals" in housing.includes


def test_prices_training_only():
    text = "training 850€"
    prices = cda._prices(text)
    assert len(prices) == 1
    assert prices[0].label == "Training"
    assert prices[0].amount == 850.0


def test_prices_none_when_absent():
    assert cda._prices("sin información de tarifas") == []


# --- _teachers ----------------------------------------------------------------


def test_teachers_all_present():
    text = "Ángel Corella Carmen Corella Dayron Vera Russell Ducker Andrea Rodriguez"
    teachers = cda._teachers(text)
    names = [t.name for t in teachers]
    assert "Ángel Corella" in names
    assert "Carmen Corella" in names
    assert "Dayron Vera" in names
    assert "Russell Ducker" in names
    assert "Andrea Rodriguez" in names


def test_teachers_subset():
    # Only Angel and Carmen mentioned on hypothetical future page.
    text = "Profesores: Ángel Corella y Carmen Corella"
    teachers = cda._teachers(text)
    names = [t.name for t in teachers]
    assert names == ["Ángel Corella", "Carmen Corella"]


def test_teachers_empty_when_none_found():
    assert cda._teachers("no faculty listed") == []


# --- _build_offerings (integration) ------------------------------------------

_MINIMAL_HTML = """\
<html><body>
<div>Del 6 al 11 de julio de 2026</div>
<h1>Company Workshop con Ángel Corella</h1>
<p>Plazas abiertas</p>
<p>Técnica de ballet</p>
<p>Puntas / Men's allegro</p>
<p>Repertorio clásico</p>
<p>Taller coreográfico</p>
<p>Moderno</p>
<p>Profesores</p>
<p>Ángel Corella</p>
<p>Carmen Corella</p>
<p>Dayron Vera</p>
<p>Russell Ducker</p>
<p>Andrea Rodriguez</p>
<p>training 1.100€ (1 semana)</p>
<p>housing 770€ (1 semana)</p>
<p>Développé à la seconde</p>
<p>Primer Arabesque</p>
</body></html>"""


def test_build_offerings_happy_path():
    offerings = cda._build_offerings(_MINIMAL_HTML, date(2026, 6, 8))
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "corella-dance-academy/angel-corella-workshop-2026"
    assert o.schedule.start == date(2026, 7, 6)
    assert o.schedule.end == date(2026, 7, 11)
    assert o.schedule.season == "2026"
    assert o.schedule.timezone == "Europe/Madrid"
    assert "classical" in o.genres
    assert "repertoire" in o.genres
    assert o.level == ["pre-professional"]

    # location
    assert o.location is not None
    assert o.location.country == "ES"
    assert o.location.city == "Barcelona"

    # prices
    amounts = {p.label: p.amount for p in o.prices}
    assert amounts["Training"] == 1100.0
    assert amounts["Housing"] == 770.0

    # application
    assert o.application.status == "open"
    reqs = o.application.requirements
    assert len(reqs) == 1
    req = reqs[0]
    assert req.type == "photos"
    assert req.specificity == "defined-poses"  # type: ignore[union-attr]
    assert len(req.poses) == 2  # type: ignore[union-attr]

    # teachers
    teacher_names = [t.name for t in o.teachers]
    assert "Ángel Corella" in teacher_names
    assert "Carmen Corella" in teacher_names


def test_build_offerings_no_dates_returns_empty():
    html = "<html><body><p>Próximas fechas disponibles próximamente.</p></body></html>"
    assert cda._build_offerings(html, date(2026, 6, 8)) == []


def test_build_offerings_source_fields():
    offerings = cda._build_offerings(_MINIMAL_HTML, date(2026, 6, 8))
    src = offerings[0].source
    assert src.provider == "corella-dance-academy"
    assert "corella" in src.url
