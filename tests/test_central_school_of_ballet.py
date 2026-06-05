"""Unit tests for the Central School of Ballet scraper.

Central serves one editorial page whose body holds several offerings, each an
`<h2>` with `<h4>` sub-blocks. These pin the judgement calls a hash check can't
catch: the `<h2>` offering-splitter, the three-track summer split (each track's
own British date range / age / fee out of one shared paragraph), the
weekday-prefixed date parsing, RAD-grade → pre-professional level, the
defined-poses photo requirement, and the drop-when-ended rule. Inline HTML, no
network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import central_school_of_ballet as csb

# Mirrors the live body: a summer `<h2>` whose Course Dates paragraph lists three
# tracks, an autumn `<h2>` with a dashed date range and a TBA cost, and a spring
# `<h2>` whose dates are "To be announced". A trailing one-day `<h2>` dated in the
# past must be dropped by `_build_offerings`.
_HTML = """
<body>
  <h1>Ballet Intensives</h1>
  <p>Central offers a range of intensive ballet courses for dancers aged 11 - 16.</p>

  <h2>International Summer Courses (11-16 years)</h2>
  <p>The Summer Courses attract talented dancers from around the globe.</p>
  <h4>Entry Requirements</h4>
  <p>Open to students aged 11-16 years old, in school years 7-11, with a minimum
  of RAD Intermediate Foundation or equivalent for 11-13 years.</p>
  <h4>Course Dates</h4>
  <p>One week courses: Week one (14-16 years) - Monday 27 July - Saturday 1 August 2026
  Week two (11-13 years) - Monday 3 August - Saturday 8 August 2026</p>
  <p>Two week courses: Monday 27 July - Saturday 8 August 2026 (11-16 years)</p>
  <h4>Cost</h4>
  <p>One week course £525 Two week course £820 Additional English Classes £190</p>
  <h4>Application Deadline and Outcome</h4>
  <p>Limited places remaining.</p>
  <h4>Application Photos</h4>
  <p>In your application, please submit the following photos: Demi plié in first position</p>
  <h3>Course Outline</h3>
  <p>The courses include a Ballet class every day as well as additional pointe work.
  Other classes provide experience of Contemporary, Repertoire and Pilates. Other
  disciplines such as Jazz, Character or Creative Choreography may also be included.
  Please note, accommodation and meals are not provided on this course.</p>

  <h2>Autumn Audition Preparation Course (14-16 years)</h2>
  <p>This intensive ballet course offers coaching for vocational auditions.</p>
  <h4>Entry Requirements</h4>
  <p>Open to students aged 14-16 years old, in school years 9-11, with a minimum
  of RAD Intermediate or equivalent.</p>
  <h4>Course Date &amp; Time</h4>
  <p>Tuesday 27 October - Thursday 29 October 2026</p>
  <h4>Cost</h4>
  <p>To be announced</p>
  <h4>Application Dates</h4>
  <p>Applications open Monday 17 August 2026 Applications close Monday 21 September 2026</p>
  <h3>Course Outline</h3>
  <p>The course includes a daily ballet class with additional pointe work. Other
  classes include contemporary, improvisation and Pilates.</p>

  <h2>Spring Course (11-16 years)</h2>
  <p>The Spring Course offers a taste of full-time training.</p>
  <h4>Entry Requirements</h4>
  <p>Open to students aged 11-16 years old, in school years 7-11, with a minimum
  of RAD Intermediate Foundation or equivalent</p>
  <h4>Course Dates</h4>
  <p>To be announced</p>
  <h4>Cost</h4>
  <p>To be announced</p>
  <h4>Application Photos</h4>
  <p>In your application, please submit the following photos.</p>
  <h3>Course Outline</h3>
  <p>The course includes a Ballet class every day as well as additional pointe
  work. Other classes provide experience of Contemporary, Repertoire and Pilates.
  Other disciplines such as Jazz, Character may also be included.</p>

  <h2>One Day Ballet Intensive (11-13 years)</h2>
  <p>An intensive day for younger dancers.</p>
  <h4>Course Date &amp; Time</h4>
  <p>Wednesday 27 May 2026 - Wednesday 27 May 2026</p>
  <h4>Cost</h4>
  <p>£68</p>
  <h3>Course Outline</h3>
  <p>A repertoire day with ballet and pointe work.</p>
