"""Staromestské baletné štúdio (Bratislava) — the youth "Letná škola tanca".

API FIRST
Laravel municipal site (Staromestské centrum kultúry), no WordPress REST, no
`ld+json`. The summer offering is one news article whose body is server-rendered
static HTML (a Word-paste with `SCXW…`/`NormalTextRun` spans and HTML entities),
so this is a structural `selectolax` text scrape of that page. A plain fetch with
our client works (no proxy). Slovak.

DISCOVERY — one in-scope youth intensive = one Offering.
The article lists five summer camps; three are run by the baletné štúdio. Only
the youth **"Letná škola tanca pre mládež 12 – 18 rokov"** (17–21 Aug 2026) is an
in-scope student intensive: daily ballet + contemporary + modern + variation
lessons, prior dance experience expected ("Skúsenosť s tancom … vítaná a
potrebná"). That is ONE Offering. NOT emitted (out of scope, recreational):
the two young-children dance day-camps ("Letný tanečný tábor" 8–11 and "Poldenný
… tábor" 5–7 — holiday tábory padded with acting workshops, theatre visits and
nature games, like the dropped Kinder editions elsewhere), and the non-dance
animation camp and English Summer Day Camp.

Because the per-course blocks share one template, the scraper slices the youth
block out by its heading and the next camp's heading before parsing, so the
younger camps' dates/prices/ages can't leak into it.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-12)
- Slovak numeric day span with the year once ("17. - 21. 8. 2026"), age band read
  from the heading ("12 – 18 rokov").
- Two `Price`s (standard + Staré Mesto-resident discount) in EUR, `includes`
  meals ("v cene sú zahrnuté obedy") + tuition; labelled.
- Genres classical + contemporary + repertoire keyed off the per-day curriculum
  line (balet / súčasný+moderný tanec / tanečná variácia).
- Registration form, no audition → empty requirements, status unstated.
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
    PriceInclude,
    Schedule,
    Source,
    now_utc,
)

SLUG = "staromestske-baletne-studio"
PAGE = (
    "https://staromestskecentrakultury.sk/novinka/132110/"
    "prihlaste-svoje-deti-do-nasich-letnych-taborov"
)
FORM = "https://forms.cloud.microsoft/e/FcLx0FdfvU"

ORG = Organization(name="Staromestské baletné štúdio", slug=SLUG, country="SK", city="Bratislava")
VENUE = Location(venue="Školská 14", city="Bratislava", country="SK")

# The youth block starts at this heading and runs until the next camp heading.
_BLOCK_START = "Letná škola tanca pre mládež"
_BLOCK_END = "English Summer Day Camp"

# "17. - 21. 8. 2026" — day-day.month.year, the year stated once.
_DATES = re.compile(r"(\d{1,2})\.\s*[-–]\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})")
# "12 – 18 rokov" in the heading.
_AGE = re.compile(r"(\d{1,2})\s*[–-]\s*(\d{1,2})\s*rokov", re.IGNORECASE)
# "Cena: 160 € / 144 € pre obyvateľstvo Starého mesta" — standard / resident.
_PRICES = re.compile(r"Cena:\s*([\d.,]+)\s*€\s*/\s*([\d.,]+)\s*€", re.IGNORECASE)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text)


def _text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _youth_block(text: str) -> str | None:
    start = text.find(_BLOCK_START)
    if start == -1:
        return None
    end = text.find(_BLOCK_END, start)
    return text[start:] if end == -1 else text[start:end]


def _dates(block: str) -> tuple[date | None, date | None, str | None]:
    m = _DATES.search(block)
    if not m:
        return None, None, None
    d1, d2, mon, year = (int(g) for g in m.groups())
    y = int(year)
    return date(y, mon, d1), date(y, mon, d2), parse.clean(m.group(0))


def _age_range(block: str) -> dict | None:
    m = _AGE.search(block)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _genres(block: str) -> list[Genre]:
    low = block.lower()
    genres: list[Genre] = []
    if "balet" in low:
        genres.append("classical")
    if "súčasný" in low or "moderný" in low:
        genres.append("contemporary")
    if "variácia" in low or "variáci" in low:
        genres.append("repertoire")
    return genres


def _prices(block: str) -> list[Price]:
    m = _PRICES.search(block)
    if not m:
        return []
    standard = parse.parse_amount(m.group(1))
    resident = parse.parse_amount(m.group(2))
    includes: list[PriceInclude] = ["tuition", "meals"] if "obedy" in block.lower() else ["tuition"]
    prices: list[Price] = []
    if standard is not None:
        prices.append(Price(amount=standard, currency="EUR", includes=includes))
    if resident is not None:
        prices.append(
            Price(
                amount=resident,
                currency="EUR",
                includes=includes,
                label="Obyvatelia Starého Mesta",
            )
        )
    return prices


def _build_offerings(html: str) -> list[Offering]:
    block = _youth_block(_text(html))
    if block is None:
        return []
    start, end, notes = _dates(block)
    season = str(start.year) if start else "2026"
    return [
        Offering(
            id=f"{SLUG}/letna-skola-tanca-mladez-{season}",
            source=Source(provider=SLUG, url=PAGE, scrapedAt=now_utc()),
            title="Letná škola tanca pre mládež",
            genres=_genres(block),
            ageRange=_age_range(block),
            organization=ORG,
            location=VENUE,
            schedule=Schedule(
                season=season, start=start, end=end, timezone="Europe/Bratislava", notes=notes
            ),
            prices=_prices(block),
            application=Application(url=FORM),
        )
    ]
