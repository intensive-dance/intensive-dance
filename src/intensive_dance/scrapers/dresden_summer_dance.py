"""Dresden Summer Dance — Dance-Workshop e.V. (DE), Dresden.

API FIRST
The site (https://www.dance-workshop.de) is built on the **checkdomain/Duda
site builder** (`dmRoot`/`dmRespRow`/`u_<id>` classes), not WordPress: `/wp-json/`
403s and there is no schema.org `Event`/`Course` `ld+json`. But every page is
server-rendered, so a plain fetch returns the full program text in the static
HTML — no JS render or proxy tier needed. We read it structurally: each course is
a builder "service-list" item (`div.listText` → `span.itemName` + `div.itemText`).

DISCOVERY — the dated edition's structured detail (ages, tuition, schedule) lives
on the SUMMER 2026 "Levels Descriptions, Tuitions & Schedules" subpage
(`/newpageb561dade`); the home page (`/dresden-summer-dance`) carries only the
edition YEAR ("SUMMER 2026" / "August 3-15, 2026"), which the levels schedule
lines omit — so we fetch both, reading the year off the home page.

The levels page lists nine service items; we emit three Offerings:
  - VOCATIONAL / PROFESSIONAL — Aug 3–15, €780. Three tracks (Junior / Intermediate
    / Senior) differ ONLY by age + required experience, sharing dates, fee, genres
    and daily schedule, so per the Rosenthal precedent this is ONE Offering with
    one age-`Session` per track (the per-track eligibility prose, incl. the two
    differing age phrasings the source gives, is preserved verbatim in each
    `Session.notes`).
  - CHILDREN & YOUTH DANCE — Aug 10–15, €340, ages 8–17 (ballet + creative dance).
  - DANCE COURSES FOR ADULTS — Aug 10–13, €90, ages 16+ (ballet or contemporary).
Dropped as out of scope: the "Pedagogic tutorial" (a dance-TEACHERS workshop, not
a student intensive), "Classes observation" (observation for teachers/pros, not
instruction), and the drop-in "Day Ticket"s (not a dated edition).

Faculty: the site has a separate workshop-wide faculty page, but it neither maps
teachers to the individual tracks nor renders names in a stable selector (glued
tokens, "comming soon" placeholders), so attributing it per-Offering would invent
a mapping — teachers are left empty rather than over-claimed.

GENRES are matched against each course's own curriculum text — vocational lists
"ballet, contemporary, variations, etude and repertoire" + a "Variation/pointe
work" class → classical, contemporary, repertoire, pointe; children teach ballet
(creative dance is not a ballet genre) → classical; adults "Ballet or Contemporary"
→ classical, contemporary.

PRICES: each course states a non-refundable €30 membership fee (→ registration)
and a per-course tuition (→ tuition), both in EUR.

REQUIREMENTS: open enrolment ("book now"); no audition material is stated (the
vocational "no less than N years of dance classes" is an experience prerequisite,
not application material) → requirements left empty (not stated).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-26)
- Duda/checkdomain SSR HTML read structurally by builder service-list items.
- Two-page fetch: edition year off the home page, per-track detail off the levels page.
- Fold-by-age: one Offering, three age `Session`s, with an open-topped overall band.
- Same-month English day ranges in two orderings ("august 3rd - 15th" / "10 - 13: August").
- Two Price categories (registration membership + tuition); raise-on-degraded guard.
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
    Price,
    Schedule,
    Session,
    Source,
    now_utc,
)

HOME = "https://www.dance-workshop.de/dresden-summer-dance"
LEVELS = "https://www.dance-workshop.de/newpageb561dade"
REGISTRATION = "https://www.dance-workshop.de/kopie-contact"

ORG = Organization(
    name="Dance-Workshop e.V.", slug="dresden-summer-dance", country="DE", city="Dresden"
)
LOCATION = Location(venue="Pegasus Theaterschule", city="Dresden", country="DE")
TIMEZONE = "Europe/Berlin"

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet",)),
    ("contemporary", ("contemporary",)),
    ("repertoire", ("repertoire", "repertory")),
    ("pointe", ("pointe",)),
]

# The three vocational tracks (folded into one Offering, one Session each) and the
# two standalone short courses. Keyed by a substring of the item's `itemName`.
_VOCATIONAL = ("junior", "intermediate", "senior")
_VOCATIONAL_LEVEL: list[Level] = ["pre-professional", "professional"]


def scrape(client: httpx.Client) -> list[Offering]:
    home = client.get(HOME)
    home.raise_for_status()
    levels = client.get(LEVELS)
    levels.raise_for_status()
    return _build_offerings(home.text, levels.text)


def _build_offerings(home_html: str, levels_html: str) -> list[Offering]:
    year = _edition_year(home_html)
    if year is None:
        # Home page rendered without the edition marker — treat as a degraded
        # fetch and raise so run.py keeps the prior store (never emit []).
        raise ValueError("Dresden Summer Dance: edition year not found on home page")

    items = _items(levels_html)
    offerings: list[Offering] = []

    vocational = [(name, text) for name, text in items if _match(name, _VOCATIONAL)]
    if vocational:
        offerings.append(_vocational_offering(vocational, year))

    for name, text in items:
        if _match(name, ("children",)):
            offerings.append(
                _single_offering("children-youth", "Children & Youth Dance", ["open"], text, year)
            )
        elif _match(name, ("adults",)):
            offerings.append(_single_offering("adults", "Adults", ["open"], text, year))

    if not offerings:
        raise ValueError("Dresden Summer Dance: no course items parsed from levels page")
    return offerings


def _match(name: str, keys: tuple[str, ...]) -> bool:
    low = name.lower()
    return any(k in low for k in keys)


def _items(levels_html: str) -> list[tuple[str, str]]:
    """(itemName, full item text) for each service-list course block."""
    tree = HTMLParser(levels_html)
    out: list[tuple[str, str]] = []
    for node in tree.css("div.listText"):
        name_node = node.css_first("span.itemName")
        if not name_node:
            continue
        name = parse.clean(name_node.text())
        if name:
            out.append((name, parse.clean(node.text(separator=" "))))
    return out


def _vocational_offering(blocks: list[tuple[str, str]], year: int) -> Offering:
    sessions: list[Session] = []
    genre_text = ""
    rep_text = blocks[0][1]  # tracks share dates/fee/schedule; read them off the first
    for name, text in blocks:
        genre_text += " " + text
        sessions.append(Session(label=name, ageRange=_age_range(text), gender="both", notes=text))

    start, end, notes = _schedule(rep_text, year)
    return Offering(
        id=f"dresden-summer-dance/vocational-{year}",
        source=Source(provider="dresden-summer-dance", url=HOME, scrapedAt=now_utc()),
        title=f"Dresden Summer Dance {year} — Vocational / Professional",
        genres=parse.match_genres(genre_text, _GENRE_KEYWORDS, default=["classical"]),
        level=_VOCATIONAL_LEVEL,
        ageRange=_overall_age(sessions),
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(
            season=str(year),
            start=start,
            end=end,
            timezone=TIMEZONE,
            sessions=sessions,
            notes=notes,
        ),
        prices=_prices(rep_text),
        application=Application(url=REGISTRATION),
    )


def _single_offering(slug: str, title: str, level: list[Level], text: str, year: int) -> Offering:
    start, end, notes = _schedule(text, year)
    return Offering(
        id=f"dresden-summer-dance/{slug}-{year}",
        source=Source(provider="dresden-summer-dance", url=HOME, scrapedAt=now_utc()),
        title=f"Dresden Summer Dance {year} — {title}",
        genres=parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"]),
        level=level,
        ageRange=_age_range(text),
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(season=str(year), start=start, end=end, timezone=TIMEZONE, notes=notes),
        prices=_prices(text),
        application=Application(url=REGISTRATION),
    )


# Home page states the year as "August 3-15, 2026" (h2) and "SUMMER 2026" (title).
_YEAR = re.compile(r"(?:August[^.]*?|SUMMER\s+)(20\d{2})", re.IGNORECASE)


def _edition_year(home_html: str) -> int | None:
    tree = HTMLParser(home_html)
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""
    m = _YEAR.search(text)
    return int(m.group(1)) if m else None


# Age stated as "from the ages of 13-16 years old", "... 15+ years old", or
# (adults) "from about 16+ years of age". The "ages of"/"about" phrasing is the
# uniform participant-age signal across all courses.
_AGE_RANGE = re.compile(r"ages of\s*(\d{1,2})\s*[-–]\s*(\d{1,2})", re.IGNORECASE)
_AGE_OPEN = re.compile(r"(?:ages of|about)\s*(\d{1,2})\s*\+", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    m = _AGE_RANGE.search(text)
    if m:
        return {"min": int(m.group(1)), "max": int(m.group(2))}
    m = _AGE_OPEN.search(text)
    if m:
        return {"min": int(m.group(1)), "max": None}
    return None


def _overall_age(sessions: list[Session]) -> dict | None:
    """Span the sessions' bands; an open-topped session keeps the whole open-topped."""
    bands = [s.age_range for s in sessions if s.age_range]
    mins = [b["min"] for b in bands if b.get("min") is not None]
    if not mins:
        return None
    maxes = [b.get("max") for b in bands]
    top = None if any(m is None for m in maxes) else max(m for m in maxes if m is not None)
    return {"min": min(mins), "max": top}


