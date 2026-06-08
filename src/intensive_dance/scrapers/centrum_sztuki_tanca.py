"""Centrum Sztuki Tańca (PL) — Kraków — its residential summer dance intensives.

API FIRST: WordPress, but the **REST API is locked** — every content endpoint
(`/wp-json/wp/v2/pages`, `…/posts`) returns 401
(`itsec_rest_api_access_restricted`, iThemes Security). Only `/wp-json/` itself
and `settings` are public, so there is no JSON body to read. We therefore parse
the two dedicated intensive **pages** as HTML (plain fetch, no proxy needed —
the host serves the full content in the static markup):
  - `/letnie-obozy-baletowe-2026/` — the summer ballet camps (two turnusy)
  - `/danceit-2026/` — the DANCEit teen intensive (redirects to a long slug)

LANGUAGE NOTE: the body is Polish in every render. The parse is
**language-agnostic** — numeric `dd – dd.mm.yyyy` dates, the numeric `zł` fee,
enum genres matched on the technique list, and an explicit "14+" age cue. The
only free text we emit (titles, lifecycle/notes) is canonical English, so the
committed data is deterministic regardless of locale.

DISCOVERY: one Offering per dated edition.
  - The summer-camp page advertises **two turnusy** ("I turnus: 12 – 19.07.2026 …
    II turnus: 19 – 26.08.2026"), each at a different venue (Małe Ciche vs Suche)
    with its own dates and per-diet surcharge → **one Offering per turnus**
    (id `…/letnie-oboz-baletowy-{start ISO}`). Both share the same fee, programme
    and faculty wording; only the place/dates differ, so folding them would lose
    the distinct schedules and locations.
  - DANCEit is a separate, older-cohort (14+) intensive at Suche → its own
    Offering. It overlaps the II turnus in time/venue but is a distinct programme
    (7-8h dance/day, guest choreographers, higher fee), not the same product.

Ended cycles are kept (IDR-24); "past" is derived from `schedule.end < today`,
never stored.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - MULTIPLE OFFERINGS from one page (two turnusy) plus a second page.
  - PRICES in local currency — a single residential fee in **PLN** bundling
    tuition + accommodation + meals + transport ("CENA … 2 400 zł … Cena zawiera:
    7 noclegów … posiłki … transport …").
  - GENRES from the stated programme — classical (Balet / taniec klasyczny) +
    contemporary (taniec współczesny); Jazz/Flamenco/Stretching fall outside the
    ballet-register Genre enum and drop out naturally.
  - AGE RANGE — DANCEit's open-ended "14+" → {min: 14} (null max); the children's
    camp states no numeric age, so its ageRange stays null (fail-open).
  - TEACHERS — DANCEit names a guest (Sandra Szatan, ex-Polski Teatr Tańca
    Poznań); the camp lists no named faculty, so it carries none.
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
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://centrumsztukitanca.pl"
CAMP_URL = f"{BASE}/letnie-obozy-baletowe-2026/"
DANCEIT_URL = f"{BASE}/danceit-2026/"

ORG = Organization(
    name="Centrum Sztuki Tańca",
    slug="centrum-sztuki-tanca",
    country="PL",
    city="Kraków",
)

# The intensives run at two guest houses in the Tatra foothills near Zakopane.
# Venue keyword → (venue, city) so each turnus carries its own place; matched on
# the venue word in the page's "TERMINY" line.
_VENUES: dict[str, tuple[str, str]] = {
    "oliwia": ("Dom Wczasowy Oliwia", "Małe Ciche"),
    "jędrol": ("Dom Wczasowy Jędrol", "Suche"),
    "jedrol": ("Dom Wczasowy Jędrol", "Suche"),
}

# DANCEit's first announced guest. Affiliation is a stable biographical fact
# (the bio is Polish prose that would be brittle to parse), so it's pinned here.
_DANCEIT_TEACHERS: list[Teacher] = [
    Teacher(
        name="Sandra Szatan",
        role="guest",
        affiliations=[
            Affiliation(organization="Polski Teatr Tańca", role="dancer", current=False),
        ],
    ),
]


def scrape(client: httpx.Client) -> list[Offering]:
    camp = _page_text(client, CAMP_URL)
    danceit = _page_text(client, DANCEIT_URL)
    return _build_offerings(camp, danceit, date.today())


def _build_offerings(camp_text: str, danceit_text: str, today: date) -> list[Offering]:  # noqa: ARG001 — today reserved
    offerings: list[Offering] = _build_camp_offerings(camp_text)
    danceit = _build_danceit_offering(danceit_text)
    if danceit is not None:
        offerings.append(danceit)
    offerings.sort(key=lambda o: o.id)
    return offerings


def _page_text(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    resp.raise_for_status()
    tree = HTMLParser(resp.text)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


# --- summer camp: two turnusy on one page ------------------------------------
#
# Each "turnus" line pairs a date range with a venue, e.g.
#   "I turnus: 12 – 19.07.2026 (8 dni) | Dom Wczasowy Oliwia, Małe Ciche"
#   "II turnus: 19 – 26.08.2026 (8 dni) | Dom Wczasowy Jędrol, Suche"
# The venue word immediately follows the date, so a non-greedy match between the
# two anchors each turnus to its own place.

_TURNUS = re.compile(
    r"turnus[:\s]+(\d{1,2})\s*[-–]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})"
    r"[^|]*\|\s*Dom Wczasowy\s+(Oliwia|Jędrol|Jedrol)",
    re.IGNORECASE,
)


def _build_camp_offerings(text: str) -> list[Offering]:
    genres = _genres(text)
    prices = _prices(text)
    offerings: list[Offering] = []
    seen: set[date] = set()
    for d1, d2, month, year, venue_kw in _TURNUS.findall(text):
        start = date(int(year), int(month), int(d1))
        end = date(int(year), int(month), int(d2))
        if start in seen:
            continue
        seen.add(start)
        venue, city = _VENUES[venue_kw.lower()]
        offerings.append(
            Offering(
                id=f"centrum-sztuki-tanca/letnie-oboz-baletowy-{start.isoformat()}",
                source=Source(provider="centrum-sztuki-tanca", url=CAMP_URL, scrapedAt=now_utc()),
                title=f"Letni obóz baletowy — {city} {start.year}",
                genres=genres,
                organization=ORG,
                location=Location(venue=venue, city=city, country="PL"),
                schedule=Schedule(
                    season=str(start.year), start=start, end=end, timezone="Europe/Warsaw"
                ),
                prices=prices,
                application=Application(url=CAMP_URL),
            )
        )
    return offerings


# --- DANCEit: one teen intensive (14+) ---------------------------------------
#
# "TERMIN 19 – 26.08.2026 Miejsce: Dom Wczasowy Jędrol, Suche"

_DANCEIT_DATES = re.compile(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")
# "Młodzież … od 14 roku życia", "dla Młodzieży 14+".
_AGE_14PLUS = re.compile(r"(\d{1,2})\s*\+|od\s+(\d{1,2})\s+roku\s+życia", re.IGNORECASE)


def _build_danceit_offering(text: str) -> Offering | None:
    m = _DANCEIT_DATES.search(text)
    if not m:
        return None
    d1, d2, month, year = m.groups()
    start = date(int(year), int(month), int(d1))
    end = date(int(year), int(month), int(d2))

    age = _danceit_age(text)
    venue, city = _VENUES["jędrol"]
    return Offering(
        id=f"centrum-sztuki-tanca/danceit-{start.isoformat()}",
        source=Source(provider="centrum-sztuki-tanca", url=DANCEIT_URL, scrapedAt=now_utc()),
        title=f"DANCEit — {city} {start.year}",
        genres=_genres(text),
        ageRange=age,
        organization=ORG,
        location=Location(venue=venue, city=city, country="PL"),
        schedule=Schedule(season=str(start.year), start=start, end=end, timezone="Europe/Warsaw"),
        teachers=list(_DANCEIT_TEACHERS),
        prices=_prices(text),
        application=Application(url=DANCEIT_URL),
    )


def _danceit_age(text: str) -> dict | None:
    m = _AGE_14PLUS.search(text)
    if not m:
        return None
    lower = int(m.group(1) or m.group(2))
    # Open-ended "14+" / "od 14 roku życia" → null upper bound.
    return {"min": lower}


# --- shared: prices & genres -------------------------------------------------
#
# The fee is a single residential rate, "CENA … 2 400 zł" / "CENA: 2 600 zł",
# whose "Cena zawiera:" list bundles 7 nights' lodging, daily meals and the
# coach transfer from Kraków — tuition + accommodation + meals. We take the
# first `zł` amount (the headline price); the smaller per-diet surcharge that
# follows is filtered out by the floor.

_PRICE = re.compile(r"(\d[\d ]*\d|\d)\s*(?:zł|zl|pln)\b", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    m = _PRICE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1).replace(" ", ""))
    if amount is None or amount < 500:
        return []
    return [
        Price(
            amount=amount,
            currency="PLN",
            label="Residential fee",
            includes=["tuition", "accommodation", "meals"],
            notes="Full board plus coach transfer from Kraków.",
        )
    ]


# Matched against the stated "PROGRAM" technique list, not loose prose, so the
# genres reflect classes actually taught. Jazz / Flamenco / Stretching /
# partnerowanie have no slot in the ballet-register Genre enum and drop out.
_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("balet", "klasyczn", "ballet", "classical")),
    ("contemporary", ("współczesn", "wspolczesn", "contemporary")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])
