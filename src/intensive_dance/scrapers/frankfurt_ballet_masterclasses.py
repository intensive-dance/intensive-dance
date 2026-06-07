"""Frankfurt Ballet Masterclasses (FBM) — Frankfurt am Main, DE.

API FIRST: none. FBM is a single-page site (under the balletcompetition.net
domain) describing the current edition — so this is a one-page HTML scrape.

TLS NOTE: the host serves an incomplete certificate chain, so the shared client
can't reach it; we fetch with our own `verify=False` client (read-only public
page — see `fetch.make_client`). Application deadline lives on a separate
`/contact-terms-conditions.html` page which we also fetch in `scrape()`.
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
    Location,
    NoneReq,
    Offering,
    Organization,
    PhotosReq,
    Price,
    Schedule,
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

BASE = "https://masterclass.balletcompetition.net"

ORG = Organization(
    name="Frankfurt Ballet Masterclasses",
    slug="frankfurt-ballet-masterclasses",
    country="DE",
    city="Frankfurt am Main",
)
VENUE = "Dr. Hoch's Konservatorium"


def scrape(client: httpx.Client) -> list[Offering]:  # noqa: ARG001 — see TLS NOTE
    # The shared client can't validate FBM's incomplete cert chain; use our own.
    own = make_client(verify=False)
    try:
        resp = own.get(f"{BASE}/")
        resp.raise_for_status()
        html = resp.text
        terms_resp = own.get(f"{BASE}/contact-terms-conditions.html")
        terms_html = terms_resp.text if terms_resp.is_success else ""
    finally:
        own.close()

    offering = _build_offering(html, terms_html, date.today())
    return [offering] if offering is not None else []


def _build_offering(html: str, terms_html: str, today: date) -> Offering | None:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    start, end = _date_range(text)
    anchor = start or end
    if anchor is None:
        return None  # no dated edition announced
    season = str(anchor.year)

    terms_text = _extract_text(terms_html)

    return Offering(
        id=f"frankfurt-ballet-masterclasses/{season}",
        source=Source(
            provider="frankfurt-ballet-masterclasses", url=f"{BASE}/", scrapedAt=now_utc()
        ),
        title=f"Frankfurt Ballet Masterclasses {season}",
        genres=_genres(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue=VENUE, city="Frankfurt am Main", country="DE"),
        schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Berlin"),
        teachers=_teachers(text),
        prices=_prices(text),
        application=Application(
            status="open"
            if re.search(r"register now|registration is open", text, re.IGNORECASE)
            else None,
            url=f"{BASE}/",
            deadline=_deadline(terms_text),
            requirements=_requirements(text),
        ),
    )


def _extract_text(html: str) -> str:
    if not html:
        return ""
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


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
    return parse.extract_age_range(text, _AGE)


# "Participation Fee - EUR 265", "Registration Fee - EUR 25" (currency before amount).
_FEE = re.compile(r"(participation|registration)\s+fee\s*[-–:]\s*EUR\s*([\d.,]+)", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    for kind, raw in _FEE.findall(text):
        amount = parse.parse_amount(raw)
        if amount is None:
            continue
        kind = kind.lower()
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=f"{kind.capitalize()} fee",
                # The participation fee is the masterclass tuition; the
                # registration fee is the (non-refundable) application fee.
                includes=["tuition"] if kind == "participation" else [],
            )
        )
    return prices


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet")),
    ("contemporary", ("contemporary",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- teachers: "Our Teachers" section of the main page ------------------------


def _teachers(text: str) -> list[Teacher]:
    """Parse the "Our Teachers" section — two named teachers with labelled disciplines."""
    teachers: list[Teacher] = []
    if "Olga Melnikova" in text:
        teachers.append(
            Teacher(
                name="Olga Melnikova",
                role="Teacher (Classical Ballet)",
                affiliations=[
                    Affiliation(
                        organization="Palucca University of Dance Dresden",
                        role="Professor",
                    )
                ],
            )
        )
    if "Denis Untila" in text:
        teachers.append(
            Teacher(
                name="Denis Untila",
                role="Teacher (Contemporary & Stretching)",
            )
        )
    return teachers


# --- application deadline: from /contact-terms-conditions.html ----------------

# "The closing date for applications is August 15, 2026 ."
_DEADLINE = re.compile(
    r"closing date for applications is\s+(" + parse.MONTHALT + r")\s+(\d{1,2}),?\s*(\d{4})",
    re.IGNORECASE,
)


def _deadline(terms_text: str) -> date | None:
    m = _DEADLINE.search(terms_text)
    if not m:
        return None
    month, day, year = m.groups()
    return date(int(year), parse.MONTHS[month.lower()], int(day))


# --- requirements: parse the FAQ photo requirements from page body ------------

# The FAQ states "Three photos as follows:" with per-group bullet poses.
# Group A (8-11): plié in 1st (profile), first arabesque 90°, à la seconde 90°
# Group B (12-18): same on pointe plus relevé in 4th croisé
_GROUP_A_POSES = [
    "Plié in first position (profile)",
    "First arabesque 90°",
    "À la seconde 90°",
]
_GROUP_B_POSES = [
    "First arabesque 90° (on pointe)",
    "À la seconde 90° (on pointe)",
    "Relevé in fourth position croisé (on pointe)",
]


def _requirements(text: str):
    """Read the application requirement from the FAQ body.

    The FAQ section "How do I apply?" lists three defined-pose photos per age
    group. The nav contains "Application requirements Cancellation" which is a
    menu link — we match the FAQ answer (anchored on "Three photos as follows")
    rather than the nav label.
    """
    if re.search(r"three photos as follows", text, re.IGNORECASE):
        # Both age groups submit three defined-pose photos; pose set differs.
        return [
            PhotosReq(
                specificity="defined-poses",
                poses=_GROUP_A_POSES,
                notes=(
                    "Group A (ages 8–11): 3 dance poses in profile — "
                    "plié in first position, first arabesque 90°, à la seconde 90°."
                ),
            ),
            PhotosReq(
                specificity="defined-poses",
                poses=_GROUP_B_POSES,
                notes=(
                    "Group B (ages 12–18): 3 dance poses on pointe — "
                    "first arabesque 90°, à la seconde 90°, relevé in fourth position croisé."
                ),
            ),
        ]
    if re.search(r"\bvideo\b", text, re.IGNORECASE):
        return [VideoReq(specificity="unspecific")]
    # Open registration with no stated requirement (e.g. future edition not yet specified).
    return [NoneReq()]
