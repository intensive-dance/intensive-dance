"""Orsolina28 — contemporary-repertoire intensive season, Moncalvo (AT), Italy.

API FIRST
The site (https://orsolina28.it) is a custom CMS — not WordPress, not Wix,
not Next.js. GET /wp-json/ → 404 (after redirect). There is no
``__NEXT_DATA__`` blob, no iCal feed, and the only ``application/ld+json``
blocks are a ``BreadcrumbList`` and an ``Organization`` stub — no ``Event``
entries. The program content is fully server-rendered static HTML, so a plain
``httpx`` fetch with our UA works without the proxy.

DISCOVERY
The listing page at ``/en/programs/professional-training/intensive/`` links
one card per edition. Each edition page carries:
  - header date  (``div.PageHeaderEventSplit-date``)
  - artist roster (``ul.PeopleList-list`` → ``li.PeopleList-item``)
  - three-tab Tabs panel (.Tabs-content[data-index=1/2/3])
      tab 1 = APPLICATION (or COST for GagaLab): deadlines + fee breakdown
      tab 2 = PARTICIPANTS: age/level description
      tab 3 = ACCOMMODATION: on-campus glamping detail (not scraped)

One Offering per edition — dates, fees, artists, apply URL differ.
Edition slugs discovered from anchor links on the listing page.

What varies across editions
- Dates (weekly, Jun 14 – Aug 16, 2026)
- Teachers and their PeopleList-subtitle role (Teaching Artist / Program Director)
- Apply URL: ``https://booking.orsolina28.it/en/course/<id>`` for most editions;
  GagaLab 2026 links to gagapeople.com
- Price structure: standard editions → € 1.500 tuition (full room & board
  included); GagaLab → ILS tuition (paid to Gaga) + € 990 room-and-board
- Submission deadline: first dated bullet in APPLICATION tab

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08)
- MULTI-PAGE ITERATION: one index fetch → per-edition fetches (9 editions 2026)
- GENRE matching against "The program" prose: all editions are contemporary;
  some add "repertoire" when the prose explicitly names repertoire study.
- TEACHERS extracted from ``.PeopleList-title`` + ``.PeopleList-subtitle``
  (role in THIS intensive only — no affiliation data published per page).
- PRICES in two currencies: EUR standard; ILS + EUR for GagaLab.
  ``parse.parse_amount`` handles European dot-thousands (€ 1.500 → 1500.0).
- APPLICATION deadline from tab-1 first bullet; ``VideoReq`` unspecific because
  the source only says "apply" without specifying a brief.
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser, Node

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    Price,
    PriceInclude,
    Schedule,
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

BASE = "https://www.orsolina28.it"
INDEX_URL = f"{BASE}/en/programs/professional-training/intensive/"

ORG = Organization(name="Orsolina28", slug="orsolina28", country="IT", city="Moncalvo")
LOCATION = Location(venue="Orsolina28", city="Moncalvo", country="IT")

# Application requirement: site describes an audition/selection process but
# gives no specific video brief — VideoReq/unspecific is the most faithful encoding.
_VIDEO_NOTE = (
    "Apply via the online booking portal. "
    "Acceptance is subject to artistic review — complete the online application form."
)

# Slugs to skip when walking the index page links (not editions).
_SKIP_SLUGS = {"archive"}

# Edition links pattern: /en/programs/professional-training/intensive/<slug>/
_EDITION_PATH_RE = re.compile(
    r"^/en/programs/professional-training/intensive/([a-z0-9][a-z0-9-]*)/?$"
)

# -------------------------------------------------------------------------
# Date parsing
# -------------------------------------------------------------------------
# Header reads "June 14 – June 21, 2026" or "July 5 – July 12, 2026".
# Year always appears on the end-date side.

_MON_DAY = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})(?:,?\s*(20\d\d))?",
    re.IGNORECASE,
)


def _parse_dates(text: str) -> tuple[date | None, date | None]:
    """Parse 'Month D – Month D, YYYY' header into (start, end) ISO dates."""
    tokens = [
        (parse.MONTHS[m.lower()], int(d), int(y) if y else None)
        for m, d, y in _MON_DAY.findall(text)
    ]
    if not tokens:
        return None, None
    last_year = next((y for _, _, y in reversed(tokens) if y), None)
    if last_year is None:
        return None, None
    points = [date(y if y else last_year, month, day) for month, day, y in tokens]
    return (min(points), max(points)) if len(points) >= 2 else (None, None)


# -------------------------------------------------------------------------
# Deadline parsing
# -------------------------------------------------------------------------
# Tab-1 first bullet: "February 4, 2026 at 6:00 P.M. (CET): Deadline for …"

_DEADLINE_RE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2}),\s+(20\d\d)",
    re.IGNORECASE,
)
# Marker that must appear after the date in the same bullet to be a submission deadline.
_SUBMISSION_MARKER = re.compile(r"deadline for the submission", re.IGNORECASE)


def _parse_deadline(tab1_text: str) -> date | None:
    """Application submission deadline from tab-1 text.

    Returns the date only when it appears in the same bullet as 'Deadline for
    the submission of an application'. GagaLab has no such bullet (its first
    dates are cancellation policy dates), so it correctly returns None.
    """
    for m in _DEADLINE_RE.finditer(tab1_text):
        # Check the text from the date to the next semicolon / newline
        tail = tab1_text[m.end() : m.end() + 120]
        if _SUBMISSION_MARKER.search(tail):
            return date(int(m.group(3)), parse.MONTHS[m.group(1).lower()], int(m.group(2)))
    return None


# -------------------------------------------------------------------------
# Price parsing
# -------------------------------------------------------------------------
# Standard tab-1:
#   "Tuition: € 1.500"
#   "Early Bird, by March 17, 2026: € 1.400"
#   "Application Fee: €40 (non-refundable)"
#
# GagaLab tab-1 (labelled COST):
#   "ILS 150 (non-refundable), …"   — application fee to Gaga
#   "ILS 2340" / "ILS 2600"         — tuition to Gaga
#   "€ 990"                          — room & board to Orsolina28
#
# parse.parse_amount handles European dot-thousands: "1.500" → 1500.0

_MONEY_RE = re.compile(
    r"(?:(?P<sym1>€|ILS)\s*(?P<amt1>\d[\d.,]*))|(?:(?P<amt2>\d[\d.,]*)\s*(?P<sym2>€|ILS))",
    re.IGNORECASE,
)
_CURRENCY_MAP = {"€": "EUR", "ils": "ILS"}


def _tab_prices(tab1_node: Node) -> list[Price]:
    """Extract prices from the APPLICATION/COST tab node.

    Evaluates each leaf ``<li>`` and each ``<p>`` individually so the label
    classification operates on one fee line at a time. Standard editions put
    fees in nested ``<li>`` (parent li wraps "Tuition" + nested "Early Bird"
    child), so we collect only *leaf* ``<li>`` elements (those with no child
    ``<li>``), which gives one clean line per tier. GagaLab puts its ILS fees
    in ``<p>`` tags, so we cover those too. Lines without a money token are
    silently skipped.
    """
    prices: list[Price] = []
    seen_amounts: set[tuple[float, str]] = set()

    def _extract(line: str) -> None:
        for m in _MONEY_RE.finditer(line):
            sym = (m.group("sym1") or m.group("sym2") or "").lower()
            raw_amt = m.group("amt1") or m.group("amt2") or ""
            amount = parse.parse_amount(raw_amt)
            if amount is None:
                continue
            currency = _CURRENCY_MAP.get(sym, "EUR")
            key = (amount, currency)
            if key in seen_amounts:
                continue
            seen_amounts.add(key)
            label, includes = _price_label(line, currency)
            prices.append(
                Price(amount=amount, currency=currency, label=label, includes=includes, notes=line)
            )

    # Walk all <li> nodes, but for those that contain a nested <ul>, extract
    # only the direct (pre-nested-ul) text — the collapsed full text would
    # double-count the nested child's amounts. Leaf <li> nodes are used as-is.
    for li in tab1_node.css("li"):
        nested_ul = li.css_first("ul")
        if nested_ul:
            # Strip the nested <ul> block to get this li's own text only.
            li_html = li.html or ""
            ul_html = nested_ul.html or ""
            line = parse.clean(HTMLParser(li_html.replace(ul_html, "")).text())
        else:
            line = parse.clean(li.text())
        _extract(line)

    # <p> nodes cover GagaLab's ILS fee lines and the room-and-board € line,
    # which are in <p> rather than <li>.
    for p in tab1_node.css("p"):
        _extract(parse.clean(p.text()))

    return prices


def _price_label(line: str, currency: str) -> tuple[str, list[PriceInclude]]:
    """Infer a label and the `includes` enum list from the fee line."""
    low = line.lower()
    if "application fee" in low:
        return "Application fee", []
    if "early bird" in low:
        return "Early Bird tuition", ["tuition", "accommodation", "meals"]
    if "room" in low or "board" in low:
        return "Room & Board", ["accommodation", "meals"]
    if currency == "ILS":
        # GagaLab tuition lines are ILS and paid to Gaga (not Orsolina28)
        return "Tuition", ["tuition"]
    # Default: "Tuition: € 1.500" — full board included per the listing
    return "Tuition (full board)", ["tuition", "accommodation", "meals"]


# -------------------------------------------------------------------------
# Teachers
# -------------------------------------------------------------------------


def _teachers(tree: HTMLParser) -> list[Teacher]:
    seen: set[str] = set()
    teachers: list[Teacher] = []
    for item in tree.css("li.PeopleList-item"):
        name_node = item.css_first("h3.PeopleList-title")
        role_node = item.css_first("p.PeopleList-subtitle")
        name = parse.clean(name_node.text()) if name_node else ""
        role = parse.clean(role_node.text()) if role_node else None
        if not name or name in seen:
            continue
        seen.add(name)
        teachers.append(Teacher(name=name, role=role))
    return teachers


# -------------------------------------------------------------------------
# Genres
# -------------------------------------------------------------------------
# Matched against "The program" prose only — teacher bios sometimes name
# choreographers whose style is a genre label (Béjart, Inger) without the
# program teaching that style explicitly. Anchoring to the program section
# prevents bio leakage. All editions fall back to contemporary (the season's
# stated focus), so we never emit an empty genres list.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("contemporary", ("contemporary", "gaga", "modern dance", "physical research")),
    ("neoclassical", ("neoclassical",)),
    ("classical", ("classical ballet", "ballet class")),
    ("repertoire", ("repertoire", "repertory")),
]


def _genres(program_text: str) -> list[Genre]:
    """Genres for one edition.

    All Orsolina28 intensive editions are contemporary dance — the entire season
    is built around contemporary choreographers (Kylián, Goecke, Bausch, Béjart,
    Inger, Akram Khan, Walerski). "Contemporary" is always the base genre.
    "Repertoire" is added when the program prose mentions repertoire study, which
    most editions do (but not all name the word). Other genres (classical, etc.)
    are added only when explicitly stated in the program text.
    """
    genres: list[Genre] = parse.match_genres(program_text, _GENRE_KEYWORDS)
    # Ensure contemporary is always present (it's the season's defined focus).
    if "contemporary" not in genres:
        genres = ["contemporary", *[g for g in genres if g != "contemporary"]]
    return genres


# -------------------------------------------------------------------------
# Levels / age range
# -------------------------------------------------------------------------
# Every edition states "students aged 18 and over … professional environment".
# All editions are pre-professional/open (no upper age bound stated).


def _levels(_tab2_text: str) -> list[Level]:
    return ["pre-professional", "open"]


# -------------------------------------------------------------------------
# Index page — collect edition slugs
# -------------------------------------------------------------------------


def _edition_slugs(index_html: str) -> list[str]:
    """Extract edition path slugs from the listing page (sorted, deduplicated)."""
    tree = HTMLParser(index_html)
    found: list[str] = []
    for a in tree.css("a"):
        href = a.attributes.get("href") or ""
        m = _EDITION_PATH_RE.match(href)
        if m:
            slug = m.group(1)
            if slug not in _SKIP_SLUGS and slug not in found:
                found.append(slug)
    return sorted(found)


# -------------------------------------------------------------------------
# Per-page offering builder (pure; tested directly)
# -------------------------------------------------------------------------


def _build_offering(page_html: str, page_url: str, edition_slug: str) -> Offering | None:
    """Parse one edition page and return its Offering, or None if undated."""
    tree = HTMLParser(page_html)

    # ---- dates ----
    date_node = tree.css_first(".PageHeaderEventSplit-date, .Date")
    date_text = parse.clean(date_node.text()) if date_node else ""
    start, end = _parse_dates(date_text)
    if start is None or end is None:
        return None

    season = str(start.year)

    # ---- title ----
    h1 = tree.css_first("h1")
    h2_sub = tree.css_first("h2.PageHeaderEventSplit-subtitle")
    h1_text = parse.clean(h1.text()) if h1 else ""
    h2_text = parse.clean(h2_sub.text()) if h2_sub else ""
    title = f"{h1_text} — {h2_text}" if h2_text else h1_text

    # ---- tabs ----
    tabs = tree.css(".Tabs-content")
    tab1_node: Node | None = tabs[0] if tabs else None
    tab1_text = parse.clean(tab1_node.text()) if tab1_node else ""
    tab2_text = parse.clean(tabs[1].text()) if len(tabs) > 1 else ""

    # ---- apply URL ----
    # Prefer booking.orsolina28.it; GagaLab links to gagapeople.com
    apply_url: str | None = None
    for a in tree.css("a"):
        href = a.attributes.get("href") or ""
        link_text = parse.clean(a.text()).lower()
        if link_text == "apply":
            raw = href
            apply_url = raw if raw.startswith("http") else urljoin(BASE, raw)
            break

    # ---- deadline ----
    deadline = _parse_deadline(tab1_text)

    # ---- prices ----
    prices = _tab_prices(tab1_node) if tab1_node is not None else []

    # ---- genres (from "The program" prose) ----
    body = tree.css_first("body")
    body_text = parse.clean(body.text()) if body else ""
    prog_idx = body_text.find("The program")
    prog_text = body_text[prog_idx : prog_idx + 600] if prog_idx >= 0 else body_text[:600]

    return Offering(
        id=f"orsolina28/{edition_slug}",
        source=Source(provider="orsolina28", url=page_url, scrapedAt=now_utc()),
        title=title,
        genres=_genres(prog_text),
        lifecycle="scheduled",
        level=_levels(tab2_text),
        ageRange={"min": 18, "max": None},
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Rome",
            notes=date_text or None,
        ),
        teachers=_teachers(tree),
        prices=prices,
        application=Application(
            deadline=deadline,
            url=apply_url,
            requirements=[VideoReq(specificity="unspecific", description=_VIDEO_NOTE)],
        ),
    )


# -------------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------------


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(INDEX_URL)
    resp.raise_for_status()
    slugs = _edition_slugs(resp.text)

    offerings: list[Offering] = []
    for slug in slugs:
        url = f"{BASE}/en/programs/professional-training/intensive/{slug}/"
        page_resp = client.get(url)
        if page_resp.status_code == 404:
            continue
        page_resp.raise_for_status()
        offering = _build_offering(page_resp.text, url, slug)
        if offering is not None:
            offerings.append(offering)

    offerings.sort(key=lambda o: (o.schedule.start or date.min, o.id))
    return offerings
