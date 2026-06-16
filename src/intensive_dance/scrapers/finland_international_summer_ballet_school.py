"""Finland International Summer Ballet School (FISBS) — Helsinki, FI.

API FIRST: none usable. The site (finsummerdance.com) runs on **Wix** — no public
content API we may use — but the pages are server-side rendered, so the full text
is in the static HTML (a plain httpx fetch returns it; no JS/proxy needed). Wix
peppers the markup with zero-width spaces, so we flatten each page to text and
strip those before parsing keywords/numbers rather than scrape garbled tokens
(the `brussels_international_ballet`/`young_stars_ballet` approach). Two pages
carry everything: `/course` (curriculum, levels+ages, fees, deadline, venue) and
the home page (edition number + year, the four weekly session dates, the ld+json
`LocalBusiness`, and the apply-form + tutor-schedule links).

DISCOVERY: the 2026 edition (the "12th") runs 22.6–18.7 in Helsinki as **four
consecutive one-week sessions** (22–27.6 / 29.6–4.7 / 6–11.7 / 13–18.7), each
running the same four-level curriculum but with a different guest-tutor roster.
We emit **one Offering per weekly session** (distinct dates + faculty), each
carrying the four levels as `Session` blocks so the per-level age bands survive
(Youth 9–12, Young 12–15+, Advanced/semi-pro/pro 16–25+, Adults open). Slugs are
year-stamped (the home title names the cycle, "12th Finland 2026"). The
multi-week fee options collapse into the per-week range; we don't fold the four
weeks into one Offering — that would lose each week's distinct faculty.

FACULTY: the home page links a Google Doc the school publishes as its 2026
schedule, whose "Tutors:" block maps each named tutor (with affiliation) to a
week. We read it as the authoritative per-week roster — fail-open: if it doesn't
fetch/parse, offerings still emit with empty `teachers` rather than guessing from
the noisy `/coaches` page (which mixes stale prior-edition entries).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-09):
  - One provider → four dated Offerings, each with four `Session` level blocks.
  - AGES on `Session`, not the Offering (each week runs all four levels), with an
    open-topped Adults block (null bounds) and an open-topped Advanced one (16+).
  - PRICES: per-week tuition range in EUR (low/high bounds as two `Price`s),
    `includes=["tuition"]` only — the page states accommodation/meals are NOT
    included.
  - GENRES matched against the structured curriculum list (Ballet / Pointe /
    Repertoire / Character / Contemporary-jazz), not loose prose.
  - APPLICATION: a Google-Form URL + a stated "before June 15th" payment deadline.
    `status` is left unset — the page states a deadline, not an application status;
    consumers derive closed-ness from deadline < today (deriving it here against
    today would also break the no-diff rule). Requirements `[]` (the form's
    contents aren't described on the public pages).
  - TEACHERS with `Affiliation` (company + role) parsed from the schedule doc.
"""

from __future__ import annotations

import html as _htmlmod
import re
from datetime import date

import httpx

