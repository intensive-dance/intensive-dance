"""Europaballett St. Pölten — the "Danceflash" summer intensive (Sommerworkshop).

API FIRST
Plain static HTML (no WordPress REST / `/wp-json/`, not Joomla, no `ld+json`,
no `__NEXT_DATA__`) — a structural `selectolax` text scrape of the single
Danceflash detail page (`/ausbildung/danceflash`). The host 403s a datacenter
fetch, so the scrape runs through the fetch proxy (`make_client` routes it
automatically when the proxy env is set). German/English mixed copy — and the
`en.` subdomain flips the PARTICIPATION-FEE block between German ("5-12 Jährige
täglich von …") and English ("5-12 year olds daily from …") by cache, so the
fee regex matches both wordings (cf. the Monreart language-by-cache trap).

DISCOVERY — one age-group track = one Offering.
Danceflash is the dated 8-day summer workshop of the state-funded Europaballett
Konservatorium (Land NÖ). The PARTICIPATION-FEE block splits the same edition
into two operational groups with their own daily schedule and fee:
  * "5-12 Jährige" — 09:30–14:30, € 300 (early bird € 280)
  * "13-26 Jährige" — 09:30–16:00, € 400 (early bird € 380)
Those are distinct ages/hours/prices, so we emit ONE Offering per group rather
than fold them (folding would lose the per-group fee/age/schedule). Both share
the same dates, location, faculty and curriculum. The closing gala (12 Juli) is
a performance, not a separate course, and is not emitted.

The registration form collects ballet experience but offers "No experience yet"
as a valid answer — open enrollment, no audition gate — so
`application.requirements` stays empty.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-12)
- Two Offerings from one page (age-group fee table → min/max + per-group fee).
- German worded day span ("04. Juli - 11. Juli 2026" / "4. bis 11. Juli 2026").
- Multi-genre ballet intensive: the weekly plan and faculty teach classical +
  Balanchine (neoclassical) + pointe + repertoire + contemporary (Jazz/Hip-Hop
  also run but have no genre-enum value, so they're simply not emitted).
- Early-bird fee captured in the Price note; € price in German "300,-" notation.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
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
    now_utc,
)

SLUG = "europaballett-danceflash"
PAGE = "https://en.europaballett.at/ausbildung/danceflash"

ORG = Organization(name="Europaballett St. Pölten", slug=SLUG, country="AT", city="St. Pölten")
VENUE = Location(city="St. Pölten", country="AT")

_MONTHS = {
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}
_MONTHALT = parse.months_alt(_MONTHS)

# "04. JuLi - 11. Juli 2026" or "4. bis 11. Juli 2026" → day–day Month Year.
# The optional letters between the first day and the separator absorb a repeated
# leading month word ("04. JuLi - …"); "bis" is also accepted as the separator.
_DATES = re.compile(
    r"(\d{1,2})\.\s*(?:[A-Za-zäöü]+\s+)?(?:[-–]|bis)\s*(\d{1,2})\.\s*("
    + _MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)

# One PARTICIPATION-FEE row per age group. The `en.` subdomain flips this block
# between German and English by cache, so match both wordings:
#   "5-12 Jährige täglich von 09:30 - 14:30 Uhr € 300,- (Early bird … € 280,-)"
#   "5-12 year olds daily from 09:30 - 14:30 € 300,-"
# "Uhr" and the early-bird parenthetical are both optional.
_FEE = re.compile(
    r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:Jährige|year olds)\s+(?:täglich\s+von|daily\s+from)\s+"
    r"([\d:]+)\s*[-–]\s*([\d:]+)\s*(?:Uhr\s*)?€\s*([\d.,]+)"
    r"[,\-]*\s*/?\s*(?:\(\s*Early bird[^€]*€\s*([\d.,]+))?",
    re.IGNORECASE,
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text)


def _text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript, nav, header, footer"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _dates(text: str) -> tuple[date | None, date | None, str | None]:
    m = _DATES.search(text)
    if not m:
        return None, None, None
    d1, d2, mon, year = m.groups()
    month = _MONTHS[mon.lower()]
    y = int(year)
    return date(y, month, int(d1)), date(y, month, int(d2)), parse.clean(m.group(0))


def _genres(text: str) -> list[Genre]:
    low = text.lower()
    table: list[tuple[Genre, tuple[str, ...]]] = [
        ("classical", ("classical training", "klassisch")),
        ("contemporary", ("contemporary",)),
        ("neoclassical", ("balanchine",)),
        ("repertoire", ("repertoire",)),
        ("pointe", ("point", "spitze")),
    ]
    return [g for g, keys in table if any(k in low for k in keys)]


def _build_offering(
    age_min: str,
    age_max: str,
    t1: str,
    t2: str,
    fee: str,
    early: str | None,
    *,
    start: date | None,
    end: date | None,
    date_notes: str | None,
    genres: list[Genre],
    season: str,
) -> Offering | None:
    amount = parse.parse_amount(fee)
    if amount is None:
        return None
    lo, hi = int(age_min), int(age_max)
    early_amount = parse.parse_amount(early) if early else None
    price = Price(
        amount=amount,
        currency="EUR",
        includes=["tuition"],
        notes=(f"Early bird: € {early_amount:.0f}" if early_amount is not None else None),
    )
    schedule_bits = [b for b in (date_notes, f"täglich {t1}–{t2} Uhr") if b]
    return Offering(
        id=f"{SLUG}/summer-intensive-{season}-ages-{lo}-{hi}",
        source=Source(provider=SLUG, url=PAGE, scrapedAt=now_utc()),
        title=f"Danceflash Summer Intensive (ages {lo}–{hi})",
        genres=genres,
        ageRange={"min": lo, "max": hi},
        organization=ORG,
        location=VENUE,
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Vienna",
            notes="; ".join(schedule_bits) or None,
        ),
        prices=[price],
        application=Application(url=PAGE),
    )


def _build_offerings(html: str) -> list[Offering]:
    text = _text(html)
    start, end, date_notes = _dates(text)
    season = str(start.year) if start else "2026"
    genres = _genres(text)
    offerings: list[Offering] = []
    for m in _FEE.finditer(text):
        age_min, age_max, t1, t2, fee, early = m.groups()
        offering = _build_offering(
            age_min,
            age_max,
            t1,
            t2,
            fee,
            early,
            start=start,
            end=end,
            date_notes=date_notes,
            genres=genres,
            season=season,
        )
        if offering is not None:
            offerings.append(offering)
    return offerings
