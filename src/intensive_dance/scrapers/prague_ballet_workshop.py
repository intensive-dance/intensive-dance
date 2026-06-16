"""Prague Ballet Workshop — Prague, CZ — its classical summer workshop.

API FIRST: none. The site runs on **Wix** (server-rendered HTML, no `/wp-json/`,
no `ld+json` events) — content is in the static markup, so we parse it with
`selectolax`. Wix peppers the markup with zero-width spaces and splits some
labels across lines; we strip the zero-width chars and read by keyword/region.

**Wix proxy trap:** like the other Wix providers, the host blocks the fetch
proxy's plain/auto datacenter egress — only the stealth `render=1` tier returns
the page. CI fetches through the proxy, so every request forces `render=1` via
`PROXY_PARAMS_HEADER` (inert on a direct dev fetch).

The current edition lives on Wix "kopie-…" ("copy") pages (the org duplicates
last year's pages for the new edition); the home menu links to them. We hard-pin
those slugs and re-confirm them when they roll over.

DISCOVERY: one provider, one current edition. The workshop runs as two
consecutive one-week blocks (13–17 and 20–24 July 2026) attendable as one week
or both — that's a fee tier, not two Offerings (same program/ages/venue, like
Prague Ballet Intensive). We emit **one Offering**, season-keyed from the parsed
year so the id rolls forward.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-16):
  - DATES: workshop page "July 13th - 24th 2026" (bespoke "<month> D-D YYYY" regex).
  - GENRES from the program list ("ballet class, point shoes, man's technique,
    repertoire, contemporary"; pilates is conditioning, not a genre) → classical,
    pointe, repertoire, contemporary.
  - AGE: "aged 13-21 years" / Terms "Age: 13 - 21 years".
  - LEVEL: "specially created for students of ballet schools and dance
    conservatories" → pre-professional.
  - PRICES in EUR: 1 week €850, 2 weeks €1400 (tuition).
  - REQUIREMENTS: a short dance video "showing dance level" — an open brief →
    VideoReq(unspecific); applications are open (downloadable form + online form).
  - TEACHERS: the "Summer 2026" instructor roster (names only — Wix splits the
    credential lines across nodes, so attributing each bio/affiliation reliably
    isn't possible; the names are the edition's named faculty).
  - LOCATION: studio at Budečská 35, Praha 2 - Vinohrady.
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
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

BASE = "https://www.pragueballetworkshop.com"
WORKSHOP = f"{BASE}/kopie-workshop-2"
PRICES = f"{BASE}/kopie-prices-and-detailed-info"
APPLICATIONS = f"{BASE}/kopie-applications-2"
INSTRUCTORS = f"{BASE}/kopie-instructors-1"
LOCATION = f"{BASE}/kopie-location-ballet-studio-1"

# Wix blocks the proxy's plain/auto egress; only the stealth render tier returns
# the page (inert on a direct dev fetch).
_RENDER = {PROXY_PARAMS_HEADER: "render=1&wait=8000"}

ORG = Organization(
    name="Prague Ballet Workshop",
    slug="prague-ballet-workshop",
    country="CZ",
    city="Prague",
)

_DATES_RE = re.compile(
    rf"({parse.MONTHALT})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*[-–]\s*(\d{{1,2}})(?:st|nd|rd|th)?\s+(\d{{4}})",
    re.I,
)
_AGE_RE = re.compile(r"(?:aged|Age:?)\s*(\d{1,2})\s*[-–]\s*(\d{1,2})\s*years", re.I)
_PRICE_RE = re.compile(r"(\d+)\s*weeks?\s*€\s*([\d.,]+)", re.I)

_GENRES: list[tuple[Genre, list[str]]] = [
    ("classical", ["ballet class", "man´s technique", "man's technique"]),
    ("pointe", ["point shoes", "pointe"]),
    ("repertoire", ["repertoire"]),
    ("contemporary", ["contemporary"]),
]

# Tokens that mark a line as a credential/section heading, not an instructor name.
_NOT_NAME = {
    "EX",
    "FROM",
    "DANCER",
    "DANCERS",
    "PRINCIPAL",
    "SOLIST",
    "SOLOIST",
    "TEACHER",
    "TEACHERS",
    "CHOREOGRAPHER",
    "INSTRUCTOR",
    "INSTRUCTORS",
    "BALLETMASTER",
    "ASSISTANT",
    "CERTIFICATED",
    "RENOWNED",
    "FREELANCE",
    "BALLET",
    "PILATES",
    "NACHO",
    "DUATO",
    "ORLANDO",
    "CZECH",
    "NATIONAL",
    "WORKING",
    "WORLD",
    "OVER",
    "ALL",
    "AND",
    "OF",
    "CONTEMPORARY",
    "DANCE",
    "VARIATION",
    "CLASS",
    "POINT",
    "SHOES",
    "MEET",
    "OUR",
    "GREAT",
    "STUDENTS",
    "WERE",
    "COMPANIES",
    "DIFFERENT",
}


def scrape(client: httpx.Client) -> list[Offering]:
    def text(url: str) -> str:
        return _page_text(client.get(url, headers=_RENDER).text)

    return _build_offerings(
        text(WORKSHOP), text(PRICES), text(APPLICATIONS), text(INSTRUCTORS), text(LOCATION)
    )


def _page_text(html: str) -> str:
    tree = HTMLParser(html)
    for junk in tree.css("script, style, noscript"):
        junk.decompose()
    body = tree.body
    text = body.text(separator="\n") if body else ""
    text = text.replace("​", "")  # Wix zero-width spaces
    lines = [parse.clean(line) for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _dates(workshop: str) -> tuple[date | None, date | None, int | None, str | None]:
    match = _DATES_RE.search(workshop)
    if not match:
        return None, None, None, None
    month = parse.MONTHS[match.group(1).lower()]
    year = int(match.group(4))
    start = date(year, month, int(match.group(2)))
    end = date(year, month, int(match.group(3)))
    return start, end, year, match.group(0)


def _age_range(text: str) -> dict | None:
    match = _AGE_RE.search(text)
    return {"min": int(match.group(1)), "max": int(match.group(2))} if match else None


def _prices(prices_text: str) -> list[Price]:
    out: list[Price] = []
    seen: set[int] = set()
    for weeks, raw_amount in _PRICE_RE.findall(prices_text):
        n = int(weeks)
        amount = parse.parse_amount(raw_amount)
        if n in seen or amount is None:
            continue
        seen.add(n)
        out.append(
            Price(
                amount=amount,
                currency="EUR",
                label=f"{n} week{'s' if n > 1 else ''}",
                includes=["tuition"],
            )
        )
    return sorted(out, key=lambda p: p.amount)


def _teachers(instructors_text: str) -> list[Teacher]:
    lower = instructors_text.lower()
    start = lower.find("meet our instructors")
    region = instructors_text[start:] if start >= 0 else instructors_text
    for marker in ("partners:", "©"):
        cut = region.lower().find(marker)
        if cut >= 0:
            region = region[:cut]
    teachers: list[Teacher] = []
    seen: set[str] = set()
    for line in region.split("\n"):
        if not _is_name(line):
            continue
        name = _norm_name(line)
        if name not in seen:
            seen.add(name)
            teachers.append(Teacher(name=name))
    return teachers


def _is_name(line: str) -> bool:
    if len(line) > 35 or any(c.isdigit() for c in line):
        return False
    tokens = re.findall(r"[^\W\d_]+", line, re.UNICODE)
    if not 2 <= len(tokens) <= 4:
        return False
    return not any(token.upper() in _NOT_NAME for token in tokens)


def _norm_name(line: str) -> str:
    return re.sub(r"[´`]", "'", line).title()


def _build_offerings(
    workshop: str, prices: str, applications: str, instructors: str, location: str
) -> list[Offering]:
    start, end, year, raw = _dates(workshop)
    if year is None:
        return []

    application = Application(
        status="open",
        url=APPLICATIONS,
        requirements=[
            VideoReq(
                specificity="unspecific", description="A short dance video showing dance level."
            )
        ]
        if "dance video" in applications.lower()
        else [],
        notes=(
            "Apply via the downloadable form plus the online form, with a short "
            "dance video. Full payment by bank transfer confirms the place."
        ),
    )

    offering = Offering(
        id=f"prague-ballet-workshop/{year}",
        source=Source(provider="prague-ballet-workshop", url=BASE, scrapedAt=now_utc()),
        title=f"Prague Summer Ballet Workshop {year}",
        genres=parse.match_genres(workshop, _GENRES),
        level=_levels(workshop),
        ageRange=_age_range(workshop) or _age_range(applications),
        organization=ORG,
        location=_location(location),
        schedule=Schedule(season="summer", start=start, end=end, notes=raw),
        teachers=_teachers(instructors),
        prices=_prices(prices),
        application=application,
    )
    return [offering]


def _levels(workshop: str) -> list[Level]:
    return ["pre-professional"] if "conservatori" in workshop.lower() else []


def _location(location: str) -> Location:
    match = re.search(r"(Budečská[^\n]*)", location)
    venue = parse.clean(match.group(1)) if match else None
    return Location(venue=venue, city="Prague", country="CZ")
