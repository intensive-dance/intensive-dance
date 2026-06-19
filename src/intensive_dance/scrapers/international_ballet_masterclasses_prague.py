"""International Ballet Masterclasses Prague (CZ) — its summer masterclasses.

API FIRST: yes. The site is **WordPress** (Avada/Fusion theme) under
`/pages/`; `GET /pages/wp-json/wp/v2/pages?slug=<slug>` returns each page with a
usable `content.rendered` body (plain HTML — the relevant pages aren't built with
a Fusion module that empties the REST body, unlike `faculty-2026`). So we read the
content pages via REST and parse their HTML — no front-end scrape, no JS render.
The host has since fallen behind a **Cloudflare challenge** that 403s the proxy's
plain *and* `auto`/`render` tiers — only the FlareSolverr `solve=1` tier returns
the REST JSON, wrapped in Chromium's JSON viewer (`wp.unwrap_json_viewer` recovers
it; same shape as `associazione_europea_danza`). So we force `solve=1` via
`PROXY_PARAMS_HEADER` and unwrap by hand rather than calling `resp.json()`.

DISCOVERY: the founder (Daria Klimentová, ex-ENB prima) runs two distinct
student programmes in Prague each summer, held at the Czech National Ballet
studios (National Theatre Prague). They differ in dates, ages, venue
arrangement and price, so we emit **one Offering per programme**:

  - **Summer Masterclasses** (senior, advanced/professional, min age 16) — two
    one-week sessions (Week 1 + Week 2) plus a full two-week option spanning
    both. One Offering with the two weeks as `schedule.sessions`; the
    one-/two-week course options become distinct `Price`s.
  - **Junior Masterclasses** (ages 13–15) — a separate five-day course the week
    after, no organised accommodation. Its own Offering.

The provider is Prague-specific; the org also runs editions in Milan, Budapest,
London and Tokyo — those are different providers/locations and out of scope here.

WHAT THE PAGES GIVE US (verified live 2026-06):
  - SENIOR DATES (`options-fees`): Week 1 "20th – 25th July 2026", Week 2 "27th
    July – 1st August 2026", Two-week "20th July – 1st August 2026".
  - SENIOR AGES/LEVEL (`how-to-apply`): "MINIMUM AGE IS 16", level
    "advanced/professional" → no upper bound, level pre-professional+professional.
  - SENIOR PRICES (`options-fees`): in EUR and GBP, package (incl. accommodation)
    and course-only, for one- and two-week options — all eight emitted faithfully.
  - SENIOR FACULTY (`classes`): a per-week 2026 roster (Week 1 / Week 2 lists).
  - SENIOR REQUIREMENTS (`how-to-apply`): a photograph in a normal ballet
    position ("1st arabesque is best") and, for students, a teacher reference.
  - SENIOR DEADLINE (`tcs-and-scholarship`): "Closing date for the applications
    is 14th July." (no year → stamped with the edition's). The separate
    full-payment cut-off ("June 1st") and deposit terms are kept as notes.
  - JUNIOR (`new-junior-masterclasses`): dates "3rd – 7th August 2026", ages
    13–15, price £750/€900, a photo (1st arabesque) to apply, named faculty.

WHAT THIS SCRAPER EXERCISES: multi-Offering provider; `schedule.sessions`;
multi-currency `Price` list (EUR + GBP, with/without accommodation); `level`;
`teachers` with per-week roles; `PhotosReq(defined-poses)`; `age_range` with a
null upper bound (senior) and a bounded one (junior).
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse, wp
from intensive_dance.fetch import PROXY_PARAMS_HEADER
from intensive_dance.models import (
    Application,
    CVReq,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    PhotosReq,
    Price,
    PriceInclude,
    Requirement,
    Schedule,
    Session,
    Source,
    Teacher,
    now_utc,
)

PROVIDER = "international-ballet-masterclasses-prague"
BASE = "https://www.balletmasterclass.com/pages"
API = f"{BASE}/wp-json/wp/v2/pages"

# Content pages we read (slug → public URL used as the Offering source link).
SENIOR_PAGES = {
    "options-fees": f"{BASE}/options-fees/",
    "classes": f"{BASE}/classes/",
    "how-to-apply": f"{BASE}/how-to-apply/",
    "tcs-and-scholarship": f"{BASE}/tcs-and-scholarship/",
}
JUNIOR_SLUG = "new-junior-masterclasses"
JUNIOR_URL = f"{BASE}/new-junior-masterclasses/"

ORG = Organization(
    name="International Ballet Masterclasses", slug=PROVIDER, country="CZ", city="Prague"
)
# The Czech National Ballet studios at the National Theatre, per `about-us` /
# `new-junior-masterclasses` (Anenske Namesti 2, Prague 1).
VENUE = "Czech National Ballet studios (National Theatre Prague), Anenské náměstí 2"
TZ = "Europe/Prague"


def scrape(client: httpx.Client) -> list[Offering]:
    senior_html = {slug: _fetch_content(client, slug) for slug in SENIOR_PAGES}
    junior_html = _fetch_content(client, JUNIOR_SLUG)
    return _build_offerings(senior_html, junior_html)


def _fetch_content(client: httpx.Client, slug: str) -> str:
    # The host fell behind a Cloudflare challenge that 403s the proxy's plain and
    # `auto`/`render` tiers; only the FlareSolverr `solve=1` tier returns the REST
    # JSON, wrapped in Chromium's JSON viewer (`wp.unwrap_json_viewer` recovers it).
    resp = client.get(
        API,
        params={"slug": slug, "_fields": "content"},
        headers={PROXY_PARAMS_HEADER: "solve=1"},
    )
    resp.raise_for_status()
    data = wp.unwrap_json_viewer(resp.text)
    return data[0]["content"]["rendered"] if data else ""


def _build_offerings(senior_html: dict[str, str], junior_html: str) -> list[Offering]:
    offerings: list[Offering] = []
    senior = _senior(senior_html)
    if senior is not None:
        offerings.append(senior)
    junior = _junior(junior_html)
    if junior is not None:
        offerings.append(junior)
    return offerings


def _text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.text(separator=" ")) if html else ""


# --- senior summer masterclasses ----------------------------------------------


def _senior(pages: dict[str, str]) -> Offering | None:
    fees_text = _text(pages.get("options-fees", ""))
    classes_text = _text(pages.get("classes", ""))
    apply_text = _text(pages.get("how-to-apply", ""))
    tc_text = _text(pages.get("tcs-and-scholarship", ""))

    sessions = _senior_sessions(fees_text)
    if not sessions:
        return None  # no dated edition announced
    start = min(s.start for s in sessions if s.start)
    end = max(s.end for s in sessions if s.end)
    season = str(end.year)

    return Offering(
        id=f"{PROVIDER}/summer-masterclasses-{season}",
        source=Source(provider=PROVIDER, url=SENIOR_PAGES["options-fees"], scrapedAt=now_utc()),
        title=f"Summer Masterclasses {season}",
        genres=_genres(classes_text + " " + apply_text),
        level=_senior_level(apply_text),
        ageRange=_senior_age(apply_text),
        organization=ORG,
        location=Location(venue=VENUE, city="Prague", country="CZ"),
        schedule=Schedule(season=season, start=start, end=end, timezone=TZ, sessions=sessions),
        teachers=_senior_teachers(classes_text),
        prices=_senior_prices(fees_text),
        application=Application(
            deadline=_closing_date(tc_text, end.year),
            url=f"{BASE}/how-to-apply/",
            requirements=_senior_requirements(apply_text),
            notes=_senior_apply_note(fees_text),
        ),
    )


# Week ranges as written on the fees page. Two shapes appear:
#   "Week 1: 20th -25th July 2025:"        — one shared trailing month
#   "Week 2: 27th July – 1st August 2026:" — a month on each bound
# So a month after the *first* day is optional, and so is a month after the
# second; we fall back to the other bound's month when one side omits it. The
# inline year is unreliable (Week 1 carries a stale "2025" typo), so we ignore it
# and stamp the season from the two-week range's closing year (read separately).
_WEEK = re.compile(
    r"Week\s+(\d):\s*(\d{1,2})(?:st|nd|rd|th)?\s*"
    r"(?:(" + parse.MONTHALT + r")\s+)?"
    r"(?:[-–—]\s*|-)\s*"
    r"(\d{1,2})(?:st|nd|rd|th)?\s*"
    r"(?:(" + parse.MONTHALT + r"))?",
    re.IGNORECASE,
)
# "Two Week Intensive Course 20th July – 1st August 2026" — the authoritative
# span (and the only place a reliable year appears).
_TWO_WEEK = re.compile(
    r"Two Week Intensive Course\s+(\d{1,2})(?:st|nd|rd|th)?\s+(" + parse.MONTHALT + r")\s*"
    r"[-–—]\s*(\d{1,2})(?:st|nd|rd|th)?\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _two_week_span(text: str) -> tuple[date, date] | None:
    start, end = parse.parse_multi_month_range(text, _TWO_WEEK)
    if start and end:
        return start, end
    return None


def _senior_sessions(text: str) -> list[Session]:
    span = _two_week_span(text)
    if span is None:
        return []
    year = span[1].year  # the reliable year, from the two-week range
    sessions: list[Session] = []
    for m in _WEEK.finditer(text):
        num, d1, m1_opt, d2, m2_opt = m.groups()
        if not (m1_opt or m2_opt):
            continue  # no month on either bound — unparseable, skip
        start_month = parse.MONTHS[(m1_opt or m2_opt).lower()]
        end_month = parse.MONTHS[(m2_opt or m1_opt).lower()]
        sessions.append(
            Session(
                label=f"Week {num}",
                start=date(year, start_month, int(d1)),
                end=date(year, end_month, int(d2)),
            )
        )
    return sessions


_AGE_MIN = re.compile(r"minimum age is\s*(\d{1,2})", re.IGNORECASE)


def _senior_age(text: str) -> dict | None:
    return parse.extract_age_range(text, _AGE_MIN)


def _senior_level(text: str) -> list[Level]:
    low = text.lower()
    levels: list[Level] = []
    if "professional" in low:
        levels.append("professional")
    # "advanced/professional … one year in full-time training for a career" — the
    # rising-pro tier alongside working professionals.
    if "advanced" in low or "full-time training" in low:
        levels.append("pre-professional")
    return levels


# Per-week 2026 roster on the `classes` page: "Teachers in Week One (...): A, B, C"
# / "Teachers in Week Two (...): ...". Names are comma-separated up to the next
# sentence.
_WEEK_FACULTY = re.compile(
    r"Teachers in Week (One|Two)\s*\([^)]*\):\s*([^.]+?)(?=\s+(?:Teachers in Week|A typical day|$))",
    re.IGNORECASE,
)


def _senior_teachers(text: str) -> list[Teacher]:
    teachers: list[Teacher] = []
    for m in _WEEK_FACULTY.finditer(text):
        week, names = m.group(1).title(), m.group(2)
        for name in re.split(r",\s*", names):
            name = parse.clean(name)
            if name:
                teachers.append(Teacher(name=name, role=f"Guest Teacher (Week {week})"))
    return teachers


# Fee lines pair a GBP and EUR amount, e.g.
# "Package fee *, including accommodation: £1720.00 (sterling) or €2000.00 (euro)"
# "Course only fee , no accommodation: £1100 (sterling) or €1300 (euro)"
_FEE_LINE = re.compile(
    r"(Package fee|Course only fee)[^£€]*?"
    r"£\s*([\d.,]+)\s*\(sterling\)\s*or\s*€\s*([\d.,]+)\s*\(euro\)",
    re.IGNORECASE,
)


def _senior_prices(text: str) -> list[Price]:
    """Emit GBP + EUR for each fee line, tagged by option (one/two week)."""
    two_week_start = text.find("Two Week Intensive Course")
    prices: list[Price] = []
    for m in _FEE_LINE.finditer(text):
        kind = m.group(1).lower()
        gbp, eur = parse.parse_amount(m.group(2)), parse.parse_amount(m.group(3))
        is_two_week = two_week_start != -1 and m.start() > two_week_start
        option = "Two-week course" if is_two_week else "One-week course"
        package = "package" in kind
        includes: list[PriceInclude] = ["tuition", "accommodation"] if package else ["tuition"]
        label_suffix = "package, incl. accommodation" if package else "course only"
        for amount, currency in ((eur, "EUR"), (gbp, "GBP")):
            if amount is None:
                continue
            prices.append(
                Price(
                    amount=amount,
                    currency=currency,
                    label=f"{option} — {label_suffix}",
                    includes=includes,
                )
            )
    return prices


# The application closing date on the T&C page, e.g. "Closing date for the
# applications is 14th July." — no year, so we stamp the edition's year.
_CLOSING = re.compile(
    r"closing date for the applications? is\s+(\d{1,2})(?:st|nd|rd|th)?\s+("
    + parse.MONTHALT
    + r")",
    re.IGNORECASE,
)


def _closing_date(text: str, year: int) -> date | None:
    m = _CLOSING.search(text)
    if not m:
        return None
    day, month = m.groups()
    return date(year, parse.MONTHS[month.lower()], int(day))


def _senior_apply_note(text: str) -> str | None:
    """Deposit terms + the full-payment cut-off, kept as raw application text."""
    parts: list[str] = []
    deposit = re.search(r"(A non-returnable deposit[^.]*\.)", text)
    if deposit:
        parts.append(parse.clean(deposit.group(1)))
    payment = re.search(r"(The fee for the course[^.]*paid in full by[^.]*\.)", text)
    if payment:
        parts.append(parse.clean(payment.group(1)))
    return " ".join(parts) if parts else None


# --- junior masterclasses -----------------------------------------------------


def _junior(html: str) -> Offering | None:
    text = _text(html)
    span = _junior_dates(text)
    if span is None:
        return None
    start, end = span
    season = str(end.year)

    return Offering(
        id=f"{PROVIDER}/junior-masterclasses-{season}",
        source=Source(provider=PROVIDER, url=JUNIOR_URL, scrapedAt=now_utc()),
        title=f"Junior Masterclasses {season}",
        genres=_genres(text),
        ageRange=_junior_age(text),
        organization=ORG,
        location=Location(venue=VENUE, city="Prague", country="CZ"),
        schedule=Schedule(season=season, start=start, end=end, timezone=TZ),
        teachers=_junior_teachers(text),
        prices=_junior_prices(text),
        application=Application(
            url=JUNIOR_URL,
            requirements=_junior_requirements(),
        ),
    )


# "The dates for 2026 will be from the 3rd -7 th August 2026 inclusive" (one month).
_JUNIOR_DATES = re.compile(
    r"dates for \d{4}[^0-9]*?(\d{1,2})(?:st|nd|rd|th)?\s*[-–—]\s*(\d{1,2})\s*(?:st|nd|rd|th)?\s+"
    r"(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _junior_dates(text: str) -> tuple[date, date] | None:
    m = _JUNIOR_DATES.search(text)
    if not m:
        return None
    d1, d2, month, year = m.groups()
    y, num = int(year), parse.MONTHS[month.lower()]
    return date(y, num, int(d1)), date(y, num, int(d2))


_JUNIOR_AGE = re.compile(r"aged\s*(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*years", re.IGNORECASE)


def _junior_age(text: str) -> dict | None:
    return parse.extract_age_range(text, _JUNIOR_AGE)


# Junior faculty: "led by ... Daria Klimentová. Joining her in 2026 will be A
# (from X), B (from Y), C (...) and D." Names are the bold-name-then-parenthetical
# pattern; we take the names, dropping the parenthetical affiliations.
_JUNIOR_LEAD = re.compile(r"led by[^.]*?\bDaria Klimentov[áa]\b", re.IGNORECASE)
_JUNIOR_JOINING = re.compile(r"Joining her in \d{4} will be\s+(.+?)\.", re.IGNORECASE | re.DOTALL)


def _junior_teachers(text: str) -> list[Teacher]:
    teachers: list[Teacher] = []
    if _JUNIOR_LEAD.search(text):
        teachers.append(Teacher(name="Daria Klimentová", role="Lead Teacher"))
    m = _JUNIOR_JOINING.search(text)
    if m:
        # Strip parenthetical affiliations, then split on commas / "and".
        names_blob = re.sub(r"\([^)]*\)", "", m.group(1))
        for name in re.split(r",\s*|\s+and\s+|\s+once again\s+", names_blob):
            name = parse.clean(name.strip(" .,"))
            # Skip filler words left by the split ("the very popular Royal Ballet
            # Dancer," etc. precede a name — keep capitalised name tokens only).
            if name and re.match(r"^[A-Z][\w’'-]+(?:\s+[A-Z][\w’'-]+)+$", name):
                teachers.append(Teacher(name=name, role="Guest Teacher"))
    return teachers


_JUNIOR_PRICE = re.compile(r"£\s*([\d.,]+)[^€]*?or\s*€\s*([\d.,]+)", re.IGNORECASE)


def _junior_prices(text: str) -> list[Price]:
    m = _JUNIOR_PRICE.search(text)
    if not m:
        return []
    gbp, eur = parse.parse_amount(m.group(1)), parse.parse_amount(m.group(2))
    prices: list[Price] = []
    for amount, currency in ((eur, "EUR"), (gbp, "GBP")):
        if amount is not None:
            prices.append(
                Price(amount=amount, currency=currency, label="Course fee", includes=["tuition"])
            )
    return prices


# --- shared helpers -----------------------------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("general class", "classical", "ballet")),
    ("pointe", ("pointe",)),
    ("repertoire", ("repertoire", "variation", "solo")),
    ("contemporary", ("contemporary",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _photo_req(text: str) -> Requirement:
    """A photograph in a defined ballet pose ("1st arabesque is best")."""
    poses = ["first arabesque"] if re.search(r"1st\s+arabesque", text, re.IGNORECASE) else []
    return PhotosReq(
        specificity="defined-poses" if poses else "freeform",
        poses=poses,
        notes="A photograph in a normal ballet position (first arabesque preferred).",
    )


_TEACHER_REF = re.compile(r"attach a reference from your teacher", re.IGNORECASE)


def _senior_requirements(text: str) -> list[Requirement]:
    reqs: list[Requirement] = [_photo_req(text)]
    # The application form page states "Please attach a reference from your teacher
    # (if a student)" — an "UPLOAD YOUR REFERENCE" field is present in the form.
    if _TEACHER_REF.search(text):
        reqs.append(CVReq())
    return reqs


def _junior_requirements() -> list[Requirement]:
    return [_photo_req("1st arabesque")]
