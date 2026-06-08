"""Pacific Northwest Ballet School — Summer Intensive — Seattle (Washington), US.

API FIRST — pnb.org is WordPress (`/wp-json/` 200). Unlike the SAB/ABT/Boston
trap (Elementor page builders that render nothing into `content.rendered`), PNB's
pages DO serve usable bodies over the REST API: the program text is present in
`content.rendered` (interleaved with Elementor CSS, which we strip). So this is
an API scrape of two pages by slug — no HTML page fetch, no proxy:
  - `pages?slug=summer-intensive` — the program detail page (ages, curriculum →
    genres, level-based tuition, audition policy).
  - `pages?slug=summer` — the "Summer at PNB School" hub, which carries the one
    line of dated schedule for the Summer Intensive ("July 6 – August 7, 2026");
    the detail page itself states no dates.

DISCOVERY: PNB School runs ONE Summer Intensive edition per year (ages 12-19, a
single ~five-week residential program in Seattle) → one Offering
(`pacific-northwest-ballet-school/summer-intensive-{year}`). Tuition differs by
level (Levels IV & V vs VI–Advanced C) but the dates/ages/audition are shared, so
the levels are two `Price`s on one Offering, not separate Offerings. Out of scope
on the summer hub, not emitted: the Eastside Summer Dance Workshops (ages 5-7),
Summer Saturdays (ages 2-7), and the Summer Day Program (ages 8-14,
intermediate) — recreational/intro, not the high-level student intensive.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - PRICES in USD, two per offering keyed by level band, both tuition-only
    ("Tuition for Levels IV & V costs a total of $2,680. Tuition for Levels VI,
    VII, VIII, and Advanced C costs $2,990."). Housing is offered but no fee is
    published on these pages, so no accommodation Price is emitted.
  - DATES from a single year-stamped range on the hub ("July 6 – August 7, 2026").
  - AGES from "ages 12 –19" (en dash with stray spaces; the detail page).
  - GENRES from the curriculum list, not prose: Technique (→ classical), Pointe,
    Variations (→ repertoire), Modern (→ contemporary), Character. Hip Hop / Jazz
    / Pas de Deux are listed but aren't register genres, so they add nothing.
  - REQUIREMENTS = VIDEO (unspecific): admission is by audition (in-person on the
    winter national tour, or video for those who cannot attend) — the same
    audition-or-video shape as SAB/Boston. No fixed deadline is published (the
    registration window is relative to each dancer's acceptance), so application
    status/deadline stay None.
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
    Level,
    Location,
    Offering,
    Organization,
    Price,
    Requirement,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://www.pnb.org"
TZ = "America/Los_Angeles"
SLUG = "pacific-northwest-ballet-school"
DETAIL_URL = f"{BASE}/school/summer/summer-intensive/"

ORG = Organization(
    name="Pacific Northwest Ballet School",
    slug=SLUG,
    country="US",
    city="Seattle",
)
LOCATION = Location(venue="The Phelps Center", city="Seattle", country="US")


def scrape(client: httpx.Client) -> list[Offering]:
    detail = _fetch_page_text(client, "summer-intensive")
    hub = _fetch_page_text(client, "summer")
    return _build_offerings(detail, hub, date.today())


def _fetch_page_text(client: httpx.Client, slug: str) -> str:
    """Fetch a WordPress page by slug and return its `content.rendered` as text."""
    resp = client.get(f"{BASE}/wp-json/wp/v2/pages", params={"slug": slug})
    resp.raise_for_status()
    pages = resp.json()
    if not pages:
        return ""
    return _render_text(pages[0]["content"]["rendered"])


def _render_text(rendered: str) -> str:
    """Strip Elementor `<style>`/`<script>` blocks and collapse HTML to plain text."""
    tree = HTMLParser(rendered)
    for node in tree.css("style, script"):
        node.decompose()
    return parse.clean(tree.text(separator=" "))


def _build_offerings(detail: str, hub: str, today: date) -> list[Offering]:  # noqa: ARG001
    start, end = _dates(hub)
    if start is None:
        return []
    year = start.year

    return [
        Offering(
            id=f"{SLUG}/summer-intensive-{year}",
            source=Source(provider=SLUG, url=DETAIL_URL, scrapedAt=now_utc()),
            title="Summer Intensive",
            genres=_genres(detail),
            # The admission sentence ("offers advanced ballet students …") lives on
            # the hub block, not the detail page.
            level=_levels(hub),
            ageRange=parse.extract_age_range(detail, _AGE),
            organization=ORG,
            location=LOCATION,
            schedule=Schedule(season=str(year), start=start, end=end, timezone=TZ),
            prices=_prices(detail),
            application=Application(
                url=DETAIL_URL,
                requirements=_requirements(detail),
            ),
        )
    ]


# --- dates -------------------------------------------------------------------

# "July 6 – August 7, 2026" — single range, year stated once at the end. The hub
# lists several summer programs each with their own "Schedule …"; anchor on the
# "PNB School Summer Intensive" heading and take the first dated "Schedule" after
# it (the Day Program's identical span sits earlier in the page, so order matters).
_RANGE = re.compile(
    r"PNB School Summer Intensive[\s\S]*?Schedule\s+"
    rf"({parse.MONTHALT})\s+(\d{{1,2}})\s*[-–]\s*"
    rf"({parse.MONTHALT})\s+(\d{{1,2}}),\s*(\d{{4}})",
    re.IGNORECASE,
)


def _dates(text: str) -> tuple[date | None, date | None]:
    return parse.parse_multi_month_range(text, _RANGE)


# --- ages --------------------------------------------------------------------

# "ages 12 –19" — en dash with a stray leading space (Elementor's rendered text).
_AGE = re.compile(r"ages\s+(\d{1,2})\s*[-–]\s*(\d{1,2})", re.IGNORECASE)


# --- levels ------------------------------------------------------------------


# PNB grades by numbered levels (IV–VIII, Advanced C) rather than the register's
# named bands. The Summer Intensive admits "advanced ballet students"; mark it
# advanced when the admission sentence says so.
def _levels(text: str) -> list[Level]:
    return ["advanced"] if re.search(r"advanced ballet students", text, re.IGNORECASE) else []


# --- genres ------------------------------------------------------------------

# Keyword-matched against the curriculum list ("Technique, Pointe, Variations,
# Pas de Deux, Modern, Hip Hop, Jazz, Character") — not loose prose. Hip Hop /
# Jazz / Pas de Deux aren't register genres, so they add nothing.
_GENRES: list[tuple[Genre, tuple[str, ...]]] = [
    ("pointe", ("pointe",)),
    ("repertoire", ("variations", "repertoire")),
    ("contemporary", ("modern", "contemporary")),
    ("character", ("character",)),
]


def _genres(text: str) -> list[Genre]:
    return ["classical", *parse.match_genres(text, _GENRES, default=[])]


# --- prices ------------------------------------------------------------------

# Two tuition figures keyed by level band, both tuition-only:
# "Tuition for Levels IV & V costs a total of $2,680. Tuition for Levels VI, VII,
# VIII, and Advanced C costs $2,990."
_PRICES: list[tuple[str, re.Pattern]] = [
    (
        "Tuition (Levels IV & V)",
        re.compile(r"Levels?\s+IV\s*&\s*V\b[^$]*\$([\d,]+)", re.IGNORECASE),
    ),
    (
        "Tuition (Levels VI–VIII & Advanced C)",
        re.compile(r"Levels?\s+VI[^$]*Advanced\s+C[^$]*\$([\d,]+)", re.IGNORECASE),
    ),
]


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    for label, pattern in _PRICES:
        m = pattern.search(text)
        if m is None:
            continue
        amount = parse.parse_amount(m.group(1))
        if amount is None:
            continue
        prices.append(Price(amount=amount, currency="USD", label=label, includes=["tuition"]))
    return prices


# --- requirements ------------------------------------------------------------


def _requirements(text: str) -> list[Requirement]:
    """Admission is by audition — in person on the winter tour, or a video for
    those who cannot attend — so the requirement is an open-brief video. Only
    emitted when the page actually states the audition policy.
    """
    low = text.lower()
    if "requires an audition" in low or "video auditions are accepted" in low:
        return [
            VideoReq(
                specificity="unspecific",
                description=(
                    "Admission is by audition — attend an in-person audition on PNB "
                    "School's national audition tour or, if unable to attend, submit a "
                    "video for consideration."
                ),
            )
        ]
    return []
