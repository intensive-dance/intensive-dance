"""Joffrey Ballet School — second scraper, exercises the `video` requirement.

API FIRST, THEN RENDER: Joffrey runs WordPress and exposes its programs as custom
post types over the REST API — we use that for **discovery** (slug, link, title,
`dance_style` / `intensive_location` taxonomy). We list three: `summer-intensives`,
`workshops`, and `master-class` (empty out of season). BUT the per-program detail
(dates, ages, location, fees) is **client-rendered by the Cornerstone/Pro page
builder** — `content.rendered` is ~870 chars with none of it, and `acf` is `[]`
(the ABT REST trap). So for each discovered program we additionally fetch the live
page **rendered** (fetch-proxy `render=1`) and parse its hero + detail. The
builder's class names are obfuscated/rotating, so we anchor on **text** (labelled
hero lines, the "Tuition & Pricing" block, a street-address line), and take the
**first** date/age/location on the page (the hero precedes the footer's
cross-program list). Per-page fail-open: a render miss keeps the offering with
its taxonomy-only fields rather than dropping it.

DISCOVERY: one `Offering` per published program, keyed `joffrey-ballet-school/{slug}`.
Joffrey reuses an evergreen entry per program (the slug is not year-stamped), so
there is one record per program, not per cycle. Programs whose only dance style
is out of scope for a *ballet* register (Tap, Hip Hop, Cirque Arts, Musical
Theater) are dropped; ballet / contemporary-ballet / jazz-&-contemporary /
multi-genre are kept.

WHAT THE RENDERED PAGE GIVES US (verified live 2026-06-06):
  - DATES: a "Month D, YYYY - Month D, YYYY" hero range (summer intensives label
    it DATES; workshops print it under the title), else a year-less prose range.
  - AGES: "AGES\\n10 - 25" (labelled) or "Ages 10-25" (workshop) → ageRange.
  - LOCATION: the hero "City, State" (+ a street-address line as venue); the
    region resolves the country (US states → US; Italy/Switzerland/Mexico → IT/CH/MX).
  - PRICES: summer intensives carry a "Tuition & Pricing" block — per-week tuition
    plus optional housing/meals and a registration fee; workshops a flat "Workshop
    Fee". "To be announced" tiers are skipped (Miami's tuition).
  - REQUIREMENTS: summer intensives are "(AUDITION REQUIRED)" → `video`/unspecific
    (the digital audition: in person / Zoom / video). Workshops that state "No
    audition is required" → `[NoneReq]`.
  - TEACHERS: none. A `faculty` post type exists (school-wide roster) but nothing
    ties a faculty member to a specific program, so `teachers` stays empty.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse, wp
from intensive_dance.fetch import PROXY_PARAMS_HEADER
from intensive_dance.models import (
    Application,
    Genre,
    Location,
    NoneReq,
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

BASE = "https://www.joffreyballetschool.com"
AUDITIONS_SLUG = "auditions-2"

ORG = Organization(
    name="Joffrey Ballet School", slug="joffrey-ballet-school", country="US", city="New York"
)

# The program post types to walk (each is a WordPress REST base).
PROGRAM_TYPES: tuple[str, ...] = ("summer-intensives", "workshops", "master-class")

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
    for rest_base in PROGRAM_TYPES:
        for record in wp.fetch_all(
            client,
            rest_base,
            base=BASE,
            params={"_fields": "id,slug,link,title,content,dance_style,intensive_location"},
        ):
            detail = _render_detail(client, record["link"])
            offering = _build_offering(record, styles, locations, audition_url, today, detail)
            if offering is not None:
                offerings.append(offering)
    offerings.sort(key=lambda o: o.id)
    return offerings


# The program detail (dates/ages/location/fees) is client-rendered, so fetch the
# page through the proxy's stealth render. Fail-open: a miss returns "" and the
# offering keeps its taxonomy-only fields rather than being dropped.
_RENDER = {PROXY_PARAMS_HEADER: "render=1&wait=8000"}


# A real program page carries one of these hero/section anchors. Their absence
# means a 404 / partial render whose only dates/fees are in the cross-program
# footer — which we must NOT parse as this program's. (See _clean_detail.)
_HERO_ANCHOR = re.compile(
    r"\bDATES\b|In-Person Instruction|Virtual Instruction|Tuition & Pricing|Workshop Fee",
    re.IGNORECASE,
)


def _render_detail(client: httpx.Client, url: str) -> str:
    # The render can flake transiently (timeout / partial); one retry steadies the
    # committed data so a good page's fields don't blink out into a no-op churn.
    for attempt in range(2):
        try:
            resp = client.get(url, headers=_RENDER, timeout=120)
            resp.raise_for_status()
        except httpx.HTTPError:
            continue
        if detail := _clean_detail(resp.text):
            return detail
    return ""


def _clean_detail(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = tree.body.text(separator="\n") if tree.body else ""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    # A still-listed program whose page has been pulled returns a soft 404 (200
    # "page not found") or a partial render — neither carries a hero/section
    # anchor, only a cross-program footer. Reject it so footer dates/fees can't
    # leak in as this program's (fail-open: the offering keeps taxonomy-only).
    if "no longer here, or never existed" in text or not _HERO_ANCHOR.search(text):
        return ""
    return text


def _auditions_url(client: httpx.Client) -> str:
    page = wp.fetch_page(client, AUDITIONS_SLUG, base=BASE)
    return page["link"] if page else f"{BASE}/auditions/"


def _build_offering(
    record: dict,
    styles: dict[int, str],
    locations: dict[int, str],
    audition_url: str,
    today: date,
    detail: str = "",
) -> Offering | None:
    """One program record → an Offering, or None if out of scope (no in-scope genre).

    `detail` is the rendered program page's text (dates/ages/location/fees); a
    discovery field (genres/scope) still comes from the REST record. Ended cycles
    are kept, not dropped — "past" is derived from `schedule.end < today`, not
    stored (the IDR-24 convention; see AGENTS.md).
    """
    title = wp.plain_text(record["title"]["rendered"])
    text = wp.plain_text(record["content"]["rendered"])
    genres = _genres(record.get("dance_style", []), styles, title, text)
    if not genres:
        return None  # no in-scope ballet/contemporary style → not for this register

    start, end, season = _parse_dates(detail or text)
    # Prefer the rendered page's own city/venue; fall back to the taxonomy region.
    city, country, venue = _detail_location(detail)
    if country is None:
        city, country = _location(record.get("intensive_location", []), locations)

    return Offering(
        id=f"joffrey-ballet-school/{record['slug']}",
        source=Source(provider="joffrey-ballet-school", url=record["link"], scrapedAt=now_utc()),
        title=title,
        genres=genres,
        ageRange=_age_range(detail),
        organization=ORG,
        location=Location(venue=venue, city=city, country=country) if country else None,
        schedule=Schedule(season=season, start=start, end=end),
        prices=_prices(detail),
        application=Application(
            url=audition_url,
            requirements=_requirements(detail),
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
# The rendered hero prints a fully-qualified span ("Month D, YYYY - Month D,
# YYYY") — the first one on the page (the footer repeats other programs', so we
# take the earliest). Prose elsewhere may give a year-less range ("December
# 28-30, 2026" / "Month D – Month D"); we trust only a *range* (a lone date is
# usually an audition/performance), inheriting a year stated nearby. No year
# anywhere → dates stay null and the season reads "unknown".

_FULL_RANGE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2}),\s*(20\d\d)\s*[-–]\s*"
    r"(" + parse.MONTHALT + r")\s+(\d{1,2}),\s*(20\d\d)",
    re.IGNORECASE,
)
_RANGE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})\s*[–-]\s*(?:(" + parse.MONTHALT + r")\s+)?(\d{1,2})"
    r"(?:,?\s*(20\d\d))?",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(20\d\d)\b")


def _parse_dates(text: str) -> tuple[date | None, date | None, str]:
    full = _FULL_RANGE.search(text)
    if full:
        m1, d1, y1, m2, d2, y2 = full.groups()
        start = date(int(y1), parse.MONTHS[m1.lower()], int(d1))
        end = date(int(y2), parse.MONTHS[m2.lower()], int(d2))
        return start, end, y1

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


# --- ages / location / prices / requirements from the rendered hero -----------

_AGE = re.compile(r"\bAges?\b\s*:?\s*(\d{1,2})\s*[-–]\s*(\d{1,2})", re.IGNORECASE)
# US states (full names) → country US; the few overseas editions name their country.
_US_STATES = frozenset(
    s.lower()
    for s in (
        "Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida "
        "Georgia Hawaii Idaho Illinois Indiana Iowa Kansas Kentucky Louisiana Maine Maryland "
        "Massachusetts Michigan Minnesota Mississippi Missouri Montana Nebraska Nevada Ohio "
        "Oklahoma Oregon Pennsylvania Tennessee Texas Utah Vermont Virginia Washington "
        "Wisconsin Wyoming"
    ).split()
)
_MULTIWORD_STATES = frozenset(
    {
        "new hampshire",
        "new jersey",
        "new mexico",
        "new york",
        "north carolina",
        "north dakota",
        "rhode island",
        "south carolina",
        "south dakota",
        "west virginia",
    }
)
_COUNTRY_BY_REGION = {
    "italy": "IT",
    "switzerland": "CH",
    "mexico": "MX",
    "canada": "CA",
    "australia": "AU",
}
# Summer intensives label the hero line "LOCATION"; workshops print it right after
# "In-Person Instruction" (a "City, Region" or a full street address). We anchor on
# those, never a free text scan, so prose like "Get ready, Canada!" can't leak in.
_LABELLED_LOCATION = re.compile(r"\bLOCATION\b\s*\n\s*([^\n]+)")
_INSTRUCTION_LOCATION = re.compile(r"(?:In-Person|Virtual) Instruction\s*\n\s*([^\n]+)")
_ADDRESS = re.compile(r"[^\n]*\b\d{1,6}\b[^\n,]*,\s*[A-Za-z .'-]+,\s*[A-Z]{2}\s+\d{5}")


def _age_range(detail: str) -> dict | None:
    match = _AGE.search(detail)
    return {"min": int(match.group(1)), "max": int(match.group(2))} if match else None


def _detail_location(detail: str) -> tuple[str | None, str | None, str | None]:
    """(city, country, venue) from the hero. Country resolves from the region name."""
    labelled = _LABELLED_LOCATION.search(detail)
    line = (labelled.group(1) if labelled else _hero_location_line(detail)).strip()
    if not line:
        return None, None, None

    city, country = _city_country(line)
    venue = line if re.search(r"\d", line) else None  # a street address, not "City, State"
    if venue is None:
        address = _ADDRESS.search(detail)
        venue = address.group(0).strip() if address else None
    return city, country, venue


def _hero_location_line(detail: str) -> str:
    match = _INSTRUCTION_LOCATION.search(detail)
    return match.group(1) if match else ""


def _city_country(line: str) -> tuple[str | None, str | None]:
    """The city + ISO country from a "…, City, Region[, …]" line, by the known region."""
    parts = [p.strip() for p in line.split(",")]
    for i, part in enumerate(parts):
        country = _region_country(part)
        if country and i > 0:
            return _clean_city(parts[i - 1]), country
    return None, None


def _clean_city(city: str) -> str | None:
    parenthetical = re.search(r"\(([^)]+)\)", city)  # "Ontario (Toronto)" → "Toronto"
    return (parenthetical.group(1) if parenthetical else city).strip() or None


def _region_country(region: str) -> str | None:
    key = region.strip().lower()
    if key in _US_STATES or key in _MULTIWORD_STATES:
        return "US"
    return _COUNTRY_BY_REGION.get(key)


# Fees on a summer intensive sit under "Tuition & Pricing": per-week tuition,
# optional housing/meals, and a registration fee. Workshops use a flat
# "Workshop Fee". "To be announced" tiers carry no number, so they're skipped.
_WORKSHOP_FEE = re.compile(r"Workshop Fee:?\s*\$(\d[\d,]*)", re.IGNORECASE)
_TUITION_BLOCK = re.compile(
    r"Tuition & Pricing(.*?)(?:\n(?:Location|Housing Details|FAQ)\b|$)", re.S
)
_PER_WEEK = re.compile(r"\$(\d[\d,]*)\s*(?:per week|Per Week)")
_EXTRA_FEES: list[tuple[str, PriceInclude]] = [
    ("Housing", "accommodation"),
    ("Meal Plans", "meals"),
]


def _amount(raw: str) -> float:
    return float(raw.replace(",", ""))


def _prices(detail: str) -> list[Price]:
    prices: list[Price] = []
    workshop = _WORKSHOP_FEE.search(detail)
    if workshop:
        prices.append(
            Price(
                amount=_amount(workshop.group(1)),
                currency="USD",
                label="Workshop fee",
                includes=["tuition"],
            )
        )
    block = _TUITION_BLOCK.search(detail)
    if block:
        seg = block.group(1)
        tuition = _PER_WEEK.search(seg)
        if tuition:
            prices.append(
                Price(
                    amount=_amount(tuition.group(1)),
                    currency="USD",
                    label="Tuition (per week)",
                    includes=["tuition"],
                )
            )
        for label, include in _EXTRA_FEES:
            m = re.search(re.escape(label) + r"\s*\$(\d[\d,]*)", seg)
            if m:
                prices.append(
                    Price(
                        amount=_amount(m.group(1)),
                        currency="USD",
                        label=f"{label} (per week)",
                        includes=[include],
                    )
                )
        reg = re.search(r"Registration Fee\s*\$(\d[\d,]*)", seg)
        if reg:
            prices.append(
                Price(
                    amount=_amount(reg.group(1)),
                    currency="USD",
                    label="Registration fee",
                    includes=[],
                )
            )
    return prices


def _requirements(detail: str) -> list[Requirement]:
    # Workshops that state no audition are open enrolment; intensives audition.
    if "no audition is required" in detail.lower():
        return [NoneReq()]
    return [VideoReq(specificity="unspecific", description=_AUDITION_NOTE)]
