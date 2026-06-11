"""American Midwest Ballet School — Council Bluffs, IA / Omaha, NE, US — its
summer programming.

API FIRST: plain **WordPress 7.0** (`GET /wp-json/` → 200, `generator` meta).
The summer programs live on one CMS page (`/school/summer_dance/`), whose body is
present as clean rendered HTML in `content.rendered` over the WP REST pages
endpoint — `wp.fetch_page(client, "summer_dance", base=...)`, no HTML scrape, no
JS. There are no event/program custom post types.

DISCOVERY: one `Offering` per dated summer *program* (the source's program cards),
keeping only those that actually teach ballet:
  - **June Children's Summer Dance Camps** (ages 6-9) — themed Saturday camps that
    each start with a ballet class. EMITTED.
  - **June Teen/Adult Summer Series** (ages 11+) — a four-week ballet (+ tap) series.
    EMITTED; the tap-only classes are out of scope and don't leak a genre.
  - **August Summer Series** (ages 3+) — a two-week after-school series spanning
    ballet, modern, contemporary, jazz and musical theater tracks. EMITTED with one
    `Price` per ballet-containing track.
  - **June Primary Dance** (ages 3-5) — creative movement, no ballet class → DROPPED
    by the empty-genre rule.
  - **Day of Dance** — a free annual open house with no registration detail yet
    ("watch this page") → DROPPED (no faithful dated course to emit).

These are recreational/academy-track summer *short courses*, not an audition
intensive — so application requirements are open-enrollment (none stated → left
unknown) and most fields are read straight from the prose.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-11):
  - DATES: US `Month DD, YYYY` — a list of single Saturdays (camps), a cross-month
    range "June 9 - July 1, 2026" (teen/adult), and two week-ranges
    "August 17-20" + "August 24-27, 2026" spanned into one start/end (August).
  - GENRES: matched against each program's prose (ballet → classical, contemporary
    → contemporary); modern/jazz/musical-theater/tap aren't in the genre enum and
    so don't leak.
  - PRICES: several `Price`s per Offering (single vs. three camps; per-track August
    fees), USD, with the source's "(N classes over M weeks)" note kept verbatim.
  - DEADLINE: explicit "Registration deadline: June 1, 2026" / "register by June 1"
    for the June programs; none stated for August → left null (fail open).
  - AGES: `(Ages 6-9)` bounded and `(Ages 11+)` / `(Ages 3+)` open-topped.
"""

from __future__ import annotations

import html as ihtml
import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    now_utc,
)

SLUG = "american-midwest-ballet"
BASE = "https://amballet.org"
PAGE = f"{BASE}/school/summer_dance/"
PAGE_WP_SLUG = "summer_dance"

ORG = Organization(name="American Midwest Ballet", slug=SLUG, country="US", city="Omaha")
LOCATION = Location(
    venue="American Midwest Ballet School",
    city="Council Bluffs",
    country="US",
)
TIMEZONE = "America/Chicago"

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet",)),
    ("contemporary", ("contemporary",)),
]

# The August series is one program card; its ballet-containing tracks each carry a
# distinct per-track fee. Tracks without a ballet class (Creative Movement,
# Pre-Dance) are excluded — the page's structure is stable, so anchoring on the
# track label is the robust way to pin each fee to its age band.
_AUGUST_TRACKS: list[tuple[str, dict]] = [
    ("Child 1-2 Series", {"min": 6, "max": 8}),
    ("Child 3/Academy 1 Series", {"min": 8, "max": 12}),
    ("Academy 2-3 Series", {"min": 10, "max": None}),
    ("Academy 4-6 Series", {"min": 12, "max": None}),
]

_MONTH = parse.MONTHALT


def scrape(client: httpx.Client) -> list[Offering]:
    page = wp.fetch_page(client, PAGE_WP_SLUG, base=BASE)
    if page is None:
        return []
    return _build_offerings(page["content"]["rendered"], date.today())


def _build_offerings(rendered: str, today: date) -> list[Offering]:
    text = _plain_text(rendered)
    builders = (_build_camps, _build_teen_adult, _build_august)
    return [o for build in builders if (o := build(text)) is not None]


# --- text helpers -------------------------------------------------------------


def _plain_text(rendered: str) -> str:
    tree = HTMLParser(rendered)
    for node in tree.css("script, style"):
        node.decompose()
    text = parse.clean(tree.text(separator=" "))
    return ihtml.unescape(text).replace("–", "-").replace("—", "-").replace("’", "'")


def _block(text: str, start: str, end: str | None) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find(end, i + 1) if end else len(text)
    return text[i : j if j >= 0 else len(text)]


# --- date helpers -------------------------------------------------------------

_SINGLE_DATE = re.compile(rf"({_MONTH})\s+(\d{{1,2}}),\s*(\d{{4}})", re.IGNORECASE)
_CROSS_RANGE = re.compile(
    rf"({_MONTH})\s+(\d{{1,2}})\s*-\s*({_MONTH})\s+(\d{{1,2}}),\s*(\d{{4}})", re.IGNORECASE
)
_WEEK_RANGE = re.compile(rf"({_MONTH})\s+(\d{{1,2}})-(\d{{1,2}}),\s*(\d{{4}})", re.IGNORECASE)


def _single_dates(block: str) -> list[date]:
    out: list[date] = []
    for m in _SINGLE_DATE.finditer(block):
        out.append(date(int(m.group(3)), parse.MONTHS[m.group(1).lower()], int(m.group(2))))
    return out


# --- application helpers ------------------------------------------------------

