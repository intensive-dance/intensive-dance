"""Unit tests for the English National Ballet Youth Dance Intensive scraper.

Pin the two-tier date spans (single trailing abbreviated month), GBP fee
extraction, overview-scoped age range, level mapping per tier, venue, and the
raise on a degraded (no date span) fetch.  Inline HTML, no network.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import english_national_ballet_youth_intensive as m

_ADVANCED_HTML = """\
<html><body>
<h1>Youth Dance Summer Intensive – Advanced</h1>
<div class="introduction-details__date"><span class="introduction-date">Mon 3 - Fri 7 Aug 2026</span></div>
<div class="introduction-details__fee"><p class="fw-bold">Fee</p>£330</div>
<div class="overview"><p><strong>For dancers aged 14 – 19 years, training at pre-vocational or vocational level,</strong> our advanced summer intensive refines ballet and contemporary technique.</p></div>
</body></html>
"""

_INTERMEDIATE_HTML = """\
<html><body>
<h1>Youth Dance Summer Intensive – Intermediate</h1>
<span class="introduction-date">Wed 29 - Fri 31 Jul 2026</span>
<div class="introduction-details__fee"><p class="fw-bold">Fee</p>£180</div>
<p>For dancers aged 12 – 16 years, with dance experience, this intensive builds ballet and contemporary technique.</p>
</body></html>
"""

_DEGRADED_HTML = (
    "<html><body><h1>Youth Dance Summer Intensive – Advanced</h1><p>Coming soon.</p></body></html>"
)


def test_advanced_dates_and_season():
    off = m._build_offering(_ADVANCED_HTML, "advanced", "https://example.com")
    assert off.id == "english-national-ballet-youth-intensive/advanced-2026"
    assert off.title == "Youth Dance Summer Intensive — Advanced"
    assert (off.schedule.start, off.schedule.end) == (date(2026, 8, 3), date(2026, 8, 7))
    assert off.schedule.notes == "Mon 3 - Fri 7 Aug 2026"
    assert off.schedule.timezone == "Europe/London"


def test_advanced_age_level_genres():
    off = m._build_offering(_ADVANCED_HTML, "advanced", "https://example.com")
    assert off.age_range == {"min": 14, "max": 19}
    assert off.level == ["advanced", "pre-professional"]
    assert off.genres == ["classical", "contemporary"]


def test_advanced_price_and_location():
    off = m._build_offering(_ADVANCED_HTML, "advanced", "https://example.com")
    assert len(off.prices) == 1
    p = off.prices[0]
    assert p.amount == 330.0
    assert p.currency == "GBP"
    assert p.type == "tuition"
    assert p.includes == ["tuition"]
    assert off.location is not None
    assert off.location.venue == "Mulryan Centre for Dance"
    assert off.location.city == "London"
    assert off.location.country == "GB"


def test_intermediate_dates_and_id():
    off = m._build_offering(_INTERMEDIATE_HTML, "intermediate", "https://example.com")
    assert off.id == "english-national-ballet-youth-intensive/intermediate-2026"
    assert off.title.endswith("Intermediate")
    assert (off.schedule.start, off.schedule.end) == (date(2026, 7, 29), date(2026, 7, 31))


def test_intermediate_age_level_price():
    off = m._build_offering(_INTERMEDIATE_HTML, "intermediate", "https://example.com")
    assert off.age_range == {"min": 12, "max": 16}
    assert off.level == ["intermediate"]
    assert len(off.prices) == 1
    assert off.prices[0].amount == 180.0
    assert off.prices[0].currency == "GBP"


def test_degraded_raises():
    with pytest.raises(ValueError):
        m._build_offering(_DEGRADED_HTML, "advanced", "u")
