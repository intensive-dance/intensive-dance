"""Unit tests for the Bayer Ballet Academy scraper (single Wix page, two editions).

Offline, inline HTML/text snippets — no network. They pin: the two-edition split
(3-week Junior vs 6-week Pre-Professional), per-edition dates / ages / genres /
prices (the 6-week-only disciplines must not leak into Junior), the shared 2026
faculty roster with academy affiliations, and the audition-or-video requirement.
Zero-width spaces are embedded to mirror the live Wix markup.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import VideoReq
from intensive_dance.scrapers import bayer_ballet_academy as bba

# A trimmed copy of the live page: the shared curriculum block (with the
# "(*) … 6-week only" disciplines), both edition blocks with their own dates /
# ages / tuition, and the 2026 faculty roster. Zero-width spaces (​) and an
# nbsp split tokens as Wix does live.
PAGE = (
    "<html><body>"
    "<h2>Master Vaganova &amp; Contemporary Instruction</h2>"
    "<p>Vaganova Ballet Technique</p>"
    "<p>Classical Ballet Repertoire</p>"
    "<p>Pas de Deux* (for lead roles)</p>"
    "<p>Character Dance*</p>"
    "<p>Contemporary Dance</p>"
    "<p>Pointe/Pre-Pointe*</p>"
    "<p>Variations</p>"
    "<p>(*) denotes elements of the 6-week intensive only</p>"
    "<h3>Junior Intensive</h3>"
    "<p>3-Week Summer Intensive</p>"
    "<p>June 8 – June 26</p>"
    "<p>Ages 8 –​10</p>"
    "<p>Sample Program</p>"
    "<p>Ballet Technique</p>"
    "<p>Repertoire / Character Dance</p>"
    "<p>Intensive culminates in a studio demonstration.</p>"
    "<p>Tuition: $2,000.00</p>"
    "<p>Early Bird Discount: $1,800.00 if paid within 5 days of audition</p>"
    "<h3>pre–professional intensive</h3>"
    "<p>6-Week Summer Intensive</p>"
    "<p>June 29 – August 9</p>"
    "<p>Ages 9 –​18 +</p>"
    "<p>Pas De Deux class (M/W/F)</p>"
    "<p>Contemporary (T/TH)</p>"
    "<p>Repertoire</p>"
    "<p>Character Dance</p>"
    "<p>Intensive culminates in a performance. Date TBD</p>"
    "<p>Tuition: $5,450.00</p>"
    "<p>Early Bird Discount: $4,9​50 if paid within 5 days of audition</p>"
    "<p>Performance Fee (Applies to All): $250</p>"
    "<p>Costume Rental Fee: Varies</p>"
    "<p>Schedule an In-Person Audition. Video submissions are also accepted.</p>"
    "<h2>2026 Summer Intensive Faculty</h2>"
    "<p>Inna</p><p> Bayer</p>"
    "<p>Bayer Ballet Founder, Artistic Director &amp; Instructor</p>"
    "<p>Education</p>"
    "<p>Master's Degree, Pedagogy with Honors, Bolshoi Ballet Academy</p>"
    "<p>Read More</p>"
    "<p>Maiia</p><p> Musaeva</p>"
    "<p>Instructor | Classical Ballet</p>"
    "<p>Education</p>"
    "<p>Master's Degree, Kazan State University of Culture and Arts</p>"
    "<p>Read More</p>"
    "<p>Elena Nikolaeva</p>"
    "<p>Instructor | Classical Ballet</p>"
    "<p>Education</p>"
    "<p>Ballet Dancer, Vaganova Ballet Academy</p>"
    "<p>Read More</p>"
    "<p>Past Summer Intensive Performance</p>"
    "</body></html>"
)


def _offerings():
    return {o.id: o for o in bba._build_offerings(PAGE, date(2026, 6, 8))}


def test_emits_two_editions():
    offs = _offerings()
    assert set(offs) == {
        "bayer-ballet-academy/junior-intensive-2026",
        "bayer-ballet-academy/pre-professional-intensive-2026",
    }


def test_junior_edition_fields():
    o = _offerings()["bayer-ballet-academy/junior-intensive-2026"]
    assert o.title == "Junior Intensive — 3-Week Summer Intensive"
    assert o.schedule.start == date(2026, 6, 8)
    assert o.schedule.end == date(2026, 6, 26)
    assert o.age_range == {"min": 8, "max": 10}
    # 3-week edition: no 6-week-only pointe / contemporary leaks in.
    assert o.genres == ["classical", "character", "repertoire"]
    assert [(p.amount, p.label) for p in o.prices] == [
        (2000.0, "Tuition"),
        (1800.0, "Tuition (early bird, paid within 5 days of audition)"),
    ]


def test_pre_professional_edition_fields():
    o = _offerings()["bayer-ballet-academy/pre-professional-intensive-2026"]
    assert o.schedule.start == date(2026, 6, 29)
    assert o.schedule.end == date(2026, 8, 9)
    # "Ages 9 –18 +" → open-topped (the "+" drops the upper bound).
    assert o.age_range == {"min": 9}
    # 6-week edition draws on the shared curriculum → pointe + contemporary present.
    assert "pointe" in o.genres
    assert "contemporary" in o.genres
    # The zero-width-split "$4,9​50" still parses; the performance fee is captured.
    assert [(p.amount, p.label) for p in o.prices] == [
        (5450.0, "Tuition"),
        (4950.0, "Tuition (early bird, paid within 5 days of audition)"),
        (250.0, "Performance fee"),
    ]


def test_shared_faculty_with_affiliations():
    o = _offerings()["bayer-ballet-academy/junior-intensive-2026"]
    names = [t.name for t in o.teachers]
    assert names == ["Inna Bayer", "Maiia Musaeva", "Elena Nikolaeva"]
    inna = o.teachers[0]
    assert "Founder" in (inna.role or "")
    assert inna.affiliations[0].organization == "Bolshoi Ballet Academy"
    elena = o.teachers[2]
    assert elena.affiliations[0].organization == "Vaganova Ballet Academy"
    # No academy keyword in Maiia's block → no affiliation invented.
    assert o.teachers[1].affiliations == []


def test_requirements_audition_or_video():
    o = _offerings()["bayer-ballet-academy/pre-professional-intensive-2026"]
    assert len(o.application.requirements) == 1
    req = o.application.requirements[0]
    assert isinstance(req, VideoReq)
    assert req.specificity == "unspecific"
    assert "$40 audition fee" in (o.application.notes or "")


def test_age_open_topped_plus():
    assert bba._age_range("Ages 9 –18 +") == {"min": 9}
    assert bba._age_range("Ages 8 –10") == {"min": 8, "max": 10}


def test_dates_need_year_from_page():
    # The edition line carries no year; without the faculty-stamp year, no dates.
    assert bba._dates("June 8 – June 26", None) == (None, None)
    assert bba._dates("June 29 – August 9", 2026) == (date(2026, 6, 29), date(2026, 8, 9))


def test_year_from_faculty_stamp():
    assert bba._year("2026 Summer Intensive Faculty") == 2026
    assert bba._year("no roster yet") is None
