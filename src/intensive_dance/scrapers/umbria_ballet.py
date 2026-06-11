"""Umbria Ballet — Centro Professionale di Danza (IT) — Legacy Master of Ballet.

API FIRST
The site (https://www.umbriaballet.com) is WordPress + WPBakery, and the program
pages DO come back through the REST API — `GET /wp-json/wp/v2/pages?slug=<slug>`
returns the full `content.rendered` (shortcodes + headings + `<p>` blocks), so
`wp.parse` turns it into heading-keyed sections with no HTML scrape, proxy or JS
render. No `ld+json`.

DISCOVERY — the school is a year-round vocational academy, but it runs one dated,
public, numero-chiuso summer intensive with its own pages → ONE Offering:
  LEGACY MASTER OF BALLET (Seconda Edizione) — 29 Jun – 4 Jul 2026, at the Resort
  Valle di Assisi. The body lives on `/iscrizione-lmb/` (dates, faculty, the
  class list, the photo/video selection, accommodation); the fee lives on a
  separate `/lmob-pagamento/` PayPal page ("850€ + 50,00€ Tariffa Paypal"), so
  both pages are fetched and merged. The landing `/lmb/` page is just the date +
  "Coming Soon", so it is not used.

The "Novità" block opens the edition to dance *teachers* who want to observe the
Académie Princesse Grace methodology — an observation add-on, not a separate
student intensive, so it does not become its own Offering.

PRICE: tuition is €850 (bank transfer); the +€50 is a PayPal surcharge, recorded
in the price note, not added to the amount. Accommodation at the Resort is
available but explicitly NOT included (bookable only after passing selection).

GENRES: scoped to the "LE LEZIONI" class list (the authoritative syllabus, not
the marketing prose) → classical (Tecnica classica/maschile), contemporary
(contemporaneo), pointe (Punte). "Repertorio contemporaneo" appears only in some
faculty's discipline labels, not the class list, so repertoire is not emitted.

AGES: the 2026 page states no age band (only "ogni livello"), so `ageRange` is
left null rather than importing a prior edition's bands.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-11)
- WordPress REST `content.rendered` parsed via `wp.parse` (WPBakery shortcodes).
- Two pages merged into one Offering (body + a separate PayPal fee page).
- Faculty roster from `<h3>`-name sections (skipping the pianist accompanists).
- A single Italian date range; a single tuition Price with a surcharge note.
- Photo/video selection → PhotosReq(freeform) + VideoReq(unspecific).
- Null `ageRange` (level-only, not stated) — faithful, not invented.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    PhotosReq,
    Price,
    Schedule,
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

BASE = "https://www.umbriaballet.com"
INFO_SLUG = "iscrizione-lmb"
PAYMENT_SLUG = "lmob-pagamento"
INFO_URL = f"{BASE}/{INFO_SLUG}/"

ORG = Organization(
    name="Umbria Ballet — Centro Professionale di Danza",
    slug="umbria-ballet",
    country="IT",
    city="Bastia Umbra",
)

_MONTHS = {
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12,
}
_MONTHALT = "|".join(_MONTHS)

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classic",)),
    ("contemporary", ("contemporane",)),
    ("pointe", ("punte", "punta")),
]

# "Luca MASALA": a title-case forename followed by an all-caps surname. Section
# headings like "DOCENTI" / "LE LEZIONI" / "PARTNER UFFICIALE" are all-caps with
# no title-case word, so they don't match.
_TEACHER_NAME = re.compile(r"^[A-ZÀ-Ý][a-zà-ý]+(?:\s+[A-ZÀ-Ý][a-zà-ý]+)*\s+[A-ZÀ-ÝÑ'’]{2,}$")


def scrape(client: httpx.Client) -> list[Offering]:
    info = wp.fetch_page(client, INFO_SLUG, base=BASE)
    if info is None:
        raise RuntimeError("Umbria Ballet: iscrizione-lmb page not found")
    payment = wp.fetch_page(client, PAYMENT_SLUG, base=BASE)
    payment_text = wp.plain_text(payment["content"]["rendered"]) if payment else ""
    return [_build_offering(info["content"]["rendered"], payment_text)]


def _build_offering(info_rendered: str, payment_text: str) -> Offering:
    content = wp.parse(info_rendered)
    flat = wp.plain_text(info_rendered)
    start, end = _date_range(flat)
    season = str((start or date(2026, 1, 1)).year)
    return Offering(
        id=f"umbria-ballet/legacy-master-of-ballet-{season}",
        source=Source(provider="umbria-ballet", url=INFO_URL, scrapedAt=now_utc()),
        title=f"Legacy Master of Ballet {season}",
        genres=_genres(content),
        organization=ORG,
        location=Location(venue="Resort Valle di Assisi", city="Assisi", country="IT"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Rome",
            notes=_dates_notes(flat),
        ),
        teachers=_teachers(content),
        prices=_prices(payment_text),
        application=_application(flat),
    )


# "Dal 29 giugno al 4 luglio 2026" (single trailing year).
_RANGE = re.compile(
    r"Dal\s+(\d{1,2})\s+(" + _MONTHALT + r")\s+al\s+(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    d1, mon1, d2, mon2, year = m.groups()
    y = int(year)
    return date(y, _MONTHS[mon1.lower()], int(d1)), date(y, _MONTHS[mon2.lower()], int(d2))


def _dates_notes(text: str) -> str | None:
    m = _RANGE.search(text)
    return m.group(0) if m else None


def _genres(content: wp.Content) -> list[Genre]:
    lessons = content.find("LEZIONI")
    scope = lessons.text() if lessons else ""
    return parse.match_genres(scope, _GENRE_KEYWORDS, default=["classical"])


def _teachers(content: wp.Content) -> list[Teacher]:
    teachers: list[Teacher] = []
    for section in content.sections:
        if not _TEACHER_NAME.match(section.heading):
            continue
        role = ", ".join(line for line in section.text().splitlines() if line.strip())
        # The PIANISTI block reuses the same name-heading shape; accompanists are
        # not teaching faculty.
        if not role or "pianista" in role.lower():
            continue
        teachers.append(Teacher(name=section.heading, role=parse.clean(role)))
    return teachers


_AMOUNT = re.compile(r"(\d[\d.,]*)\s*€")


def _prices(payment_text: str) -> list[Price]:
    m = _AMOUNT.search(payment_text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    return [
        Price(
            amount=amount,
            currency="EUR",
            label="Tuition",
            includes=["tuition"],
            notes="Plus a €50 PayPal surcharge; accommodation at the Resort not included.",
        )
    ]


def _application(text: str) -> Application:
    requirements = []
    if re.search(r"selezione\s+foto/?\s*video", text, re.IGNORECASE):
        requirements.append(PhotosReq(specificity="freeform"))
        requirements.append(VideoReq(specificity="unspecific", description="Selezione foto/video"))
    return Application(url=INFO_URL, requirements=requirements)
