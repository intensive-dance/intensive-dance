"""Frankfurt Ballet Masterclasses (FBM) — Frankfurt am Main, DE.

API FIRST: none. FBM is a single-page site (under the balletcompetition.net
domain) describing the current edition — so this is a one-page HTML scrape.

TLS NOTE: the host serves an incomplete certificate chain, so the shared client
can't reach it; we fetch with our own `verify=False` client (read-only public
page — see `fetch.make_client`). One `Offering` — the current two-day
masterclass — dropped once its end date is past.
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
    Genre,
    Location,
    NoneReq,
    Offering,
    Organization,
    PhotosReq,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://masterclass.balletcompetition.net"

ORG = Organization(
    name="Frankfurt Ballet Masterclasses", slug="frankfurt-ballet-masterclasses",
    country="DE", city="Frankfurt am Main",
)
VENUE = "Dr. Hoch's Konservatorium"


def scrape(client: httpx.Client) -> list[Offering]:  # noqa: ARG001 — see TLS NOTE
    # The shared client can't validate FBM's incomplete cert chain; use our own.
    own = make_client(verify=False)
    try:
        resp = own.get(f"{BASE}/")
        resp.raise_for_status()
        html = resp.text
    finally:
        own.close()

    offering = _build_offering(html, date.today())
    return [offering] if offering is not None else []


def _build_offering(html: str, today: date) -> Offering | None:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    start, end = _date_range(text)
    anchor = start or end
    if anchor is None:
        return None  # no dated edition announced
    season = str(anchor.year)

    return Offering(
        id=f"frankfurt-ballet-masterclasses/{season}",
        source=Source(provider="frankfurt-ballet-masterclasses", url=f"{BASE}/", scrapedAt=now_utc()),
        title=f"Frankfurt Ballet Masterclasses {season}",
        genres=_genres(text),
        kind="masterclass",
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue=VENUE, city="Frankfurt am Main", country="DE"),
        schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Berlin"),
        application=Application(
            status="open" if re.search(r"register now|registration is open", text, re.IGNORECASE) else None,
            url=f"{BASE}/",
            requirements=_requirements(text),
        ),
    )


# --- parsing ------------------------------------------------------------------

# "August 22 - 23, 2026" or "August 22/23, 2026" (shared month).
_RANGE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})\s*[-/–]\s*(\d{1,2}),?\s*(\d{4})", re.IGNORECASE
)
_AGE = re.compile(r"(?:ages?|aged)\s*(\d{1,2})\s*(?:[-–]|to)\s*(\d{1,2})", re.IGNORECASE)


def _date_range(text: str) -> tuple[date | None, date | None]:
    match = _RANGE.search(text)
    if not match:
        return None, None
    month, d1, d2, year = match.groups()
    num = parse.MONTHS[month.lower()]
    return date(int(year), num, int(d1)), date(int(year), num, int(d2))


def _age_range(text: str) -> dict | None:
    match = _AGE.search(text)
    return {"min": int(match.group(1)), "max": int(match.group(2))} if match else None


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet")),
    ("contemporary", ("contemporary",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _requirements(text: str):
    """Read the application requirement from the page, defaulting to none.

    FBM is open to beginners through pre-professionals, so most editions take
    open registration; we only emit a requirement when the page states one.
    """
    section = text
    match = re.search(r"application requirements?(.*?)(cancellation|contact|\Z)", text, re.IGNORECASE | re.DOTALL)
    if match:
        section = match.group(1)
    low = section.lower()
    if "video" in low:
        return [VideoReq(specificity="unspecific", description=parse.clean(section)[:300] or None)]
    if re.search(r"\bphoto|picture|headshot", low):
        return [PhotosReq(specificity="freeform", notes=parse.clean(section)[:300] or None)]
    return [NoneReq()]  # open registration (beginners welcome) — explicitly nothing required
