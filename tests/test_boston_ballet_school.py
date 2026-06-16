"""Unit tests for the Boston Ballet School summer-intensives scraper.

BBS is an HTML scrape of three summer pages whose bodies the WP REST API leaves
empty: the SDP "Tuition, Dates, and FAQ" page (dates/ages/fees), the SDP
audition-tour page (video window + status), and the Junior Summer Intensive page
(three dated sessions). These snippets pin the judgement calls a hash check can't
catch: the weekday-prefixed year-less date stamping, the labeled fee lines and
their inclusions, the per-program requirement branch (SDP audition→video vs JSI
photos+headshot+letter), and the video-window status/deadline. No network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import CVReq, HeadshotReq, PhotosReq, VideoReq
from intensive_dance.scrapers import boston_ballet_school as bbs

# SDP landing page: cycle title + curriculum styles (the genre source).
_LANDING = """
<body>
  <h2>Summer Dance Program 2026</h2>
  <p>While Summer Dance Program maintains a strong focus on classical ballet
  technique, the curriculum also explores a broader spectrum: character, modern,
  and choreography/improv.</p>
</body>
"""

# SDP FAQ page: cycle title, labeled fee line (tuition + registration + housing +
# lunch, with the "Lunch Plan :" stray-space colon), the placement/last-day date
# lines, and the age floor/ceiling. Curriculum styles are NOT here (landing only).
_FAQ = """
<body>
  <h1>Tuition, Dates, and Frequently Asked Questions</h1>
  <h4>TUITION AND IMPORTANT DATES</h4>
  <p>Tuition: $3,620 <i>(plus $100 registration fee)</i>
  Food/Housing: $3,570 <i>(residential students only)</i>
  Lunch Plan <i>: </i>$320 <i>(optional, residential students only)</i></p>
  <p>Move-in day (residential students only): Saturday, June 27
  Placement classes: Sunday, June 28&ndash;Monday, June 29
  First full day of classes: Tuesday, June 30
  Last day of classes / Parent Observation: Saturday, July 25</p>
  <p>Boston Ballet School's Summer Dance Program 2026 offers training for serious
  ballet students.</p>
  <p>Students must be between the ages of 12* and 18 when the program begins.</p>
</body>
"""

# SDP audition-tour page: in-person tour concluded, video window still open.
_AUDITION = """
<body>
  <h2>Summer Dance Program Audition Tour</h2>
  <p>Pre-recorded videos will now be accepted through Sunday, March 15. The
  registration fee for a pre-recorded video submission is $60.</p>
  <p>The in-person audition tour for Summer Dance Program 2026 has concluded, but
  video auditions will be accepted through Sunday March 15.</p>
</body>
"""

# JSI page: three dated sessions, the age+year clause, labeled fee line, and the
# application photo/headshot/letter intake.
_JSI = """
<body>
  <h1>Junior Summer Intensive</h1>
  <p>Session 1 | June 22&ndash;July 3
  Session 2 | July 6&ndash;17
  Session 3 | July 20&ndash;31
  Ages 9&ndash;12 (as of August 31, 2026)</p>
  <p>Under the instruction of Boston Ballet School faculty, students engage in
  daily classical ballet technique. A pre-pointe/pointe curriculum is offered to
  all students. Students broaden their knowledge of dance styles through character,
  modern, and jazz.</p>
  <h2>Session Schedules</h2>
  <p>Session 1: Classes Monday, June 22 through Friday, July 3 (weekdays only)
  Session 2: Classes Monday, July 6 through Friday, July 17 (weekdays only)
  Session 3: Classes Monday, July 20 through Friday, July 31 (weekdays only)</p>
  <h4>Tuition and Residential Fees:</h4>
  <p>Tuition: $2,200 (plus $70 registration fee)
  Residential Fees: $2,500 (plus $200 activity fee)</p>
  <p>Students must be between the ages of 9 and 12 on August 31, 2026.</p>
  <p>Please be prepared to upload a letter of recommendation, a headshot, a photo
  in first position with preparatory arms and a photo in tendu a la seconde.</p>
