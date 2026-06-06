"""Bolshoi Academy Tokyo Summer Intensive — Tokyo (JP), hosted by Russian Ballet
International (澁谷芸術企画).

This is a Bolshoi-branded summer intensive **run in Japan by a local host org**,
Russian Ballet International — not the Moscow academy itself. The host stages the
course with visiting Bolshoi Academy faculty, so the organization recorded here is
the local host and the Bolshoi connection lives on the teacher entry (an
affiliation) and in the schedule note, not as the running org.

API FIRST: the host runs **WordPress** (`/wp-json/` is live), and the program
page is also reachable as a page via `wp/v2/pages?slug=tokyo-program`. But its
body is WPBakery shortcode soup (`[vc_row]…`) wrapping the same copy that the
page already renders into static, server-side HTML — the full text (dates, ages,
fee, classes, faculty line) sits in the markup. So we read the rendered page text
directly (selectolax), the cleaner source.

PROXY: the host sits behind a **Cloudflare challenge** that blocks the CI runner's
datacenter IP (403) and which the proxy's auto/render tiers don't clear — only the
FlareSolverr `solve=1` tier does. So we force it via the `x-fetch-proxy-params`
header (inert on a direct fetch, e.g. local dev where the IP isn't blocked).

DISCOVERY: one dated edition — the AUGUST 17-22, 2026 Tokyo intensive. The page
lists two age groups (09/13 and 14/19+) that share the same dates, registration
fee and class list, so per the model's per-band rule this is **one Offering with
one `Session` per age group** (the age split lives on `Session`; folding the
Offering ageRange would lose the band boundary). The slug is year-stamped so the
id rolls forward when a new edition is posted.

BILINGUAL (EN + JP): parsed language-agnostically — the date span ("AUGUST 17-22,
2026") and the "$125" fee are read off the English line (the JP line "2026 年 8 月
17 ～ 22 日 / 登録料：125ドル" mirrors it), age bands off the numeric "09/13" /
"14/19+" tokens, classes/requirements off keyword matches that fire in either
language. Source free text is kept faithfully, never translated inline.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-06):
  - One Offering, two `Session`s (per-age-band split) with distinct ageRange;
    the open-ended "19+" band records only a min bound.
  - A USD registration fee ($125, non-refundable) — a registration/audition fee,
    not tuition, so emitted with no `includes` and the non-refundable terms noted.
  - A `video`/`unspecific` audition requirement: entry is "by audition only" via a
    video form OR in person, with no defined pose/clip brief stated.
  - The Bolshoi-faculty affiliation captured as a collective `Teacher` (no
    individual names are published) with an `Affiliation` to the Bolshoi Academy.
  - Genres matched against the published class list: classical, pointe,
    repertoire, character.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.fetch import PROXY_PARAMS_HEADER
from intensive_dance.models import (
    Affiliation,
    Application,
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

BASE = "https://www.russianballetinternational.com"
PAGE = f"{BASE}/tokyo-program/"
# Entry is "by audition only": the video-audition form or an in-person audition.
AUDITION_URL = f"{BASE}/auditions/video-auditions/"

# The local host that stages the intensive in Japan (not the Moscow academy).
ORG = Organization(
    name="Russian Ballet International",
    slug="russian-ballet-international",
    country="JP",
    city="Tokyo",
)

_APPLY_NOTE = (
    "Entry is by audition only: fill out the video-audition form or audition "
    "in person, pay the audition fee, then submit your video; accepted dancers "
    "receive an official acceptance letter with registration details."
)
# The visiting faculty are named only collectively ("full-time teachers of the
# Bolshoi Academy"), so we record the affiliation, not individual names.
_FACULTY_NOTE = "Taught by full-time teachers of the Bolshoi Ballet Academy (visiting faculty)."


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE, follow_redirects=True, headers={PROXY_PARAMS_HEADER: "solve=1"})
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    offering = _build_offering(resp.text)
    return [offering] if offering is not None else []


def _build_offering(html: str) -> Offering | None:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    start, end = _date_range(text)
    anchor = start or end
    if anchor is None:
        return None  # no dated edition parseable
    season = str(anchor.year)

    sessions = _sessions(text)
    return Offering(
        id=f"bolshoi-summer-intensive-tokyo/summer-intensive-{season}",
        source=Source(provider="bolshoi-summer-intensive-tokyo", url=PAGE, scrapedAt=now_utc()),
        title=f"Bolshoi Academy Tokyo Summer Intensive {season}",
        genres=_genres(text),
        ageRange=_offering_age_range(sessions),
        organization=ORG,
        location=Location(city="Tokyo", country="JP"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Asia/Tokyo",
            sessions=sessions,
            notes=_FACULTY_NOTE,
        ),
        teachers=_teachers(text),
        prices=_prices(text),
        application=Application(
            url=AUDITION_URL,
            requirements=_requirements(text),
            notes=_APPLY_NOTE,
        ),
    )


# --- dates --------------------------------------------------------------------
#
# A single English span on one line, year included: "AUGUST 17-22, 2026". Month
# name, two days, shared trailing year (the JP line "2026 年 8 月 17 ～ 22 日"
# mirrors it but is not needed).

_RANGE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})\s*[-–—]\s*(\d{1,2}),?\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    month = parse.MONTHS[m.group(1).lower()]
    year = int(m.group(4))
    return date(year, month, int(m.group(2))), date(year, month, int(m.group(3)))


# --- age bands → sessions -----------------------------------------------------
#
# The page lists two groups under "Age groups": "09/13" and "14/19+". The "/"
# separates the low and high bound of a band; a trailing "+" on the high bound
# means open-ended (record only the min). Each band becomes its own Session.

_AGE_BAND = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})(\+)?")


def _sessions(text: str) -> list[Session]:
    # Scope to the "Age groups" block so unrelated numbers (a fee, a phone) can't
    # masquerade as a band.
    block = _age_block(text)
    sessions: list[Session] = []
    for m in _AGE_BAND.finditer(block):
        low, high, open_ended = int(m.group(1)), int(m.group(2)), bool(m.group(3))
        if not (3 <= low <= 25 and low <= high <= 30):
            continue
        age_range: dict = {"min": low} if open_ended else {"min": low, "max": high}
        label = f"Ages {low}–{high}+" if open_ended else f"Ages {low}–{high}"
        sessions.append(Session(label=label, ageRange=age_range, notes=m.group(0)))
    return sessions


# "Age groups 09/13 14/19+ Classes …" — slice from the heading to the next
# section so only the band tokens are read.
_AGE_HEADING = re.compile(r"Age\s+groups", re.IGNORECASE)
_AGE_END = re.compile(r"Classes|クラス", re.IGNORECASE)


def _age_block(text: str) -> str:
    start = _AGE_HEADING.search(text)
    if not start:
        return ""
    rest = text[start.end() :]
    end = _AGE_END.search(rest)
    return rest[: end.start()] if end else rest


def _offering_age_range(sessions: list[Session]) -> dict | None:
    bounds = [s.age_range for s in sessions if s.age_range]
    if not bounds:
        return None
    age_range: dict = {"min": min(b["min"] for b in bounds)}
    # Only set a max when every band has one (an open-ended band leaves it open).
    if all("max" in b for b in bounds):
        age_range["max"] = max(b["max"] for b in bounds)
    return age_range


# --- prices: "Registration Fee: $125" — a USD, non-refundable registration fee
# (not tuition), so no `includes` and the terms kept as a note ------------------

_FEE = re.compile(r"Registration\s+Fee:?\s*\$\s*([\d,]+)", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    m = _FEE.search(text)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    return [
        Price(
            amount=amount,
            currency="USD",
            label="Registration fee",
            notes="Non-refundable; due upon registration, before the audition form.",
        )
    ]


# --- genres: matched against the published class list -------------------------
#
# "Ballet Technique, Pointe, Repertoire, Character Dance, and Bolshoi stretch
# class" — keyword-match the curriculum, not loose prose.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet technique", "バレエテクニック")),
    ("pointe", ("pointe", "ポアント", "ポワント")),
    ("repertoire", ("repertoire", "レパートリー")),
    ("character", ("character dance", "キャラクターダンス")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- teachers: the Bolshoi Academy faculty (collective; no names published) ----


def _teachers(text: str) -> list[Teacher]:
    if not re.search(r"teachers?\s+of\s+the\s+Bolshoi", text, re.IGNORECASE):
        return []
    return [
        Teacher(
            name="Bolshoi Ballet Academy faculty",
            role="Full-time teachers of the Bolshoi Ballet Academy (visiting faculty)",
            affiliations=[
                Affiliation(
                    organization="Bolshoi Ballet Academy",
                    slug="bolshoi-ballet-academy",
                    role="Full-time faculty",
                    current=True,
                )
            ],
        )
    ]


# --- requirements: "by audition only" — video form OR in person ----------------


def _requirements(text: str) -> list[Requirement]:
    low = text.lower()
    if "audition only" in low or "video audition" in low:
        # In-person OR video accepted, no defined pose/clip brief → unspecific.
        return [
            VideoReq(
                specificity="unspecific",
                description=(
                    "Audition required (in person or by video); no pose or clip brief is published."
                ),
            )
        ]
    return []
