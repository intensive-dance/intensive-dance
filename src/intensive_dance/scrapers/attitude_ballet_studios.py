"""Attitude Ballet Studios Vienna — its public **Vienna Ballet Intensive**.

API FIRST: WordPress (`/wp-json/` is 200, NAME "Attitude Ballet Studios
Vienna"), but the REST `content.rendered` for the intensive page (id 3929) is
**empty** — the page is built with **Elementor**, which renders nothing into the
REST body and exposes only the page shell. So this is an HTML scrape of the
rendered page (the ABT trap: WP present, API body useless). The host runs
ModSecurity that 406s a bare `Mozilla/5.0` UA, but our scraper UA (and the proxy)
are *not* blocked — a plain `make_client()` fetch returns the full server-rendered
markup, so **no fetch proxy is needed**. The page peppers the markup with
zero-width spaces (the Elementor/Wix-style trap shared with `idc_berlin` /
`brussels_international_ballet`), so we strip them before parsing.

DISCOVERY: one page (`/vienna-ballet-intensive/`) describes the current edition —
a single two-week summer ballet intensive in Vienna. We emit **one Offering**,
season-keyed from the parsed dates so the id rolls forward when the page advances
a year. A separate `/vienna-ballet-camp/` page is a distinct product and is not
scraped here.

WHAT THE PAGE GIVES US (verified live 2026-06-08):
  - DATES: "13 - 25 July 2026" — two weeks; the season is taken from the parsed
    year (and cross-checked against the title stamp "… Intensive 2026").
  - AGES: "Students 12+ years old" — open-ended upper bound, so only the lower
    bound; an exception for 11-year-olds "with excellent technique" is kept as a
    schedule note, not folded into the bound.
  - LEVEL: "Ballet professionals and pre-professionals are welcome" →
    `professional` + `pre-professional`.
  - GENRES from the **curriculum list** (not loose prose — the SAB trap):
    Ballet Study Class, Variations, Pointes, Modern and Contemporary, Character
    Dance, Neoclassical Choreography → classical/repertoire/pointe/contemporary/
    character/neoclassical.
  - PRICES in EUR: two tuition tiers — €1,350 (2 weeks, full program) and €750
    (1 week) — plus a €200 non-refundable deposit (kept as a price note, not a
    separate Price, since it's part of the tuition, not an add-on).
  - STATUS: "Registrations are OPEN" → application `open` (the edition itself is
    `scheduled`).
  - REQUIREMENTS: the application form requires a **ballet pose photo** upload
    *and* a **video link** (a classical variation, centre work, or barre work —
    or a 20-second smartphone clip). The video brief lists acceptable content but
    no set combination, so it's `video`/`unspecific`; the photo is a single
    freeform pose → `photos`/`freeform`. Both branches are emitted.

FACULTY: the page publishes a named 2026 roster with stated affiliations (mostly
Wiener Staatsballett / Wiener Staatsoper principals & soloists and their Ballett
Akademie teachers). Elementor lays the names, role labels and bios in separate
non-adjacent DOM columns, so document-order pairing is unreliable; we bind each
name to its source-stated role + affiliation via a curated map and emit only the
names actually present on the live page (so a roster change drops missing names).
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
    PhotosReq,
    Price,
    Requirement,
    Schedule,
    Session,
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

BASE = "https://www.attitudestudios.at"
PAGE = f"{BASE}/vienna-ballet-intensive/"

ORG = Organization(
    name="Attitude Ballet Studios Vienna",
    slug="attitude-ballet-studios",
    country="AT",
    city="Vienna",
)
VENUE = "Attitude Ballet Studios Vienna (Pfeilgasse 14/1, 1080 Vienna, Josefstadt)"

# Elementor/Wix-style markup injects zero-width spaces (ZWSP/ZWNJ/ZWJ/BOM).
_ZERO_WIDTH = re.compile("[" + "".join(map(chr, (0x200B, 0x200C, 0x200D, 0xFEFF))) + "]")

_VIDEO_BRIEF = (
    "Submit a video link featuring a classical variation, centre work, or barre "
    "work (a 20-second smartphone clip is accepted if no recording exists)."
)
_APPLY_NOTE = (
    "Apply via the form on the intensive page (a ballet-pose photo and a video "
    "link are required). A non-refundable €200 deposit is due on acceptance; the "
    "tuition balance is due by 01 April 2026 (01 May 2026 for later registrations). "
    "Housing is not included; an exception may be made for 11-year-olds with "
    "excellent technique."
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    offering = _build_offering(resp.text)
    return [offering] if offering is not None else []


def _build_offering(html: str) -> Offering | None:
    text = _text(html)

    start, end = _date_range(text)
    anchor = end or start
    if anchor is None:
        return None  # no dated edition parseable
    season = str(anchor.year)

    return Offering(
        id=f"attitude-ballet-studios/vienna-ballet-intensive-{season}",
        source=Source(provider="attitude-ballet-studios", url=PAGE, scrapedAt=now_utc()),
        title=f"Vienna Ballet Intensive {season}",
        genres=_genres(text),
        level=_levels(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue=VENUE, city="Vienna", country="AT"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Vienna",
            sessions=[Session(start=start, end=end, notes=_schedule_note(text))],
        ),
        teachers=_teachers(text),
        prices=_prices(text),
        application=Application(
            status=_status(text),
            url=PAGE,
            requirements=_requirements(text),
            notes=_APPLY_NOTE,
        ),
    )


def _text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    raw = tree.body.text(separator=" ") if tree.body else ""
    return parse.clean(_ZERO_WIDTH.sub("", raw))


# --- dates --------------------------------------------------------------------

# "13 - 25 July 2026" — one trailing month + year spanning both days.
_RANGE = re.compile(
    r"(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    d1, d2, month_name, year = m.groups()
    month = parse.MONTHS[month_name.lower()]
    y = int(year)
    return date(y, month, int(d1)), date(y, month, int(d2))


_SCHEDULE_NOTE = (
    "Monday to Friday 10:00-16:30, Saturday 10:00-13:00; ends with a final "
    "presentation and signed certificates."
)


def _schedule_note(text: str) -> str | None:
    return _SCHEDULE_NOTE if re.search(r"final presentation", text, re.IGNORECASE) else None


# --- ages / level -------------------------------------------------------------

# "Students 12+ years old" — open-ended upper bound (records only the lower).
_AGE = re.compile(r"(\d{1,2})\s*\+\s*years?\s*old", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    return parse.extract_age_range(text, _AGE)


def _levels(text: str) -> list[Level]:
    low = text.lower()
    out: list[Level] = []
    if "pre-professional" in low or "preprofessional" in low:
        out.append("pre-professional")
    if re.search(r"\bprofessionals?\b", low):
        out.append("professional")
    return out


# --- genres: match the curriculum list, not loose prose -----------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet study class", "ballet")),
    ("pointe", ("pointe",)),
    ("repertoire", ("variations", "repertoire")),
    ("contemporary", ("modern and contemporary", "contemporary")),
    ("character", ("character dance",)),
    ("neoclassical", ("neoclassical",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- prices: €1,350 (2 weeks) / €750 (1 week) ---------------------------------

# Standard-rate prose: "2 Weeks (Full Program): €1,350" / "1 Week: €750". The €
# sits in a <sup>, so text extraction yields "€ 1350" — the symbol may carry a
# trailing space and the amount may use a thousands separator.
_PRICE_LINES: list[tuple[str, str, list]] = [
    (r"2\s*Weeks?\s*\(Full Program\)\s*:\s*€\s*([\d.,]+)", "2 weeks (full program)", ["tuition"]),
    (r"1\s*Week\s*:\s*€\s*([\d.,]+)", "1 week", ["tuition"]),
]


def _prices(text: str) -> list[Price]:
    deposit_note = (
        "A non-refundable €200 deposit reserves the spot; balance due 01 April 2026."
        if re.search(r"deposit", text, re.IGNORECASE)
        else None
    )
    prices: list[Price] = []
    for pattern, label, includes in _PRICE_LINES:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        amount = parse.parse_amount(m.group(1))
        if amount is None:
            continue
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=label,
                includes=includes,
                notes=deposit_note,
            )
        )
    return prices


# --- status -------------------------------------------------------------------


def _status(text: str):
    low = text.lower()
    if re.search(r"registrations?\s+(are\s+)?open", low):
        return "open"
    if re.search(r"registrations?\s+(are\s+)?closed", low):
        return "closed"
    return None


# --- requirements: a ballet-pose photo + a video link -------------------------


def _requirements(text: str) -> list[Requirement]:
    low = text.lower()
    reqs: list[Requirement] = []
    if "ballet pose photo" in low or "upload ballet pose" in low:
        reqs.append(PhotosReq(specificity="freeform", notes="One ballet pose photo."))
    if re.search(r"video link", low):
        reqs.append(VideoReq(specificity="unspecific", description=_VIDEO_BRIEF))
    return reqs


# --- teachers: curated name → role + affiliation, gated on page presence ------

# (name, role-in-this-intensive, [(organization, role-at-org, current)]). Every
# affiliation is stated on the page; Elementor's split columns make document-order
# pairing unreliable, so we bind explicitly and emit only names present on the
# live page. Vienna State Opera / State Ballet is one house, but it's named two
# ways on the page (Wiener Staatsballett / Wiener Staatsoper), kept as written.
_FACULTY: list[tuple[str, str, list[tuple[str, str | None, bool | None]]]] = [
    (
        "Laura Cristinoiu",
        "Artistic Director",
        [("Attitude Ballet Studios Vienna", "founder", True)],
    ),
    (
        "Liudmila Konovalova",
        "Special Master Ballet Teacher",
        [("Wiener Staatsballett", "Prima Ballerina / Principal Dancer", True)],
    ),
    (
        "Roman Lazik",
        "Special Guest Master Teacher",
        [("Vienna State Ballet", "First Soloist", False)],
    ),
    (
        "Natalya Kusch",
        "Special Guest Master Teacher",
        [("Vienna State Opera Ballet", "Soloist", None)],
    ),
    (
        "Annkathrin Dehn",
        "Special Guest Teacher",
        [("Staatsoper Ballett Akademie Vienna", "teacher", True)],
    ),
    (
        "Alexandra Inculet",
        "Special Guest Teacher",
        [("Wiener Staatsoper", "Demi Soloist", True)],
    ),
    (
        "Robert Gabdullin",
        "Special Guest Teacher",
        [
            ("Wiener Staatsoper", "Principal Dancer", False),
            ("Ballett Akademie of the Vienna State Opera", "teacher", True),
        ],
    ),
    (
        "Máire Elizabeth New",
        "Special Guest Teacher",
        [("Bolshoi Ballet Academy", "graduate", False)],
    ),
]


def _teachers(text: str) -> list[Teacher]:
    out: list[Teacher] = []
    for name, role, orgs in _FACULTY:
        if name not in text:
            continue
        out.append(
            Teacher(
                name=name,
                role=role,
                affiliations=[
                    Affiliation(organization=org, role=org_role, current=current)
                    for org, org_role, current in orgs
                ],
            )
        )
    return out
