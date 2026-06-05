"""John Cranko School (Stuttgart, DE) — its Summer School.

API FIRST: none. The school runs a niche theatre CMS ("spiritec WebCMS") with no
JSON API or structured data, but the Summer School lives on a single, tidy,
server-rendered page (`/summer_school/`) — so this is a one-page HTML scrape.

DISCOVERY: one `Offering` — the current Summer School. We read its dates, age
band, fee, application deadline and the video-audition brief straight off the
page, and drop the offering once its end date is past (same "keep only live"
rule as the other scrapers). The page is in German.
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
    PriceInclude,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://www.john-cranko-schule.de"
SUMMER_SCHOOL = f"{BASE}/summer_school/"

ORG = Organization(name="John Cranko School", slug="john-cranko-schule", country="DE", city="Stuttgart")

# The video brief stated on the page (≈15–20 min: barre / centre / jumps).
_VIDEO_BRIEF = (
    "Apply by video (~15–20 min) showing excerpts from barre, centre and jumps "
    "(plus a variation if available)."
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(SUMMER_SCHOOL)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    offering = _build_offering(resp.text, date.today())
    return [offering] if offering is not None else []


def _build_offering(html: str, today: date) -> Offering | None:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = re.sub(r"[ \t]+", " ", tree.body.text(separator="\n")) if tree.body else ""
    blob = parse.clean(text)

    start, end = _date_range(blob)
    if end is not None and end < today:
        return None  # last cycle already finished
    anchor = start or end
    season = str(anchor.year) if anchor else _year(blob)

    deadline = _deadline(blob)
    return Offering(
        id=f"john-cranko-schule/summer-school-{season}",
        source=Source(provider="john-cranko-schule", url=SUMMER_SCHOOL, scrapedAt=now_utc()),
        title=f"John Cranko School Summer School {season}".strip(),
        genres=_genres(blob),
        kind="summer-school",
        ageRange=_age_range(blob),
        organization=ORG,
        location=Location(city="Stuttgart", country="DE"),
        schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Berlin", notes=_dates_note(blob)),
        prices=_prices(blob),
        application=Application(
            status="closed" if (deadline and deadline < today) else None,
            deadline=deadline,
            url=SUMMER_SCHOOL,
            requirements=[VideoReq(specificity="specific", description=_VIDEO_BRIEF)],
            notes=_VIDEO_BRIEF,
        ),
    )


# --- German parsing -----------------------------------------------------------
#
# The page is in German, so the month names are this scraper's own — only the
# regex-building (`parse.months_alt`) and language-agnostic helpers are shared.

_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}
_MONTHALT = parse.months_alt(_MONTHS)
# "1. Juni 2026" — German day-month-year.
_DATE = re.compile(r"(\d{1,2})\.\s*(" + _MONTHALT + r")\s+(\d{4})", re.IGNORECASE)
# The course span: "… 1. Juni 2026 bis Samstag, 6. Juni 2026".
_RANGE = re.compile(
    r"(\d{1,2})\.\s*(" + _MONTHALT + r")\s+(\d{4})\s+bis\s+(?:\w+,?\s+)?(\d{1,2})\.\s*(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
_AGE = re.compile(r"Alter\s+(\d{1,2})\s*[-–]\s*(\d{1,2})", re.IGNORECASE)
_YEAR = re.compile(r"\b(20\d\d)\b")
_MONEY = re.compile(r"(\d[\d.]*),(\d{2})\s*€")


def _date(day: str, month: str, year: str) -> date:
    return date(int(year), _MONTHS[month.lower()], int(day))


def _date_range(text: str) -> tuple[date | None, date | None]:
    match = _RANGE.search(text)
    if match:
        d1, m1, y1, d2, m2, y2 = match.groups()
        return _date(d1, m1, y1), _date(d2, m2, y2)
    single = _DATE.search(text)
    return (_date(*single.groups()), None) if single else (None, None)


def _dates_note(text: str) -> str | None:
    match = _RANGE.search(text)
    return parse.clean(match.group(0)) if match else None


def _year(text: str) -> str:
    match = _YEAR.search(text)
    return match.group(1) if match else "unknown"


def _deadline(text: str) -> date | None:
    match = re.search(r"Einsendeschluss[^.]*?(\d{1,2})\.\s*(" + _MONTHALT + r")\s+(\d{4})", text, re.IGNORECASE)
    return _date(*match.groups()) if match else None


def _age_range(text: str) -> dict | None:
    match = _AGE.search(text)
    return {"min": int(match.group(1)), "max": int(match.group(2))} if match else None


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("klassisches ballett", "ballett")),
    ("contemporary", ("contemporary",)),
    ("repertoire", ("repertoire",)),
    ("character", ("spanischer tanz", "charakter", "character")),
    ("pointe", ("spitzenschuh", "spitze")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _prices(text: str) -> list[Price]:
    match = _MONEY.search(text)
    if not match:
        return []
    amount = float(f"{match.group(1).replace('.', '')}.{match.group(2)}")
    # The page states the fee covers tuition + the closing performance, excluding
    # accommodation and meals.
    includes: list[PriceInclude] = ["tuition"]
    if "aufführung" in text.lower() or "vorstellung" in text.lower():
        includes.append("performance")
    return [Price(amount=amount, currency="EUR", label="Tuition (6 days incl. performance)", includes=includes)]
