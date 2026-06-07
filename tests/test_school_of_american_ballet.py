"""Unit tests for the School of American Ballet summer-programs scraper.

SAB is an HTML scrape of two program pages sharing one template: an `<h1>`, dated
prose, and a single two-column fee table. These pin the judgement calls a hash
check can't catch: the two date phrasings (dashed vs "through" with weekday
prefixes), the floor/ceiling age sentence, level extraction that ignores loose
prose, the fee-table inclusions, the audition→video requirement, and the
status/deadline detection from the "auditions have passed" notice.
Inline HTML snippets, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import VideoReq
from intensive_dance.scrapers import school_of_american_ballet as sab

# Summer Course: dashed date range with both years, intermediate/advanced, a
# six-row fee table including Room and Board, plus a Contemporary curriculum line.
_SC_HTML = """
<body>
  <h1>Summer Course in NYC</h1>
  <h2>2026 Summer Course</h2>
  <p>The 2026 Summer Course will take place from June 29, 2026 – July 31, 2026
  at SAB's headquarters at the world famous Lincoln Center for the Performing Arts.</p>
  <p>Study in SAB's Summer Course is for intermediate and advanced students; for
  admission, students must be no younger than 12 and no older than 18 as of
  July 31, 2026.</p>
  <h2>Auditions</h2>
  <p>The Summer Course is highly selective. All students must audition. We will
  also accept video applications through February 15 for any applicant who cannot
  attend and audition in person.</p>
  <p><em><strong>All auditions for our 2026 programs have now passed.</strong></em></p>
  <h3>Technique</h3><h3>Pointe</h3><h3>Character</h3><h3>Variations</h3><h3>Contemporary</h3>
  <h4>2026 Summer Course Tuition Rates</h4>
  <table><tbody>
    <tr><td><strong>Tuition (All Levels)</strong></td><td>$3,870</td></tr>
    <tr><td><b>Registration Fee</b></td><td>$135</td></tr>
    <tr><td><b>Room and Board</b></td><td>$4,170</td></tr>
    <tr><td><b>Single Room Surcharge</b></td><td>$625</td></tr>
    <tr><td><b>Activity Fee</b></td><td>$170</td></tr>
    <tr><td><b>Laundry Fee</b></td><td>$20</td></tr>
  </tbody></table>
</body>
"""

# NY Junior Session: "through" range with weekday prefixes and a single trailing
# year, ages 10-12, a one-row fee table, no Contemporary line. "the most advanced
# girls" appears in prose and must NOT leak into levels.
_NJS_HTML = """
<body>
  <h1>New York Junior Session</h1>
  <h2>2026 NY Junior Session</h2>
  <p>The 2026 New York Junior Session will take place from Monday, June 22
  through Saturday, June 27, 2026 at the School of American Ballet at Lincoln Center.</p>
  <p>Students must be no younger than 10 as of July 31, 2026, and no older than 12
  on final day of the program. 12 year olds should be training at the intermediate
  level. Boys and the most advanced girls participate in a seminar.</p>
  <h2>Auditions</h2>
  <p>All students must audition. We will also accept video applications through
  February 15.</p>
  <h3>Technique</h3><h3>Pointe</h3><h3>Character Dancing</h3><h3>Variations</h3>
  <h4>Tuition Rates</h4>
  <table><tbody>
    <tr><td>Tuition</td><td>$990</td></tr>
    <tr><td>Registration Fee</td><td>$110</td></tr>
  </tbody></table>
