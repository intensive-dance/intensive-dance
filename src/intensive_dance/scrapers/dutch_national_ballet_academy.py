"""Dutch National Ballet Academy (Amsterdam, NL) — its Amsterdam International
Summer School.

API FIRST: none. The Academy is part of the AHK (Academy of Theatre and Dance),
whose site runs on TYPO3 with no usable API — but the Summer School and its fees
live on two tidy, server-rendered pages, so this is an HTML scrape scoped to the
main content (`.container.content`) to keep the site-wide nav out.

DISCOVERY: the summer school offers a **Senior** course (aged 15-21, two weeks)
and a **Junior** course (aged 12-14, one week). We emit one `Offering` per
course, reading each course's age band and fee from the pages, with the shared
season dates, deadline and disciplines. Dropped once the season's end is past.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

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

ORG = Organization(name="Dutch National Ballet Academy", slug="dutch-national-ballet-academy", country="NL", city="Amsterdam")

# Course label as printed on the pages → (slug fragment, weeks of duration text).
_COURSES = ("Senior Course", "Junior Course")


def scrape(client: httpx.Client) -> list[Offering]:
    summary = _content(client, SUMMER)
    fees = _content(client, FEES)
    if not summary:
        return []

    today = date.today()
    season = _season(summary)
    start, end = _date_range(summary, season)
    if end is not None and end < today:
        return []  # this year's school is over

    deadline = _deadline(summary)
    genres = _genres(summary)
    offerings = []
    for label in _COURSES:
        ages = _course_age(summary, label)
        fee = _course_fee(fees, label)
        if ages is None and fee is None:
            continue
        slug = label.lower().replace(" course", "").strip()
        offerings.append(
            Offering(
                id=f"dutch-national-ballet-academy/summer-school-{slug}-{season}",
                source=Source(provider="dutch-national-ballet-academy", url=SUMMER, scrapedAt=now_utc()),
                title=f"Amsterdam International Summer School — {label} {season}",
                genres=genres,
                kind="summer-school",
                ageRange=ages,
                organization=ORG,
                location=Location(city="Amsterdam", country="NL"),
                schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Amsterdam"),
                prices=[Price(amount=fee, currency="EUR", label=label, includes=["tuition"])] if fee else [],
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

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"],
        start=1,
    )
}
_MONTHALT = "|".join(_MONTHS)
_YEAR = re.compile(r"Summer School\s+(20\d\d)", re.IGNORECASE)
# "6 - 17 July 2026" or "July 6 to 17, 2026".
_RANGE = re.compile(
    r"(\d{1,2})\s*[-–to]+\s*(\d{1,2})\s+(" + _MONTHALT + r")|(" + _MONTHALT + r")\s+(\d{1,2})\s*(?:[-–]|to)\s*(\d{1,2})",
    re.IGNORECASE,
)
_DEADLINE = re.compile(r"open until\s+(\d{1,2})\s+(" + _MONTHALT + r")\s+(20\d\d)", re.IGNORECASE)


def _season(text: str) -> str:
    match = _YEAR.search(text)
    return match.group(1) if match else "unknown"


def _date_range(text: str, season: str) -> tuple[date | None, date | None]:
    year = int(season) if season.isdigit() else None
    if year is None:
        return None, None
    match = _RANGE.search(text)
    if not match:
        return None, None
    if match.group(3):  # "<d1> - <d2> <Month>"
        d1, d2, month = match.group(1), match.group(2), match.group(3)
    else:  # "<Month> <d1> to <d2>"
        month, d1, d2 = match.group(4), match.group(5), match.group(6)
    num = _MONTHS[month.lower()]
    return date(year, num, int(d1)), date(year, num, int(d2))


def _deadline(text: str) -> date | None:
    match = _DEADLINE.search(text)
    return date(int(match.group(3)), _MONTHS[match.group(2).lower()], int(match.group(1))) if match else None


def _course_age(text: str, label: str) -> dict | None:
    match = re.search(re.escape(label) + r"\s+is for ballet students aged\s+(\d{1,2})\s*[-–]\s*(\d{1,2})", text, re.IGNORECASE)
    return {"min": int(match.group(1)), "max": int(match.group(2))} if match else None


def _course_fee(text: str, label: str) -> float | None:
    match = re.search(re.escape(label) + r":\s*€\s?([\d.,]+)", text, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1).replace(".", "").replace(",", "."))


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical ballet", "ballet", "pas de deux")),
    ("contemporary", ("contemporary",)),
    ("character", ("caracter", "character")),
    ("repertoire", ("repertoire",)),
]


def _genres(text: str) -> list[Genre]:
    low = text.lower()
    return [g for g, keys in _GENRE_KEYWORDS if any(k in low for k in keys)] or ["classical"]


def _content(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    if resp.status_code == 404:
        return ""
    resp.raise_for_status()
    tree = HTMLParser(resp.text)
    for node in tree.css("script, style, noscript, nav, header, footer"):
        node.decompose()
    main = tree.css_first(".container.content") or tree.body
    return re.sub(r"\s+", " ", main.text(separator=" ")) if main else ""
