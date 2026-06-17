"""Bobbio Summer Ballet Intensive — Bobbio (Piacenza), IT — its summer intensive.

API FIRST: **WordPress**, but the page builder (Elementor) renders *nothing*
into the REST `content.rendered` (the ABT trap) — `/wp-json/wp/v2/pages` bodies
come back empty, and The Events Calendar plugin holds zero events. So we parse
the **server-rendered HTML** (plain nginx, no Cloudflare, content is all in the
static markup — no JS render, no proxy tier needed).

The site is Italian (gtranslate overlay); we read the Italian source directly.

DISCOVERY: one provider, one dedicated single-purpose site, one current edition.
We emit **one Offering** for the upcoming summer edition, season-keyed from the
parsed year (id rolls forward as the site advances). The site's *detail* pages
(schedule/pricing/general-info) still carry **stale 2025** content; only the
home page was updated for the new edition, so — like Prague Ballet Intensive —
the dated edition lives in the **home** page text ("Summer Camp 2026: dal 14 al
24 Luglio"), and we take everything edition-specific from pages confirmed current
(home + registration, both footer "© 2026"). We do **not** borrow the 2025
pricing page's course fees onto a 2026 offering (that would be inventing data);
only the registration page's current €150 registration fee is kept (as an
application note).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-16):
  - DATES: home "dal 14 al 24 Luglio" + year from "Summer Camp 2026" (Italian
    month map, bespoke "dal D al D <mese>" regex).
  - GENRES from the home curriculum list ("danza classica, punte, … variazioni,
    repertorio, danza contemporanea … Horton") → classical, pointe, repertoire,
    contemporary.
  - LEVEL: "ballerini di tutti i livelli, dai principianti agli avanzati" + the
    three home tracks (Introduzione / Perfezionamento / Innovazione) → beginner,
    intermediate, advanced.
  - APPLICATION: status open ("Le candidature sono aperte"), deadline 30 June,
    requirements = a portrait (HeadshotReq) + two defined ballet poses
    (PhotosReq/defined-poses: fourth croisé en relevé, first arabesque; pointe
    not required), €150 registration fee + 50% cancellation refund in notes.
  - TEACHERS: the dedicated site's "Docenti" page roster (single-purpose site, so
    these are this intensive's faculty); the artistic director (Dora Ciacca) is
    role-tagged, the rest name-only (no over-claimed affiliations).
  - AGE: not numerically stated for the main intensive ("ogni livello", "tutte le
    età") — left null rather than guessed (the 5-12 children's mini-track lives
    only on the stale 2025 pricing page, so it is not emitted).

ROBUSTNESS: a missing "Summer Camp YYYY" marker on this always-current site means
a degraded fetch, so `_build_offerings` *raises* (run.py then keeps the prior
store) rather than returning [] and wiping the committed edition — one such silent
wipe tripped the zero-offering audit (#316).
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
    HeadshotReq,
    Level,
    Location,
    Offering,
    Organization,
    PhotosReq,
    Requirement,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://bobbiosummerballetintensive.com"
HOME = f"{BASE}/"
REGISTRATION = f"{BASE}/registrazione/"
DOCENTI = f"{BASE}/docenti/"

ORG = Organization(
    name="Bobbio Summer Ballet Intensive",
    slug="bobbio-summer-ballet-intensive",
    country="IT",
    city="Bobbio",
)

# Italian month names (the home/registration dates are month-named, not numeric).
_IT_MONTHS: dict[str, int] = {
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
_IT_MONTHALT = parse.months_alt(_IT_MONTHS)

_DATES_RE = re.compile(rf"dal\s+(\d{{1,2}})\s+al\s+(\d{{1,2}})\s+({_IT_MONTHALT})", re.I)
_YEAR_RE = re.compile(r"Summer Camp\s+(\d{4})", re.I)
_DEADLINE_RE = re.compile(rf"Scadenza\s+(?:il\s+)?(\d{{1,2}})\s+({_IT_MONTHALT})", re.I)
_REG_FEE_RE = re.compile(r"quota di registrazione di\s*(\d+)\s*€", re.I)

_GENRES: list[tuple[Genre, list[str]]] = [
    ("classical", ["danza classica", "balletto classico", "classica"]),
    ("pointe", ["punte"]),
    ("contemporary", ["contemporanea", "horton"]),
    ("repertoire", ["repertorio", "variazioni"]),
]
_LEVELS: list[tuple[Level, list[str]]] = [
    ("beginner", ["principianti", "introduzione al balletto"]),
    ("intermediate", ["tutti i livelli", "ogni livello"]),
    ("advanced", ["avanzati", "esperti", "perfezionamento"]),
]


def scrape(client: httpx.Client) -> list[Offering]:
    home = _page_text(client.get(HOME).text)
    registration = _page_text(client.get(REGISTRATION).text)
    docenti = client.get(DOCENTI).text
    return _build_offerings(home, registration, docenti, date.today())


def _page_text(html: str) -> str:
    """Flatten an Elementor page to one cleaned text blob for keyword/regex reads."""
    tree = HTMLParser(html)
    for junk in tree.css("script, style, noscript"):
        junk.decompose()
    node = tree.css_first("div.elementor") or tree.body
    text = node.text(separator="\n") if node else ""
    lines = [parse.clean(line) for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _dates(home: str) -> tuple[date | None, date | None, int | None, str | None]:
    year_match = _YEAR_RE.search(home)
    year = int(year_match.group(1)) if year_match else None
    span = _DATES_RE.search(home)
    if not span or year is None:
        return None, None, year, span.group(0) if span else None
    month = _IT_MONTHS[span.group(3).lower()]
    start = date(year, month, int(span.group(1)))
    end = date(year, month, int(span.group(2)))
    return start, end, year, span.group(0)


def _requirements(registration: str) -> list[Requirement]:
    if "foto" not in registration.lower() or "arabesque" not in registration.lower():
        return []
    pointe_note = (
        "Pointe shoes are not required for the photos."
        if "punte non sono obbligatorie" in registration.lower()
        else None
    )
    return [
        HeadshotReq(),
        PhotosReq(
            specificity="defined-poses",
            poses=["fourth position croisé en relevé", "first arabesque"],
            notes=pointe_note,
        ),
    ]


def _application(registration: str, year: int | None) -> Application:
    status = "open" if "candidature sono aperte" in registration.lower() else None
    deadline = None
    if (match := _DEADLINE_RE.search(registration)) and year is not None:
        deadline = date(year, _IT_MONTHS[match.group(2).lower()], int(match.group(1)))
    notes = []
    if fee := _REG_FEE_RE.search(registration):
        notes.append(f"A non-refundable €{fee.group(1)} registration fee completes enrolment.")
    if "rimborso del 50%" in registration.lower():
        notes.append(
            "Cancelling before the programme starts refunds 50% of the amount paid, "
            "excluding the registration fee."
        )
    return Application(
        status=status,
        deadline=deadline,
        url=REGISTRATION,
        requirements=_requirements(registration),
        notes=" ".join(notes) or None,
    )


def _teachers(docenti_html: str) -> list[Teacher]:
    tree = HTMLParser(docenti_html)
    container = tree.css_first("div.elementor") or tree.body
    if container is None:
        return []
    teachers: list[Teacher] = []
    seen: set[str] = set()
    for heading in container.css("h2"):
        # The faculty page lists a contemporary duo under one "X e Y" heading.
        for name in re.split(r"\s+e\s+", parse.clean(heading.text())):
            name = name.strip()
            if not _looks_like_name(name) or name in seen:
                continue
            seen.add(name)
            role = "Artistic director" if name == "Dora Ciacca" else None
            teachers.append(Teacher(name=name, role=role))
    return teachers


def _looks_like_name(text: str) -> bool:
    words = text.split()
    return 2 <= len(words) <= 5 and all(word[:1].isupper() for word in words)


def _build_offerings(
    home: str, registration: str, docenti_html: str, today: date
) -> list[Offering]:
    start, end, year, raw = _dates(home)
    if year is None:
        # This single-purpose site always advertises a "Summer Camp YYYY" edition,
        # so a missing year marker means a degraded fetch (a challenge/partial
        # render returned 200), not a genuinely empty source. Raise rather than
        # return [] so run.py treats it as a failed attempt and KEEPS the prior
        # store — otherwise one bad fetch silently wipes the committed edition
        # (IDR-24 keeps past cycles) and trips the zero-offering audit.
        raise ValueError(
            "Bobbio home page lacks the 'Summer Camp YYYY' edition marker — "
            "likely a degraded fetch; refusing to emit an empty store."
        )
    genres = parse.match_genres(home, _GENRES)
    levels = [level for level, keys in _LEVELS if any(k in home.lower() for k in keys)]

    schedule = Schedule(season="summer", start=start, end=end, notes=raw)
    offering = Offering(
        id=f"bobbio-summer-ballet-intensive/{year}",
        source=Source(provider="bobbio-summer-ballet-intensive", url=HOME, scrapedAt=now_utc()),
        title=f"Bobbio Summer Ballet Intensive {year}",
        genres=genres,
        level=levels,
        organization=ORG,
        location=Location(city="Bobbio", country="IT"),
        schedule=schedule,
        teachers=_teachers(docenti_html),
        application=_application(registration, year),
    )
    return [offering]