_DEADLINE = re.compile(rf"deadline:\s*({_MONTH})\s+(\d{{1,2}}),\s*(\d{{4}})", re.IGNORECASE)
_REGISTER_BY = re.compile(rf"register by\s*({_MONTH})\s+(\d{{1,2}})", re.IGNORECASE)


def _application(block: str, year: int) -> Application:
    deadline: date | None = None
    notes: str | None = None
    if (m := _DEADLINE.search(block)) is not None:
        deadline = date(int(m.group(3)), parse.MONTHS[m.group(1).lower()], int(m.group(2)))
        notes = f"Registration deadline: {m.group(1)} {m.group(2)}, {m.group(3)}"
    elif (m := _REGISTER_BY.search(block)) is not None:
        deadline = date(year, parse.MONTHS[m.group(1).lower()], int(m.group(2)))
        notes = f"Register by {m.group(1)} {m.group(2)}"
    return Application(url=PAGE, deadline=deadline, notes=notes)


def _offering(
    *,
    offering_slug: str,
    title: str,
    block: str,
    start: date,
    end: date,
    age_range: dict,
    prices: list[Price],
    schedule_notes: str,
) -> Offering | None:
    genres = parse.match_genres(block, _GENRE_KEYWORDS)
    if not genres:
        return None
    season = str(start.year)
    return Offering(
        id=f"{SLUG}/{offering_slug}-{season}",
        source=Source(provider=SLUG, url=PAGE, scrapedAt=now_utc()),
        title=f"{title} {season}",
        genres=genres,
        ageRange=age_range,
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(
            season=season, start=start, end=end, timezone=TIMEZONE, notes=schedule_notes
        ),
        prices=prices,
        application=_application(block, start.year),
    )


# --- per-program builders -----------------------------------------------------


def _build_camps(text: str) -> Offering | None:
    block = _block(text, "June Children's Summer Dance Camps", "June Teen/Adult Summer Series")
    if not block:
        return None
    # Dates only from the camp list ("Camps*: …") — the block also carries the
    # "Registration deadline: June 1" date, which must not become the start.
    dates = _single_dates(_block(block, "Camps", "Cost:"))
    if not dates:
        return None
    prices = _camp_prices(block)
    return _offering(
        offering_slug="june-childrens-dance-camps",
        title="June Children's Summer Dance Camps",
        block=block,
        start=min(dates),
        end=max(dates),
        age_range={"min": 6, "max": 9},
        prices=prices,
        schedule_notes="Themed Saturday camps; 9:45-11:45 am. Enroll in one, two, or all three.",
    )


def _camp_prices(block: str) -> list[Price]:
    prices: list[Price] = []
    if (m := re.search(r"Single camp:\s*\$(\d+)", block)) is not None:
        prices.append(_usd(m.group(1), "Single camp", ["tuition"]))
    if (m := re.search(r"Three camps:\s*\$(\d+)", block)) is not None:
        prices.append(_usd(m.group(1), "All three camps", ["tuition"]))
    return prices


def _build_teen_adult(text: str) -> Offering | None:
    block = _block(text, "June Teen/Adult Summer Series", "August Summer Series")
    if not block:
        return None
    m = _CROSS_RANGE.search(block)
    if m is None:
        return None
    year = int(m.group(5))
    start = date(year, parse.MONTHS[m.group(1).lower()], int(m.group(2)))
    end = date(year, parse.MONTHS[m.group(3).lower()], int(m.group(4)))
    prices: list[Price] = []
    if (p := re.search(r"\$(\d+)\s*\(([^)]*classes[^)]*)\)", block)) is not None:
        prices.append(_usd(p.group(1), f"Per class ({parse.clean(p.group(2))})", ["tuition"]))
    return _offering(
        offering_slug="june-teen-adult-summer-series",
        title="June Teen/Adult Summer Series",
        block=block,
        start=start,
        end=end,
        age_range={"min": 11, "max": None},
        prices=prices,
        schedule_notes="Four-week series for beginning through advanced teen and adult students.",
    )


def _build_august(text: str) -> Offering | None:
    block = _block(text, "August Summer Series", "Day of Dance")
    if not block:
        return None
    weeks = list(_WEEK_RANGE.finditer(block))
    if not weeks:
        return None
    first, last = weeks[0], weeks[-1]
    start = date(int(first.group(4)), parse.MONTHS[first.group(1).lower()], int(first.group(2)))
    end = date(int(last.group(4)), parse.MONTHS[last.group(1).lower()], int(last.group(3)))
    notes = "; ".join(f"{w.group(1)} {w.group(2)}-{w.group(3)}, {w.group(4)}" for w in weeks)
    return _offering(
        offering_slug="august-summer-series",
        title="August Summer Series",
        block=block,
        start=start,
        end=end,
        age_range={"min": 3, "max": None},
        prices=_august_prices(block),
        schedule_notes=notes,
    )


def _august_prices(block: str) -> list[Price]:
    prices: list[Price] = []
    for label, _age in _AUGUST_TRACKS:
        m = re.search(re.escape(label) + r"\b.*?Cost:\s*\$(\d+)\s*(\([^)]*\))?", block)
        if m is None:
            continue
        note = parse.clean(m.group(2).strip("()")) if m.group(2) else None
        prices.append(_usd(m.group(1), label, ["tuition"], notes=note))
    if (m := re.search(r"Adult Classes.*?\$(\d+)", block)) is not None:
        prices.append(_usd(m.group(1), "Adult class", ["tuition"], notes="per class"))
    return prices


def _usd(amount: str, label: str, includes: list, notes: str | None = None) -> Price:
    return Price(amount=float(amount), currency="USD", label=label, includes=includes, notes=notes)
