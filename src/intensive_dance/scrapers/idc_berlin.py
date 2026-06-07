"""IDC Berlin (International Dance Competition Berlin) — its Summer Intensive.

API FIRST: none usable. IDC runs on **Wix** (server `Pepyaka`, no public content
API we may use), but the Summer Intensive page is server-side rendered, so the
full text is in the static HTML — a one-page scrape, no JS. Wix peppers the
markup with zero-width spaces, so we strip them before parsing (the same trap
the Young Stars and Brussels scrapers handle).

DISCOVERY: one page (`/summer`) describes the current edition as a single Summer
Intensive run in **two parts** you may take individually or together (combined
pricing for both). We emit one `Offering`, the two parts as `schedule.sessions`,
season-keyed from the parsed year.

WHAT THE PAGE GIVES US (verified live 2026-06):
  - DATES: Part 1 (13–18 July 2026, Deutsche Oper studios) and Part 2
    (10–15 August 2026, Berlin Dance Institute) — two distinct Berlin venues,
    kept in the session notes alongside each part's showcase.
  - AGES: "Dancers ages 7+ are welcome" — open-ended, so only the lower bound.
  - LEVEL: "Open for all levels — from hobby dancers to professional students"
    → `open`.
  - PRICES in EUR: four tuition tiers (one intensive vs. both × the Violet and
    Indigo/Aqua age groups).
  - STATUS: both parts are "FULL"; the form is now a waitlist sign-up, so the
    application is `closed` (the edition still takes place — `lifecycle` stays
    `scheduled`).
  - REQUIREMENTS: the registration page (`/register-for-summer-intensive`, not the
    scraped `/summer` page) carries the "This is not an audition" phrase; the
    `/summer` page we scrape lacks that trigger text, so `_requirements` returns
    `[]` rather than `[NoneReq()]`. Requirements therefore stays empty — faithfully
    reflecting what the scraped page states, with the nuance in the application note.

Faculty: the page lists a guest-teacher roll and the full 2026 faculty is now
published, but the names run together in one un-delimited block, so teachers are
left empty rather than over-claimed (same call as Brussels/Joffrey).
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
    Level,
    Location,
    NoneReq,
    Offering,
    Organization,
    Price,
    Requirement,
    Schedule,
    Session,
    Source,
    now_utc,
)

BASE = "https://www.idc-dance.com"
PAGE = f"{BASE}/summer"
APPLY_URL = f"{BASE}/register-for-summer-intensive"

ORG = Organization(name="IDC Berlin", slug="idc-berlin", country="DE", city="Berlin")

# Wix injects zero-width spaces (ZWSP / ZWNJ / ZWJ / BOM) into the rendered text.
_ZERO_WIDTH = re.compile("[" + "".join(map(chr, (0x200B, 0x200C, 0x200D, 0xFEFF))) + "]")

_APPLY_NOTE = (
    "Both 2026 parts are full; the registration form is a waitlist sign-up. "
    "Registration is not an audition and does not affect acceptance — a video "
    "may be sent optionally for group placement only. Boys may apply for a "
    "scholarship."
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE, follow_redirects=True)
    resp.raise_for_status()
    offering = _build_offering(resp.text)
    return [offering] if offering is not None else []


def _build_offering(html: str) -> Offering | None:
    text = _text(html)

    sessions = _sessions(text)
    if not sessions:
        return None  # no dated parts announced
    start = min(s.start for s in sessions if s.start)
    end = max(s.end for s in sessions if s.end)
    season = str(end.year)

    return Offering(
        id=f"idc-berlin/summer-intensive-{season}",
        source=Source(provider="idc-berlin", url=PAGE, scrapedAt=now_utc()),
        title=f"Summer Intensive {season}",
        genres=_genres(text),
        level=_levels(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(city="Berlin", country="DE"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Berlin",
            sessions=sessions,
        ),
        prices=_prices(text),
        application=Application(
            status=_status(text),
            url=APPLY_URL,
            requirements=_requirements(text),
            notes=_APPLY_NOTE,
        ),
    )


def _text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    raw = tree.body.text(separator=" ") if tree.body else ""
    return parse.clean(_ZERO_WIDTH.sub("", raw))


# --- sessions: two parts, each "<Month> <d>-<d>, <year>" ----------------------

# "July 13-18, 2026" — one month spanning both days, with a trailing year. The
# string recurs (banner + teachers header), so callers dedupe on (start, end).
_PART = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})\s*[-–—]\s*(\d{1,2}),\s*(\d{4})",
    re.IGNORECASE,
)
# "IDC Berlin Part 1 will take place at the Studios … Address: … 10585 Berlin" /
# "IDC Berlin Part 2: Berlin Dance Institute Address: … 12103 Berlin". The
# "IDC Berlin " prefix is what distinguishes the Locations block from the
# "PART 1: WAITLIST …" status banner, which also fits "Part N: …".
_VENUE = re.compile(
    r"IDC Berlin Part\s+(\d)\s*(?:will take place at\s+(?:the\s+)?|:\s*)"
    r"(.+?)\s*Address:\s*(.+?\d{5}\s+Berlin)",
    re.IGNORECASE,
)
# "Showcase July 18th at 4pm" — matched to its part by the closing date.
_SHOWCASE = re.compile(
    r"Showcase\s+(" + parse.MONTHALT + r")\s+(\d{1,2})(?:st|nd|rd|th)?\s+at\s+"
    r"(\d{1,2}(?::\d{2})?\s*[ap]m)",
    re.IGNORECASE,
)


def _venues(text: str) -> dict[int, tuple[str, str]]:
    return {
        int(m.group(1)): (parse.clean(m.group(2)), parse.clean(m.group(3)))
        for m in _VENUE.finditer(text)
    }


def _showcases(text: str) -> dict[tuple[int, int], str]:
    out: dict[tuple[int, int], str] = {}
    for m in _SHOWCASE.finditer(text):
        month, day, time = m.groups()
        out[(parse.MONTHS[month.lower()], int(day))] = parse.clean(time)
    return out


def _sessions(text: str) -> list[Session]:
    venues = _venues(text)
    showcases = _showcases(text)
    seen: set[tuple[date, date]] = set()
    out: list[Session] = []
    for m in _PART.finditer(text):
        month_name, d1, d2, year = m.groups()
        month = parse.MONTHS[month_name.lower()]
        start = date(int(year), month, int(d1))
        end = date(int(year), month, int(d2))
        if (start, end) in seen:
            continue
        seen.add((start, end))
        part = len(out) + 1
        notes: list[str] = []
        if part in venues:
            venue, address = venues[part]
            notes.append(f"{venue} ({address})")
        showcase = showcases.get((end.month, end.day))
        if showcase:
            notes.append(f"Showcase {end:%d %B} at {showcase}")
        out.append(
            Session(label=f"Part {part}", start=start, end=end, notes="; ".join(notes) or None)
        )
    return out


# --- ages / level -------------------------------------------------------------

_AGE = re.compile(r"Dancers ages\s*(\d{1,2})\s*\+", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    return parse.extract_age_range(text, _AGE)


def _levels(text: str) -> list[Level]:
    return ["open"] if re.search(r"all levels", text, re.IGNORECASE) else []


# --- genres -------------------------------------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet",)),
    ("repertoire", ("repertoire", "variations")),
    ("contemporary", ("modern", "lyrical", "jazz", "commercial")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- prices: four tuition tiers (one vs. both × Violet / Indigo-Aqua) ----------

_PRICE_BLOCK = re.compile(
    r"Tuition\s+(One Intensive.*?)(?:Boys may|Register Now|Take a look)",
    re.IGNORECASE,
)
_SCOPE = re.compile(
    r"(One Intensive|Both Intensives)\s*:?(.*?)(?=One Intensive|Both Intensives|$)",
    re.IGNORECASE,
)
_TIER = re.compile(r"([A-Za-z/ ]+?)\s*:\s*(\d[\d.,]*)\s*Euro", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    block = _PRICE_BLOCK.search(text)
    if not block:
        return []
    prices: list[Price] = []
    for scope_m in _SCOPE.finditer(block.group(1)):
        scope = parse.clean(scope_m.group(1))
        for tier_m in _TIER.finditer(scope_m.group(2)):
            amount = parse.parse_amount(tier_m.group(2))
            if amount is None:
                continue
            tier = parse.clean(tier_m.group(1))
            prices.append(
                Price(
                    amount=amount,
                    currency="EUR",
                    label=f"{scope} — {tier}",
                    includes=["tuition"],
                )
            )
    return prices


# --- status / requirements ----------------------------------------------------


def _status(text: str):
    low = text.lower()
    if "waitlist" in low or re.search(r"\(\s*full\s*\)", low):
        return "closed"
    if re.search(r"register now|sign up now", low):
        return "open"
    return None


def _requirements(text: str) -> list[Requirement]:
    # The page is explicit that registration is not an audition; an optional
    # video only places you in a group. So nothing is *required*.
    return [NoneReq()] if re.search(r"not an audition", text, re.IGNORECASE) else []
