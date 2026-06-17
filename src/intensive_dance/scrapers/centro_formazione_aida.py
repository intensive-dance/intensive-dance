"""Centro Formazione Aida (CFA) — Milan, IT — its Ballet Summer Camp.

API FIRST: WordPress, clean `/wp-json/`. Each edition of the *Ballet Summer Camp*
is a post ("Ballet Summer Camp – dal … al … <month> <year>"); discover by
`search=ballet summer camp` and keep titles that start with it (dropping the
out-of-scope "Baby Summer Camp" and the audition posts). One Offering per edition,
year-stamped (kept per IDR-24).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-17):
  - DATES + SESSIONS: two one-week sessions ("I SESSIONE dal 15 al 19 giugno 2026",
    "II SESSIONE dal 22 al 26 giugno 2026"); overall = min start … max end.
  - GENRES: the discipline list (Tecnica classica / Punte e repertorio / Tecnica
    contemporanea) → classical/pointe/repertoire/contemporary; Italian keywords.
  - AGES: the three age-defined tiers ("I livello 10/11 anni … III livello 14/16
    anni") → 10–16. These are age bands, not skill levels, so `level` stays unset.
  - APPLICATION: a registration deadline whose stated year is a stale typo (the
    2026 post says "entro il 3 giugno 2025") — re-stamped with the course year, the
    P9 fix. The camp doubles as a trial for academy admission → kept as a note,
    not a requirement (P1). PRICES are not stated (info by email) → unset.
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

BASE = "https://www.centroformazioneaida.com"

ORG = Organization(
    name="Centro Formazione Aida",
    slug="centro-formazione-aida",
    country="IT",
    city="Milan",
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

_EDITION = re.compile(r"^\s*ballet summer camp", re.IGNORECASE)
_OVERALL = re.compile(
    r"dal\s+(\d{1,2})\s+al\s+(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})", re.IGNORECASE
)
_SESSION = re.compile(
    r"sessione\s+dal\s+(\d{1,2})\s+al\s+(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})", re.IGNORECASE
)
_AGE = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})\s*anni", re.IGNORECASE)
_DEADLINE = re.compile(r"entro il\s+(\d{1,2})\s+(" + _MONTHALT + r")", re.IGNORECASE)

_GENRES: list[tuple[Genre, list[str]]] = [
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
        params={"search": "ballet summer camp", "_fields": "id,link,title,content"},
    )
    return _build_offerings(posts)


def _sessions(text: str) -> list[Session]:
    out: list[Session] = []
    for n, (d1, d2, mon, year) in enumerate(_SESSION.findall(text), start=1):
        y, m = int(year), _MONTHS[mon.lower()]
        out.append(
            Session(label=f"Session {n}", start=date(y, m, int(d1)), end=date(y, m, int(d2)))
        )
    return out


def _overall(text: str, sessions: list[Session]) -> tuple[date, date] | None:
    if sessions:
        starts = [s.start for s in sessions if s.start]
        ends = [s.end for s in sessions if s.end]
        return min(starts), max(ends)
    if m := _OVERALL.search(text):
        d1, d2, mon, year = m.groups()
        y, mo = int(year), _MONTHS[mon.lower()]
        return date(y, mo, int(d1)), date(y, mo, int(d2))
    return None


def _ages(text: str) -> dict | None:
    pairs = [(int(a), int(b)) for a, b in _AGE.findall(text)]
    if not pairs:
        return None
    return {"min": min(a for a, _ in pairs), "max": max(b for _, b in pairs)}


def _deadline(text: str, course_year: int) -> date | None:
    m = _DEADLINE.search(text)
    if not m:
        return None
    # Stated year is a stale typo (a 2026 post writes "3 giugno 2025"); use the course year (P9).
    return date(course_year, _MONTHS[m.group(2).lower()], int(m.group(1)))


def _build_offerings(posts: list[dict]) -> list[Offering]:
    offerings: list[Offering] = []
    seen: set[str] = set()
    for post in posts:
        title = html.unescape(post["title"]["rendered"])
        if not _EDITION.match(title):
            continue
        body = parse.clean(re.sub(r"<[^>]+>", " ", html.unescape(post["content"]["rendered"])))
        sessions = _sessions(body)
        span = _overall(body, sessions)
        if span is None:
            continue
        start, end = span
        offering_id = f"centro-formazione-aida/{start.year}"
        if offering_id in seen:
            continue
        seen.add(offering_id)
        offerings.append(
            Offering(
                id=offering_id,
                source=Source(
                    provider="centro-formazione-aida", url=post["link"], scrapedAt=now_utc()
                ),
                title=f"Ballet Summer Camp {start.year}",
                genres=parse.match_genres(body, _GENRES, default=["classical"]),
                ageRange=_ages(body),
                organization=ORG,
                location=Location(city="Milan", country="IT"),
                schedule=Schedule(
                    season="summer",
                    start=start,
                    end=end,
                    timezone="Europe/Rome",
                    sessions=sessions,
                ),
                application=Application(
                    url=post["link"],
                    deadline=_deadline(body, start.year),
                    notes=(
                        "The two intensive weeks also count as a trial period for possible "
                        "admission to the academy's year course."
                    ),
                ),
            )
        )
    offerings.sort(key=lambda o: o.id)
    return offerings
