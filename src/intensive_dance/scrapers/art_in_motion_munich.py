"""Art in Motion Munich (AiMM) — "Ballett-Sommerkurs" ballet summer school, Munich.

API FIRST: none usable. The site is **Wix** (`generator: Wix.com`, no `/wp-json/`,
no usable `ld+json`), but server-rendered — the prose is in the static HTML. The
edition's facts are split across three small pages (home = dates + deadline,
`/information` = age bands + classes, `/fees` = costs), so we fetch all three and
combine.

DISCOVERY: one `Offering` — the dated summer school edition (3-15 August 2026),
with one `Session` per age band (10-12 / 12-15 / over-15), each carrying the band's
girls/boys class list as notes.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-11):
  - DATES: numeric German "03.08.2026 till 15.08.2026" range + a "15.07.26"
    two-digit-year application deadline.
  - GENRES: matched against the classes list — classical, points→pointe,
    repertoire. "modern dance" and "(mens) technic" have no genre-enum value and
    don't leak.
  - AGES: three bands ("10 -12 years", "12-15 years", "over 15 years") → one
    open-topped Offering range {min: 10} plus a Session per band.
  - PRICES: several EUR prices (1 week / 2 weeks tuition; an optional personal
    coaching extra), with Wix's intra-number space ("13 90 €") normalised by
    `parse.parse_amount`.
  - REQUIREMENTS/LEVEL: not stated (an application form, no audition) → left empty.
"""

from __future__ import annotations

import html as ihtml
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
    now_utc,
)

SLUG = "art-in-motion-munich"
BASE = "https://www.artinmotionmunich.com"
HOME = f"{BASE}/"
INFO = f"{BASE}/information"
FEES = f"{BASE}/fees"

ORG = Organization(name="Art in Motion Munich", slug=SLUG, country="DE", city="Munich")
LOCATION = Location(city="Munich", country="DE")

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿­"), None)

_RANGE = re.compile(
    r"(\d{1,2})\.\s*(\d{1,2})\.(\d{4})\s*till\s*(\d{1,2})\.\s*(\d{1,2})\.(\d{4})", re.IGNORECASE
)
_DEADLINE = re.compile(
    r"deadline for applications is\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{2,4})", re.I
)

# An age band header, e.g. "for children 10 -12 years" / "for children over 15 years".
_BAND = re.compile(
    r"for children\s+(?:over\s+(\d{1,2})|(\d{1,2})\s*-\s*(\d{1,2}))\s*years",
    re.IGNORECASE,
)

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical",)),
    ("pointe", ("points", "pointe")),
    ("repertoire", ("repertoire",)),
]


def scrape(client: httpx.Client) -> list[Offering]:
    texts = []
    for url in (HOME, INFO, FEES):
        resp = client.get(url)
        resp.raise_for_status()
        texts.append(_text(resp.text))
    offering = _build_offering(*texts)
    return [offering] if offering is not None else []


def _build_offering(home: str, info: str, fees: str) -> Offering | None:
    span = _RANGE.search(home)
    if span is None:
        return None
    d1, m1, y1, d2, m2, y2 = (int(g) for g in span.groups())
    start = date(y1, m1, d1)
    end = date(y2, m2, d2)
    season = str(end.year)

    genres: list[Genre] = parse.match_genres(info, _GENRE_KEYWORDS, default=["classical"])
    sessions = _sessions(info)
    age_min = min((s.age_range["min"] for s in sessions if s.age_range), default=None)

    return Offering(
        id=f"{SLUG}/summer-school-{season}",
        source=Source(provider=SLUG, url=HOME, scrapedAt=now_utc()),
        title=f"Ballet Summer School {season}",
        genres=genres,
        ageRange={"min": age_min, "max": None} if age_min is not None else None,
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Berlin",
            sessions=sessions,
            notes="Three classes a day (ages 10-12) / four classes a day (ages 12+).",
        ),
        prices=_prices(fees),
        application=Application(url=INFO, deadline=_deadline(home)),
    )


def _text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    body = tree.body.text(separator=" ") if tree.body else ""
    return parse.clean(ihtml.unescape(body).translate(_ZERO_WIDTH))


def _deadline(home: str) -> date | None:
    m = _DEADLINE.search(home)
    if m is None:
        return None
    year = int(m.group(3))
    return date(2000 + year if year < 100 else year, int(m.group(2)), int(m.group(1)))


def _sessions(info: str) -> list[Session]:
    sessions: list[Session] = []
    matches = list(_BAND.finditer(info))
    for index, m in enumerate(matches):
        over, lo, hi = m.groups()
        if over is not None:
            age_range = {"min": int(over), "max": None}
            label = f"Ages {over}+"
        else:
            age_range = {"min": int(lo), "max": int(hi)}
            label = f"Ages {lo}-{hi}"
        nxt = matches[index + 1].start() if index + 1 < len(matches) else len(info)
        notes = re.sub(r"^old\s*", "", parse.clean(info[m.end() : nxt]))
        # Drop a trailing "N classes a day" that belongs to the next band's header.
        notes = re.sub(r"\s*\d+\s+classes a day\s*$", "", notes)
        notes = re.sub(r"\s*©.*$", "", notes).strip()
        sessions.append(Session(label=label, ageRange=age_range, notes=notes or None))
    return sessions


def _prices(fees: str) -> list[Price]:
    prices: list[Price] = []
    for weeks, label in ((r"1\s*week", "1 week"), (r"2\s*weeks", "2 weeks")):
        m = re.search(weeks + r"\s+([\d ]+?)\s*€", fees)
        if m and (amount := parse.parse_amount(m.group(1))) is not None:
            prices.append(Price(amount=amount, currency="EUR", label=label, includes=["tuition"]))
    m = re.search(r"(\d{1,2})\s*minutes?\s*:\s*(\d+)\s*€", fees)
    if m:
        prices.append(
            Price(
                amount=float(m.group(2)),
                currency="EUR",
                label=f"Personal coaching ({m.group(1)} minutes)",
                notes="optional extra",
            )
        )
    return prices
