"""Nederlands Dans Theater (NDT) Summer Intensive — The Hague, NL.

API FIRST: ndt.nl runs WordPress (Yoast SEO meta, wp-json oembed links visible in
HTML), but the WP REST API is locked behind authentication (GET /wp-json/wp/v2/types
returns HTTP 401 "Only authenticated users can access the REST API"). No structured
ld+json Event/Course block present on the intensive page, and no __NEXT_DATA__.
Fall-through to HTML parsing (selectolax) of the primary public-facing page:
https://www.ndt.nl/en/ndt-summer-intensive/

DISCOVERY: one offering per dated edition. The `/en/ndt-summer-intensive/` page
embeds all key facts: course dates, age range, tuition, accommodation fee, and
application timeline. Supplementary application details (video requirements, full
deadline list) are cross-checked against:
  /en/audition-procedure-ndt-summer-intensive/
Both pages are server-rendered (no JS required) and accessible without a proxy.
One Offering is emitted per year when dates are found on the main info page.
Year-stamp the slug because the source distinguishes editions by year.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
- HTML parsing via selectolax (WP REST unavailable)
- contemporary-only genre (NDT is a contemporary dance company; no classical)
- pre-professional + open level (ages 16–25 means overlapping bands)
- two Price objects: tuition + optional accommodation
- VideoReq with specificity="specific" (video with defined constraints: max 6 min,
  no pointe work, visible and solo)
- Application with deadline and opensAt from the source
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
    VideoReq,
    now_utc,
)

_INFO_URL = "https://www.ndt.nl/en/ndt-summer-intensive/"
_AUDITION_URL = "https://www.ndt.nl/en/audition-procedure-ndt-summer-intensive/"

ORG = Organization(
    name="Nederlands Dans Theater",
    slug="ndt-summer-intensive",
    country="NL",
    city="The Hague",
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(_INFO_URL)
    resp.raise_for_status()
    html = resp.text

    # Fetch the audition-procedure page for application dates — the info page
    # only shows the course dates and fees; the full timeline lives on the
    # audition page.
    aud_resp = client.get(_AUDITION_URL)
    aud_html = aud_resp.text if aud_resp.is_success else ""

    return _build_offerings(html, aud_html, date.today())


def _build_offerings(html: str, aud_html: str, today: date) -> list[Offering]:  # noqa: ARG001
    text = _extract_text(html)
    aud_text = _extract_text(aud_html)

    start, end = _course_dates(text)
    anchor = start or end
    if anchor is None:
        # No dated edition announced — emit nothing rather than faking data.
        return []

    season = str(anchor.year)

    opens_at, deadline = _application_dates(aud_text)

    return [
        Offering(
            id=f"ndt-summer-intensive/{season}",
            source=Source(
                provider="ndt-summer-intensive",
                url=_INFO_URL,
                scrapedAt=now_utc(),
            ),
            title=f"NDT Summer Intensive {season}",
            genres=_genres(text),
            ageRange=_age_range(text),
            level=["pre-professional", "open"],
            organization=ORG,
            location=Location(venue="NDT Studios", city="The Hague", country="NL"),
            schedule=Schedule(
                season=season,
                start=start,
                end=end,
                timezone="Europe/Amsterdam",
                notes=_date_note(text),
            ),
            prices=_prices(text),
            application=Application(
                # Application closes well before the course; by the time the scraper
                # runs in summer the window is closed — but we don't hardcode status.
                status="closed" if deadline and today > deadline else None,
                opensAt=opens_at,
                deadline=deadline,
                url=_AUDITION_URL,
                requirements=[
                    VideoReq(
                        specificity="specific",
                        description=(
                            "Solo video, max 6 minutes, no pointe work. "
                            "Dancer must be clearly and completely visible (no other dancers). "
                            "Perform movement to music; do not edit separate music to the video. "
                            "Upload to YouTube (public, no password) or Vimeo "
                            "(public, rated 'all audiences')."
                        ),
                    )
                ],
            ),
        )
    ]


def _extract_text(html: str) -> str:
    """Strip scripts/styles and collapse whitespace."""
    if not html:
        return ""
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


# "27 July - 8 August 2026" or "Monday 27 July – Saturday 8 August 2026"
# The page renders the cross-month range on the info card; optional day-name prefixes
# (Monday/Saturday) are consumed by \w+ before the date number.
_DAY_OPT = r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+)?"
_CROSS_MONTH = re.compile(
    _DAY_OPT
    + r"(\d{1,2})\s+("
    + parse.MONTHALT
    + r")\s*[-–]\s*"
    + _DAY_OPT
    + r"(\d{1,2})\s+("
    + parse.MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)
# Fallback: same-month range "27–31 July 2026"
_SAME_MONTH = re.compile(
    r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _course_dates(text: str) -> tuple[date | None, date | None]:
    m = _CROSS_MONTH.search(text)
    if m:
        d1, mo1, d2, mo2, yr = m.groups()
        y = int(yr)
        return (
            date(y, parse.MONTHS[mo1.lower()], int(d1)),
            date(y, parse.MONTHS[mo2.lower()], int(d2)),
        )
    m2 = _SAME_MONTH.search(text)
    if m2:
        d1, d2, mo, yr = m2.groups()
        y = int(yr)
        num = parse.MONTHS[mo.lower()]
        return date(y, num, int(d1)), date(y, num, int(d2))
    return None, None


def _date_note(text: str) -> str | None:
    """Return the raw date string from the source if found."""
    m = _CROSS_MONTH.search(text)
    if m:
        return m.group(0)
    m2 = _SAME_MONTH.search(text)
    if m2:
        return m2.group(0)
    return None


# "12 January 2026" / "9 February 2026" patterns on the audition page
_DATE_LINE = re.compile(
    r"(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
# Labels on the audition procedure page that precede the dates
_OPENS_LABEL = re.compile(r"application open|registration open|opens at", re.IGNORECASE)
_CLOSES_LABEL = re.compile(r"application close|registration close|closes at", re.IGNORECASE)


def _application_dates(aud_text: str) -> tuple[date | None, date | None]:
    """Parse the two key application dates from the audition-procedure page.

    The page has a table-like "Important dates" section:
      "12 January 2026  Application opens at …"
      "9 February 2026  Application closes at …"
    We scan for these date + label pairs.
    """
    dates: list[date] = []
    opens_at: date | None = None
    deadline: date | None = None

    # Walk through all date occurrences and check the surrounding context.
    for m in _DATE_LINE.finditer(aud_text):
        d = int(m.group(1))
        mo = parse.MONTHS[m.group(2).lower()]
        y = int(m.group(3))
        parsed = date(y, mo, d)

        # The label for "opens" or "closes" appears shortly after the date string.
        window = aud_text[m.end() : m.end() + 200]
        if _OPENS_LABEL.search(window):
            opens_at = parsed
        elif _CLOSES_LABEL.search(window):
            deadline = parsed

        dates.append(parsed)

    return opens_at, deadline


_AGE = re.compile(r"aged?\s*(\d{1,2})\s*[-–]\s*(\d{1,2})", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    return parse.extract_age_range(text, _AGE)


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("contemporary", ("contemporary",)),
    ("classical", ("classical ballet", "classical dance")),
]


def _genres(text: str) -> list[Genre]:
    # NDT is a contemporary company; include classical only if explicitly listed.
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["contemporary"])


# "€1500,-" or "€1,500" or "1500"
_FEE = re.compile(r"(?:course\s+)?tuition\s+is\s+[€$]?\s*([\d.,]+)", re.IGNORECASE)
# Match the optional accommodation line: "accommodation at … available for €1150"
_ACCOM = re.compile(r"accommodation\s+at\s+.*?available\s+for\s+[€$]?\s*([\d.,]+)", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []

    # Tuition fee
    m = _FEE.search(text)
    if m:
        amount = parse.parse_amount(m.group(1))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="Course tuition",
                    includes=["tuition"],
                    notes="Including VAT, excluding accommodation.",
                )
            )

    # Optional accommodation
    m2 = _ACCOM.search(text)
    if m2:
        amount2 = parse.parse_amount(m2.group(1))
        if amount2 is not None and amount2 > 0:
            prices.append(
                Price(
                    amount=amount2,
                    currency="EUR",
                    label="Optional accommodation (The Social Hub)",
                    includes=["accommodation"],
                    notes="Including VAT and city taxes. The Social Hub, The Hague.",
                )
            )

    return prices
