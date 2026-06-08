"""Yorkshire Ballet Seminars (YBS) — its summer residential intensive.

API FIRST: none. YBS runs on **Wix** (server-side rendered, like Brussels and
Young Stars Ballet), so the content is in the static HTML — no JS, no proxy. A
`/wp-json/` probe 301-redirects (it is not WordPress). We read two pages: the
Residential Courses page (`/residentialscourses`, the dated editions + venue) and
the homepage (`/`, the canonical "ages 9 to 19" line and the Artistic Director).

DISCOVERY: the Residential Courses page advertises one summer course —
"Summer Residential <year>" — priced "(per week)" and listed as four consecutive
**weekly editions** ("July 12th - July 18th", … "August 2nd - August 8th"). The
weeks are the same course (same ages 9–19, same Ashville College venue, same
genres) at different dates, so we emit **one Offering per week** (a dancer books
by the week), year-stamped (`summer-<year>-week-<n>`) so each dated edition stays
distinct and diffable. The single editions `<h2>` carries the season+year title
and all four date ranges; we read the title for the season and split the ranges.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - MULTIPLE dated Offerings from one provider page — one per weekly edition, all
    sharing ages/venue/genres but carrying their own British date range
    ("July 12th - July 18th", year on the page title only).
  - TEACHERS: the named Artistic Director (Isabelle Brouwers), affiliated to YBS
    with role="Artistic Director". YBS's marquee guest faculty rotate each year
    and are not published as a current roster on the site (the "Our History" prose
    only lists *past* teachers), and the Patrons line names patrons, not teaching
    staff — so neither is laundered into the per-edition roster.
  - PRICES: NOT emitted. The page states "(per week)" but publishes no figure in
    scrapeable markup (the fee lives behind the Wix application/payment form), so
    under fail-open we leave prices empty rather than invent one.
  - REQUIREMENTS: the residential is applied for via a form with no stated media
    brief; the in-person scholarship audition is a separate, optional track. So
    application requirements stay `[]` (not stated), with the apply URL recorded.
  - AGES 9–19 and GENRES (classical, pointe, contemporary, repertoire) from the
    course prose. LOCATION = Ashville College, Harrogate (the venue address block).
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
    Schedule,
    Session,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.ybss.co.uk"
HOME_URL = f"{BASE}/"
COURSES_URL = f"{BASE}/residentialscourses"
APPLY_URL = f"{BASE}/summerapply"

# Zero-width space / non-joiner / joiner / BOM — Wix scatters these through text.
_ZERO_WIDTH = re.compile("[​‌‍﻿]")

ORG = Organization(
    name="Yorkshire Ballet Seminars",
    slug="yorkshire-ballet-seminars",
    country="GB",
    city="Harrogate",
)
# The residential's home, stated on the courses page venue block.
VENUE = Location(
    venue="Ashville College, Green Lane, Harrogate HG2 9JP",
    city="Harrogate",
    country="GB",
)


def scrape(client: httpx.Client) -> list[Offering]:
    courses_html = _get(client, COURSES_URL)
    home_text = _text(_get(client, HOME_URL))
    return _build_offerings(courses_html, home_text, date.today())


def _get(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    resp.raise_for_status()
    return resp.text


def _text(html: str) -> str:
    """Visible body text with Wix's zero-width characters stripped."""
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    raw = tree.body.text(separator=" ") if tree.body else ""
    return parse.clean(_ZERO_WIDTH.sub("", raw))


def _build_offerings(courses_html: str, home_text: str, today: date) -> list[Offering]:
    season, weeks = _summer_editions(courses_html)
    if not weeks:
        return []  # no dated editions announced

    age_range = _age_range(home_text)
    # The single residential's curriculum is described across both pages — the
    # courses prose ("technique classes and repertoire sessions") and the homepage
    # line ("classical ballet, pointe work and contemporary").
    genres = _genres(f"{_text(courses_html)} {home_text}")
    teachers = _teachers(home_text)

    offerings: list[Offering] = []
    for index, (start, end) in enumerate(weeks, start=1):
        offerings.append(
            Offering(
                id=f"yorkshire-ballet-seminars/summer-{season}-week-{index}",
                source=Source(
                    provider="yorkshire-ballet-seminars", url=COURSES_URL, scrapedAt=now_utc()
                ),
                title=f"Summer Residential {season} — Week {index} ({_span(start, end)})",
                genres=genres,
                ageRange=age_range,
                organization=ORG,
                location=VENUE,
                schedule=Schedule(
                    season=season,
                    start=start,
                    end=end,
                    timezone="Europe/London",
                    sessions=[Session(label=f"Week {index}", start=start, end=end)],
                ),
                teachers=teachers,
                application=Application(url=APPLY_URL),
            )
        )
    return offerings


