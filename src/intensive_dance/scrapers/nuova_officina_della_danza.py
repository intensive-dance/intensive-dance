"""Nuova Officina della Danza (NOD) — Turin, IT — its summer intensive.

API FIRST: none. The site runs on **Wix** (server-rendered HTML, no `/wp-json/`,
no `ld+json`), so we parse the static markup with `selectolax`, stripping Wix's
zero-width spaces. Like the other Wix providers the host can block the proxy's
plain/auto egress, so every request forces `render=1` via `PROXY_PARAMS_HEADER`
(inert on a direct dev fetch).

DISCOVERY: one current edition. The NOD Summer Intensive Program runs as three
consecutive one-week blocks (a single multi-week intensive); attending one week
or a single workshop is a fee tier, not a separate Offering (same program/venue,
like Prague Ballet Workshop). We emit **one Offering** with a `Session` per week
(each week has its own dates and guest artists), season-keyed from the year.

It's a **contemporary** intensive that also teaches **ballet** (three ballet
classes per week, explicitly part of the program) → both genres.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-16):
  - DATES: per-week headers "WEEK 1 | JUNE 29 > JULY 3" → overall span (earliest
    start … latest end) + one Session per week; year from the page ("June 15, 2026").
  - SESSIONS: three weeks, each with its guest-artist roster in the notes.
  - TEACHERS: the eight guest artists from the "Full Week | …" rosters.
  - LEVEL: "dancers with strong contemporary technique … toward a professional
    career" → pre-professional.
  - PRICES in EUR: full 3-week early-bird (€1,900 / €2,040 incl. Emilie Leriche)
    and regular (€2,300); the one-week/single-workshop tiers are kept as a note.
  - REQUIREMENTS: the application form takes a CV and two video links (Vimeo/
    YouTube); selection may include a Zoom interview → CVReq + VideoReq(unspecific).
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.fetch import PROXY_PARAMS_HEADER
from intensive_dance.models import (
    Application,
    CVReq,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    Price,
    Requirement,
    Schedule,
    Session,
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

BASE = "https://www.nuovaofficinadelladanza.org"
PROGRAM = f"{BASE}/nodsummerintensiveprogram26"

# Wix can block the proxy's plain/auto egress; force the render tier (inert direct).
_RENDER = {PROXY_PARAMS_HEADER: "render=1&wait=8000"}

ORG = Organization(
    name="Nuova Officina della Danza",
    slug="nuova-officina-della-danza",
    country="IT",
    city="Turin",
)

_YEAR_RE = re.compile(r"\b(20\d{2})\b")
# "WEEK 1 | JUNE 29 > JULY 3"
_WEEK_RE = re.compile(
    rf"WEEK\s*(\d)\s*\|\s*({parse.MONTHALT})\s+(\d{{1,2}})\s*>\s*({parse.MONTHALT})\s+(\d{{1,2}})",
    re.I,
)
_FULLWEEK_RE = re.compile(r"Full\s*[Ww]eek\s*\|\s*(.+)")
_EARLY7_RE = re.compile(r"€\s*([\d.,]+)\s*[—-]\s*Fee for 7 artists", re.I)
_EARLY8_RE = re.compile(r"€\s*([\d.,]+)\s*[—-]\s*Fee for 8 artists", re.I)
_REGULAR_RE = re.compile(r"Regular fee:\s*€\s*([\d.,]+)", re.I)

_GENRES: list[tuple[Genre, list[str]]] = [
    ("contemporary", ["contemporary"]),
    ("classical", ["ballet class"]),
]


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PROGRAM, headers=_RENDER)
    return _build_offerings(_page_text(resp.text))


def _page_text(html: str) -> str:
    tree = HTMLParser(html)
    for junk in tree.css("script, style, noscript"):
        junk.decompose()
    body = tree.body
    text = body.text(separator="\n") if body else ""
    text = text.replace("​", "")  # Wix zero-width spaces
    lines = [parse.clean(line) for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _weeks(text: str) -> list[tuple[Session, list[str]]]:
    """Each WEEK header paired with the guest artists from its 'Full Week' line."""
    year_match = _YEAR_RE.search(text)
    if not year_match:
        return []
    year = int(year_match.group(1))
    lines = text.split("\n")
    out: list[tuple[Session, list[str]]] = []
    pending: re.Match[str] | None = None
    for line in lines:
        if header := _WEEK_RE.search(line):
            pending = header
            continue
        if pending and (full := _FULLWEEK_RE.search(line)):
            names = [parse.clean(n) for n in full.group(1).split(",")]
            names = [n for n in names if n]
            start = date(year, parse.MONTHS[pending.group(2).lower()], int(pending.group(3)))
            end = date(year, parse.MONTHS[pending.group(4).lower()], int(pending.group(5)))
            session = Session(label=f"Week {pending.group(1)}", start=start, end=end)
            out.append((session, names))
            pending = None
    return out


def _prices(text: str) -> list[Price]:
    out: list[Price] = []
    tiers = [
        (_EARLY7_RE, "Full 3-week program — early bird (by Dec 31), 7 artists"),
        (
            _EARLY8_RE,
            "Full 3-week program — early bird (by Dec 31), 8 artists incl. Emilie Leriche",
        ),
        (_REGULAR_RE, "Full 3-week program — regular (registration fee included)"),
    ]
    note = (
        "One-week blocks (€680–840) and single workshops (€280–340) are also "
        "offered; ballet classes are included in full weeks, €40 extra otherwise."
    )
    for pattern, label in tiers:
        if (match := pattern.search(text)) and (amount := parse.parse_amount(match.group(1))):
            out.append(
                Price(amount=amount, currency="EUR", label=label, includes=["tuition"], notes=note)
            )
    return out


def _build_offerings(text: str) -> list[Offering]:
    weeks = _weeks(text)
    if not weeks:
        return []
    year = weeks[0][0].start.year if weeks[0][0].start else None
    if year is None:
        return []

    sessions = [session for session, _ in weeks]
    seen: set[str] = set()
    teachers: list[Teacher] = []
    for _, names in weeks:
        for name in names:
            if name not in seen:
                seen.add(name)
                teachers.append(Teacher(name=name, role="Guest artist"))

    starts = [s.start for s in sessions if s.start]
    ends = [s.end for s in sessions if s.end]

    requirements: list[Requirement] = []
    if "cv" in text.lower() or "curriculum" in text.lower():
        requirements.append(CVReq())
    if re.search(r"vimeo|youtube|video", text, re.I):
        requirements.append(
            VideoReq(specificity="unspecific", description="Two video links (Vimeo/YouTube).")
        )

    offering = Offering(
        id=f"nuova-officina-della-danza/{year}",
        source=Source(provider="nuova-officina-della-danza", url=PROGRAM, scrapedAt=now_utc()),
        title=f"NOD Summer Intensive Program {year}",
        genres=parse.match_genres(text, _GENRES),
        level=_levels(text),
        organization=ORG,
        location=Location(city="Turin", country="IT"),
        schedule=Schedule(
            season="summer",
            start=min(starts) if starts else None,
            end=max(ends) if ends else None,
            sessions=sessions,
        ),
        teachers=teachers,
        prices=_prices(text),
        application=Application(
            url=PROGRAM,
            requirements=requirements,
            notes=(
                "Apply via the online form (CV + two video links); selection may "
                "include a Zoom interview with the artistic director. A €500 deposit "
                "reserves a place after confirmation."
            ),
        ),
    )
    return [offering]


def _levels(text: str) -> list[Level]:
    return ["pre-professional"] if "professional" in text.lower() else []
