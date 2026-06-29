"""The Hammond — Chester, GB — its Summer School intensive.

API FIRST: none usable. The Hammond runs on **Squarespace** (assets under
`images.squarespace-cdn.com`, no `/wp-json/`); the only `ld+json` is generic
`WebSite`/`Organization`/`LocalBusiness` SEO data (no `Event`/`Course`). The
`/summer-school-2026` page is fully server-rendered, so it's a plain text scrape.

DISCOVERY: the Summer School runs as **two one-week courses** ("Dance and
Musical Theatre Intensive", residential or non-residential). The weeks are
distinct dated editions of the same course, so — like GradPro — we emit **one
Offering per week** (distinct dates, shared ages/fees/genres). Season-keyed from
the parsed year so ids roll forward.

WHAT THE PAGE GIVES US (verified live 2026-06-26):
  - DATES: "Dates: 2026 / Week One: Monday, 27th July - Friday, 31st July / Week
    Two: Monday, 3rd August - Friday, 7th August" — the day-month ranges are
    year-less; the year is read from the "Dates: YYYY" stamp above them.
  - AGES: "For Ages: 7 - 17".
  - GENRES: curriculum is "Ballet, Jazz, Musical Theatre, Repertoire, and
    Commercial dance" → classical + repertoire. The non-ballet styles (Jazz,
    Musical Theatre, Commercial, Lyrical, singing) are out of scope and dropped.
  - PRICES: "Residential - £625 / Non-Residential - £385" — emitted as two Price
    options; the residential one bundles boarding accommodation.
  - APPLICATION: open enrollment via an "Apply Now" form ("now open for
    application"); no audition material is required for the summer school →
    status open, requirements left unknown.

SCOPE CALLS:
  - The full-time school fees on `/fees-funding` (per-term tuition, a £160
    audition **registration** fee) belong to the year-round vocational school's
    audition flow — NOT the open-enrollment summer school — so they're not
    borrowed onto it.
  - The "Acting & Musical Theatre" / "Acting & Performance" summer tabs teach no
    ballet → out of scope. The Autumn/Spring "Holiday Courses" on `/intensives`
    carry prices but **no specific dates** and no stated ballet discipline → not
    emitted (would mean inventing dates/genre).

WHAT THIS SCRAPER EXERCISES: multi-Offering-per-page week split; year-less
day-month ranges with a separate year stamp; multi-Price (tuition vs
tuition+accommodation); out-of-scope genre drop; raise-on-degraded-fetch.
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
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.thehammond.co.uk"
PAGE = f"{BASE}/summer-school-2026"
APPLY_PAGE = f"{BASE}/apply"

ORG = Organization(name="The Hammond", slug="the-hammond", country="GB", city="Chester")

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet",)),
    ("repertoire", ("repertoire",)),
]

# "Week One: Monday, 27th July - Friday, 31st July" — weekday words prefix each
# bound but aren't captured; the lines are year-less (year read separately).
_WEEK = re.compile(
    r"Week\s+(One|Two|Three|Four)\s*:\s*\w+,?\s*(\d{1,2})(?:st|nd|rd|th)?\s+("
    + parse.MONTHALT
    + r")\s*[-–—]\s*\w+,?\s*(\d{1,2})(?:st|nd|rd|th)?\s+("
    + parse.MONTHALT
    + r")",
    re.IGNORECASE,
)
_YEAR = re.compile(r"Dates:\s*(20\d\d)|Summer School\s+(20\d\d)", re.IGNORECASE)
_AGES = re.compile(r"For Ages:\s*(\d{1,2})\s*[-–]\s*(\d{1,2})", re.IGNORECASE)
_NON_RES = re.compile(r"Non-?Residential\s*[-–:]?\s*£\s*([\d,]+)", re.IGNORECASE)
_RES = re.compile(r"(?<![Nn]on-)(?<![Nn]on)\bResidential\s*[-–:]?\s*£\s*([\d,]+)", re.IGNORECASE)
_OPEN = re.compile(r"open\s+for\s+application", re.IGNORECASE)

_WEEK_ORD = {"one": "1", "two": "2", "three": "3", "four": "4"}
_SCHEDULE_NOTE = "09:00–16:00 daily; residential or non-residential."
_APPLY_NOTE = "Open-enrollment summer school; apply via The Hammond's online form."


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text)


def _build_offerings(html: str) -> list[Offering]:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ") if tree.body else "")

    ym = _YEAR.search(text)
    if not ym:
        raise ValueError("The Hammond: no summer-school year stamp found (degraded fetch?)")
    year = int(ym.group(1) or ym.group(2))
    season = str(year)

    genres = _genres(text)
    age_range = _age_range(text)
    prices = _prices(text)
    status = "open" if _OPEN.search(html) or _OPEN.search(text) else None
    location = Location(venue="The Hammond", city="Chester", country="GB")

    offerings: list[Offering] = []
    for m in _WEEK.finditer(text):
        ordinal = m.group(1).lower()
        start = date(year, parse.MONTHS[m.group(3).lower()], int(m.group(2)))
        end = date(year, parse.MONTHS[m.group(5).lower()], int(m.group(4)))
        slug = _WEEK_ORD[ordinal]
        offerings.append(
            Offering(
                id=f"the-hammond/summer-school-{season}-week-{slug}",
                source=Source(provider="the-hammond", url=PAGE, scrapedAt=now_utc()),
                title=f"Summer School {season} — Week {m.group(1).title()}",
                genres=genres,
                ageRange=age_range,
                organization=ORG,
                location=location,
                schedule=Schedule(
                    season=season,
                    start=start,
                    end=end,
                    timezone="Europe/London",
                    notes=_SCHEDULE_NOTE,
                ),
                prices=prices,
                application=Application(status=status, url=APPLY_PAGE, notes=_APPLY_NOTE),
            )
        )

    if not offerings:
        raise ValueError("The Hammond: no Summer School week markers found (degraded fetch?)")
    return offerings


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _age_range(text: str) -> dict | None:
    m = _AGES.search(text)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    nm = _NON_RES.search(text)
    if nm and (amount := parse.parse_amount(nm.group(1))) is not None:
        prices.append(
            Price(amount=amount, currency="GBP", label="Non-residential", includes=["tuition"])
        )
    rm = _RES.search(text)
    if rm and (amount := parse.parse_amount(rm.group(1))) is not None:
        prices.append(
            Price(
                amount=amount,
                currency="GBP",
                label="Residential",
                includes=["tuition", "accommodation"],
                notes="Includes boarding accommodation.",
            )
        )
    return prices
