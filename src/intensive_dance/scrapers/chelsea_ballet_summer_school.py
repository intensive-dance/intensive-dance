"""Chelsea Ballet — Summer School (London, GB).

API FIRST: chelsea-ballet.com is **custom** (no `/wp-json/`, no `ld+json`). The
Summer School page is server-rendered. Everything we need is in the page's
prose: the date ("Monday 10 - Saturday 15 August 2026"), venue ("ArtsEd,
Chiswick"), age ("over the age of 18"), and curriculum ("ballet, pointe,
repertoire, PBT and more"). Plain `selectolax` text scrape, no HTML position
guessing.

DISCOVERY: one dated edition per year → a single `Offering`.

WHAT WE EXTRACT (verified live 2026-07-01):
  - DATES: "Monday 10 - Saturday 15 August 2026" — month stated once at the end,
    applied to both bounds.
  - AGES: "anyone over the age of 18" → min 18, no upper bound (adult-only).
  - LEVEL: "elementary and above standard of ballet" → beginner excluded, so
    intermediate and up.
  - GENRES: "ballet, pointe, repertoire, PBT" → classical + pointe + repertoire.
    (PBT = Progressing Ballet Technique, a conditioning method, not a genre.)
  - PRICES: none on the page (fees behind a booking form).
  - LOCATION: ArtsEd, Chiswick, London.
  - APPLICATION: no audition stated; not for beginners. Requirements left unknown.
  - TEACHERS: Nina Thilas-Mohs, Richard Ramsey, Bethany Ramsey, Naomi Smart —
    kept as `Teacher` names only (no further affiliations on-page).

WHAT THIS SCRAPER EXERCISES: custom (non-WP) server-rendered HTML; prose-anchored
single-date extraction; English day-prefixed span with trailing month; open-topped
adult age; no-price faithful scrape; teacher roster; raise-on-degraded fetch.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
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

BASE = "https://chelsea-ballet.com"
PAGE = f"{BASE}/summerschool/"

ORG = Organization(
    name="Chelsea Ballet", slug="chelsea-ballet-summer-school", country="GB", city="London"
)
VENUE = "ArtsEd, Chiswick"

# "Monday 10 - Saturday 15 August 2026". Month once at the end.
_DATE = re.compile(
    r"\w+\s+(\d{1,2})\s*[-–]\s*\w+\s+(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
_AGE = re.compile(r"over the age of (\d{1,2})", re.IGNORECASE)

_TEACHERS = [
    "Nina Thilas-Mohs",
    "Richard Ramsey",
    "Bethany Ramsey",
    "Naomi Smart",
]
_GENRES: list[Genre] = ["classical", "pointe", "repertoire"]

LEVELS: list[Level] = ["intermediate", "open"]


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return [_build_offering(resp.text)]


def _build_offering(html: str) -> Offering:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ") if tree.body else "")

    m = _DATE.search(text)
    if not m:
        raise ValueError("Chelsea Ballet: no date found (degraded fetch?)")
    year = int(m.group(4))
    start = date(year, parse.MONTHS[m.group(3).lower()], int(m.group(1)))
    end = date(year, parse.MONTHS[m.group(3).lower()], int(m.group(2)))
    season = str(year)

    age = _AGE.search(text)
    ageRange = {"min": int(age.group(1))} if age else None

    return Offering(
        id=f"{ORG.slug}/{season}",
        source=Source(provider=ORG.slug, url=PAGE, scrapedAt=now_utc()),
        title=f"Summer School {season}",
        genres=_GENRES,
        level=LEVELS,
        ageRange=ageRange,
        organization=ORG,
        location=Location(venue=VENUE, city="London", country="GB"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/London",
            notes="Design-your-own programme: day or full week. Not for beginners.",
        ),
        teachers=[Teacher(name=name) for name in _TEACHERS],
    )
