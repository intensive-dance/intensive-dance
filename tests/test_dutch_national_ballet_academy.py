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


def test_course_age_company_experience_week():
    # The live page uses a subheading "Pre-Professional students 16-19 y.o." and
    # prose "give pre-professionals aged 16-19" rather than the ballet-students phrase.
    text_subheading = (
        "The Company Experience Week Pre-Professional students 16-19 y.o. After last year"
    )
    assert dnba._course_age(text_subheading, "Company Experience Week") == {"min": 16, "max": 19}
    text_prose = "The Company Experience Week: to give pre-professionals aged 16-19 the chance"
    assert dnba._course_age(text_prose, "Company Experience Week") == {"min": 16, "max": 19}


def test_course_fee_per_course_and_euro_format():
    text = "Senior Course: €1400 Junior Course: €850 Company Experience Week: €1000 Accommodation (optional): €1.100"
    assert dnba._course_fee(text, "Senior Course") == 1400.0
    assert dnba._course_fee(text, "Junior Course") == 850.0
    assert dnba._course_fee(text, "Company Experience Week") == 1000.0
    assert dnba._course_fee(text, "Accommodation (optional)") == 1100.0


def test_course_dates_read_per_course_from_heading():
    # Each course heading carries its own span; all three courses differ, so a
    # single shared range (the old behaviour) was wrong.
    text = (
        "06 - 17 July 2026 - Senior Course … "
        "13 - 17 July 2026 - Junior Course … "
        "07 - 11 July 2026 - The Company Experience Week …"
    )
    assert dnba._course_dates(text, "Senior Course", "2026") == (
        date(2026, 7, 6),
        date(2026, 7, 17),
    )
    assert dnba._course_dates(text, "Junior Course", "2026") == (
        date(2026, 7, 13),
        date(2026, 7, 17),
    )
    # "The Company Experience Week" heading matches label "Company Experience Week"
    # because _course_dates allows an optional leading "The ".
    assert dnba._course_dates(text, "Company Experience Week", "2026") == (
        date(2026, 7, 7),
        date(2026, 7, 11),
    )


def test_course_dates_none_when_label_absent():
    assert dnba._course_dates("a two week course", "Senior Course", "2026") == (None, None)


def test_genres():
    text = "Classical ballet, solo and pas de deux, repertoire, caracter, contemporary workshops"
    assert dnba._genres(text) == ["classical", "contemporary", "character", "repertoire"]


def test_accommodation_fee():
    # Pattern: €amount … (slug) where slug = label with " Week" stripped.
    text = "€1.100 per week (Senior Course) €500 per week (Junior Course and Company Experience)"
    assert dnba._accommodation_fee(text, "Senior Course") == 1100.0
    assert dnba._accommodation_fee(text, "Junior Course") == 500.0
    assert dnba._accommodation_fee(text, "Company Experience Week") == 500.0
    # No match when label is absent
    assert dnba._accommodation_fee(text, "Unknown Course") is None


def test_build_prices_tuition_and_accommodation():
    prices = dnba._build_prices("Senior Course", 1400.0, 1100.0)
    assert len(prices) == 2
    tuition = prices[0]
    assert tuition.amount == 1400.0
    assert tuition.includes == ["tuition"]
    acc = prices[1]
    assert acc.amount == 1100.0
    assert acc.includes == ["accommodation"]
    assert "meals" not in acc.includes


def test_build_prices_no_accommodation():
    prices = dnba._build_prices("Junior Course", 850.0, None)
    assert len(prices) == 1
    assert prices[0].includes == ["tuition"]


def test_build_prices_no_fee():
    assert dnba._build_prices("Senior Course", None, None) == []
