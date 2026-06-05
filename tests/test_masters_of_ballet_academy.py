"""Unit tests for the Masters of Ballet Academy scraper.

MOBA serves a hand-rolled PHP site (`courses.php?course=N` + `forms.php?f=N`).
These pin the judgement calls a hash check can't catch: the cross-month vs
same-month date shapes, the Tbilisi stale-"2025" trap (dates come from the
headings, the stale body line must be ignored), the title parsed from `<h1>`,
the course-specific apply CTA (not the generic nav link), the two GBP price
tiers vs a single EUR fee, and the form's defined-poses photo requirement
(de-duplicated union of the two position sets). Inline HTML, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import masters_of_ballet_academy as moba

# Shaped like courses.php?course=11 (London): the `<h1>` carries the title; an
# `<h2>` carries the "Date:" cross-month range; the body lists the syllabus, the
# age band, the two GBP tiers (with the Juniors photo exemption), and links the
# course-specific apply form alongside the generic "How to Apply" nav link.
_LONDON_COURSE = """
<body>
  <nav><a href="forms.php?f=1">How to Apply</a></nav>
  <h1>SUMMER INTENSIVE COURSE 2026 - LONDON</h1>
  <h1>Masters of Ballet Academy Summer Intensive Course - SADLER'S WELLS</h1>
  <a href="forms.php?f=17">Click here to apply for this course</a>
  <p>Masters of Ballet Academy runs a non-residential Summer Intensive for one
  week for girls and boys aged 8 -19.</p>
  <h2>Date: 27th of July to 1st of August 2026</h2>
  <p>VENUE : SADLER'S WELLS Rosebery Ave, London EC1R 4TN.</p>
  <p>PRICES: JUNIORS 8/9/10 years (2 hours per day - NO PHOTO UPLOAD REQUIRED) - £250
  SENIORS, PRE PROFESSIONALS (6 hours per day, 11-19 years) - £750</p>
  <h2>Syllabus</h2>
  <p>Each 6-hour day consists of Ballet, Character, Pas de Deux, and
  Neo-Classical/ Contemporary classes.</p>
  <a href="forms.php?f=17">Click here to apply for this course</a>
</body>
"""

# Shaped like courses.php?course=10 (Tbilisi): the `<h2>` heading carries the
# good "19th - 25th July 2026" same-month range, while a body "Date:" line is the
# stale 2025 leftover that must NOT win. Single EUR fee; syllabus names Pointe.
_TBILISI_COURSE = """
<body>
  <nav><a href="forms.php?f=1">How to Apply</a></nav>
  <h1>SUMMER INTENSIVE COURSE 2026 - TBILISI, Georgia</h1>
  <a href="forms.php?f=19">Click here to apply for this course</a>
  <h2>Masters of Ballet Summer Intensive Course - TBILISI 19th - 25th July 2026</h2>
  <p>Welcoming talented young dancers aged 11-19 from around the world.</p>
  <p>The timetable will include 7 full days of curriculum, including Ballet,
  Pointe, Solos, Character, Neo Classical and Pas de Deux.</p>
  <p>Date: 19th July to 25th July 2025 PRICE: 7 Day Course - 900 Euros (£800)</p>
</body>
"""

# Shaped like forms.php?f=17/19: the photo brief with two position sets between
# the "5mb" cap and the "How did you learn about us?" question.
_FORM = """
<body>
  <p>Selection for the Summer Intensive will be based on uploaded application
  photos. Files must be in jpeg format, and not exceed 5mb
  1: Demi plié in 1st position 2: Tendu in 2nd 3: Developpé in 2nd (90 degrees)
  4: Arabesque en l'aire
  1: Demi plié in 1st position 2: Developpé in 2nd (above 90 degrees)
  3: Arabesque en l'aire 4: Échappé in 2nd, on pointe
  How did you learn about us?</p>
