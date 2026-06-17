"""Art Studio Danza — Salò (BS), IT — its Stage Internazionale del Lago di Garda.

API FIRST: WordPress + **Elementor**, clean `/wp-json/`. Art Studio runs the dated
summer *Stage Internazionale del Lago di Garda* (one page per edition,
`<N>-stage-internazionale-del-lago-di-garda`). We list the pages, pick the
current (highest-numbered) stage edition and parse its Elementor HTML.

SCOPE: the site also runs the **Winter Festival / Easter Festival / Falling
Leaves** — those are **competitions (icebox #80, out of scope)** and are NOT
built; only the summer stage is.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-17):
  - DATES: "dal 18 al 26 Luglio 2026" — same-month Italian span.
  - GENRES: the curriculum (tecnica accademica/repertorio/punte/contemporanea e
    modern) → classical/repertoire/pointe/contemporary; Italian keywords.
  - TEACHERS: the faculty in `.docente-title` (name, `<br>`-split) + `.docente-desc`
    (credential / what they teach) Elementor widgets.
  - PRICES in EUR: stage enrollment (€650 tuition) + the hotel convention
    (€65/person/day, half board, accommodation) — gala tickets, the teachers'
    seminar and private-lesson extras are left out (not the stage's own fee).
    AGES are not stated for participants → unset (faithful, fail open).
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse, wp
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

BASE = "https://artstudiodanza.it"
_STAGE_SLUG = re.compile(r"^(\d+)-stage-(?:internazionale|estivo)")

ORG = Organization(
    name="Art Studio Danza",
    slug="art-studio-danza",
    country="IT",
    city="Salò",
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
_TUITION = re.compile(r"Iscrizione\s*€\s*([\d.,]+)", re.IGNORECASE)
_LODGING = re.compile(r"€\s*([\d.,]+)\s*a\s+persona\s+al\s+giorno", re.IGNORECASE)

_GENRES: list[tuple[Genre, list[str]]] = [
    ("classical", ["accademica", "classica", "classico"]),
    ("pointe", ["punte", "punta"]),
    ("contemporary", ["contemporanea", "contemporaneo", "modern"]),
    ("repertoire", ["repertorio"]),
    ("character", ["carattere"]),
]


def scrape(client: httpx.Client) -> list[Offering]:
    pages = wp.fetch_all(client, "pages", base=BASE, params={"_fields": "id,slug"})
    editions = [(int(m.group(1)), p["slug"]) for p in pages if (m := _STAGE_SLUG.match(p["slug"]))]
    if not editions:
        return []
    _, slug = max(editions)
    page = wp.fetch_page(client, slug, base=BASE)
    if not page:
        return []
    return _build_offerings(page["content"]["rendered"], page["link"], page["title"]["rendered"])


def _collapsed(html_str: str) -> str:
    tree = HTMLParser(html_str)
    for junk in tree.css("script, style, noscript"):
        junk.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _dates(text: str) -> tuple[date, date] | None:
    m = _DATE.search(text)
    if not m:
        return None
    d1, d2, mon, year = m.groups()
    y, month = int(year), _MONTHS[mon.lower()]
    return date(y, month, int(d1)), date(y, month, int(d2))


def _teachers(tree: HTMLParser) -> list[Teacher]:
    """Faculty from interleaved `.docente-title` / `.docente-desc` Elementor widgets.

    Walked in document order (a comma `css` selector groups by selector, which would
    pile every description onto the last teacher).
    """
    body = tree.body
    if body is None:
        return []
    out: list[Teacher] = []
    seen: set[str] = set()
    current: Teacher | None = None
    descs: list[str] = []

    def flush() -> None:
        nonlocal current
        if current and current.name and current.name not in seen:
            seen.add(current.name)
            current.role = " — ".join(descs) or None
            out.append(current)
        current = None

    for node in body.traverse(include_text=False):
        classes = node.attributes.get("class") or ""
        if "docente-title" in classes:
            flush()
            name = parse.clean(" ".join(wp.node_lines(node)))
            current = Teacher(name=name.title() if name.isupper() else name) if name else None
            descs = []
        elif "docente-desc" in classes and current is not None:
            if line := parse.clean(node.text(separator=" ")):
                descs.append(line)
    flush()
    return out


def _prices(text: str) -> list[Price]:
    out: list[Price] = []
    if (m := _TUITION.search(text)) and (v := parse.parse_amount(m.group(1))) is not None:
        out.append(Price(amount=v, currency="EUR", label="Stage enrollment", includes=["tuition"]))
    if (m := _LODGING.search(text)) and (v := parse.parse_amount(m.group(1))) is not None:
        out.append(
            Price(
                amount=v,
                currency="EUR",
                label="Accommodation (per person/day)",
                includes=["accommodation", "meals"],
                notes="Hotel convention, half board; booked through the organisation.",
            )
        )
    return out


def _build_offerings(html_str: str, url: str, title_rendered: str) -> list[Offering]:
    import html as _html

    tree = HTMLParser(html_str)
    text = _collapsed(html_str)
    span = _dates(text)
    if span is None:
        return []
    start, end = span
    return [
        Offering(
            id=f"art-studio-danza/{start.year}",
            source=Source(provider="art-studio-danza", url=url, scrapedAt=now_utc()),
            title=parse.clean(_html.unescape(title_rendered)),
            genres=parse.match_genres(text, _GENRES, default=["classical"]),
            organization=ORG,
            location=Location(venue="Art Studio Danza", city="Salò", country="IT"),
            schedule=Schedule(season="summer", start=start, end=end, timezone="Europe/Rome"),
            teachers=_teachers(tree),
            prices=_prices(text),
            application=Application(url=url),
        )
    ]
