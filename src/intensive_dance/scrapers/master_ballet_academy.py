"""Master Ballet Academy (MBA) — Scottsdale, AZ, US — its Summer Intensive.

API FIRST: none usable. MBA runs on **Wix** (`parastorage`/`x-wix-request-id`,
no `/wp-json/`), which exposes no public content API we may use. But the Summer
Intensive page is server-side rendered (note the `ssr-caching` response header),
so the full prose is present in the static HTML — a one-page scrape, no JS needed.

DISCOVERY: one `Offering` per dated edition. The site lists three summer-ish
programs, of which only one is an in-scope student intensive:
  - `/summerintensiveauditions` — **Summer Intensive 2026**, the audition-only,
    technique-focused 6-week ballet intensive. EMITTED. Season-keyed from the
    parsed dates so the id rolls forward when the page advances a year.
  - `/summercamps` — recreational day camps for ages 3-9 (Tap/Jazz/Tumbling mixes).
    Out of scope (not a ballet student intensive).
  - `/grandprixintensive` — the Labor-Day "Grand Prix Intensive". DROPPED: the
    page carries an unyeared "September 4-7" header contradicted by stale prior
    "August 29th – September 1st 2025" prose, so the edition can't be dated
    faithfully (emit nothing rather than guess — the NZ-school precedent).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-11):
  - DATES: "June 15, 2026 to July 24, 2026" — US `Month DD, YYYY` range, both
    years explicit (6-group `parse_multi_month_range`).
  - GENRES: matched against the curriculum sentence (ballet/variations/character/
    contemporary) — the page also names musical theater and flamenco, which aren't
    in the genre enum and so don't leak.
  - REQUIREMENTS: audition-only — a headshot + a *first arabesque* photo (a
    defined pose), plus a video for the video-audition route (`video`/unspecific).
  - AGES/PRICES/DEADLINE: none stated for the program itself (the "age 13 and up"
    is a *housing* condition, not eligibility), so all left null — fail open.
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
    HeadshotReq,
    Location,
    Offering,
    Organization,
    PhotosReq,
    Requirement,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://www.masterballetacademy.com"
PAGE = f"{BASE}/summerintensiveauditions"

ORG = Organization(
    name="Master Ballet Academy",
    slug="master-ballet-academy",
    country="US",
    city="Scottsdale",
)

_APPLY_NOTE = (
    "By audition only. Auditions can be done via Video, Zoom or In Person. A "
    "headshot and first arabesque photo are required; the video-audition route "
    "also requires a video."
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    offering = _build_offering(resp.text)
    return [offering] if offering is not None else []


def _build_offering(html: str) -> Offering | None:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    start, end = _date_range(text)
    anchor = end or start
    if anchor is None:
        return None  # no dated edition parseable
    season = str(anchor.year)

    return Offering(
        id=f"master-ballet-academy/summer-intensive-{season}",
        source=Source(provider="master-ballet-academy", url=PAGE, scrapedAt=now_utc()),
        title=f"Summer Intensive {season}",
        genres=_genres(text),
        organization=ORG,
        location=Location(venue="Master Ballet Academy studios", city="Scottsdale", country="US"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="America/Phoenix",
            notes=_schedule_note(text),
        ),
        application=Application(
            url=PAGE,
            requirements=_requirements(text),
            notes=_APPLY_NOTE,
        ),
    )


# --- parsing ------------------------------------------------------------------

# "June 15, 2026 to July 24, 2026" — US Month DD, YYYY with both years explicit.
_RANGE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2}),?\s+(\d{4})"
    r"\s+to\s+"
    r"(" + parse.MONTHALT + r")\s+(\d{1,2}),?\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    return parse.parse_multi_month_range(text, _RANGE)


_WEEKS = re.compile(r"(\d{1,2})-week program", re.IGNORECASE)
_MIN_WEEKS = re.compile(r"minimum of (\d{1,2}) weeks", re.IGNORECASE)


def _schedule_note(text: str) -> str | None:
    parts: list[str] = []
    if (m := _WEEKS.search(text)) is not None:
        parts.append(f"{m.group(1)}-week program")
    if (m := _MIN_WEEKS.search(text)) is not None:
        parts.append(f"minimum of {m.group(1)} weeks required")
    if "Summer Showcase" in text:
        parts.append("weeks 4-6 required to participate in the Summer Showcase")
    return "; ".join(parts) if parts else None


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet technique", "ballet partnering", "classical")),
    ("repertoire", ("variations", "repertoire")),
    ("character", ("character dance", "character")),
    ("contemporary", ("contemporary",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _requirements(text: str) -> list[Requirement]:
    reqs: list[Requirement] = []
    low = text.lower()
    if "headshot" in low:
        reqs.append(HeadshotReq())
    if "arabesque" in low:
        reqs.append(PhotosReq(specificity="defined-poses", poses=["first arabesque"]))
    if "submit a video" in low:
        reqs.append(VideoReq(specificity="unspecific"))
    return reqs
