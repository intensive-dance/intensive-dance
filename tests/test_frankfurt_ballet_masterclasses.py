"""Unit tests for the Frankfurt Ballet Masterclasses scraper (single page)."""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import frankfurt_ballet_masterclasses as fbm


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


def test_requirements_none_when_open():
    # Open registration → an explicit `none` requirement (not `[]`, which means "not stated").
    reqs = fbm._requirements(
        "Application requirements: open to all, no audition. Cancellation Policy"
    )
    assert [r.type for r in reqs] == ["none"]


def test_requirements_video_when_stated():
    (req,) = fbm._requirements("Application requirements: please submit a video. Cancellation")
    assert req.type == "video"


def test_requirements_photo_when_stated():
    (req,) = fbm._requirements("Application requirements: send a photo in first arabesque. Contact")
    assert req.type == "photos"
