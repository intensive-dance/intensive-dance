"""Staatsballett Berlin — holiday ballet intensives (Feriencamp / Ferienkurs), Berlin.

API FIRST
The site is TYPO3, plain server-rendered HTML — a direct fetch returns the full
content (no WordPress REST, no `ld+json` on the course pages, no JS render or
proxy). The education overview (`/tanz-ist-klasse.html`) links ~20 program detail
pages under `/spielplan/stueck-detail/stid/<slug>/<id>.html`, but the vast
majority are out-of-scope outreach (inclusive/Parkinson's/cerebral-palsy courses,
seniors, family workshops, beginner tasters, teacher training). Rather than
auto-classify that noisy list every hour, we PIN the two stable detail pages that
are genuine dated student ballet intensives (same approach as balletto_di_roma's
fixed program URLs).

DISCOVERY — two programs, one Offering per dated edition:
  1. FERIENCAMP (stid/feriencamp/161) — a five-day camp for ages 12–16 with ≥5
     years' ballet, classical training + a variation in the morning, contemporary
     / own choreography in the afternoon, €200, at the Staatsoper Unter den
     Linden. It carries TWO timeblock start dates → two Offerings (autumn 2026,
     spring 2027); the camp is "fünftägig", so each end is start + 4 days.
  2. FERIENKURS „SPITZE AUF SPITZE" (stid/ferienangebot/142) — a pointe-technique
     course for ages 14–20 with prior pointe experience + own shoes, €100, at the
     Deutsche Oper. It runs on non-consecutive days (9, 10, 13, 14 July 2026), so
     the span is read from the explicit date sentence, not start + duration.

OUT OF SCOPE (not emitted): the Ferienkurs „Ich tanz' nach meiner Pfeife" (for
children with cerebral palsy — creative dance, not a classical intensive), and
the recurring single-session TanzTanz repertoire workshops (open drop-in master
sessions, not multi-day intensives).

PREREQUISITES vs REQUIREMENTS: both pin "Vorkenntnisse" (years of ballet / prior
pointe) — a participation prerequisite, NOT an audition/photo/video, so
`application.requirements` stays empty (no admission gate is stated).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-11)
- TYPO3 detail pages parsed from the visually-hidden timeblock date spans.
- One program → multiple Offerings (Feriencamp's two dated editions).
- Consecutive duration ("fünftägig" → start+4) vs an explicit non-consecutive
  date span (Spitze's "9. und 10. … 13. und 14. Juli").
- German parsing: month map, "zwischen N und M Jahren" ages, "N Euro" price,
  classical/contemporary/pointe genres scoped to the description.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

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
    now_utc,
)

BASE = "https://www.staatsballett-berlin.de/spielplan/stueck-detail/stid"
FERIENCAMP_URL = f"{BASE}/feriencamp/161.html"
SPITZE_URL = f"{BASE}/ferienangebot/142.html"

ORG = Organization(
    name="Staatsballett Berlin", slug="staatsballett-berlin-feriencamp", country="DE", city="Berlin"
)

_MONTHS = {
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}
_MONTHALT = "|".join(_MONTHS)

_DURATION = {"drei": 3, "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7}

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("klassischen tanz", "ballett", "klassisch")),
    ("contemporary", ("zeitgenössisch",)),
    ("pointe", ("spitze", "spitzentanz", "spitzenschuh")),
]


def scrape(client: httpx.Client) -> list[Offering]:
    offerings = _feriencamp(_get(client, FERIENCAMP_URL))
    offerings.append(_spitze(_get(client, SPITZE_URL)))
    offerings.sort(key=lambda o: o.id)
    return offerings


def _get(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    resp.raise_for_status()
    return resp.text


def _content_text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""
    cut = text.find("Zurück zum Seitenanfang")
    return text[:cut] if cut >= 0 else text


# Course dates live in visually-hidden spans: "Montag, 19. Oktober 2026 9:30".
_TIMEBLOCK = re.compile(r'visually-hidden">([^<]*\d{4}[^<]*)</span>')
_DATE = re.compile(r"(\d{1,2})\.\s+(" + _MONTHALT + r")\s+(\d{4})", re.IGNORECASE)


def _timeblock_dates(html: str) -> list[date]:
    dates: list[date] = []
    for raw in _TIMEBLOCK.findall(html):
        m = _DATE.search(raw)
        if m:
            day, month, year = m.groups()
            dates.append(date(int(year), _MONTHS[month.lower()], int(day)))
    return dates


def _duration_days(text: str, default: int = 5) -> int:
    m = re.search(r"(" + "|".join(_DURATION) + r")tägig", text, re.IGNORECASE)
    return _DURATION[m.group(1).lower()] if m else default


def _ages(text: str) -> dict | None:
    m = re.search(r"zwischen\s+(\d{1,2})\s+und\s+(\d{1,2})\s+Jahren", text, re.IGNORECASE)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _price(text: str) -> list[Price]:
    m = re.search(r"(\d{1,4})\s*Euro", text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    return (
        [Price(amount=amount, currency="EUR", label="Tuition", includes=["tuition"])]
        if amount
        else []
    )


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _date_sentence(text: str) -> str | None:
    m = re.search(r"Der Kurs findet.*?statt", text, re.IGNORECASE | re.DOTALL)
    return parse.clean(m.group(0)) if m else None


def _feriencamp(html: str) -> list[Offering]:
    text = _content_text(html)
    span = _duration_days(text) - 1
    ages = _ages(text)
    genres = _genres(text)
    prices = _price(text)
    notes = _date_sentence(text)
    offerings: list[Offering] = []
    for start in _timeblock_dates(html):
        end = start + timedelta(days=span)
        year = start.year
        offerings.append(
            Offering(
                id=f"staatsballett-berlin-feriencamp/feriencamp-{year}",
                source=Source(
                    provider="staatsballett-berlin-feriencamp",
                    url=FERIENCAMP_URL,
                    scrapedAt=now_utc(),
                ),
                title=f"Feriencamp {year}",
                genres=genres,
                ageRange=ages,
                organization=ORG,
                location=Location(venue="Staatsoper Unter den Linden", city="Berlin", country="DE"),
                schedule=Schedule(
                    season=str(year),
                    start=start,
                    end=end,
                    timezone="Europe/Berlin",
                    notes=notes,
                ),
                prices=prices,
                application=Application(url=FERIENCAMP_URL),
            )
        )
    return offerings


# Spitze runs on non-consecutive days, so span is read from the date sentence.
_SENTENCE_DAYS = re.compile(r"(\d{1,2})\.")


def _spitze(html: str) -> Offering:
    text = _content_text(html)
    starts = _timeblock_dates(html)
    sentence = _date_sentence(text) or ""
    mon = re.search(r"(" + _MONTHALT + r")", sentence, re.IGNORECASE)
    days = [int(d) for d in _SENTENCE_DAYS.findall(sentence)]
    year = starts[0].year if starts else (date.today().year)
    start = end = None
    if mon and days:
        month = _MONTHS[mon.group(1).lower()]
        start = date(year, month, min(days))
        end = date(year, month, max(days))
    return Offering(
        id=f"staatsballett-berlin-feriencamp/spitze-auf-spitze-{year}",
        source=Source(
            provider="staatsballett-berlin-feriencamp", url=SPITZE_URL, scrapedAt=now_utc()
        ),
        title=f"Ferienkurs „Spitze auf Spitze“ {year}",
        genres=_genres(text),
        ageRange=_ages(text),
        organization=ORG,
        location=Location(venue="Deutsche Oper Berlin", city="Berlin", country="DE"),
        schedule=Schedule(
            season=str(year), start=start, end=end, timezone="Europe/Berlin", notes=sentence or None
        ),
        prices=_price(text),
        application=Application(url=SPITZE_URL),
    )
