"""Baletní akademie Adély Pollertové — Prague, CZ — its children's summer intensives.

API FIRST: none usable. `/wp-json/` returns the page shell (not a REST API), and
the site serves a **generic nav/contact shell for every non-home path** (a JS
catch-all), so detail "pages" (`/letni-kurzy/`, news, e-shop) carry no
edition-specific content. The one place the dated editions are server-rendered is
the **home** page's summer block, so we parse that HTML (plain nginx, no proxy).

The academy is run by Adéla Pollertová (former soloist, Hamburg Ballet & National
Theatre Prague). The site publishes only the editions' names and date spans — no
prices, numeric ages, faculty, or application detail are exposed statically, so
we emit the faithful minimum and don't invent the rest.

DISCOVERY: the home advertises two **separate dated editions** of the summer
intensive ("Letní soustředění"), split by age group — younger children and older
children, each its own week. We emit **one Offering per edition** (distinct
dates), year-stamped from the parsed year.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-16):
  - DATES: home block "Letní soustředění pro mladší děti - 10.8.-14.8. 2026"
    (Czech numeric "D.M.-D.M. YYYY" span).
  - DISCOVERY split: younger ("mladší") vs older ("starší") children → two
    Offerings; the raw Czech label is kept in `schedule.notes`.
  - GENRE: classical (a ballet academy's ballet intensive).
  - AGE: published only as "younger"/"older children" (no numeric bounds) → left
    null; the group is in the notes.
  - LOCATION: the academy studio, Na Poříčí 25, Praha 1.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Location,
    Offering,
    Organization,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.baletniakademie.cz"
HOME = f"{BASE}/"

ORG = Organization(
    name="Baletní akademie Adély Pollertové",
    slug="baletni-akademie-pollertova",
    country="CZ",
    city="Prague",
)
_LOCATION = Location(venue="Na Poříčí 25, Praha 1", city="Prague", country="CZ")

# "Letní soustředění pro mladší děti - 10.8.-14.8. 2026"
_EDITION_RE = re.compile(
    r"Letní soustředění pro (mladší|starší) děti\s*[-–]\s*"
    r"(\d{1,2})\.(\d{1,2})\.\s*[-–]\s*(\d{1,2})\.(\d{1,2})\.\s*(\d{4})",
    re.I,
)
# Czech "mladší"/"starší" → (slug fragment, English label).
_GROUPS = {
    "mladší": ("younger-children", "Younger Children"),
    "starší": ("older-children", "Older Children"),
}


def scrape(client: httpx.Client) -> list[Offering]:
    return _build_offerings(_page_text(client.get(HOME).text))


def _page_text(html: str) -> str:
    tree = HTMLParser(html)
    for junk in tree.css("script, style, noscript"):
        junk.decompose()
    body = tree.body
    text = body.text(separator="\n") if body else ""
    lines = [parse.clean(line) for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _build_offerings(home: str) -> list[Offering]:
    offerings: list[Offering] = []
    for match in _EDITION_RE.finditer(home):
        group_key = match.group(1).lower()
        slug_part, label = _GROUPS[group_key]
        year = int(match.group(6))
        start = date(year, int(match.group(3)), int(match.group(2)))
        end = date(year, int(match.group(5)), int(match.group(4)))
        offerings.append(
            Offering(
                id=f"baletni-akademie-pollertova/{slug_part}-{year}",
                source=Source(
                    provider="baletni-akademie-pollertova", url=HOME, scrapedAt=now_utc()
                ),
                title=f"Summer Intensive for {label} {year}",
                genres=["classical"],
                organization=ORG,
                location=_LOCATION,
                schedule=Schedule(season="summer", start=start, end=end, notes=match.group(0)),
            )
        )
    return offerings
