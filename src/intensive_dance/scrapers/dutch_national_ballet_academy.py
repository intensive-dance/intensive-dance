"""Dutch National Ballet Academy (Amsterdam, NL) — its Amsterdam International
Summer School.

API FIRST: none. The Academy is part of the AHK (Academy of Theatre and Dance),
whose site runs on TYPO3 with no usable API — but the Summer School and its fees
live on two tidy, server-rendered pages, so this is an HTML scrape scoped to the
main content (`.container.content`) to keep the site-wide nav out.

DISCOVERY: the summer school offers a **Senior** course (aged 15-21, two weeks)
and a **Junior** course (aged 12-14, one week). We emit one `Offering` per
course, reading each course's own dates (from its section heading), age band and
fee from the pages, with the shared deadline and disciplines. The two courses
run on different dates, so dates are per-course. Dropped once its end is past.
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
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.atd.ahk.nl"
SUMMER = f"{BASE}/en/dance-programmes/dutch-national-ballet-academy/summer-school/"
FEES = f"{SUMMER}application-and-fees/"

ORG = Organization(
    name="Dutch National Ballet Academy",
    slug="dutch-national-ballet-academy",
    country="NL",
    city="Amsterdam",
)

# Course labels as printed on the pages; each becomes its own Offering, with its
# age band and fee read from the text by label (see _course_age / _course_fee).
_COURSES = ("Senior Course", "Junior Course")


def scrape(client: httpx.Client) -> list[Offering]:
    summary = _content(client, SUMMER)
    fees = _content(client, FEES)
    if not summary:
        return []

    today = date.today()
    season = _season(summary)

    deadline = _deadline(summary)
    genres = _genres(summary)
    offerings = []
    for label in _COURSES:
        ages = _course_age(summary, label)
        fee = _course_fee(fees, label)
        if ages is None and fee is None:
            continue
        start, end = _course_dates(summary, label, season)
        slug = label.lower().replace(" course", "").strip()
        offerings.append(
            Offering(
                id=f"dutch-national-ballet-academy/summer-school-{slug}-{season}",
                source=Source(
                    provider="dutch-national-ballet-academy", url=SUMMER, scrapedAt=now_utc()
                ),
                title=f"Amsterdam International Summer School — {label} {season}",
                genres=genres,
                ageRange=ages,
                organization=ORG,
                location=Location(city="Amsterdam", country="NL"),
                schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Amsterdam"),
                prices=[Price(amount=fee, currency="EUR", label=label, includes=["tuition"])]
                if fee
                else [],
                application=Application(
                    status="closed" if (deadline and deadline < today) else None,
                    deadline=deadline,
                    url=SUMMER,
                ),
            )
        )
    offerings.sort(key=lambda o: o.id)
    return offerings


# --- parsing ------------------------------------------------------------------

_YEAR = re.compile(r"Summer School\s+(20\d\d)", re.IGNORECASE)
# Each course heading prints its own span before the label, e.g.
# "06 - 17 July 2026 - Senior Course" / "13 - 17 July 2026 - Junior Course",
# so dates are read per-course (the courses don't share one span).
_DEADLINE = re.compile(
    r"open until\s+(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(20\d\d)", re.IGNORECASE
)


def _season(text: str) -> str:
    match = _YEAR.search(text)
    return match.group(1) if match else "unknown"


def _course_dates(text: str, label: str, season: str) -> tuple[date | None, date | None]:
    """Read the span from this course's own heading ("06 - 17 July 2026 - Senior Course")."""
    match = re.search(
        r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+("
        + parse.MONTHALT
        + r")\s+(\d{4})\s*[-–]\s*"
        + re.escape(label),
        text,
        re.IGNORECASE,
    )
    if not match:
        return None, None
    year, num = int(match.group(4)), parse.MONTHS[match.group(3).lower()]
    return date(year, num, int(match.group(1))), date(year, num, int(match.group(2)))


def _deadline(text: str) -> date | None:
    match = _DEADLINE.search(text)
    return (
        date(int(match.group(3)), parse.MONTHS[match.group(2).lower()], int(match.group(1)))
        if match
        else None
    )


def _course_age(text: str, label: str) -> dict | None:
    pattern = re.compile(
        re.escape(label) + r"\s+is for ballet students aged\s+(\d{1,2})\s*[-–]\s*(\d{1,2})",
        re.IGNORECASE,
    )
    return parse.extract_age_range(text, pattern)


def _course_fee(text: str, label: str) -> float | None:
    match = re.search(re.escape(label) + r":\s*€\s?([\d.,]+)", text, re.IGNORECASE)
    return parse.parse_amount(match.group(1)) if match else None


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical ballet", "ballet", "pas de deux")),
    ("contemporary", ("contemporary",)),
    ("character", ("caracter", "character")),
    ("repertoire", ("repertoire",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _content(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    if resp.status_code == 404:
        return ""
    resp.raise_for_status()
    tree = HTMLParser(resp.text)
    # Keep <header>: each course's dates sit in its section header
    # ("06 - 17 July 2026 - Senior Course"). The .container.content scope below
    # already excludes the site's nav/header chrome.
    for node in tree.css("script, style, noscript, nav, footer"):
        node.decompose()
    main = tree.css_first(".container.content") or tree.body
    return re.sub(r"\s+", " ", main.text(separator=" ")) if main else ""
