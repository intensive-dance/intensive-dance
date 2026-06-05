"""Unit tests for the fragile, regex-heavy parsing in the RBS scraper and the
shared WPBakery helpers.

These pin the *behaviour* of the parsers (dates, money, prices, place, sessions)
against literal source-shaped strings, so a regex tweak that silently mis-parses
fails here — something the data-store hash check in `validate.py` cannot catch.
No network: every input is an inline string or snippet of HTML.
"""

from __future__ import annotations

from datetime import date

from intensive_dance import wp
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


# --- genres / levels / kind ---------------------------------------------------


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


def test_kind_masterclass_vs_intensive():
    assert rbs._kind("uk-summer-intensive", "UK Summer Intensive") == "intensive"
    assert rbs._kind("guest-masterclass", "Guest Masterclass") == "masterclass"


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


# --- wp helpers ---------------------------------------------------------------


def test_parse_sections_by_heading():
    content = wp.parse("<h2>Dates</h2><p>21 July 2026</p><h3>Fees</h3><p>£48</p>")
    assert content.text("Dates") == "21 July 2026"
    assert content.text("Fees") == "£48"


def test_parse_strips_wpbakery_shortcodes():
    content = wp.parse(
        "[vc_row][vc_column_text]<h2>Location</h2><p>London</p>[/vc_column_text][/vc_row]"
    )
    assert content.text("Location") == "London"


def test_node_lines_recovers_br_separated_lines():
    content = wp.parse("<h2>Venue</h2><p>White Lodge<br>Richmond Park</p>")
    section = content.find("Venue")
    assert section is not None
    (node,) = section.nodes
    assert wp.node_lines(node) == ["White Lodge", "Richmond Park"]


def test_table_rows():
    section = wp.parse(
        "<h2>Fees</h2><table><tr><th>Course</th><th>Fee</th></tr>"
        "<tr><td>Summer</td><td>£485</td></tr></table>"
    ).find("Fees")
    assert section is not None
    table = section.table()
    assert table is not None
    assert wp.table_rows(table) == [["Course", "Fee"], ["Summer", "£485"]]
