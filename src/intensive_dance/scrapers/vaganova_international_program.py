"""Vaganova International Program (VIP) — Summer intensive at UNLV, Las Vegas, US.

API FIRST — none usable. The site is a single static hand-built page (no
WordPress: `/wp-json/` 404s; no ld+json, no Wix/Next state blob, no `generator`
meta). Everything we need is in the static HTML of the home page — dates, ages,
levels, curriculum, prices and the application status are all server-side text —
so this is a one-page selectolax scrape. The only dynamic part is the faculty
bios, which live as a `facultyBios` object in `main.js`; those affiliations are
well-known and hard-coded here (the named teachers, not free-scraped prose).

DISCOVERY: one dated summer edition per page. The home `<title>` and a "Summer
2026 — Las Vegas, Nevada" block stamp the cycle; the "Program dates: June 22nd to
July 3rd" line (year-less, ordinal suffixes) carries the span — we read the year
from the "Summer 2026" stamp and apply it. One Offering, season-keyed so the id
rolls forward when the page advances a year.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-09):
  - DATES from a year-less ordinal phrase ("June 22nd to July 3rd"), year lifted
    from the "Summer 2026" stamp (same shape as the Japanese year-less datelines).
  - AGES 9-19, the floor/ceiling of the three stated level bands (Level 1 9-11 …
    Level 3 15-19); the bands also map to beginner/intermediate/pre-professional.
  - PRICES in USD: tuition $2000 + non-refundable $150 registration, plus two
    optional UNLV room-and-board packages (private $1,600 / shared $1,150, both
    12 nights, accommodation+meals) — kept as separate `Price`s, not folded in.
  - REQUIREMENTS = VIDEO (unspecific): admission is by video audition (the
    audition form asks for an "Audition Video Link (YouTube/Vimeo)") — open-brief.
  - STATUS = closed: "all registrations closed … wait list". That closes the
    *application*, not the course — `lifecycle` stays `scheduled` (IDR-24: closed
    ≠ cancelled; the dated 2026 edition is kept).
  - TEACHERS: the two founder-directors plus five named faculty, each with a
    verifiable affiliation (Bolshoi, Colorado Ballet, Mariinsky, UNCSA, …).
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

BASE = "https://vaganovainternationalprogram.com"
PAGE = f"{BASE}/"
TZ = "America/Los_Angeles"  # Las Vegas, Nevada

ORG = Organization(
    name="Vaganova International Program",
    slug="vaganova-international-program",
    country="US",
    city="Las Vegas",
)

# Named faculty with their headline affiliation. These are confirmed roster names
# on the page (the `facultyBios` block / profile links), not free-scraped prose,
# so they stay hard-coded rather than guessed from the page text.
_TEACHERS: list[Teacher] = [
    Teacher(
        name="Alexei Moskalenko",
        role="Founder & Artistic Director",
        affiliations=[Affiliation(organization="Bolshoi Ballet", role="former dancer")],
    ),
    Teacher(
        name="Natalia Bashkatova",
        role="Founder & Artistic Director",
        affiliations=[Affiliation(organization="Bolshoi Theatre", role="former principal dancer")],
    ),
    Teacher(
        name="Maria Mosina",
        affiliations=[Affiliation(organization="Colorado Ballet")],
    ),
    Teacher(
        name="Misha Tchoupakov",
        affiliations=[
            Affiliation(organization="Bolshoi Ballet", role="former dancer"),
            Affiliation(
                organization="University of North Carolina School of the Arts",
                role="professor",
                current=True,
            ),
        ],
    ),
    Teacher(
        name="Maxwell Simoes",
        affiliations=[Affiliation(organization="Béjart Ballet Lausanne", role="former dancer")],
    ),
    Teacher(
        name="Andrea Astuto",
        affiliations=[
            Affiliation(
                organization="Odasz Dance Theatre",
                role="assistant director & company choreographer",
                current=True,
            )
        ],
    ),
    Teacher(
        name="Nadezhda Gonchar",
        affiliations=[Affiliation(organization="Mariinsky Ballet", role="former dancer")],
    ),
]


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

    year = _year(text)
    start, end = _dates(text, year)
    if start is None:
        return None  # no dated edition parseable
    season = str(start.year)

    return Offering(
        id=f"vaganova-international-program/summer-intensive-{season}",
        source=Source(provider="vaganova-international-program", url=PAGE, scrapedAt=now_utc()),
        title=f"Vaganova International Program — Summer {season}",
        genres=_genres(text),
        level=_levels(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(
            venue="University of Nevada, Las Vegas (UNLV)", city="Las Vegas", country="US"
        ),
        schedule=Schedule(season=season, start=start, end=end, timezone=TZ),
        teachers=_TEACHERS,
        prices=_prices(text),
        application=Application(
            status=_status(text),
            url=PAGE,
            requirements=_requirements(text),
            notes=_application_note(text),
        ),
    )


# --- dates -------------------------------------------------------------------

# "Summer 2026 — Las Vegas, Nevada" / "<title> … Summer 2026". The dateline
# itself ("Program dates: June 22nd to July 3rd") carries no year.
_YEAR = re.compile(r"Summer\s*(20\d{2})", re.IGNORECASE)
# "June 22nd to July 3rd" — ordinal suffixes, year supplied separately.
_RANGE = re.compile(
    rf"({parse.MONTHALT})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s+to\s+"
    rf"({parse.MONTHALT})\s+(\d{{1,2}})(?:st|nd|rd|th)?",
    re.IGNORECASE,
)


def _year(text: str) -> int | None:
    m = _YEAR.search(text)
    return int(m.group(1)) if m else None


def _dates(text: str, year: int | None) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m or year is None:
        return None, None
    m1, d1, m2, d2 = m.groups()
    start = date(year, parse.MONTHS[m1.lower()], int(d1))
    end = date(year, parse.MONTHS[m2.lower()], int(d2))
    return start, end


# --- ages & levels -----------------------------------------------------------

# Three level bands: "Level 1: Ages 9–11", "Level 2: Ages 12–14",
# "Level 3: Ages 15–19". The offering age range spans their floor and ceiling.
_LEVEL_BAND = re.compile(r"Level\s*\d\s*:?\s*Ages?\s*(\d{1,2})\s*[–-]\s*(\d{1,2})", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    bands = [(int(a), int(b)) for a, b in _LEVEL_BAND.findall(text)]
    if not bands:
        return None
    return {"min": min(a for a, _ in bands), "max": max(b for _, b in bands)}


def _levels(text: str) -> list[Level]:
    """Map the three age-banded levels to training levels.

    The youngest band (from ~9) is a beginner intake, the oldest (to 19) a
    pre-professional track (the program markets competition/audition prep), and
    anything between is intermediate.
    """
    bands = [(int(a), int(b)) for a, b in _LEVEL_BAND.findall(text)]
    levels: list[Level] = []
    for low, high in bands:
        if low <= 11:
            lvl: Level = "beginner"
        elif high >= 15:
            lvl = "pre-professional"
        else:
            lvl = "intermediate"
        if lvl not in levels:
            levels.append(lvl)
    return levels


# --- genres ------------------------------------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet technique", "classical", "male technique")),
    ("pointe", ("pointe",)),
    ("repertoire", ("repertoire", "variations")),
    ("contemporary", ("contemporary",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- prices ------------------------------------------------------------------

# "Program Tuition: 2000" / "Registration Fee: 150 (non refundable)".
_TUITION = re.compile(r"Program Tuition:\s*\$?\s*([\d,]+)", re.IGNORECASE)
_REGISTRATION = re.compile(r"Registration Fee:\s*\$?\s*([\d,]+)", re.IGNORECASE)
# "Private Room + Meals (12 nights): $1,600" / "Shared Room + Meals (12 nights): $1,150".
_ROOM = re.compile(
    r"(Private|Shared) Room \+ Meals \((\d+) nights?\):\s*\$\s*([\d,]+)", re.IGNORECASE
)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []

    if m := _TUITION.search(text):
        if (amount := parse.parse_amount(m.group(1))) is not None:
            prices.append(
                Price(amount=amount, currency="USD", label="Program Tuition", includes=["tuition"])
            )
    if m := _REGISTRATION.search(text):
        if (amount := parse.parse_amount(m.group(1))) is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="USD",
                    label="Registration Fee",
                    notes="Non-refundable.",
                )
            )
    # Optional UNLV room-and-board packages — each accommodation + meals.
    for kind, nights, raw in _ROOM.findall(text):
        if (amount := parse.parse_amount(raw)) is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="USD",
                    label=f"{kind.title()} Room + Meals",
                    includes=["accommodation", "meals"],
                    notes=f"Optional UNLV housing package ({nights} nights).",
                )
            )
    return prices


# --- application -------------------------------------------------------------

# "Due to high demand, all registrations closed … wait list" — application closed,
# the edition itself is unaffected (kept as scheduled).
_CLOSED = re.compile(
    r"all registrations? closed|automatically placed on the wait list", re.IGNORECASE
)

_APPLY_NOTE = (
    "Registration is closed; new applicants join a waiting list. Admission is by "
    "video audition (submit a YouTube/Vimeo audition video link)."
)


def _status(text: str):
    return "closed" if _CLOSED.search(text) else None


def _application_note(text: str) -> str | None:
    return _APPLY_NOTE if _CLOSED.search(text) else None


def _requirements(text: str):
    """Admission is by video audition — the audition form requests a YouTube/Vimeo
    video link — so the requirement is an open-brief (unspecific) video.
    """
    if "wait list" in text.lower() or "registration" in text.lower():
        return [
            VideoReq(
                specificity="unspecific",
                description=(
                    "Admission is by video audition: submit a YouTube or Vimeo "
                    "audition video link via the program's audition form."
                ),
            )
        ]
    return []
