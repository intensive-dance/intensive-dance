"""Unit tests for the TANZOLYMP scraper (server-rendered HTML, two pages).

These pin the regex parsing: the edition + festival dates from the homepage
banner, the four declared age groups → age_range union + per-group Sessions, the
category list → genres (Pop/Jazz/Tap stays out of scope), the mandatory online
video requirement, the deadline-driven application status, and the
faithful-no-price behaviour ("calculated individually"). Teacher names are read
from the per-teacher rich-text modules (the accented spellings), not the noisy
image alts. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import tanzolymp as tz

_HOME = (
    "<body>WELCOME TO TANZOLYMP XXIII INTERNATIONAL DANCE FESTIVAL | "
    "FEBRUARY 12th - 17th, 2026 winners 2026 "
    "Venue: Fontane Haus, Königshorster Str. 6, 13439 Berlin, Germany</body>"
)

_PARTICIPATION = (
    "<body>"
    "Application forms for the Festival 2026, filled in completely, have to be "
    "submitted by December 10th, 2025. "
    "Every participant / group must send a link to an online video of the "
    "performance on YouTube or other websites. "
    "CP- Classical / Neoclassical Dance: state schools and professional dancers "
    "MP- Modern / Contemporary Dance: state schools "
    "FP- Folk Dance: for all "
    "DP- Pop, Jazz and Tap Dance: for all "
    "Group 1: from 8-12 years old Group 2: from 13-15 years old "
    "Group 3: from 16-18 years old Group 4: from 19-25 years old "
    "TEACHERS FOR WORKSHOPS AND SCHOLARSHIPS "
    '<div class="fl-module fl-module-rich-text"><p>Nina Ananiashvili</p></div>'
    '<div class="fl-module fl-module-rich-text"><p>Agnès Letestu</p></div>'
    '<div class="fl-module fl-module-rich-text"><p>Kelvin O. Hardy</p></div>'
    "</body>"
)


def test_full_offering_happy_path():
    o = tz._build_offering(_HOME, _PARTICIPATION, date(2026, 6, 5))
    assert o is not None
    assert o.id == "tanzolymp/2026"
    assert o.title == "TANZOLYMP XXIII — International Dance Festival"
    assert o.kind == "competition"
    assert o.schedule.start == date(2026, 2, 12)
    assert o.schedule.end == date(2026, 2, 17)
    assert o.schedule.season == "2026"
    assert o.age_range == {"min": 8, "max": 25}
    assert o.location is not None
    assert o.location.venue == "Fontane Haus"
    assert o.location.city == "Berlin"
    # Pop/Jazz/Tap (DP) is out of scope for a ballet register — not mapped.
    assert o.genres == ["classical", "neoclassical", "contemporary", "character"]
    # No fixed price; the fee model is recorded as text only.
    assert o.prices == []
    assert o.application.notes is not None
    assert "calculated individually" in o.application.notes


def test_sessions_are_per_age_group():
    o = tz._build_offering(_HOME, _PARTICIPATION, date(2026, 6, 5))
    assert o is not None
    assert [(s.label, s.age_range) for s in o.schedule.sessions] == [
        ("Age group 1", {"min": 8, "max": 12}),
        ("Age group 2", {"min": 13, "max": 15}),
        ("Age group 3", {"min": 16, "max": 18}),
        ("Age group 4", {"min": 19, "max": 25}),
    ]


def test_requirement_is_unspecific_video():
    o = tz._build_offering(_HOME, _PARTICIPATION, date(2026, 6, 5))
    assert o is not None
    (req,) = o.application.requirements
    assert req.type == "video"
    assert req.specificity == "unspecific"


def test_status_flips_on_deadline():
    # Deadline is December 10th, 2025.
    before = tz._build_offering(_HOME, _PARTICIPATION, date(2025, 11, 1))
    after = tz._build_offering(_HOME, _PARTICIPATION, date(2026, 6, 5))
    assert before is not None and after is not None
    assert before.application.status == "open"
    assert after.application.status == "closed"
    assert after.application.deadline == date(2025, 12, 10)


def test_teachers_from_rich_text_modules_keep_accents():
    o = tz._build_offering(_HOME, _PARTICIPATION, date(2026, 6, 5))
    assert o is not None
    assert [t.name for t in o.teachers] == [
        "Nina Ananiashvili",
        "Agnès Letestu",
        "Kelvin O. Hardy",
    ]


def test_no_edition_banner_emits_nothing():
    # When no current edition is announced, the homepage banner is absent and we
    # emit no Offering rather than guessing dates.
    assert (
        tz._build_offering("<body>WELCOME TO TANZOLYMP</body>", _PARTICIPATION, date.today())
        is None
    )
