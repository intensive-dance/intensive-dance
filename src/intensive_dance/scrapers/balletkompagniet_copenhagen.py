"""Balletkompagniet — Summer Schools (Copenhagen, DK).

API FIRST: balletkompagniet.dk is WordPress (clean `/wp-json/`), but the
summer-schools page is a **WP blog post** with all editions laid out as prose
blocks — each a title line, a Danish date line, and a booking link. No CPT
or event plugin exposes them via REST, so it's a plain `selectolax` scrape
of the post body. The page structure is stable (each edition is a pair of
paragraphs: title + date), but prices live on the external
klub-modul.dk booking site, not on this page — left empty.

DISCOVERY: the provider runs 8+ dated summer-school editions across weeks
27/28/31/32, at different Copenhagen-area venues, for age groups 6–8, 9–12,
teens, and adults (pre-season). Each edition has its own date, age band,
venue, and teacher — so one `Offering` per edition. The "Spirekompagniet" is
the youngest group (pre-school ballet, ~4–6 years).

WHAT WE EXTRACT (verified live 2026-07-01):
  - EDITIONS: title lines like "Sommerskole for 9-12-årige med Henriette H.
    Lange i Hørsholm", paired with Danish date lines ("Tirsdag-torsdag d.
    30. juni-2. juli 2026, uge 27").
  - DATES: Danish day-span format — "d. DD. [month]-DD. [month] YYYY" with
    Danish month names (juni/juli/august). No year on the start bound when
    the end carries it. Day-of-week prefix ("Tirsdag-torsdag") ignored.
  - AGES: from the title ("9-12-årige" → 9–12, "6-8-årige" → 6–8). The
    "Spirekompagniet" group is youngest (~4–6, from the site's age table).
    "teens" and "pre-season" editions: ages left as notes.
  - VENUES: from the title ("i Hørsholm", "på Frederiksberg", "i Fields",
    "i City2", "i Skovshoved").
  - TEACHERS: from the title ("med <Name>").
  - PRICES: not on this page (fees behind the klub-modul.dk booking link)
    — left empty, faithful.
  - BOOKING: each edition has a klub-modul.dk link.
  - GENRES: the entire programme is "klassisk ballet" → classical only.

WHAT THIS SCRAPER EXERCISES: WP blog-post prose scrape (not a CPT); multi-
edition discovery from a single page; Danish date parsing with local month
names; age extracted from the edition title; venue from the title suffix;
one Offering per dated edition; raise-on-degraded fetch.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    Location,
    Offering,
    Organization,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://balletkompagniet.dk"
PAGE = f"{BASE}/balletkompagniets-sommerskoler-2026/"

ORG = Organization(
    name="Balletkompagniet",
    slug="balletkompagniet-copenhagen",
    country="DK",
    city="Copenhagen",
)

# Danish month names → number.
_DK_MONTHS: dict[str, int] = {
    "januar": 1,
    "februar": 2,
    "marts": 3,
    "april": 4,
    "maj": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}
_DK_MONTH_ALT = parse.months_alt(_DK_MONTHS)

# "d. 30. juni-2. juli 2026" / "d. 7.-9. juli 2026" / "d. 29. juni-1. juli 2026".
# First bound may omit the month (same month). Year may appear only on the end.
_DK_DATE = re.compile(
    r"d\.\s+(\d{1,2})\.\s*(?:(januar|februar|marts|april|maj|juni|juli|august|september|oktober|november|december)\s*)?"
    r"[-–]\s*(\d{1,2})\.\s*(januar|februar|marts|april|maj|juni|juli|august|september|oktober|november|december)\s+(\d{4})",
    re.IGNORECASE,
)

# Title-based age: "9-12-årige" / "6-8-årige".
_TITLE_AGE = re.compile(r"(\d{1,2})[-–](\d{1,2})[-–]?år")
# "Spirekompagniet" = youngest group (~4–6).
_SPIRE = re.compile(r"Spirekompagniet", re.IGNORECASE)
# "teens" / "pre-season" in the title.
_TEENS = re.compile(r"\bteens\b", re.IGNORECASE)
_PRESEASON = re.compile(r"pre-season", re.IGNORECASE)

# Teacher: "med <Name>" at the end of the title, before "i/på <venue>".
_TEACHER = re.compile(r"med\s+(.+)\s+(?:i|på)\s+", re.IGNORECASE)
# Venue: "i <Venue>" or "på <Venue>" at the end of the title.
_VENUE = re.compile(r"(?:i|på)\s+([^.]+)$", re.IGNORECASE)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text, date.today())


def _build_offerings(html: str, today: date) -> list[Offering]:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()

    body = tree.body.text(separator="\n") if tree.body else ""
    lines = body.split("\n")
    offerings: list[Offering] = []

    # Each edition is a title line containing "Sommerskole" or "pre-season" /
    # "sommerklasser", followed within 1–3 lines by a Danish date line "d. DD.".
    i = 0
    while i < len(lines):
        title_line = parse.clean(lines[i])
        if _is_edition_title(title_line):
            date_line = _find_date_line(lines, i + 1)
            if date_line:
                offering = _edition_offering(title_line, date_line)
                if offering:
                    offerings.append(offering)
        i += 1

    if not offerings:
        raise ValueError("Balletkompagniet: no editions parsed (degraded fetch?)")
    return offerings


def _is_edition_title(line: str) -> bool:
    return bool(re.search(r"Sommerskole|sommerklasser|pre-season", line, re.IGNORECASE))


def _find_date_line(lines: list[str], start: int) -> str | None:
    """The Danish date line within 3 lines of the title."""
    for j in range(start, min(start + 4, len(lines))):
        candidate = parse.clean(lines[j])
        if _DK_DATE.search(candidate):
            return candidate
    return None


def _edition_offering(title: str, date_line: str) -> Offering | None:
    start, end, season = _parse_dates(date_line)
    if start is None:
        return None  # unparseable date — skip rather than invent

    slug = _slugify(title)
    age = _age_from_title(title)
    teacher = _teacher_from_title(title)
    venue = _venue_from_title(title)

    return Offering(
        id=f"{ORG.slug}/{slug}-{season}",
        source=Source(provider=ORG.slug, url=PAGE, scrapedAt=now_utc()),
        title=title,
        genres=["classical"],
        ageRange=age,
        organization=ORG,
        location=Location(venue=venue, city=venue, country="DK")
        if venue
        else Location(city="Copenhagen", country="DK"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Copenhagen",
            notes=f"{date_line}" + (" — pre-season intensive" if _PRESEASON.search(title) else ""),
        ),
        teachers=[Teacher(name=teacher)] if teacher else [],
        application=Application(url=PAGE),
    )


def _parse_dates(text: str) -> tuple[date | None, date | None, str]:
    m = _DK_DATE.search(text)
    if not m:
        return None, None, "unknown"
    d1, m1, d2, m2, year = m.groups()
    month2 = _DK_MONTHS[m2.lower()]
    month1 = _DK_MONTHS[m1.lower()] if m1 else month2
    year_int = int(year)
    start = date(year_int, month1, int(d1))
    end = date(year_int, month2, int(d2))
    return start, end, str(year_int)


def _age_from_title(title: str) -> dict | None:
    m = _TITLE_AGE.search(title)
    if m:
        return {"min": int(m.group(1)), "max": int(m.group(2))}
    if _SPIRE.search(title):
        return {"min": 4, "max": 6}
    # teens/pre-season: ages unstated (leave as notes via the session or None).
    return None


def _teacher_from_title(title: str) -> str | None:
    m = _TEACHER.search(title)
    return parse.clean(m.group(1)) if m else None


def _venue_from_title(title: str) -> str | None:
    m = _VENUE.search(title)
    return parse.clean(m.group(1)) if m else None


def _slugify(title: str) -> str:
    # "Sommerskole for 9-12-årige med Henriette H. Lange i Hørsholm" → slug
    slug = re.sub(r"[^a-z0-9\s-]", "", title.lower())
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug[:60].rstrip("-")
