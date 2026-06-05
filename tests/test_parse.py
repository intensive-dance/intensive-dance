"""Unit tests for the shared, provider-agnostic parsing helpers.

These pin the consolidated logic that the scrapers used to copy-paste — the money
parser (which two scrapers had diverged on), the genre matcher, whitespace
cleaning, and the month-alternation builder — against literal inputs. No network.
"""

from __future__ import annotations

from intensive_dance import parse


# --- parse_amount: European vs Anglo notation (unified on the DNBA logic) ------


def test_parse_amount_handles_european_and_anglo_notation():
    # European thousands ("1.100"), Anglo thousands ("1,400"), and either decimal
    # form must all parse — a comma'd thousands must not collapse to 1.4.
    assert parse.parse_amount("1400") == 1400.0
    assert parse.parse_amount("1.100") == 1100.0
    assert parse.parse_amount("1,400") == 1400.0
    assert parse.parse_amount("1.299,00") == 1299.0
    assert parse.parse_amount("1,299.00") == 1299.0
    assert parse.parse_amount("12,50") == 12.5


def test_parse_amount_bare_european_thousands_does_not_collapse():
    # The bug in MOSA's old parser: "1.400" must be 1400, not 1.4.
    assert parse.parse_amount("1.400") == 1400.0


def test_parse_amount_mosa_committed_values_unchanged():
    # The amounts MOSA commits today must survive the switch to the shared parser.
    assert parse.parse_amount("749") == 749.0
    assert parse.parse_amount("749.00") == 749.0
    assert parse.parse_amount("1,299.00") == 1299.0
    assert parse.parse_amount("1.299,00") == 1299.0
    assert parse.parse_amount("1,299") == 1299.0


def test_parse_amount_strips_trailing_separators_and_spaces():
    assert parse.parse_amount(" 1 400 ") == 1400.0
    assert parse.parse_amount("950,") == 950.0


def test_parse_amount_returns_none_on_garbage():
    assert parse.parse_amount("free") is None
    assert parse.parse_amount("") is None


# --- match_genres -------------------------------------------------------------

_TABLE = [
    ("classical", ("classical", "ballet")),
    ("contemporary", ("contemporary",)),
    ("repertoire", ("repertoire",)),
]


def test_match_genres_in_table_order_not_text_order():
    assert parse.match_genres("Repertoire and classical ballet", _TABLE) == [
        "classical",
        "repertoire",
    ]


def test_match_genres_default_when_no_match():
    assert parse.match_genres("tap and jazz", _TABLE, default=["classical"]) == ["classical"]


def test_match_genres_empty_when_no_match_and_no_default():
    assert parse.match_genres("tap and jazz", _TABLE) == []


# --- clean & months -----------------------------------------------------------


def test_clean_collapses_whitespace_and_nbsp():
    assert parse.clean("  a\xa0\n  b\t c ") == "a b c"


def test_clean_handles_none_safely():
    assert parse.clean("") == ""


def test_months_alt_builds_alternation_for_any_map():
    assert parse.MONTHALT.startswith("january|february|")
    assert parse.months_alt({"januar": 1, "februar": 2}) == "januar|februar"
