"""Goh Ballet Academy — Vancouver summer intensives.

API FIRST — clean WordPress REST, but only via the ``?rest_route=`` query form,
no proxy. gohballet.com runs WordPress (``/wp-json/`` index is 200) and exposes
its programs as a ``programs`` custom post type. The school's whole program
catalogue lives in ACF, and the Vancouver summer offerings are one record
(``programs/2472``, slug ``summer-programs``) whose ``acf.contents`` is a repeater
of ``class_information`` blocks — one block per summer offering, the dated edition
encoded in the block ``name`` ("…Ages 7-18+ | July 6–31, 2026"), and the
curriculum / levels in nested ``accordion`` lists. We read that one record.

  Trap: the host's rewrite **blocks the path form** ``/wp-json/wp/v2/…`` (it
  301s to a themed 404), so ``wp.fetch_all`` can't be used; the **query form**
  ``{base}/?rest_route=/wp/v2/programs/{id}`` returns the JSON on a plain fetch
  with our UA (no datacenter-IP block, no proxy). The WP site lives under
  ``…/content`` while pages render at the bare host.

DISCOVERY — one ``Offering`` per dated, day-specific summer **intensive** block
for ages 7+, keyed ``goh-ballet-academy/{block-slug}-{year}``. The Vancouver
record's ``contents`` repeater holds six blocks; we keep only those whose name
carries a day-specific date range ("Month D–D") *and* an age floor of 7+:

  - "Ballet & Beyond – July International Summer Intensive" (Ages 7-18+, July
    6–31, 2026) — two sessions (Competition Prep July 6-17; Choreography &
    Repertoire July 20-31).
  - "Passion & Precision - August Summer Program" (Ages 7-18+, Aug 10–20, 2026)
    — culminates in a final-day performance.

Dropped (discovery, not a date cut): the Children's Summer Dance Camps (ages
4-7) and Saturday Summer Ballet (ages 3-10) are recreational children's programs,
not student intensives; the "Summer Programs Toronto" and "中文" blocks are bare
cross-links (no date / no age). The age floor + day-specific date test separates
the intensives from the camps without hardcoding which blocks are which.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - AGES open-topped — "Ages 7-18+" → ``{"min": 7, "max": None}`` (the "+" makes
    the band open above 18; an Offering keeps that null upper bound).
  - SESSIONS — Ballet & Beyond states two dated sub-sessions in a ``list_set``;
    each becomes a ``Session`` under the one Offering (same fee/ages, distinct
    dates). Passion & Precision is a single span → one session.
  - GENRES matched against each block's own Curriculum accordion list only (so
    one block's disciplines don't leak into the other). Flamenco / Musical
    Theatre have no Genre enum, so they simply don't map.
  - REQUIREMENTS = ``video``/unspecific — enrollment for ages 7+ requires an
    Evaluation Assessment (a complimentary in-person group audition); the source
    states no submitted photo/video brief, so it's an unspecific audition with a
    clarifying note, and the application URL is the audition booking link.
  - PRICES — the record states no tuition figure anywhere (fees are quoted on
    enquiry), so we fail open with no Price rather than invent one.
  - TEACHERS — both blocks list "Guest Instructors: TBA", so ``teachers`` stays
    empty (the marquee guest faculty isn't yet named for this cycle).
"""

from __future__ import annotations

import html
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
    Session,
    Source,
    VideoReq,
    now_utc,
)

PROVIDER = "goh-ballet-academy"
# The WP install lives under /content; the public program page renders at the host.
API_BASE = "https://www.gohballet.com/content"
# The Vancouver summer-programs `programs` record (slug `summer-programs`).
SUMMER_PROGRAM_ID = 2472
PAGE_URL = "https://www.gohballet.com/program/summer-programs/"

ORG = Organization(
    name="Goh Ballet Academy",
    slug=PROVIDER,
    country="CA",
    city="Vancouver",
)
LOCATION = Location(venue="Goh Ballet Academy", city="Vancouver", country="CA")
TIMEZONE = "America/Vancouver"

# Enrollment for ages 7+ requires an Evaluation Assessment — a complimentary
# in-person group audition (no stated submitted-material brief).
_AUDITION_NOTE = (
    "Enrollment into the Junior & Senior summer programs (ages 7+) requires an "
    "Evaluation Assessment — a complimentary in-person group audition. No "
    "submitted photo or video brief is stated."
)


