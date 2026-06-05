"""Helsinki International Ballet Competition (HIBC).

API FIRST: none usable. The site is WordPress (Yoast emits a `WebPage` JSON-LD
graph, but no schema.org `Event`), and the only structured posts are news — the
competition itself lives in static `/competition/*` pages. WordPress REST is
reachable, but the EN/SV/FI translations aren't exposed by a `?lang=` filter we
can query, so we fetch the published `/en/` HTML by stable slug. The pages are
fully server-rendered (no JS), so the text is all in the static markup.

DISCOVERY: HIBC is one biennial competition; the live site describes a single
edition (the 10th, 28 May–5 Jun 2026) across four `/en/competition/*` pages —
`info` (overview, categories, jury), `saannot` (rules + fees), `schedule`
(round dates/times), `palkinnot` (prizes). We emit **one** `Offering` for the
edition; the three age divisions become `schedule.sessions` (each with its own
age range) rather than separate Offerings — they're one competition, judged
together, sharing dates/fees/requirements. No 2027 cycle is announced yet.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-05):
  - KIND: `competition` (judged for prizes), `lifecycle` scheduled.
  - DATES: banner "28.5.–5.6.2026" → schedule start/end; the edition's end date
    is *today*, so it must NOT be dropped as past (past = end < today).
  - CATEGORIES: Juniors 15–18 / Young Professionals 19–21 / Seniors 22–25 →
    three `Session`s, each year-bounded; the Offering `age_range` spans 15–25.
  - GENRES: classical + contemporary (Round I classical variations, Round II a
    post-2020 contemporary piece, Finals both).
  - PRICES (EUR): €100 video qualification + €250 participation (paid only by
    those accepted from the video round). Both non-refundable.
  - APPLICATION: window 1.11.2025–31.1.2026, now elapsed → `status` closed,
    `opensAt`/`deadline` set. Requirement is a qualification **video** in which
    the dancer must perform alone → `video`/`specific`.
  - TEACHERS: jury President Javier Torres (Artistic Director, Finnish National
    Ballet); the rest of the jury is "announced in spring 2026", so only the
    President is recorded rather than over-claiming an unannounced panel.
  - LOCATION: Finnish National Opera and Ballet, Helsinki, FI.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from intensive_dance import parse
from intensive_dance.models import (
    Affiliation,
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Session,
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

BASE = "https://ibchelsinki.fi"
INFO = f"{BASE}/en/competition/info/"
# The registration form is published on the site only during the application
# window; the Rules page is the stable EN URL describing how to apply.
RULES = f"{BASE}/en/competition/saannot/"
APPLY = RULES

ORG = Organization(
    name="Helsinki International Ballet Competition",
    slug="helsinki-international-ballet-competition",
    country="FI",
    city="Helsinki",
)
VENUE = "Finnish National Opera and Ballet"

# Yoast injects a WebPage JSON-LD graph that mentions dates; strip <script>/<style>
# so those don't leak into the parsed body text.
_DROP = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")

# "28.5.–5.6.2026" — the edition's headline span (DD.MM.–DD.MM.YYYY); the year
# sits only on the end date, so it applies to both bounds.
_SPAN = re.compile(r"(\d{1,2})\.(\d{1,2})\.\s*[–-]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")
# "The 10th Helsinki International Ballet Competition"
_EDITION = re.compile(r"\b(\d+)(?:st|nd|rd|th)\s+Helsinki International Ballet Competition")

# "Juniors (ages 15 to 18)" — each category's age band on the info page.
_CATEGORY = re.compile(
    r"(Juniors|Young Professionals|Seniors)\s*\(ages\s*(\d{1,2})\s*to\s*(\d{1,2})\)",
    re.IGNORECASE,
)
# "1.11.2025–31.1.2026" — the application window (DD.MM.YYYY–DD.MM.YYYY).
_WINDOW = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s*[–-]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")
# "fee … is 100€" / "fee for the competition is 250€" — euro amounts in context.
_QUAL_FEE = re.compile(r"video qualification is\s*(\d+)\s*€", re.IGNORECASE)
_PART_FEE = re.compile(r"fee for the competition is\s*(\d+)\s*€", re.IGNORECASE)


def scrape(client: httpx.Client) -> list[Offering]:
    info = client.get(INFO)
    info.raise_for_status()
    rules = client.get(RULES)
    rules.raise_for_status()
    offering = _build_offering(info.text, rules.text, date.today())
    return [offering] if offering is not None else []


def _build_offering(info_html: str, rules_html: str, today: date) -> Offering | None:
    info = _text(info_html)
    rules = _text(rules_html)

    span = _dates(info)
    if span is None:
        return None  # no dated edition announced
    start, end = span
    if end < today:
        return None  # edition is over — drop, never goes stale

    season = str(end.year)
    edition = _edition_label(info)
    title = (
        f"{edition} Helsinki International Ballet Competition"
        if edition
        else f"Helsinki International Ballet Competition {season}"
    )

    sessions = _sessions(info)
    return Offering(
        id=f"helsinki-international-ballet-competition/{season}",
        source=Source(provider=ORG.slug, url=INFO, scrapedAt=now_utc()),
        title=title,
        genres=_genres(info),
        kind="competition",
        ageRange=_age_range(sessions),
        organization=ORG,
        location=Location(venue=VENUE, city="Helsinki", country="FI"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Helsinki",
            sessions=sessions,
            notes="28.5.–5.6.2026",
        ),
        teachers=_teachers(info),
        prices=_prices(rules),
        application=_application(rules, today),
    )


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", _TAGS.sub(" ", _DROP.sub(" ", html))).strip()


def _dates(text: str) -> tuple[date, date] | None:
    m = _SPAN.search(text)
    if not m:
        return None
    d1, m1, d2, m2, year = (int(g) for g in m.groups())
    return date(year, m1, d1), date(year, m2, d2)


def _edition_label(text: str) -> str | None:
    m = _EDITION.search(text)
    if not m:
        return None
    n = int(m.group(1))
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _sessions(text: str) -> list[Session]:
    sessions: list[Session] = []
    for m in _CATEGORY.finditer(text):
        label, lo, hi = m.group(1), int(m.group(2)), int(m.group(3))
        sessions.append(
            Session(
                label=label,
                ageRange={"min": lo, "max": hi},
                notes=f"{label} (ages {lo} to {hi})",
            )
        )
    return sessions


def _age_range(sessions: list[Session]) -> dict | None:
    bounds = [s.age_range for s in sessions if s.age_range]
    if not bounds:
        return None
    return {"min": min(b["min"] for b in bounds), "max": max(b["max"] for b in bounds)}


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical",)),
    ("contemporary", ("contemporary",)),
    ("repertoire", ("repertoire", "variations")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


def _teachers(text: str) -> list[Teacher]:
    # Only the jury President is named; the rest is "announced in spring 2026".
    if "Javier Torres" not in text:
        return []
    return [
        Teacher(
            name="Javier Torres",
            role="Jury President",
            affiliations=[
                Affiliation(
                    organization="Finnish National Ballet",
                    role="Artistic Director",
                    current=True,
                )
            ],
        )
    ]


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    qual = _QUAL_FEE.search(text)
    if qual:
        prices.append(
            Price(
                amount=float(qual.group(1)),
                currency="EUR",
                label="Video qualification (non-refundable)",
            )
        )
    part = _PART_FEE.search(text)
    if part:
        prices.append(
            Price(
                amount=float(part.group(1)),
                currency="EUR",
                label="Participation — paid by competitors accepted from the video qualification",
                includes=["accommodation"],
                notes="Free shared twin-room hotel accommodation provided for the competition.",
            )
        )
    return prices


def _application(text: str, today: date) -> Application:
    opens_at: date | None = None
    deadline: date | None = None
    status = None
    m = _WINDOW.search(text)
    if m:
        d1, mo1, y1, d2, mo2, y2 = (int(g) for g in m.groups())
        opens_at = date(y1, mo1, d1)
        deadline = date(y2, mo2, d2)
        if today < opens_at:
            status = "upcoming"
        elif today > deadline:
            status = "closed"
        else:
            status = "open"
    return Application(
        status=status,
        opensAt=opens_at,
        deadline=deadline,
        url=APPLY,
        requirements=[
            VideoReq(
                specificity="specific",
                description=(
                    "Qualification video for the pre-selection; the dancer must "
                    "perform alone in the submitted video."
                ),
            )
        ],
        notes="Application period 1.11.2025–31.1.2026 (pre-selection by video).",
    )
