"""Unit tests for the Paris Opera Ballet School summer-school scraper."""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import ecole_danse_opera_paris as paris


def test_season():
    assert paris._season("The 2026 Summer School will take place …") == "2026"


def test_date_range_ordinal_with_spaces():
    # The page renders the ordinal as a separate token: "July 6 th to 18 th".
    text = "take place from July 6 th to 18 th included"
    assert paris._date_range(text, "2026") == (date(2026, 7, 6), date(2026, 7, 18))


def test_age_range():
    assert paris._age_range("young dancers from age 10 to 19") == {"min": 10, "max": 19}


def test_application_fee():
    assert paris._application_fee("The 51€ of application fees for 2026 are non-refundable") == 51.0
    assert paris._application_fee("no fee stated here") is None


def test_genres_default_classical():
    assert paris._genres("a unique opportunity to train") == ["classical"]
