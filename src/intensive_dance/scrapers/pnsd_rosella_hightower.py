"""PNSD Rosella Hightower (Cannes, FR) — its summer "stages" intensives.

API FIRST: none usable. The school's site has no public content API, but the
`/stages` hub is server-rendered (the full text — dated editions and per-edition
faculty — is in the static HTML), so this is a one-page scrape with no JS.

DISCOVERY: the long-term offering is the DNSP cursus / EAT preparation, which is
out of scope. The short-term student offering lives on `/stages`: the school runs
"stages" in spring and summer ("au printemps et en été"). The summer block
("STAGES - ETE <year>") lists four separately dated one-week editions ("STAGE 1
… STAGE 4"), each with its own dates and faculty roster. We emit **one Offering
per dated summer edition** (id year+stage-keyed). The spring 2027 and children's
blocks are "dates à venir" (no dates) and yield nothing.

FRENCH SOURCE: we keep the source language faithfully (no inline translation —
AGENTS.md). Dates are parsed language-agnostically with a local French month map
("Juin"…"Août"); a leading weekday word ("Samedi", "Mercredi") may precede either
bound and the start day may omit its month when it shares the end's (STAGE 2:
"du Mercredi 8 au Mardi 14 Juillet"). Faculty names are kept verbatim.

CITY: the stages run at the school's **Mougins** campus ("140 allée Rosella
Hightower 06250 MOUGINS", per the registration contract + site JSON-LD). The
school's informal shorthand is "Cannes-Mougins" but the postal commune is Mougins
(06250), not Cannes; both organization.city and location.city are set to "Mougins".

WHAT THE PAGE GIVES US (verified live 2026-06-07):
  - DATES: "du <weekday?> <d> <Month?> au <weekday?> <d> <Month> <year>" per stage.
  - AGES: "Stages à partir de 10 ans" — open-ended upper bound, so min only.
  - GENRES: classical + contemporary per edition (the shared curriculum also lists
    pointe and classical/contemporary repertoire). Jazz is out of scope (no Jazz
    genre in the register) and dropped; every edition still teaches ballet.
  - FACULTY: a per-edition roster split by discipline (CLASSIQUE / CONTEMPORAIN /
    JAZZ). We keep the classical + contemporary teachers (jazz-only names dropped).
  - PRICES: nothing is priced inline; the per-stage fee grid lives in the summer
    registration contract PDF (linked as "Formulaire d'inscription"). We fetch and
    read it (pypdf), emitting the public "tarif normal" tuition per stage (STAGE
    N°1 6-day vs STAGE N°2-3-4 7-day) with the under-13 rate in the note, plus the
    obligatory annual membership. Fail-open: a PDF fetch/parse failure leaves
    prices empty rather than erroring. The multi-stage forfait discounts and the
    accommodation/meal grids are not folded in (cross-offering / optional tiers).
  - ACCOMMODATION / "portes ouvertes": noted on the schedule, not priced.
"""

from __future__ import annotations

import io
import re
from datetime import date

import httpx
from pypdf import PdfReader
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
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.pnsd.fr"
PAGE = f"{BASE}/stages"

ORG = Organization(
    name="PNSD Rosella Hightower",
    slug="pnsd-rosella-hightower",
    country="FR",
    city="Mougins",
)

# French month names → number, kept local like the German map in john_cranko_school
# (the regex-building helper `parse.months_alt` and date math are shared).
_MONTHS = {
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
}
_MONTHALT = parse.months_alt(_MONTHS)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text, _fetch_contract_text(client, resp.text))


def _build_offerings(html: str, contract_text: str = "") -> list[Offering]:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    summer = _summer_block(text)
    if not summer:
        return []

    curriculum = _curriculum(text)
    fees = _stage_fees(contract_text)
    membership = _membership(contract_text)
    offerings: list[Offering] = []
    for label, body in _stages(summer):
        offering = _build_offering(label, body, curriculum, fees, membership)
        if offering is not None:
            offerings.append(offering)
    return offerings


# --- prices: read off the summer registration contract PDF --------------------
#
# The /stages page prices nothing inline; the per-stage fee grid lives in the
# "Formulaire d'inscription" contract PDF (`…contrat-ete<year>.pdf`). We fetch and
# read it, mapping STAGE N°1 (6-day) and STAGE N°2-3-4 (7-day) to their offerings.
# Fail-open: any fetch/parse failure just leaves prices empty (never crashes).


