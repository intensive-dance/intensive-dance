"""Hong Kong Academy of Ballet (school arm of Hong Kong Ballet) — Summer Intensive.

API FIRST: none usable. The site runs a custom CMS (not WordPress — no
`/wp-json/`, no JSON-LD `Event`/`Course`, no `__NEXT_DATA__`, no feeds), but the
Summer Intensive page is fully server-rendered, so the whole programme lives in
the static HTML — a one-page scrape, no JS. The URL carries the year
(`…/summerintensive{YEAR}`); the bare slug 404s, so we derive the year from
today and fall back across recent years.

DISCOVERY: the page lists one Summer Intensive run in five age-banded classes
(A–E), each bookable for Week 1, Week 2 or both. The classes differ in ages,
curriculum, fees, guest faculty and (for D/E) entry requirements, so folding
them into one record would lose all of that. We therefore emit **one Offering
per class** (slug `summer-intensive-{year}-class-{a..e}`), with the two weeks as
`schedule.sessions`. Faculty differs per week, so each guest teacher is tagged
to its week via `Teacher.role`.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-05, re-verified 2026-06-07):
  - SESSIONS: Week 1 (20–25 Jul 2026) and Week 2 (27 Jul – 1 Aug 2026) for
    Classes B–E (continuous Mon–Sat). Class A runs a non-consecutive 4-day camp:
    Week 1 Mon–Tue, Thu–Fri (20–21, 23–24 Jul → session end 2026-07-24) and
    Week 2 Mon–Tue, Thu–Fri (27–28, 30–31 Jul → session end 2026-07-31); Class A
    therefore has schedule.end 2026-07-31, not 2026-08-01. The non-consecutive
    days are recorded in each session's notes field.
  - AGES: per-class `age_range` from the heading — Class E ("ages 14+") is
    open-ended (only a lower bound).
  - LEVEL: D/E are `pre-professional` (years of training + pointe, RAD
    Intermediate Foundation/Advanced reference); A–C carry no stated level.
  - PRICES in HKD: full + early-bird × per-week + 2-week (10% multi-week
    discount), all `tuition`.
  - GENRES: keyword-matched against each class's "Programme includes" syllabus,
    not the shared blurb (so Class A's no-pointe camp doesn't inherit pointe).
  - REQUIREMENTS: D/E require photo submission → `[PhotosReq]`; A–C state none.
  - TEACHERS: named guest faculty (e.g. Sarah Lamb, Claresta Alim) for D/E,
    tagged to their week.
  - APPLICATION: opens 9 Feb 2026, first-come; status is not programmatic so we
    leave it unset and store the Google Form URL.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    PhotosReq,
    Price,
    Requirement,
    Schedule,
    Session,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.hkballet.com"
PROGRAMME = f"{BASE}/en/explore-and-engage/workshops-classes-programme"
APPLY_URL = "https://forms.gle/fEzRBPRzk2zT8Lgz7"

ORG = Organization(
    name="Hong Kong Academy of Ballet",
    slug="hong-kong-academy-of-ballet",
    country="HK",
    city="Hong Kong",
)

# The programme spans two named venues; we record the city/country and keep the
# studio split in the per-session venue notes (which venue serves which days
# varies by class).
LOCATION = Location(city="Hong Kong", country="HK")


def _page_url(year: int) -> str:
    return f"{PROGRAMME}/summerintensive{year}"


def scrape(client: httpx.Client) -> list[Offering]:
    today = date.today()
    # The slug is year-stamped and the bare slug 404s, so try this year and the
    # next/previous edition until one resolves.
    for year in (today.year, today.year + 1, today.year - 1):
        url = _page_url(year)
        resp = client.get(url, follow_redirects=True)
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        offerings = _build_offerings(resp.text, url)
        if offerings:
            return offerings
    return []


def _build_offerings(html: str, url: str) -> list[Offering]:
    text = _text(html)
    # Full-week sessions shared by Classes B–E.
    shared_sessions = _sessions(text)
    if not shared_sessions:
        return []
    # Ended editions are kept (IDR-24): "past" is derived consumer-side from
    # schedule.end, never filtered here.
    season = str(max(s.end.year for s in shared_sessions if s.end))

    # Class A has non-consecutive 4-day weeks; all other classes use the full week.
    class_a_sessions = _class_a_sessions(text)

    offerings: list[Offering] = []
    for klass in _classes(text):
        # Pick the right session list for this class.
        if klass.letter == "A" and class_a_sessions:
            klass_sessions = class_a_sessions
        else:
            klass_sessions = shared_sessions
        klass_start = min((s.start for s in klass_sessions if s.start), default=None)
        klass_end = max((s.end for s in klass_sessions if s.end), default=None)
        offerings.append(
            Offering(
                id=f"hong-kong-academy-of-ballet/summer-intensive-{season}-class-{klass.letter.lower()}",
                source=Source(provider="hong-kong-academy-of-ballet", url=url, scrapedAt=now_utc()),
                title=f"Summer Intensive Programme {season} — Class {klass.letter} (ages {klass.ages_label})",
                genres=klass.genres,
                level=klass.level,
                ageRange=klass.age_range,
                organization=ORG,
                location=LOCATION,
                schedule=Schedule(
                    season=season,
                    start=klass_start,
                    end=klass_end,
                    timezone="Asia/Hong_Kong",
                    sessions=klass_sessions,
                    notes=klass.schedule_note,
                ),
                teachers=klass.teachers,
                prices=klass.prices,
                application=Application(
                    opensAt=klass.opens_at,
                    url=APPLY_URL,
                    requirements=klass.requirements,
                    notes=klass.application_note,
                ),
            )
        )
    return offerings


def _text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    raw = tree.body.text(separator=" ") if tree.body else ""
    return parse.clean(raw)


# --- sessions: the two programme weeks ----------------------------------------

# "[Week 1] 20-25 July, 2026" / "[Week 2] 27 July - 1 August, 2026" — the second
# week spans two months, so each endpoint carries its own (optional) month.
# Matches Class B–E's continuous day-ranges.
_WEEK = re.compile(
    r"\[Week\s*(\d)\]\s*"
    r"(\d{1,2})\s*(?:(" + parse.MONTHALT + r"))?\s*[-–—]\s*"
    r"(\d{1,2})\s*(" + parse.MONTHALT + r"),?\s*(\d{4})",
    re.IGNORECASE,
)

# Class A runs a 4-day camp skipping Wednesday: "[Week 1] 20-21 July, 23-24 July 2026".
# The pattern is two d1-d2 ranges in the same month separated by a comma, with the
# year trailing the second range (no year after the first).
# Note: the page's HTML renders Week 2 as "[Week 2] ] 27 -28 July …" (an extra "]"
# from the bold markup), so we allow an optional stray "]" after the closing bracket.
_CLASS_A_WEEK = re.compile(
    r"\[Week\s*(\d)\]\s*\]?\s*"
    r"(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+(" + parse.MONTHALT + r"),\s*"
    r"(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _sessions(text: str) -> list[Session]:
    seen: set[tuple[date, date]] = set()
    out: list[Session] = []
    for m in _WEEK.finditer(text):
        wk, d1, mon1, d2, mon2, year = m.groups()
        end_month = parse.MONTHS[mon2.lower()]
        start_month = parse.MONTHS[mon1.lower()] if mon1 else end_month
        start = date(int(year), start_month, int(d1))
        end = date(int(year), end_month, int(d2))
        if (start, end) in seen:
            continue
        seen.add((start, end))
        out.append(Session(label=f"Week {wk}", start=start, end=end))
    return out


def _class_a_sessions(text: str) -> list[Session]:
    """Parse Class A's non-consecutive 4-day weeks (Mon-Tue, Thu-Fri per week).

    The page shows e.g. "[Week 1] 20-21 July, 23-24 July 2026" — two day-pairs
    in the same month. We record the first day of each pair as session start and
    the last day of each pair as session end, keeping the non-consecutive days in
    a note so consumers can see the Wednesday gap.
    """
    seen: set[tuple[date, date]] = set()
    out: list[Session] = []
    for m in _CLASS_A_WEEK.finditer(text):
        wk, d1a, d1b, mon1, d2a, d2b, mon2, year = m.groups()
        start_month = parse.MONTHS[mon1.lower()]
        end_month = parse.MONTHS[mon2.lower()]
        start = date(int(year), start_month, int(d1a))
        end = date(int(year), end_month, int(d2b))
        if (start, end) in seen:
            continue
        seen.add((start, end))
        days_note = f"{d1a}–{d1b} & {d2a}–{d2b} {mon2.title()} (Mon–Tue, Thu–Fri; Wed excluded)"
        out.append(Session(label=f"Week {wk}", start=start, end=end, notes=days_note))
    return out


# --- per-class blocks ---------------------------------------------------------

# Each class is "Class X (ages 5-6)" / "Class E (ages 14+)" up to the next class
# heading or the post-class "Photo Requirement" section. The faculty heading also
# appears in the page's section-tab nav *before* the classes, so it can't bound
# the last class — only the "Photo Requirement" block reliably follows Class E.
_CLASS_HEAD = re.compile(
    r"Class\s+([A-E])\s*\(ages\s*(\d{1,2})\s*(?:[-–](\d{1,2})|\+)\s*\)",
    re.IGNORECASE,
)
_BLOCK_END = re.compile(r"Photo Requirement for Application", re.IGNORECASE)

# "Programme includes: … " up to the first dated/venue/fee marker — the syllabus
# list we keyword-match genres against (not the shared intro blurb).
_SYLLABUS = re.compile(
    r"Programme includes:\s*(.*?)(?:\*For students|\[Week|Venue:|Course Fee:)",
    re.IGNORECASE | re.DOTALL,
)

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet technique", "ballet movement", "classical")),
    ("pointe", ("pointe",)),
    ("repertoire", ("variation", "repertor", "repertion")),
    ("contemporary", ("contemporary",)),
]

# "HK$8,400 per week (6 days)" vs "HK$15,120 for 2 weeks" — we label by span.
_FEE_LABELLED = re.compile(
    r"HK\$\s*([\d,]+)\s*(per week|for 2 weeks|2-weeks|2 weeks)",
    re.IGNORECASE,
)
_EARLY_BIRD = re.compile(r"Early Bird", re.IGNORECASE)
# "submitted on or before 24 March 2026" — the early-bird cutoff.
_EARLY_DATE = re.compile(
    r"on or before\s*(\d{1,2})\s*(" + parse.MONTHALT + r")\s*(\d{4})",
    re.IGNORECASE,
)
# "Applications will open on 9 February 2026" / "Starts on 9 February 2026".
_OPENS = re.compile(
    r"(?:open on|Starts on)\s*(\d{1,2})\s*(" + parse.MONTHALT + r")\s*(\d{4})",
    re.IGNORECASE,
)
# "Guest Teacher: Sarah Lamb (Principal Dancer of The Royal Ballet)" — name +
# parenthetical role, scoped per week by the preceding "[Week N]".
_GUEST = re.compile(
    r"\[Week\s*(\d)\][^\[]*?Guest Teacher:\s*([^()\[]+?)\s*\(([^)]+)\)",
    re.IGNORECASE,
)


class _Class:
    """One parsed age-class block (A–E)."""

    def __init__(self, letter: str, age_min: int, age_max: int | None, body: str) -> None:
        self.letter = letter.upper()
        self.age_min = age_min
        self.age_max = age_max
        self._body = body

    @property
    def ages_label(self) -> str:
        return f"{self.age_min}+" if self.age_max is None else f"{self.age_min}-{self.age_max}"

    @property
    def age_range(self) -> dict:
        rng: dict = {"min": self.age_min}
        if self.age_max is not None:
            rng["max"] = self.age_max
        return rng

    @property
    def genres(self) -> list[Genre]:
        m = _SYLLABUS.search(self._body)
        syllabus = m.group(1) if m else self._body
        return parse.match_genres(syllabus, _GENRE_KEYWORDS, default=["classical"])

    @property
    def level(self) -> list[Level]:
        # D/E demand years of prior training + pointe (RAD Intermediate
        # Foundation / Advanced reference) → pre-professional; A–C state none.
        return ["pre-professional"] if "years of ballet training" in self._body.lower() else []

    @property
    def teachers(self) -> list[Teacher]:
        out: list[Teacher] = []
        for m in _GUEST.finditer(self._body):
            wk, name, role = m.groups()
            out.append(
                Teacher(
                    name=parse.clean(name),
                    role=f"Guest Teacher (Week {wk}) — {parse.clean(role)}",
                )
            )
        return out

    @property
    def prices(self) -> list[Price]:
        prices: list[Price] = []
        # The block has a full-price section then an "Early Bird Offer" section;
        # everything after the marker is the discounted tier.
        eb = _EARLY_BIRD.search(self._body)
        regular = self._body[: eb.start()] if eb else self._body
        early = self._body[eb.start() :] if eb else ""
        prices += self._fees(regular, "Course fee", early=False)
        prices += self._fees(early, "Early bird", early=True)
        return prices

    def _fees(self, segment: str, label_prefix: str, *, early: bool) -> list[Price]:
        cutoff = None
        if early:
            d = _EARLY_DATE.search(segment)
            cutoff = (
                f"by {parse.clean(d.group(1))} {d.group(2).title()} {d.group(3)}" if d else None
            )
        out: list[Price] = []
        for m in _FEE_LABELLED.finditer(segment):
            amount = parse.parse_amount(m.group(1))
            if amount is None:
                continue
            span = "2 weeks" if "2" in m.group(2) or "for" in m.group(2).lower() else "per week"
            label = f"{label_prefix} — {span}"
            note = cutoff if early else None
            out.append(
                Price(amount=amount, currency="HKD", label=label, includes=["tuition"], notes=note)
            )
        return out

    @property
    def requirements(self) -> list[Requirement]:
        # D/E ask for photographs as part of the application; A–C state nothing.
        # The page only asks for "photographs" without naming poses, so this is
        # `freeform`, not `defined-poses` (which would carry a named-pose list).
        if "submit photograph" in self._body.lower() or "must submit photo" in self._body.lower():
            return [PhotosReq(specificity="freeform", notes="Photo submission required")]
        return []

    @property
    def opens_at(self) -> date | None:
        m = _OPENS.search(self._body)
        if not m:
            return None
        return date(int(m.group(3)), parse.MONTHS[m.group(2).lower()], int(m.group(1)))

    @property
    def schedule_note(self) -> str | None:
        m = re.search(r"Venue:\s*(.+?)(?:Course Fee:|Application)", self._body, re.DOTALL)
        return parse.clean(m.group(1)) if m else None

    @property
    def application_note(self) -> str | None:
        m = re.search(
            r"Application (?:Period|Requirements)\s*:?\s*(.+?)(?:APPLY HERE|$)",
            self._body,
            re.DOTALL,
        )
        return parse.clean(m.group(1)) if m else None


def _classes(text: str) -> list[_Class]:
    heads = list(_CLASS_HEAD.finditer(text))
    end_marker = _BLOCK_END.search(text)
    limit = end_marker.start() if end_marker else len(text)
    out: list[_Class] = []
    for i, h in enumerate(heads):
        body_end = heads[i + 1].start() if i + 1 < len(heads) else limit
        age_max = int(h.group(3)) if h.group(3) else None
        out.append(_Class(h.group(1), int(h.group(2)), age_max, text[h.start() : body_end]))
    return out
