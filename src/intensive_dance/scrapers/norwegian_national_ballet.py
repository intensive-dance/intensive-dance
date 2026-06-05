"""Norwegian National Ballet (Nasjonalballetten) — its summer course.

API FIRST: none usable. operaen.no runs on Optimizely/Episerver (not WordPress —
no `/wp-json/`), serves no JSON-LD `Event`/`Course`, and exposes no feed or search
API. The article is fully server-side rendered, so the whole course description is
in the static HTML — a one-page scrape, no JS. Cloudflare fronts the host but does
not challenge a realistic browser User-Agent, so a plain fetch suffices (no proxy).

DISCOVERY: the course runs once a year and lives at a per-year article slug that
DRIFTS and whose past editions are unpublished (404). The `sitemap.xml` lists only
section pages, not articles, and there is no usable search endpoint — so we probe
the predictable slug `.../articles/norwegian-national-ballets-summer-course-{year}/`
for the current and next year (the next-year edition can appear before the rollover
date) and accept the first page whose heading is actually the summer course. We
prefer the EN page over the Norwegian one. One page → one `Offering` per year.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-05):
  - DATES: "22.06.26 – 27.06.26" (DD.MM.YY) — one week in the Oslo Opera House.
  - AGES: "from 10 to 19" → bounded ageRange.
  - GENRES: the curriculum sentence lists classical ballet, modern ballet and
    variations/repertoire → classical + contemporary + repertoire (matched against
    the syllabus, not the surrounding prose).
  - PRICE: "NOK 2600 and includes tuition, lunch, and fruit" → one Price
    (tuition + meals). Accommodation/travel are explicitly the student's cost, so
    they are NOT in `includes`.
  - APPLICATION: MS Forms apply URL, deadline 23.02.2026, decisions by 20.03.2026
    (kept in the note). Requirements: a `video` of specific exercises (tendu/adagio,
    pirouette, petit/grand allegro, échappé/passé) — `specific` — waived for
    applicants from Wilhelmsen, KHIO and Ballettskolen (noted, not modelled).
  - LIFECYCLE: stays `scheduled`; we drop the edition once it has ended (end < today).
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
    Price,
    Requirement,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://www.operaen.no"
# Per-year EN article slug; the current edition is the first that resolves + matches.
ARTICLE = "{base}/en/articles/norwegian-national-ballets-summer-course-{year}/"
# MS Forms application for dancers (a separate form exists for accompanying teachers).
APPLY_URL = "https://forms.office.com/e/tXASbXnU6t"

ORG = Organization(
    name="Norwegian National Ballet", slug="norwegian-national-ballet", country="NO", city="Oslo"
)

_APPLY_NOTE = (
    "Applicants are evaluated by a jury and notified by 20.03.2026; places are "
    "allocated by skill level. A short video of set exercises is required, except "
    "for applicants from Wilhelmsen Akademiet, KHIO and Ballettskolen."
)


def scrape(client: httpx.Client) -> list[Offering]:
    today = date.today()
    for year in (today.year, today.year + 1):
        url = ARTICLE.format(base=BASE, year=year)
        resp = client.get(url, follow_redirects=True)
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        offering = _build_offering(resp.text, url, today)
        if offering is not None:
            return [offering]
    return []


def _build_offering(html: str, url: str, today: date) -> Offering | None:
    tree = HTMLParser(html)
    title = _title(tree)
    if title is None or "summer course" not in title.lower():
        return None  # not the summer-course article (slug drifted onto something else)

    text = _text(tree)
    start, end = _dates(text)
    if end is not None and end < today:
        return None  # this edition has already finished

    season = str(start.year) if start else _slug_year(url) or "unknown"

    return Offering(
        id=f"norwegian-national-ballet/summer-course-{season}",
        source=Source(provider="norwegian-national-ballet", url=url, scrapedAt=now_utc()),
        title=title,
        genres=_genres(text),
        kind="summer-school",
        level=_levels(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue="Oslo Opera House", city="Oslo", country="NO"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Oslo",
            notes=_dates_text(text),
        ),
        prices=_prices(text),
        application=Application(
            deadline=_deadline(text),
            url=APPLY_URL,
            requirements=_requirements(text),
            notes=_APPLY_NOTE,
        ),
    )


def _title(tree: HTMLParser) -> str | None:
    node = tree.css_first("h1")
    return parse.clean(node.text()) if node else None


def _text(tree: HTMLParser) -> str:
    for node in tree.css("script, style, noscript"):
        node.decompose()
    raw = tree.body.text(separator=" ") if tree.body else ""
    return parse.clean(raw)


def _slug_year(url: str) -> str | None:
    m = re.search(r"summer-course-(\d{4})", url)
    return m.group(1) if m else None


# --- dates: "22.06.26 – 27.06.26" (DD.MM.YY) ----------------------------------

# Two DD.MM.YY dates around an en/em dash or hyphen. Years are two-digit on this
# page, so we map them into the 2000s.
_DATE_RANGE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{2})\s*[-–—]\s*(\d{1,2})\.(\d{1,2})\.(\d{2})")


def _dates(text: str) -> tuple[date | None, date | None]:
    m = _DATE_RANGE.search(text)
    if not m:
        return None, None
    d1, mo1, y1, d2, mo2, y2 = (int(g) for g in m.groups())
    return date(2000 + y1, mo1, d1), date(2000 + y2, mo2, d2)


def _dates_text(text: str) -> str | None:
    m = _DATE_RANGE.search(text)
    return parse.clean(m.group(0)) if m else None


# --- ages: "from 10 to 19" ----------------------------------------------------

_AGE = re.compile(r"from\s+(\d{1,2})\s+to\s+(\d{1,2})", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    m = _AGE.search(text)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _levels(text: str) -> list[Level]:
    # Aimed at "ballet talents" / talented students — but the page never names a
    # technical level (beginner..professional), so we don't infer one.
    return []


# --- genres -------------------------------------------------------------------

# Scoped to the curriculum sentence ("instruction in classical ballet, modern
# ballet, variations/repertoire …") so surrounding prose can't leak a genre.
_CURRICULUM = re.compile(r"instruction in\s+(.+?)(?:\bas well as\b|\blectures\b|\.)", re.IGNORECASE)

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical ballet", "ballet")),
    ("contemporary", ("modern",)),
    ("repertoire", ("repertoire", "variations")),
]


def _genres(text: str) -> list[Genre]:
    m = _CURRICULUM.search(text)
    syllabus = m.group(1) if m else text
    return parse.match_genres(syllabus, _GENRE_KEYWORDS, default=["classical"])


# --- price: "NOK 2600 and includes tuition, lunch, and fruit" ------------------

_PRICE = re.compile(r"NOK\s+([\d.,\s]+?)\s+and includes\s+(.+?)(?:\.|Application)", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    m = _PRICE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    blurb = m.group(2).lower()
    includes = []
    if "tuition" in blurb:
        includes.append("tuition")
    # Lunch + daily fruit are meals; accommodation/travel are explicitly excluded.
    if "lunch" in blurb or "fruit" in blurb:
        includes.append("meals")
    return [
        Price(
            amount=amount,
            currency="NOK",
            label="Course fee",
            includes=includes,
            notes="Excludes accommodation and travel.",
        )
    ]


# --- application: deadline + video requirement --------------------------------

_DEADLINE = re.compile(
    r"closing date for applications is:?\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", re.IGNORECASE
)


def _deadline(text: str) -> date | None:
    m = _DEADLINE.search(text)
    if not m:
        return None
    d, mo, y = (int(g) for g in m.groups())
    return date(y, mo, d)


def _requirements(text: str) -> list[Requirement]:
    # The page lists named exercises to film (tendu/adagio, pirouette, allegro,
    # échappé/passé), so the video brief is `specific`, not open.
    if re.search(r"link to a short video", text, re.IGNORECASE):
        return [
            VideoReq(
                specificity="specific",
                description=(
                    "Short video: tendu & adagio in centre, pirouette, petit & grand "
                    "allegro, and échappé/passé in centre for dancers already on pointe. "
                    "Waived for applicants from Wilhelmsen Akademiet, KHIO and Ballettskolen."
                ),
            )
        ]
    return []
