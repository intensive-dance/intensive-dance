"""CORDS. Dance Ballet Studio — Wrocław's recurring summer "Intensywne Warsztaty
Baletowe" (Intensive Ballet Workshops), classical + contemporary, ~6 days.

API FIRST — yes, partly. cordsdance.com is **WordPress** (`/wp-json/` is 200) but
built with **Elementor**, not WPBakery, so `wp.parse()` (which slices WPBakery
shortcodes) doesn't apply; the page body *is* present in `content.rendered`,
though, so we fetch the page record over the REST API
(`/wp-json/wp/v2/pages?slug=…`) and read its HTML structurally with selectolax.
No HTML page fetch, no proxy needed (the datacenter IP is served fine, verified
2026-06-08). Registration runs through a **Fitssey** booking app
(`app.fitssey.com/cordsdance/frontoffice`) which exposes only a generic
front-office widget — no per-edition structured endpoint — so the dated facts
come from the WordPress page; the Fitssey URL is just the application link.

DISCOVERY: each edition is its own WP page (`summer-intensive` = 2023,
`summer-intensive-2024`, `summer-intensive-2025`, …; some have a `-2` duplicate
slug from a republish). We list pages, keep the summer-intensive ones, and emit
**one Offering for the latest published year** — the upcoming-year page isn't
created until it's announced (the 2026 slug 404s as of this scrape), so the store
carries the most recent edition (an ended cycle is kept, never date-filtered —
IDR-24). Within a year we prefer the bare slug over its `-2` republish (the bare
one is the public URL and the more complete body).

The workshop is **open-enrolment by class pass** — you buy a Fitssey pass (per
N classes, or an all-access Golden Pass) and self-book classes from the grid;
there is **no audition**, so `application.requirements = [NoneReq]`. It's not a
single-track intensive but a menu of levelled classes (Beginner/Intermediate +
Advanced ballet, pointe, variations, contemporary, neoclassical, …), so it's one
Offering spanning the whole edition, not one-per-class.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - TEACHERS with AFFILIATIONS — a named marquee roster of faculty, parsed from
    the dedicated /team/ page (also WP). Resident faculty are Wrocław Opera
    (Opera Wrocławska) dancers; guests carry international houses — ex-San
    Francisco Ballet (Shannon Maynor), ex-Vienna State Opera / John Cranko School
    (Anna Kowalska), etc. We resolve a known-institution table to `affiliations`.
  - PRICES in PLN — a class-pass ladder (1→40 classes) plus an all-access Golden
    Pass, parsed language-agnostically from the "N - X PLN" / "… 3000 PLN" lines.
  - NoneReq — the open-enrolment branch (no audition, just buy a pass).
  - Polish, parsed language-agnostically: numeric date span ("21 -26 lipca 2025")
    via a Polish month map, numeric prices, and an English title from the API.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse, wp
from intensive_dance.models import (
    Affiliation,
    Application,
    Genre,
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

BASE = "https://cordsdance.com"
TEAM_SLUG = "team"
APPLY_URL = "https://app.fitssey.com/cordsdance/frontoffice"

ORG = Organization(name="Cords Dance", slug="cords-dance", country="PL", city="Wrocław")

VENUE = "Akademia Sztuk Teatralnych, ul. Braniborska 59"

# Pages whose slug names a summer-intensive edition. The year-less `summer-intensive`
# is the 2023 edition (its title carries the year); year-stamped slugs follow. A
# trailing `-N` *after* the year (the `dup` group) is a republish duplicate of the
# same year — we drop it in favour of the bare slug (the public URL, and the more
# complete body). The year itself is matched as `-20\d\d`, so it is NOT a `dup`.
_EDITION_SLUG = re.compile(r"^summer-intensive(?:-(?P<year>20\d\d))?(?P<dup>-\d+)?$")

# Polish month names (genitive, as they appear in date lines: "lipca" = of July).
_PL_MONTHS = {
    "stycznia": 1,
    "lutego": 2,
    "marca": 3,
    "kwietnia": 4,
    "maja": 5,
    "czerwca": 6,
    "lipca": 7,
    "sierpnia": 8,
    "września": 9,
    "wrzesnia": 9,
    "października": 10,
    "pazdziernika": 10,
    "listopada": 11,
    "grudnia": 12,
}
_PL_MONTHALT = parse.months_alt(_PL_MONTHS)

# "21 -26 lipca 2025" — a day-day span sharing one month + a trailing year.
_DATE_SPAN = re.compile(
    r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(" + _PL_MONTHALT + r")\s+(20\d\d)",
    re.IGNORECASE,
)
_DEADLINE = re.compile(r"do\s+(\d{1,2})\s+(" + _PL_MONTHALT + r")", re.IGNORECASE)
# Pricing lines: "N - X PLN" (class-pass ladder) and "Golden Pass … 3000 PLN".
_PASS = re.compile(r"(\d{1,3})\s*[-–]\s*([\d ]{2,})\s*PLN", re.IGNORECASE)
_GOLDEN = re.compile(r"Golden Pass.*?([\d ]{3,})\s*PLN", re.IGNORECASE | re.DOTALL)


def scrape(client: httpx.Client) -> list[Offering]:
    pages = wp.fetch_all(
        client, "pages", base=BASE, params={"_fields": "id,slug,title,content,status,link"}
    )
    team_html = _team_html(pages)
    return _build_offerings(pages, team_html, date.today())


def _team_html(pages: list[dict]) -> str:
    team = next((p for p in pages if p.get("slug") == TEAM_SLUG), None)
    return team["content"]["rendered"] if team else ""


def _build_offerings(pages: list[dict], team_html: str, today: date) -> list[Offering]:
    page = _latest_edition(pages)
    if page is None:
        return []
    html = page["content"]["rendered"]
    text = parse.clean(HTMLParser(html).text(separator=" "))
    title = parse.clean(_decode(page["title"]["rendered"]))

    start, end, year = _dates(text)
    season = (
        str(year)
        if year
        else (str(_year_from_title(title)) if _year_from_title(title) else "unknown")
    )
    teachers = _teachers(_featured_names(html), team_html)

    return [
        Offering(
            id=f"cords-dance/summer-intensive-{season}",
            source=Source(provider="cords-dance", url=page["link"], scrapedAt=now_utc()),
            title=f"CORDS. Dance Summer Intensive {season}".strip(),
            genres=_genres(text),
            level=["beginner", "intermediate", "advanced", "open"],
            organization=ORG,
            location=Location(venue=VENUE, city="Wrocław", country="PL"),
            schedule=Schedule(
                season=season,
                start=start,
                end=end,
                timezone="Europe/Warsaw",
                notes=_dateline(text),
            ),
            teachers=teachers,
            prices=_prices(text),
            application=Application(
                url=APPLY_URL,
                deadline=_deadline(text, year),
                requirements=[NoneReq()],
                notes=_apply_notes(text),
            ),
        )
    ]


# --- edition selection --------------------------------------------------------


def _latest_edition(pages: list[dict]) -> dict | None:
    """The published summer-intensive page for the most recent year.

    Year comes from the slug, falling back to the title (the 2023 edition's slug
    is year-less). Within a year, the bare slug beats its `-N` republish.
    """
    candidates: list[tuple[int, bool, dict]] = []  # (year, is_dup, page)
    for page in pages:
        slug = page.get("slug") or ""
        match = _EDITION_SLUG.match(slug)
        if page.get("status") != "publish" or match is None:
            continue
        year = match.group("year")
        resolved = int(year) if year else _year_from_title(_decode(page["title"]["rendered"]))
        if resolved is None:
            continue
        candidates.append((resolved, bool(match.group("dup")), page))
    if not candidates:
        return None
    # latest year; within a year prefer the non-duplicate (is_dup False sorts first).
    candidates.sort(key=lambda c: (-c[0], c[1]))
    return candidates[0][2]


def _year_from_title(title: str) -> int | None:
    match = re.search(r"\b(20\d\d)\b", title)
    return int(match.group(1)) if match else None


# --- dates --------------------------------------------------------------------


def _dates(text: str) -> tuple[date | None, date | None, int | None]:
    match = _DATE_SPAN.search(text)
    if not match:
        return None, None, None
    d1, d2, month_name, year_str = match.groups()
    month = _PL_MONTHS[month_name.lower()]
    year = int(year_str)
    return date(year, month, int(d1)), date(year, month, int(d2)), year


def _dateline(text: str) -> str | None:
    match = _DATE_SPAN.search(text)
    return parse.clean(match.group(0)) if match else None


def _deadline(text: str, year: int | None) -> date | None:
    """The application deadline ("Zapisy prowadzimy do 15 LIPCA").

    Several "do <day> <month>" phrases appear (early-bird cut-offs come first);
    the registration deadline is the latest of them, so take the max.
    """
    if year is None:
        return None
    dates = [
        date(year, _PL_MONTHS[m.lower()], int(d))
        for d, m in _DEADLINE.findall(text)
        if m.lower() in _PL_MONTHS
    ]
    return max(dates) if dates else None


def _apply_notes(text: str) -> str:
    """The booking model + early-bird/deadline gist, in source words."""
    note = (
        "Open enrolment via the Fitssey booking app: buy a class pass (per number "
        "of classes, or an all-access Golden Pass) and self-book classes from the "
        "grid; a non-refundable 30% deposit is due within 7 days. No audition."
    )
    if "15%" in text or "10%" in text:
        note += " Early-bird discounts (15% / 10%) before the listed dates."
    seen: set[str] = set()
    deadlines: list[str] = []
    for d, m in _DEADLINE.findall(text):
        label = f"do {d} {m.lower()}"
        if label not in seen:
            seen.add(label)
            deadlines.append(label)
    if deadlines:
        note += " Deadlines: " + ", ".join(deadlines) + "."
    return note


# --- genres -------------------------------------------------------------------
#
# Matched against the class menu in the page body (ballet/pointe/contemporary/
# neoclassical/variations), not teacher bios.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet", "balet", "classical")),
    ("contemporary", ("contemporary",)),
    ("neoclassical", ("neoclassical", "neocclasical", "neoklas")),
    ("pointe", ("pointe", "point work", "4 pointe")),
    ("repertoire", ("variation", "wariacj", "repertoire")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- prices -------------------------------------------------------------------


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    for count, amount in _PASS.findall(text):
        value = parse.parse_amount(amount)
        if value is None:
            continue
        prices.append(
            Price(
                amount=value,
                currency="PLN",
                label=f"{count}-class pass",
                includes=["tuition"],
                notes=f"{count} - {parse.clean(amount)} PLN",
            )
        )
    golden = _GOLDEN.search(text)
    if golden:
        value = parse.parse_amount(golden.group(1))
        if value is not None:
            prices.append(
                Price(
                    amount=value,
                    currency="PLN",
                    label="Golden Pass (all classes)",
                    includes=["tuition"],
                    notes="Golden Pass — access to all classes.",
                )
            )
    return prices


# --- teachers + affiliations --------------------------------------------------
#
# The edition page lists the faculty by name (a "Nauczyciele" block of name +
# "Zobacz"/"see" links); the full bios live on the /team/ page. We take the
# featured names from the edition page and resolve each bio on the team page to
# pull institution affiliations. Institutions are matched case-insensitively
# against a known table — resident faculty are Opera Wrocławska dancers; guests
# carry international houses.

# Bio substring → (canonical organization, slug | None). Order is the emit order
# (stable, not a primary-affiliation ranking).
_INSTITUTIONS: list[tuple[str, str, str | None]] = [
    ("opera wrocławska", "Opera Wrocławska", None),
    ("opera wroclawska", "Opera Wrocławska", None),
    ("wrocław opera", "Opera Wrocławska", None),
    ("wroclaw opera", "Opera Wrocławska", None),
    ("san francisco ballet", "San Francisco Ballet", None),
    ("oregon ballet", "Oregon Ballet Theatre", None),
    ("vienna state opera", "Vienna State Opera", None),
    ("john cranko", "John Cranko School", "john-cranko-schule"),
    ("boris eifman", "Boris Eifman Ballet", None),
    ("polish national ballet", "Polish National Ballet", None),
    ("state ballet school of berlin", "State Ballet School Berlin", None),
    ("staatsballet berlin", "Staatsballett Berlin", None),
    ("victor ullate", "Víctor Ullate Ballet", None),
    ("staatstheater wiesbaden", "Staatstheater Wiesbaden", None),
    ("staatsoper hannover", "Staatsoper Hannover", None),
    ("ballet de la generalitat valenciana", "Ballet de la Generalitat Valenciana", None),
    ("split dance school", "Split Dance School", None),
    ("wrocław dance theatre", "Wrocław Dance Theatre", None),
    ("wroclaw dance theatre", "Wrocław Dance Theatre", None),
    ("martha graham", "Martha Graham School", None),
]
_PAST = ("ex ", "ex-", "former", "graduate", "graduated", "trained and performed", "prior to")
_PRESENT = ("current", "now teaches", "she now", "is currently", "demi soloist", "soloist")


def _featured_names(html: str) -> list[str]:
    """Faculty names from the edition page's 'Nauczyciele' (Teachers) block.

    Elementor renders the roster as a heading block followed by name + "Zobacz"
    ("see") buttons; the names sit between the "Nauczyciele" marker and the
    schedule ("Grafik"). We scan the per-node text lines that fall in that window
    and keep the ones that look like a person name.
    """
    lines = [parse.clean(line) for line in HTMLParser(html).text(separator="\n").split("\n")]
    lows = [line.lower() for line in lines]
    if "nauczyciele" not in lows:
        return []
    start = lows.index("nauczyciele")
    end = lows.index("grafik") if "grafik" in lows[start + 1 :] else len(lines)
    if "grafik" in lows[start + 1 :]:
        end = start + 1 + lows[start + 1 :].index("grafik")

    seen: set[str] = set()
    out: list[str] = []
    for line in lines[start + 1 : end]:
        low = line.lower()
        if low in {"zobacz", "see", "nauczyciele", "grafik"}:
            continue
        if _looks_like_name(line) and low not in seen:
            seen.add(low)
            out.append(line)
    return out


def _looks_like_name(line: str) -> bool:
    """A 2–4 token person name (letters, allowing parentheses for maiden names)."""
    if not (2 <= len(line.split()) <= 4):
        return False
    return bool(re.fullmatch(r"[A-Za-zÀ-ž().'\-\s]+", line))


def _teachers(featured: list[str], team_html: str) -> list[Teacher]:
    team_text = parse.clean(HTMLParser(team_html).text(separator=" ")) if team_html else ""
    teachers: list[Teacher] = []
    for name in featured:
        bio = _bio_window(name, team_text)
        teachers.append(Teacher(name=_tidy_name(name), affiliations=_affiliations(bio)))
    return teachers


def _tidy_name(name: str) -> str:
    """Title-case an all-caps roster name, keeping a parenthetical maiden name."""
    parts = []
    for token in name.split():
        core = token.strip("()")
        if core.isupper() and core.isalpha() and len(core) > 1:
            parts.append(token.replace(core, core.capitalize()))
        else:
            parts.append(token)
    return " ".join(parts)


# On the /team/ page (Elementor), each person's bio prose immediately follows
# their name in the flattened text ("SHANNON MAYNOR originally from California,
# has been a Berlin based artist…"), but the name's case/spelling differs from
# the edition-page roster (ALL-CAPS vs Title, maiden name in parentheses). We
# locate the bio by the person's distinctive surname token and read the window
# of text that follows up to the next teacher's bio — robust to the column-based
# DOM that defeats a heading→sibling pairing.
_BIO_WINDOW = 700


def _bio_window(name: str, team_text: str) -> str:
    """The slice of the team-page text that follows `name`'s surname token."""
    if not team_text:
        return ""
    low = team_text.lower()
    # the longest name token (usually the surname) is the most distinctive anchor
    tokens = sorted(
        (t.strip("().") for t in name.split() if len(t.strip("().")) > 3),
        key=len,
        reverse=True,
    )
    for token in tokens:
        idx = low.find(token.lower())
        if idx >= 0:
            return team_text[idx : idx + _BIO_WINDOW]
    return ""


def _affiliations(bio: str) -> list[Affiliation]:
    low = bio.lower()
    orgs: list[tuple[str, str | None]] = []
    for needle, org, slug in _INSTITUTIONS:
        if needle in low and not any(org == o for o, _ in orgs):
            orgs.append((org, slug))
    if not orgs:
        return []
    # current/past is only attributable confidently when the bio names one house.
    current = None
    if len(orgs) == 1:
        if any(p in low for p in _PAST):
            current = False
        elif any(p in low for p in _PRESENT):
            current = True
    return [Affiliation(organization=org, slug=slug, current=current) for org, slug in orgs]


def _decode(raw: str) -> str:
    import html as _html

    return _html.unescape(raw)
