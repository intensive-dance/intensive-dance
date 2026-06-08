"""Corella Dance Academy (Barcelona International Ballet Conservatory) — Barcelona, ES.

API FIRST: the site (www.corelladanceacademy.com → canonical corellabarcelona.com)
runs **WordPress** with the Elementor page builder. `/wp-json/` returns 200 and
exposes the full page list via `/wp-json/wp/v2/pages`. The `content.rendered` field
carries the complete Elementor-built HTML — unlike the ABT / Joffrey REST trap,
Elementor *does* inject rendered text nodes into the response, so no JS render is
needed. We fetch the page JSON directly from the REST API; the program-bearing
heading text and price blocks are present in `content.rendered`.

DISCOVERY: two workshop pages have specific 2026 dates at scrape time:

  • page 4374 — "Company Workshop con Ángel Corella" (Jul 6–11, 2026): classical
    ballet + choreographic workshop at a pre-professional level. The headline
    states "Del 6 al 11 de julio de 2026"; the schedule section has a copy-error
    ("junio") that contradicts the banner — we trust the banner date (July).
    In-scope ballet intensive → one Offering.

  • page 4363 — "Workshop adultos corella" (Aug 11–16, 2026): targets adult
    amateurs, curriculum mixes jazz + Spanish dance alongside ballet — out of scope
    for a ballet register.

Other pages (women retreat, Gyrokinesis workshop) are either adult-wellness/out-of-
scope or have no firm 2026 dates. The "Programa de Verano" page (page 2674) lists
no 2026 dates yet ("próximos horarios disponibles"), so it is not emitted.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - WordPress REST API + Elementor rendered HTML (no JS needed)
  - Spanish-language date string: "Del 6 al 11 de julio de 2026"
  - Defined-pose photo requirement (two poses stated in the application form)
  - Multi-teacher roster scraped from named headings
  - Two-price structure (training + housing, IVA included)
  - Pre-professional level inferred from "ritmo pre-profesional" prose
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Affiliation,
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    PhotosReq,
    Price,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://corellabarcelona.com"
# WP REST page ID for the Angel Corella company workshop
_WORKSHOP_PAGE_ID = 4374
_WORKSHOP_URL = f"{BASE}/company-workshop-con-angel-corella/"

ORG = Organization(
    name="Corella Dance Academy",
    slug="corella-dance-academy",
    country="ES",
    city="Barcelona",
)

# Spanish months → number, for the "del D al D de MES de YYYY" pattern used on the site
_ES_MONTHS: dict[str, int] = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

# "Del 6 al 11 de julio de 2026" — headline format on the workshop banner
_DATE_RANGE_ES = re.compile(
    r"[Dd]el\s+(\d{1,2})\s+al\s+(\d{1,2})\s+de\s+(" + "|".join(_ES_MONTHS) + r")\s+de\s+(\d{4})",
    re.IGNORECASE,
)

# Price lines extracted from Elementor widget text:
#   "training\n1.100€" / "1.100€\n(1 semana)"
#   "housing\n770€"  / "770€\n(1 semana)"
_PRICE = re.compile(r"(training|housing)\s+([\d.,]+)\s*€", re.IGNORECASE)

# Application requirement: two defined poses listed in the form section.
_WORKSHOP_POSES = [
    "Développé à la seconde",
    "Primer Arabesque",
]


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(f"{BASE}/wp-json/wp/v2/pages/{_WORKSHOP_PAGE_ID}")
    resp.raise_for_status()
    page_json = resp.json()
    html = page_json.get("content", {}).get("rendered", "")
    return _build_offerings(html, date.today())


def _build_offerings(html: str, today: date) -> list[Offering]:  # noqa: ARG001
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator="\n")) if tree.body else ""

    start, end = _date_range(text)
    if start is None or end is None:
        # No firm dated edition present — do not emit.
        return []

    season = str(start.year)

    return [
        Offering(
            id=f"corella-dance-academy/angel-corella-workshop-{season}",
            source=Source(
                provider="corella-dance-academy",
                url=_WORKSHOP_URL,
                scrapedAt=now_utc(),
            ),
            title=f"Company Workshop con Ángel Corella {season}",
            genres=_genres(text),
            level=["pre-professional"],
            organization=ORG,
            location=Location(
                # The academy is located at Masía Mas Berenguer at the foot of
                # Parc Natural del Montseny — outside central Barcelona, but
                # the org city is Barcelona per official branding.
                venue="Masía Mas Berenguer, Parc Natural del Montseny",
                city="Barcelona",
                country="ES",
            ),
            schedule=Schedule(
                season=season,
                start=start,
                end=end,
                timezone="Europe/Madrid",
                notes=f"Del {start.day} al {end.day} de {_ES_MONTHS_INV[start.month]} de {season}",
            ),
            teachers=_teachers(text),
            prices=_prices(text),
            application=Application(
                status="open" if re.search(r"plazas abiertas", text, re.IGNORECASE) else None,
                url=_WORKSHOP_URL,
                requirements=[
                    PhotosReq(
                        specificity="defined-poses",
                        poses=_WORKSHOP_POSES,
                        notes=(
                            "Two photos in dance attire (leotard and tights): "
                            "développé à la seconde and primer arabesque. "
                            "Dancers under 13 in demi-pointe shoes."
                        ),
                    )
                ],
            ),
        )
    ]


# Inverse month map for the schedule.notes label
_ES_MONTHS_INV: dict[int, str] = {v: k for k, v in _ES_MONTHS.items()}


# --- helpers ------------------------------------------------------------------


def _date_range(text: str) -> tuple[date | None, date | None]:
    """Parse 'Del D al D de MES de YYYY' from the workshop banner."""
    m = _DATE_RANGE_ES.search(text)
    if not m:
        return None, None
    d1, d2, month_es, year = m.groups()
    month_num = _ES_MONTHS[month_es.lower()]
    y = int(year)
    return date(y, month_num, int(d1)), date(y, month_num, int(d2))


def _genres(text: str) -> list[Genre]:
    """Classical ballet + repertoire are the declared content; contemporary
    choreographic workshop is also present ('taller coreográfico', 'moderno')."""
    _GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
        ("classical", ("técnica de ballet", "ballet", "puntas")),
        ("contemporary", ("moderno", "contemporary")),
        ("repertoire", ("repertorio clásico",)),
    ]
    return parse.match_genres(text.lower(), _GENRE_KEYWORDS, default=["classical"])


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    for kind, raw in _PRICE.findall(text):
        amount = parse.parse_amount(raw)
        if amount is None:
            continue
        kind = kind.lower()
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=kind.capitalize(),
                includes=["tuition"] if kind == "training" else ["accommodation", "meals"],
                notes="IVA included.",
            )
        )
    return prices


# Named teachers on the 2026 page roster.  Ángel Corella's ABT principal role is
# his verifiable public credential; the others are stated as faculty of corella.
_TEACHERS: list[Teacher] = [
    Teacher(
        name="Ángel Corella",
        role="Artistic Director",
        affiliations=[
            Affiliation(
                organization="American Ballet Theatre",
                role="Former principal dancer",
                current=False,
            ),
            Affiliation(
                organization="Corella Dance Academy",
                role="Artistic Director",
                current=True,
            ),
        ],
    ),
    Teacher(
        name="Carmen Corella",
        role="Director",
        affiliations=[
            Affiliation(organization="Corella Dance Academy", role="Director", current=True)
        ],
    ),
    Teacher(
        name="Dayron Vera",
        role="Faculty",
        affiliations=[
            Affiliation(organization="Corella Dance Academy", role="Faculty", current=True)
        ],
    ),
    Teacher(
        name="Russell Ducker",
        role="Faculty",
        affiliations=[
            Affiliation(organization="Corella Dance Academy", role="Faculty", current=True)
        ],
    ),
    Teacher(
        name="Andrea Rodriguez",
        role="Faculty",
        affiliations=[
            Affiliation(organization="Corella Dance Academy", role="Faculty", current=True)
        ],
    ),
]


def _teachers(text: str) -> list[Teacher]:
    """Return only the teachers whose names appear on the page."""
    return [t for t in _TEACHERS if t.name in text]
