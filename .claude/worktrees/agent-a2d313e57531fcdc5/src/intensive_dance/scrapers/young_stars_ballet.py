"""Young Stars Ballet (Berlin, DE) — its summer intensives.

API FIRST: none. Young Stars Ballet runs on **Wix** (server-side rendered, like
Brussels), so the content is in the static HTML — no JS. We read two pages: the
Summer Intensive page (dates, price, ages, curriculum, location, guest
masterclass) and the application form at `/apply-here` (the required uploads).

DISCOVERY: the homepage links the current Summer Intensive page; we follow that
link (so the id rolls forward when the season advances) rather than hardcode the
year. The page advertises two 10-day editions — "YSB 1" and "YSB 2" — that a
dancer may take singly or back-to-back, so we emit one `Offering` for the summer
intensive with the two editions as `schedule.sessions`.

WHAT THE PAGES GIVE US (verified live 2026-06):
  - DATES: "YSB 1 | 16 July - 26 July 2026", "YSB2 | 29 July - 8 August 2026".
  - PRICE: €740 per intensive (10 days, 7 h/day); group/both-week discounts noted.
  - AGES: 13–21. GENRES from the curriculum (ballet, repertoire, modern, pointe).
  - TEACHER: a named guest masterclass (e.g. Melike Demirtas) — the register's
    first emitted `Teacher`.
  - REQUIREMENTS from the application form: a headshot, 2–3 full-body dance
    photos (applicant's choice, examples suggested), and a CV/letter — no video.
    Wix renders inline form labels with letter-spacing that garbles words mid-
    token ("a rabesque"), so we detect the requirement *keywords* (which render
    cleanly) and describe them in normalized prose rather than scrape the
    garbled example list verbatim.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    CVReq,
    Genre,
    HeadshotReq,
    Location,
    Offering,
    Organization,
    PhotosReq,
    Price,
    Requirement,
    Schedule,
    Session,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.youngstarsballet.com"
APPLY_URL = f"{BASE}/apply-here"

# Zero-width space / non-joiner / joiner / BOM — Wix scatters these through text.
_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\ufeff]")

ORG = Organization(
    name="Young Stars Ballet", slug="young-stars-ballet", country="DE", city="Berlin"
)
VENUE = Location(
    venue="Tanzraum Wedding, Oudenarder Str. 16-20, 13347 Berlin", city="Berlin", country="DE"
)


def scrape(client: httpx.Client) -> list[Offering]:
    summer_url = _summer_url(client)
    if summer_url is None:
        return []
    summer = _text(client.get(summer_url))
    apply_text = _text(client.get(APPLY_URL))
    offering = _build_offering(summer, summer_url, apply_text)
    return [offering] if offering is not None else []


def _summer_url(client: httpx.Client) -> str | None:
    """The current Summer Intensive page, discovered from the homepage nav."""
    tree = HTMLParser(client.get(f"{BASE}/").text)
    for a in tree.css("a"):
        href = a.attributes.get("href") or ""
        if re.search(r"summer-intensive", href, re.IGNORECASE):
            return href if href.startswith("http") else BASE + href
    return None


def _text(resp: httpx.Response) -> str:
    resp.raise_for_status()
    tree = HTMLParser(resp.text)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    raw = tree.body.text(separator=" ") if tree.body else ""
    # Wix peppers the markup with zero-width spaces (e.g. "PRICE: <zwsp> €740");
    # strip them so amounts and names aren't split by an invisible character.
    raw = _ZERO_WIDTH.sub("", raw)
    return parse.clean(raw)


def _build_offering(summer: str, summer_url: str, apply_text: str) -> Offering | None:
    sessions = _sessions(summer)
    if not sessions:
        return None  # no dated editions announced
    start = min(s.start for s in sessions if s.start)
    end = max(s.end for s in sessions if s.end)
    season = str(end.year)

    return Offering(
        id=f"young-stars-ballet/summer-intensive-{season}",
        source=Source(provider="young-stars-ballet", url=summer_url, scrapedAt=now_utc()),
        title=f"Summer Intensive {season}",
        genres=_genres(summer),
        ageRange=_age_range(summer),
        organization=ORG,
        location=VENUE,
        schedule=Schedule(
            season=season, start=start, end=end, timezone="Europe/Berlin", sessions=sessions
        ),
        prices=_prices(summer),
        teachers=_teachers(summer),
        application=Application(
            status="open",
            url=APPLY_URL,
            requirements=_requirements(apply_text),
        ),
    )


# --- dates: "YSB 1 | 16 July - 26 July 2026" (year on the closing date only) ---

_SESSION = re.compile(
    r"YSB\s*(\d)\s*\|?\s*(\d{1,2})\s+(" + parse.MONTHALT + r")\s*[-–]\s*"
    r"(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _sessions(text: str) -> list[Session]:
    sessions = []
    for m in _SESSION.finditer(text):
        n, d1, m1, d2, m2, year = m.groups()
        sessions.append(
            Session(
                label=f"YSB {n}",
                start=date(int(year), parse.MONTHS[m1.lower()], int(d1)),
                end=date(int(year), parse.MONTHS[m2.lower()], int(d2)),
            )
        )
    return sessions


_AGE = re.compile(r"ages?:?\s*(\d{1,2})\s*[-–]\s*(\d{1,2})", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    m = _AGE.search(text)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


_PRICE = re.compile(r"price:?\s*€\s*(\d[\d.,]*)", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    m = _PRICE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    notes = None
    if re.search(r"15%\s*discount", text, re.IGNORECASE):
        notes = "15% discount for attending both editions (20 days) or for groups of 3+ from one school."
    return [
        Price(
            amount=amount,
            currency="EUR",
            label="Per intensive (10 days)",
            includes=["tuition"],
            notes=notes,
        )
    ]


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet", "technique", "classical")),
    ("repertoire", ("repertoire", "corps de ballet")),
    ("contemporary", ("modern", "contemporary")),
    ("pointe", ("pointe",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# "Balletmasterclass by Melike Demirtas" — a named guest teacher for this edition.
# Name words are Title-case (capital + lowercase); this stops an ALL-CAPS heading
# that follows the name (e.g. "… Demirtas WHEN:") from being swallowed into it.
_NAME = r"[A-ZÀ-Ý][a-zà-ÿ'’-]+"
_TEACHER = re.compile(r"masterclass\s+by\s+(" + _NAME + r"(?:\s+" + _NAME + r"){1,2})")


def _teachers(text: str) -> list[Teacher]:
    m = _TEACHER.search(text)
    return [Teacher(name=parse.clean(m.group(1)), role="Masterclass")] if m else []


def _requirements(apply_text: str) -> list[Requirement]:
    low = apply_text.lower()
    reqs: list[Requirement] = []
    if "headshot" in low:
        reqs.append(HeadshotReq())
    if "dance poses" in low or "dance pose" in low:
        reqs.append(
            PhotosReq(
                specificity="freeform",
                notes=(
                    "Two to three full-body dance photos of the applicant's choice "
                    "(examples suggested: arabesque, attitude, tendu, port de bras; "
                    "contemporary poses welcome)."
                ),
            )
        )
    if re.search(r"\bcv\b|letter detailing", low):
        reqs.append(CVReq())
    return reqs
