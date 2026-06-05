"""MOSA Ballet School (Liège, BE) — fourth scraper, first European round-1 provider.

API FIRST: MOSA runs on **Squarespace**. There is no JSON API we may use (the
`?format=json` view is disallowed by robots on `/event` paths), but the
**sitemap** is a clean machine-readable index of every event, and each event
lives at a server-rendered `/event/<slug>-<id>` page — so discovery is
sitemap-driven and we parse the (static) event pages, no JS needed.

DISCOVERY: the sitemap lists ~120 events of every kind — intensives, auditions,
galas, recitals, performances, info sessions, symposiums, CPD workshops. We keep
only the actual short-term *training* offerings (intensive / immersion /
signature course / masterclass / "exploring ballet" taster) and drop the rest,
and drop the rest. Past editions are kept (the sitemap lists years of them), so a
course's history stays findable — greyed in the UI from its dates. One `Offering`
per kept event, keyed by its event slug.

WHAT THE PAGES GIVE US (verified live 2026-06):
  - DATES: each event renders "Starts <d Month yyyy> … Ends <d Month yyyy>".
  - AGES: in the title / excerpt ("(12-29)", "age 8-12", "15-20").
  - PRICES in EUR, parsed from the body (course fee, plus accommodation/audition
    fees kept with their labels).
  - REQUIREMENTS: MOSA pre-selects dancers by audition ("with pre-selection") —
    online or in person — so pre-selected courses get a `video` requirement;
    open-enrolment tasters get none.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    Genre,
    Location,
    NoneReq,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://www.mosaballetschool.eu"
SITEMAP = f"{BASE}/sitemap.xml"
_SM_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

ORG = Organization(name="MOSA Ballet School", slug="mosa-ballet-school", country="BE", city="Liège")

# An event is in scope when its slug names a training format …
_KEEP = (
    "intensive",
    "signature",
    "immersion",
    "immersive",
    "exploring-ballet",
    "discovering-mosa",
    "masterclass",
)
# … and is not one of MOSA's many non-training event types.
_DROP = (
    "audition",
    "admission-test",
    "gala",
    "recital",
    "performance",
    "information-session",
    "online-information",
    "info-session",
    "symposium",
    "conference",
    "open-doors",
    "visit-of",
    "christmas",
    "afterwork",
    "annual",
    "workshop",
    "parkinson",
    "ageing",
    "aging",
    "cancer",
    "inclusive",
    "adapted",
    "cyclo",
    "formation-en",
    "moovement",
    "dance-with-mosa-teachers",
    "let-s-dance-for-life",
    "la-procure",
    "dance-for-pd",
    "health-and",
    "secundary-school",
)
_AUDITION_NOTE = (
    "Admission is by pre-selection: MOSA auditions dancers in person or online (by video) "
    "before a place is confirmed."
)


def scrape(client: httpx.Client) -> list[Offering]:
    today = date.today()
    offerings = [
        offering
        for url in _event_urls(client, today)
        if (offering := _build_offering(client, url, today)) is not None
    ]
    offerings.sort(key=lambda o: o.id)
    return offerings


def _event_urls(client: httpx.Client, today: date) -> list[str]:
    """Live, in-scope `/event/` URLs from the sitemap (API-first discovery)."""
    resp = client.get(SITEMAP)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    urls = []
    for node in root.findall(f"{_SM_NS}url"):
        loc = node.findtext(f"{_SM_NS}loc") or ""
        slug = loc.rsplit("/event/", 1)[-1]
        if "/event/" in loc and _in_scope(slug):
            urls.append(loc)
    return sorted(set(urls))


def _in_scope(slug: str) -> bool:
    low = slug.lower()
    if any(k in low for k in _DROP):
        return False
    return any(k in low for k in _KEEP)


def _build_offering(client: httpx.Client, url: str, today: date) -> Offering | None:
    resp = client.get(url)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    tree = HTMLParser(resp.text)
    slug = url.rsplit("/event/", 1)[-1]

    title = _meta(tree, "og:title") or _text(tree.css_first("h1")) or slug.replace("-", " ").title()
    body = _body_text(tree)

    start, end = _dates(body)
    anchor = start or end
    if anchor is None:
        return None  # no parseable dates — can't place it in time (likely a stale one-off)
    season = str(anchor.year)

    pre_selection = "pre-selection" in body.lower() or "preselection" in body.lower()
    return Offering(
        id=f"mosa-ballet-school/{slug}",
        source=Source(provider="mosa-ballet-school", url=url, scrapedAt=now_utc()),
        title=_clean_title(title),
        genres=_genres(f"{title} {body}"),
        ageRange=_age_range(f"{title} {slug}", body),
        organization=ORG,
        location=Location(city="Liège", country="BE"),
        schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Brussels"),
        prices=_prices(body),
        application=Application(
            status=_status(body),
            url=url,
            requirements=[VideoReq(specificity="unspecific", description=_AUDITION_NOTE)]
            if pre_selection
            else [NoneReq()],  # open-enrolment taster: explicitly nothing required
            notes=_AUDITION_NOTE if pre_selection else None,
        ),
    )


# --- parsing helpers ----------------------------------------------------------

_STARTS = re.compile(r"Starts\s+(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})", re.IGNORECASE)
_ENDS = re.compile(r"Ends\s+(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})", re.IGNORECASE)
# Age band: read from the (clean) title/slug as "12-29"/"8-12"/"12-20 ans"; the
# body is too noisy ("3 to 6 people" rooms), so there we require an "aged" cue.
_AGE = re.compile(r"\b(\d{1,2})\s*(?:[-–]|to)\s*(\d{1,2})\b")
_AGED = re.compile(r"(?:aged?|ages)\s*(\d{1,2})\s*(?:to|[-–])\s*(\d{1,2})", re.IGNORECASE)
_MONEY = re.compile(r"(?:€\s*(\d[\d.,]*)|(\d[\d.,]*)\s*(?:€|eur|euros?))", re.IGNORECASE)
# A course-tuition cue near a price ("6 days", "2 weeks") — distinguishes the
# course fee from accommodation/audition/ticket-widget amounts.
_DURATION = re.compile(r"\b\d+\s*(?:days?|weeks?)\b", re.IGNORECASE)


def _one(match: re.Match | None) -> date | None:
    if not match:
        return None
    day, month, year = match.groups()
    return date(int(year), parse.MONTHS[month.lower()], int(day))


def _dates(text: str) -> tuple[date | None, date | None]:
    return _one(_STARTS.search(text)), _one(_ENDS.search(text))


def _age_range(primary: str, body: str = "") -> dict | None:
    bounds = [(int(a), int(b)) for a, b in _AGE.findall(primary) if 3 <= int(a) <= int(b) <= 30]
    if not bounds:  # fall back to an explicit "aged X to Y" in the body
        bounds = [(int(a), int(b)) for a, b in _AGED.findall(body) if 3 <= int(a) <= int(b) <= 30]
    if not bounds:
        return None
    return {"min": min(a for a, _ in bounds), "max": max(b for _, b in bounds)}


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet", "classical", "pointe", "repertoire")),
    ("contemporary", ("contemporary", "immersion", "other dances")),
    ("character", ("character",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _status(text: str):
    low = text.lower()
    if re.search(r"registrations?\s+closed|registration\s+closed", low):
        return "closed"
    if re.search(r"registrations?\s+open|register now|registration.*open", low):
        return "open"
    return None


def _prices(text: str) -> list[Price]:
    """Course-tuition fees in EUR.

    MOSA's Squarespace pages mix the course fee with accommodation, audition and
    a "Tickets From … to …" widget, so we keep only amounts sitting next to a
    duration cue ("6 days", "2 weeks") / "lunch" and *not* next to an
    accommodation/audition word, deduped by amount. Other fee formats are skipped
    rather than risk mislabelling.
    """
    prices: list[Price] = []
    seen: set[float] = set()
    for match in _MONEY.finditer(text):
        amount = parse.parse_amount(match.group(1) or match.group(2))
        if amount is None or amount < 50 or amount in seen:
            continue
        context = text[max(0, match.start() - 55) : match.start()].lower()
        duration = _DURATION.search(context)
        # MOSA states course fees as "<N> days (<n> classes per day) with lunch";
        # requiring both the duration and "lunch" cleanly excludes accommodation,
        # audition and the "Tickets From … to …" widget amounts.
        if not (duration and "lunch" in context):
            continue
        seen.add(amount)
        label = f"{duration.group(0)} with lunch"
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=parse.clean(label).capitalize(),
                includes=["tuition"],
            )
        )
    return prices


# --- small DOM helpers --------------------------------------------------------


def _meta(tree: HTMLParser, prop: str) -> str | None:
    node = tree.css_first(f'meta[property="{prop}"]') or tree.css_first(f'meta[name="{prop}"]')
    return parse.clean(node.attributes.get("content") or "") or None if node else None


def _body_text(tree: HTMLParser) -> str:
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return re.sub(r"\s+", " ", tree.body.text(separator=" ")) if tree.body else ""


def _clean_title(title: str) -> str:
    # Squarespace og:title often appends " — Mosa Ballet School"
    return re.sub(r"\s*[—–|]\s*Mosa Ballet School\s*$", "", parse.clean(title), flags=re.IGNORECASE)


def _text(node) -> str:
    return parse.clean(node.text()) if node is not None else ""
