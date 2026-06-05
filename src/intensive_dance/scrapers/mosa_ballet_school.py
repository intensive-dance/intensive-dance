"""MOSA Ballet School (Liège, BE) — sitemap discovery + Odoo event pages.

API FIRST: MOSA replatformed from Squarespace onto **Odoo** (website-events). The
**sitemap** is unchanged — a clean machine index whose `/event/<slug>-<id>` URLs
keep the same slugs — so discovery stays sitemap-driven. The event pages are now
Odoo, which is a *gift* for parsing: dates come from ISO `<time datetime=…
data-oe-expression="event.date_begin|date_end">` attributes and prices from
schema.org `Offer` microdata (`itemprop="name|price|priceCurrency"`), both
language-independent. We never parse the localized UI chrome.

FETCH: MOSA 403s every non-browser client (its own datacenter-IP block plus a
client fingerprint check) on `/sitemap.xml` and `/event/*`. The fetch-proxy gets
through by auto-escalating the 403 to a stealth Chromium render, so we use the
normal shared `client` (the proxy renders each page). We pin `Accept-Language: en`
(`_LANG`) on every request: Odoo serves a German `og:title` for the handful of
events that have a German translation, and the proxy's default render locale is
`de-DE` — without this the title (a field we *do* read) leaks German into an
English register. The rest of what we read is ISO attributes and microdata.

DISCOVERY: the sitemap lists ~120 events of every kind — intensives, auditions,
galas, recitals, performances, info sessions, symposiums, CPD workshops. We keep
only the short-term *training* offerings (intensive / immersion / signature
course / masterclass / "exploring ballet" taster) and drop the rest. Past editions
are kept (the sitemap lists years of them) so a course's history stays findable.
One `Offering` per kept event, keyed by its event slug.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-05): a provider behind a render
proxy; ISO-attribute dates; multi-`Price` Offerings from Offer microdata with a
`meals` include ("Lunch Included"); `age_range` from the title; a `video`
requirement for pre-selected courses vs `NoneReq` for open-enrolment tasters;
`application.status` open/closed read from the Odoo registration widget.
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
    NoneReq,
    Offering,
    Organization,
    Price,
    PriceInclude,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://www.mosaballetschool.eu"
SITEMAP = f"{BASE}/sitemap.xml"
_EVENT_URL = re.compile(rf"{re.escape(BASE)}/event/[A-Za-z0-9\-]+")

ORG = Organization(name="MOSA Ballet School", slug="mosa-ballet-school", country="BE", city="Liège")

# Pin the proxy's render locale to English (Odoo localizes og:title where a German
# translation exists, and the proxy renders de-DE by default).
_LANG = {"Accept-Language": "en"}

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
        for url in _event_urls(client)
        if (offering := _build_offering(client, url, today)) is not None
    ]
    offerings.sort(key=lambda o: o.id)
    return offerings


def _event_urls(client: httpx.Client) -> list[str]:
    """In-scope `/event/` URLs from the sitemap (API-first discovery).

    The proxy 403s on `/sitemap.xml` and escalates to a Chromium render, which
    wraps the XML in the browser's XML-viewer HTML — so we can't ET-parse it. The
    `/event/` URLs survive verbatim in both forms (raw XML on a direct fetch, the
    rendered wrapper through the proxy), so we regex them out of either.
    """
    resp = client.get(SITEMAP, headers=_LANG)
    resp.raise_for_status()
    return _parse_event_urls(resp.text)


def _parse_event_urls(sitemap: str) -> list[str]:
    """In-scope `/event/` URLs found in the sitemap — raw XML or rendered wrapper."""
    urls = {u for u in _EVENT_URL.findall(sitemap) if _in_scope(u.rsplit("/event/", 1)[-1])}
    return sorted(urls)


def _in_scope(slug: str) -> bool:
    low = slug.lower()
    if any(k in low for k in _DROP):
        return False
    return any(k in low for k in _KEEP)


def _build_offering(client: httpx.Client, url: str, today: date) -> Offering | None:
    resp = client.get(url, headers=_LANG)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    tree = HTMLParser(resp.text)
    slug = url.rsplit("/event/", 1)[-1]

    title = _meta(tree, "og:title") or _text(tree.css_first("h1")) or slug.replace("-", " ").title()
    body = _body_text(tree)

    start, end = _dates(tree)
    anchor = start or end
    if anchor is None:
        return None  # no parseable dates — can't place it in time
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
        prices=_prices(tree),
        application=Application(
            status=_status(tree),
            url=url,
            requirements=[VideoReq(specificity="unspecific", description=_AUDITION_NOTE)]
            if pre_selection
            else [NoneReq()],  # open-enrolment taster: explicitly nothing required
            notes=_AUDITION_NOTE if pre_selection else None,
        ),
    )


# --- parsing helpers ----------------------------------------------------------

# Age band: read from the (clean) title/slug as "12-29"/"8-12"/"12-20 ans"; the
# body is too noisy ("3 to 6 people" rooms), so there we require an "aged" cue.
_AGE = re.compile(r"\b(\d{1,2})\s*(?:[-–]|to)\s*(\d{1,2})\b")
_AGED = re.compile(r"(?:aged?|ages)\s*(\d{1,2})\s*(?:to|[-–])\s*(\d{1,2})", re.IGNORECASE)
# Registration-closed banner, matched in both English and the de-DE render locale.
_CLOSED = re.compile(
    r"registration[s]?\s*(?:are\s*)?closed|anmeldungen\s+geschlossen", re.IGNORECASE
)


def _dates(tree: HTMLParser) -> tuple[date | None, date | None]:
    """Start/end from Odoo's ISO `<time data-oe-expression="event.date_*">` nodes."""
    return _oe_date(tree, "event.date_begin"), _oe_date(tree, "event.date_end")


