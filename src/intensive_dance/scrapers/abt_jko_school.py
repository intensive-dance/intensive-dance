"""American Ballet Theatre — JKO School Summer Intensives — New York, US.

API FIRST — tried, none usable. abt.org is WordPress, but the page body is
assembled by a custom module/ACF builder that renders nothing into
`content.rendered` and exposes only module *names* (not their data) over the
REST API. So this is an HTML scrape (selectolax) of the one Summer Intensives
page, which lays its three sites out as a tidy `.accordion-wrap` of
`.accordion-item`s — one per site, each with a four-column table
(Age Group · Cost · Location · Housing).

DISCOVERY: three sibling intensives on the single page — New York (5 weeks),
Florida (3 weeks, USF Tampa) and California (2 weeks, CSU Long Beach). They
differ in dates, ages, fees and housing, so each becomes its own `Offering`
(`abt-jko-school/{site}-{season}`), the same per-location split RMB makes.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-05):
  - PRICES in USD, multiple per offering — Florida lists Tuition + a Day Student
    Fee + Room and Board in one Cost cell; we emit one `Price` per labelled line
    and map "Room and Board" → accommodation+meals.
  - REQUIREMENTS = VIDEO (unspecific). Admission is by audition: in person on
    ABT's National Audition Tour *or* a video submission — the open-brief video
    branch. Shared across all three sites (one audition feeds all).
  - TEACHERS with AFFILIATIONS — the New York prose names ABT Artistic Director
    Susan Jaffe as a guest teacher; resolved to an `American Ballet Theatre`
    affiliation. Florida/California cite only unnamed "ABT faculty" → none.
  - opensAt — auditions pre-register from a stated date ("November 1, 2025"); no
    hard application deadline is published, so `deadline`/`status` stay unset.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser, Node

from intensive_dance import parse
from intensive_dance.models import (
    Affiliation,
    Application,
    Genre,
    Level,
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

BASE = "https://www.abt.org"
PAGE = f"{BASE}/training/dancer-training/summer-programs/summer-intensives/"
AUDITION_PAGE = f"{BASE}/training/dancer-training/summer-programs/audition-info/"

ORG = Organization(
    name="American Ballet Theatre — JKO School",
    slug="abt-jko-school",
    country="US",
    city="New York",
)

# Site name (as it heads its accordion) → the slug we key the offering on and the
# IANA zone for its schedule. The page never spells the state out, so this is
# also where "which coast" is decided.
_SITES: dict[str, tuple[str, str]] = {
    "new york": ("new-york", "America/New_York"),
    "florida": ("florida", "America/New_York"),
    "california": ("california", "America/Los_Angeles"),
}


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text, date.today())


def _build_offerings(html: str, today: date) -> list[Offering]:  # noqa: ARG001 — see opensAt note
    tree = HTMLParser(html)
    wraps = tree.css(".accordion-wrap")
    if not wraps:
        return []

    page_text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""
    requirements = _requirements(page_text)
    opens_at = _opens_at(page_text)

    offerings: list[Offering] = []
    # The first accordion-wrap holds the per-site items; later wraps are
    # curriculum/tuition/scholarship prose shared across all three.
    for item in wraps[0].css(".accordion-item"):
        title_node = item.css_first(".accordion-item-title")
        body_node = item.css_first(".accordion-item-content")
        if title_node is None or body_node is None:
            continue
        title = parse.clean(title_node.text())
        site = next((s for key, s in _SITES.items() if key in title.lower()), None)
        if site is None:
            continue
        slug, tz = site

        prose = parse.clean(body_node.text(separator=" "))
        start, end = _dates(prose)
        if start is None:
            continue
        season = str(start.year)

        cells = _value_cells(body_node)
        offerings.append(
            Offering(
                id=f"abt-jko-school/{slug}-{season}",
                source=Source(provider="abt-jko-school", url=PAGE, scrapedAt=now_utc()),
                title=title,
                genres=_genres(prose),
                kind="intensive",
                level=_levels(prose),
                ageRange=_age_range(_cell_text(cells.get("age"))),
                organization=ORG,
                location=_location(cells.get("location")),
                schedule=Schedule(season=season, start=start, end=end, timezone=tz),
                teachers=_teachers(prose),
                prices=_prices(_cell_text(cells.get("cost"))),
                application=Application(
                    opensAt=opens_at,
                    url=AUDITION_PAGE,
                    requirements=requirements,
                ),
            )
        )
    return offerings


# --- table -------------------------------------------------------------------


def _value_cells(body: Node) -> dict[str, Node]:
    """Map the site table's value-row cells to {age, cost, location, housing}.

    The table is a header row (Age Group · Cost · Location · Housing) followed by
    one value row; we key the value cells by matching the header text rather than
    by fixed column index, so a reordered table degrades to missing keys, not
    wrong ones. Cells are returned as nodes (not text) because the location cell's
    `<p>` line structure carries the venue/city split — collapsing it would glue
    a street number onto the city name.
    """
    table = body.css_first("table")
    if table is None:
        return {}
    rows = [tr.css("td, th") for tr in table.css("tr")]
    if len(rows) < 2:
        return {}
    headers, values = rows[0], rows[1]
    keys = {"age group": "age", "cost": "cost", "location": "location", "housing": "housing"}
    out: dict[str, Node] = {}
    for head, cell in zip(headers, values):
        key = keys.get(parse.clean(head.text()).lower())
        if key:
            out[key] = cell
    return out


def _cell_text(cell: Node | None) -> str:
    return parse.clean(cell.text(separator=" ")) if cell is not None else ""


# --- parsing -----------------------------------------------------------------

# "June 22 – July 24, 2026" — both bounds carry an explicit month; the year is
# stated once, at the end, and applies to both.
_RANGE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})\s*[-–]\s*"
    r"(" + parse.MONTHALT + r")\s+(\d{1,2}),?\s*(\d{4})",
    re.IGNORECASE,
)
_AGE = re.compile(r"\b(\d{1,2})\s*[-–]\s*(\d{1,2})\b")
_FEE = re.compile(r"([A-Za-z][A-Za-z &]*?):\s*\$\s*([\d,]+)\s*USD", re.IGNORECASE)
_OPENS = re.compile(
    r"pre-registration will open on (" + parse.MONTHALT + r")\s+(\d{1,2}),?\s*(\d{4})",
    re.IGNORECASE,
)
_GUEST = re.compile(r"Artistic Director ([A-Z][a-z]+(?: [A-Z][a-z]+)+)")


def _dates(text: str) -> tuple[date | None, date | None]:
    match = _RANGE.search(text)
    if not match:
        return None, None
    m1, d1, m2, d2, year = match.groups()
    y = int(year)
    return (
        date(y, parse.MONTHS[m1.lower()], int(d1)),
        date(y, parse.MONTHS[m2.lower()], int(d2)),
    )


def _age_range(text: str) -> dict | None:
    match = _AGE.search(text)
    return {"min": int(match.group(1)), "max": int(match.group(2))} if match else None


_LEVELS: list[tuple[Level, tuple[str, ...]]] = [
    ("beginner", ("beginner",)),
    ("intermediate", ("intermediate",)),
    ("advanced", ("advanced",)),
    ("pre-professional", ("pre-professional",)),
]


def _levels(text: str) -> list[Level]:
    low = text.lower()
    return [lvl for lvl, keys in _LEVELS if any(k in low for k in keys)]


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet", "technique")),
    ("repertoire", ("repertory", "repertoire")),
    ("pointe", ("pointe",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# Cost-line label → what the fee covers. A bare "Tuition" or "Day Student Fee"
# carries no extra inclusion beyond tuition itself.
_INCLUDES: list[tuple[str, tuple[PriceInclude, ...]]] = [
    ("room and board", ("accommodation", "meals")),
    ("tuition", ("tuition",)),
]


def _prices(cost: str) -> list[Price]:
    prices: list[Price] = []
    for label, amount in _FEE.findall(cost):
        value = parse.parse_amount(amount)
        if value is None:
            continue
        label = parse.clean(label)
        low = label.lower()
        includes = next(
            (list(inc) for key, inc in _INCLUDES if key in low),
            [],
        )
        prices.append(Price(amount=value, currency="USD", label=label, includes=includes))
    return prices


# "City, ST 12345" — the address line we lift the city from (the state is always
# US, so we don't keep it separately).
_CITY = re.compile(r"^(.+?),\s*[A-Z]{2}\s+\d{5}\b")


def _location(cell: Node | None) -> Location | None:
    if cell is None:
        return None
    lines = [parse.clean(p.text()) for p in cell.css("p")]
    lines = [line for line in lines if line]
    if not lines:
        return None
    venue = lines[0]
    city = next(
        (m.group(1) for line in lines if (m := _CITY.match(line))),
        None,
    )
    return Location(venue=venue, city=city, country="US")


def _teachers(prose: str) -> list[Teacher]:
    teachers: list[Teacher] = []
    for name in _GUEST.findall(prose):
        teachers.append(
            Teacher(
                name=name,
                role="guest teacher",
                affiliations=[
                    Affiliation(
                        organization="American Ballet Theatre",
                        slug="american-ballet-theatre",
                        role="Artistic Director",
                        current=True,
                    )
                ],
            )
        )
    return teachers


def _opens_at(text: str) -> date | None:
    match = _OPENS.search(text)
    if not match:
        return None
    month, day, year = match.groups()
    return date(int(year), parse.MONTHS[month.lower()], int(day))


def _requirements(text: str):
    """Admission is by audition — in person on the National Audition Tour or a
    video submission — so the relevant requirement is an open-brief video. We
    only emit it when the page actually describes the audition (it's the same
    process for all three sites), defaulting to nothing otherwise.
    """
    low = text.lower()
    if "video audition" in low or ("audition" in low and "video" in low):
        return [
            VideoReq(
                specificity="unspecific",
                description=(
                    "Audition in person on ABT's National Audition Tour or submit a "
                    "video audition; online pre-registration required."
                ),
            )
        ]
    return []
