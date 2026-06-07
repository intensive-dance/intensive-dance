"""Masters of Ballet Academy (London) — its 2026 Summer Intensive editions.

API FIRST: none usable. MOBA runs a hand-rolled PHP site (`courses.php?course=N`,
`forms.php?f=N`) with no JSON API or embedded structured data; the pages are
server-rendered, so the full text is in the static HTML — a plain fetch, no JS.

DISCOVERY: the nav lists two short-term Summer Intensive editions for 2026, each
its own `courses.php?course=N` page that links to its own `forms.php?f=N`
application form:
  - course 11 → London (Sadler's Wells), 27 July – 1 August 2026, ages 8–19.
  - course 10 → Tbilisi (Opera & Ballet State Theatre), 19–25 July 2026,
    ages 11–19.
These are distinct places/dates/ages/fees, so we emit one Offering per edition
(per the model's one-Offering-per-place rule). The third nav course (course 4,
"Unlocked Heroes Competition") is a competition, not an intensive, so it's out of
scope and not read.

DATE TRAP (Tbilisi): a heading says "19th - 25th July 2026" (matching the nav
title and the `<h1>`) but a stale body "Date:" line reads "...2025" — leftover
from the 2025 anniversary edition the body describes as past ("In 2025 ... we
held ... bringing it back again"). We parse dates from the `<h1>`/`<h2>` heading
text only, so the stale body line never reaches the date parser.

REQUIREMENTS: the application form for each edition states selection is by
uploaded photos in named positions (jpeg, ≤5mb) — a *defined-poses* photo
requirement. The form lists two position sets (age-banded: 11–13 and 14+);
we emit their de-duplicated union as the poses. The youngest Juniors
(8–10) are exempt from the photo upload (course page), kept as a requirement note.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-05):
  - PRICES in the *local* currency: London quotes two GBP tiers (£250 Juniors,
    £750 Seniors/Pre-Pro); Tbilisi quotes 900 EUR (a £800 figure is shown in
    parentheses but EUR is the headline/local currency for a Georgia course).
  - AGE ranges from "aged 8-19" / "aged 11-19".
  - GENRES keyword-matched against the syllabus the course page names:
    London "Ballet, Character, Pas de Deux, Neo-Classical/ Contemporary"
    (no repertoire/solos/pointe); Tbilisi "Ballet, Pointe, Solos, Character,
    Neo Classical and Pas de Deux" (no contemporary).
  - REQUIREMENTS = PHOTOS, defined-poses, with the form's named positions.
  - TEACHERS: none emitted — the roster mixes confirmed guests with "to be
    announced" and legacy bios, so naming them would over-claim (same call the
    Brussels and Princess Grace scrapers make).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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
    PhotosReq,
    Price,
    PriceInclude,
    Requirement,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://mastersofballetacademy.com"

ORG = Organization(
    name="Masters of Ballet Academy",
    slug="masters-of-ballet-academy",
    country="GB",
    city="London",
)


@dataclass(frozen=True)
class _Edition:
    """One Summer Intensive edition: its course page, slug suffix, place & timezone."""

    course_id: int
    slug: str
    venue_city: str
    venue_country: str  # ISO 3166-1 alpha-2
    timezone: str
    venue_name: str | None = None  # named theatre/venue where the course is held
    # True when the page has a confirmed, complete "FULL FACULTY:" roster;
    # False when the roster mixes confirmed guests with TBA announcements and
    # emitting partial names would over-claim.
    emit_teachers: bool = False


# The two short-term editions the nav lists for 2026.
_EDITIONS = (
    _Edition(
        11,
        "summer-intensive-london",
        "London",
        "GB",
        "Europe/London",
        "Sadler's Wells",
        emit_teachers=False,
    ),
    _Edition(
        10,
        "summer-intensive-tbilisi",
        "Tbilisi",
        "GE",
        "Asia/Tbilisi",
        "Tbilisi Opera and Ballet State Theatre",
        emit_teachers=True,
    ),
)


def scrape(client: httpx.Client) -> list[Offering]:
    offerings: list[Offering] = []
    for ed in _EDITIONS:
        course_url = f"{BASE}/courses.php?course={ed.course_id}"
        resp = client.get(course_url)
        resp.raise_for_status()
        course_html = resp.text

        # The course page links its own application form; fetch it for the poses.
        form_path = _apply_path(course_html)
        form_html = ""
        if form_path is not None:
            form_resp = client.get(f"{BASE}/{form_path}")
            form_resp.raise_for_status()
            form_html = form_resp.text

        offering = _build_offering(ed, course_url, course_html, form_html)
        if offering is not None:
            offerings.append(offering)
    offerings.sort(key=lambda o: o.id)
    return offerings


def _build_offering(
    ed: _Edition, course_url: str, course_html: str, form_html: str
) -> Offering | None:
    text = _body_text(course_html)
    headings = _heading_text(course_html)
    start, end = _date_range(headings)  # headings carry the authoritative dates
    anchor = start or end
    season = str(anchor.year) if anchor is not None else "unknown"

    form_path = _apply_path(course_html)
    apply_url = f"{BASE}/{form_path}" if form_path is not None else course_url

    return Offering(
        id=f"masters-of-ballet-academy/{ed.slug}-{season}",
        source=Source(provider="masters-of-ballet-academy", url=course_url, scrapedAt=now_utc()),
        title=_title(course_html, season),
        genres=_genres(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=_location(ed),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone=ed.timezone,
        ),
        teachers=_teachers(course_html) if ed.emit_teachers else [],
        prices=_prices(text),
        application=Application(
            url=apply_url,
            requirements=_requirements(form_html),
            notes=_requirement_note(text),
        ),
    )


# --- teachers: named faculty from the "FULL FACULTY:" section ----------------
#
# The page lists confirmed faculty under a "FULL FACULTY:" heading as bold
# `<h2>` or `<strong>` entries, each followed by a bio. Entries that say
# "to be announced" are skipped. London's roster mixes confirmed guests with
# unannounced ones, so we emit whoever has a full name here — the gate is
# whether a name is present, not presence on either specific course.


_FULL_FACULTY = re.compile(r"FULL FACULTY\s*:", re.IGNORECASE)
_TBA = re.compile(r"to be announced|TBA", re.IGNORECASE)


def _teachers(course_html: str) -> list[Teacher]:
    """Named confirmed faculty after the 'FULL FACULTY:' heading."""
    tree = HTMLParser(course_html)
    body = tree.body
    if body is None:
        return []
    # Collect all heading text (h2/strong) from the full-faculty block.
    full_text = body.text(separator="\n")
    m = _FULL_FACULTY.search(full_text)
    if m is None:
        return []
    faculty_block = full_text[m.end() :]
    teachers: list[Teacher] = []
    seen: set[str] = set()
    for h in tree.css("h2, strong"):
        text = parse.clean(h.text())
        if not text or _TBA.search(text):
            continue
        # Only consider headings that appear after "FULL FACULTY:" in the page
        # and look like a name (two+ words, no sentence punctuation).
        if text not in faculty_block:
            continue
        if len(text.split()) < 2 or any(c in text for c in ".,;?!:"):
            continue
        # Faculty names on this site are ALL CAPS (e.g. "ELENA GLURJIDZE"); title-case
        # or mixed-case text is an org name or heading, not a person — skip it.
        if text != text.upper():
            continue
        if text in seen:
            continue
        seen.add(text)
        teachers.append(Teacher(name=text))
    return teachers


# --- helpers ------------------------------------------------------------------


def _body_text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript, nav, header, footer"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _heading_text(html: str) -> str:
    """Just the `<h1>`/`<h2>` heading text, space-joined.

    Dates are parsed from here, not the body: the authoritative ranges live in
    headings, while the stale Tbilisi "Date: ...2025" line sits in a body
    paragraph and must not reach the date parser.
    """
    tree = HTMLParser(html)
    parts = [parse.clean(h.text()) for h in tree.css("h1, h2")]
    return " | ".join(p for p in parts if p)


# Only the *course-specific* CTA ("Click here to apply for this course") links the
# right form; the generic "How to Apply" nav link (forms.php?f=1) must be ignored.
def _apply_path(course_html: str) -> str | None:
    tree = HTMLParser(course_html)
    for a in tree.css("a[href*='forms.php']"):
        if "apply for this course" in parse.clean(a.text()).lower():
            href = a.attributes.get("href")
            if href:
                return href.lstrip("/")
    return None


def _title(course_html: str, season: str) -> str:
    """Place from the page `<h1>`, e.g. "SUMMER INTENSIVE COURSE 2026 - LONDON"."""
    tree = HTMLParser(course_html)
    h1 = tree.css_first("h1")
    place = ""
    if h1 is not None:
        match = re.search(r"-\s*([A-Za-z][A-Za-z ]*)", parse.clean(h1.text()))
        if match:
            place = parse.clean(match.group(1)).title()  # "TBILISI" → "Tbilisi"
    return f"Summer Intensive {season} — {place}" if place else f"Summer Intensive {season}"


# Dates come two shapes: a same-month heading range "19th - 25th July 2026" and a
# cross-month "Date:" line "27th of July to 1st of August 2026". The same-month
# form drops the month on the first day; the cross-month form carries it on both.
_RANGE_CROSS_MONTH = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + parse.MONTHALT + r")\s+to\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
_RANGE_SAME_MONTH = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s*[-–]\s*(\d{1,2})(?:st|nd|rd|th)?\s+("
    + parse.MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    start, end = parse.parse_multi_month_range(text, _RANGE_CROSS_MONTH)
    if start and end:
        return start, end
    same = _RANGE_SAME_MONTH.search(text)
    if same:
        d1, d2, month, year = same.groups()
        yr = int(year)
        mo = parse.MONTHS[month.lower()]
        return date(yr, mo, int(d1)), date(yr, mo, int(d2))
    return None, None


_AGE = re.compile(r"aged?\s+(\d{1,2})\s*[-–]\s*(\d{1,2})", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    return parse.extract_age_range(text, _AGE)


def _location(ed: _Edition) -> Location:
    return Location(venue=ed.venue_name, city=ed.venue_city, country=ed.venue_country)


# Genres keyword-matched against the syllabus the course pages name.
_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet", "classical")),
    ("contemporary", ("contemporary",)),
    ("neoclassical", ("neo-classical", "neo classical", "neoclassical")),
    ("character", ("character",)),
    ("repertoire", ("repertoire", "solos", "variations")),
    ("pointe", ("pointe",)),
]

# Both course page shapes state the class list in a single sentence:
# London: "Each N-hour day consists of …"
# Tbilisi: "timetable will include … curriculum, including …"
# Scoping to this sentence prevents teacher bios (e.g. "classical ballet
# repertoire" / "contemporary choreographer") from leaking genre keywords.
_SYLLABUS_SENTENCE = re.compile(
    r"(?:consists of|curriculum,\s*including)\s+([^.]+\.)",
    re.IGNORECASE,
)


def _syllabus_text(body: str) -> str:
    """The class-list sentence from the Syllabus or timetable section."""
    m = _SYLLABUS_SENTENCE.search(body)
    return m.group(0) if m else ""


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(_syllabus_text(text), _GENRE_KEYWORDS, default=["classical"])


# Prices: GBP tiers "JUNIORS ... - £250", "SENIORS ... - £750"; or "900 Euros".
_GBP = re.compile(
    r"(JUNIORS|SENIORS[^£]*|PRE[ -]?PROFESSIONALS?[^£]*)[^£]*£\s?([\d,]+)", re.IGNORECASE
)
_EUR = re.compile(r"(\d[\d,]*)\s*Euros?", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    for m in _GBP.finditer(text):
        amount = parse.parse_amount(m.group(2))
        if amount is None:
            continue
        label = _gbp_label(m.group(1))
        prices.append(
            Price(amount=amount, currency="GBP", label=label, includes=_TUITION),
        )
    if not prices:
        # No GBP tiers → a single EUR fee (Tbilisi). A £ figure may sit in
        # parentheses as a conversion, but EUR is the headline/local currency.
        m = _EUR.search(text)
        if m:
            amount = parse.parse_amount(m.group(1))
            if amount is not None:
                prices.append(
                    Price(amount=amount, currency="EUR", label="Course fee", includes=_TUITION),
                )
    return prices


_TUITION: list[PriceInclude] = ["tuition"]


def _gbp_label(raw: str) -> str:
    head = parse.clean(raw).lower()
    if "junior" in head:
        return "Juniors"
    return "Seniors / Pre-Professionals"


# Requirements: the application form names the photo positions.
def _requirements(form_html: str) -> list[Requirement]:
    if not form_html:
        return []
    text = _body_text(form_html)
    if "uploaded application photos" not in text.lower():
        return []
    poses = _poses(text)
    return [
        PhotosReq(
            specificity="defined-poses",
            poses=poses,
            notes=(
                "Selection is by uploaded application photos in the named positions (jpeg, ≤5mb)."
            ),
        )
    ]


# The form lists the positions as "1: ... 2: ... 3: ... 4: ..." in two groups (a
# non-pointe set and a pointe set), bracketed by "...5mb" and "How did you learn".
_POSE_REGION = re.compile(r"not exceed 5mb(.*?)How did you learn", re.IGNORECASE | re.DOTALL)
_POSE_ITEM = re.compile(r"\s*\d:\s*")


def _poses(text: str) -> list[str]:
    region = _POSE_REGION.search(text)
    if not region:
        return []
    poses: list[str] = []
    for raw in _POSE_ITEM.split(region.group(1)):
        pose = parse.clean(raw)
        if pose and pose not in poses:  # the two groups overlap; keep the union
            poses.append(pose)
    return poses


_JUNIOR_EXEMPT = re.compile(r"JUNIORS[^)]*NO PHOTO UPLOAD REQUIRED", re.IGNORECASE)


def _requirement_note(text: str) -> str | None:
    if _JUNIOR_EXEMPT.search(text):
        return "Juniors (8-10) are exempt from the photo upload."
    return None
