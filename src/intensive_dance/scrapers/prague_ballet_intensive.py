"""Prague Ballet Intensive (PBI) — Prague, CZ — its summer coaching program.

API FIRST: **WordPress**. The site is plain WordPress (theme "simple"), not the
Wix/JS the issue guessed — `GET /wp-json/` returns 200 and the page bodies are
exposed as clean HTML in `wp/v2/pages` `content.rendered`, so we read the body
text straight from the REST API (no WPBakery shortcodes, no JS render, no proxy:
the host serves a valid cert from a normal IP and the content is all server-side).

The one thing not in a page body is the **dated edition title** — the home
page's content block is theme-rendered and empty, but the dates live in the WP
site description (the `<title>` tag: "… Summer 2026, August 10th – 22nd"), so we
fetch the home HTML once for that and pull the rest from the API.

DISCOVERY: one current edition. PBI runs a single 12-working-day summer
intensive (about-us, apply, tuition all describe the one course); we emit **one
Offering**, season-keyed from the parsed year so the id rolls forward when the
site advances. The course can be attended for the full two weeks or a single
week — that's a fee tier and an application note, not a second Offering (same
dates/ages/curriculum).

WHAT THE PAGES GIVE US (verified live 2026-06-06):
  - DATES: "Summer 2026, August 10th – 22nd" — one month, the year stated before
    it (so a bespoke single-month regex, not the shared multi-month helper).
  - AGES: "between 15 – 35 years of age" (apply + about-us).
  - LEVEL: "pre-professional and professional" (about-us) → both levels.
  - GENRES from the about-us/schedule curriculum: ballet class, variations
    (repertoire), pas de deux, contemporary (yoga each evening is conditioning,
    out of scope as a genre).
  - PRICES in EUR (CZK alternatives noted): 1660 full course tuition, 860 one
    week; a 200 EUR non-refundable deposit is a `Price` note. Accommodation is a
    third-party hostel discount (not PBI tuition), kept only as an application note.
  - REQUIREMENTS: the course doubles as an audition — a short CV, a headshot, a
    current photo in first arabesque (a defined pose) and one ballet photo of the
    applicant's choice (freeform). The arabesque is the granular pose IDR-28 wants.

Teachers: the site names only pianists (Khidirova, Smoliarov) and org-level
directors — no named ballet teaching faculty is pinned to the 2026 edition, so
teachers are left empty rather than over-claimed (same call as Brussels/Joffrey).
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
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
    Requirement,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.pragueballetintensive.com"
HOME = f"{BASE}/"
APPLY_URL = f"{BASE}/apply/"
# Page bodies are clean HTML in the WP REST API; ids are stable (resolved live).
_PAGE_IDS = {"about": 13, "apply": 23, "tuition": 30, "location": 43}

ORG = Organization(
    name="Prague Ballet Intensive",
    slug="prague-ballet-intensive",
    country="CZ",
    city="Prague",
)

_APPLY_NOTE = (
    "Apply via the form on the PBI website; the course doubles as the audition. "
    "A 200 EUR non-refundable deposit is due after acceptance and is deducted "
    "from the invoice. To attend a single week, state which week in the "
    "application. Places are limited."
)
_ACCOMMODATION_NOTE = (
    "Accommodation is not included: PBI participants get a discounted rate at the "
    "nearby KDM hostel (~1 minute walk; ~36 EUR/night single, ~26 EUR/bed/night "
    "double, plus ~2 EUR/night city tax), booked directly with the hostel."
)


def scrape(client: httpx.Client) -> list[Offering]:
    home = client.get(HOME)
    home.raise_for_status()
    pages = {}
    for key, page_id in _PAGE_IDS.items():
        resp = client.get(f"{BASE}/wp-json/wp/v2/pages/{page_id}?_fields=content")
        resp.raise_for_status()
        pages[key] = _page_text(resp.json())
    offering = _build_offering(home.text, pages)
    return [offering] if offering is not None else []


def _page_text(payload: dict) -> str:
    """Visible text of a WP page body (`content.rendered` HTML → clean string)."""
    html = (payload.get("content") or {}).get("rendered", "")
    tree = HTMLParser(html)
    return parse.clean(tree.text(separator=" ")) if html else ""


def _title_text(home_html: str) -> str:
    """The `<title>` text, which carries the dated edition string."""
    tree = HTMLParser(home_html)
    node = tree.css_first("title")
    return parse.clean(node.text()) if node else ""


def _build_offering(home_html: str, pages: dict[str, str]) -> Offering | None:
    title = _title_text(home_html)
    start, end = _date_range(title)
    if start is None or end is None:
        return None  # no dated edition parseable
    season = str(start.year)

    facts = " ".join([title, pages.get("about", ""), pages.get("apply", "")])

    return Offering(
        id=f"prague-ballet-intensive/summer-intensive-{season}",
        source=Source(provider="prague-ballet-intensive", url=HOME, scrapedAt=now_utc()),
        title=f"Summer Intensive {season}",
        genres=_genres(pages.get("about", "")),
        level=_levels(pages.get("about", "")),
        ageRange=_age_range(facts),
        organization=ORG,
        location=_location(pages.get("location", "")),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Prague",
        ),
        prices=_prices(pages.get("tuition", "")),
        application=Application(
            url=APPLY_URL,
            requirements=_requirements(pages.get("apply", "")),
            notes=f"{_APPLY_NOTE} {_ACCOMMODATION_NOTE}",
        ),
    )


# --- dates: "Summer 2026, August 10th – 22nd" (one month, year before it) ------

# Year then a single month with a day–day span (ordinal suffixes optional, any
# dash). Language-agnostic on the month via the shared English month alternation.
_RANGE = re.compile(
    r"(\d{4})\s*,?\s*("
    + parse.MONTHALT
    + r")\s+(\d{1,2})(?:st|nd|rd|th)?\s*[-–—]\s*(\d{1,2})(?:st|nd|rd|th)?",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    year, month, d1, d2 = m.groups()
    month_num = parse.MONTHS[month.lower()]
    return (
        date(int(year), month_num, int(d1)),
        date(int(year), month_num, int(d2)),
    )


# --- ages: "between 15 – 35 years" / "aged 15 – 35 years" ----------------------

_AGE = re.compile(r"(?:between|aged)\s+(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*years", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    return parse.extract_age_range(text, _AGE)


# --- level ---------------------------------------------------------------------


def _levels(text: str) -> list[Level]:
    low = text.lower()
    levels: list[Level] = []
    if "pre-professional" in low or "pre professional" in low:
        levels.append("pre-professional")
    if re.search(r"(?<!pre-)(?<!pre )professional", low):
        levels.append("professional")
    return levels


# --- genres: matched against the curriculum description, not loose prose -------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet class", "classical", "pas de deux")),
    ("repertoire", ("variations", "repertoire")),
    ("contemporary", ("contemporary",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- prices: "tuition will amount 1 660 euros …", "One week … 860 euros …" ------

_FULL = re.compile(r"course\s+tuition\s+will\s+amount\s+([\d  .,]+?)\s*euros", re.IGNORECASE)
_WEEK = re.compile(r"one\s+week\s+tuition\s+will\s+amount\s+([\d  .,]+?)\s*euros", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    full = _FULL.search(text)
    if full:
        amount = parse.parse_amount(full.group(1).replace(" ", ""))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="Full course tuition (two weeks)",
                    includes=["tuition"],
                    notes="Payable in two installments; the second is due by July 31st.",
                )
            )
    week = _WEEK.search(text)
    if week:
        amount = parse.parse_amount(week.group(1).replace(" ", ""))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="One week tuition",
                    includes=["tuition"],
                )
            )
    return prices


# --- requirements: the course doubles as an audition --------------------------


def _requirements(text: str) -> list[Requirement]:
    low = text.lower()
    reqs: list[Requirement] = []
    if re.search(r"\bcv\b|resume", low):
        reqs.append(CVReq())
    if "headshot" in low:
        reqs.append(HeadshotReq())
    poses = _poses(low)
    if poses or "ballet photo" in low:
        notes = None
        if "of your choice" in low or "of your own choice" in low:
            notes = "Plus one ballet photo of the applicant's own choice (freeform)."
        reqs.append(
            PhotosReq(
                specificity="defined-poses" if poses else "freeform",
                poses=poses,
                notes=notes,
            )
        )
    return reqs


def _poses(low: str) -> list[str]:
    """Named photo poses the application asks for (currently 'first arabesque')."""
    poses: list[str] = []
    if "first arabesque" in low:
        poses.append("first arabesque")
    elif "arabesque" in low:
        poses.append("arabesque")
    return poses


# --- location ------------------------------------------------------------------


_VENUE = re.compile(r"held at\s+(?:[^.]*?\bat\s+)?(.+?)\s*\.", re.IGNORECASE)


def _location(text: str) -> Location:
    """Venue from "… will be held at <studio> at <venue>." — take the named venue
    (the trailing "at <X>"), not the studio room label that may precede it."""
    venue = None
    m = _VENUE.search(text)
    if m:
        venue = parse.clean(m.group(1))
    return Location(venue=venue, city="Prague", country="CZ")
