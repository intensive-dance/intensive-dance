"""Unit tests for the IDC Berlin scraper (Wix, one page, two parts).

These pin the regex parsing of the `/summer` page: the two dated parts with
their distinct Berlin venues and showcases, the open-ended age floor, the
`open` level, the four EUR tuition tiers, the curriculum genres, the
full/waitlist → `closed` status, and the explicit `none` requirement (the page
states it is not an audition). Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import NoneReq
from intensive_dance.scrapers import idc_berlin as idc

_DATES = (
    "PART 1: WAITLIST July 13-18, 2026 Showcase July 18th at 4pm "
    "PART 2: WAITLIST August 10-15, 2026 Showcase August 15th at 4pm "
    "Locations IDC Berlin Part 1 will take place at the Studios of the Staatsballett "
    "Berlin in the Deutsche Oper Address: Richard Wagner St. 10 10585 Berlin "
    "IDC Berlin Part 2: Berlin Dance Institute Address: Egelingzeile 6 12103 Berlin"
)


def test_sessions_two_parts_with_venue_and_showcase():
    sessions = idc._sessions(_DATES)
    assert [(s.label, s.start, s.end) for s in sessions] == [
        ("Part 1", date(2026, 7, 13), date(2026, 7, 18)),
        ("Part 2", date(2026, 8, 10), date(2026, 8, 15)),
    ]
    # Exact notes — guards against the "PART 1: WAITLIST" banner over-capturing
    # the whole page into the venue note.
    assert sessions[0].notes == (
        "Studios of the Staatsballett Berlin in the Deutsche Oper "
        "(Richard Wagner St. 10 10585 Berlin); Showcase 18 July at 4pm"
    )
    assert sessions[1].notes == (
        "Berlin Dance Institute (Egelingzeile 6 12103 Berlin); Showcase 15 August at 4pm"
    )
    assert "WAITLIST" not in (sessions[0].notes or "")


def test_sessions_dedupe_repeated_date_string():
    # The "July 13-18, 2026" string also appears in the teachers header; the same
    # (start, end) must not yield a duplicate Part.
    text = "July 13-18, 2026 ... Meet our Teachers Part 1 July 13-18, 2026 Ballet"
    sessions = idc._sessions(text)
    assert len(sessions) == 1
    assert sessions[0].label == "Part 1"


def test_age_range_open_ended():
    assert idc._age_range("Dancers ages 7+ are welcome") == {"min": 7}


def test_levels_open():
    assert idc._levels("Open for all levels- from hobby dancers to professional students") == [
        "open"
    ]


def test_prices_four_tuition_tiers():
    text = (
        "Tuition One Intensive: Violet: 360 Euro Indigo/ Aqua: 485 Euro "
        "Both Intensives: Violet: 650 Euro Indigo/ Aqua: 890 Euro "
        "Boys may apply for scholarship!"
    )
    prices = idc._prices(text)
    assert [(p.amount, p.currency, p.label, p.includes) for p in prices] == [
        (360.0, "EUR", "One Intensive — Violet", ["tuition"]),
        (485.0, "EUR", "One Intensive — Indigo/ Aqua", ["tuition"]),
        (650.0, "EUR", "Both Intensives — Violet", ["tuition"]),
        (890.0, "EUR", "Both Intensives — Indigo/ Aqua", ["tuition"]),
    ]


def test_genres():
    text = "Dancers will take classes in Ballet, Variations, Repertoire, Commercial, Modern, Lyrical Dance."
    assert idc._genres(text) == ["classical", "repertoire", "contemporary"]


def test_status_closed_when_full_waitlist():
    assert idc._status("PART 1- JULY 13-18 ( FULL ) // PART 2 WAITLIST") == "closed"


def test_requirements_none_not_an_audition():
    reqs = idc._requirements("This is not an audition and does not affect acceptance.")
    assert len(reqs) == 1
    assert isinstance(reqs[0], NoneReq)


def test_requirements_absent_when_not_stated():
    assert idc._requirements("Train with today's top professionals.") == []