</body>
"""


def _text(html: str) -> str:
    return bbs._page_text(html)


# --- SDP date stamping --------------------------------------------------------


def test_sdp_dates_stamped_from_cycle_year():
    faq = _text(_FAQ)
    assert bbs._stamped(bbs._SDP_START, faq, 2026) == date(2026, 6, 28)
    assert bbs._stamped(bbs._SDP_END, faq, 2026) == date(2026, 7, 25)


def test_sdp_year_from_title():
    assert bbs._sdp_year(_text(_FAQ)) == 2026
    assert bbs._sdp_year("no cycle named") is None


# --- SDP genres / ages / prices ----------------------------------------------


def test_sdp_genres_classical_plus_character_and_modern():
    assert bbs._sdp_genres(_text(_LANDING)) == ["classical", "character", "contemporary"]


def test_sdp_genres_classical_only_when_silent():
    assert bbs._sdp_genres("classical ballet technique only") == ["classical"]


def test_sdp_age_floor_ceiling():
    from intensive_dance import parse

    assert parse.extract_age_range(_text(_FAQ), bbs._SDP_AGE) == {"min": 12, "max": 18}


def test_sdp_prices_labeled_with_inclusions():
    prices = bbs._sdp_prices(_text(_FAQ))
    assert [(p.label, p.amount, p.includes) for p in prices] == [
        ("Tuition", 3620.0, ["tuition"]),
        ("Registration fee", 100.0, []),
        ("Food/Housing", 3570.0, ["accommodation", "meals"]),
        ("Lunch Plan", 320.0, ["meals"]),  # parsed despite the "Lunch Plan :" stray space
    ]


# --- SDP status / deadline ----------------------------------------------------


def test_sdp_deadline_from_video_window():
    assert bbs._sdp_deadline(_text(_AUDITION), 2026) == date(2026, 3, 15)


def test_sdp_status_unset_while_video_window_stated():
    # A stated video deadline is a deadline, not a status — leave status unset
    # (no date-derived "closed"; consumers derive closed-ness from deadline).
    deadline = date(2026, 3, 15)
    assert bbs._sdp_status(_text(_AUDITION), deadline) is None


def test_sdp_status_closed_when_concluded_and_no_window():
    # Explicit "has concluded" with no remaining video window → faithful closed.
    assert bbs._sdp_status("The audition tour has concluded.", None) == "closed"
    assert bbs._sdp_status("Auditions are ongoing.", None) is None


# --- JSI sessions -------------------------------------------------------------


def test_jsi_genres_includes_pointe_character_modern():
    assert bbs._jsi_genres(_text(_JSI)) == [
        "classical",
        "pointe",
        "character",
        "contemporary",
    ]


def test_jsi_prices_labeled_with_inclusions():
    prices = bbs._jsi_prices(_text(_JSI))
    assert [(p.label, p.amount, p.includes) for p in prices] == [
        ("Tuition", 2200.0, ["tuition"]),
        ("Registration fee", 70.0, []),
        ("Residential Fees", 2500.0, ["accommodation", "meals"]),
        ("Activity fee", 200.0, []),
    ]


def test_jsi_requirements_photos_headshot_letter():
    reqs = bbs._jsi_requirements()
    assert [type(r) for r in reqs] == [PhotosReq, HeadshotReq, CVReq]
    photos = reqs[0]
    assert isinstance(photos, PhotosReq)
    assert photos.specificity == "defined-poses"
    assert len(photos.poses) == 3


# --- end-to-end ---------------------------------------------------------------


def test_build_offerings_sdp_and_three_jsi_sessions():
    offerings = bbs._build_offerings(_text(_LANDING), _text(_FAQ), _text(_AUDITION), _text(_JSI))
    ids = [o.id for o in offerings]
    assert ids == [
        "boston-ballet-school/summer-dance-program-2026",
        "boston-ballet-school/junior-summer-intensive-s1-2026",
        "boston-ballet-school/junior-summer-intensive-s2-2026",
        "boston-ballet-school/junior-summer-intensive-s3-2026",
    ]

    sdp = offerings[0]
    assert sdp.title == "Summer Dance Program"
    assert sdp.genres == ["classical", "character", "contemporary"]
    assert sdp.schedule.start == date(2026, 6, 28)
    assert sdp.schedule.end == date(2026, 7, 25)
    assert sdp.schedule.timezone == "America/New_York"
    assert sdp.age_range == {"min": 12, "max": 18}
    assert sdp.location is not None
    assert (sdp.location.venue, sdp.location.city, sdp.location.country) == (
        "Boston Ballet School",
        "Boston",
        "US",
    )
    assert sdp.application.deadline == date(2026, 3, 15)
    assert sdp.application.status is None
    assert isinstance(sdp.application.requirements[0], VideoReq)

    s1 = offerings[1]
    assert s1.title == "Junior Summer Intensive — Session 1"
    assert s1.schedule.start == date(2026, 6, 22)
    assert s1.schedule.end == date(2026, 7, 3)
    assert s1.age_range == {"min": 9, "max": 12}
    assert s1.location is not None
    assert (s1.location.venue, s1.location.city) == ("Walnut Hill School for the Arts", "Natick")
    assert offerings[3].schedule.start == date(2026, 7, 20)
    assert offerings[3].schedule.end == date(2026, 7, 31)


def test_no_sdp_when_dates_absent():
    offerings = bbs._build_offerings("", "<body><h1>BBS</h1></body>", "", "")
    assert offerings == []
