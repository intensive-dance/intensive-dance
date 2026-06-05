"""English National Ballet School (London, GB) — its Summer Intensives.

API FIRST: WordPress REST. The site is WordPress (The Events Calendar is
installed but unused — its events collection is empty), so the Summer
Intensives page is fetched as a record from `/wp-json/wp/v2/pages?slug=summer`
and parsed from `content.rendered`.

DISCOVERY: one page lists three summer courses. The WPBakery layout groups all
course titles (`<h4>`) ahead of a shared block of detail sub-headings, so the
heading-nesting `wp.Content` relies on doesn't map a course to its own dates.
Instead we split the page text on the `COURSE ONE/TWO/THREE` markers (the same
per-track text-splitting `russian_masters_ballet` uses) and read each course's
date range, age band and level from its chunk; the £1250 course fee and £30
non-refundable application fee are shared across all three.

We emit one `Offering` per course and drop any whose end date is past — so the
Spring, Boys' Workshop and Introduction to 4Pointe intensives (all earlier 2026
or 2025 cycles) fall away on their own once parsed, and only the live summer
courses remain.

Teachers are named in prose per course but sit in the shared detail block where
they can't be reliably attributed to one course, so they're left empty (same
call as the Joffrey scraper makes for its unpublished fields).
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://www.enbschool.org.uk"
PAGE_SLUG = "summer"
APPLY_URL = f"{BASE}/intensives/summer-intensive-application/"

ORG = Organization(
    name="English National Ballet School",
    slug="english-national-ballet-school",
    country="GB",
    city="London",
)
VENUE = Location(
    venue="Carlyle Building, Hortensia Road, Chelsea, SW10 0QS", city="London", country="GB"
)

_NUMERALS = {"ONE": "1", "TWO": "2", "THREE": "3"}

_VIDEO_BRIEF = "Entry is by video submission; applicants follow the ENBS Video Requirements."
_APPLY_NOTE = "Places are allocated first-come, first-served; applications close once a course reaches capacity."


def scrape(client: httpx.Client) -> list[Offering]:
    page = wp.fetch_page(client, PAGE_SLUG, base=BASE)
    if page is None:
        return []
    rendered = page["content"]["rendered"]
    text = _plain(rendered)
    today = date.today()
    # Fees and applicant guidance live in a shared block after the third course;
    # split courses from the region before it so its "RAD intermediate level"
    # prose doesn't bleed into Course Three's own level/age.
    shared = _SHARED.search(text)
    course_region = text[: shared.start()] if shared else text
    offerings = [_build_offering(course, text, today) for course in _courses(course_region)]
    return [o for o in offerings if o is not None]


def _plain(rendered: str) -> str:
    """Rendered body as collapsed plain text, with inline scripts dropped and
    `<sup>` ordinals (which arrive as a detached "31 st") rejoined."""
    tree = HTMLParser(wp._SHORTCODE.sub("", rendered))
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.text(separator=" ")) if tree.body else ""
    return re.sub(r"(\d{1,2})\s*(?:st|nd|rd|th)\b", r"\1", text)


# --- per-course parsing -------------------------------------------------------

_COURSE = re.compile(r"COURSE\s+(ONE|TWO|THREE)\s*[-–]\s*", re.IGNORECASE)
_SHARED = re.compile(r"All Summer Intensive Course Information", re.IGNORECASE)
_MONTHALT = parse.MONTHALT
_TOKEN = re.compile(r"(\d{1,2})\s+(" + _MONTHALT + r")(?:\s+(\d{4}))?", re.IGNORECASE)
_AGE = re.compile(r"Age:?\s*(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})", re.IGNORECASE)


def _courses(text: str) -> list[tuple[str, str, str]]:
    """Split the page into `(numeral, title, chunk)` per COURSE ONE/TWO/THREE."""
    marks = list(_COURSE.finditer(text))
    courses = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        chunk = text[mark.end() : end]
        title = _title(chunk)
        courses.append((_NUMERALS[mark.group(1).upper()], title, chunk))
    return courses


def _title(chunk: str) -> str:
    """A course's title — the text before its first date token."""
    token = _TOKEN.search(chunk)
    head = chunk[: token.start()] if token else chunk
    return parse.clean(re.split(r"\b(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\b", head)[0]).rstrip(
        " -–"
    )


