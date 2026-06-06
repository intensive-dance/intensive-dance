"""Stage International de Danse Charles Jude (Marseille, FR) — its summer stage.

API FIRST: WordPress. The site (stagedansecj.com) serves a 200 from `/wp-json/`,
so the body comes straight from the REST API — no live-HTML scraping. There is no
course custom post type: the current summer edition lives in the home *page*
(`/wp-json/wp/v2/pages?slug=accueil`, id 311), built with WPBakery, and the
JSON-LD carries only `Organization`/`WebSite` (no `Event`/`Course`). So the
offering data is that page's `content.rendered`, read language-agnostically
(numeric dates, French month name, enum genres, numeric ages/prices) — the rich
French prose is kept verbatim, never inline-translated.

DISCOVERY: one dated edition — the "11ème édition" summer stage, "6-18 Juillet
2026" at the École Nationale de Danse de Marseille. It is bookable as one or two
weeks (the `tarifs` block has a "1 semaine" and a "2 semaine" tab, each a
per-day-count fee ladder), with an on-site balance due Sunday 5 July (week 1) or
Sunday 12 July (week 2). We emit ONE `Offering` for the stage, season-keyed from
the parsed year, with the two weeks as `schedule.sessions` (labelled, their
balance-date kept as a note — the source never states a precise per-week calendar
split, so per-week start/end stay null). The separate Bordeaux winter edition
(`autres-stages`, "20-22 décembre 2025") is a different, past edition on its own
page and out of this scraper's scope.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-06):
  - DATES: a single French day-range with one trailing month+year ("6-18 Juillet
    2026"), parsed by a local regex against `parse.months_alt` (French names).
  - AGES: open-access from 8 — the three levels are "Élementaire (à partir de 8
    ans)", "Intermédiaire (à partir de 11 ans)", "Avancé-Pro (à partir de 14
    ans)". The lower bound (8) is taken; the upper is open (adults attend), so
    the max bound stays null.
  - LEVEL: `open` — the page states the stage is "accessible aux enfants et
    adultes amateurs ou professionnels" with no audition / selection.
  - PRICES in EUR: the per-day-count ladder for each duration (1-week 210/350/
    490/700, 2-week 400/680/950/1350, plus a 40€ drop-in and a 15€ membership),
    each `includes=["tuition"]`.
  - GENRES: classical + contemporary + pointe, keyword-matched against the
    dress-code/curriculum wording (classique / contemporain / pointes).
  - REQUIREMENTS: `[NoneReq]` — open-access, the page describes no audition; only
    a non-refundable 50% deposit to pre-register, kept as an application note.
  - TEACHERS: the faculty are étoiles/anciens of the Opéra national de Paris
    (Charles Jude, Élisabeth Maurin, Delphine Moussin, …) but the page lists them
    as long artist bios without a per-2026 teaching roster, so — as Joffrey/BIB do
    for unattributable rosters — none are emitted rather than over-claimed.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    Genre,
    Level,
    Location,
    NoneReq,
    Offering,
    Organization,
    Price,
    Schedule,
    Session,
    Source,
    now_utc,
)

BASE = "https://stagedansecj.com"
SLUG = "accueil"
PAGE_URL = f"{BASE}/"
APPLY_URL = f"{BASE}/inscription"

ORG = Organization(
    name="Stage International de Danse Charles Jude",
    slug="stage-charles-jude",
    country="FR",
    city="Marseille",
)
LOCATION = Location(
    venue="École Nationale de Danse de Marseille",
    city="Marseille",
    country="FR",
)

# The non-refundable deposit the page states for pre-registration. Kept verbatim
# (French) as an application note — the source is preserved, not translated.
_APPLY_NOTE = (
    "Pour valider la pré-inscription, 50% du montant total est à régler "
    "(non remboursable) ; le solde est dû sur place le dimanche 5 juillet "
    "(1ère semaine) ou le dimanche 12 juillet (2ème semaine)."
)

# French month names — local to this scraper (the page is French); only the
# regex-building (`parse.months_alt`) is shared.
_MONTHS_FR = {
    "janvier": 1,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
}
_MONTHALT_FR = parse.months_alt(_MONTHS_FR)


def scrape(client: httpx.Client) -> list[Offering]:
    page = wp.fetch_page(client, SLUG, base=BASE)
    if page is None:
        return []
    offering = _build_offering(page["content"]["rendered"])
    return [offering] if offering is not None else []


def _build_offering(rendered: str) -> Offering | None:
    text = wp.plain_text(rendered)

    start, end = _date_range(text)
    anchor = start or end
    if anchor is None:
        return None  # no dated edition parseable
    season = str(anchor.year)

    return Offering(
        id=f"stage-charles-jude/summer-stage-{season}",
        source=Source(provider="stage-charles-jude", url=PAGE_URL, scrapedAt=now_utc()),
        title=f"Stage International de Danse Charles Jude {season}",
        genres=_genres(text),
        level=_level(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Paris",
            sessions=_sessions(text),
            notes=_dates_note(text),
        ),
        prices=_prices(text),
        application=Application(
            url=APPLY_URL,
            requirements=[NoneReq()],
            notes=_APPLY_NOTE,
        ),
    )


# --- dates: "6-18 Juillet 2026" (one day-range, trailing month + year) --------

_RANGE = re.compile(
    r"(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+(" + _MONTHALT_FR + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    match = _RANGE.search(text)
    if not match:
        return None, None
    d1, d2, month, year = match.groups()
    m = _MONTHS_FR[month.lower()]
    y = int(year)
    return date(y, m, int(d1)), date(y, m, int(d2))


def _dates_note(text: str) -> str | None:
    match = _RANGE.search(text)
    return parse.clean(match.group(0)) if match else None


# The stage is bookable per week; the page distinguishes a "1ère semaine" and a
# "2ème semaine" with their own on-site balance dates (5 / 12 July). The source
# never gives a precise per-week calendar split, so each Session keeps its label
# and balance-date note but leaves start/end null (faithful, not fabricated).
_WEEK_BALANCE = {
    1: "Solde dû sur place le dimanche 5 juillet (17h–19h).",
    2: "Solde dû sur place le dimanche 12 juillet (17h–19h).",
}


def _sessions(text: str) -> list[Session]:
    low = text.lower()
    if "1ere semaine" not in low and "1ère semaine" not in low and "2eme semaine" not in low:
        return []
    return [
        Session(label=f"Semaine {n}", notes=_WEEK_BALANCE[n])
        for n in (1, 2)
        if any(k in low for k in (f"{n}ere semaine", f"{n}ère semaine", f"{n}eme semaine"))
    ]


# --- ages: "à partir de 8 ans" (lowest stated level threshold; adults attend) -

_AGE_FROM = re.compile(r"à\s+partir\s+de\s+(\d{1,2})\s+ans", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    lows = [int(n) for n in _AGE_FROM.findall(text) if 3 <= int(n) <= 25]
    if not lows:
        return None
    return {"min": min(lows)}  # open upper bound — adults attend ("enfants et adultes")


# --- level: open-access ("accessible aux enfants et adultes … amateurs …") ----


def _level(text: str) -> list[Level]:
    low = text.lower()
    return ["open"] if "accessible aux enfants et adultes" in low else []


# --- prices: the per-day-count ladder, by duration ----------------------------
#
# Two tabs ("1 semaine" / "2 semaine") each list "<n> cours/jour <amount>€",
# "cours illimités <amount>€" and "cours à l'unité 40€ (+ 15€ adhésion)". We read
# every "<label> <amount>€" pair and label each Price with its duration.

_LADDER = re.compile(
    r"(\d\s+cours/jour|cours\s+illimités|cours\s+à\s+l['’]unité)\s*([\d.,]+)\s*€",
    re.IGNORECASE,
)
_MEMBERSHIP = re.compile(r"\(\s*\+\s*([\d.,]+)\s*€\s+en\s+adhésion", re.IGNORECASE)
# The fee block runs "1 semaine … 2 semaine …"; we split on the second tab so each
# ladder amount is attributed to the right duration.
_TWO_WEEK_ANCHOR = re.compile(r"1\s*cours/jour\s+400", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    split = _TWO_WEEK_ANCHOR.search(text)
    prices: list[Price] = []
    if split:
        prices += _ladder_prices(text[: split.start()], "1 semaine")
        prices += _ladder_prices(text[split.start() :], "2 semaines")
    else:
        prices += _ladder_prices(text, "Stage")
    membership = _MEMBERSHIP.search(text)
    if membership:
        amount = parse.parse_amount(membership.group(1))
        if amount is not None and not any(p.label == "Adhésion" for p in prices):
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="Adhésion",
                    notes="Adhésion à ajouter à chaque tarif.",
                )
            )
    return prices


def _ladder_prices(segment: str, duration: str) -> list[Price]:
    prices: list[Price] = []
    seen: set[tuple[str, float]] = set()
    for match in _LADDER.finditer(segment):
        label = parse.clean(match.group(1))
        amount = parse.parse_amount(match.group(2))
        if amount is None or (label, amount) in seen:
            continue
        seen.add((label, amount))
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=f"{duration} — {label}",
                includes=["tuition"],
            )
        )
    return prices


# --- genres -------------------------------------------------------------------
#
# Matched against the dress-code / curriculum wording, which names the disciplines
# actually taught (collant rose pour le classique, … pour le contemporain; pointes).

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classique", "danse classique")),
    ("contemporary", ("contemporain", "contemporaine")),
    ("pointe", ("pointe", "pointes")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])