from intensive_dance import parse
from intensive_dance.models import (
    Affiliation,
    Application,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Session,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.finsummerdance.com"
HOME = f"{BASE}/"
COURSE = f"{BASE}/course"
TZ = "Europe/Helsinki"

ORG = Organization(
    name="Finland International Summer Ballet School",
    slug="finland-international-summer-ballet-school",
    country="FI",
    city="Helsinki",
)

# Kaikukatu 4 A, 5th floor (Leipätehdas), home of Helsingin Tanssiopisto's studios.
LOCATION = Location(
    venue="Leipätehdas (Helsingin Tanssiopisto), Kaikukatu 4 A",
    city="Helsinki",
    country="FI",
)

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿­"))


def _text(html: str) -> str:
    """Flatten a Wix page to whitespace-collapsed visible text, zero-width stripped."""
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    stripped = re.sub(r"<[^>]+>", " ", html).translate(_ZERO_WIDTH)
    return parse.clean(_htmlmod.unescape(stripped))


def scrape(client: httpx.Client) -> list[Offering]:
    home = client.get(HOME)
    home.raise_for_status()
    course = client.get(COURSE)
    course.raise_for_status()
    doc = _fetch_schedule_doc(client, home.text)
    return _build_offerings(home.text, course.text, doc)


def _fetch_schedule_doc(client: httpx.Client, home_html: str) -> str:
    """The Google-Doc schedule the home page links, as plain text. Fail-open."""
    match = re.search(r"docs\.google\.com/document/d/([\w-]+)", home_html)
    if not match:
        return ""
    url = f"https://docs.google.com/document/d/{match.group(1)}/export?format=txt"
    try:
        resp = client.get(url)
        resp.raise_for_status()
    except httpx.HTTPError:
        return ""
    return resp.text.translate(_ZERO_WIDTH)


# --- the four weekly sessions ------------------------------------------------
#
# Day-day.month tokens on the home page; the year comes from the edition title.

_WEEK = re.compile(
    r"(\d{1,2})\s*-\s*(\d{1,2})\.(\d{1,2})|(\d{1,2})\.(\d{1,2})\s*-\s*(\d{1,2})\.(\d{1,2})"
)
_EDITION = re.compile(r"(\d{1,2})(?:th|st|nd|rd)\s+Finland\s+(\d{4})", re.IGNORECASE)


def _year(home_text: str) -> int | None:
    match = _EDITION.search(home_text)
    return int(match.group(2)) if match else None


def _weeks(home_text: str, year: int) -> list[tuple[date, date]]:
    """The four published one-week spans (22-27.6 / 29.6-4.7 / 6-11.7 / 13-18.7).

    Each token is either `d-d.m` (same month) or `d.m-d.m` (month crossing).
    Deduped + date-ordered; only well-formed weekly spans survive.
    """
    spans: list[tuple[date, date]] = []
    for raw in re.findall(r"\d{1,2}\.?\d?\s*-\s*\d{1,2}\.\d{1,2}", home_text):
        span = _week_span(raw, year)
        if span and span not in spans:
            spans.append(span)
    return sorted(spans)


def _week_span(raw: str, year: int) -> tuple[date, date] | None:
    m = _WEEK.fullmatch(raw.replace(" ", ""))
    if not m:
        return None
    try:
        if m.group(1):  # d - d . m  (same month)
            d1, d2, mo = int(m.group(1)), int(m.group(2)), int(m.group(3))
            start, end = date(year, mo, d1), date(year, mo, d2)
        else:  # d . m - d . m  (month crossing)
            d1, m1, d2, m2 = (int(m.group(g)) for g in (4, 5, 6, 7))
            start, end = date(year, m1, d1), date(year, m2, d2)
    except ValueError:
        return None
    # A real week runs forward over a handful of days; reject reversed/odd spans.
    if not 0 < (end - start).days <= 10:
        return None
    return start, end


# --- levels (as Session blocks) ----------------------------------------------
#
# The course page lists four fixed levels with age bands; every week runs all
# four, so they live on each Offering's `Session`s (carrying the ages), not on
# the Offering's own ageRange.

_LEVELS: list[tuple[str, Level, dict | None]] = [
    ("Intermediate / Youth", "intermediate", {"min": 9, "max": 12}),
    ("Intermediate / Young students", "intermediate", {"min": 12, "max": 15}),
    ("Advanced / Professional / Semi-professional", "advanced", {"min": 16, "max": 25}),
    ("Adult ballet classes — open level", "open", None),
]


def _sessions() -> list[Session]:
    return [Session(label=label, ageRange=ages, notes=label) for label, _, ages in _LEVELS]


def _levels() -> list[Level]:
    seen: list[Level] = []
    for _label, lvl, _ages in _LEVELS:
        if lvl not in seen:
            seen.append(lvl)
    return seen


# --- genres ------------------------------------------------------------------
#
# Matched against the structured "includes education in:" curriculum list only.

_CURRICULUM = re.compile(
    r"includes education in:?(.*?)(?:There will be|levels of)", re.IGNORECASE | re.DOTALL
)

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet", "classical")),
    ("pointe", ("pointe",)),
    ("repertoire", ("repertoire", "variation")),
    ("character", ("character",)),
    ("contemporary", ("contemporary", "jazz")),
]


