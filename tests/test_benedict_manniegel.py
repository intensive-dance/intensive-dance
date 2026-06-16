"""Offline tests for the Benedict Manniegel Osterworkshop scraper.

Snippets mirror the structure of the Stundenplan (timetable) PDFs as extracted
by pypdf: a letter-spaced title line, a "DD.MM." day-header row, a LEVEL legend
with age bands, the class names, and the LEHRKRÄFTE legend.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers.benedict_manniegel import (
    _build_offerings,
    _select_schedule,
)

# Osterworkshop 2026 — all five levels incl. PreBallet, open-topped Level IV.
OSTER_2026 = """\
ZEIT
S 1 S 2 S 1 S 2 S 1 S 2
10:00-11:30 11:00-12:45
III LBM II
Klassisches Ballett
Spitze
Charaktertanz
Tanzgeschichte
OSTERWORKSHOP 2026 | STUNDENPLAN 7. - 11. APRIL 2026
DIENSTAG 07.04. MITTWOCH 08.04. DONNERSTAG 09.04. FREITAG 10.04. SAMSTAG 11.04.
RÄUME im 1. OG
LEVEL
Level I
Für 8-10 J. mit altersgemäßen Basis-Ballettkenntnissen
Level II
Für 10-12 J. mit altersgemäßen Ballettkenntnissen
Level III
Für 13-15 J. mit guten Ballettkenntnissen
Level IV
Ab 16 J.; für fortgeschrittene Tänzer:innen auf Ausbildungsniveau
PreBallet
Ballett-Schnupperkurs für 5-7 J.
LEHRKRÄFTE
CB Cosima Borrer
ChB Christine Becker
LBM Laurel Benedict-Manniegel
NHS Natalia Hoffmann-Sitnikova
VS Vladimir Stadnik
Stand: 24. März 2026 (004)
"""

INFO = "https://www.benedictmanniegel.de/academy/workshops-events/"


def test_oster_2026_happy_path():
    (off,) = _build_offerings(OSTER_2026, 2026, INFO)

    assert off.id == "benedict-manniegel/osterworkshop-2026"
    assert off.title == "Osterworkshop 2026"
    assert off.schedule.season == "2026"
    assert (off.schedule.start, off.schedule.end) == (
        date(2026, 4, 7),
        date(2026, 4, 11),
    )
    # PreBallet 5-7 sets the floor; Level IV "Ab 16 J." is open-topped → null max.
    assert off.age_range == {"min": 5}
    assert off.genres == ["classical", "pointe", "character"]
    assert set(off.level) == {"beginner", "intermediate", "advanced"}
    assert [t.name for t in off.teachers] == [
        "Cosima Borrer",
        "Christine Becker",
        "Laurel Benedict-Manniegel",
        "Natalia Hoffmann-Sitnikova",
        "Vladimir Stadnik",
    ]
    # Open-enrollment, no audition; the schedule states no fee.
    assert off.prices == []
    assert [r.type for r in off.application.requirements] == ["none"]
    assert off.application.deadline is None
    assert off.location is not None
    assert off.location.city == "Munich"


# A prior edition: different bands ("ab ca. N J." open top), no PreBallet, no
# character class — confirms the parse doesn't assume a fixed legend.
OSTER_2025 = """\
Klassisches Ballett
Spitze
OSTERWORKSHOP 2025 | STUNDENPLAN 8. - 12. APRIL 2025
DIENSTAG 08.04. MITTWOCH 09.04. DONNERSTAG 10.04. FREITAG 11.04. SAMSTAG 12.04.
LEVEL
Level I
für 9-11 J. mit einer Trainings-routine
Level II
für 12-14 J. mit einer Trainings-routine
Level III + IV
ab ca. 14 J. mit einer Trainings-routine
LEHRKRÄFTE
LBM Laurel Benedict-Manniegel
Stand: 20. März 2025 (003)
"""


def test_oster_2025_open_top_and_no_character():
    (off,) = _build_offerings(OSTER_2025, 2025, INFO)

    assert off.schedule.start == date(2025, 4, 8)
    assert off.schedule.end == date(2025, 4, 12)
    # "ab ca. 14 J." → open-topped; the 9-11 band is the floor.
    assert off.age_range == {"min": 9}
    assert "character" not in off.genres
    assert "classical" in off.genres and "pointe" in off.genres
    assert [t.name for t in off.teachers] == ["Laurel Benedict-Manniegel"]


def test_no_day_header_emits_nothing():
    assert _build_offerings("LEVEL\nLevel I\nFür 8-10 J.\n", 2026, INFO) == []


def test_select_schedule_picks_latest_year_and_revision():
    media = [
        {
            "title": {"rendered": "Stdplan_Osterworkshop_2025_003"},
            "source_url": "https://x/2025_003.pdf",
        },
        {
            "title": {"rendered": "Stdplan_Osterworkshop_2026_004"},
            "source_url": "https://x/2026_004.pdf",
        },
        {
            "title": {"rendered": "Stdplan_Osterworkshop_2026_001"},
            "source_url": "https://x/2026_001.pdf",
        },
        # noise: a summer schedule and a non-PDF must be ignored.
        {
            "title": {"rendered": "Stdplan_SummerWorkshop_2027_002"},
            "source_url": "https://x/summer.pdf",
        },
        {
            "title": {"rendered": "Stdplan_Osterworkshop_2099_009"},
            "source_url": "https://x/banner.png",
        },
    ]
    assert _select_schedule(media) == ("https://x/2026_004.pdf", 2026)


def test_select_schedule_none_when_no_match():
    assert (
        _select_schedule([{"title": {"rendered": "Gebuehren-2025"}, "source_url": "x.pdf"}]) is None
    )
