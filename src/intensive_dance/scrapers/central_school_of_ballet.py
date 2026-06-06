"""Central School of Ballet (London) — multiple intensives in one prose page.

API FIRST: Central runs WordPress and serves a 200 from `/wp-json/`, so the body
comes straight from the REST API — no HTML scraping of the live site. There is no
course custom post type: the intensives live in a single editorial *page*
(`/wp-json/wp/v2/pages/24340`, slug `ballet-intensives`), and the JSON-LD on the
page carries no `Event`/`Course`, so the offering data is the page's
`content.rendered`. Unlike the WPBakery houses, Central uses a custom block theme,
so the body is plain semantic HTML (`<h2>`/`<h4>` headings, no shortcodes) — we
section it on those headings directly rather than via `wp.parse`'s shortcode path.

DISCOVERY: one page body holds several offerings, each introduced by an `<h2>`
("International Summer Courses", "Autumn Audition Preparation Course", "Spring
Course"), with `<h4>` sub-blocks underneath ("Entry Requirements", "Course Dates",
"Cost", "Application …", "Course Outline"). A splitter cuts the body at each `<h2>`
into one block per offering. The summer `<h2>` lists three distinct course tracks
(one-week 14-16, one-week 11-13, two-week 11-16) with their own dates / ages /
fees — we emit one Offering per track so none of that is folded away. The other
two `<h2>`s are a single offering each. The companion "11+ years" page (id 1854)
lists the one-day intensives (One Day Ballet Intensive 11-13 / 14-16, Dance Days,
…); as of 2026-06-05 every one of those has already happened, so under the
drop-ended rule none are emitted and we don't read that page.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-05):
  - REQUIREMENTS = PHOTOS, defined-poses. Application asks for five named poses
    (demi plié 1st, tendu devant effacé, tendu à la seconde, first arabesque,
    fourth croisé on pointe) — emitted as `photos`/`defined-poses` with the poses
    listed. Not every offering states them (Autumn doesn't), so those stay `[]`.
  - PRICES carry includes=["tuition"] and a note that accommodation/meals are not
    provided. Seasonal "To be announced" fees (Autumn, Spring) → no Price.
  - DATES are British ("Mon 27 July – Sat 1 August 2026"); Spring is "To be
    announced", so its start/end stay null and season reads "unknown" (fail-open).
  - LEVEL: RAD-grade prerequisites map to `pre-professional` (vocational-audition
    prep). AGE comes from the "aged 11-16" / school-year wording.
  - TEACHERS: none emitted — Central credits "Central's ballet teaching faculty"
    / "degree course tutors" generically, with no named individuals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import httpx
from selectolax.parser import HTMLParser, Node

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    PhotosReq,
    Price,
    Requirement,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.centralschoolofballet.co.uk"
PAGE_ID = 24340
PAGE_URL = f"{BASE}/dance-classes-courses/short-courses/ballet-intensives/"
APPLY_URL = f"{BASE}/applications/summer-course-application-form/"

ORG = Organization(
    name="Central School of Ballet", slug="central-school-of-ballet", country="GB", city="London"
)
LOCATION = Location(city="London", country="GB")

# Course Outline prose names the disciplines actually taught, so genres are
# keyword-matched against that (not the marketing blurb). Pointe work is always
# present for the girls; jazz/character are "subject to length", so only emitted
# where the outline names them.
_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("contemporary", ("contemporary",)),
    ("repertoire", ("repertoire", "rep ")),
    ("character", ("character",)),
    ("pointe", ("pointe",)),
]

# The five poses Central asks applicants to photograph, in page order.
_POSES = [
    "Demi plié in first position, arms in 2nd",
    "Tendu devant efface (open position), arms in 2nd",
    "Tendu à la seconde arms in 2nd",
    "First arabesque, en l'air (facing side)",
    "Fourth croisé on pointe, arms in 5th",
]

_ACCOMMODATION_NOTE = "Accommodation and meals are not provided."


@dataclass
class _Block:
    """An `<h2>` offering heading and the block nodes that follow it."""

    heading: str
    nodes: list[Node]

    def field(self, *headings: str) -> str:
        """Text of the paragraphs under the first matching `<h4>`, until the next heading."""
        wants = [h.lower() for h in headings]
        capturing = False
        out: list[str] = []
        for node in self.nodes:
            if node.tag in {"h3", "h4", "h5", "h6"}:
                capturing = any(w in node.text(strip=True).lower() for w in wants)
                continue
            if capturing:
                line = parse.clean(node.text(separator=" "))
                if line:
                    out.append(line)
        return "\n".join(out)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(f"{BASE}/wp-json/wp/v2/pages/{PAGE_ID}", params={"_fields": "content"})
    resp.raise_for_status()
    return _build_offerings(resp.json()["content"]["rendered"], date.today())


def _build_offerings(rendered: str, today: date) -> list[Offering]:
    offerings: list[Offering] = []
    for block in _split_offerings(rendered):
        offerings.extend(_offering_from_block(block, today))
    offerings.sort(key=lambda o: o.id)
    return offerings


def _split_offerings(rendered: str) -> list[_Block]:
    """Cut the page body into one `_Block` per top-level offering (`<h2>`)."""
    body = HTMLParser(rendered).body
    if body is None:
        return []
    tags = {"h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "table"}
    blocks: list[_Block] = []
    current: _Block | None = None
    for node in body.traverse(include_text=False):
        if node.tag not in tags:
            continue
        if node.tag == "h2":
            heading = node.text(strip=True)
            if not heading:
                continue
            current = _Block(heading=heading, nodes=[])
            blocks.append(current)
        elif current is not None:
            current.nodes.append(node)
    return blocks


# --- one offering block → Offering(s) -----------------------------------------


def _offering_from_block(block: _Block, today: date) -> list[Offering]:
    head = block.heading.lower()
    if "summer" in head:
        return _summer_offerings(block, today)
    if "autumn" in head:
        return _single_offering(block, "autumn-audition-preparation", today)
    if "spring" in head:
        return _single_offering(block, "spring-course", today)
    return []


# Each summer track: slug suffix, label, the line in "Course Dates" that carries
# its span, and the cost line that carries its fee. Splitting here keeps the three
# tracks' distinct dates / ages / prices instead of folding them into one record.
_SUMMER_TRACKS = [
    ("summer-week-one", "One week course (14-16 years)", "week one", "One week course"),
    ("summer-week-two", "One week course (11-13 years)", "week two", "One week course"),
    ("summer-two-week", "Two week course (11-16 years)", "two week", "Two week course"),
]


def _summer_offerings(block: _Block, today: date) -> list[Offering]:
    dates_text = block.field("Course Date")
    cost_text = block.field("Cost")
    outline = block.field("Course Outline")
    entry = block.field("Entry Requirements")
    photos = block.field("Application Photos")
    deadline_note = block.field("Application Deadline") or None

    offerings: list[Offering] = []
    for suffix, label, date_key, cost_key in _SUMMER_TRACKS:
        start, end = _track_dates(dates_text, date_key)
        if _ended(end, today):
            continue
        offerings.append(
            _make_offering(
                slug=suffix,
                title=f"International Summer Course — {label}",
                outline=outline,
                entry=entry,
                photos=photos,
                start=start,
                end=end,
                dates_note=dates_text or None,
                price=_track_price(cost_text, cost_key, label),
                deadline_note=deadline_note,
            )
        )
    return offerings


def _single_offering(block: _Block, slug: str, today: date) -> list[Offering]:
    dates_text = block.field("Course Date")
    start, end = _date_range(dates_text)
    if _ended(end, today):
        return []
    deadline = block.field("Application Deadline", "Application Dates", "Application Outcome")
    return [
        _make_offering(
            slug=slug,
            title=block.heading,
            outline=block.field("Course Outline"),
            entry=block.field("Entry Requirements"),
            photos=block.field("Application Photos"),
            start=start,
            end=end,
            dates_note=dates_text or None,
            price=_single_price(block.field("Cost")),
            deadline_note=deadline or None,
        )
    ]


def _make_offering(
    *,
    slug: str,
    title: str,
    outline: str,
    entry: str,
    photos: str,
    start: date | None,
    end: date | None,
    dates_note: str | None,
    price: Price | None,
    deadline_note: str | None,
) -> Offering:
    season = str(start.year) if start else "unknown"
    return Offering(
        id=f"central-school-of-ballet/{slug}",
        source=Source(provider="central-school-of-ballet", url=PAGE_URL, scrapedAt=now_utc()),
        title=title,
        genres=_genres(outline),
        level=["pre-professional"] if _has_grade_prereq(entry) else [],
        ageRange=_age_range(f"{title}\n{entry}"),
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(season=season, start=start, end=end, notes=dates_note),
        prices=[price] if price else [],
        application=Application(
            url=APPLY_URL,
            requirements=_requirements(photos),
            notes=deadline_note,
        ),
    )


# --- field parsing ------------------------------------------------------------


def _genres(outline: str) -> list[Genre]:
    # Ballet ("daily ballet") is the spine of every course, so classical is
    # always present — not just a fallback. match_genres' `default` fires only
    # when nothing matches, which dropped classical whenever a secondary style
    # (contemporary/pointe/…) was found alongside it.
    extras = parse.match_genres(outline, _GENRE_KEYWORDS, default=[])
    return ["classical", *(g for g in extras if g != "classical")]


_GRADE = re.compile(r"\bRAD\b", re.IGNORECASE)


def _has_grade_prereq(entry: str) -> bool:
    return bool(_GRADE.search(entry))


_AGE = re.compile(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*years?", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    return parse.extract_age_range(text, _AGE)


def _requirements(photos: str) -> list[Requirement]:
    if not photos:
        return []
    return [PhotosReq(specificity="defined-poses", poses=list(_POSES), notes=parse.clean(photos))]


# --- prices -------------------------------------------------------------------

_PRICE_LINE = re.compile(r"£\s?([\d,]+)")


def _single_price(cost_text: str) -> Price | None:
    """A standalone offering states one fee, e.g. "£68" or "To be announced"."""
    match = _PRICE_LINE.search(cost_text)
    if not match:
        return None
    amount = parse.parse_amount(match.group(1))
    if amount is None:
        return None
    return Price(
        amount=amount,
        currency="GBP",
        label="Course fee",
        includes=["tuition"],
        notes=_ACCOMMODATION_NOTE,
    )


def _track_price(cost_text: str, cost_key: str, label: str) -> Price | None:
    """Pull the fee for a named summer track from the multi-line Cost block.

    The Cost block reads "One week course £525 Two week course £820 …"; we anchor
    on the track's wording and take the first £-amount after it.
    """
    low = cost_text.lower()
    idx = low.find(cost_key.lower())
    if idx == -1:
        return None
    match = _PRICE_LINE.search(cost_text, idx)
    if not match:
        return None
    amount = parse.parse_amount(match.group(1))
    if amount is None:
        return None
    return Price(
        amount=amount,
        currency="GBP",
        label=label,
        includes=["tuition"],
        notes=_ACCOMMODATION_NOTE,
    )


# --- dates --------------------------------------------------------------------
#
# British "[Weekday] D Month – [Weekday] D Month YYYY" ranges, e.g.
# "Monday 27 July – Saturday 1 August 2026". A weekday name may precede either
# date and is skipped; the year sits on the end date only. Summer lists several
# such ranges in one paragraph, each prefixed by a track label ("Week one …",
# "Two week courses: …").

_WEEKDAY = r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\s+"
_RANGE = re.compile(
    r"(?:" + _WEEKDAY + r")?(\d{1,2})\s+(" + parse.MONTHALT + r")"
    r"\s*[–-]\s*"
    r"(?:" + _WEEKDAY + r")?(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    return parse.parse_multi_month_range(text, _RANGE)


def _track_dates(text: str, date_key: str) -> tuple[date | None, date | None]:
    """The date range whose line names `date_key` (e.g. "week one", "two week")."""
    low = text.lower()
    idx = low.find(date_key.lower())
    if idx == -1:
        return None, None
    return parse.parse_multi_month_range(text[idx:], _RANGE)


def _ended(end: date | None, today: date) -> bool:
    return end is not None and end < today
