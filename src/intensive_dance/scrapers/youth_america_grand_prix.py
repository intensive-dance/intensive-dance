"""Youth America Grand Prix (YAGP) — its European competition semi-finals.

API FIRST: the WordPress REST `content.rendered` is EMPTY for these schedule
pages (the body is built by a custom Elementor module, not block content), so
REST gives us nothing. But the page ships **embedded structured data**: each
season stop is emitted as a `var javascript_array = {...};` JSON object carrying
the stop's name, date range, flag image and registration-button state. That's
the API-first tier-2 source (embedded JSON over HTML parsing), and it's far
cleaner than the visible Elementor markup — where each city's `<h3>` header and
its date are duplicated and the date cell precedes its header. We parse the JSON
blobs and dedupe by stop name.

DISCOVERY: one international-schedule page lists every semi-final worldwide plus
the Finals and a Job Fair. We are a ballet *intensive/competition* register
scoped to **Europe**, so we emit one `Offering` per **European competition
stop** only — Paris, Barcelona, Genoa, Lagoa for 2026-27 — keyed by city slug +
season. The Stuttgart "Job Fair" is not a judged competition, and the US/Asia
stops are out of geographic scope, so both are dropped. The YAGP summer
intensive is run by affiliated schools (not yagp.org) and is not modelled here.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-05):
  - `kind="competition"`: a judged ranking event, not an admission audition.
  - Cross-month date ranges ("October 29 - November 1, 2026") and same-month
    ranges ("December 1 - 6, 2026") → schedule start/end, season "2026-27".
  - Country derived from the stop name's trailing country word (EU allowlist),
    no street venue (the page gives only city/country) → `Location(city, country)`.
  - A flat $125 USD registration fee (from the registration-notice page), the
    same for every stop, with `includes=[]` (it reserves a competition slot, not
    tuition). Stops are emitted even without per-stop fee enrichment.
  - Registration runs through external DanceCompGenie and the page exposes no
    programmatic open/closed flag, so `application.status` is left null and only
    the schedule URL is stored.
"""

from __future__ import annotations

import json
import re
from datetime import date

import httpx

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
    now_utc,
)

BASE = "https://yagp.org"
SCHEDULE_URL = f"{BASE}/competition/yagp-2026-2027-international-locations-dates/"
REGISTRATION_URL = f"{BASE}/registration-notice/"

ORG = Organization(name="Youth America Grand Prix", slug="youth-america-grand-prix", country="US")

GENRES: list[Genre] = ["classical", "contemporary"]

# A YAGP semi-final reserves a competition slot for a flat, non-refundable fee
# that the registration-notice page states applies "at any location".
REGISTRATION_FEE = Price(
    amount=125.0,
    currency="USD",
    label="Registration fee",
    notes="Non-refundable registration fee, the same at every location.",
)

# Stop names end in their country; only these European countries are in scope.
# (The page also lists US/Asia stops and a German "Job Fair" — both dropped.)
_COUNTRY_ISO: dict[str, str] = {
    "FRANCE": "FR",
    "SPAIN": "ES",
    "ITALY": "IT",
    "PORTUGAL": "PT",
}

# `var javascript_array = { ... };` — one per stop, the embedded structured data.
_BLOB = re.compile(r"javascript_array\s*=\s*(\{.*?\});", re.DOTALL)

# "2026-2027" — the season the whole page covers; normalized to "2026-27". Every
# stop belongs to this one season, so we read it once rather than guess per-stop
# (a single-year stop like a February semi-final would otherwise mislabel).
_SEASON = re.compile(r"(\d{4})\s*[-–—]\s*(\d{4})")

# "October 29 - November 1, 2026" (cross-month) or "December 1 - 6, 2026"
# (same month, where the second month is implied by the first).
_DATE_RANGE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})\s*[-–—]\s*"
    r"(?:(" + parse.MONTHALT + r")\s+)?(\d{1,2}),\s*(\d{4})",
    re.IGNORECASE,
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(SCHEDULE_URL, follow_redirects=True)
    resp.raise_for_status()
    return _build_offerings(resp.text, date.today())


def _build_offerings(html: str, today: date) -> list[Offering]:
    season = _season(html)
    offerings: list[Offering] = []
    seen: set[str] = set()
    for stop in _stops(html):
        name = stop["name"]
        if name in seen:
            continue  # the page repeats each stop's markup; the blob too can recur
        seen.add(name)

        if _is_job_fair(name):
            continue
        country = _country(name)
        if country is None:
            continue  # out of European scope (US / Asia stops)

        span = _date_range(stop.get("date", ""))
        if span is None or span[1] < today:
            continue  # undated or already-ended cycle
        start, end = span

        offerings.append(_offering(name, country, start, end, stop.get("date", ""), season))
    return offerings


def _offering(
    name: str, country: str, start: date, end: date, raw_date: str, season: str
) -> Offering:
    city = _city(name)
    return Offering(
        id=f"youth-america-grand-prix/{_slug(city)}-{season}",
        source=Source(provider="youth-america-grand-prix", url=SCHEDULE_URL, scrapedAt=now_utc()),
        title=_title(name),
        genres=GENRES,
        kind="competition",
        organization=ORG,
        location=Location(city=city, country=country),
        schedule=Schedule(season=season, start=start, end=end, notes=parse.clean(raw_date)),
        prices=[REGISTRATION_FEE],
        application=Application(url=REGISTRATION_URL),
    )


def _stops(html: str) -> list[dict]:
    out: list[dict] = []
    for m in _BLOB.finditer(html):
        try:
            blob = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(blob, dict) and blob.get("name"):
            out.append(blob)
    return out


def _is_job_fair(name: str) -> bool:
    return "JOB FAIR" in name.upper()


def _country(name: str) -> str | None:
    # "CITY, COUNTRY" or "CITY, COUNTRY (JOB FAIR)" — take the country word.
    parts = name.split(",")
    if len(parts) < 2:
        return None
    country_word = re.sub(r"\(.*?\)", "", parts[-1]).strip().upper()
    return _COUNTRY_ISO.get(country_word)


def _city(name: str) -> str:
    return parse.clean(name.split(",")[0]).title()


def _title(name: str) -> str:
    return f"YAGP {parse.clean(re.sub(r'\\(.*?\\)', '', name)).title()}"


def _slug(city: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-")


def _season(html: str) -> str:
    # YAGP's season spans two calendar years (autumn → spring); the page states
    # it as "2026-2027", which we normalize to "2026-27".
    m = _SEASON.search(html)
    return f"{m.group(1)}-{m.group(2)[-2:]}" if m else "unknown"


def _date_range(raw: str) -> tuple[date, date] | None:
    m = _DATE_RANGE.search(raw)
    if not m:
        return None
    month1, day1, month2, day2, year = m.groups()
    start_month = parse.MONTHS[month1.lower()]
    end_month = parse.MONTHS[month2.lower()] if month2 else start_month
    # A cross-month range can straddle New Year (rare here, but be faithful):
    # if the end month precedes the start month, the end falls in the next year.
    end_year = int(year)
    start_year = end_year if end_month >= start_month else end_year - 1
    return (
        date(start_year, start_month, int(day1)),
        date(end_year, end_month, int(day2)),
    )
