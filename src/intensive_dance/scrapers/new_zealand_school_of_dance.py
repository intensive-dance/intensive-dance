"""New Zealand School of Dance — public young-dancer short intensives (Wellington).

API FIRST
The site (https://www.nzschoolofdance.ac.nz) is **Webflow**, not WordPress —
``GET /wp-json/`` 404s and the markup is the Webflow runtime
(``data-wf-domain``/``cdn.prod.webflow``). There is no JSON API, no schema.org
``ld+json``, and no embedded state blob, so this is a plain HTML scrape
(selectolax). The course pages are static server-rendered HTML whose dated
detail (date range, fee, venue, ages) sits in the page body as a flat run of
``Label:`` lines ("Dates:", "Where:", "Cost:"). A plain fetch with our UA works —
no proxy needed (verified live 2026-06-08).

DISCOVERY
NZSD's Young Dancer Programmes split into year-round, tiered **pre-vocational**
schemes (Scholars, Associates — weekly/weekend classes across the academic year,
in partnership with the Royal New Zealand Ballet) and **short-term holiday
intensives**. Only the short courses are in scope, and only the editions that
publish a concrete date range on their own course page:

  - Contemporary Intensive Programme (CIP), Wellington — a two-day contemporary
    intensive (``/courses/contemporary-intensive-programme``).
  - Winter School — a five-day classical + contemporary holiday course in the
    first week of the winter school holidays (``/courses/winter-school``).

We emit **one Offering per course page** (each is a single dated edition). The
Summer Intensive page is currently undated ("No items found"; it points to a
future edition via "contact us"), so it yields nothing — discovery, not a date
cut. The full-time NZ Diploma in Dance (Levels 6/7) is the long-term vocational
course and is out of scope, as are the year-round Scholars/Associates schemes and
the out-of-genre festival workshops (Hip Hop, Pacific/Tempo schools workshops).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08)
  - Webflow static HTML read by labelled body lines (no API, no proxy).
  - ONE Offering per dated course page; an undated page (Summer Intensive) is
    skipped — no invented dates.
  - PRICES in NZD: a course fee + a separate registration fee, both per-program.
  - AGE RANGE only where stated ("aged 15-18" on CIP); Winter School states a
    syllabus level ("RAD Grade 5 to Solo Seal") but no numeric age, so its
    ``ageRange`` stays null (fail-open).
  - GENRES from the per-program prose: contemporary (CIP) / classical +
    contemporary (Winter School).
  - REQUIREMENTS = NoneReq: both register via an open form — neither states an
    audition (CIP's "foundation in contemporary dance" and Winter School's RAD
    level are eligibility, not an application submission).
  - TEACHERS: none named per program (the pages credit "NZSD faculty" and guest
    tutors collectively), so teachers stays empty — the Joffrey case.
  - Past cycles are kept (IDR-24); "past" is derived consumer-side.
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
    NoneReq,
    Offering,
    Organization,
    Price,
    Schedule,
    Session,
    Source,
    now_utc,
)

BASE = "https://www.nzschoolofdance.ac.nz"

ORG = Organization(
    name="New Zealand School of Dance",
    slug="new-zealand-school-of-dance",
    country="NZ",
    city="Wellington",
)
TIMEZONE = "Pacific/Auckland"

# The course pages whose body publishes a dated short-term intensive edition.
# (slug, offering-slug, fallback title) — the page's own heading wins the title.
PAGES: list[tuple[str, str, str]] = [
    (
        "courses/contemporary-intensive-programme",
        "contemporary-intensive-programme",
        "Contemporary Intensive Programme (CIP)",
    ),
    ("courses/winter-school", "winter-school", "Winter School"),
]

# A class list / prose keyword → genre. Ballet phrasing ("classical", "ballet")
# adds classical; "contemporary" adds contemporary. Matched against the program
# prose, not faculty bios.
_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet")),
    ("contemporary", ("contemporary",)),
]


def scrape(client: httpx.Client) -> list[Offering]:
    pages: dict[str, str] = {}
    for slug, _offering_slug, _title in PAGES:
        resp = client.get(f"{BASE}/{slug}")
        resp.raise_for_status()
        pages[slug] = resp.text
    return _build_offerings(pages, date.today())


def _build_offerings(pages: dict[str, str], today: date) -> list[Offering]:
    offerings: list[Offering] = []
    for slug, offering_slug, fallback_title in PAGES:
        html = pages.get(slug)
        if html is None:
            continue
        offering = _page_offering(html, slug, offering_slug, fallback_title)
        if offering is not None:
            offerings.append(offering)
    offerings.sort(key=lambda o: (o.schedule.start or date.min, o.id))
    return offerings


def _page_offering(
    html: str, slug: str, offering_slug: str, fallback_title: str
) -> Offering | None:
    body = _body_text(html)
    start, end = _dates(body)
    if start is None:
        # No dated edition published on this page (e.g. Summer Intensive's
        # "No items found"): emit nothing rather than invent a date.
        return None

    title = _heading(html) or fallback_title
    season = str(start.year)
    age_range = _age_range(body)
    genres = _genres(body)
    levels = _levels(body)
    prices = _prices(body)
    venue = _venue(body)
    eligibility = _eligibility(body)

    return Offering(
        id=f"new-zealand-school-of-dance/{offering_slug}-{season}",
        source=Source(
            provider="new-zealand-school-of-dance",
            url=f"{BASE}/{slug}",
            scrapedAt=now_utc(),
        ),
        title=f"{title} {season}",
        genres=genres,
        level=levels,
        ageRange=age_range,
        organization=ORG,
        location=Location(venue=venue, city="Wellington", country="NZ"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone=TIMEZONE,
            sessions=[Session(start=start, end=end, ageRange=age_range)],
        ),
        prices=prices,
        application=Application(
            url=f"{BASE}/{slug}",
            requirements=[NoneReq()],
            notes=eligibility,
        ),
    )


def _body_text(html: str) -> str:
    """The page body as flat single-spaced text (scripts/styles dropped)."""
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    container = tree.body or tree
    return parse.clean(container.text(separator=" "))


def _heading(html: str) -> str | None:
    """The Webflow ``og:title`` (the page's own programme heading)."""
    tree = HTMLParser(html)
    for meta in tree.css("meta"):
        if meta.attributes.get("property") == "og:title":
            return parse.clean(meta.attributes.get("content") or "") or None
    return None


# --- dates --------------------------------------------------------------------
#
# The body states one date range under a "Dates:" label, in two shapes:
#   "Dates: 27 - 28 June 2026"                     (shared month + year)
#   "Dates: Sunday 5 - Thursday 9 July 2026"       (weekday-prefixed, shared month)
# Both days share the trailing month and year. We anchor on the digit-dash-digit
# day pair (weekday words optional on either side) so the weekdays don't matter.

_DATE_RE = re.compile(
    r"(\d{1,2})\s*[-–]\s*(?:[A-Za-z]+\s+)?(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(20\d\d)",
    re.IGNORECASE,
)


def _dates(body: str) -> tuple[date | None, date | None]:
    # Prefer a range that immediately follows the "Dates:" label, else the first
    # day-dash-day-month-year range on the page.
    match = re.search(r"Dates?\s*:?\s*([^.]*?20\d\d)", body, re.IGNORECASE)
    window = match.group(1) if match else body
    found = _DATE_RE.search(window) or _DATE_RE.search(body)
    if not found:
        return None, None
    d1, d2, month, year = found.groups()
    month_num = parse.MONTHS[month.lower()]
    yr = int(year)
    return date(yr, month_num, int(d1)), date(yr, month_num, int(d2))


# --- venue --------------------------------------------------------------------
#
# "Where: Te Whaea: National Dance and Drama Centre" — note the venue itself
# carries an internal colon, so we read to the next labelled section ("Cost:",
# "Dates:") or the start of the following descriptive sentence (the page either
# runs straight into a "Cost:" line or into prose beginning "This …"/"Over …").

_VENUE_RE = re.compile(
    r"Where\s*:\s*(.+?)\s*(?:Cost\s*:|Dates?\s*:|This\b|Over\b|All\b|$)", re.IGNORECASE
)


def _venue(body: str) -> str | None:
    match = _VENUE_RE.search(body)
    if not match:
        return None
    venue = parse.clean(match.group(1)).strip(" :‍")
    return venue or None


# --- ages ---------------------------------------------------------------------
#
# Stated as "aged 15-18" / "aged 15 to 18". Winter School gives a syllabus level
# instead of a numeric age, so this returns None there.

_AGE_RE = re.compile(r"aged?\s+(\d{1,2})\s*(?:to|-|–)\s*(\d{1,2})", re.IGNORECASE)


def _age_range(body: str) -> dict | None:
    match = _AGE_RE.search(body)
    if not match:
        return None
    return {"min": int(match.group(1)), "max": int(match.group(2))}


# --- levels -------------------------------------------------------------------


def _levels(body: str) -> list[Level]:
    """Open-enrolment short courses; both accept a broad range by self-selected
    form (CIP wants an existing contemporary foundation, Winter School an RAD
    level), neither streams by audition — so 'open'."""
    return ["open"]


# --- genres -------------------------------------------------------------------


def _genres(body: str) -> list[Genre]:
    return parse.match_genres(body, _GENRE_KEYWORDS, default=["classical"])


# --- prices -------------------------------------------------------------------
#
# "Cost: $200.00 + $25.00 registration fee." — a course fee and a separate,
# smaller registration fee, both in NZD. The first amount is the course fee; an
# amount tagged "registration" is the registration fee.

# Capture the whole "Cost:" sentence. A bare "." can't terminate it (the amounts
# carry decimal points like "$200.00"); end on "fee." or a period that is not part
# of a "$NN.NN" decimal — i.e. a "." not immediately followed by two digits.
_COST_RE = re.compile(r"Cost\s*:\s*(.*?(?:fee\.|\.(?!\d{2})))", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)")


def _prices(body: str) -> list[Price]:
    match = _COST_RE.search(body)
    if not match:
        # No "Cost:" line (e.g. Winter School lists its fee only behind the
        # registration form): leave prices unset rather than grab a stray "$".
        return []
    cost_text = match.group(0)
    amounts = _AMOUNT_RE.findall(cost_text)
    prices: list[Price] = []
    if amounts:
        course = parse.parse_amount(amounts[0])
        if course is not None:
            prices.append(
                Price(amount=course, currency="NZD", label="Course fee", includes=["tuition"])
            )
    if len(amounts) >= 2 and "registration" in cost_text.lower():
        reg = parse.parse_amount(amounts[1])
        if reg is not None:
            # A registration fee is an administrative charge, not tuition, so its
            # `includes` is left empty.
            prices.append(Price(amount=reg, currency="NZD", label="Registration fee"))
    return prices


# --- eligibility (application notes) ------------------------------------------

_ELIGIBILITY_RE = re.compile(
    r"(designed for dancers aged[^.]+\.|suitable for students working[^.]+\.)",
    re.IGNORECASE,
)


def _eligibility(body: str) -> str | None:
    match = _ELIGIBILITY_RE.search(body)
    return parse.clean(match.group(1)) if match else None
