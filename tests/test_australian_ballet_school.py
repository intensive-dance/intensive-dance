"""Tests for the Australian Ballet School (Summer School) scraper.

All offline — inline Shopify ``products.json`` snippets captured from the live
collection on 2026-06-08. No network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers.australian_ballet_school import (
    _age_range,
    _build_offerings,
    _deadline,
    _gender,
    _genres,
    _levels,
    _prices,
    _weeks,
)

# A single-week, male-only program (Boys).
_BOYS_BODY = (
    "Specifically designed for boys aged 10 to 13, this five-day program offers "
    "specialised classical ballet coaching from leading male teachers, along with "
    "classes in complementary dance styles such as jazz, contemporary, and character. "
    "Event Dates: Week One: 3 - 7 January 2026 "
    "Online enrolments must close 16 December 2025, unless sold out earlier. "
    "Fee: $700 Early Bird Fee $740 Standard Fee Early Bird pricing ends 31 October 2025 "
    "Eligibility: Male students aged 10 to 13 years. "
    "No audition is required to enrol in our Summer School program"
)

# A two-week program (Open), all genders, with irregular dash spacing.
_OPEN_BODY = (
    "Open to all genders and designed for passionate young dancers aged 8 to 18, this "
    "inspiring 5-day program offers world-class ballet training alongside exciting "
    "classes in jazz, contemporary, and character dance. "
    "Event Dates: Week One: 3 -  7 January 2026 SOLD OUT Week Two: 8 - 12 January 2026 "
    "SOLD OUT Online enrolments must close: 16 December 2025, unless sold out earlier. "
    "Fee: $700 Early Bird Fee $740 Standard Fee. "
    "No audition is required to enrol in our Summer School program"
)

# The Pre-Professional program: bare "Age:" label, advanced-level prerequisite.
_PREPRO_BODY = (
    "Designed for dedicated and advanced-level dancers of all genders aged 14 to 21, "
    "this intensive 5-day program. "
    "Event Dates: Week One: 3 -  7 January 2026 Week Two: 8 - 12 January 2026 "
    "Online enrolments must close: 16 December 2025, unless sold out earlier. "
    "Fee: $700 Early Bird Fee $740 Standard Fee "
    "Age: 14 to 21 years Eligibility: Advanced ballet experience required "
    "(ABS Levels 5 and above)"
)


def _product(handle: str, title: str, body: str, tags: list[str], price: str = "740.00") -> dict:
    return {
        "handle": handle,
        "title": title,
        "tags": tags,
        "variants": [{"title": "Default Title", "price": price}],
        "body_html": body,
    }


_PAYLOAD = {
    "products": [
        _product(
            "summer-school-2026-boys-program",
            "Summer School 2026 - Boys Program",
            _BOYS_BODY,
            ["Boys Only", "Summer School", "VIC"],
        ),
        _product(
            "summer-school-2026-open-program",
            "Summer School 2026 - Open Program",
            _OPEN_BODY,
            ["Summer School", "VIC"],
        ),
        _product(
            "summer-school-2026-pre-professional-program",
            "Summer School 2026 - Pre-Professional Program",
            _PREPRO_BODY,
            ["Summer School", "VIC"],
        ),
        # Non-program products that must be skipped (no "Program" in title).
        _product(
            "2026-summer-school-auditions",
            "Summer School 2026 - Auditions",
            "Audition slots. Week 1 (Tuesday 6 January)",
            ["Summer School", "Summer School Audition"],
            price="130.00",
        ),
        _product(
            "2026-summer-school-graduate-access",
            "2026 Summer School | Graduate Access",
            "Eligibility: 2025 Level 8 Graduates. One classical class per day. "
            "Week 1: 3 - 7 January 2026 Week 2: 8 - 12 January 2026 Cost: $100 per week",
            ["Summer School", "With Form"],
            price="100.00",
        ),
    ]
}


# ---------------------------------------------------------------------------
# _weeks
# ---------------------------------------------------------------------------


def test_weeks_single() -> None:
    weeks = _weeks(_BOYS_BODY)
    assert weeks == [("Week One", date(2026, 1, 3), date(2026, 1, 7))]


def test_weeks_two_with_irregular_spacing() -> None:
    weeks = _weeks(_OPEN_BODY)
    assert weeks == [
        ("Week One", date(2026, 1, 3), date(2026, 1, 7)),
        ("Week Two", date(2026, 1, 8), date(2026, 1, 12)),
    ]


def test_weeks_none_when_undated() -> None:
    assert _weeks("Merchandise. Showbag A (Pencil Case)") == []


# ---------------------------------------------------------------------------
# _age_range / _deadline / _gender / _genres / _levels
# ---------------------------------------------------------------------------


def test_age_range_from_cue() -> None:
    assert _age_range(_BOYS_BODY) == {"min": 10, "max": 13}


def test_age_range_from_label() -> None:
    # Pre-Pro states "aged 14 to 21" in prose and "Age: 14 to 21" under a label.
    assert _age_range(_PREPRO_BODY) == {"min": 14, "max": 21}


def test_age_range_ignores_date_range() -> None:
    # "3 - 7 January" must not be read as an age band.
    assert _age_range("Event Dates: Week One: 3 - 7 January 2026") is None


def test_deadline() -> None:
    assert _deadline(_OPEN_BODY) == date(2025, 12, 16)


def test_deadline_missing() -> None:
    assert _deadline("No enrolment date stated.") is None


def test_gender_boys_only_from_tag() -> None:
    product = _product("x", "Boys Program", _BOYS_BODY, ["Boys Only"])
    assert _gender(_BOYS_BODY, product) == "male"


def test_gender_default_both() -> None:
    product = _product("x", "Open Program", _OPEN_BODY, ["Summer School"])
    assert _gender(_OPEN_BODY, product) == "both"


def test_genres_classical_base_plus_others() -> None:
    genres = _genres(_OPEN_BODY)
    assert genres[0] == "classical"
    assert "contemporary" in genres  # jazz/contemporary map to contemporary
    assert "character" in genres


def test_genres_classical_only_when_no_other_class() -> None:
    assert _genres("World-class ballet training and specialised workshops.") == ["classical"]


def test_levels_pre_professional() -> None:
    levels = _levels(_PREPRO_BODY)
    assert "pre-professional" in levels
    assert "open" in levels


def test_levels_open_default() -> None:
    assert _levels(_OPEN_BODY) == ["open"]


# ---------------------------------------------------------------------------
# _prices
# ---------------------------------------------------------------------------


def test_prices_standard_and_early_bird() -> None:
    product = _product("x", "Open Program", _OPEN_BODY, [])
    prices = _prices(_OPEN_BODY, product)
    by_label = {p.label: p for p in prices}
    assert by_label["Standard fee"].amount == 740.0
    assert by_label["Standard fee"].currency == "AUD"
    assert by_label["Early Bird fee"].amount == 700.0
    assert all(p.includes == ["tuition"] for p in prices)


def test_prices_falls_back_to_variant_when_body_silent() -> None:
    product = _product("x", "Open Program", "No fee stated.", [], price="555.00")
    prices = _prices("No fee stated.", product)
    assert len(prices) == 1
    assert prices[0].amount == 555.0
    assert prices[0].label == "Standard fee"


# ---------------------------------------------------------------------------
# _build_offerings (integration)
# ---------------------------------------------------------------------------


def test_build_offerings_count_and_skips() -> None:
    offs = _build_offerings(_PAYLOAD, date(2026, 6, 8))
    # Boys (1 week) + Open (2) + Pre-Pro (2) = 5; auditions/graduate-access skipped.
    assert len(offs) == 5
    ids = {o.id for o in offs}
    assert "australian-ballet-school/summer-school-2026-boys-program-week-one" in ids
    assert "australian-ballet-school/summer-school-2026-open-program-week-two" in ids
    # No graduate-access or auditions offering.
    assert not any("graduate-access" in o.id or "auditions" in o.id for o in offs)


def test_build_offerings_one_per_week() -> None:
    offs = _build_offerings(_PAYLOAD, date(2026, 6, 8))
    open_offs = [o for o in offs if "open-program" in o.id]
    assert len(open_offs) == 2
    starts = sorted(o.schedule.start for o in open_offs if o.schedule.start)
    assert starts == [date(2026, 1, 3), date(2026, 1, 8)]


def test_build_offering_fields() -> None:
    offs = _build_offerings(_PAYLOAD, date(2026, 6, 8))
    boys = next(o for o in offs if "boys-program" in o.id)
    assert boys.organization.country == "AU"
    assert boys.location is not None
    assert boys.location.city == "Melbourne"
    assert boys.schedule.timezone == "Australia/Melbourne"
    assert boys.schedule.season == "2026"
    assert boys.age_range == {"min": 10, "max": 13}
    assert boys.application.deadline == date(2025, 12, 16)
    assert len(boys.application.requirements) == 1
    assert boys.application.requirements[0].type == "none"
    assert boys.schedule.sessions[0].gender == "male"
    assert "character" in boys.genres


def test_build_offering_kept_when_past() -> None:
    """Past cycles (Jan 2026) are kept — 'past' is derived, never filtered."""
    offs = _build_offerings(_PAYLOAD, date(2026, 6, 8))
    assert offs  # all are in the past relative to today, but still emitted
    assert all(o.schedule.end is not None and o.schedule.end < date(2026, 6, 8) for o in offs)
