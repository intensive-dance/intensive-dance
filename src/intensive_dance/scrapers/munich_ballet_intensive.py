"""Munich Ballet Intensive (Dance Arts Academy) — its Summer Intensiv workshop.

API FIRST: none usable. The provider's school site (danceartsacademy.de) runs on
**Wix** (Pepyaka server, parastorage assets; `/wp-json/` 301-redirects — not
WordPress) and its `/workshops` page only teases the intensive with a "Mehr
erfahren" link out to a dedicated **Google Sites** microsite,
`munichballetintensive.com`. That microsite is the canonical source and is
server-side rendered (Google Sites bakes the body text into the static HTML), so
this is a small multi-page HTML scrape — no JS/proxy needed. Google Sites
fragments inline text across spans (the Preise page splits "1 3 - 1 7 Jahre"), so
ages are parsed by collapsing digit-internal spaces and prices/dates anchor on
the intact "Gruppe N", "NNN €" and numeric "DD.MM.YYYY" tokens.

DISCOVERY: one dated edition runs twice yearly ("Zweimal jährlich"); the site
advertises the single upcoming Summer Intensiv with a numeric date span on the
Startseite/Preise pages → one Offering, year-stamped from the span. The two
priced Gruppen differ only by age band and fee (same dates/venue/faculty), so
they are folded into ONE Offering carrying both `Price`s, not two Offerings.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-09):
  - DATES: a numeric "03.08.2026 - 08.08.2026" span (DD.MM.YYYY) read directly —
    no month-name map needed; season = the span's year.
  - AGES: overall 10–17, taken from the wider of the two Gruppe bands
    (Gruppe 1 10–13, Gruppe 2 13–17).
  - LEVEL: "fortgeschrittene Ballettstudenten" (advanced students) → `advanced`.
  - GENRES: matched against the Preise curriculum list (Floor work / Ballet class
    / Technique & Coordination / Repertoire / Point work) → classical + repertoire
    + pointe; not from the marketing prose.
  - PRICES in EUR: two tuition tiers, one per age Gruppe (300 € / 350 €).
  - TEACHERS: the "Über uns" page names the two directors, Katherina Markowskaja
    ("Katja") and Maxim Chashchegorov, each with their company affiliations
    (Bavarian State Ballet soloists; Semperoper Dresden / Mariinsky pedigree).
  - APPLICATION: "Unsere Anmeldung ist geöffnet" → `open`; the registration form
    lives back on the school's Wix site (anmeldungsformular). No audition stated
    → requirements `[NoneReq]`.
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
    Level,
    Location,
    NoneReq,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.munichballetintensive.com"
HOME = f"{BASE}/startseite"
PRICES = f"{BASE}/preise"
ABOUT = f"{BASE}/%C3%BCber-uns"  # "/über-uns"
# Registration lives on the school's own Wix site, linked from the microsite.
APPLY_URL = "https://www.danceartsacademy.de/anmeldungsformular"
TZ = "Europe/Berlin"

ORG = Organization(
    name="Dance Arts Academy",
    slug="munich-ballet-intensive",
    country="DE",
    city="Munich",
)

# The school's studios in Unterschleißheim (Munich metro), per the microsite's
# Kontakt page; the programme itself is billed as taking place "in München".
_LOCATION = Location(
    venue="Dance Arts Academy (Pater-Kolbe-Straße 7, 85716 Unterschleißheim)",
    city="Munich",
    country="DE",
)

_APPLY_NOTE = (
    "Held twice a year in Munich for advanced ballet students. Registration is "
    "open; the registration form is hosted on the Dance Arts Academy site."
)


def scrape(client: httpx.Client) -> list[Offering]:
    home = client.get(HOME, follow_redirects=True)
    home.raise_for_status()
    prices = client.get(PRICES, follow_redirects=True)
    prices.raise_for_status()
    about = client.get(ABOUT, follow_redirects=True)
    about.raise_for_status()
    offering = _build_offering(home.text, prices.text, about.text)
    return [offering] if offering is not None else []


def _build_offering(home_html: str, prices_html: str, about_html: str) -> Offering | None:
    home = _text(home_html)
    prices_text = _text(prices_html)

    start, end = _dates(home + " " + prices_text)
    if start is None or end is None:
        return None  # no dated edition advertised
    season = str(start.year)

    return Offering(
        id=f"munich-ballet-intensive/summer-intensive-{season}",
        source=Source(provider="munich-ballet-intensive", url=HOME, scrapedAt=now_utc()),
        title=f"Summer Intensiv {season}",
        genres=_genres(prices_text),
        level=_levels(home),
        ageRange=_age_range(prices_text),
        organization=ORG,
        location=_LOCATION,
        schedule=Schedule(season=season, start=start, end=end, timezone=TZ),
        teachers=_teachers(_text(about_html)),
        prices=_prices(prices_text),
        application=Application(
            status=_status(home),
            url=APPLY_URL,
            requirements=[NoneReq()],
            notes=_APPLY_NOTE,
        ),
    )


def _text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    raw = tree.body.text(separator=" ") if tree.body else ""
    return parse.clean(raw)


# --- dates: a numeric "DD.MM.YYYY - DD.MM.YYYY" span --------------------------

_RANGE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s*[-–—]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _dates(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    d1, mo1, y1, d2, mo2, y2 = (int(g) for g in m.groups())
    try:
        return date(y1, mo1, d1), date(y2, mo2, d2)
    except ValueError:
        return None, None


# --- ages: widest of the two Gruppe bands ("10 - 13", split "1 3 - 1 7") ------

# Collapse spaces between digits first ("1 3 - 1 7" -> "13-17") so split spans
# don't defeat the band match; then read every "<lo> - <hi> Jahre" band.
_BAND = re.compile(r"(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*Jahre", re.IGNORECASE)
_DIGIT_GAP = re.compile(r"(?<=\d)\s+(?=\d)")


def _age_range(text: str) -> dict | None:
    collapsed = _DIGIT_GAP.sub("", text)
    bands = [(int(a), int(b)) for a, b in _BAND.findall(collapsed)]
    if not bands:
        return None
    return {"min": min(lo for lo, _ in bands), "max": max(hi for _, hi in bands)}


# --- level --------------------------------------------------------------------


def _levels(text: str) -> list[Level]:
    return ["advanced"] if re.search(r"fortgeschrittene", text, re.IGNORECASE) else []


# --- genres: matched on the Preise curriculum list ----------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet class", "technique", "floor work")),
    ("repertoire", ("repertoire", "variation")),
    ("pointe", ("point work", "pointe")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- prices: one tuition tier per age Gruppe ----------------------------------

# "Gruppe 1 10 - 13 Jahre 300 €" / "Gruppe 2 1 3 - 1 7 Jahre 350 €". The age
# digits can be space-split, so the band is matched loosely; the fee is an intact
# "NNN €" token.
_PRICE = re.compile(
    r"(Gruppe\s*\d+)\s*"
    r"(\d{1,2}(?:\s*\d)?\s*[-–—]\s*\d{1,2}(?:\s*\d)?)\s*Jahre\s*"
    r"(\d[\d.,]*)\s*€",
    re.IGNORECASE,
)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    for m in _PRICE.finditer(text):
        amount = parse.parse_amount(m.group(3))
        if amount is None:
            continue
        group = parse.clean(m.group(1))
        # Collapse Google Sites' split digits ("1 3 - 1 7") and dash spacing into
        # a tidy "13-17" band for the label.
        band = re.sub(r"\s+", "", parse.clean(m.group(2))).replace("–", "-").replace("—", "-")
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=f"{group} ({band} years)",
                includes=["tuition"],
            )
        )
    return prices


# --- teachers: the two directors with their company affiliations --------------

# The "Über uns" page gives each director a biography paragraph keyed by their
# name. Affiliations are pinned to the companies the bios name (kept conservative:
# the engagements they actually held, not every mentioned stage).
_TEACHERS: list[tuple[str, str, list[Affiliation]]] = [
    (
        "Katherina Markowskaja",
        "Director / teacher",
        [
            Affiliation(organization="Bavarian State Ballet", role="Soloist", current=False),
            Affiliation(
                organization="Semperoper Ballett (Sächsische Staatsoper Dresden)",
                role="Principal",
                current=False,
            ),
        ],
    ),
    (
        "Maxim Chashchegorov",
        "Director / teacher",
        [
            Affiliation(organization="Bavarian State Ballet", role="Soloist", current=False),
            Affiliation(organization="Mariinsky Ballet", role="Corps de ballet", current=False),
        ],
    ),
]


def _teachers(about_text: str) -> list[Teacher]:
    # Tolerate the name being space-split across spans on Google Sites by matching
    # on the surname, which renders intact.
    out: list[Teacher] = []
    for name, role, affiliations in _TEACHERS:
        surname = name.split()[-1]
        if surname.lower() in about_text.lower():
            out.append(Teacher(name=name, role=role, affiliations=affiliations))
    return out


# --- application status -------------------------------------------------------


def _status(text: str):
    low = text.lower()
    if "anmeldung ist geöffnet" in low or "jetzt anmelden" in low:
        return "open"
    return None
