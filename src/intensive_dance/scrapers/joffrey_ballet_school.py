"""Joffrey Ballet School — second scraper, exercises the `video` requirement.

API FIRST: Joffrey runs WordPress and exposes its programs as dedicated custom
post types over the REST API — no HTML scraping of the live site. We list three:
`summer-intensives`, `workshops`, and `master-class` (empty out of season). Each
record carries `dance_style` / `intensive_location` taxonomy ids, which we
resolve to names via `wp.fetch_terms` and map onto our genre/location enums.

DISCOVERY: one `Offering` per published program, keyed `joffrey-ballet-school/{slug}`.
Joffrey reuses an evergreen entry per program (the slug is not year-stamped), so
there is one record per program, not per cycle. Programs whose only dance style
is out of scope for a *ballet* register (Tap, Hip Hop, Cirque Arts, Musical
Theater) are dropped; ballet / contemporary-ballet / jazz-&-contemporary /
multi-genre are kept.

WHAT THE API GIVES US — and what it doesn't (verified live 2026-06-03):
  - REQUIREMENTS = VIDEO. Joffrey runs a digital audition: dancers may "submit
    your video" or audition in-person / via Zoom. This is the `video` branch RBS
    (photos-only) could not exercise; emitted as `video` / unspecific.
  - DATES are inconsistent. Workshops publish "December 28-30, 2026"-style dates
    in the body; most summer intensives don't state dates at all. We parse a range
    where present, else leave start/end null and season "unknown" (fail-open, same
    as RBS — discovery, not date-parsing, decides what's listed).
  - PRICES: none. The WooCommerce `product` namespace is enabled but has no
    products, and fees aren't in the program body — so `prices` stays empty.
  - TEACHERS: none. A `faculty` post type exists (school-wide roster) but nothing
    ties a faculty member to a specific program, so `teachers` stays empty.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    Genre,
    Kind,
    Location,
    Offering,
    Organization,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://www.joffreyballetschool.com"
AUDITIONS_SLUG = "auditions-2"

ORG = Organization(
    name="Joffrey Ballet School", slug="joffrey-ballet-school", country="US", city="New York"
)

# Each program post type, and the `kind` an Offering from it takes.
PROGRAM_TYPES: dict[str, Kind] = {
    "summer-intensives": "intensive",
    "workshops": "workshop",
    "master-class": "masterclass",
}

# dance_style term name → our genres. Styles absent here (Tap, Hip Hop, Cirque
# Arts, Musical Theater) are out of scope for a ballet register, so a program
# with no in-scope style is dropped entirely.
_GENRES_BY_STYLE: dict[str, list[Genre]] = {
    "Ballet": ["classical"],
    "Contemporary Ballet": ["contemporary"],
    "Jazz & Contemporary": ["contemporary"],
    "Multi-Genre": ["classical", "contemporary"],
}

# Workshops carry no dance_style taxonomy, so scope + genres are read from text.
# A *title* naming an out-of-scope discipline ("Hip Hop Workshop") is dropped;
# otherwise genres come from the title, falling back to the body for multi-genre
# workshops that only name a city in the title. "contemporary"/"jazz" →
# contemporary, "ballet" → classical.
_OUT_OF_SCOPE = (
    "musical theater",
    "musical theatre",
    "hip hop",
    "hip-hop",
    "cirque",
    "circus",
    "tap",
)
_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("contemporary", ("contemporary", "jazz")),
    ("classical", ("ballet",)),
]

# intensive_location term name → (city, ISO country). "All" / "International" are
# meta-buckets with no place, so they're omitted.
_LOCATIONS: dict[str, tuple[str | None, str]] = {
    "New York": ("New York", "US"),
    "California": (None, "US"),
    "Colorado": (None, "US"),
    "Florida": (None, "US"),
    "Georgia": (None, "US"),
    "Nevada": (None, "US"),
    "Texas": (None, "US"),
    "Iowa": (None, "US"),
    "Michigan": (None, "US"),
    "Ohio": (None, "US"),
    "Switzerland": (None, "CH"),
    "Italy": (None, "IT"),
    "Mexico": (None, "MX"),
}

_AUDITION_NOTE = (
    "Joffrey runs a digital audition: dancers may audition in person, virtually "
    "via Zoom, or by submitting a video for consideration."
)


def scrape(client: httpx.Client) -> list[Offering]:
    styles = wp.fetch_terms(client, "dance_style", base=BASE)
    locations = wp.fetch_terms(client, "intensive_location", base=BASE)
    audition_url = _auditions_url(client)

    today = date.today()
    offerings: list[Offering] = []
    for rest_base, kind in PROGRAM_TYPES.items():
        for record in wp.fetch_all(
            client,
            rest_base,
            base=BASE,
            params={"_fields": "id,slug,link,title,content,dance_style,intensive_location"},
        ):
            offering = _build_offering(record, kind, styles, locations, audition_url, today)
            if offering is not None:
                offerings.append(offering)
    offerings.sort(key=lambda o: o.id)
    return offerings


def _auditions_url(client: httpx.Client) -> str:
    page = wp.fetch_page(client, AUDITIONS_SLUG, base=BASE)
    return page["link"] if page else f"{BASE}/auditions/"


def _build_offering(
    record: dict,
    kind: Kind,
    styles: dict[int, str],
    locations: dict[int, str],
    audition_url: str,
    today: date,
) -> Offering | None:
    """One program record → an Offering, or None if out of scope / already ended."""
    title = wp.plain_text(record["title"]["rendered"])
    text = wp.plain_text(record["content"]["rendered"])
    genres = _genres(record.get("dance_style", []), styles, title, text)
    if not genres:
        return None  # no in-scope ballet/contemporary style → not for this register

    start, end, season = _parse_dates(text)
    city, country = _location(record.get("intensive_location", []), locations)

    return Offering(
        id=f"joffrey-ballet-school/{record['slug']}",
        source=Source(provider="joffrey-ballet-school", url=record["link"], scrapedAt=now_utc()),
        title=title,
        genres=genres,
        kind=kind,
        organization=ORG,
        location=Location(city=city, country=country) if country else None,
        schedule=Schedule(season=season, start=start, end=end),
        application=Application(
            url=audition_url,
            requirements=[VideoReq(specificity="unspecific", description=_AUDITION_NOTE)],
            notes=_AUDITION_NOTE,
        ),
    )


def _genres(term_ids: list[int], styles: dict[int, str], title: str, body: str) -> list[Genre]:
    seen: list[Genre] = []
    for term_id in term_ids:
        for genre in _GENRES_BY_STYLE.get(styles.get(term_id, ""), []):
            if genre not in seen:
                seen.append(genre)
    if seen:
        return seen
    if any(term in title.lower() for term in _OUT_OF_SCOPE):
        return []
    return _genres_from_text(title) or _genres_from_text(body)


def _genres_from_text(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS)


def _location(term_ids: list[int], locations: dict[int, str]) -> tuple[str | None, str | None]:
    for term_id in term_ids:
        place = _LOCATIONS.get(locations.get(term_id, ""))
        if place:
            return place
    return None, None


# --- dates --------------------------------------------------------------------
#
# Joffrey writes the course span as a range — "Month D–D", "Month D – Month D",
# or with a trailing year ("December 28-30, 2026"). We only trust a *range* for
# start/end: lone dates in the prose are usually an audition or performance date,
# not the course span. A range may omit the year, in which case we take the year
# stated elsewhere in the body; with no year anywhere, dates stay null and the
# season reads "unknown".

_RANGE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})\s*[–-]\s*(?:(" + parse.MONTHALT + r")\s+)?(\d{1,2})"
    r"(?:,?\s*(20\d\d))?",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(20\d\d)\b")


def _parse_dates(text: str) -> tuple[date | None, date | None, str]:
    body_year = _YEAR.search(text)
    year_fallback = int(body_year.group(1)) if body_year else None

    match = _RANGE.search(text)
    if match:
        m1, d1, m2, d2, year = match.groups()
        resolved = int(year) if year else year_fallback
        if resolved is not None:
            start_month, end_month = parse.MONTHS[m1.lower()], parse.MONTHS[(m2 or m1).lower()]
            start = date(resolved, start_month, int(d1))
            # A range that runs backwards across the year boundary (e.g. Dec → Jan).
            end_year = resolved + 1 if end_month < start_month else resolved
            return start, date(end_year, end_month, int(d2)), str(resolved)

    return None, None, (str(year_fallback) if year_fallback else "unknown")
