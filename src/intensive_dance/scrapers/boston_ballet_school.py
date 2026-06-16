"""Boston Ballet School — summer intensives — Boston (Massachusetts), US.

API FIRST — bostonballet.org is WordPress (`/wp-json/` 200) and the summer
programs are an `education-program` custom post type, but every one renders
*nothing* into `content.rendered` over the REST API — the body is assembled by a
page builder that the API leaves empty (the same SAB/ABT trap). So this is an
HTML scrape (selectolax) of the public summer pages, parsed from their collapsed
plain text with labeled regexes (markup-change-tolerant), not DOM position. No
proxy needed — a plain UA fetch is served the full markup.

DISCOVERY: BBS runs two distinct summer intensives, each its own dated edition(s):
  - Summer Dance Program (SDP) — one ~four-week edition, ages 12-18, the flagship
    high-level intensive. Its dates/ages/fees live on the "Tuition, Dates, and
    FAQ" page; the landing page names the cycle year + curriculum styles (→
    genres); the audition-tour page carries the video-audition window + status.
    → one Offering (`boston-ballet-school/summer-dance-program-{year}`).
  - Junior Summer Intensive (JSI) — ages 9-12, three separate two-week Sessions
    (distinct dates) at Walnut Hill School for the Arts, Natick MA. Each Session
    is its own Offering (`boston-ballet-school/junior-summer-intensive-s{n}-{year}`)
    because they differ in dates; ages/fees/curriculum are shared.
Out of scope, not emitted: Summer Camps (ages 2-9, recreational) and the Adult
Dance Program Intensive (ages 16+ adult, no audition).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - PRICES in USD, multiple per offering from a labeled fee line: SDP tuition
    (tuition) + Food/Housing (accommodation+meals) + optional Lunch Plan (meals)
    + registration; JSI tuition (tuition) + Residential Fees (accommodation+meals)
    + registration + activity. Inclusions keyed off the label, not position.
  - DATES from a weekday-prefixed range, year-less, stamped with the year read
    from the cycle title ("Summer Dance Program 2026") / the age clause
    ("as of August 31, 2026").
  - AGES from "ages of 12 … and 18" (SDP) / "ages of 9 and 12 on August 31, 2026"
    (JSI).
  - GENRES from the curriculum prose: classical base + character/modern (→
    contemporary) for both (the SDP styles live on its landing page, not the FAQ),
    plus jazz mention on JSI (not a register genre, so it doesn't add one). Pointe
    for JSI (pre-pointe/pointe curriculum).
  - REQUIREMENTS branch per program: SDP is by audition with an open in-person /
    video option → VideoReq(unspecific); JSI is application-only with three
    defined-pose photos + a headshot + a faculty recommendation letter →
    PhotosReq(defined-poses) + HeadshotReq + CVReq.
  - APPLICATION status/deadline: SDP — the in-person tour "has concluded" but
    video auditions are accepted "through Sunday, March 15" → deadline = that
    date; `status` stays unset while a video window is stated (the page gives a
    deadline, not a status — consumers derive closed-ness from deadline < today).
    Only an explicit "has concluded" with no remaining window reads as closed.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    ApplicationStatus,
    CVReq,
    Genre,
    HeadshotReq,
    Location,
    Offering,
    Organization,
    PhotosReq,
    Price,
    PriceInclude,
    Requirement,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://www.bostonballet.org"
TZ = "America/New_York"

SDP_URL = f"{BASE}/education/summer-dance-program/"
SDP_FAQ_URL = f"{BASE}/education/summer-dance-program/faq/"
SDP_AUDITION_URL = f"{BASE}/education/summer-dance-program/audition-tour/"
JSI_URL = f"{BASE}/education/junior-summer-intensive/"

ORG = Organization(
    name="Boston Ballet School",
    slug="boston-ballet-school",
    country="US",
    city="Boston",
)
SDP_LOCATION = Location(venue="Boston Ballet School", city="Boston", country="US")
JSI_LOCATION = Location(venue="Walnut Hill School for the Arts", city="Natick", country="US")


def scrape(client: httpx.Client) -> list[Offering]:
    landing = _fetch_text(client, SDP_URL)
    faq = _fetch_text(client, SDP_FAQ_URL)
    audition = _fetch_text(client, SDP_AUDITION_URL)
    jsi = _fetch_text(client, JSI_URL)
    return _build_offerings(landing, faq, audition, jsi)


def _fetch_text(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    resp.raise_for_status()
    return _page_text(resp.text)


def _page_text(html: str) -> str:
    """Collapse an HTML page to whitespace-normalized plain text (scripts/styles dropped)."""
    tree = HTMLParser(html)
    for node in tree.css("style, script"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ") if tree.body else "")


def _build_offerings(landing: str, faq: str, audition: str, jsi: str) -> list[Offering]:
    offerings: list[Offering] = []
    sdp = _build_sdp(landing, faq, audition)
    if sdp is not None:
        offerings.append(sdp)
    offerings.extend(_build_jsi(jsi))
    return offerings


# --- Summer Dance Program -----------------------------------------------------

# "Summer Dance Program 2026" — the cycle year.
_SDP_YEAR = re.compile(r"Summer Dance Program\s+(20\d\d)", re.IGNORECASE)
_WEEKDAY = r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
# The program opens at placement classes and ends on the last day of classes;
# both lines are weekday-prefixed and year-less.
_SDP_START = re.compile(
    r"Placement classes:\s*" + _WEEKDAY + r"(" + parse.MONTHALT + r")\s+(\d{1,2})",
    re.IGNORECASE,
)
_SDP_END = re.compile(
    r"Last day of classes[^:]*:\s*" + _WEEKDAY + r"(" + parse.MONTHALT + r")\s+(\d{1,2})",
    re.IGNORECASE,
)
# "between the ages of 12* and 18" — the eligibility floor/ceiling.
_SDP_AGE = re.compile(r"ages of\s+(\d{1,2})\D*?and\s+(\d{1,2})", re.IGNORECASE)


def _build_sdp(landing: str, faq: str, audition: str) -> Offering | None:
    year = _sdp_year(faq) or _sdp_year(landing) or _sdp_year(audition)
    start = _stamped(_SDP_START, faq, year)
    end = _stamped(_SDP_END, faq, year)
    if year is None or start is None:
        return None

    deadline = _sdp_deadline(audition, year)
    return Offering(
        id=f"boston-ballet-school/summer-dance-program-{year}",
        source=Source(provider=ORG.slug, url=SDP_FAQ_URL, scrapedAt=now_utc()),
        title="Summer Dance Program",
        genres=_sdp_genres(landing),
        ageRange=parse.extract_age_range(faq, _SDP_AGE),
        organization=ORG,
        location=SDP_LOCATION,
        schedule=Schedule(season=str(year), start=start, end=end, timezone=TZ),
        prices=_sdp_prices(faq),
        application=Application(
            status=_sdp_status(audition, deadline),
            deadline=deadline,
            url=SDP_AUDITION_URL,
            requirements=[
                VideoReq(
                    specificity="unspecific",
                    description=(
                        "Admission is by audition. Dancers attend an in-person audition "
                        "on the audition tour or, if unable to attend, submit a "
                        "pre-recorded video audition."
                    ),
                )
            ],
        ),
    )


def _sdp_year(text: str) -> int | None:
    m = _SDP_YEAR.search(text)
    return int(m.group(1)) if m else None


# SDP curriculum is classical-ballet led (over half the training hours) plus a
# broader spectrum named in the in-studio highlights: character, modern (→
# contemporary), choreography/improv. Keyword-matched against the page prose.
_SDP_GENRES: list[tuple[Genre, tuple[str, ...]]] = [
    ("character", ("character",)),
    ("contemporary", ("modern", "contemporary")),
]


def _sdp_genres(text: str) -> list[Genre]:
    return ["classical", *parse.match_genres(text, _SDP_GENRES, default=[])]


# SDP fee line: "Tuition: $3,620 (plus $100 registration fee) Food/Housing:
# $3,570 (residential students only) Lunch Plan : $320 (optional …)". The label
# colon can carry stray whitespace (the "Lunch Plan :" markup), so allow `\s*:`.
_SDP_PRICES: list[tuple[str, re.Pattern, list[PriceInclude]]] = [
    ("Tuition", re.compile(r"Tuition\s*:\s*\$([\d,]+)", re.IGNORECASE), ["tuition"]),
    (
        "Registration fee",
        re.compile(r"plus\s*\$([\d,]+)\s*registration fee", re.IGNORECASE),
        [],
    ),
    (
        "Food/Housing",
        re.compile(r"Food/Housing\s*:\s*\$([\d,]+)", re.IGNORECASE),
        ["accommodation", "meals"],
    ),
    ("Lunch Plan", re.compile(r"Lunch Plan\s*:\s*\$([\d,]+)", re.IGNORECASE), ["meals"]),
]


def _sdp_prices(text: str) -> list[Price]:
    return _prices_from(text, _SDP_PRICES)


# "video auditions will be accepted through Sunday March 15" — close of the
# video-application window (year-less; stamped with the cycle year).
_SDP_VIDEO_DEADLINE = re.compile(
    r"video auditions?\s+(?:will (?:now )?be|are)?\s*accepted through\s+"
    + _WEEKDAY
    + r"("
    + parse.MONTHALT
    + r")\s+(\d{1,2})",
    re.IGNORECASE,
)


def _sdp_deadline(text: str, year: int | None) -> date | None:
    return _stamped(_SDP_VIDEO_DEADLINE, text, year)


def _sdp_status(text: str, deadline: date | None) -> ApplicationStatus | None:
    """Faithful, source-stated status only. When the page says the audition tour
    "has concluded" and offers no remaining video window, that's an explicit
    closed signal. When a video deadline is still stated, we leave `status` unset
    (the page states a deadline, not a status) — consumers derive closed-ness from
    deadline < today, and deriving it here against today would break the no-diff
    rule since status is part of content_hash.
    """
    if "has concluded" in text.lower() and deadline is None:
        return "closed"
    return None


# --- Junior Summer Intensive --------------------------------------------------

# "ages of 9 and 12 on August 31, 2026" carries both the age band and the cycle
# year; the year-less session ranges are stamped with it.
_JSI_AGE_YEAR = re.compile(
    r"ages of\s+(\d{1,2})\s+and\s+(\d{1,2})\s+on\s+(?:"
    + parse.MONTHALT
    + r")\s+\d{1,2},\s*(20\d\d)",
    re.IGNORECASE,
)
# "Session 1: Classes Monday, June 22 through Friday, July 3 (weekdays only)" —
# the precise per-session span in the Session Schedules block (year-less).
_JSI_SESSION = re.compile(
    r"Session\s+(\d)\s*:\s*Classes\s+"
    + _WEEKDAY
    + r"("
    + parse.MONTHALT
    + r")\s+(\d{1,2})\s+through\s+"
    + _WEEKDAY
    + r"("
    + parse.MONTHALT
    + r")\s+(\d{1,2})",
    re.IGNORECASE,
)


def _build_jsi(text: str) -> list[Offering]:
    age_match = _JSI_AGE_YEAR.search(text)
    if age_match is None:
        return []
    age_min = int(age_match.group(1))
    age_max = int(age_match.group(2))
    year = int(age_match.group(3))

    genres = _jsi_genres(text)
    prices = _jsi_prices(text)
    requirements = _jsi_requirements()

    offerings: list[Offering] = []
    for match in _JSI_SESSION.finditer(text):
        num = match.group(1)
        start = date(year, parse.MONTHS[match.group(2).lower()], int(match.group(3)))
        end = date(year, parse.MONTHS[match.group(4).lower()], int(match.group(5)))
        offerings.append(
            Offering(
                id=f"boston-ballet-school/junior-summer-intensive-s{num}-{year}",
                source=Source(provider=ORG.slug, url=JSI_URL, scrapedAt=now_utc()),
                title=f"Junior Summer Intensive — Session {num}",
                genres=genres,
                ageRange={"min": age_min, "max": age_max},
                organization=ORG,
                location=JSI_LOCATION,
                schedule=Schedule(season=str(year), start=start, end=end, timezone=TZ),
                prices=prices,
                application=Application(url=JSI_URL, requirements=requirements),
            )
        )
    return offerings


# JSI: daily classical technique + pre-pointe/pointe curriculum + supplemental
# character, modern (→ contemporary), jazz. Jazz isn't a register genre, so it
# adds nothing; pointe and the character/modern styles do.
_JSI_GENRES: list[tuple[Genre, tuple[str, ...]]] = [
    ("pointe", ("pointe",)),
    ("character", ("character",)),
    ("contemporary", ("modern", "contemporary")),
]


def _jsi_genres(text: str) -> list[Genre]:
    return ["classical", *parse.match_genres(text, _JSI_GENRES, default=[])]


# JSI fee line: "Tuition: $2,200 (plus $70 registration fee) Residential Fees:
# $2,500 (plus $200 activity fee)".
_JSI_PRICES: list[tuple[str, re.Pattern, list[PriceInclude]]] = [
    ("Tuition", re.compile(r"Tuition\s*:\s*\$([\d,]+)", re.IGNORECASE), ["tuition"]),
    (
        "Registration fee",
        re.compile(r"plus\s*\$([\d,]+)\s*registration fee", re.IGNORECASE),
        [],
    ),
    (
        "Residential Fees",
        re.compile(r"Residential Fees\s*:\s*\$([\d,]+)", re.IGNORECASE),
        ["accommodation", "meals"],
    ),
    (
        "Activity fee",
        re.compile(r"plus\s*\$([\d,]+)\s*activity fee", re.IGNORECASE),
        [],
    ),
]


def _jsi_prices(text: str) -> list[Price]:
    return _prices_from(text, _JSI_PRICES)


def _jsi_requirements() -> list[Requirement]:
    """JSI is application-only: defined-pose photos + a headshot + a faculty
    recommendation letter.
    """
    return [
        PhotosReq(
            specificity="defined-poses",
            poses=[
                "First position with preparatory arms",
                "Tendu à la seconde (en face)",
                "Relevé in first position (centre; barre if en pointe less than one year)",
            ],
            notes="Required of all applicants; a pointe pose for students en pointe this summer.",
        ),
        HeadshotReq(),
        CVReq(),
    ]


# --- shared helpers -----------------------------------------------------------


def _stamped(pattern: re.Pattern, text: str, year: int | None) -> date | None:
    """Resolve a year-less `(month, day)` regex hit to a date with the cycle year."""
    m = pattern.search(text)
    if m is None or year is None:
        return None
    return date(year, parse.MONTHS[m.group(1).lower()], int(m.group(2)))


def _prices_from(text: str, table: list[tuple[str, re.Pattern, list[PriceInclude]]]) -> list[Price]:
    prices: list[Price] = []
    for label, pattern, includes in table:
        m = pattern.search(text)
        if m is None:
            continue
        amount = parse.parse_amount(m.group(1))
        if amount is None:
            continue
        prices.append(Price(amount=amount, currency="USD", label=label, includes=list(includes)))
    return prices
