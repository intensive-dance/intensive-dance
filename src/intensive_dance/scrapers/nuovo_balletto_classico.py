"""Nuovo Balletto Classico — Reggio Emilia, IT — its summer perfezionamento courses.

API FIRST: WordPress, but the site **blocks direct datacenter fetches outright**
(a plain request returns nothing) and `/wp-json/` is unreachable that way. The
fetch proxy's `auto=1` tier clears it and returns the server-rendered
`/corsi-estivi-YYYY/` page; the page is built with LayerSlider so its blocks
repeat — we parse by content, deduping.

DISCOVERY: one summer programme per year ("Corsi estivi 2026"), a single dated
window split into age bands (10–12, 13–15, 16+) and personalizable by intensity
(1–3 weeks, 1–6 lessons/day). We emit **one Offering** for the edition; the age
bands and week/lesson flexibility are notes, and each intensity tier is a Price.

WHAT WE EXTRACT (verified live 2026-06-26):
  - DATES: "Dal 29 giugno al 18 luglio 2026" (local Italian month map).
  - GENRES: "danza classica e punte / repertorio e passo a due / danza di
    carattere e contemporanea" → classical + pointe + repertoire + character +
    contemporary.
  - AGES: "dai 10 anni in su" with bands to 16+ → min 10, open upper bound.
  - PRICES: the weekly tiers "Percorso <name> (<N> lezioni/giorno): € <amt>"
    (deduped), plus the residential full-board package ("330 € a settimana",
    meals + transport).
  - APPLICATION: "Sono aperte le iscrizioni" → status open; entry is open
    enrollment with a free personalized quote (no audition material stated).

SCOPE CALL: the faculty is a rotating "docenti interni e ospiti" roster whose
bios run together in the duplicated slider markup (and carry a name-spelling
variant) — not cleanly attributable per-person, so teachers are left empty
rather than over-claimed (cf. Joffrey/ENBS/BIB).

WHAT THIS SCRAPER EXERCISES: proxy `auto=1` for a datacenter-blocked WP site;
LayerSlider dedup; Italian date range; multi-Price intensity tiers + residential
package; five-genre offering; open-topped age; raise-on-degraded-fetch.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
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

BASE = "https://www.nuovoballettoclassico.it"
PAGE = f"{BASE}/corsi-estivi-2026/"

ORG = Organization(
    name="Nuovo Balletto Classico",
    slug="nuovo-balletto-classico",
    country="IT",
    city="Reggio Emilia",
)

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

_RANGE = re.compile(
    r"Dal\s+(\d{1,2})\s+(" + _MONTH_IT + r")\s+al\s+(\d{1,2})\s+(" + _MONTH_IT + r")\s+(\d{4})",
    re.IGNORECASE,
)
_AGE_MIN = re.compile(r"dai\s+(\d{1,2})\s+anni\s+in\s+su", re.IGNORECASE)
# The tier name is a short letters-only run immediately before "(N lezioni/giorno)";
# bounding length + excluding punctuation stops it swallowing a preceding bio
# paragraph that also happens to start with the word "Percorso".
_TIER = re.compile(
    r"Percorso\s+([A-Za-zÀ-ÿ ]{2,22}?)\s*\((\d+)\s*lezion[ei]/giorno\)\s*:?\s*€\s*([\d.,]+)",
    re.IGNORECASE,
)
_RESIDENTIAL = re.compile(r"(\d{2,4})\s*€\s*a\s+settimana", re.IGNORECASE)
_OPEN = re.compile(r"aperte\s+le\s+iscrizioni", re.IGNORECASE)

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("danza classica",)),
    ("pointe", ("punte", "punta")),
    ("repertoire", ("repertorio",)),
    ("character", ("carattere",)),
    ("contemporary", ("contemporanea", "contemporaneo")),
]
_APPLY_NOTE = "Open enrollment; request a free personalized quote. No audition material stated."
_SCHED_NOTE = (
    "Perfezionamento courses, personalizable 1–3 weeks, 1–6 lessons/day. "
    "Age bands 10–12, 13–15, 16+."
)


def scrape(client: httpx.Client) -> list[Offering]:
    # Direct datacenter fetches are blocked; the proxy auto-escalation tier returns
    # the server-rendered page.
    resp = client.get(PAGE, headers={PROXY_PARAMS_HEADER: "auto=1"})
    resp.raise_for_status()
    return [_build_offering(resp.text)]


def _build_offering(html: str) -> Offering:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ") if tree.body else "")

    m = _RANGE.search(text)
    if not m:
        raise ValueError("Nuovo Balletto Classico: no summer date range found (degraded fetch?)")
    year = int(m.group(5))
    start = date(year, _ITALIAN_MONTHS[m.group(2).lower()], int(m.group(1)))
    end = date(year, _ITALIAN_MONTHS[m.group(4).lower()], int(m.group(3)))
    season = str(year)

    return Offering(
        id=f"nuovo-balletto-classico/corsi-estivi-{season}",
        source=Source(provider="nuovo-balletto-classico", url=PAGE, scrapedAt=now_utc()),
        title=f"Corsi Estivi {season}",
        genres=_genres(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue="Nuovo Balletto Classico", city="Reggio Emilia", country="IT"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Rome",
            notes=_SCHED_NOTE,
        ),
        prices=_prices(text),
        application=Application(
            status="open" if _OPEN.search(text) else None, url=PAGE, notes=_APPLY_NOTE
        ),
    )


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _age_range(text: str) -> dict | None:
    m = _AGE_MIN.search(text)
    return {"min": int(m.group(1))} if m else None  # bands up to "16+" → upper open


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    seen: set[str] = set()
    for m in _TIER.finditer(text):
        tier = parse.clean(m.group(1))
        lessons = m.group(2)
        amount = parse.parse_amount(m.group(3))
        key = tier.lower()
        if amount is None or key in seen:
            continue
        seen.add(key)
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=f"Percorso {tier} ({lessons} lessons/day)",
                includes=["tuition"],
                notes="Per week.",
            )
        )
    rm = _RESIDENTIAL.search(text)
    if rm and (amount := parse.parse_amount(rm.group(1))) is not None:
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label="Residential package",
                includes=["accommodation", "meals"],
                notes="Per week; Sunday dinner to Saturday lunch, meals and transport included.",
            )
        )
    return prices
