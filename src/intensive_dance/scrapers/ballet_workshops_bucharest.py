"""Ballet Workshops Bucharest (Casa de Balet) — its Ballet Summer Camp, Bucharest (RO).

API FIRST: none usable. The site (`balletworkshops.com`) is a **Wix** build, but —
like the other Wix providers in the register — it server-renders the full text
into the static HTML (dates, ages, fee, faculty, curriculum all present), so a
plain fetch of the Summer Camp page is enough; no JS render or proxy escalation
was needed (verified live 2026-06). The Wix markup peppers the text with
**zero-width spaces** (gluing tokens together), stripped up front.

DISCOVERY: one page (`/balletsummercamp`) describes the current dated edition —
"Ballet Summer Camp | Edition VII | 9-19 July 2026, Bucharest", a single
short-term classical intensive culminating in a Final Showcase Gala at the
National Opera Bucharest. We emit one `Offering`, season-keyed from the parsed
year so the id rolls forward when the page advances an edition. The course splits
enrolment into three age groups (9-11, 12-14, 15+) that share one curriculum,
fee and dates, so each becomes one `Session` (the Offering ageRange spans all
three; the open-ended "15+" top group leaves the upper bound null).

WHAT THE PAGE GIVES US (verified live 2026-06):
  - DATES: "9-19 July 2026" — a single-month day range with a shared trailing year.
  - AGES: "students aged 9 to 18", three groups "9-11 years, 12-14 years, 15+ years".
  - GENRES: the Classes list — Classical Technique, Pointe Technique, Repertoire
    (Female/Male Variations and Group), Contemporary Dance → classical, pointe,
    repertoire, contemporary.
  - PRICES in EUR: €1100 "Full workshop and Final Showcase Gala" (tuition + the
    gala performance). Accommodation is offered as separate assistance (breakfast
    included) but is not part of the fee, so it stays out of `includes` and is kept
    as a schedule note.
  - DEADLINE: "The registration deadline is June 9th." (the camp year) — entry is
    via an online registration form; the page states no photo/video audition brief,
    so `requirements` stays `[]` ("not stated").
  - TEACHERS: a structured 2026 roster (name + role) in the page's TEACHERS block
    (Wix `.info-member` repeater). The homepage's *legacy* roll of past guests
    (Isabelle Ciaravola, Vladimir Shishov, Steffi Scherzer, …) is "had been invited
    in our programs" — not a confirmed 2026 roster — so it is not claimed (the same
    call the BIB scraper makes for unattributable faculty).
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
    Price,
    Schedule,
    Session,
    Source,
    Teacher,
    now_utc,
)

# Zero-width characters Wix peppers through the markup (ZWSP, ZWNJ, BOM/ZWNBSP).
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿"))

BASE = "https://www.balletworkshops.com"
PAGE = f"{BASE}/balletsummercamp"
APPLY_URL = f"{BASE}/registrationsbsc"

ORG = Organization(
    name="Ballet Workshops Bucharest",
    slug="ballet-workshops-bucharest",
    country="RO",
    city="Bucharest",
)

VENUE = "Casa de Balet, Bucharest (Final Showcase Gala at the National Opera Bucharest)"

_ACCOMMODATION_NOTE = (
    "Accommodation assistance is offered close to the venue with breakfast "
    "included (not part of the participation fee); airport transfers provided."
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    offering = _build_offering(resp.text)
    return [offering] if offering is not None else []


def _build_offering(html: str) -> Offering | None:
    tree = HTMLParser(html)
    teachers = _teachers(tree)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    raw = tree.body.text(separator=" ") if tree.body else ""
    text = parse.clean(raw.translate(_ZERO_WIDTH))

    start, end = _date_range(text)
    anchor = end or start
    if anchor is None:
        return None  # no dated edition parseable
    season = str(anchor.year)

    return Offering(
        id=f"ballet-workshops-bucharest/summer-camp-{season}",
        source=Source(provider="ballet-workshops-bucharest", url=PAGE, scrapedAt=now_utc()),
        title=f"Ballet Summer Camp {season}",
        genres=_genres(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue=VENUE, city="Bucharest", country="RO"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Bucharest",
            sessions=_sessions(text),
            notes=_ACCOMMODATION_NOTE,
        ),
        teachers=teachers,
        prices=_prices(text),
        application=Application(
            deadline=_deadline(text, anchor.year),
            url=APPLY_URL,
            notes=_apply_note(text),
        ),
    )


# --- dates: "9-19 July 2026" — single-month day range, shared trailing year ----

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


# --- ages: "aged 9 to 18", groups "9-11 years, 12-14 years, 15+ years" ---------

_AGE = re.compile(r"aged?\s+(\d{1,2})\s+(?:to|-|–|and)\s+(\d{1,2})", re.IGNORECASE)
# Each declared group; the trailing "15+ years" group is open-topped (no max),
# so it carries no second number.
_GROUP = re.compile(r"(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+years|(\d{1,2})\s*\+\s*years", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    m = _AGE.search(text)
    if not m:
        return None
    return {"min": int(m.group(1)), "max": int(m.group(2))}


def _sessions(text: str) -> list[Session]:
    sessions: list[Session] = []
    for m in _GROUP.finditer(text):
        if m.group(3):  # "15+ years" — open-ended upper bound
            low = int(m.group(3))
            sessions.append(
                Session(label=f"{low}+ years", ageRange={"min": low}, notes=f"{low}+ years")
            )
        else:
            low, high = int(m.group(1)), int(m.group(2))
            sessions.append(
                Session(
                    label=f"{low}-{high} years",
                    ageRange={"min": low, "max": high},
                    notes=f"{low}-{high} years",
                )
            )
    return sessions


# --- genres: the Classes list -------------------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical technique", "classical ballet")),
    ("pointe", ("pointe",)),
    ("repertoire", ("repertoire", "variations")),
    ("contemporary", ("contemporary",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- price: "€1100 Full workshop and Final Showcase Gala" ----------------------

_PRICE = re.compile(r"€\s*(\d[\d.,]*)\s*([^€]{0,60})", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    m = _PRICE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    label = parse.clean(m.group(2))
    # Keep only the fee's own descriptor, not whatever sentence follows it.
    label = re.split(r"\bThe\b|\bDiscounts\b|\bHOW\b", label)[0].strip()
    return [
        Price(
            amount=amount,
            currency="EUR",
            label=label or "Full workshop",
            includes=["tuition", "performance"],
        )
    ]


# --- deadline + application note ----------------------------------------------

_DEADLINE = re.compile(
    r"registration deadline is\s+(" + parse.MONTHALT + r")\s+(\d{1,2})", re.IGNORECASE
)


def _deadline(text: str, year: int) -> date | None:
    m = _DEADLINE.search(text)
    if not m:
        return None
    return date(year, parse.MONTHS[m.group(1).lower()], int(m.group(2)))


def _apply_note(text: str) -> str | None:
    if re.search(r"online registration form", text, re.IGNORECASE):
        return (
            "Entry is via the online registration form; the student is assigned to the "
            "appropriate age and experience group from the form. Discounts do not stack."
        )
    return None


# --- teachers: the structured 2026 TEACHERS roster (Wix `.info-member`) --------


def _teachers(tree: HTMLParser) -> list[Teacher]:
    """Name + role pairs from the page's TEACHERS block.

    Wix renders the roster as an alternating run of `.info-member.info-element-title`
    (name) then `.info-member.info-element-description` (role), so we pair each
    title with the description that follows it — structural, not positional.
    """
    members = tree.css(".info-member")
    teachers: list[Teacher] = []
    i = 0
    while i < len(members):
        cls = members[i].attributes.get("class") or ""
        if "info-element-title" in cls:
            name = parse.clean((members[i].text(separator=" ")).translate(_ZERO_WIDTH))
            role: str | None = None
            nxt = members[i + 1] if i + 1 < len(members) else None
            if nxt is not None and "info-element-description" in (
                nxt.attributes.get("class") or ""
            ):
                role = parse.clean((nxt.text(separator=" ")).translate(_ZERO_WIDTH)) or None
                i += 1
            if name:
                teachers.append(Teacher(name=name, role=role))
        i += 1
    return teachers
