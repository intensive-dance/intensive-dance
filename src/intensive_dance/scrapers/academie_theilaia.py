"""Académie de Ballet Nini Theilade (Lyon, FR) — its "Theilaïa" summer intensive.

API FIRST: WordPress. academie-ballet.fr runs WordPress and exposes the standard
`/wp-json/wp/v2/pages` REST collection, so we pull the Theilaïa stage page record
by slug and read its `content.rendered` (no HTML page scrape, no JS). The body is
WPBakery markup whose meaningful facts (dates in the heading, level bands, the
fee block) sit inside `[vc_toggle]` panels; we strip the shortcodes and inline
team-plugin CSS and read the resulting plain text.

DISCOVERY: one page = one dated edition (the "24e Stage International du 13 au
17 juillet 2026"). Theilaïa is a single one-week summer course held at the CNSMD
de Lyon, so we emit a single `Offering`, season-keyed from the dates so the id
rolls forward when the page advances to the next edition. Per IDR-66 scope, only
the genuine dated edition is built — nothing is fabricated.

FRENCH SOURCE: kept faithful (no inline translation). Dates are parsed
language-agnostically: numeric day/day + a French month map ("du 13 au 17
juillet 2026"), so the edition's title anchors the schedule regardless of how the
prose reads.

WHAT THE PAGE GIVES US (verified live 2026-06):
  - DATES: the course title carries "du 13 au 17 juillet 2026" (a single shared
    month + year across both days). Sunday 12 July is arrivals/check-in only.
  - AGES/LEVELS: "Cours ouverts aux Enfants dès 9 ans … Adultes" over five bands
    (Élémentaire 9-11 … Supérieur 16+ … Adulte), so open from 9 with no upper
    bound (adults included), spanning beginner → professional + open.
  - PRICES in EUR: a 525 € forfait (4-6 classes/day, tuition), a 150 € adult
    evening 4-class card (tuition), and 525 € supervised full-board boarding
    (accommodation + meals). Partner-hotel rack rates are the hotels', not the
    course's, so they're not emitted.
  - GENRES: the curriculum is Classical Ballet, Repertory, Pas de deux, Character
    Dance, Baroque Dance, Floor Barre → classical / repertoire / character.
  - APPLICATION: online registration opens "à partir du lundi 12 janvier 2026";
    a reduced rate applies to sign-ups before 30 March 2026. Requirements aren't
    described (it's an open enrolment, not an audition), so they stay `[]`.

Faculty are a named roll of POB étoiles and CNSMD professors, but listed as a
standing artistic team (some marked "*sous réserve"), not a confirmed per-class
2026 roster, so teachers are left empty rather than over-attributed (the same
call the Brussels and Joffrey scrapers make).
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.academie-ballet.fr"
PAGE_SLUG = "theilaia-24e-stage-international-du-13-au-17-juillet-2026"

ORG = Organization(
    name="Académie de Ballet Nini Theilade",
    slug="academie-theilaia",
    country="FR",
    city="Lyon",
)
# Classes are held in the studios of the Conservatoire (CNSMD), not at the school.
VENUE = "Conservatoire National Supérieur Musique et Danse de Lyon (CNSMD)"

# French month names → number, for language-agnostic date parsing (the rest of
# the prose is left untranslated). Local to this scraper per AGENTS.md.
_FR_MONTHS: dict[str, int] = {
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
_FR_MONTHALT = parse.months_alt(_FR_MONTHS)


def scrape(client: httpx.Client) -> list[Offering]:
    record = wp.fetch_page(client, PAGE_SLUG, base=BASE)
    if record is None:
        return []
    rendered = record["content"]["rendered"]
    title = record["title"]["rendered"]
    link = record.get("link") or f"{BASE}/{PAGE_SLUG}/"
    offering = _build_offering(title, rendered, link)
    return [offering] if offering is not None else []


def _build_offering(title: str, rendered: str, url: str) -> Offering | None:
    title = parse.clean(_unescape_entities(title))
    text = _plain_text(rendered)

    start, end = _date_range(title)
    anchor = end or start
    if anchor is None:
        return None  # no dated edition parseable — don't fabricate
    season = str(anchor.year)
    edition = _edition_label(title)

    return Offering(
        id=f"academie-theilaia/stage-international-{season}",
        source=Source(provider="academie-theilaia", url=url, scrapedAt=now_utc()),
        title=f"Theilaïa — Stage International {season}" + (f" ({edition})" if edition else ""),
        genres=_genres(text),
        level=_levels(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue=VENUE, city="Lyon", country="FR"),
        schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Paris"),
        prices=_prices(text),
        application=_application(text, url),
    )


# --- text extraction ----------------------------------------------------------


def _unescape_entities(raw: str) -> str:
    import html as _html

    return _html.unescape(raw)


def _plain_text(rendered: str) -> str:
    """Collapse the WPBakery body to plain text, dropping inline team-plugin CSS.

    `wp.plain_text` keeps the `<style>` blocks the team-manager plugin injects as
    literal text (a wall of selectors), so we strip those nodes first.
    """
    clean = re.sub(r"\[/?[a-z][^\]]*\]", " ", _unescape_entities(rendered))
    tree = HTMLParser(clean)
    for node in tree.css("style, script"):
        node.decompose()
    return parse.clean(tree.text(separator=" ")) if tree.body else ""


# --- dates: "du 13 au 17 juillet 2026" (shared month + year) ------------------

_RANGE = re.compile(
    r"du\s+(\d{1,2})\s+au\s+(\d{1,2})\s+(" + _FR_MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(title: str) -> tuple[date | None, date | None]:
    match = _RANGE.search(title)
    if not match:
        return None, None
    d1, d2, month_name, year = match.groups()
    month = _FR_MONTHS[month_name.lower()]
    y = int(year)
    return date(y, month, int(d1)), date(y, month, int(d2))


_EDITION = re.compile(r"(\d{1,3})\s*e\b", re.IGNORECASE)


def _edition_label(title: str) -> str | None:
    """The ordinal edition stamp, e.g. "24e edition", kept in the offering title."""
    match = _EDITION.search(title)
    return f"{match.group(1)}e edition" if match else None


# --- ages / levels ------------------------------------------------------------

# "Cours ouverts aux Enfants dès 9 ans … Adultes" — open from the lowest age, no
# upper bound (adults are included, so the top stays null per the model).
_AGE_LOW = re.compile(r"d[èe]s\s+(\d{1,2})\s+ans", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    match = _AGE_LOW.search(text)
    if not match:
        return None
    return {"min": int(match.group(1))}


# Five named bands, mapped onto our level enum. "Adulte" → open (anyone may join);
# the named pre-professional admission is explicit ("Pré-professionnels").
_LEVEL_KEYWORDS: list[tuple[Level, tuple[str, ...]]] = [
    ("beginner", ("élémentaire", "amateur")),
    ("intermediate", ("intermédiaire",)),
    ("advanced", ("avancé", "supérieur")),
    ("pre-professional", ("pré-professionnel",)),
    ("professional", ("professionnel",)),
    ("open", ("adulte",)),
]


def _levels(text: str) -> list[Level]:
    low = text.lower()
    found: list[Level] = []
    for level, keys in _LEVEL_KEYWORDS:
        if any(k in low for k in keys):
            found.append(level)
    return found


# --- prices: the 2026 fee block ----------------------------------------------

# "Forfait tarif réduit 525 €", "Carte de 4 cours adulte en soirée 150 €",
# "Hébergement en internat surveillé en pension complète 525 €". Each is a label
# line followed by an amount + €; partner-hotel rack rates are excluded (they're
# the hotels' prices, billed separately, not the course fee).
_FORFAIT = re.compile(r"Forfait\s+tarif\s+r[ée]duit\s+(\d[\d .]*)\s*€", re.IGNORECASE)
_ADULT_CARD = re.compile(
    r"Carte\s+de\s+4\s+cours\s+adulte\s+en\s+soir[ée]e\s+(\d[\d .]*)\s*€", re.IGNORECASE
)
_BOARDING = re.compile(
    r"H[ée]bergement\s+en\s+internat\s+surveill[ée]\s+en\s+pension\s+compl[èe]te\s+(\d[\d .]*)\s*€",
    re.IGNORECASE,
)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    forfait = _FORFAIT.search(text)
    if forfait:
        amount = parse.parse_amount(forfait.group(1))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="Forfait (4 à 6 cours par jour) — tarif réduit",
                    includes=["tuition"],
                    notes="Tarif réduit pour toute inscription avant le 30 mars 2026.",
                )
            )
    adult = _ADULT_CARD.search(text)
    if adult:
        amount = parse.parse_amount(adult.group(1))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="Carte de 4 cours adulte en soirée",
                    includes=["tuition"],
                )
            )
    boarding = _BOARDING.search(text)
    if boarding:
        amount = parse.parse_amount(boarding.group(1))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label="Hébergement en internat surveillé (pension complète)",
                    includes=["accommodation", "meals"],
                )
            )
    return prices


# --- genres: the curriculum list ---------------------------------------------

# Match the syllabus ("Classical Ballet, Repertory, Pas de deux, Character Dance,
# Baroque Dance, Floor Barre"), not loose prose. Baroque is grouped with
# character on the site ("Danse de Caractère et Danse Baroque"), folded here.
_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "classique")),
    ("repertoire", ("repertory", "repertoire", "répertoire")),
    ("character", ("character", "caractère", "baroque")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- application --------------------------------------------------------------

# "Inscription au stage – à partir du lundi 12 janvier 2026".
_OPENS = re.compile(
    r"Inscription[^–-]*[–-]?\s*à\s+partir\s+du\s+\w+\s+(\d{1,2})\s+("
    + _FR_MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _opens_at(text: str) -> date | None:
    match = _OPENS.search(text)
    if not match:
        return None
    day, month_name, year = match.groups()
    return date(int(year), _FR_MONTHS[month_name.lower()], int(day))


def _application(text: str, url: str) -> Application:
    opens = _opens_at(text)
    # Status follows the stated opening date — "upcoming" before it, "open" once
    # registration has opened (Theilaïa is open enrolment, not a closed audition).
    status = None
    if opens is not None:
        status = "open" if date.today() >= opens else "upcoming"
    return Application(
        status=status,
        opensAt=opens,
        url=url,
        notes=(
            "Inscription en ligne (places limitées). Tarif réduit pour toute "
            "inscription avant le 30 mars 2026."
        ),
    )
