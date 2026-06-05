"""TANZOLYMP — International Dance Festival & Competition, Berlin.

API FIRST: none usable. The site runs on WordPress, but the `wp/v2` content
endpoints answer 401 (an iThemes Security lock) and the feeds are empty, so the
REST API gives us nothing. The pages are server-side rendered, so the full text
is in the static HTML — a plain two-page scrape (homepage + `/participation`),
no JS, no proxy needed.

DISCOVERY: TANZOLYMP is an annual competition (`kind="competition"`), not a
multi-track program — one edition per year. We emit a SINGLE Offering for the
current edition. The edition number (Roman numeral) and the festival dates live
in a banner on the **homepage** (`/information` is a stale 2023 page — do not
read it). The rules, categories, age groups, fees and requirements live on
`/participation`, which is keyed to the same edition (matching Feb 2026 dates),
so we read both: dates + edition from the homepage, everything else from
participation.

LIFECYCLE CAVEAT: as of 2026-06-05 the latest published edition (XXIII, 12-17
Feb 2026) is already in the past and the next (XXIV, ~Feb 2027) is not yet
announced. We emit the XXIII edition faithfully — "past" is not stored, it is
derived by consumers from `schedule.end < today` (see models.py), so the runner
keeps the record rather than dropping it. The committed file therefore holds the
2026 edition until the 2027 banner replaces it.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-05):
  - kind="competition"; one Offering per edition, year-stamped slug.
  - TITLE: "TANZOLYMP XXIII — International Dance Festival" (Roman edition).
  - DATES: "FEBRUARY 12th - 17th, 2026" parsed from the homepage banner.
  - VENUE: Fontane Haus, Berlin (from the homepage program).
  - AGES: four declared age groups (8-12 / 13-15 / 16-18 / 19-25). The overall
    age_range spans the union (8-25); each group is kept as a Session.
  - GENRES: from the category list — Classical/Neoclassical (CP/CS) → classical
    + neoclassical, Modern/Contemporary (MP/MS) → contemporary, Folk (FP) →
    character. Pop/Jazz/Tap (DP) is out of scope for a ballet register and is
    not mapped to a genre.
  - PRICE: none. Fees are "calculated individually" → no Price, recorded as text.
  - REQUIREMENTS: a YouTube/online video link of the performance is mandatory on
    every application form → VideoReq(unspecific) (the dancer's own repertoire,
    not a set variation).
  - STATUS: derived from the application deadline vs. today (closed once past).
  - TEACHERS: the workshop/scholarship faculty listed on `/participation`.
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
    Schedule,
    Session,
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

BASE = "https://tanzolymp.com"
HOME = f"{BASE}/"
PARTICIPATION = f"{BASE}/participation"
REGISTRATION = f"{BASE}/registration"

ORG = Organization(name="TANZOLYMP", slug="tanzolymp", country="DE", city="Berlin")

_FEES_NOTE = (
    "Fees are calculated individually by TANZOLYMP (participation + a compulsory "
    "4-night stay at the Park Inn Hotel Alexanderplatz). No fixed price is published."
)


def scrape(client: httpx.Client) -> list[Offering]:
    home = client.get(HOME, follow_redirects=True)
    home.raise_for_status()
    participation = client.get(PARTICIPATION, follow_redirects=True)
    participation.raise_for_status()
    offering = _build_offering(home.text, participation.text, date.today())
    return [offering] if offering is not None else []


def _build_offering(home_html: str, participation_html: str, today: date) -> Offering | None:
    home = _text(home_html)
    edition = _edition(home)
    if edition is None:
        return None  # no current edition announced

    roman, start, end = edition
    part = _text(participation_html)
    season = str(start.year)
    teachers = _teachers(participation_html)

    return Offering(
        id=f"tanzolymp/{season}",
        source=Source(provider="tanzolymp", url=HOME, scrapedAt=now_utc()),
        title=f"TANZOLYMP {roman} — International Dance Festival",
        genres=_genres(part),
        kind="competition",
        ageRange=_age_range(part),
        organization=ORG,
        location=Location(venue=_venue(home), city="Berlin", country="DE"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Berlin",
            sessions=_sessions(part),
        ),
        teachers=teachers,
        application=Application(
            status=_status(part, today),
            deadline=_deadline(part),
            url=REGISTRATION,
            requirements=[VideoReq(specificity="unspecific", description=_video_note(part))],
            notes=_FEES_NOTE,
        ),
    )


def _text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    raw = tree.body.text(separator=" ") if tree.body else ""
    return parse.clean(raw)


# --- edition + dates (homepage banner) ----------------------------------------

# "TANZOLYMP XXIII INTERNATIONAL DANCE FESTIVAL | FEBRUARY 12th - 17th, 2026" —
# one month spanning both days, with a trailing year. Roman numeral = edition.
_EDITION = re.compile(
    r"TANZOLYMP\s+([IVXLC]+)\s+INTERNATIONAL DANCE FESTIVAL\s*\|\s*"
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})(?:st|nd|rd|th)?\s*[-–—]\s*"
    r"(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})",
    re.IGNORECASE,
)


def _edition(home_text: str) -> tuple[str, date, date] | None:
    m = _EDITION.search(home_text)
    if not m:
        return None
    roman, month_name, d1, d2, year = m.groups()
    month = parse.MONTHS[month_name.lower()]
    return roman.upper(), date(int(year), month, int(d1)), date(int(year), month, int(d2))


# "Venue: Fontane Haus, Königshorster Str. 6, 13439 Berlin" — the recurring
# competition venue in the homepage program.
_VENUE = re.compile(r"Venue:\s*(Fontane Haus)[,\s]", re.IGNORECASE)


def _venue(home_text: str) -> str | None:
    m = _VENUE.search(home_text)
    return parse.clean(m.group(1)) if m else None


# --- age groups (participation) -----------------------------------------------

# "Group 1: from 8-12 years old" ... "Group 4: from 19-25 years old".
_AGE_GROUP = re.compile(
    r"Group\s+(\d)\s*:\s*from\s+(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*years old",
    re.IGNORECASE,
)


def _age_groups(text: str) -> list[tuple[int, int, int]]:
    return [(int(m.group(1)), int(m.group(2)), int(m.group(3))) for m in _AGE_GROUP.finditer(text)]


def _age_range(text: str) -> dict | None:
    groups = _age_groups(text)
    if not groups:
        return None
    return {"min": min(g[1] for g in groups), "max": max(g[2] for g in groups)}


def _sessions(text: str) -> list[Session]:
    return [
        Session(label=f"Age group {num}", ageRange={"min": lo, "max": hi})
        for num, lo, hi in _age_groups(text)
    ]


# --- genres (participation category list) -------------------------------------

# Map the competition's own category labels to genres. Pop/Jazz/Tap (DP) is
# out of scope for a ballet register, so it is deliberately absent.
_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical",)),
    ("neoclassical", ("neoclassical",)),
    ("contemporary", ("modern", "contemporary")),
    ("character", ("folk dance",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- requirements / application -----------------------------------------------

_DEADLINE = re.compile(
    r"submitted by\s+(" + parse.MONTHALT + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})",
    re.IGNORECASE,
)


def _deadline(text: str) -> date | None:
    m = _DEADLINE.search(text)
    if not m:
        return None
    month_name, day, year = m.groups()
    return date(int(year), parse.MONTHS[month_name.lower()], int(day))


def _status(text: str, today: date):
    deadline = _deadline(text)
    if deadline is None:
        return None
    return "closed" if today > deadline else "open"


def _video_note(text: str) -> str | None:
    # The rules require an online video link of the dancer's own performance —
    # quote it verbatim so the requirement is auditable, not paraphrased.
    if re.search(r"link to an online video", text, re.IGNORECASE):
        return (
            "Every participant / group must submit a link to an online video of "
            "the performance (YouTube or other website) on the application form."
        )
    return None


# --- teachers (participation faculty roll) ------------------------------------

# Each workshop/scholarship teacher is a separate WPBakery rich-text module that
# holds ONLY the (accented, correctly spelled) name — the right structural unit
# to read, since the collapsed body text runs the names together with no
# delimiter and the image `alt`s are noisy ("Agnes" vs "Agnès", "photo by …").
# A faculty name is two-to-four capitalised words (incl. accents / initials).
_NAME = re.compile(r"^(?:[A-ZÀ-Ý][\w.'’-]*\.?\s+){1,3}[A-ZÀ-Ý][\w.'’-]*$")


def _teachers(html: str) -> list[Teacher]:
    tree = HTMLParser(html)
    names: list[str] = []
    for node in tree.css(".fl-module-rich-text"):
        text = parse.clean(node.text())
        if _NAME.match(text) and text not in names:
            names.append(text)
    return [Teacher(name=name) for name in names]
