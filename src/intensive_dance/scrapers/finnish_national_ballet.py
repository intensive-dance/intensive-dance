"""Finnish National Ballet — International Summer Intensive — Helsinki, FI.

API FIRST: oopperabaletti.fi runs WordPress and the program lives on a single
page whose full body is served in `content.rendered` over the REST API
(`/wp-json/wp/v2/pages?slug=international-summer-intensive`) — no HTML scraping of
the live site. The body is Gutenberg blocks (clean `<h2>`/`<h3>` headings, `<p>`
blocks), so `wp.parse()` turns it into heading-keyed sections we read by name.
`robots.txt` disallows `/wp-json/` for *indexing* only; the API still serves.
The site is bilingual (Polylang EN/FI); we pin the English page by slug.

DISCOVERY: the page advertises two distinct offerings, each its own `Offering`
(`finnish-national-ballet/{slug}-2026`) because they differ in audience, dates,
fee and requirements:
  - `international-summer-intensive` — the 6th-edition youth intensive, ages
    12-22, 20-25 Jul 2026, €900 (early €800) incl. a warm lunch.
  - `ballet-in-bloom` — a 2026-new adult-amateur track, 20-24 Jul 2026 evenings,
    €450 (early €375), classes only.
The slug is year-stamped because the body names the cycle ("6th edition", "New in
2026"). EXCLUDED: the free, Finland-only, video-audition "Kesäakatemia" lives on a
separate FI page and is out of scope for an international register.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-05):
  - REQUIREMENTS = mixed per offering. The youth intensive accepts three intake
    routes (pro-school: recommendation letter; company: CV; private school: video
    link) but *every* applicant attaches a headshot + a 1st-arabesque photo — so
    it emits `photos` (defined-poses) + `video` (unspecific) + `cv`. Ballet in
    Bloom explicitly requires only a headshot and no video → `headshot`.
  - PRICES in EUR, two per offering (full + early-bird), `includes` keyed off the
    "includes ... a warm lunch" sentence (meals) vs "all classes" (tuition only).
  - TEACHERS: 8 named faculty, each an `<h3>` over a `<br>`-separated `<p>`
    (country · affiliation · teaching subject · CV link); the teaching subject is
    their role in this intensive.
  - DATES + APPLICATION window both stated explicitly ("20 to 25 July 2026",
    "Application dates are 15 December 2025 – 30 April 2026"), so application
    status is derived against today.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    ApplicationStatus,
    CVReq,
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
    VideoReq,
    now_utc,
)

BASE = "https://oopperabaletti.fi"
SLUG = "international-summer-intensive"
TZ = "Europe/Helsinki"

ORG = Organization(
    name="Finnish National Ballet",
    slug="finnish-national-ballet",
    country="FI",
    city="Helsinki",
)

# Both offerings share the venue; Ballet in Bloom runs in the same building.
LOCATION = Location(venue="Finnish National Opera and Ballet", city="Helsinki", country="FI")

_PHOTO_POSES = ["headshot", "1st arabesque"]


def scrape(client: httpx.Client) -> list[Offering]:
    page = wp.fetch_page(client, SLUG, base=BASE)
    if page is None:
        return []
    return _build_offerings(page, date.today())


def _build_offerings(page: dict, today: date) -> list[Offering]:
    url = page["link"]
    rendered = page["content"]["rendered"]
    content = wp.parse(rendered)
    apply_url = _apply_url(rendered)
    opens, deadline = _application_window(content)

    offerings = [
        _summer_intensive(content, url, apply_url, opens, deadline, today),
        _ballet_in_bloom(content, url, apply_url, opens, deadline, today),
    ]
    return [o for o in offerings if o is not None]


# --- offerings ---------------------------------------------------------------


def _summer_intensive(
    content: wp.Content,
    url: str,
    apply_url: str | None,
    opens: date | None,
    deadline: date | None,
    today: date,
) -> Offering | None:
    body = _section_text(content, "summer intensive")
    start, end = _dates(body)
    if start is None or (end is not None and end < today):
        return None

    # Every applicant attaches the two photos; private-school applicants add a
    # video link, company members a CV — so the union of all three intake routes.
    requirements: list[Requirement] = [
        PhotosReq(
            specificity="defined-poses",
            poses=list(_PHOTO_POSES),
            notes="Headshot photo and a picture in 1st arabesque, required of all applicants.",
        ),
        VideoReq(
            specificity="unspecific",
            description=(
                "Private-school applicants submit a video link (YouTube or Vimeo): "
                "3-5 min barre, 3-5 min centre (adagio, pirouettes, allegro), some "
                "pointe work for women, optional classical variation."
            ),
        ),
        CVReq(),
    ]

    return Offering(
        id="finnish-national-ballet/international-summer-intensive-2026",
        source=Source(provider=ORG.slug, url=url, scrapedAt=now_utc()),
        title="International Summer Intensive of the Finnish National Ballet",
        genres=_genres(body),
        ageRange=_age_range(body),
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(season=str(start.year), start=start, end=end, timezone=TZ),
        teachers=_teachers(content),
        prices=_prices(content, "Summer Intensive", includes_lunch=True),
        application=Application(
            status=_status(opens, deadline, today),
            opensAt=opens,
            deadline=deadline,
            url=apply_url,
            requirements=requirements,
        ),
    )


def _ballet_in_bloom(
    content: wp.Content,
    url: str,
    apply_url: str | None,
    opens: date | None,
    deadline: date | None,
    today: date,
) -> Offering | None:
    body = _section_text(content, "New in 2026", "More info about Ballet in Bloom")
    start, end = _dates(body)
    if start is None or (end is not None and end < today):
        return None

    return Offering(
        id="finnish-national-ballet/ballet-in-bloom-2026",
        source=Source(provider=ORG.slug, url=url, scrapedAt=now_utc()),
        title="Ballet in Bloom — Finnish National Ballet Summer Intensive",
        genres=_genres(body),
        # Adult amateur track — no age band stated, open level by design.
        level=["open"],
        organization=ORG,
        location=LOCATION,
        schedule=Schedule(season=str(start.year), start=start, end=end, timezone=TZ),
        teachers=_teachers(content),
        prices=_prices(content, "Ballet in Bloom", includes_lunch=False),
        application=Application(
            status=_status(opens, deadline, today),
            opensAt=opens,
            deadline=deadline,
            url=apply_url,
            # The page is explicit: only a headshot, no video / recommendation.
            requirements=[HeadshotReq()],
            notes="A minimum of five years of prior ballet training is recommended.",
        ),
    )


# --- sections ----------------------------------------------------------------


def _section_text(content: wp.Content, *headings: str) -> str:
    """Concatenated text of the sections whose heading starts with any given.

    Anchored on the heading *start* rather than `Content.find`'s loose substring:
    the body sits under "summer intensive" and "New in 2026: Ballet in Bloom", and
    we don't want the "welcome to the … Summer Intensive" intro leaking in.
    """
    wants = [h.lower() for h in headings]
    parts = [
        s.text() for s in content.sections if s.heading.strip().lower().startswith(tuple(wants))
    ]
    return "\n".join(p for p in parts if p)


_LYYTI = re.compile(r"https://www\.lyyti\.fi/reg/[^\s\"'<>]+")


def _apply_url(rendered: str) -> str | None:
    """The Lyyti registration link, a Gutenberg `<a>` button (not a WPBakery btn)."""
    match = _LYYTI.search(rendered)
    return match.group(0) if match else None


# --- dates -------------------------------------------------------------------
#
# Both spans are written day-from-to with a single trailing "Month Year":
# "from 20 to 25 July 2026" and "20–24 July 2026".

_RANGE = re.compile(
    rf"(\d{{1,2}})\s*(?:to|[–-])\s*(\d{{1,2}})\s+({parse.MONTHALT})\s+(\d{{4}})",
    re.IGNORECASE,
)


def _dates(text: str) -> tuple[date | None, date | None]:
    match = _RANGE.search(text)
    if not match:
        return None, None
    d1, d2, month_name, year = match.groups()
    month = parse.MONTHS[month_name.lower()]
    return date(int(year), month, int(d1)), date(int(year), month, int(d2))


# --- ages --------------------------------------------------------------------

_AGE = re.compile(r"aged\s+(\d{1,2})\s*[–-]\s*(\d{1,2})")


def _age_range(text: str) -> dict | None:
    return parse.extract_age_range(text, _AGE)


# --- application window ------------------------------------------------------

_WINDOW = re.compile(
    rf"Application dates are\s+(\d{{1,2}})\s+({parse.MONTHALT})\s+(\d{{4}})"
    rf"\s*[–-]\s*(\d{{1,2}})\s+({parse.MONTHALT})\s+(\d{{4}})",
    re.IGNORECASE,
)


def _application_window(content: wp.Content) -> tuple[date | None, date | None]:
    match = _WINDOW.search(_section_text(content, "how to apply"))
    if not match:
        return None, None
    d1, m1, y1, d2, m2, y2 = match.groups()
    opens = date(int(y1), parse.MONTHS[m1.lower()], int(d1))
    deadline = date(int(y2), parse.MONTHS[m2.lower()], int(d2))
    return opens, deadline


def _status(opens: date | None, deadline: date | None, today: date) -> ApplicationStatus | None:
    if opens is None or deadline is None:
        return None
    if today < opens:
        return "upcoming"
    if today > deadline:
        return "closed"
    return "open"


# --- genres ------------------------------------------------------------------
#
# Matched against the curriculum sentence, not loose prose. Street / urban dance
# is taught (Akim Bakhtaoui) but has no enum value in a ballet register, so it is
# silently out of scope — only the mapped styles below are emitted.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet")),
    ("pointe", ("pointe",)),
    ("repertoire", ("repertoire", "repertory")),
    ("character", ("character",)),
    ("contemporary", ("contemporary",)),
    ("neoclassical", ("neoclassical",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- prices ------------------------------------------------------------------
#
# The tuition section lists each offering as "<Offering>: €NNN" and an
# "Early bird campaign: €NNN" line directly under it.

_FEE = re.compile(r"€\s*([\d.,]+)")


def _prices(content: wp.Content, label: str, *, includes_lunch: bool) -> list[Price]:
    lines = [line.strip() for line in _section_text(content, "tuition").split("\n")]
    includes: list[PriceInclude] = ["tuition", "meals"] if includes_lunch else ["tuition"]
    prices: list[Price] = []
    capture = False
    for line in lines:
        low = line.lower()
        if low.startswith(f"{label.lower()}:"):
            capture = True
            prices.append(_price(line, "Tuition", includes))
        elif capture and low.startswith("early bird"):
            prices.append(_price(line, "Early bird", includes))
            break
        elif capture:
            # A non-early-bird line ends this offering's block.
            break
    return prices


def _price(line: str, label: str, includes: list[PriceInclude]) -> Price:
    match = _FEE.search(line)
    amount = parse.parse_amount(match.group(1)) if match else None
    notes = "VAT included" if "vat" in line.lower() else None
    return Price(
        amount=amount if amount is not None else 0.0,
        currency="EUR",
        label=label,
        includes=list(includes),
        notes=notes,
    )


# --- teachers ----------------------------------------------------------------


def _teachers(content: wp.Content) -> list[Teacher]:
    """Each faculty `<h3>` (name) over a `<br>`-separated `<p>`.

    Lines: country · affiliation/title · teaching subject · "Read more …". The
    teaching subject (3rd line) is the role in this intensive.
    """
    block = content.find_block("faculty")
    if block is None:
        return []
    _, subs = block
    teachers: list[Teacher] = []
    for section in subs:
        if section.level != 3 or not section.nodes:
            continue
        lines = wp.clean_node_lines(section.nodes[0])
        role = parse.clean(lines[2]) if len(lines) >= 3 else None
        teachers.append(Teacher(name=parse.clean(section.heading), role=role))
    return teachers
