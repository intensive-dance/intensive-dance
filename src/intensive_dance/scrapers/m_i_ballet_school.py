"""Munich International Ballet School (München, DE) — its Ballet Summer Intensive.

API FIRST: none. The school runs two Hostinger Website Builder sites. The public
`.de` site (`mi-ballet-school.de`) only teases "Summer Workshop 2026" as a bare
heading with no dates/fees and links out to the `.net` site for the real thing;
the `.net` site (`mi-ballet-school.net`) is a single page that holds the full
Summer Intensive (dates, fees, faculty, prerequisites, registration form). The
builder embeds the body in an HTML-encoded state blob, but it is fully
server-rendered into the static markup — selectolax reads the DOM text directly,
no JS render or fetch proxy needed. Note: the page `<title>` and JSON-LD carry
stale 2025 metadata; the live content is in the HTML body as confirmed 2026 dates.

DISCOVERY: one `Offering` — the "Ballet Summer Intensive – Preparation for the
Company Entrance". The page advertises four consecutive one-week sessions, each
led by a different guest company director, that a dancer may "follow one or more
weeks" of under one shared fee table and one (open) prerequisite. So we emit a
single Offering with the four weeks as `schedule.sessions`, season-keyed from the
year on the registration form's date checkboxes (the prose week ranges omit it).

WHAT THE PAGE GIVES US (verified live 2026-06):
  - DATES: four German "27. Juli – 1. August" week ranges (year only on the
    `dd.mm.yyyy` registration checkboxes, e.g. "27.7.2026").
  - TEACHERS: each week names a guest director (Pokorný/Pilsen, Barankiewicz/
    Prague, Petrov/Thüringer Staatsballett, Looris/Estonian National Ballet),
    tied to that week — confirmed 2026 faculty, so emitted with affiliations.
  - PRICES in EUR: 1 day 123€ · 6 days in a row 680€ · 12 days in a row 1.290€.
  - REQUIREMENTS: the "Prerequisites" section states "There are no restrictions
    on participation, everyone can take part regardless of their dance
    experience." — explicitly nothing required, so `[NoneReq]` (not `[]`).
  - AGES: none stated for the intensive (the 3–15 band on the `.de` site is the
    children's term courses, a different program), so `age_range` is omitted.

WHAT THIS SCRAPER EXERCISES: multi-session `Schedule`, German date parsing, a
multi-`Price` fee table, named `Teacher`s with `Affiliation`s, and an explicit
`NoneReq` (the "open to all, no audition" branch). Verified live 2026-06-05.
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
    Location,
    NoneReq,
    Offering,
    Organization,
    Price,
    PriceInclude,
    Requirement,
    Schedule,
    Session,
    Source,
    Teacher,
    now_utc,
)

# The public .de site only teases the intensive; the full page lives on .net.
PAGE = "https://mi-ballet-school.net/"
REGISTER_URL = f"{PAGE}#registersummer"

ORG = Organization(
    name="Munich International Ballet School",
    slug="m-i-ballet-school",
    country="DE",
    city="Munich",
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

    year = _year(text)
    sessions = _sessions(text, year)
    if not sessions:
        return None  # no dated weeks announced
    dated = [s for s in sessions if s.start and s.end]
    if not dated:
        return None
    start = min(s.start for s in dated if s.start)
    end = max(s.end for s in dated if s.end)
    season = str(end.year)

    return Offering(
        id=f"m-i-ballet-school/summer-intensive-{season}",
        source=Source(provider="m-i-ballet-school", url=PAGE, scrapedAt=now_utc()),
        title=f"Ballet Summer Intensive {season}",
        genres=_genres(text),
        organization=ORG,
        location=Location(venue="Marsstraße 40", city="Munich", country="DE"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Berlin",
            sessions=sessions,
        ),
        teachers=_teachers(text),
        prices=_prices(text),
        application=Application(
            url=REGISTER_URL,
            requirements=_requirements(text),
            notes=_prereq_note(text),
        ),
    )


# --- German dates -------------------------------------------------------------
#
# The page is German, so the month names are this scraper's own (only juli/august
# appear, but the full map keeps the regex honest if the school shifts a week).

_MONTHS = {
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}
_MONTHALT = parse.months_alt(_MONTHS)

# Prose week range, e.g. "27. Juli – 1. August: Jiri Pokorny (Direktor des …)".
# The trailing director name (to the next bracketed clause) labels the week.
_WEEK = re.compile(
    r"(\d{1,2})\.\s*(" + _MONTHALT + r")\s*[–-]\s*"
    r"(\d{1,2})\.\s*(" + _MONTHALT + r")\s*:\s*"
    r"([^(]+?)\s*\(([^)]*)\)",
    re.IGNORECASE,
)
# The registration checkboxes carry the year the prose ranges omit ("27.7.2026").
_NUM_DATE = re.compile(r"\b\d{1,2}\.\d{1,2}\.(20\d\d)\b")


def _year(text: str) -> int | None:
    match = _NUM_DATE.search(text)
    return int(match.group(1)) if match else None


def _sessions(text: str, year: int | None) -> list[Session]:
    """The four guest-director weeks, in source order, deduped by date range.

    The prose ranges appear several times (heading list + form selectors); we
    keep the first occurrence of each distinct week.
    """
    sessions: list[Session] = []
    seen: set[tuple[int, int, int, int]] = set()
    for m in _WEEK.finditer(text):
        d1, mon1, d2, mon2, director, org = m.groups()
        key = (int(d1), _MONTHS[mon1.lower()], int(d2), _MONTHS[mon2.lower()])
        if key in seen:
            continue
        seen.add(key)
        start = end = None
        if year is not None:
            start = date(year, _MONTHS[mon1.lower()], int(d1))
            end = date(year, _MONTHS[mon2.lower()], int(d2))
        label = f"{parse.clean(director)} ({parse.clean(org)})"
        sessions.append(Session(label=label, start=start, end=end))
    return sessions


# --- teachers: each week's named guest director -------------------------------


def _teachers(text: str) -> list[Teacher]:
    teachers: list[Teacher] = []
    seen: set[str] = set()
    for m in _WEEK.finditer(text):
        name = parse.clean(m.group(5))
        org = parse.clean(m.group(6))
        if name in seen:
            continue
        seen.add(name)
        teachers.append(
            Teacher(
                name=name,
                role="Guest director (weekly)",
                affiliations=[Affiliation(organization=_strip_director(org), current=True)],
            )
        )
    return teachers


# "Direktor des J.K. TyL Theatre Pilsen" → "J.K. TyL Theatre Pilsen".
_DIRECTOR_OF = re.compile(r"^Direktor\s+des\s+", re.IGNORECASE)


def _strip_director(org: str) -> str:
    return parse.clean(_DIRECTOR_OF.sub("", org))


# --- prices: "1 day 123€", "6 days in a row 680€", "12 days in a row 1.290€" ---

_PRICE = re.compile(r"(1 day|\d+\s*days?\s+in a row)\s+(\d[\d.,]*)\s*€", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    includes: list[PriceInclude] = ["tuition"]
    for m in _PRICE.finditer(text):
        amount = parse.parse_amount(m.group(2))
        if amount is None:
            continue
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=parse.clean(m.group(1)),
                includes=includes,
            )
        )
    return prices


# --- genres -------------------------------------------------------------------
#
# The page has no curriculum/class listing — only director bios that mention
# "classical and contemporary repertoire" in career descriptions. Matching the
# full page text against "contemporary"/"repertoire" keywords would derive genres
# from bio prose rather than a syllabus. Since the course content is not stated
# beyond "Ballet Summer Intensive", the defensible default is ["classical"].

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet", "ballett")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- requirements: prerequisites are explicitly open to all -------------------

_OPEN_TO_ALL = re.compile(r"no restrictions on participation|everyone can take part", re.IGNORECASE)


def _requirements(text: str) -> list[Requirement]:
    # The page states participation is open regardless of experience — an
    # explicit "nothing required" ([NoneReq]), not an unknown ([]).
    return [NoneReq()] if _OPEN_TO_ALL.search(text) else []


def _prereq_note(text: str) -> str | None:
    m = re.search(
        r"There are no restrictions on participation[^.]*\.",
        text,
        re.IGNORECASE,
    )
    return parse.clean(m.group(0)) if m else None
