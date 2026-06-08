"""Akademia Sztuki Baletowej (PL) — Summer Dance Project, Hotel Gołuń (Kashubia).

API FIRST: WordPress REST. ASB runs plain WordPress (no custom post type for
programs — only `posts`/`pages`). The Summer Dance Project lives on the evergreen
`/warsztaty/` **page** (`wp/v2/pages?slug=warsztaty`), which carries the cleanest,
single copy of the announcement: both dated sessions, the techniques, the 3200 zł
fee and the named guest. (Two duplicate dated *posts* also carry it; we don't use
them — they'd double the same two sessions.) `content.rendered` is flat prose, not
WPBakery sections, so we strip tags and parse the text directly. No HTML/proxy.

LANGUAGE NOTE: the body is Polish in every render (the `/en/` URLs serve the same
Polish text), so the parse is **language-agnostic** — numeric/Polish-month dates,
the numeric `zł` fee, enum genres matched on technique keywords, and a hard-coded
guest name. The only free text we emit is canonical English (titles, notes), so
the committed data is deterministic.

DISCOVERY: one announcement runs the same residential workshop in **two summer
sessions** ("w dwóch terminach: od 27 czerwca do 05 lipca 2026 … od 22 do 31
sierpnia 2026"). Same venue/fee/faculty/techniques, different dates → **one
Offering per session** (id `…/summer-dance-project-golun-{start ISO}`), so each
dated edition stays distinct and diffable. Ended cycles are kept (IDR-24); "past"
is derived from dates, never stored.

DEADLINE TYPO: the duplicate posts append "zapisy do 10.05.2025 / 10.06.2025" —
registration deadlines whose **year is a copy-paste typo** (the sessions are
unambiguously 2026, and a May/June 2025 deadline for a 2026 course is impossible).
Rather than commit a misleading 2025 `application.deadline`, we leave it null
("not stated reliably", fail-open). The clean `/warsztaty/` page omits the
deadlines entirely, so the scrape never sees them.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - TEACHERS with AFFILIATIONS — the named special guest (Guido Marni, ex-La Scala
    / National Ballet of Canada / Semperoper Dresden) plus the resident faculty
    from the `/pedagodzy/` (teachers) page, each resolved to its house (e.g. Stella
    Walasik, currently Polish National Ballet). For scoring.
  - PRICES in local currency — a single residential fee in **PLN** that bundles
    tuition + accommodation + meals ("Koszt … 3200zł … cztery posiłki dziennie").
  - SELECTIVITY — "Ilość miejsc ograniczona!" (limited places), recorded in notes;
    no audition/photo submission is stated → requirements left [] (unknown).
"""

from __future__ import annotations

import html
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

BASE = "https://asb-balet.pl"
PAGE_SLUG = "warsztaty"
PAGE_URL = f"{BASE}/warsztaty/"

ORG = Organization(
    name="Akademia Sztuki Baletowej",
    slug="akademia-sztuki-baletowej",
    country="PL",
    city="Sopot",
)

# Hotel Gołuń sits in Wdzydze Tucholskie, Kashubia (Pomerania), where the
# residential workshop is held — distinct from the academy's home in Sopot/Gdańsk.
VENUE = "Hotel Gołuń"
VENUE_CITY = "Wdzydze Tucholskie"

# Resident faculty + the named guest, with affiliations resolved for scoring. The
# guest is named only in the announcement; the resident roster comes from the
# `/pedagodzy/` (teachers) page. Affiliations are stable facts about each person,
# not scraped per-run, so they're pinned here (the bios are Polish prose that would
# be brittle to parse and the set changes rarely).
_TEACHERS: list[Teacher] = [
    Teacher(
        name="Guido Marni",
        role="guest",
        affiliations=[
            Affiliation(organization="Teatro alla Scala", current=False),
            Affiliation(organization="National Ballet of Canada", current=False),
            Affiliation(organization="Semperoper Dresden", current=False),
        ],
    ),
    Teacher(
        name="Jacek Walasik",
        role="teacher",
        affiliations=[
            Affiliation(
                organization="Akademia Sztuki Baletowej",
                slug="akademia-sztuki-baletowej",
                role="founder",
                current=True,
            ),
        ],
    ),
    Teacher(
        name="Stella Walasik",
        role="teacher",
        affiliations=[
            Affiliation(organization="Polish National Ballet", role="dancer", current=True),
        ],
    ),
    Teacher(
        name="Kazimierz Wrzosek",
        role="teacher",
        affiliations=[
            Affiliation(organization="Gdańsk Ballet School", role="teacher", current=True),
            Affiliation(
                organization="Teatr Wielki w Łodzi", role="principal dancer", current=False
            ),
        ],
    ),
    Teacher(
        name="Lidia Kowcz",
        role="teacher",
        affiliations=[
            Affiliation(organization="Teatr Wielki w Warszawie", role="soloist", current=False),
        ],
    ),
]

