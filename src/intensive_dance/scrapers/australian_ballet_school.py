"""The Australian Ballet School — annual Summer School, Melbourne (austral summer).

API FIRST
The site (https://www.australianballetschool.com.au) is **Shopify**, not
WordPress — ``GET /wp-json/`` 404s and serves a Shopify 404 shell. Shopify
exposes clean structured JSON, so there is no HTML scraping at all: the Summer
School programs are Shopify **products** in the ``summer-school`` collection,
read via ``/collections/summer-school/products.json``. Each product's
``body_html`` carries the dated detail (event dates, fee, venue, eligibility),
and the variants carry the bookable per-week sub-editions and the standard fee.
A plain fetch with our UA works — no proxy needed (verified live 2026-06-08).

DISCOVERY
The Summer School is the School's public, dated short-term student intensive
(its full-time vocational course and the invitation-only Interstate Training
Program "ITP" / Intensive Training Sessions are out of scope — the ITP is a
closed talent-pipeline scheme for already-selected students, not a public
intensive). The 2026 edition (Jan 2026, now past — kept per IDR-24) runs four
student programs that differ by age band, and the two senior ones run in two
separate weeks:
  - Open Program          ages 8-18  — Week One AND Week Two
  - Pre-Professional      ages 14-21 — Week One AND Week Two (advanced level only)
  - Boys Program          ages 10-13 — Week One only
  - Creative Program      ages 6-7   — Week Two only
We emit **one Offering per (program, week)** — the weeks have distinct dates, so
folding them would lose a cycle. Non-program products in the collection
(Auditions, Merchandise, Graduate Access) carry no "Event Dates" block and are
skipped. No 2027 products exist yet ("enrolments open in 2026").

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08)
  - SHOPIFY products.json as the structured source (no HTML parse, no proxy).
  - ONE Offering per dated week-edition from a multi-week program.
  - PRICES in AUD: an Early Bird and a Standard fee per program (the variant
    price is the Standard fee; the Early Bird is read from the body).
  - REQUIREMENTS = NoneReq: the Summer School is open-enrolment — every program
    states "No audition is required" (the Pre-Professional adds an advanced-level
    *prerequisite*, which is eligibility, not an application submission).
  - GENRES from the per-product class list (classical base + character /
    contemporary where the body names those classes; jazz maps to contemporary).
  - TEACHERS: none named per program (the body credits "staff of the School and
    guest teachers from The Australian Ballet" collectively), so teachers stays
    empty — the Joffrey case.
  - DEADLINE: the body's "Online enrolments must close <date>" line.
  - GENDER on the Session: the Boys Program is male-only (tag "Boys Only").
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    Gender,
    Genre,
    Level,
    Location,
    NoneReq,
    Offering,
    Organization,
    Price,
    Schedule,
    Session,
    Source,
    now_utc,
)

BASE = "https://www.australianballetschool.com.au"
COLLECTION_URL = f"{BASE}/collections/summer-school/products.json?limit=250"

ORG = Organization(
    name="The Australian Ballet School",
    slug="australian-ballet-school",
    country="AU",
    city="Melbourne",
)
LOCATION = Location(
    venue="The Primrose Potter Australian Ballet Centre, 2 Kavanagh St, Southbank",
    city="Melbourne",
    country="AU",
)
TIMEZONE = "Australia/Melbourne"

# Summer School is open-enrolment; every program states no audition is required.
_REQUIREMENT_NOTE = (
    "No audition is required to enrol in the Summer School. "
    "The Pre-Professional Program additionally requires advanced-level "
    "ballet experience (ABS Level 5+, RAD Advanced I, Cecchetti Advanced I, "
    "or equivalent)."
)

# Class list → genres. Ballet is the base (it's a ballet school's summer school);
# the other styles are added only when the program's prose names that class. Jazz
# is not a register genre, so it maps to contemporary.
_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("contemporary", ("contemporary", "jazz")),
    ("character", ("character",)),
]


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(COLLECTION_URL)
    resp.raise_for_status()
    return _build_offerings(resp.json(), date.today())


def _build_offerings(payload: dict, today: date) -> list[Offering]:
    offerings: list[Offering] = []
    for product in payload.get("products", []):
        offerings.extend(_product_offerings(product))
    offerings.sort(key=lambda o: (o.schedule.start or date.min, o.id))
    return offerings


def _product_offerings(product: dict) -> list[Offering]:
    """One product → one Offering per dated week, or [] if it isn't a program.

    The collection also lists supporting products that are not the multi-hour
    student intensive: Auditions, Merchandise (no dates), and a Graduate Access
    pass (a single 90-min class/day for alumni). The four real programs are the
    only ones titled "… Program", so that word gates the discovery.
    """
    title = parse.clean(product.get("title") or "")
    if "program" not in title.lower():
        return []

    body = _body_text(product.get("body_html") or "")
    weeks = _weeks(body)
    if not weeks:
        return []

    handle = product.get("handle") or ""
    genres = _genres(body)
    levels = _levels(body)
    age_range = _age_range(body)
    deadline = _deadline(body)
    prices = _prices(body, product)
    gender = _gender(body, product)

    offerings: list[Offering] = []
    for label, start, end in weeks:
        week_slug = _week_slug(label)
        offerings.append(
            Offering(
                id=f"australian-ballet-school/{_offering_slug(handle, week_slug)}",
                source=Source(
                    provider="australian-ballet-school",
                    url=f"{BASE}/products/{handle}",
                    scrapedAt=now_utc(),
                ),
                title=f"{title} — {label}" if label else title,
                genres=genres,
                level=levels,
                ageRange=age_range,
                organization=ORG,
                location=LOCATION,
                schedule=Schedule(
                    season=str(start.year),
                    start=start,
                    end=end,
                    timezone=TIMEZONE,
                    notes=label or None,
                    sessions=[
                        Session(
                            label=label or None,
                            start=start,
                            end=end,
                            ageRange=age_range,
                            gender=gender,
                        )
                    ],
                ),
                prices=prices,
                application=Application(
                    deadline=deadline,
                    url=f"{BASE}/products/{handle}",
                    requirements=[NoneReq()],
                    notes=_REQUIREMENT_NOTE,
                ),
            )
        )
    return offerings


def _body_text(body_html: str) -> str:
    """The product body as flat text with single spaces."""
    return parse.clean(HTMLParser(body_html).text(separator=" "))


# --- dates --------------------------------------------------------------------
#
# The body lists one or two weeks: "Week One: 3 - 7 January 2026" / "Week Two:
# 8 - 12 January 2026" (spacing around the dash is irregular). Both days share
# a month and year stated after the second day.

_WEEK_RE = re.compile(
    r"Week\s+(One|Two|Three|1|2|3)\s*:\s*(\d{1,2})\s*[-–]\s*(\d{1,2})\s+("
    + parse.MONTHALT
    + r")\s+(20\d\d)",
    re.IGNORECASE,
)
_WEEK_LABELS = {
    "one": "Week One",
    "1": "Week One",
    "two": "Week Two",
    "2": "Week Two",
    "three": "Week Three",
    "3": "Week Three",
}


def _weeks(body: str) -> list[tuple[str, date, date]]:
    """(label, start, end) per week, de-duplicated and date-ordered."""
    seen: set[tuple[date, date]] = set()
    weeks: list[tuple[str, date, date]] = []
    for ordinal, d1, d2, month, year in _WEEK_RE.findall(body):
        month_num = parse.MONTHS[month.lower()]
        start = date(int(year), month_num, int(d1))
        end = date(int(year), month_num, int(d2))
        if (start, end) in seen:
            continue
        seen.add((start, end))
        label = _WEEK_LABELS.get(ordinal.lower(), "")
        weeks.append((label, start, end))
    weeks.sort(key=lambda w: w[1])
    return weeks


def _week_slug(label: str) -> str:
    return label.lower().replace(" ", "-") if label else ""


def _offering_slug(handle: str, week_slug: str) -> str:
    return f"{handle}-{week_slug}" if week_slug else handle


# --- deadline -----------------------------------------------------------------
#
# "Online enrolments must close 16 December 2025" (a colon may follow "close").

_DEADLINE_RE = re.compile(
    r"enrolments?\s+must\s+close:?\s+(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(20\d\d)",
    re.IGNORECASE,
)


def _deadline(body: str) -> date | None:
    match = _DEADLINE_RE.search(body)
    if not match:
        return None
    day, month, year = match.groups()
    return date(int(year), parse.MONTHS[month.lower()], int(day))


# --- ages ---------------------------------------------------------------------
#
# Eligibility prose names a band: "aged 8 to 18", "aged 10 to 13", or a bare
# "Age: 14 to 21" under a label. We anchor on those cues so the "3 - 7 January"
# date range can't be misread as ages.

_AGE_CUE_RE = re.compile(r"aged?\s+(\d{1,2})\s*(?:to|-|–)\s*(\d{1,2})", re.IGNORECASE)
_AGE_LABEL_RE = re.compile(r"\bAge\b\s*:?\s*(\d{1,2})\s*(?:to|-|–)\s*(\d{1,2})", re.IGNORECASE)


def _age_range(body: str) -> dict | None:
    match = _AGE_CUE_RE.search(body) or _AGE_LABEL_RE.search(body)
    if not match:
        return None
    return {"min": int(match.group(1)), "max": int(match.group(2))}


# --- levels -------------------------------------------------------------------


def _levels(body: str) -> list[Level]:
    low = body.lower()
    levels: list[Level] = []
    if "advanced-level" in low or "advanced level" in low or "advanced ballet" in low:
        levels.append("pre-professional")
    levels.append("open")  # open-enrolment by age, no streaming audition
    return levels


# --- genres -------------------------------------------------------------------


def _genres(body: str) -> list[Genre]:
    """Classical base plus any other class the program's prose names."""
    extra = parse.match_genres(body, _GENRE_KEYWORDS)
    genres: list[Genre] = ["classical"]
    for genre in extra:
        if genre not in genres:
            genres.append(genre)
    return genres


