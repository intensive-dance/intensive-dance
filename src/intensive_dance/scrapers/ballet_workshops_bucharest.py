"""Ballet Workshops Bucharest (Casa de Balet) — its Summer Camp, Winter Camp and
guest Masterclasses, Bucharest (RO).

This is Casa de Balet's open-enrolment short-course brand; the standalone
`casa-de-balet` provider seed was the **same organisation** (its school site
`casadebalet.ro`) and was collapsed into this row to avoid a double-build (the
ART-of precedent in AGENTS.md — one scraper, the redundant seed removed).

API FIRST: none usable. The site (`balletworkshops.com`) is a **Wix** build, but —
like the other Wix providers in the register — it server-renders the full text of
its landing pages into the static HTML (dates, ages, fee, faculty all present), so
a plain fetch is enough; no JS render or proxy escalation was needed (verified live
2026-06). (The `/programbsc` *curriculum* sub-pages, by contrast, hydrate via XHR
and are empty in the static HTML — so we read the landing pages, not those.) The
Wix markup peppers the text with **zero-width spaces** (gluing tokens together),
stripped up front.

DISCOVERY: one `Offering` per dated edition, across three landing pages, each
season-keyed from its parsed year so the id rolls forward as the page advances:
  - `/balletsummercamp` — the Ballet Summer Camp ("Edition VII | 9-19 July 2026"),
    splitting enrolment into three age groups (9-11, 12-14, 15+) that share one
    curriculum, fee and dates → one `Session` each (the open-topped "15+" group
    leaves the upper bound null).
  - `/balletwintercamp` — the Ballet Winter Camp ("2-6 January 2026"); a past edition
    is kept (IDR-24, no date filtering). Its deadline year rolls back across the
    year boundary (a "DECEMBER 22" deadline for a January camp → the prior year).
  - `/masterclass` — an UPCOMING list of one-off guest masterclasses; we emit one
    Offering per listed guest (name + class title + its own dates), the guest as the
    single `Teacher`, genre from the class title.

WHAT THE PAGES GIVE US (verified live 2026-06):
  - DATES: "9-19 July 2026" / "2-6 January 2026" — single-month day ranges, shared
    trailing year; masterclasses add a single-day form ("21-22 March 2026").
  - AGES: "aged 9 to 18" / "aged between 9 and 18"; the summer groups are listed
    ("9-11 years, 12-14 years, 15+ years"), the winter landing states only the band.
  - GENRES: from the Classes list / class title — classical, pointe, repertoire,
    contemporary.
  - PRICES in EUR: €1100 "Full workshop and Final Showcase Gala" (tuition + the gala
    performance); €600 "ALL LEVELS" for winter. Accommodation is offered as separate
    assistance (breakfast included) but is not part of the fee, so it stays out of
    `includes` and is kept as a schedule note. Masterclasses publish no fee.
  - DEADLINE: "The registration deadline is …" — entry is via an online registration
    form; the camps state no photo/video audition brief, so `requirements` stays `[]`.
  - TEACHERS: a structured roster (name + role) in each camp page's TEACHERS block
    (Wix `.info-member` repeater). The homepage's *legacy* roll of past guests is "had
    been invited in our programs" — not a confirmed roster — so it is not claimed.
"""

from __future__ import annotations

import re
import unicodedata
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
    PriceInclude,
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
WINTER_PAGE = f"{BASE}/balletwintercamp"
MASTERCLASS_PAGE = f"{BASE}/masterclass"
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
    offerings: list[Offering] = []
    summer = client.get(PAGE)
    summer.raise_for_status()
    if (offering := _build_offering(summer.text)) is not None:
        offerings.append(offering)
    winter = client.get(WINTER_PAGE)
    winter.raise_for_status()
    if (offering := _build_winter(winter.text)) is not None:
        offerings.append(offering)
    masterclass = client.get(MASTERCLASS_PAGE)
    masterclass.raise_for_status()
    offerings.extend(_build_masterclasses(masterclass.text))
    return offerings


def _page_text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    raw = tree.body.text(separator=" ") if tree.body else ""
    return parse.clean(raw.translate(_ZERO_WIDTH))


def _build_offering(html: str) -> Offering | None:
    tree = HTMLParser(html)
    teachers = _teachers(tree)
    text = _page_text(html)

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


def _build_winter(html: str) -> Offering | None:
    teachers = _teachers(HTMLParser(html))
    text = _page_text(html)

    start, end = _date_range(text)
    anchor = end or start
    if anchor is None:
        return None  # no dated edition parseable
    season = str(anchor.year)

    return Offering(
        id=f"ballet-workshops-bucharest/winter-camp-{season}",
        source=Source(provider="ballet-workshops-bucharest", url=WINTER_PAGE, scrapedAt=now_utc()),
        title=f"Ballet Winter Camp {season}",
        genres=_winter_genres(text),
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
            deadline=_deadline_rollback(text, start),
            url=WINTER_PAGE,
            notes=_apply_note(text),
        ),
    )