# --- editions: a single <h2> holds "Summer Residential <year>" + the date list ---
#
# The heading text reads e.g. "Summer Residential 2026 (per week) July 12th -
# July 18th  July 19th - July 25th  …". We anchor on the heading carrying both
# "Residential" and a four-digit year (the season+year title), then split out the
# British "<Month> <day> - <Month> <day>" ranges, applying the title year.

_TITLE = re.compile(r"\bResidential\b.*?\b(20\d\d)\b", re.IGNORECASE)
_RANGE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})(?:st|nd|rd|th)?\s*[-–—]\s*"
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})(?:st|nd|rd|th)?",
    re.IGNORECASE,
)


def _summer_editions(html: str) -> tuple[str, list[tuple[date, date]]]:
    """(season, [(start, end), …]) from the editions heading.

    Returns ("unknown", []) when no dated editions heading is present.
    """
    tree = HTMLParser(html)
    for heading in tree.css("h1, h2, h3"):
        text = parse.clean(_ZERO_WIDTH.sub("", heading.text(separator=" ")))
        title = _TITLE.search(text)
        if not title:
            continue
        year = int(title.group(1))
        weeks = _ranges(text, year)
        if weeks:
            return str(year), weeks
    return "unknown", []


def _ranges(text: str, year: int) -> list[tuple[date, date]]:
    """The British "<Month> <day> - <Month> <day>" ranges in `text`, year applied.

    A range whose end month precedes its start month (e.g. an end in early January)
    rolls the end into the next year.
    """
    weeks: list[tuple[date, date]] = []
    for m1, d1, m2, d2 in _RANGE.findall(text):
        start = date(year, parse.MONTHS[m1.lower()], int(d1))
        end_year = year + 1 if parse.MONTHS[m2.lower()] < parse.MONTHS[m1.lower()] else year
        end = date(end_year, parse.MONTHS[m2.lower()], int(d2))
        weeks.append((start, end))
    return weeks


def _span(start: date, end: date) -> str:
    """Compact British label "12–18 July" / "26 July – 1 August"."""
    months = [m.title() for m in parse.MONTHS]
    if start.month == end.month:
        return f"{start.day}–{end.day} {months[end.month - 1]}"
    return f"{start.day} {months[start.month - 1]} – {end.day} {months[end.month - 1]}"


# --- ages -------------------------------------------------------------------
# The homepage states the course's age band: "ages 9 to 19".

_AGE = re.compile(r"ages?\s*(\d{1,2})\s*(?:to|[-–])\s*(\d{1,2})", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    return parse.extract_age_range(text, _AGE)


# --- genres -----------------------------------------------------------------
# Matched against the course prose ("technique classes and repertoire sessions").

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet", "classical", "technique")),
    ("pointe", ("pointe",)),
    ("contemporary", ("contemporary", "modern")),
    ("repertoire", ("repertoire", "repertory")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- teachers ---------------------------------------------------------------
# Only the named Artistic Director is a stable, current roster fact. Marquee guest
# faculty rotate yearly and aren't published as a current list; the "Our History"
# names are explicitly past, and Patrons are patrons, not teaching staff.

# The byline reads "Isabelle Brouwers, Artistic Director" — the comma + singular
# "Director" is load-bearing: it skips the "Welcome New Artistic Director" heading
# (no comma) and the "previous Artistic Directors" prose (plural, no comma).
_DIRECTOR = re.compile(
    r"([A-Z][a-zà-ÿ'’-]+(?:\s+[A-Z][a-zà-ÿ'’-]+){1,2})\s*,\s*Artistic Director\b(?!s)",
)


def _teachers(text: str) -> list[Teacher]:
    match = _DIRECTOR.search(text)
    if not match:
        return []
    return [
        Teacher(
            name=parse.clean(match.group(1)),
            role="Artistic Director",
            affiliations=[
                Affiliation(
                    organization="Yorkshire Ballet Seminars",
                    slug="yorkshire-ballet-seminars",
                    role="Artistic Director",
                    current=True,
                )
            ],
        )
    ]