def _genres(course_text: str) -> list[Genre]:
    match = _CURRICULUM.search(course_text)
    source = match.group(1) if match else course_text
    return parse.match_genres(source, _GENRE_KEYWORDS, default=["classical"])


# --- prices ------------------------------------------------------------------
#
# "Summer Ballet School Fee for 1 week in Helsinki: 150-475 eur" — a per-week
# range spanning the four levels. We emit the low and high bounds as two Prices.

_WEEK_FEE = re.compile(r"Fee for 1 week[^:]*:\s*(\d+)\s*-\s*(\d+)\s*eur", re.IGNORECASE)

_FEE_NOTE = (
    "Per-week tuition; spans level (adult open level to advanced). "
    "Accommodation and meals not included."
)


def _prices(course_text: str) -> list[Price]:
    match = _WEEK_FEE.search(course_text)
    if not match:
        return []
    low, high = float(match.group(1)), float(match.group(2))
    return [
        Price(
            amount=low,
            currency="EUR",
            label="From (per week)",
            includes=["tuition"],
            notes=_FEE_NOTE,
        ),
        Price(
            amount=high,
            currency="EUR",
            label="To (per week)",
            includes=["tuition"],
            notes=_FEE_NOTE,
        ),
    ]


# --- application -------------------------------------------------------------

_FORM = re.compile(r"https://forms\.gle/[\w-]+")
_DEADLINE = re.compile(r"before\s+June\s+(\d{1,2})", re.IGNORECASE)


def _apply_url(home_html: str) -> str | None:
    match = _FORM.search(home_html)
    return match.group(0) if match else None


def _deadline(course_text: str, year: int) -> date | None:
    match = _DEADLINE.search(course_text)
    return date(year, 6, int(match.group(1))) if match else None


# --- teachers (per week, from the linked schedule doc) -----------------------
#
# The doc's "Tutors:" block groups tutors under week headers (a date span line),
# each tutor as "Name (affiliation)". We key each tutor to its week's start date.

# A doc header opens with a week span in the same two shapes as the home tokens
# (`d-d.m` same-month or `d.m-d.m` month-crossing); we reuse `_week_span` to parse.
_DOC_WEEK = re.compile(r"^\s*(\d{1,2}\.?\d?\s*-\s*\d{1,2}\.\d{1,2})")
# A tutor is "First Last (affiliation)": the *two* capitalized alphabetic words
# immediately before the paren (alphabetic-only excludes schedule prefixes like
# "Mo-Fr-"). Names are upper- or title-case in the doc (e.g. "SERGEI UPKIN").
_NAME_WORD = r"[A-ZА-ЯÅÄÖ][A-Za-zА-Яа-яÅÄÖåäö'’]+"
_TUTOR = re.compile(rf"({_NAME_WORD}\s+{_NAME_WORD})\s*\(([^)]+)\)")
# Bare-place parentheticals ("(Stockholm)") aren't affiliations — only an org/role.
_PREPOSITION = re.compile(r"\b(?:with|of|at|from)\b\s+(?:the\s+)?", re.IGNORECASE)


def _doc_faculty(doc_text: str, year: int) -> dict[date, list[Teacher]]:
    """Map each week's start date -> tutors named in that week's doc block.

    The doc lists weeks 6-11.7 and 13-18.7 under one "6-18.7" header, so a tutor
    named there is attributed to both later weeks; we attach by start date and
    resolve at build time.
    """
    if "Tutors:" not in doc_text:
        return {}
    block = doc_text.split("Tutors:", 1)[1].split("SCHEDULE", 1)[0]
    by_week: dict[date, list[Teacher]] = {}
    current: list[date] = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        starts = _doc_week_starts(line, year)
        if starts:
            current = starts
            for s in starts:
                by_week.setdefault(s, [])
        for teacher in _line_teachers(line):
            for s in current:
                if teacher.name not in [t.name for t in by_week[s]]:
                    by_week[s].append(teacher)
    return by_week


