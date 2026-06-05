"""Accademia Teatro alla Scala (La Scala Academy, Milan, IT) — its summer stages.

API FIRST: none usable. The Academy is **not** WordPress (`/wp-json/` → 204) — it
runs a custom CMS with no JSON-LD, feed, or state blob. Each programme lives on a
tidy, fully server-rendered page (the text is in the static HTML, no JS), so this
is an HTML scrape of two known programme URLs. The site root 301-redirects to
`http` on `www`; `make_client`/`follow_redirects` lands us back on the real page.

DISCOVERY: the Danza department lists two in-scope summer programmes (the rest of
the catalogue is long-term triennio/biennio/perfezionamento, out of scope). We
emit **one Offering per programme** — the professional/semi-professional "Stage
estivi di danza" and the children's pre-academic "Stage di propedeutica alla
danza". Each programme runs several one-week sessions, kept as
`schedule.sessions`, season-keyed from the parsed year.

The page is in Italian: month names are this scraper's own map (the German-month
pattern in `john_cranko_school`), and the genres key off the curriculum list
("Programma"), not loose prose, so we don't leak a genre the stage doesn't teach.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-05):
  - SESSIONS: multiple "<d> <month> – <d> <month> <year>" weekly blocks per
    programme (the summer stage has two; propedeutica four).
  - LEVEL: the summer stage states "livello professionale o semi-professionale"
    → `professional` + `pre-professional`; propedeutica is for children with no
    level stated → empty.
  - AGES: grade-group prose ("fino ai 23 anni non compiuti"; "bambini tra i 7 e
    gli 11 anni") → numeric `age_range`.
  - GENRES: classical-academic + modern/contemporary + repertoire/pointe for the
    summer stage; classical-only for propedeutica.
  - PRICES in EUR (€820/week incl. one canteen meal/day; €390/session) — the
    summer-stage fee exercises the `meals` include.
  - DEADLINE: "Entro il 7 giugno 2026" → `application.deadline`; the apply URL is
    the login-gated registration portal (stored, not followed).
  - REQUIREMENTS: registration only, no audition → `NoneReq`.
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
    NoneReq,
    Offering,
    Organization,
    Price,
    PriceInclude,
    Schedule,
    Session,
    Source,
    now_utc,
)

BASE = "https://www.accademialascala.it"
SUMMER_STAGE = f"{BASE}/danza/stage-estivi-di-danza"
PROPEDEUTICA = f"{BASE}/danza/stage-di-propedeutica-alla-danza"
APPLY_URL = "https://iscrizioni.accademialascala.it"

ORG = Organization(
    name="Accademia Teatro alla Scala",
    slug="accademia-teatro-alla-scala",
    country="IT",
    city="Milan",
)

# The Danza department's own venue (the central Academy is a different address).
VENUE = "Via Campo Lodigiano, 2"

# Italian month names — local to this scraper, like the German map in
# `john_cranko_school`; only the regex-building stays shared.
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


def scrape(client: httpx.Client) -> list[Offering]:
    offerings: list[Offering] = []
    for builder, url in ((_build_summer_stage, SUMMER_STAGE), (_build_propedeutica, PROPEDEUTICA)):
        resp = client.get(url, follow_redirects=True)
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        offering = builder(_text(resp.text), url)
        if offering is not None:
            offerings.append(offering)
    return offerings


def _text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _build_summer_stage(text: str, url: str) -> Offering | None:
    sessions = _sessions(text)
    if not sessions:
        return None
    start = min(s.start for s in sessions if s.start)
    end = max(s.end for s in sessions if s.end)
    season = str(end.year)

    return Offering(
        id=f"accademia-teatro-alla-scala/stage-estivi-di-danza-{season}",
        source=Source(provider="accademia-teatro-alla-scala", url=url, scrapedAt=now_utc()),
        title=f"Stage estivi di danza {season}",
        genres=_genres(text),
        level=_levels(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue=VENUE, city="Milan", country="IT"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Rome",
            sessions=sessions,
        ),
        prices=_prices(text),
        application=Application(
            deadline=_deadline(text),
            url=APPLY_URL,
            requirements=[NoneReq()],
            notes=_deadline_note(text),
        ),
    )


def _build_propedeutica(text: str, url: str) -> Offering | None:
    sessions = _sessions(text)
    if not sessions:
        return None
    start = min(s.start for s in sessions if s.start)
    end = max(s.end for s in sessions if s.end)
    season = str(end.year)

    return Offering(
        id=f"accademia-teatro-alla-scala/stage-di-propedeutica-alla-danza-{season}",
        source=Source(provider="accademia-teatro-alla-scala", url=url, scrapedAt=now_utc()),
        title=f"Stage di propedeutica alla danza {season}",
        # Pre-academic classical preparation only — no contemporary class listed.
        genres=["classical"],
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue=VENUE, city="Milan", country="IT"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Rome",
            sessions=sessions,
        ),
        prices=_prices(text),
        application=Application(
            deadline=_deadline(text),
            url=APPLY_URL,
            requirements=[NoneReq()],
            notes=_deadline_note(text),
        ),
    )


# --- sessions: one-week blocks "dal <d> <month?> al <d> <month> <year?>" -------
#
# Two elisions complicate the source: the start day may drop its month when both
# fall in the same month ("dal 6 al 10 luglio 2026"), and the year may be stated
# only once for a run of blocks joined by "e" ("dal 29 giugno al 3 luglio e dal 6
# al 10 luglio 2026" — the first block has no trailing year). So the year is
# optional per match and back-filled from the next dated block; likewise the
# end-month back-fills a missing start-month. The opener is "dal" or elided
# "dall'" (dall'8, dall'11).
_SESSION = re.compile(
    r"dal(?:l['’])?\s*(\d{1,2})\s*(?:("
    + _MONTHALT
    + r")\s+)?al(?:l['’])?\s*(\d{1,2})\s+("
    + _MONTHALT
    + r")(?:\s+(\d{4}))?",
    re.IGNORECASE,
)


def _sessions(text: str) -> list[Session]:
    raw = [(int(d1), m1, int(d2), m2, year) for d1, m1, d2, m2, year in _SESSION.findall(text)]
    # Back-fill years stated only on a later block in the same "e"-joined run.
    years = [int(y) if y else None for *_, y in raw]
    last = next((y for y in reversed(years) if y is not None), None)
    for i in range(len(years) - 1, -1, -1):
        if years[i] is not None:
            last = years[i]
        else:
            years[i] = last

    seen: set[tuple[date, date]] = set()
    out: list[Session] = []
    for (d1, m1, d2, m2, _), year in zip(raw, years):
        if year is None:
            continue
        end_month = _MONTHS[m2.lower()]
        start_month = _MONTHS[m1.lower()] if m1 else end_month
        start = date(year, start_month, d1)
        end = date(year, end_month, d2)
        if (start, end) in seen:
            continue
        seen.add((start, end))
        head = f"{d1} {m1}" if m1 else str(d1)
        out.append(Session(start=start, end=end, notes=f"{head}–{d2} {m2} {year}"))
    return out


# --- ages ---------------------------------------------------------------------
#
# Two source shapes: the summer stage's upper bound ("fino ai 23 anni") and
# propedeutica's explicit band ("tra i 7 e gli 11 anni").
_AGE_BAND = re.compile(r"tra\s+i\s+(\d{1,2})\s+e\s+gli\s+(\d{1,2})\s+anni", re.IGNORECASE)
_AGE_MAX = re.compile(r"fino\s+ai\s+(\d{1,2})\s+anni", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    band = _AGE_BAND.search(text)
    if band:
        return {"min": int(band.group(1)), "max": int(band.group(2))}
    upper = _AGE_MAX.search(text)
    if upper:
        return {"max": int(upper.group(1))}  # open-ended below
    return None


# --- level --------------------------------------------------------------------


def _levels(text: str) -> list[Level]:
    low = text.lower()
    levels: list[Level] = []
    if "professional" in low:  # "livello professionale o semi-professionale"
        levels.append("professional")
    if "semi-professional" in low or "semi professional" in low or "semiprofessional" in low:
        levels.append("pre-professional")
    return levels


# --- genres: key off the "Programma" curriculum list, not loose prose ---------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classico-accademica", "classica", "classico", "balletto")),
    ("contemporary", ("moderno-contemporanea", "contemporane", "moderno")),
    ("repertoire", ("repertorio",)),
    ("pointe", ("punta", "punte")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- prices -------------------------------------------------------------------
#
# "€ 820 per ciascuna settimana" / "€ 390 a sessione". The summer-stage fee
# states it includes one canteen meal per teaching day.
_PRICE = re.compile(r"€\s*(\d[\d.]*)\s+(?:per\s+ciascuna\s+settimana|a\s+sessione)", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    m = _PRICE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    includes: list[PriceInclude] = ["tuition"]
    if "pasto in mensa" in text.lower():
        includes.append("meals")
    return [Price(amount=amount, currency="EUR", label="Per week", includes=includes)]


# --- application deadline -----------------------------------------------------
#
# "Iscrizioni 2026 Entro il 7 giugno 2026 (...)". The summer stage states a
# single deadline; propedeutica states two (per-session) that don't apply to the
# whole programme — so we only set `deadline` when the page names exactly one,
# and otherwise leave it null with the full prose kept in the note.
_DEADLINE = re.compile(r"Entro\s+il\s+(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})", re.IGNORECASE)


def _deadline(text: str) -> date | None:
    found = _DEADLINE.findall(text)
    if len(found) != 1:
        return None
    d, mon, y = found[0]
    return date(int(y), _MONTHS[mon.lower()], int(d))


def _deadline_note(text: str) -> str | None:
    m = re.search(r"Iscrizioni\s+\d{4}\s+(Entro.+?)(?:Scarica|Scopri|Richiedi)", text)
    return parse.clean(m.group(1)) if m else None
