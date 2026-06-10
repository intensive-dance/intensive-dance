"""Unit tests for the Japan Ballet Intensives (JBI) scraper.

These pin the per-page regex parsing of the one Spring Intensive edition — the
clean English date span, the open-ended age band, the curriculum-driven genres,
the JPY price ladder (incl. the Wix-split 2-day amount "25 .000"), the faculty
roll (international guest + local contemporary teacher + pianist), and the
"registrations closed" status with the kept audition note. Inline strings, no
network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import NoneReq
from intensive_dance.scrapers import japan_ballet_intensives as jbi

# Flattened page texts mirroring the real (Wix) server-rendered bodies.
_SCHEDULE = "Schedule March 21 - 22, 2026 14:00 - 16:00 Classic Ballet & Pointes 16:20 - 17:50 Contemporary Dance"
_COURSES = (
    "Courses All classes are open for participants age 13 and above with a minimum of 3 years "
    "in ballet education. Classic Ballet & Pointes (120 minutes) Contemporary Dance (90 minutes)"
)
_TUITION = (
    "Tuition 2-Day Workshop 4 classes 25 .000 Yen One day 2 classes 15.000 Yen "
    "Sibling Reduction 50% reduction on the regular price starting from the second "
    "participant of the same family."
)
_FACULTY = "FACULTY Wilfried Jacobs Belgium Classical Ballet Mosa Ballet School Head of Faculty"
_PIANISTS = "PIANIST Noriko Yamamoto"
_HOME = (
    "Spring Ballet Intensive in Osaka Registrations are now closed Welcome to the Spring Ballet "
    "Intensive in Osaka! The classical classes will be taught by Wilfried Jacobs, Head of Faculty "
    "of the Mosa Ballet School. We have found a great 'local' contemporary teacher in Mr. Minoru "
    "Harata. During the Intensive, participants will have the opportunity to audition for the Mosa "
    "Ballet School's Summer Intensive. This high-level Summer Intensive will be held at the end of "
    "August 2026 in Liège, Belgium."
)

_TEXTS = {
    "": _HOME,
    "schedule": _SCHEDULE,
    "courses": _COURSES,
    "tuition": _TUITION,
    "faculty": _FACULTY,
    "pianists": _PIANISTS,
}


def _offering():
    offerings = jbi._build_offerings(_TEXTS, date(2026, 6, 9))
    assert len(offerings) == 1
    return offerings[0]


def test_date_range_clean_english_span():
    assert jbi._date_range(_SCHEDULE) == (date(2026, 3, 21), date(2026, 3, 22))


def test_date_range_absent():
    assert jbi._date_range("no dated edition announced yet") == (None, None)


def test_no_offering_without_dates():
    texts = dict(_TEXTS, schedule="Schedule TBA")
    assert jbi._build_offerings(texts, date(2026, 6, 9)) == []


def test_age_range_open_topped():
    # "age 13 and above" → min 13, no upper bound.
    assert jbi._age_range(_COURSES) == {"min": 13, "max": None}


def test_genres_from_curriculum():
    # Classic Ballet & Pointes + Contemporary Dance; Character (org blurb) not taught.
    assert jbi._genres(_COURSES) == ["classical", "pointe", "contemporary"]


def test_prices_jpy_ladder_tax_inclusive():
    prices = jbi._prices(_TUITION)
    amounts = {p.label: p.amount for p in prices}
    assert amounts["2-Day Workshop (4 classes, tax incl.)"] == 25000.0
    assert amounts["One day (2 classes, tax incl.)"] == 15000.0
    assert all(p.currency == "JPY" for p in prices)
    assert all(p.includes == ["tuition"] for p in prices)
    assert all("50% reduction" in (p.notes or "") for p in prices)


def test_teachers_guest_local_and_pianist():
    teachers = jbi._teachers(_HOME, _FACULTY, _PIANISTS)
    by_name = {t.name: t for t in teachers}
    assert set(by_name) == {"Wilfried Jacobs", "Minoru Harata", "Noriko Yamamoto"}
    jacobs = by_name["Wilfried Jacobs"]
    assert jacobs.role == "Classical Ballet"
    assert jacobs.affiliations[0].organization == "Mosa Ballet School"
    assert jacobs.affiliations[0].slug == "mosa-ballet-school"
    assert by_name["Noriko Yamamoto"].role == "Pianist"


def test_status_closed_and_audition_note_kept():
    assert jbi._status(_HOME) == "closed"
    note = jbi._audition_note(_HOME)
    assert note is not None
    assert "audition for the Mosa Ballet School" in note
    assert note.endswith("Belgium.")


def test_offering_shape():
    o = _offering()
    assert o.id == "japan-ballet-intensives/spring-intensive-osaka-2026"
    assert o.title == "Spring Ballet Intensive in Osaka 2026"
    assert o.schedule.season == "2026"
    assert o.schedule.timezone == "Asia/Tokyo"
    assert o.location is not None
    assert o.location.venue == "Garage Art Space"
    assert o.location.city == "Osaka"
    assert o.location.country == "JP"
    assert o.lifecycle == "scheduled"  # closed registration ≠ cancelled course
    # No audition brief described → requirements stay unknown (not [NoneReq]).
    assert o.application.requirements == []
    assert not any(isinstance(r, NoneReq) for r in o.application.requirements)
    assert o.application.status == "closed"
