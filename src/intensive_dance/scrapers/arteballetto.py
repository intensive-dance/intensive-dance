"""Arteballetto — Catania, Sicily, IT — its "Summer Course in Sicily".

API FIRST: WordPress with a clean `/wp-json/` (`wp/v2`). Each yearly edition of
the *Summer Course in Sicily* is announced as a **post** (titled "N° Summer
Course …"); there's no dedicated post type or tidy category (the posts sit in the
generic "news" category), so we discover them by `search=summer course` and keep
the posts whose title *starts with* the edition number — that drops the
"…modulo di partecipazione al 16°…" registration-form post (a duplicate of an
edition, not an edition of its own).

DISCOVERY: one `Offering` per edition, year-stamped (editions kept per IDR-24).
The post bodies are free Italian prose whose shape drifts year to year, so we
only extract the fields that parse reliably across editions:

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-17):
  - DATES: "Dal 7 al 12 Luglio 2025" / "6/11 Luglio 2026" in the body, or only in
    the title for the thin years ("(11 Luglio-16 Luglio)", "26/31 Luglio 2021");
    the year comes from the date string, else the post's publish year.
  - GENRES: matched on the **Italian discipline words** only (classico/repertorio/
    contemporaneo/…), never the prose — so "London Contemporary Dance School" in a
    teacher's affiliation can't leak a `contemporary` genre (P3). Default classical.
  - LEVELS: Principianti/Intermedio/Avanzato → beginner/intermediate/advanced.
  - TEACHERS: names only — the source lists faculty three different ways across
    years (prose "Name … (affiliation)", bullet "-Name (affiliation) per …", dash
    "– NAME – affiliation"), and the institution prose is too unstructured to trust,
    so we keep just the cleanly-parseable names (cf. prague_ballet_workshop).
  - LOCATION: Catania (Sicily). AGES/PRICES/DEADLINE are never stated → unset.
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
    Level,
    Location,
    Offering,
    Organization,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.arteballetto.net"

ORG = Organization(
    name="Arteballetto",
    slug="arteballetto",
    country="IT",
    city="Catania",
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

_EDITION = re.compile(r"^\s*(\d+)\s*[°'′]\s*summer course", re.IGNORECASE)
# "Dal 7 al 12 Luglio 2025" | "6/11 Luglio2026" | "26/31 Luglio 2021"
_DATE = re.compile(
    r"(?:dal\s*)?(\d{1,2})\s*(?:[–/\-]|al)\s*(\d{1,2})\s*(" + _MONTHALT + r")\s*(\d{4})?",
    re.IGNORECASE,
)
# Two-month title form: "(11 Luglio-16 Luglio)"
_DATE2 = re.compile(
    r"(\d{1,2})\s*(" + _MONTHALT + r")\s*[-–]\s*(\d{1,2})\s*(" + _MONTHALT + r")", re.IGNORECASE
)

# Faculty region ends at the first boilerplate cue; teachers are parsed before it.
_STOPS = re.compile(
    r"\b(il prestigioso|a fine cors|le classi saranno|per info|borse di studio"
    r"|borsa di studio|email|per partecipare)",
    re.IGNORECASE,
)
# Prose / bullet: "Name … (affiliation)".
_TEACHER_PAREN = re.compile(
    r"([A-ZÀ-Ý][\wÀ-ÿ'’.\-]+(?:\s+[A-ZÀ-Ý][\wÀ-ÿ'’.\-]+){0,3}?)\s*(?:[a-zà-ÿ ]+?)?\([^)]+\)"
)
# Dash list: "– PATRICK ARMAND – affiliation".
_TEACHER_DASH = re.compile(r"[–-]\s*([A-ZÀ-Ý][A-ZÀ-Ý'’.\- ]{3,}?)\s*[–-]")

_GENRES: list[tuple[Genre, list[str]]] = [
    ("classical", ["classico", "classica"]),
    ("pointe", ["punta"]),
    ("contemporary", ["contemporaneo", "contemporanea"]),
    ("repertoire", ["repertorio"]),
    ("character", ["carattere"]),
]
_LEVELS: list[tuple[Level, str]] = [
    ("beginner", "principianti"),
    ("intermediate", "intermedio"),
    ("advanced", "avanzato"),
]


def scrape(client: httpx.Client) -> list[Offering]:
    posts = wp.fetch_all(
        client,
        "posts",
        base=BASE,
        params={"search": "summer course", "_fields": "id,date,link,title,content"},
    )
    return _build_offerings(posts)


def _dates(text: str, fallback_year: int) -> tuple[date, date] | None:
    if m := _DATE.search(text):
        d1, d2, mon, year = m.groups()
        month = _MONTHS[mon.lower()]
        y = int(year) if year else fallback_year
        return date(y, month, int(d1)), date(y, month, int(d2))
    if m := _DATE2.search(text):
        d1, mon1, d2, mon2 = m.groups()
        return (
            date(fallback_year, _MONTHS[mon1.lower()], int(d1)),
            date(fallback_year, _MONTHS[mon2.lower()], int(d2)),
        )
    return None


def _teachers(text: str) -> list[Teacher]:
    region = text[: m.start()] if (m := _STOPS.search(text)) else text
    names = [n.strip() for n in _TEACHER_PAREN.findall(region)]
    if not names:
        names = [n.strip() for n in _TEACHER_DASH.findall(region)]
    seen: set[str] = set()
    out: list[Teacher] = []
    for name in names:
        clean = parse.clean(name.title() if name.isupper() else name)
        if clean and clean not in seen:
            seen.add(clean)
            out.append(Teacher(name=clean))
    return out


def _levels(text: str) -> list[Level]:
    low = text.lower()
    return [level for level, key in _LEVELS if key in low]


def _build_offerings(posts: list[dict]) -> list[Offering]:
    offerings: list[Offering] = []
    for post in posts:
        title = html.unescape(post["title"]["rendered"])
        edition = _EDITION.search(title)
        if not edition:
            continue
        body = parse.clean(re.sub(r"<[^>]+>", " ", html.unescape(post["content"]["rendered"])))
        fallback_year = int(post["date"][:4])
        span = _dates(f"{title} {body}", fallback_year)
        if span is None:
            continue
        start, end = span
        offerings.append(
            Offering(
                id=f"arteballetto/{start.year}",
                source=Source(provider="arteballetto", url=post["link"], scrapedAt=now_utc()),
                title=f"{edition.group(1)}° Summer Course in Sicily",
                genres=parse.match_genres(body, _GENRES, default=["classical"]),
                level=_levels(body),
                organization=ORG,
                location=Location(venue="Arteballetto", city="Catania", country="IT"),
                schedule=Schedule(
                    season="summer",
                    start=start,
                    end=end,
                    timezone="Europe/Rome",
                ),
                teachers=_teachers(body),
                application=Application(url=post["link"]),
            )
        )
    offerings.sort(key=lambda o: o.id)
    return offerings
