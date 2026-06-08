"""Royal Conservatoire The Hague — International Dance Intensive (The Hague, NL).

API FIRST: koncon.nl is NOT WordPress (GET /wp-json/ → 404). The page does
embed a `<script type="application/ld+json">` block, but it carries a generic
`WebPage` graph — no `Event`/`Course` node, so no structured dates. The
description field inside the `WebPage` node does contain the dated programme
summary ("24-29th August 2026", age "12-25"), and that is read from the ld+json
rather than parsing HTML attributes. The rest of the data (fees, deadline,
requirements) lives on the sub-page
`/en/dance-intensive/programme-and-registration`, parsed as plain HTML.

Direct httpx fetch works — no proxy needed, TLS is clean, no Cloudflare block.

DISCOVERY: one Offering per annual edition; the programme runs every August and
the dates are stated in the ld+json description on the main page. The slug is
year-stamped (e.g. `international-dance-intensive-2026`) to stay diffable across
editions.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - ld+json `WebPage.description` for dates + age range (not a full Event node)
  - Two-page scrape: main page (programme overview) + registration sub-page (fees,
    deadline, video requirements)
  - Date pattern: "24-29th August 2026" (day-range prefix + ordinal suffix + month)
  - Two fees: regular participant (€550 tuition) + RC student (€350 tuition)
  - Deadline: "before July 1st, 2026" (ordinal day)
  - Video requirement: YouTube-only, max 6 min, ballet + contemporary class
    material (centre work, no barre); optional 3-min solo for coaching applicants
  - Level: advanced, pre-professional
"""

from __future__ import annotations

import json
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
    Offering,
    Organization,
    Price,
    Requirement,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://www.koncon.nl"
PAGE_URL = f"{BASE}/en/dance-intensive"
REG_URL = f"{BASE}/en/dance-intensive/programme-and-registration"

SLUG = "royal-conservatoire-the-hague"
OFFERING_SLUG_PREFIX = "international-dance-intensive"

ORG = Organization(
    name="Royal Conservatoire The Hague",
    slug=SLUG,
    country="NL",
    city="The Hague",
)

_VIDEO_NOTE = (
    "YouTube video link required (max 6 minutes): ballet and contemporary class "
    "material (centre work; no barre). Dancers applying for individual coaching "
    "also submit a second link (max 3 minutes) of a pre-rehearsed solo or variation."
)

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet")),
    ("contemporary", ("contemporary",)),
]

_LEVEL_KEYWORDS: list[tuple[Level, tuple[str, ...]]] = [
    ("advanced", ("advanced",)),
    ("pre-professional", ("pre-professional", "preprofessional")),
    ("professional", ("professional",)),
]


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE_URL)
    resp.raise_for_status()
    main_html = resp.text

    reg_resp = client.get(REG_URL)
    reg_html = reg_resp.text if reg_resp.is_success else ""

    today = date.today()
    offerings = _build_offerings(main_html, reg_html, today)
    return offerings


def _build_offerings(main_html: str, reg_html: str, today: date) -> list[Offering]:  # noqa: ARG001
    description = _ld_description(main_html)
    if not description:
        return []

    start, end = _parse_dates(description)
    season = str(start.year) if start else _year_from_text(description)
    if not season:
        return []

    age_range = _parse_age_range(description)

    reg_text = _extract_text(reg_html)
    level = _parse_level(reg_text or description)
    prices = _parse_prices(reg_text)
    deadline = _parse_deadline(reg_text)
    requirements = _parse_requirements(reg_text)
    genres = _parse_genres(description + " " + reg_text)

    slug = f"{OFFERING_SLUG_PREFIX}-{season}"

    return [
        Offering(
            id=f"{SLUG}/{slug}",
            source=Source(provider=SLUG, url=PAGE_URL, scrapedAt=now_utc()),
            title=f"International Dance Intensive {season}",
            genres=genres,
            level=level,
            ageRange=age_range,
            organization=ORG,
            location=Location(
                venue="Royal Conservatoire The Hague",
                city="The Hague",
                country="NL",
            ),
            schedule=Schedule(
                season=season,
                start=start,
                end=end,
                timezone="Europe/Amsterdam",
                notes=_dates_note(description),
            ),
            prices=prices,
            application=Application(
                url=REG_URL,
                deadline=deadline,
                requirements=requirements,
                notes=_VIDEO_NOTE,
            ),
        )
    ]


