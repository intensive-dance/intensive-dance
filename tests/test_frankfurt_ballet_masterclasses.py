"""Unit tests for the Frankfurt Ballet Masterclasses scraper (single page)."""

from __future__ import annotations

from datetime import date

from intensive_dance.models import PhotosReq
from intensive_dance.scrapers import frankfurt_ballet_masterclasses as fbm

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


def test_teachers_olga_melnikova_and_denis_untila():
    teachers = fbm._teachers(_MAIN_PAGE_TEXT)
    names = [t.name for t in teachers]
    assert "Olga Melnikova" in names
    assert "Denis Untila" in names
    olga = next(t for t in teachers if t.name == "Olga Melnikova")
    assert "Classical Ballet" in (olga.role or "")
    assert any("Palucca" in (a.organization or "") for a in olga.affiliations)


def test_teachers_empty_when_no_names():
    assert fbm._teachers("No teachers mentioned here.") == []


def test_build_offering_includes_teachers_deadline_and_photos():
    offering = fbm._build_offering(
        f"<html><body>{_MAIN_PAGE_TEXT}</body></html>",
        _TERMS_PAGE_TEXT,
        date.today(),
    )
    assert offering is not None
    assert len(offering.teachers) == 2
    assert offering.application.deadline == date(2026, 8, 15)
    assert all(isinstance(r, PhotosReq) for r in offering.application.requirements)
