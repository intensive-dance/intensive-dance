"""The Royal Ballet School — first scraper.

API FIRST: RBS runs on WordPress and exposes a public REST API, so the core
fields come straight from JSON — no HTML scraping of the live site. The body is
WPBakery shortcode markup, cleaned and sectioned by `intensive_dance.wp`.

DISCOVERY: RBS runs *many* intensives (UK Summer, Los Angeles, Livorno, Hong
Kong, …) and re-dates the same WordPress pages each cycle. Rather than hardcode a
list, we fetch the children of the "Intensive Courses" page. We keep them all:
cancelled courses are tagged `lifecycle="cancelled"` (not dropped) so families
still find them, and past cycles stay too (greyed in the UI, derived from dates).
A newly-opened cycle or a brand-new location is picked up automatically.

One `Offering` per program. Offering ids are `{providerSlug}/{pageSlug}-{season}`
(e.g. `royal-ballet-school/uk-summer-intensive-2026`), keeping year-over-year
cycles distinct and diffable.

SCOPE FILTER — long-term programmes: RBS occasionally lists multi-month
programmes that span several weekends across 5–6 months (e.g. the Livorno
Special Training Programme: four weekends spread from Oct 2026 to Apr 2027,
schedule.start → schedule.end = 176 days). These are not short-term intensives
and are out of scope per the project's scope definition. Any offering whose
overall schedule span (end − start) exceeds MAX_SPAN_DAYS (45) is dropped.
The threshold sits well above the longest genuine intensive (the UK Summer
Intensive is ~31 days) and well below the shortest long-term programme seen so
far (176 days), so there is ample headroom in both directions. The rule is
applied after building the Offering so the full schedule is available; past
short intensives are always kept (IDR-24 — "past" is a consumer concern).

Requirements are PHOTOS ONLY — RBS assesses on photo submissions, no video and
no in-person audition. The required positions are published as age-banded
*diagrams* on the photograph-requirements page, not as named poses, so we emit
`photos` with `specificity="defined-poses"` and an empty `poses` list, keeping
the raw guidance + page URL in `notes`. (Use a video-requiring house such as
Joffrey / ABT to exercise the `video` branch of the requirements union.)

Course fees live in a table on a shared fees page (the WooCommerce `wc/v3`
namespace is enabled but does not expose these as products); the per-program
application fee and ancillary fees are inline on each program page.

TEACHERS: none emitted. RBS names no individual faculty on the intensive pages —
they credit "the School's artistic faculty", "Artistic Director", and "guest
teachers" generically, with nothing to attribute to a person. So `teachers` is
left empty here; exercise the `Teacher`/`Affiliation` models with a house that
publishes a named roster (e.g. Joffrey / ABT).

WHAT THIS SCRAPER EXERCISES: WordPress REST children fetch · WPBakery section
parse · `photos`/`defined-poses` requirements · inline price parsing
(mixed-currency, £/€/$) · table price parsing (FEE_TABLES) · per-country dollar
resolution · session parsing (week/short/student/weekend/city-date shapes) ·
`lifecycle="cancelled"` · long-term scope filter · verified live 2026-06-08.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    Gender,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    PhotosReq,
    Price,
    PriceInclude,
    Schedule,
    Session,
    Source,
    now_utc,
)

BASE = "https://www.royalballetschool.org.uk"
INTENSIVE_COURSES_SLUG = "intensive-courses"
FEES_SLUG = "intensive-courses-fees"

# Offerings whose overall schedule span (end − start) exceeds this threshold are
# long-term programmes, not short-term intensives, and are out of scope.  The UK
# Summer Intensive (~31 days) is the longest genuine intensive seen so far; the
# shortest long-term programme seen is 176 days — so 45 days gives ample margin.
MAX_SPAN_DAYS = 45

ORG = Organization(
    name="The Royal Ballet School", slug="royal-ballet-school", country="GB", city="London"
)

# Programs whose course fees live on the shared fees page (heading → its table)
# rather than inline on the program page. Most programs price inline.
FEE_TABLES = {"uk-summer-intensive": "Summer Intensive fees"}


def scrape(client: httpx.Client) -> list[Offering]:
    root = wp.fetch_page(client, INTENSIVE_COURSES_SLUG, base=BASE)
    if root is None:
        return []
    fees_page = wp.fetch_page(client, FEES_SLUG, base=BASE)
    fees = wp.parse(fees_page["content"]["rendered"]) if fees_page else None

    today = date.today()
    offerings = [
        o
        for record in wp.fetch_children(client, root["id"], base=BASE)
        for o in [_build_offering(record, fees, today)]
        if not _is_long_term(o)
    ]
    offerings.sort(key=lambda o: o.id)
    return offerings


def _build_offering(record: dict, fees: wp.Content | None, today: date) -> Offering:
    """Parse one program page into an Offering.

    A cancelled course is kept and tagged `lifecycle="cancelled"` (not dropped),
    so families still find it; ended cycles are kept too — "past" is derived from
    `schedule.end < today`, not stored.
    """
    slug = record["slug"]
    base_title = record["title"]["rendered"].strip()
    content = wp.parse(record["content"]["rendered"])

    cancelled = "cancel" in slug.lower() or "cancel" in base_title.lower()

    blob = " ".join(section.text() for section in content.sections)
    dates_text = content.text("Dates")
    start, end, season = _date_range(dates_text) if dates_text else (None, None, _year(blob))
    title = _title(base_title, season)

    photo_url = _absolute(content.link("photograph"))
    requirement_notes = content.text("Requirements")
    # Keep the Requirements blurb only when it actually describes the photos (poses,
    # positions, portrait). Otherwise it's generic application prose (deadlines,
    # eligibility) that pollutes the PhotosReq notes — drop it.
    if requirement_notes and not re.search(
        r"photo|image|positio|pose|portrait|arabesque", requirement_notes, re.IGNORECASE
    ):
        requirement_notes = None
    photos = PhotosReq(
        specificity="defined-poses",
        notes=_join(
            requirement_notes,
            "Required positions are published as age-banded diagrams "
            f"on the photograph-requirements page: {photo_url}"
            if photo_url
            else None,
        ),
    )

    application = _application(
        content.find_block("Application deadline", "Applications", "Bookings"),
        url=_absolute(content.link("apply", "book")),
        requirements=[photos],
    )

    location_section = content.find("Location", "Venue")
    location_text = location_section.text() if location_section else ""
    city, country, timezone = _place(location_text)

    # "Fees" holds the application fee; course tiers may be in a sibling
    # "Course fees" subsection (e.g. uk-spring-intensive has both).
    fees_text = "\n".join(filter(None, [content.text("Fees"), content.text("Course fees")]))
    prices = _inline_prices(fees_text, _dollar_currency(country))
    fee_table = FEE_TABLES.get(slug)
    if fee_table and fees:
        section = fees.find(fee_table)
        if section and section.table() is not None:
            prices += _table_prices(section.table())

    sessions = _sessions(content, season)
    # When no "Dates" section is present (e.g. Autumn Intensives, which uses
    # city-heading / date-heading pairs), derive the overall span from sessions.
    if start is None and sessions:
        dated = [s for s in sessions if s.start and s.end]
        if dated:
            start = min(s.start for s in dated)
            end = max(s.end for s in dated)

    return Offering(
        id=f"royal-ballet-school/{slug}-{season}",
        source=Source(provider="royal-ballet-school", url=record["link"], scrapedAt=now_utc()),
        title=title,
        genres=_genres(blob),
        lifecycle="cancelled" if cancelled else "scheduled",
        lifecycleNote=base_title if cancelled else None,
        level=_levels(blob),
        ageRange=_age_range(content.text("Eligibility")),
        organization=ORG,
        location=Location(
            venue=_venue(location_section),
            city=city,
            country=country,
            online=True if "online" in f"{slug} {base_title} {location_text}".lower() else None,
        ),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone=timezone,
            sessions=sessions,
            notes=dates_text or None,
        ),
        application=application,
        prices=prices,
    )


# --- scope filter ---


def _is_long_term(offering: Offering) -> bool:
    """True when the offering's schedule span exceeds MAX_SPAN_DAYS.

    Uses schedule.start / schedule.end when both are set; returns False
    (keep) when either is absent, since undated offerings can't be classified
    as long-term by span alone.
    """
    sched = offering.schedule
    if sched is None or sched.start is None or sched.end is None:
        return False
    return (sched.end - sched.start).days > MAX_SPAN_DAYS


# --- parsing helpers ---

_DATE = re.compile(r"(\d{1,2})\s+(" + parse.MONTHALT + r")(?:\s+(\d{4}))?", re.IGNORECASE)
# A short range like "21-25 July", "6 – Friday 10 July" or "15 and 16 November"
# (shared month; year explicit or inherited). The leading day omits the month —
# _DATE only sees the trailing `DD Month`, so callers add d1 back from here.
_SHORT = re.compile(
    r"(\d{1,2})\s*(?:[-–]|and|&)\s*(?:[A-Za-z]+\s+)?(\d{1,2})\s+(" + parse.MONTHALT + r")"
    r"(?:\s+(\d{4}))?",
    re.IGNORECASE,
)
# Money in either order: symbol-prefixed ("£48", "€390") or word-suffixed
# ("390 euros"), since RBS prices its overseas programs in local currency.
_MONEY = re.compile(
    r"(?P<sym>[£€$])\s*(?P<sym_amt>[\d,]+(?:\.\d+)?)"
    r"|(?P<word_amt>[\d,]+(?:\.\d+)?)\s*(?P<word>euros?|eur|pounds?|gbp|dollars?|usd)\b",
    re.IGNORECASE,
)
_CURRENCY_SYMBOL = {"£": "GBP", "€": "EUR"}
_CURRENCY_WORD = {
    "euro": "EUR",
    "eur": "EUR",
    "pound": "GBP",
    "gbp": "GBP",
    "dollar": "USD",
    "usd": "USD",
}
# `$` is ambiguous — RBS prices overseas programs in local currency, so resolve it
# from the program's country rather than assuming USD (Hong Kong → HKD, etc.).
_DOLLAR_CURRENCY = {"US": "USD", "HK": "HKD", "SG": "SGD", "AU": "AUD", "CA": "CAD", "NZ": "NZD"}
_AGE = re.compile(r"aged\s+(\d{1,2})\s*(?:[-–]\s*(\d{1,2}))?", re.IGNORECASE)
_YEAR = re.compile(r"\b(20\d{2})\b")


def _dollar_currency(country: str | None) -> str:
    return _DOLLAR_CURRENCY.get(country or "", "USD")


def _money(match: re.Match, dollar_currency: str = "USD") -> tuple[float, str]:
    if sym := match.group("sym"):
        currency = dollar_currency if sym == "$" else _CURRENCY_SYMBOL[sym]
        return float(match.group("sym_amt").replace(",", "")), currency
    word = match.group("word").lower().rstrip("s")
    return float(match.group("word_amt").replace(",", "")), _CURRENCY_WORD[word]


def _year(text: str) -> str:
    match = _YEAR.search(text)
    return match.group(1) if match else "unknown"


def _title(base_title: str, season: str) -> str:
    # Strip a trailing 4-digit year from the base title before appending the
    # season, so pages that already embed the year (e.g. "Online Spring
    # Intensive 2022") don't produce "Online Spring Intensive 2022 2022".
    base_stripped = re.sub(r"\s+\d{4}$", "", base_title)
    return f"{base_stripped} {season}".strip()


def _date_range(text: str) -> tuple[date | None, date | None, str]:
    """Earliest start / latest end across every `DD Month [YYYY]` in `text`.

    Day-month tokens that omit a year inherit the cycle's year (the single
    4-digit year present in the section), which is how RBS writes ranges like
    "21 July – 21 August 2026".
    """
    tokens = _DATE.findall(text)
    if not tokens:
        return None, None, _year(text)

    years = {int(y) for _, _, y in tokens if y}
    year = max(years) if years else None
    if year is None:
        return None, None, _year(text)

    dates = [date(int(y) if y else year, parse.MONTHS[m.lower()], int(d)) for d, m, y in tokens]
    # A range's leading day shares the trailing token's month ("3-7 April",
    # "15 and 16 November"); _DATE saw only the trailing day, so add d1 back.
    for d1, _d2, m, y in _SHORT.findall(text):
        dates.append(date(int(y) if y else year, parse.MONTHS[m.lower()], int(d1)))
    return min(dates), max(dates), str(year)


def _deadline(text: str) -> date | None:
    match = re.search(r"clos\w*[^.]*?(\d{1,2}\s+[A-Za-z]+\s+\d{4})", text, re.IGNORECASE)
    if not match:
        return None
    start, end, _ = _date_range(match.group(1))
    return start


_RELEVANT = re.compile(r"open|clos|deadline|appl|booking", re.IGNORECASE)


def _status(text: str):
    low = text.lower()
    if "closed" in low:
        return "closed"
    if "now open" in low or "now accepting" in low or "applications are open" in low:
        return "open"
    if "opens" in low or "will open" in low:
        return "upcoming"
    return None


def _application(block, *, url, requirements) -> Application:
    """Build the Application from a booking section and its subsections.

    RBS states the cycle state under `<h6>` children ("Selective course →
    Applications are now closed"), so we fold the relevant subsection lines in
    and lift the closed/open state into the structured `status` field rather
    than leaving it buried in `notes`.
    """
    primary_text = ""
    lines: list[str] = []
    if block:
        section, subs = block
        primary_text = section.text()
        lines.append(primary_text)
        lines += [line for sub in subs for line in sub.text().split("\n") if _RELEVANT.search(line)]
    notes = "\n".join(line for line in lines if line.strip()) or None
    return Application(
        status=_status(notes or ""),
        deadline=_deadline(primary_text),
        url=url,
        requirements=requirements,
        notes=notes,
    )


def _age_range(text: str) -> dict | None:
    bounds: list[int] = []
    for low, high in _AGE.findall(text):
        bounds.append(int(low))
        if high:
            bounds.append(int(high))
    if not bounds:
        return None
    return {"min": min(bounds), "max": max(bounds)}


# City + ISO country + IANA timezone, keyed by a place name in the venue address.
# Reference data, not a program gate — discovery still decides which programs run;
# an unlisted venue degrades to (None, derived-country, None).
_PLACES: list[tuple[str, str, str, str]] = [
    ("los angeles", "Los Angeles", "US", "America/Los_Angeles"),
    ("covent garden", "London", "GB", "Europe/London"),
    ("richmond", "London", "GB", "Europe/London"),
    ("london", "London", "GB", "Europe/London"),
    ("livorno", "Livorno", "IT", "Europe/Rome"),
    ("bangkok", "Bangkok", "TH", "Asia/Bangkok"),
    ("tokyo", "Tokyo", "JP", "Asia/Tokyo"),
    ("hong kong", "Hong Kong", "HK", "Asia/Hong_Kong"),
    ("singapore", "Singapore", "SG", "Asia/Singapore"),
    ("madrid", "Madrid", "ES", "Europe/Madrid"),
]
_COUNTRY_NAMES = {
    "united states": "US",
    "united kingdom": "GB",
    "thailand": "TH",
    "japan": "JP",
    "hong kong": "HK",
    "singapore": "SG",
    "korea": "KR",
    "italy": "IT",
    "spain": "ES",
}
_UK_POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b")
_US_ZIP = re.compile(r"\b[A-Z]{2}\s+\d{5}\b")


def _place(text: str) -> tuple[str | None, str | None, str | None]:
    low = text.lower()
    for needle, city, country, timezone in _PLACES:
        if needle in low:
            return city, country, timezone
    return None, _country(text), None


def _venue(section: wp.Section | None) -> str | None:
    """A tidy one-line venue: address lines joined by commas, venues by ` · `.

    Recovers `<br>`-separated address lines (collapsed by plain `.text()`) and
    drops the stray spaces WPBakery leaves before punctuation around links.
    """
    if section is None:
        return None
    blocks = [", ".join(wp.clean_node_lines(node)) for node in section.nodes]
    return " · ".join(block for block in blocks if block) or None


def _country(text: str) -> str | None:
    low = text.lower()
    for name, code in _COUNTRY_NAMES.items():
        if name in low:
            return code
    if _US_ZIP.search(text):
        return "US"
    if _UK_POSTCODE.search(text):
        return "GB"
    return None


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical", "ballet technique")),
    ("neoclassical", ("neoclassical",)),
    ("contemporary", ("contemporary",)),
    ("character", ("character",)),
    ("repertoire", ("repertoire",)),
    ("pointe", ("pointe",)),
]


def _genres(blob: str) -> list[Genre]:
    # RBS teaches classical ballet exclusively, so a sparse page (e.g. an
    # international masterclass announcement that names no style) still describes
    # classical training — default to classical rather than emit a genre-less
    # Offering. Other styles are only added when the page actually names them.
    return parse.match_genres(blob, _GENRE_KEYWORDS, default=["classical"])


# Level is only emitted when the page states it. RBS intensives are organized by
# age, not by level, so this is typically empty for them — but the parser is
# generic so level-stating houses (Joffrey/ABT) populate it for free.
_LEVELS: list[tuple[Level, str]] = [
    ("beginner", r"\bbeginner"),
    ("intermediate", r"\bintermediate"),
    ("advanced", r"\badvanced"),
    ("pre-professional", r"pre[\s-]professional"),
    ("professional", r"(?<!pre[\s-])\bprofessional"),
    ("open", r"\ball levels\b|\bopen level\b"),
]


def _levels(blob: str) -> list[Level]:
    low = blob.lower()
    return [level for level, pattern in _LEVELS if re.search(pattern, low)]


def _amount(text: str) -> float | None:
    match = _MONEY.search(text)
    return _money(match)[0] if match else None


def _includes(text: str) -> list[PriceInclude]:
    low = text.lower()
    if "application" in low or "coaching" in low or "session" in low:
        return []
    includes: list[PriceInclude] = ["tuition"]
    if "residential-catering" in low or ("residential" in low and "non-residential" not in low):
        includes += ["accommodation", "meals"]
    elif "catering" in low or "full board" in low:
        includes += ["meals"]
    return includes


def _inline_prices(text: str, dollar_currency: str = "USD") -> list[Price]:
    """Fees written as prose on a program page.

    A price's label is the text right before its amount. When that's empty, we
    fall back to the carried `context` — the trailing text after the previous
    amount, or a preceding price-less line. This untangles RBS markup that merges
    "Application fee: £48" and the next "Non-selective course …" label into one
    paragraph ahead of a bare "£485 …" line, and keeps overseas programs that mix
    currencies on one line (e.g. "Application fee: £50 Course fee: 390 euros")
    correctly split.
    """
    prices: list[Price] = []
    context: str | None = None
    for line in (line.strip() for line in text.split("\n")):
        if not line:
            continue
        matches = list(_MONEY.finditer(line))
        if not matches:
            context = line
            continue
        for i, match in enumerate(matches):
            start = matches[i - 1].end() if i else 0
            label = line[start : match.start()].strip(" :–-") or context or "Fee"
            context = None
            amount, currency = _money(match, dollar_currency)
            prices.append(
                Price(
                    amount=amount,
                    currency=currency,
                    label=label,
                    includes=_includes(label),
                    notes=line,
                )
            )
        context = line[matches[-1].end() :].strip(" :–-") or None
    return prices


def _table_prices(table) -> list[Price]:
    rows = wp.table_rows(table)
    prices: list[Price] = []
    for row in rows[1:]:  # skip header row
        course, location, duration, fee, *_ = (*row, "", "", "", "")
        amount = _amount(fee)
        if amount is None:
            continue
        label = f"{course} ({duration})".strip() if duration else course
        prices.append(
            Price(
                amount=amount,
                currency="GBP",
                label=label,
                includes=_includes(course),
                notes=" | ".join(cell for cell in (course, location, duration, fee) if cell),
            )
        )
    return prices


def _join(*parts: str | None) -> str | None:
    kept = [p.strip() for p in parts if p and p.strip()]
    return "\n\n".join(kept) or None


def _absolute(url: str | None) -> str | None:
    return f"{BASE}{url}" if url and url.startswith("/") else url


# --- sessions: per-block dates, age range, and gender ---
#
# RBS publishes each course block by age + gender, in two shapes:
#   White Lodge / Upper School (UK): "Week three, 3-7 August: aged 10 and 11
#     female and male training; aged 14 and 15 male training" — `;`-separated
#     (age, gender) subgroups, one session each.
#   Los Angeles: "Students aged 10-13, one-week course: <dates> OR <dates>".
# Ages/gender are normalized into fields; the raw subgroup stays in `notes`.

# Not IGNORECASE: the `(?=Week\s)` lookahead must not match the lowercase "week"
# inside "Three-week courses" (which would truncate the group). Week markers are
# always capitalized in the source.
_WEEK = re.compile(
    r"Week\s+([\w ]+?),\s*(\d{1,2}\s*[-–]\s*\d{1,2}\s+[A-Za-z]+)\s*:\s*(.*?)(?=Week\s|\Z)",
    re.DOTALL,
)
_COURSE_LABEL = re.compile(r"\b(?:one|two|three|four|five)-week courses?\b", re.IGNORECASE)
_STUDENTS = re.compile(
    r"Students aged\s+(\d{1,2})\s*[-–]\s*(\d{1,2}),\s*([-\w ]+?course)\s*:\s*(.*?)(?=Students aged|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_VENUES = {"white lodge", "upper school"}


def _span(text: str, year: int | None) -> tuple[date | None, date | None]:
    points: list[date] = []
    for day, month, yr in _DATE.findall(text):
        resolved = int(yr) if yr else year
        if resolved:
            points.append(date(resolved, parse.MONTHS[month.lower()], int(day)))
    for d1, d2, month, yr in _SHORT.findall(text):
        resolved = int(yr) if yr else year
        if resolved:
            points += [date(resolved, parse.MONTHS[month.lower()], int(d)) for d in (d1, d2)]
    return (min(points), max(points)) if points else (None, None)


def _session_gender(text: str) -> Gender:
    female = re.search(r"\bfemale\b", text, re.IGNORECASE)
    male = re.search(r"\bmale\b", text, re.IGNORECASE)
    if female and male:
        return "both"
    if female:
        return "female"
    if male:
        return "male"
    return "both"  # source silent on gender → open to both


def _session_ages(text: str) -> dict | None:
    ages = [int(n) for n in re.findall(r"\b(\d{1,2})\b", text) if 3 <= int(n) <= 25]
    return {"min": min(ages), "max": max(ages)} if ages else None


def _sessions(content: wp.Content, season: str) -> list[Session]:
    year = int(season) if season.isdigit() else None
    sessions: list[Session] = []
    venue: str | None = None

    for section in content.sections:
        heading = section.heading.lower()
        if heading in _VENUES:
            venue = section.heading
        if heading == "selective course":
            sessions += _week_sessions(section.text(), year, venue)
        elif "non-selective" in heading and "8-9" in heading:
            sessions += _short_sessions(section, year)

    sessions += _student_sessions(" ".join(s.text() for s in content.sections), year)

    # Fallback for programs that just list dated blocks (e.g. Livorno's four
    # weekends, "17-18 October 2026 … 10-11 April 2027") rather than age/gender
    # course tables.
    if not sessions:
        dates = content.find("Dates")
        if dates:
            sessions += _weekend_sessions(dates.text())

    # Fallback for programs (e.g. Autumn Intensives) where each city edition has
    # its own heading (e.g. "Edinburgh") followed by a date-range heading (e.g.
    # "16 & 17 October 2025") and the venue text as body — no "Dates" section.
    if not sessions:
        sessions += _city_date_sessions(content.sections, year)
    return sessions


_WEEKEND = re.compile(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")


def _weekend_sessions(text: str) -> list[Session]:
    sessions: list[Session] = []
    for d1, d2, month, year in _WEEKEND.findall(text):
        if month.lower() not in parse.MONTHS:
            continue
        month_num, yr = parse.MONTHS[month.lower()], int(year)
        label = f"{d1}-{d2} {month} {year}"
        sessions.append(
            Session(
                label=label,
                start=date(yr, month_num, int(d1)),
                end=date(yr, month_num, int(d2)),
                gender="both",
                notes=label,
            )
        )
    return sessions


# The Autumn Intensives page groups dates by city: a city heading ("Edinburgh")
# is immediately followed by a date-range heading ("16 & 17 October 2025"); the
# date heading's body is the venue address.  We extract one Session per
# city+date pair from that flat heading sequence.
_KNOWN_CITIES = {
    "edinburgh",
    "london",
    "manchester",
    "birmingham",
    "bristol",
    "glasgow",
    "leeds",
    "liverpool",
    "newcastle",
    "oxford",
    "bath",
    "brighton",
}
# "DD & DD Month YYYY" or "DD and DD Month YYYY" heading: both days in the same month.
_CITY_DATE = re.compile(
    r"(\d{1,2})\s*(?:&|and)\s*(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _city_date_sessions(sections: list[wp.Section], year: int | None) -> list[Session]:
    """Sessions from the city-heading / date-heading / venue-body structure.

    Walks the flat section list; a city heading sets the current city label; the
    next heading that parses as a date range (DD & DD Month YYYY) yields one
    Session, with the section body used as venue notes.  Stops tracking after
    the first non-city, non-date heading so deeper timetable subsections
    (e.g. 'Students aged 9-11 years') don't produce spurious sessions.
    """
    sessions: list[Session] = []
    city: str | None = None
    for section in sections:
        heading = section.heading.strip()
        heading_low = heading.lower()
        if heading_low in _KNOWN_CITIES:
            city = heading
            continue
        m = _CITY_DATE.match(heading)
        if m and city:
            d1, d2, month, yr = m.groups()
            if month.lower() not in parse.MONTHS:
                continue
            mo = parse.MONTHS[month.lower()]
            yr_int = int(yr)
            label = f"{city} — {heading}"
            sessions.append(
                Session(
                    label=label,
                    start=date(yr_int, mo, int(d1)),
                    end=date(yr_int, mo, int(d2)),
                    gender="both",
                    notes=section.text() or heading,
                )
            )
            city = None  # consumed
    return sessions


def _week_sessions(text: str, year: int | None, venue: str | None) -> list[Session]:
    sessions: list[Session] = []
    for label, dates, groups in _WEEK.findall(text):
        start, end = _span(dates, year)
        prefix = f"{venue} — " if venue else ""
        for sub in _COURSE_LABEL.sub("", groups).split(";"):
            sub = sub.strip(" ,\n")
            if not sub:
                continue
            sessions.append(
                Session(
                    label=f"{prefix}Week {label.strip()}",
                    start=start,
                    end=end,
                    ageRange=_session_ages(sub),
                    gender=_session_gender(sub),
                    notes=sub,
                )
            )
    return sessions


def _short_sessions(section: wp.Section, year: int | None) -> list[Session]:
    ages = _age_range(section.heading) or _age_range(section.text())
    sessions: list[Session] = []
    for d1, d2, month, yr in _SHORT.findall(section.text()):
        resolved = int(yr) if yr else year
        if not resolved:
            continue
        sessions.append(
            Session(
                label=f"Non-selective {d1}-{d2} {month}",
                start=date(resolved, parse.MONTHS[month.lower()], int(d1)),
                end=date(resolved, parse.MONTHS[month.lower()], int(d2)),
                ageRange=ages,
                gender="both",
                notes=f"{d1}-{d2} {month}",
            )
        )
    return sessions


def _student_sessions(blob: str, year: int | None) -> list[Session]:
    sessions: list[Session] = []
    for low, high, course, dates in _STUDENTS.findall(blob):
        ages = {"min": int(low), "max": int(high)}
        for option in re.split(r"\bOR\b", dates):
            start, end = _span(option, year)
            if start is None:
                continue
            sessions.append(
                Session(
                    label=course.strip(),
                    start=start,
                    end=end,
                    ageRange=ages,
                    gender="both",
                    notes=option.strip(),
                )
            )
    return sessions
