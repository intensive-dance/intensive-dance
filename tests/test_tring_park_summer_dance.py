"""Unit tests for the Tring Park Summer Dance scraper.

Pins the ordinal English date range, age bracket, jazz genre drop, dual
Day-Pupil / Boarder pricing with VAT note, and raise-on-degraded contract.
Inline HTML, no network.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import tring_park_summer_dance as m

_HAPPY = """
<html><head><meta property="og:title" content="Summer Dance Course - Tring Park"></head><body>
<div class="event-detail event-date"><span>When</span>9th August 2026 - 13th August 2026</div>
<div class="event-detail event-ages"><span>Ages</span>10 - 16</div>
<div class="event-detail event-cost"><span>Cost</span>from £457*</div>
<p>Take classes in Classical Ballet, Classical Repertoire, Contemporary and Jazz.</p>
<div class="fees-list bg-purple"><div class="left"><p>Day Pupils</p></div><div class="right"><p>£457</p></div></div>
<div class="fees-list bg-purple"><div class="left"><p>Boarders</p></div><div class="right"><p>£630</p></div></div>
<p>Fees are inclusive of VAT.</p>
</body></html>
"""

_DEGRADED = (
    '<html><body><div class="event-detail event-date"><span>When</span>TBC</div></body></html>'
)


def test_date_range_and_id():
    off = m._build_offering(_HAPPY)
    assert off.id == "tring-park-summer-dance/summer-dance-course-2026"
    assert off.title == "Summer Dance Course 2026"
    assert (off.schedule.start, off.schedule.end) == (date(2026, 8, 9), date(2026, 8, 13))
    assert off.schedule.season == "2026"


def test_schedule_notes_and_timezone():
    off = m._build_offering(_HAPPY)
    assert off.schedule.notes == "9th August 2026 - 13th August 2026"
    assert off.schedule.timezone == "Europe/London"


def test_age_range():
    off = m._build_offering(_HAPPY)
    assert off.age_range == {"min": 10, "max": 16}


def test_genres_jazz_dropped():
    off = m._build_offering(_HAPPY)
    assert off.genres == ["classical", "repertoire", "contemporary"]
    assert "jazz" not in off.genres


def test_location():
    off = m._build_offering(_HAPPY)
    assert off.location is not None
    assert off.location.venue == "Park Studios, Tring Park School"
    assert off.location.city == "Tring"
    assert off.location.country == "GB"


def test_two_prices():
    off = m._build_offering(_HAPPY)
    assert len(off.prices) == 2

    day = off.prices[0]
    assert day.amount == 457.0
    assert day.currency == "GBP"
    assert day.label == "Day Pupils"
    assert day.includes == ["tuition", "meals"]
    assert day.notes == "VAT-inclusive."

    board = off.prices[1]
    assert board.amount == 630.0
    assert board.currency == "GBP"
    assert board.label == "Boarders"
    assert board.includes == ["tuition", "accommodation", "meals"]
    assert board.notes == "VAT-inclusive."


def test_degraded_raises_valueerror():
    with pytest.raises(ValueError):
        m._build_offering(_DEGRADED)
