"""Academy of Northern Ballet (Leeds, GB) — its International Summer Intensives.

API FIRST: none usable. The site runs on **Drupal** and server-renders the
Academy pages, so the full text of each intensive is in the static HTML — a
two-page scrape (one per track), no JS needed.

DISCOVERY: the Academy's short-term student offering is the *International
Summer Intensives*, split into two tracks with their own dated page, ages,
price and photo brief — so we emit **one Offering per track**:
  - **Seniors** (16–19): a one-week intensive offered in two interchangeable
    weeks (students attend one or both), so its two weeks are `schedule.sessions`.
  - **Intermediates** (12–16): a single one-week course.
Term-time weekly Associate classes and full-time vocational training are *not*
short-term intensives and are deliberately out of scope. Each track is
season-keyed from its parsed course year so the id rolls forward yearly.

WHAT THE PAGES GIVE US (verified live 2026-06):
  - DATES: weekday-prefixed "Monday 27 July - Friday 31 July 2026" ranges (year
    on the closing date only). Seniors lists two such weeks; Intermediates one.
  - AGES: "Ages 16-19 Years" / "Ages 12-16 Years".
  - PRICES in GBP: Seniors £410/week and £745/two-weeks (tuition); Intermediates
    £375 (tuition) plus optional £48/night accommodation (the course is
    non-residential — accommodation is a separate, optional line, kept as such).
  - REQUIREMENTS — both tracks double as a photo audition with *named poses*
    (demi plié / tendu à la seconde / arabesque, the Seniors brief adding an
    "à la seconde en l'air"), plus an occasional video ("On occasion applicants
    may be asked to submit a short video") → a `video`/`unspecific` requirement.
  - DEADLINE: the closing date omits its year ("Friday 29 May"); we only set
    `application.deadline` when the stated weekday matches the parsed course year
    (it does for 2026), else we keep just the raw note — never an invented year.

WHAT THIS SCRAPER EXERCISES: two Offerings; multi-session schedule (Seniors);
several Prices with distinct `includes` (tuition vs accommodation); a defined-
poses `PhotosReq` plus an unspecific `VideoReq`; a derived-but-verified deadline.
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
    PhotosReq,
    Price,
    PriceInclude,
    Requirement,
    Schedule,
    Session,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://northernballet.com"
INTENSIVES = "/academy/workshops-events/international-summer-intensives"
SENIORS = f"{BASE}{INTENSIVES}/seniors"
INTERMEDIATES = f"{BASE}{INTENSIVES}/intermediates"

ORG = Organization(
    name="Academy of Northern Ballet",
    slug="northern-ballet-academy",
    country="GB",
    city="Leeds",
)

_VIDEO_NOTE = (
    "On occasion applicants may be asked to submit a short video as part of their application."
)


def scrape(client: httpx.Client) -> list[Offering]:
    offerings: list[Offering] = []
    for url, track in ((SENIORS, "Seniors"), (INTERMEDIATES, "Intermediates")):
        resp = client.get(url)
        resp.raise_for_status()
        offering = _build_offering(resp.text, url, track)
        if offering is not None:
            offerings.append(offering)
    return offerings


def _build_offering(html: str, url: str, track: str) -> Offering | None:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    sessions = _sessions(text)
    if not sessions:
        return None  # no dated edition announced
    start = min(s.start for s in sessions if s.start)
    end = max(s.end for s in sessions if s.end)
    season = str(end.year)

    return Offering(
        id=f"northern-ballet-academy/summer-intensive-{track.lower()}-{season}",
        source=Source(provider="northern-ballet-academy", url=url, scrapedAt=now_utc()),
        title=f"International Summer Intensive: {track} {season}",
        genres=_genres(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue="Northern Ballet", city="Leeds", country="GB"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/London",
            # A single-week course carries no extra signal as a one-item session
            # list; keep sessions only when there's a genuine choice of weeks.
            sessions=sessions if len(sessions) > 1 else [],
        ),
        prices=_prices(text),
        application=Application(
            url=_apply_url(html) or url,
            deadline=_deadline(text, end.year),
            requirements=_requirements(text),
            notes=_apply_note(text),
        ),
    )


# --- dates: weekday-prefixed "Monday 27 July - Friday 31 July 2026" weeks ------

# The closing year only on the trailing date; weekday words prefix each bound but
# aren't captured. The Intermediates page elides the first month ("Monday 27 -
# Friday 31 July 2026"), so the opening month is optional.
_WEEK = re.compile(
    r"\w+\s+(\d{1,2})(?:st|nd|rd|th)?\s+(?:(" + parse.MONTHALT + r")\s+)?"
    r"[-–—]\s*\w+\s+(\d{1,2})(?:st|nd|rd|th)?\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _sessions(text: str) -> list[Session]:
    sessions: list[Session] = []
    for i, m in enumerate(_WEEK.finditer(text), start=1):
        d1, m1, d2, m2, year = m.groups()
        end_month = parse.MONTHS[m2.lower()]
        start_month = parse.MONTHS[m1.lower()] if m1 else end_month
        start = date(int(year), start_month, int(d1))
        end = date(int(year), end_month, int(d2))
        label = f"Week {i}" if _has_two_weeks(text) else None
        sessions.append(Session(label=label, start=start, end=end))
    return sessions


def _has_two_weeks(text: str) -> bool:
    return bool(re.search(r"\bWeek 2\b", text, re.IGNORECASE))


# --- ages: "Ages 16-19 Years" / "Ages 12-16 Years" ----------------------------

_AGE = re.compile(r"ages?\s*(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*years?", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    m = _AGE.search(text)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


# --- prices: "One week £410", "Two weeks £745", "£375", "£48 per person per night"

_TUITION = re.compile(r"(One week|Two weeks)\s*£\s*(\d[\d.,]*)", re.IGNORECASE)
_FLAT = re.compile(r"\bPrice\b\s*£\s*(\d[\d.,]*)", re.IGNORECASE)
_ACCOM = re.compile(r"£\s*(\d[\d.,]*)\s*per person per night", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    tuition: list[PriceInclude] = ["tuition"]

    labelled = list(_TUITION.finditer(text))
    if labelled:
        for m in labelled:
            amount = parse.parse_amount(m.group(2))
            if amount is not None:
                prices.append(
                    Price(amount=amount, currency="GBP", label=m.group(1), includes=tuition)
                )
    else:
        flat = _FLAT.search(text)
        if flat:
            amount = parse.parse_amount(flat.group(1))
            if amount is not None:
                prices.append(Price(amount=amount, currency="GBP", includes=tuition))

    accom = _ACCOM.search(text)
    if accom:
        amount = parse.parse_amount(accom.group(1))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="GBP",
                    label="Accommodation (per person per night)",
                    includes=["accommodation"],
                    notes="Optional — the course is non-residential.",
                )
            )
    return prices


# --- genres: keyword-match the course-content syllabus ------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet class", "ballet technique")),
    ("contemporary", ("contemporary",)),
    ("repertoire", ("repertoire", "variations")),
    ("pointe", ("pointe",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- requirements: photo audition (named poses) + occasional video ------------

# Each pose line is "<orientation> – <pose description>"; we keep them verbatim.
_POSE_LINE = re.compile(
    r"((?:Facing the camera|Profile to the camera)\s*[-–—]\s*[^.]+?)"
    r"(?=\s*(?:Facing the camera|Profile to the camera|Apply Now|$))",
    re.IGNORECASE,
)


def _poses(text: str) -> list[str]:
    return [parse.clean(m.group(1)) for m in _POSE_LINE.finditer(text)]


def _requirements(text: str) -> list[Requirement]:
    reqs: list[Requirement] = []
    poses = _poses(text)
    if poses:
        reqs.append(
            PhotosReq(
                specificity="defined-poses",
                poses=poses,
                notes=(
                    "Photos uploaded with the application form; a studio is not "
                    "required (a small space at home, camera or smartphone, is fine)."
                ),
            )
        )
    if re.search(r"submit a short video", text, re.IGNORECASE):
        reqs.append(VideoReq(specificity="unspecific", description=_VIDEO_NOTE))
    return reqs


# --- deadline & notes: "Closing date for applications is Friday 29 May …" ------

_CLOSING = re.compile(
    r"Closing date for applications is\s+(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?\s+("
    + parse.MONTHALT
    + r")",
    re.IGNORECASE,
)
_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _deadline(text: str, year: int) -> date | None:
    """The closing date, only if the stated weekday confirms the course year.

    The page omits the deadline's year; we read it as the course year *only* when
    the named weekday matches that year's calendar — otherwise we leave it null
    and keep the raw text in `application.notes`, never inventing a year.
    """
    m = _CLOSING.search(text)
    if not m:
        return None
    weekday, day, month = m.groups()
    wd = _WEEKDAYS.get(weekday.lower())
    if wd is None:
        return None
    candidate = date(year, parse.MONTHS[month.lower()], int(day))
    return candidate if candidate.weekday() == wd else None


_NOTE = re.compile(r"(Closing date for applications is[^.]*\.)", re.IGNORECASE)


def _apply_note(text: str) -> str | None:
    m = _NOTE.search(text)
    return parse.clean(m.group(1)) if m else None


# --- application form URL (a per-track Wufoo form behind "Apply Now") ----------

_APPLY = re.compile(
    r'<a[^>]+href="([^"]+)"[^>]*>\s*Apply Now',
    re.IGNORECASE,
)


def _apply_url(html: str) -> str | None:
    m = _APPLY.search(html)
    return m.group(1) if m else None
