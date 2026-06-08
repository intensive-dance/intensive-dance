"""Royal Winnipeg Ballet School — Summer programs — Winnipeg, Canada.

API FIRST — clean WordPress REST, no HTML scrape and no proxy. rwb.org runs
WordPress (`/wp-json/` is 200, reachable on a direct fetch). The school's
programs are a `lesson` custom post type, each record carrying the structured
detail in **ACF fields** (`event_start_date`/`event_end_date`/`event_age_range`/
`event_price`/`event_registration_deadline`/`event_location`/`event_available`)
plus a `content.rendered` prose body that lists the class disciplines. We pull
the summer programs via the `session-type=summer` taxonomy term, read dates/ages/
fees/deadline from the ACF block, and match genres against the curriculum prose.

DISCOVERY: the `session-type=summer` term returns four `lesson`s, of which two
are dated, ballet-core **student** summer intensives — one `Offering` each,
keyed `royal-winnipeg-ballet-school/{slug}-{year}`:
  - `summer-session` — the Professional Division's three-week summer intensive
    (also the second phase of the professional-program audition), ages 10+.
  - `dance-intensive` — a two-week Recreational Division summer intensive,
    ages 10-18, CAD 1150.
The other two summer `lesson`s are out of scope and dropped: `adult-summer-dance`
is a twice-a-week adult drop-in series (ages 16+, not a student intensive), and
`summer-dance-day-camp` is a play-based children's day camp (ages 3-10, taught in
tap / hip hop / musical theatre alongside ballet). The scope decision is per
slug because the discipline mix alone can't separate the day camp (which also
teaches ballet) from a ballet intensive — see `_SUMMER_INTENSIVES`.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - PRICES in CAD — Dance Intensive's "$1150" tuition (accommodation / meals are
    stated as extra and uncosted, so they aren't emitted). Summer Session leaves
    `event_price` empty (price on acceptance) → no Price.
  - REQUIREMENTS = PHOTOS (freeform). Dance Intensive asks each applicant to
    upload two dance photos with the brief "provided with the link" (no defined
    poses) → `photos`/`freeform`. Summer Session is itself the in-person audition
    phase and states no submitted material → requirements `[]` (not stated).
  - APPLICATION STATUS + DEADLINE from ACF — Dance Intensive carries a
    `20260615` deadline and `event_available: false` (closed); Summer Session has
    `event_available: true` (open) and no deadline.
  - AGE RANGE open-topped — "10+" → `{"min": 10, "max": None}`; "10-18" → bounded.
  - GENRES read from the curriculum prose only (ballet, pointe, character,
    modern/contemporary, variations, repertoire, pas de deux) — never the marquee
    blurb — so jazz (no Genre enum) and out-of-scope words don't leak.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    ApplicationStatus,
    Genre,
    Location,
    Offering,
    Organization,
    PhotosReq,
    Price,
    Requirement,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.rwb.org"
TZ = "America/Winnipeg"
SESSION_TYPE = "session-type"  # the WP taxonomy whose "summer" term lists summer programs

ORG = Organization(
    name="Royal Winnipeg Ballet School",
    slug="royal-winnipeg-ballet-school",
    country="CA",
    city="Winnipeg",
)

# The two summer `lesson` slugs that are dated, ballet-core student intensives.
# The other summer lessons (adult-summer-dance, summer-dance-day-camp) are out of
# scope (adult drop-in / children's play camp) — see the module docstring.
_SUMMER_INTENSIVES = ("summer-session", "dance-intensive")


def scrape(client: httpx.Client) -> list[Offering]:
    term_id = _summer_term_id(client)
    params: dict = {
        "_fields": "id,slug,link,title,content,acf",
        "orderby": "id",
        "order": "asc",
    }
    if term_id is not None:
        params[SESSION_TYPE] = term_id
    records = wp.fetch_all(client, "lesson", base=BASE, params=params)

    today = date.today()
    offerings: list[Offering] = []
    for record in records:
        if record["slug"] not in _SUMMER_INTENSIVES:
            continue
        offering = _build_offering(record, today)
        if offering is not None:
            offerings.append(offering)
    offerings.sort(key=lambda o: o.id)
    return offerings


def _summer_term_id(client: httpx.Client) -> int | None:
    """The `session-type` term id whose name is "summer", or None if not found."""
    for term_id, name in wp.fetch_terms(client, SESSION_TYPE, base=BASE).items():
        if name.strip().lower() == "summer":
            return term_id
    return None


def _build_offering(record: dict, today: date) -> Offering | None:  # noqa: ARG001
    acf = record.get("acf") or {}
    start = _acf_date(acf.get("event_start_date"))
    end = _acf_date(acf.get("event_end_date"))
    if start is None:
        return None  # without a dated edition there is nothing to register
    season = str(start.year)

    title = wp.plain_text(record["title"]["rendered"])
    curriculum = wp.plain_text(record["content"]["rendered"])
    url = record["link"]

    return Offering(
        id=f"royal-winnipeg-ballet-school/{record['slug']}-{season}",
        source=Source(provider="royal-winnipeg-ballet-school", url=url, scrapedAt=now_utc()),
        title=title,
        genres=_genres(curriculum),
        ageRange=_age_range(acf.get("event_age_range")),
        organization=ORG,
        location=_location(acf.get("event_location")),
        schedule=Schedule(season=season, start=start, end=end, timezone=TZ),
        prices=_prices(acf.get("event_price")),
        application=Application(
            status=_status(acf.get("event_available")),
            deadline=_acf_date(acf.get("event_registration_deadline")),
            url=url,
            requirements=_requirements(curriculum),
        ),
    )


# --- ACF dates ---------------------------------------------------------------
#
# ACF event dates are bare YYYYMMDD strings ("20260706"); a null/empty value
# means "not stated".

_ACF_DATE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")


def _acf_date(raw: object) -> date | None:
    if not isinstance(raw, str):
        return None
    match = _ACF_DATE.match(raw.strip())
    if not match:
        return None
    year, month, day = (int(g) for g in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


# --- ages --------------------------------------------------------------------
#
# `event_age_range` is "10-18" (bounded) or "10+" (open-topped, null max).

_AGE_RANGE = re.compile(r"(\d{1,2})\s*-\s*(\d{1,2})")
_AGE_OPEN = re.compile(r"(\d{1,2})\s*\+")


def _age_range(raw: object) -> dict | None:
    if not isinstance(raw, str):
        return None
    bounded = _AGE_RANGE.search(raw)
    if bounded:
        return {"min": int(bounded.group(1)), "max": int(bounded.group(2))}
    open_top = _AGE_OPEN.search(raw)
    if open_top:
        return {"min": int(open_top.group(1)), "max": None}
    return None


# --- genres ------------------------------------------------------------------
#
# Match against the curriculum prose only (it names each class discipline). Jazz
# has no Genre enum, so it simply doesn't map; out-of-scope camp words (tap, hip
# hop) never reach a kept offering because the day camp is dropped by slug.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet", "classical")),
    ("pointe", ("pointe",)),
    ("character", ("character",)),
    ("contemporary", ("contemporary", "modern")),
    ("repertoire", ("repertoire", "variations", "pas de deux", "choreography")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- location ----------------------------------------------------------------


def _location(raw: object) -> Location:
    venue = parse.clean(raw) if isinstance(raw, str) else None
    return Location(venue=venue or None, city="Winnipeg", country="CA")


# --- prices ------------------------------------------------------------------
#
# `event_price` is a "$1150" tuition figure (CAD) or empty (price on acceptance).
# Accommodation / meals are stated as extra and uncosted, so only tuition emits.

_PRICE = re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)")


def _prices(raw: object) -> list[Price]:
    if not isinstance(raw, str):
        return []
    match = _PRICE.search(raw)
    if not match:
        return []
    amount = parse.parse_amount(match.group(1))
    if amount is None:
        return []
    return [Price(amount=amount, currency="CAD", label="Tuition", includes=["tuition"])]


# --- application status & requirements ---------------------------------------


def _status(available: object) -> ApplicationStatus | None:
    """`event_available` is a bool: True → open, False → closed; None → not stated."""
    if available is True:
        return "open"
    if available is False:
        return "closed"
    return None


def _requirements(curriculum: str) -> list[Requirement]:
    """Two dance photos, brief supplied later (no defined poses) → freeform photos.

    Only emitted when the page states the photo step; the audition-phase Summer
    Session names no submitted material, so its requirements stay `[]`.
    """
    low = curriculum.lower()
    if "dance photos" in low or "two dance photo" in low:
        return [
            PhotosReq(
                specificity="freeform",
                notes=(
                    "Applicants upload two dance photos after applying; the photo "
                    "brief is provided with the upload link."
                ),
            )
        ]
    return []
