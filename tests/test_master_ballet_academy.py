"""Unit tests for the Master Ballet Academy scraper (single Wix page).

These pin the regex parsing of the one Summer Intensive page — the US-format
date range, the curriculum-driven genres (musical theater / flamenco must not
leak, being outside the genre enum), the audition requirements, and the
schedule note. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import master_ballet_academy as mba

_PAGE = (
    "MASTER BALLET ACADEMY SUMMER INTENSIVE 2026 Master Ballet Academy's Summer "
    "Intensive is a very technique focused summer intensive program held at the "
    "Master Ballet Academy studios in Scottsdale, Arizona. The emphasis is on "
    "ballet and ballet technique. This is a well-rounded summer education to "
    "include ballet partnering, variations, stretching, character dance, "
    "contemporary, musical theater, and flamenco. This is a 6-week program held "
    "from June 15, 2026 to July 24, 2026. There is a minimum of 3 weeks required. "
    "A minimum of weeks 4,5, and 6 is required to participate in the Summer "
    "Showcase. Housing is available at additional cost for students age 13 and up. "
    "The program is by audition only. Auditions can be done via Video, Zoom or In "
    "Person. All students auditioning for Summer Intensive will need to submit a "
    "headshot and first arabesque photo. Students who are auditioning by Video "
    "will need to submit a video here in the application."
)


def test_date_range_us_format():
    assert mba._date_range(_PAGE) == (date(2026, 6, 15), date(2026, 7, 24))


def test_date_range_absent():
    assert mba._date_range("no dated edition announced yet") == (None, None)


def test_genres_from_curriculum_no_leak():
    # musical theater / flamenco aren't in the genre enum, so they must not leak.
    assert mba._genres(_PAGE) == ["classical", "repertoire", "character", "contemporary"]


def test_genres_default_classical():
    assert mba._genres("a summer ballet education") == ["classical"]


def test_requirements_audition():
    reqs = mba._requirements(_PAGE)
    types = [r.type for r in reqs]
    assert types == ["headshot", "photos", "video"]
    photo = reqs[1]
    assert photo.type == "photos"
    assert photo.specificity == "defined-poses"
    assert photo.poses == ["first arabesque"]
    video = reqs[2]
    assert video.type == "video"
    assert video.specificity == "unspecific"


def test_schedule_note():
    assert mba._schedule_note(_PAGE) == (
        "6-week program; minimum of 3 weeks required; "
        "weeks 4-6 required to participate in the Summer Showcase"
    )


def test_build_offering_full():
    html = f"<html><body><p>{_PAGE}</p></body></html>"
    offering = mba._build_offering(html)
    assert offering is not None
    assert offering.id == "master-ballet-academy/summer-intensive-2026"
    assert offering.title == "Summer Intensive 2026"
    assert offering.schedule.season == "2026"
    assert offering.schedule.start == date(2026, 6, 15)
    assert offering.schedule.end == date(2026, 7, 24)
    assert offering.location is not None
    assert offering.location.city == "Scottsdale"
    assert offering.location.country == "US"
    # No age/price/deadline stated for the program — fail open.
    assert offering.age_range is None
    assert offering.prices == []
    assert offering.application.deadline is None


def test_build_offering_no_dates_emits_nothing():
    html = "<html><body><p>Summer Intensive — dates to be announced.</p></body></html>"
    assert mba._build_offering(html) is None
