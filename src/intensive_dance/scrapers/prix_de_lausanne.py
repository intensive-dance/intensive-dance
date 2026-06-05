"""Prix de Lausanne (Lausanne, CH) — the register's first `competition`.

API FIRST: the site runs WordPress (`/wp-json/` = 200; root 301s to `www`). The
practical-information page carries no Event JSON-LD, so we read its
`content.rendered` over the REST API (page slug `practical_information`) rather
than scraping HTML — one paragraph that states the edition title, the date span
and the venue: "The Prix de Lausanne 2027 will take place from 31 January to
7 February 2027, at Beaulieu Lausanne, Switzerland."

DISCOVERY: one `Offering` per *edition* (year-stamped slug), keyed
`prix-de-lausanne/{year}`. The practical-information page always advertises the
*next* edition, so the id rolls forward when the season advances — the 2026
edition already ran and is gone from the page, leaving only 2027. We drop any
edition whose end date is already past (fail-open on "next edition only").

WHAT THE PAGE GIVES US — and what it doesn't (verified live 2026-06-05):
  - KIND = competition (judged for ranking/prizes), the first in the register —
    distinct from an `audition-tour`.
  - DATES + VENUE come straight from the live paragraph; season = the edition year.
  - GENRES = classical + contemporary: the competition is judged over a classical
    and a contemporary variation (the live `classical-variations` /
    `contemp-variations-audios` pages confirm both rounds). Stable to the format,
    not date-parsed.
  - APPLICATION: candidate registration for the next edition is not yet open (the
    `/candidates/` and `/registration/` slugs 301 to old galleries — no live
    eligibility/rules page exists yet), so we leave `application.status` null with
    a note. We do NOT invent the registration deadline, fees, age range or the
    video/photo/medical requirements: none are on the live page, and the
    per-edition rules PDF that carries them isn't published for 2027 yet. Faithful
    over complete — those fields stay empty until the page states them.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from intensive_dance import parse, wp
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

BASE = "https://www.prixdelausanne.org"
INFO_SLUG = "practical_information"

ORG = Organization(name="Prix de Lausanne", slug="prix-de-lausanne", country="CH", city="Lausanne")

# Both rounds the competition is judged on; stable to the format, not the prose.
GENRES: list[Genre] = ["classical", "contemporary"]

_REGISTRATION_NOTE = (
    "Candidate registration for the next edition is not yet open on the official site."
)


def scrape(client: httpx.Client) -> list[Offering]:
    page = wp.fetch_page(client, INFO_SLUG, base=BASE)
    if page is None:
        return []
    return _build_offerings(page, date.today())


def _build_offerings(page: dict, today: date) -> list[Offering]:
    text = wp.plain_text(page["content"]["rendered"])
    start, end = _dates(text)
    if start is None or end is None or end < today:
        return []  # only the next, not-yet-run edition is in scope

    season = str(end.year)
    return [
        Offering(
            id=f"prix-de-lausanne/{season}",
            source=Source(provider="prix-de-lausanne", url=page["link"], scrapedAt=now_utc()),
            title=_title(text, season),
            genres=GENRES,
            kind="competition",
            organization=ORG,
            location=_location(text),
            schedule=Schedule(
                season=season,
                start=start,
                end=end,
                timezone="Europe/Zurich",
                notes=_dates_note(text),
            ),
            application=Application(notes=_REGISTRATION_NOTE),
        )
    ]


# "from 31 January to 7 February 2027" — the year sits on the closing date only,
# and the span can run across a month boundary (it never crosses a year here, but
# we resolve the start year defensively the same way the dated scrapers do).
_RANGE = re.compile(
    r"from\s+(\d{1,2})\s+(" + parse.MONTHALT + r")\s+to\s+"
    r"(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(20\d\d)",
    re.IGNORECASE,
)


def _dates(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    d1, m1, d2, m2, year = m.groups()
    end_year = int(year)
    start_month, end_month = parse.MONTHS[m1.lower()], parse.MONTHS[m2.lower()]
    start_year = end_year - 1 if start_month > end_month else end_year
    return date(start_year, start_month, int(d1)), date(end_year, end_month, int(d2))


def _dates_note(text: str) -> str | None:
    m = _RANGE.search(text)
    return parse.clean(m.group(0)) if m else None


# "The Prix de Lausanne 2027 will take place …" — prefer the title as written;
# fall back to a year-stamped name if the phrasing changes.
_TITLE = re.compile(r"(Prix de Lausanne\s+20\d\d)", re.IGNORECASE)


def _title(text: str, season: str) -> str:
    m = _TITLE.search(text)
    return parse.clean(m.group(1)) if m else f"Prix de Lausanne {season}"


# "at Beaulieu Lausanne, Switzerland." — venue + city before the country.
_VENUE = re.compile(r"\bat\s+(.+?),\s*Switzerland", re.IGNORECASE)


def _location(text: str) -> Location:
    m = _VENUE.search(text)
    venue = parse.clean(m.group(1)) if m else None
    return Location(venue=venue, city="Lausanne", country="CH")
