"""Tanzquartier Köln — the dance school's summer "Ballett & Contemporary" intensive.

API FIRST
Plain server-rendered HTML on a custom CMS — no WordPress REST (`/wp-json/` absent),
no `ld+json` — so this is a structural `selectolax` text scrape of the single
workshop detail page (`/workshops/intensiv-workshop-sommerferien-<year>`). German.

DISCOVERY — one dated edition = one Offering.
Tanzquartier Köln is a year-round Tanzschule; its one in-scope short-term student
intensive is the summer "Ballett & Contemporary Intensiv-Workshop", a five-day
holiday course with two daily modules (Klassisches Ballett in the morning,
Contemporary in the afternoon) bookable together or separately. Because the two
modules share one dated edition, venue, age band and level, they are ONE Offering
(genres classical + contemporary) carrying one Price per booking option, not two
Offerings. (The school's recreational year-round courses — Kinderballett, Hip-Hop,
K-Pop, Jazz — are out of scope and not emitted.)

The "Mittelstufe (gute Vorkenntnisse …)" line is a level/prerequisite, not an
audition gate, so `application.requirements` stays empty.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-11)
- German worded day span ("24.-28. August 2026"), open-topped age ("ab 15 Jahren"
  → null max), Mittelstufe → intermediate level.
- Several labelled Prices (both modules / ballet only / contemporary only) each
  with the member discount kept in `notes`.
- A partial sell-out note ("Klassisches Ballett ist ausgebucht!") preserved in
  `application.notes`; `application.status` stays unset (the page states
  availability, never an open/closed application status).
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
    Source,
    now_utc,
)

SLUG = "tanzquartier-koeln"
PAGE = "https://tanzquartier.koeln/workshops/intensiv-workshop-sommerferien-2026"

ORG = Organization(name="Tanzquartier Köln", slug=SLUG, country="DE", city="Cologne")

_MONTHS = {
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
_MONTHALT = parse.months_alt(_MONTHS)

# "24.-28. August 2026" → day–day Month Year.
_DATES = re.compile(
    r"(\d{1,2})\.\s*[-–]\s*(\d{1,2})\.\s*(" + _MONTHALT + r")\s+(\d{4})", re.IGNORECASE
)
_AGE = re.compile(r"ab\s+(\d{1,2})\s+Jahren", re.IGNORECASE)

# Each booking option: "<label>: <amount>,- EUR / Mitglieder <amount>,- EUR".
_PRICE_OPTIONS: list[tuple[str, str]] = [
    ("Beide Module (Ballett & Contemporary)", r"Beide Module:"),
    ("Klassisches Ballett", r"Klassisches Ballett:"),
    ("Contemporary", r"Contemporary:"),
]


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text)


def _text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _dates(text: str) -> tuple[date | None, date | None, str | None]:
    m = _DATES.search(text)
    if not m:
        return None, None, None
    d1, d2, mon, year = m.groups()
    month = _MONTHS[mon.lower()]
    y = int(year)
    return date(y, month, int(d1)), date(y, month, int(d2)), parse.clean(m.group(0))


def _age_range(text: str) -> dict | None:
    m = _AGE.search(text)
    return {"min": int(m.group(1)), "max": None} if m else None


def _level(text: str) -> list[Level]:
    return ["intermediate"] if "mittelstufe" in text.lower() else []


def _genres(text: str) -> list[Genre]:
    low = text.lower()
    genres: list[Genre] = []
    if "ballett" in low:
        genres.append("classical")
    if "contemporary" in low:
        genres.append("contemporary")
    return genres


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    for label, anchor in _PRICE_OPTIONS:
        # German "185,-" notation: a trailing "-" stands in for the cents.
        m = re.search(
            anchor + r"\s*([\d.,]+)-?\s*EUR(?:\s*/\s*Mitglieder\s*([\d.,]+)-?\s*EUR)?",
            text,
            re.IGNORECASE,
        )
        if not m:
            continue
        amount = parse.parse_amount(m.group(1))
        if amount is None:
            continue
        member = parse.parse_amount(m.group(2)) if m.group(2) else None
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=label,
                includes=["tuition"],
                notes=f"Mitglieder: {member:.0f} EUR" if member is not None else None,
            )
        )
    return prices


# Anchored on the module name so the note starts cleanly, not at the prior
# (terminator-less) date line when the page joins the two blocks with a space.
_SOLD_OUT = re.compile(
    r"(?:Klassisches Ballett|Contemporary)[^.!?]*ausgebucht[^.!?]*[.!]?", re.IGNORECASE
)


def _application(text: str) -> Application:
    # The page states availability ("… ausgebucht! … nur noch einige wenige Plätze …"),
    # never an application status — so we keep that note but leave `status` unset
    # rather than invent "open" (faithful, fail open).
    m = _SOLD_OUT.search(text)
    return Application(url=PAGE, notes=parse.clean(m.group(0)) if m else None)


def _build_offerings(html: str) -> list[Offering]:
    text = _text(html)
    start, end, notes = _dates(text)
    season = str(start.year) if start else "2026"
    return [
        Offering(
            id=f"{SLUG}/ballett-contemporary-intensiv-workshop-{season}",
            source=Source(provider=SLUG, url=PAGE, scrapedAt=now_utc()),
            title="Ballett & Contemporary Intensiv-Workshop",
            genres=_genres(text),
            level=_level(text),
            ageRange=_age_range(text),
            organization=ORG,
            location=Location(
                venue="Tanzquartier Köln – Studio Elsaßstraße", city="Cologne", country="DE"
            ),
            schedule=Schedule(
                season=season, start=start, end=end, timezone="Europe/Berlin", notes=notes
            ),
            prices=_prices(text),
            application=_application(text),
        )
    ]
