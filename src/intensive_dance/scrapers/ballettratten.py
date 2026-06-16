"""Ballettratten (Vienna) — the youth summer "Sommerintensivkurs".

API FIRST
Joomla site (generator meta "Joomla! - Open Source Content Management"), no
WordPress REST, no `ld+json` — so this is a structural `selectolax` text scrape
of the single Teenager intensive detail page
(`/neu/index.php/de/sommerintensivkurs-2026-teenager`). German.

DISCOVERY — one dated edition = one Offering.
Ballettratten is a recreational Viennese ballet school (Ballettinstitut Döbling).
Its one in-scope short-term student intensive is the youth "Sommerintensivkurs"
for Teenager (10–18): five days of classical training plus dedicated pointe
(Spitzentechnik) and variation (Variationsunterricht) units, grouped by age and
level. That is ONE Offering. The school's other dated summer offerings are out of
scope and not emitted: the "Sommerballett" Kinder editions (ages 4–12, themed
"Alice im Wunderland"/"Schwanensee" holiday camps with acrobatics and free
improvisation — recreational) and the "Erwachsene" adult course (16+, evening
hobbyist class).

The "nach Alter und Niveau in verschiedenen Gruppen" line groups participants by
level internally; it is not an audition gate, so `application.requirements` stays
empty and `level` is left unstated.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-12)
- German worded day span ("13. - 17. Juli 2026"), bounded age band
  ("(10 - 18 Jahre)" → min/max), German "€ 320" price.
- Genres classical + pointe + repertoire keyed off the curriculum terms
  (Klassisches Training / Spitze / Variation).
- Email-only registration with no audition → empty requirements; the page states
  no application status/deadline, so both stay unset (faithful, not invented).
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

SLUG = "ballettratten"
PAGE = "https://www.ballettratten.com/neu/index.php/de/sommerintensivkurs-2026-teenager"

ORG = Organization(name="Ballettratten", slug=SLUG, country="AT", city="Vienna")
VENUE = Location(venue="Ballettinstitut Döbling", city="Vienna", country="AT")

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

# "13. - 17. Juli 2026" → day–day Month Year.
_DATES = re.compile(
    r"(\d{1,2})\.\s*[-–]\s*(\d{1,2})\.\s*(" + _MONTHALT + r")\s+(\d{4})", re.IGNORECASE
)
# "Teenager (10 - 18 Jahre)" → min/max.
_AGE = re.compile(r"\((\d{1,2})\s*[-–]\s*(\d{1,2})\s*Jahre", re.IGNORECASE)
_PRICE = re.compile(r"Kosten:\s*€\s*([\d.,]+)", re.IGNORECASE)


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
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _genres(text: str) -> list[Genre]:
    low = text.lower()
    genres: list[Genre] = []
    if "ballett" in low or "klassisch" in low:
        genres.append("classical")
    if "spitze" in low:
        genres.append("pointe")
    if "variation" in low:
        genres.append("repertoire")
    return genres


def _prices(text: str) -> list[Price]:
    m = _PRICE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    return [Price(amount=amount, currency="EUR", includes=["tuition"])]


def _build_offerings(html: str) -> list[Offering]:
    text = _text(html)
    start, end, notes = _dates(text)
    season = str(start.year) if start else "2026"
    return [
        Offering(
            id=f"{SLUG}/sommerintensivkurs-teenager-{season}",
            source=Source(provider=SLUG, url=PAGE, scrapedAt=now_utc()),
            title="Sommerintensivkurs – Teenager",
            genres=_genres(text),
            ageRange=_age_range(text),
            organization=ORG,
            location=VENUE,
            schedule=Schedule(
                season=season, start=start, end=end, timezone="Europe/Vienna", notes=notes
            ),
            prices=_prices(text),
            application=Application(url=PAGE),
        )
    ]
