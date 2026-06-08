"""Bayer Ballet Academy — Mountain View, CA, US — its Vaganova Summer Intensive.

API FIRST: none usable. bayerballet.com runs on **Wix** (Pepyaka server,
parastorage/wixstatic assets, `ssr-caching` response header) — there is no public
content API we may use, and `/wp-json/` 301-redirects (it is not WordPress). The
Summer Intensive page is server-side rendered, so the full text is in the static
HTML — a one-page scrape, no JS/proxy needed. Wix peppers the markup with
zero-width spaces (they split "Ages 9 –18", "$4,950"), so they're stripped up
front (the `brussels_international_ballet` / `young_stars_ballet` trap).

DISCOVERY: the `/summer-intensive` page describes two distinct dated editions,
each its own `Offering` (they differ in length, dates, ages, fees and curriculum):
  - Junior Intensive — a 3-week edition, ages 8-10, culminating in a studio
    demonstration (no pas de deux / pointe / contemporary / performance).
  - Pre-Professional Intensive — the 6-week flagship, ages 9-18+, adding pas de
    deux, pointe, contemporary and an end-of-intensive staged performance.
The editions share one 2026 faculty roster and one audition process, so those are
parsed once and attached to both. The dates carry no inline year; the year is read
from the "2026 Summer Intensive Faculty" stamp on the page. Out of scope and not
emitted: Summer Camps (ages 5-8), Saturday/weekday open classes, adult — they sit
on `/summerprograms`, not this page.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - TWO Offerings from one page, split on the edition headings; per-edition dates,
    ages, genres and prices read from each edition's own text segment so the
    6-week-only disciplines (pointe/contemporary) don't leak into the Junior one.
  - PRICES in USD, several per offering: Tuition + an Early Bird tuition tier;
    the 6-week adds a flat Performance Fee. (Costume Rental "Varies" → no number,
    skipped.)
  - AGES: "Ages 8 –10" (both bounds) and "Ages 9 –18 +" (open-topped — the "+"
    means a null upper bound).
  - TEACHERS: the page names a 2026 faculty roster (Inna Bayer + four classical
    instructors) with their training academies as affiliations — captured for both
    editions. (The body's "World-Renowned Faculty (to be announced)" marketing
    blurb is ignored in favour of the named roster section.)
  - REQUIREMENTS = VIDEO (unspecific): admission is by audition, in person every
    Saturday or by video submission — an open audition-or-video brief; the $40
    audition fee is kept as an application note.
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
    Price,
    PriceInclude,
    Requirement,
    Schedule,
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

BASE = "https://www.bayerballet.com"
PAGE = f"{BASE}/summer-intensive"
TZ = "America/Los_Angeles"

ORG = Organization(
    name="Bayer Ballet Academy",
    slug="bayer-ballet-academy",
    country="US",
    city="Mountain View",
)

_LOCATION = Location(
    venue="Bayer Ballet Studios",
    city="Mountain View",
    country="US",
)

_AUDITION_NOTE = (
    "Admission is by audition: in person at Bayer Ballet Studios (held most "
    "Saturdays) or by video submission. A $40 audition fee applies."
)

# Edition headings split the page into two segments. Each tuple is (offering-slug,
# opening heading, closing heading, six_week). The Junior block ends where the
# Pre-Professional one begins; the latter ends at the audition section that follows
# both. `six_week` editions also see the shared curriculum block for genre matching
# (it lists Pas de Deux / Character / Pointe as "(*) … 6-week intensive only").
_EDITIONS: list[tuple[str, str, str, bool]] = [
    ("junior-intensive", "Junior Intensive", "pre–professional intensive", False),
    ("pre-professional-intensive", "pre–professional intensive", "Past Summer Intensive", True),
]

# The 6-week-only disciplines live in this shared curriculum block (above both
# editions), tagged "(*) denotes elements of the 6-week intensive only". It's
# appended to the 6-week edition's genre text so Pointe / Pas de Deux register
# there but not in the 3-week Junior edition.
_CURRICULUM_HEADING = "Master Vaganova"


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text, date.today())


def _build_offerings(html: str, today: date) -> list[Offering]:  # noqa: ARG001
    text = _page_text(html)
    year = _year(text)
    teachers = _teachers(text)
    requirements = _requirements(text)
    curriculum = _segment(text, _CURRICULUM_HEADING, "Junior Intensive")
    offerings: list[Offering] = []
    for slug, open_heading, close_heading, six_week in _EDITIONS:
        segment = _segment(text, open_heading, close_heading)
        # The 6-week edition's genres also draw on the shared curriculum block;
        # the Junior edition sees only its own text (no 6-week-only disciplines).
        genre_text = f"{segment}\n{curriculum}" if six_week else segment
        offering = _build_offering(segment, genre_text, slug, year, teachers, requirements)
        if offering is not None:
            offerings.append(offering)
    return offerings


def _build_offering(
    segment: str,
    genre_text: str,
    slug: str,
    year: int | None,
    teachers: list[Teacher],
    requirements: list[Requirement],
) -> Offering | None:
    if not segment:
        return None
    start, end = _dates(segment, year)
    title = _title(segment)
    season = str(start.year) if start else (str(year) if year else "unknown")
    return Offering(
        id=f"bayer-ballet-academy/{slug}-{season}",
        source=Source(provider="bayer-ballet-academy", url=PAGE, scrapedAt=now_utc()),
        title=title,
        genres=_genres(genre_text),
        ageRange=_age_range(segment),
        organization=ORG,
        location=_LOCATION,
        schedule=Schedule(season=season, start=start, end=end, timezone=TZ),
        teachers=teachers,
        prices=_prices(segment),
        application=Application(
            url=PAGE,
            requirements=requirements,
            notes=_AUDITION_NOTE,
        ),
    )


# --- text & segmentation ------------------------------------------------------


def _page_text(html: str) -> str:
    # Strip Wix's zero-width spaces (they split "Ages 9 –18" / "$4,950") before any
    # parsing, then collapse to newline-separated lines for segment slicing.
    html = html.replace("​", "").replace("﻿", "")
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = tree.body.text(separator="\n") if tree.body else ""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text


def _segment(text: str, open_heading: str, close_heading: str) -> str:
    start = text.find(open_heading)
    if start < 0:
        return ""
    end = text.find(close_heading, start + len(open_heading))
    return text[start : end if end > 0 else len(text)]


def _title(segment: str) -> str:
    # The first non-empty line is the edition name ("Junior Intensive" /
    # "pre–professional intensive"); pair it with its course-length label.
    lines = [ln.strip() for ln in segment.splitlines() if ln.strip()]
    name = parse.clean(lines[0]).title() if lines else "Summer Intensive"
    length = next((parse.clean(ln) for ln in lines if "Week Summer Intensive" in ln), "")
    return f"{name} — {length}" if length else name


# --- year & dates -------------------------------------------------------------

# The dated section headers carry no year ("June 8 – June 26"); the page stamps
# the cycle once, above the faculty roster ("2026 Summer Intensive Faculty").
_FACULTY_YEAR = re.compile(r"(20\d\d)\s*\n?\s*Summer Intensive Faculty")
# A same-year range with one or two month names: "June 8 – June 26" /
# "June 29 – August 9".
_RANGE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})\s*[-–—]\s*"
    r"(?:(" + parse.MONTHALT + r")\s+)?(\d{1,2})",
    re.IGNORECASE,
)


def _year(text: str) -> int | None:
    match = _FACULTY_YEAR.search(text)
    return int(match.group(1)) if match else None


def _dates(segment: str, year: int | None) -> tuple[date | None, date | None]:
    match = _RANGE.search(segment)
    if not match or year is None:
        return None, None
    m1, d1, m2, d2 = match.groups()
    start_month = parse.MONTHS[m1.lower()]
    end_month = parse.MONTHS[(m2 or m1).lower()]
    return date(year, start_month, int(d1)), date(year, end_month, int(d2))


# --- ages ---------------------------------------------------------------------

# "Ages 8 –10" (both bounds) and "Ages 9 –18 +" (open-topped — the "+" drops the
# upper bound). The en-dash and surrounding spaces vary, hence the loose spacing.
_AGE = re.compile(r"Ages?\s*(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*(\+)?", re.IGNORECASE)


def _age_range(segment: str) -> dict | None:
    match = _AGE.search(segment)
    if not match:
        return None
    low, high, plus = match.groups()
    return {"min": int(low)} if plus else {"min": int(low), "max": int(high)}


# --- genres -------------------------------------------------------------------

# Matched against each edition's own segment (sample program + curriculum), so the
# 6-week-only disciplines (pointe / contemporary / pas de deux) stay out of the
# Junior edition, whose text only lists ballet technique + repertoire / character.
_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet technique", "vaganova", "classical")),
    ("pointe", ("pointe",)),
    ("character", ("character",)),
    ("contemporary", ("contemporary",)),
    ("repertoire", ("repertoire", "variations", "pas de deux")),
]


def _genres(segment: str) -> list[Genre]:
    return parse.match_genres(segment, _GENRE_KEYWORDS, default=["classical"])


# --- prices -------------------------------------------------------------------

# Tuition and its early-bird tier sit under "Tuition:" / "Early Bird Discount:".
# The 6-week edition adds a flat "Performance Fee". "Costume Rental Fee: Varies"
# carries no number, so it's not emitted.
_TUITION = re.compile(r"Tuition:\s*\$([\d,]+(?:\.\d{2})?)", re.IGNORECASE)
_EARLY_BIRD = re.compile(r"Early Bird Discount:\s*\$([\d,]+(?:\.\d{2})?)", re.IGNORECASE)
_PERFORMANCE_FEE = re.compile(r"Performance Fee[^$]*\$([\d,]+(?:\.\d{2})?)", re.IGNORECASE)


def _price(match: re.Match[str] | None, label: str, includes: list[PriceInclude]) -> Price | None:
    if match is None:
        return None
    amount = parse.parse_amount(match.group(1))
    return Price(amount=amount, currency="USD", label=label, includes=includes) if amount else None


def _prices(segment: str) -> list[Price]:
    candidates = [
        _price(_TUITION.search(segment), "Tuition", ["tuition"]),
        _price(
            _EARLY_BIRD.search(segment),
            "Tuition (early bird, paid within 5 days of audition)",
            ["tuition"],
        ),
        _price(_PERFORMANCE_FEE.search(segment), "Performance fee", ["performance"]),
    ]
    return [p for p in candidates if p is not None]


# --- teachers -----------------------------------------------------------------

# The faculty section runs from "Summer Intensive Faculty" to the past-performance
# gallery, one entry per teacher delimited by a "Read More" link. Each entry is a
# name (1-2 lines), a role line, an "Education" label, then training lines. We read
# the name + role and lift the training academy as an affiliation for scoring.
_FACULTY_SECTION = re.compile(
    r"Summer Intensive Faculty(.*?)(?:past summer intensive|Join Our Mailing List)",
    re.IGNORECASE | re.S,
)
_ROLE_LINE = re.compile(r"(Founder|Artistic Director|Instructor|Choreographer|Faculty)", re.I)
# Training academies worth recording as an affiliation, longest-match first so
# "Vaganova Academy of Russian Ballet" wins over a bare "Vaganova".
_ACADEMIES: list[str] = [
    "Bolshoi Ballet Academy",
    "Vaganova Academy of Russian Ballet",
    "Vaganova Ballet Academy",
]


def _teachers(text: str) -> list[Teacher]:
    section = _FACULTY_SECTION.search(text)
    if not section:
        return []
    teachers: list[Teacher] = []
    for block in section.group(1).split("Read More"):
        teacher = _teacher(block)
        if teacher is not None:
            teachers.append(teacher)
    return teachers


def _teacher(block: str) -> Teacher | None:
    lines = [parse.clean(ln) for ln in block.splitlines() if parse.clean(ln)]
    role_idx = next((i for i, ln in enumerate(lines) if _ROLE_LINE.search(ln)), None)
    if role_idx is None or role_idx == 0:
        return None
    # The role line is the first to mention a role word; the name is the line(s)
    # before it joined ("Inna" + "Bayer" → "Inna Bayer", or a single full-name line).
    name = " ".join(lines[:role_idx]).strip()
    if not name or len(name) > 60:
        return None
    role = lines[role_idx]
    return Teacher(name=name, role=role, affiliations=_affiliations(block))


def _affiliations(block: str) -> list[Affiliation]:
    low = block.lower()
    for academy in _ACADEMIES:
        if academy.lower() in low:
            return [Affiliation(organization=academy, role="trained")]
    return []


# --- requirements -------------------------------------------------------------


def _requirements(text: str) -> list[Requirement]:
    low = text.lower()
    if "audition" not in low:
        return []
    return [
        VideoReq(
            specificity="unspecific",
            description=(
                "Admission is by audition — attend an in-person audition (held most "
                "Saturdays) or submit a video: a short introduction, barre and centre "
                "exercises, optional variation, and a photo in first arabesque."
            ),
        )
    ]
