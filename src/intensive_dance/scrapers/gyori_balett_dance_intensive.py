"""Győri Balett — Dance Intensive — Győr, HU.

API FIRST: WordPress. `https://gyoribalett.hu/wp-json/` is 200 and the
Dance Intensive editions are ordinary pages whose English copy lives, fully
server-rendered, in `content.rendered` (SiteOrigin Page Builder widgets, *not*
WPBakery — so plain `selectolax` text, no `wp.parse` shortcode pass). We
discover the edition pages with
`wp/v2/pages?search=dance%20intensive&_fields=…`, keep the **English** ones
(slug `dance-intensive-gyor-<year>-en`), and parse each. The proxy is only
needed because the host blocks the CI datacenter IP — it's a no-JS API scrape.

DISCOVERY: one `Offering` per *edition page that states its own dates*. The
workshop runs inside the Hungarian Dance Festival, but we **never borrow the
festival window** — we read the dates off the intensive page itself ("…between
18 and 22 June 2025…" / "When? 18-22 June"). The 2025 edition runs two parallel
tracks (classical ballet · contemporary) at the same place and dates, so it is
ONE Offering with one `Session` per track (each track's daily time window kept
in the session notes); folding them would lose the distinct teacher/time. As of
2026-06-12 only the 2025 edition page exists (the 2026 Dance Intensive page is
not yet published — the 2026 festival page is a performance programme with no
workshop listing), so this scraper currently emits the past 2025 edition (kept
per the IDR-24 "don't filter on dates" rule); it will pick up a 2026 EN page
automatically once published.

WHAT THIS SCRAPER EXERCISES: schedule with start/end + per-track `Session`s;
two `Genre`s (classical, contemporary); per-track and combined `Price`s in HUF;
`Teacher`s with their track role; `Application` with an email contact, no stated
audition requirement (open enrollment → `NoneReq`). Verified live 2026-06-12.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    Genre,
    Location,
    NoneReq,
    Offering,
    Organization,
    Price,
    Schedule,
    Session,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://gyoribalett.hu"
PROVIDER = "gyori-balett-dance-intensive"

ORG = Organization(name="Győri Balett", slug=PROVIDER, country="HU", city="Győr")

# Edition pages are slugged `dance-intensive-gyor-<year>-en` (the `-en` page is the
# canonical English copy; a `-<year>` page is the Hungarian twin we ignore).
_SLUG = re.compile(r"^dance-intensive-gyor-(\d{4})-en$")


def scrape(client: httpx.Client) -> list[Offering]:
    pages = wp.fetch_all(
        client,
        "pages",
        base=BASE,
        params={"search": "dance intensive", "_fields": "id,slug,link,content"},
    )
    offerings: list[Offering] = []
    for page in pages:
        m = _SLUG.match(page.get("slug", ""))
        if not m:
            continue
        offering = _build_offering(page["link"], int(m.group(1)), page["content"]["rendered"])
        if offering is not None:
            offerings.append(offering)
    return offerings


def _build_offering(url: str, year: int, rendered: str) -> Offering | None:
    text = parse.clean(HTMLParser(rendered).text(separator=" "))
    start, end = _date_range(text, year)
    if start is None:  # no dates stated on the page → emit nothing (never borrow festival window)
        return None
    return Offering(
        id=f"{PROVIDER}/{year}",
        source=Source(provider=PROVIDER, url=url, scrapedAt=now_utc()),
        title=f"Dance Intensive Győr {year}",
        genres=_genres(text),
        organization=ORG,
        location=_location(text),
        schedule=Schedule(
            season=str(year),
            start=start,
            end=end,
            timezone="Europe/Budapest",
            sessions=_sessions(rendered),
        ),
        teachers=_teachers(rendered),
        prices=_prices(text),
        application=Application(url=url, requirements=[NoneReq()], notes=_contact(text)),
    )


# --- dates --------------------------------------------------------------------

# Intro line carries the year: "…between 18 and 22 June 2025…".
_RANGE_FULL = re.compile(
    r"between\s+(\d{1,2})\s+and\s+(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str, year: int) -> tuple[date | None, date | None]:
    m = _RANGE_FULL.search(text)
    if not m:
        return None, None
    d1, d2, month, yr = m.groups()
    num = parse.MONTHS[month.lower()]
    return date(int(yr), num, int(d1)), date(int(yr), num, int(d2))


# --- genres -------------------------------------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical ballet",)),
    ("contemporary", ("contemporary",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS)


# --- location -----------------------------------------------------------------

# "Where? Szabolcska Mihály Str. 5, Győr 9023 – Dance and Fine Arts … – Ballet Hall"
_WHERE = re.compile(r"Where\?\s*(.+?)(?:Classical ballet workshop|Do you have a question|$)", re.S)


def _location(text: str) -> Location:
    m = _WHERE.search(text)
    venue = parse.clean(m.group(1)).rstrip(" .") if m else None
    return Location(venue=venue or None, city="Győr", country="HU")


# --- per-track sessions -------------------------------------------------------

# Each track is a "<Genre> workshop: <Teacher>" block with a daily time window:
# "Every day from 14:00 to 15:30" (the contemporary line uses dots: "16.00 to 17.30").
_TRACK = re.compile(
    r"(Classical ballet|Contemporary dance) workshop:\s*(.+?)"
    r"Every day from\s*([\d.:]+)\s*to\s*([\d.:]+)",
    re.IGNORECASE | re.S,
)


def _sessions(rendered: str) -> list[Session]:
    text = parse.clean(HTMLParser(rendered).text(separator=" "))
    sessions: list[Session] = []
    for track, teacher, t1, t2 in _TRACK.findall(text):
        teacher = parse.clean(teacher).rstrip(" .")
        sessions.append(
            Session(
                label=parse.clean(track),
                notes=f"{teacher} — every day {_time(t1)}–{_time(t2)}",
            )
        )
    return sessions


def _time(raw: str) -> str:
    return raw.replace(".", ":")


# --- teachers -----------------------------------------------------------------

# The "Guest teachers" block names each track's teacher; their own bio pages are
# linked under the workshop blocks ("<Genre> workshop: <a …>Name</a>").
_TEACHER_LINK = re.compile(
    r"(Classical ballet|Contemporary dance) workshop:\s*<a\b[^>]*>(.*?)</a>",
    re.IGNORECASE | re.S,
)
_TRACK_ROLE = {
    "classical ballet": "Classical ballet",
    "contemporary dance": "Contemporary dance",
}


def _teachers(rendered: str) -> list[Teacher]:
    teachers: list[Teacher] = []
    seen: set[str] = set()
    for track, name in _TEACHER_LINK.findall(rendered):
        name = parse.clean(HTMLParser(name).text())
        if not name or name in seen:
            continue
        seen.add(name)
        teachers.append(Teacher(name=name, role=_TRACK_ROLE.get(track.lower())))
    return teachers


# --- prices -------------------------------------------------------------------

# Per-track: "10,000 HUF /hour" and "40,000 HUF a 5-day PASS"; combined:
# "80,000 HUF combined … PASS for 5 days". HUF uses comma thousands separators.
_HOUR = re.compile(r"([\d,]+)\s*HUF\s*/?\s*hour", re.IGNORECASE)
_PASS5 = re.compile(r"([\d,]+)\s*HUF\s*a?\s*5-day PASS", re.IGNORECASE)
_COMBINED = re.compile(r"([\d,]+)\s*HUF\s*combined", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    seen: set[tuple[float, str]] = set()

    def add(raw: str, label: str) -> None:
        amount = parse.parse_amount(raw)
        if amount is None:
            return
        key = (amount, label)
        if key in seen:
            return
        seen.add(key)
        prices.append(Price(amount=amount, currency="HUF", label=label, includes=["tuition"]))

    # Per-track hourly + 5-day single-track pass (both tracks list the same figures).
    for raw in dict.fromkeys(_HOUR.findall(text)):
        add(raw, "Per hour (single workshop)")
    for raw in dict.fromkeys(_PASS5.findall(text)):
        add(raw, "5-day pass (single workshop)")
    m = _COMBINED.search(text)
    if m:
        add(m.group(1), "5-day combined pass (classical + contemporary)")
    return prices


# --- application contact ------------------------------------------------------

_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")


def _contact(text: str) -> str | None:
    m = _EMAIL.search(text)
    return f"Open enrollment; questions to {m.group(0)}" if m else None
