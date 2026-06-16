"""Prix de Lausanne — Summer Intensive (International Preselection), Lausanne, CH.

SCOPE: this scraper covers ONLY the Prix de Lausanne **Summer Intensive** — the
six-day July training programme — NOT the Prix de Lausanne *competition*, which
stays out of scope (icebox epic #80). The competition has its own separate
`prix-de-lausanne` seed in providers.json; this is a distinct provider/slug
(`prix-de-lausanne-summer-intensive`) for the training intensive only.

API FIRST: none usable. The site is WordPress (Yoast JSON-LD present) but the
only `application/ld+json` block is `WebPage` metadata — no `Course`/`Event`. The
`/summer-intensive/` page is fully **server-side rendered**, so the whole brief
(dates, ages, registration window, fee, video deadline) is in the static HTML —
a one-page scrape, no JS render needed. We pin `Accept-Language: en` because the
site is bilingual (EN/FR); EN is the canonical brief and keeps the parse stable.

DISCOVERY: one page describes the current dated edition — a single six-day
Summer Intensive each July. We emit one `Offering`, season-keyed from the parsed
dates so the id rolls forward when the page advances a year.

WHAT THE PAGE GIVES US (verified live 2026-06):
  - DATES: "The 2026 Summer Intensive will take place from 6 to 11 July 2026"
    (a single-month day range with a shared trailing year).
  - AGES: stated as a **birthdate band**, not a number — "Dancers must be born
    between 7 February 2008 and 6 February 2012." We keep that verbatim in the
    schedule note and derive the age band the dancers reach by the course
    (14–18 in July 2026) from the two birthdates.
  - REGISTRATION WINDOW: registration ran 15 March – 15 April 2026. We keep the
    dated bounds (`opensAt` / `deadline`) and leave `application.status` unset —
    the page states a window, not a current status, and deriving open/closed from
    `today` would invent a status and break the no-diff rule (status is hashed).
    Consumers derive open/closed from those dates. Closing the booking window does
    not cancel the edition (the course still takes place), so `lifecycle` stays
    `scheduled` (the IDR-24 closed ≠ cancelled distinction).
  - REQUIREMENTS: applicants "must upload their video by 15 April 2026" — a video
    submission, but the page never describes its content (variations? free?), so
    it's `video`/`unspecific`; the upload deadline is kept on the application.
  - FEE: a 1st registration fee of CHF 150 (non-refundable). Tuition is mentioned
    ("registration and tuition fees are non-refundable") but no tuition amount is
    published here, so only the registration fee is emitted.

Faculty are described generically ("world-renowned teachers and artistic
figures"), with no named 2026 roster, so teachers are left empty rather than
over-claimed (the same call the Brussels and Joffrey scrapers make).
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
    Requirement,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://www.prixdelausanne.org"
PAGE = f"{BASE}/summer-intensive/"

ORG = Organization(
    name="Prix de Lausanne — Summer Intensive",
    slug="prix-de-lausanne-summer-intensive",
    country="CH",
    city="Lausanne",
)

VENUE = "Beaulieu Theatre"

_APPLY_NOTE = (
    "Selection by application with a video upload (deadline 15 April 2026); a "
    "1st registration fee of CHF 150 is due by the same date. Selected dancers "
    "are notified by 5 May 2026 and a select few earn a place at the Prix de "
    "Lausanne competition itself. All registration and tuition fees are "
    "non-refundable."
)


def scrape(client: httpx.Client) -> list[Offering]:
    # Pin EN: the site is bilingual (EN/FR); EN is the canonical brief.
    resp = client.get(PAGE, headers={"Accept-Language": "en"})
    resp.raise_for_status()
    offering = _build_offering(resp.text)
    return [offering] if offering is not None else []


def _build_offering(html: str) -> Offering | None:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    start, end = _date_range(text)
    anchor = end or start
    if anchor is None:
        return None  # no dated edition parseable
    season = str(anchor.year)

    reg_open, reg_close = _registration_window(text)

    return Offering(
        id=f"prix-de-lausanne-summer-intensive/summer-intensive-{season}",
        source=Source(provider="prix-de-lausanne-summer-intensive", url=PAGE, scrapedAt=now_utc()),
        title=f"Summer Intensive {season}",
        genres=_genres(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue=VENUE, city="Lausanne", country="CH"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Zurich",
            notes=_schedule_note(text),
        ),
        prices=_prices(text),
        application=Application(
            # The page states a registration window (opens/closes dates), not a
            # current status — keep the dated bounds (opensAt/deadline) and leave
            # `status` unset. Deriving open/upcoming/closed from `today` invents a
            # status and is non-deterministic (status is hashed). Consumers derive
            # it from opensAt/deadline vs today.
            opensAt=reg_open,
            deadline=_video_deadline(text) or reg_close,
            url=PAGE,
            requirements=_requirements(text),
            notes=_APPLY_NOTE,
        ),
    )


# --- dates: "from 6 to 11 July 2026" (single month, shared trailing year) ------

_RANGE = re.compile(
    r"from\s+(\d{1,2})\s+to\s+(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    d1, d2, month, year = m.groups()
    y, mo = int(year), parse.MONTHS[month.lower()]
    return date(y, mo, int(d1)), date(y, mo, int(d2))


def _schedule_note(text: str) -> str | None:
    m = _BIRTH_BAND.search(text)
    return f"Open to dancers born between {m.group(1)} and {m.group(2)}." if m else None


# --- ages: a birthdate band, not a number -------------------------------------

# "born between 7 February 2008 and 6 February 2012".
_BIRTH_BAND = re.compile(
    r"born\s+between\s+"
    r"(\d{1,2}\s+(?:" + parse.MONTHALT + r")\s+\d{4})"
    r"\s+and\s+"
    r"(\d{1,2}\s+(?:" + parse.MONTHALT + r")\s+\d{4})",
    re.IGNORECASE,
)
_DATE = re.compile(r"(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})", re.IGNORECASE)


def _parse_birthdate(raw: str) -> date | None:
    m = _DATE.search(raw)
    if not m:
        return None
    d, month, year = m.groups()
    return date(int(year), parse.MONTHS[month.lower()], int(d))


def _age_at(course: date, born: date) -> int:
    years = course.year - born.year
    if (course.month, course.day) < (born.month, born.day):
        years -= 1
    return years


def _age_range(text: str) -> dict | None:
    """Derive the age band the dancers reach by the course from the birthdate band.

    The oldest dancer (earliest birthdate) gives the upper bound; the youngest
    (latest birthdate) the lower. Anchored on the course start.
    """
    band = _BIRTH_BAND.search(text)
    start, _ = _date_range(text)
    if not band or start is None:
        return None
    oldest = _parse_birthdate(band.group(1))
    youngest = _parse_birthdate(band.group(2))
    if oldest is None or youngest is None:
        return None
    return {"min": _age_at(start, youngest), "max": _age_at(start, oldest)}


# --- registration window: "from 15 March to 15 April 2026" ---------------------

_REG_WINDOW = re.compile(
    r"[Rr]egistration\s+(?:was|will be)\s+open\s+from\s+"
    r"(\d{1,2})\s+(" + parse.MONTHALT + r")\s+"
    r"to\s+"
    r"(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _registration_window(text: str) -> tuple[date | None, date | None]:
    m = _REG_WINDOW.search(text)
    if not m:
        return None, None
    d1, m1, d2, m2, year = m.groups()
    y = int(year)
    return (
        date(y, parse.MONTHS[m1.lower()], int(d1)),
        date(y, parse.MONTHS[m2.lower()], int(d2)),
    )


# --- video deadline: "upload their video by 15 April 2026" ---------------------

_VIDEO_DEADLINE = re.compile(
    r"upload\s+(?:their\s+)?video\s+by\s+(\d{1,2}\s+(?:" + parse.MONTHALT + r")\s+\d{4})",
    re.IGNORECASE,
)


def _video_deadline(text: str) -> date | None:
    m = _VIDEO_DEADLINE.search(text)
    return _parse_birthdate(m.group(1)) if m else None


def _requirements(text: str) -> list[Requirement]:
    # A video upload is required, but its content isn't described → unspecific.
    if re.search(r"upload\s+(?:their\s+)?video", text, re.IGNORECASE):
        return [
            VideoReq(
                specificity="unspecific",
                description="A video must be uploaded with the application by the deadline.",
            )
        ]
    return []


# --- price: "1st registration fee* (CHF 150-.)" --------------------------------

_FEE = re.compile(
    r"registration\s+fee\b[^.]*?CHF\s*(\d[\d'.,]*)",
    re.IGNORECASE,
)


def _prices(text: str) -> list[Price]:
    m = _FEE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1).replace("'", ""))
    if amount is None:
        return []
    return [
        Price(
            amount=amount,
            currency="CHF",
            label="1st registration fee",
            notes="Non-refundable. Tuition fees apply but are not published on this page.",
        )
    ]


# --- genres -------------------------------------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet")),
    ("contemporary", ("contemporary",)),
    ("repertoire", ("variation", "repertoire")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])
