"""IntoDance (Athens, GR) — summer intensive with international guest faculty.

API FIRST: IntoDance runs **WordPress** (`/wp-json/` is 200) with an **Elementor**
front end. There is no custom post type for events — the public programme lives on
one **Events** page (`/wp-json/wp/v2/pages?slug=events`) whose `content.rendered`
is fully populated Elementor markup (not the empty-body trap), so we read the API,
no HTML scrape of the live page and no proxy (a plain fetch is unblocked). Genre,
ages and prices aren't enumerated on the page (the card only says "Train with
INTERNATIONAL BALLET STARS"), so we stay faithful and emit only what's stated.

DISCOVERY: each event is a self-contained Elementor section holding exactly one
`hfe-infocard` widget (the title), a sibling date `heading`, and `text-editor`
widgets (location). We walk those sections and emit **one Offering per dated
edition** of the Athens intensive (keyed by its season year). We drop sections that
aren't a short-term student intensive in scope — the page also carries an
*audition* for a vocational academy (ACCADEMIA UCRAINA DI BALLETTO MILANO) held in
Tokyo, which is neither an intensive nor in Athens.

IntoDance is co-founded by Giordano Bozza (Principal, Thüringer Staatsballett) and
Ruika Yokoyama, and is known for a marquee international guest roster — but the
Events card for a given edition names no per-edition faculty (it links to Instagram
for the lineup), so we don't launder the site-wide collaborating-artist roster onto
a specific edition. Teachers stay empty until a future edition lists its own.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08): a WordPress/Elementor page
whose events are `hfe-infocard` sections; a day-month range with a trailing year
("29 June - 3 july 2026") read with a shared-month regex; an Offering kept
deliberately sparse (no ages/prices/teachers stated → those fields stay empty,
`requirements=[]` = not stated) rather than invented.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser, Node

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://into-dance.com"
EVENTS_SLUG = "events"

ORG = Organization(name="IntoDance", slug="intodance-athens", country="GR", city="Athens")

_INFOCARD = '[data-widget_type="hfe-infocard.default"]'
_HEADING = '[data-widget_type="heading.default"]'
_TEXT = '[data-widget_type="text-editor.default"]'

# An event section is in scope only when it's the Athens summer intensive. The page
# also lists an academy *audition* held in Tokyo — not a student intensive, not in
# Athens — which these cues exclude.
_KEEP = ("intensive",)
_DROP = ("audition", "オーディション")


def scrape(client: httpx.Client) -> list[Offering]:
    page = wp.fetch_page(client, EVENTS_SLUG, base=BASE)
    if page is None:
        return []
    return _build_offerings(page["content"]["rendered"], date.today())


def _build_offerings(html: str, today: date) -> list[Offering]:
    tree = HTMLParser(html)
    offerings: list[Offering] = []
    for section in _event_sections(tree):
        offering = _build_offering(section)
        if offering is not None:
            offerings.append(offering)
    offerings.sort(key=lambda o: o.id)
    return offerings


def _event_sections(tree: HTMLParser) -> list[Node]:
    """The top-level container holding each single event (one info-card apiece).

    Walking up from each info-card to the nearest ancestor that wraps exactly one
    card keeps every event's date/location/contact grouped, however many wrapper
    containers Elementor nests.
    """
    sections: list[Node] = []
    seen: set[int] = set()
    for card in tree.css(_INFOCARD):
        node: Node | None = card
        while node is not None:
            parent = node.parent
            if parent is None or len(parent.css(_INFOCARD)) != 1:
                break
            node = parent
        if node is not None and id(node) not in seen:
            seen.add(id(node))
            sections.append(node)
    return sections


def _build_offering(section: Node) -> Offering | None:
    card_text = _text(section.css_first(_INFOCARD))
    dates_text = _date_heading(section)
    if not _in_scope(card_text):
        return None

    start, end = _dates(dates_text)
    anchor = start or end
    season = str(anchor.year) if anchor else "unknown"

    title = _title(card_text)

    return Offering(
        id=f"intodance-athens/summer-intensive-{season}",
        source=Source(provider="intodance-athens", url=f"{BASE}/events/", scrapedAt=now_utc()),
        title=f"{title} {season}".strip() if season != "unknown" else title,
        genres=_genres(card_text),
        organization=ORG,
        location=_location(section),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Athens",
            notes=dates_text or None,
        ),
        application=Application(url=f"{BASE}/events/", requirements=[]),
    )


# --- section text helpers -----------------------------------------------------


def _in_scope(card_text: str) -> bool:
    low = card_text.lower()
    if any(k in low for k in _DROP):
        return False
    return any(k in low for k in _KEEP)


def _title(card_text: str) -> str:
    """The info-card's first line (its title), dropping the tagline that follows."""
    first = card_text.split("\n", 1)[0]
    # The card can collapse title + tagline onto one line; cut the known tagline.
    return parse.clean(re.split(r"train with", first, flags=re.IGNORECASE)[0]) or "Summer Intensive"


def _date_heading(section: Node) -> str:
    """The event's date heading — the one heading carrying a year."""
    for heading in section.css(_HEADING):
        text = _text(heading)
        if re.search(r"\b20\d\d\b", text):
            return text
    return ""


def _location(section: Node) -> Location:
    """City/country from the section's text-editor lines (the page writes
    "Athens, Greece"); default to the org's Athens base when none is given."""
    for node in section.css(_TEXT):
        if "athens" in _text(node).lower():
            return Location(city="Athens", country="GR")
    return Location(city="Athens", country="GR")


# --- dates --------------------------------------------------------------------
#
# The heading is a day-first range with a single trailing year, in either of two
# shapes: cross-month ("29 June - 3 july 2026", each day carrying its own month)
# or shared-month ("14 - 18 July 2025", one month for both days). We collect every
# (day, month) point from both forms, stamp them with the year, and take the
# earliest start and latest end.

_DAY_MONTH = re.compile(r"(\d{1,2})\s+(" + parse.MONTHALT + r")", re.IGNORECASE)
# A shared-month range: "14 - 18 July" — the first day has no month of its own.
_SHARED_MONTH = re.compile(
    r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(" + parse.MONTHALT + r")", re.IGNORECASE
)
_YEAR = re.compile(r"\b(20\d\d)\b")


def _dates(text: str) -> tuple[date | None, date | None]:
    year_match = _YEAR.search(text)
    if year_match is None:
        return None, None
    year = int(year_match.group(1))
    points = [
        date(year, parse.MONTHS[month.lower()], int(day)) for day, month in _DAY_MONTH.findall(text)
    ]
    for first, last, month in _SHARED_MONTH.findall(text):
        month_num = parse.MONTHS[month.lower()]
        points += [date(year, month_num, int(first)), date(year, month_num, int(last))]
    if not points:
        return None, None
    return min(points), max(points)


# --- genres -------------------------------------------------------------------
#
# The card names no syllabus, so we match only its own words. IntoDance is a
# classical/modern/contemporary platform, but a given edition's card doesn't
# enumerate classes — default to classical (a ballet intensive) and add
# contemporary only when the card itself says so.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet", "classical")),
    ("contemporary", ("contemporary", "modern")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _text(node: Node | None) -> str:
    """Node text with whitespace collapsed but block newlines preserved."""
    if node is None:
        return ""
    raw = node.text(separator="\n")
    lines = [parse.clean(line) for line in raw.split("\n")]
    return "\n".join(line for line in lines if line)