def scrape(client: httpx.Client) -> list[Offering]:
    # The host blocks the /wp-json/wp/v2/ path form; the ?rest_route= query form
    # returns the same JSON on a plain fetch (no proxy needed).
    resp = client.get(
        f"{API_BASE}/",
        params={"rest_route": f"/wp/v2/programs/{SUMMER_PROGRAM_ID}"},
    )
    resp.raise_for_status()
    return _build_offerings(resp.json(), date.today())


def _build_offerings(record: dict, today: date) -> list[Offering]:  # noqa: ARG001
    acf = record.get("acf") or {}
    url = record.get("link") or PAGE_URL

    offerings: list[Offering] = []
    for block in acf.get("contents") or []:
        if (block.get("acf_fc_layout") or "") != "class_information":
            continue
        title, ages, start, end, dates_text = _parse_name(block.get("name") or "")
        # In scope only when the block names a day-specific dated edition AND an
        # age floor of 7+ — that excludes the children's camps (ages 3-10/4-7,
        # no day numbers) and the bare Toronto / 中文 cross-link blocks.
        if start is None or ages is None or (ages["min"] or 0) < 7:
            continue

        curriculum = _curriculum_text(block)
        offerings.append(
            Offering(
                id=f"{PROVIDER}/{_slug(title)}-{start.year}",
                source=Source(provider=PROVIDER, url=url, scrapedAt=now_utc()),
                title=title,
                genres=_genres(curriculum),
                level=_levels(_levels_text(block)),
                ageRange=ages,
                organization=ORG,
                location=LOCATION,
                schedule=Schedule(
                    season=str(start.year),
                    start=start,
                    end=end,
                    timezone=TIMEZONE,
                    sessions=_sessions(block, start, end),
                    notes=dates_text or None,
                ),
                application=Application(
                    url=_audition_url(block),
                    requirements=[VideoReq(specificity="unspecific", description=_AUDITION_NOTE)],
                    notes=_AUDITION_NOTE,
                ),
            )
        )
    offerings.sort(key=lambda o: (o.schedule.start or date.min, o.id))
    return offerings


# ---------------------------------------------------------------------------
# Block name → title / ages / dates
# ---------------------------------------------------------------------------
# A block name is "<Title> <p…>Ages A-B[+] | <Month D–D, YYYY></p>" — the title
# is the text before the inline age/date `<p>`; the age band and the dated edition
# are in that `<p>`.

_AGE = re.compile(r"Ages?\s+(\d{1,2})\s*[-–]\s*(\d{1,2})(\+)?", re.IGNORECASE)
# A day-specific range: "Month D – D, YYYY" or "Month D – Month D, YYYY". A
# month-only span ("July - August, 2026", no day numbers) deliberately does NOT
# match — those are the recreational children's blocks.
_RANGE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})\s*[-–]\s*"
    r"(?:(" + parse.MONTHALT + r")\s+)?(\d{1,2}),?\s*(20\d\d)",
    re.IGNORECASE,
)


def _plain(raw: str) -> str:
    return parse.clean(HTMLParser(html.unescape(raw)).text()) if raw else ""


def _parse_name(name: str) -> tuple[str, dict | None, date | None, date | None, str]:
    """(title, age_range, start, end, dates_text) from a block `name`."""
    text = _plain(name)
    age_m = _AGE.search(text)
    ages = _age_range(age_m)
    start, end, dates_text = _parse_range(text)
    # The title is the run before the "Ages …" / date metadata in the name.
    cut = min(
        (m.start() for m in (age_m, _RANGE.search(text)) if m),
        default=len(text),
    )
    title = text[:cut].strip(" |–-").strip()
    return title or text, ages, start, end, dates_text


def _age_range(m: re.Match | None) -> dict | None:
    if not m:
        return None
    # A trailing "+" ("7-18+") opens the band above the stated upper bound.
    upper = None if m.group(3) else int(m.group(2))
    return {"min": int(m.group(1)), "max": upper}


def _parse_range(text: str) -> tuple[date | None, date | None, str]:
    m = _RANGE.search(text)
    if not m:
        return None, None, ""
    m1, d1, m2, d2, year = m.groups()
    yr = int(year)
    start = date(yr, parse.MONTHS[m1.lower()], int(d1))
    end = date(yr, parse.MONTHS[(m2 or m1).lower()], int(d2))
    return start, end, m.group(0).strip()


