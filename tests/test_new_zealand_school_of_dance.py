"""Tests for the New Zealand School of Dance scraper.

All offline — inline HTML snippets modelled on the live Webflow course pages
captured on 2026-06-08 (the labelled "Dates:" / "Where:" / "Cost:" body lines and
the ``og:title`` heading). No network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers.new_zealand_school_of_dance import (
    _age_range,
    _build_offerings,
    _dates,
    _genres,
    _prices,
    _venue,
)


def _page(og_title: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html><head>"
        f'<meta property="og:title" content="{og_title}"/>'
        "</head><body>"
        "<nav>Study Full-Time How to Apply</nav>"
        f"<main>{body}</main>"
        "</body></html>"
    )


# CIP: a dated two-day contemporary intensive with ages + two fee tiers. The
# "Where:" value carries its own internal colon (Te Whaea: …), and a zero-width
# joiner (‍) separates the labelled lines, as on the live page.
_CIP_BODY = (
    "Contemporary Intensive Programme (CIP) Register now No items found. "
    "The New Zealand School of Dance (NZSD) Contemporary Intensive Programme is "
    "designed for dancers aged 15-18 who already have a foundation in contemporary "
    "dance and are curious about taking their training further. "
    "Registrations are now open ‍ "
    "Dates: 27 - 28 June 2026 "
    "Where: Te Whaea: National Dance and Drama Centre ‍ "
    "Cost: $200.00 + $25.00 registration fee. "
    "Over two full days, you’ll work closely with NZSD faculty."
)

# Winter School: a five-day classical + contemporary holiday course. Dates carry
# weekday prefixes ("Sunday 5 - Thursday 9 July 2026"); no numeric age (a syllabus
# level instead) and no on-page Cost line (the fee sits behind the form).
_WINTER_BODY = (
    "Winter School Register now No items found. "
    "The NZSD Winter School is a five-day course, offering intensive tuition in "
    "classical ballet and contemporary dance, is held in the first week of the "
    "winter school holidays. Registrations are now open "
    "Dates: Sunday 5 - Thursday 9 July 2026 "
    "Where: Te Whaea: National Dance and Drama Centre "
    "This five-day course offers intensive tuition. Winter School is suitable for "
    "students working at the equivalent of RAD Grade 5 up to Solo Seal."
)

# Summer Intensive: the course page is currently undated ("No items found") and
# only points to a future edition via "contact us" — it must yield no Offering.
_SUMMER_BODY = (
    "Summer Intensive No items found. "
    "This programme gives dancers a taste of what is taught at the School. "
    "Classes specialised in preferred dance form, where dancers will choose to "
    "join either the contemporary dance or classical ballet classes. "
    "COST: $360 course fee + $50 registration fee "
    "For questions or information about our 2027 Summer Intensive programme "
    "please contact us."
)

_PAGES = {
    "courses/contemporary-intensive-programme": _page(
        "Contemporary Intensive Programme (CIP)", _CIP_BODY
    ),
    "courses/winter-school": _page("Winter School", _WINTER_BODY),
}


# ---------------------------------------------------------------------------
# _dates
# ---------------------------------------------------------------------------


def test_dates_shared_month_range() -> None:
    assert _dates("Dates: 27 - 28 June 2026") == (date(2026, 6, 27), date(2026, 6, 28))


def test_dates_weekday_prefixed_range() -> None:
    # "Sunday 5 - Thursday 9 July 2026" — weekday words on both sides are ignored.
    assert _dates("Dates: Sunday 5 - Thursday 9 July 2026") == (
        date(2026, 7, 5),
        date(2026, 7, 9),
    )


def test_dates_none_when_undated() -> None:
    assert _dates(_SUMMER_BODY) == (None, None)


# ---------------------------------------------------------------------------
# _age_range / _venue / _genres / _prices
# ---------------------------------------------------------------------------


def test_age_range_from_aged_cue() -> None:
    assert _age_range(_CIP_BODY) == {"min": 15, "max": 18}


def test_age_range_none_when_only_syllabus_level() -> None:
    # Winter School states "RAD Grade 5 to Solo Seal", not a numeric age.
    assert _age_range(_WINTER_BODY) is None


def test_venue_keeps_internal_colon() -> None:
    assert _venue(_CIP_BODY) == "Te Whaea: National Dance and Drama Centre"
    assert _venue(_WINTER_BODY) == "Te Whaea: National Dance and Drama Centre"


def test_genres_contemporary_only() -> None:
    assert _genres(_CIP_BODY) == ["contemporary"]


def test_genres_classical_and_contemporary() -> None:
    assert _genres(_WINTER_BODY) == ["classical", "contemporary"]


def test_prices_course_and_registration() -> None:
    prices = _prices(_CIP_BODY)
    by_label = {p.label: p for p in prices}
    assert by_label["Course fee"].amount == 200.0
    assert by_label["Course fee"].currency == "NZD"
    assert by_label["Course fee"].includes == ["tuition"]
    assert by_label["Registration fee"].amount == 25.0
    assert by_label["Registration fee"].includes == []  # a fee, not tuition


def test_prices_empty_when_no_cost_line() -> None:
    # Winter School publishes no on-page fee — don't grab a stray "$".
    assert _prices(_WINTER_BODY) == []


# ---------------------------------------------------------------------------
# _build_offerings (integration)
# ---------------------------------------------------------------------------


def test_build_offerings_one_per_dated_page() -> None:
    offs = _build_offerings(_PAGES, date(2026, 6, 8))
    assert len(offs) == 2
    ids = {o.id for o in offs}
    assert ids == {
        "new-zealand-school-of-dance/contemporary-intensive-programme-2026",
        "new-zealand-school-of-dance/winter-school-2026",
    }


def test_build_offerings_skips_undated_page() -> None:
    pages = dict(_PAGES)
    pages["courses/summer-intensive"] = _page("Summer Intensive", _SUMMER_BODY)
    offs = _build_offerings(pages, date(2026, 6, 8))
    # The undated Summer Intensive page adds no Offering.
    assert len(offs) == 2
    assert not any("summer" in o.id for o in offs)


def test_cip_offering_fields() -> None:
    offs = _build_offerings(_PAGES, date(2026, 6, 8))
    cip = next(o for o in offs if "contemporary-intensive" in o.id)
    assert cip.title == "Contemporary Intensive Programme (CIP) 2026"
    assert cip.organization.country == "NZ"
    assert cip.location is not None
    assert cip.location.city == "Wellington"
    assert cip.location.venue == "Te Whaea: National Dance and Drama Centre"
    assert cip.schedule.timezone == "Pacific/Auckland"
    assert cip.schedule.season == "2026"
    assert cip.schedule.start == date(2026, 6, 27)
    assert cip.age_range == {"min": 15, "max": 18}
    assert cip.genres == ["contemporary"]
    assert cip.level == ["open"]
    assert len(cip.application.requirements) == 1
    assert cip.application.requirements[0].type == "none"
    assert cip.teachers == []
    assert cip.schedule.sessions[0].age_range == {"min": 15, "max": 18}


def test_winter_offering_unset_fields() -> None:
    offs = _build_offerings(_PAGES, date(2026, 6, 8))
    winter = next(o for o in offs if "winter-school" in o.id)
    assert winter.age_range is None
    assert winter.prices == []
    assert winter.genres == ["classical", "contemporary"]


def test_build_offering_kept_when_past() -> None:
    """Past cycles (June/July 2026) are kept — 'past' is derived, never filtered."""
    offs = _build_offerings(_PAGES, date(2026, 12, 1))
    assert offs
    assert all(o.schedule.end is not None and o.schedule.end < date(2026, 12, 1) for o in offs)
