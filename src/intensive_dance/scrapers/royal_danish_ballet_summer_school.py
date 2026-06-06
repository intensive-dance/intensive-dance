"""Royal Danish Ballet Summer School (Det Kongelige Teater, Copenhagen, DK).

API FIRST: none usable. The site runs on ASP.NET/Umbraco behind BunnyCDN (not
WordPress — `/wp-json/` 404s) and the only embedded `application/ld+json` is the
org/breadcrumb graph, no schema.org `Course`/`Event`. But the Summer School lives
on a single, server-rendered page, so this is a one-page HTML scrape. We read the
English page (`hreflang="en"`); the Danish twin carries no field the EN page
lacks, so there is nothing to translate.

DISCOVERY: one `Offering` — the current Summer School. The page advertises a
two-programme split (Advanced / Elite), but both run on the *same* dates, ages,
fees and audition; the programmes differ only in technical level and a couple of
syllabus subjects (modern vs. contemporary), so we keep them as one Offering and
note the two programmes rather than emitting near-duplicate records. A separate
"pianist course" sub-page used to exist but now 404s, so there is no second
Offering to emit.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-05):
  - a two-week summer course running 20 Jul – 1 Aug 2026.
  - AGE band 12–21 (both bounds), `level` left empty — "Advanced"/"Elite" name the
    two internal programmes, not an admission level the source pins to the course.
  - GENRES from the curriculum list (classical ballet, Bournonville → character,
    repertoire, contemporary, pas de deux → none of the enum, Pilates → none).
  - PRICES in DKK: tuition (incl. VAT), optional lunch (meals), optional
    accommodation (15+ only), each a separate `Price`.
  - APPLICATION `closed` (deadline 20 Mar 2026 already past today); the offering
    itself still takes place, so `lifecycle` stays `scheduled`.
  - REQUIREMENTS: a video audition is required for all applicants (`video`,
    `unspecific` — the brief is just "a link to an audition video").
  - TEACHERS empty — the page repeats "Teachers will be announced soon".
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

BASE = "https://www.kglteater.dk"
PAGE = f"{BASE}/en/about-the-royal-danish-theatre/summerschool/"

ORG = Organization(
    name="The Royal Danish Theatre",
    slug="royal-danish-ballet-summer-school",
    country="DK",
    city="Copenhagen",
)

_VIDEO_BRIEF = "All applicants must upload a link to an audition video."


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE, follow_redirects=True)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    offering = _build_offering(resp.text, date.today())
    return [offering] if offering is not None else []


def _build_offering(html: str, today: date) -> Offering | None:
    text = _text(html)

    start, end = _date_range(text)
    anchor = start or end
    season = str(anchor.year) if anchor else "unknown"

    deadline = _deadline(text)
    return Offering(
        id=f"royal-danish-ballet-summer-school/summer-school-{season}",
        source=Source(provider="royal-danish-ballet-summer-school", url=PAGE, scrapedAt=now_utc()),
        title=f"Royal Danish Ballet Summer School {season}".strip(),
        genres=_genres(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(
            venue="The Royal Danish Theatre (Tordenskjoldsgade 8)",
            city="Copenhagen",
            country="DK",
        ),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Copenhagen",
            notes=_dates_note(text),
        ),
        prices=_prices(text),
        application=Application(
            status=_status(deadline, today),
            deadline=deadline,
            url=PAGE,
            requirements=_requirements(text),
            notes=_VIDEO_BRIEF,
        ),
    )


def _text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    raw = tree.body.text(separator=" ") if tree.body else ""
    return parse.clean(raw)


# --- dates: "20 July – 1 August 2026" (day-month, year only on the second) -----

_MONTHALT = parse.MONTHALT
# Two day-month pairs sharing a single trailing year — the year applies to both.
_RANGE = re.compile(
    r"Dates:\s*(\d{1,2})\s+("
    + _MONTHALT
    + r")\s*[-–—]\s*(\d{1,2})\s+("
    + _MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    return parse.parse_multi_month_range(text, _RANGE)


def _dates_note(text: str) -> str | None:
    m = _RANGE.search(text)
    return parse.clean(m.group(0)) if m else None


# --- ages: "aged 12-21" / "Minimum age … is 12 …, maximum is 21" ---------------

_AGE = re.compile(r"aged\s+(\d{1,2})\s*[-–—]\s*(\d{1,2})", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    return parse.extract_age_range(text, _AGE)


# --- genres: keyed off the stated curriculum, not loose prose ------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet class", "classical ballet", "ballet")),
    ("repertoire", ("repertoire",)),
    ("contemporary", ("contemporary", "modern dance")),
    # Bournonville is the Danish school's signature character-dance style.
    ("character", ("bournonville",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- prices: tuition (DKK), optional lunch, optional accommodation -------------

# "DKK 12.500" — Danish notation uses "." as the thousands separator.
_TUITION = re.compile(r"price for both weeks is\s*DKK\s*([\d.]+)", re.IGNORECASE)
_LUNCH = re.compile(r"Lunch[^:]*:\s*DKK\s*([\d.]+)\s*per week", re.IGNORECASE)
_ACCOM = re.compile(r"price is\s*DKK\s*([\d.]+)\s*DKK?\s*per student per week", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    # Danish "12.500" reads as a thousands-grouped integer (dot + exactly three
    # digits), which `parse.parse_amount` already handles.
    out: list[Price] = []
    if (m := _TUITION.search(text)) and (a := parse.parse_amount(m.group(1))) is not None:
        out.append(
            Price(
                amount=a,
                currency="DKK",
                label="Tuition (both weeks, incl. VAT)",
                includes=["tuition"],
            )
        )
    if (m := _LUNCH.search(text)) and (a := parse.parse_amount(m.group(1))) is not None:
        out.append(
            Price(
                amount=a,
                currency="DKK",
                label="Lunch (per week, optional)",
                includes=["meals"],
            )
        )
    if (m := _ACCOM.search(text)) and (a := parse.parse_amount(m.group(1))) is not None:
        out.append(
            Price(
                amount=a,
                currency="DKK",
                label="Accommodation at Suhrs Højskole (per week, ages 15+, optional)",
                includes=["accommodation"],
            )
        )
    return out


# --- application status / requirements ----------------------------------------

_DEADLINE = re.compile(
    r"deadline for application is\s*(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _deadline(text: str) -> date | None:
    m = _DEADLINE.search(text)
    if not m:
        return None
    day, month, year = m.groups()
    return date(int(year), parse.MONTHS[month.lower()], int(day))


def _status(deadline: date | None, today: date):
    if deadline and deadline < today:
        return "closed"
    return None


def _requirements(text: str) -> list[Requirement]:
    if re.search(r"audition video", text, re.IGNORECASE):
        return [VideoReq(specificity="unspecific", description=_VIDEO_BRIEF)]
    return []
