"""Opus Ballet — Florence, IT — its Summer Campus (DanzaFirenze).

API FIRST: WordPress + **Elementor**, so `/wp-json/` `content.rendered` is the
usual Elementor empty shell — useless. The `/campus/summer-campus/` page is
server-rendered, though, so it's a plain `selectolax` text scrape. The course
fees live in an image (`modalita-summer-2026.jpg`, not text-extractable), but the
registration form **PDF** (`SCHEDA-ISCRIZIONE-SUMMER-CAMPUS-…pdf`, linked from
the page) carries the €20 registration fee and the venue address.

DISCOVERY: the Summer Campus is one dated edition per year ("XXVI edizione …
2026"); we emit a single `Offering`, season-keyed from the parsed year. (The
provider also runs a Winter Campus / teacher Master and a competition — separate
pages, out of this build.)

WHAT WE EXTRACT (verified live 2026-06-26):
  - DATES: an Italian "dal 29 giugno all'11 luglio 2026" span (local month map;
    the apostrophe elision `all'11` is handled).
  - GENRES: "danza classica, modern, contemporanea, hip hop" → classical +
    contemporary (modern folds into contemporary; hip hop is out of scope).
  - AGES: a junior strand "dai 7 ai 12 anni" alongside an ADULTI category → we
    record the youngest stated bound (min 7) and leave the upper open.
  - PRICES: "QUOTA DI ISCRIZIONE € 20,00" from the SCHEDA PDF — a registration
    fee (the per-course tuition is image-only, so not invented).
  - LOCATION / APPLICATION: venue address from the PDF ("via Ugo Foscolo, 6 -
    50124 Firenze"); entry is open-enrollment via the form + bank transfer (no
    audition material) — requirements left unknown, the €20 fee + early-payment
    note recorded.

WHAT THIS SCRAPER EXERCISES: Elementor-empty-REST fallthrough to HTML; Italian
date range with elision; PDF-sourced registration fee + venue; out-of-scope genre
drop; open-topped age; raise-on-degraded-fetch.
"""

from __future__ import annotations

import io
import re
from datetime import date

import httpx
from pypdf import PdfReader
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.fetch import PROXY_PARAMS_HEADER
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

BASE = "https://opusballet.it"
PAGE = f"{BASE}/campus/summer-campus/"

ORG = Organization(name="Opus Ballet", slug="opus-ballet", country="IT", city="Florence")

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

# "dal 29 giugno all'11 luglio 2026" — day month, then "al/all'" + day month year.
_RANGE = re.compile(
    r"(\d{1,2})\s+(" + _MONTH_IT + r")\s+all?['’\s]+(\d{1,2})\s+(" + _MONTH_IT + r")\s+(\d{4})",
    re.IGNORECASE,
)
_EDITION = re.compile(r"\b([IVXLC]+)\s+edizione", re.IGNORECASE)
_AGE_MIN = re.compile(r"dai?\s+(\d{1,2})\s+ai\s+\d{1,2}\s+anni", re.IGNORECASE)
_QUOTA = re.compile(r"QUOTA\s+DI\s+ISCRIZIONE\s*€?\s*([\d.,]+)", re.IGNORECASE)
_PDF_HREF = re.compile(r'href="([^"]*SCHEDA[^"]*\.pdf)"', re.IGNORECASE)
_ADDR = re.compile(r"(via[^,]+,\s*\d+)\s*-\s*\d{5}\s+Firenze", re.IGNORECASE)

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classica",)),
    ("contemporary", ("contemporanea", "modern")),
]
_APPLY_NOTE = (
    "Open-enrollment via the registration form + bank transfer; €20 registration "
    "fee. Early payment by 31 May (Soluzione A), standard after."
)


def scrape(client: httpx.Client) -> list[Offering]:
    # The HTML page sits behind a bot gate the proxy's plain/auto tier clears only
    # intermittently (401), so force the FlareSolverr `solve=1` tier — it returns
    # the rendered HTML reliably. The registration PDF under /wp-content is NOT
    # gated and must stay on the plain tier (solve=1 wraps a PDF in a viewer DOM).
    resp = client.get(PAGE, headers={PROXY_PARAMS_HEADER: "solve=1"})
    resp.raise_for_status()
    html = resp.text
    pdf_text = ""
    pm = _PDF_HREF.search(html)
    if pm:
        pdf_url = pm.group(1)
        if pdf_url.startswith("/"):
            pdf_url = BASE + pdf_url
        pdf_resp = client.get(pdf_url)
        if pdf_resp.status_code == 200:
            pdf_text = _pdf_text(pdf_resp.content)
    return [_build_offering(html, pdf_text)]


def _pdf_text(data: bytes) -> str:
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    return parse.clean(text)


def _build_offering(html: str, pdf_text: str = "") -> Offering:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ") if tree.body else "")

    m = _RANGE.search(text)
    if not m:
        raise ValueError("Opus Ballet: no Summer Campus date range found (degraded fetch?)")
    year = int(m.group(5))
    start = date(year, _ITALIAN_MONTHS[m.group(2).lower()], int(m.group(1)))
    end = date(year, _ITALIAN_MONTHS[m.group(4).lower()], int(m.group(3)))
    season = str(year)

    em = _EDITION.search(text)
    edition = f"{em.group(1).upper()} edizione — " if em else ""

    return Offering(
        id=f"opus-ballet/summer-campus-{season}",
        source=Source(provider="opus-ballet", url=PAGE, scrapedAt=now_utc()),
        title=f"Summer Campus {season}",
        genres=_genres(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=_location(pdf_text),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Rome",
            notes=f"{edition}DanzaFirenze Summer Campus, Florence.".strip(),
        ),
        prices=_prices(pdf_text),
        application=Application(url=PAGE, notes=_APPLY_NOTE),
    )


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _age_range(text: str) -> dict | None:
    m = _AGE_MIN.search(text)
    return {"min": int(m.group(1))} if m else None  # adults included → upper open


def _location(pdf_text: str) -> Location:
    m = _ADDR.search(pdf_text)
    venue = parse.clean(m.group(1)).title() if m else None
    return Location(venue=venue, city="Florence", country="IT")


def _prices(pdf_text: str) -> list[Price]:
    m = _QUOTA.search(pdf_text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    return [Price(amount=amount, currency="EUR", label="Quota di iscrizione", includes=[])]
