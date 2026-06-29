"""Unit tests for the PHP Ballet Intensive scraper (single Wix page).

Pin the two-edition discovery, the numeric DD.MM date spans (incl. the typo'd
year "20269" → 2026 and the cross-month range), ages, curriculum genres,
pre-professional level, teacher attribution, and the fail-open raise. Inline
HTML, no network.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import php_ballet_intensive as p

_HTML = """
<html><body>
<h1>PHP Ballet Intensive Course</h1>
<p>Designed for young pre-professional students from 7 to 15 years old.</p>
<p>They will be systematically taught: Floor barre, Ballet Class, Work on Pointe,
Classical Variation, Stretch.</p>
<p>Created by principal dancers Kateryna Shalkina and Oscar Chacon.</p>
<p>PHP Ballet Intensive</p>
<p>29.06-3.07 20269</p>
<p>10.08-14.08 2026</p>
<p>Event Address: Ecole BeauBallet à Morges</p>
</body></html>
"""


def test_two_editions_with_typo_tolerant_year():
    offerings = p._build_offerings(_HTML)
    assert [o.id for o in offerings] == [
        "php-ballet-intensive/intensive-2026-06-29",
        "php-ballet-intensive/intensive-2026-08-10",
    ]


def test_cross_month_and_same_month_ranges():
    o1, o2 = p._build_offerings(_HTML)
    assert (o1.schedule.start, o1.schedule.end) == (date(2026, 6, 29), date(2026, 7, 3))
    assert (o2.schedule.start, o2.schedule.end) == (date(2026, 8, 10), date(2026, 8, 14))


def test_ages_genres_level():
    o1, _ = p._build_offerings(_HTML)
    assert o1.age_range == {"min": 7, "max": 15}
    assert o1.genres == ["classical", "pointe", "repertoire"]
    assert o1.level == ["pre-professional"]


def test_teachers_names_and_shared_affiliation():
    o1, _ = p._build_offerings(_HTML)
    assert [t.name for t in o1.teachers] == ["Kateryna Shalkina", "Oscar Chacon"]
    assert o1.teachers[0].affiliations[0].organization == "Béjart Ballet Lausanne"


def test_location_and_empty_prices():
    o1, _ = p._build_offerings(_HTML)
    assert o1.location is not None
    assert o1.location.city == "Morges"
    assert o1.location.country == "CH"
    assert o1.prices == []
    assert o1.application.requirements == []


def test_raises_when_no_dates():
    with pytest.raises(ValueError):
        p._build_offerings("<html><body><p>Coming soon.</p></body></html>")
