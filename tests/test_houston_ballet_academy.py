"""Unit tests for the Houston Ballet Academy summer-programs scraper.

Houston is an HTML scrape of five public summer pages: the five-week SIP page
(dates/ages/level), the curriculum page (SIP genre list), the shared tuition page
(SIP + YSTP fee sections), the audition page (video window), and the YSTP page
(two dated sessions). These snippets pin the judgement calls a hash check can't
catch: the year-once/year-each date phrasings, the open-topped "Ages N+" floor,
the SIP-scoped fee parse (so YSTP's own registration fee can't bleed in), the
per-session YSTP tuition split, the curriculum-list genre match, and the
video-window deadline/status. No network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance import parse
from intensive_dance.models import VideoReq
from intensive_dance.scrapers import houston_ballet_academy as hba

# SIP five-week page: cycle title, level/age line, the date range.
_SIP = """
<body>
  <h2>SUMMER 2026</h2>
  <h3>LEVEL 5-8 (AGES 12+)</h3>
  <p>Students will be immersed in dance with classes six to eight hours per day,
  six days per week, learning from our world-class instructors, including Houston
  Ballet Academy artistic staff and Houston Ballet Company dancers.</p>
  <p>June 20 &ndash; July 24, 2026</p>
</body>
"""

# Curriculum page: the SIP class list (the genre source) + a year-once date line.
_CURRICULUM = """
<body>
  <h2>SUMMER INTENSIVE PROGRAM SCHEDULE</h2>
  <p>June 20 - July 24, 2026 Monday through Saturday</p>
  <p>Class offerings: Ballet Technique, Pointe, Partnering, Men's Technique,
  Repertory, Coaching, Variations, Modern, Contemporary, Jazz, Musical Theater,
  Character, Yoga, Pilates Mat Classes, Dance History, Nutrition</p>
</body>
"""

# Shared tuition page: the YSTP section (per-session level-band tuition + its own
# $75 registration fee) then the SIP section (the fees we want), then Adult.
_TUITION = """
<body>
  <h2>YOUTH SUMMER TRAINING PROGRAM (AGES 7+)</h2>
  <p>TUITION Level Session 1 Tuition Session 2 Tuition Session 1 &amp; Session 2 Tuition
  Level 1/Level 2 $675.00 $750.00 $1,425.00
  Level 3/Level 4/Intermediate/Advanced $1,350.00 $1,500.00 $2,565.00</p>
  <p>Registration Fee: $75</p>
  <h2>SUMMER INTENSIVE PROGRAM (AGES 12+)</h2>
  <p>Fees: Registration Fee: $275 Health &amp; Wellness Fee: $125 Tuition: $3,000
  Housing Registration Fee: $200
  University of St. Thomas (UST) Housing (optional): $3,400
  Center for Dance (CFD) Housing (optional; available by artistic invitation only): $1,085
  Market Square Tower (MST) Housing (optional; available by artistic invitation only): $1,085</p>
  <h2>ADULT INTENSIVE (18+)</h2>
  <p>5-Day Tuesday - Saturday $550.00</p>
</body>
"""

# Audition page: the open video-application window for the upcoming summer.
_AUDITION = """
<body>
  <h2>2027 Summer Intensive Audition Tour Will Open on Sunday, November 1st.</h2>
  <p>To be considered for Summer 2026, submissions will be accepted
  January 5 - February 15, 2026.</p>
</body>
"""

# YSTP page: two dated sessions (year-once / year-each), open-topped age floor.
_YSTP = """
<body>
  <h2>SUMMER 2026</h2>
  <h3>(AGES 7+)</h3>
  <p>Houston Ballet Academy's Youth Summer Training Program offers training for
  students ages 7 and up.</p>
  <p>Session 1: June 8 &ndash; 18, 2026</p>
  <p>Session 2: July 27 &ndash; August 7, 2026</p>
