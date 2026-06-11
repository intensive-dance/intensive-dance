"""Unit tests for the Frankfurt Ballet Masterclasses scraper (single page)."""

from __future__ import annotations

from datetime import date

from selectolax.parser import HTMLParser

from intensive_dance.models import PhotosReq
from intensive_dance.scrapers import frankfurt_ballet_masterclasses as fbm

# The "#ourTeachers" section: two class-teacher cards + the organizer card, each linking to a
# modal whose bio names institutions (mirrors the real page so the DOM parse is exercised).
_TEACHERS_HTML = """
<section id="ourTeachers"><div class="row">
  <div class="col"><a href="#" data-bs-toggle="modal" data-bs-target="#olgaModal">
    <div class="card"><div class="card-body"><div class="mb-2">
      <h4 class="h5">Olga Melnikova</h4>
      <span class="small">Teacher</span><br><span class="small">Classical Ballet</span>
    </div></div></div></a></div>
  <div class="col"><a href="#" data-bs-toggle="modal" data-bs-target="#denisModal">
    <div class="card"><div class="card-body"><div class="mb-2">
      <h4 class="h5">Denis Untila</h4>
      <span class="small">Teacher</span><br><span class="small">Contemporary &amp; Stretching</span>
    </div></div></div></a></div>
  <div class="col"><a href="#" data-bs-toggle="modal" data-bs-target="#ninaModal">
    <div class="card"><div class="card-body"><div class="mb-2">
      <h4 class="h5">Nina Bakhareva</h4>
      <span class="small">Organizer</span><br><span class="small">FBM Founder</span>
    </div></div></div></a></div>
</div></section>
<div class="modal" id="olgaModal"><div class="modal-body">
  <span class="small">Professor for Classical Dance at Palucca University of Dance Dresden</span>
  <ul><li>Educated at the Vaganova Ballet Academy.</li>
  <li>Career at the Mariinsky Theatre (Kirov Ballet) 1989-2000, then Semperoper Ballett Dresden.</li>
  </ul></div></div>
<div class="modal" id="denisModal"><div class="modal-body">
  <span class="small">Dancer and Choreographer</span>
  <ul><li>Trained at the Conservatory of Vienna.</li>
  <li>Soloist with Ballet Kiel (2001); from 2006 with Aalto Ballett Essen.</li></ul></div></div>
<div class="modal" id="ninaModal"><div class="modal-body"><p>Vaganova graduate, FIBC founder.</p>
  </div></div>
"""

# Inline snippet mirroring the main page structure (FAQ + Our Teachers + schedule).
_MAIN_PAGE_TEXT = (
    "Frankfurt Ballet Masterclasses Ages 8-18 | A two-day ballet intensive. "
    "Register Now! "
    "Our Teachers Olga Melnikova Teacher Classical Ballet "
    "Denis Untila Teacher Contemporary & Stretching "
    "Nina Bakhareva Organizer FBM Founder "
    "Masterclass schedule Classes divided by Age Groups: GROUP A (Ages 8-11) GROUP B (Ages 12-18) "
    "Masterclass Fees Participation Fee - EUR 265, Registration Fee - EUR 25, "
    "refine classical and contemporary dance technique "
    "August 22 - 23, 2026 | Frankfurt, Germany "
    "Who is the Masterclass for? The masterclass is designed for experienced young amateur dancers. "
    "Group A (Ages 8–11): Dancers with at least 2 years of experience. Pointe work is not required. "
    "Group B (Ages 12–18): Dancers with at least 3 to 4 years of experience. "
    "Is there an application process? Yes. The number of participants is limited. "
    "How do I apply? Complete the online registration form, which requires "
    "A short summary of your dancing background "
    "Three photos as follows: "
    "For Group A (ages 8-11): 3 dance poses (in profile plié in first position, "
    "first arabesque 90°, à la seconde 90°) "
    "For Group B (ages 12-18): 3 dance poses on pointe (first arabesque 90°, "
    "à la seconde 90°, relevé in fourth position croisé) "
    "Full payment (EUR 25 non-refundable application fee + participation fee)"
)

