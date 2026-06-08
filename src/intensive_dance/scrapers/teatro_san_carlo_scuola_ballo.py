"""Scuola di Ballo del Teatro di San Carlo (Naples, IT) — its summer workshop.

API FIRST: none usable. The Teatro di San Carlo runs WordPress, but `/wp-json/`
and every HTML page sit behind an aggressive bot-protection challenge ("Security
check required") that the fetch proxy's stealth/FlareSolverr tiers clear only
intermittently — not a deterministic source. The one stable artifact is the
workshop's **bando PDF** under `/files/.../scuola_di_ballo/`, which the proxy's
plain `auto=1` tier fetches reliably (the challenge gates HTML, not the PDF).
So this is a PDF scrape (pypdf), parsed from the bando's structured Italian text.

DISCOVERY: the school itself is a full-time, multi-year vocational diploma course
(corso triennale + corsi propedeutici, admission by audizione/bando) — out of
scope. But in summer 2024 it launched **"Passi d'Estate in Teatro"**, a public,
dated, short-term intensive workshop open to students "da tutte le scuole
Italiane ed Estere" regardless of level — exactly in scope. One dated edition →
**one Offering** (1° edizione, 10–13 July 2024). No 2025/2026 edition was
published at scrape time; per AGENTS.md (IDR-24) the ended 2024 edition is kept,
not dropped — "past" is derived consumer-side from `schedule.end`, never stored.

The "Iniziative, Masterclass e Stage" educational page is unrelated — it lists
university *tirocini* (work placements) at the theatre, not dance courses.

LANGUAGE NOTE: parsed language-agnostically from the Italian bando — numeric
dates (Italian month map), enum genres keyed off the curriculum list, numeric
ages/prices (EUR), faculty names verbatim. Only canonical-English free text is
emitted (level labels), never the page wording.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - Single dated edition from a bando PDF → one Offering (kept though ended).
  - Italian single-month date range "Dal 10 Luglio al 13 Luglio 2024".
  - Open-topped ageRange {min: 9} (the Avanzato band is "Over 16", no max);
    three level bands → beginner/intermediate/advanced.
  - GENRES off the curriculum list: classical + pointe + repertoire +
    contemporary (Fisiotecnica/Laboratorio are not register genres).
  - Multiple EUR Prices (per-level packages), the headline tuition each.
  - DEADLINE "entro e non oltre il 1° luglio 2024"; requirements = enrolment
    only, no audition/photos/video selection (open to all levels) → NoneReq.
  - TEACHERS: the 4-strong faculty incl. the school director (Stéphane Fournial).
"""

from __future__ import annotations

import io
import re
from datetime import date

import httpx
from pypdf import PdfReader

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
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.teatrosancarlo.it"
# The bando lives in the school's "amministrazione trasparente" file store; the
# proxy's plain tier fetches it reliably while the HTML pages stay challenged.
BANDO_PDF = (
    f"{BASE}/files/amministrazione_trasparente/aggiornamenti_2024/"
    "scuola_di_ballo/Passi_d_Estate.pdf"
)
# Public-facing page for the edition (kept as the human-readable apply/info URL).
INFO_URL = f"{BASE}/news/workshop-passi-destate-2024/"

ORG = Organization(
    name="Scuola di Ballo del Teatro di San Carlo",
    slug="teatro-san-carlo-scuola-ballo",
    country="IT",
    city="Naples",
)

VENUE = "Teatro di San Carlo, via San Carlo 100"

# Italian month names (numeric dates make the parse language-agnostic).
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
    resp = client.get(BANDO_PDF)
    resp.raise_for_status()
    return _build_offerings(_pdf_text(resp.content))


def _pdf_text(data: bytes) -> str:
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    return parse.clean(text)


def _build_offerings(text: str) -> list[Offering]:
    start, end = _date_range(text)
    anchor = start or end
    if anchor is None:
        return []  # no dated edition parseable
    season = str(anchor.year)

    return [
        Offering(
            id=f"teatro-san-carlo-scuola-ballo/passi-d-estate-{season}",
            source=Source(
                provider="teatro-san-carlo-scuola-ballo", url=INFO_URL, scrapedAt=now_utc()
            ),
            title=f"Passi d'Estate in Teatro {season}",
            genres=_genres(text),
            level=_levels(text),
            ageRange=_age_range(text),
            organization=ORG,
            location=Location(venue=VENUE, city="Naples", country="IT"),
            schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Rome"),
            teachers=_teachers(text),
            prices=_prices(text),
            application=Application(
                deadline=_deadline(text),
                url=INFO_URL,
                # Open to all levels with no audition/photo/video selection — the
                # only attachments are a payment receipt and a sports-fitness
                # medical certificate (administrative), so admission requires
                # nothing of the dancer: explicitly NoneReq, not unknown ([]).
                requirements=[NoneReq()],
            ),
        )
    ]


# --- dates: "Dal 10 Luglio al 13 Luglio 2024" (single month, trailing year) ----

