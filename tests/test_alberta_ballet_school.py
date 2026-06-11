"""Offline tests for the Alberta Ballet School Summer Intensive scraper.

Inline HTML mirrors the server-rendered page: the two date ranges, the disciplines
sentence (for genres), the grade bands, and the audition routes.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import alberta_ballet_school as abs_

HTML = """
<html><body>
<h1>Summer Intensive</h1>
<p>Reach new heights with our three-week Summer Intensive! During this program,
students will train 30 hours per week in ballet, pointe work, contemporary dance,
and other disciplines.</p>
<p>Summer Intensives 2026 June 29 - July 17 and July 20 - August 7</p>
<p>Alberta Ballet School's Summer Intensive is a three-week intensive training
program. It includes ballet, pointe work, pas de deux (for some levels),
repertoire, variations, contemporary dance, character dance and physical
conditioning. In 2026, the Summer Intensive dates are June 29 - July 17, 2026 and
July 20 - August 7, 2026.</p>
<p>Ballet Students in Grades 5-8: register for auditions as a junior student.
Ballet Students in Grades 9-12: register for auditions as a senior student.</p>
<p>Auditioning at one of our Audition Tour locations, online or via video is your
first step. For up-to-date tuition fees, please visit our website.</p>
</body></html>
"""


def test_two_sessions_emitted():
    offerings = abs_._build_offerings(HTML)
    assert [o.id for o in offerings] == [
        "alberta-ballet-school/summer-intensive-2026-session-1",
        "alberta-ballet-school/summer-intensive-2026-session-2",
    ]


def test_session_one_fields():
    o = abs_._build_offerings(HTML)[0]
    assert o.title == "Summer Intensive 2026 (Session 1)"
    assert o.schedule.start == date(2026, 6, 29)
    assert o.schedule.end == date(2026, 7, 17)
    assert o.genres == ["classical", "pointe", "repertoire", "contemporary", "character"]
    assert o.level == ["pre-professional"]
    assert o.age_range == {"min": 10, "max": 18}
    assert "Grades 5-8" in (o.schedule.notes or "")
    assert "30 hours" in (o.schedule.notes or "")
    # In-person OR video audition → video / unspecific.
    assert [r.type for r in o.application.requirements] == ["video"]
    # Tuition not stated on the page → no price invented.
    assert o.prices == []
    assert o.location is not None and o.location.city == "Calgary"


def test_session_two_dates():
    o = abs_._build_offerings(HTML)[1]
    assert o.schedule.start == date(2026, 7, 20)
    assert o.schedule.end == date(2026, 8, 7)
    assert o.schedule.season == "2026"
