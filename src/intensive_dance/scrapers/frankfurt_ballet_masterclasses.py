"""Frankfurt Ballet Masterclasses (FBM) — Frankfurt am Main, DE.

API FIRST: none. FBM is a single-page site (under the balletcompetition.net
domain) describing the current edition — so this is a one-page HTML scrape.

TLS NOTE: the host serves an incomplete certificate chain, so the shared client
can't reach it; we fetch with our own `verify=False` client (read-only public
page — see `fetch.make_client`). Application deadline lives on a separate
`/contact-terms-conditions.html` page which we also fetch in `scrape()`.

FACULTY: the class teachers live in the "#ourTeachers" Bootstrap cards (name +
discipline), each opening a modal whose bio names the teacher's training/company
institutions. We parse the cards (skipping the organizer/founder card) and mine
each modal bio for the institutions in `_INSTITUTIONS` → `Teacher.affiliations`.
Parsing the DOM (not hardcoding names) keeps A1 (faculty pedigree) correct when a
future edition swaps its faculty — e.g. Olga Melnikova → Mariinsky/Semperoper/
Palucca, Denis Untila → Aalto/Ballett Kiel/Vienna (verified live 2026-06-07).
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
        teachers=_teachers(tree),
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


# Faculty live in the "#ourTeachers" section as Bootstrap cards: an <h4> name + two
# <span class="small"> (role-type "Teacher"/"Organizer", then the discipline), each linking
# to a modal whose body carries the career bio. We keep the class teachers (skip the
# organizer/founder card) and mine each bio for the institutions below → Affiliations
# (faithful: each org is stated in the teacher's own bio). DOM-based so a faculty change in
# a future edition is picked up automatically, not silently dropped.
_NOT_TEACHER = {"organizer", "organiser", "founder"}

# Notable training/company institutions, matched case-insensitively in a teacher's bio.
# (needle, canonical organization); aliases (kirov→Mariinsky) dedupe to one Affiliation.
_INSTITUTIONS: list[tuple[str, str]] = [
    ("vaganova", "Vaganova Ballet Academy"),
    ("mariinsky", "Mariinsky Theatre"),
    ("kirov", "Mariinsky Theatre"),
    ("bolshoi", "Bolshoi Ballet"),
    ("semperoper", "Semperoper Ballett Dresden"),
    ("palucca", "Palucca Hochschule für Tanz Dresden"),
    ("aalto", "Aalto Ballett Essen"),
    ("ballet kiel", "Ballett Kiel"),
    ("conservatory of vienna", "Conservatory of Vienna"),
    ("vienna conservat", "Conservatory of Vienna"),
    ("paris opera", "Paris Opera Ballet"),
    ("opéra de paris", "Paris Opera Ballet"),
    ("royal ballet", "The Royal Ballet"),
    ("la scala", "Teatro alla Scala Ballet"),
    ("stuttgart ballet", "Stuttgart Ballet"),
    ("hamburg ballet", "Hamburg Ballett"),
    ("nederlands dans", "Nederlands Dans Theater"),
]


def _teachers(tree: HTMLParser) -> list[Teacher]:
    """Parse the "#ourTeachers" cards — class teachers with disciplines + mined affiliations."""
    section = tree.css_first("#ourTeachers")
    if section is None:
        return []
    teachers: list[Teacher] = []
    for card in section.css("div.col a[data-bs-target]"):
        name_node = card.css_first("h4")
        if name_node is None:
            continue
        name = parse.clean(name_node.text())
        if not name:
            continue
        spans = [parse.clean(s.text()) for s in card.css("span.small")]
        role_type = spans[0].lower() if spans else ""
        if role_type in _NOT_TEACHER:
            continue  # the FBM organizer/founder card, not a class teacher
        role = f"{spans[0]} ({spans[1]})" if len(spans) > 1 else (spans[0] if spans else None)
        modal_id = (card.attributes.get("data-bs-target") or "").lstrip("#")
        modal = tree.css_first(f"#{modal_id}") if modal_id else None
        affiliations = _affiliations(modal) if modal is not None else []
        teachers.append(Teacher(name=name, role=role, affiliations=affiliations))
    return teachers


def _affiliations(modal) -> list[Affiliation]:
    bio = parse.clean(modal.text(separator=" ")).lower()
    affs: list[Affiliation] = []
    seen: set[str] = set()
    for needle, org in _INSTITUTIONS:
        if needle in bio and org not in seen:
            affs.append(Affiliation(organization=org))
            seen.add(org)
    return affs


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
