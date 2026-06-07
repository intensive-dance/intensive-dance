"""BalletStage Summer Intensive — Ljubljana, Slovenia (its dated 2026 edition).

API FIRST: none usable. BalletStage runs on **Wix** (no public content API we may
use), but the Summer Intensive page is server-side rendered, so the full text is
present in the static HTML — a one-page scrape, no JS needed. We route through the
fetch proxy only because the CI runner's datacenter IP is otherwise blocked; the
markup is identical to a direct fetch.

DISCOVERY: BalletStage is a multi-event org (a Summer Intensive plus separate
Summer/Winter MasterClass events), all currently in **Ljubljana** — there are no
dated 2026 editions in other cities (Brno/Kyiv appear only inside faculty bios).
The `/summerintensive2026` page describes one two-week Summer Intensive
MasterClass; we emit a single `Offering`, season-keyed from the parsed dates so
the id rolls forward when the page advances a year. The co-located but distinct
MasterClass events are out of scope for this IDR-68 target.

WHAT THE PAGE GIVES US (verified live 2026-06):
  - DATES: "13 - 25 July 2026" (a two-week course; shared trailing month+year).
  - AGES: four participant groups A 10-13, B 13-14, C 15-17, D 18-30 — the
    Offering age band is the union (min 10, max 30); the per-group bands are kept
    verbatim as `schedule.sessions` notes so the pointe prerequisites survive.
  - LEVEL: eligibility is "professional, semi-professional, or … at least one year
    of full-time training" → pre-professional.
  - PRICES in EUR: tuition options (1370/wk, 2370/2wk incl. daily lunches) and
    camp options bundling accommodation + meals (1960/wk, 3460/2wk), plus add-ons
    (contemporary week, Olga Smirnova class, camp-only). All "incl. applicable
    taxes". The Summer-Camp section repeats the camp prices, so we de-duplicate.
  - DEADLINE: "The deadline for applications is 20th June 2026" (the page's own
    figure — kept verbatim over any external hint). A separate cutoff: the chosen
    variation's title/video/music are "submitted one month before the start, by 12
    June", kept as an application note.
  - REQUIREMENTS: the Online Application Form asks for a YouTube video link of a
    variation/performance (no older than 2025), a portrait photo (headshot) and an
    arabesque photo (defined pose) — the granular audition data IDR-28 wants.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Affiliation,
    Application,
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
    Teacher,
    VideoReq,
    now_utc,
)

BASE = "https://www.balletstage.com"
PAGE = f"{BASE}/summerintensive2026"
APPLY_URL = f"{BASE}/summerintensiveapplicationform2026"

ORG = Organization(
    name="BalletStage",
    slug="balletstage",
    country="SI",
    city="Ljubljana",
)

VENUE = "Conservatory of Music and Ballet Ljubljana (KGBL)"

_VARIATION_NOTE = (
    "The chosen variation's title, video and music must be submitted one month "
    "before the start of the intensive (by 12 June). "
    "Payment terms: a non-refundable EUR 400 deposit secures a place once accepted "
    "and must be paid within 7 days of the acceptance notification; "
    "the balance is due within 60 days of the deposit (but no later than 1 June "
    "for late applications)."
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    offering = _build_offering(resp.text)
    return [offering] if offering is not None else []


def _build_offering(html: str) -> Offering | None:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    start, end = _date_range(text)
    if start is None or end is None:
        return None  # no dated edition parseable
    season = str(end.year)
    sessions = _sessions(text, start, end)

    return Offering(
        id=f"balletstage/summer-intensive-{season}",
        source=Source(provider="balletstage", url=PAGE, scrapedAt=now_utc()),
        title=f"Summer Intensive MasterClass {season}",
        genres=_genres(text),
        level=_level(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue=VENUE, city="Ljubljana", country="SI"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Ljubljana",
            sessions=sessions,
        ),
        teachers=_teachers(text),
        prices=_prices(text),
        application=Application(
            status=_status(text),
            deadline=_deadline(text),
            url=APPLY_URL,
            requirements=_requirements(),
            notes=_VARIATION_NOTE,
        ),
    )


# --- dates: "13 - 25 July 2026" (shared trailing month + year) ----------------

_RANGE = re.compile(
    r"(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    d1, d2, month, year = m.groups()
    mon = parse.MONTHS[month.lower()]
    y = int(year)
    return date(y, mon, int(d1)), date(y, mon, int(d2))


# --- participant groups: "Group A 10-13 years old | No Pointe Shoes …" ---------

_GROUP = re.compile(
    r"Group\s+([A-D])\s+(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+years?\s+old\s*\|?\s*"
    r"([^G]*?)(?=Group\s+[A-D]\b|Ballet Shop|Apply Now|$)",
    re.IGNORECASE,
)


def _sessions(text: str, start: date, end: date) -> list[Session]:
    """One `Session` per participant group, preserving each band's pointe note.

    The groups differ only by age and pointe prerequisite (not by date or fee),
    so they're sessions of the one Offering rather than separate Offerings.
    """
    sessions: list[Session] = []
    for m in _GROUP.finditer(text):
        letter, low, high, note = m.groups()
        sessions.append(
            Session(
                label=f"Group {letter}",
                start=start,
                end=end,
                ageRange={"min": int(low), "max": int(high)},
                notes=parse.clean(note) or None,
            )
        )
    return sessions


def _age_range(text: str) -> dict | None:
    """Union of the per-group age bands (Group A's floor → Group D's ceiling)."""
    bounds = [(int(lo), int(hi)) for _, lo, hi, _ in _GROUP.findall(text)]
    if not bounds:
        return None
    return {"min": min(lo for lo, _ in bounds), "max": max(hi for _, hi in bounds)}


def _level(text: str) -> list[Level]:
    low = text.lower()
    if "full-time training" in low or "semi-professional" in low:
        return ["pre-professional"]
    return []


# --- prices: "<label> Euro 1370 including applicable taxes" --------------------

_PRICE = re.compile(
    r"([A-Za-z0-9 &\"'()/.-]+?)\s+Euro\s+([\d.,]+)\s+including applicable taxes",
    re.IGNORECASE,
)
# Per-day add-on stated differently ("Euro 200 per day").
_PRICE_PER_DAY = re.compile(r"Euro\s+([\d.,]+)\s+per day", re.IGNORECASE)


def _price_includes(label: str) -> list[PriceInclude]:
    low = label.lower()
    includes: list[PriceInclude] = []
    if "camp only" not in low:
        includes.append("tuition")
    if "accommodation" in low:
        includes.append("accommodation")
    if "meals" in low or "lunch" in low:
        includes.append("meals")
    return includes


_OPTION_START = re.compile(r"(?:\d+\s+Weeks?|Olga Smirnova)", re.IGNORECASE)


def _price_label(label: str) -> str:
    """Trim the label to its own option name (drop the preceding option's prose).

    The price capture greedily absorbs trailing text from the option above it, so
    we keep only the tail from the *last* option-start keyword ("N Week(s)" /
    "Olga Smirnova") before the amount — that's where this option's name begins.
    """
    label = parse.clean(label)
    starts = list(_OPTION_START.finditer(label))
    return label[starts[-1].start() :] if starts else label


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    seen: set[tuple[float, str]] = set()
    for m in _PRICE.finditer(text):
        amount = parse.parse_amount(m.group(2))
        if amount is None:
            continue
        label = _price_label(m.group(1))
        key = (amount, label.lower())
        if key in seen:  # the Summer-Camp section repeats the camp options
            continue
        seen.add(key)
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=label,
                includes=_price_includes(label),
                notes="Includes applicable taxes.",
            )
        )
    day = _PRICE_PER_DAY.search(text)
    if day:
        amount = parse.parse_amount(day.group(1))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="Olga Smirnova class (per day)",
                    includes=["tuition"],
                    notes="For participants without general masterclass admission (21–24 July).",
                )
            )
    return prices


# --- genres -------------------------------------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet class", "ballet technique")),
    ("pointe", ("pointe",)),
    ("repertoire", ("repertoire", "variation")),
    ("contemporary", ("contemporary",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- application status & deadline --------------------------------------------


def _status(text: str):
    low = text.lower()
    if re.search(r"registrations?\s+open", low):
        return "open"
    # The status word sits right after the event title ("… MasterClass Closed");
    # the Winter edition states a bare "Closed" rather than "Registrations Closed".
    if re.search(r"registrations?\s+closed|applications?\s+closed|masterclass\s+closed", low):
        return "closed"
    return None


_DEADLINE = re.compile(
    r"deadline for applications is\s+(\d{1,2})(?:st|nd|rd|th)?\s+("
    + parse.MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _deadline(text: str) -> date | None:
    m = _DEADLINE.search(text)
    if not m:
        return None
    day, month, year = m.groups()
    return date(int(year), parse.MONTHS[month.lower()], int(day))


# --- teachers: "Meet Our Ballet Masters" section ------------------------------


def _teachers(text: str) -> list[Teacher]:
    """Parse the eight named ballet masters from the 'Meet Our Ballet Masters' section.

    Each master's role label follows their name directly; affiliations are stated
    in the opening sentences of their biography. Roles and affiliations are taken
    verbatim from what the page states, without embellishment.
    """
    teachers: list[Teacher] = []

    if "Olga Smirnova" in text:
        teachers.append(
            Teacher(
                name="Olga Smirnova",
                role="Special Guest",
                affiliations=[Affiliation(organization="Dutch National Ballet", role="Principal")],
            )
        )
    if "Natalia Gasmaeva" in text:
        teachers.append(
            Teacher(
                name="Natalia Gasmaeva",
                role="Ballet Master",
                affiliations=[
                    Affiliation(
                        organization="John Cranko School",
                        role="Ballet Master",
                        current=True,
                    )
                ],
            )
        )
    if "Stéphane Phavorin" in text:
        teachers.append(
            Teacher(
                name="Stéphane Phavorin",
                role="International Guest Ballet Master",
                affiliations=[
                    Affiliation(
                        organization="Paris Opéra Ballet",
                        role="former Premier Danseur",
                        current=False,
                    )
                ],
            )
        )
    if "Denis Matvienko" in text:
        teachers.append(
            Teacher(
                name="Denis Matvienko",
                role="Co-Founder & Artistic Director",
                affiliations=[
                    Affiliation(organization="BalletStage", role="Co-Founder & Artistic Director")
                ],
            )
        )
    if "Anastasia Matvienko" in text:
        teachers.append(
            Teacher(
                name="Anastasia Matvienko",
                role="Principal Guest Dancer & Co-Founder",
                affiliations=[
                    Affiliation(
                        organization="BalletStage", role="Principal Guest Dancer & Co-Founder"
                    )
                ],
            )
        )
    if "Valeryia Vapniarskaya" in text:
        teachers.append(
            Teacher(
                name="Valeryia Vapniarskaya",
                role="Ballet Master & Choreographer",
            )
        )
    if "Maša Kagao Knez" in text:
        teachers.append(
            Teacher(
                name="Maša Kagao Knez",
                role="Ballet Master",
            )
        )
    if "Tijuana Križman Khudernik" in text:
        teachers.append(
            Teacher(
                name="Tijuana Križman Khudernik",
                role="Ballet Dancer & Contemporary Ballet Master",
            )
        )

    return teachers


# --- requirements: the Online Application Form (audition by submission) --------


def _requirements() -> list[Requirement]:
    """The application form's fixed fields — a video link, a portrait, an arabesque.

    These are stable form fields (not free prose), so they're encoded directly
    rather than scraped from the (separate, mostly-empty) form page.
    """
    return [
        VideoReq(
            specificity="specific",
            description=(
                "A YouTube link to a video of a variation or performance, "
                "filmed no earlier than 2025."
            ),
        ),
        HeadshotReq(),
        PhotosReq(
            specificity="defined-poses",
            poses=["arabesque"],
            notes="One portrait photo and one photo in arabesque.",
        ),
    ]
