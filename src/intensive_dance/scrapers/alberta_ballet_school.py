"""Alberta Ballet School — Calgary, Alberta, Canada — its Summer Intensive.

API FIRST: none usable. The site runs on a headless CMS fronted by **SEOmatic**
(no `/wp-json/`); its only `ld+json` is generic `WebPage`/`Organization` SEO
metadata, no `Event`/`Course`. But the Summer Intensive page is fully
server-rendered — the dates, disciplines, grade bands and audition routes are all
present in the static HTML, so it's a one-page `selectolax` text scrape, no JS.

DISCOVERY: one `Offering` per dated **session**. The 2026 Summer Intensive runs as
two parallel three-week blocks (June 29 - July 17 and July 20 - August 7), each a
separately-bookable edition with the same curriculum/grades/audition — so each
becomes its own Offering (a shared 6-week start/end would misrepresent two distinct
3-week sessions).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-11):
  - DATES: two US-style cross-month ranges "June 29 - July 17, 2026" /
    "July 20 - August 7, 2026" (5-group `parse_multi_month_range`).
  - GENRES: matched against the disciplines sentence — ballet→classical, pointe
    work→pointe, repertoire/variations→repertoire, contemporary→contemporary,
    character dance→character. Pas de deux (partnering) and physical conditioning
    have no genre and don't leak.
  - AGES: stated as **school grades** (Junior Grades 5-8, Senior Grades 9-12), not
    numbers — mapped via the Alberta grade schedule (Grade N ≈ age N+5) to ages
    10-18, with the raw grade bands kept in `schedule.notes`.
  - REQUIREMENTS: audition by Audition Tour, online, or video → `video`/unspecific.
  - PRICES: not stated on this page ("visit our website for up-to-date tuition") →
    left empty (fail open).
  - LEVEL: pre-professional intensive training (also a final audition for the
    full-year program).
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
    Requirement,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

SLUG = "alberta-ballet-school"
BASE = "https://www.albertaballetschool.com"
PAGE = f"{BASE}/summer-intensive"
AUDITION_URL = f"{BASE}/auditions/information"

ORG = Organization(name="Alberta Ballet School", slug=SLUG, country="CA", city="Calgary")
LOCATION = Location(venue="Alberta Ballet School", city="Calgary", country="CA")

# Junior Grades 5-8, Senior Grades 9-12. Alberta enters Grade 1 at age 6, so a
# grade maps to roughly age = grade + 5 at the school-year start; the oldest
# (Grade 12) dancers are graduating at 17-18.
_AGE_RANGE = {"min": 10, "max": 18}
_GRADES_NOTE = "Junior: Grades 5-8; Senior: Grades 9-12"

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet",)),
    ("pointe", ("pointe",)),
    ("repertoire", ("repertoire", "variations")),
    ("contemporary", ("contemporary",)),
    ("character", ("character",)),
]

# Two cross-month ranges, e.g. "June 29 - July 17, 2026".
_RANGE = re.compile(
    rf"({parse.MONTHALT})\s+(\d{{1,2}})\s*-\s*({parse.MONTHALT})\s+(\d{{1,2}}),\s*(\d{{4}})",
    re.IGNORECASE,
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text)


def _build_offerings(html: str) -> list[Offering]:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    genres: list[Genre] = parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])
    requirements: list[Requirement] = (
        [VideoReq(specificity="unspecific")] if "audition" in text.lower() else []
    )
    hours_note = "Students train 30 hours per week." if "30 hours" in text else None

    offerings: list[Offering] = []
    for index, match in enumerate(_RANGE.finditer(text), start=1):
        m1, d1, m2, d2, year = match.groups()
        y = int(year)
        start = date(y, parse.MONTHS[m1.lower()], int(d1))
        end = date(y, parse.MONTHS[m2.lower()], int(d2))
        season = year
        notes = "; ".join(part for part in (_GRADES_NOTE, hours_note) if part)
        offerings.append(
            Offering(
                id=f"{SLUG}/summer-intensive-{season}-session-{index}",
                source=Source(provider=SLUG, url=PAGE, scrapedAt=now_utc()),
                title=f"Summer Intensive {season} (Session {index})",
                genres=genres,
                level=["pre-professional"],
                ageRange=_AGE_RANGE,
                organization=ORG,
                location=LOCATION,
                schedule=Schedule(season=season, start=start, end=end, notes=notes),
                application=Application(url=AUDITION_URL, requirements=requirements),
            )
        )
    return offerings