</body>
"""

TODAY = date(2026, 6, 5)


def _by_id(offerings: list, suffix: str):
    return next(o for o in offerings if o.id.endswith(suffix))


# --- splitter + drop-ended ----------------------------------------------------


def test_emits_one_per_track_and_drops_past_one_day():
    offerings = csb._build_offerings(_HTML, TODAY)
    # 3 summer tracks + autumn + spring; the past one-day intensive is dropped.
    ids = sorted(o.id for o in offerings)
    assert ids == [
        "central-school-of-ballet/autumn-audition-preparation",
        "central-school-of-ballet/spring-course",
        "central-school-of-ballet/summer-two-week",
        "central-school-of-ballet/summer-week-one",
        "central-school-of-ballet/summer-week-two",
    ]


# --- summer track split -------------------------------------------------------


def test_summer_week_one_dates_age_price():
    o = _by_id(csb._build_offerings(_HTML, TODAY), "summer-week-one")
    assert o.schedule.start == date(2026, 7, 27)
    assert o.schedule.end == date(2026, 8, 1)
    assert o.age_range == {"min": 14, "max": 16}
    assert [(p.amount, p.currency, p.includes) for p in o.prices] == [(525.0, "GBP", ["tuition"])]


def test_summer_week_two_distinct_dates_and_age():
    o = _by_id(csb._build_offerings(_HTML, TODAY), "summer-week-two")
    assert o.schedule.start == date(2026, 8, 3)
    assert o.schedule.end == date(2026, 8, 8)
    assert o.age_range == {"min": 11, "max": 13}
    assert o.prices[0].amount == 525.0


def test_summer_two_week_span_and_higher_fee():
    o = _by_id(csb._build_offerings(_HTML, TODAY), "summer-two-week")
    assert o.schedule.start == date(2026, 7, 27)
    assert o.schedule.end == date(2026, 8, 8)
    assert o.age_range == {"min": 11, "max": 16}
    assert o.prices[0].amount == 820.0


# --- single offerings ---------------------------------------------------------


def test_autumn_intensive_dates_and_no_tba_price():
    o = _by_id(csb._build_offerings(_HTML, TODAY), "autumn-audition-preparation")
    assert o.schedule.start == date(2026, 10, 27)
    assert o.schedule.end == date(2026, 10, 29)
    assert o.prices == []  # "To be announced" → no Price
    assert o.application.notes is not None


def test_spring_tba_dates_stay_null():
    o = _by_id(csb._build_offerings(_HTML, TODAY), "spring-course")
    assert o.schedule.start is None
    assert o.schedule.end is None
    assert o.schedule.season == "unknown"
    assert o.prices == []


# --- field helpers ------------------------------------------------------------


def test_date_range_skips_weekday_prefix():
    assert csb._date_range("Tuesday 27 October - Thursday 29 October 2026") == (
        date(2026, 10, 27),
        date(2026, 10, 29),
    )


def test_date_range_tba_returns_none():
    assert csb._date_range("To be announced") == (None, None)


def test_age_range_from_aged_phrase():
    assert csb._age_range("aged 11-16 years old") == {"min": 11, "max": 16}


def test_level_pre_professional_from_rad_grade():
    assert csb._has_grade_prereq("minimum of RAD Intermediate or equivalent") is True
    assert csb._has_grade_prereq("open to all children") is False


def test_genres_match_curriculum_outline():
    outline = "Ballet class every day, additional pointe work, Contemporary, Repertoire, Character"
    assert csb._genres(outline) == ["contemporary", "repertoire", "character", "pointe"]


def test_genres_default_classical_when_outline_silent():
    assert csb._genres("A day of dance for all abilities.") == ["classical"]


def test_requirements_defined_poses():
    (req,) = csb._requirements("Please submit the following photos: demi plié")
    assert req.type == "photos"
    assert req.specificity == "defined-poses"
    assert len(req.poses) == 5


def test_requirements_empty_when_no_photos_block():
    assert csb._requirements("") == []
