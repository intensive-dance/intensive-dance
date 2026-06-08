"""ART Ballet — ART Ballet Camp (Lato 2026), Gdynia (PL).

API FIRST: none. ART Ballet (Niepubliczna Szkoła Sztuki Tańca, Gdynia-Orłowo)
runs a plain custom PHP site — `/wp-json/` 302-redirects to the homepage (not
WordPress), and there is no schema.org `ld+json`, `__NEXT_DATA__` blob, or feed.
So this is a straight HTML scrape (selectolax) of the single `/warsztaty` page,
whose camp announcement sits whole in the static server-rendered markup (no JS).

LANGUAGE NOTE: the site is Polish-only (no `/en/` variant or language switch), so
the parse is **language-agnostic** — numeric/Polish-month dates, enum genres
matched on technique keywords. The only free text we emit is canonical English
(title, notes), so the committed data is deterministic.

DISCOVERY: one announcement runs the residential ART Ballet Camp at Hotel Gołuń
in **two summer 2026 sessions** ("Terminy: 7-16 lipca 2026 … 15-22 sierpnia
2026"). Same venue/genres, different dates → **one Offering per session** (id
`…/camp-golun-{start ISO}`), so each dated edition stays distinct and diffable.
Ended cycles are kept (IDR-24); "past" is derived from dates, never stored.

VERIFY-OR-DEFER: the page publishes the two dated sessions, the venue and the
class list — but **no fees, no age range and no named faculty**. We fail open:
emit only what's stated (prices `[]`, ageRange null, teachers `[]`) rather than
invent them.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - GENRES from the stated class list — classical ("taniec klasycznego"),
    repertoire ("Praca nad repertuarem … wariacji baletowych"), contemporary
    ("Taniec współczesny"); stretching/pilates and artistic play are not ballet
    genres and are not emitted.
  - SELECTIVITY + COMPETITION PREP — "Liczba miejsc ograniczona!" (limited places)
    and "Przygotowanie do nowego sezonu konkursowego" (prep for the new
    competition season) recorded in notes; no audition/photo/video submission is
    stated, so requirements stay [] (unknown).
  - The fail-open path: a public dated edition with prices/ages/faculty all
    unpublished — every such field left null/empty, not guessed.
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

BASE = "https://www.artballet.pl"
PAGE_URL = f"{BASE}/warsztaty"

ORG = Organization(name="ART Ballet", slug="art-ballet-gdynia", country="PL", city="Gdynia")

# Hotel Gołuń sits in the Wdzydze Landscape Park (Kashubia, Pomerania), where the
# residential camp is held — distinct from the school's home in Gdynia-Orłowo.
VENUE = "Hotel Gołuń"
VENUE_CITY = "Wdzydze"

# Polish month names → number, so the day-range dates parse from the Polish body.
# Genitive forms are what the text uses ("7-16 lipca", "15-22 sierpnia").
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

# A session span: "7-16 lipca 2026" / "15-22 sierpnia 2026" — a single-month day
# range (both days share the trailing month) with the year after the month.
_SESSION = re.compile(
    r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})",
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
    for start, end in _sessions(text):
        offerings.append(
            Offering(
                id=f"art-ballet-gdynia/camp-golun-{start.isoformat()}",
                source=Source(provider="art-ballet-gdynia", url=PAGE_URL, scrapedAt=now_utc()),
                title=f"ART Ballet Camp — Gołuń {start.year}",
                genres=genres,
                organization=ORG,
                location=Location(venue=VENUE, city=VENUE_CITY, country="PL"),
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


# --- sessions -----------------------------------------------------------------


def _sessions(text: str) -> list[tuple[date, date]]:
    """The dated session spans, deduped and chronologically ordered."""
    spans: list[tuple[date, date]] = []
    for m in _SESSION.finditer(text):
        d1, d2, month, year = m.groups()
        num = _MONTHS[month.lower()]
        y = int(year)
        span = (date(y, num, int(d1)), date(y, num, int(d2)))
        if span not in spans:
            spans.append(span)
    return sorted(spans)


# --- genres -------------------------------------------------------------------
#
# Matched against the stated class list ("Lekcje tańca klasycznego", "Praca nad
# repertuarem – nauka wariacji baletowych", "Taniec współczesny"), so the genres
# reflect classes actually taught. Stretching/pilates and the artistic-play and
# integration sessions are not ballet genres and are not emitted.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("klasyczn", "classical", "ballet", "balet")),
    ("repertoire", ("repertuar", "wariacj", "repertoire", "repertory")),
    ("contemporary", ("współczesn", "wspolczesn", "contemporary")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- application --------------------------------------------------------------
#
# No audition / photo / video submission is stated, so requirements stay []
# (unknown). What the source *does* say: places are limited ("Liczba miejsc
# ograniczona!") and the camp doubles as competition-season prep ("Przygotowanie
# do nowego sezonu konkursowego") — both kept as a selectivity/positioning note.

_LIMITED = re.compile(r"liczba\s+miejsc\s+ograniczona", re.IGNORECASE)
_COMPETITION = re.compile(r"sezonu\s+konkursowego", re.IGNORECASE)


def _application_notes(text: str) -> str | None:
    parts: list[str] = []
    if _LIMITED.search(text):
        parts.append("Places are limited.")
    if _COMPETITION.search(text):
        parts.append("Includes preparation for the new competition season.")
    return " ".join(parts) or None
