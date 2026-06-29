"""PHP Ballet Intensive (Programme de Haute Performance) — Morges, CH.

API FIRST: none usable. PHP runs on **Wix** (`generator: Wix.com Website
Builder`, no `/wp-json/`, only generic SEO `ld+json`). The single-page site is
server-side rendered, so the full text is in the static HTML — a one-page
scrape. (Wix peppers the markup with zero-width spaces, stripped up front.)

DISCOVERY: a single-purpose intensive site. The home page lists **two one-week
editions** of the same course (different summer weeks); we emit **one Offering
per edition**, slugged by start date so the ids roll forward.

WHAT THE PAGE GIVES US (verified live 2026-06-26):
  - DATES: numeric "DD.MM-D.MM YYYY" spans ("29.06-3.07 2026", "10.08-14.08
    2026"). The first carries a source typo ("20269"); the year regex takes the
    leading 4 digits (2026).
  - AGES: "young pre-professional students from 7 to 15 years old".
  - LEVEL: pre-professional (the intro and og description both say so).
  - GENRES: curriculum is "Floor barre, Ballet Class, Work on Pointe, Classical
    Variation, Stretch" → classical + pointe + repertoire (classical variation).
    The "improvisational composition" block is a created-for-the-week piece, not
    a taught contemporary class, so contemporary is not claimed.
  - LOCATION: "Ecole BeauBallet à Morges, Avenue de Gottaz 30, 1110 Morges".
  - TEACHERS: created by principal dancers Kateryna Shalkina and Oscar Chacon;
    both bios state Béjart Ballet Lausanne. Per the Wix-roster trap (credentials
    run together in the flat markup), we attribute **names + the one unambiguous
    shared affiliation** only, not the per-person credential list.
  - PRICES / APPLICATION: no fee is published; entry is via an on-page
    registration form with no audition material → prices/requirements empty,
    status not stated.

WHAT THIS SCRAPER EXERCISES: multi-edition discovery (one Offering per dated
week); numeric DD.MM date spans with a typo-tolerant year; pre-professional
level; teacher names + shared affiliation; empty prices/requirements (fail open);
raise-on-degraded-fetch.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Affiliation,
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.phpballetintensive.ch"
PAGE = f"{BASE}/"

ORG = Organization(
    name="PHP Ballet Intensive", slug="php-ballet-intensive", country="CH", city="Morges"
)

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿­"), None)

# "29.06-3.07 2026" / "10.08-14.08 2026" — numeric DD.MM-D.MM with a (possibly
# typo'd, e.g. "20269") trailing year; the leading 4 digits are the year.
_RANGE = re.compile(r"(\d{1,2})\.(\d{1,2})\s*[-–—]\s*(\d{1,2})\.(\d{1,2})\s*(20\d\d)\d*")
_AGES = re.compile(r"from\s+(\d{1,2})\s+to\s+(\d{1,2})\s+years", re.IGNORECASE)

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet", "floor barre")),
    ("pointe", ("pointe",)),
    ("repertoire", ("variation", "repertory", "repertoire")),
]

_BEJART = Affiliation(organization="Béjart Ballet Lausanne", role="principal dancer")
_TEACHERS = [
    Teacher(name="Kateryna Shalkina", role="founding teacher", affiliations=[_BEJART]),
    Teacher(name="Oscar Chacon", role="founding teacher", affiliations=[_BEJART]),
]
_APPLY_NOTE = "Register via the on-page form; no audition material stated."


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text)


def _build_offerings(html: str) -> list[Offering]:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean((tree.body.text(separator=" ") if tree.body else "").translate(_ZERO_WIDTH))

    genres = _genres(text)
    age_range = _age_range(text)
    location = Location(venue="École BeauBallet", city="Morges", country="CH")

    offerings: list[Offering] = []
    seen: set[str] = set()
    for m in _RANGE.finditer(text):
        year = int(m.group(5))
        start = date(year, int(m.group(2)), int(m.group(1)))
        end = date(year, int(m.group(4)), int(m.group(3)))
        slug = f"intensive-{start.isoformat()}"
        if slug in seen:
            continue
        seen.add(slug)
        offerings.append(
            Offering(
                id=f"php-ballet-intensive/{slug}",
                source=Source(provider="php-ballet-intensive", url=PAGE, scrapedAt=now_utc()),
                title=(
                    f"PHP Ballet Intensive — {start.strftime('%-d %B')} to "
                    f"{end.strftime('%-d %B %Y')}"
                ),
                genres=genres,
                level=["pre-professional"],
                ageRange=age_range,
                organization=ORG,
                location=location,
                schedule=Schedule(
                    season=str(year),
                    start=start,
                    end=end,
                    timezone="Europe/Zurich",
                    notes="One-week intensive, 09:30–16:30.",
                ),
                teachers=_TEACHERS,
                application=Application(url=PAGE, notes=_APPLY_NOTE),
            )
        )

    if not offerings:
        raise ValueError("PHP Ballet Intensive: no dated editions found (degraded fetch?)")
    return offerings


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _age_range(text: str) -> dict | None:
    m = _AGES.search(text)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None
