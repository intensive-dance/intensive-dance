"""Hungarian Dance University (MTE), Budapest — public summer ballet intensives.

API FIRST
The site is WordPress with The Events Calendar (Tribe) + WooCommerce, but the
Tribe REST (`/wp-json/tribe/events/v1/...`) does NOT expose the two summer-course
pages (they 400 / aren't listed), and the WooCommerce fee options load via an AJAX
cart — not in the static markup. The course detail itself (dates, ages, curriculum,
deadline) IS server-rendered into the page HTML, so this is a plain `selectolax`
text scrape of two fixed course URLs (one EN, one HU). `ld+json` carries only
Yoast WebPage/Organization data, no Event.

DISCOVERY — one Offering per dated edition (two in 2026).
MTE is a full-time dance university, but it also runs two public, dated short-term
student intensives every summer (the "full-time school that also sells public
short courses" pattern):
  1. International Summer Intensive Ballet Course (ISIBC) — a 10-day pre-professional
     course (ages 14–24), classical + modern + repertoire, EN page.
  2. Nyári Balett Stúdió — a one-week course for younger students (ages 11–14),
     classical + modern + repertoire, HU page.
The full-time degree programs are out of scope and not emitted.

PRICES: the per-package fees (classes / +lunch / +accommodation / full) live only
in the WooCommerce AJAX cart, never in the static page text, so prices are left
empty (fail-open) rather than scraped non-deterministically.

REQUIREMENTS vs PREREQUISITES: ISIBC states "4 years of classical ballet training"
and (for female dancers) "3 years of pointe work" — participation prerequisites,
not an audition/photo/video submission, so `application.requirements` stays empty.
The optional in-course HDU audition / BBGP pre-selection classes are add-ons, not a
gate to attend. Pointe is a prerequisite, not a taught class, so it is NOT a genre.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-11)
- Two pages, two languages → two Offerings; genre matching scoped to the
  "course includes" / "oktató mesterek" curriculum clause so faculty bios don't
  leak genres.
- English same-month day span ("5–14 August 2026") and a Hungarian cross-month
  span ("2026. július 27. – augusztus 2.") with a local Hungarian month map.
- A closed cycle kept (Nyári's deadline is marked "LEZÁRULT" → status closed),
  per the keep-ended-cycles rule.
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
    Level,
    Location,
    Offering,
    Organization,
    Schedule,
    Source,
    now_utc,
)

SLUG = "hungarian-dance-university"
ISIBC_URL = "https://mte.eu/en/events/international-summer-intensive-ballet-course-2026/"
NYARI_URL = "https://mte.eu/esemenyek/nyari-balettkurzus-2026/"

ORG = Organization(name="Hungarian Dance University", slug=SLUG, country="HU", city="Budapest")
VENUE = Location(venue="Hungarian Dance University", city="Budapest", country="HU")

_HU_MONTHS = {
    "január": 1,
    "február": 2,
    "március": 3,
    "április": 4,
    "május": 5,
    "június": 6,
    "július": 7,
    "augusztus": 8,
    "szeptember": 9,
    "október": 10,
    "november": 11,
    "december": 12,
}
_HU_MONTHALT = parse.months_alt(_HU_MONTHS)

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical ballet", "klasszikus balett")),
    ("contemporary", ("modern technique", "modern repertoire", "moderntánc", "modern")),
    ("repertoire", ("repertoire", "repertoár")),
]


def scrape(client: httpx.Client) -> list[Offering]:
    offerings = [
        _build_isibc(_get(client, ISIBC_URL)),
        _build_nyari(_get(client, NYARI_URL)),
    ]
    offerings.sort(key=lambda o: o.id)
    return offerings


def _get(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    resp.raise_for_status()
    return resp.text


def _text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _genres(curriculum: str) -> list[Genre]:
    return parse.match_genres(curriculum, _GENRE_KEYWORDS, default=["classical"])


# --- ISIBC (English) ---

_ISIBC_DATES = re.compile(
    r"Dates:\s*(\d{1,2})\s*[–-]\s*(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
_ISIBC_AGES = re.compile(
    r"age limit.{0,80}?is\s*(\d{1,2})\s*[–-]\s*(\d{1,2})\s*years", re.IGNORECASE
)
_ISIBC_DEADLINE = re.compile(
    r"deadline\s*:\s*(" + parse.MONTHALT + r")\s+(\d{1,2})\.?\s+(\d{4})", re.IGNORECASE
)
_ISIBC_CURRICULUM = re.compile(r"course includes:(.*?)age limit", re.IGNORECASE | re.DOTALL)


def _build_isibc(html: str) -> Offering:
    text = _text(html)
    start = end = None
    notes = None
    m = _ISIBC_DATES.search(text)
    if m:
        d1, d2, mon, year = m.groups()
        month = parse.MONTHS[mon.lower()]
        start = date(int(year), month, int(d1))
        end = date(int(year), month, int(d2))
        notes = parse.clean(m.group(0))
    season = str(start.year) if start else "2026"

    ages = None
    am = _ISIBC_AGES.search(text)
    if am:
        ages = {"min": int(am.group(1)), "max": int(am.group(2))}

    deadline = None
    dm = _ISIBC_DEADLINE.search(text)
    if dm:
        deadline = date(int(dm.group(3)), parse.MONTHS[dm.group(1).lower()], int(dm.group(2)))

    cm = _ISIBC_CURRICULUM.search(text)
    genres = _genres(cm.group(1) if cm else text)

    return Offering(
        id=f"{SLUG}/international-summer-intensive-ballet-course-{season}",
        source=Source(provider=SLUG, url=ISIBC_URL, scrapedAt=now_utc()),
        title=f"International Summer Intensive Ballet Course {season}",
        genres=genres,
        level=_isibc_level(text),
        ageRange=ages,
        organization=ORG,
        location=VENUE,
        schedule=Schedule(
            season=season, start=start, end=end, timezone="Europe/Budapest", notes=notes
        ),
        application=Application(deadline=deadline, url=ISIBC_URL),
    )


def _isibc_level(text: str) -> list[Level]:
    return ["pre-professional"] if "professional" in text.lower() else []


# --- Nyári Balett Stúdió (Hungarian) ---

_NYARI_DATES = re.compile(
    r"Időpont:\s*(\d{4})\.\s*("
    + _HU_MONTHALT
    + r")\s*(\d{1,2})\.\s*[–-]\s*("
    + _HU_MONTHALT
    + r")\s*(\d{1,2})",
    re.IGNORECASE,
)
# The page sidebar lists many talent-program age bands; anchor on the course's own
# audience sentence ("Várjuk azon 11–14 éves …") so those don't get mis-picked.
_NYARI_AGES = re.compile(r"Várjuk azon\s*(\d{1,2})\s*[–-]\s*(\d{1,2})\s*éves", re.IGNORECASE)
_NYARI_DEADLINE = re.compile(r"határidő:\s*(\d{4})\.(\d{1,2})\.(\d{1,2})", re.IGNORECASE)
_NYARI_CURRICULUM = re.compile(
    r"oktató mesterek:(.*?)(?:További információ|$)", re.IGNORECASE | re.DOTALL
)


def _build_nyari(html: str) -> Offering:
    text = _text(html)
    start = end = None
    notes = None
    m = _NYARI_DATES.search(text)
    if m:
        year, m1, d1, m2, d2 = m.groups()
        start = date(int(year), _HU_MONTHS[m1.lower()], int(d1))
        end = date(int(year), _HU_MONTHS[m2.lower()], int(d2))
        notes = parse.clean(m.group(0))
    season = str(start.year) if start else "2026"

    ages = None
    am = _NYARI_AGES.search(text)
    if am:
        ages = {"min": int(am.group(1)), "max": int(am.group(2))}

    deadline = None
    status = None
    dm = _NYARI_DEADLINE.search(text)
    if dm:
        deadline = date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
    if "LEZÁRULT" in text:
        status = "closed"

    cm = _NYARI_CURRICULUM.search(text)
    genres = _genres(cm.group(1) if cm else text)

    return Offering(
        id=f"{SLUG}/nyari-balett-studio-{season}",
        source=Source(provider=SLUG, url=NYARI_URL, scrapedAt=now_utc()),
        title=f"Nyári Balett Stúdió {season}",
        genres=genres,
        ageRange=ages,
        organization=ORG,
        location=VENUE,
        schedule=Schedule(
            season=season, start=start, end=end, timezone="Europe/Budapest", notes=notes
        ),
        application=Application(status=status, deadline=deadline, url=NYARI_URL),
    )
