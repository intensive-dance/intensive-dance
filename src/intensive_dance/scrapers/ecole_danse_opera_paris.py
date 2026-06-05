"""École de Danse de l'Opéra national de Paris — its international Summer School
("Stage d'été").

API FIRST: none usable. operadeparis.fr is a large custom site, but the Summer
School page is server-rendered, so we read the (distinctive) facts straight out
of the page text. One `Offering` — the current Summer School — dropped once its
end date is past.

WHAT THE PAGE GIVES US (verified live 2026-06): season + dates ("the 2026 Summer
School will take place from July 6th to 18th"), the 10-19 age range, and a
non-refundable application fee (51 € for 2026). The graduated course fees are
listed without clear labels, so they're left out (noted in `application.notes`)
rather than guessed.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance.models import (
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.operadeparis.fr"
SUMMER = f"{BASE}/en/artists/ballet-school/summer-internship"
PRACTICAL = f"{SUMMER}/practical-information"

ORG = Organization(
    name="École de Danse de l'Opéra national de Paris", slug="ecole-danse-opera-paris",
    country="FR", city="Paris",
)
VENUE = "École de Danse de l'Opéra national de Paris, Nanterre"


def scrape(client: httpx.Client) -> list[Offering]:
    # Dates/ages are on the main page; the application fee is on the practical page.
    text = " ".join(filter(None, (_text(client, SUMMER), _text(client, PRACTICAL))))
    if not text.strip():
        return []
    return [o] if (o := _build_offering(text, date.today())) is not None else []


def _build_offering(text: str, today: date) -> Offering | None:
    season = _season(text)
    start, end = _date_range(text, season)
    if end is not None and end < today:
        return None

    app_fee = _application_fee(text)
    notes = f"Non-refundable application fee of €{app_fee:g} (course fees graduated; see the school's site)." if app_fee else None
    return Offering(
        id=f"ecole-danse-opera-paris/summer-school-{season}",
        source=Source(provider="ecole-danse-opera-paris", url=SUMMER, scrapedAt=now_utc()),
        title=f"Paris Opera Ballet School — Summer School {season}",
        genres=_genres(text),
        kind="summer-school",
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue=VENUE, city="Paris", country="FR"),
        schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Paris"),
        application=Application(url=SUMMER, notes=notes),
    )


# --- parsing ------------------------------------------------------------------

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"],
        start=1,
    )
}
_MONTHALT = "|".join(_MONTHS)
_SEASON = re.compile(r"(20\d\d)\s+Summer School", re.IGNORECASE)
# "from July 6th to 18th" — the page renders the ordinal as a separate token
# ("July 6 th to 18 th"), so allow whitespace before st/nd/rd/th.
_RANGE = re.compile(
    r"(" + _MONTHALT + r")\s+(\d{1,2})\s*(?:st|nd|rd|th)?\s+to\s+(\d{1,2})\s*(?:st|nd|rd|th)?", re.IGNORECASE
)
_AGE = re.compile(r"age\s+(\d{1,2})\s+to\s+(\d{1,2})", re.IGNORECASE)
_APP_FEE = re.compile(r"(\d{1,3})\s?€\s+of application fees", re.IGNORECASE)


def _season(text: str) -> str:
    match = _SEASON.search(text)
    return match.group(1) if match else "unknown"


def _date_range(text: str, season: str) -> tuple[date | None, date | None]:
    year = int(season) if season.isdigit() else None
    match = _RANGE.search(text)
    if not match or year is None:
        return None, None
    num = _MONTHS[match.group(1).lower()]
    return date(year, num, int(match.group(2))), date(year, num, int(match.group(3)))


def _age_range(text: str) -> dict | None:
    match = _AGE.search(text)
    return {"min": int(match.group(1)), "max": int(match.group(2))} if match else None


def _application_fee(text: str) -> float | None:
    match = _APP_FEE.search(text)
    return float(match.group(1)) if match else None


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet")),
    ("contemporary", ("contemporary",)),
    ("character", ("character",)),
    ("repertoire", ("repertoire",)),
]


def _genres(text: str) -> list[Genre]:
    low = text.lower()
    return [g for g, keys in _GENRE_KEYWORDS if any(k in low for k in keys)] or ["classical"]


def _text(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    if resp.status_code == 404:
        return ""
    resp.raise_for_status()
    tree = HTMLParser(resp.text)
    for node in tree.css("script, style, noscript, nav, header, footer"):
        node.decompose()
    return re.sub(r"\s+", " ", tree.body.text(separator=" ")) if tree.body else ""