_RANGE = re.compile(
    r"\b(\d{1,2})\s+(" + _MONTHALT + r")\s+al\s+(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    d1, mon1, d2, mon2, year = m.groups()
    y = int(year)
    return date(y, _MONTHS[mon1.lower()], int(d1)), date(y, _MONTHS[mon2.lower()], int(d2))


# --- ages: three level bands "9/12", "13/15", "Over 16" -----------------------
#
# The bando states "Principianti: 9/12 anni - Intermedio: 13/15 anni - Avanzato:
# Over 16". The closed bands set both bounds; the "Over 16" band is open-topped,
# so the overall max is left null (no finite cap can be inferred from "Over").

_AGE_BAND = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})\s*anni")
_AGE_OVER = re.compile(r"\bOver\s+(\d{1,2})\b", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    bands = [(int(a), int(b)) for a, b in _AGE_BAND.findall(text) if 5 <= int(a) <= int(b) <= 30]
    overs = [int(m.group(1)) for m in _AGE_OVER.finditer(text) if 5 <= int(m.group(1)) <= 30]
    if not bands and not overs:
        return None
    mins = [a for a, _ in bands] + overs
    if overs:  # an open-ended top band → null max
        return {"min": min(mins)}
    return {"min": min(mins), "max": max(b for _, b in bands)}


# --- levels: the three Italian band labels ------------------------------------

_LEVEL_KEYWORDS: list[tuple[Level, tuple[str, ...]]] = [
    ("beginner", ("principiant",)),
    ("intermediate", ("intermedio",)),
    ("advanced", ("avanzato",)),
]


def _levels(text: str) -> list[Level]:
    return parse.match_genres(text, _LEVEL_KEYWORDS, default=[])


# --- genres: keyed off the curriculum list, not loose prose -------------------
#
# "Danza Classica e Tecnica delle Punte, Repertorio, Fisiotecnica, Danza
# Contemporanea e Laboratorio coreografico." Fisiotecnica/Laboratorio are not
# register genres, so they map to nothing.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("danza classica", "classica", "classico")),
    ("pointe", ("punte", "punta")),
    ("repertoire", ("repertorio",)),
    ("contemporary", ("contemporane",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- prices: the per-package EUR rates ----------------------------------------
#
# The "COSTI" section lists the student lesson packages, each line ending
# "(...): NNN,NN euro" under a level heading ("Livello Principianti" / "Livello
# Intermedio/Avanzato – pacchetto …"). The trailing "OPEN CARD – DOCENTI O
# UDITORI" block (90/110 €) is for accompanying teachers/auditors, not students,
# so we cut the window at it. The fee includes tuition only.

# Each package's rate sits at the end of its description: "(... 8 lezioni): 250,00
# euro" or "Totale di 12 lezioni: 490,00 euro". We split the COSTI window on each
# rate and label every price with the lesson-count clause just before its colon
# (the parenthetical, else the bare phrase), so the two distinct 250 € packages
# stay apart.
_PRICE = re.compile(r"([^:]*?):\s*(\d{1,3}(?:[.,]\d{2})?)\s*euro", re.IGNORECASE)
_DETAIL = re.compile(r"\(([^()]+)\)\s*$")  # trailing "(...)" descriptor


def _prices(text: str) -> list[Price]:
    # Restrict to the student-package window: from "COSTI" up to the auditor
    # "OPEN CARD" block (everything after is teacher/auditor passes).
    start = re.search(r"\bCOSTI\b", text, re.IGNORECASE)
    if start is None:
        return []
    window = text[start.end() :]
    cut = re.search(r"OPEN\s+CARD", window, re.IGNORECASE)
    if cut is not None:
        window = window[: cut.start()]

    prices: list[Price] = []
    seen: set[tuple[float, str]] = set()
    for clause_raw, amount_raw in _PRICE.findall(window):
        amount = parse.parse_amount(amount_raw)
        if amount is None or amount < 50:
            continue
        clause = parse.clean(clause_raw)
        detail = _DETAIL.search(clause)
        if detail:  # rate sits right after a "(...)" lesson-count descriptor
            label = parse.clean(detail.group(1))
        else:  # e.g. "... 12-13 luglio (...) Totale di 12 lezioni" → trailing phrase
            label = parse.clean(clause.rsplit(")", 1)[-1]) or clause
        key = (amount, label.lower())
        if key in seen:
            continue
        seen.add(key)
        prices.append(
            Price(amount=amount, currency="EUR", label=label or None, includes=["tuition"])
        )
    return prices


# --- application deadline: "entro e non oltre il 1° luglio 2024" ---------------

_DEADLINE = re.compile(
    r"entro(?:\s+e\s+non\s+oltre)?\s+il\s+(\d{1,2})°?\s+(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _deadline(text: str) -> date | None:
    m = _DEADLINE.search(text)
    if not m:
        return None
    day, month, year = m.groups()
    return date(int(year), _MONTHS[month.lower()], int(day))


# --- teachers: the named faculty roster (incl. the school director) -----------
#
# The bando's "DOCENTI" section names each teacher followed by their role in a
# parenthetical, e.g. "Stéphane Fournial (Direttore Scuola di Ballo Teatro di San
# Carlo) Docente danza classica e repertorio ...". We take the known roster
# (anchored on each name) so a stray capitalised word elsewhere isn't mistaken
# for a teacher; the director carries his title.

_FACULTY: list[tuple[str, str | None]] = [
    ("Stéphane Fournial", "Direttore Scuola di Ballo"),
    ("Rossella Lo Sapio", "Docente danza classica"),
    ("Assunta Anatrella", "Docente danza classica"),
    ("Emma Cianchi", "Docente danza contemporanea"),
]


def _teachers(text: str) -> list[Teacher]:
    return [Teacher(name=name, role=role) for name, role in _FACULTY if name in text]
