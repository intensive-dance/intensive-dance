"""Académie de Danse Princesse Grace (Monaco) — its summer short courses.

API FIRST: none. The Ballets de Monte-Carlo site runs on **Drupal** and
server-renders the Princess Grace Academy "Admission & Short courses" page, so
the full text is in the static HTML — a one-page scrape, no JS.

TLS NOTE: the host serves an incomplete certificate chain, so the shared client
can't validate it; we fetch with our own `verify=False` client (read-only
public page — see `fetch.make_client`), the same call the Frankfurt scraper makes.

DISCOVERY: one page lists the summer course as four consecutive one-week
sessions (e.g. 6–11 July, 13–18 July, …). They share one curriculum, age band
and price and you may "follow one or more weeks", so we emit a single
`Offering` for the summer course with the four weeks as `schedule.sessions`,
season-keyed from the parsed year.

WHAT THE PAGE GIVES US (verified live 2026-06):
  - DATES: four "From <weekday> <Month>, <d> to <weekday> <Month>, <d> <year>"
    week ranges (the year only on the closing date).
  - AGES: "between 11 and 19 years old".
  - PRICES in EUR: 1200/week (tuition + accommodation) and 700/week (tuition
    only — accommodation not included).
  - REQUIREMENTS — the richest set in the register, and the first with *named
    poses*: the short course doubles as an audition, so it asks for a CV, an ID
    photo (headshot), two dance photos in defined poses (arabesque + développé
    seconde), and a classical + contemporary video (≤15 min). This is exactly
    the granular requirement data IDR-28 wants for a shoot plan.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.fetch import make_client
from intensive_dance.models import (
    Application,
    CVReq,
    Genre,
    HeadshotReq,
    Level,
    Location,
    Offering,
    Organization,
    PhotosReq,
    Price,
    PriceInclude,
    Requirement,
    Schedule,
    Session,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://www.balletsdemontecarlo.com"
PAGE = f"{BASE}/en/princess-grace-academy/admission-short-courses"
APPLY_URL = "https://academy.balletsdemontecarlo.com/en"

ORG = Organization(
    name="Académie de Danse Princesse Grace",
    slug="academie-princesse-grace",
    country="MC",
    city="Monaco",
)


def scrape(client: httpx.Client) -> list[Offering]:  # noqa: ARG001 — see TLS NOTE
    # The shared client can't validate the incomplete cert chain; use our own.
    own = make_client(verify=False)
    try:
        resp = own.get(PAGE)
        resp.raise_for_status()
        html = resp.text
    finally:
        own.close()
    offering = _build_offering(html)
    return [offering] if offering is not None else []


def _build_offering(html: str) -> Offering | None:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    sessions = _sessions(text)
    if not sessions:
        return None  # no dated summer weeks announced
    start = min(s.start for s in sessions if s.start)
    end = max(s.end for s in sessions if s.end)
    season = str(end.year)

    return Offering(
        id=f"academie-princesse-grace/summer-courses-{season}",
        source=Source(provider="academie-princesse-grace", url=PAGE, scrapedAt=now_utc()),
        title=f"Summer Courses {season}",
        genres=_genres(text),
        level=_level(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(city="Monaco", country="MC"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Monaco",
            sessions=sessions,
        ),
        prices=_prices(text),
        application=Application(
            url=APPLY_URL,
            requirements=_requirements(text),
            notes=_audition_note(text),
        ),
    )


# --- dates: four "From <wd> <Month>, <d> to <wd> <Month>, <d> <year>" weeks ----

_WEEK = re.compile(
    r"From\s+\w+\s+(" + parse.MONTHALT + r"),?\s+(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"to\s+\w+\s+(" + parse.MONTHALT + r"),?\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})",
    re.IGNORECASE,
)


def _sessions(text: str) -> list[Session]:
    sessions = []
    for i, m in enumerate(_WEEK.finditer(text), start=1):
        m1, d1, m2, d2, year = m.groups()
        start = date(int(year), parse.MONTHS[m1.lower()], int(d1))
        end = date(int(year), parse.MONTHS[m2.lower()], int(d2))
        sessions.append(Session(label=f"Week {i}", start=start, end=end))
    return sessions


_AGE = re.compile(r"between\s+(\d{1,2})\s+and\s+(\d{1,2})\s+years", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    return parse.extract_age_range(text, _AGE)


def _level(text: str) -> list[Level]:
    low = text.lower()
    return (
        ["pre-professional"]
        if re.search(r"\b(selected|selection)\b", low) and "audition" in low
        else []
    )


# --- prices: "1200€/week (tuition + accommodation)", "700€/week (…)" -----------

_PRICE = re.compile(r"(\d[\d.,]*)\s*€\s*/\s*week\s*\(([^)]*)\)", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    for m in _PRICE.finditer(text):
        amount = parse.parse_amount(m.group(1))
        if amount is None:
            continue
        label = parse.clean(m.group(2))
        notes = None
        if re.search(r"optional meals available", label, re.IGNORECASE):
            notes = "Optional meals available."
            label = parse.clean(
                re.sub(r";?\s*optional meals available", "", label, flags=re.IGNORECASE)
            )
        includes: list[PriceInclude] = ["tuition"]
        if re.search(r"\+\s*accommodation|accommodation\s+included", label, re.IGNORECASE):
            includes.append("accommodation")
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=f"Per week ({label})",
                includes=includes,
                notes=notes,
            )
        )
    return prices


# --- genres -------------------------------------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "men's class", "ballet")),
    ("contemporary", ("contemporary",)),
    ("pointe", ("pointe",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- requirements: the short course doubles as an audition --------------------

# "2 dance outfit photos (poses arabesque and développé seconde)".
_POSES = re.compile(r"dance outfit photos?\s*\(poses?\s+([^)]+)\)", re.IGNORECASE)
_VIDEO_MINUTES = re.compile(r"duration must not exceed:?\s*(\d+)\s*minutes", re.IGNORECASE)


def _requirements(text: str) -> list[Requirement]:
    low = text.lower()
    reqs: list[Requirement] = []
    if re.search(r"\bcv\b|resume", low):
        reqs.append(CVReq())
    if "id photo" in low:
        reqs.append(HeadshotReq())
    poses_match = _POSES.search(text)
    if poses_match:
        poses = [
            parse.clean(p) for p in re.split(r"\s+and\s+|,\s*", poses_match.group(1)) if p.strip()
        ]
        reqs.append(
            PhotosReq(
                specificity="defined-poses",
                poses=poses,
                notes="Two dance-outfit photos in the named poses, plus the ID photo.",
            )
        )
    video = _video_req(low)
    if video is not None:
        reqs.append(video)
    return reqs


def _video_req(low: str) -> VideoReq | None:
    """A concise, faithful summary of the classical + contemporary video brief.

    The page enumerates exact barre/centre exercises; we keep the structure
    (which extracts, the duration cap) rather than dumping the full list — the
    business-critical granularity (the photo poses) is captured precisely above.
    """
    parts = []
    if "classical extract" in low:
        parts.append("a classical extract (barre + centre exercises, adapted to level)")
    if "contemporary extract" in low:
        parts.append("a contemporary extract")
    if not parts:
        return None
    description = "Video audition: " + " and ".join(parts)
    minutes = _VIDEO_MINUTES.search(low)
    if minutes:
        description += f"; total video ≤ {minutes.group(1)} minutes"
    return VideoReq(specificity="specific", description=description + ".")


_AUDITION = re.compile(r"(Possible audition for season[^.]*\.?)", re.IGNORECASE)


def _audition_note(text: str) -> str | None:
    m = _AUDITION.search(text)
    return parse.clean(m.group(1)) if m else None
