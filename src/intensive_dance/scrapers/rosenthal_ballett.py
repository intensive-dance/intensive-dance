"""Rosenthal Ballett (DE) — Summer Intensive, Düsseldorf.

API FIRST
The site (https://www.rosenthal-ballett.de) is a **Wix** build with no WordPress
REST and no schema.org `Event`/`Course` `ld+json`. But Wix server-side renders
the content, so a plain fetch of `/summer-intensive` returns the full program
text in the static HTML — no JS render or proxy needed. We read the rendered body
text (stripping Wix's zero-width spaces) and parse it structurally.

DISCOVERY — the studio runs recreational adult classes year-round, plus
standalone adult weekend workshops (out of scope), but its one dated, public,
audition-gated student intensive is a single Offering:
  THE ROSENTHAL BALLETT SUMMER INTENSIVE — 21 Jul – 2 Aug 2026, Düsseldorf. The
  page forms TWO audition groups that differ only by age (A: 13–15 / pre-pro,
  B: 16–19), same dates and fee, so it is ONE Offering with one `Session` per
  group (gender-neutral), and an overall age band of 13–19.

GENRES: scoped to the daily-schedule list ("Floor Barre … Classical Ballet
Technique … Variation Coaching … Repertoire Focus … works of Jiří Kylián"), not
loose prose → classical, repertoire, contemporary (the Kylián repertoire focus).
Pointe appears only in the audition centre brief, not as a taught class, so it is
not emitted.

PRICE: a single €890 tuition fee for the two weeks. Accommodation is not
mentioned → tuition only.

REQUIREMENTS: admission by video audition only, with a specific barre + centre
combination list → VideoReq(specific). Deadline 30 Apr 2026.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-11)
- Wix SSR HTML read as body text (zero-width spaces stripped), parsed by labels.
- One Offering, two age-only `Session`s (Group A / Group B) + an overall band.
- English date range, a single tuition Price, VideoReq(specific) with a deadline.
- Named faculty roster parsed from an inline "including …" sentence.
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
    Schedule,
    Session,
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

URL = "https://www.rosenthal-ballett.de/summer-intensive"

ORG = Organization(
    name="Rosenthal Ballett", slug="rosenthal-ballett", country="DE", city="Düsseldorf"
)

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿"), None)

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical ballet", "ballet technique")),
    ("repertoire", ("repertoire",)),
    ("contemporary", ("kylián", "kylian", "contemporary")),
]


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(URL)
    resp.raise_for_status()
    return [_build_offering(resp.text)]


def _page_text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    body = tree.body.text(separator=" ") if tree.body else ""
    return parse.clean(body.translate(_ZERO_WIDTH))


def _build_offering(html: str) -> Offering:
    text = _page_text(html)
    start, end = _date_range(text)
    season = str((start or date(2026, 1, 1)).year)
    sessions = _sessions(text)
    return Offering(
        id=f"rosenthal-ballett/summer-intensive-{season}",
        source=Source(provider="rosenthal-ballett", url=URL, scrapedAt=now_utc()),
        title=f"Summer Intensive {season}",
        genres=_genres(text),
        ageRange=_age_range(sessions),
        organization=ORG,
        location=Location(venue="Rosenthal Ballett", city="Düsseldorf", country="DE"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Berlin",
            sessions=sessions,
            notes=_dates_notes(text),
        ),
        teachers=_teachers(text),
        prices=_prices(text),
        application=_application(text),
    )


# "Dates: 21 July – 2 August 2026" (single trailing year).
_RANGE = re.compile(
    r"Dates:\s*(\d{1,2})\s+("
    + parse.MONTHALT
    + r")\s*[–-]\s*(\d{1,2})\s+("
    + parse.MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    d1, mon1, d2, mon2, year = m.groups()
    y = int(year)
    return date(y, parse.MONTHS[mon1.lower()], int(d1)), date(
        y, parse.MONTHS[mon2.lower()], int(d2)
    )


def _dates_notes(text: str) -> str | None:
    m = _RANGE.search(text)
    return m.group(0) if m else None


# Each group block: "Group A : Younger dance students (min. 13 to 15 years) …",
# bounded by the next group or the deadline line. Ages are read from the block.
_GROUP = re.compile(
    r"Group\s+([AB])\s*:?\s*(.*?)(?=\s*[-–]?\s*Group\s+[AB]\b|Video\s+Submission|🎥|$)",
    re.IGNORECASE | re.DOTALL,
)
_GROUP_AGE = re.compile(r"min\.?\s*(\d{1,2})\s*to\s*(\d{1,2})\s*years", re.IGNORECASE)


def _sessions(text: str) -> list[Session]:
    sessions: list[Session] = []
    for letter, blurb in _GROUP.findall(text):
        age = _GROUP_AGE.search(blurb)
        sessions.append(
            Session(
                label=f"Group {letter.upper()}",
                ageRange={"min": int(age.group(1)), "max": int(age.group(2))} if age else None,
                notes=parse.clean(f"Group {letter.upper()}: {blurb}"),
            )
        )
    return sessions


def _age_range(sessions: list[Session]) -> dict | None:
    bounds = [s.age_range for s in sessions if s.age_range]
    if not bounds:
        return None
    return {
        "min": min(b["min"] for b in bounds if b.get("min") is not None),
        "max": max(b["max"] for b in bounds if b.get("max") is not None),
    }


def _genres(text: str) -> list[Genre]:
    m = re.search(r"includes:(.*?)Set in the heart", text, re.IGNORECASE | re.DOTALL)
    scope = m.group(1) if m else text
    return parse.match_genres(scope, _GENRE_KEYWORDS, default=["classical"])


_FACULTY = re.compile(
    r"including\s+(.*?),?\s+and\s+distinguished\s+guest", re.IGNORECASE | re.DOTALL
)


def _teachers(text: str) -> list[Teacher]:
    m = _FACULTY.search(text)
    if not m:
        return []
    names = [parse.clean(n) for n in m.group(1).split(",")]
    return [Teacher(name=n) for n in names if n]


_FEE = re.compile(r"Fee:\s*(\d[\d.,]*)\s*€")


def _prices(text: str) -> list[Price]:
    m = _FEE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    return [Price(amount=amount, currency="EUR", label="Tuition", includes=["tuition"])]


_DEADLINE = re.compile(
    r"Deadline:\s*(" + parse.MONTHALT + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.IGNORECASE
)
_AUDITION = re.compile(r"(Barre\s*[-–].*?tours\))", re.IGNORECASE | re.DOTALL)


def _application(text: str) -> Application:
    requirements = []
    audition = _AUDITION.search(text)
    if re.search(r"Video\s+Audition", text, re.IGNORECASE):
        requirements.append(
            VideoReq(
                specificity="specific",
                description=parse.clean(audition.group(1)) if audition else None,
            )
        )
    deadline = None
    dm = _DEADLINE.search(text)
    if dm:
        month, day, year = dm.groups()
        deadline = date(int(year), parse.MONTHS[month.lower()], int(day))
    return Application(url=URL, requirements=requirements, deadline=deadline)