_TERMS_PAGE_TEXT = (
    "TERMS & CONDITIONS OF PARTICIPATION "
    "1. Application Requirements "
    "Three photos as follows: For Group A (ages 8-11): 3 dance poses "
    "3. Application Deadline "
    "The closing date for applications is August 15, 2026 . "
    "Places will be allocated to qualifying applicants on a first-come, first-served basis."
)

# The published class timetable: a real HTML table read by column header.
# Group A (8–11) does Pre-Pointe; Group B (12–18) does Pointe — the per-group difference.
_TIMETABLE_HTML = """
<table>
  <tr><th>GROUP</th><th>DAY</th><th>DATE</th><th>START</th><th>END</th><th>CLASS</th><th>TEACHER</th><th>ROOM</th></tr>
  <tr><td>A</td><td>Day 1</td><td>22-Aug</td><td>09:45</td><td>11:15</td><td>Contemporary</td><td>Denis Untila</td><td>4010</td></tr>
  <tr><td>A</td><td>Day 1</td><td>22-Aug</td><td>11:30</td><td>12:30</td><td>Stretching</td><td>Denis Untila</td><td>4010</td></tr>
  <tr><td>A</td><td>Day 1</td><td>22-Aug</td><td>12:45</td><td>14:15</td><td>Classical Ballet</td><td>Olga Melnikova</td><td>4010</td></tr>
  <tr><td>A</td><td>Day 1</td><td>22-Aug</td><td>14:30</td><td>15:30</td><td>Pre Pointe Class</td><td>Olga Melnikova</td><td>4010</td></tr>
  <tr><td>A</td><td>Day 2</td><td>23-Aug</td><td>11:30</td><td>13:00</td><td>Classical Ballet</td><td>Olga Melnikova</td><td>4010</td></tr>
  <tr><td>A</td><td>Day 2</td><td>23-Aug</td><td>13:15</td><td>14:45</td><td>Contemporary</td><td>Denis Untila</td><td>4010</td></tr>
  <tr><td>B</td><td>Day 1</td><td>22-Aug</td><td>09:45</td><td>11:15</td><td>Classical Ballet</td><td>Olga Melnikova</td><td>4015</td></tr>
  <tr><td>B</td><td>Day 1</td><td>22-Aug</td><td>11:30</td><td>12:30</td><td>Pointe Class</td><td>Olga Melnikova</td><td>4015</td></tr>
  <tr><td>B</td><td>Day 2</td><td>23-Aug</td><td>11:30</td><td>13:00</td><td>Contemporary</td><td>Denis Untila</td><td>4015</td></tr>
</table>
"""


def test_date_range_dash_and_slash():
    assert fbm._date_range("August 22 - 23, 2026 | Frankfurt") == (
        date(2026, 8, 22),
        date(2026, 8, 23),
    )
    assert fbm._date_range("August 22/23, 2026") == (date(2026, 8, 22), date(2026, 8, 23))


def test_date_range_absent():
    assert fbm._date_range("no dated edition yet") == (None, None)


def test_age_range():
    assert fbm._age_range("Ages 8-18 | A two-day ballet intensive") == {"min": 8, "max": 18}
    assert fbm._age_range("for dancers aged 8 to 18") == {"min": 8, "max": 18}


def test_genres():
    assert fbm._genres("refine classical and contemporary dance technique") == [
        "classical",
        "contemporary",
    ]


def test_prices_participation_and_registration_fees():
    # Currency precedes the amount ("EUR 265"); participation = tuition,
    # registration = non-refundable application fee.
    prices = fbm._prices("Masterclass Fees Participation Fee - EUR 265, Registration Fee - EUR 25,")
    assert [(p.amount, p.currency, p.label, p.includes) for p in prices] == [
        (265.0, "EUR", "Participation fee", ["tuition"]),
        (25.0, "EUR", "Registration fee", []),
    ]


def test_prices_absent_when_no_fee_line():
    assert fbm._prices("No fees mentioned here.") == []


