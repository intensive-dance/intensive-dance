"""Unit tests for the GradPro Summer Intensive scraper (single Wix page).

Pin the two-Offering split (one per week / cohort), the ordinal + weekday date
spans, the curriculum-driven genres, the pre-professional level, and the
fail-open raise when the week markers are missing. Inline HTML, no network.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import gradpro_summer_intensive as g

# Mirrors the live page: Wix zero-width spaces inside the date tokens, two weeks
# with distinct cohorts, a stray G2P closing date that must NOT be picked up.
_HTML = """
<html><body>
<h1>SUMMER INTENSIVE COURSES 2026</h1>
<p>GradPro is running Summer Intensive Courses at The Dance Hub in Birmingham Royal Ballet from</p>
<p>Week 1: Monday 20​th July to Friday 24th July 2026 inclusive.</p>
<p>Week 2: Monday 27th July to Friday 31st July 2026 inclusive.</p>
<p>Open to students in their first or second year of vocational training. This is
an amazing opportunity to take company style class taught by industry
professionals, with repertoire, virtuosity and technique, pas de deux and pointe work.</p>
<p>G2P Pre Professional Stage 2026 Closing Date: 5th July 2026</p>
</body></html>
"""


def test_emits_one_offering_per_week():
    offerings = g._build_offerings(_HTML)
    assert [o.id for o in offerings] == [
        "gradpro-summer-intensive/summer-intensive-week-1-2026",
        "gradpro-summer-intensive/summer-intensive-week-2-2026",
    ]


def test_week_dates_parsed_with_ordinals_and_zero_width():
    w1, w2 = g._build_offerings(_HTML)
    assert (w1.schedule.start, w1.schedule.end) == (date(2026, 7, 20), date(2026, 7, 24))
    assert (w2.schedule.start, w2.schedule.end) == (date(2026, 7, 27), date(2026, 7, 31))
    assert w1.schedule.season == "2026"


def test_genres_and_level():
    w1, _ = g._build_offerings(_HTML)
    assert w1.genres == ["classical", "repertoire", "pointe"]
    assert w1.level == ["pre-professional"]


def test_location_and_cohort_note():
    w1, w2 = g._build_offerings(_HTML)
    assert w1.location is not None
    assert w1.location.city == "Birmingham"
    assert w1.location.country == "GB"
    assert "first year" in (w1.schedule.notes or "")
    assert "second year" in (w2.schedule.notes or "")


def test_application_url_no_invented_fields():
    w1, _ = g._build_offerings(_HTML)
    # The stray G2P "5th July" closing date must not leak onto the intensive.
    assert w1.application.deadline is None
    assert w1.application.status is None
    assert w1.application.requirements == []
    assert w1.application.url == g.APPLY_PAGE
    assert w1.prices == []
    assert w1.age_range is None


def test_raises_when_no_week_markers():
    with pytest.raises(ValueError):
        g._build_offerings("<html><body><p>Tickets on sale now.</p></body></html>")
