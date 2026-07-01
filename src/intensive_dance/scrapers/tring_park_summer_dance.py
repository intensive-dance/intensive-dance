"""Tring Park School — Summer Dance Course (Tring, GB).

API FIRST: tringpark.com is WordPress (clean `/wp-json/`), but the holiday-course
detail is a server-rendered page whose fields sit in stable theme classes
(`div.event-date`, `div.event-ages`, `div.event-cost`, each a `<span>` label +
value) and a Day-Pupils/Boarders fee table (`div.left` label ↔ `div.right`
amount). So a plain `selectolax` scrape, no REST needed.

DISCOVERY: one dated Summer Dance Course per year → a single `Offering`. The two
fee rows (Day Pupils / Boarders) are booking options for the *same* course, so
they're two `Price`s on one Offering, not two Offerings.

WHAT WE EXTRACT (verified live 2026-07-01):
  - DATES: "9th August 2026 - 13th August 2026" (ordinal-suffixed, English
    month names).
  - AGES: "10 - 16" from the ages field.
  - GENRES: "Classical Ballet, Classical Repertoire, Contemporary and Jazz" —
    classical + repertoire + contemporary (jazz is out of scope for a ballet
    register).
  - PRICES: Day Pupils £457 (meals: lunch + tea) and Boarders £630
    (accommodation + all meals), both GBP, VAT-inclusive.
  - LOCATION: Park Studios, Tring Park School, Tring, GB.
  - APPLICATION: open booking on the website (no audition — payment secures the
    place); booking closes ~4 weeks before the start.

WHAT THIS SCRAPER EXERCISES: server-rendered WP page outside the REST API;
label/value theme-class fields; ordinal English date range; multi-Price single
Offering (day vs boarding) with accommodation/meals includes; out-of-scope genre
drop; raise-on-degraded fetch.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser, Node

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    Price,
    PriceInclude,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.tringpark.com"
PAGE = f"{BASE}/holiday-courses/summer-residential-dance-course-2/"

ORG = Organization(
    name="Tring Park School", slug="tring-park-summer-dance", country="GB", city="Tring"
)
VENUE = "Park Studios, Tring Park School"

# "9th August 2026 - 13th August 2026" — ordinal day, English month, year on both.
_RANGE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+(" + parse.MONTHALT + r")\s+(\d{4})"
    r"\s*[-–]\s*(\d{1,2})(?:st|nd|rd|th)?\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
_AGE = re.compile(r"(\d{1,2})\s*[-–]\s*(\d{1,2})")

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical ballet", "ballet")),
    ("repertoire", ("repertoire",)),
    ("contemporary", ("contemporary",)),
]

# Boarders' fee bundles a bed and all meals; day pupils get lunch + afternoon tea.
_FEE_INCLUDES: dict[str, list[PriceInclude]] = {
    "boarders": ["tuition", "accommodation", "meals"],
    "day pupils": ["tuition", "meals"],
}


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return [_build_offering(resp.text)]


def _field(tree: HTMLParser, cls: str) -> str:
    """The value of an `event-<cls>` block (its text minus the `<span>` label)."""
    node = tree.css_first(f"div.event-{cls}")
    if not node:
        return ""
    label = node.css_first("span")
    text = node.text()
    return parse.clean(text.replace(label.text(), "", 1) if label else text)


def _build_offering(html: str) -> Offering:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()

    m = _RANGE.search(_field(tree, "date"))
    if not m:
        raise ValueError("Tring Park: no Summer Dance Course date range (degraded fetch?)")
    start = date(int(m.group(3)), parse.MONTHS[m.group(2).lower()], int(m.group(1)))
    end = date(int(m.group(6)), parse.MONTHS[m.group(5).lower()], int(m.group(4)))
    season = str(start.year)

    body = tree.body.text(separator=" ") if tree.body else ""

    return Offering(
        id=f"{ORG.slug}/summer-dance-course-{season}",
        source=Source(provider=ORG.slug, url=PAGE, scrapedAt=now_utc()),
        title=f"Summer Dance Course {season}",
        genres=parse.match_genres(body, _GENRE_KEYWORDS, default=["classical"]),
        ageRange=_age_range(_field(tree, "ages")),
        organization=ORG,
        location=Location(venue=VENUE, city="Tring", country="GB"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/London",
            notes=_field(tree, "date") or None,
        ),
        prices=_prices(tree),
        application=Application(url=PAGE),
    )


def _age_range(text: str) -> dict | None:
    m = _AGE.search(text)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _prices(tree: HTMLParser) -> list[Price]:
    prices: list[Price] = []
    for left in tree.css("div.left"):
        parent: Node | None = left.parent
        right = parent.css_first("div.right") if parent else None
        if not right:
            continue
        label = parse.clean(left.text())
        includes = _FEE_INCLUDES.get(label.lower())
        if not includes:
            continue
        amount = parse.parse_amount(right.text().replace("£", ""))
        if amount is None:
            continue
        prices.append(
            Price(
                amount=amount,
                currency="GBP",
                label=label,
                includes=includes,
                notes="VAT-inclusive.",
            )
        )
    return prices
