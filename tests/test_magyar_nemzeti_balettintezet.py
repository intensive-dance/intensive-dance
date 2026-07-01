"""Unit tests for the Magyar Nemzeti Balettintézet scraper.

Pin the cross-month date range (29 Jun–4 Jul 2026), age 6–17, classical-only
genre, 98 000 HUF price with tuition+meals includes, application deadline,
venue string assembly, and the raise on degraded (dateless) HTML.  Inline
snippets, no network.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import magyar_nemzeti_balettintezet as m

_HTML = """\
<html><body>
<h1>Intensive summer ballet courses at the OPERA</h1>
<p>The Hungarian National Ballet Institute announces a 6-day summer courses
for children between the ages of 6 through 17 who love to dance.</p>
<p>Date of the course: 29 June - 4 July 2026</p>
<p>Classes are held from Monday to Saturday, from 9 a.m. to 4:30 p.m.
Venue: Opera House, 1061 Budapest, Andrássy út 22.</p>
<p>Course fee: 98 000 HUF The price is a gross price that includes the cost
of the lessons and lunch (a two-course, warm meal).</p>
<p>Application deadline: 15 June 2026 (Monday)</p>
<p>Apply via e-mail: balettiskola@opera.hu</p>
</body></html>
"""

_BAD = "<html><body><h1>Summer course</h1><p>Details coming soon.</p></body></html>"


def test_cross_month_date_range():
    off = m._build_offering(_HTML)
    assert off.schedule.start == date(2026, 6, 29)
    assert off.schedule.end == date(2026, 7, 4)
    assert off.id == "magyar-nemzeti-balettintezet/summer-course-2026"
    assert off.title == "Summer Ballet Course 2026"
    assert off.schedule.season == "2026"


def test_age_range():
    off = m._build_offering(_HTML)
    assert off.age_range == {"min": 6, "max": 17}


def test_classical_only_genre():
    off = m._build_offering(_HTML)
    assert off.genres == ["classical"]


def test_price_with_includes():
    off = m._build_offering(_HTML)
    assert len(off.prices) == 1
    assert off.prices[0].amount == 98000.0
    assert off.prices[0].currency == "HUF"
    assert off.prices[0].includes == ["tuition", "meals"]


def test_application_deadline():
    off = m._build_offering(_HTML)
    assert off.application.deadline == date(2026, 6, 15)


def test_venue_assembly():
    off = m._build_offering(_HTML)
    assert off.location is not None
    assert off.location.venue == "Opera House, 1061 Budapest, Andrássy út 22"
    assert off.location.city == "Budapest"
    assert off.location.country == "HU"


def test_timezone():
    off = m._build_offering(_HTML)
    assert off.schedule.timezone == "Europe/Budapest"


def test_raises_on_degraded_html():
    with pytest.raises(ValueError):
        m._build_offering(_BAD)