def _fetch_contract_text(client: httpx.Client, html: str) -> str:
    tree = HTMLParser(html)
    href = next(
        (
            a.attributes.get("href") or ""
            for a in tree.css("a[href]")
            if "contrat-ete" in (a.attributes.get("href") or "").lower()
        ),
        "",
    )
    if not href:
        return ""
    url = href if href.startswith("http") else f"{BASE}{href}"
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return _pdf_text(resp.content)
    except Exception:
        return ""


def _pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


# Euro amounts in the contract read top-down per fee block as the rate rows
# (tarif normal, moins de 13 ans, élève PNSD …); we keep the first two — the
# public rate and the under-13 rate. Amounts are integers; digits-only avoids a
# "date+amount" run (e.g. "2026 35") bridging across a space into one number.
_EURO = re.compile(r"(\d+)\s*€")
# The annual membership sits on a dated line; skip past the dates to its amount.
_MEMBERSHIP = re.compile(r"adh[éè]sion annuelle obligatoire[^€]*?(\d+)\s*€", re.IGNORECASE)


def _euros(segment: str) -> list[float]:
    return [float(m) for m in _EURO.findall(segment)]


def _stage_fees(contract_text: str) -> dict[str, tuple[float, float | None]]:
    """Per-block (tarif normal, moins de 13 ans), keyed '1' and '234'.

    STAGE N°1 (6-day) is priced on its own; STAGE N°2-3-4 (7-day) share a grid
    whose first column ("Un stage") is a single edition's fee.
    """
    fees: dict[str, tuple[float, float | None]] = {}
    for key, start, end in (
        ("1", "STAGE N°1", "STAGE N°2"),
        ("234", "STAGE N°2", "Cours au ticket"),
    ):
        i = contract_text.find(start)
        if i < 0:
            continue
        j = contract_text.find(end, i + len(start))
        amounts = _euros(contract_text[i : j if j > i else len(contract_text)])
        if amounts:
            fees[key] = (amounts[0], amounts[1] if len(amounts) > 1 else None)
    return fees


def _membership(contract_text: str) -> float | None:
    m = _MEMBERSHIP.search(contract_text)
    return float(m.group(1)) if m else None


# --- segmentation -------------------------------------------------------------

# The summer editions sit under "STAGES - ETE <year>" and end where the next
# heading (spring / children's stages) begins. Keep the heading order faithful.
_SUMMER = re.compile(
    r"STAGES?\s*[-–]\s*ETE\b.*?(?=STAGES?\s*[-–]\s*PRINTEMPS|STAGES?\s+ENFANTS|$)",
    re.IGNORECASE,
)
# Curriculum disciplines listed once above the editions ("Classique/Contemporain/
# Jazz Pointes … Répertoire classique et contemporain …").
_CURRICULUM = re.compile(
    r"Possibilité d'hébergement[^.]*\.\s*(.*?)\s*STAGES?\s*[-–]\s*ETE",
    re.IGNORECASE,
)
# "STAGE 1 : <body up to the next STAGE n or end>".
_STAGE = re.compile(
    r"STAGE\s+(\d+)\s*:\s*(.*?)(?=STAGE\s+\d+\s*:|Formulaire|Planning type|$)",
    re.IGNORECASE,
)


def _summer_block(text: str) -> str:
    m = _SUMMER.search(text)
    return m.group(0) if m else ""


def _curriculum(text: str) -> str:
    m = _CURRICULUM.search(text)
    return parse.clean(m.group(1)) if m else ""


def _stages(summer: str) -> list[tuple[str, str]]:
    return [(f"Stage {m.group(1)}", parse.clean(m.group(2))) for m in _STAGE.finditer(summer)]


# --- one edition --------------------------------------------------------------


def _build_offering(
    label: str,
    body: str,
    curriculum: str,
    fees: dict[str, tuple[float, float | None]],
    membership: float | None,
) -> Offering | None:
    start, end = _date_range(body)
    anchor = end or start
    if anchor is None:
        return None  # an edition with "dates à venir" — nothing dated to emit
    season = str(anchor.year)
    stage_no = label.split()[-1]

    return Offering(
        id=f"pnsd-rosella-hightower/stage-ete-{season}-{stage_no}",
        source=Source(provider="pnsd-rosella-hightower", url=PAGE, scrapedAt=now_utc()),
        title=f"Stage d'été {season} — {label}",
        genres=_genres(f"{body} {curriculum}"),
        ageRange=_age_range(curriculum),
        organization=ORG,
        location=Location(city="Mougins", country="FR"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Paris",
            notes=_schedule_note(body),
        ),
        teachers=_teachers(body),
        prices=_prices(stage_no, fees, membership),
        application=Application(url=PAGE, notes=_APPLY_NOTE),
    )


