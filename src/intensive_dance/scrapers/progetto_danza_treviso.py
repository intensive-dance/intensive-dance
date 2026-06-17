"""Progetto Danza — "Stage Internazionale di Danza", Treviso IT.

API FIRST: the site runs an ancient WordPress (3.7.1) with no usable REST API
(`/wp-json/` just serves an HTML page), so this is a plain `selectolax` HTML
scrape. The dated edition's detail lives at
`/iniziative/<n>-stage-internazionale-di-danza-<year>/`, linked from the home
page's "stage" panel — we follow the latest-year link. The page lists the dates,
the faculty ("Insegnanti"), the price list ("QUOTE DI PARTECIPAZIONE") and the
registration deadline, but **not** the disciplines: those are only in the linked
`PROGRAMMA…pdf`, so we fetch and read it for genres.

DISCOVERY: one dated Stage per year (a two-week international summer stage); we
emit a single Offering for it. The site's *Concorso* (competition — icebox #80)
and teacher-training *Corsi per insegnanti* (not student intensives) are out of
scope and skipped by only following the stage link. Year-stamped slug; kept per
IDR-24 (the deadline 10 June 2026 is already past, the stage is not).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-17):
  - HTML for dates/teachers/prices/deadline + a linked PDF for disciplines.
  - DATES: "Dal 28.06.2026 al 11.07.2026" (numeric DD.MM.YYYY).
  - GENRES off the PDF programme's discipline headers: DANZA CLASSICA →
    classical, DANZA CONTEMPORANEA / CONTEMPORARY URBAN → contemporary, Punte →
    pointe, Repertorio → repertoire, Neo classico → neoclassical. (Danza moderna
    / Musical have no enum genre.)
  - LEVELS: tessere "livello intermedio / avanzato" → intermediate, advanced.
  - AGES: only the children's level states a band ("BAMBINI (9-11 ANNI)"); the
    intermediate/advanced levels are open-topped → ageRange 9–open.
  - PRICES in EUR: the QUOTE DI PARTECIPAZIONE lines (Open Card 1/2 weeks, the
    children's cards, lesson packets, the €50 registration fee).
  - TEACHERS: the "Insegnanti" list — names only (no roles are given).
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
    Level,
    Location,
    Offering,
    Organization,
    Price,
    PriceInclude,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.progettodanza.org"
PROVIDER = "progetto-danza-treviso"

ORG = Organization(name="Progetto Danza", slug=PROVIDER, country="IT", city="Treviso")

_MONTHS_IT = {
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
_MONTHALT = parse.months_alt(_MONTHS_IT)

_STAGE_HREF = re.compile(r"stage-internazionale-di-danza-(\d{4})", re.IGNORECASE)
_DATES = re.compile(r"Dal\s+(\d{1,2})\.(\d{1,2})\.(\d{4})\s+al\s+(\d{1,2})\.(\d{1,2})\.(\d{4})")
_DEADLINE = re.compile(
    r"iscrizioni\s+entro\s+il\s+(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})", re.I
)
_PRICE_LINE = re.compile(r"^(.*?)\s*€\s*([\d.,]+)\s*$")
_BAMBINI = re.compile(r"bambini\s*\((\d{1,2})\s*-\s*(\d{1,2})\s*anni\)", re.IGNORECASE)
_NAME = re.compile(r"^[A-ZÀ-Þ][a-zà-ÿ]+(?:\s+[A-ZÀ-Þ][a-zà-ÿ.'-]+){1,3}$")

_GENRES: list[tuple[Genre, list[str]]] = [
    ("classical", ["danza classica"]),
    ("contemporary", ["danza contemporanea", "contemporary"]),
    ("neoclassical", ["neo classico", "neoclassico"]),
    ("repertoire", ["repertorio"]),
    ("pointe", ["punte", "punta"]),
]
_LEVELS: list[tuple[Level, str]] = [
    ("intermediate", "intermedio"),
    ("advanced", "avanzato"),
]


def scrape(client: httpx.Client) -> list[Offering]:
    home = client.get(BASE)
    home.raise_for_status()
    detail_url = _latest_stage_url(home.text)
    if not detail_url:
        return []
    detail = client.get(detail_url)
    detail.raise_for_status()
    pdf_url = _programma_pdf_url(detail.text)
    pdf_text = ""
    if pdf_url:
        pdf = client.get(pdf_url)
        pdf.raise_for_status()
        pdf_text = _pdf_text(pdf.content)
    return _build_offerings(detail.text, detail_url, pdf_text, date.today())


def _latest_stage_url(home_html: str) -> str | None:
    best: tuple[int, str] | None = None
    for a in HTMLParser(home_html).css("a"):
        href = a.attributes.get("href") or ""
        m = _STAGE_HREF.search(href)
        if m and "/iniziative/" in href:
            year = int(m.group(1))
            if best is None or year > best[0]:
                best = (year, href)
    return _absolute(best[1]) if best else None


def _programma_pdf_url(detail_html: str) -> str | None:
    for a in HTMLParser(detail_html).css("a"):
        href = a.attributes.get("href") or ""
        if "programma" in href.lower() and href.lower().endswith(".pdf"):
            return _absolute(href)
    return None


def _absolute(href: str) -> str:
    if href.startswith("//"):
        return f"https:{href}"
    if href.startswith("http"):
        return href
    return f"{BASE}{href if href.startswith('/') else '/' + href}"


def _pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


def _content_lines(detail_html: str) -> list[str]:
    node = HTMLParser(detail_html).css_first(".contentWrap")
    if node is None:
        return []
    lines = (parse.clean(line) for line in node.text(separator="\n").split("\n"))
    return [line for line in lines if line]


def _dates(text: str) -> tuple[date, date] | None:
    m = _DATES.search(text)
    if not m:
        return None
    d1, m1, y1, d2, m2, y2 = (int(g) for g in m.groups())
    return date(y1, m1, d1), date(y2, m2, d2)


def _deadline(text: str) -> date | None:
    m = _DEADLINE.search(text)
    if not m:
        return None
    return date(int(m.group(3)), _MONTHS_IT[m.group(2).lower()], int(m.group(1)))


def _teachers(lines: list[str]) -> list[Teacher]:
    try:
        start = lines.index("Insegnanti")
        end = lines.index("Come iscriversi", start)
    except ValueError:
        return []
    return [Teacher(name=line) for line in lines[start + 1 : end] if _NAME.match(line)]


def _prices(lines: list[str]) -> list[Price]:
    try:
        start = next(i for i, line in enumerate(lines) if "quote di partecipazione" in line.lower())
    except StopIteration:
        return []
    prices: list[Price] = []
    for line in lines[start + 1 :]:
        m = _PRICE_LINE.match(line)
        if not m:
            break  # the price block is a contiguous run of "Label € amount" lines
        amount = parse.parse_amount(m.group(2))
        if amount is None:
            continue
        label = _it_title(m.group(1))
        includes: list[PriceInclude] = [] if "iscrizione" in label.lower() else ["tuition"]
        prices.append(Price(amount=amount, currency="EUR", label=label, includes=includes))
    return prices


def _age_range(text: str) -> dict | None:
    m = _BAMBINI.search(text)
    # Children's level states 9–11; intermediate/advanced are open-topped, so the
    # stage as a whole runs from the youngest stated age with no stated maximum.
    return {"min": int(m.group(1)), "max": None} if m else None


def _build_offerings(
    detail_html: str, detail_url: str, pdf_text: str, today: date
) -> list[Offering]:
    lines = _content_lines(detail_html)
    text = "\n".join(lines)
    span = _dates(text)
    if span is None:
        return []
    start, end = span
    return [
        Offering(
            id=f"{PROVIDER}/{start.year}",
            source=Source(provider=PROVIDER, url=detail_url, scrapedAt=now_utc()),
            title=_title(lines[0] if lines else f"Stage Internazionale di Danza {start.year}"),
            genres=parse.match_genres(pdf_text, _GENRES),
            level=[lvl for lvl, key in _LEVELS if key in text.lower()],
            ageRange=_age_range(text),
            organization=ORG,
            location=Location(venue="La Ghirada – Città dello Sport", city="Treviso", country="IT"),
            schedule=Schedule(season="summer", start=start, end=end, timezone="Europe/Rome"),
            teachers=_teachers(lines),
            prices=_prices(lines),
            application=Application(
                deadline=_deadline(text),
                url=detail_url,
                notes="Iscrizioni a numero chiuso fino a esaurimento posti (acconto €100). "
                "Documenti: scheda di iscrizione, certificato medico per attività non "
                "agonistica, fotografia formato tessera.",
            ),
        )
    ]


_IT_PARTICLES = re.compile(r"\b(Di|Il|La|Lo|Al|Dal|Da|Del|Della|E)\b")


def _it_title(raw: str) -> str:
    """Title-case Italian text, keeping the small particles (di/al/da/…) lowercase."""
    return parse.clean(_IT_PARTICLES.sub(lambda m: m.group(1).lower(), raw.title()))


def _title(raw: str) -> str:
    return _it_title(raw)