def _slug(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    # Drop generic tail words so the slug stays the offering's distinctive name.
    base = re.sub(r"-(international-)?summer-(intensive|program)$", "", base)
    return base or "summer"


# ---------------------------------------------------------------------------
# Sessions (dated sub-sessions stated in a list_set)
# ---------------------------------------------------------------------------
# Ballet & Beyond splits into two dated sessions ("Session One … July 6–17,
# 2026"); each <strong>…date</strong> line is one Session. A block with no such
# dated sub-list collapses to a single Session spanning the block's dates.


def _sessions(block: dict, start: date | None, end: date | None) -> list[Session]:
    sessions: list[Session] = []
    for item in _list_items(block):
        label = item.split(":")[0].strip(" –-") if ":" in item else item.strip()
        s, e, _ = _parse_range(item)
        if s is not None:
            sessions.append(Session(label=label or None, start=s, end=e, notes=item.strip()))
    if sessions:
        return sessions
    return [Session(start=start, end=end)]


def _list_items(block: dict) -> list[str]:
    """The <strong>-led prose lines of the block's top-level `list_set`."""
    for part in block.get("main_contents") or []:
        if (part.get("acf_fc_layout") or "") == "list_set":
            return [_plain(row.get("text") or "") for row in part.get("list") or []]
    return []


# ---------------------------------------------------------------------------
# Curriculum / Levels (nested in an accordion_set)
# ---------------------------------------------------------------------------


def _accordion_panel(block: dict, title: str) -> list[dict]:
    """The inner content layouts of the accordion panel named `title`."""
    for part in block.get("main_contents") or []:
        if (part.get("acf_fc_layout") or "") != "accordion_set":
            continue
        for panel in part.get("accordion") or []:
            if (panel.get("title") or "").strip().lower() == title.lower():
                return panel.get("acc_inside_contents") or []
    return []


def _panel_list_text(panel: list[dict]) -> str:
    """Flatten a panel's `list` / `list_with_title` items into one string."""
    lines: list[str] = []
    for layout in panel:
        rows = layout.get("list")
        if rows is None and isinstance(layout.get("list_with_title"), dict):
            rows = layout["list_with_title"].get("list")
        for row in rows or []:
            lines.append(_plain(row.get("text") or ""))
    return "\n".join(lines)


def _curriculum_text(block: dict) -> str:
    return _panel_list_text(_accordion_panel(block, "Curriculum"))


def _levels_text(block: dict) -> str:
    return _panel_list_text(_accordion_panel(block, "Levels"))


# ---------------------------------------------------------------------------
# Genres / levels
# ---------------------------------------------------------------------------
# Matched against the block's own Curriculum list only. Flamenco / Musical
# Theatre have no Genre enum and so don't map.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical ballet", "ballet")),
    ("pointe", ("pointe",)),
    ("contemporary", ("contemporary", "modern")),
    ("repertoire", ("repertoire", "variations", "pas de deux", "partnering")),
]


def _genres(curriculum: str) -> list[Genre]:
    return parse.match_genres(curriculum, _GENRE_KEYWORDS, default=["classical"])


# The two blocks name their level tiers with bespoke labels (En Marché … En
# Volée; Aspen … Spruce), but each tier's gloss states the skill stage. We map
# only the stages the gloss names; "advanced dancers" anchors advanced.
_LEVEL_KEYWORDS: list[tuple[Level, tuple[str, ...]]] = [
    ("beginner", ("early steps", "first steps", "discovery", "wonder")),
    ("intermediate", ("transitioning", "develop skills", "increasing")),
    ("advanced", ("advanced", "artistry", "professional practice", "maturity")),
]


def _levels(levels_text: str) -> list[Level]:
    levels: list[Level] = []
    low = levels_text.lower()
    for level, keys in _LEVEL_KEYWORDS:
        if any(k in low for k in keys) and level not in levels:
            levels.append(level)
    return levels


# ---------------------------------------------------------------------------
# Application URL (the audition/assessment booking link in the block)
# ---------------------------------------------------------------------------


def _audition_url(block: dict) -> str | None:
    for part in block.get("main_contents") or []:
        if (part.get("acf_fc_layout") or "") != "link_set":
            continue
        link = part.get("link")
        if isinstance(link, dict) and (url := link.get("url")):
            return url
    return None
