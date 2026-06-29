"""GradPro Summer Intensive — Birmingham, GB.

API FIRST: none usable. GradPro runs on **Wix** (`name="generator"
content="Wix.com Website Builder"`, no `/wp-json/`, only a generic `WebSite`
ld+json), but the Summer Intensive page is server-side rendered, so the full
text is present in the static HTML — a one-page scrape, no JS needed.

DISCOVERY: a single page (`/summer-intensive-2026`) describes the current
edition as **two distinct one-week courses** at Birmingham Royal Ballet's Dance
Hub. The weeks differ by cohort (Week 1 = end of first vocational-training year;
Week 2 = end of second year / graduating), so we emit **one Offering per week**
(distinct dates + cohort note) rather than fold them into one span — the same
per-track rule the model asks for. Both are season-keyed from the parsed year so
the ids roll forward when the page advances an edition.

WHAT THE PAGE GIVES US (verified live 2026-06-26):
  - DATES: "Week 1: Monday 20th July to Friday 24th July 2026" and "Week 2:
    Monday 27th July to Friday 31st July 2026" — ordinal-suffixed, weekday-
    prefixed, "to"-separated day-month/day-month-year spans.
  - LEVEL: open to students "in their first or second year of vocational
    training" / "graduating in July 2026" → pre-professional. The per-week cohort
    distinction is kept verbatim in `schedule.notes`.
  - GENRES: "company style class", "repertoire", "pointe work", "pas de deux" →
    classical + repertoire + pointe. (Choreography is described as guest-led
    group work, not a taught contemporary class, so contemporary is not claimed.)
  - AGES / PRICES: not stated on the page (admission is by training year, not
    age; no fee is published) → left null/empty.
  - APPLICATION: an "Apply Now" form (`/apply-now`); no audition material, fee or
    deadline is stated for the intensive (the "5th July" closing date on the page
    belongs to the adjacent G2P programme, not this course) → requirements/status
    left unknown, with the apply URL and contact recorded.

WHAT THIS SCRAPER EXERCISES: multi-Offering-per-page split by cohort; ordinal/
weekday date spans; pre-professional level; empty age/price/requirements
(fail-open); raise-on-degraded-fetch (no week markers → exception, not []).
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
    Offering,
    Organization,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.gradpro.co.uk"
PAGE = f"{BASE}/summer-intensive-2026"
APPLY_PAGE = f"{BASE}/apply-now"

ORG = Organization(
    name="GradPro",
    slug="gradpro-summer-intensive",
    country="GB",
    city="Birmingham",
)

_APPLY_NOTE = "Apply via GradPro's online form; questions to julie@gradpro.co.uk."

# Zero-width / soft-hyphen characters Wix sprinkles through the markup, which
# would otherwise split "20th" / "July" mid-token before the date regex runs.
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿­"), None)

# "Week 1: Monday 20th July to Friday 24th July 2026" — weekday words prefix each
# bound but aren't captured; the start day-month borrows the trailing year.
_WEEK = re.compile(
    r"Week\s*(\d)\s*:\s*\w+\s+(\d{1,2})(?:st|nd|rd|th)?\s+("
    + parse.MONTHALT
    + r")\s+to\s+\w+\s+(\d{1,2})(?:st|nd|rd|th)?\s+("
    + parse.MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)

# The sentence that distinguishes each week's cohort, kept as the schedule note.
_COHORT = {
    "1": "Week 1 focuses on students at the end of their first year of vocational training.",
    "2": (
        "Week 2 focuses on students at the end of their second year of vocational "
        "training or graduating in July 2026."
    ),
}

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("company style class", "company-style class", "technique", "pas de deux")),
    ("repertoire", ("repertoire",)),
    ("pointe", ("pointe",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text)


def _build_offerings(html: str) -> list[Offering]:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    raw = tree.body.text(separator=" ") if tree.body else ""
    text = parse.clean(raw.translate(_ZERO_WIDTH))

    genres = _genres(text)
    offerings: list[Offering] = []
    for m in _WEEK.finditer(text):
        week = m.group(1)
        start = date(int(m.group(6)), parse.MONTHS[m.group(3).lower()], int(m.group(2)))
        end = date(int(m.group(6)), parse.MONTHS[m.group(5).lower()], int(m.group(4)))
        season = str(end.year)
        offerings.append(
            Offering(
                id=f"gradpro-summer-intensive/summer-intensive-week-{week}-{season}",
                source=Source(provider="gradpro-summer-intensive", url=PAGE, scrapedAt=now_utc()),
                title=f"Summer Intensive {season} — Week {week}",
                genres=genres,
                level=_LEVEL,
                organization=ORG,
                location=Location(
                    venue="The Dance Hub (Birmingham Royal Ballet)",
                    city="Birmingham",
                    country="GB",
                ),
                schedule=Schedule(
                    season=season,
                    start=start,
                    end=end,
                    timezone="Europe/London",
                    notes=_COHORT.get(week),
                ),
                application=Application(url=APPLY_PAGE, notes=_APPLY_NOTE),
            )
        )

    if not offerings:
        # Single, always-current page: a 200 that lacks the week markers is a
        # degraded fetch (challenge/partial render). Raise so run.py keeps the
        # prior store instead of overwriting it with [] (IDR-24 / audit #316).
        raise ValueError("GradPro: no Summer Intensive week markers found in page text")
    return offerings


_LEVEL: list[Level] = ["pre-professional"]
