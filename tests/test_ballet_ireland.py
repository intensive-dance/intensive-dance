"""Unit tests for the Ballet Ireland Summer Intensive scraper.

Ballet Ireland serves one Divi-built WordPress page whose summary sits in an
`[et_pb_text]` block and whose faculty are `[et_pb_team_member]` shortcode
attributes. These pin the judgement calls a hash check can't catch: the two-week
split into one Offering each, the "Fully Booked" → `closed` mapping (cycle kept,
not dropped), the open-topped "12+" age, the "Grade 4 to Professional" level
span, the per-week EUR price, the named faculty read from shortcode attributes,
and the fail-open handling of a week with no parseable dates. Inline content, no
network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import ballet_ireland as bi

# Mirrors the live `content.rendered`: a single summary `[et_pb_text]` block with
# the two weeks (Week 1 flagged "Fully Booked"), the venue/age/level/price line,
# then the Divi faculty grid as `[et_pb_team_member]` shortcodes (curly quotes,
# empty bio bodies — exactly as Divi emits them).
_RENDERED = """
[et_pb_section][et_pb_text admin_label=“Text” _builder_version=“4.27.6”]
A unique Summer Intensive providing students with the training required for
Ballet Dancers of today. Each day will start with ballet-based Pilates. Students
will train with world renowned tutors in ballet, pointe work and repertoire.
Week 1: Monday 27 July to Friday 31 July 2026 – Fully Booked
Week 2: Tuesday 4 August to Saturday 8 August 2026
DanceHouse, Foley Street, Dublin 1 9:45AM – 5PM
FOR AGES: 12+ LEVEL: GRADE 4 to PROFESSIONAL PRICE: €300 per week
Please complete the registration and payment forms below.
[/et_pb_text][/et_pb_section]
[et_pb_section admin_label=“Faculty Section”][et_pb_row]
[et_pb_team_member name=“Anne Maher” position=“Ballet & Repertoire” image_url=“https://x/a.png”][/et_pb_team_member]
[et_pb_team_member name=“Filipe Portugal” position=“Ballet & Repertoire”][/et_pb_team_member]
[et_pb_team_member name=“Fiona Brockway” position=“Ballet & Repertoire”][/et_pb_team_member]
[et_pb_team_member name=“Kate Lyons” position=“Ballet & Repertoire”][/et_pb_team_member]
[et_pb_team_member name=“Dominic Harrison” position=“Ballet & Repertoire”][/et_pb_team_member]
[et_pb_team_member name=“Hayley Cunningham” position=“Pilates”][/et_pb_team_member]
[/et_pb_row][/et_pb_section]
"""

_TODAY = date(2026, 6, 8)


def _offerings():
    return bi._build_offerings(_RENDERED, _TODAY)


def test_emits_one_offering_per_week():
    offerings = _offerings()
    assert [o.id for o in offerings] == [
        "ballet-ireland/summer-intensive-week-1-2026",
        "ballet-ireland/summer-intensive-week-2-2026",
    ]


def test_week_dates_and_titles():
    week1, week2 = _offerings()
    assert week1.title == "Summer Intensive — Week 1 2026"
    assert week1.schedule.start == date(2026, 7, 27)
    assert week1.schedule.end == date(2026, 7, 31)
    assert week2.schedule.start == date(2026, 8, 4)
    assert week2.schedule.end == date(2026, 8, 8)
    assert week1.schedule.season == "2026"


def test_fully_booked_maps_to_closed_but_keeps_cycle():
    week1, week2 = _offerings()
    # Week 1 is flagged "Fully Booked" → closed; the cycle is still emitted.
    assert week1.application.status == "closed"
    assert week1.application.notes is not None
    assert "fully booked" in week1.application.notes.lower()
    # Week 2 is silent → status stays None (fail-open).
    assert week2.application.status is None
    assert week2.application.notes is None


def test_age_is_open_topped():
    week1, _ = _offerings()
    assert week1.age_range == {"min": 12, "max": None}


def test_level_span():
    week1, _ = _offerings()
    assert week1.level == ["pre-professional", "professional"]


def test_genres_from_syllabus():
    week1, _ = _offerings()
    assert week1.genres == ["classical", "repertoire", "pointe"]


def test_price_eur_per_week():
    week1, _ = _offerings()
    assert len(week1.prices) == 1
    price = week1.prices[0]
    assert price.amount == 300.0
    assert price.currency == "EUR"
    assert price.includes == ["tuition"]


def test_location():
    week1, _ = _offerings()
    assert week1.location is not None
    assert week1.location.city == "Dublin"
    assert week1.location.country == "IE"
    assert week1.location.venue is not None
    assert "DanceHouse" in week1.location.venue
    assert "Dublin 1" in week1.location.venue


def test_faculty_roster_with_roles_no_affiliations():
    week1, _ = _offerings()
    names = {t.name: t.role for t in week1.teachers}
    assert names == {
        "Anne Maher": "Ballet & Repertoire",
        "Filipe Portugal": "Ballet & Repertoire",
        "Fiona Brockway": "Ballet & Repertoire",
        "Kate Lyons": "Ballet & Repertoire",
        "Dominic Harrison": "Ballet & Repertoire",
        "Hayley Cunningham": "Pilates",
    }
    # The page gives no bios, so no institution is asserted.
    assert all(t.affiliations == [] for t in week1.teachers)


def test_no_requirements_stated():
    # Booking is by registration form; no audition/photos/video stated.
    week1, _ = _offerings()
    assert week1.application.requirements == []


# --- edge: a week whose dates don't parse stays open (season "unknown") --------

_RENDERED_TBA = """
[et_pb_text]
Week 1: Monday 27 July to Friday 31 July 2026
Week 2: Dates to be announced
FOR AGES: 12+ LEVEL: GRADE 4 to PROFESSIONAL PRICE: €300 per week
[/et_pb_text]
"""


def test_undated_week_fails_open():
    offerings = bi._build_offerings(_RENDERED_TBA, _TODAY)
    by_id = {o.id: o for o in offerings}
    tba = by_id["ballet-ireland/summer-intensive-week-2-unknown"]
    assert tba.schedule.start is None
    assert tba.schedule.end is None
    assert tba.schedule.season == "unknown"


# --- the embedded registration form must not leak into the summary/notes -------

_RENDERED_WITH_FORM = """
[et_pb_text]
Week 1: Monday 27 July to Friday 31 July 2026
Week 2: Tuesday 4 August to Saturday 8 August 2026 PRICE: €300 per week
<style>.gform_wrapper{--gf-color:#204ce5;font-size:14px}</style>
FACULTY
<form id="gform_1"><label>Student's Name *</label>
<select><option>Ireland</option><option>France</option></select></form>
2026 Summer Intensive Registration Form * indicates required fields
[/et_pb_text]
"""


def test_registration_form_css_and_fields_do_not_leak_into_notes():
    summary = bi._summary_text(_RENDERED_WITH_FORM)
    # CSS, form field labels, country options, and the gform heading are all gone.
    for junk in ("gform", "--gf-color", "Student's Name", "Ireland", "indicates required fields"):
        assert junk not in summary, junk
    # The real week info survives.
    assert "Week 2: Tuesday 4 August" in summary
    assert "€300 per week" in summary
    # And the last week's notes stay clean (no FACULTY/form tail).
    _, week2 = bi._build_offerings(_RENDERED_WITH_FORM, _TODAY)
    assert "FACULTY" not in (week2.schedule.notes or "")
    assert "Student's Name" not in (week2.schedule.notes or "")
