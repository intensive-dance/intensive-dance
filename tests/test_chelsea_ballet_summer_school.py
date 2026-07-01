"""Unit tests for the Chelsea Ballet Summer School scraper.

Pin the English day-prefixed date span with trailing month, open-topped adult
age (min 18, no max), classical + pointe + repertoire genres, teacher roster,
and degraded-fixture raise. Inline HTML, no network.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import chelsea_ballet_summer_school as m

_HTML = """
<html><body>
<h1>Chelsea Ballet</h1>
<p>We are delighted that the Chelsea Ballet Summer School will return on Monday 10
- Saturday 15 August 2026 at the new location of famous dance school ArtsEd,
Chiswick.</p>
<p>Take part in classes including ballet, pointe, repertoire, PBT and more, from
renowned teachers Nina Thilas-Mohs, Richard Ramsey, Bethany Ramsey and Naomi
Smart.</p>
<p>The summer school is open to anyone over the age of 18 with an elementary and
above standard of ballet.</p>
</body></html>
"""

_BAD = "<html><body><h1>Chelsea Ballet</h1><p>Coming soon.</p></body></html>"


def test_date_range():
    o = m._build_offering(_HTML)
    assert (o.schedule.start, o.schedule.end) == (date(2026, 8, 10), date(2026, 8, 15))
    assert o.schedule.season == "2026"


def test_open_topped_adult_age():
    o = m._build_offering(_HTML)
    assert o.age_range == {"min": 18}


def test_genres():
    o = m._build_offering(_HTML)
    # PBT dropped (conditioning, not a genre)
    assert o.genres == ["classical", "pointe", "repertoire"]


def test_teachers():
    o = m._build_offering(_HTML)
    assert [t.name for t in o.teachers] == [
        "Nina Thilas-Mohs",
        "Richard Ramsey",
        "Bethany Ramsey",
        "Naomi Smart",
    ]


def test_location():
    o = m._build_offering(_HTML)
    assert o.location is not None
    assert o.location.venue == "ArtsEd, Chiswick"
    assert o.location.city == "London"


def test_raises_on_degraded():
    with pytest.raises(ValueError):
        m._build_offering(_BAD)
