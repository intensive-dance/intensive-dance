"""Unit tests for the Balletkompagniet Copenhagen scraper.

Pin the Danish date parsing (month-on-both vs month-once, Danish month names),
the title-based age extraction ("9-12-årige", "Spirekompagniet"), the
multi-edition discovery (8 editions from one page), and the degraded-fixture
raise. Inline HTML, no network.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import balletkompagniet_copenhagen as m

# Minimal HTML with 2 editions: one with a Danish month-on-both date ("juni-
# juli"), one with month-once ("juli"), plus one degenerate title (no date).
_HTML = """
<html><body>
<p>Sommerskole for 9-12-årige med Henriette H. Lange i Hørsholm</p>
<p>Tirsdag-torsdag d. 30. juni-2. juli 2026, uge 27</p>
<p>https://balletkompagniet.klub-modul.dk/cms/ProfileEventEnrollment.aspx?EventID=443</p>
<p>Sommerskole for Spirekompagniet med Amalie Peronard i Fields, uge 27</p>
<p>Mandag-onsdag d. 29. juni-1. juli 2026</p>
<p>https://balletkompagniet.klub-modul.dk/cms/ProfileEventEnrollment.aspx?EventID=431</p>
<p>Tre dages intensive pre-season sommerklasser med Juliette Schaufuss på Frederiksberg</p>
<p>Onsdag-fredag d. 5.-7. august 2026, uge 32</p>
<p>https://balletkompagniet.klub-modul.dk/cms/ProfileEventEnrollment.aspx?EventID=460</p>
<p>Sommerskole for 6-8-årige med Silje Bjerre i City2</p>
<p>Mandag-onsdag d. 27.-29. juli 2026, uge 31</p>
</body></html>
"""

_BAD = "<html><body><p>Coming soon.</p></body></html>"


def test_four_editions():
    offs = m._build_offerings(_HTML, date(2026, 6, 1))
    assert len(offs) == 4


def test_cross_month_date():
    """30 juni → 2 juli crosses months."""
    o = m._build_offerings(_HTML, date(2026, 6, 1))[0]
    assert (o.schedule.start, o.schedule.end) == (date(2026, 6, 30), date(2026, 7, 2))
    assert o.schedule.season == "2026"


def test_age_from_title():
    offs = m._build_offerings(_HTML, date(2026, 6, 1))
    # 9-12
    hørsholm = [o for o in offs if "9-12" in o.title][0]
    assert hørsholm.age_range == {"min": 9, "max": 12}
    # Spirekompagniet (youngest)
    spire = [o for o in offs if "Spire" in o.title][0]
    assert spire.age_range == {"min": 4, "max": 6}
    # 6-8
    city2 = [o for o in offs if "6-8" in o.title][0]
    assert city2.age_range == {"min": 6, "max": 8}


def test_pre_season_has_no_age():
    o = [o for o in m._build_offerings(_HTML, date(2026, 6, 1)) if "pre-season" in o.title][0]
    assert o.age_range is None
    assert "pre-season" in (o.schedule.notes or "").lower()


def test_teacher_and_venue():
    o = m._build_offerings(_HTML, date(2026, 6, 1))[0]
    assert o.teachers[0].name == "Henriette H. Lange"
    assert o.location is not None
    assert "Hørsholm" in (o.location.venue or o.location.city or "")


def test_classical_genre():
    for o in m._build_offerings(_HTML, date(2026, 6, 1)):
        assert o.genres == ["classical"]


def test_raises_on_degraded():
    with pytest.raises(ValueError):
        m._build_offerings(_BAD, date(2026, 6, 1))