# Polish month names → number, so the day-month-year dates parse from the Polish
# body. Genitive forms are what the text uses ("27 czerwca", "05 lipca").
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

# A session span: "od 27 czerwca do 05 lipca 2026" (start month differs from end)
# or "od 22 do 31 sierpnia 2026" (single shared month, no start month). The year
# trails the end. The start month is optional so both shapes match.
_SESSION = re.compile(
    r"od\s+(\d{1,2})\s+(?:(" + _MONTHALT + r")\s+)?do\s+(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(f"{BASE}/wp-json/wp/v2/pages", params={"slug": PAGE_SLUG})
    resp.raise_for_status()
    records = resp.json()
    rendered = records[0]["content"]["rendered"] if records else ""
    return _build_offerings(rendered, date.today())


def _build_offerings(rendered: str, today: date) -> list[Offering]:  # noqa: ARG001 — today reserved
    text = _plain_text(rendered)
    genres = _genres(text)
    prices = _prices(text)
    notes = _application_notes(text)

    offerings: list[Offering] = []
    for start, end in _sessions(text):
        offerings.append(
            Offering(
                id=f"akademia-sztuki-baletowej/summer-dance-project-golun-{start.isoformat()}",
                source=Source(
                    provider="akademia-sztuki-baletowej", url=PAGE_URL, scrapedAt=now_utc()
                ),
                title=f"Summer Dance Project — Gołuń {start.year}",
                genres=genres,
                organization=ORG,
                location=Location(venue=VENUE, city=VENUE_CITY, country="PL"),
                schedule=Schedule(
                    season=str(start.year),
                    start=start,
                    end=end,
                    timezone="Europe/Warsaw",
                ),
                teachers=list(_TEACHERS),
                prices=prices,
                application=Application(url=PAGE_URL, notes=notes),
            )
        )
    offerings.sort(key=lambda o: o.id)
    return offerings


def _plain_text(rendered: str) -> str:
    tree = HTMLParser(rendered)
    for node in tree.css("script, style"):
        node.decompose()
    return parse.clean(html.unescape(tree.text(separator=" ")))


# --- sessions -----------------------------------------------------------------


def _sessions(text: str) -> list[tuple[date, date]]:
    """The dated session spans, deduped and chronologically ordered."""
    spans: list[tuple[date, date]] = []
    for m in _SESSION.finditer(text):
        d1, m1, d2, m2, year = m.groups()
        y = int(year)
        end_month = _MONTHS[m2.lower()]
        # A single-month span ("od 22 do 31 sierpnia") omits the start month —
        # it shares the end month.
        start_month = _MONTHS[m1.lower()] if m1 else end_month
        span = (date(y, start_month, int(d1)), date(y, end_month, int(d2)))
        if span not in spans:
            spans.append(span)
    return sorted(spans)


# --- prices -------------------------------------------------------------------
#
# The fee is a single residential rate, written as "Koszt … 3200zł" / "Koszt
# pobytu 3200zł". It bundles lodging + four meals a day ("cztery posiłki dziennie
# / szwedzki stół"), so it covers tuition, accommodation and meals.

_PRICE = re.compile(r"(\d[\d ]*\d|\d)\s*(?:zł|zl|pln)\b", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    m = _PRICE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1).replace(" ", ""))
    if amount is None or amount < 100:
        return []
    return [
        Price(
            amount=amount,
            currency="PLN",
            label="Residential fee",
            includes=["tuition", "accommodation", "meals"],
            notes="Full board (four meals a day).",
        )
    ]


# --- genres -------------------------------------------------------------------
#
# Matched against the stated technique list ("w technikach: taniec klasyczny,
# technika point, taniec współczesny, repertuar, partnerowanie …"), not loose
# prose, so the genres reflect classes actually taught.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("klasyczn", "classical", "ballet", "balet")),
    ("pointe", ("point", "pointe", "puent")),
    ("contemporary", ("współczesn", "wspolczesn", "contemporary")),
    ("repertoire", ("repertuar", "repertoire", "repertory")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- application --------------------------------------------------------------
#
# No audition / photo / video submission is stated, so requirements stay []
# (unknown). What the source *does* say is that places are limited ("Ilość miejsc
# ograniczona!") — a selectivity signal worth keeping as a note. The registration
# deadlines on the duplicate posts carry a typo'd 2025 year (see module docstring),
# and the clean page omits them, so application.deadline is never set.

_LIMITED = re.compile(r"ilo[śs][ćc]\s+miejsc\s+ograniczona", re.IGNORECASE)


def _application_notes(text: str) -> str | None:
    if _LIMITED.search(text):
        return "Places are limited."
    return None
