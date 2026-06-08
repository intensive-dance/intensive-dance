"""Houston Ballet Academy (Ben Stevenson Academy) — summer programs — Houston, US.

API FIRST — none usable. houstonballet.org runs a custom CMS that 404s a
non-browser request to any path (including a probed `/wp-json/`), but serves the
real markup to a normal browser User-Agent (`fetch.make_client` already sends
one), so no proxy is needed — a plain fetch returns the full, server-rendered
HTML. There is no JSON API, ld+json `Event`, or feed; the program facts live as
labeled prose in the page bodies. So this is an HTML scrape (selectolax) of the
public summer pages, parsed from their collapsed plain text with labeled regexes
(markup-change-tolerant), not DOM position. The Academy's pages sit under
`/about/academy/summer-intensive-program/` (the `/academy/…` URLs in the brief
404 — the real tree is one level deeper, found via the sitemap).

DISCOVERY: Houston Ballet Academy runs several dated 2026 summer programs off one
hub page; two are in scope for a pre-professional ballet register, each its own
dated edition(s):
  - Summer Intensive Program (SIP) — one ~five-week edition, Levels 5-8, ages 12+,
    the flagship high-level intensive (6-8 hrs/day, six days/week). Dates live on
    its own page + the curriculum page; ages/levels on the five-week page; fees in
    the SIP section of the shared tuition page; the video-audition window on the
    audition page. → one Offering (`houston-ballet-academy/summer-intensive-program-{year}`).
  - Youth Summer Training Program (YSTP) — ages 7+, two separate ~two-week Sessions
    (distinct dates), five days/week. Each Session is its own Offering
    (`houston-ballet-academy/youth-summer-training-s{n}-{year}`) because they differ
    in dates; ages/audition shared, per-session tuition read from the YSTP table.
Out of scope, not emitted: the Preschool Summer Program (ages 2-7, recreational,
no audition), Children's Workshops (ages 4+, story-ballet weeks, no audition) and
the Adult Intensive (ages 18+, no audition) — the same recreational/adult cuts as
Boston's Summer Camps / Adult Dance Program.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08):
  - PRICES in USD, multiple per offering from labeled fee lines. SIP: tuition
    (tuition) + registration + health & wellness + a housing registration fee +
    the optional University of St. Thomas dorm (accommodation; the by-invitation
    CFD/MST rooms are omitted — not openly bookable). YSTP: the two per-session
    level-band tuitions (tuition) + a registration fee. Inclusions keyed off the
    label, not position; SIP fees are scoped to the SIP table so YSTP's own
    "Registration Fee: $75" can't bleed in.
  - DATES from a single year-stamped range ("June 20 – July 24, 2026") for SIP and
    two labeled year-stamped session ranges for YSTP ("Session 1: June 8 – 18,
    2026"), one regex covering the year-once and year-each phrasings.
  - AGES open-topped — "Ages 12+" (SIP) / "Ages 7+" (YSTP) → {min, max=None}; an
    Offering inherits the open upper bound.
  - GENRES from the SIP curriculum list (Ballet Technique/Pointe/Repertory/
    Variations/Contemporary/Character → classical+pointe+repertoire+contemporary+
    character; Modern→contemporary, Jazz/Musical Theater not register genres).
    YSTP states no syllabus → classical only.
  - REQUIREMENTS = VIDEO (unspecific): admission is by audition with an open
    in-person *or* recorded-video route (audition page), the ABT/Boston shape.
  - APPLICATION status/deadline (SIP): the video window "January 5 - February 15,
    2026" → deadline that date; status="closed" once it has passed.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    ApplicationStatus,
    Genre,
    Location,
    Offering,
    Organization,
    Price,
    PriceInclude,
    Schedule,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://www.houstonballet.org/about/academy/summer-intensive-program"
TZ = "America/Chicago"

SIP_URL = f"{BASE}/five-week-summer-intensive/"
CURRICULUM_URL = f"{BASE}/summer-curriculum-schedule/"
TUITION_URL = f"{BASE}/summer-tuition-and-fees/"
AUDITION_URL = f"{BASE}/sip-audition-tour2/"
YSTP_URL = f"{BASE}/youth-summer-training-program/"

ORG = Organization(
    name="Houston Ballet Academy",
    slug="houston-ballet-academy",
    country="US",
    city="Houston",
)
# Both programs run at the Academy's home studios.
LOCATION = Location(venue="Margaret Alkek Williams Center for Dance", city="Houston", country="US")

_AUDITION_NOTE = (
    "Admission is by audition. Dancers attend an in-person audition on the summer "
    "audition tour or, if unable to attend, submit a recorded video audition."
)


def scrape(client: httpx.Client) -> list[Offering]:
    sip = _fetch_text(client, SIP_URL)
    curriculum = _fetch_text(client, CURRICULUM_URL)
    tuition = _fetch_text(client, TUITION_URL)
    audition = _fetch_text(client, AUDITION_URL)
    ystp = _fetch_text(client, YSTP_URL)
    return _build_offerings(sip, curriculum, tuition, audition, ystp, date.today())


def _fetch_text(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    resp.raise_for_status()
    return _page_text(resp.text)


def _page_text(html: str) -> str:
    """Collapse an HTML page to whitespace-normalized plain text (scripts/styles dropped)."""
    tree = HTMLParser(html)
    for node in tree.css("style, script, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ") if tree.body else "")


def _build_offerings(
    sip: str, curriculum: str, tuition: str, audition: str, ystp: str, today: date
) -> list[Offering]:
    offerings: list[Offering] = []
    sip_offering = _build_sip(sip, curriculum, tuition, audition, today)
    if sip_offering is not None:
        offerings.append(sip_offering)
    offerings.extend(_build_ystp(ystp, tuition, today))
    return offerings


# --- dates --------------------------------------------------------------------
#
# Houston states a single fully-stamped range, with the start's year either
# omitted ("June 8 – 18, 2026") or repeated ("July 27 – August 7, 2026"), and the
# end month sometimes elided when it matches the start ("June 20 – July 24" keeps
# both). One regex covers all three: a month + day, an optional end month, an end
# day, and the trailing year (inherited by the start).
_RANGE = re.compile(
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})\s*[–-]\s*"
    r"(?:(" + parse.MONTHALT + r")\s+)?(\d{1,2}),?\s*(20\d\d)",
    re.IGNORECASE,
)


def _range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if m is None:
        return None, None
    m1, d1, m2, d2, year = m.groups()
    y = int(year)
    start = date(y, parse.MONTHS[m1.lower()], int(d1))
    end_month = parse.MONTHS[(m2 or m1).lower()]
    return start, date(y, end_month, int(d2))


# "Session 1: June 8 – 18, 2026" — the labeled per-session span (YSTP).
_SESSION = re.compile(
    r"Session\s+(\d)\s*:\s*"
    r"(" + parse.MONTHALT + r")\s+(\d{1,2})\s*[–-]\s*"
    r"(?:(" + parse.MONTHALT + r")\s+)?(\d{1,2}),?\s*(20\d\d)",
    re.IGNORECASE,
)


# --- ages ---------------------------------------------------------------------

# "Ages 12+" / "(AGES 7+)" — an open-topped floor.
_AGE_OPEN = re.compile(r"\bAges?\s+(\d{1,2})\s*\+", re.IGNORECASE)


def _age_open(text: str) -> dict | None:
    m = _AGE_OPEN.search(text)
    return {"min": int(m.group(1)), "max": None} if m else None


# --- Summer Intensive Program -------------------------------------------------


def _build_sip(
    sip: str, curriculum: str, tuition: str, audition: str, today: date
) -> Offering | None:
    start, end = _range(sip)
    if start is None:
        return None
    year = start.year
    deadline = _sip_deadline(audition, year)
    return Offering(
        id=f"houston-ballet-academy/summer-intensive-program-{year}",
        source=Source(provider=ORG.slug, url=SIP_URL, scrapedAt=now_utc()),
        title="Summer Intensive Program",
        genres=_sip_genres(curriculum),
        level=["intermediate", "advanced", "pre-professional"],
        ageRange=_age_open(sip),
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(season=str(year), start=start, end=end, timezone=TZ),
        prices=_sip_prices(tuition),
        application=Application(
            status=_status(deadline, today),
            deadline=deadline,
            url=AUDITION_URL,
            requirements=[VideoReq(specificity="unspecific", description=_AUDITION_NOTE)],
        ),
    )


# SIP curriculum: classical-ballet led, with pointe, repertory/variations,
# contemporary (incl. modern) and character classes. Jazz/Musical Theater aren't
# register genres, so they add nothing. Matched against the curriculum class list.
_SIP_GENRES: list[tuple[Genre, tuple[str, ...]]] = [
    ("pointe", ("pointe",)),
    ("repertoire", ("repertory", "repertoire", "variations")),
    ("contemporary", ("contemporary", "modern")),
    ("character", ("character",)),
]


def _sip_genres(text: str) -> list[Genre]:
    return ["classical", *parse.match_genres(text, _SIP_GENRES, default=[])]


# SIP fees sit in the "SUMMER INTENSIVE PROGRAM (AGES 12+)" section of the shared
# tuition page; scope the search to it so YSTP's own "Registration Fee: $75"
# doesn't leak in. The by-invitation CFD/MST dorms are omitted (not openly
# bookable); only the open University of St. Thomas dorm is emitted.
_SIP_SECTION = re.compile(
    r"SUMMER INTENSIVE PROGRAM \(AGES 12\+\)(.*?)ADULT INTENSIVE", re.IGNORECASE | re.S
)
_SIP_PRICES: list[tuple[str, re.Pattern, list[PriceInclude]]] = [
    ("Tuition", re.compile(r"\bTuition:\s*\$([\d,]+)", re.IGNORECASE), ["tuition"]),
    ("Registration fee", re.compile(r"\bRegistration Fee:\s*\$([\d,]+)", re.IGNORECASE), []),
    (
        "Health & Wellness fee",
        re.compile(r"Health & Wellness Fee:\s*\$([\d,]+)", re.IGNORECASE),
        [],
    ),
    (
        "Housing registration fee",
        re.compile(r"Housing Registration Fee:\s*\$([\d,]+)", re.IGNORECASE),
        [],
    ),
    (
        "University of St. Thomas housing (optional)",
        re.compile(r"University of St\. Thomas \(UST\) Housing[^$]*\$([\d,]+)", re.IGNORECASE),
        ["accommodation"],
    ),
]


def _sip_prices(tuition: str) -> list[Price]:
    section = _SIP_SECTION.search(tuition)
    return _prices_from(section.group(1) if section else "", _SIP_PRICES)


# "submissions will be accepted January 5 - February 15, 2026" — the video-audition
# window for the upcoming summer; its close is the application deadline.
_SIP_VIDEO_WINDOW = re.compile(
    r"accepted\s+(?:" + parse.MONTHALT + r")\s+\d{1,2}\s*[–-]\s*"
    r"(" + parse.MONTHALT + r")\s+(\d{1,2}),\s*(20\d\d)",
    re.IGNORECASE,
)


def _sip_deadline(audition: str, year: int) -> date | None:
    m = _SIP_VIDEO_WINDOW.search(audition)
    if m is None:
        return None
    # Trust the window only when it names the SIP's own cycle year (the audition
    # page rolls to the next year's tour once the current window closes).
    if int(m.group(3)) != year:
        return None
    return date(int(m.group(3)), parse.MONTHS[m.group(1).lower()], int(m.group(2)))


def _status(deadline: date | None, today: date) -> ApplicationStatus | None:
    return "closed" if deadline is not None and today > deadline else None


# --- Youth Summer Training Program --------------------------------------------


def _build_ystp(ystp: str, tuition: str, today: date) -> list[Offering]:  # noqa: ARG001
    age = _age_open(ystp)
    genres: list[Genre] = ["classical"]
    section = _YSTP_SECTION.search(tuition)
    session_prices = _ystp_session_prices(section.group(1) if section else "")

    offerings: list[Offering] = []
    for m in _SESSION.finditer(ystp):
        num = m.group(1)
        start = date(int(m.group(6)), parse.MONTHS[m.group(2).lower()], int(m.group(3)))
        end_month = parse.MONTHS[(m.group(4) or m.group(2)).lower()]
        end = date(int(m.group(6)), end_month, int(m.group(5)))
        offerings.append(
            Offering(
                id=f"houston-ballet-academy/youth-summer-training-s{num}-{start.year}",
                source=Source(provider=ORG.slug, url=YSTP_URL, scrapedAt=now_utc()),
                title=f"Youth Summer Training Program — Session {num}",
                genres=genres,
                ageRange=age,
                organization=ORG,
                location=LOCATION,
                schedule=Schedule(season=str(start.year), start=start, end=end, timezone=TZ),
                prices=session_prices.get(num, []),
                application=Application(
                    url=YSTP_URL,
                    requirements=[VideoReq(specificity="unspecific", description=_AUDITION_NOTE)],
                ),
            )
        )
    return offerings


_YSTP_SECTION = re.compile(
    r"YOUTH SUMMER TRAINING PROGRAM \(AGES 7\+\)(.*?)SUMMER INTENSIVE PROGRAM",
    re.IGNORECASE | re.S,
)
# Each level band lists its Session 1 / Session 2 / combined tuition in one row:
# "Level 1/Level 2 $675.00 $750.00 $1,425.00".
_YSTP_TUITION_ROW = re.compile(
    r"(Level 1/Level 2|Level 3/Level 4/Intermediate/Advanced)\s+"
    r"\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s+\$[\d,]+\.\d{2}",
)
_YSTP_REG_FEE = re.compile(r"Registration Fee:\s*\$([\d,]+)", re.IGNORECASE)


def _ystp_session_prices(section: str) -> dict[str, list[Price]]:
    """Per-session tuition for each level band, keyed by session number ("1"/"2").

    The page tabulates each band's Session 1 and Session 2 tuition separately, so
    a one-session Offering carries that session's column for both bands, plus the
    flat YSTP registration fee.
    """
    columns: dict[str, list[Price]] = {"1": [], "2": []}
    for m in _YSTP_TUITION_ROW.finditer(section):
        band = m.group(1)
        for num, raw in (("1", m.group(2)), ("2", m.group(3))):
            amount = parse.parse_amount(raw)
            if amount is not None:
                columns[num].append(
                    Price(
                        amount=amount,
                        currency="USD",
                        label=f"Tuition — {band}",
                        includes=["tuition"],
                    )
                )
    reg = _YSTP_REG_FEE.search(section)
    if reg is not None:
        amount = parse.parse_amount(reg.group(1))
        if amount is not None:
            for num in columns:
                columns[num].append(
                    Price(amount=amount, currency="USD", label="Registration fee", includes=[])
                )
    return columns


# --- shared -------------------------------------------------------------------


def _prices_from(text: str, table: list[tuple[str, re.Pattern, list[PriceInclude]]]) -> list[Price]:
    prices: list[Price] = []
    for label, pattern, includes in table:
        m = pattern.search(text)
        if m is None:
            continue
        amount = parse.parse_amount(m.group(1))
        if amount is None:
            continue
        prices.append(Price(amount=amount, currency="USD", label=label, includes=list(includes)))
    return prices
