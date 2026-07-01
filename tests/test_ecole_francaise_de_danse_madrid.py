"""Unit tests for the École Française de Danse Madrid scraper.

Pin the Tribe Events REST API multi-edition parsing: track deduplication
(adult/student/masterclass by category slug), per-track age ranges,
session construction from start/end dates, the special Phavorin masterclass
as a standalone Offering, and the degraded-fixture raise. Inline event dicts
(no network).
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import ecole_francaise_de_danse_madrid as m


def _ev(title: str, start: str, end: str, cats: list[str]) -> dict:
    """Minimal Tribe Events record."""
    return {
        "title": title,
        "start_date": start,
        "end_date": end,
        "categories": [{"name": c} for c in cats],
        "url": f"https://ecolefrancaisededanse.com/evento/{title.lower().replace(' ', '-')}/",
    }


_EVENTS = [
    _ev(
        "INTENSIVOS DE VERANO",
        "2026-06-29 09:30:00",
        "2026-07-03 14:00:00",
        ["ECOLE", "INTENSIVOS", "INTENSIVOS ESTUDIANTES"],
    ),
    _ev(
        "INTENSIVOS DE VERANO",
        "2026-07-13 09:30:00",
        "2026-07-17 14:30:00",
        ["ECOLE", "INTENSIVOS", "INTENSIVOS ESTUDIANTES"],
    ),
    _ev(
        "INTENSIVOS DE VERANO PARA ADULTOS",
        "2026-06-29 00:00:00",
        "2026-07-03 23:59:59",
        ["ECOLE", "INTENSIVOS", "INTENSIVOS ADULTOS"],
    ),
    _ev(
        "INTENSIVOS DE VERANO PARA ADULTOS",
        "2026-07-06 00:00:00",
        "2026-07-10 23:59:59",
        ["ECOLE", "INTENSIVOS", "INTENSIVOS ADULTOS"],
    ),
    _ev(
        "INTENSIVOS DE VERANO PARA ADULTOS",
        "2026-07-13 00:00:00",
        "2026-07-17 23:59:59",
        ["ECOLE", "INTENSIVOS", "INTENSIVOS ADULTOS"],
    ),
    _ev(
        "Curso intensivo con Stéphane Phavorin",
        "2026-07-06 09:30:00",
        "2026-07-10 14:00:00",
        ["ECOLE", "INTENSIVOS", "INTENSIVOS ESTUDIANTES", "MASTERCLASS", "PROGRAMA ESPECIAL"],
    ),
]


def test_three_offerings():
    offs = m._build_offerings(_EVENTS)
    assert len(offs) == 3
    ids = {o.id for o in offs}
    assert "ecole-francaise-de-danse-madrid/adult-2026" in ids
    assert "ecole-francaise-de-danse-madrid/student-2026" in ids
    assert "ecole-francaise-de-danse-madrid/phavorin-masterclass-2026" in ids


def test_student_intensive():
    offs = {o.id: o for o in m._build_offerings(_EVENTS)}
    o = offs["ecole-francaise-de-danse-madrid/student-2026"]
    assert o.age_range == {"min": 8}
    assert o.level == ["intermediate", "advanced"]
    assert o.genres == ["classical", "repertoire", "contemporary"]
    assert o.schedule.start == date(2026, 6, 29)
    assert o.schedule.end == date(2026, 7, 17)
    assert len(o.schedule.sessions) == 2
    assert o.schedule.sessions[0].start == date(2026, 6, 29)
    assert o.schedule.sessions[1].start == date(2026, 7, 13)


def test_adult_intensive():
    offs = {o.id: o for o in m._build_offerings(_EVENTS)}
    o = offs["ecole-francaise-de-danse-madrid/adult-2026"]
    assert o.age_range == {"min": 18}
    assert o.level == ["open"]
    assert len(o.schedule.sessions) == 3
    assert o.schedule.start == date(2026, 6, 29)
    assert o.schedule.end == date(2026, 7, 17)


def test_phavorin_masterclass_is_standalone():
    offs = {o.id: o for o in m._build_offerings(_EVENTS)}
    o = offs["ecole-francaise-de-danse-madrid/phavorin-masterclass-2026"]
    # Phavorin has both ESTUDIANTES and PROGRAMA ESPECIAL cats → masterclass
    # takes priority over student.
    assert "Phavorin" in o.title
    assert len(o.schedule.sessions) == 1
    assert o.schedule.sessions[0].start == date(2026, 7, 6)


def test_phavorin_not_in_student_sessions():
    """The Phavorin week must not appear as a session of the student track."""
    offs = {o.id: o for o in m._build_offerings(_EVENTS)}
    student = offs["ecole-francaise-de-danse-madrid/student-2026"]
    student_starts = {s.start for s in student.schedule.sessions}
    assert date(2026, 7, 6) not in student_starts


def test_empty_events_returns_no_offerings():
    assert m._build_offerings([]) == []
