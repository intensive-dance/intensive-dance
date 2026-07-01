"""Unit tests for the London Children's Ballet Summer School scraper.

Pin the per-edition date parsing (month-on-both vs month-once), age ranges,
sold-out → closed status, NoneReq (explicitly no audition), out-of-scope genre
drop, year from section header, and the degraded-fixture raise. Inline HTML, no
network.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import london_childrens_ballet_summer_school as m

_HTML = """
<html><body>
<h2>2026 Dates</h2>
<p><span><strong>SOLD OUT</strong></span>
<span><strong>Girls Week 1:</strong> Monday 20 July - Friday 24 July (12-14yrs)</span></p>
<p><span><strong>SOLD OUT</strong></span>
<span><strong>Girls Week 2:</strong> Monday 27 July - Friday 31 July (9-11yrs)</span></p>
<p><span><strong>Boys Summer Intensive:</strong> Saturday 29 - Sunday 30 August (9-12yrs)</span></p>
<p>The summer school includes ballet, repertoire, jazz, contemporary, Musical
Theatre, and pointe.</p>
</body></html>
"""

_BAD = "<html><body><h2>Coming soon</h2><p>TBC</p></body></html>"


def test_three_editions():
    offs = m._build_offerings(_HTML, date(2026, 7, 1))
    assert len(offs) == 3


def test_girls_week_1():
    o = m._build_offerings(_HTML, date(2026, 7, 1))[0]
    assert o.id.endswith("/girls-week-1-2026")
    assert (o.schedule.start, o.schedule.end) == (date(2026, 7, 20), date(2026, 7, 24))
    assert o.age_range == {"min": 12, "max": 14}
    assert o.application.status == "closed"
    assert o.application.requirements[0].type == "none"


def test_girls_week_2():
    o = m._build_offerings(_HTML, date(2026, 7, 1))[1]
    assert o.age_range == {"min": 9, "max": 11}
    assert o.application.status == "closed"


def test_boys_intensive():
    o = m._build_offerings(_HTML, date(2026, 7, 1))[2]
    assert "boys" in o.id
    assert (o.schedule.start, o.schedule.end) == (date(2026, 8, 29), date(2026, 8, 30))
    assert o.age_range == {"min": 9, "max": 12}
    assert o.application.status is None  # not sold out


def test_genres_out_of_scope_drop():
    o = m._build_offerings(_HTML, date(2026, 7, 1))[0]
    # jazz and Musical Theatre dropped
    assert o.genres == ["classical", "repertoire", "contemporary", "pointe"]


def test_no_audition():
    for o in m._build_offerings(_HTML, date(2026, 7, 1)):
        assert o.application.requirements[0].type == "none"


def test_raises_on_degraded():
    with pytest.raises(ValueError):
        m._build_offerings(_BAD, date(2026, 7, 1))
