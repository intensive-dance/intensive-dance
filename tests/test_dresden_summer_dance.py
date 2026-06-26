"""Offline tests for the Dresden Summer Dance (Dance-Workshop e.V.) scraper.

Inline HTML mirrors the Duda/checkdomain service-list markup (div.listText →
span.itemName + div.itemText) of the home + levels pages. No network.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import dresden_summer_dance as dsd

HOME = """
<html><body>
<title>SUMMER 2026</title>
<h1>Dresden Summer Dance</h1>
<h2>August 3-15, 2026</h2>
</body></html>
"""


def _block(name: str, body: str) -> str:
    return (
        '<div class="listText">'
        f'<span class="itemName">{name}</span>'
        f'<div class="itemText">{body}</div>'
        "</div>"
    )


LEVELS = (
    "<html><body>"
    + _block(
        "Junior",
        "Students of vocational training from 12-15 years old with no less than 2 years "
        "of dance classes. They will be offered daily ballet, contemporary, variations, "
        "etude and repertoire. This workshop is created for local, national and "
        "international dancers from the ages of 13-16 years old. "
        "Membership fee: 30 Euros (Non-Refundable) from January 1st Tuition: 780 Euros "
        "Schedule - august 3rd - 15th: • Ballet 10:30 – 12:00 • "
        "Variation/pointe work 12:15 – 13:15",
    )
    + _block(
        "Intermediate",
        "Students of vocational training from 13-16 years old with no less than 4 years "
        "of dance classes. This workshop is created for ... from the ages of 14-17 years old. "
        "Membership fee: 30 Euros (Non-Refundable) from January 1st Tuition: 780 Euros "
        "Schedule - august 3rd - 15th: • Ballet 10:30 – 12:00",
    )
    + _block(
        "Senior",
        "Professional dancers & Students in professional education from 14 + years old. "
        "This workshop is created for ... from the ages of 15+ years old. "
        "Membership fee: 30 Euros (Non-Refundable) from January 1st Tuition: 780 Euros "
        "Schedule - august 3rd - 15th: • Ballet 10:30 – 12:00",
    )
    + _block(
        "Childrens & Youth Dance",
        "The children and youth dance classes ... Besides the creative dance, this course "
        "also includes daily ballet classes and a project. This workshop is created for ... "
        "from the ages of 8-17 years old. "
        "Membership fee: 30 Euros (Non-Refundable) from January 1st Tuition: 340 Euros "
        "Schedule - 10th - 15th: August • Ballet or Creative Dance 09:00 – 10:15",
    )
    + _block(
        "Pedagogic tutorial",
        "The Dance teachers Workshop course is directed to professionally employed dance "
        "teachers ... from the ages of 23+ years old. "
        "Membership fee: 30 Euros (Non-Refundable) from January 1st Tuition: 190 Euros "
        "Schedule to be announced",
    )
    + _block(
        "Dance Courses for Adults",
        "It is never too late to start. ... dance classes in Ballet or Contemporary for "
        "adults. This workshop is created for ... hobby dance enthusiasts from about 16+ "
        "years of age Membership fee: 30 Euros (Non-Refundable) from January 1st "
        "Tuition: 90 Euros Schedule - 10 - 13: August • Ballet or Contemporary Dance "
        "19:00 – 20:30",
    )
    + _block(
        "Classes observation",
        "We offer the opportunity to teachers, choreographers and dance professionals to "
        "observe the daily classes. Membership fee: 30 Euros Tuition 1 Week: 70 Euros "
        "From august 3rd to 9th",
    )
    + _block(
        "Day Ticket",
        "Category: Day ticket 60 minutes: €24.00 half day (2,5 hours): €60.00",
    )
    + "</body></html>"
)


def _by_id(offerings, suffix):
    return next(o for o in offerings if o.id.endswith(suffix))


def test_emits_only_in_scope_courses():
    offerings = dsd._build_offerings(HOME, LEVELS)
    ids = sorted(o.id for o in offerings)
    assert ids == [
        "dresden-summer-dance/adults-2026",
        "dresden-summer-dance/children-youth-2026",
        "dresden-summer-dance/vocational-2026",
    ]


def test_vocational_folds_three_age_sessions():
    o = _by_id(dsd._build_offerings(HOME, LEVELS), "vocational-2026")
    assert o.title == "Dresden Summer Dance 2026 — Vocational / Professional"
    assert o.schedule.start == date(2026, 8, 3)
    assert o.schedule.end == date(2026, 8, 15)
    labels = [s.label for s in o.schedule.sessions]
    assert labels == ["Junior", "Intermediate", "Senior"]
    assert o.schedule.sessions[0].age_range == {"min": 13, "max": 16}
    assert o.schedule.sessions[2].age_range == {"min": 15, "max": None}
    # open-topped Senior keeps the overall band open-topped
    assert o.age_range == {"min": 13, "max": None}
    assert o.level == ["pre-professional", "professional"]
    # the differing first-sentence age phrasing is preserved verbatim
    assert "12-15" in (o.schedule.sessions[0].notes or "")


def test_genres_scoped_to_curriculum():
    offerings = dsd._build_offerings(HOME, LEVELS)
    voc = _by_id(offerings, "vocational-2026")
    assert voc.genres == ["classical", "contemporary", "repertoire", "pointe"]
    children = _by_id(offerings, "children-youth-2026")
    assert children.genres == ["classical"]  # creative dance is not a ballet genre
    adults = _by_id(offerings, "adults-2026")
    assert adults.genres == ["classical", "contemporary"]


def test_prices_membership_and_tuition():
    voc = _by_id(dsd._build_offerings(HOME, LEVELS), "vocational-2026")
    labels = {(p.label, p.amount, p.type) for p in voc.prices}
    assert ("Membership fee", 30.0, "registration") in labels
    assert ("Tuition", 780.0, "tuition") in labels
    assert all(p.currency == "EUR" for p in voc.prices)
    mem = next(p for p in voc.prices if p.label == "Membership fee")
    assert "Non-Refundable" in (mem.notes or "")


def test_children_and_adults_dates_and_ages():
    offerings = dsd._build_offerings(HOME, LEVELS)
    children = _by_id(offerings, "children-youth-2026")
    assert children.schedule.start == date(2026, 8, 10)
    assert children.schedule.end == date(2026, 8, 15)
    assert children.age_range == {"min": 8, "max": 17}
    assert children.level == ["open"]
    adults = _by_id(offerings, "adults-2026")
    assert adults.schedule.start == date(2026, 8, 10)
    assert adults.schedule.end == date(2026, 8, 13)
    assert adults.age_range == {"min": 16, "max": None}


def test_location_and_org():
    o = dsd._build_offerings(HOME, LEVELS)[0]
    assert o.location is not None
    assert o.location.venue == "Pegasus Theaterschule"
    assert o.location.city == "Dresden"
    assert o.organization.country == "DE"


def test_missing_year_raises_rather_than_empty():
    # A degraded home fetch (no edition marker) must raise, not emit [].
    with pytest.raises(ValueError):
        dsd._build_offerings("<html><body><h1>Dresden Summer Dance</h1></body></html>", LEVELS)
