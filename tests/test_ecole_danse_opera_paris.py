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


def test_genres_includes_pointe_from_curriculum():
    # "pointe shoes technique" is listed in the programme for several levels.
    text = "Elémentaire: ballet, folk dance, mime, music, pointe shoes technique"
    genres = paris._genres(text)
    assert "pointe" in genres
    assert "classical" in genres


# --- course fees: four tiers from the practical-information page ----------------

_FEES_TEXT = (
    "Tuition for one week - 2026 (from July 6 th to 11 th or 13 th to 18 th 2026) "
    "Residential (classes, 3 meals and accommodation) Non-residential (classes, lunch and snack) "
    "All levels €1,200 €876 "
    "Tuition for two weeks - 2026 (from July 6 st to 18 th 2026) "
    "Residential (classes, 3 meals and accommodation) Non-residential (classes, lunch and snack) "
    "All levels €2,208 €1,560"
)


def test_course_fees_four_tiers():
    prices = paris._course_fees(_FEES_TEXT)
    by_label = {p.label: p for p in prices}
    assert set(by_label) == {
        "Residential — 1 week",
        "Non-residential — 1 week",
        "Residential — 2 weeks",
        "Non-residential — 2 weeks",
    }
    assert by_label["Residential — 1 week"].amount == 1200.0
    assert by_label["Non-residential — 1 week"].amount == 876.0
    assert by_label["Residential — 2 weeks"].amount == 2208.0
    assert by_label["Non-residential — 2 weeks"].amount == 1560.0


def test_course_fees_residential_includes_accommodation_meals():
    prices = paris._course_fees(_FEES_TEXT)
    residential = [
        p for p in prices if p.label and "residential" in p.label.lower() and "Non" not in p.label
    ]
    for p in residential:
        assert "accommodation" in p.includes
        assert "meals" in p.includes


def test_course_fees_nonresidential_tuition_only():
    prices = paris._course_fees(_FEES_TEXT)
    nonres = [p for p in prices if p.label and p.label.startswith("Non-residential")]
    for p in nonres:
        assert p.includes == ["tuition"]


def test_course_fees_currency_eur():
    prices = paris._course_fees(_FEES_TEXT)
    assert all(p.currency == "EUR" for p in prices)


def test_build_offering_city_nanterre():
    # The venue is on the Nanterre campus, not in Paris.
    text = (
        "The 2026 Summer School will take place from July 6 th to 18 th included. "
        "young dancers from age 10 to 19."
    )
    offering = paris._build_offering(text, date(2026, 6, 1))
    assert offering is not None
    assert offering.location is not None
    assert offering.location.city == "Nanterre"