</body>
"""

LONDON = moba._EDITIONS[0]
TBILISI = moba._EDITIONS[1]


# --- date shapes --------------------------------------------------------------


def test_date_range_cross_month():
    assert moba._date_range("Date: 27th of July to 1st of August 2026") == (
        date(2026, 7, 27),
        date(2026, 8, 1),
    )


def test_date_range_same_month():
    assert moba._date_range("TBILISI 19th - 25th July 2026") == (
        date(2026, 7, 19),
        date(2026, 7, 25),
    )


def test_date_range_none_when_absent():
    assert moba._date_range("Syllabus and faculty") == (None, None)


# --- title + apply link -------------------------------------------------------


def test_title_from_h1_place():
    assert moba._title(_LONDON_COURSE, "2026") == "Summer Intensive 2026 — London"
    # Trailing ", Georgia" is dropped at the comma; place is title-cased.
    assert moba._title(_TBILISI_COURSE, "2026") == "Summer Intensive 2026 — Tbilisi"


def test_apply_path_picks_course_specific_cta_not_nav():
    assert moba._apply_path(_LONDON_COURSE) == "forms.php?f=17"
    assert moba._apply_path(_TBILISI_COURSE) == "forms.php?f=19"


# --- age + genres -------------------------------------------------------------


def test_age_range_from_aged_phrase():
    assert moba._age_range("girls and boys aged 8 -19") == {"min": 8, "max": 19}
    assert moba._age_range("dancers aged 11-19 from around the world") == {"min": 11, "max": 19}


def test_genres_match_syllabus():
    london = moba._genres("Ballet, Character, Pas de Deux, and Neo-Classical/ Contemporary")
    assert london == ["classical", "contemporary", "neoclassical", "character"]
    tbilisi = moba._genres("Ballet, Pointe, Solos, Character, Neo Classical and Pas de Deux")
    assert tbilisi == ["classical", "neoclassical", "character", "repertoire", "pointe"]


# --- prices -------------------------------------------------------------------


def test_prices_two_gbp_tiers():
    prices = moba._prices(
        "JUNIORS 8/9/10 years (NO PHOTO UPLOAD REQUIRED) - £250 "
        "SENIORS, PRE PROFESSIONALS (11-19 years) - £750"
    )
    assert [(p.amount, p.currency, p.label) for p in prices] == [
        (250.0, "GBP", "Juniors"),
        (750.0, "GBP", "Seniors / Pre-Professionals"),
    ]


def test_prices_single_eur_fee_when_no_gbp_tier():
    prices = moba._prices("7 Day Course - 900 Euros (£800)")
    assert [(p.amount, p.currency) for p in prices] == [(900.0, "EUR")]


# --- requirements -------------------------------------------------------------


def test_requirements_defined_poses_dedupes_two_sets():
    (req,) = moba._requirements(_FORM)
    assert req.type == "photos"
    assert req.specificity == "defined-poses"
    assert req.poses == [
        "Demi plié in 1st position",
        "Tendu in 2nd",
        "Developpé in 2nd (90 degrees)",
        "Arabesque en l'aire",
        "Developpé in 2nd (above 90 degrees)",
        "Échappé in 2nd, on pointe",
    ]


def test_requirements_empty_without_form():
    assert moba._requirements("") == []


def test_junior_exemption_note():
    assert (
        moba._requirement_note(_LONDON_COURSE) == "Juniors (8-10) are exempt from the photo upload."
    )
    assert moba._requirement_note(_TBILISI_COURSE) is None


# --- end-to-end _build_offering -----------------------------------------------


def test_build_offering_london():
    url = "https://mastersofballetacademy.com/courses.php?course=11"
    o = moba._build_offering(LONDON, url, _LONDON_COURSE, _FORM)
    assert o is not None
    assert o.id == "masters-of-ballet-academy/summer-intensive-london-2026"
    assert o.title == "Summer Intensive 2026 — London"
    assert o.schedule.start == date(2026, 7, 27)
    assert o.schedule.end == date(2026, 8, 1)
    assert o.schedule.timezone == "Europe/London"
    assert o.age_range == {"min": 8, "max": 19}
    assert o.location is not None
    assert (o.location.city, o.location.country) == ("London", "GB")
    assert [(p.amount, p.currency) for p in o.prices] == [(250.0, "GBP"), (750.0, "GBP")]
    assert o.application.url == "https://mastersofballetacademy.com/forms.php?f=17"
    (req,) = o.application.requirements
    assert req.type == "photos"


def test_build_offering_tbilisi_ignores_stale_2025():
    url = "https://mastersofballetacademy.com/courses.php?course=10"
    o = moba._build_offering(TBILISI, url, _TBILISI_COURSE, _FORM)
    assert o is not None
    # The good heading range (2026) wins over the stale body "Date: ...2025".
    assert o.id == "masters-of-ballet-academy/summer-intensive-tbilisi-2026"
    assert o.schedule.start == date(2026, 7, 19)
    assert o.schedule.end == date(2026, 7, 25)
    assert o.schedule.season == "2026"
    assert o.schedule.timezone == "Asia/Tbilisi"
    assert o.location is not None
    assert (o.location.city, o.location.country) == ("Tbilisi", "GE")
    assert [(p.amount, p.currency) for p in o.prices] == [(900.0, "EUR")]
    assert "pointe" in o.genres
    assert o.application.url == "https://mastersofballetacademy.com/forms.php?f=19"
