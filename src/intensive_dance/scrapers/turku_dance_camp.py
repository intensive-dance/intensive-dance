"""Turku Dance Camp — Ruusuilla tanssijat ry (Turku, FI).

API FIRST: ruusuillatanssijat.fi is WordPress (block/Gutenberg theme). The camp
page is server-rendered and its participation groups sit in native
`<details><summary>` accordions, so a plain `selectolax` scrape reading each
accordion is enough — no REST needed (the fields we want are all in the rendered
body).

DISCOVERY: one dated camp per year (26–31 Jul 2026) offered in several
participation groups (Standard, Intensive, Lite, Children's course) plus an
optional Choreography add-on. It's a single course, so it's **one Offering** with
one `Session` per group and a labelled `Price` per group/tier — not one Offering
per group (they share the week, venue and gala).

WHAT WE EXTRACT (verified live 2026-07-01):
  - DATES: "from Sunday 26 to Friday 31 July 2026" (the whole-camp span). The
    Lite group runs the 26–30 subset, kept in that Session's notes.
  - SESSIONS / AGES: Standard (aged 13+), Intensive (aged 15+, pre-/professional
    level), Lite (all adults + young dancers born ≤2013 → aged ~13+), Children's
    course (aged 10–12). The Offering's age band spans them (min 10, open top);
    levels are open + pre-professional.
  - GENRES: "ballet, repertoire, contemporary and body conditioning" → classical
    + contemporary + repertoire.
  - PRICES: Standard €400, Intensive €400, Lite €240 (all) / €180 (ballet only) /
    €150 (contemporary only), Children €220, and a Choreography workshop top-up
    €100 — each a labelled EUR `Price` on the one Offering.
  - LOCATION: Turku, FI (Gala at Sigyn Hall / dinner at Turku Castle).
  - APPLICATION: open enrolment via a Tally registration form — no audition
    stated, so requirements are left unknown.

WHAT THIS SCRAPER EXERCISES: WP block `<details>` accordion parsing; one Offering
with several age/gender-neutral Sessions; many labelled EUR Prices (incl. a
sub-course-scoped Lite tier and an add-on); European "400,00€" amount notation;
open-topped multi-group age band; raise-on-degraded fetch.
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
    Session,
    Source,
    now_utc,
)

BASE = "https://ruusuillatanssijat.fi"
PAGE = f"{BASE}/turkudancecamp/"

ORG = Organization(
    name="Turku Dance Camp",
    slug="turku-dance-camp",
    country="FI",
    city="Turku",
)

# "from Sunday 26 to Friday 31 July 2026" — day-day, month + year once at the end.
_RANGE = re.compile(
    r"from\s+\w+\s+(\d{1,2})\s+to\s+\w+\s+(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
_EUR = re.compile(r"(\d{2,4},\d{2})\s*€")
_AGE = re.compile(r"aged (\d{1,2})(?:\s*[–-]\s*(\d{1,2}))?", re.IGNORECASE)

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet",)),
    ("contemporary", ("contemporary",)),
    ("repertoire", ("repertoire",)),
]


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE)
    resp.raise_for_status()
    return [_build_offering(resp.text)]


def _build_offering(html: str) -> Offering:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ") if tree.body else "")

    m = _RANGE.search(text)
    if not m:
        raise ValueError("Turku Dance Camp: no camp date range found (degraded fetch?)")
    year = int(m.group(4))
    month = parse.MONTHS[m.group(3).lower()]
    start = date(year, month, int(m.group(1)))
    end = date(year, month, int(m.group(2)))
    season = str(year)

    groups = _groups(tree)
    sessions, prices = _sessions_and_prices(groups, year, month)

    return Offering(
        id=f"{ORG.slug}/{season}",
        source=Source(provider=ORG.slug, url=PAGE, scrapedAt=now_utc()),
        title=f"Turku Dance Camp {season}",
        genres=parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"]),
        level=["open", "pre-professional"],
        ageRange=_offering_age(sessions),
        organization=ORG,
        location=Location(city="Turku", country="FI"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Helsinki",
            sessions=sessions,
            notes="Six-day camp; finale Gala at Sigyn Hall and dinner at Turku Castle.",
        ),
        prices=prices,
        application=Application(url=PAGE),
    )


def _groups(tree: HTMLParser) -> dict[str, str]:
    """Accordion label → its collapsed text."""
    out: dict[str, str] = {}
    for det in tree.css("details"):
        summary = det.css_first("summary")
        if not summary:
            continue
        label = parse.clean(summary.text())
        out[label] = parse.clean(det.text(separator=" "))
    return out


def _sessions_and_prices(
    groups: dict[str, str], year: int, month: int
) -> tuple[list[Session], list[Price]]:
    sessions: list[Session] = []
    prices: list[Price] = []
    for label, body in groups.items():
        low = label.lower()
        if "choreography" in low:
            # A top-up add-on, not its own group — record only its price.
            eur = _EUR.search(body)
            if eur:
                prices.append(
                    Price(
                        amount=parse.parse_amount(eur.group(1)) or 0.0,
                        currency="EUR",
                        label="Choreography workshop (add-on)",
                        includes=["tuition"],
                    )
                )
            continue

        sessions.append(Session(label=label, ageRange=_group_age(body)))
        for eur in _EUR.finditer(body):
            amount = parse.parse_amount(eur.group(1))
            if amount is None:
                continue
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label=f"{label} — {_price_qualifier(body, eur.end())}".strip(" —"),
                    includes=["tuition"],
                )
            )
    return sessions, prices


def _price_qualifier(body: str, at: int) -> str:
    """The 'all classes' / 'only ballet' / 'only contemporary' qualifier that
    follows a Lite sub-price, scoped to the run before the next amount."""
    tail = body[at:].lower()
    tail = _EUR.split(tail, maxsplit=1)[0]  # stop at the next "N,NN€"
    if "only ballet" in tail:
        return "ballet only"
    if "only contemporary" in tail:
        return "contemporary only"
    if "all classes" in tail:
        return "all classes"
    return ""


def _group_age(body: str) -> dict | None:
    m = _AGE.search(body)
    if not m:
        return None
    lo = int(m.group(1))
    return {"min": lo, "max": int(m.group(2))} if m.group(2) else {"min": lo}


def _offering_age(sessions: list[Session]) -> dict | None:
    mins = [s.age_range["min"] for s in sessions if s.age_range and "min" in s.age_range]
    if not mins:
        return None
    # Adults are welcomed in Standard/Lite → the band is open-topped.
    return {"min": min(mins)}
