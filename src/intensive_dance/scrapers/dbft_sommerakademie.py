"""DBfT — Sommerakademie Junior, a one-week classical ballet intensive in Dortmund.

API FIRST
The DBfT site is plain server-rendered HTML (latin-1 encoded), no WordPress REST
and no `ld+json` on the course page — a direct fetch returns the full content, so
this is a structural `selectolax` text scrape. The provider's registered URL
(`/Berufsregister/Sommerakademie-Junior/`) 404s; the live page lives under
`/Fortbildungen-Weiterbildungen/Seminarangebot/Sommerakademie-Junior/index.html`.

DISCOVERY — one dated edition = one Offering.
The page documents the current "Aktuelles Programm <year>": a single five/six-day
"intensive Ballettwoche" for ages 13–15 with strong classical-ballet
groundwork. (Historically the DBfT split it into two leveled courses, "Junior I /
Junior II"; the current programme text describes one cohort, so we emit one
Offering, year-stamped because the source labels the edition by year.)

The application is a separate Tally form (`tally.so/r/...`) whose questions load
via JS and aren't in any fetched page, so the submission requirements aren't
stated — `application.requirements` stays empty; only the stated deadline and the
form URL are recorded.

The stated "sehr gute Vorkenntnisse im Klassischen Tanz" is a participation
prerequisite, not an audition/photo/video gate, so it does not become a
`requirement` (same call as staatsballett_berlin_feriencamp).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-11)
- Numeric German date span ("Mo, 24.08.2026 bis Sa, 29.08.2026"), scoped to the
  "Zeitraum:" sentence so the same-format application deadline ("15.06.2026")
  isn't mis-read as a course date.
- "im Alter von 13 bis 15 Jahren" → age_range; "Kursgebühr: 360 €" → Price (EUR).
- A stated application deadline + form URL with empty (unknown) requirements.
- classical-only genre scoped to the description.
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
    Schedule,
    Source,
    now_utc,
)

PAGE = (
    "https://www.dbft.de/Fortbildungen-Weiterbildungen/"
    "Seminarangebot/Sommerakademie-Junior/index.html"
)
SLUG = "dbft-sommerakademie"

ORG = Organization(name="DBfT — Sommerakademie Junior", slug=SLUG, country="DE", city="Dortmund")

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("klassischen tanz", "ballett", "klassisch")),
    ("contemporary", ("zeitgenössisch", "zeitgenössische")),
]

# DD.MM.YYYY — German numeric date, used for both the course span and deadline.
_NUM_DATE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text)


def _content_text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _num_date(raw: str) -> date | None:
    m = _NUM_DATE.search(raw)
    if not m:
        return None
    day, month, year = (int(g) for g in m.groups())
    return date(year, month, day)


def _course_span(text: str) -> tuple[date | None, date | None, str | None]:
    """Start/end + raw notes, scoped to the 'Zeitraum:' sentence."""
    m = re.search(r"Zeitraum:\s*(.*?)(?:Ort:|Zeit:|Kursgebühr:|$)", text, re.IGNORECASE)
    if not m:
        return None, None, None
    segment = parse.clean(m.group(1))
    dates = [date(int(y), int(mo), int(d)) for d, mo, y in _NUM_DATE.findall(segment)]
    start = dates[0] if dates else None
    end = dates[1] if len(dates) > 1 else None
    return start, end, segment or None


def _deadline(text: str) -> date | None:
    m = re.search(r"bis\s+(\d{1,2}\.\d{1,2}\.\d{4})\s+möglich", text, re.IGNORECASE)
    return _num_date(m.group(1)) if m else None


def _ages(text: str) -> dict | None:
    m = re.search(r"Alter\s+von\s+(\d{1,2})\s+bis\s+(\d{1,2})\s+Jahren", text, re.IGNORECASE)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _price(text: str) -> list[Price]:
    m = re.search(r"Kursgebühr:\s*(\d{1,4})\s*€", text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    return (
        [Price(amount=amount, currency="EUR", label="Kursgebühr", includes=["tuition"])]
        if amount
        else []
    )


def _venue(text: str) -> str | None:
    m = re.search(r"Ort:\s*(.*?)(?:Zeit:|Kursgebühr:|$)", text, re.IGNORECASE)
    return parse.clean(m.group(1)) if m else None


def _form_url(html: str) -> str | None:
    m = re.search(r'href="(https://tally\.so/[^"]+)"', html)
    return m.group(1) if m else None


def _year(text: str, fallback: date | None) -> int | None:
    m = re.search(r"Sommerakademie Junior\s+(20\d\d)", text) or re.search(
        r"Programm\s+(20\d\d)", text
    )
    if m:
        return int(m.group(1))
    return fallback.year if fallback else None


def _build_offerings(html: str) -> list[Offering]:
    text = _content_text(html)
    start, end, span_notes = _course_span(text)
    year = _year(text, start)
    season = str(year) if year else "unknown"

    return [
        Offering(
            id=f"{SLUG}/sommerakademie-junior-{year}" if year else f"{SLUG}/sommerakademie-junior",
            source=Source(provider=SLUG, url=PAGE, scrapedAt=now_utc()),
            title=f"Sommerakademie Junior {year}" if year else "Sommerakademie Junior",
            genres=parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"]),
            ageRange=_ages(text),
            organization=ORG,
            location=Location(venue=_venue(text), city="Dortmund", country="DE"),
            schedule=Schedule(
                season=season,
                start=start,
                end=end,
                timezone="Europe/Berlin",
                notes=span_notes,
            ),
            prices=_price(text),
            application=Application(
                deadline=_deadline(text),
                url=_form_url(html) or PAGE,
            ),
        )
    ]
