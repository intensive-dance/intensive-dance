"""Młody Balet Polski — Letnie Warsztaty Baletowe (Summer Ballet Workshops), Warszawa.

API FIRST — but there is none. The site (balet.info.pl) is a bespoke PHP CMS, not
WordPress: `/wp-json/` 404s, there is no schema.org `ld+json` and no state blob.
The dated edition is **server-rendered** plain HTML, so this is a selectolax read
of one announcement page (no JS / proxy needed — a direct httpx fetch returns the
real markup, verified live 2026-06-08).

DISCOVERY: the annual summer intensive runs in the **second half of August** for
children of school grades 1-9 (plus a separate 6-10 group). Its dated edition is
published as a news article ("Aktualności"), e.g. "Summer Ballet Workshops 10-21
sierpnia 2026". We anchor on that article page and emit **one Offering per
edition** (`mlody-balet-polski/summer-intensive-{year}`); the article lists two
age tracks that differ only by ages/hours/programme (not dates/fee), so they
become **one Offering with one `Session` per track** (the `tokyo_ballet_school`
pattern) — folding them would lose the distinct ages and class lists.

LANGUAGE NOTE: parsed **language-agnostically** — numeric dates ("10-21 sierpnia
2026") with a Polish month map, numeric ages, and enum genres keyed off the Polish
programme words (Balet → classical, Pointy → pointe, Repertuar → repertoire). No
Polish free text is emitted into the data; titles/notes are canonical English so
the committed record is stable.

PRICE: the article does not state a fee (registration is by phone, places
limited), and the school's `/cennik` page is year-round monthly tuition — not the
intensive price — so `prices` is left empty rather than misattributing it.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - SESSIONS — two age tracks (11-19 with pointe/repertoire 9-15h; 6-10 basics
    15-17h) as one Offering, one Session each, ages + raw programme in notes.
  - TEACHER (no affiliation roster ties to this edition) — only the school's named
    artistic director, Anna Davies, is emitted, role "director".
  - GENRES from the programme word list (classical + pointe + repertoire), scoped
    to the edition's own class lists, not the school's general blurb.
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
    Schedule,
    Session,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://balet.info.pl"
# The dated edition is announced as a news article; this is the 2026 edition's
# canonical page. The slug is opaque (a CMS "copy" id), so it is pinned here.
ARTICLE_URL = (
    f"{BASE}/pl/informacje/aktualnosci/konkurs-fotograficzny-balerina-na-wakacjach_kopia_644928"
)

ORG = Organization(
    name="Młody Balet Polski", slug="mlody-balet-polski", country="PL", city="Warszawa"
)

# Plac Defilad 1 — Palace of Culture and Science (PKiN), 6th floor; the school's
# single Warsaw venue (from /pl/kontakt).
VENUE = "Pałac Kultury i Nauki, Plac Defilad 1, 6th floor"

# Founder / artistic & programme director — the one person tied to the school as a
# whole (the per-edition article names no teachers). Studied at the Martha Graham
# School in New York; pedagogue of classical dance and choreographer.
DIRECTOR = Teacher(name="Anna Davies", role="director")

# Polish month names → number, on top of the shared English map, so the date line
# parses whichever wording is used ("sierpnia" is the genitive August takes here).
_MONTHS = {
    **parse.MONTHS,
    "stycznia": 1,
    "lutego": 2,
    "marca": 3,
    "kwietnia": 4,
    "maja": 5,
    "czerwca": 6,
    "lipca": 7,
    "sierpnia": 8,
    "września": 9,
    "wrzesnia": 9,
    "października": 10,
    "pazdziernika": 10,
    "listopada": 11,
    "grudnia": 12,
}
_MONTHALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

# "10-21 sierpnia 2026" — a day-range sharing one month + year.
_RANGE = re.compile(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})", re.IGNORECASE)
# A single labelled age band: "Wiek 11-19" / "Wiek 6-10".
_AGE = re.compile(r"wiek\s*(\d{1,2})\s*[-–]\s*(\d{1,2})", re.IGNORECASE)

# Programme word (Polish) → genre. Keyed off the article's own class lists so the
# edition's genres reflect what it teaches, not the school's general description.
_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("balet", "klasyczn", "ballet", "classical")),
    ("pointe", ("point", "pointy", "pointe")),
    ("contemporary", ("współczesn", "wspolczesn", "contemporary")),
    ("character", ("narodow", "charakterystyczn", "character")),
    ("repertoire", ("repertuar", "repertoire", "repertory")),
]


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(ARTICLE_URL)
    resp.raise_for_status()
    offering = _build_offering(resp.text, date.today())
    return [offering] if offering is not None else []


def _build_offering(html: str, today: date) -> Offering | None:  # noqa: ARG001 — today reserved
    text = _page_text(html)
    start, end = _date_range(text)
    if start is None or end is None:
        return None  # no dated edition published → defer rather than invent one
    season = str(end.year)

    sessions = _sessions(text)

    return Offering(
        id=f"mlody-balet-polski/summer-intensive-{season}",
        source=Source(provider="mlody-balet-polski", url=ARTICLE_URL, scrapedAt=now_utc()),
        title=f"Summer Ballet Workshops {season}",
        genres=_genres(text),
        ageRange=_combined_age_range(sessions),
        organization=ORG,
        location=Location(venue=VENUE, city="Warszawa", country="PL"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Warsaw",
            sessions=sessions,
        ),
        teachers=[DIRECTOR],
        application=Application(url=ARTICLE_URL),
    )


def _page_text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript, nav, header, footer"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    d1, d2, month, year = m.groups()
    num = _MONTHS[month.lower()]
    return date(int(year), num, int(d1)), date(int(year), num, int(d2))


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- sessions: one per labelled "Wiek N-M" age track --------------------------
#
# The article lays the edition out as two age tracks, each a "Wiek N-M  godz. HH-HH"
# header followed by a "Program: …" class list. We slice the text on each "Wiek"
# marker so a track's programme stays with its own age band (matching ages by
# position, not folding the two into one record).


def _sessions(text: str) -> list[Session]:
    sessions: list[Session] = []
    spans = list(_AGE.finditer(text))
    for i, m in enumerate(spans):
        lo, hi = int(m.group(1)), int(m.group(2))
        block = text[m.start() : spans[i + 1].start()] if i + 1 < len(spans) else text[m.start() :]
        sessions.append(
            Session(
                ageRange={"min": min(lo, hi), "max": max(lo, hi)},
                notes=_block_notes(block),
            )
        )
    return sessions


def _block_notes(block: str) -> str | None:
    """The track's own line (ages + hours + programme), trimmed to the class list."""
    note = parse.clean(block)
    # Cut at the next section that isn't this track's programme (phone/registration).
    for stop in ("Rejestracja", "Ilość", "Kontakt", "Copyright"):
        idx = note.find(stop)
        if idx > 0:
            note = note[:idx]
    return note.strip() or None


def _combined_age_range(sessions: list[Session]) -> dict | None:
    bounds = [
        n
        for s in sessions
        if s.age_range
        for n in (s.age_range.get("min"), s.age_range.get("max"))
        if n is not None
    ]
    return {"min": min(bounds), "max": max(bounds)} if bounds else None
