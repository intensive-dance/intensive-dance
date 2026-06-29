r"""Sommer Tanz Camp — Intensive Ballett Days Berlin (Samuel's Dance Hall), DE.

API FIRST: `/wp-json/` answers 200 but the site is **not** content-served by
WordPress — it's a flowweb.de-CMS site whose program data lives in flat,
hand-built HTML (`generator=flowweb.de`, `<div align="center">` blocks, no
`content.rendered`, the only `ld+json` is generic `LocalBusiness`/`WebSite`). So
this is a plain HTML scrape; no proxy needed (public, datacenter-reachable).

SCOPE: the brand (sommertanzcamp.de = "Summer Dance Camp") is mostly an **urban**
dance camp ("urbane Tanzstile" — KIDS/TEENS/ADULTS weeks, BREAKING days) which is
OUT of scope for a ballet register. Only the dated **"Ballett Intensive Days"**
editions are in scope; we drop every BREAKING / urban week via the genre filter
(an edition segment must say "Ballett" and must not say "Breaking").

DISCOVERY: one Offering per dated ballet edition. The editions are split across
two pages and we union them by date range:
  - `/de/termine` (the calendar) carries the **Oster** (Easter) edition with its
    age/level note: "(ab 14 Jahre Mittelstufe bis Fortgeschritten)".
  - `/de/anmeldung` (the registration page) carries the **Herbst** (autumn)
    edition with its price ("180,00 €"), daily hours and venue address.
A past edition (Oster already ran) is kept per IDR-24 — discovery, not a date cut.
The dedicated `/de/ballett-days-berlin` page describes the program ("4 intensive
Tage voller Ballett, Modern und Contemporary") and its trainers; we apply those
genres + faculty only to the edition whose dates match that page (the Oster one),
leaving the others labelled from their own segment ("Ballett" → classical).

TRAPS: the calendar dates carry a stray double dot ("02.04..2026") — the date
regex tolerates `\.+`. Titles are ALL-CAPS in the `<u>` heading (title-cased
here). Faculty are first-name-only with a free-text credential; we keep the name
and map only the two credential strings that name a real teaching institution
(Samuel's Dance Hall, Palucca Hochschule) to an affiliation — achievements
(a competition title, a cruise-ship gig) are not affiliations and are dropped.

WHAT THIS SCRAPER EXERCISES: multi-page union/dedupe by date key; German age
("ab N Jahre" → open-topped) and level (Mittelstufe/Fortgeschritten/Einsteiger)
parsing; a per-edition price; cross-page genre/teacher enrichment gated on a date
match; explicit NoneReq (open registration, no audition). Verified live
2026-06-26.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Affiliation,
    Application,
    Genre,
    Level,
    Location,
    NoneReq,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.sommertanzcamp.de"
TERMINE_URL = f"{BASE}/de/termine"
ANMELDUNG_URL = f"{BASE}/de/anmeldung"
DETAIL_URL = f"{BASE}/de/ballett-days-berlin"

ORG = Organization(
    name="Summer Dance Camp",
    slug="sommer-tanz-camp-berlin",
    country="DE",
    city="Berlin",
)
VENUE = "Samuel's Dance Hall, Berlin-Tempelhof"


def scrape(client: httpx.Client) -> list[Offering]:
    termine = client.get(TERMINE_URL)
    termine.raise_for_status()
    anmeldung = client.get(ANMELDUNG_URL)
    anmeldung.raise_for_status()
    detail = client.get(DETAIL_URL)
    detail.raise_for_status()
    return _build_offerings(termine.text, anmeldung.text, detail.text, date.today())


# --- date / age / level parsing ----------------------------------------------

# A DD.MM.YYYY token; tolerates the calendar's stray double dot ("02.04..2026").
_DATE = r"(\d{1,2})\.(\d{1,2})\.+(\d{4})"
_RANGE = re.compile(_DATE + r"\s*[-–]\s*" + _DATE)
_AGE = re.compile(r"ab\s*(\d{1,2})\s*Jahre", re.IGNORECASE)

# German level words → enum. "bis"/"-" between two of them means a range.
_LEVELS: list[tuple[Level, tuple[str, ...]]] = [
    ("beginner", ("einsteiger", "anfänger")),
    ("intermediate", ("mittelstufe",)),
    ("advanced", ("fortgeschritten",)),
]

_GENRES: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballett", "ballet", "klassisch", "classical")),
    ("contemporary", ("contemporary", "modern", "zeitgenöss")),
]


def _dates(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    d1, m1, y1, d2, m2, y2 = (int(g) for g in m.groups())
    try:
        return date(y1, m1, d1), date(y2, m2, d2)
    except ValueError:
        return None, None


def _ages(text: str) -> dict | None:
    m = _AGE.search(text)
    return {"min": int(m.group(1)), "max": None} if m else None


def _levels(text: str) -> list[Level]:
    low = text.lower()
    return [lvl for lvl, keys in _LEVELS if any(k in low for k in keys)]


def _cycle_tag(title: str, start: date) -> tuple[str, str]:
    """(slug-suffix, season-label) distinguishing same-year cycles by their
    German season word (Oster/Herbst/…), falling back to the start month."""
    low = title.lower()
    for word, tag in (
        ("oster", "spring"),
        ("frühjahr", "spring"),
        ("herbst", "autumn"),
        ("sommer", "summer"),
        ("winter", "winter"),
    ):
        if word in low:
            label = {
                "oster": "Oster",
                "frühjahr": "Frühjahr",
                "herbst": "Herbst",
                "sommer": "Sommer",
                "winter": "Winter",
            }[word]
            return tag, f"{label} {start.year}"
    tag = {3: "spring", 4: "spring", 10: "autumn"}.get(start.month, "edition")
    return tag, str(start.year)


# --- per-page edition extraction ---------------------------------------------


def _termine_editions(html: str) -> list[dict]:
    """Ballet editions from the calendar page. Each sits in its own
    `<div align="center">`: `<u>TITLE</u> (ages levels) >>>start-end<<< venue`."""
    tree = HTMLParser(html)
    out: list[dict] = []
    for div in tree.css('div[align="center"]'):
        text = parse.clean(div.text(separator=" "))
        low = text.lower()
        if "ballett" not in low or "breaking" in low:
            continue
        start, end = _dates(text)
        if start is None:
            continue
        u = div.css_first("u")
        title = parse.clean(u.text()) if u else text.split("(")[0]
        paren = re.search(r"\(([^)]*)\)", text)
        note = paren.group(1) if paren else ""
        out.append(
            {
                "title": title.title(),
                "start": start,
                "end": end,
                "ageRange": _ages(note),
                "level": _levels(note),
                "price": None,
                "notes": parse.clean(text.split("<<<")[0].replace(">>>", " ")),
            }
        )
    return out


# "180,00 € Herbst Ballett Intensive Days in Berlin 26.10.2026-29.10.2026
#  wann: täglich 10.00-14.00 Uhr … wo: Samuel`s Dance Hall … Download"
_ANM_BALLET = re.compile(
    r"(\d+[.,]\d{2})\s*€\s*([^€0-9]*?Ballett[^€0-9]*?)\s*"
    + _DATE
    + r"\s*[-–]\s*"
    + _DATE
    + r".*?wann:\s*(.*?)\s*(?:wo:|Download|$)",
    re.IGNORECASE | re.DOTALL,
)


def _anmeldung_editions(html: str) -> list[dict]:
    """Ballet editions from the registration page (price + daily hours)."""
    tree = HTMLParser(html)
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""
    out: list[dict] = []
    for m in _ANM_BALLET.finditer(text):
        raw_price, title, d1, m1, y1, d2, m2, y2, hours = m.groups()
        if "breaking" in title.lower():
            continue
        try:
            start, end = date(int(y1), int(m1), int(d1)), date(int(y2), int(m2), int(d2))
        except ValueError:
            continue
        amount = parse.parse_amount(raw_price)
        prices = (
            [Price(amount=amount, currency="EUR", label="Tuition", includes=["tuition"])]
            if amount is not None
            else []
        )
        out.append(
            {
                "title": parse.clean(title),
                "start": start,
                "end": end,
                "ageRange": _ages(title),
                "level": [],
                "price": prices,
                "notes": parse.clean(f"{d1}.{m1}.{y1}-{d2}.{m2}.{y2} {hours}"),
            }
        )
    return out


# --- detail page: program genres + faculty (applied to its own edition) ------

_DETAIL_DATE = re.compile(r"(\d{1,2})\.(\d{1,2})\.?\s*[-–]\s*(\d{1,2})\.(\d{1,2})\.?(\d{4})")
# "Sandra - Samuels Crew Member" — one first-name trainer per line.
_TRAINER = re.compile(r"^([A-ZÄÖÜ][a-zäöüß]+)\s*[-–]\s*(.{3,120})$")
# Credential strings that name a real teaching institution → affiliation.
_INSTITUTIONS: list[tuple[str, str, bool | None]] = [
    ("samuel", "Samuel's Dance Hall", True),
    ("palucca", "Palucca Hochschule für Tanz Dresden", None),
]


def _detail_program(html: str) -> dict | None:
    """The Ballett Days program page: its dates, genres and trainers. Returned so
    callers can enrich the matching dated edition (faithful: it describes one)."""
    tree = HTMLParser(html)
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""
    dm = _DETAIL_DATE.search(text)
    if dm is None:
        return None
    d1, m1, d2, m2, year = (int(g) for g in dm.groups())
    try:
        start, end = date(year, m1, d1), date(year, m2, d2)
    except ValueError:
        return None
    genres = parse.match_genres(text, _GENRES, default=["classical"])
    teachers: list[Teacher] = []
    seen: set[str] = set()
    for div in tree.css("li, div"):
        line = parse.clean(div.text())
        tm = _TRAINER.match(line)
        if tm is None:
            continue
        name, credential = tm.group(1), tm.group(2).lower()
        if name in seen or name.lower() in {"impressum", "datenschutz"}:
            continue
        seen.add(name)
        affs = [
            Affiliation(organization=org, current=cur)
            for needle, org, cur in _INSTITUTIONS
            if needle in credential
        ]
        teachers.append(Teacher(name=name, affiliations=affs))
    return {"start": start, "end": end, "genres": genres, "teachers": teachers}


# --- assembly -----------------------------------------------------------------


def _build_offerings(termine: str, anmeldung: str, detail: str, today: date) -> list[Offering]:
    by_key: dict[tuple[date | None, date | None], dict] = {}
    for ed in _termine_editions(termine) + _anmeldung_editions(anmeldung):
        key = (ed["start"], ed["end"])
        if key in by_key:
            # Union complementary fields if the same edition is on both pages.
            cur = by_key[key]
            for field in ("ageRange", "level", "price"):
                if not cur.get(field) and ed.get(field):
                    cur[field] = ed[field]
        else:
            by_key[key] = ed

    if not by_key:
        # Degraded fetch (challenge page / restructure) must not empty the store.
        raise RuntimeError("sommer_tanz_camp_berlin: no ballet editions found")

    program = _detail_program(detail)

    offerings: list[Offering] = []
    for (start, end), ed in sorted(by_key.items(), key=lambda kv: kv[0][0] or date.max):
        assert start is not None
        tag, season = _cycle_tag(ed["title"], start)
        genres: list[Genre] = parse.match_genres(ed["title"], _GENRES, default=["classical"])
        teachers: list[Teacher] = []
        if program and program["start"] == start and program["end"] == end:
            genres = program["genres"]
            teachers = program["teachers"]
        offerings.append(
            Offering(
                id=f"sommer-tanz-camp-berlin/ballett-{start.year}-{tag}",
                source=Source(provider="sommer-tanz-camp-berlin", url=BASE, scrapedAt=now_utc()),
                title=ed["title"],
                genres=genres,
                level=ed.get("level") or [],
                ageRange=ed.get("ageRange"),
                organization=ORG,
                location=Location(venue=VENUE, city="Berlin", country="DE"),
                schedule=Schedule(
                    season=season,
                    start=start,
                    end=end,
                    timezone="Europe/Berlin",
                    notes=ed.get("notes"),
                ),
                teachers=teachers,
                prices=ed.get("price") or [],
                application=Application(url=ANMELDUNG_URL, requirements=[NoneReq()]),
            )
        )
    return offerings
