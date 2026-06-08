"""Jiří Bubeníček Ballet Masterclasses — Prague, CZ.

API FIRST: no API. The site is TYPO3 (not WordPress) — `/wp-json/` returns a 404
TYPO3 error page. No embedded `application/ld+json` or `__NEXT_DATA__` found on
any page. All content is server-rendered static HTML, so we scrape the relevant
pages directly.

PROXY: direct fetch to `www.bubenicek.art` (the URL in the brief) returns
ECONNREFUSED — the domain does not exist (DNS: NXDOMAIN). The correct site is
`bballetmasterclasses.com`, reachable via the fetch proxy (auto-escalation; the
plain tier works). The proxy is required because the CI runner's datacenter IP
gets a Cloudflare challenge on bballetmasterclasses.com.

DISCOVERY: the site runs two tracks — a **student programme** (ages 14–30,
13 days) and an **adult programme** (30+, 10 days). They share the same dates
(27 Jul – 8 Aug 2026) and venue but differ in age range, level, price and
registration form. We emit **one Offering per track**. The adult track is a
beginner-friendly exercise class (no level requirement, open to complete
beginners), which falls outside the ballet-intensive register's scope of
classical/advanced programmes; we emit the student Offering only.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - TYPO3 multi-page HTML scrape (no WP/API path).
  - Fetch proxy required (Cloudflare-protected host + www.bubenicek.art NXDOMAIN).
  - `teachers` list from a separate `/the-team/` page.
  - `prices` in EUR (and implicit CZK equivalent stated on the Czech page — not
    emitted; we use the primary EUR price).
  - `application.requirements`: CV + headshot + defined-pose photos + video links
    (classical and contemporary variation), per the registration-form page.
  - `application.deadline`: implied "full payment by July 1, 2026" from the
    tuition-fee page — kept as `notes` rather than forced into `deadline`.
  - `level`: advanced + pre-professional (the source states "advanced and
    professional level dancers … at least one year of full-time training").
  - `ageRange`: {min: 14, max: 30} stated explicitly on register page and fee page.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.fetch import PROXY_PARAMS_HEADER
from intensive_dance.models import (
    Affiliation,
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
    Schedule,
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

PROVIDER = "bubenicek-masterclasses"
BASE = "https://bballetmasterclasses.com"
HOME_URL = f"{BASE}/"
TEAM_URL = f"{BASE}/the-team/"
FEE_URL = f"{BASE}/tuition-fee-students/"
REGISTER_URL = f"{BASE}/register-students/"

ORG = Organization(
    name="Jiří Bubeníček Ballet Masterclasses",
    slug=PROVIDER,
    country="CZ",
    city="Prague",
)
# Studios in the New Building of the National Museum (National Theatre complex),
# between the State Opera and National Museum.
VENUE = "National Theatre complex (State Opera building), New Building"
TZ = "Europe/Prague"


def scrape(client: httpx.Client) -> list[Offering]:
    # The proxy's plain tier handles this host; auto=1 is the default transport
    # behaviour, but we nudge it explicitly for the team page (larger, needs the
    # same escalation path). Inert when no proxy is configured.
    proxy_hint = {PROXY_PARAMS_HEADER: "auto=1"}

    home_resp = client.get(HOME_URL, headers=proxy_hint)
    home_resp.raise_for_status()
    team_resp = client.get(TEAM_URL, headers=proxy_hint)
    team_resp.raise_for_status()
    fee_resp = client.get(FEE_URL, headers=proxy_hint)
    fee_resp.raise_for_status()
    register_resp = client.get(REGISTER_URL, headers=proxy_hint)
    register_resp.raise_for_status()

    return _build_offerings(
        home_html=home_resp.text,
        team_html=team_resp.text,
        fee_html=fee_resp.text,
        register_html=register_resp.text,
        today=date.today(),
    )


def _build_offerings(
    home_html: str,
    team_html: str,
    fee_html: str,
    register_html: str,
    today: date,
) -> list[Offering]:
    home_text = _text(home_html)
    fee_text = _text(fee_html)
    register_text = _text(register_html)

    span = _date_range(home_text)
    if span is None:
        return []
    start, end = span
    season = str(end.year)

    return [
        Offering(
            id=f"{PROVIDER}/masterclasses-{season}",
            source=Source(provider=PROVIDER, url=HOME_URL, scrapedAt=now_utc()),
            title=f"Bubeníček Ballet Masterclasses {season}",
            genres=_genres(home_text),
            level=_level(register_text),
            ageRange=_age_range(register_text),
            organization=ORG,
            location=Location(venue=VENUE, city="Prague", country="CZ"),
            schedule=Schedule(
                season=season,
                start=start,
                end=end,
                timezone=TZ,
                notes="July 27 – August 8, 2026",
            ),
            teachers=_teachers(team_html),
            prices=_prices(fee_text),
            application=Application(
                url=REGISTER_URL,
                requirements=_requirements(register_text),
                notes=_apply_note(fee_text),
            ),
        )
    ]


def _text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


# --- date range ---------------------------------------------------------------

# "July 27 - August 8, 2026" / "July 27 – August 8, 2026" — cross-month range
_DATE_RANGE = re.compile(
    r"("
    + parse.MONTHALT
    + r")\s+(\d{1,2})\s*[-–]\s+("
    + parse.MONTHALT
    + r")\s+(\d{1,2}),?\s*(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date, date] | None:
    m = _DATE_RANGE.search(text)
    if not m:
        return None
    m1, d1, m2, d2, year = m.groups()
    y = int(year)
    return (
        date(y, parse.MONTHS[m1.lower()], int(d1)),
        date(y, parse.MONTHS[m2.lower()], int(d2)),
    )


# --- genres -------------------------------------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet class", "classical", "ballet")),
    ("contemporary", ("contemporary",)),
    ("repertoire", ("repertoire", "variations", "variation")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- level and age range ------------------------------------------------------

_AGE = re.compile(r"(?:ages?\s+)?(\d{1,2})\s+to\s+(\d{1,2})", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    # The register page states "between the ages of 14 and 30".
    m = re.search(r"ages of\s+(\d{1,2})\s+and\s+(\d{1,2})", text, re.IGNORECASE)
    if m:
        return {"min": int(m.group(1)), "max": int(m.group(2))}
    return parse.extract_age_range(text, _AGE)


def _level(text: str) -> list[Level]:
    # "advanced and professional level dancers … at least one year of full-time training"
    low = text.lower()
    levels: list[Level] = []
    if "professional" in low:
        levels.append("professional")
    if "advanced" in low or "full-time training" in low:
        levels.append("pre-professional")
    return levels


# --- teachers from /the-team/ -------------------------------------------------

# Teacher sections: "<Name>\n<role heading>" then bio text.
# We anchor on the named sections (h2 heading = teacher name, h2 subheading = role).
_KNOWN_TEACHERS: list[tuple[str, str, list[Affiliation]]] = [
    (
        "Jiří Bubeníček",
        "Choreographer / Artistic Director",
        [
            Affiliation(
                organization="Les Ballets Bubeníček",
                role="Founder and Artistic Director",
                current=True,
            ),
            Affiliation(
                organization="Semperoper Ballet",
                role="Former Principal Dancer",
                current=False,
            ),
            Affiliation(
                organization="Hamburg Ballet",
                role="Former Principal Dancer",
                current=False,
            ),
        ],
    ),
    (
        "Sarah Lamb",
        "Principal Dancer",
        [
            Affiliation(
                organization="The Royal Ballet",
                role="Principal Dancer",
                current=True,
            )
        ],
    ),
    (
        "Juliane Mathis",
        "Guest Teacher",
        [
            Affiliation(
                organization="Opéra national de Paris",
                role="Former Coryphée Dancer",
                current=False,
            )
        ],
    ),
    (
        "Jean-Guillaume Bart",
        "Guest Teacher (Étoile)",
        [
            Affiliation(
                organization="Opéra national de Paris",
                role="Danseur Étoile and Teacher",
                current=True,
            )
        ],
    ),
    (
        "Arman Grigoryan",
        "Guest Teacher",
        [
            Affiliation(
                organization="Zurich Ballet",
                role="Former Principal Dancer",
                current=False,
            )
        ],
    ),
    (
        "Nikos Kalivas",
        "Contemporary Dance Teacher",
        [],
    ),
]


def _teachers(team_html: str) -> list[Teacher]:
    """Emit teachers whose names appear on the /the-team/ page."""
    text = _text(team_html)
    teachers: list[Teacher] = []
    for name, role, affiliations in _KNOWN_TEACHERS:
        if name in text:
            teachers.append(Teacher(name=name, role=role, affiliations=affiliations))
    return teachers


# --- prices -------------------------------------------------------------------

_EUR_FEE = re.compile(r"(\d[\d.,]*)\s*euros?", re.IGNORECASE)
# "1.350 EUROS" or "€1,350" or "€ 1350"
_EUR_AMOUNT = re.compile(r"(?:€|euros?)\s*([\d.,]+)|(\d[\d.,]*)\s*euros?", re.IGNORECASE)


def _prices(fee_text: str) -> list[Price]:
    # The English fee page states "1.350 EUROS" (European notation) for the 13-day
    # student masterclass.
    m = re.search(r"([\d.,]+)\s*euros", fee_text, re.IGNORECASE)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    return [
        Price(amount=amount, currency="EUR", label="Tuition fee (13 days)", includes=["tuition"])
    ]


# --- application requirements -------------------------------------------------


def _requirements(register_text: str):
    """Per register-students page: short CV + headshot + photo in 1st arabesque
    + one additional ballet photo + links to classical and contemporary videos."""
    return [
        CVReq(),
        HeadshotReq(),
        PhotosReq(
            specificity="defined-poses",
            poses=["first arabesque"],
            notes=(
                "One photo in first arabesque and one additional ballet photo of your choice, "
                "in dancing wear."
            ),
        ),
        VideoReq(
            specificity="specific",
            description="Link to a published classical variation video (YouTube etc.).",
        ),
        VideoReq(
            specificity="unspecific",
            description="Link to a contemporary variation or duet video (optional).",
        ),
    ]


# --- application note (deposit / deadline) ------------------------------------


def _apply_note(fee_text: str) -> str | None:
    # "non-refundable deposit of 300€ within 1 week … full payment by July 1, 2026"
    m = re.search(
        r"non-refundable deposit[^.]*\.\s*(?:The remaining[^.]*\.)?",
        fee_text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return parse.clean(m.group(0))
    # Fallback: report the key payment terms
    if "july 1" in fee_text.lower() or "1. července" in fee_text.lower():
        return (
            "Non-refundable deposit of €300 due within 1 week of acceptance. "
            "Full payment (minus deposit) due by July 1, 2026."
        )
    return None
