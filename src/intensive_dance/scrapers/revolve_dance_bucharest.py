"""Revolve Dance Festival — Summer Intensive, Bucharest (RO).

API FIRST: the host runs WordPress (`/wp-json/` answers 200) but the programme
page is built with the **Brizy** page builder, which renders the content as a
deep tree of hash-named `brz-css-*` columns — there is no clean custom post type
for the groups and no schema.org `ld+json`. The page is fully server-rendered,
though, so the whole curriculum is in the static HTML; we read it as text and
slice on the group headings (the same structural-slice tactic
`russian_masters_ballet` uses), which is robust to the volatile Brizy classes.
A plain fetch returns the English `/en/` page verbatim (no proxy needed).

DISCOVERY: one dated 2026 edition (10–23 Aug, Bucharest; Stars Gala 23 Aug at
the Bucharest National Opera) split into age-graded **tracks** that differ in
ages, daily hours, fee and curriculum — so per the model we emit one `Offering`
per track rather than folding them:
  - CHILDREN (9–11), JUNIOR (12–14), JUNIOR PRO (13–15), SENIOR (16–20): the
    full-fortnight groups, sharing the 10–23 Aug span.
  - SENIOR PRO (18–25): a two-week NEW track priced per week (700/800/1300 €),
    contemporary/neoclassical-weighted, including Duato/Béjart castings.
  - Special groups "Nacho Duato" and "Maurice Béjart" (18–25, 17–23 Aug): short
    repertory courses that "can be taken separately, outside the summer course",
    each its own dates/fee/curriculum — kept as distinct Offerings.
The "Paquita" gala-casting line (150 €) is an *add-on fee* within the course,
not a track with its own curriculum/dates, so it is not a separate Offering.

MULTI-GENRE: this provider is genuinely multi-genre. Genres are matched per
track against that track's own curriculum sentence — Children/Junior teach
classical + character + repertoire + contemporary; the Pro/Senior tracks add
neoclassical and pas de deux; the Duato/Béjart special groups are
contemporary/neoclassical repertory. We do **not** force classical onto a track
whose curriculum is contemporary.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-06):
  - One provider → several Offerings, one per track (distinct ages/fees/genres).
  - PRICES in EUR, tuition-only; the SENIOR PRO track carries three (per-week +
    package), parsed from its own prose.
  - A confirmed named GUEST faculty roster (Nacho Duato, Ivan Liška, Nina
    Ivanovich/Vaganova, Andrey Ivanov/Eifman, Anne-Cécile Morelle, Domenico
    Levré) shared across the festival, with affiliations for the verifiable
    institutions.
  - REQUIREMENTS = video + two photos: the application form asks for a video
    link and two JPG photos (freeform, no named poses) → `video`/`unspecific`
    plus `photos`/`freeform`.
  - AGES via `{min, max}`; the "20+" intro is open-ended but every track states a
    closed band, so each Offering carries its own bounded range.
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

BASE = "https://revolvedance.ro"
PAGE = f"{BASE}/en/schedule/summer-intensive-2026/"

ORG = Organization(
    name="Revolve Dance Festival",
    slug="revolve-dance-bucharest",
    country="RO",
    city="Bucharest",
)

GALA_VENUE = "Bucharest National Opera"

# The application form asks for a video link and two photos, with no posing
# brief, so the requirements (below) are unspecific. The festival doubles its
# short courses as auditions for the gala choreographies (Duato/Béjart castings).
_APPLY_NOTE = (
    "Enrolment is open to students from public or private dance schools in "
    "Romania and abroad; groups are formed by level of preparation, and ages are "
    "completed by 1 January 2026. Apply via the online form with a video link "
    "(YouTube/Vimeo) and two photos. Gala-choreography places (Paquita, Duato, "
    "Béjart) are cast by audition during the first week of the course."
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text)


# Each track is introduced by a heading that appears verbatim in the body text;
# we slice the readable text between consecutive headings. `slug`/`title` name
# the Offering; `default_dates` is True for the four full-fortnight groups whose
# block omits explicit dates (they inherit the festival's 10–23 Aug span).
_TRACKS: list[tuple[str, str, str, bool]] = [
    ("CHILDREN group", "children", "Children (9–11)", True),
    ("JUNIOR group", "junior", "Junior (12–14)", True),
    ("JUNIOR PRO group", "junior-pro", "Junior Pro (13–15)", True),
    ("SENIOR group", "senior", "Senior (16–20)", True),
    ("SENIOR PRO Group", "senior-pro", "Senior Pro (18–25)", False),
    ("SPECIAL GROUP “Nacho Duato”", "special-nacho-duato", "Special Group — Nacho Duato", False),
    (
        "SPECIAL GROUP “Maurice Bejart”",
        "special-maurice-bejart",
        "Special Group — Maurice Béjart",
        False,
    ),
]
# Where the track list ends in the body text (faculty section follows).
_TRACKS_END = "Guest teachers"


def _build_offerings(html: str) -> list[Offering]:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    intro = _intro(text)
    festival_start, festival_end = _festival_dates(intro)
    season = str(festival_end.year) if festival_end else "2026"
    teachers = _teachers(text)

    offerings: list[Offering] = []
    for heading, slug, title, default_dates in _TRACKS:
        block = _slice(text, heading)
        if block is None:
            continue
        offerings.append(
            _build_offering(
                block,
                slug,
                title,
                season,
                festival_start if default_dates else None,
                festival_end if default_dates else None,
                teachers,
            )
        )
    return offerings


def _build_offering(
    block: str,
    slug: str,
    title: str,
    season: str,
    default_start: date | None,
    default_end: date | None,
    teachers: list[Teacher],
) -> Offering:
    start, end = _track_dates(block)
    if start is None and end is None:
        start, end = default_start, default_end

    return Offering(
        id=f"revolve-dance-bucharest/{slug}-{season}",
        source=Source(provider="revolve-dance-bucharest", url=PAGE, scrapedAt=now_utc()),
        title=f"Summer Intensive {season} — {title}",
        genres=_genres(block),
        level=_level(slug),
        ageRange=_age_range(block),
        organization=ORG,
        location=Location(city="Bucharest", country="RO"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Bucharest",
            sessions=_sessions(block),
            notes=f"Stars Gala on 23 August {season} at the {GALA_VENUE}.",
        ),
        teachers=teachers,
        prices=_prices(block),
        application=Application(
            url=PAGE,
            requirements=_requirements(),
            notes=_APPLY_NOTE,
        ),
    )


# --- text slicing -------------------------------------------------------------

# Heading order in the body text, used to bound each track's slice.
_HEADINGS = [h for h, _, _, _ in _TRACKS]


def _intro(text: str) -> str:
    """The enrolment intro, up to the first track heading (carries the dates)."""
    start = text.find("Enrollment for Revolve")
    first = _first_index(text, _HEADINGS)
    if start < 0:
        start = 0
    return text[start:first] if first is not None else text[start:]


def _slice(text: str, heading: str) -> str | None:
    """Body text from `heading` to the next heading (or the faculty section)."""
    begin = text.find(heading)
    if begin < 0:
        return None
    rest_from = begin + len(heading)
    ends = [e for h in _HEADINGS if (e := text.find(h, rest_from)) >= 0]
    cutoff = text.find(_TRACKS_END, rest_from)
    if cutoff >= 0:
        ends.append(cutoff)
    stop = min(ends) if ends else len(text)
    return text[begin:stop]


def _first_index(text: str, needles: list[str]) -> int | None:
    found = [i for n in needles if (i := text.find(n)) >= 0]
    return min(found) if found else None


# --- dates --------------------------------------------------------------------
#
# The festival span is in the intro ("August 10 – 23 in Bucharest"); a track
# block may restate its own ("Schedule: August 17-23" for the special groups,
# "Week 1, August 10-15" for Senior Pro). All dates are within one month/year.

_YEAR = 2026
_TZ_MONTH_RANGE = re.compile(
    r"August\s+(\d{1,2})\s*[-–]\s*(\d{1,2})",
    re.IGNORECASE,
)
# "presented at the Stars Gala on August 23, 2026" — the explicit gala year.
_GALA_YEAR = re.compile(r"August\s+\d{1,2},?\s+(20\d\d)", re.IGNORECASE)


def _year(text: str) -> int:
    m = _GALA_YEAR.search(text)
    return int(m.group(1)) if m else _YEAR


def _festival_dates(intro: str) -> tuple[date | None, date | None]:
    year = _year(intro)
    m = _TZ_MONTH_RANGE.search(intro)
    if not m:
        return None, None
    return date(year, 8, int(m.group(1))), date(year, 8, int(m.group(2)))


def _track_dates(block: str) -> tuple[date | None, date | None]:
    """Earliest start / latest end across the August ranges named in the block."""
    year = _year(block)
    spans = [
        (date(year, 8, int(a)), date(year, 8, int(b))) for a, b in _TZ_MONTH_RANGE.findall(block)
    ]
    if not spans:
        return None, None
    return min(s for s, _ in spans), max(e for _, e in spans)


# "Week 1, August 10-15: 700 euros" — the Senior Pro track's two weeks.
_WEEK = re.compile(
    r"Week\s+(\d)\s*,\s*August\s+(\d{1,2})\s*[-–]\s*(\d{1,2})",
    re.IGNORECASE,
)


def _sessions(block: str) -> list[Session]:
    year = _year(block)
    return [
        Session(
            label=f"Week {n}",
            start=date(year, 8, int(a)),
            end=date(year, 8, int(b)),
        )
        for n, a, b in _WEEK.findall(block)
    ]


# --- ages ---------------------------------------------------------------------

# "09 - 11 years", "18 - 25 years old", "Age: 18 - 25 years".
_AGE = re.compile(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*years", re.IGNORECASE)


def _age_range(block: str) -> dict | None:
    m = _AGE.search(block)
    if not m:
        return None
    return {"min": int(m.group(1)), "max": int(m.group(2))}


# --- levels -------------------------------------------------------------------

# The two-week "Pro" tracks and the casting-by-audition special groups read as
# pre-professional; the younger graded groups carry no level claim.
_PRE_PRO_SLUGS = {"junior-pro", "senior-pro", "special-nacho-duato", "special-maurice-bejart"}


def _level(slug: str) -> list[Level]:
    return ["pre-professional"] if slug in _PRE_PRO_SLUGS else []


# --- genres -------------------------------------------------------------------
#
# Matched against each track's own curriculum sentence — multi-genre by design,
# never force-defaulted to classical (a contemporary special group stays
# contemporary). "technique"/"ballet technique" reads as classical; "points"/
# "pointes" is the site's spelling of pointe. The two special groups *are* their
# named choreographer's repertory — that choreographer is the curriculum, so the
# name fixes the genre: Nacho Duato → contemporary, Maurice Béjart → neoclassical
# (Béjart's idiom) plus contemporary.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet technique", "technique", "boys", "pas de deux", "duet")),
    ("neoclassical", ("neo classic", "neo-classic", "neoclassic", "bejart", "béjart")),
    ("contemporary", ("contemporary", "duato")),
    ("character", ("character",)),
    ("repertoire", ("repertoire", "repertory", "choreograph")),
    ("pointe", ("pointe", "point")),
]


def _genres(block: str) -> list[Genre]:
    return parse.match_genres(block, _GENRE_KEYWORDS, default=["classical"])


# --- prices -------------------------------------------------------------------
#
# Tuition fees in EUR. We target the three shapes the page actually uses rather
# than scan every euro figure — the latter would catch the audition fee (50 €)
# and the optional Paquita add-on (150 €), neither of which is course tuition.
# The Senior Pro track names per-week and package prices ("Week 1, … : 700
# euros", "total package of 1300 euros"); the graded groups carry a single
# trailing tuition figure ("1090 €").

# "Week 1, … : 700 euros" — a labelled per-week tuition line.
_WEEK_PRICE = re.compile(r"Week\s+(\d)\s*,[^:]*:\s*(\d[\d.,]*)\s*euros?", re.IGNORECASE)
# "total package of 1300 euros" — the combined two-week package.
_PACKAGE_PRICE = re.compile(r"total package of\s*(\d[\d.,]*)\s*euros?", re.IGNORECASE)
# A lone trailing tuition figure ("1090 €"), used by the single-fee tracks.
_FLAT_PRICE = re.compile(r"(\d[\d.,]*)\s*€")


def _prices(block: str) -> list[Price]:
    week_prices = [_price(amount, f"Week {n}") for n, amount in _WEEK_PRICE.findall(block)]
    if week_prices:
        package = _PACKAGE_PRICE.search(block)
        if package:
            week_prices.append(_price(package.group(1), "Both weeks (package)"))
        return [p for p in week_prices if p is not None]

    # Single-fee track: take the first standalone "NNNN €" tuition figure.
    flat = _FLAT_PRICE.search(block)
    price = _price(flat.group(1), None) if flat else None
    return [price] if price is not None else []


def _price(raw: str, label: str | None) -> Price | None:
    amount = parse.parse_amount(raw)
    if amount is None:
        return None
    return Price(amount=amount, currency="EUR", label=label, includes=["tuition"])


# --- requirements -------------------------------------------------------------


def _requirements() -> list[Requirement]:
    return [
        VideoReq(specificity="unspecific", description="A video link (YouTube/Vimeo)."),
        PhotosReq(specificity="freeform", notes="Two photos (JPG)."),
    ]


# --- teachers -----------------------------------------------------------------
#
# A confirmed 2026 guest roster shared across the festival. Each is listed with
# a one-line bio in the "Guest teachers" block; we resolve the verifiable
# institutions to affiliations and keep the role line otherwise.

# (name, role-line, [(organization, slug|None)])
_ROSTER: list[tuple[str, str, list[tuple[str, str | None]]]] = [
    ("Nacho Duato", "International choreographer", [("Compañía Nacional de Danza", None)]),
    (
        "Ivan Liška",
        "Director, Bayerisches Junior Ballett München and Heinz-Bosl-Stiftung",
        [("Bayerisches Junior Ballett München", None)],
    ),
    (
        "Nina Ivanovich",
        "Professor of historical, character and classical dance",
        [("Vaganova Ballet Academy", "vaganova-ballet-academy")],
    ),
    (
        "Andrey Ivanov",
        "Head of professional selection and teacher; former Principal at the Mariinsky Theatre",
        [("Boris Eifman Dance Academy", None), ("Mariinsky Theatre", None)],
    ),
    (
        "Anne-Cécile Morelle",
        "Former soloist for Maurice Béjart and Roland Petit; State Diploma jury member",
        [],
    ),
    (
        "Domenico Levré",
        "Répétiteur of the Béjart Ballet Lausanne",
        [("Béjart Ballet Lausanne", None)],
    ),
]


def _teachers(text: str) -> list[Teacher]:
    # Only emit the roster if the faculty section is actually present on the page,
    # so a layout change doesn't silently bake in a stale roster.
    if _TRACKS_END not in text:
        return []
    teachers: list[Teacher] = []
    for name, role, orgs in _ROSTER:
        if name not in text:
            continue
        teachers.append(
            Teacher(
                name=name,
                role=role,
                affiliations=[Affiliation(organization=org, slug=slug) for org, slug in orgs],
            )
        )
    return teachers
