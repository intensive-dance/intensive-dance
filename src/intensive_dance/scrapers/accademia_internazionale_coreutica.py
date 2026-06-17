"""Accademia Internazionale Coreutica — Florence, IT — its summer intensive.

API FIRST: WordPress with a clean `/wp-json/` (`wp/v2`). The evergreen *Summer
Intensive Course* page (id 1950) carries only a generic blurb and embeds the
dated edition through a WPBakery `vc_basic_grid` pulling **posts in category 135**
("Corso"). So we read that category directly — no HTML scraping. The post bodies
are raw WPBakery shortcodes (not server-rendered to headings), a flat run of
`[vc_column_text]` label/value blocks, which we slice and key on Italian labels.

DISCOVERY: one `Offering` per edition post. The Summer Course is *"open to all"*
and doubles as the audition for the academy's year-round tracks — a P1 trap: we
attribute only the summer course's own (unstated) requirements and keep the
audition-doubling as a faithful note, never importing academy-entry rules. The
category name is generic ("Corso"), so we scope to titles containing "estiv"
(estivo/estiva = summer). Editions are kept per IDR-24; the year-stamped slug
distinguishes cycles, and the next edition is auto-captured when it's published.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-17):
  - DATES: "Dal 21 al 26 Luglio 2025" — same-month span, start day drops its
    month → back-fill from the end month (shared `_SESSION` shape, Italian map).
  - AGES: "dai 10 ai 20 anni" → ageRange 10–20.
  - GENRES: matched against the curriculum (Livelli) block only — classical,
    pointe, contemporary, repertoire, character vary by edition (XXIII has pointe
    + repertoire, XXIV doesn't), so per-post matching, not page-wide.
  - LEVELS: Elementare/Intermedio/Avanzato → beginner/intermediate/advanced.
  - TEACHERS: "Docenti stabili" + "Docenti invitati" — `Name (discipline)` pairs;
    an invited teacher's "Name: career bio (discipline)" form is split on the colon.
  - PRICES in EUR: the "FORMULA N lezioni al giorno … € amount" tiers, scoped to
    the "Costo del corso" block so the €12 show ticket isn't mistaken for a fee.
  - DEADLINE: "Scadenza iscrizioni: 12 luglio 2025"; APPLICATION url = post link.
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
    Level,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.accademiainternazionalecoreutica.org"
SUMMER_CATEGORY = 135  # "Corso" — the summer-edition posts

ORG = Organization(
    name="Accademia Internazionale Coreutica",
    slug="accademia-internazionale-coreutica",
    country="IT",
    city="Florence",
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

# "Dal 21 al 26 Luglio 2025" — start day may drop its (shared) month.
_SESSION = re.compile(
    r"dal(?:l['’])?\s*(\d{1,2})\s*(?:("
    + _MONTHALT
    + r")\s+)?al(?:l['’])?\s*(\d{1,2})\s+("
    + _MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)
_HEADING = re.compile(r"(corso\s+internazionale\s+estivo.*?edizione)", re.IGNORECASE)
_AGES = re.compile(r"dai\s+(\d{1,2})\s+ai\s+(\d{1,2})\s+anni", re.IGNORECASE)
_DEADLINE = re.compile(
    r"scadenza\s+iscrizioni:?\s*(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})", re.IGNORECASE
)
_FORMULA = re.compile(r"formula\s+(\d+)\s+lezioni[^€]*€\s*([\d.,]+)", re.IGNORECASE)
_TEACHER = re.compile(r"([^()]+?)\s*\(([^)]+)\)")
_ROMAN = re.compile(r"^[IVXLCDM]+$", re.IGNORECASE)
_VC_TEXT = re.compile(
    r"\[vc_column_text[^\]]*\](.*?)\[/vc_column_text\]", re.DOTALL | re.IGNORECASE
)

_GENRES: list[tuple[Genre, list[str]]] = [
    ("classical", ["danza classica"]),
    ("pointe", ["punta"]),
    ("contemporary", ["contemporanea", "contemporaneo"]),
    ("repertoire", ["repertorio"]),
    ("character", ["carattere"]),
]
_LEVELS: list[tuple[Level, str]] = [
    ("beginner", "elementare"),
    ("intermediate", "intermedio"),
    ("advanced", "avanzato"),
]


def scrape(client: httpx.Client) -> list[Offering]:
    posts = wp.fetch_all(
        client,
        "posts",
        base=BASE,
        params={"categories": SUMMER_CATEGORY, "_fields": "id,link,title,content"},
    )
    return _build_offerings(posts)


def _blocks(rendered: str) -> list[str]:
    """The ordered text of each WPBakery `[vc_column_text]` block, tags stripped."""
    out: list[str] = []
    for raw in _VC_TEXT.findall(rendered):
        text = parse.clean(re.sub(r"<[^>]+>", " ", html.unescape(raw)))
        if text:
            out.append(text)
    return out


def _block_with(blocks: list[str], *needles: str) -> str:
    low = [n.lower() for n in needles]
    return next((b for b in blocks if any(n in b.lower() for n in low)), "")


def _value_after(blocks: list[str], *needles: str) -> str:
    """The block following the label block (a `Label:` heading then its value)."""
    low = [n.lower() for n in needles]
    for i, block in enumerate(blocks[:-1]):
        if any(block.lower().startswith(n) for n in low):
            return blocks[i + 1]
    return ""


def _dates(text: str) -> tuple[date, date] | None:
    m = _SESSION.search(text)
    if not m:
        return None
    d1, m1, d2, m2, year = m.groups()
    y = int(year)
    end_month = _MONTHS[m2.lower()]
    start_month = _MONTHS[m1.lower()] if m1 else end_month
    return date(y, start_month, int(d1)), date(y, end_month, int(d2))


def _title(heading_block: str, year: int) -> str:
    m = _HEADING.search(heading_block)
    if not m:
        return f"Corso Internazionale Estivo {year}"
    words = m.group(1).split()
    return " ".join(w.upper() if _ROMAN.match(w) else w.capitalize() for w in words)


def _ages(text: str) -> dict | None:
    m = _AGES.search(text)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _levels(curriculum: str) -> list[Level]:
    low = curriculum.lower()
    return [level for level, key in _LEVELS if key in low]


def _prices(blocks: list[str]) -> list[Price]:
    block = _value_after(blocks, "costo del corso") or _block_with(blocks, "formula")
    out: list[Price] = []
    for lessons, amount in _FORMULA.findall(block):
        if (value := parse.parse_amount(amount)) is not None:
            out.append(
                Price(
                    amount=value,
                    currency="EUR",
                    label=f"{lessons} lessons/day",
                    includes=["tuition"],
                )
            )
    return out


def _teachers(blocks: list[str]) -> list[Teacher]:
    stable = _value_after(blocks, "docenti stabili", "docenti")
    invited = _value_after(blocks, "docenti invitati")
    body = f"{stable} {invited}".strip()
    if not body:
        return []
    seen: set[str] = set()
    out: list[Teacher] = []
    for raw_name, discipline in _TEACHER.findall(body):
        # An invited teacher reads "Name: career bio (discipline)".
        name = parse.clean(raw_name.split(":")[0]).strip(" .,")
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(Teacher(name=name, role=parse.clean(discipline)))
    return out


def _location(blocks: list[str]) -> Location:
    block = _value_after(blocks, "sede del corso")
    # The block pairs the course venue with the (different) show venue; keep the course one.
    course = re.split(r"spettacolo", block, flags=re.IGNORECASE)[0]
    course = re.sub(r"^corso\s+estivo\s*:?\s*", "", course, flags=re.IGNORECASE)
    venue = parse.clean(course).strip(" .,")
    return Location(venue=venue or None, city="Florence", country="IT")


def _deadline(text: str) -> date | None:
    m = _DEADLINE.search(text)
    if not m:
        return None
    return date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))


def _build_offerings(posts: list[dict]) -> list[Offering]:
    offerings: list[Offering] = []
    for post in posts:
        title_rendered = html.unescape(post["title"]["rendered"])
        rendered = post["content"]["rendered"]
        blocks = _blocks(rendered)
        text = "\n".join(blocks)
        # The category is generic ("Corso"); only the summer ("estiv") posts qualify.
        if "estiv" not in (title_rendered + text).lower():
            continue
        span = _dates(text)
        if span is None:
            continue
        start, end = span
        curriculum = _block_with(blocks, "livell")
        audition = _value_after(blocks, "audizione")
        offerings.append(
            Offering(
                id=f"accademia-internazionale-coreutica/{start.year}",
                source=Source(
                    provider="accademia-internazionale-coreutica",
                    url=post["link"],
                    scrapedAt=now_utc(),
                ),
                title=_title(blocks[0] if blocks else "", start.year),
                genres=parse.match_genres(curriculum, _GENRES),
                level=_levels(curriculum),
                ageRange=_ages(text),
                organization=ORG,
                location=_location(blocks),
                schedule=Schedule(
                    season="summer",
                    start=start,
                    end=end,
                    timezone="Europe/Rome",
                ),
                teachers=_teachers(blocks),
                prices=_prices(blocks),
                application=Application(
                    deadline=_deadline(text),
                    url=post["link"],
                    notes=parse.clean(audition) or None,
                ),
            )
        )
    offerings.sort(key=lambda o: o.id)
    return offerings
