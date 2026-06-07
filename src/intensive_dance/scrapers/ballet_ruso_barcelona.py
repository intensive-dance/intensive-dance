"""Ballet Ruso Barcelona (Spain) — its Summer Intensive (Programa de Verano).

API FIRST: none. The site is built on **Tilda**, which server-renders every
block, so the full Summer Program page text is in the static HTML — a one-page
scrape, no JS, no JSON API.

TLS NOTE: the host serves a self-signed / incomplete certificate chain (a common
Tilda-on-custom-domain misconfiguration), so the shared client can't validate
it. We fetch with our own `verify=False` client (read-only public page — see
`fetch.make_client`), the same call the Princess Grace and Frankfurt scrapers make.

LANGUAGE: the marketing copy on this page is English, but the structured fields
(dates, schedule) use Spanish numeric conventions — week ranges are `DD.MM - DD.MM`
with the year only in the page header ("June 29 - July 24, 2026" / "Summer
Intensive 2026"). We parse those numerics language-agnostically and lift the year
from the header; the genre/requirement keywords are matched against the page's
own curriculum lists, not loose prose.

DISCOVERY: the one page describes **two parallel programs** — the
`Pre-professional Program` (from age 10) and a `Young Artist Camp` (from age 3,
mixing in singing / drama / musical theatre). We emit **only the Pre-professional
Program**: the camp is recreational early-years and outside the register's
ambitious / pre-professional scope, so we deliberately skip it (its `_CAMP_HEAD`
header is still used as the slice boundary, just not emitted).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-07):
  - One in-scope program sliced out of a two-program page (early-years camp skipped).
  - `schedule.sessions` from `DD.MM - DD.MM` week ranges, year from the header.
  - `age_range` with an open upper bound ("from N years old" → max null).
  - Several `Price` tiers (one per week-count), tuition-only.
  - Genre matching from the program's own curriculum list (incl. Pointe).
  - Requirements: the pre-professional doubles as an audition accepting an
    **in-person or online** submission → `VideoReq`/`unspecific`.
  - Named artistic directors (Mariinsky / Vaganova lineage) as `Teacher`s.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.fetch import make_client
from intensive_dance.models import (
    Affiliation,
    Application,
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

BASE = "https://balletrusobarcelona.com"
PAGE = f"{BASE}/summerprogram"
APPLY_URL = "https://balletrusobarcelona.playoffinformatica.com/actividad/60/Audition-Ballet-Ruso-Barcelona-2026/"

ORG = Organization(
    name="Ballet Ruso Barcelona",
    slug="ballet-ruso-barcelona",
    country="ES",
    city="Barcelona",
)
LOCATION = Location(venue="Josep Tarradellas 42", city="Barcelona", country="ES")

# `_PREPRO_HEAD` opens the pre-professional program's data block; `_CAMP_HEAD`
# (the header of the skipped Young Artist Camp) is the end marker, so the
# pre-professional slice (ages/dates/fees/curriculum) is read in isolation —
# that scoping keeps the camp's "modern dance" out of the pre-professional's Pointe.
_PREPRO_HEAD = "PRE-PROFESSIONAL program Age"
_CAMP_HEAD = "YOUNG ARTIST camp Age"


def scrape(client: httpx.Client) -> list[Offering]:  # noqa: ARG001 — see TLS NOTE
    # The shared client can't validate the self-signed/incomplete chain; use our own.
    own = make_client(verify=False)
    try:
        resp = own.get(PAGE)
        resp.raise_for_status()
        html = resp.text
    finally:
        own.close()
    return _build_offerings(html, date.today())


def _build_offerings(html: str, today: date) -> list[Offering]:  # noqa: ARG001
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    year = _year(text)
    if year is None:
        return []  # no announced edition year → nothing dated to emit

    offerings: list[Offering] = []

    prepro = _slice(text, _PREPRO_HEAD, _CAMP_HEAD)
    if prepro:
        offerings.append(
            _offering(
                slug=f"summer-intensive-{year}-pre-professional",
                title=f"Summer Intensive {year} — Pre-professional Program",
                block=prepro,
                year=year,
                curriculum=_slice(text, "Ballet Technique Pointe", "Young Artist Camp"),
                requirements=_audition_requirements(text),
                level=["pre-professional"],
            )
        )

    # The Young Artist Camp (from age 3, with singing/drama/musical theatre) is
    # recreational early-years — out of the register's pre-professional scope, so
    # we deliberately do not emit it.

    return offerings


def _offering(
    *,
    slug: str,
    title: str,
    block: str,
    year: int,
    curriculum: str,
    requirements: list[Requirement],
    level: list[Level],
) -> Offering:
    sessions = _sessions(block, year)
    start = min((s.start for s in sessions if s.start), default=None)
    end = max((s.end for s in sessions if s.end), default=None)
    return Offering(
        id=f"ballet-ruso-barcelona/{slug}",
        source=Source(provider="ballet-ruso-barcelona", url=PAGE, scrapedAt=now_utc()),
        title=title,
        genres=_genres(curriculum),
        level=level,
        ageRange=_age_range(block),
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(
            season=str(year),
            start=start,
            end=end,
            timezone="Europe/Madrid",
            sessions=sessions,
        ),
        teachers=_directors(),
        prices=_prices(block),
        application=Application(url=APPLY_URL, requirements=requirements),
    )


def _slice(text: str, start_marker: str, end_marker: str) -> str:
    i = text.find(start_marker)
    if i == -1:
        return ""
    j = text.find(end_marker, i + len(start_marker))
    return text[i : j if j != -1 else len(text)]


# --- year: lifted from the header ("Summer Intensive 2026") --------------------

_YEAR = re.compile(r"Summer Intensive\s+(20\d{2})")


def _year(text: str) -> int | None:
    m = _YEAR.search(text)
    return int(m.group(1)) if m else None


# --- weeks: "Week #N: DD.MM - DD.MM" (year from the header) --------------------

_WEEK = re.compile(r"Week\s*#(\d+):\s*(\d{1,2})\.(\d{1,2})\s*-\s*(\d{1,2})\.(\d{1,2})")


def _sessions(block: str, year: int) -> list[Session]:
    sessions: list[Session] = []
    for m in _WEEK.finditer(block):
        num, d1, mo1, d2, mo2 = (int(g) for g in m.groups())
        sessions.append(
            Session(
                label=f"Week #{num}",
                start=date(year, mo1, d1),
                end=date(year, mo2, d2),
            )
        )
    return sessions


# --- age: "from N years old" (open upper bound) -------------------------------

_AGE = re.compile(r"from\s+(\d{1,2})\s+years\s+old", re.IGNORECASE)


def _age_range(block: str) -> dict | None:
    res = parse.extract_age_range(block, _AGE)
    if res:
        res["max"] = None
    return res


# --- prices: "N week(s): NNN€" tuition tiers ----------------------------------

_PRICE = re.compile(r"(\d+)\s*weeks?:\s*(\d[\d.,]*)\s*€")


def _prices(block: str) -> list[Price]:
    prices: list[Price] = []
    for m in _PRICE.finditer(block):
        weeks = int(m.group(1))
        amount = parse.parse_amount(m.group(2))
        if amount is None:
            continue
        label = "1 week" if weeks == 1 else f"{weeks} weeks"
        prices.append(Price(amount=amount, currency="EUR", label=label, includes=["tuition"]))
    return prices


# --- genres: matched against each program's own curriculum --------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet technique", "classical")),
    ("pointe", ("pointe",)),
    ("contemporary", ("contemporary", "modern dance")),
    ("character", ("character dance",)),
    ("repertoire", ("variations", "repertoire")),
]


def _genres(curriculum: str) -> list[Genre]:
    return parse.match_genres(curriculum, _GENRE_KEYWORDS, default=["classical"])


# --- requirements: the pre-professional program is an audition ----------------


def _audition_requirements(text: str) -> list[Requirement]:
    """The pre-professional program admits via a live **or** online audition.

    An audition that accepts an in-person or video submission maps to a
    `VideoReq`/`unspecific` (per the data-model note), capturing the dual path
    and the two stated fees without inventing a fixed brief.
    """
    low = text.lower()
    if "on-line audition" not in low and "live-audition" not in low:
        return []
    notes = (
        "Admission audition for the pre-professional program, in person (€30) or "
        "online (€15); results within two weeks."
    )
    return [VideoReq(specificity="unspecific", description=notes)]


# --- teachers: the named artistic directors -----------------------------------


def _directors() -> list[Teacher]:
    """The two BRB artistic directors named as supervising the summer program."""
    return [
        Teacher(
            name="Boris Shepelev",
            role="Artistic Director",
            affiliations=[
                Affiliation(organization="Mariinsky Theatre", role="Soloist", current=False),
                Affiliation(organization="Mikhailovsky Theatre", role="Principal", current=False),
            ],
        ),
        Teacher(
            name="Blanca Hartmann",
            role="Artistic Director",
            affiliations=[
                Affiliation(
                    organization="Vaganova Ballet Academy",
                    role="Vaganova-method graduate",
                    current=False,
                ),
            ],
        ),
    ]


__all__ = ["scrape"]
