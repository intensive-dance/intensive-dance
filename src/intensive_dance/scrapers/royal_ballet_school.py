"""The Royal Ballet School — first scraper.

API FIRST: RBS runs on WordPress and exposes a public REST API, so the core
fields come straight from JSON — no HTML scraping of the live site. For each
program we fetch its page record by slug from `/wp-json/wp/v2/pages`; the body
is WPBakery shortcode markup, cleaned and sectioned by `intensive_dance.wp`.

RBS runs *many* intensives (UK Summer, Los Angeles, Thailand, Hong Kong, …), so
this emits one `Offering` per program. Offering ids are
`{providerSlug}/{pageSlug}-{season}` (e.g. `royal-ballet-school/uk-summer-intensive-2026`),
which keeps year-over-year cycles distinct and diffable.

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
from dataclasses import dataclass
from datetime import date

import httpx

from intensive_dance import wp
from intensive_dance.models import (
    Application,
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
FEES_SLUG = "intensive-courses-fees"

ORG = Organization(name="The Royal Ballet School", slug="royal-ballet-school", country="GB", city="London")


@dataclass(frozen=True)
class Program:
    page_slug: str
    city: str
    country: str
    fee_table: str | None = None  # heading on the fees page whose table holds course fees


PROGRAMS = [
    Program("uk-summer-intensive", city="London", country="GB", fee_table="Summer Intensive fees"),
    Program("los-angeles-intensive", city="Los Angeles", country="US"),
]


def scrape(client: httpx.Client) -> list[Offering]:
    fees_page = wp.fetch_page(client, FEES_SLUG, base=BASE)
    fees = wp.parse(fees_page["content"]["rendered"]) if fees_page else None

    offerings: list[Offering] = []
    for program in PROGRAMS:
        record = wp.fetch_page(client, program.page_slug, base=BASE)
        if record is None:
            continue
        offerings.append(_build_offering(record, program, fees))
    return offerings


def _build_offering(record: dict, program: Program, fees: wp.Content | None) -> Offering:
    content = wp.parse(record["content"]["rendered"])
    blob = " ".join(section.text() for section in content.sections)

    dates_text = content.text("Dates")
    start, end, season = _date_range(dates_text) if dates_text else (None, None, _year(blob))

    base_title = record["title"]["rendered"].strip()
    title = f"{base_title} {season}".strip()

    photo_url = content.link("photograph")
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
        url=content.link("apply", "book"),
        requirements=[photos],
    )

    prices = _inline_prices(content.text("Fees"))
    if program.fee_table and fees:
        section = fees.find(program.fee_table)
        if section and section.table() is not None:
            prices += _table_prices(section.table())

    location_text = content.text("Location")

    return Offering(
        id=f"royal-ballet-school/{program.page_slug}-{season}",
        source=Source(provider="royal-ballet-school", url=record["link"], scrapedAt=now_utc()),
        title=title,
        genres=_genres(blob),
        kind="intensive",
        level=_levels(blob),
        ageRange=_age_range(content.text("Eligibility")),
        organization=ORG,
        location=Location(
            venue=location_text.replace("\n", " · ") or None,
            city=program.city,
            country=program.country,
        ),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/London" if program.country == "GB" else None,
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
_MONEY = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
_AGE = re.compile(r"aged\s+(\d{1,2})\s*(?:[-–]\s*(\d{1,2}))?", re.IGNORECASE)
_YEAR = re.compile(r"\b(20\d{2})\b")


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
    return float(match.group(1).replace(",", "")) if match else None


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

    A price's label is the text right before its `£` amount. When that's empty,
    we fall back to the carried `context` — the trailing text after the previous
    amount, or a preceding price-less line. This untangles RBS markup that merges
    "Application fee: £48" and the next "Non-selective course …" label into one
    paragraph ahead of a bare "£485 …" line.
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
            amount = float(match.group(1).replace(",", ""))
            prices.append(
                Price(amount=amount, currency="GBP", label=label, includes=_includes(label), notes=line)
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