# --- gender -------------------------------------------------------------------


def _gender(body: str, product: dict) -> Gender:
    low = body.lower()
    tags = [t.lower() for t in product.get("tags", [])]
    if "boys only" in tags or "male students" in low or "young male dancers" in low:
        return "male"
    return "both"


# --- prices -------------------------------------------------------------------
#
# The body states "$700 Early Bird Fee / $740 Standard Fee" in AUD; the Shopify
# variant price is the Standard fee. We emit both tiers.

_EARLY_BIRD_RE = re.compile(r"\$\s*([\d,]+)\s*Early\s*Bird", re.IGNORECASE)
_STANDARD_RE = re.compile(r"\$\s*([\d,]+)\s*Standard", re.IGNORECASE)


def _prices(body: str, product: dict) -> list[Price]:
    prices: list[Price] = []
    standard = _STANDARD_RE.search(body)
    standard_amount = parse.parse_amount(standard.group(1)) if standard else None
    if standard_amount is None:
        # Fall back to the variant price if the body omits a Standard line.
        standard_amount = _variant_price(product)
    if standard_amount is not None:
        prices.append(
            Price(
                amount=standard_amount,
                currency="AUD",
                label="Standard fee",
                includes=["tuition"],
            )
        )
    early = _EARLY_BIRD_RE.search(body)
    early_amount = parse.parse_amount(early.group(1)) if early else None
    if early_amount is not None:
        prices.append(
            Price(
                amount=early_amount,
                currency="AUD",
                label="Early Bird fee",
                includes=["tuition"],
                notes="Early Bird pricing ends before the stated cut-off date.",
            )
        )
    return prices


def _variant_price(product: dict) -> float | None:
    for variant in product.get("variants", []):
        amount = parse.parse_amount(str(variant.get("price") or ""))
        if amount is not None:
            return amount
    return None