def _date_range(chunk: str) -> tuple[date | None, date | None]:
    """First two date tokens in a chunk as (start, end), sharing a year/month
    when one omits it (e.g. "20 July – 31 July 2026")."""
    tokens = _TOKEN.findall(chunk)[:2]
    if not tokens:
        return None, None
    if len(tokens) == 1:
        return _to_date(tokens[0]), None
    (d1, m1, y1), (d2, m2, y2) = tokens
    year = y1 or y2
    end_year = y2 or y1
    return _to_date((d1, m1, year)), _to_date((d2, m2, end_year))


def _to_date(token: tuple[str, str, str]) -> date | None:
    day, month, year = token
    if not year:
        return None
    return date(int(year), parse.MONTHS[month.lower()], int(day))


def _age_range(chunk: str) -> dict | None:
    match = _AGE.search(chunk)
    return {"min": int(match.group(1)), "max": int(match.group(2))} if match else None


def _levels(chunk: str) -> list[Level]:
    low = chunk.lower()
    levels: list[Level] = []
    if "intermediate" in low:
        levels.append("intermediate")
    if re.search(r"pre-?professional", low):
        levels.append("pre-professional")
    if "professional" in re.sub(r"pre-?professional", "", low):
        levels.append("professional")
    return levels


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet")),
    ("contemporary", ("contemporary",)),
    ("repertoire", ("repertoire",)),
    ("character", ("character dance", "national dance")),
    ("pointe", ("pointe",)),
]


def _genres(chunk: str) -> list[Genre]:
    return parse.match_genres(chunk, _GENRE_KEYWORDS, default=["classical"])


_COURSE_FEE = re.compile(
    r"(?:Course\s*Fee|Each\s+Intensive\s+Course\s+is)\D{0,12}£\s?([\d,.]+)", re.IGNORECASE
)
_APP_FEE = re.compile(r"application\s+fee\D{0,30}£\s?([\d,.]+)", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    course = _COURSE_FEE.search(text)
    if course and (amount := parse.parse_amount(course.group(1))) is not None:
        prices.append(
            Price(amount=amount, currency="GBP", label="Course fee", includes=["tuition"])
        )
    app = _APP_FEE.search(text)
    if app and (amount := parse.parse_amount(app.group(1))) is not None:
        prices.append(
            Price(
                amount=amount,
                currency="GBP",
                label="Application fee (non-refundable)",
                notes="Non-refundable; payable on every Summer Intensive application.",
            )
        )
    return prices


def _build_offering(course: tuple[str, str, str], text: str, today: date) -> Offering | None:
    numeral, title, chunk = course
    start, end = _date_range(chunk)
    if end is not None and end < today:
        return None  # this course's cycle has finished
    anchor = end or start
    season = str(anchor.year) if anchor else "unknown"
    return Offering(
        id=f"english-national-ballet-school/summer-intensive-{season}-course-{numeral}",
        source=Source(
            provider="english-national-ballet-school",
            url=f"{BASE}/intensives/summer/",
            scrapedAt=now_utc(),
        ),
        title=f"Summer Intensive {season} — Course {numeral}: {title}",
        genres=_genres(chunk),
        kind="intensive",
        level=_levels(chunk),
        ageRange=_age_range(chunk),
        organization=ORG,
        location=VENUE,
        schedule=Schedule(
            season=season, start=start, end=end, timezone="Europe/London", notes=_dates_note(chunk)
        ),
        prices=_prices(text),
        application=Application(
            status="open" if "applications are now open" in text.lower() else None,
            url=APPLY_URL,
            requirements=[VideoReq(specificity="unspecific", description=_VIDEO_BRIEF)],
            notes=_APPLY_NOTE,
        ),
    )


def _dates_note(chunk: str) -> str | None:
    tokens = list(_TOKEN.finditer(chunk))[:2]
    if not tokens:
        return None
    span = chunk[tokens[0].start() : tokens[-1].end()]
    return parse.clean(span)