def _doc_week_starts(line: str, year: int) -> list[date]:
    """Start dates a doc header line covers ("6-18.7" -> the 6.7 and 13.7 weeks)."""
    m = _DOC_WEEK.match(line)
    if not m:
        return []
    span = _doc_span(m.group(1), year)
    if span is None:
        return []
    start, end = span
    # A two-week header (6-18.7) seeds both contained weekly starts.
    if (end - start).days > 8:
        try:
            return [start, date(start.year, start.month, start.day + 7)]
        except ValueError:
            return [start]
    return [start]


def _doc_span(raw: str, year: int) -> tuple[date, date] | None:
    """Parse a header date token, allowing a longer (two-week) span than `_week_span`."""
    m = _WEEK.fullmatch(raw.replace(" ", ""))
    if not m:
        return None
    try:
        if m.group(1):  # d - d . m  (same month)
            start = date(year, int(m.group(3)), int(m.group(1)))
            end = date(year, int(m.group(3)), int(m.group(2)))
        else:  # d . m - d . m  (month crossing)
            start = date(year, int(m.group(5)), int(m.group(4)))
            end = date(year, int(m.group(7)), int(m.group(6)))
    except ValueError:
        return None
    return (start, end) if start < end else None


def _line_teachers(line: str) -> list[Teacher]:
    teachers: list[Teacher] = []
    for name, aff in _TUTOR.findall(line):
        affiliations = _affiliations(parse.clean(aff))
        teachers.append(Teacher(name=_title_name(name), affiliations=affiliations))
    return teachers


def _title_name(raw: str) -> str:
    """Normalize an all-caps doc name ("SERGEI UPKIN") to title case."""
    name = parse.clean(raw)
    return name.title() if name.isupper() else name


def _affiliations(text: str) -> list[Affiliation]:
    """ "ex-Principal Dancer with the X" -> [role X]; a bare place -> no affiliation."""
    m = _PREPOSITION.search(text)
    if not m:
        return []  # e.g. "(Stockholm)" — a place, not a company
    role = parse.clean(text[: m.start()]) or None
    org = parse.clean(text[m.end() :])
    if not org:
        return []
    return [Affiliation(organization=org, role=role)]


# --- build -------------------------------------------------------------------


def _build_offerings(home_html: str, course_html: str, doc_text: str) -> list[Offering]:
    home_text = _text(home_html)
    course_text = _text(course_html)

    year = _year(home_text)
    if year is None:
        return []

    weeks = _weeks(home_text, year)
    if not weeks:
        return []

    genres = _genres(course_text)
    levels = _levels()
    prices = _prices(course_text)
    apply_url = _apply_url(home_html)
    deadline = _deadline(course_text, year)
    faculty = _doc_faculty(doc_text, year)
    sessions = _sessions()

    offerings: list[Offering] = []
    for start, end in weeks:
        slug = f"summer-{start.year}-{start.month:02d}-{start.day:02d}"
        offerings.append(
            Offering(
                id=f"{ORG.slug}/{slug}",
                source=Source(provider=ORG.slug, url=HOME, scrapedAt=now_utc()),
                title=_title(start, end),
                genres=list(genres),
                level=list(levels),
                organization=ORG,
                location=LOCATION,
                schedule=Schedule(
                    season=str(start.year),
                    start=start,
                    end=end,
                    timezone=TZ,
                    sessions=list(sessions),
                ),
                teachers=faculty.get(start, []),
                prices=list(prices),
                application=Application(deadline=deadline, url=apply_url),
            )
        )
    return offerings


_MONTHS_EN = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


def _month_name(month: int) -> str:
    return _MONTHS_EN[month]


def _title(start: date, end: date) -> str:
    """Edition title with a month-crossing-aware date span."""
    if start.month == end.month:
        span = f"{start.day}–{end.day} {_month_name(start.month)} {start.year}"
    else:
        span = (
            f"{start.day} {_month_name(start.month)} – "
            f"{end.day} {_month_name(end.month)} {start.year}"
        )
    return f"Finland International Summer Ballet School — week of {span}"
