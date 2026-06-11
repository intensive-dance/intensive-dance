"""Dance & Fashion CIC — "TT Stage" Summer Ballet Intensive in Rapallo, Italy.

API FIRST: none usable. The site is **Wix** (`generator: Wix.com`, no `/wp-json/`);
its only structured `ld+json` is a generic `Service` blob (no dated `Event`). Wix
is server-side rendered, so the prose is in the static HTML — but the summer page
is a long Italian press round-up (years of "KEEP READING" article excerpts) around
one current-edition paragraph, so we parse **only** that paragraph's dates and the
program summary, not the stale clippings.

DISCOVERY: one `Offering` — the dated "TTSTAGE Summer Course & Ballet Gala" edition
("da 20 luglio 01 agosto 2026"). The page's prior-year press excerpts (a "15-27
luglio" line, "Summer Intensive 2024", etc.) are NOT separate editions and must not
be parsed as dates.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-11):
  - DATES: an Italian, separator-less day-month-day-month-year span ("20 luglio 01
    agosto 2026") via a local Italian month map.
  - GENRES: matched against the page's `meta description` program summary (Italian):
    classica→classical, punte→pointe, repertorio→repertoire, carattere→character.
    "moderno"/pas de deux have no genre-enum value and don't leak.
  - AGES: "di età dagli 11 anni in su" → open-topped {min: 11}.
  - LEVEL: "ballerini professionisti e adulti amatoriali" → professional + open.
  - PRICES / REQUIREMENTS: a plain registration form, no fee or audition stated →
    left empty (fail open); no invented price or requirement.
"""

from __future__ import annotations

import html as ihtml
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
    now_utc,
)

SLUG = "dance-and-fashion-cic"
PAGE = "https://www.danceandfashioncic.com/summer-ballet-intensive-ttstage-italy"

ORG = Organization(name="Dance & Fashion CIC", slug=SLUG, country="IT", city="Rapallo")
LOCATION = Location(city="Rapallo", country="IT")

# Wix peppers the markup with zero-width / soft-hyphen characters that split words.
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿­"), None)

_ITALIAN_MONTHS: dict[str, int] = {
    m: i
    for i, m in enumerate(
        [
            "gennaio",
            "febbraio",
            "marzo",
            "aprile",
            "maggio",
            "giugno",
            "luglio",
            "agosto",
            "settembre",
            "ottobre",
            "novembre",
            "dicembre",
        ],
        start=1,
    )
}
_MONTH_IT = parse.months_alt(_ITALIAN_MONTHS)

# "20 luglio 01 agosto 2026" — day month day month year, no separators.
_SPAN = re.compile(
    rf"(\d{{1,2}})\s+({_MONTH_IT})\s+(\d{{1,2}})\s+({_MONTH_IT})\s+(\d{{4}})",
    re.IGNORECASE,
)
_AGE_MIN = re.compile(r"dagli?\s+(\d{1,2})\s+anni\s+in\s+su", re.IGNORECASE)

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classica",)),
    ("pointe", ("punte",)),
    ("repertoire", ("repertorio",)),
    ("character", ("carattere",)),
]


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    offering = _build_offering(resp.text)
    return [offering] if offering is not None else []


def _build_offering(html: str) -> Offering | None:
    tree = HTMLParser(html)
    description = _meta_description(tree)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = _clean(tree.body.text(separator=" ")) if tree.body else ""

    span = _SPAN.search(text)
    if span is None:
        return None
    d1, m1, d2, m2, year = span.groups()
    y = int(year)
    start = date(y, _ITALIAN_MONTHS[m1.lower()], int(d1))
    end = date(y, _ITALIAN_MONTHS[m2.lower()], int(d2))
    season = year

    genres: list[Genre] = parse.match_genres(description, _GENRE_KEYWORDS, default=["classical"])

    return Offering(
        id=f"{SLUG}/summer-ballet-intensive-{season}",
        source=Source(provider=SLUG, url=PAGE, scrapedAt=now_utc()),
        title=f"Summer Ballet Intensive TT Stage {season}",
        genres=genres,
        level=_levels(description),
        ageRange=_age_range(text),
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Rome"),
        application=Application(url=PAGE),
    )


def _meta_description(tree: HTMLParser) -> str:
    node = tree.css_first('meta[name="description"]')
    return _clean(node.attributes.get("content") or "") if node else ""


def _clean(text: str) -> str:
    return parse.clean(ihtml.unescape(text).translate(_ZERO_WIDTH))


def _age_range(text: str) -> dict | None:
    m = _AGE_MIN.search(text)
    return {"min": int(m.group(1)), "max": None} if m else None


def _levels(description: str) -> list[Level]:
    low = description.lower()
    levels: list[Level] = []
    if "professionist" in low:
        levels.append("professional")
    if "amatori" in low:
        levels.append("open")
    return levels
