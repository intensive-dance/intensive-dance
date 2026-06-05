"""Unit tests for the Dutch National Ballet Academy summer-school scraper."""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import dutch_national_ballet_academy as dnba


def test_season_and_deadline():
    assert dnba._season("Amsterdam International Summer School 2026 …") == "2026"
    assert dnba._deadline("applications open until 1 March 2026.") == date(2026, 3, 1)


def test_course_age_per_course():
    text = "Senior Course is for ballet students aged 15-21. Junior Course is for ballet students aged 12-14."
    assert dnba._course_age(text, "Senior Course") == {"min": 15, "max": 21}
    assert dnba._course_age(text, "Junior Course") == {"min": 12, "max": 14}


def test_course_fee_per_course_and_euro_format():
    text = "Senior Course: €1400 Junior Course: €850 Accommodation (optional): €1.100"
    assert dnba._course_fee(text, "Senior Course") == 1400.0
    assert dnba._course_fee(text, "Junior Course") == 850.0
    assert dnba._course_fee(text, "Accommodation (optional)") == 1100.0


def test_amount_handles_european_and_anglo_notation():
    # European thousands ("1.100"), Anglo thousands ("1,400"), and either decimal
    # form must all parse — a comma'd thousands must not collapse to 1.4.
    assert dnba._amount("1400") == 1400.0
    assert dnba._amount("1.100") == 1100.0
    assert dnba._amount("1,400") == 1400.0
    assert dnba._amount("1.299,00") == 1299.0
    assert dnba._amount("1,299.00") == 1299.0
    assert dnba._amount("12,50") == 12.5


def test_date_range_or_none():
    assert dnba._date_range("classes run 6 - 17 July 2026", "2026") == (date(2026, 7, 6), date(2026, 7, 17))
    assert dnba._date_range("a two week course", "2026") == (None, None)


def test_genres():
    text = "Classical ballet, solo and pas de deux, repertoire, caracter, contemporary workshops"
    assert dnba._genres(text) == ["classical", "contemporary", "character", "repertoire"]
