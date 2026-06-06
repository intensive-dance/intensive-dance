"""Académie Internationale de Danse de Biarritz (FR) — its summer academy week.

API FIRST: yes. The site runs on **WordPress** and exposes a clean REST API
(`/wp-json/wp/v2/pages`), so every detail page (présentation, infos pratiques,
inscription, équipe pédagogique) is read as `content.rendered` HTML — no
front-end HTML scrape, no JS render.

TLS NOTE: the host serves a certificate whose hostname doesn't match
(`CERTIFICATE_VERIFY_FAILED`), so the shared client can't validate it. We fetch
with our own `make_client(verify=False)` — the same call Princesse Grace and
Frankfurt make. When the fetch proxy is configured (CI) `make_client` routes
through it instead, and the broken-chain concern moves server-side; `verify` only
affects the direct dev hop.

DISCOVERY: one organisation, one dated edition per year — a single week-long
academy at the Lycée hôtelier Biarritz Atlantique ("du 2 au 7 août 2026", ~350
stagiaires). It's **open-enrolment**, not an audition: a dancer buys a "carte"
(6 / 12 / 18 / unlimited classes) on HelloAsso and picks classes by level. So we
emit **one** `Offering`, season-keyed from the parsed year, with no audition
requirements — the only selection on the site is the *optional* company class
with Malandain Ballet (17+, CV + video), kept as an application note.

FRENCH SOURCE kept faithfully (no inline translation); the date is parsed
language-agnostically via a French month map (`août` → 8) plus the year read off
the "… août 2026" headline, since the day-month lines themselves carry no year.

WHAT THE PAGES GIVE US (verified live 2026-06):
  - DATES: "Début des cours : dimanche 2 août / Fin des cours : vendredi 7 août".
  - LEVELS/AGES: tiers Élémentaire 9/10 → Supérieur 16+; explicitly **no
    beginners** ("un minimum de deux ans de danse est requis"). Lower age bound 9,
    open-topped (pre-pro/pro adults welcome).
  - GENRES: classique, pointes, répertoire (filles/garçons), and choreographic
    ateliers/workshops (Malandain, Kylian, Inger, Forsythe…) → contemporary.
  - PRICES in EUR: four class cards at the public tier (240/380/480/520 €);
    reduced "grandes écoles"/professional tiers kept as a price note. Accommodation
    (internat, pension complète) is described but its forfait isn't a number here.
  - TEACHERS: a confirmed 2026 faculty roster, each with their home company/school
    (Opéra de Paris, Bordeaux, Cuba, Zurich, Marseille…) — carried as affiliations.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse, wp
from intensive_dance.fetch import make_client
from intensive_dance.models import (
    Affiliation,
    Application,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://biarritz-academie-danse.com"
PAGE = f"{BASE}/"
INSCRIPTION_URL = f"{BASE}/inscription/"

ORG = Organization(
    name="Académie Internationale de Danse de Biarritz",
    slug="academie-danse-biarritz",
    country="FR",
    city="Biarritz",
)

VENUE = "Lycée hôtelier Biarritz Atlantique"

# French month names → number, for the language-agnostic date parse.
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

_APPLY_NOTE = (
    "Open enrolment via HelloAsso: each dancer buys a class card (6 / 12 / 18 or "
    "unlimited classes) and selects classes by level. No beginners — a minimum of "
    "two years of dance is required. An optional class with the Malandain Ballet "
    "Biarritz company is open to pre-professional/professional dancers aged 17+, by "
    "selection on application (CV + a ~3-minute video)."
)


def scrape(client: httpx.Client) -> list[Offering]:  # noqa: ARG001 — see TLS NOTE
    # The shared client can't validate the host's mismatched cert; use our own
    # (which still routes through the fetch proxy in CI when it's configured).
    own = make_client(verify=False)
    try:
        pages = {
            slug: ((wp.fetch_page(own, slug, base=BASE) or {}).get("content", {}) or {}).get(
                "rendered", ""
            )
            for slug in ("infos-pratiques", "presentation", "equipe-pedagogique", "et-aussi")
        }
    finally:
        own.close()
    offering = _build_offering(pages, date.today())
    return [offering] if offering is not None else []


def _build_offering(pages: dict[str, str], today: date) -> Offering | None:  # noqa: ARG001
    infos = _text(pages.get("infos-pratiques", ""))
    presentation = _text(pages.get("presentation", ""))
    etaussi = _text(pages.get("et-aussi", ""))

    start, end = _date_range(infos, " ".join((presentation, infos, etaussi)))
    anchor = end or start
    if anchor is None:
        return None  # no dated edition parseable
    season = str(anchor.year)

    return Offering(
        id=f"academie-danse-biarritz/academy-{season}",
        source=Source(provider="academie-danse-biarritz", url=PAGE, scrapedAt=now_utc()),
        title=f"Académie Internationale de Danse de Biarritz {season}",
        genres=_genres(presentation),
        level=_levels(presentation),
        ageRange=_age_range(presentation),
        organization=ORG,
        location=Location(venue=VENUE, city="Biarritz", country="FR"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Paris",
            notes=_schedule_note(etaussi),
        ),
        teachers=_teachers(pages.get("equipe-pedagogique", "")),
        prices=_prices(pages.get("infos-pratiques", "")),
        application=Application(url=INSCRIPTION_URL, notes=_APPLY_NOTE),
    )


def _text(html: str) -> str:
    if not html:
        return ""
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.text(separator=" "))


# --- dates: "Début des cours : dimanche 2 août" / "Fin des cours : vendredi 7 août" ---
# The day-month lines carry no year; it lives in the "… août 2026" headline.
_START = re.compile(
    r"Début\s+des\s+cours\s*:?\s*\w+\s+(\d{1,2})\s+(" + _FR_MONTHALT + r")", re.IGNORECASE
)
_END = re.compile(
    r"Fin\s+des\s+cours\s*:?\s*\w+\s+(\d{1,2})\s+(" + _FR_MONTHALT + r")", re.IGNORECASE
)
_YEAR = re.compile(r"(" + _FR_MONTHALT + r")\s+(\d{4})", re.IGNORECASE)


def _date_range(infos: str, year_text: str) -> tuple[date | None, date | None]:
    year_m = _YEAR.search(year_text)
    if not year_m:
        return None, None
    year = int(year_m.group(2))
    start = _one_date(_START.search(infos), year)
    end = _one_date(_END.search(infos), year)
    return start, end


def _one_date(match: re.Match | None, year: int) -> date | None:
    if not match:
        return None
    return date(year, _FR_MONTHS[match.group(2).lower()], int(match.group(1)))


_DEMO = re.compile(
    r"(Une\s+démonstration\s+publique[^.]*?au\s+théâtre\s+de\s+la\s+Gare\s+du\s+Midi[^.]*\.)",
    re.IGNORECASE,
)


def _schedule_note(etaussi: str) -> str | None:
    match = _DEMO.search(etaussi)
    return parse.clean(match.group(1)) if match else None


# --- ages: tier list "Élémentaire : 9/10 ans … Supérieur : plus de 16 ans" --------
# Lower bound = the smallest tier age; the top is open (pre-pro/pro adults), so null.
_AGE = re.compile(r"(\d{1,2})\s*/\s*\d{1,2}\s*ans|(\d{1,2})\s*ans", re.IGNORECASE)


def _age_range(presentation: str) -> dict | None:
    ages = [int(g) for m in _AGE.finditer(presentation) for g in m.groups() if g]
    ages = [a for a in ages if 5 <= a <= 25]
    if not ages:
        return None
    return {"min": min(ages)}  # open-topped — adults / professionals are welcome


# --- levels: explicit tiers, beginners explicitly excluded -----------------------


def _levels(presentation: str) -> list[Level]:
    low = presentation.lower()
    levels: list[Level] = []
    if "intermédiaire" in low or "moyen" in low:
        levels.append("intermediate")
    if "avancé" in low:
        levels.append("advanced")
    if "préprofessionnel" in low or "pré-professionnel" in low or "préprofessionnels" in low:
        levels.append("pre-professional")
    if "professionnel" in low:
        levels.append("professional")
    if "amateur" in low or "adulte" in low:
        levels.append("open")
    return levels


# --- genres: classique / pointes / répertoire / ateliers chorégraphiques ----------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classique", "barre à terre", "adage")),
    ("pointe", ("pointe",)),
    ("repertoire", ("répertoire", "variation")),
    # Choreographic ateliers/workshops (Malandain, Kylian, Inger, Forsythe…).
    ("contemporary", ("atelier chorégraphique", "ateliers chorégraphiques", "workshop")),
]


def _genres(presentation: str) -> list[Genre]:
    return parse.match_genres(presentation, _GENRE_KEYWORDS, default=["classical"])


# --- prices: the "Tarifs des cours" table, public ("Pour tous") tier --------------
# Table: Carte | Pour tous | Grandes écoles et Eurocité (1) | Professionnels (2).

_EURO = re.compile(r"(\d[\d\s.,]*)\s*€")


def _prices(infos_html: str) -> list[Price]:
    if not infos_html:
        return []
    tree = HTMLParser(infos_html)
    table = _price_table(tree)
    if table is None:
        return []
    prices: list[Price] = []
    for row in table.css("tr")[1:]:  # skip header row
        cells = [parse.clean(c.text()) for c in row.css("th, td")]
        if len(cells) < 2:
            continue
        card = cells[0]
        public = _EURO.search(cells[1])
        if not card or not public:
            continue
        amount = parse.parse_amount(public.group(1))
        if amount is None:
            continue
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=f"Carte « {card} » (tarif plein)",
                includes=["tuition"],
                notes=_reduced_note(cells),
            )
        )
    return prices


def _price_table(tree: HTMLParser):
    for table in tree.css("table"):
        head = parse.clean(table.text()).lower()
        if "carte" in head and "€" in head:
            return table
    return None


def _reduced_note(cells: list[str]) -> str | None:
    parts = []
    if len(cells) >= 3 and (m := _EURO.search(cells[2])):
        parts.append(f"grandes écoles/eurocités {parse.clean(m.group(0))}")
    if len(cells) >= 4 and (m := _EURO.search(cells[3])):
        parts.append(f"professionnels {parse.clean(m.group(0))}")
    return "Reduced: " + "; ".join(parts) + "." if parts else None


# --- teachers: roster page ---------------------------------------------------------
# Elementor reorders the grid via CSS, so in the DOM every faculty name (an <h4>
# widget) precedes the block of affiliation paragraphs (short text widgets). Both
# lists are in matching document order, so we pair them positionally: name[i] ↔
# affiliation[i]. The trailing names (the pianists) have no affiliation line and
# are skipped — they're accompanists, not dance faculty.

# Section-label text widgets ("Professeurs"/"Ateliers"/"Pianistes") and the intro
# prose blocks aren't affiliations; the labels are short, the prose is long.
_SECTION_LABELS = {"professeurs", "ateliers", "pianistes"}
_AFFILIATION_MAXLEN = 120  # Beechey's two-role line is ~100 chars; prose blocks are 149+.


def _teachers(equipe_html: str) -> list[Teacher]:
    if not equipe_html:
        return []
    tree = HTMLParser(equipe_html)
    for node in tree.css("script, style"):
        node.decompose()

    names = [n for node in tree.css("h4") if (n := parse.clean(node.text())) and len(n) <= 60]
    # Don't dedup — two teachers legitimately share an affiliation (e.g. both
    # from the Opéra national de Paris), so positional pairing must keep repeats.
    affiliations: list[str] = []
    for node in tree.css(".elementor-widget-text-editor"):
        text = parse.clean(node.text())
        if not text or text.lower() in _SECTION_LABELS or len(text) > _AFFILIATION_MAXLEN:
            continue  # empty, a section header, or intro prose — not an affiliation
        affiliations.append(text)

    return [
        Teacher(name=name, affiliations=[Affiliation(organization=affiliation)])
        for name, affiliation in zip(names, affiliations)
    ]
