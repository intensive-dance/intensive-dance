"""Unit tests for the Academy of Northern Ballet scraper (Drupal pages).

These pin the regex parsing of the two intensive tracks: the Seniors page (two
interchangeable weeks → a multi-session schedule, £410/£745 tuition, four named
photo poses) and the Intermediates page (a single week, £375 plus optional
£48/night accommodation, three named poses). Both carry an occasional-video
requirement and a year-less closing date the parser only trusts when its weekday
matches the course year. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import PhotosReq, VideoReq
from intensive_dance.scrapers import northern_ballet_academy as nba

# Source-shaped excerpts of the rendered page text (whitespace already collapsed).
SENIORS = (
    "International Summer Intensive: Seniors Ages 16-19 Years A one-week intensive "
    "to challenge, inspire, and prepare you. "
    "Dates Week 1: Monday 27 July - Friday 31 July 2026 "
    "Week 2: Monday 3 August – Friday 7 August 2026 "
    "Students can attend one or two weeks of summer intensive training. "
    "Price One week £410 Two weeks £745 "
    "Course Content Highlights Daily activation and Classical ballet classes "
    "followed by enhancement classes including: Contemporary Pas De Deux "
    "Variations Pilates Repertoire Men's and women's coaching Observe Company class "
    "Application Process Applicants must complete the online application form, "
    "including uploading required photographs. On occasion applicants may be asked "
    "to submit a short video as part of their application. "
    "Closing date for applications is Friday 29 May subject to availability. "
    "Photo Requirements Where requested on the application forms, photos should be "
    "uploaded. Photos can be taken on a camera or smartphone. "
    "Facing the camera – Demi plié in first position, arms in bras bas "
    "Facing the camera – Tendu á la seconde, arms in second position (either leg) "
    "Facing the camera - Á la seconde en l’air, straight supporting leg, arms in "
    "second position "
    "Profile to the camera – 1st Arabesque on a straight supporting leg Apply Now"
)

INTERMEDIATES = (
    "International Summer Intensive: Intermediates Ages 12-16 Years "
    "Challenge yourself, learn from experts, and be inspired by the world of ballet. "
    "Date Monday 27 - Friday 31 July 2026 Price £375 "
    "Course Content Daily warm up and ballet class alongside enhancement sessions "
    "including (age dependent): Contemporary Drama Pilates Repertoire Pointe prep "
    "Application Process Applicants must complete the online application form, "
    "including uploading required photographs. On occasion applicants may be asked "
    "to submit a short video as part of their application. "
    "Closing date for applications is Thursday 11 June. "
    "Photo Requirements Where requested on the application forms, photos should be "
    "uploaded. "
    "Facing the camera – Demi plié in first position, arms in bras bas "
    "Facing the camera – Tendu á la seconde, arms in second position (either leg) "
    "Profile to the camera – 1st Arabesque on a straight supporting leg Apply Now "
    "Accommodation Our summer intensive is non-residential. "
    "Price: £48 per person per night."
)


def test_seniors_two_interchangeable_weeks():
    sessions = nba._sessions(SENIORS)
    assert [(s.label, s.start, s.end) for s in sessions] == [
        ("Week 1", date(2026, 7, 27), date(2026, 7, 31)),
        ("Week 2", date(2026, 8, 3), date(2026, 8, 7)),
    ]


def test_intermediates_single_week_elided_opening_month():
    # "Monday 27 - Friday 31 July 2026" — opening month omitted, single session.
    sessions = nba._sessions(INTERMEDIATES)
    assert [(s.label, s.start, s.end) for s in sessions] == [
        (None, date(2026, 7, 27), date(2026, 7, 31)),
    ]


def test_sessions_absent():
    assert nba._sessions("no dated weeks here") == []


def test_age_ranges():
    assert nba._age_range(SENIORS) == {"min": 16, "max": 19}
    assert nba._age_range(INTERMEDIATES) == {"min": 12, "max": 16}


def test_seniors_two_tuition_tiers():
    prices = nba._prices(SENIORS)
    assert [(p.label, p.amount, p.currency, p.includes) for p in prices] == [
        ("One week", 410.0, "GBP", ["tuition"]),
        ("Two weeks", 745.0, "GBP", ["tuition"]),
    ]


def test_intermediates_flat_tuition_plus_optional_accommodation():
    prices = nba._prices(INTERMEDIATES)
    assert [(p.label, p.amount, p.currency, p.includes) for p in prices] == [
        (None, 375.0, "GBP", ["tuition"]),
        ("Accommodation (per person per night)", 48.0, "GBP", ["accommodation"]),
    ]


def test_genres():
    assert nba._genres(SENIORS) == ["classical", "contemporary", "repertoire"]
    assert nba._genres(INTERMEDIATES) == [
        "classical",
        "contemporary",
        "repertoire",
        "pointe",
    ]


def test_seniors_four_named_poses_plus_video():
    reqs = nba._requirements(SENIORS)
    photos = next(r for r in reqs if isinstance(r, PhotosReq))
    assert photos.specificity == "defined-poses"
    assert len(photos.poses) == 4
    assert photos.poses[0].startswith("Facing the camera")
    assert "1st Arabesque" in photos.poses[-1]

    video = next(r for r in reqs if isinstance(r, VideoReq))
    assert video.specificity == "unspecific"


def test_intermediates_three_named_poses():
    reqs = nba._requirements(INTERMEDIATES)
    photos = next(r for r in reqs if isinstance(r, PhotosReq))
    assert len(photos.poses) == 3


def test_deadline_trusted_only_when_weekday_matches_year():
    # 29 May 2026 is a Friday → trusted; the wrong-year weekday would be dropped.
    assert nba._deadline(SENIORS, 2026) == date(2026, 5, 29)
    assert nba._deadline(INTERMEDIATES, 2026) == date(2026, 6, 11)
    # Same date string read against 2025 (29 May 2025 is a Thursday) → not Friday.
    assert nba._deadline(SENIORS, 2025) is None


def test_apply_url_per_track():
    html = '<a href="https://northernballet.wufoo.com/forms/w1bbr10y0axntgm/">Apply Now</a>'
    assert nba._apply_url(html) == "https://northernballet.wufoo.com/forms/w1bbr10y0axntgm/"


def test_build_offering_seniors_end_to_end():
    html = (
        f"<html><body>{SENIORS}"
        '<a href="https://northernballet.wufoo.com/forms/w1bbr10y0axntgm/">Apply Now</a>'
        "</body></html>"
    )
    o = nba._build_offering(html, nba.SENIORS, "Seniors")
    assert o is not None
    assert o.id == "northern-ballet-academy/summer-intensive-seniors-2026"
    assert o.title == "International Summer Intensive: Seniors 2026"
    assert o.schedule.start == date(2026, 7, 27)
    assert o.schedule.end == date(2026, 8, 7)
    assert len(o.schedule.sessions) == 2
    assert o.location is not None and o.location.city == "Leeds"
    assert o.application.deadline == date(2026, 5, 29)
    assert o.application.url == "https://northernballet.wufoo.com/forms/w1bbr10y0axntgm/"


def test_build_offering_intermediates_single_session_dropped():
    html = f"<html><body>{INTERMEDIATES}</body></html>"
    o = nba._build_offering(html, nba.INTERMEDIATES, "Intermediates")
    assert o is not None
    assert o.id == "northern-ballet-academy/summer-intensive-intermediates-2026"
    # One week → no session list (a single-item list carries no extra signal).
    assert o.schedule.sessions == []
    assert o.schedule.start == date(2026, 7, 27)
    assert o.schedule.end == date(2026, 7, 31)
