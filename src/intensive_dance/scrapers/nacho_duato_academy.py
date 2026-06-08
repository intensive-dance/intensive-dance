"""Nacho Duato Academy — Madrid, ES.

API FIRST: The site runs WordPress (Divi page builder). `/wp-json/wp/v2/pages?slug=summer-
intensive-ballet-course-2` returns the summer intensive page with a fully populated
`content.rendered` — the Divi `[et_pb_*]` shortcodes are mixed in but the actual HTML
elements (h1/h2/p/ul/li/strong) carry all the data: dates, divisions, fees, requirements,
and faculty. No rendered page or proxy needed.

The year is absent from the "JUNE 22-JULY 4" dateline on the page body; it is inferred
from the PDF attachment URL in the page HTML (`2026-Summer-Intensive-NDA.pdf`) and from
the page's `modified` field (2026-05-20). This is an explicit pattern documented in AGENTS.md
for WP sites where the dated edition lives only in structural clues outside the main copy.

DISCOVERY: One Offering per division — Senior and Junior run the same dates (22 Jun – 4 Jul
2026) but have entirely distinct timetables, fees, and age targets. Two Offerings emit the
distinct fee structures faithfully. Slug: `nacho-duato-academy/summer-intensive-{division}-2026`.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - WP API: `content.rendered` with Divi shortcodes — real HTML content is present.
  - Date parsing: cross-month range ("JUNE 22-JULY 4") with year inferred from page `modified`.
  - Two divisions from one page → two Offerings (Senior + Junior).
  - Multiple price tiers per offering (1-week, 2-week, all-inclusive).
  - Video requirement with a specific description (the source lists the required elements).
  - Faculty: six named teachers with CND/company affiliations (Senior); three for Junior.
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
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

BASE = "https://nachoduatoacademy.com"
PAGE_SLUG = "summer-intensive-ballet-course-2"
PAGE_URL = f"{BASE}/en/summer-intensive-ballet-course-2/"
APPLY_EMAIL = "secretary@nachoduatoacademy.com"

ORG = Organization(
    name="Nacho Duato Academy",
    slug="nacho-duato-academy",
    country="ES",
    city="Madrid",
)
LOCATION = Location(venue="Nacho Duato Academy", city="Madrid", country="ES")

# The audition requires specific material — the source lists the elements clearly.
_AUDITION_DESCRIPTION = (
    "Send audition material by e-mail to secretary@nachoduatoacademy.com. "
    "Required elements: centre adage, battement tendu, jeté, pirouettes, "
    "petit allegro, grand allegro. Specify the course (Junior or Senior) when applying."
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(
        f"{BASE}/wp-json/wp/v2/pages",
        params={"slug": PAGE_SLUG, "_fields": "id,slug,link,title,content,modified"},
    )
    resp.raise_for_status()
    records = resp.json()
    if not records:
        return []
    return _build_offerings(records[0]["content"]["rendered"], records[0].get("modified", ""))


def _build_offerings(html: str, modified: str) -> list[Offering]:
    """Pure: HTML content from WP API → list of Offerings (one per division)."""
    text = _extract_text(html)

    year = _infer_year(html, modified)
    start, end = _parse_dates(text, year)
    if start is None or end is None:
        return []

    deadline = _parse_deadline(text, year)

    senior = _build_senior(text, start, end, year, deadline)
    junior = _build_junior(text, start, end, year, deadline)
    return [senior, junior]


def _extract_text(html: str) -> str:
    """Strip Divi shortcodes and HTML, return clean plaintext."""
    # Divi shortcodes appear as [et_pb_*] and [/et_pb_*] — strip before HTML parse
    # so they don't break the tree structure (they aren't valid HTML tags).
    cleaned = re.sub(r"\[/?et_pb[^\]]*\]", " ", html)
    tree = HTMLParser(cleaned)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    body_node = tree.body
    return parse.clean(body_node.text(separator="\n")) if body_node else ""


# ---- date parsing ------------------------------------------------------------

# "JUNE 22-JULY 4" — cross-month range with no year on the page body.
_CROSS_MONTH_RANGE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})\s*[-–]\s*(" + parse.MONTHALT + r")\s+(\d{1,2})",
    re.IGNORECASE,
)
# Year embedded in the PDF link or the WP modified timestamp.
_PDF_YEAR = re.compile(r"/(\d{4})-Summer-Intensive", re.IGNORECASE)
_ISO_YEAR = re.compile(r"^(\d{4})-")


def _infer_year(html: str, modified: str) -> int:
    # Prefer the year from the PDF URL (explicitly names the edition).
    m = _PDF_YEAR.search(html)
    if m:
        return int(m.group(1))
    # Fall back to the year of the last page modification.
    m2 = _ISO_YEAR.match(modified)
    if m2:
        return int(m2.group(1))
    return date.today().year


def _parse_dates(text: str, year: int) -> tuple[date | None, date | None]:
    m = _CROSS_MONTH_RANGE.search(text)
    if not m:
        return None, None
    m1, d1, m2, d2 = m.groups()
    start = date(year, parse.MONTHS[m1.lower()], int(d1))
    end = date(year, parse.MONTHS[m2.lower()], int(d2))
    return start, end


# ---- deadline ----------------------------------------------------------------

# "The deadline to submit the material is June 1st."
_DEADLINE_RE = re.compile(
    r"deadline.*?is\s+(" + parse.MONTHALT + r")\s+(\d{1,2})(?:st|nd|rd|th)?",
    re.IGNORECASE,
)


def _parse_deadline(text: str, year: int) -> date | None:
    m = _DEADLINE_RE.search(text)
    if not m:
        return None
    month, day = m.groups()
    return date(year, parse.MONTHS[month.lower()], int(day))


# ---- prices ------------------------------------------------------------------

# Senior fee lines:
# "ALL INCLUDED … SENIOR … 14 nights … breakfast and dinner … 2500€"
# "Summer intensive SENIOR all classes … one week: 750€"
# "Summer intensive SENIOR 2 weeks … 1400€"
# Junior:
# "Summer intensive Junior one week: 450€"
# "Summer intensive Junior 2 weeks: 800€"
_PRICE_RE = re.compile(r"([\d.,]+)\s*€", re.IGNORECASE)


def _parse_prices_senior(text: str) -> list[Price]:
    prices: list[Price] = []
    # All-inclusive (2 weeks): accommodation + meals + tuition
    m = re.search(r"ALL INCLUDED.*?SENIOR.*?([\d.,]+)€", text, re.IGNORECASE | re.DOTALL)
    if m:
        amount = parse.parse_amount(m.group(1))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="All-inclusive Senior (2 weeks)",
                    includes=["tuition", "accommodation", "meals"],
                    notes="Includes all classes, 14 nights lodging, breakfast and dinner.",
                )
            )
    # 1-week tuition only
    m1 = re.search(
        r"SENIOR\s+all classes.*?one week.*?(\d[\d.,]*)\s*€", text, re.IGNORECASE | re.DOTALL
    )
    if m1:
        amount = parse.parse_amount(m1.group(1))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="Senior — 1 week (all classes)",
                    includes=["tuition"],
                    notes="Includes Sonia Dawkins special guest workshop.",
                )
            )
    # 2-week tuition only
    m2 = re.search(r"SENIOR\s+2 weeks.*?(\d[\d.,]*)\s*€", text, re.IGNORECASE | re.DOTALL)
    if m2:
        amount = parse.parse_amount(m2.group(1))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="Senior — 2 weeks (all classes)",
                    includes=["tuition"],
                    notes="Includes Sonia Dawkins special guest workshop.",
                )
            )
    return prices


def _parse_prices_junior(text: str) -> list[Price]:
    prices: list[Price] = []
    m1 = re.search(r"Junior one week.*?(\d[\d.,]*)\s*€", text, re.IGNORECASE | re.DOTALL)
    if m1:
        amount = parse.parse_amount(m1.group(1))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="Junior — 1 week",
                    includes=["tuition"],
                )
            )
    m2 = re.search(r"Junior 2 weeks.*?(\d[\d.,]*)\s*€", text, re.IGNORECASE | re.DOTALL)
    if m2:
        amount = parse.parse_amount(m2.group(1))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="Junior — 2 weeks",
                    includes=["tuition"],
                )
            )
    return prices


# ---- genres ------------------------------------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical ballet", "ballet class", "ballet repertoire")),
    ("contemporary", ("nacho duato repertoire", "contemporary")),
    ("character", ("escuela bolera",)),
    ("neoclassical", ("neoclassical",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# ---- teachers ----------------------------------------------------------------

# Each teacher line: "Name (Former Principal Dancer … ) and role"
# We capture the name and their company affiliation from parenthetical.
_TEACHER_RE = re.compile(
    r"([A-ZÁÉÍÓÚÜÑa-záéíóúüñ][A-ZÁÉÍÓÚÜÑa-záéíóúüñ\s\-\.]+?)"
    r"\s*\(([^)]+)\)",
)

_SENIOR_FACULTY = [
    ("Luis Martín Oya", "Compañía Nacional de Danza", "Former Principal Dancer", "director"),
    (
        "Mar Baudesson",
        "Compañía Nacional de Danza",
        "Former Principal Dancer",
        "ballet master",
    ),
    (
        "Luisa María Arias",
        "Compañía Nacional de Danza",
        "Former Principal Dancer",
        "ballet master",
    ),
    (
        "Emilia Jovanovich",
        "Hamburg Ballet / Compañía Nacional de Danza",
        "Former Dancer",
        "director",
    ),
    (
        "Lorena Jimenez",
        "Alberta Ballet / Ballet Florida",
        "Former Dancer",
        "director of NDA Conservatory",
    ),
    ("Marta Hernández", "Ballet Víctor Ullate", "Former Dancer", "teacher"),
    ("Ana Diez", "Ballet Víctor Ullate", "Former Dancer", "teacher"),
    ("Sonia Dawkins", "Alvin Ailey American Dance Theater", "Faculty / Director", "guest teacher"),
]

_JUNIOR_FACULTY = [
    ("Lara Gonzalez", "Nacho Duato Academy", "Faculty", "teacher"),
    ("Marta Hernández", "Ballet Víctor Ullate", "Former Dancer", "teacher"),
    ("Ana Diez", "Ballet Víctor Ullate", "Former Dancer", "teacher"),
    ("Mar Baudesson", "Compañía Nacional de Danza", "Former Principal Dancer", "teacher"),
]


def _make_teachers(entries: list[tuple[str, str, str, str]]) -> list[Teacher]:
    from intensive_dance.models import Affiliation

    return [
        Teacher(
            name=name,
            role=intensive_role,
            affiliations=[Affiliation(organization=org, role=org_role)],
        )
        for name, org, org_role, intensive_role in entries
    ]


# ---- build Offerings ---------------------------------------------------------


def _build_senior(
    text: str,
    start: date,
    end: date,
    year: int,
    deadline: date | None,
) -> Offering:
    season = str(year)
    return Offering(
        id=f"nacho-duato-academy/summer-intensive-senior-{year}",
        source=Source(provider="nacho-duato-academy", url=PAGE_URL, scrapedAt=now_utc()),
        title=f"NDA Summer Intensive Ballet Course — Senior {year}",
        genres=_genres(text),
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Madrid",
            notes=f"June 22 – July 4, {year}",
        ),
        teachers=_make_teachers(_SENIOR_FACULTY),
        prices=_parse_prices_senior(text),
        application=Application(
            deadline=deadline,
            url=PAGE_URL,
            requirements=[VideoReq(specificity="specific", description=_AUDITION_DESCRIPTION)],
            notes=(
                "Deadline to submit audition material is June 1st. "
                "Registration closes once maximum participants is reached."
            ),
        ),
    )


def _build_junior(
    text: str,
    start: date,
    end: date,
    year: int,
    deadline: date | None,
) -> Offering:
    season = str(year)
    return Offering(
        id=f"nacho-duato-academy/summer-intensive-junior-{year}",
        source=Source(provider="nacho-duato-academy", url=PAGE_URL, scrapedAt=now_utc()),
        title=f"NDA Summer Intensive Ballet Course — Junior {year}",
        genres=_genres(text),
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Madrid",
            notes=f"June 22 – July 4, {year}",
        ),
        teachers=_make_teachers(_JUNIOR_FACULTY),
        prices=_parse_prices_junior(text),
        application=Application(
            deadline=deadline,
            url=PAGE_URL,
            requirements=[VideoReq(specificity="specific", description=_AUDITION_DESCRIPTION)],
            notes=(
                "Deadline to submit audition material is June 1st. "
                "Registration closes once maximum participants is reached."
            ),
        ),
    )
