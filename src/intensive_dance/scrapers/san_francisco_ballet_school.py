"""San Francisco Ballet School — Summer Session — San Francisco, US.

API FIRST — WordPress, and (unlike the SAB/ABT trap) the program bodies arrive
intact in `content.rendered` over the REST API — no HTML render or JS needed.
The one wrinkle: sfballet.org's WAF 403s our non-browser UA on a *direct* fetch
(even of `/wp-json/`), so the request goes through the fetch proxy, which fetches
server-side with a Chrome UA and clears the block (auto tier, no render). We read
two WP pages by slug under `/wp-json/wp/v2/pages`:

  - `summer-auditions-audition-tour` — the authoritative current-cycle source.
    Its heading names the cycle ("2026 Summer Session"); a one-line-per-session
    block gives the dated span + age band ("Session 1 : Ages 12–15, June 15 –
    July 10"); a TUITION block gives per-session tuition + optional housing
    ("Summer Session 1 (ages 12–15) tuition is $3,495 … housing is an additional
    $3,495. Housing includes two meals daily."); plus the audition/video-
    application policy and the video window (→ deadline).
  - `summer-programs` (the landing page) — its per-session paragraph carries the
    curriculum (→ genres) and the level wording ("advanced", "pre-professional
    track") the audition page omits. The date wording there ("as of July 1,
    2025") is a stale age-reference clause, not the schedule — we take dates from
    the audition page only.

DISCOVERY: SFB School runs its student summer intensive as two distinct, dated
*Sessions* (one Offering each, `san-francisco-ballet-school/summer-session-{n}-{year}`):
  - Session I — four weeks, ages 12–15.
  - Session II — four weeks, ages 15–18, an advanced / pre-professional track.
They differ in dates, ages, fees and curriculum, so they are not folded. The
year-less session date line is stamped with the year from the "20xx Summer
Session" heading. Out of scope and not emitted: the adult Summer Workshop, the
open-enrolment Summer Ballet Classes (ages 2–13, no audition), the Pianist
Workshop, and the free Boys & Girls Clubs Summer Dance Camp (Hip Hop/Bhangra/…).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - PRICES in USD, two per offering: tuition (tuition) and the optional
    supervised housing (accommodation+meals — "Housing includes two meals daily").
  - GENRES per session from the curriculum prose only — Session II's
    "contemporary repertoire" adds `contemporary` that Session I lacks.
  - LEVELS read from the landing-page session wording ("advanced",
    "pre-professional track"); Session I states no level, so it stays empty.
  - REQUIREMENTS = VIDEO (unspecific): "Admission … is by audition or invitation";
    applicants who cannot attend a live audition apply by video (DanceApply).
  - DEADLINE from the video-application window ("between January 10–February 15,
    2026") — the close date, stamped with its stated year.
  - TEACHERS: none. A school-wide `sfb_faculty` roster exists but nothing ties a
    faculty member to a specific Session, so `teachers` stays empty (Joffrey's case).
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://www.sfballet.org"
TZ = "America/Los_Angeles"
AUDITION_SLUG = "summer-auditions-audition-tour"
LANDING_SLUG = "summer-programs"

ORG = Organization(
    name="San Francisco Ballet School",
    slug="san-francisco-ballet-school",
    country="US",
    city="San Francisco",
)
LOCATION = Location(venue="San Francisco Ballet", city="San Francisco", country="US")

_AUDITION_NOTE = (
    "Admission is by audition or invitation from the artistic leadership. Dancers "
    "may attend a live audition on the audition tour, or — if unable to attend — "
    "apply by video via DanceApply. Registration requires an identity photo and "
    "proof of age."
)


def scrape(client: httpx.Client) -> list[Offering]:
    audition = wp.fetch_page(client, AUDITION_SLUG, base=BASE)
    landing = wp.fetch_page(client, LANDING_SLUG, base=BASE)
    if audition is None:
        return []
    audition_text = _page_text(audition["content"]["rendered"])
    landing_text = _page_text(landing["content"]["rendered"]) if landing else ""
    return _build_offerings(audition_text, landing_text, audition["link"], date.today())


def _page_text(rendered: str) -> str:
    """Collapse a WP `content.rendered` body to whitespace-normalized plain text."""
    tree = HTMLParser(rendered)
    for node in tree.css("style, script"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ") if tree.body else "")


# --- per-session discovery ----------------------------------------------------

# "2026 Summer Session" — the cycle heading; supplies the year for the year-less
# session date lines.
_SEASON = re.compile(r"\b(20\d\d)\s+Summer Session", re.IGNORECASE)
# "Session 1 : Ages 12–15, June 15 – July 10" — one line per session, no year.
_SESSION = re.compile(
    r"Session\s+([12])\s*:?\s*Ages\s*(\d{1,2})\s*[–-]\s*(\d{1,2}),\s*"
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})\s*[–-]\s*(" + parse.MONTHALT + r")\s+(\d{1,2})",
    re.IGNORECASE,
)
# "Summer Session 1 (ages 12–15) tuition is $3,495 and optional … housing is an
# additional $3,495. Housing includes two meals daily."
_TUITION = re.compile(
    r"Summer Session\s+([12])\b.*?tuition is\s*\$([\d,]+)"
    r"(?:.*?additional\s*\$([\d,]+)\.\s*Housing includes two meals)?",
    re.IGNORECASE,
)
# Video-application window close → deadline. "between January 10–February 15, 2026".
_VIDEO_WINDOW = re.compile(
    r"between\s+(?:" + parse.MONTHALT + r")\s+\d{1,2}\s*[–-]\s*"
    r"(" + parse.MONTHALT + r")\s+(\d{1,2}),\s*(20\d\d)",
    re.IGNORECASE,
)


def _build_offerings(
    audition_text: str, landing_text: str, url: str, today: date
) -> list[Offering]:  # noqa: ARG001
    year = _season_year(audition_text)
    if year is None:
        return []
    deadline = _deadline(audition_text)
    tuitions = _tuitions(audition_text)

    offerings: list[Offering] = []
    for match in _SESSION.finditer(audition_text):
        num = match.group(1)
        age_min, age_max = int(match.group(2)), int(match.group(3))
        start = date(year, parse.MONTHS[match.group(4).lower()], int(match.group(5)))
        end = date(year, parse.MONTHS[match.group(6).lower()], int(match.group(7)))
        prose = _session_prose(landing_text, num)

        offerings.append(
            Offering(
                id=f"san-francisco-ballet-school/summer-session-{num}-{year}",
                source=Source(provider="san-francisco-ballet-school", url=url, scrapedAt=now_utc()),
                title=f"Summer Session {_roman(num)}",
                genres=_genres(prose),
                level=_levels(prose),
                ageRange={"min": age_min, "max": age_max},
                organization=ORG,
                location=LOCATION,
                schedule=Schedule(season=str(year), start=start, end=end, timezone=TZ),
                prices=tuitions.get(num, []),
                application=Application(
                    deadline=deadline,
                    url=url,
                    requirements=[VideoReq(specificity="unspecific", description=_AUDITION_NOTE)],
                ),
            )
        )
    return offerings


def _season_year(text: str) -> int | None:
    match = _SEASON.search(text)
    return int(match.group(1)) if match else None


def _roman(num: str) -> str:
    return {"1": "I", "2": "II"}.get(num, num)


def _deadline(text: str) -> date | None:
    match = _VIDEO_WINDOW.search(text)
    if not match:
        return None
    return date(int(match.group(3)), parse.MONTHS[match.group(1).lower()], int(match.group(2)))


# --- prices -------------------------------------------------------------------


def _tuitions(text: str) -> dict[str, list[Price]]:
    """Map session number → its [tuition, housing] Price list from the TUITION block."""
    by_session: dict[str, list[Price]] = {}
    for match in _TUITION.finditer(text):
        num, tuition_raw, housing_raw = match.group(1), match.group(2), match.group(3)
        prices: list[Price] = []
        tuition = parse.parse_amount(tuition_raw)
        if tuition is not None:
            prices.append(
                Price(amount=tuition, currency="USD", label="Tuition", includes=["tuition"])
            )
        if housing_raw:
            housing = parse.parse_amount(housing_raw)
            if housing is not None:
                prices.append(
                    Price(
                        amount=housing,
                        currency="USD",
                        label="Supervised housing",
                        includes=["accommodation", "meals"],
                    )
                )
        by_session[num] = prices
    return by_session


# --- genres / levels (from the landing-page session paragraph) ----------------

# Genres are matched against the curriculum prose only — Session II names
# "contemporary repertoire", Session I does not. Both teach classical/pointe/
# repertoire; classical is the always-present base.
_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("pointe", ("pointe",)),
    ("contemporary", ("contemporary",)),
    ("repertoire", ("repertoire", "repertory")),
]

_LEVEL_WORDS: list[tuple[Level, str]] = [
    ("advanced", "advanced"),
    ("pre-professional", "pre-professional"),
]


def _session_prose(landing_text: str, num: str) -> str:
    """The landing page's paragraph for SUMMER SESSION {roman}, or '' if absent."""
    roman = _roman(num)
    pattern = re.compile(
        r"SUMMER SESSION " + roman + r"\b(.*?)"
        r"(?=SUMMER SESSION|SUMMER AUDITIONS|ADULT SUMMER|SUMMER PIANIST|SUMMER DANCE CAMP|$)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(landing_text)
    return match.group(1) if match else ""


def _genres(prose: str) -> list[Genre]:
    found = parse.match_genres(prose, _GENRE_KEYWORDS, default=[])
    # Classical is the always-present base for the ballet intensive; prepend it.
    return ["classical", *[g for g in found if g != "classical"]]


def _levels(prose: str) -> list[Level]:
    low = prose.lower()
    return [level for level, word in _LEVEL_WORDS if word in low]