</body>
"""


# --- dates --------------------------------------------------------------------


def test_dates_dashed_range_both_years():
    assert sab._dates("from June 29, 2026 – July 31, 2026 at") == (
        date(2026, 6, 29),
        date(2026, 7, 31),
    )


def test_dates_through_range_with_weekdays_single_year():
    assert sab._dates("Monday, June 22 through Saturday, June 27, 2026 at") == (
        date(2026, 6, 22),
        date(2026, 6, 27),
    )


def test_dates_absent():
    assert sab._dates("no dated edition yet") == (None, None)


# --- ages ---------------------------------------------------------------------


def test_age_range_floor_ceiling():
    assert sab._age_range("no younger than 12 and no older than 18 as of July 31") == {
        "min": 12,
        "max": 18,
    }


def test_age_range_spans_intervening_clause():
    assert sab._age_range(
        "no younger than 10 as of July 31, 2026, and no older than 12 on final day"
    ) == {"min": 10, "max": 12}


def test_age_range_absent():
    assert sab._age_range("an introductory program") is None


# --- levels -------------------------------------------------------------------


def test_levels_coordinated_phrase():
    assert sab._levels("is for intermediate and advanced students") == ["intermediate", "advanced"]


def test_levels_comma_separated_list():
    text = "for intermediate, advanced, and pre-professional students"
    assert sab._levels(text) == ["intermediate", "advanced", "pre-professional"]


def test_levels_ignores_loose_prose():
    text = "training at the intermediate level. the most advanced girls participate"
    assert sab._levels(text) == ["intermediate"]


# --- genres -------------------------------------------------------------------


def test_genres_summer_course_includes_contemporary():
    text = "ballet technique, pointe, character, variations and contemporary"
    assert sab._genres(text) == ["classical", "pointe", "character", "contemporary", "repertoire"]


def test_genres_junior_session_no_contemporary():
    text = "ballet technique, pointe, character dancing and variations"
    assert sab._genres(text) == ["classical", "pointe", "character", "repertoire"]


# --- requirements -------------------------------------------------------------


def test_requirements_video_when_audition_stated():
    (req,) = sab._requirements("All students must audition.")
    assert isinstance(req, VideoReq)
    assert req.specificity == "unspecific"


def test_requirements_none_when_silent():
    assert sab._requirements("Classes run Monday to Friday.") == []


# --- application status & deadline -------------------------------------------


def test_status_closed_when_auditions_passed():
    text = "All auditions for our 2026 programs have now passed."
    assert sab._status(text) == "closed"


def test_status_none_when_not_stated():
    assert sab._status("Auditions open every January.") is None


def test_deadline_from_video_application_sentence():
    text = "We will also accept video applications through February 15 for any applicant."
    assert sab._deadline(text, 2026) == date(2026, 2, 15)


def test_deadline_none_when_absent():
    assert sab._deadline("All students must audition.", 2026) is None


def test_deadline_none_when_no_year():
    text = "We will also accept video applications through February 15 for any applicant."
    assert sab._deadline(text, None) is None


# --- end-to-end ---------------------------------------------------------------


def test_summer_course_offering():
    o = sab._build_offering(
        _SC_HTML, "https://sab.org/enrollment/summer-course/", "summer-course", date(2026, 1, 1)
    )
    assert o is not None
    assert o.id == "school-of-american-ballet/summer-course-2026"
    assert o.title == "Summer Course in NYC"
    assert o.schedule.start == date(2026, 6, 29)
    assert o.schedule.end == date(2026, 7, 31)
    assert o.schedule.timezone == "America/New_York"
    assert o.age_range == {"min": 12, "max": 18}
    assert o.level == ["intermediate", "advanced"]
    assert o.genres == ["classical", "pointe", "character", "contemporary", "repertoire"]
    assert o.location is not None
    assert (o.location.venue, o.location.city, o.location.country) == (
        "Lincoln Center",
        "New York",
        "US",
    )
    assert [(p.label, p.amount, p.includes) for p in o.prices] == [
        ("Tuition (All Levels)", 3870.0, ["tuition"]),
        ("Registration Fee", 135.0, []),
        ("Room and Board", 4170.0, ["accommodation", "meals"]),
        ("Single Room Surcharge", 625.0, []),
        ("Activity Fee", 170.0, []),
        ("Laundry Fee", 20.0, []),
    ]
    assert o.application.requirements[0].type == "video"
    assert o.application.status == "closed"
    assert o.application.deadline == date(2026, 2, 15)


def test_junior_session_offering():
    o = sab._build_offering(
        _NJS_HTML,
        "https://sab.org/enrollment/new-york-junior-session/",
        "new-york-junior-session",
        date(2026, 1, 1),
    )
    assert o is not None
    assert o.id == "school-of-american-ballet/new-york-junior-session-2026"
    assert o.schedule.start == date(2026, 6, 22)
    assert o.schedule.end == date(2026, 6, 27)
    assert o.age_range == {"min": 10, "max": 12}
    assert o.level == ["intermediate"]
    assert o.genres == ["classical", "pointe", "character", "repertoire"]
    assert [p.amount for p in o.prices] == [990.0, 110.0]


def test_no_offering_when_dates_absent():
    assert (
        sab._build_offering(
            "<body><h1>SAB</h1></body>", "https://sab.org/x/", "x", date(2026, 1, 1)
        )
        is None
    )
