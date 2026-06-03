"""Unit tests for the Joffrey scraper's parsing — dates, genre scoping, location.

Joffrey's data is thin and inconsistent (sparse dates, no fees, taxonomy on
intensives but not workshops), so these pin the judgement calls: a range is the
only thing trusted for a span, scope is decided by taxonomy-or-title, and the
body is a last-resort genre signal for multi-genre workshops. Inline strings, no
network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import joffrey_ballet_school as jbs

STYLES = {70: "Ballet", 185: "Contemporary Ballet", 71: "Jazz & Contemporary", 77: "Musical Theater"}
LOCATIONS = {86: "New York", 254: "Switzerland", 90: "Florida", 104: "All"}


# --- dates --------------------------------------------------------------------


def test_same_month_range_with_year():
    assert jbs._parse_dates("August 12-14, 2026") == (date(2026, 8, 12), date(2026, 8, 14), "2026")


def test_cross_month_range():
    assert jbs._parse_dates("runs July 27 – August 7, 2026") == (
        date(2026, 7, 27),
        date(2026, 8, 7),
        "2026",
    )


def test_range_without_year_inherits_body_year():
    assert jbs._parse_dates("Dates July 19–31. Apply for the 2027 season.") == (
        date(2027, 7, 19),
        date(2027, 7, 31),
        "2027",
    )


def test_range_spanning_year_boundary():
    start, end, season = jbs._parse_dates("December 30 – January 4, 2026")
    assert (start, end, season) == (date(2026, 12, 30), date(2027, 1, 4), "2026")


def test_lone_date_is_not_treated_as_a_span():
    # A single prose date (a performance, not the course) must not set start/end.
    assert jbs._parse_dates("Perform at a theater on Friday, July 17, 2026.") == (None, None, "2026")


def test_no_dates_no_year():
    assert jbs._parse_dates("An immersive summer program.") == (None, None, "unknown")


# --- genres & scope -----------------------------------------------------------


def test_genres_from_taxonomy():
    assert jbs._genres([70], STYLES, "any", "any") == ["classical"]
    assert jbs._genres([185], STYLES, "any", "any") == ["contemporary"]


def test_out_of_scope_taxonomy_style_dropped():
    # Musical Theater has no in-scope mapping and the title names it → dropped.
    assert jbs._genres([77], STYLES, "NYC Musical Theater Intensive", "body") == []


def test_workshop_genres_from_title_when_no_taxonomy():
    assert jbs._genres([], {}, "Joffrey NY Contemporary Ballet Winter Workshop", "") == [
        "contemporary",
        "classical",
    ]


def test_workshop_genres_fall_back_to_body():
    # City-only title, but the body reveals a multi-genre ballet/contemporary workshop.
    assert jbs._genres([], {}, "Joffrey Canada Workshop", "ballet, contemporary and jazz") == [
        "contemporary",
        "classical",
    ]


def test_out_of_scope_title_beats_in_scope_body():
    # A hip-hop-titled workshop isn't ours even if its body mentions ballet.
    assert jbs._genres([], {}, "NYC Hip Hop Winter Workshop", "some ballet too") == []


# --- location -----------------------------------------------------------------


def test_location_skips_meta_term():
    assert jbs._location([104, 90], LOCATIONS) == (None, "US")  # "All" skipped, Florida → US


def test_location_city_when_known():
    assert jbs._location([86], LOCATIONS) == ("New York", "US")


def test_location_international_country():
    assert jbs._location([254], LOCATIONS) == (None, "CH")


def test_location_only_meta_is_empty():
    assert jbs._location([104], LOCATIONS) == (None, None)
