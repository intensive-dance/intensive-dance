"""Canada's National Ballet School (NBS) — Toronto summer intensives.

API FIRST
The site (https://www.nbs-enb.ca) runs a custom CMS (its own ``/api/sections/``
HAL surface — *not* WordPress: ``GET /wp-json/`` → 404, no ``__NEXT_DATA__``).
The ld+json on the event pages is only an ``Organization``/``EducationalOrganization``
/``Service`` stub (no schema.org ``Event`` with dates), and the registration
fees live behind a JS-rendered Amilia store (``app.amilia.com``) the NBS page
itself never states. So we read the event pages' server-rendered HTML directly —
a plain ``httpx`` fetch with our UA works, no proxy needed (the datacenter IP is
not blocked). The headline date range is in ``<meta name="description">`` and the
event name in ``<meta property="og:title">``; the per-stream / per-track detail
is the prose inside ``div.article-content``.

DISCOVERY
Two public, dated, short-term summer programs, each emitting one Offering per
distinct stream/track (they differ in genre, level, ages and audition policy, so
folding them would lose information):

  /events/young-dancers-program-summer-immersion  (Aug 4-14, 2026) — two streams:
    - Open Dance      : ages 7-18, no audition, daily ballet + hip hop/contemp/jazz
    - Intensive Ballet: by application (placement class day 1, min 3-4 yrs training),
                        ballet repertoire/choreography + a concluding presentation
  /events/adult-ballet-summer-intensive           (Aug 4-15, 2026) — two dated
    level-tracks (ballet, conditioning, composition/repertoire), adults:
    - Aug 4-8 : Elementary + Intermediate levels
    - Aug 11-15: Beginner level (marked "Full" — kept, see below)

We do NOT scrape the Adult *Winter* Term, teacher Ideas-Exchange, LEAD summit, or
the Adaptive program (out of scope: long-term / teacher PD / adaptive, not a
student ballet intensive).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08)
  - Multi-edition discovery from a fixed event-slug registry, one Offering per
    stream/track; ended/"Full" cycles are KEPT (IDR-24 — "past"/sold-out is
    derived consumer-side, never stored).
  - REQUIREMENTS branches: Open Dance / Adult → ``[NoneReq]`` ("No application or
    audition is required"); Intensive Ballet → ``video``/unspecific — it's an
    *application* (online form + day-1 placement class), with no specific brief.
  - GENRES matched against each stream's own prose only (Open Dance names hip
    hop/contemporary/jazz alongside ballet; Intensive Ballet is classical +
    repertoire) so a stream's genres don't leak across.
  - AGES: Open Dance states "ages 7-18"; the others state none → null age_range.
  - PRICES: the NBS page states no fee (fees live on the JS Amilia store), so we
    fail open with no Price rather than invent one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    Genre,
    Level,
    Location,
    NoneReq,
    Offering,
    Organization,
    Requirement,
    Schedule,
    Session,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://www.nbs-enb.ca"
PROVIDER = "canadas-national-ballet-school"

ORG = Organization(
    name="Canada's National Ballet School",
    slug=PROVIDER,
    country="CA",
    city="Toronto",
)
LOCATION = Location(venue="Canada's National Ballet School", city="Toronto", country="CA")
TIMEZONE = "America/Toronto"

# Intensive Ballet asks for an application via an online form plus a day-one
# placement class — an admission process, not a defined audition brief.
_APPLICATION_NOTE = (
    "Admission to the Intensive Ballet stream is by application only "
    "(submitted via the NBS online form). A placement class on the first day "
    "determines the dancer's level; a minimum of 3-4 years of dance training is expected."
)
_OPEN_NOTE = "No application or audition is required."


@dataclass(frozen=True)
class _Track:
    """One stream/track on an event page → one Offering."""

    slug: str  # offering-slug suffix
    title: str  # human title for this track
    # Anchor text of the heading that introduces this track's prose block in
    # div.article-content. The prose between this heading and the next known
    # heading is the track's own copy (matched for genres/ages/requirements).
    heading: str


@dataclass(frozen=True)
class _Event:
    path: str  # /events/<slug>
    season: str
    tracks: list[_Track] = field(default_factory=list)


# The two public student/community summer intensives, with their stream/track
# split. Headings mirror the live page's heading anchors verbatim.
EVENTS: list[_Event] = [
    _Event(
        path="/events/young-dancers-program-summer-immersion",
        season="2026",
        tracks=[
            _Track("open-dance-2026", "Summer Immersion — Open Dance", "Open Dance"),
            _Track(
                "intensive-ballet-2026", "Summer Immersion — Intensive Ballet", "Intensive Ballet"
            ),
        ],
    ),
    _Event(
        path="/events/adult-ballet-summer-intensive",
        season="2026",
        tracks=[
            _Track(
                "adult-week-1-2026",
                "Adult Ballet Summer Intensive — Elementary & Intermediate",
                "August 4-8, 2026",
            ),
            _Track(
                "adult-week-2-2026",
                "Adult Ballet Summer Intensive — Beginner",
                "August 11-15, 2026",
            ),
        ],
    ),
]

# All headings we slice the article on, so a track's prose stops at the next one.
_ALL_HEADINGS: list[str] = [t.heading for e in EVENTS for t in e.tracks]


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
# Two shapes: a single-month range "August 4-14, 2026" (the headline / a track
# heading) and a cross-month "Month D – Month D, YYYY". Year always present.

_RANGE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})\s*[-–]\s*"
    r"(?:(" + parse.MONTHALT + r")\s+)?(\d{1,2}),?\s*(20\d\d)",
    re.IGNORECASE,
)


def _parse_range(text: str) -> tuple[date | None, date | None]:
    """Parse 'Month D-D, YYYY' or 'Month D – Month D, YYYY' → (start, end)."""
    m = _RANGE.search(text)
    if not m:
        return None, None
    m1, d1, m2, d2, year = m.groups()
    yr = int(year)
    start_month = parse.MONTHS[m1.lower()]
    end_month = parse.MONTHS[(m2 or m1).lower()]
    return date(yr, start_month, int(d1)), date(yr, end_month, int(d2))


# ---------------------------------------------------------------------------
# Genres (matched against each track's own prose only)
# ---------------------------------------------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet",)),
    ("contemporary", ("contemporary", "hip hop", "jazz")),
    ("repertoire", ("repertoire", "repertory")),
]


def _genres(prose: str) -> list[Genre]:
    # Every NBS stream centres on ballet (a daily ballet class / ballet
    # repertoire), so classical is the guaranteed base; other genres are added
    # only when the stream's own copy names them. We force classical first
    # because a stream can mention "repertoire" without the word "ballet" in its
    # own slice (the Intensive Ballet copy does), and match_genres' default fires
    # only when *nothing* matches.
    matched = parse.match_genres(prose, _GENRE_KEYWORDS)
    return ["classical", *[g for g in matched if g != "classical"]]


# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------

_LEVEL_KEYWORDS: list[tuple[Level, tuple[str, ...]]] = [
    ("beginner", ("beginner",)),
    ("intermediate", ("intermediate", "elementary")),
    ("advanced", ("advanced",)),
]


def _levels(prose: str) -> list[Level]:
    levels: list[Level] = []
    low = prose.lower()
    for level, keys in _LEVEL_KEYWORDS:
        if any(k in low for k in keys) and level not in levels:
            levels.append(level)
    # The Intensive Ballet stream is for "experienced dancers" preparing for the
    # next season — pre-professional, even though it names no level word.
    if not levels and "experienced dancers" in low:
        levels.append("pre-professional")
    return levels


# ---------------------------------------------------------------------------
# Ages
# ---------------------------------------------------------------------------

_AGE = re.compile(r"\bages?\s+(\d{1,2})\s*[-–]\s*(\d{1,2})\b", re.IGNORECASE)


def _age_range(prose: str) -> dict | None:
    m = _AGE.search(prose)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------


def _requirements(prose: str) -> list[Requirement]:
    low = prose.lower()
    if "no application or audition is required" in low:
        return [NoneReq()]
    if "by application only" in low or "application for" in low:
        # An application + day-one placement class, no stated video/photo brief.
        return [VideoReq(specificity="unspecific", description=_APPLICATION_NOTE)]
    return []


def _requirement_note(prose: str) -> str | None:
    low = prose.lower()
    if "no application or audition is required" in low:
        return _OPEN_NOTE
    if "by application only" in low or "application for" in low:
        return _APPLICATION_NOTE
    return None


# ---------------------------------------------------------------------------
# Article slicing
# ---------------------------------------------------------------------------


def _article_text(html: str) -> str:
    """The prose of div.article-content as a single cleaned string (or '')."""
    tree = HTMLParser(html)
    node = tree.css_first("div.article-content")
    return parse.clean(node.text()) if node is not None else ""


def _track_prose(article: str, heading: str) -> str:
    """The article slice owned by `heading` — from it to the next known heading.

    Anchoring on the track headings keeps each stream's genre/age/requirement
    keywords from leaking into a sibling stream.
    """
    low = article.lower()
    start = low.find(heading.lower())
    if start < 0:
        return ""
    start += len(heading)
    ends = [e for h in _ALL_HEADINGS if h != heading and (e := low.find(h.lower(), start)) >= 0]
    return article[start : min(ends)].strip() if ends else article[start:].strip()


def _meta(tree: HTMLParser, name: str) -> str:
    node = tree.css_first(f'meta[name="{name}"]')
    return (node.attributes.get("content") or "").strip() if node is not None else ""


# ---------------------------------------------------------------------------
# Apply URLs (register / application links in the article)
# ---------------------------------------------------------------------------


def _apply_url(html: str, heading: str) -> str | None:
    """The register/apply href whose anchor text names this track, if any."""
    tree = HTMLParser(html)
    node = tree.css_first("div.article-content")
    if node is None:
        return None
    needle = heading.lower()
    for a in node.css("a"):
        text = parse.clean(a.text()).lower()
        if needle in text and (href := a.attributes.get("href")):
            return href
    return None


# ---------------------------------------------------------------------------
# Per-track Offering builder (pure; tested directly)
# ---------------------------------------------------------------------------


def _build_offerings(html: str, url: str, event: _Event) -> list[Offering]:
    tree = HTMLParser(html)
    headline = _meta(tree, "description")  # e.g. "August 4-14, 2026"
    article = _article_text(html)

    offerings: list[Offering] = []
    for track in event.tracks:
        prose = _track_prose(article, track.heading)
        # A track heading that is itself a date range ("August 4-8, 2026") carries
        # the track's dates; otherwise the headline range applies to the stream.
        start, end = _parse_range(track.heading)
        if start is None:
            start, end = _parse_range(headline)
        dates_note = track.heading if _RANGE.search(track.heading) else (headline or None)

        offerings.append(
            Offering(
                id=f"{PROVIDER}/{track.slug}",
                source=Source(provider=PROVIDER, url=url, scrapedAt=now_utc()),
                title=track.title,
                genres=_genres(prose),
                level=_levels(prose),
                ageRange=_age_range(prose),
                organization=ORG,
                location=LOCATION,
                schedule=Schedule(
                    season=event.season,
                    start=start,
                    end=end,
                    timezone=TIMEZONE,
                    sessions=[Session(label=track.title, start=start, end=end)],
                    notes=dates_note,
                ),
                application=Application(
                    url=_apply_url(html, track.heading),
                    requirements=_requirements(prose),
                    notes=_requirement_note(prose),
                ),
            )
        )
    return offerings


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def scrape(client: httpx.Client) -> list[Offering]:
    offerings: list[Offering] = []
    for event in EVENTS:
        url = f"{BASE}{event.path}"
        resp = client.get(url)
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        offerings += _build_offerings(resp.text, url, event)
    offerings.sort(key=lambda o: (o.schedule.start or date.min, o.id))
    return offerings
