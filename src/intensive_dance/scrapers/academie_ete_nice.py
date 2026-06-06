"""Académie Internationale d'Été de Nice (FR) — its summer dance stage.

API FIRST: WP REST exists (`/wp-json/`) but is useless here — the dance page is
built by a page builder that renders **nothing** into `content.rendered` (the ABT
trap), so the only source of truth is the server-rendered HTML. The dance stage
lives on its own subdomain (`danse.academie-internationale-ete-nice.org`), a
single-page WordPress site whose full text is in the static HTML — a one-page
scrape, no JS. We route through the fetch proxy because the host blocks the CI
runner's datacenter IP on a direct httpx fetch.

SOURCE LANGUAGE: French. Month names and the level/genre vocabulary are this
scraper's own; only the numeric date/price/age parsing is shared.

DISCOVERY: the Académie runs three summer sessions (music / song-music-dance /
music); **dance is Session 2 only**, a single week. We emit **one** `Offering`
for that dance stage, season-keyed from the parsed year. The umbrella academy is
music-first — we deliberately scrape only the dedicated dance subdomain so we
don't over-claim the music programme.

SCOPE GUARD — ballet is the core: the inscription form's course list is the
curriculum (Barre à terre, Classique, Technique pointes, Technique garçons,
Répertoire / Pas de deux, Atelier chorégraphique contemporain). We keyword-match
*that* list (not the teachers' biographies, which name dozens of choreographers)
so the genres reflect what's actually taught: classical, pointe, repertoire and a
contemporary choreography workshop — no jazz/character/etc.

WHAT THE PAGE GIVES US (verified live 2026-06-06):
  - DATES: the dance banner states "Du 27 juillet au 1 Aout 2026" (the homepage's
    "2 août" is the broader Session-2 span; the dance banner is authoritative for
    the stage). One week, one shared trailing year.
  - LEVELS: three tiers by minimum age — Élémentaire (8+), Moyen-Intermédiaire
    (11+), Avancé-Pro (14+) — and "Ouvert aux enfants, adolescents et adultes".
    So `level` spans beginner→advanced and `age_range` is min 8 with an open top
    (adults welcome).
  - PRICES in EUR: weekly tuition tiers by classes/day (1/2/3/unlimited → 220 /
    391 / 570 / 655 €, each incl. a 20€ membership), plus optional Clairvallon
    accommodation (370 €/week, half-board) and canteen lunch (79 €/week).
  - DIRECTOR/FACULTY: Charles Jude (Opéra de Paris étoile, ex-Bordeaux dance
    director), with Stéphanie Roublot, Monique Loudières (étoile), Thomas Klein
    and Igor Yebra (étoile) named for the 2026 stage.
  - REGISTRATION: the dance page carries a live inscription form (→ HelloAsso
    payment) but no status *sentence*, so `application.status` stays None rather
    than inferred from the form's presence. The audition/admission isn't
    described, so requirements stay `[]`.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.fetch import make_client
from intensive_dance.models import (
    Application,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    Price,
    PriceInclude,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://danse.academie-internationale-ete-nice.org"
PAGE = f"{BASE}/"

ORG = Organization(
    name="Académie Internationale d'Été de Nice",
    slug="academie-ete-nice",
    country="FR",
    city="Nice",
)

# Named for the 2026 dance stage (director + the teacher/étoile roster). Pianists
# and music faculty are out of scope.
_TEACHERS: list[Teacher] = [
    Teacher(name="Charles Jude", role="Artistic director"),
    Teacher(name="Stéphanie Roublot"),
    Teacher(name="Monique Loudières"),
    Teacher(name="Thomas Klein"),
    Teacher(name="Igor Yebra"),
]


def scrape(client: httpx.Client) -> list[Offering]:  # noqa: ARG001 — own proxy client
    # The host blocks the runner's datacenter IP on a direct fetch; route through
    # the proxy (make_client wires it from FETCH_PROXY_URL/TOKEN when present).
    own = make_client()
    try:
        resp = own.get(PAGE)
        resp.raise_for_status()
        html = resp.text
    finally:
        own.close()
    offering = _build_offering(html)
    return [offering] if offering is not None else []


def _build_offering(html: str) -> Offering | None:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    start, end = _date_range(text)
    anchor = end or start
    if anchor is None:
        return None  # no dated dance stage announced
    season = str(anchor.year)

    return Offering(
        id=f"academie-ete-nice/summer-dance-stage-{season}",
        source=Source(provider="academie-ete-nice", url=PAGE, scrapedAt=now_utc()),
        title=f"Stage International de Danse {season}",
        genres=_genres(text),
        level=_levels(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(city="Nice", country="FR"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Paris",
        ),
        teachers=_TEACHERS,
        prices=_prices(text),
        application=Application(url=PAGE),
    )


# --- French dates: "Du 27 juillet au 1 Aout 2026" -----------------------------
#
# The page is French, so the month names are this scraper's own; the year is
# shared across both day-month pairs (trailing once).

_MONTHS = {
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
}
_MONTHALT = parse.months_alt(_MONTHS)

_RANGE = re.compile(
    r"[Dd]u\s+(\d{1,2})(?:er)?\s*(" + _MONTHALT + r")"
    r"\s+au\s+(\d{1,2})(?:er)?\s*(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    d1, m1, d2, m2, year = m.groups()
    y = int(year)
    start = date(y, _MONTHS[m1.lower()], int(d1))
    end = date(y, _MONTHS[m2.lower()], int(d2))
    return start, end


# --- ages: three level tiers by minimum age; adults welcome (open top) --------

_AGE_LOW = re.compile(r"\(\s*à\s+partir\s+de\s+(\d{1,2})\s*ans\s*\)", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    lows = [int(n) for n in _AGE_LOW.findall(text)]
    if not lows:
        return None
    # "Ouvert aux enfants, adolescents et adultes" → no stated upper bound.
    return {"min": min(lows)}


# --- levels: Élémentaire / Moyen-Intermédiaire / Avancé-Pro -------------------

_LEVEL_KEYWORDS: list[tuple[Level, tuple[str, ...]]] = [
    ("beginner", ("élementaire", "élémentaire", "elementaire")),
    ("intermediate", ("intermédiaire", "intermediaire", "moyen")),
    ("advanced", ("avancé", "avance-pro", "avancé-pro")),
]


def _levels(text: str) -> list[Level]:
    low = text.lower()
    return [lvl for lvl, keys in _LEVEL_KEYWORDS if any(k in low for k in keys)]


# --- genres: keyword-match the inscription course list, not the teacher bios --
#
# "Choix des cours: Barre à terre, Classique, Technique pointes, Technique
# garçons, Répertoire / Pas de deux, Atelier chorégraphique contemporain."

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classique", "barre à terre", "technique garçons", "technique garcons")),
    ("pointe", ("technique pointes", "pointes")),
    ("repertoire", ("répertoire / pas de deux", "pas de deux", "répertoire", "repertoire")),
    ("contemporary", ("atelier chorégraphique contemporain", "chorégraphique contemporain")),
]


def _genres(text: str) -> list[Genre]:
    # Anchor on the course list so a teacher's bio (which names contemporary
    # choreographers) can't leak a genre that isn't on the timetable.
    m = re.search(r"Choix des cours(.*?)(?:Sélectionne|Envoyer|$)", text, re.IGNORECASE)
    scope = m.group(1) if m else text
    return parse.match_genres(scope, _GENRE_KEYWORDS, default=["classical"])


# --- prices: weekly tuition tiers + accommodation + meals ---------------------

# "1 cours par jour (soit 6 cours) Frais pédagogique 200€ Adhésion 20€ 220€"
_WEEK_TIER = re.compile(
    r"(\d+\s+cours?\s+par\s+jour|[Cc]ours\s+illimités?)\s*(?:\([^)]*\))?\s*"
    r"Frais\s+pédagogique\s+\d[\d.,]*\s*€\s*Adhésion\s+\d[\d.,]*\s*€\s*(\d[\d.,]*)\s*€",
    re.IGNORECASE,
)
_ACCOMMODATION = re.compile(r"Tarif\s*:\s*(\d[\d.,]*)\s*€\s*la\s+semaine", re.IGNORECASE)
_LUNCH = re.compile(r"Déjeuner\s+à\s+la\s+cantine\s+(\d[\d.,]*)\s*€\s*la\s+semaine", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    for m in _WEEK_TIER.finditer(text):
        amount = parse.parse_amount(m.group(2))
        if amount is None:
            continue
        label = parse.clean(m.group(1))
        includes: list[PriceInclude] = ["tuition"]
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=f"Per week — {label} (incl. 20€ membership)",
                includes=includes,
            )
        )
    lunch = _LUNCH.search(text)
    if lunch:
        amount = parse.parse_amount(lunch.group(1))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="Canteen lunch (per week)",
                    includes=["meals"],
                )
            )
    accom = _ACCOMMODATION.search(text)
    if accom:
        amount = parse.parse_amount(accom.group(1))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="Residence Clairvallon (per week, half-board)",
                    includes=["accommodation", "meals"],
                    notes="Recommended for minors; Sunday-to-Sunday.",
                )
            )
    return prices
