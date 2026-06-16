"""Ballet Ireland — the national company's public Summer Intensive (Dublin).

API FIRST: Ballet Ireland runs WordPress. `GET /wp-json/` is 200 (its `name`
is "Ballet Ireland", `description` "The National Ballet of Ireland"), so the
body comes straight from the REST API — no HTML scraping of the live site. The
Summer Intensive lives in a single editorial *page* (`/wp-json/wp/v2/pages/1308`,
slug `summer-intensive`); there is no course custom post type and the JSON-LD
carries no `Event`/`Course`, so the offering data is the page's
`content.rendered`. The page is built with **Divi** (`[et_pb_*]` shortcodes), not
WPBakery, so `wp.parse` (which keys WPBakery sections by heading) doesn't fit:
the whole summary sits in one `[et_pb_text]` block and the faculty in
`[et_pb_team_member name=… position=…]` shortcode *attributes* that a
shortcode-stripping parse would discard. So we strip the Divi shortcodes to plain
text for the summary, and regex the team-member attributes for the roster. A
plain fetch with our scraper UA returns 200 (a truncated `Mozilla/5.0` UA trips
the WAF, but our real UA does not) — **no proxy needed**.

DISCOVERY: the page advertises one intensive run as **two selectable weeks**
("Week 1: Monday 27 July … Week 2: Tuesday 4 August …"); a student can take
either week or both. The two weeks share everything (venue, ages, level, fee,
faculty) but have **distinct dates and booking state** ("Week 1 … – Fully
Booked"), so we emit **one Offering per week** — folding them would lose the
per-week dates and the closed booking window. Ids are
`ballet-ireland/summer-intensive-week-{n}-{year}`.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - TEACHERS without affiliations — a named six-tutor roster (Anne Maher, Filipe
    Portugal, Fiona Brockway, Kate Lyons, Dominic Harrison on "Ballet &
    Repertoire"; Hayley Cunningham on "Pilates"), each with a role but no stated
    institution, so `affiliations` stays empty (faithful: the page gives no bios).
  - APPLICATION.STATUS from listing text — "Fully Booked" on a week maps to
    `closed` (the cycle is kept, not dropped); a silent week stays `None`.
    Booking is by registration + payment form, no audition stated, so
    `requirements` is `[]`.
  - OPEN-TOPPED AGE — "FOR AGES: 12+" → `{"min": 12, "max": None}`.
  - LEVEL across a span — "GRADE 4 to PROFESSIONAL" → pre-professional +
    professional (an RAD-grade prerequisite, open through the working level).
  - PRICE in EUR — "€300 per week", tuition only, on each week's Offering.
"""

from __future__ import annotations

import html
import re
from datetime import date

import httpx

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.balletireland.ie"
PAGE_ID = 1308
PAGE_URL = f"{BASE}/join-in/summer-intensive/"

ORG = Organization(name="Ballet Ireland", slug="ballet-ireland", country="IE", city="Dublin")

# The summary names the disciplines actually taught ("ballet, pointe work and
# repertoire", plus a daily Pilates warm-up). Ballet is the spine, so classical
# is always present; pointe/repertoire are added when the prose names them.
_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("repertoire", ("repertoire", "repertory")),
    ("pointe", ("pointe",)),
]


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(f"{BASE}/wp-json/wp/v2/pages/{PAGE_ID}", params={"_fields": "content"})
    resp.raise_for_status()
    return _build_offerings(resp.json()["content"]["rendered"], date.today())


def _build_offerings(rendered: str, today: date) -> list[Offering]:
    summary = _summary_text(rendered)
    teachers = _teachers(rendered)
    ages = _age_range(summary)
    levels = _levels(summary)
    genres = _genres(summary)
    location = _location(summary)
    price = _price(summary)

    offerings: list[Offering] = []
    for week in _weeks(summary):
        season = str(week.start.year) if week.start else "unknown"
        offerings.append(
            Offering(
                id=f"ballet-ireland/summer-intensive-week-{week.number}-{season}",
                source=Source(provider="ballet-ireland", url=PAGE_URL, scrapedAt=now_utc()),
                title=f"Summer Intensive — Week {week.number} {season}",
                genres=genres,
                level=levels,
                ageRange=ages,
                organization=ORG,
                location=location,
                schedule=Schedule(season=season, start=week.start, end=week.end, notes=week.notes),
                teachers=teachers,
                prices=[price] if price else [],
                application=Application(
                    status="closed" if week.fully_booked else None,
                    url=PAGE_URL,
                    notes=week.notes if week.fully_booked else None,
                ),
            )
        )
    offerings.sort(key=lambda o: o.id)
    return offerings


# --- summary text -------------------------------------------------------------
#
# The whole offering summary sits in one Divi `[et_pb_text]` block. Stripping the
# `[et_pb_*]` shortcodes and the HTML tags leaves clean prose; the Divi builder
# uses curly quotes in attributes, so we normalize them before stripping.

_SHORTCODE = re.compile(r"\[/?[a-z][^\]]*\]", re.IGNORECASE)