def test_requirements_defined_poses_from_faq():
    # The FAQ states "Three photos as follows" → two PhotosReq (one per age group).
    reqs = fbm._requirements(_MAIN_PAGE_TEXT)
    assert len(reqs) == 2
    assert all(isinstance(r, PhotosReq) for r in reqs)
    assert all(r.specificity == "defined-poses" for r in reqs)
    # Group A poses are on profile (no pointe); Group B are on pointe.
    group_a, group_b = reqs
    assert any("plié" in p.lower() for p in group_a.poses)
    assert "pointe" in (group_b.notes or "").lower()


def test_requirements_none_when_open():
    # No photo/video hint → explicit `none` (open registration, nothing stated).
    reqs = fbm._requirements("Application requirements: open to all, no audition. Cancellation")
    assert [r.type for r in reqs] == ["none"]


def test_requirements_video_when_stated():
    (req,) = fbm._requirements("Application requirements: please submit a video. Cancellation")
    assert req.type == "video"


def test_deadline_from_terms():
    assert fbm._deadline(_TERMS_PAGE_TEXT) == date(2026, 8, 15)


def test_deadline_absent():
    assert fbm._deadline("Terms and conditions, no deadline mentioned.") is None


def test_teachers_extracted_with_affiliations():
    teachers = fbm._teachers(HTMLParser(_TEACHERS_HTML))
    # the organizer card (Nina) is skipped; the two class teachers are kept in order
    assert [t.name for t in teachers] == ["Olga Melnikova", "Denis Untila"]
    olga, denis = teachers
    assert olga.role == "Teacher (Classical Ballet)"
    # affiliations mined from the modal bio (aliases like Kirov dedupe to Mariinsky)
    assert [a.organization for a in olga.affiliations] == [
        "Vaganova Ballet Academy",
        "Mariinsky Theatre",
        "Semperoper Ballett Dresden",
        "Palucca Hochschule für Tanz Dresden",
    ]
    assert denis.role == "Teacher (Contemporary & Stretching)"
    assert [a.organization for a in denis.affiliations] == [
        "Aalto Ballett Essen",
        "Ballett Kiel",
        "Conservatory of Vienna",
    ]


def test_teachers_absent_section():
    assert fbm._teachers(HTMLParser("<div>no teachers section here</div>")) == []


def test_sessions_per_age_group():
    sessions = fbm._sessions(HTMLParser(_TIMETABLE_HTML), _MAIN_PAGE_TEXT)
    assert [s.label for s in sessions] == ["Group A (ages 8–11)", "Group B (ages 12–18)"]
    group_a, group_b = sessions
    assert group_a.age_range == {"min": 8, "max": 11}
    assert group_b.age_range == {"min": 12, "max": 18}
    # the per-group difference: A trains Pre-Pointe, B trains Pointe
    assert "Pre Pointe Class" in (group_a.notes or "")
    assert "Pointe Class" in (group_b.notes or "") and "Pre Pointe" not in (group_b.notes or "")
    # real hours/day read off the grid (Day 1 = 5 h, avg 4 h/day)
    assert "Day 1: 5 h" in (group_a.notes or "")
    assert "≈4 h/day" in (group_a.notes or "")


def test_sessions_absent_when_no_timetable():
    assert fbm._sessions(HTMLParser("<div>no schedule table here</div>"), _MAIN_PAGE_TEXT) == []


def test_build_offering_includes_teachers_deadline_photos_and_sessions():
    # The page carries text content (dates/prices/FAQ), teacher markup, and the timetable.
    offering = fbm._build_offering(
        f"<html><body>{_MAIN_PAGE_TEXT}{_TEACHERS_HTML}{_TIMETABLE_HTML}</body></html>",
        _TERMS_PAGE_TEXT,
        date.today(),
    )
    assert offering is not None
    assert [t.name for t in offering.teachers] == ["Olga Melnikova", "Denis Untila"]
    assert offering.application.deadline == date(2026, 8, 15)
    assert all(isinstance(r, PhotosReq) for r in offering.application.requirements)
    assert [s.label for s in offering.schedule.sessions] == [
        "Group A (ages 8–11)",
        "Group B (ages 12–18)",
    ]
