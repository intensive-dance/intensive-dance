"""La Sylphide Academic Ballet School — Bucharest, RO — "La Sylphide Summer Intensive".

API FIRST: plain WordPress with a clean `/wp-json/` (`wp/v2`); no proxy needed.
The body is **Avada/Fusion**-rendered HTML (not WPBakery shortcodes), so `wp.parse`
doesn't apply — we strip tags to flat Romanian prose and read it with local
regexes. Each yearly edition of the summer intensive is its own **page** under a
`summer-school*` slug (`summer-school` = the latest edition, `summer-school-YYYY`
for prior years). We discover them with `search=summer` + a `slug.startswith
("summer-school")` filter, which drops the look-alikes (`young-talents-summer-gala`,
the `scoala-de-vara` evergreen overview, `spectacole`).

DISCOVERY: one `Offering` per edition page, year-stamped (editions kept per
IDR-24 — past cycles stay in the store). The page *title* is unreliable (the
current edition's page is titled "Summer School 2023" but its body announces the
2024 intensive), so the year and dates come from the body header, never the title.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-20):
  - DATES: the header line before the "În fiecare an" boilerplate, two shapes —
    "… 10-29 Iulie 2024" (year trails) and "Summer School Intensive 2021 5 – 24
    Iulie" (year leads, separator-less). Year read independently of the day range;
    month via a local Romanian month map. Raw header kept in `schedule.notes`.
  - AGE TIERS → SESSIONS: the program runs 3 age groups on the *same* dates
    ("Age 1: 8 – 10 ani …") — one `Session` per tier (ageRange + raw note), and
    the offering's `ageRange` spans the overall min..max (cf. the RBS White Lodge
    age-block sessions).
  - GENRES: matched on the Romanian curriculum words (balet/poante/repertoriu/
    caracter/contemporan/neoclasic) over the program region only — sliced *before*
    "Profesori" so the international teachers' bios (full of "clasice și
    contemporane") can't leak a genre the program doesn't teach.
  - APPLICATION: registration is open-enrollment online/email by a stated deadline
    ("… până pe data de DD.MM.YYYY") — deadline parsed, raw line kept in notes; no
    audition material is stated for the short course, so `requirements` is left
    empty (the site's separate "Audiții" flow belongs to the year-round school).
  - PRICES / LEVELS / TEACHERS: never stated as structured data on the edition
    pages (fees are quote-on-request; faculty live as Fusion modal bios whose
    "Name – role" prose drifts year to year) → left unset rather than guessed.
"""

from __future__ import annotations

import html
import re
from datetime import date

import httpx

from intensive_dance import parse
from intensive_dance import wp
from intensive_dance.models import (
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    Schedule,
    Session,
    Source,
    now_utc,
)

BASE = "https://baletcopii.com"

ORG = Organization(
    name="La Sylphide Academic Ballet School",
    slug="la-sylphide-ballet-academy",
    country="RO",
    city="Bucharest",
)

_RO_MONTHS = {
    "ianuarie": 1,
    "februarie": 2,
    "martie": 3,
    "aprilie": 4,
    "mai": 5,
    "iunie": 6,
    "iulie": 7,
    "august": 8,
    "septembrie": 9,
    "octombrie": 10,
    "noiembrie": 11,
    "decembrie": 12,
}
_MONTHALT = parse.months_alt(_RO_MONTHS)

# "10-29 Iulie" | "4 – 23 Iulie" — the day span + month within the header line.
_DAY_RANGE = re.compile(r"(\d{1,2})\s*[–\-]\s*(\d{1,2})\s+(" + _MONTHALT + r")", re.IGNORECASE)
_YEAR = re.compile(r"\b(20\d\d)\b")
# "Age 1: 8 – 10 ani" — one per tier.
_AGE = re.compile(r"Age\s*\d+\s*:\s*(\d{1,2})\s*[–\-]\s*(\d{1,2})\s*ani", re.IGNORECASE)
# "… până pe data de 25.06.2024"
_DEADLINE = re.compile(
    r"p[âa]n[ăa]\s+pe\s+data\s+de\s+(\d{1,2})\.(\d{1,2})\.(\d{4})", re.IGNORECASE
)
_REGISTER = re.compile(r"Înscrier[^.]{0,200}", re.IGNORECASE)

