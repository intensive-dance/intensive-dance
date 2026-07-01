"""Magyar Nemzeti Balettintézet — Intensive summer ballet courses (Budapest, HU).

The Hungarian National Ballet Institute (the training arm of the Hungarian State
Opera) runs a public 6-day summer course at the Opera House.

API FIRST: mnbi.hu is a **custom** site (no `/wp-json/`, generator meta absent;
its only structured data is generic SEO/Breadcrumb). The English application page
is fully server-rendered, so it's a plain `selectolax` text scrape anchored on the
page's own labelled prose ("Date of the course:", "Course fee:", "Application
deadline:", "Venue:", "ages of N through M") — never HTML position.

DISCOVERY: one dated summer course per year → a single `Offering`.

WHAT WE EXTRACT (verified live 2026-07-01):
  - DATES: "Date of the course: 29 June - 4 July 2026" (English month names,
    cross-month, year stated once at the end).
  - AGES: "children between the ages of 6 through 17".
  - GENRES: classical ballet only (the Institute's classical syllabus).
  - PRICES: "Course fee: 98 000 HUF" (space-grouped thousands), gross, and the
    page states it includes lunch → tuition + meals.
  - DEADLINE: "Application deadline: 15 June 2026".
  - LOCATION: Opera House, 1061 Budapest, Andrássy út 22.
  - APPLICATION: apply by e-mail with the downloadable form — no audition
    material stated, so requirements are left unknown.

WHAT THIS SCRAPER EXERCISES: custom (non-WP) server-rendered HTML; label-anchored
prose fields; English cross-month date range with a single trailing year;
space-grouped HUF amount with tuition+meals includes; stated application
deadline; raise-on-degraded fetch.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.mnbi.hu"
PAGE = f"{BASE}/en/application/summer-intense-ballet-courses-in-the-opera/"

ORG = Organization(
    name="Magyar Nemzeti Balettintézet",
    slug="magyar-nemzeti-balettintezet",
    country="HU",
    city="Budapest",
)

_RANGE = re.compile(
    r"Date of the course:\s*(\d{1,2})\s+(" + parse.MONTHALT + r")\s*[-–]\s*"
    r"(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
_AGE = re.compile(r"ages of (\d{1,2})\s+through\s+(\d{1,2})", re.IGNORECASE)
_FEE = re.compile(r"Course fee:\s*([\d\s]+?)\s*HUF", re.IGNORECASE)
_DEADLINE = re.compile(
    r"Application deadline:\s*(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
_VENUE = re.compile(r"Venue:\s*([^.]+?),\s*(\d{4}\s+[^.]+?)(?:\.|\s+Course|$)", re.IGNORECASE)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return [_build_offering(resp.text)]


def _build_offering(html: str) -> Offering:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ") if tree.body else "")

    m = _RANGE.search(text)
    if not m:
        raise ValueError("MNBI: no 'Date of the course' range found (degraded fetch?)")
    year = int(m.group(5))
    start = date(year, parse.MONTHS[m.group(2).lower()], int(m.group(1)))
    end = date(year, parse.MONTHS[m.group(4).lower()], int(m.group(3)))
    season = str(year)

    return Offering(
        id=f"{ORG.slug}/summer-course-{season}",
        source=Source(provider=ORG.slug, url=PAGE, scrapedAt=now_utc()),
        title=f"Summer Ballet Course {season}",
        genres=["classical"],
        ageRange=_age_range(text),
        organization=ORG,
        location=_location(text),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Budapest",
            notes="Classes Monday–Saturday, 9:00–16:30.",
        ),
        prices=_prices(text),
        application=Application(url=PAGE, deadline=_deadline(text)),
    )


def _age_range(text: str) -> dict | None:
    m = _AGE.search(text)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _prices(text: str) -> list[Price]:
    m = _FEE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1).replace(" ", ""))
    if amount is None:
        return []
    # The page: "gross price that includes the cost of the lessons and lunch".
    return [Price(amount=amount, currency="HUF", includes=["tuition", "meals"])]


def _deadline(text: str) -> date | None:
    m = _DEADLINE.search(text)
    if not m:
        return None
    return date(int(m.group(3)), parse.MONTHS[m.group(2).lower()], int(m.group(1)))


def _location(text: str) -> Location:
    m = _VENUE.search(text)
    venue = parse.clean(f"{m.group(1)}, {m.group(2)}") if m else "Opera House"
    return Location(venue=venue, city="Budapest", country="HU")
