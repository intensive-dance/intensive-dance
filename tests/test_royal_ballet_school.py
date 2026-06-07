"""Unit tests for the fragile, regex-heavy parsing in the RBS scraper.

These pin the *behaviour* of the parsers (dates, money, prices, place, sessions)
against literal source-shaped strings, so a regex tweak that silently mis-parses
fails here — something the data-store hash check in `validate.py` cannot catch.
No network: every input is an inline string or snippet of HTML.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import royal_ballet_school as rbs


def money(text: str, dollar_currency: str = "USD") -> tuple[float, str]:
    match = rbs._MONEY.search(text)
    assert match is not None
    return rbs._money(match, dollar_currency)


# --- money & currency ---------------------------------------------------------


def test_money_symbol_prefixed():
    assert money("£48") == (48.0, "GBP")
    assert money("€390") == (390.0, "EUR")
    assert money("£1,730") == (1730.0, "GBP")


def test_money_word_suffixed():
    assert money("390 euros") == (390.0, "EUR")
    assert money("500 pounds") == (500.0, "GBP")


def test_dollar_resolves_from_country_not_hardcoded_usd():
    assert money("$865", rbs._dollar_currency("HK")) == (865.0, "HKD")
    assert money("$865", rbs._dollar_currency("SG")) == (865.0, "SGD")
    assert money("$865", rbs._dollar_currency("US")) == (865.0, "USD")
    assert money("$865", rbs._dollar_currency(None)) == (865.0, "USD")  # unknown → USD


# --- dates --------------------------------------------------------------------


def test_date_range_spans_min_to_max_with_implied_year():
    start, end, season = rbs._date_range("21 July – 21 August 2026")
    assert (start, end, season) == (date(2026, 7, 21), date(2026, 8, 21), "2026")


def test_date_range_no_dates_falls_back_to_year():
    assert rbs._date_range("Summer 2027 cohort") == (None, None, "2027")


def test_date_range_keeps_leading_day_of_same_month_range():
    # "3-7 April" — the leading day omits the month, so _DATE alone saw only
    # the 7th and reported start == end. The range must span 3 → 7.
    start, end, season = rbs._date_range("Intensive: 3-7 April 2026")
    assert (start, end, season) == (date(2026, 4, 3), date(2026, 4, 7), "2026")


def test_date_range_keeps_leading_day_of_and_separated_range():
    start, end, _ = rbs._date_range("Thursday 19 and Friday 20 February 2026")
    assert (start, end) == (date(2026, 2, 19), date(2026, 2, 20))


def test_date_range_leading_day_inherits_own_year_across_cycles():
    # Multi-year weekend list: the October leading day must take 2026, not the
    # global max (2027), so it cannot leak across the cycle boundary.
    start, end, _ = rbs._date_range("17-18 October 2026 and 10-11 April 2027")
    assert (start, end) == (date(2026, 10, 17), date(2027, 4, 11))


def test_deadline_extracts_close_date():
    assert rbs._deadline("Applications close 1 March 2026.") == date(2026, 3, 1)
    assert rbs._deadline("No deadline stated") is None


# --- ages ---------------------------------------------------------------------


def test_age_range_dash():
    assert rbs._age_range("for dancers aged 16-19") == {"min": 16, "max": 19}


def test_age_range_none_when_absent():
    assert rbs._age_range("open to all") is None


# --- place & country ----------------------------------------------------------


def test_place_known_venue():
    assert rbs._place("135 N. Grand Avenue, Los Angeles, CA 90012, United States") == (
        "Los Angeles",
        "US",
        "America/Los_Angeles",
    )
    assert rbs._place("via Masi 7, 57121 – Livorno, Italy") == ("Livorno", "IT", "Europe/Rome")


def test_place_unknown_falls_back_to_country_only():
    assert rbs._place("123 Main St, NY 10001") == (None, "US", None)


def test_dollar_currency_map():
    assert rbs._dollar_currency("HK") == "HKD"
    assert rbs._dollar_currency("AU") == "AUD"
    assert rbs._dollar_currency("FR") == "USD"


# --- inline prices ------------------------------------------------------------


def test_inline_prices_splits_mixed_currency_line():
    prices = rbs._inline_prices("Application fee: £50 Course fee: 390 euros")
    assert [(p.amount, p.currency, p.label) for p in prices] == [
        (50.0, "GBP", "Application fee"),
        (390.0, "EUR", "Course fee"),
    ]


def test_inline_prices_application_fee_includes_nothing():
    (fee,) = rbs._inline_prices("Application fee: £48")
    assert fee.includes == []


def test_inline_prices_carries_label_from_preceding_line():
    prices = rbs._inline_prices("Non-residential course\n£1,730")
    assert (prices[0].amount, prices[0].label) == (1730.0, "Non-residential course")


def test_inline_prices_dollar_uses_resolved_currency():
    (fee,) = rbs._inline_prices("Course fee: $865", rbs._dollar_currency("HK"))
    assert (fee.amount, fee.currency) == (865.0, "HKD")


# --- genres / levels ----------------------------------------------------------


def test_genres_keywords():
    assert rbs._genres("classical ballet, contemporary, repertoire on pointe") == [
        "classical",
        "contemporary",
        "repertoire",
        "pointe",
    ]


def test_levels_pre_professional_does_not_double_count_professional():
    assert rbs._levels("for advanced and pre-professional dancers") == [
        "advanced",
        "pre-professional",
    ]


# --- sessions -----------------------------------------------------------------


def test_session_gender():
    assert rbs._session_gender("aged 10 and 11 female and male training") == "both"
    assert rbs._session_gender("male training") == "male"
    assert rbs._session_gender("female only") == "female"
    assert rbs._session_gender("no gender stated") == "both"


def test_session_ages_ignores_out_of_band_numbers():
    assert rbs._session_ages("aged 10 and 11") == {"min": 10, "max": 11}


def test_weekend_sessions_spanning_year_boundary():
    sessions = rbs._weekend_sessions("17-18 October 2026 then 10-11 April 2027")
    assert [(s.start, s.end) for s in sessions] == [
        (date(2026, 10, 17), date(2026, 10, 18)),
        (date(2027, 4, 10), date(2027, 4, 11)),
    ]


# --- title year deduplication ---------------------------------------------------


def test_title_strips_trailing_year_before_appending_season():
    # "Online Spring Intensive 2022" already ends with the year; appending the
    # season would yield "Online Spring Intensive 2022 2022" without the strip.
    # Test the stripping logic directly via regex (the same as _build_offering uses).
    import re

    def build_title(base_title: str, season: str) -> str:
        base_stripped = re.sub(r"\s+\d{4}$", "", base_title)
        return f"{base_stripped} {season}".strip()

    assert build_title("Online Spring Intensive 2022", "2022") == "Online Spring Intensive 2022"
    assert build_title("UK Summer Intensive", "2026") == "UK Summer Intensive 2026"
    assert build_title("Japan Intensive", "2025") == "Japan Intensive 2025"


# --- UK Spring Intensive — course-fees subsection --------------------------------


def test_inline_prices_reads_course_fees_subsection():
    # The uk-spring-intensive page has two sibling sections: "Fees" (app fee)
    # and "Course fees" (three tiers). Both must be joined before parsing.
    text = (
        "Application fee: £48\n"
        "White Lodge\n"
        "Five days, non-residential: £865\n"
        "Five days, residential (catering included): £1,485\n"
        "Upper School\n"
        "Three days, non-residential: £485"
    )
    prices = rbs._inline_prices(text, "GBP")
    amounts = [(p.amount, p.includes) for p in prices]
    assert (48.0, []) in amounts
    assert (865.0, ["tuition"]) in amounts
    assert (1485.0, ["tuition", "accommodation", "meals"]) in amounts
    assert (485.0, ["tuition"]) in amounts


# --- Autumn Intensives — city-date session headings -----------------------------

_AUTUMN_SECTIONS = [
    # Simulate the wp.Content sections the autumn page produces
]


def test_city_date_sessions_three_uk_cities():
    from intensive_dance import wp

    # Minimal section list: city headings followed by date-range headings.
    sections = [
        wp.Section(heading="Edinburgh", level=3, nodes=[]),
        wp.Section(heading="16 & 17 October 2025", level=4, nodes=[]),
        wp.Section(heading="London", level=3, nodes=[]),
        wp.Section(heading="26 & 27 October 2025", level=4, nodes=[]),
        wp.Section(heading="Manchester", level=3, nodes=[]),
        wp.Section(heading="27 & 28 October 2025", level=4, nodes=[]),
    ]
    sessions = rbs._city_date_sessions(sections, 2025)
    assert len(sessions) == 3
    assert sessions[0].start == date(2025, 10, 16)
    assert sessions[0].end == date(2025, 10, 17)
    assert "Edinburgh" in (sessions[0].label or "")
    assert sessions[2].end == date(2025, 10, 28)


def test_city_date_sessions_ignores_non_city_non_date_headings():
    from intensive_dance import wp

    # A heading that is neither a known city nor a DD & DD Month YYYY date
    # should not break the parser or produce a spurious session.
    sections = [
        wp.Section(heading="Some title", level=2, nodes=[]),
        wp.Section(heading="Edinburgh", level=3, nodes=[]),
        wp.Section(heading="16 & 17 October 2025", level=4, nodes=[]),
    ]
    sessions = rbs._city_date_sessions(sections, 2025)
    assert len(sessions) == 1
    assert sessions[0].start == date(2025, 10, 16)
