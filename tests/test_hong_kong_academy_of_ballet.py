"""Unit tests for the Hong Kong Academy of Ballet scraper (server-rendered HTML).

These pin the per-class parsing of the Summer Intensive page: the two programme
weeks as shared sessions, the five age-banded classes (A–E) split into one
Offering each, the open-ended top band (Class E "ages 14+"), HKD course-fee and
early-bird tiers (per-week + 2-week), syllabus-scoped genres, the D/E
pre-professional level + photo requirement + week-tagged guest faculty, and the
9 Feb application-open date. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import hong_kong_academy_of_ballet as hkab

# A trimmed two-class fixture mirroring the live page's flat text: the shared
# week header, an A-class 4-day camp with no level/teacher/requirement, and a
# D-class with pointe, guest faculty per week, and a photo requirement.
_PAGE = (
    "International Guest Teachers & Faculty "  # nav tab — must NOT bound a class
    "Summer Intensive Programme 2026 "
    "[Week 1] 20-25 July, 2026 (Mon-Sat) [Week 2] 27 July - 1 August, 2026 (Mon-Sat) "
    "Venue: Hong Kong Cultural Centre and/or Wong Chuk Hang Studio "
    "Class A (ages 5-6) Over the four-day camp young dancers explore movement. "
    "Programme includes: Ballet Technique Class Body Conditioning Creative & Repertories "
    "Music Appreciation Arts & Crafts "
    "[Week 1] 20-21 July, 23-24 July 2026 [Week 2] 27 -28 July, 30 -31 July 2026 "
    "Venue: Rehearsal Studio, Hong Kong Cultural Centre (10 Salisbury Road) "
    "Course Fee: HK$3,850 per week (4 days) HK$6,930 for 2 weeks (8 days) - 10% off! "
    "Early Bird Offer: For applications submitted on or before 9 March 2026 : "
    "HK$3,500 per week (4 days) HK$6,300 2-weeks (8 days) - additional 10% off! "
    "Application Period : Starts on 9 February 2026. Enrollment based on a "
    "first-come, first-served basis. APPLY HERE "
    "Class D (ages 12-13) For committed dance students. "
    "Programme includes: Ballet Technique Class Body Conditioning Variations Pointe "
    "Contemporary Music Appreciation Rehearsal Dance Showcase "
    "*For students with at least 6 years of ballet training and with pointe experience. "
    "[Week 1] 20-25 July, 2026 (Mon-Sat) Guest Teacher: Sarah Lamb (Principal Dancer of "
    "The Royal Ballet) [Week 2] 27 July - 1 August, 2026 (Mon-Sat) Guest Teacher: "
    "Claresta Alim (Founder and Artistic Director of Indonesia Dance Company) "
    "Venue: Wong Chuk Hang Studio "
    "Course Fee: HK$8,400 per week (6 days) HK$15,120 for 2 weeks (12 days) - 10% off! "
    "[Early Bird Offer] For applications submitted on or before 24 March 2026 : "
    "[HK$7,600 per week (6 days)] [HK$13,680 2-weeks (12 days) - additional 10% off!] "
    "Application Requirements : Applications will open on 9 February 2026 and applicants "
    "must submit photographs as part of their application. APPLY HERE "
    "Photo Requirement for Application (Class D & Class E) "
    "International Guest Teachers & Faculty"
)


def _html(body: str) -> str:
    return f"<html><body>{body}</body></html>"


def _offerings():
    return hkab._build_offerings(_html(_PAGE), "https://x", date(2026, 6, 5))


def test_two_weeks_as_sessions():
    sessions = hkab._sessions(_PAGE)
    assert [(s.label, s.start, s.end) for s in sessions] == [
        ("Week 1", date(2026, 7, 20), date(2026, 7, 25)),
        ("Week 2", date(2026, 7, 27), date(2026, 8, 1)),  # crosses month boundary
    ]


def test_one_offering_per_class():
    offs = _offerings()
    assert [o.id for o in offs] == [
        "hong-kong-academy-of-ballet/summer-intensive-2026-class-a",
        "hong-kong-academy-of-ballet/summer-intensive-2026-class-d",
    ]
    assert all(o.kind == "summer-school" for o in offs)
    assert all(len(o.schedule.sessions) == 2 for o in offs)


def test_class_a_ages_genres_no_level_or_requirement():
    a = _offerings()[0]
    assert a.age_range == {"min": 5, "max": 6}
    # Syllabus has no pointe — must not leak from the shared programme blurb.
    assert "pointe" not in a.genres
    assert a.genres == ["classical", "repertoire"]
    assert a.level == []
    assert a.application.requirements == []
    assert a.teachers == []


def test_class_d_level_pointe_photo_and_week_tagged_faculty():
    d = _offerings()[1]
    assert d.age_range == {"min": 12, "max": 13}
    assert "pointe" in d.genres and "contemporary" in d.genres
    assert d.level == ["pre-professional"]
    reqs = d.application.requirements
    assert len(reqs) == 1 and reqs[0].type == "photos"
    assert [(t.name, t.role) for t in d.teachers] == [
        ("Sarah Lamb", "Guest Teacher (Week 1) — Principal Dancer of The Royal Ballet"),
        (
            "Claresta Alim",
            "Guest Teacher (Week 2) — Founder and Artistic Director of Indonesia Dance Company",
        ),
    ]


def test_prices_full_and_early_bird_tiers():
    a = _offerings()[0]
    priced = {(p.label, p.amount, p.notes) for p in a.prices}
    assert priced == {
        ("Course fee — per week", 3850.0, None),
        ("Course fee — 2 weeks", 6930.0, None),
        ("Early bird — per week", 3500.0, "by 9 March 2026"),
        ("Early bird — 2 weeks", 6300.0, "by 9 March 2026"),
    }
    assert all(p.currency == "HKD" for p in a.prices)
    assert all(p.includes == ["tuition"] for p in a.prices)


def test_application_open_date():
    for o in _offerings():
        assert o.application.opens_at == date(2026, 2, 9)
        assert o.application.url == "https://forms.gle/fEzRBPRzk2zT8Lgz7"


def test_open_ended_top_band():
    # Class E "ages 14+" → lower bound only, no max key.
    cls = hkab._classes("Class E (ages 14+) Programme includes: Ballet Technique Class")
    assert len(cls) == 1
    assert cls[0].age_range == {"min": 14}


def test_drops_edition_already_over():
    assert hkab._build_offerings(_html(_PAGE), "https://x", date(2027, 1, 1)) == []
