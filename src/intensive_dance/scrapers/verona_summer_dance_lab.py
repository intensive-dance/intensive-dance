"""Verona Summer Dance Lab — Verona IT.

API FIRST: a Wix site (no `/wp-json/`, no `ld+json` events). Wix is
server-rendered, so the single event page carries everything in the static HTML
(the plain proxy tier returns it) — a `selectolax` text scrape. We strip Wix's
zero-width spaces first (they split tokens).

LANGUAGE: the page is bilingual and the proxy serves **Italian by default** (the
English mirror lives on the `en.` subdomain; `Accept-Language: en` does *not*
pin English on `www`). To stay deterministic whichever the proxy returns, we
parse **language-agnostically** — EN+IT month map and both date orders, enum
genre/level keywords in both languages, numeric ages, language-invariant teacher
names (cf. `fondazione_monreart`). The `<title>` is stale ("…2024"); the live
edition is read from the body.

DISCOVERY: one dated edition on the home page → one Offering, year-stamped from
the body dates (next year's edition is picked up automatically). Kept per IDR-24.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-17):
  - DATES both orders: "August 3-8, 2026" / "3-8 Agosto, 2026".
  - GENRES off the courses list — Ballet/Classico → classical, Contemporary/
    Contemporaneo → contemporary, Repertoire/Repertorio → repertoire (the
    Choreographic Lab / Laboratorio Coreografico has no enum genre).
  - LEVELS: "Advanced and Intermediate" / "Avanzato e Intermedio".
  - AGES: "from 14 to 30 years" / "dai 14 ai 30 anni" → 14–30.
  - TEACHERS: the Faculty / Docenti Ospiti list — names only (their discipline
    labels split across lines, so roles aren't captured reliably).
  - DEADLINE: "no later than July 5th" / "non oltre il 5 Luglio".
  - PRICES: the tuition figure is a Wix widget absent from the static HTML
    (render=1 doesn't surface it either) — left empty (not stated), not invented.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.veronadancelab.com"
PROVIDER = "verona-summer-dance-lab"

ORG = Organization(name="Verona Summer Dance Lab", slug=PROVIDER, country="IT", city="Verona")

_MONTHS_IT = {
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12,
}
_MONTHS = {**parse.MONTHS, **_MONTHS_IT}
_MONTHALT = parse.months_alt(_MONTHS)

# "August 3-8, 2026" (month first) and "3-8 Agosto, 2026" (day span first).
_DATES_MONTH_FIRST = re.compile(
    r"(" + _MONTHALT + r")\s+(\d{1,2})\s*[-–]\s*(\d{1,2}),?\s*(\d{4})", re.IGNORECASE
)
_DATES_DAY_FIRST = re.compile(
    r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(" + _MONTHALT + r"),?\s*(\d{4})", re.IGNORECASE
)
_AGES = re.compile(
    r"(?:from|dai)\s+(\d{1,2})\s+(?:to|ai)\s+(\d{1,2})\s+(?:years|anni)", re.IGNORECASE
)
_DEADLINE_EN = re.compile(r"no later than\s+(" + _MONTHALT + r")\s+(\d{1,2})", re.IGNORECASE)
_DEADLINE_IT = re.compile(r"non oltre il\s+(\d{1,2})\s+(" + _MONTHALT + r")", re.IGNORECASE)
_NAME = re.compile(r"^[A-ZÀ-Þ][a-zà-ÿ]+\s+[A-ZÀ-Þ][a-zà-ÿ]+$")

_FACULTY_HEADINGS = {"Faculty", "Docenti Ospiti", "Docenti"}
_FACULTY_END = ("days,", "giorni,")

_GENRES: list[tuple[Genre, list[str]]] = [
    ("classical", ["ballet", "balletto", "classico", "classical"]),
    ("contemporary", ["contempor"]),  # contemporary / contemporaneo (+ source typo)
    ("repertoire", ["repertoire", "repertorio"]),
]
_LEVELS: list[tuple[Level, list[str]]] = [
    ("intermediate", ["intermediate", "intermedio"]),
    ("advanced", ["advanced", "avanzato"]),
]


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(BASE)
    resp.raise_for_status()
    return _build_offerings(resp.text, date.today())


def _lines(html: str) -> list[str]:
    tree = HTMLParser(html.replace("​", "").replace("﻿", ""))
    for node in tree.css("script, style, noscript"):
        node.decompose()
    body = tree.body
    if body is None:
        return []
    out = (parse.clean(line) for line in body.text(separator="\n").split("\n"))
    return [line for line in out if line]


def _dates(text: str) -> tuple[date, date] | None:
    if m := _DATES_MONTH_FIRST.search(text):
        month, d1, d2, year = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
    elif m := _DATES_DAY_FIRST.search(text):
        d1, d2, month, year = int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4))
    else:
        return None
    mo = _MONTHS[month.lower()]
    return date(year, mo, d1), date(year, mo, d2)


def _ages(text: str) -> dict | None:
    m = _AGES.search(text)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _deadline(text: str, year: int) -> date | None:
    if m := _DEADLINE_EN.search(text):
        return date(year, _MONTHS[m.group(1).lower()], int(m.group(2)))
    if m := _DEADLINE_IT.search(text):
        return date(year, _MONTHS[m.group(2).lower()], int(m.group(1)))
    return None


def _levels(text: str) -> list[Level]:
    low = text.lower()
    return [lvl for lvl, keys in _LEVELS if any(k in low for k in keys)]


def _teachers(lines: list[str]) -> list[Teacher]:
    """Names (2-word Title-case lines) in the Faculty / Docenti section."""
    try:
        start = next(i for i, line in enumerate(lines) if line in _FACULTY_HEADINGS)
        end = next(
            i
            for i, line in enumerate(lines)
            if i > start and any(cue in line.lower() for cue in _FACULTY_END)
        )
    except StopIteration:
        return []
    seen: set[str] = set()
    teachers: list[Teacher] = []
    for line in lines[start + 1 : end]:
        if _NAME.match(line) and line not in seen:
            seen.add(line)
            teachers.append(Teacher(name=line))
    return teachers


def _location(text: str) -> Location:
    venue = "Educandato Statale agli Angeli" if "agli angeli" in text.lower() else None
    return Location(venue=venue, city="Verona", country="IT")


def _build_offerings(html: str, today: date) -> list[Offering]:
    lines = _lines(html)
    text = "\n".join(lines)
    span = _dates(text)
    if span is None:
        return []
    start, end = span
    return [
        Offering(
            id=f"{PROVIDER}/{start.year}",
            source=Source(provider=PROVIDER, url=BASE, scrapedAt=now_utc()),
            title=f"Verona Summer Dance Lab {start.year}",
            genres=parse.match_genres(text, _GENRES),
            level=_levels(text),
            ageRange=_ages(text),
            organization=ORG,
            location=_location(text),
            schedule=Schedule(season="summer", start=start, end=end, timezone="Europe/Rome"),
            teachers=_teachers(lines),
            application=Application(
                status="open",
                deadline=_deadline(text, start.year),
                url=BASE,
                notes="Open enrolment — no selection process; for dancers who regularly "
                "study dance (no beginners). Groups A/B (Advanced/Intermediate) assigned "
                "after registration; spots limited. Registrations close at capacity, or by "
                "the stated deadline. Scholarships may be awarded; a certificate of "
                "participation is issued.",
            ),
        )
    ]
