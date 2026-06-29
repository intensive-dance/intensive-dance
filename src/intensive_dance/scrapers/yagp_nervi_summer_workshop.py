"""YGP International Summer Workshop at the Nervi Festival (IT), Genoa.

API FIRST
yagp.org is **WordPress** (`/wp-json/` 200) on an **Elementor** theme. The Nervi
workshop has one *page* per yearly edition; we discover them via the REST search
(`pages?search=nervi festival`) and pick the latest by the year in the slug
(`the-ygp-<YYYY>-international-summer-workshop-at-nervi-festival`), skipping the
stray "… Copy" duplicate. Elementor leaves most layout out of `content.rendered`,
but the bits we need survive as text: the program blurb (→ genres), the
`APPLICATION DEADLINE - <date>` line, and the link to the edition's **GUIDE PDF**.
The page itself states no program dates — those live only in the guide — so we
fetch that PDF and read the registration + gala days from it (pypdf).

DISCOVERY — the *competition* (Youth America Grand Prix) is out of scope (icebox
#80); this is YAGP's own dated **student summer workshop / intensive** run under
its own provider slug, one Offering per edition (cf. the
prix-de-lausanne-summer-intensive precedent). The latest published edition is
built; ended cycles are kept (IDR-24), so a past edition is not dropped, and the
rotation picks up a newer one once yagp.org publishes it.

WHAT'S STATED vs NOT — faithful/fail-open:
- DATES: the guide gives registration ("Registration will be held on Sunday,
  July 20") and the two Gala days ("Gala performances on July 26 and July 27");
  year from the title. We take start = registration day, end = the last gala, and
  keep the raw phrasing in schedule.notes. If the guide can't be read, dates stay
  null rather than guessed.
- GENRES: classical + contemporary + repertoire (the blurb names classical
  technique classes, contemporary works and a casting/repertoire process).
- AGES and TUITION are not stated on the page or in the guide (the guide only
  lists optional extras — a €100 private lesson, a €150 tutu, hotel rates — which
  are NOT the program price), so ageRange and prices are left empty, not invented.
- application.deadline from the page; requirements left empty (not stated).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-26)
- WP REST search → latest-by-year edition select (excluding a "Copy" page).
- Elementor `content.rendered` text mining (deadline, GUIDE link, genres).
- A linked GUIDE **PDF** scraped (pypdf) for the only dates the source states.
- A faithfully thin Offering: null ageRange/prices where the source is silent.
"""

from __future__ import annotations

import io
import re
from datetime import date

import httpx
from pypdf import PdfReader
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
    now_utc,
)

BASE = "https://yagp.org"

ORG = Organization(
    name="Youth America Grand Prix", slug="yagp-nervi-summer-workshop", country="IT", city="Genoa"
)
LOCATION = Location(venue="Teatro Carlo Felice", city="Genoa", country="IT")

_SLUG = re.compile(r"^the-ygp-(\d{4})-international-summer-workshop-at-nervi-festival$")

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet")),
    ("contemporary", ("contemporary",)),
    ("repertoire", ("repertoire",)),
]


def scrape(client: httpx.Client) -> list[Offering]:
    pages = wp.fetch_all(client, "pages", base=BASE, params={"search": "nervi festival"})
    page = _select_latest(pages)
    if page is None:
        # Search returned no edition page — degraded; raise so the prior store stays.
        raise ValueError("YAGP Nervi: no edition page found via WP search")

    rendered = page.get("content", {}).get("rendered", "")
    guide_text = ""
    guide_url = _guide_url(rendered)
    if guide_url:
        pdf = client.get(guide_url)
        if pdf.status_code == 200 and "pdf" in pdf.headers.get("content-type", "").lower():
            guide_text = _pdf_text(pdf.content)
    return [_build_offering(page, guide_text)]


def _select_latest(pages: list[dict]) -> dict | None:
    """The Nervi edition page with the highest year in its slug, skipping the
    stray '… Copy' duplicate."""
    best: tuple[int, dict] | None = None
    for p in pages:
        m = _SLUG.match(p.get("slug", ""))
        if not m:
            continue
        if "copy" in p.get("title", {}).get("rendered", "").lower():
            continue
        year = int(m.group(1))
        if best is None or year > best[0]:
            best = (year, p)
    return best[1] if best else None


def _pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


def _guide_url(rendered_html: str) -> str | None:
    for m in re.finditer(r'href="([^"]+)"', rendered_html):
        if re.search(r"GUIDE\.pdf|NERVI[^\"]*GUIDE", m.group(1), re.IGNORECASE):
            return m.group(1)
    return None


def _build_offering(page: dict, guide_text: str) -> Offering:
    link = page.get("link", BASE)
    raw_title = parse.clean(HTMLParser(page.get("title", {}).get("rendered", "")).text())
    title = re.sub(r"^The\s+", "", raw_title)
    year_m = re.search(r"(\d{4})", title)
    year = int(year_m.group(1)) if year_m else None
    season = str(year) if year else "unknown"

    rendered_text = parse.clean(HTMLParser(page.get("content", {}).get("rendered", "")).text())
    start, end, notes = _dates(guide_text, year)

    return Offering(
        id=f"yagp-nervi-summer-workshop/nervi-{season}",
        source=Source(provider="yagp-nervi-summer-workshop", url=link, scrapedAt=now_utc()),
        title=title or "YGP International Summer Workshop at Nervi Festival",
        genres=parse.match_genres(rendered_text, _GENRE_KEYWORDS, default=["classical"]),
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Rome", notes=notes),
        prices=_prices(),
        application=_application(rendered_text, link),
    )


_REGISTRATION = re.compile(
    r"Registration will be held on\s+\w+,?\s+(" + parse.MONTHALT + r")\s+(\d{1,2})", re.IGNORECASE
)
_GALAS = re.compile(
    r"Gala performances on\s+("
    + parse.MONTHALT
    + r")\s+(\d{1,2})\s+and\s+("
    + parse.MONTHALT
    + r")\s+(\d{1,2})",
    re.IGNORECASE,
)


def _dates(guide_text: str, year: int | None) -> tuple[date | None, date | None, str | None]:
    if not guide_text or year is None:
        return None, None, None
    reg = _REGISTRATION.search(guide_text)
    gala = _GALAS.search(guide_text)
    start = date(year, parse.MONTHS[reg.group(1).lower()], int(reg.group(2))) if reg else None
    end = date(year, parse.MONTHS[gala.group(3).lower()], int(gala.group(4))) if gala else None
    if start is None and end is None:
        return None, None, None
    notes_bits = []
    if reg:
        notes_bits.append(f"Registration {reg.group(1)} {reg.group(2)}")
    if gala:
        notes_bits.append(
            f"Gala performances {gala.group(1)} {gala.group(2)} and {gala.group(3)} {gala.group(4)}"
        )
    return start, end, "; ".join(notes_bits) or None


def _prices() -> list[Price]:
    # The program tuition is not published on the page or in the guide (the guide
    # lists only optional extras — a private lesson, a tutu, hotel rates — which are
    # not the intensive's price), so we emit no Price rather than invent one.
    return []


_DEADLINE = re.compile(
    r"APPLICATION DEADLINE\s*[-–]\s*(" + parse.MONTHALT + r")\s+(\d{1,2}),?\s+(\d{4})",
    re.IGNORECASE,
)


def _application(rendered_text: str, link: str) -> Application:
    m = _DEADLINE.search(rendered_text)
    deadline = (
        date(int(m.group(3)), parse.MONTHS[m.group(1).lower()], int(m.group(2))) if m else None
    )
    return Application(deadline=deadline, url=link)
