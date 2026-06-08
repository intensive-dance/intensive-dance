"""Les Ballets de Pologne (PL) — summer ballet workshop, Warszawa.

API FIRST: WordPress, but the REST API is locked. The site is plain WordPress
(Yoast schema, `wp-content`), yet `/wp-json/` and `wp/v2/posts` both 401 behind a
"Disable REST API" plugin ("DRA: Only authenticated users can access the REST
API"). The page HTML is served fine, so we fetch the single workshop page
(`/warsztaty-wakacyjne/`) — the one place the summer-workshop editions live — and
parse its text. No proxy needed (a plain httpx fetch returns the real markup; the
host doesn't gate the datacenter IP).

LANGUAGE NOTE: the body is Polish in every render, so the parse is
**language-agnostic** — numeric/Polish-month dates and enum genres normalise to
stable values; the only free text we emit is canonical English (title, notes), so
the committed data is deterministic.

DISCOVERY: the workshop page announces the recurring "Warsztaty wakacyjne" (summer
holiday workshop) and carries the dated editions inline. Each dated edition →
**one Offering** (id `…/warsztaty-wakacyjne-{start ISO}`), so editions stay
distinct and diffable. Ended cycles are kept (IDR-24); "past" is derived from
dates consumer-side, never stored — the page currently shows two 2023 editions.

FAIL OPEN: the page states only the dates, a 12-per-group cap and "free dress
code". It does **not** publish per-edition price, age band, level or named
faculty for the workshop (the school's year-round `/cennik`+`/grafik` pages cover
the regular classes, a different product), so those fields are left null/empty
rather than borrowed from the regular-class pages. Email-only signup, no audition
/ photo / video submission stated → requirements [] (unknown); the group cap is
recorded as a selectivity note.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - Multi-edition discovery from one page — two summer editions, one Offering each,
    spanning a single month ("3-9 lipca 2023") and crossing months
    ("28 sierpnia - 2 września 2023").
  - LANGUAGE-AGNOSTIC Polish-month dates with both genitive shapes.
  - FAIL-OPEN minimal record — dates + genres + a places-limited note, no invented
    price/age/level/faculty.
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
    Schedule,
    Source,
    now_utc,
)

BASE = "https://lesballets.pl"
PAGE_URL = f"{BASE}/warsztaty-wakacyjne/"

ORG = Organization(
    name="Les Ballets de Pologne",
    slug="les-ballets-de-pologne",
    country="PL",
    city="Warszawa",
)

# Polish month names → number (genitive forms, as the dateline uses them:
# "3-9 lipca", "28 sierpnia").
_MONTHS = {
    "stycznia": 1,
    "lutego": 2,
    "marca": 3,
    "kwietnia": 4,
    "maja": 5,
    "czerwca": 6,
    "lipca": 7,
    "sierpnia": 8,
    "września": 9,
    "wrzesnia": 9,
    "października": 10,
    "pazdziernika": 10,
    "listopada": 11,
    "grudnia": 12,
}
_MONTHALT = parse.months_alt(sorted(_MONTHS, key=len, reverse=True))

# Single-month span: "3-9 lipca 2023" (day-day month year).
_SPAN_SINGLE = re.compile(
    r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
# Cross-month span: "28 sierpnia - 2 września 2023" (day month - day month year);
# the year trails the end.
_SPAN_CROSS = re.compile(
    r"(\d{1,2})\s+(" + _MONTHALT + r")\s*[-–]\s*(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE_URL)
    resp.raise_for_status()
    return _build_offerings(resp.text, date.today())


def _build_offerings(html: str, today: date) -> list[Offering]:  # noqa: ARG001 — today reserved
    text = _plain_text(html)
    genres = _genres(text)
    notes = _application_notes(text)

    offerings: list[Offering] = []
    for start, end in _editions(text):
        offerings.append(
            Offering(
                id=f"les-ballets-de-pologne/warsztaty-wakacyjne-{start.isoformat()}",
                source=Source(provider="les-ballets-de-pologne", url=PAGE_URL, scrapedAt=now_utc()),
                title=f"Summer ballet workshop {start.year}",
                genres=genres,
                organization=ORG,
                location=Location(city="Warszawa", country="PL"),
                schedule=Schedule(
                    season=str(start.year),
                    start=start,
                    end=end,
                    timezone="Europe/Warsaw",
                ),
                application=Application(url=PAGE_URL, notes=notes),
            )
        )
    offerings.sort(key=lambda o: o.id)
    return offerings


def _plain_text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


# --- editions -----------------------------------------------------------------


def _editions(text: str) -> list[tuple[date, date]]:
    """Dated workshop editions, deduped and chronologically ordered.

    Both Polish shapes are read: a single-month span ("3-9 lipca 2023") and a
    cross-month one ("28 sierpnia - 2 września 2023").
    """
    spans: list[tuple[date, date]] = []

    for m in _SPAN_CROSS.finditer(text):
        d1, m1, d2, m2, year = m.groups()
        y = int(year)
        span = (date(y, _MONTHS[m1.lower()], int(d1)), date(y, _MONTHS[m2.lower()], int(d2)))
        if span not in spans:
            spans.append(span)

    for m in _SPAN_SINGLE.finditer(text):
        d1, d2, month, year = m.groups()
        y = int(year)
        num = _MONTHS[month.lower()]
        span = (date(y, num, int(d1)), date(y, num, int(d2)))
        if span not in spans:
            spans.append(span)

    return sorted(spans)


# --- genres -------------------------------------------------------------------
#
# The workshop is a ballet workshop ("warsztaty baletowe"); the page names no
# technique list, so classical is the only stated genre.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("baletow", "balet", "ballet", "klasyczn", "classical")),
    ("pointe", ("point", "pointe", "puent")),
    ("contemporary", ("współczesn", "wspolczesn", "contemporary")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- application --------------------------------------------------------------
#
# Signup is email-only ("obowiązują zapisy mailowe") with no audition / photo /
# video stated → requirements stay [] (unknown). The page does state a per-group
# cap ("w każdej grupie obowiązuje limit 12 osób") — a selectivity signal kept as
# a note.

_LIMIT = re.compile(r"limit\s+(\d{1,3})\s+os[oó]b", re.IGNORECASE)


def _application_notes(text: str) -> str | None:
    m = _LIMIT.search(text)
    if m:
        return f"Places limited to {m.group(1)} per group."
    return None
