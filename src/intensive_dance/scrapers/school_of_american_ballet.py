"""School of American Ballet — Summer programs — New York, US.

API FIRST — tried, none usable. sab.org is WordPress, but every program page is
assembled by a page builder that renders *nothing* into `content.rendered` over
the REST API (the same trap ABT hits). So this is an HTML scrape (selectolax) of
the two public summer-program pages, which share one template: an `<h1>` title,
prose under a "20xx …" heading carrying the dates / ages / audition policy, and a
single two-column fee `<table>` under "Tuition Rates".

DISCOVERY: SAB runs two distinct summer intensives, each on its own page and each
its own `Offering` (`school-of-american-ballet/{program}-{season}`) — they differ
in dates, ages and fees:
  - Summer Course — five weeks, ages 12-18, intermediate/advanced.
  - New York Junior Session — one week, ages 10-12, an introductory program.
Both are year-stamped (the page headings name the cycle, e.g. "2026 …").

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-05):
  - PRICES in USD, multiple per offering from the fee table — "Tuition" →
    tuition, "Room and Board" → accommodation+meals, the rest (Registration /
    Activity / Laundry fees, Single Room Surcharge) carry no inclusion.
  - REQUIREMENTS = VIDEO (unspecific). "All students must audition" with video
    applications accepted for anyone who cannot attend in person — open-brief
    video, the same audition-or-video shape as ABT.
  - DATES across two phrasings — "June 29, 2026 – July 31, 2026" (both bounds
    dated) and "Monday, June 22 through Saturday, June 27, 2026" (weekday-prefixed,
    year stated once); one range regex covers both.
  - LEVELS read from the admission sentence only ("intermediate and advanced
    students" / "training at the intermediate level"), not loose prose — so
    "the most advanced girls" in the Junior Session blurb doesn't leak in.
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
    Level,
    Location,
    Offering,
    Organization,
    Price,
    PriceInclude,
    Requirement,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://sab.org"
TZ = "America/New_York"

ORG = Organization(
    name="School of American Ballet",
    slug="school-of-american-ballet",
    country="US",
    city="New York",
)

# (page url, offering slug) — one Offering per program page.
_PROGRAMS: list[tuple[str, str]] = [
    (f"{BASE}/enrollment/summer-course/", "summer-course"),
    (f"{BASE}/enrollment/new-york-junior-session/", "new-york-junior-session"),
]


def scrape(client: httpx.Client) -> list[Offering]:
    offerings: list[Offering] = []
    for url, slug in _PROGRAMS:
        resp = client.get(url)
        resp.raise_for_status()
        offering = _build_offering(resp.text, url, slug, date.today())
        if offering is not None:
            offerings.append(offering)
    return offerings


def _build_offering(html: str, url: str, slug: str, today: date) -> Offering | None:  # noqa: ARG001
    tree = HTMLParser(html)
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""
    start, end = _dates(text)
    if start is None:
        return None
    season = str(start.year)

    title_node = tree.css_first("h1")
    title = parse.clean(title_node.text()) if title_node is not None else slug

    # Genres come from the curriculum headings, not prose: the Junior Session's
    # Variations blurb mentions "contemporary works" without teaching a
    # Contemporary class, which the Summer Course's <h3>Contemporary</h3> does.
    headings = parse.clean(" ".join(h.text() for h in tree.css("h1, h2, h3, h4")))

    return Offering(
        id=f"school-of-american-ballet/{slug}-{season}",
        source=Source(provider="school-of-american-ballet", url=url, scrapedAt=now_utc()),
        title=title,
        genres=_genres(headings),
        kind="summer-school",
        level=_levels(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=_location(text),
        schedule=Schedule(season=season, start=start, end=end, timezone=TZ),
        prices=_prices(tree),
        application=Application(url=url, requirements=_requirements(text)),
    )


# --- dates -------------------------------------------------------------------

_WEEKDAY = r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
# Two live phrasings: "June 29, 2026 – July 31, 2026" (both bounds dated) and
# "Monday, June 22 through Saturday, June 27, 2026" (weekday prefixes, year only
# at the end). The first bound's year is optional and falls back to the second's.
_RANGE = re.compile(
    rf"(?:{_WEEKDAY})?"
    rf"({parse.MONTHALT})\s+(\d{{1,2}})(?:,\s*(\d{{4}}))?\s*"
    rf"(?:[-–]|through)\s*"
    rf"(?:{_WEEKDAY})?"
    rf"({parse.MONTHALT})\s+(\d{{1,2}}),?\s*(\d{{4}})",
    re.IGNORECASE,
)


def _dates(text: str) -> tuple[date | None, date | None]:
    match = _RANGE.search(text)
    if not match:
        return None, None
    m1, d1, y1, m2, d2, y2 = match.groups()
    year2 = int(y2)
    year1 = int(y1) if y1 else year2
    return (
        date(year1, parse.MONTHS[m1.lower()], int(d1)),
        date(year2, parse.MONTHS[m2.lower()], int(d2)),
    )


# --- ages --------------------------------------------------------------------

# "no younger than 12 and no older than 18" — the admission floor/ceiling. Both
# pages state it this way (alongside a looser "ages 10-12" blurb we ignore).
_AGE = re.compile(r"no younger than (\d{1,2}).*?no older than (\d{1,2})", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    match = _AGE.search(text)
    return {"min": int(match.group(1)), "max": int(match.group(2))} if match else None


# --- levels ------------------------------------------------------------------

_LEVELS_ORDER: list[Level] = [
    "beginner",
    "intermediate",
    "advanced",
    "pre-professional",
    "professional",
]
_LEVEL_WORDS = "|".join(_LEVELS_ORDER)
# Anchor on the noun ("intermediate and advanced students" / "intermediate
# level") so descriptive prose ("the most advanced girls") doesn't count.
_LEVEL_PHRASE = re.compile(
    rf"((?:{_LEVEL_WORDS})(?:\s+(?:and|or|to|,)\s*(?:{_LEVEL_WORDS}))*)"
    r"\s+(?:students|dancers|level)\b",
    re.IGNORECASE,
)


def _levels(text: str) -> list[Level]:
    found: list[Level] = []
    for match in _LEVEL_PHRASE.finditer(text):
        span = match.group(1).lower()
        for lvl in _LEVELS_ORDER:
            pattern = r"(?<!pre-)\bprofessional\b" if lvl == "professional" else rf"\b{lvl}\b"
            if re.search(pattern, span) and lvl not in found:
                found.append(lvl)
    return found


# --- genres ------------------------------------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet", "technique")),
    ("pointe", ("pointe",)),
    ("character", ("character",)),
    ("contemporary", ("contemporary",)),
    ("repertoire", ("variations", "repertoire", "repertory")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- prices ------------------------------------------------------------------

# Fee-row label → what it covers. Every other line (registration / activity /
# laundry fees, single-room surcharge) is a bare charge with no inclusion.
_INCLUDES: list[tuple[str, tuple[PriceInclude, ...]]] = [
    ("room and board", ("accommodation", "meals")),
    ("tuition", ("tuition",)),
]
_AMOUNT = re.compile(r"\$\s*([\d,]+)")


def _prices(tree: HTMLParser) -> list[Price]:
    """Read the single two-column fee table (label · $amount).

    Each page renders exactly one table — its Tuition Rates breakdown — so we take
    the first one and key inclusions off the row label, not its position.
    """
    table = tree.css_first("table")
    if table is None:
        return []
    prices: list[Price] = []
    for row in table.css("tr"):
        cells: list[Node] = row.css("td")
        if len(cells) < 2:
            continue
        label = parse.clean(cells[0].text())
        amount_match = _AMOUNT.search(parse.clean(cells[1].text()))
        if not label or amount_match is None:
            continue
        value = parse.parse_amount(amount_match.group(1))
        if value is None:
            continue
        low = label.lower()
        includes = next((list(inc) for key, inc in _INCLUDES if key in low), [])
        prices.append(Price(amount=value, currency="USD", label=label, includes=includes))
    return prices


# --- location & requirements -------------------------------------------------


def _location(text: str) -> Location:
    venue = "Lincoln Center" if "Lincoln Center" in text else None
    return Location(venue=venue, city="New York", country="US")


def _requirements(text: str) -> list[Requirement]:
    """Admission is by audition — in person or, for anyone who cannot attend, a
    video application — so the requirement is an open-brief video. Only emitted
    when the page actually states the audition policy.
    """
    low = text.lower()
    if "must audition" in low or "video application" in low:
        return [
            VideoReq(
                specificity="unspecific",
                description=(
                    "Admission is by audition — attend an in-person audition or, if "
                    "unable to attend, submit a video application."
                ),
            )
        ]
    return []
