"""Nordsee Akademie — Sommertanztage (DE), Leck.

API FIRST
The site (https://www.nordsee-akademie.de) is **TYPO3** (no `/wp-json/` — 404)
with no schema.org `Event`/`Course` `ld+json`; it is fully server-rendered, so a
plain fetch returns the program text — no proxy tier needed. We read it
structurally: the event header carries a `span.teaser__date` ("05.07.2026 – bis
11.07.2026"), and the body labels are plain prose.

DISCOVERY — the academy's `/programm` index lists every event; the Sommertanztage
editions are the anchors whose href is `/programm/sommertanztage-…`. Each is a
separate dated week → one Offering per edition (two in 2026: I = 5–11 Jul, II =
12–18 Jul), discovered from the index so new years/editions are picked up
automatically (the academy's separate "Momentum — Young Dancers Intensive" is a
different slug, left to its own seed).

GENRES are matched against the curriculum sentence ("Neben klassischem Ballett
(… auch mit Spitzentanz) stehen Contemporary und Musical Jazz … Charaktertanz …
Erarbeitung eines Repertoirestücks aus den berühmten Ballettwerken"): classical,
pointe, contemporary, character, repertoire. Musical Jazz is dropped (out of scope
for a ballet register).

PRICE: one residential seminar price (€740/person) bundling tuition, accommodation
(1–4-bed rooms) and meals → Price(includes tuition/accommodation/meals). The €50
sibling discount is a conditional rebate, not a separate charge — kept only in the
price notes.

REQUIREMENTS: open enrolment ("Anmeldung … geöffnet"); classes are assigned by the
academy's teachers, with no audition material → status open, requirements empty.
Ages 11–19 (the source explicitly admits 18–19-year-olds).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-26)
- TYPO3 SSR HTML; index-driven multi-edition discovery (one Offering per week).
- German numeric date range (DD.MM.YYYY – DD.MM.YYYY) off a structured date span.
- German genre keyword table (incl. character/pointe), dropping a non-ballet genre.
- A bundled residential Price (tuition + accommodation + meals); status=open.
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

BASE = "https://www.nordsee-akademie.de"
INDEX = f"{BASE}/programm"

ORG = Organization(
    name="Nordsee Akademie", slug="nordsee-akademie-sommertanztage", country="DE", city="Leck"
)
LOCATION = Location(venue="Nordsee Akademie", city="Leck", country="DE")
TIMEZONE = "Europe/Berlin"

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("klassische", "ballett")),
    ("pointe", ("spitzentanz",)),
    ("contemporary", ("contemporary",)),
    ("character", ("charaktertanz",)),
    ("repertoire", ("repertoire",)),
]


def scrape(client: httpx.Client) -> list[Offering]:
    index = client.get(INDEX)
    index.raise_for_status()
    offerings: list[Offering] = []
    for url in _edition_urls(index.text):
        page = client.get(url)
        page.raise_for_status()
        offerings.append(_build_offering(page.text, url))
    if not offerings:
        # Index rendered without the Sommertanztage links — degraded fetch; raise
        # so run.py keeps the prior store rather than overwriting it with [].
        raise ValueError("Nordsee Akademie: no Sommertanztage editions found on /programm")
    return offerings


def _edition_urls(index_html: str) -> list[str]:
    """Sommertanztage detail URLs linked from the /programm index, de-duplicated
    in first-seen order (the index repeats links in sliders)."""
    tree = HTMLParser(index_html)
    seen: list[str] = []
    for a in tree.css("a"):
        href = a.attributes.get("href", "") or ""
        if re.search(r"/programm/sommertanztage-[\w-]+", href):
            url = href if href.startswith("http") else BASE + href
            url = url.split("?")[0].split("#")[0]
            if url not in seen:
                seen.append(url)
    return seen


_TITLE = re.compile(r"Sommertanztage\s+(I{1,3})\s+(\d{4})")
_DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})\D+?(\d{2})\.(\d{2})\.(\d{4})")
_AGES = re.compile(r"zwischen\s*(\d{1,2})\s*und\s*(\d{1,2})\s*Jahren", re.IGNORECASE)
_PRICE = re.compile(r"Preis pro Person:\s*([\d.,]+)\s*€", re.IGNORECASE)


def _build_offering(html: str, url: str) -> Offering:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    tm = _TITLE.search(text)
    title = f"Sommertanztage {tm.group(1)} {tm.group(2)}" if tm else "Sommertanztage"

    start, end, notes = _date_range(tree)
    season = str(start.year if start else (int(tm.group(2)) if tm else 0))
    slug = url.rstrip("/").rsplit("/", 1)[-1]

    return Offering(
        id=f"nordsee-akademie-sommertanztage/{slug}",
        source=Source(provider="nordsee-akademie-sommertanztage", url=url, scrapedAt=now_utc()),
        title=title,
        genres=parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"]),
        ageRange=_age_range(text),
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(season=season, start=start, end=end, timezone=TIMEZONE, notes=notes),
        teachers=_teachers(text),
        prices=_prices(text),
        application=Application(status="open" if "geöffnet" in text.lower() else None, url=url),
    )


def _date_range(tree: HTMLParser) -> tuple[date | None, date | None, str | None]:
    node = tree.css_first("span.teaser__date")
    # The "–" is aria-hidden and the "bis" visually-hidden, so the extracted text
    # glues them ("–bis"); re-space for a readable raw note.
    raw = parse.clean(node.text()).replace("–bis", "– bis") if node else ""
    m = _DATE.search(raw)
    if not m:
        return None, None, raw or None
    d1, mo1, y1, d2, mo2, y2 = (int(g) for g in m.groups())
    return date(y1, mo1, d1), date(y2, mo2, d2), raw


def _age_range(text: str) -> dict | None:
    m = _AGES.search(text)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _teachers(text: str) -> list[Teacher]:
    if "Maike Jürgensen" not in text:
        return []
    return [
        Teacher(
            name="Maike Jürgensen",
            role="Künstlerische Leitung",
            affiliations=[
                Affiliation(
                    organization="Tanzakademie Hannover-Neustadt", role="Inhaberin", current=True
                )
            ],
        )
    ]


def _prices(text: str) -> list[Price]:
    m = _PRICE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    notes = "Geschwisterrabatt: 50 € pro Familie." if "Geschwisterrabatt" in text else None
    return [
        Price(
            amount=amount,
            currency="EUR",
            label="Seminarpreis (pro Person)",
            includes=["tuition", "accommodation", "meals"],
            notes=notes,
        )
    ]
