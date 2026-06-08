"""Balletto di Roma (IT) — the company school's public summer intensives, Rome.

API FIRST
The site (https://www.ballettodiroma.com) is WordPress + Polylang, but the
program pages are built by a page builder whose body does NOT come back through
the REST API: `GET /wp-json/wp/v2/pages/<id>` 404s for these pages (same trap as
ABT — the builder renders nothing into `content.rendered`). The REST index *is*
useful for discovery (it confirmed the two live program slugs), but the content
itself is parsed from the server-rendered `/it/` HTML, which a plain httpx fetch
with our UA returns in full — no proxy, no JS render needed.

DISCOVERY — two distinct dated editions, one Offering each (different venue /
ages / start date), both linked from `/it/formazione/`:
  1. SUMMER SCHOOL — `/it/formazione-workshop/corsi-scuola-di-danza-summer-school/`
     14th edition, 6 July – 5 September 2026, at the two Rome school sites (Via
     della Pineta Sacchetti / Via Baldo degli Ubaldi). The flagship intensive
     with European guest faculty. The public page names only "danza classica";
     the "e contemporanea" wording lives only on the gated brochure page, so the
     public Offering is classical-only (faithful to the page, not inflated).
  2. CAMPUS ESTIVO "La Scuola Continua" —
     `/it/landing/campus-estivo-balletto-di-roma-monterotondo/`
     1st edition, from 6 July 2026, four weeks, at the Monterotondo Scalo site
     (Via Salaria 86). Camp for ages 6-18; classical + contemporary (urban is
     dropped as out of scope for a ballet register).

LANGUAGE NOTE: parsing is language-agnostic in spirit (Italian month map on top
of the English one, numeric ages/dates, enum genres) so it survives an EN render
too, but the IT URLs are the stable canonical ones and are pinned here.

PRICES: neither page publishes a fee — both gate costs behind a brochure-request
form ("Per ricevere i costi … compila il form"), so `prices` is left empty (not
stated, per the fail-open rule), not invented.

DATES: the Summer School states a full cross-month range; the Campus states only
a start ("Dal 6 luglio") plus "quattro settimane" with no explicit end, so its
`end` is left null rather than computing four weeks.

AGE / LEVELS: the Summer School lists three open-ended level bands (Beginners
8+, Intermediate 12+, Advanced 15+) → ageRange {min: 8} with a null max (the
advanced band is "dai 15 anni in su"). The Campus states a closed "dai 6 ai 18
anni" → {min: 6, max: 18}.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08)
- TWO fixed program pages → one Offering each (distinct venue / dates / ages).
- Open-ended age band (null max) vs. closed band, both from Italian prose.
- Level enum derived from Italian band labels (Principianti/Intermedio/Avanzato).
- Empty `prices` (gated behind a form) — faithful, not invented.
- Cross-month Italian date range vs. a start-only edition with null `end`.
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
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.ballettodiroma.com"
SUMMER_SCHOOL_URL = f"{BASE}/it/formazione-workshop/corsi-scuola-di-danza-summer-school/"
CAMPUS_URL = f"{BASE}/it/landing/campus-estivo-balletto-di-roma-monterotondo/"

ORG = Organization(name="Balletto di Roma", slug="balletto-di-roma", country="IT", city="Rome")

# Italian month names on top of the shared English map so a date regex parses
# whichever language the page renders in.
_MONTHS = {
    **parse.MONTHS,
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
_MONTHALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classica", "classico", "classical", "ballet")),
    ("contemporary", ("contemporane", "contemporary")),
]

# Italian level-band labels → Level enum, matched against the admission sentence
# so a stray mention elsewhere doesn't leak a band.
_LEVEL_KEYWORDS: list[tuple[Level, tuple[str, ...]]] = [
    ("beginner", ("principiant",)),
    ("intermediate", ("intermedio",)),
    ("advanced", ("avanzato",)),
]


def scrape(client: httpx.Client) -> list[Offering]:
    summer = _page_text(client, SUMMER_SCHOOL_URL)
    campus = _page_text(client, CAMPUS_URL)
    offerings = [
        _summer_school(summer),
        _campus(campus),
    ]
    offerings.sort(key=lambda o: o.id)
    return offerings


def _page_text(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    resp.raise_for_status()
    tree = HTMLParser(resp.text)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


# --- Summer School (Rome) -----------------------------------------------------


def _summer_school(text: str) -> Offering:
    start, end = _date_range(text)
    season = str((end or start or date(2026, 1, 1)).year)
    return Offering(
        id=f"balletto-di-roma/summer-school-{season}",
        source=Source(provider="balletto-di-roma", url=SUMMER_SCHOOL_URL, scrapedAt=now_utc()),
        title=f"Summer School {season}",
        genres=_genres(text),
        level=_levels(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(city="Rome", country="IT"),
        schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Rome"),
        prices=[],
        application=Application(url=SUMMER_SCHOOL_URL),
    )


# --- Campus Estivo "La Scuola Continua" (Monterotondo) ------------------------


def _campus(text: str) -> Offering:
    start = _single_date(text)
    season = str((start or date(2026, 1, 1)).year)
    return Offering(
        id=f"balletto-di-roma/campus-estivo-monterotondo-{season}",
        source=Source(provider="balletto-di-roma", url=CAMPUS_URL, scrapedAt=now_utc()),
        title=f"Campus Estivo Monterotondo {season}",
        genres=_genres(text),  # classical + contemporary; urban dropped (out of scope)
        level=_levels(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(
            venue="Balletto di Roma — Monterotondo", city="Monterotondo", country="IT"
        ),
        schedule=Schedule(season=season, start=start, end=None, timezone="Europe/Rome"),
        prices=[],
        application=Application(url=CAMPUS_URL),
    )


# --- shared helpers -----------------------------------------------------------

# Cross-month range: "6 luglio – 5 settembre 2026" (single trailing year).
_RANGE = re.compile(
    r"(\d{1,2})\s+(" + _MONTHALT + r")\s*[-–]\s*(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    d1, mon1, d2, mon2, year = m.groups()
    y = int(year)
    return date(y, _MONTHS[mon1.lower()], int(d1)), date(y, _MONTHS[mon2.lower()], int(d2))


# Start-only line: "Dal 6 luglio …"; the year is carried elsewhere in the page.
_SINGLE = re.compile(r"\bdal\s+(\d{1,2})\s+(" + _MONTHALT + r")\b", re.IGNORECASE)
_YEAR = re.compile(r"\b(20\d{2})\b")


def _single_date(text: str) -> date | None:
    m = _SINGLE.search(text)
    if not m:
        return None
    day, month = m.groups()
    ym = _YEAR.search(text)
    if not ym:
        return None
    return date(int(ym.group(1)), _MONTHS[month.lower()], int(day))


# "dagli 8 anni", "dai 12 anni", "dai 6 ai 18 anni", "dai 15 anni in su".
# A closed "dai N ai M anni" sets both bounds; bare "dai N anni" / "in su" sets a
# lower bound only. When any open-ended band is present the overall max is null.
_AGE_CLOSED = re.compile(r"da[il]?\s+(\d{1,2})\s+a[il]?\s+(\d{1,2})\s+anni", re.IGNORECASE)
_AGE_OPEN = re.compile(r"da(?:gli|i|l)?\s+(\d{1,2})\s+anni", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    closed = [(int(a), int(b)) for a, b in _AGE_CLOSED.findall(text) if 3 <= int(a) <= int(b) <= 30]
    if closed:
        return {"min": min(a for a, _ in closed), "max": max(b for _, b in closed)}
    # Strip the closed matches before reading open bands so we don't double count.
    rest = _AGE_CLOSED.sub(" ", text)
    opens = [int(m.group(1)) for m in _AGE_OPEN.finditer(rest) if 3 <= int(m.group(1)) <= 30]
    if not opens:
        return None
    return {"min": min(opens)}  # open-ended top band → null max


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _levels(text: str) -> list[Level]:
    return parse.match_genres(text, _LEVEL_KEYWORDS, default=[])
