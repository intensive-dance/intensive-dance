"""École de Danse de l'Opéra national de Paris — its international Summer School
("Stage d'été").

API FIRST: none usable. operadeparis.fr is a large custom site, but the Summer
School page is server-rendered, so we read the (distinctive) facts straight out
of the page text. One `Offering` — the current Summer School — dropped once its
end date is past.

WHAT THE PAGE GIVES US (verified live 2026-06): season + dates ("the 2026 Summer
School will take place from July 6th to 18th"), the 10-19 age range, a
non-refundable application fee (51 € for 2026), and four course fee tiers from
the practical-information page (1-week residential €1,200 / non-residential €876;
2-week residential €2,208 / non-residential €1,560). Residential includes
tuition + accommodation + meals (3 meals); non-residential includes tuition only
(classes, lunch and snack). Venue is the school campus in Nanterre.
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
    PriceInclude,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.operadeparis.fr"
SUMMER = f"{BASE}/en/artists/ballet-school/summer-internship"
PRACTICAL = f"{SUMMER}/practical-information"

ORG = Organization(
    name="École de Danse de l'Opéra national de Paris",
    slug="ecole-danse-opera-paris",
    country="FR",
    city="Paris",
)
VENUE = "École de Danse de l'Opéra national de Paris, Nanterre"


def scrape(client: httpx.Client) -> list[Offering]:
    # Dates/ages are on the main page; the application fee is on the practical page.
    text = " ".join(filter(None, (_text(client, SUMMER), _text(client, PRACTICAL))))
    if not text.strip():
        return []
    return [o] if (o := _build_offering(text, date.today())) is not None else []


def _build_offering(text: str, today: date) -> Offering | None:
    season = _season(text)
    start, end = _date_range(text, season)
    app_fee = _application_fee(text)
    notes = f"Non-refundable application fee of €{app_fee:g}." if app_fee else None
    return Offering(
        id=f"ecole-danse-opera-paris/summer-school-{season}",
        source=Source(provider="ecole-danse-opera-paris", url=SUMMER, scrapedAt=now_utc()),
        title=f"Paris Opera Ballet School — Summer School {season}",
        genres=_genres(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue=VENUE, city="Nanterre", country="FR"),
        schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Paris"),
        prices=_course_fees(text),
        application=Application(url=SUMMER, notes=notes),
    )


# --- parsing ------------------------------------------------------------------

# "Tuition for one week" / "Tuition for two weeks" block, then a pair of euro
# amounts (residential, non-residential) on the "All levels" line.
_FEE_BLOCK = re.compile(
    r"Tuition for (one|two) week[s]?[^€]*€\s*([\d,]+)[^€]*€\s*([\d,]+)",
    re.IGNORECASE,
)

_SEASON = re.compile(r"(20\d\d)\s+Summer School", re.IGNORECASE)
# "from July 6th to 18th" — the page renders the ordinal as a separate token
# ("July 6 th to 18 th"), so allow whitespace before st/nd/rd/th.
_RANGE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})\s*(?:st|nd|rd|th)?\s+to\s+(\d{1,2})\s*(?:st|nd|rd|th)?",
    re.IGNORECASE,
)
_AGE = re.compile(r"age\s+(\d{1,2})\s+to\s+(\d{1,2})", re.IGNORECASE)
_APP_FEE = re.compile(r"(\d{1,3})\s?€\s+of application fees", re.IGNORECASE)


def _season(text: str) -> str:
    match = _SEASON.search(text)
    return match.group(1) if match else "unknown"


def _date_range(text: str, season: str) -> tuple[date | None, date | None]:
    year = int(season) if season.isdigit() else None
    match = _RANGE.search(text)
    if not match or year is None:
        return None, None
    num = parse.MONTHS[match.group(1).lower()]
    return date(year, num, int(match.group(2))), date(year, num, int(match.group(3)))


def _age_range(text: str) -> dict | None:
    return parse.extract_age_range(text, _AGE)


def _application_fee(text: str) -> float | None:
    match = _APP_FEE.search(text)
    return float(match.group(1)) if match else None


def _course_fees(text: str) -> list[Price]:
    """Parse the four course-fee tiers from the practical-information page.

    The page lists residential and non-residential fees for one-week and
    two-week durations.  Residential includes tuition, accommodation and 3
    meals; non-residential includes tuition only (classes, lunch and snack).
    """
    prices: list[Price] = []
    for m in _FEE_BLOCK.finditer(text):
        duration, res_raw, nonres_raw = m.groups()
        label_stem = f"{'1 week' if duration.lower() == 'one' else '2 weeks'}"
        res_amt = parse.parse_amount(res_raw)
        nonres_amt = parse.parse_amount(nonres_raw)
        res_includes: list[PriceInclude] = ["tuition", "accommodation", "meals"]
        nonres_includes: list[PriceInclude] = ["tuition"]
        if res_amt is not None:
            prices.append(
                Price(
                    amount=res_amt,
                    currency="EUR",
                    label=f"Residential — {label_stem}",
                    includes=res_includes,
                )
            )
        if nonres_amt is not None:
            prices.append(
                Price(
                    amount=nonres_amt,
                    currency="EUR",
                    label=f"Non-residential — {label_stem}",
                    includes=nonres_includes,
                )
            )
    return prices


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet")),
    ("contemporary", ("contemporary",)),
    ("character", ("character",)),
    ("repertoire", ("repertoire",)),
    ("pointe", ("pointe shoes technique", "technique/pointes", "technique, pointes")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _text(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    if resp.status_code == 404:
        return ""
    resp.raise_for_status()
    tree = HTMLParser(resp.text)
    for node in tree.css("script, style, noscript, nav, header, footer"):
        node.decompose()
    return re.sub(r"\s+", " ", tree.body.text(separator=" ")) if tree.body else ""
