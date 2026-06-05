"""Unit tests for the MOSA Ballet School scraper (Squarespace + sitemap).

These pin the discovery filter (which sitemap events are real training offerings)
and the regex-heavy parsing of the event pages — dates, ages (title vs noisy
body), kind, prices (course fee vs accommodation/audition noise), status, and the
European money formats. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import mosa_ballet_school as mosa


# --- discovery filter ---------------------------------------------------------


def test_in_scope_keeps_training_events():
    assert mosa._in_scope("august-signature-intensive-course-2026-age-12-29-231")
    assert mosa._in_scope("exploring-ballet-other-dances-age-8-12-august-2026-232")
    assert mosa._in_scope("masterclass-charleston-222")
    assert mosa._in_scope("july-mosa-intensive-2026-230")


def test_in_scope_drops_non_training_events():
    for slug in [
        "online-auditions-for-2026-2027-213",
        "annual-gala-2023-at-15-00-85",
        "annual-recital-2026-friday-3-july-at-7pm-251",
        "workshop-dance-and-parkinson-s-disease-82",
        "admission-test-mosa-preparation-program-9-12-12-june-2026-250",
        "open-doors-april-2026-by-registration-only-245",
    ]:
        assert not mosa._in_scope(slug), slug


def test_kind_from_slug():
    assert mosa._kind("august-signature-intensive-course-2026") == "intensive"
    assert mosa._kind("exploring-ballet-other-dances-age-8-12") == "workshop"
    assert mosa._kind("masterclass-charleston-222") == "masterclass"


def test_is_past_year_relative_to_run_year():
    # The cutoff tracks the run year, so 2025 is "past" in 2026 but not in 2025;
    # a slug with no year (or a coming year) is never pre-filtered out.
    today = date(2026, 6, 1)
    assert mosa._is_past_year("annual-gala-2023-at-15-00-85", today)
    assert mosa._is_past_year("july-mosa-intensive-2025-200", today)
    assert not mosa._is_past_year("july-mosa-intensive-2026-230", today)
    assert not mosa._is_past_year("online-auditions-for-2026-2027-213", today)
    assert not mosa._is_past_year("masterclass-charleston-222", today)
    assert not mosa._is_past_year("july-mosa-intensive-2025-200", date(2025, 6, 1))


# --- dates --------------------------------------------------------------------


def test_dates_starts_ends():
    text = "Starts 14 August 2026 9:00 AM Ends 26 August 2026 6:15 PM"
    assert mosa._dates(text) == (date(2026, 8, 14), date(2026, 8, 26))


def test_dates_absent():
    assert mosa._dates("no dates rendered here") == (None, None)


# --- ages: clean title/slug, noisy body needs an "aged" cue -------------------


def test_age_from_title():
    assert mosa._age_range("August Signature Intensive Course 2026 (age 12-29)") == {"min": 12, "max": 29}


def test_age_body_fallback_requires_aged_cue():
    # "3 to 6 people" (shared room) in the body must NOT become an age range.
    body = "Shared room (3 to 6 people). For dancers aged 12 to 21."
    assert mosa._age_range("July Mosa Intensive 2026", body) == {"min": 12, "max": 21}


def test_age_none_when_only_room_numbers():
    assert mosa._age_range("July Mosa Intensive 2026", "Shared room (3 to 6 people).") is None


# --- prices: only "<N> days … with lunch" course fees -------------------------


def test_prices_keep_course_fee_with_lunch():
    text = "6 days (4 classes per day) with lunch 749.00 € or 12 days (4 classes per day) with lunch 1,299.00 €"
    assert [(p.amount, p.label) for p in mosa._prices(text)] == [
        (749.0, "6 days with lunch"),
        (1299.0, "12 days with lunch"),
    ]


def test_prices_drop_accommodation_and_audition():
    # No "lunch" cue → accommodation / audition amounts are skipped.
    assert mosa._prices("Single room 480 EUR for one week") == []
    assert mosa._prices("Audition at Mosa: 120 EUR for 6 days") == []


# --- status -------------------------------------------------------------------


def test_status():
    assert mosa._status("Registrations Closed") == "closed"
    assert mosa._status("Registration is open — register now") == "open"
    assert mosa._status("starts 14 August") is None
