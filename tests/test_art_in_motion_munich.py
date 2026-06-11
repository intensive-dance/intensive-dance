"""Offline tests for the Art in Motion Munich summer-school scraper.

The three inline texts mirror the home / information / fees Wix pages, including
the intra-number space in "13 90 €" and the two-digit-year deadline.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import art_in_motion_munich as aim

HOME = (
    "Our next summer stage will take place from 03. 08.2026 till 15.08.2026 "
    "(The deadline for applications is 15.07.26) organized by: Art in Motion Munich"
)
INFO = (
    "What we offer: Classes with Vaganova diplomated teachers. "
    "Date: 3th till 15th of August 2026 "
    "3 classes a day for children 10 -12 years old "
    "Girls: classical class, points, modern dance "
    "Boys: classical class, technic, modern dance "
    "4 classes a day for children 12-15 years old "
    "Girls: classical class, points, repertoire, modern dance "
    "Boys: classical class, mens technic, repertoire, modern dance "
    "4 classes a day for children over 15 years old "
    "Girls: classical class, points, repertoire, modern dance "
    "Boys: classical class, mens technic, repertoire, modern dance © 2015"
)
FEES = "Course Fees: 1 week 790 € 2 weeks 13 90 € Extra : Personal coaching 20 minutes : 35 €"


def test_dates_and_deadline():
    o = aim._build_offering(HOME, INFO, FEES)
    assert o is not None
    assert o.schedule.start == date(2026, 8, 3)
    assert o.schedule.end == date(2026, 8, 15)
    assert o.application.deadline == date(2026, 7, 15)
    assert o.id == "art-in-motion-munich/summer-school-2026"


def test_genres_ages_sessions():
    o = aim._build_offering(HOME, INFO, FEES)
    assert o is not None
    # modern dance / mens technic have no genre-enum value and don't leak.
    assert o.genres == ["classical", "pointe", "repertoire"]
    assert o.age_range == {"min": 10, "max": None}
    labels = [s.label for s in o.schedule.sessions]
    assert labels == ["Ages 10-12", "Ages 12-15", "Ages 15+"]
    over15 = o.schedule.sessions[2]
    assert over15.age_range == {"min": 15, "max": None}
    # Notes must not leak the next band's "N classes a day" header.
    assert "classes a day" not in (o.schedule.sessions[0].notes or "")


def test_prices_normalised():
    o = aim._build_offering(HOME, INFO, FEES)
    assert o is not None
    amounts = {p.label: p.amount for p in o.prices}
    assert amounts == {
        "1 week": 790.0,
        "2 weeks": 1390.0,  # "13 90 €" → 1390
        "Personal coaching (20 minutes)": 35.0,
    }


def test_no_date_yields_nothing():
    assert aim._build_offering("no dates here", INFO, FEES) is None
