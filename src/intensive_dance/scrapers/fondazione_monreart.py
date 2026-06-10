"""Fondazione Monreart (IT) — its International Schools across Europe.

API FIRST: WordPress REST. Monreart runs on WordPress and exposes its intensives
as an `eventi` custom post type at `/wp-json/wp/v2/eventi` — we use that for
discovery (slug, link, title). The body isn't in the API (Elementor builds it on
the page), so per-event detail is parsed from each event page.

LANGUAGE NOTE: the `/en/` pages flip between English and Italian depending on the
Varnish cache, so the scrape is **language-agnostic** — dates (English *and*
Italian month names), ages, prices (numeric €) and genres normalise to stable
values, and the title comes from the REST API. Any free text we emit (lifecycle
notes) is canonical English, never the page's wording, so the committed data is
deterministic no matter which language renders.

LIFECYCLE (IDR-24): one school — Budapest — carries a "postponed to 2027" banner;
we keep it with `lifecycle="postponed"` (showing the new date) rather than
dropping it. Past editions (e.g. the December 2025 Winter School) are kept too;
"past" is derived from dates, not stored. The motivating case for IDR-24.

AGE RANGE: the Winter School (Verona) lists Junior 11-14 AND Senior "da 15 anni
in su" (open-ended); the combined ageRange is {min:11} (null max). The `_AGE_OPEN`
regex catches the open "da N anni in su" / "from N years and older" forms; when any
open-ended band is present the max is left null rather than capping at 14.

REQUIREMENTS + DEADLINE (verified live 2026-06-07):
  - Winter School Verona: "no photographic selection required" → [NoneReq].
  - Volta Mantovana / Cyprus / Budapest: "Submit application … attaching photos"
    → [PhotosReq(freeform)].
  - Volta Mantovana deadline: "open until July 31, 2026" → deadline=2026-07-31.
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
    Lifecycle,
    Location,
    NoneReq,
    Offering,
    Organization,
    PhotosReq,
    Price,
    Requirement,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.monreart.com"
EVENTI_API = f"{BASE}/wp-json/wp/v2/eventi?per_page=50&_fields=slug,link,title"

ORG = Organization(
    name="Fondazione Monreart", slug="fondazione-monreart", country="IT", city="Volta Mantovana"
)

# Italian month names on top of the shared English map, so dates parse whichever
# language the page renders in.
_MONTHS = {
    **parse.MONTHS,
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
_MONTHALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

# Event slug → (city, country). The schools sit at a handful of fixed venues and
# the slug is the one language-invariant identifier (the page body flips EN/IT and
# carries the foundation's Volta Mantovana HQ address in every footer), so we map
# the known slugs rather than scrape the place text. A new, unmapped event still
# yields an Offering — just without a placed location (a maintenance signal).
_PLACE: dict[str, tuple[str | None, str]] = {
    "international-summer-school-cyprus": ("Limassol", "CY"),
    "international-summer-school-budapest": ("Budapest", "HU"),
    "international-spring-school-italia": ("Verona", "IT"),
    "international-winter-school-verona": ("Verona", "IT"),
    "international-summer-school-volta-mantovana": ("Volta Mantovana", "IT"),
}


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(EVENTI_API)
    resp.raise_for_status()
    offerings = []
    for record in resp.json():
        offering = _build_offering(client, record)
        if offering is not None:
            offerings.append(offering)
    offerings.sort(key=lambda o: o.id)
    return offerings


def _build_offering(client: httpx.Client, record: dict) -> Offering | None:
    slug = record["slug"]
    link = record["link"]
    title = parse.clean(re.sub(r"<[^>]+>", "", record["title"]["rendered"])).title()

    text = _page_text(client, link)
    start, end = _date_range(text)
    anchor = end or start
    if anchor is None:
        return None  # no parseable dates
    season = str(anchor.year)

    lifecycle, note = _lifecycle(text)
    city, country = _PLACE.get(slug, (None, None))

    return Offering(
        id=f"fondazione-monreart/{slug}-{season}",
        source=Source(provider="fondazione-monreart", url=link, scrapedAt=now_utc()),
        title=f"{title} {season}",
        genres=_genres(text),
        lifecycle=lifecycle,
        lifecycleNote=note,
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(city=city, country=country),
        schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Rome"),
        prices=_prices(text),
        application=Application(
            deadline=_deadline(text, int(season)),
            url=link,
            requirements=_requirements(text),
        ),
    )


def _page_text(client: httpx.Client, url: str) -> str:
    tree = HTMLParser(client.get(url).text)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


# --- dates: "20 - 25 July 2026" / "27 - 31 Dicembre 2025" (single month) -------

_RANGE = re.compile(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})", re.IGNORECASE)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    d1, d2, month, year = m.groups()
    num = _MONTHS[month.lower()]
    return date(int(year), num, int(d1)), date(int(year), num, int(d2))


# --- lifecycle: postponement / cancellation banners (not refund boilerplate) ---

_POSTPONED = re.compile(r"(?:postpon\w*|posticipat\w*|rimandat\w*)\D{0,12}(\d{4})", re.IGNORECASE)
_CANCELLED = re.compile(
    r"(?:event has been cancel\w*|evento\s+(?:è\s+stato\s+)?annullat\w*|corso\s+annullat\w*)",
    re.IGNORECASE,
)


def _lifecycle(text: str) -> tuple[Lifecycle, str | None]:
    if _CANCELLED.search(text):
        return "cancelled", "This edition has been cancelled."
    m = _POSTPONED.search(text)
    if m:
        return "postponed", f"Postponed to {m.group(1)}."
    return "scheduled", None


# --- ages (bilingual, so EN and IT renders give the same numbers) -------------
# Cue form: "aged between 9 and 19", "età compresa tra i 9 e i 19 anni".
_AGE_CUE = re.compile(
    r"(?:\bage\w*\b|\betà\b|\btra\b|\bbetween\b)[^\d]{0,20}(\d{1,2})[^\d]{1,6}(\d{1,2})",
    re.IGNORECASE,
)
# Bare form with an explicit unit: "Junior: 11-14 anni", "15-19 years".
_AGE_BARE = re.compile(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:anni|years)", re.IGNORECASE)
# Open-ended lower-bound form: "da 15 anni in su", "15 years and older",
# "from 15 years", "15 years old and older". When this matches, the upper bound
# is null (open-ended senior band).
_AGE_OPEN = re.compile(
    r"(?:da\s+)?(\d{1,2})\s+(?:anni\s+in\s+su|years?\s+(?:and\s+)?older|and\s+older)",
    re.IGNORECASE,
)


def _age_range(text: str) -> dict | None:
    pairs = [
        (int(a), int(b))
        for a, b in _AGE_CUE.findall(text) + _AGE_BARE.findall(text)
        if 5 <= int(a) <= int(b) <= 30
    ]
    open_mins = [int(m.group(1)) for m in _AGE_OPEN.finditer(text) if 5 <= int(m.group(1)) <= 30]
    if not pairs and not open_mins:
        return None
    all_mins = [a for a, _ in pairs] + open_mins
    # Upper bound is null when any open-ended band is present (no finite max can
    # be inferred from "da N anni in su").
    if open_mins:
        return {"min": min(all_mins)}
    return {"min": min(all_mins), "max": max(b for _, b in pairs)}


# --- prices: the headline cost (€/euro, either side), near a cost cue ----------

_PRICE = re.compile(
    r"(?:cost|costo|total[ei]?)\D{0,30}?(?:€\s*)?(\d[\d.,]*)\s*(?:€|euro)?", re.IGNORECASE
)


def _prices(text: str) -> list[Price]:
    m = _PRICE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None or amount < 50:
        return []
    return [Price(amount=amount, currency="EUR", label="Total cost", includes=["tuition"])]


# --- application deadline & requirements -------------------------------------

# "Le iscrizioni sono aperte fino al 31 luglio 2026" (IT: day month year)
# "Registration is open until July 31, 2026." (EN: month day year)
# Two patterns handle both word orders; both are language-agnostic.
_DEADLINE_DMY = re.compile(
    r"(?:fino al|entro il)\s+(\d{1,2})\s+(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
_DEADLINE_MDY = re.compile(
    r"(?:open until|until)\s+(" + _MONTHALT + r")\s+(\d{1,2}),?\s*(\d{4})",
    re.IGNORECASE,
)


def _deadline(text: str, season: int) -> date | None:  # noqa: ARG001 — season reserved
    m = _DEADLINE_DMY.search(text)
    if m:
        day, month, year = m.groups()
        return date(int(year), _MONTHS[month.lower()], int(day))
    m = _DEADLINE_MDY.search(text)
    if m:
        month, day, year = m.groups()
        return date(int(year), _MONTHS[month.lower()], int(day))
    return None


# "non è richiesta selezione fotografica / no photographic selection required" →
# NoneReq. "Submit application via online form attaching photos" → PhotosReq freeform.
_NO_SELECTION = re.compile(
    r"no photographic selection required|non.*?richiesta\s+selezi\w*\s+fotografic",
    re.IGNORECASE,
)
_PHOTOS_REQUIRED = re.compile(r"attaching photos|allegando\s+(?:le\s+)?foto", re.IGNORECASE)


def _requirements(text: str) -> list[Requirement]:
    if _NO_SELECTION.search(text):
        return [NoneReq()]
    if _PHOTOS_REQUIRED.search(text):
        return [PhotosReq(specificity="freeform", notes="Application form with photos.")]
    return []


# --- genres -------------------------------------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet", "classical", "classic", "classica", "classico")),
    ("contemporary", ("contemporary", "contemporane")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])