def _oe_date(tree: HTMLParser, expr: str) -> date | None:
    node = tree.css_first(f'time[data-oe-expression="{expr}"]')
    iso = node.attributes.get("datetime") if node else None
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    return date(int(match[1]), int(match[2]), int(match[3])) if match else None


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


def _status(tree: HTMLParser):
    """Read the Odoo registration widget: purchasable tickets == open, the
    closed banner == closed, otherwise unknown (don't invent one)."""
    if tree.css_first(".o_wevent_ticket_selector") is not None:
        return "open"
    if _CLOSED.search(tree.body.text() if tree.body else ""):
        return "closed"
    return None


def _prices(tree: HTMLParser) -> list[Price]:
    """One `Price` per Odoo ticket, from its schema.org `Offer` microdata.

    Each `.o_wevent_ticket_selector` row carries `itemprop="name"` (the program /
    duration label), `itemprop="price"` (a machine float) and `priceCurrency`.
    "Lunch Included" in the name adds a `meals` include alongside tuition.
    """
    prices: list[Price] = []
    seen: set[tuple[str, float]] = set()
    for row in tree.css(".o_wevent_ticket_selector"):
        price_node = row.css_first('[itemprop="price"]')
        if price_node is None:
            continue
        try:
            amount = float(price_node.text(strip=True))
        except ValueError:
            continue
        label = _text(row.css_first('[itemprop="name"]')) or None
        key = (label or "", amount)
        if key in seen:
            continue
        seen.add(key)
        currency = _text(row.css_first('[itemprop="priceCurrency"]')) or "EUR"
        includes: list[PriceInclude] = ["tuition"]
        if label and "lunch" in label.lower():
            includes.append("meals")
        prices.append(Price(amount=amount, currency=currency, label=label, includes=includes))
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
    return re.sub(r"\s*[—–|]\s*Mosa Ballet School\s*$", "", parse.clean(title), flags=re.IGNORECASE)


def _text(node) -> str:
    return parse.clean(node.text()) if node is not None else ""
