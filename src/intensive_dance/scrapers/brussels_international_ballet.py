"""Brussels International Ballet (BIB) — Brussels, BE — its Summer Intensive.

API FIRST: none usable. BIB runs on **Wix**, which has no public content API we
may use, but the Summer Intensive page is server-side rendered (note the
`ssr-caching` response header), so the full text is present in the static HTML —
a one-page scrape, no JS needed.

DISCOVERY: a single page (`/summer-intensive-2026`) describes the current
edition — one two-week Summer Intensive. We emit one `Offering`, season-keyed
from the parsed dates so the id rolls forward when the page advances a year.

WHAT THE PAGE GIVES US (verified live 2026-06):
  - DATES: the course runs "20 July – 01 August 2026"; the residential package
    brackets it (19 July – 02 August), kept as a schedule note.
  - AGES: open from 12 with groups "12–14" and "15–17+" — the upper "17+" is
    open-ended, so we record only the lower bound (per the model's null-bound
    convention).
  - STATUS: the page states "Registration is now closed." That closes the
    *application*, not the course — the edition is still upcoming, so `lifecycle`
    stays `scheduled` (the IDR-24 distinction: closed ≠ cancelled).
  - PRICES: the registration page (`/registration-sp26`) states a non-refundable
    €29 registration fee; it is emitted as a `Price` with `includes=[]` (fee only,
    not tuition).
  - REQUIREMENTS: `/registration-sp26` asks for a headshot and links guidelines.
    We emit `headshot`; photo requirements are `defined-poses` only when the text
    explicitly says positions, otherwise `freeform`.

Faculty are listed as a legacy roll of guest artists ("names such as …"), not a
confirmed 2026 roster, so teachers are left empty rather than over-claimed (the
same call the Joffrey and ENBS scrapers make for unattributable fields).
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
    Source,
    Price,
    HeadshotReq,
    PhotosReq,
    Requirement,
    now_utc,
)

BASE = "https://www.brusselsintballet.org"
PAGE = f"{BASE}/summer-intensive-2026"
REGISTRATION_PAGE = f"{BASE}/registration-sp26"

ORG = Organization(
    name="Brussels International Ballet",
    slug="brussels-international-ballet",
    country="BE",
    city="Brussels",
)

_APPLY_NOTE = (
    "Entry is by application via BIB's Online Application Form. Tuition excludes "
    "audition fees and optional extras; a 60% deposit is due within 14 days of "
    "acceptance to secure a place."
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    reg_resp = client.get(REGISTRATION_PAGE)
    reg_resp.raise_for_status()
    offering = _build_offering(resp.text, reg_resp.text)
    return [offering] if offering is not None else []


def _build_offering(html: str, reg_html: str = "") -> Offering | None:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    reg_tree = HTMLParser(reg_html)
    for node in reg_tree.css("script, style, noscript"):
        node.decompose()
    reg_text = parse.clean(reg_tree.body.text(separator=" ")) if reg_tree.body else ""

    start, end = _date_range(text)
    anchor = end or start
    if anchor is None:
        return None  # no dated edition parseable
    season = str(anchor.year)

    return Offering(
        id=f"brussels-international-ballet/summer-intensive-{season}",
        source=Source(provider="brussels-international-ballet", url=PAGE, scrapedAt=now_utc()),
        title=f"Summer Intensive {season}",
        genres=_genres(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(city="Brussels", country="BE"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Brussels",
            notes=_schedule_note(text),
        ),
        prices=_prices(reg_text),
        application=Application(
            status=_status(text),
            url=PAGE,
            requirements=_requirements(reg_text),
            notes=_APPLY_NOTE,
        ),
    )


_APP_FEE = re.compile(r"(?:registration|audition)\s+fee\D{0,15}€\s*(\d+)", re.IGNORECASE)


def _prices(reg_text: str) -> list[Price]:
    prices: list[Price] = []
    m = _APP_FEE.search(reg_text)
    if m and (amount := parse.parse_amount(m.group(1))) is not None:
        prices.append(Price(amount=amount, currency="EUR", label="Registration fee", includes=[]))
    return prices


def _requirements(reg_text: str) -> list[Requirement]:
    reqs: list[Requirement] = []
    low = reg_text.lower()
    if "headshot" in low:
        reqs.append(HeadshotReq())
    if "guidelines for the positions" in low:
        reqs.append(
            PhotosReq(
                specificity="defined-poses",
                notes="Attire and positions must follow the guidelines PDF.",
            )
        )
    elif "attire follows these guidelines" in low:
        reqs.append(
            PhotosReq(specificity="freeform", notes="Attire must follow the guidelines PDF.")
        )
    return reqs


# --- parsing ------------------------------------------------------------------

# "20 July – 01 August 2026" (a shared trailing year across both day-month pairs).
_RANGE = re.compile(
    r"(\d{1,2})\s+("
    + parse.MONTHALT
    + r")\s*[-–—]\s*(\d{1,2})\s+("
    + parse.MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)
# The residential window, kept as a note ("Sunday 19 July – Sunday 02 August");
# weekday words may prefix either bound, so they're allowed but not captured.
_RESIDENTIAL = re.compile(
    r"Residential[^.]*?Dates:\s*"
    r"((?:\w+\s+)?\d{1,2}\s+\w+\s*[-–—]\s*(?:\w+\s+)?\d{1,2}\s+\w+)",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    return parse.parse_multi_month_range(text, _RANGE)


def _schedule_note(text: str) -> str | None:
    match = _RESIDENTIAL.search(text)
    return f"Residential package: {parse.clean(match.group(1))}" if match else None


# "For ages 12 and over", groups "12–14" and "15–17+". The lower bound is the
# smallest stated age; the upper is open-ended ("and over" / "17+").
_AGE_LOW = re.compile(r"ages?\s*(\d{1,2})", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    lows = [int(n) for n in _AGE_LOW.findall(text) if 3 <= int(n) <= 25]
    if not lows:
        return None
    return {"min": min(lows)}  # null upper bound — "17+ / and over" is open-ended


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet technique", "male technique")),
    ("pointe", ("pointe",)),
    ("repertoire", ("repertoire", "variations")),
    ("contemporary", ("contemporary",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _status(text: str):
    low = text.lower()
    if re.search(r"registration\s+is\s+(now\s+)?closed|registrations?\s+closed", low):
        return "closed"
    if re.search(r"registration\s+is\s+(now\s+)?open|register\s+now", low):
        return "open"
    return None
