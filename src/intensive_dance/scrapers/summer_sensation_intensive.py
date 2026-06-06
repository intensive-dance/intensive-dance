"""DART Dance Company — its Summer Sensation Intensive (Berlin, DE).

API FIRST: none usable. DART runs on **Wix** (server `Pepyaka`, no public content
API we may use), but the intensive page (`/summer-intensive-berlin`) is
server-side rendered, so the full text is in the static HTML — a one-page scrape,
no JS. Wix peppers the markup with zero-width spaces, so we strip them before
parsing (the same trap the Brussels / Young Stars / IDC scrapers handle).

DISCOVERY: one page describes the current edition as a single three-week
contemporary-repertoire intensive — three consecutive Monday–Friday weeks you may
take individually or together (1 / 2 / 3-week pricing). We emit one `Offering`,
the three weeks as `schedule.sessions`, season-keyed from the first week's year.

WHAT THE PAGE GIVES US (verified live 2026-06):
  - DATES: Week 1 "3rd - 7th August 2026", Week 2 "10th - 14th August", Week 3
    "17th - 21st August". The source mistypes weeks 2 & 3 as "2025" while the
    title ("BERLIN 26") and week 1 say 2026; since the block is plainly one
    consecutive August run, we anchor every week to week 1's year and record the
    source typo in a schedule note (faithful + transparent).
  - REPERTOIRE: Mats Ek, Nacho Duato, Marco Goecke, Lightfoot/León, Jiří Kylián,
    Johan Inger, Alexander Ekman and DART's own work — all contemporary /
    neoclassical, taught as repertoire. No classical *class* is taught (the ballet
    video is an application requirement only), so we don't force `classical`.
  - FACULTY: a confirmed seven-teacher roster, cleanly delimited between the
    "following teachers:" line and "WORKSHOP SCHEDULE" — so we emit it (unlike the
    Brussels/IDC guest rolls, which were legacy/unconfirmed and run-together).
  - PRICES in EUR: 1 week 595, 2 weeks 995, 3 weeks 1395 — tuition incl. the
    registration cost.
  - REQUIREMENTS: apply with a CV, a ≤5-min improvisation video and a ≤10-min
    ballet video with four named centre exercises (tendus, pirouettes, petit
    allegro, grand allegro), both on YouTube. → CV + a `specific` video.
  - AGES / LEVEL: not stated on the page, so both are left empty.

Application is by email (dartdanceworkshop@gmail.com) or a Google Form; we keep
the form as `application.url` and the email in the note.
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
    Location,
    Offering,
    Organization,
    Price,
    Requirement,
    Schedule,
    Session,
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

BASE = "https://www.dart.theater"
PAGE = f"{BASE}/summer-intensive-berlin"
APPLY_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSeioTEztqjHiEIPUK7RcZ6GUeOX1VRXEidZGYv3VEAEMyI-Mg/viewform"
)
APPLY_EMAIL = "dartdanceworkshop@gmail.com"

ORG = Organization(
    name="DART Dance Company", slug="dart-dance-company", country="DE", city="Berlin"
)

# Wix injects zero-width spaces (ZWSP / ZWNJ / ZWJ / BOM) into the rendered text.
_ZERO_WIDTH = re.compile("[" + "".join(map(chr, (0x200B, 0x200C, 0x200D, 0xFEFF))) + "]")

VENUE = "DART Studios, Motzener Strasse 5, 12277 Marienfelde, Berlin"


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE, follow_redirects=True)
    resp.raise_for_status()
    offering = _build_offering(resp.text)
    return [offering] if offering is not None else []


def _build_offering(html: str) -> Offering | None:
    tree = _parse(html)
    text = _collapse(tree)

    sessions = _sessions(text)
    if not sessions:
        return None  # no dated weeks announced
    start = min(s.start for s in sessions if s.start)
    end = max(s.end for s in sessions if s.end)
    season = str(start.year)

    return Offering(
        id=f"dart-dance-company/summer-sensation-intensive-{season}",
        source=Source(provider="summer-sensation-intensive", url=PAGE, scrapedAt=now_utc()),
        title=f"Summer Sensation Intensive Berlin {season}",
        genres=_genres(text),
        organization=ORG,
        location=Location(venue=VENUE, city="Berlin", country="DE"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Berlin",
            sessions=sessions,
            notes=_schedule_note(text, season),
        ),
        teachers=_teachers(_spans(tree), text),
        prices=_prices(text),
        application=Application(
            url=APPLY_URL,
            requirements=_requirements(text),
            notes=(
                f"Apply by email to {APPLY_EMAIL} (CV plus the two YouTube videos) "
                "or via the Google Form. Places are limited; payment instructions "
                "follow acceptance."
            ),
        ),
    )


def _strip_zw(s: str) -> str:
    return _ZERO_WIDTH.sub("", s)


def _parse(html: str) -> HTMLParser:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return tree


def _collapse(tree: HTMLParser) -> str:
    raw = tree.body.text(separator=" ") if tree.body else ""
    return parse.clean(_strip_zw(raw))


def _spans(tree: HTMLParser) -> list[str]:
    """Each element's own text (no descendants), in document order.

    Wix renders the teacher roster as one `<span>` per name, so the names are
    only cleanly separable at the element boundary — collapsing the page glues
    them into one run. We read the per-element text and let `_teachers` pick the
    roster window out of it.
    """
    return [parse.clean(_strip_zw(node.text(deep=False))) for node in tree.css("span")]


# --- sessions: three weeks, "<d> - <d> <Month> <year>" ------------------------

# "3rd - 7th August 2026" — one month + year spanning both days, ordinals optional.
_WEEK = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s*[-–—]\s*(\d{1,2})(?:st|nd|rd|th)?\s+("
    + parse.MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _sessions(text: str) -> list[Session]:
    weeks = list(_WEEK.finditer(text))
    if not weeks:
        return []
    # The source mistypes later weeks' years; anchor every week to the first
    # week's year, since the block is one consecutive run (see docstring).
    anchor_year = int(weeks[0].group(4))
    out: list[Session] = []
    for i, m in enumerate(weeks, start=1):
        d1, d2, month_name, _year = m.groups()
        month = parse.MONTHS[month_name.lower()]
        start = date(anchor_year, month, int(d1))
        end = date(anchor_year, month, int(d2))
        out.append(Session(label=f"Week {i}", start=start, end=end))
    return out


def _schedule_note(text: str, season: str) -> str | None:
    # Flag the source typo only when it's actually present (some weeks dated a
    # different year than the anchor), so the note is faithful, not boilerplate.
    years = {m.group(4) for m in _WEEK.finditer(text)}
    if len(years) > 1:
        return (
            f"The source dates the later weeks {', '.join(sorted(years - {season}))} "
            f"(an apparent typo); all three weeks run consecutively in August {season}."
        )
    return None


# --- teachers: a confirmed seven-name roster ----------------------------------

# The roster sits, one name-span each, between the "following teachers" intro and
# the "WORKSHOP SCHEDULE" heading. A name-span is one-to-three capitalised words
# with no digits and none of the all-caps section words that surround it.
_NAME = re.compile(r"[A-ZÀ-Ý][\wÀ-ÿ.'’-]+(?:\s+[A-ZÀ-Ý][\wÀ-ÿ.'’-]+){1,2}")
_NOT_A_NAME = re.compile(
    r"REPERTOIRE|SCHEDULE|WEEK|COMPANY|DANCE|STRETCHING|INTENSIVE|BERLIN|STUDIOS|VIDEOS|FORM|POLICY",
)
# Kinga Varga is named "Artistic Director/DART Dance Company" in the schedule.
_DIRECTOR = re.compile(
    r"([A-ZÀ-Ý][\wÀ-ÿ.'’-]+(?:\s+[A-ZÀ-Ý][\wÀ-ÿ.'’-]+)+)\s*-\s*Artistic Director",
    re.IGNORECASE,
)


def _is_name(span: str) -> bool:
    return bool(_NAME.fullmatch(span)) and not _NOT_A_NAME.search(span.upper())


def _teachers(spans: list[str], text: str) -> list[Teacher]:
    try:
        intro = next(i for i, s in enumerate(spans) if "following teachers" in s.lower())
        schedule = next(i for i, s in enumerate(spans) if "WORKSHOP SCHEDULE" in s.upper())
    except StopIteration:
        return []
    director_m = _DIRECTOR.search(text)
    director = parse.clean(director_m.group(1)) if director_m else None
    out: list[Teacher] = []
    seen: set[str] = set()
    for span in spans[intro + 1 : schedule]:
        if not _is_name(span) or span in seen:
            continue
        seen.add(span)
        role = "Artistic Director" if span == director else None
        out.append(Teacher(name=span, role=role))
    return out


# --- genres: contemporary repertoire, no classical class ----------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("contemporary", ("contemporary",)),
    ("repertoire", ("repertoire",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["contemporary"])


# --- prices: "1 week - 595 Euros", "2 weeks - 995 Euros", … -------------------

_PRICE = re.compile(
    r"(\d+)\s*weeks?\s*[-–—]\s*(\d[\d.,]*)\s*Euros?",
    re.IGNORECASE,
)


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    for m in _PRICE.finditer(text):
        amount = parse.parse_amount(m.group(2))
        if amount is None:
            continue
        weeks = int(m.group(1))
        label = f"{weeks} week" + ("s" if weeks != 1 else "")
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=label,
                includes=["tuition"],
                notes="Includes the registration cost.",
            )
        )
    return prices


# --- requirements: a CV and two YouTube videos --------------------------------

_VIDEO_NOTE = (
    "Apply with a CV, a maximum five-minute improvisation video and a maximum "
    "ten-minute ballet video with four short centre exercises (tendus, "
    "pirouettes, petit allegro and grand allegro). Both videos must be uploaded "
    "to YouTube without a password."
)


def _requirements(text: str) -> list[Requirement]:
    low = text.lower()
    reqs: list[Requirement] = []
    if re.search(r"\bcv\b|resume", low):
        reqs.append(CVReq())
    if "improvisation" in low or "ballet video" in low:
        reqs.append(VideoReq(specificity="specific", description=_VIDEO_NOTE))
    return reqs