def _build_masterclasses(html: str) -> list[Offering]:
    """One Offering per guest in the page's UPCOMING masterclass list.

    The block runs `<name> <class title> <dates>` per guest; we walk it date-first,
    taking the text since the previous date as `<name> <title>` (the guest name is
    the leading two words, the rest the class title). Thin by design — these pages
    publish only the guest, the discipline and the dates.
    """
    segment = _upcoming_segment(_page_text(html))
    offerings: list[Offering] = []
    seen: set[str] = set()
    cursor = 0
    for match in _MC_DATE.finditer(segment):
        chunk = parse.clean(segment[cursor : match.start()])
        cursor = match.end()
        if "class" not in chunk.lower():
            continue
        words = chunk.split()
        if len(words) < 3:
            continue
        name = " ".join(words[:2])
        title = " ".join(words[2:])
        start, end = _mc_dates(match)
        season = str(start.year)
        slug = f"masterclass-{_slugify(name)}-{season}"
        if slug in seen:
            continue
        seen.add(slug)
        offerings.append(
            Offering(
                id=f"ballet-workshops-bucharest/{slug}",
                source=Source(
                    provider="ballet-workshops-bucharest", url=MASTERCLASS_PAGE, scrapedAt=now_utc()
                ),
                title=f"{name} — {title}",
                genres=parse.match_genres(title, _GENRE_KEYWORDS, default=["classical"]),
                organization=ORG,
                location=Location(city="Bucharest", country="RO"),
                schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Bucharest"),
                teachers=[Teacher(name=name, role="Masterclass teacher")],
                application=Application(url=MASTERCLASS_PAGE),
            )
        )
    return offerings


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

_AGE = re.compile(r"aged?\s+(?:between\s+)?(\d{1,2})\s+(?:to|-|–|and)\s+(\d{1,2})", re.IGNORECASE)
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


# The winter landing has no Classes list — only the prose "studies of classical
# ballet, duet, classical repertoire, contemporary dance". Scope genre-matching to
# that clause so a teacher's bio ("Creator of 4 Pointe") can't leak a `pointe` the
# winter programme doesn't teach (the curriculum-scoping trap in AGENTS.md).
_WINTER_CURRICULUM = re.compile(r"studies of\s+(.+?)(?:\s+and more\b|\.)", re.IGNORECASE)


def _winter_genres(text: str) -> list[Genre]:
    m = _WINTER_CURRICULUM.search(text)
    scope = m.group(1) if m else text
    return parse.match_genres(scope, _GENRE_KEYWORDS, default=["classical"])


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
    label = re.split(r"\bThe\b|\bDiscounts\b|\bHOW\b|\bFull payment\b", label)[0].strip()
    if not label:  # winter states the band before the figure ("ALL LEVELS €600")
        label = "All levels" if "ALL LEVELS" in text.upper() else "Tuition"
    # The gala/showcase is the included performance; absent it, the fee is tuition only.
    includes: list[PriceInclude] = ["tuition"]
    if re.search(r"gala|showcase|performance", text, re.IGNORECASE):
        includes.append("performance")
    return [Price(amount=amount, currency="EUR", label=label, includes=includes)]


# --- deadline + application note ----------------------------------------------

_DEADLINE = re.compile(
    r"registration deadline is\s+(" + parse.MONTHALT + r")\s+(\d{1,2})", re.IGNORECASE
)


def _deadline(text: str, year: int) -> date | None:
    m = _DEADLINE.search(text)
    if not m:
        return None
    return date(year, parse.MONTHS[m.group(1).lower()], int(m.group(2)))


def _deadline_rollback(text: str, start: date | None) -> date | None:
    """A bare "Month Day" deadline with no year, resolved against the camp: it
    rolls back a year when its month comes later in the calendar than the camp's
    (a December deadline for a January camp belongs to the prior year)."""
    if start is None:
        return None
    m = _DEADLINE.search(text)
    if not m:
        return None
    month = parse.MONTHS[m.group(1).lower()]
    year = start.year if month <= start.month else start.year - 1
    return date(year, month, int(m.group(2)))


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


# --- masterclasses: the UPCOMING guest list -----------------------------------

# A guest's dates: a day or day-range ("06-08 March 2026" / "21-22 March 2026"),
# one month with a shared trailing year.
_MC_DATE = re.compile(
    r"(\d{1,2})(?:\s*[-–—]\s*(\d{1,2}))?\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _upcoming_segment(text: str) -> str:
    """Just the UPCOMING list — bounded so a stray date elsewhere on the page
    (a footer carousel, a past-event roll) can't be read as a masterclass."""
    m = re.search(r"\bUPCOMING\b", text, re.IGNORECASE)
    if not m:
        return ""
    tail = text[m.end() :]
    tail = re.split(r"Soon more guests|\bTBA\b", tail, maxsplit=1)[0]
    return tail[:600]


def _mc_dates(match: re.Match) -> tuple[date, date]:
    d1, d2, month, year = match.groups()
    mon, y = parse.MONTHS[month.lower()], int(year)
    start = date(y, mon, int(d1))
    end = date(y, mon, int(d2)) if d2 else start
    return start, end


def _slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
