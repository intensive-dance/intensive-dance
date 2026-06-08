"""Unit tests for the San Francisco Ballet School Summer Session scraper.

SFB is a WordPress-API scrape of two `content.rendered` page bodies: the audition
page (cycle heading, one dated/aged line per session, a tuition+housing block, the
video-application window) and the landing page (per-session curriculum + level
prose). These pin the judgement calls a hash check can't catch: the year-less
session date line stamped from the "20xx Summer Session" heading, the per-session
tuition/housing split, the deadline from the video window, and the per-session
genre/level extraction (Session II's "contemporary repertoire" + "advanced" /
"pre-professional" that Session I lacks). Inline snippets, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import VideoReq
from intensive_dance.scrapers import san_francisco_ballet_school as sfb

# A faithful reduction of the audition page body: the cycle heading, the two
# session lines (year-less), the per-session tuition+housing block, the video
# window, and the audition policy.
_AUDITION = (
    "LIVE AUDITIONS 2026 Summer Session Spend a month dancing in San Francisco. "
    "Students should audition with the age group based on their age as of July 1, 2026. "
    "Session 1 : Ages 12–15, June 15 – July 10 "
    "Session 2 : Ages 15–18, July 14 – August 8 "
    "The audition fee is $50 and must be paid by credit card online. "
    "Summer Session 1 (ages 12–15) tuition is $3,495 and optional, supervised housing is an "
    "additional $3,495. Housing includes two meals daily. "
    "Summer Session 2 (ages 15–18) tuition is $3,500 and optional, supervised housing is an "
    "additional $3,500. Housing includes two meals daily. "
    "Admission to Sessions I and II is by audition or invitation. "
    "A $75 summer session video audition fee will be charged upon submission. SF Ballet School "
    "will only accept electronic online submissions through Danceapply, between "
    "January 10–February 15, 2026."
)

# Landing page: per-session curriculum + level wording.
_LANDING = (
    "Summer Programs CLASSES SUMMER BALLET CLASSES Weekly classes for dancers ages 2 to 13. "
    "SUMMER SESSION I A four-week session for students ages 12–15, featuring daily classes in "
    "technique, pointe, batterie, pas de deux, repertoire, and conditioning. Supervised dorm "
    "housing is available. "
    "SUMMER SESSION II A four-week advanced session for students ages 15–18. This "
    "pre-professional track includes daily technique, pointe, batterie, pas de deux, "
    "contemporary repertoire, acting workshops, and conditioning. Supervised dorm housing is "
    "available. "
    "SUMMER AUDITIONS Admission to Sessions I and II is by audition or invitation. "
    "ADULT SUMMER WORKSHOP A six-day program for adult dancers. "
    "SUMMER DANCE CAMP A free, week-long summer camp."
)

_URL = "https://www.sfballet.org/the-school/summer-programs/summer-auditions-audition-tour/"


# --- season / deadline --------------------------------------------------------


def test_season_year_from_heading():
    assert sfb._season_year("LIVE AUDITIONS 2026 Summer Session Spend a month") == 2026


def test_season_year_absent():
    assert sfb._season_year("Spend a month dancing in San Francisco.") is None


def test_deadline_from_video_window_close():
    assert sfb._deadline("between January 10–February 15, 2026.") == date(2026, 2, 15)


def test_deadline_absent():
    assert sfb._deadline("Online registration opens on November 1.") is None


# --- prices -------------------------------------------------------------------


def test_tuitions_split_per_session():
    by_session = sfb._tuitions(_AUDITION)
    assert [(p.label, p.amount, p.includes) for p in by_session["1"]] == [
        ("Tuition", 3495.0, ["tuition"]),
        ("Supervised housing", 3495.0, ["accommodation", "meals"]),
    ]
    assert [(p.amount, p.includes) for p in by_session["2"]] == [
        (3500.0, ["tuition"]),
        (3500.0, ["accommodation", "meals"]),
    ]


# --- genres / levels ----------------------------------------------------------


def test_genres_session_one_no_contemporary():
    prose = sfb._session_prose(_LANDING, "1")
    assert sfb._genres(prose) == ["classical", "pointe", "repertoire"]


def test_genres_session_two_adds_contemporary():
    prose = sfb._session_prose(_LANDING, "2")
    assert sfb._genres(prose) == ["classical", "pointe", "contemporary", "repertoire"]


def test_levels_session_one_unstated():
    assert sfb._levels(sfb._session_prose(_LANDING, "1")) == []


def test_levels_session_two_advanced_preprofessional():
    assert sfb._levels(sfb._session_prose(_LANDING, "2")) == ["advanced", "pre-professional"]


def test_session_prose_absent_landing():
    # No landing page → no prose → classical-only, no level.
    assert sfb._genres("") == ["classical"]
    assert sfb._levels("") == []


# --- end-to-end ---------------------------------------------------------------


def test_build_offerings_two_sessions():
    offerings = sfb._build_offerings(_AUDITION, _LANDING, _URL, date(2026, 1, 1))
    assert [o.id for o in offerings] == [
        "san-francisco-ballet-school/summer-session-1-2026",
        "san-francisco-ballet-school/summer-session-2-2026",
    ]

    s1, s2 = offerings
    assert s1.title == "Summer Session I"
    assert s1.schedule.season == "2026"
    assert (s1.schedule.start, s1.schedule.end) == (date(2026, 6, 15), date(2026, 7, 10))
    assert s1.schedule.timezone == "America/Los_Angeles"
    assert s1.age_range == {"min": 12, "max": 15}
    assert s1.genres == ["classical", "pointe", "repertoire"]
    assert s1.level == []
    assert s1.location is not None
    assert (s1.location.venue, s1.location.city, s1.location.country) == (
        "San Francisco Ballet",
        "San Francisco",
        "US",
    )
    assert [p.amount for p in s1.prices] == [3495.0, 3495.0]
    assert s1.application.deadline == date(2026, 2, 15)
    assert s1.application.url == _URL
    (req,) = s1.application.requirements
    assert isinstance(req, VideoReq)
    assert req.specificity == "unspecific"

    assert s2.title == "Summer Session II"
    assert (s2.schedule.start, s2.schedule.end) == (date(2026, 7, 14), date(2026, 8, 8))
    assert s2.age_range == {"min": 15, "max": 18}
    assert s2.genres == ["classical", "pointe", "contemporary", "repertoire"]
    assert s2.level == ["advanced", "pre-professional"]
    assert [p.amount for p in s2.prices] == [3500.0, 3500.0]


def test_no_offerings_when_year_absent():
    text = "Session 1 : Ages 12–15, June 15 – July 10"  # no "20xx Summer Session" heading
    assert sfb._build_offerings(text, "", _URL, date(2026, 1, 1)) == []


def test_offerings_without_landing_prose():
    # Audition page alone (no landing) → sessions still emit, classical-only, no level.
    offerings = sfb._build_offerings(_AUDITION, "", _URL, date(2026, 1, 1))
    assert len(offerings) == 2
    assert all(o.genres == ["classical"] for o in offerings)
    assert all(o.level == [] for o in offerings)