</body>
"""


def _text(html: str) -> str:
    return hba._page_text(html)


# --- dates --------------------------------------------------------------------


def test_sip_range_year_once_end_month_kept():
    start, end = hba._range(_text(_SIP))
    assert start == date(2026, 6, 20)
    assert end == date(2026, 7, 24)


def test_no_sip_when_dates_absent():
    assert hba._range("no dates here") == (None, None)


# --- ages ---------------------------------------------------------------------


def test_age_open_topped():
    assert hba._age_open(_text(_SIP)) == {"min": 12, "max": None}
    assert hba._age_open(_text(_YSTP)) == {"min": 7, "max": None}


# --- SIP genres ---------------------------------------------------------------


def test_sip_genres_from_curriculum_list():
    # Ballet/Pointe/Repertory+Variations/Contemporary+Modern/Character; Jazz and
    # Musical Theater aren't register genres, so they add nothing.
    assert hba._sip_genres(_text(_CURRICULUM)) == [
        "classical",
        "pointe",
        "repertoire",
        "contemporary",
        "character",
    ]


def test_sip_genres_classical_only_when_silent():
    assert hba._sip_genres("ballet technique only") == ["classical"]


# --- SIP prices (scoped to the SIP section) -----------------------------------


def test_sip_prices_labeled_with_inclusions():
    prices = hba._sip_prices(_text(_TUITION))
    assert [(p.label, p.amount, p.includes) for p in prices] == [
        ("Tuition", 3000.0, ["tuition"]),
        ("Registration fee", 275.0, []),  # the SIP $275, not the YSTP $75
        ("Health & Wellness fee", 125.0, []),
        ("Housing registration fee", 200.0, []),
        ("University of St. Thomas housing (optional)", 3400.0, ["accommodation"]),
    ]


# --- SIP deadline -------------------------------------------------------------


def test_sip_deadline_from_video_window():
    assert hba._sip_deadline(_text(_AUDITION), 2026) == date(2026, 2, 15)


def test_sip_deadline_rejected_when_year_mismatches_cycle():
    # The window names 2026; an SIP cycle for 2027 must not borrow it.
    assert hba._sip_deadline(_text(_AUDITION), 2027) is None


# --- YSTP per-session prices --------------------------------------------------


def test_ystp_session_prices_split_by_session():
    section = hba._YSTP_SECTION.search(_text(_TUITION))
    assert section is not None
    cols = hba._ystp_session_prices(section.group(1))
    assert [(p.label, p.amount) for p in cols["1"]] == [
        ("Tuition — Level 1/Level 2", 675.0),
        ("Tuition — Level 3/Level 4/Intermediate/Advanced", 1350.0),
        ("Registration fee", 75.0),
    ]
    assert [(p.label, p.amount) for p in cols["2"]] == [
        ("Tuition — Level 1/Level 2", 750.0),
        ("Tuition — Level 3/Level 4/Intermediate/Advanced", 1500.0),
        ("Registration fee", 75.0),
    ]


# --- end-to-end ---------------------------------------------------------------


def test_build_offerings_sip_and_two_ystp_sessions():
    offerings = hba._build_offerings(
        _text(_SIP),
        _text(_CURRICULUM),
        _text(_TUITION),
        _text(_AUDITION),
        _text(_YSTP),
    )
    ids = [o.id for o in offerings]
    assert ids == [
        "houston-ballet-academy/summer-intensive-program-2026",
        "houston-ballet-academy/youth-summer-training-s1-2026",
        "houston-ballet-academy/youth-summer-training-s2-2026",
    ]

    sip = offerings[0]
    assert sip.title == "Summer Intensive Program"
    assert sip.genres == ["classical", "pointe", "repertoire", "contemporary", "character"]
    assert sip.level == ["intermediate", "advanced", "pre-professional"]
    assert sip.schedule.start == date(2026, 6, 20)
    assert sip.schedule.end == date(2026, 7, 24)
    assert sip.schedule.timezone == "America/Chicago"
    assert sip.age_range == {"min": 12, "max": None}
    assert sip.location is not None
    assert (sip.location.venue, sip.location.city, sip.location.country) == (
        "Margaret Alkek Williams Center for Dance",
        "Houston",
        "US",
    )
    assert sip.application.deadline == date(2026, 2, 15)
    assert sip.application.status is None
    assert isinstance(sip.application.requirements[0], VideoReq)
    assert sip.application.requirements[0].specificity == "unspecific"

    s1 = offerings[1]
    assert s1.title == "Youth Summer Training Program — Session 1"
    assert s1.genres == ["classical"]
    assert s1.age_range == {"min": 7, "max": None}
    assert s1.schedule.start == date(2026, 6, 8)
    assert s1.schedule.end == date(2026, 6, 18)
    assert [p.amount for p in s1.prices] == [675.0, 1350.0, 75.0]

    s2 = offerings[2]
    assert s2.schedule.start == date(2026, 7, 27)
    assert s2.schedule.end == date(2026, 8, 7)  # year-each phrasing, end month differs
    assert [p.amount for p in s2.prices] == [750.0, 1500.0, 75.0]


def test_sip_keeps_deadline_without_inventing_status():
    offerings = hba._build_offerings(
        _text(_SIP),
        _text(_CURRICULUM),
        _text(_TUITION),
        _text(_AUDITION),
        _text(_YSTP),
    )
    sip = offerings[0]
    assert sip.application.deadline == date(2026, 2, 15)
    assert sip.application.status is None


def test_parse_amount_used_for_thousands():
    assert parse.parse_amount("3,000") == 3000.0
