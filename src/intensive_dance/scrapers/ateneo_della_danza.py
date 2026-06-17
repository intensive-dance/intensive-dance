"""Ateneo della Danza — Siena, IT — its Intensive Summer School.

API FIRST: WordPress + **Elementor**, clean `/wp-json/`. The dated edition lives
on one page (`intensive-summer-school`); Elementor renders real HTML into
`content.rendered`, so we parse it with `selectolax` (no page fetch / no JS render
needed). One living page = one current edition (it's re-dressed each year), so we
emit a single, year-stamped `Offering`.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-17):
  - DATES: "dal 4 al 13 Luglio 2026" — same-month span, Italian month map.
  - GENRES: the curriculum (classical/pointe/repertoire/character/contemporary),
    matched on **Italian** discipline words only — so English affiliation names
    ("American Repertory Ballet", "Ballet Hagen") can't leak a genre (P3).
  - TEACHERS: the 16 faculty in `.elementor-image-box` widgets — `<h3>` name, then
    a `<p>` of "affiliation <br> disciplines"; role = the disciplines, affiliation
    = the institution (multi-line affiliations join, the last line is the role).
  - PRICES in EUR: tuition (€700 full / €600 early-bird by 15/05), accommodation
    (€540), meals (€295) — the labelled participant fees only; show tickets, the
    auditor pass and the deposit are deliberately left out (not a participant fee).
  - APPLICATION: entry needs a **video pre-selection** → VideoReq(unspecific).
    AGES/LEVELS are never stated on the page → left unset (faithful, fail open).
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse, wp
from intensive_dance.models import (
    Affiliation,
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    Price,
    PriceInclude,
    Schedule,
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

BASE = "https://www.ateneodelladanza.it"
PAGE_SLUG = "intensive-summer-school"

ORG = Organization(
    name="Ateneo della Danza",
    slug="ateneo-della-danza",
    country="IT",
    city="Siena",
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

_DATE = re.compile(
    r"dal\s+(\d{1,2})\s+al\s+(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})", re.IGNORECASE
)
_TUITION = re.compile(r"quota\s+d['’]iscrizione\s*€\s*(\d+)(?:\s*€\s*(\d+))?", re.IGNORECASE)
_ACCOMMODATION = re.compile(r"Alloggio\s*€\s*(\d+)", re.IGNORECASE)
_MEALS = re.compile(r"Pasti\s*€\s*(\d+)", re.IGNORECASE)
_DISCIPLINE = re.compile(r"danza|tecnica|repertorio|contempo|carattere|punte", re.IGNORECASE)

_GENRES: list[tuple[Genre, list[str]]] = [
    ("classical", ["classica", "classico"]),
    ("pointe", ["punte", "punta"]),
    ("contemporary", ["contemporanea", "contemporaneo"]),
    ("repertoire", ["repertorio"]),
    ("character", ["carattere"]),
]


def scrape(client: httpx.Client) -> list[Offering]:
    page = wp.fetch_page(client, PAGE_SLUG, base=BASE)
    if not page:
        return []
    return _build_offerings(page["content"]["rendered"], page["link"])


def _dates(text: str) -> tuple[date, date] | None:
    m = _DATE.search(text)
    if not m:
        return None
    d1, d2, mon, year = m.groups()
    y, month = int(year), _MONTHS[mon.lower()]
    return date(y, month, int(d1)), date(y, month, int(d2))


def _teachers(tree: HTMLParser) -> list[Teacher]:
    out: list[Teacher] = []
    seen: set[str] = set()
    for box in tree.css(".elementor-image-box-content"):
        title = box.css_first(".elementor-image-box-title")
        desc = box.css_first(".elementor-image-box-description")
        if not title or not desc:
            continue
        name = parse.clean(title.text())
        lines = wp.node_lines(desc)
        if not name or name in seen or not lines or not _DISCIPLINE.search(" ".join(lines)):
            continue
        seen.add(name)
        role = parse.clean(lines[-1]) if len(lines) > 1 else None
        affiliation = (
            parse.clean(" ".join(lines[:-1])).replace(" | ", ", ") if len(lines) > 1 else None
        )
        affiliations = [Affiliation(organization=affiliation)] if affiliation else []
        out.append(Teacher(name=name, role=role, affiliations=affiliations))
    return out


def _prices(text: str) -> list[Price]:
    out: list[Price] = []

    def add(amount: str | None, includes: list[PriceInclude], label: str, notes: str | None = None):
        if amount and (value := parse.parse_amount(amount)) is not None:
            out.append(
                Price(amount=value, currency="EUR", label=label, includes=includes, notes=notes)
            )

    if m := _TUITION.search(text):
        full, early = m.groups()
        add(full, ["tuition"], "Tuition (full)")
        add(early, ["tuition"], "Tuition (early-bird, by 15 May)")
    if m := _ACCOMMODATION.search(text):
        add(m.group(1), ["accommodation"], "Accommodation (double/triple room, breakfast)")
    if m := _MEALS.search(text):
        add(m.group(1), ["meals"], "Meals (lunch + dinner, full course)")
    return out


def _collapsed(html: str) -> str:
    tree = HTMLParser(html)
    for junk in tree.css("script, style, noscript"):
        junk.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _build_offerings(html: str, url: str) -> list[Offering]:
    tree = HTMLParser(html)
    text = _collapsed(html)
    span = _dates(text)
    if span is None:
        return []
    start, end = span
    return [
        Offering(
            id=f"ateneo-della-danza/{start.year}",
            source=Source(provider="ateneo-della-danza", url=url, scrapedAt=now_utc()),
            title=f"Intensive Summer School {start.year}",
            genres=parse.match_genres(text, _GENRES, default=["classical"]),
            organization=ORG,
            location=Location(venue="Ateneo della Danza", city="Siena", country="IT"),
            schedule=Schedule(season="summer", start=start, end=end, timezone="Europe/Rome"),
            teachers=_teachers(tree),
            prices=_prices(text),
            application=Application(
                url=url,
                requirements=[
                    VideoReq(specificity="unspecific", description="Video pre-selection.")
                ],
                notes=(
                    "Entry requires a video pre-selection; up to 50 scholarships of €200 "
                    "(off the full tuition) may be awarded."
                ),
            ),
        )
    ]
