"""Unit tests for The Hammond scraper (single Squarespace summer-school page).

Pin the two-Offering week split, the year-less day-month ranges (year from the
separate "Dates: YYYY" stamp), the ages, the out-of-scope genre drop, the two
price options (residential bundles accommodation), and the fail-open raise.
Inline HTML, no network.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import the_hammond as h

# Mirrors the live page: a "Dates: 2026" stamp, two year-less week ranges, ages,
# a multi-style curriculum (only Ballet + Repertoire are in scope), two fees.
_HTML = """
<html><body>
<h1>Summer School 2026</h1>
<p>For Ages: 7 - 17</p>
<p>Dates: 2026 Week One: Monday, 27th July - Friday, 31st July 09:00 - 16:00
Week Two: Monday, 3rd August - Friday, 7th August 09:00 - 16:00</p>
<p>Cost: Residential - £625 Non-Residential - £385</p>
<p>The curriculum offers training across Ballet, Jazz, Musical Theatre,
Repertoire, and Commercial dance.</p>
<p>Limited non-residential spots now open for application.</p>
</body></html>
"""


def test_two_weeks_with_ids_and_titles():
    offerings = h._build_offerings(_HTML)
    assert [o.id for o in offerings] == [
        "the-hammond/summer-school-2026-week-1",
        "the-hammond/summer-school-2026-week-2",
    ]
    assert offerings[0].title == "Summer School 2026 — Week One"


def test_year_less_ranges_use_year_stamp():
    w1, w2 = h._build_offerings(_HTML)
    assert (w1.schedule.start, w1.schedule.end) == (date(2026, 7, 27), date(2026, 7, 31))
    assert (w2.schedule.start, w2.schedule.end) == (date(2026, 8, 3), date(2026, 8, 7))


def test_ages_and_in_scope_genres_only():
    w1, _ = h._build_offerings(_HTML)
    assert w1.age_range == {"min": 7, "max": 17}
    assert w1.genres == ["classical", "repertoire"]  # Jazz/MT/Commercial dropped


def test_two_price_options_residential_bundles_accommodation():
    w1, _ = h._build_offerings(_HTML)
    by_label = {p.label: p for p in w1.prices}
    assert by_label["Non-residential"].amount == 385
    assert by_label["Non-residential"].includes == ["tuition"]
    res = by_label["Residential"]
    assert res.amount == 625
    assert "accommodation" in res.includes


def test_application_open_status():
    w1, _ = h._build_offerings(_HTML)
    assert w1.application.status == "open"
    assert w1.application.url == h.APPLY_PAGE


def test_raises_without_year_stamp():
    with pytest.raises(ValueError):
        h._build_offerings(
            "<html><body><p>Week One: Monday, 1st July - Friday, 5th July</p></body></html>"
        )
