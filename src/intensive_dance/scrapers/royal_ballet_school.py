"""The Royal Ballet School — first scraper.

API FIRST: RBS runs on WordPress and exposes a public REST API, so the core
fields come straight from JSON — no HTML scraping of the live site. The body is
WPBakery shortcode markup, cleaned and sectioned by `intensive_dance.wp`.

DISCOVERY: RBS runs *many* intensives (UK Summer, Los Angeles, Livorno, Hong
Kong, …) and re-dates the same WordPress pages each cycle. Rather than hardcode a
list, we fetch the children of the "Intensive Courses" page and keep only the
ones that are still **live** — dropping cancelled courses and cycles whose last
course date is already in the past. So a newly-opened cycle (or a brand-new
location) is picked up automatically, and last season's listings fall away.

One `Offering` per live program. Offering ids are `{providerSlug}/{pageSlug}-{season}`
(e.g. `royal-ballet-school/uk-summer-intensive-2026`), keeping year-over-year
cycles distinct and diffable.

Requirements are PHOTOS ONLY — RBS assesses on photo submissions, no video and
no in-person audition. The required positions are published as age-banded
*diagrams* on the photograph-requirements page, not as named poses, so we emit
`photos` with `specificity="defined-poses"` and an empty `poses` list, keeping
the raw guidance + page URL in `notes`. (Use a video-requiring house such as
Joffrey / ABT to exercise the `video` branch of the requirements union.)

Course fees live in a table on a shared fees page (the WooCommerce `wc/v3`
namespace is enabled but does not expose these as products); the per-program
application fee and ancillary fees are inline on each program page.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from intensive_dance import wp
from intensive_dance.models import (
    Application,
    Genre,
    Kind,
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

ORG = Organization(name="The Royal Ballet School", slug="royal-ballet-school", country="GB", city="London")

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
        offering
        for record in wp.fetch_children(client, root["id"], base=BASE)
        if (offering := _build_offering(record, fees, today)) is not None
    ]
    offerings.sort(key=lambda o: o.id)
    return offerings


def _build_offering(record: dict, fees: wp.Content | None, today: date) -> Offering | None:
    """Parse one program page into an Offering, or None if it isn't live.

    Skips cancelled courses and cycles whose last course date is already past —
    this is what keeps the committed store to currently-open programs as RBS
    leaves prior cycles published.
    """
    slug = record["slug"]
    base_title = record["title"]["rendered"].strip()
    content = wp.parse(record["content"]["rendered"])

    if "cancel" in slug.lower() or "cancel" in base_title.lower():
        return None
    last_date = _latest_course_date(content)
    if last_date is not None and last_date < today:
        return None

    blob = " ".join(section.text() for section in content.sections)
    dates_text = content.text("Dates")
    start, end, season = _date_range(dates_text) if dates_text else (None, None, _year(blob))
    title = f"{base_title} {season}".strip()

    photo_url = _absolute(content.link("photograph"))
    requirement_notes = content.text("Requirements")
    photos = PhotosReq(
        specificity="defined-poses",
        notes=_join(
            requirement_notes,
            "Required positions are published as age-banded diagrams "
            f"on the photograph-requirements page: {photo_url}" if photo_url else None,
        ),
    )

    application = _application(
        content.find_block("Application deadline", "Applications", "Bookings"),
        url=_absolute(content.link("apply", "book")),
        requirements=[photos],
    )

    prices = _inline_prices(content.text("Fees"))
    fee_table = FEE_TABLES.get(slug)
    if fee_table and fees:
        section = fees.find(fee_table)
        if section and section.table() is not None:
            prices += _table_prices(section.table())

    location_section = content.find("Location", "Venue")
    location_text = location_section.text() if location_section else ""
    city, country, timezone = _place(location_text)

    return Offering(
        id=f"royal-ballet-school/{slug}-{season}",
        source=Source(provider="royal-ballet-school", url=record["link"], scrapedAt=now_utc()),
        title=title,
        genres=_genres(blob),
        kind=_kind(slug, base_title),
        level=_levels(blob),
        ageRange=_age_range(content.text("Eligibility")),
        organization=ORG,
        location=Location(
            venue=_venue(location_section),
            city=city,
            country=country,
        ),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone=timezone,
            sessions=_sessions(content, season),
            notes=dates_text or None,
        ),
        application=application,
        prices=prices,
    )


# --- parsing helpers ---

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"],
        start=1,
    )
}
_MONTHALT = "|".join(_MONTHS)
_DATE = re.compile(r"(\d{1,2})\s+(" + _MONTHALT + r")(?:\s+(\d{4}))?", re.IGNORECASE)
# A short range like "21-25 July" or "6 – Friday 10 July" (shared month, year implied).
_SHORT = re.compile(r"(\d{1,2})\s*[-–]\s*(?:[A-Za-z]+\s+)?(\d{1,2})\s+(" + _MONTHALT + r")", re.IGNORECASE)
# Money in either order: symbol-prefixed ("£48", "€390") or word-suffixed
# ("390 euros"), since RBS prices its overseas programs in local currency.
_MONEY = re.compile(
    r"(?P<sym>[£€$])\s*(?P<sym_amt>[\d,]+(?:\.\d+)?)"
    r"|(?P<word_amt>[\d,]+(?:\.\d+)?)\s*(?P<word>euros?|eur|pounds?|gbp|dollars?|usd)\b",
    re.IGNORECASE,
)
_CURRENCY_SYMBOL = {"£": "GBP", "€": "EUR", "$": "USD"}
_CURRENCY_WORD = {"euro": "EUR", "eur": "EUR", "pound": "GBP", "gbp": "GBP", "dollar": "USD", "usd": "USD"}
_AGE = re.compile(r"aged\s+(\d{1,2})\s*(?:[-–]\s*(\d{1,2}))?", re.IGNORECASE)
_YEAR = re.compile(r"\b(20\d{2})\b")


def _money(match: re.Match) -> tuple[float, str]:
    if match.group("sym"):
        return float(match.group("sym_amt").replace(",", "")), _CURRENCY_SYMBOL[match.group("sym")]
    word = match.group("word").lower().rstrip("s")
    return float(match.group("word_amt").replace(",", "")), _CURRENCY_WORD[word]


def _year(text: str) -> str:
    match = _YEAR.search(text)
    return match.group(1) if match else "unknown"


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

    dates = [date(int(y) if y else year, _MONTHS[m.lower()], int(d)) for d, m, y in tokens]
    return min(dates), max(dates), str(year)


def _deadline(text: str) -> date | None:
    match = re.search(r"clos\w*[^.]*?(\d{1,2}\s+[A-Za-z]+\s+\d{4})", text, re.IGNORECASE)
    if not match:
        return None
    start, end, _ = _date_range(match.group(1))
    return start


# RBS reckons age "on 31 August <year>"; that cutoff must not count as a course
# date, or every page would look current.
_CUTOFF = re.compile(r"on \d{1,2}\s+[A-Za-z]+\s+\d{4}", re.IGNORECASE)


def _latest_course_date(content: wp.Content) -> date | None:
    """Latest concrete course date on the page — drives the live/ended gate.

    Yearless day-month tokens inherit the latest year seen on the page, so a
    multi-weekend program spanning into next year reads as live.
    """
    text = _CUTOFF.sub(" ", " ".join(section.text() for section in content.sections))
    years = [int(y) for y in _YEAR.findall(text)]
    year = max(years) if years else None
    points: list[date] = []
    for day, month, yr in _DATE.findall(text):
        resolved = int(yr) if yr else year
        if resolved and month.lower() in _MONTHS:
            points.append(date(resolved, _MONTHS[month.lower()], int(day)))
    if year:
        for _, end_day, month in _SHORT.findall(text):
            if month.lower() in _MONTHS:
                points.append(date(year, _MONTHS[month.lower()], int(end_day)))
    return max(points) if points else None


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
        lines += [
            line for sub in subs for line in sub.text().split("\n") if _RELEVANT.search(line)
        ]
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


def _kind(slug: str, title: str) -> Kind:
    return "masterclass" if "masterclass" in f"{slug} {title}".lower() else "intensive"


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
    "united states": "US", "united kingdom": "GB", "thailand": "TH", "japan": "JP",
    "hong kong": "HK", "singapore": "SG", "korea": "KR", "italy": "IT", "spain": "ES",
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
    blocks = [
        ", ".join(_tidy(line) for line in wp.node_lines(node) if _tidy(line))
        for node in section.nodes
    ]
    return " · ".join(block for block in blocks if block) or None


def _tidy(text: str) -> str:
    return re.sub(r"\s{2,}", " ", re.sub(r"\s+([,.])", r"\1", text)).strip(" ,")


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
    low = blob.lower()
    return [genre for genre, keys in _GENRE_KEYWORDS if any(k in low for k in keys)]


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


def _inline_prices(text: str) -> list[Price]:
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
            amount, currency = _money(match)
            prices.append(
                Price(amount=amount, currency=currency, label=label, includes=_includes(label), notes=line)
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
            points.append(date(resolved, _MONTHS[month.lower()], int(day)))
    if year:
        for d1, d2, month in _SHORT.findall(text):
            points += [date(year, _MONTHS[month.lower()], int(d)) for d in (d1, d2)]
    return (min(points), max(points)) if points else (None, None)


def _session_gender(text: str) -> str:
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
    return sessions


_WEEKEND = re.compile(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")


def _weekend_sessions(text: str) -> list[Session]:
    sessions: list[Session] = []
    for d1, d2, month, year in _WEEKEND.findall(text):
        if month.lower() not in _MONTHS:
            continue
        month_num, yr = _MONTHS[month.lower()], int(year)
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
    for d1, d2, month in _SHORT.findall(section.text()):
        if not year:
            continue
        sessions.append(
            Session(
                label=f"Non-selective {d1}-{d2} {month}",
                start=date(year, _MONTHS[month.lower()], int(d1)),
                end=date(year, _MONTHS[month.lower()], int(d2)),
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
