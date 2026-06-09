"""Japan Ballet Intensives (JBI), Osaka (JP) — its short ballet intensive.

JBI is run by Wilfried Jacobs (Head of Faculty, Mosa Ballet School, Liège, BE),
who brings an international guest faculty to a two-day intensive in Osaka. The
intensive doubles as a Japan audition for the Mosa Ballet School Summer Intensive.

API FIRST: none usable. The site (`jbi-japanballetintensives.com`) is a **Wix**
build — no public content API we may use — but, like the other Wix providers in
the register, it server-renders the full text into the static HTML (dates, ages,
prices, faculty all present; note the `ssr-caching` response header), so a plain
per-page fetch is enough. No JS render or proxy escalation needed (verified live
2026-06-09). The site is bilingual: English content pages plus Japanese mirrors
under `/blank-*`; the English pages carry the same facts, so we parse those.

DISCOVERY: the site advertises **one** dated edition — the *Spring Intensive in
Osaka, 21–22 March 2026* — described across sibling pages (home/schedule/courses/
tuition/faculty/pianists). We emit a single `Offering`, season-keyed from the
parsed year so the id rolls forward when the page advances. The og:title carries a
stale "Christmas Intensive" SEO leftover, but no Christmas-edition content, dates,
or page exists anywhere on the site (confirmed via the sitemap), so nothing is
invented for it. Per IDR-24 the past Spring edition is kept, not dropped — "past"
is derived consumer-side from `schedule.end < today`.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-09):
  - DATES: a clean English span "March 21 - 22, 2026" on the schedule page.
  - AGES: open band "age 13 and above ... minimum of 3 years in ballet education"
    — a min bound of 13, no upper bound (model's null-bound convention).
  - GENRES: classical + pointe (Classic Ballet & Pointes) + contemporary
    (Contemporary Dance), keyword-matched against the *courses* curriculum, not
    the org's marketing blurb (which also name-drops Character Dance — not taught
    this edition, so not claimed).
  - PRICES: a two-rung JPY ladder, both tax-inclusive (税込 per the JP mirror) —
    a 2-day pass (4 classes, 25,000 JPY) and a single day (2 classes, 15,000 JPY),
    plus a 50% sibling reduction kept as a price note. The 2-day amount is split
    by a Wix node ("25 .000 Yen"), so the amount regex tolerates inner whitespace.
  - FACULTY: an international guest (Wilfried Jacobs, Classical Ballet, with a
    Mosa Ballet School affiliation) plus a local contemporary teacher (Minoru
    Harata) and the pianist (Noriko Yamamoto), each captured only when present.
  - STATUS: the home page says "Registrations are now closed" — that closes the
    *application*, not the course, so `lifecycle` stays `scheduled`; the audition
    note (the intensive doubles as a Mosa Summer Intensive audition) is kept
    verbatim in `application.notes`. No audition brief (photo/video) is described,
    so requirements stay `[]` ("not stated").
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
    ApplicationStatus,
    Genre,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.jbi-japanballetintensives.com"
# The English content pages of the current edition; each contributes some facts.
PAGES = ["", "schedule", "courses", "tuition", "faculty", "pianists"]

ORG = Organization(
    name="Japan Ballet Intensives",
    slug="japan-ballet-intensives",
    country="JP",
    city="Osaka",
)

# Wix peppers the markup with zero-width spaces and BOMs; drop them before parsing.
_ZERO_WIDTH = ("​", "﻿", "‌", "‍")


def scrape(client: httpx.Client) -> list[Offering]:
    texts: dict[str, str] = {}
    for page in PAGES:
        resp = client.get(f"{BASE}/{page}", follow_redirects=True)
        resp.raise_for_status()
        texts[page] = _page_text(resp.text)
    return _build_offerings(texts, date.today())


def _page_text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    raw = tree.body.text(separator=" ") if tree.body else ""
    for ch in _ZERO_WIDTH:
        raw = raw.replace(ch, "")
    return parse.clean(raw)


def _build_offerings(texts: dict[str, str], today: date) -> list[Offering]:
    start, end = _date_range(texts.get("schedule", ""))
    if start is None or end is None:
        return []  # no dated edition parseable → emit nothing (don't fabricate)
    season = str(start.year)
    home = texts.get("", "")
    courses = texts.get("courses", "")

    offering = Offering(
        id=f"japan-ballet-intensives/spring-intensive-osaka-{season}",
        source=Source(provider="japan-ballet-intensives", url=f"{BASE}/", scrapedAt=now_utc()),
        title=f"Spring Ballet Intensive in Osaka {season}",
        genres=_genres(courses),
        ageRange=_age_range(courses),
        organization=ORG,
        location=Location(venue="Garage Art Space", city="Osaka", country="JP"),
        schedule=Schedule(season=season, start=start, end=end, timezone="Asia/Tokyo"),
        teachers=_teachers(home, texts.get("faculty", ""), texts.get("pianists", "")),
        prices=_prices(texts.get("tuition", "")),
        application=Application(
            status=_status(home),
            url=f"{BASE}/registration",
            notes=_audition_note(home),
        ),
    )
    return [offering]


# --- dates: clean English span "March 21 - 22, 2026" on the schedule page -------

_RANGE = re.compile(
    rf"({parse.MONTHALT})\s+(\d{{1,2}})\s*-\s*(\d{{1,2}}),\s*(\d{{4}})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    month = parse.MONTHS[m.group(1).lower()]
    year = int(m.group(4))
    return date(year, month, int(m.group(2))), date(year, month, int(m.group(3)))


# --- ages: "age 13 and above ... minimum of 3 years in ballet education" --------

_AGE_MIN = re.compile(r"age\s+(\d{1,2})\s+and above", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    m = _AGE_MIN.search(text)
    return {"min": int(m.group(1)), "max": None} if m else None


# --- genres: keyword-matched against the courses curriculum only ----------------
#
# The courses page lists "Classic Ballet & Pointes" and "Contemporary Dance". The
# org's marketing blurb also names Character Dance, but it isn't on this edition's
# curriculum, so it's deliberately not claimed.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classic ballet", "classical")),
    ("pointe", ("pointe",)),
    ("contemporary", ("contemporary",)),
]


def _genres(courses_text: str) -> list[Genre]:
    return parse.match_genres(courses_text.lower(), _GENRE_KEYWORDS, default=["classical"])


# --- prices: the two-rung JPY ladder, tax-inclusive (税込 in the JP mirror) -------
#
# "2-Day Workshop 4 classes 25.000 Yen" / "One day 2 classes 15.000 Yen". A Wix
# node split inserts a stray space into the 2-day amount ("25 .000"), so the
# amount group tolerates inner whitespace before parsing.

_PRICE_2DAY = re.compile(r"2-Day Workshop\s+\d+\s+classes\s+([\d.,\s]+?)\s*Yen", re.IGNORECASE)
_PRICE_1DAY = re.compile(r"One day\s+\d+\s+classes\s+([\d.,\s]+?)\s*Yen", re.IGNORECASE)
_SIBLING = re.compile(r"(50% reduction[^.]*\.)", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    sibling = _SIBLING.search(text)
    note = parse.clean(sibling.group(1)) if sibling else None
    prices: list[Price] = []
    for label, pat in (
        ("2-Day Workshop (4 classes, tax incl.)", _PRICE_2DAY),
        ("One day (2 classes, tax incl.)", _PRICE_1DAY),
    ):
        m = pat.search(text)
        if not m:
            continue
        amount = parse.parse_amount(m.group(1).replace(" ", ""))
        if amount is None:
            continue
        prices.append(
            Price(amount=amount, currency="JPY", label=label, includes=["tuition"], notes=note)
        )
    return prices


# --- teachers: international guest + local contemporary teacher + pianist --------
#
# Wilfried Jacobs teaches the classical classes (Head of Faculty, Mosa Ballet
# School, Liège); Minoru Harata is the "local" contemporary teacher; Noriko
# Yamamoto is the pianist. Each is added only when its name is present.

_HARATA = re.compile(r"contemporary teacher in Mr\.\s*([A-Z][a-z]+\s+[A-Z][a-z]+)")
_PIANIST = re.compile(r"PIANIST\s+([A-Z][a-z]+\s+[A-Z][a-z]+)")


def _teachers(home: str, faculty: str, pianists: str) -> list[Teacher]:
    teachers: list[Teacher] = []
    if "Wilfried Jacobs" in faculty or "Wilfried Jacobs" in home:
        affiliations = []
        if "Mosa Ballet School" in faculty or "Mosa Ballet School" in home:
            affiliations.append(
                Affiliation(
                    organization="Mosa Ballet School",
                    slug="mosa-ballet-school",
                    role="Head of Faculty",
                    current=True,
                )
            )
        teachers.append(
            Teacher(name="Wilfried Jacobs", role="Classical Ballet", affiliations=affiliations)
        )
    hm = _HARATA.search(home)
    if hm:
        teachers.append(Teacher(name=parse.clean(hm.group(1)), role="Contemporary Dance (local)"))
    pm = _PIANIST.search(pianists)
    if pm:
        teachers.append(Teacher(name=parse.clean(pm.group(1)), role="Pianist"))
    return teachers


# --- application status + audition note -----------------------------------------

_AUDITION = re.compile(
    r"(During the Intensive, participants will have the opportunity to audition.*?"
    r"Lièg?e?,?\s*Belgium\.)"
)


def _status(home: str) -> ApplicationStatus | None:
    if re.search(r"Registrations? (are|is) now closed", home, re.IGNORECASE):
        return "closed"
    return None


def _audition_note(home: str) -> str | None:
    m = _AUDITION.search(home)
    return parse.clean(m.group(1)) if m else None
