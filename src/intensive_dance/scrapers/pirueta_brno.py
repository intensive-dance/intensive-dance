"""Baletní škola Pirueta (Brno) — the residential "Letní baletní soustředění".

API FIRST
WordPress 5.5.8, but the soustředění lives in a custom post type (`portfolio`)
that is NOT exposed over REST (`/wp-json/wp/v2/portfolio?slug=…` → 404
`rest_no_route`; `pages?slug=soustredeni` → `[]`). So this is a structural
`selectolax` text scrape of the single detail page (`/portfolio/soustredeni/`).
The host 403s the default httpx UA but serves our project UA fine — no proxy.
Czech.

DISCOVERY — one dated edition = one Offering.
Pirueta is a Brno ballet school; its one in-scope short-term student intensive is
the annual residential "Letní baletní soustředění" (26th edition in 2026): a
seven-day live-in ballet camp at ParkHOTEL MOZOLOV (Nadějkov) for children 6–17
who already have ballet training (`s baletní průpravou`, also open to pupils of
other schools). That is ONE Offering. The school's term-time classes and the
registration form page are not dated editions and are not emitted.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-12)
- Czech numeric day span with the year only on the end date ("27.7. – 2.8.2026"),
  bounded age band ("6 – 17 let"), Czech price notation ("9.580,-" → 9580 CZK
  with `Kč` omitted on the page).
- A residential Price bundling tuition + accommodation + full board + materials.
- Single classical genre keyed off "výuka baletu" (the rest of the programme —
  choreography making, sports, disco, pool — is not a taught dance genre).
- A stated registration deadline ("nejpozději do 31.3.2026") with no audition →
  `application.deadline` set, `requirements` empty, `status` unstated.
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

SLUG = "pirueta-brno"
PAGE = "https://pirueta.cz/portfolio/soustredeni/"
FORM = "https://pirueta.cz/prihlasky/vyuka-pro-deti/objednavka-soustredeni/"

ORG = Organization(name="Baletní škola Pirueta", slug=SLUG, country="CZ", city="Brno")
VENUE = Location(venue="ParkHOTEL MOZOLOV", city="Nadějkov", country="CZ")

# "Termín konání: 27.7. – 2.8.2026" — year only on the end date.
_DATES = re.compile(r"(\d{1,2})\.(\d{1,2})\.\s*[–-]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")
# "ve věku 6 – 17 let" → min/max.
_AGE = re.compile(r"ve věku\s*(\d{1,2})\s*[–-]\s*(\d{1,2})\s*let", re.IGNORECASE)
# "Cena:  9.580,-" → the value before the ",-".
_PRICE = re.compile(r"Cena:\s*([\d.]+),-")
# "nejpozději do 31.3.2026" → registration deadline.
_DEADLINE = re.compile(r"nejpozději do\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", re.IGNORECASE)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return _build_offerings(resp.text)


def _text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _dates(text: str) -> tuple[date | None, date | None, str | None]:
    m = _DATES.search(text)
    if not m:
        return None, None, None
    d1, m1, d2, m2, year = (int(g) for g in m.groups())
    return date(year, m1, d1), date(year, m2, d2), parse.clean(m.group(0))


def _age_range(text: str) -> dict | None:
    m = _AGE.search(text)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _genres(text: str) -> list[Genre]:
    return ["classical"] if "balet" in text.lower() else []


def _prices(text: str) -> list[Price]:
    m = _PRICE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    return [
        Price(
            amount=amount,
            currency="CZK",
            includes=["tuition", "accommodation", "meals", "materials"],
        )
    ]


def _deadline(text: str) -> date | None:
    m = _DEADLINE.search(text)
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def _build_offerings(html: str) -> list[Offering]:
    text = _text(html)
    start, end, notes = _dates(text)
    season = str(start.year) if start else "2026"
    return [
        Offering(
            id=f"{SLUG}/letni-baletni-soustredeni-{season}",
            source=Source(provider=SLUG, url=PAGE, scrapedAt=now_utc()),
            title="Letní baletní soustředění",
            genres=_genres(text),
            ageRange=_age_range(text),
            organization=ORG,
            location=VENUE,
            schedule=Schedule(
                season=season, start=start, end=end, timezone="Europe/Prague", notes=notes
            ),
            prices=_prices(text),
            application=Application(deadline=_deadline(text), url=FORM),
        )
    ]
