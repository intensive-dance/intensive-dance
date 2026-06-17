"""DAM Danza Arte e Movimento — Turin, IT — its two summer intensives.

API FIRST: WordPress, clean `/wp-json/`. DAM runs two dated summer programs, each
published as a per-edition **post**: the residential *Summer Dance Intensive
Bardonecchia* ("a porte aperte", a week on stage in the Alps) and the *Torino
Danza Estate – Stage Intensivo* (a weekly summer stage in town). We discover the
posts by `search=intensive`, keep the canonical "Dam –" ones (dropping the stray
"Programma"/"Sold Out"/"Gift Card" duplicates), and emit **one Offering per
(program, year)**, deduped. Editions are kept per IDR-24.

The intensives are multi-disciplinary; we keep only the in-scope ballet genres and
drop Hip Hop / Musical (out of scope for a ballet register). Teachers are NOT
emitted: the program hub lists "i docenti dell'ultima edizione" (last edition's
faculty), so attributing names to a given year isn't safe.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-17):
  - DATES: Bardonecchia same-month "23 – 29 Agosto 2026"; Torino two-month
    "dal 15 Giugno al 17 Luglio 2026" + one `Session` per listed week.
  - GENRES: the Discipline list, Italian keywords, ballet subset only.
  - AGES: Torino "dai 6 agli 11 anni … dai 12 anni in su" → 6+ (open top);
    Bardonecchia states none → unset.
  - PRICES are never listed (apply by form) → unset (faithful, fail open).
"""

from __future__ import annotations

import html
import re
from datetime import date

import httpx

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    Schedule,
    Session,
    Source,
    now_utc,
)

BASE = "https://www.damdanzatorino.it"

ORG = Organization(
    name="DAM Danza Arte e Movimento",
    slug="dam-danza-torino",
    country="IT",
    city="Turin",
)

_MONTHS = {
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12,
}
_MONTHALT = parse.months_alt(_MONTHS)

# "23 – 29 Agosto 2026" (same month) | "15 Giugno al 17 Luglio 2026" (two months).
_SPAN = re.compile(
    r"(\d{1,2})\s*(?:("
    + _MONTHALT
    + r")\s+)?(?:[-–]|al)\s*(\d{1,2})\s+("
    + _MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)
_WEEK = re.compile(r"settimana\s*\(([^)]+)\)", re.IGNORECASE)
_AGE_MIN = re.compile(r"dai\s+(\d{1,2})\b", re.IGNORECASE)
_AGE_MAX = re.compile(
    r"a(?:gli|i)\s+(\d{1,2})\s+anni", re.IGNORECASE
)  # "ai 23 anni" / "agli 11 anni"
_AGE_OPEN = re.compile(r"in\s+su", re.IGNORECASE)

_GENRES: list[tuple[Genre, list[str]]] = [
    ("neoclassical", ["neoclassic"]),
    ("classical", ["classica", "classico"]),
    ("pointe", ["punte", "punta"]),
    ("contemporary", ["contemporanea", "contemporaneo"]),
    ("repertoire", ["repertorio"]),
    ("character", ["carattere"]),
]


def scrape(client: httpx.Client) -> list[Offering]:
    posts = wp.fetch_all(
        client,
        "posts",
        base=BASE,
        params={"search": "intensive", "_fields": "id,link,title,content"},
    )
    return _build_offerings(posts)


def _span(text: str) -> tuple[date, date] | None:
    m = _SPAN.search(text)
    if not m:
        return None
    d1, m1, d2, m2, year = m.groups()
    y, end_month = int(year), _MONTHS[m2.lower()]
    start_month = _MONTHS[m1.lower()] if m1 else end_month
    return date(y, start_month, int(d1)), date(y, end_month, int(d2))


def _sessions(text: str) -> list[Session]:
    out: list[Session] = []
    for n, block in enumerate(_WEEK.findall(text), start=1):
        span = _span(block)
        if span:
            out.append(Session(label=f"Week {n}", start=span[0], end=span[1]))
    return out


def _ages(text: str) -> dict | None:
    m = _AGE_MIN.search(text)
    if not m:
        return None
    if _AGE_OPEN.search(text):  # "… dai 12 anni in su" → open top
        return {"min": int(m.group(1))}
    upper = _AGE_MAX.search(text)
    return (
        {"min": int(m.group(1)), "max": int(upper.group(1))} if upper else {"min": int(m.group(1))}
    )


def _program(title: str) -> tuple[str, str, Location] | None:
    low = title.lower()
    if "bardonecchia" in low:
        return (
            "bardonecchia",
            "Summer Dance Intensive Bardonecchia",
            Location(city="Bardonecchia", country="IT"),
        )
    if "estate" in low or "stage intensivo" in low:
        return (
            "torino-estate",
            "Torino Danza Estate — Stage Intensivo",
            Location(venue="DAM — Teatro Nuovo", city="Turin", country="IT"),
        )
    return None


def _build_offerings(posts: list[dict]) -> list[Offering]:
    offerings: list[Offering] = []
    seen: set[str] = set()
    for post in posts:
        title = html.unescape(post["title"]["rendered"])
        # Canonical edition posts only — skip "Programma"/"Sold Out"/"Gift Card" dupes.
        if not re.match(r"\s*dam\b", title, re.IGNORECASE):
            continue
        program = _program(title)
        if program is None:
            continue
        slug, label, location = program
        body = parse.clean(re.sub(r"<[^>]+>", " ", html.unescape(post["content"]["rendered"])))
        span = _span(body)
        if span is None:
            continue
        start, end = span
        offering_id = f"dam-danza-torino/{slug}-{start.year}"
        if offering_id in seen:
            continue
        seen.add(offering_id)
        offerings.append(
            Offering(
                id=offering_id,
                source=Source(provider="dam-danza-torino", url=post["link"], scrapedAt=now_utc()),
                title=f"{label} {start.year}",
                genres=parse.match_genres(body, _GENRES, default=["classical"]),
                ageRange=_ages(body),
                organization=ORG,
                location=location,
                schedule=Schedule(
                    season="summer",
                    start=start,
                    end=end,
                    timezone="Europe/Rome",
                    sessions=_sessions(body),
                ),
                application=Application(url=post["link"]),
            )
        )
    offerings.sort(key=lambda o: o.id)
    return offerings
