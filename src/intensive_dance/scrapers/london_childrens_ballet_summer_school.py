"""London Children's Ballet — Summer School (London, GB).

API FIRST: londonchildrensballet.com is a **Squarespace** site (no `/wp-json/`,
no `Event`/`Course` `ld+json`). The Summer School page is server-rendered, so it's
a plain `selectolax` scrape. Each dated edition is one `<p>` in the "2026 Dates"
block: an optional "SOLD OUT" span, a `<strong>Label:</strong>`, then the date
span and "(A-B yrs)".

DISCOVERY: three dated editions per year — Girls Week 1, Girls Week 2, and the
Boys Summer Intensive — each with its own dates/ages, so one `Offering` per
edition. Sold-out weeks are kept (IDR-24: past/closed cycles stay in the store).

WHAT WE EXTRACT (verified live 2026-07-01):
  - EDITIONS/DATES: "Monday 20 July - Friday 24 July" (month on both bounds) and
    "Saturday 29 - Sunday 30 August" (month once). No year is printed per line —
    it's read from the "2026 Dates" section header and applied to all editions.
  - AGES: the "(12-14yrs)" bound after each edition.
  - GENRES: the Summer School curriculum is "ballet, repertoire, jazz,
    contemporary, Musical Theatre, and pointe (for those en pointe)" → classical
    + repertoire + contemporary + pointe (jazz + Musical Theatre are out of scope
    for a ballet register).
  - LOCATION: LCB Studios, 3 Holman Road, Battersea, SW11 3RL.
  - APPLICATION: "All are welcome, no audition required" → NoneReq. The girls
    weeks show "SOLD OUT" → application.status = closed for those.

WHAT THIS SCRAPER EXERCISES: Squarespace server-rendered scrape; one Offering per
dated edition in a shared block; per-line date span with month-on-both vs
month-once; year inherited from a section header; out-of-scope genre drop
(jazz/MT); NoneReq (explicitly no audition); sold-out → closed status;
raise-on-degraded fetch.
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
    Location,
    NoneReq,
    Offering,
    Organization,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.londonchildrensballet.com"
PAGE = f"{BASE}/summer-school"

ORG = Organization(
    name="London Children's Ballet",
    slug="london-childrens-ballet-summer-school",
    country="GB",
    city="London",
)
VENUE = "London Children's Ballet Studios, 3 Holman Road, Battersea, SW11 3RL"

# "<Label>: <Day> D [Month] - <Day> D Month … (A-B yrs)". The first bound's month
# is optional (a same-month span prints it once at the end).
_EDITION = re.compile(
    r"(Girls Week \d|Boys Summer Intensive)\s*:?\s*"
    r"\w+\s+(\d{1,2})(?:\s+([A-Za-z]+))?\s*[-–]\s*\w+\s+(\d{1,2})\s+([A-Za-z]+)"
    r".{0,20}?\((\d{1,2})\s*[-–]\s*(\d{1,2})\s*yrs\)",
    re.IGNORECASE,
)
_YEAR = re.compile(r"(20\d\d)\s*Dates", re.IGNORECASE)

# The 12-14yrs week runs pointe; younger weeks don't. Kept simple: the curriculum
_GENRES: list[Genre] = ["classical", "repertoire", "contemporary", "pointe"]


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text, date.today())


def _build_offerings(html: str, today: date) -> list[Offering]:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    full = tree.body.text(separator="\n") if tree.body else ""

    ym = _YEAR.search(full)
    if not ym:
        raise ValueError("LCB: no 'YYYY Dates' header found (degraded fetch?)")
    year = int(ym.group(1))

    offerings: list[Offering] = []
    for para in tree.css("p"):
        text = parse.clean(para.text(separator=" "))
        m = _EDITION.search(text)
        if not m:
            continue
        offerings.append(_edition_offering(m, text, year))
    if not offerings:
        raise ValueError("LCB: no editions parsed from the dates block (degraded fetch?)")
    return offerings


def _edition_offering(m: re.Match, text: str, year: int) -> Offering:
    label, d1, m1, d2, m2, amin, amax = m.groups()
    month1 = parse.MONTHS[(m1 or m2).lower()]
    month2 = parse.MONTHS[m2.lower()]
    start = date(year, month1, int(d1))
    end = date(year, month2, int(d2))
    slug = _slugify(label)
    sold_out = "sold out" in text.lower()

    return Offering(
        id=f"{ORG.slug}/{slug}-{year}",
        source=Source(provider=ORG.slug, url=PAGE, scrapedAt=now_utc()),
        title=f"{label} {year}",
        genres=_GENRES,
        ageRange={"min": int(amin), "max": int(amax)},
        organization=ORG,
        location=Location(venue=VENUE, city="London", country="GB"),
        schedule=Schedule(
            season=str(year),
            start=start,
            end=end,
            timezone="Europe/London",
            notes=text,
        ),
        application=Application(
            url=PAGE,
            status="closed" if sold_out else None,
            requirements=[NoneReq()],
            notes="Sold out." if sold_out else None,
        ),
    )


def _slugify(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
