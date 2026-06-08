"""Nationaltheater Mannheim — NTM Tanz Summer Intensive, Mannheim DE.

API FIRST: No WordPress (`/wp-json/` → 404). No `<script type="application/ld+json">`
on any page. No `__NEXT_DATA__`. The site is a custom CMS (German theatre platform).
The dedicated programme page at `/das-theater/tanz/summer-intensive/` is server-
rendered and fetches cleanly with a plain httpx client — no proxy needed.

DISCOVERY: One Summer Intensive per year; a single Offering. The INFORMATION block
is an English-language `<ul>` inside `class="richtext" lang="en"` — the dates,
location, tuition fee, and application status live there as labelled list items.
The AUDITION PROCEDURE section documents the requirements: headshot + video link.

WHAT THIS SCRAPER EXERCISES:
- Plain HTML scrape (no API, no proxy), structured INFORMATION block
- `application.status = "closed"` (site says "+++ Application is closed +++")
- `application.requirements`: HeadshotReq + VideoReq (specific)
- `prices`: single EUR fee with meals included (`tuition`, `meals`)
- `level`: professional (ages 18+, explicitly "professional dancers")
- `genres`: classical + contemporary (daily classes alternate between them)
- Verified live 2026-06-08
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    ApplicationStatus,
    Genre,
    HeadshotReq,
    Level,
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

PAGE = "https://www.nationaltheater-mannheim.de/das-theater/tanz/summer-intensive/"

ORG = Organization(
    name="Nationaltheater Mannheim",
    slug="nationaltheater-mannheim",
    country="DE",
    city="Mannheim",
)

# The venue for the final showing; daily classes are at the Nationaltheater itself.
_VENUE_FINAL = "Tanzhaus Käfertal"


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text, date.today())


def _build_offerings(html: str, today: date) -> list[Offering]:  # noqa: ARG001
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()

    # Pull text only from the English-language rich-text blocks (lang="en"), which
    # contain the structured INFORMATION and AUDITION PROCEDURE sections.  Concatenate
    # them into one string for the downstream helpers.
    en_nodes = tree.css('[lang="en"]')
    en_text = parse.clean(" ".join(n.text(separator=" ") for n in en_nodes))

    start, end = _date_range(en_text)
    anchor = start or end
    if anchor is None:
        return []
    season = str(anchor.year)

    return [
        Offering(
            id=f"nationaltheater-mannheim/summer-intensive-{season}",
            source=Source(
                provider="nationaltheater-mannheim",
                url=PAGE,
                scrapedAt=now_utc(),
            ),
            title=f"NTM Tanz Summer Intensive {season}",
            genres=_genres(en_text),
            level=_levels(en_text),
            ageRange=_age_range(en_text),
            organization=ORG,
            location=Location(venue=_VENUE_FINAL, city="Mannheim", country="DE"),
            schedule=Schedule(
                season=season,
                start=start,
                end=end,
                timezone="Europe/Berlin",
                notes="Monday, July 13th – Sunday, July 19th 2026",
            ),
            teachers=_teachers(en_text),
            prices=_prices(en_text),
            application=Application(
                status=_app_status(en_text),
                deadline=_deadline(en_text),
                url=PAGE,
                requirements=_requirements(en_text),
                notes=_app_notes(en_text),
            ),
        )
    ]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

# "Monday, July 13th – Sunday, July 19th 2026"
# An optional weekday+comma prefix sits before each month name on the NTM page.
_RANGE_FULL = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})(?:st|nd|rd|th)?\s*[-–]\s*"
    r"(?:\w+,\s*)?("  # optional weekday prefix before the second month name
     + parse.MONTHALT + r")\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE_FULL.search(text)
    if not m:
        return None, None
    m1, d1, m2, d2, year = m.groups()
    y = int(year)
    return (
        date(y, parse.MONTHS[m1.lower()], int(d1)),
        date(y, parse.MONTHS[m2.lower()], int(d2)),
    )


# "25 professional dancers (ages 18+, X/M/F)" → min 18, no max
_AGE = re.compile(r"ages?\s*(\d{1,2})\s*\+", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    m = _AGE.search(text)
    if not m:
        return None
    return {"min": int(m.group(1)), "max": None}


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet")),
    ("contemporary", ("contemporary",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical", "contemporary"])


_LEVEL_KEYWORDS: list[tuple[Level, tuple[str, ...]]] = [
    ("professional", ("professional dancers", "professional training")),
]


def _levels(text: str) -> list[Level]:
    low = text.lower()
    return [lvl for lvl, keys in _LEVEL_KEYWORDS if any(k in low for k in keys)]


# "€ 650,00 (including daily lunch, excluding accommodation)"
# Anchor on the € symbol so the date digits earlier in the text don't match.
_FEE = re.compile(r"€\s*([\d.,]+)")


def _prices(text: str) -> list[Price]:
    m = _FEE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    # Source says "including daily lunch" — maps to meals; it's also the tuition.
    includes: list[PriceInclude] = ["tuition", "meals"]
    notes = "Including daily lunch; accommodation excluded."
    return [
        Price(amount=amount, currency="EUR", label="Tuition fee", includes=includes, notes=notes)
    ]


_APP_CLOSED = re.compile(r"application\s+is\s+closed", re.IGNORECASE)


def _app_status(text: str) -> ApplicationStatus | None:
    if _APP_CLOSED.search(text):
        return "closed"
    if re.search(r"registration\s+is\s+open|registration\s+opens", text, re.IGNORECASE):
        return "open"
    return None


# "Registration closes: February 28th 2026"
_DEADLINE = re.compile(
    r"[Rr]egistration\s+closes[:\s]+(?:\w+,\s+)?("
    + parse.MONTHALT
    + r")\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})",
    re.IGNORECASE,
)


def _deadline(text: str) -> date | None:
    m = _DEADLINE.search(text)
    if not m:
        return None
    month, day, year = m.groups()
    return date(int(year), parse.MONTHS[month.lower()], int(day))


def _app_notes(text: str) -> str | None:
    """Return the raw closed/open status text from the INFORMATION block."""
    m = re.search(r"(\+\+\+ Application is closed \+\+\+)", text, re.IGNORECASE)
    return m.group(1) if m else None


def _requirements(text: str) -> list[Requirement]:
    """Parse from the AUDITION PROCEDURE section.

    The source states: (1) attach a recent headshot, (2) share one video link
    (Showreel + 1 min improvisation, max 3 min).  Both are required.
    """
    reqs: list[Requirement] = []
    if re.search(r"headshot", text, re.IGNORECASE):
        reqs.append(HeadshotReq())
    if re.search(r"video\s+link|showreel|vimeo|youtube", text, re.IGNORECASE):
        reqs.append(
            VideoReq(
                specificity="specific",
                description=(
                    "One video link (YouTube or Vimeo): Showreel "
                    "(stage or studio) + 1 minute of improvisation, unedited, "
                    "to original music. Total max 3 minutes."
                ),
            )
        )
    return reqs


def _teachers(text: str) -> list[Teacher]:
    """Parse named teachers from the programme description.

    Stephan Thoss is named as artistic director / course leader; Luis Tena Torres
    and Albert Galindo are named as choreographers leading the new creation.
    """
    teachers: list[Teacher] = []
    if "Stephan Thoss" in text:
        teachers.append(
            Teacher(
                name="Stephan Thoss",
                role="Artistic Director / Course Leader",
            )
        )
    if "Luis Tena Torres" in text:
        teachers.append(
            Teacher(
                name="Luis Tena Torres",
                role="Choreographer (new creation)",
            )
        )
    if "Albert Galindo" in text:
        teachers.append(
            Teacher(
                name="Albert Galindo",
                role="Choreographer (new creation)",
            )
        )
    return teachers
