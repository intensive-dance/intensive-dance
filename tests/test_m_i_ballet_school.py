"""Unit tests for the Munich International Ballet School scraper.

These pin the parsing of the single `.net` Summer Intensive page: the four
German guest-director week ranges (year carried only by the registration
checkboxes), the three-tier EUR fee table, the named teachers with their
(de-prefixed) affiliations, and the explicit open-to-all prerequisite that maps
to `[NoneReq]` rather than an unknown `[]`. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import NoneReq
from intensive_dance.scrapers import m_i_ballet_school as mi

# Shaped like the rendered body text: prose week ranges (no year) plus the
# registration checkboxes that carry the year, the fee table, and prerequisites.
_PAGE = (
    "Ballet Summer Intensive - Preperation for the Company Entrance - Limited places "
    "27. Juli – 1. August: Jiri Pokorny (Direktor des J.K. TyL Theatre Pilsen) "
    "3. August – 8. August: Filip Barankiewicz (Direktor des Národní Divadlo Prag) "
    "10. August – 15. August: Vitaliy Petrov (Direktor des Thüringer Staatsballett) "
    "17. August – 22. August: Linnar Looris (Direktor des Estonian National Ballet) "
    "Fees 1 day 123€ 6 days in a row 680€ 12 days in a row 1.290€ "
    "Prerequisites There are no restrictions on participation, everyone can take part "
    "regardless of their dance experience. "
    "Days week: Jiri Pokorny 27.7.2026 28.7.2026 01.8.2026 "
    "Days week: Linnar Looris 17.08.2026 22.08.2026"
)


def test_year_from_registration_checkboxes():
    assert mi._year(_PAGE) == 2026


def test_year_absent():
    assert mi._year("27. Juli – 1. August: someone") is None


def test_sessions_four_weeks_with_year_from_checkboxes():
    sessions = mi._sessions(_PAGE, mi._year(_PAGE))
    assert [(s.start, s.end) for s in sessions] == [
        (date(2026, 7, 27), date(2026, 8, 1)),
        (date(2026, 8, 3), date(2026, 8, 8)),
        (date(2026, 8, 10), date(2026, 8, 15)),
        (date(2026, 8, 17), date(2026, 8, 22)),
    ]
    assert sessions[0].label == "Jiri Pokorny (Direktor des J.K. TyL Theatre Pilsen)"


def test_sessions_without_year_keep_labels_but_no_dates():
    sessions = mi._sessions(_PAGE, None)
    assert len(sessions) == 4
    assert all(s.start is None and s.end is None for s in sessions)
    assert sessions[1].label == "Filip Barankiewicz (Direktor des Národní Divadlo Prag)"


def test_sessions_absent():
    assert mi._sessions("no dated weeks here", 2026) == []


def test_prices_three_tiers():
    prices = mi._prices(_PAGE)
    assert [(p.amount, p.currency, p.label, p.includes) for p in prices] == [
        (123.0, "EUR", "1 day", ["tuition"]),
        (680.0, "EUR", "6 days in a row", ["tuition"]),
        (1290.0, "EUR", "12 days in a row", ["tuition"]),
    ]


def test_teachers_named_with_stripped_affiliation():
    teachers = mi._teachers(_PAGE)
    assert [t.name for t in teachers] == [
        "Jiri Pokorny",
        "Filip Barankiewicz",
        "Vitaliy Petrov",
        "Linnar Looris",
    ]
    first = teachers[0]
    assert first.role == "Guest director (weekly)"
    assert first.affiliations[0].organization == "J.K. TyL Theatre Pilsen"
    assert first.affiliations[0].current is True


def test_genres_from_title_and_directors():
    assert mi._genres(_PAGE) == ["classical"]


def test_requirements_open_to_all_is_explicit_none():
    reqs = mi._requirements(_PAGE)
    assert len(reqs) == 1
    assert isinstance(reqs[0], NoneReq)


def test_requirements_unknown_when_no_prereq_statement():
    assert mi._requirements("Fees 1 day 123€") == []


def test_prereq_note_kept_verbatim():
    note = mi._prereq_note(_PAGE)
    assert note == (
        "There are no restrictions on participation, everyone can take part "
        "regardless of their dance experience."
    )


def test_build_offering_end_to_end():
    offering = mi._build_offering(f"<html><body>{_PAGE}</body></html>")
    assert offering is not None
    assert offering.id == "m-i-ballet-school/summer-intensive-2026"
    assert offering.title == "Ballet Summer Intensive 2026"
    assert offering.schedule.start == date(2026, 7, 27)
    assert offering.schedule.end == date(2026, 8, 22)
    assert len(offering.schedule.sessions) == 4
    assert len(offering.prices) == 3
    assert len(offering.teachers) == 4
    assert offering.location is not None
    assert offering.location.venue == "Marsstraße 40"
    assert offering.age_range is None