# "Schedule - august 3rd - 15th:" (month first) or "Schedule - 10 - 13: August"
# (days first) — both same-month day ranges, bounded before the bulleted timetable.
_SCHED = re.compile(r"Schedule\s*[-–]?\s*(.*?)(?:•|book now|$)", re.IGNORECASE)
_DAYS = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s*[-–]\s*(\d{1,2})(?:st|nd|rd|th)?")


def _schedule(text: str, year: int) -> tuple[date | None, date | None, str | None]:
    m = _SCHED.search(text)
    if not m:
        return None, None, None
    snippet = parse.clean(m.group(1))
    month = re.search(parse.MONTHALT, snippet, re.IGNORECASE)
    days = _DAYS.search(snippet)
    if not month or not days:
        return None, None, snippet or None
    mon = parse.MONTHS[month.group(0).lower()]
    start = date(year, mon, int(days.group(1)))
    end = date(year, mon, int(days.group(2)))
    return start, end, snippet


_TUITION = re.compile(r"Tuition:\s*([\d.,]+)\s*Euros?", re.IGNORECASE)
_MEMBER = re.compile(r"Membership fee:\s*([\d.,]+)\s*Euros?\s*([^•]*?)(?:Tuition|$)", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    mem = _MEMBER.search(text)
    if mem:
        amount = parse.parse_amount(mem.group(1))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="Membership fee",
                    notes=parse.clean(mem.group(2)) or None,
                )
            )
    tui = _TUITION.search(text)
    if tui:
        amount = parse.parse_amount(tui.group(1))
        if amount is not None:
            prices.append(
                Price(amount=amount, currency="EUR", label="Tuition", includes=["tuition"])
            )
    return prices