# Romanian curriculum words → our genres. Matched against the program region only.
_GENRES: list[tuple[Genre, list[str]]] = [
    ("classical", ["balet"]),
    ("pointe", ["poante", "pointe"]),
    ("repertoire", ["repertoriu"]),
    ("character", ["caracter"]),
    ("contemporary", ["contemporan"]),
    ("neoclassical", ["neoclasic"]),
]


def scrape(client: httpx.Client) -> list[Offering]:
    pages = wp.fetch_all(
        client,
        "pages",
        base=BASE,
        params={"search": "summer", "_fields": "slug,link,title,content"},
    )
    editions = [p for p in pages if str(p.get("slug", "")).startswith("summer-school")]
    if not editions:
        # The summer-intensive pages reliably exist; an empty discovery means a
        # degraded fetch — raise so run.py keeps the prior store (IDR-24).
        raise RuntimeError("la-sylphide: no summer-school edition pages found")
    return _build_offerings(editions)


def _text(rendered: str) -> str:
    return parse.clean(re.sub(r"<[^>]+>", " ", html.unescape(rendered)))


def _dates(header: str) -> tuple[date, date] | None:
    year_m = _YEAR.search(header)
    day_m = _DAY_RANGE.search(header)
    if not year_m or not day_m:
        return None
    year = int(year_m.group(1))
    month = _RO_MONTHS[day_m.group(3).lower()]
    return date(year, month, int(day_m.group(1))), date(year, month, int(day_m.group(2)))


def _sessions(text: str, start: date, end: date) -> list[Session]:
    sessions: list[Session] = []
    for i, (lo, hi) in enumerate(_AGE.findall(text), start=1):
        sessions.append(
            Session(
                label=f"Age group {i}",
                start=start,
                end=end,
                ageRange={"min": int(lo), "max": int(hi)},
                gender="both",
                notes=f"Age {i}: {lo}–{hi} ani",
            )
        )
    return sessions


def _age_range(text: str) -> dict | None:
    tiers = _AGE.findall(text)
    if not tiers:
        return None
    return {"min": min(int(lo) for lo, _ in tiers), "max": max(int(hi) for _, hi in tiers)}


def _build_offering(page: dict) -> Offering | None:
    text = _text(page["content"]["rendered"])
    header = text.split("În fiecare an")[0].strip()
    span = _dates(header)
    if span is None:
        return None
    start, end = span
    year = start.year

    # Genres only from the program region (before the teacher bios), so the
    # faculty's "clasice și contemporane" prose can't leak a genre.
    program = text.split("Profesori")[0]

    deadline = None
    if m := _DEADLINE.search(text):
        d, mo, y = (int(x) for x in m.groups())
        deadline = date(y, mo, d)
    note = parse.clean(reg.group(0)) if (reg := _REGISTER.search(text)) else None

    return Offering(
        id=f"la-sylphide-ballet-academy/{year}",
        source=Source(provider="la-sylphide-ballet-academy", url=page["link"], scrapedAt=now_utc()),
        title=f"La Sylphide Summer Intensive {year}",
        genres=parse.match_genres(program, _GENRES, default=["classical"]),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(city="Bucharest", country="RO"),
        schedule=Schedule(
            season=str(year),
            start=start,
            end=end,
            timezone="Europe/Bucharest",
            sessions=_sessions(text, start, end),
            notes=header or None,
        ),
        application=Application(deadline=deadline, url=page["link"], notes=note),
    )


def _build_offerings(pages: list[dict]) -> list[Offering]:
    offerings = [o for p in pages if (o := _build_offering(p)) is not None]
    offerings.sort(key=lambda o: o.id)
    return offerings