def _ld_description(html: str) -> str:
    """Extract the programme description from the page's ld+json WebPage node."""
    blocks = re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
    for raw in blocks:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        graph = data.get("@graph", [data])
        for node in graph:
            if node.get("@type") == "WebPage":
                desc = node.get("description", "")
                if desc and "intensive" in desc.lower():
                    return desc
    return ""


def _extract_text(html: str) -> str:
    if not html:
        return ""
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


# --- dates -------------------------------------------------------------------

# "24-29th August 2026" — day range with optional ordinal suffix, then month+year.
# Also handles "24th-29th August 2026" form.
_DATE_RANGE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s*[-–]\s*(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(20\d\d)\b")


def _parse_dates(text: str) -> tuple[date | None, date | None]:
    m = _DATE_RANGE.search(text)
    if m:
        d1, d2, month, year = m.groups()
        mon = parse.MONTHS[month.lower()]
        yr = int(year)
        return date(yr, mon, int(d1)), date(yr, mon, int(d2))
    return None, None


def _year_from_text(text: str) -> str:
    m = _YEAR_RE.search(text)
    return m.group(1) if m else ""


def _dates_note(text: str) -> str | None:
    """Extract a short raw date phrase from the description for the notes field."""
    m = re.search(
        r"\d{1,2}(?:st|nd|rd|th)?\s*[-–]\s*\d{1,2}(?:st|nd|rd|th)?\s+"
        + "(?:"
        + parse.MONTHALT
        + r")\s+\d{4}",
        text,
        re.IGNORECASE,
    )
    return m.group(0) if m else None


# --- age range ---------------------------------------------------------------

# "12-25 years old" or "12 to 25"
_AGE = re.compile(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:years?\s*old|y\.o\.?)", re.IGNORECASE)


def _parse_age_range(text: str) -> dict | None:
    return parse.extract_age_range(text, _AGE)


# --- genres ------------------------------------------------------------------


def _parse_genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- level -------------------------------------------------------------------


def _parse_level(text: str) -> list[Level]:
    low = text.lower()
    return [lvl for lvl, keys in _LEVEL_KEYWORDS if any(k in low for k in keys)]


# --- prices ------------------------------------------------------------------

# "Advanced & Pre-professional Dance Intensive course fee:  € 550"
# "Royal Conservatoire student fee:  € 350"
_FEE = re.compile(
    r"([A-Za-z][A-Za-z &/-]{5,60}(?:course fee|student fee))\s*:\s*€\s*([\d.,]+)",
    re.IGNORECASE,
)


def _parse_prices(text: str) -> list[Price]:
    prices: list[Price] = []
    for label, raw in _FEE.findall(text):
        amount = parse.parse_amount(raw)
        if amount is None:
            continue
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=parse.clean(label),
                includes=["tuition"],
                notes="Includes all dance classes, workshops, and coaching. "
                "Accommodation and meals not included.",
            )
        )
    return prices


# --- deadline ----------------------------------------------------------------

# "before July 1st, 2026" or "1st of July" — ordinal day + month + year
_DEADLINE = re.compile(
    r"(?:before\s+)?(" + parse.MONTHALT + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})",
    re.IGNORECASE,
)
# "before 1st of July" variant
_DEADLINE_DAY_FIRST = re.compile(
    r"(?:before\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + parse.MONTHALT + r"),?\s*(\d{4})",
    re.IGNORECASE,
)


def _parse_deadline(text: str) -> date | None:
    # Search for the application-close sentence: "received before July 1st, 2026"
    # or "closing date … is July 1st, 2026". Use the month-first pattern first
    # (matches "before July 1st, 2026"), then the day-first fallback.
    for pattern, month_grp, day_grp, year_grp in (
        (_DEADLINE, 1, 2, 3),
        (_DEADLINE_DAY_FIRST, 2, 1, 3),
    ):
        m = pattern.search(text)
        if m:
            grps = m.groups()
            month_str = grps[month_grp - 1]
            day_str = grps[day_grp - 1]
            year_str = grps[year_grp - 1]
            try:
                return date(int(year_str), parse.MONTHS[month_str.lower()], int(day_str))
            except (KeyError, ValueError):
                continue
    return None


# --- requirements ------------------------------------------------------------


def _parse_requirements(text: str) -> list[Requirement]:
    # The registration page explicitly requires a YouTube video link — this
    # is the primary selection criterion (applications without videos are rejected).
    if re.search(r"\bvideo\b", text, re.IGNORECASE):
        return [VideoReq(specificity="specific", description=_VIDEO_NOTE)]
    return []
