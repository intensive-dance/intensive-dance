"""ART of – Ballet Summer Course (Oleg Klymyuk) — its Zürich + Madrid editions.

API FIRST: none. ART of runs a hand-built PHP site (the per-city subdomains
`zurich.art-of.net` / `madrid.art-of.net`) with no content API, but every page is
server-rendered — the full text (dates, ages, prices, faculty, education plan) is
in the static HTML, so a plain `make_client()` fetch suffices, no JS render needed
(verified live 2026-06).

DISCOVERY: the two subdomains are the **same organisation, two city editions**
(same director Oleg Klymyuk, same Zürich mailing address) — Zürich and Madrid run
on different dates, ages, venues and currencies, so we emit **one `Offering` per
city** off a single scraper, keyed by city. Each city's data is split across a few
sub-pages (`general_information`, `teachers`, `education-plan`), all fetched here.

WHAT THE PAGES GIVE US (verified live 2026-06):
  - DATES: a "3rd - 15th August 2026" / "13th - 25th July 2026" landing-page range.
  - AGES: a "minimum age … is 10/14 years" floor (open-ended upper bound).
  - PRICES (CHF in Zürich, EUR in Madrid): the Complete Course at 700/week &
    1200/two-weeks tuition, plus a professional-dancer discounted tier
    (500/850). Per-week extras (coaching, media) are noted, not priced as the
    course fee.
  - GENRES: read from the per-city Education Plan curriculum headings (classical,
    pointe, repertoire, neoclassical, contemporary via the Forsythe
    Improvisation Technologies module), not the marketing prose.
  - FACULTY: a named per-city roster (e.g. Leanne Benjamin in Zürich) with each
    teacher's stated former-role line. Distinct rosters per city, so kept per
    Offering.
  - REQUIREMENTS: the photo audition — the application form plus a portrait
    (headshot) and two full-body shots in named dance positions (1st arabesque
    90°, sauté 2nd) → `photos`/`defined-poses` + `headshot`.
  - APPLICATION: a stated deadline (28 Jul 2026 Zürich, 3 Jul 2026 Madrid); the
    course is the William Forsythe tie ("with the kind support of William
    Forsythe").

NOTE: the landing pages also carry a "partner summer school of the Prix de
Lausanne" line. That claim is unverified, so it is deliberately **not** recorded
anywhere in the emitted data.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    Genre,
    HeadshotReq,
    Location,
    Offering,
    Organization,
    PhotosReq,
    Price,
    PriceInclude,
    Requirement,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

PROVIDER = "art-of-zurich"  # the register slug this scraper is filed under

ORG = Organization(
    name="ART of – Ballet Summer Course",
    slug=PROVIDER,
    country="CH",
    city="Zürich",
)


@dataclass(frozen=True)
class _Edition:
    """One city edition and the sub-pages it is assembled from."""

    key: str  # offering-slug stem, e.g. "zurich"
    base: str
    city: str
    country: str
    timezone: str
    currency: str  # ISO 4217, local to the edition
    general_info: str
    education_plan: str
    teachers: str = "teachers/coaches_teachers.php"


_EDITIONS = (
    _Edition(
        key="zurich",
        base="https://zurich.art-of.net",
        city="Zürich",
        country="CH",
        timezone="Europe/Zurich",
        currency="CHF",
        general_info="general_information/belletintensive_information.php",
        education_plan="education-plan/zurich_education_plan.php",
    ),
    _Edition(
        key="madrid",
        base="https://madrid.art-of.net",
        city="Madrid",
        country="ES",
        timezone="Europe/Madrid",
        currency="EUR",
        general_info="general_information/balletintensive_general_information.php",
        education_plan="education-plan/madrid_education_plan.php",
    ),
)


def scrape(client: httpx.Client) -> list[Offering]:
    offerings: list[Offering] = []
    for ed in _EDITIONS:
        landing = _text(client, ed.base + "/")
        general = _text(client, f"{ed.base}/{ed.general_info}")
        education = _text(client, f"{ed.base}/{ed.education_plan}")
        teachers_html = _html(client, f"{ed.base}/{ed.teachers}")
        offering = _build_offering(ed, landing, general, education, teachers_html)
        if offering is not None:
            offerings.append(offering)
    offerings.sort(key=lambda o: o.id)
    return offerings


def _text(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    resp.raise_for_status()
    return _readable(resp.text)


def _html(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    resp.raise_for_status()
    return resp.text


def _readable(page_html: str) -> str:
    tree = HTMLParser(page_html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _build_offering(
    ed: _Edition, landing: str, general: str, education: str, teachers_html: str
) -> Offering | None:
    start, end = _date_range(landing)
    if start is None or end is None:
        return None  # no dated edition announced
    season = str(end.year)
    apply_url = f"{ed.base}/"

    return Offering(
        id=f"{PROVIDER}/{ed.key}-summer-course-{season}",
        source=Source(provider=PROVIDER, url=apply_url, scrapedAt=now_utc()),
        title=f"ART of – Ballet Summer Course {ed.city} {season}",
        genres=_genres(education),
        ageRange=_age_range(general),
        organization=ORG,
        location=Location(venue=_venue(general), city=ed.city, country=ed.country),
        schedule=Schedule(season=season, start=start, end=end, timezone=ed.timezone),
        teachers=_teachers(teachers_html),
        prices=_prices(general, ed.currency),
        application=Application(
            deadline=_deadline(general),
            url=apply_url,
            requirements=_requirements(general),
            notes=_APPLY_NOTE,
        ),
    )


_APPLY_NOTE = (
    "Application is by photo audition: the completed form, a portrait photo and "
    "two full-body shots in dance attire. The course takes place with the kind "
    "support of William Forsythe."
)


# --- dates: landing-page "3rd - 15th August 2026" (one trailing year) ----------

_RANGE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s*[-–—]\s*(\d{1,2})(?:st|nd|rd|th)?\s+("
    + parse.MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    d1, d2, month, year = m.groups()
    mo = parse.MONTHS[month.lower()]
    return date(int(year), mo, int(d1)), date(int(year), mo, int(d2))


# --- ages: "minimum age … is 10 years" (open-ended upper bound) ----------------

_AGE_MIN = re.compile(r"minimum age[^.]*?\bis\s+(\d{1,2})\s+years", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    m = _AGE_MIN.search(text)
    return {"min": int(m.group(1))} if m else None


# --- venue: the "Course location <venue> <address>" line -----------------------

# The venue name is the text between "Course location" and the street address;
# both editions begin the address with a street name + number or a quoted name.
_VENUE = re.compile(
    r"Course location\s+(.+?)\s+(?:Calle|Pfingstweidstrasse|Building|\(Building)",
    re.IGNORECASE,
)


def _venue(text: str) -> str | None:
    m = _VENUE.search(text)
    return parse.clean(m.group(1)) if m else None


# --- prices: "One week: 700 CHF / Euro", "Two weeks: 1200 …" --------------------

# The Complete Course is the course fee; the professional-dancer tier is a
# discount on the same course. Only the first (standard) week/two-week pair is
# emitted; per-30-min coaching and media extras are intentionally not course fees.
_FEE = re.compile(
    r"(One week|Two weeks)\s*:\s*(\d[\d.,]*)\s*(?:CHF|Euro|EUR|€)",
    re.IGNORECASE,
)


def _prices(text: str, currency: str) -> list[Price]:
    # The page lists the full Complete Course block first, then the discounted
    # professional-dancer block; the first two matches are the standard fees.
    matches = _FEE.findall(text)
    prices: list[Price] = []
    includes: list[PriceInclude] = ["tuition"]
    for label, raw in matches[:2]:
        amount = parse.parse_amount(raw)
        if amount is None:
            continue
        prices.append(
            Price(
                amount=amount,
                currency=currency,
                label=f"Complete Course — {parse.clean(label.lower())}",
                includes=includes,
            )
        )
    return prices


# --- application deadline ------------------------------------------------------

# The deadline is phrased two ways across the editions: Zürich spells it out
# ("…deadline for ART of - Ballet Summer Course Zurich is July 28th, 2026") and
# Madrid labels it ("Application Deadline: July 3rd, 2026"). We try the
# Summer-Course-specific sentence first so the Madrid pattern can't swallow the
# Scholarship deadline ("Scholarship Application Deadline: March …"), which we
# never want — hence the negative lookbehind on the generic form.
_DATE = r"(" + parse.MONTHALT + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})"
_DEADLINE_SUMMER = re.compile(
    r"Summer Course[^.]*?\bis\s+" + _DATE,
    re.IGNORECASE,
)
_DEADLINE_GENERIC = re.compile(
    r"(?<!Scholarship )Application Deadline[^A-Za-z0-9]*?" + _DATE,
    re.IGNORECASE,
)


def _deadline(text: str) -> date | None:
    m = _DEADLINE_SUMMER.search(text) or _DEADLINE_GENERIC.search(text)
    if not m:
        return None
    month, day, year = m.groups()
    return date(int(year), parse.MONTHS[month.lower()], int(day))


# --- genres: read from the Education Plan curriculum headings ------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical ballet", "men and women technique")),
    ("pointe", ("pointe",)),
    ("repertoire", ("repertoire",)),
    ("neoclassical", ("neo -classical", "neo-classical", "neoclassical")),
    ("contemporary", ("improvisation technologies", "forsythe improvisation")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- requirements: a photo audition with named full-body poses -----------------

# "two full body shots in a dance position … (example: 1st arabesque 90°, sauté -
# 2nd feet position) and your portrait picture".
_POSES = re.compile(r"\(example:\s*([^)]+)\)", re.IGNORECASE)


def _requirements(text: str) -> list[Requirement]:
    low = text.lower()
    reqs: list[Requirement] = []
    if "portrait" in low:
        reqs.append(HeadshotReq())
    if "full body shot" in low or "full body shots" in low:
        poses: list[str] = []
        m = _POSES.search(text)
        if m:
            poses = [parse.clean(p) for p in re.split(r",\s*", m.group(1)) if parse.clean(p)]
        reqs.append(
            PhotosReq(
                specificity="defined-poses",
                poses=poses,
                notes="Two full-body photos in dance attire in a dance position, "
                "plus a portrait photo.",
            )
        )
    return reqs


# --- faculty: per-city "<strong>NAME</strong>" + "<em><strong>role</strong>" ---

# Each teacher block is `<p><strong>NAME</strong></p>` followed by an italic
# role line, on a stable per-city Teachers page.
_TEACHER = re.compile(
    r"<strong>\s*([A-ZÁÉÍÓÚÜÑÖ][A-ZÁÉÍÓÚÜÑÖ \-'.]{2,40})\s*</strong>\s*</p>\s*"
    r"<p>\s*<em>\s*<strong>\s*(.+?)\s*</strong>\s*</em>",
    re.IGNORECASE,
)
_NOT_NAMES = {"en", "de", "es"}


def _teachers(teachers_html: str) -> list[Teacher]:
    teachers: list[Teacher] = []
    seen: set[str] = set()
    for raw_name, raw_role in _TEACHER.findall(teachers_html):
        name = _detag(raw_name).title()
        if not name or name.lower() in _NOT_NAMES or name in seen:
            continue
        seen.add(name)
        teachers.append(Teacher(name=name, role=_detag(raw_role) or None))
    return teachers


def _detag(fragment: str) -> str:
    """Strip tags, decode HTML entities (&amp;, &nbsp;) and collapse whitespace."""
    return parse.clean(html.unescape(re.sub(r"<[^>]+>", "", fragment)))
