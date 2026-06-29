"""Professione Danza Pescara — Pescara, IT — its Summer Intensive School.

API FIRST: WordPress (`/wp-json/` 200), but the dated edition lives on a page
(`/summer-intensive-school-2026/`) whose **REST `content.rendered` holds only a
FooGallery shortcode** — the real text (week dates, faculty, fees) is rendered
server-side from **SiteOrigin page-builder panels** stored in postmeta. So we
fetch the rendered **HTML** and parse its text, not the REST body. (The sibling
`/summer-school-luglio-2026/` page is an image-only teaser — skipped.)

DISCOVERY: one Summer Intensive School edition split into **two tracks** with
distinct ages / curricula / fees — children (7–13) and youth (14–25) — so we
emit **one Offering per track**. Each track runs four weekly blocks; we keep one
`Session` per week and the per-week + four-week fees as `Price`s.

WHAT WE EXTRACT (verified live 2026-06-26):
  - DATES: per-week "DAL <d> <mese> AL <d> <mese>" lines (Italian month map),
    no year on the line → year read from the header "… Luglio 2026". Overall
    span = earliest week start … latest week end (children to 24 Jul, youth to
    31 Jul).
  - AGES: the track heading "DAGLI 7 AI 13 ANNI" / "DAI 14 AI 25".
  - GENRES: matched against the **curriculum sentence only** (not faculty bios):
    children "Danza Classica … Contemporaneo" → classical + contemporary; youth
    adds "Tecnica delle Punte" → + pointe.
  - PRICES: the per-track "Costi:" block — weekly tiers (with con/senza-stage
    note) + the four-week package. The à-la-carte external workshop per-lesson
    prices ("COSTI WORKSHOP PER GLI ESTERNI …") are add-ons for non-enrolled
    externals, not the intensive's fee — omitted.
  - TEACHERS: the ALLCAPS faculty names per track.

SCOPE CALL: faculty bios cram role + (sometimes several) external orgs +
discipline into one freeform Italian line ("Direttrice Professione Danza Pescara
e Balletto Di Pescara (Classico, Fisiotecnica)"), with the dash dropped in the
4th-week blocks — not cleanly splittable into structured affiliations, so
teachers are captured **names-only** rather than over-attributed (cf.
arteballetto). Application is open-enrollment (registration via the school's
MODULO ISCRIZIONE) with no audition material stated → requirements left unknown.

WHAT THIS SCRAPER EXERCISES: WP page whose body lives in SiteOrigin panels (HTML,
not REST content); one-org/two-track → two Offerings; per-week Sessions; Italian
date range with the year on a separate header line; multi-Price weekly tiers +
package; curriculum-scoped genre match; raise-on-degraded-fetch.
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
    Session,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.professionedanza.org"
PAGE = f"{BASE}/summer-intensive-school-2026/"

ORG = Organization(
    name="Professione Danza Pescara",
    slug="professione-danza-pescara",
    country="IT",
    city="Pescara",
)

_ITALIAN_MONTHS: dict[str, int] = {
    m: i
    for i, m in enumerate(
        [
            "gennaio",
            "febbraio",
            "marzo",
            "aprile",
            "maggio",
            "giugno",
            "luglio",
            "agosto",
            "settembre",
            "ottobre",
            "novembre",
            "dicembre",
        ],
        start=1,
    )
}
_MONTH_IT = parse.months_alt(_ITALIAN_MONTHS)

_YEAR = re.compile(r"(?:" + _MONTH_IT + r")\s+(20\d{2})", re.IGNORECASE)
_WEEK = re.compile(
    r"DAL\s+(\d{1,2})\s+(" + _MONTH_IT + r")\s+AL\s+(\d{1,2})\s+(" + _MONTH_IT + r")",
    re.IGNORECASE,
)
_AGE = re.compile(r"(?:DAGLI|DAI)\s+(\d{1,2})\s+AI\s+(\d{1,2})", re.IGNORECASE)
# A faculty name line: ALLCAPS (accents/apostrophe ok), 2–3 tokens.
_NAME = re.compile(r"^[A-ZÀ-ÝÄ-Ü'’ ]{4,}$")
_ROLE_LEAD = ("–", "-", "—", "direttrice", "docente", "danzatore", "contemporary",
              "international", "maitre", "maître")  # fmt: skip

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("danza classica", "classico")),
    ("pointe", ("punte", "punta")),
    ("contemporary", ("contemporaneo", "contemporanea")),
    ("character", ("carattere",)),
    ("repertoire", ("repertorio",)),
]

_APPLY_NOTE = (
    "Open-enrollment summer school; registration via the school's MODULO ISCRIZIONE form. "
    "Merit scholarships are awarded to selected students during the course."
)

# Each track: heading marker, id/title suffix, where its section ends.
_TRACKS = [
    ("PER BAMBINI", "bambini", "Bambini (7–13)"),
    ("PER RAGAZZI", "ragazzi", "Ragazzi e Ragazze (14–25)"),
]


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text)


def _flat_lines(html: str) -> list[str]:
    tree = HTMLParser(html)
    for node in tree.css("script, style, nav, header, footer, form"):
        node.decompose()
    body = tree.body.text(separator="\n") if tree.body else ""
    return [parse.clean(line) for line in body.split("\n") if parse.clean(line)]


def _build_offerings(html: str) -> list[Offering]:
    lines = _flat_lines(html)
    full = "\n".join(lines)
    ym = _YEAR.search(full)
    if not ym:
        raise ValueError("Professione Danza Pescara: no year in header (degraded fetch?)")
    year = int(ym.group(1))

    offerings: list[Offering] = []
    for i, (marker, suffix, label) in enumerate(_TRACKS):
        start_idx = full.find(marker)
        if start_idx < 0:
            raise ValueError(f"Professione Danza Pescara: track '{marker}' missing (degraded?)")
        # The section ends at the next track marker, else at the scholarship block.
        end_idx = len(full)
        for nxt_marker, _, _ in _TRACKS[i + 1 :]:
            j = full.find(nxt_marker, start_idx + 1)
            if j > 0:
                end_idx = j
                break
        else:
            b = full.find("BORSE DI STUDIO", start_idx)
            if b > 0:
                end_idx = b
        offerings.append(_build_offering(full[start_idx:end_idx], year, suffix, label))
    return offerings


def _build_offering(section: str, year: int, suffix: str, label: str) -> Offering:
    sessions = _sessions(section, year)
    if not sessions:
        raise ValueError(f"Professione Danza Pescara: no week dates for '{suffix}'")
    start = min(s.start for s in sessions if s.start)
    end = max(s.end for s in sessions if s.end)

    return Offering(
        id=f"professione-danza-pescara/summer-intensive-{year}-{suffix}",
        source=Source(provider="professione-danza-pescara", url=PAGE, scrapedAt=now_utc()),
        title=f"Summer Intensive School {year} — {label}",
        genres=_genres(section),
        ageRange=_age_range(section),
        organization=ORG,
        location=Location(venue="Professione Danza Pescara", city="Pescara", country="IT"),
        schedule=Schedule(
            season=str(year),
            start=start,
            end=end,
            timezone="Europe/Rome",
            sessions=sessions,
        ),
        teachers=_teachers(section),
        prices=_prices(section),
        application=Application(url=PAGE, notes=_APPLY_NOTE),
    )


def _genres(section: str) -> list[Genre]:
    # Match only the curriculum sentence (heading → first week), so faculty-bio
    # disciplines (e.g. "Repertorio Forsythe") can't leak a genre not taught.
    head = section.split("1°", 1)[0]
    return parse.match_genres(head, _GENRE_KEYWORDS, default=["classical"])


def _age_range(section: str) -> dict | None:
    m = _AGE.search(section)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _sessions(section: str, year: int) -> list[Session]:
    sessions: list[Session] = []
    for n, m in enumerate(_WEEK.finditer(section), start=1):
        start = date(year, _ITALIAN_MONTHS[m.group(2).lower()], int(m.group(1)))
        end = date(year, _ITALIAN_MONTHS[m.group(4).lower()], int(m.group(3)))
        sessions.append(Session(label=f"{n}ª settimana", start=start, end=end))
    return sessions


def _teachers(section: str) -> list[Teacher]:
    lines = section.split("\n")
    names: list[str] = []
    seen: set[str] = set()
    for idx, line in enumerate(lines):
        if not _NAME.match(line) or not (2 <= len(line.split()) <= 3):
            continue
        nxt = lines[idx + 1].lower() if idx + 1 < len(lines) else ""
        if not nxt.startswith(_ROLE_LEAD):
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(line.title())
    return [Teacher(name=n) for n in names]


# A fee line: "<label>: Euro <amount> (optional qualifier)". SiteOrigin can split
# the amount/qualifier onto their own lines, so we collapse whitespace and read
# label→amount→qualifier across it (label has the only colon; amounts have none).
_FEE = re.compile(r"([^:]+?):\s*Euro\s*([\d.,]+)\s*(?:\(([^)]*)\))?", re.IGNORECASE)


def _prices(section: str) -> list[Price]:
    block = section.split("Costi:", 1)
    if len(block) < 2:
        return []
    body = block[1]
    for stop in ("I costi includono", "COSTI WORKSHOP", "BORSE DI STUDIO"):
        body = body.split(stop, 1)[0]
    body = parse.clean(body)

    prices: list[Price] = []
    for m in _FEE.finditer(body):
        amount = parse.parse_amount(m.group(2))
        if amount is None:
            continue
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=parse.clean(m.group(1)),
                includes=["tuition"],
                notes=parse.clean(m.group(3)) if m.group(3) else None,
            )
        )
    return prices