def _summary_text(rendered: str) -> str:
    text = html.unescape(rendered).replace("“", '"').replace("”", '"')
    text = _SHORTCODE.sub(" ", text)
    # Drop <style>/<script>/<form> blocks whole — their body sits *between* the
    # tags, so the generic tag strip below would leave the raw CSS/JS/field-label
    # text as content (the embedded Gravity Forms registration form leaked ~11k
    # chars of CSS + every form field label and country-dropdown option into a
    # week's notes).
    text = re.sub(
        r"<(style|script|form)\b[^>]*>.*?</\1>", " ", text, flags=re.IGNORECASE | re.DOTALL
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # The page ends with a faculty section + the embedded registration form's
    # heading/field labels (the form body is stripped above, but its surrounding
    # gform heading text survives). None of it is per-week info and it has no
    # closing "Week N:" terminator, so it lands in the last week's notes — cut it.
    # Teachers come from `_teachers(rendered)`, so dropping this tail is safe.
    return re.split(r"\bFACULTY\b", text, maxsplit=1)[0].strip()


# --- weeks / dates ------------------------------------------------------------
#
# "Week 1: Monday 27 July to Friday 31 July 2026 – Fully Booked  Week 2: Tuesday
# 4 August to Saturday 8 August 2026". The year sits on the end date of each
# span; "Fully Booked" trails the week it applies to (until the next "Week N:").


class _Week:
    def __init__(
        self,
        number: int,
        start: date | None,
        end: date | None,
        notes: str,
        fully_booked: bool,
    ) -> None:
        self.number = number
        self.start = start
        self.end = end
        self.notes = notes
        self.fully_booked = fully_booked


_WEEKDAY = r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\s+"
_RANGE = re.compile(
    r"(?:" + _WEEKDAY + r")?(\d{1,2})\s+(" + parse.MONTHALT + r")"
    r"\s+to\s+"
    r"(?:" + _WEEKDAY + r")?(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
_WEEK = re.compile(r"Week\s+(\d+)\s*:", re.IGNORECASE)


def _weeks(summary: str) -> list[_Week]:
    """One `_Week` per "Week N:" label, sliced to the text before the next label."""
    markers = list(_WEEK.finditer(summary))
    weeks: list[_Week] = []
    for i, marker in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(summary)
        chunk = summary[marker.start() : end]
        start, dend = _date_range(chunk)
        notes = re.sub(r"\s+", " ", chunk).strip(" .–-")
        weeks.append(
            _Week(
                number=int(marker.group(1)),
                start=start,
                end=dend,
                notes=notes,
                fully_booked="fully booked" in chunk.lower(),
            )
        )
    return weeks


def _date_range(text: str) -> tuple[date | None, date | None]:
    return parse.parse_multi_month_range(text, _RANGE)


# --- ages / level / genres / location / price ---------------------------------

_AGE_OPEN = re.compile(r"FOR AGES:\s*(\d{1,2})\s*\+", re.IGNORECASE)
_AGE_RANGE = re.compile(r"FOR AGES:\s*(\d{1,2})\s*[-–]\s*(\d{1,2})", re.IGNORECASE)


def _age_range(summary: str) -> dict | None:
    span = _AGE_RANGE.search(summary)
    if span:
        return {"min": int(span.group(1)), "max": int(span.group(2))}
    open_top = _AGE_OPEN.search(summary)
    if open_top:
        return {"min": int(open_top.group(1)), "max": None}
    return None


def _levels(summary: str) -> list[Level]:
    """ "GRADE 4 to PROFESSIONAL" — an RAD-grade prerequisite open through the
    professional level → pre-professional + professional."""
    low = summary.lower()
    levels: list[Level] = []
    if re.search(r"grade\s*\d", low):
        levels.append("pre-professional")
    if "professional" in low:
        levels.append("professional")
    return levels


def _genres(summary: str) -> list[Genre]:
    extras = parse.match_genres(summary, _GENRE_KEYWORDS, default=[])
    return ["classical", *(g for g in extras if g != "classical")]


# Venue line in the summary: "DanceHouse, Foley Street, Dublin 1". We anchor on
# the known venue name rather than absolute position.
_VENUE = re.compile(r"(DanceHouse[^.]*?Dublin\s*\d+)", re.IGNORECASE)


def _location(summary: str) -> Location:
    match = _VENUE.search(summary)
    venue = parse.clean(match.group(1)) if match else None
    return Location(venue=venue, city="Dublin", country="IE")


_PRICE = re.compile(r"PRICE:\s*€\s?([\d,.]+)\s*(per\s+week)?", re.IGNORECASE)


def _price(summary: str) -> Price | None:
    match = _PRICE.search(summary)
    if not match:
        return None
    amount = parse.parse_amount(match.group(1))
    if amount is None:
        return None
    per_week = bool(match.group(2))
    return Price(
        amount=amount,
        currency="EUR",
        label="Tuition per week" if per_week else "Tuition",
        includes=["tuition"],
        notes="Per week; a student may book either week or both." if per_week else None,
    )


# --- faculty ------------------------------------------------------------------
#
# Faculty are Divi team-member shortcodes carrying name + position as attributes
# (the bio body is empty), so we read the attributes directly. Curly quotes are
# normalized to straight ones first.

_TEAM = re.compile(
    r'\[et_pb_team_member\b[^\]]*?name="([^"]+)"[^\]]*?position="([^"]*)"',
    re.IGNORECASE,
)


def _teachers(rendered: str) -> list[Teacher]:
    text = html.unescape(rendered).replace("“", '"').replace("”", '"')
    teachers: list[Teacher] = []
    seen: set[str] = set()
    for raw_name, raw_role in _TEAM.findall(text):
        name = parse.clean(raw_name)
        if not name or name in seen:
            continue
        seen.add(name)
        role = parse.clean(raw_role) or None
        teachers.append(Teacher(name=name, role=role))
    return teachers
