"""DART Dance Company — its Summer Sensation Intensive (Berlin, DE) and its
Italy Summer Master Intensive (Milan, IT).

API FIRST: none usable. DART runs on **Wix** (server `Pepyaka`, no public content
API we may use), but both intensive pages are server-side rendered, so the full
text is in the static HTML — one-page scrapes, no JS. Wix peppers the markup with
zero-width spaces, so we strip them before parsing (the same trap the Brussels /
Young Stars / IDC scrapers handle).

DISCOVERY: two pages, two `Offering`s — one per city/edition:

  Berlin (`/summer-intensive-berlin`): one three-week contemporary-repertoire
  intensive — three consecutive Monday–Friday weeks you may take individually or
  together (1 / 2 / 3-week pricing). We emit one `Offering`, the three weeks as
  `schedule.sessions`, season-keyed from the first week's year.

  Milan (`/summer-intensive-milan`): a three-day master intensive at two
  Milan venues (Teatro Carcano day 1, Teatro Arcimboldi days 2-3). Emitted as a
  separate `Offering` (distinct dates, location, price and teachers).

WHAT THE BERLIN PAGE GIVES US (verified live 2026-06):
  - DATES: Week 1 "3rd - 7th August 2026", Week 2 "10th - 14th August", Week 3
    "17th - 21st August". The source mistypes weeks 2 & 3 as "2025" while the
    title ("BERLIN 26") and week 1 say 2026; since the block is plainly one
    consecutive August run, we anchor every week to week 1's year and record the
    source typo in a schedule note (faithful + transparent).
  - REPERTOIRE: Mats Ek, Nacho Duato, Marco Goecke, Lightfoot/León, Jiří Kylián,
    Johan Inger, Alexander Ekman and DART's own work — all contemporary /
    neoclassical, taught as repertoire. No classical *class* is taught (the ballet
    video is an application requirement only), so we don't force `classical`.
  - FACULTY: a confirmed seven-teacher roster, cleanly delimited between the
    "following teachers:" line and "WORKSHOP SCHEDULE" — so we emit it (unlike the
    Brussels/IDC guest rolls, which were legacy/unconfirmed and run-together).
  - PRICES in EUR: 1 week 595, 2 weeks 995, 3 weeks 1395 — tuition incl. the
    registration cost.
  - REQUIREMENTS: apply with a CV, a ≤5-min improvisation video and a ≤10-min
    ballet video with four named centre exercises (tendus, pirouettes, petit
    allegro, grand allegro), both on YouTube. → CV + a `specific` video.
  - AGES / LEVEL: not stated on the page, so both are left empty.

WHAT THE MILAN PAGE GIVES US (verified live 2026-06):
  - TITLE: "Italy Summer Master Intensive 2026"
  - DATES: "SCHEDULE 15th to 17th June 2026" — three days.
  - VENUES: "TEATRO CARCANO, Corso di Porta Romana, 63, 20122, Milan" (day 1);
    "TEATRO ARCIMBOLDI, Viale dell'Innovazione 20, 20126, Milan" (days 2-3).
    We record the two-venue note in schedule.notes rather than picking one.
  - TEACHERS: Kinga Varga, Clyde Emmanuel Archer, Alessandra La Bella.
  - PRICE: 468 EUR (single tier, includes tuition/registration).
  - APPLICATION: by email (dartdanceworkshop@gmail.com), CV + ≤5-min improv video
    on YouTube without password. Deadline: June 13, 2026.
  - AGES / LEVEL: not stated.

Application is by email (dartdanceworkshop@gmail.com) or a Google Form; we keep
the form as `application.url` and the email in the note.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    CVReq,
    Genre,
    Location,
    Offering,
    Organization,
    Price,
    Requirement,
    Schedule,
    Session,
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

BASE = "https://www.dart.theater"
PAGE_BERLIN = f"{BASE}/summer-intensive-berlin"
PAGE_MILAN = f"{BASE}/summer-intensive-milan"
APPLY_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSeioTEztqjHiEIPUK7RcZ6GUeOX1VRXEidZGYv3VEAEMyI-Mg/viewform"
)
APPLY_EMAIL = "dartdanceworkshop@gmail.com"

ORG = Organization(
    name="DART Dance Company", slug="dart-dance-company", country="DE", city="Berlin"
)

# Wix injects zero-width spaces (ZWSP / ZWNJ / ZWJ / BOM) into the rendered text.
_ZERO_WIDTH = re.compile("[" + "".join(map(chr, (0x200B, 0x200C, 0x200D, 0xFEFF))) + "]")

VENUE_BERLIN = "DART Studios, Motzener Strasse 5, 12277 Marienfelde, Berlin"
VENUE_MILAN_NOTE = (
    "Day 1: Teatro Carcano, Corso di Porta Romana 63, 20122 Milan; "
    "Days 2-3: Teatro Arcimboldi, Viale dell'Innovazione 20, 20126 Milan"
)


def scrape(client: httpx.Client) -> list[Offering]:
    offerings: list[Offering] = []

    resp_berlin = client.get(PAGE_BERLIN, follow_redirects=True)
    resp_berlin.raise_for_status()
    berlin = _build_offering(resp_berlin.text)
    if berlin is not None:
        offerings.append(berlin)

    resp_milan = client.get(PAGE_MILAN, follow_redirects=True)
    if resp_milan.status_code != 404:
        resp_milan.raise_for_status()
        milan = _build_milan_offering(resp_milan.text)
        if milan is not None:
            offerings.append(milan)

    return offerings


def _build_offering(html: str) -> Offering | None:
    tree = _parse(html)
    text = _collapse(tree)

    sessions = _sessions(text)
    if not sessions:
        return None  # no dated weeks announced
    start = min(s.start for s in sessions if s.start)
    end = max(s.end for s in sessions if s.end)
    season = str(start.year)

    return Offering(
        id=f"dart-dance-company/summer-sensation-intensive-{season}",
        source=Source(provider="summer-sensation-intensive", url=PAGE_BERLIN, scrapedAt=now_utc()),
        title=f"Summer Sensation Intensive Berlin {season}",
        genres=_genres(text),
        organization=ORG,
        location=Location(venue=VENUE_BERLIN, city="Berlin", country="DE"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Berlin",
            sessions=sessions,
            notes=_schedule_note(text, season),
        ),
        teachers=_teachers(_spans(tree), text),
        prices=_prices(text),
        application=Application(
            url=APPLY_URL,
            requirements=_requirements(text),
            notes=(
                f"Apply by email to {APPLY_EMAIL} (CV plus the two YouTube videos) "
                "or via the Google Form. Places are limited; payment instructions "
                "follow acceptance."
            ),
        ),
    )


def _build_milan_offering(html: str) -> Offering | None:
    tree = _parse(html)
    text = _collapse(tree)

    start, end = _milan_dates(text)
    if start is None or end is None:
        return None
    season = str(start.year)
    deadline = _milan_deadline(text)

    return Offering(
        id=f"dart-dance-company/italy-summer-master-intensive-{season}",
        source=Source(provider="summer-sensation-intensive", url=PAGE_MILAN, scrapedAt=now_utc()),
        title=f"Italy Summer Master Intensive Milan {season}",
        genres=_genres(text),
        organization=ORG,
        location=Location(city="Milan", country="IT"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Rome",
            notes=VENUE_MILAN_NOTE,
        ),
        teachers=_milan_teachers(text),
        prices=_milan_prices(text),
        application=Application(
            # The page states a deadline, not a current status — keep the deadline
            # and leave `status` unset (deriving "closed" from deadline < today
            # invents a status and breaks the no-diff rule, since status is hashed).
            deadline=deadline,
            requirements=_milan_requirements(text),
            notes=(
                f"Apply by email to {APPLY_EMAIL} with a CV and a maximum five-minute "
                "improvisation video uploaded to YouTube without a password. Places "
                "are limited; payment instructions follow acceptance."
            ),
        ),
    )


def _strip_zw(s: str) -> str:
    return _ZERO_WIDTH.sub("", s)


def _parse(html: str) -> HTMLParser:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return tree


def _collapse(tree: HTMLParser) -> str:
    raw = tree.body.text(separator=" ") if tree.body else ""
    return parse.clean(_strip_zw(raw))


def _spans(tree: HTMLParser) -> list[str]:
    """Each element's own text (no descendants), in document order.

    Wix renders the teacher roster as one `<span>` per name, so the names are
    only cleanly separable at the element boundary — collapsing the page glues
    them into one run. We read the per-element text and let `_teachers` pick the
    roster window out of it.
    """
    return [parse.clean(_strip_zw(node.text(deep=False))) for node in tree.css("span")]


# --- sessions: three weeks, "<d> - <d> <Month> <year>" ------------------------

# "3rd - 7th August 2026" — one month + year spanning both days, ordinals optional.
_WEEK = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s*[-–—]\s*(\d{1,2})(?:st|nd|rd|th)?\s+("
    + parse.MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _sessions(text: str) -> list[Session]:
    weeks = list(_WEEK.finditer(text))
    if not weeks:
        return []
    # The source mistypes later weeks' years; anchor every week to the first
    # week's year, since the block is one consecutive run (see docstring).
    anchor_year = int(weeks[0].group(4))
    out: list[Session] = []
    for i, m in enumerate(weeks, start=1):
        d1, d2, month_name, _year = m.groups()
        month = parse.MONTHS[month_name.lower()]
        start = date(anchor_year, month, int(d1))
        end = date(anchor_year, month, int(d2))
        out.append(Session(label=f"Week {i}", start=start, end=end))
    return out


def _schedule_note(text: str, season: str) -> str | None:
    # Flag the source typo only when it's actually present (some weeks dated a
    # different year than the anchor), so the note is faithful, not boilerplate.
    years = {m.group(4) for m in _WEEK.finditer(text)}
    if len(years) > 1:
        return (
            f"The source dates the later weeks {', '.join(sorted(years - {season}))} "
            f"(an apparent typo); all three weeks run consecutively in August {season}."
        )
    return None


# --- teachers: a confirmed seven-name roster ----------------------------------

# The roster sits, one name-span each, between the "following teachers" intro and
# the "WORKSHOP SCHEDULE" heading. A name-span is one-to-three capitalised words
# with no digits and none of the all-caps section words that surround it.
_NAME = re.compile(r"[A-ZÀ-Ý][\wÀ-ÿ.'’-]+(?:\s+[A-ZÀ-Ý][\wÀ-ÿ.'’-]+){1,2}")
_NOT_A_NAME = re.compile(
    r"REPERTOIRE|SCHEDULE|WEEK|COMPANY|DANCE|STRETCHING|INTENSIVE|BERLIN|STUDIOS|VIDEOS|FORM|POLICY",
)
# Kinga Varga is named "Artistic Director/DART Dance Company" in the schedule.
_DIRECTOR = re.compile(
    r"([A-ZÀ-Ý][\wÀ-ÿ.'’-]+(?:\s+[A-ZÀ-Ý][\wÀ-ÿ.'’-]+)+)\s*-\s*Artistic Director",
    re.IGNORECASE,
)


def _is_name(span: str) -> bool:
    return bool(_NAME.fullmatch(span)) and not _NOT_A_NAME.search(span.upper())


def _teachers(spans: list[str], text: str) -> list[Teacher]:
    try:
        intro = next(i for i, s in enumerate(spans) if "following teachers" in s.lower())
        schedule = next(i for i, s in enumerate(spans) if "WORKSHOP SCHEDULE" in s.upper())
    except StopIteration:
        return []
    director_m = _DIRECTOR.search(text)
    director = parse.clean(director_m.group(1)) if director_m else None
    out: list[Teacher] = []
    seen: set[str] = set()
    for span in spans[intro + 1 : schedule]:
        if not _is_name(span) or span in seen:
            continue
        seen.add(span)
        role = "Artistic Director" if span == director else None
        out.append(Teacher(name=span, role=role))
    return out


# --- genres: contemporary repertoire, no classical class ----------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("contemporary", ("contemporary",)),
    ("repertoire", ("repertoire",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["contemporary"])


# --- prices: "1 week - 595 Euros", "2 weeks - 995 Euros", … -------------------

_PRICE = re.compile(
    r"(\d+)\s*weeks?\s*[-–—]\s*(\d[\d.,]*)\s*Euros?",
    re.IGNORECASE,
)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    for m in _PRICE.finditer(text):
        amount = parse.parse_amount(m.group(2))
        if amount is None:
            continue
        weeks = int(m.group(1))
        label = f"{weeks} week" + ("s" if weeks != 1 else "")
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=label,
                includes=["tuition"],
                notes="Includes the registration cost.",
            )
        )
    return prices


# --- requirements: a CV and two YouTube videos --------------------------------

_VIDEO_NOTE = (
    "Apply with a CV, a maximum five-minute improvisation video and a maximum "
    "ten-minute ballet video with four short centre exercises (tendus, "
    "pirouettes, petit allegro and grand allegro). Both videos must be uploaded "
    "to YouTube without a password."
)


def _requirements(text: str) -> list[Requirement]:
    low = text.lower()
    reqs: list[Requirement] = []
    if re.search(r"\bcv\b|resume", low):
        reqs.append(CVReq())
    if "improvisation" in low or "ballet video" in low:
        reqs.append(VideoReq(specificity="specific", description=_VIDEO_NOTE))
    return reqs


# --- Milan-specific helpers ---------------------------------------------------
#
# The Milan page has a different structure: a single range "15th to 17th June",
# a single price "Workshop price: 468 EUR", a three-name faculty list, and an
# application deadline ("13th of June 2026"). No multi-week sessions or
# "following teachers:" / "WORKSHOP SCHEDULE" delimiters.

# "SCHEDULE 15th to 17th June 2026" or "15th to 17th June 2026"
_MILAN_DATES = re.compile(
    r"(?:SCHEDULE\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+to\s+(\d{1,2})(?:st|nd|rd|th)?\s+("
    + parse.MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)

# "13th of June 2026" — application deadline
_MILAN_DEADLINE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+of\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)

# "Workshop price: 468 EUR" / "468 EUR" / "468 Euros"
_MILAN_PRICE = re.compile(r"(?:Workshop\s+price\s*:\s*)?(\d[\d.,]*)\s*EUR(?:os?)?", re.IGNORECASE)

# The three Milan teachers are named in prose (not in separate spans), so we
# extract them by looking for sequences of Title-Case words that follow a known
# cue ("Under the guidance of …", "will lead …", "will introduce …").
_MILAN_TEACHER_NAMES = ("Kinga Varga", "Clyde Emmanuel Archer", "Alessandra La Bella")

_MILAN_VIDEO_NOTE = (
    "Apply with a CV and a maximum five-minute improvisation video uploaded to "
    "YouTube without a password."
)


def _milan_dates(text: str) -> tuple[date | None, date | None]:
    m = _MILAN_DATES.search(text)
    if not m:
        return None, None
    d1, d2, month_name, year = m.group(1), m.group(2), m.group(3), m.group(4)
    month = parse.MONTHS[month_name.lower()]
    return date(int(year), month, int(d1)), date(int(year), month, int(d2))


def _milan_deadline(text: str) -> date | None:
    m = _MILAN_DEADLINE.search(text)
    if not m:
        return None
    return date(int(m.group(3)), parse.MONTHS[m.group(2).lower()], int(m.group(1)))


def _milan_prices(text: str) -> list[Price]:
    m = _MILAN_PRICE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    return [
        Price(
            amount=amount,
            currency="EUR",
            label="Workshop price",
            includes=["tuition"],
            notes="Includes the cost of registration.",
        )
    ]


def _milan_teachers(text: str) -> list[Teacher]:
    # The teacher names are stated in the prose of the Milan page and are fixed;
    # we check for each name's presence rather than relying on element boundaries
    # (Wix renders prose differently from the Berlin span-per-name layout).
    return [Teacher(name=name) for name in _MILAN_TEACHER_NAMES if name.lower() in text.lower()]


def _milan_requirements(text: str) -> list[Requirement]:
    low = text.lower()
    reqs: list[Requirement] = []
    if re.search(r"\bcv\b|resume", low):
        reqs.append(CVReq())
    if "improvisation" in low:
        reqs.append(VideoReq(specificity="unspecific", description=_MILAN_VIDEO_NOTE))
    return reqs