# STAGE N°1 is the 6-day edition (the first); STAGE N°2-3-4 share the 7-day grid.
def _prices(
    stage_no: str, fees: dict[str, tuple[float, float | None]], membership: float | None
) -> list[Price]:
    prices: list[Price] = []
    fee = fees.get("1" if stage_no == "1" else "234")
    if fee is not None:
        normal, under_13 = fee
        prices.append(
            Price(
                amount=normal,
                currency="EUR",
                label="Forfait stage (tarif normal)",
                includes=["tuition"],
                notes=f"Moins de 13 ans : {under_13:g} €" if under_13 is not None else None,
            )
        )
    if membership is not None:
        prices.append(
            Price(
                amount=membership,
                currency="EUR",
                label="Adhésion annuelle obligatoire",
                includes=[],
            )
        )
    return prices


# --- dates --------------------------------------------------------------------

# "du <weekday?> <d> <Month?> au <weekday?> <d> <Month> <year>". The start day may
# omit its month when it shares the end's (STAGE 2: "du Mercredi 8 au Mardi 14
# Juillet 2026"); leading weekday words are allowed but not captured.
_RANGE = re.compile(
    r"du\s+(?:\w+\s+)?(\d{1,2})\s*(" + _MONTHALT + r")?\s+"
    r"au\s+(?:\w+\s+)?(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    d1, m1, d2, m2, year = m.groups()
    end_month = _MONTHS[m2.lower()]
    start_month = _MONTHS[m1.lower()] if m1 else end_month
    y = int(year)
    start = date(y, start_month, int(d1))
    end = date(y, end_month, int(d2))
    return start, end


# Stop before the faculty list ("Professeur.e.s") whose embedded dots defeat a
# naive [^.]* run; the open-house phrase ends at the next ":" block.
_OPEN_DAY = re.compile(r"Portes\s+ouvertes\s+le\s+dernier\s+jour\s+du\s+stage", re.IGNORECASE)


def _schedule_note(body: str) -> str | None:
    m = _OPEN_DAY.search(body)
    return parse.clean(m.group(0)) if m else None


# --- ages: "Stages à partir de 10 ans" (open-ended upper bound) ---------------

_AGE = re.compile(r"à partir de\s+(\d{1,2})\s+ans", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    return parse.extract_age_range(text, _AGE)


# --- genres -------------------------------------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classique",)),
    ("contemporary", ("contemporain",)),
    ("pointe", ("pointe",)),
    ("repertoire", ("répertoire", "repertoire")),
]


def _genres(text: str) -> list[Genre]:
    # Jazz is out of scope (no Jazz genre in the register) so it contributes no
    # genre; every edition still teaches classical + contemporary.
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- faculty: per-edition roster, split by discipline -------------------------

# "CLASSIQUE : a, b, c CONTEMPORAIN : d, e JAZZ : f" — we keep the classical and
# contemporary names with their discipline as the role; jazz-only names are
# dropped (out of scope for a ballet register).
_DISCIPLINE = re.compile(
    r"(CLASSIQUE|CONTEMPORAIN)\s*:\s*(.*?)(?=\b(?:CLASSIQUE|CONTEMPORAIN|JAZZ|Planning)\b|$)",
    re.IGNORECASE,
)
_ROLE = {"classique": "Classique", "contemporain": "Contemporain"}


def _teachers(body: str) -> list[Teacher]:
    teachers: list[Teacher] = []
    seen: set[str] = set()
    for m in _DISCIPLINE.finditer(body):
        role = _ROLE[m.group(1).lower()]
        for raw in m.group(2).split(","):
            name = parse.clean(raw)
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            teachers.append(Teacher(name=name, role=role))
    return teachers


_APPLY_NOTE = (
    "Inscription via le formulaire/contrat de stage de l'école ; possibilité "
    "d'hébergement sur place et pension complète."
)
