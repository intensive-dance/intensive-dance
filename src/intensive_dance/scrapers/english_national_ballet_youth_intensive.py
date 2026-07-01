"""English National Ballet — Youth Dance Summer Intensive (London, GB).

API FIRST: ballet.org.uk is WordPress (clean `/wp-json/`), but the intensive
lives at `/class/<slug>/` which is NOT a REST-exposed post type (the `class`
route is a theme template, absent from `/wp-json/wp/v2/types`). The pages are
fully server-rendered, though, so it's a plain `selectolax` scrape anchored on
stable theme classes (`span.introduction-date`, `div.introduction-details__fee`)
plus the overview age sentence — no HTML-position guessing.

DISCOVERY: the intensive runs in two parallel age/level tiers, each its own
`/class/` page with distinct dates, ages and fee — so one `Offering` per tier
(`advanced`, `intermediate`), never folded. The related-events rail links a
separate ENBYouthCo audition program; we only parse the two tier pages we fetch.

WHAT WE EXTRACT (verified live 2026-07-01):
  - DATES: the hero "Mon 3 - Fri 7 Aug 2026" span (month + year stated once at
    the end, applied to both bounds; the general parser also handles a
    cross-month start).
  - AGES: "For dancers aged 14 – 19 years" from the overview.
  - LEVEL: Advanced (pre-vocational/vocational) → advanced + pre-professional;
    Intermediate (with dance experience) → intermediate.
  - GENRES: the overview names "ballet and contemporary technique" as what's
    taught → classical + contemporary. "diverse repertoire" is the company's
    rep the dancers *experience*, not a repertoire class, so it's not counted.
  - PRICES: the hero fee box ("£330" / "£180"), GBP tuition.
  - LOCATION: the Mulryan Centre for Dance, London (ENB's home studios).
  - APPLICATION: open booking via WooCommerce (daily-space listings), no
    audition for the intensive itself → no stated requirements.

WHAT THIS SCRAPER EXERCISES: server-rendered WP page outside the REST API;
one-Offering-per-tier discovery; day-of-week-prefixed date span with a single
trailing month/year; overview-scoped ages/genres; GBP tuition; raise-on-degraded
fetch (missing the hero date span).
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    Level,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.ballet.org.uk"
# Age/level tier → its /class/ page slug.
TIERS: dict[str, str] = {
    "advanced": "youth-dance-summer-intensive-advanced",
    "intermediate": "youth-dance-summer-intensive-intermediate",
}

ORG = Organization(
    name="English National Ballet",
    slug="english-national-ballet-youth-intensive",
    country="GB",
    city="London",
)
VENUE = "Mulryan Centre for Dance"

# The hero prints 3-letter month abbreviations ("Aug", "Jul"); the site's own
# names, kept local. "Mon 3 - Fri 7 Aug 2026" / "Wed 29 - Fri 31 Jul 2026" —
# month is stated once at the end, applied to both bounds; the optional leading
# month covers a would-be cross-month start.
_MONTHS_ABBR: dict[str, int] = {
    m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), start=1)
}
_MONTH_ABBR = parse.months_alt(_MONTHS_ABBR)
_DATE_SPAN = re.compile(
    r"(?:\w{3}\s+)?(\d{1,2})(?:\s+(" + _MONTH_ABBR + r"))?"
    r"\s*[-–]\s*(?:\w{3}\s+)?(\d{1,2})\s+(" + _MONTH_ABBR + r")\s+(\d{4})",
    re.IGNORECASE,
)
_AGE = re.compile(r"aged\s+(\d{1,2})\s*[–\-]\s*(\d{1,2})\s+years", re.IGNORECASE)
_FEE = re.compile(r"£\s*([\d,]+)")

_LEVELS: dict[str, list[Level]] = {
    "advanced": ["advanced", "pre-professional"],
    "intermediate": ["intermediate"],
}


def scrape(client: httpx.Client) -> list[Offering]:
    offerings: list[Offering] = []
    for tier, slug in TIERS.items():
        url = f"{BASE}/class/{slug}/"
        resp = client.get(url)
        resp.raise_for_status()
        offerings.append(_build_offering(resp.text, tier, url))
    return offerings


def _build_offering(html: str, tier: str, url: str) -> Offering:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()

    date_node = tree.css_first("span.introduction-date")
    span = parse.clean(date_node.text()) if date_node else ""
    start, end, season = _parse_dates(span)
    if start is None:
        raise ValueError(f"ENB {tier}: no hero date span found (degraded fetch?)")

    body = tree.body.text(separator="\n") if tree.body else ""
    title = f"Youth Dance Summer Intensive — {tier.capitalize()}"

    return Offering(
        id=f"{ORG.slug}/{tier}-{season}",
        source=Source(provider=ORG.slug, url=url, scrapedAt=now_utc()),
        title=title,
        genres=["classical", "contemporary"],
        level=_LEVELS[tier],
        ageRange=_age_range(body),
        organization=ORG,
        location=Location(venue=VENUE, city="London", country="GB"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/London",
            notes=span or None,
        ),
        prices=_prices(tree),
        application=Application(url=url),
    )


def _parse_dates(span: str) -> tuple[date | None, date | None, str]:
    m = _DATE_SPAN.search(span)
    if not m:
        return None, None, "unknown"
    start_day, start_month, end_day, end_month, year = m.groups()
    month_end = _MONTHS_ABBR[end_month.lower()]
    month_start = _MONTHS_ABBR[start_month.lower()] if start_month else month_end
    year_int = int(year)
    start = date(year_int, month_start, int(start_day))
    end = date(year_int, month_end, int(end_day))
    return start, end, str(year_int)


def _age_range(body: str) -> dict | None:
    m = _AGE.search(body)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _prices(tree: HTMLParser) -> list[Price]:
    fee_node = tree.css_first("div.introduction-details__fee")
    if not fee_node:
        return []
    m = _FEE.search(fee_node.text())
    if not m:
        return []
    return [Price(amount=float(m.group(1).replace(",", "")), currency="GBP", includes=["tuition"])]
