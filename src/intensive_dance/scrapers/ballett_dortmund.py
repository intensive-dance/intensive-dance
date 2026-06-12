"""Ballett Dortmund — Internationale Sommerakademie, a one-week summer intensive.

API FIRST
theaterdo.de is a TYPO3 site: no WordPress REST (`/wp-json/` 404s) and the only
`ld+json` on the page is a generic `BreadcrumbList` (no `Event`/`Course`). The
page is fully server-rendered plain HTML, so this is a structural `selectolax`
scrape. Each edition lives in a `div.frame--type-text` whose `<h3>` names it and
whose `<p>` bodies carry `<strong>Label</strong> value` pairs split by `<br>`.

DISCOVERY — one dated edition = one Offering, the open course only.
The Sommerakademie page lists two parallel editions for the same week: the
**Internationale Sommerakademie** (ages 15+, open registration) and the
**Sommerakademie Junior** (ages 12–15, a DBfT cooperation with a video
application). The Junior course is already in the register under the
`dbft-sommerakademie` provider (scraped from dbft.de), so to avoid a
cross-provider duplicate this scraper emits **only the Internationale
Sommerakademie**. Year-stamped because the source labels the edition by year.

The Internationale Sommerakademie has no audition/photo/video gate — "Willkommen
sind alle … Hobbytänzer*innen", reached via a plain "Anmeldung" link — so
`application.requirements` is `[NoneReq]` (explicitly nothing), unlike the Junior
course's `Bewerbungspflicht`.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-12)
- German month-name day span ("24-29. August 2026") via a local month map.
- Label/value extraction from `<strong>…</strong>` runs inside `<p>`/`<br>`.
- Open-topped age ("ab 15 Jahren") → age_range with null max.
- "Kursgebühr 590 €" → Price (EUR) with tuition+meals (lunch/fruit/water listed;
  accommodation explicitly NOT included, no amount → no separate Price).
- Genres scoped to the "Kurse" curriculum line (classical/contemporary/
  repertoire/pointe), not loose prose.
- `application.requirements = [NoneReq]` for an open-registration course.
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
    Price,
    Schedule,
    Source,
    now_utc,
)

PAGE = "https://www.theaterdo.de/ballett/startseite/mitmachen/sommerakademie/"
SLUG = "ballett-dortmund"

ORG = Organization(name="Ballett Dortmund", slug=SLUG, country="DE", city="Dortmund")

# The open course's section heading; the Junior course (DBfT) is skipped here.
_HEADING = "Internationale Sommerakademie"

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("klassischer tanz", "klassisch")),
    ("contemporary", ("moderne tanz", "modern", "clug", "kylián", "kylian")),
    ("repertoire", ("repertoire",)),
    ("pointe", ("point work", "pointe", "spitze")),
]

_GERMAN_MONTHS = {
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}

# "24-29. August 2026" — day–day, one month name, one year.
_DATE_SPAN = re.compile(
    r"(\d{1,2})\.?\s*[-–]\s*(\d{1,2})\.?\s*(" + "|".join(_GERMAN_MONTHS) + r")\s+(\d{4})",
    re.IGNORECASE,
)
_AGE_FROM = re.compile(r"ab\s+(\d{1,2})\s+Jahren", re.IGNORECASE)
_PRICE = re.compile(r"(\d[\d.,]*)\s*€")
_LABEL = re.compile(r"<strong>\s*(.*?)\s*</strong>\s*(.*)", re.IGNORECASE | re.DOTALL)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text)


def _section(html: str) -> tuple[dict[str, str], str] | None:
    """The Internationale-Sommerakademie frame as a label→value map + its text."""
    tree = HTMLParser(html)
    for frame in tree.css("div.frame--type-text"):
        heading = frame.css_first("h3")
        if heading and parse.clean(heading.text()) == _HEADING:
            return _fields(frame), parse.clean(frame.text(separator=" "))
    return None


def _fields(frame) -> dict[str, str]:
    fields: dict[str, str] = {}
    for para in frame.css("p"):
        for segment in re.split(r"<br\s*/?>", para.html or ""):
            m = _LABEL.search(segment)
            if not m:
                continue
            label = parse.clean(HTMLParser(m.group(1)).text())
            value = parse.clean(HTMLParser(m.group(2)).text())
            if label and label not in fields:
                fields[label] = value
    return fields


def _span(value: str) -> tuple[date | None, date | None]:
    m = _DATE_SPAN.search(value)
    if not m:
        return None, None
    d1, d2, month_name, year = m.groups()
    month = _GERMAN_MONTHS[month_name.lower()]
    return date(int(year), month, int(d1)), date(int(year), month, int(d2))


def _age_range(value: str) -> dict | None:
    m = _AGE_FROM.search(value)
    return {"min": int(m.group(1)), "max": None} if m else None


def _price(value: str) -> list[Price]:
    m = _PRICE.search(value)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if not amount:
        return []
    return [
        Price(
            amount=amount,
            currency="EUR",
            label="Kursgebühr",
            includes=["tuition", "meals"],
        )
    ]


def _build_offerings(html: str) -> list[Offering]:
    found = _section(html)
    if not found:
        return []
    fields, section_text = found

    start, end = _span(fields.get("Termin", ""))
    year = start.year if start else None
    season = str(year) if year else "unknown"
    curriculum = fields.get("Kurse", "")

    return [
        Offering(
            id=f"{SLUG}/internationale-sommerakademie-{year}"
            if year
            else f"{SLUG}/internationale-sommerakademie",
            source=Source(provider=SLUG, url=PAGE, scrapedAt=now_utc()),
            title=f"Internationale Sommerakademie {year}"
            if year
            else "Internationale Sommerakademie",
            genres=parse.match_genres(curriculum, _GENRE_KEYWORDS, default=["classical"]),
            ageRange=_age_range(fields.get("Alter", "")),
            organization=ORG,
            location=Location(
                venue=fields.get("Ort") or "Ballettzentrum Westfalen",
                city="Dortmund",
                country="DE",
            ),
            schedule=Schedule(
                season=season,
                start=start,
                end=end,
                timezone="Europe/Berlin",
                notes=parse.clean(fields.get("Termin", "")) or None,
            ),
            prices=_price(fields.get("Kursgebühr", section_text)),
            application=Application(
                url=PAGE,
                requirements=[NoneReq()],
            ),
        )
    ]
