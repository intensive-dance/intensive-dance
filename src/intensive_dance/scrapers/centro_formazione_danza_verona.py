"""Centro Formazione Danza Verona — Verona, IT — its Ballet Summer School.

API FIRST: WordPress, clean `/wp-json/`. The dated edition lives on the
`summer-school` page; the body renders to plain text we read off
`content.rendered`, keyed on the page's Italian labels (Date / Sessioni / Quote /
Programma / Audizioni). One Offering with one `Session` per week.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-17):
  - DATES + SESSIONS: two one-week blocks ("1 sessione 29 giugno – 4 luglio 2026",
    "2 sessione 6 luglio – 11 luglio 2026"); the overall span is min start … max
    end. Two-month Italian date spans (giugno → luglio).
  - GENRES: the Programma (Classico/punte, Repertorio, Contemporaneo) → classical,
    pointe, repertoire, contemporary; matched on Italian discipline words.
  - PRICES in EUR: €450 per week (tuition) + €25 registration; both weeks carry a
    30% course-fee discount, kept as a note.
  - APPLICATION: registration is open online — the "Audizioni 10 luglio" is a
    separate audition held *during* the school (for the year-round courses), so it
    is kept as a note, NOT as a requirement to attend (P1). AGES/LEVELS/TEACHERS
    are not stated → left unset (faithful, fail open).
"""

from __future__ import annotations

import html
import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Session,
    Source,
    now_utc,
)

BASE = "https://cfdanzaverona.it"
PAGE_SLUG = "summer-school"
APPLY_URL = f"{BASE}/iscrizione-summer-school/"

ORG = Organization(
    name="Centro Formazione Danza Verona",
    slug="centro-formazione-danza-verona",
    country="IT",
    city="Verona",
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

_SESSION = re.compile(
    r"(\d)\s*sessione\s+(\d{1,2})\s+("
    + _MONTHALT
    + r")\s*[–-]\s*(\d{1,2})\s+("
    + _MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)
_WEEK_PRICE = re.compile(r"(\d+)\s*euro\s+per\s+una\s+settimana", re.IGNORECASE)
_REG_PRICE = re.compile(r"(\d+)\s*euro\s+di\s+iscrizione", re.IGNORECASE)
_AUDITION = re.compile(r"Audizioni\s+(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})", re.IGNORECASE)

_GENRES: list[tuple[Genre, list[str]]] = [
    ("classical", ["classico", "classica"]),
    ("pointe", ["punte", "punta"]),
    ("contemporary", ["contemporaneo", "contemporanea"]),
    ("repertoire", ["repertorio"]),
    ("character", ["carattere"]),
]


def scrape(client: httpx.Client) -> list[Offering]:
    page = wp.fetch_page(client, PAGE_SLUG, base=BASE)
    if not page:
        return []
    return _build_offerings(page["content"]["rendered"], page["link"])


def _text(html_str: str) -> str:
    tree = HTMLParser(html_str)
    for junk in tree.css("script, style, noscript"):
        junk.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _sessions(text: str) -> list[Session]:
    out: list[Session] = []
    for num, d1, m1, d2, m2, year in _SESSION.findall(text):
        y = int(year)
        out.append(
            Session(
                label=f"Session {num}",
                start=date(y, _MONTHS[m1.lower()], int(d1)),
                end=date(y, _MONTHS[m2.lower()], int(d2)),
            )
        )
    return out


def _prices(text: str) -> list[Price]:
    out: list[Price] = []
    if m := _WEEK_PRICE.search(text):
        if (value := parse.parse_amount(m.group(1))) is not None:
            out.append(
                Price(
                    amount=value,
                    currency="EUR",
                    label="Per week",
                    includes=["tuition"],
                    notes="Both weeks: 30% off the course fee (registration fee unchanged).",
                )
            )
    if m := _REG_PRICE.search(text):
        if (value := parse.parse_amount(m.group(1))) is not None:
            out.append(Price(amount=value, currency="EUR", label="Registration fee"))
    return out


_EN_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def _audition_note(text: str) -> str | None:
    m = _AUDITION.search(text)
    if not m:
        return None
    month = _EN_MONTHS[_MONTHS[m.group(2).lower()] - 1]
    return (
        f"An audition for the school's year-round programmes is held on {int(m.group(1))} "
        f"{month} {m.group(3)}, during the Summer School (not required to attend)."
    )


def _build_offerings(html_str: str, url: str) -> list[Offering]:
    text = html.unescape(html_str)
    text = _text(text)
    sessions = _sessions(text)
    if not sessions:
        return []
    starts = [s.start for s in sessions if s.start]
    ends = [s.end for s in sessions if s.end]
    start, end = min(starts), max(ends)
    return [
        Offering(
            id=f"centro-formazione-danza-verona/{start.year}",
            source=Source(provider="centro-formazione-danza-verona", url=url, scrapedAt=now_utc()),
            title=f"Ballet Summer School {start.year}",
            genres=parse.match_genres(text, _GENRES, default=["classical"]),
            organization=ORG,
            location=Location(
                venue="Centro Formazione Danza Verona, Via Berbera 19/b",
                city="Verona",
                country="IT",
            ),
            schedule=Schedule(
                season="summer",
                start=start,
                end=end,
                timezone="Europe/Rome",
                sessions=sessions,
            ),
            prices=_prices(text),
            application=Application(url=APPLY_URL, notes=_audition_note(text)),
        )
    ]
