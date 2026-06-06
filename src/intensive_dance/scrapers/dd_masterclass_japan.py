"""D&D Masterclass Japan (D&D Art Production), Tokyo + Osaka (JP).

The summer ballet masterclass run by David Makhateli (founder of D&D Art
Productions / the "Grand Audition" company audition), taught in the Royal Ballet
School tradition with guest teacher Valeri Hristov of The Royal Ballet School.

API FIRST: none usable. The site (`dd-balletjapan.com`) is a Wix build, but —
like the other Wix providers in the register — it server-renders the full text
into the static HTML (dates, ages, prices, faculty all present), so a plain fetch
of each city page is enough; no JS render or proxy escalation was needed
(verified 2026-06). The aggregator listings (balletchannel.jp / ballet-search.com)
are deliberately ignored — this is D&D Art Production's own primary page.

DISCOVERY: the 18th edition runs as **two separate city sessions** with distinct
dates, venues, fees and pianist — Tokyo (恵比寿 Studio H, 7/24–27) and Osaka
(Garage Art Space, 7/28–30). They are genuinely different editions of the same
course, so we emit **one Offering per city** (folding would lose the per-city
dates/venue/price split). Each city page splits enrolment into two age groups
(Group A 12–15 / Group B 16+) that share the curriculum, fee and dates, so the
groups become one `Session` each (the model's per-group age band lives on
`Session`); the Offering ageRange spans both groups.

JAPANESE SOURCE: parsed language-agnostically and kept faithfully (no inline
translation). The course-date line uses **full-width digits** and carries no year
("７月２４日（金）から２６日（日）" plus the open-day line "７月２７日（月）"); the year
(2026) is read from the price/deadline lines ("2026年6月20日申請分まで"). Ages are
plain numbers ("１２歳から１５歳", "１６歳から" = open-ended). JPY amounts are
tax-inclusive (全て税込価格).

WHAT THIS SCRAPER EXERCISES (verified live 2026-06):
  - Two Offerings from two sibling pages (per-city split), distinct dates/venue/
    prices/pianist; each with two `Session`s (Group A/B) — one open-ended age max.
  - Full-width-digit, year-less date lines resolved against the deadline year, and
    the open-day line extending the span past the "から" range close.
  - A rich JPY price ladder (early-bird / regular / single-day / private-lesson /
    returning-student discount), all tax-inclusive.
  - classical + pointe + repertoire genres (Ballet Class / Pointe / Variation);
    no contemporary class is taught, so it isn't claimed.
  - Named faculty: Makhateli (founder), Hristov (RBS guest), and the city pianist.
  - Requirements stay `[]` ("not stated"): the masterclass doubles as an audition
    for scholarships, but the public page states no photo/video entry brief and the
    "about" page is explicit it is a class, not an entry audition — so nothing is
    invented; the scholarship/audition note is kept verbatim.
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
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Session,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.dd-balletjapan.com"

ORG = Organization(
    name="D&D Masterclass Japan",
    slug="dd-masterclass-japan",
    country="JP",
)


class _City:
    def __init__(self, key: str, page: str, label_ja: str, timezone: str) -> None:
        self.key = key
        self.page = f"{BASE}/{page}"
        self.label_ja = label_ja
        self.timezone = timezone


# The two city pages of the current (18th) edition. 404 → that city drops out.
_CITIES = [
    _City("tokyo", "18th-tokyo", "東京", "Asia/Tokyo"),
    _City("osaka", "18th-osaka", "大阪", "Asia/Tokyo"),
]


def scrape(client: httpx.Client) -> list[Offering]:
    offerings: list[Offering] = []
    for city in _CITIES:
        resp = client.get(city.page, follow_redirects=True)
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        offering = _build_offering(resp.text, city)
        if offering is not None:
            offerings.append(offering)
    return offerings


def _build_offering(html: str, city: _City) -> Offering | None:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = (parse.clean(tree.body.text(separator=" ")) if tree.body else "").translate(
        parse.FULLWIDTH_DIGITS_TRANS
    )

    year = _year(text)
    if year is None:
        return None  # no dated edition parseable
    start, end = _date_range(text, year)
    if start is None:
        return None
    season = str(year)

    sessions = _sessions(text)
    return Offering(
        id=f"dd-masterclass-japan/18th-{city.key}-{season}",
        source=Source(provider="dd-masterclass-japan", url=city.page, scrapedAt=now_utc()),
        title=f"18th D&D Masterclass {city.label_ja} {season}",
        genres=_genres(text),
        ageRange=_offering_age_range(sessions),
        organization=ORG,
        location=_location(text, city),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone=city.timezone,
            sessions=sessions,
        ),
        teachers=_teachers(text),
        prices=_prices(text),
        application=Application(
            deadline=_deadline(text, year),
            url=city.page,
            notes=_scholarship_note(text),
        ),
    )


# --- year: read from the price/deadline lines "2026年6月20日申請分まで" --------------
#
# The course-date line is year-less; the only year on the page is in the
# application-deadline rows, so the earliest such year anchors the edition.

_YEAR = re.compile(r"(\d{4})年\s*\d{1,2}月\s*\d{1,2}日申請")


def _year(text: str) -> int | None:
    years = [int(m.group(1)) for m in _YEAR.finditer(text)]
    return min(years) if years else None


# --- dates --------------------------------------------------------------------
#
# Main span "7月24日（金）から26日（日）" (shared month, bare closing day), then a
# separate open-day line "7月27日（月）" that runs a day past the range close. The
# course actually ends on the open day, so the end is the max day seen in the
# whole 7月…日 run for that month.

_RANGE = re.compile(r"(\d{1,2})月\s*(\d{1,2})日[^月]*?から\s*(\d{1,2})日")
_OPEN_DAY = re.compile(
    r"(\d{1,2})月\s*(\d{1,2})日（[月火水木金土日]）\s*Group\s*A\s*[\d:]+\s*-\s*[\d:]+\s*Open\s*day"
)


def _date_range(text: str, year: int) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    month, d1, d2 = (int(g) for g in m.groups())
    start = date(year, month, d1)
    end = date(year, month, d2)
    # The open-day line (if any) extends the span past the "から" range close.
    om = _OPEN_DAY.search(text)
    if om and int(om.group(1)) == month:
        open_end = date(year, month, int(om.group(2)))
        if open_end > end:
            end = open_end
    return start, end


# --- deadline: the earliest "YYYY年M月D日申請分まで" (the early-bird cut-off) --------

_DEADLINE = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日申請")


def _deadline(text: str, year: int) -> date | None:
    dates = [
        date(int(m.group(1)), int(m.group(2)), int(m.group(3))) for m in _DEADLINE.finditer(text)
    ]
    return min(dates) if dates else None


# --- groups → sessions --------------------------------------------------------
#
# "Group A 12歳から15歳（4年以上のバレエ経験者）" and "Group B 16歳から" (open-ended).
# Both groups share dates/fee/curriculum, so each is a `Session` carrying its own
# age band; the raw eligibility text is kept verbatim in notes.

_GROUP_A = re.compile(r"Group\s*A\s*(\d{1,2})歳から(\d{1,2})歳\s*(（[^）]*）)?")
_GROUP_B = re.compile(r"Group\s*B\s*(\d{1,2})歳から(?!\d)")


def _sessions(text: str) -> list[Session]:
    sessions: list[Session] = []
    a = _GROUP_A.search(text)
    if a:
        eligibility = parse.clean(a.group(3)) if a.group(3) else ""
        note = f"Group A {a.group(1)}歳から{a.group(2)}歳" + eligibility
        sessions.append(
            Session(
                label="Group A",
                ageRange={"min": int(a.group(1)), "max": int(a.group(2))},
                notes=parse.clean(note),
            )
        )
    b = _GROUP_B.search(text)
    if b:
        sessions.append(
            Session(
                label="Group B",
                ageRange={"min": int(b.group(1)), "max": None},
                notes=f"Group B {b.group(1)}歳から（上限なし）",
            )
        )
    return sessions


def _offering_age_range(sessions: list[Session]) -> dict | None:
    bounds = [s.age_range for s in sessions if s.age_range]
    if not bounds:
        return None
    maxes = [b["max"] for b in bounds]
    # If any group is open-ended (Group B = 16+), the offering's upper bound is too.
    overall_max = None if any(m is None for m in maxes) else max(maxes)
    return {"min": min(b["min"] for b in bounds), "max": overall_max}


# --- location: "Studio H （アッシュ） 住所：〒150-0013 東京都…" -----------------------
#
# Venue name precedes "住所：", which is followed by the postcode + prefecture
# address; the prefecture token (東京都/大阪府/…) gives the city for the record.

_VENUE = re.compile(r"Location\s+(.+?)\s*住所[：:]")
_ADDRESS = re.compile(r"住所[：:]\s*〒[\d－\-]+\s*([^ ]+?[都道府県][^ ]*)")
_CITY = {"tokyo": "Tokyo", "osaka": "Osaka"}


def _location(text: str, city: _City) -> Location:
    vm = _VENUE.search(text)
    venue = parse.clean(vm.group(1)) if vm else None
    return Location(venue=venue, city=_CITY[city.key], country="JP")


# --- prices: the JPY ladder, all tax-inclusive (全て税込) -----------------------
#
# Rows read "<label> <span> <amount>円 …": early-bird / regular multi-day, a
# single-day fee, a per-15-min private lesson, and a returning-student discount.

_PRICE_ROWS: list[tuple[str, re.Pattern[str]]] = [
    ("早割料金（全日程・税込）", re.compile(r"早割料金\s*\d+日間\s*([\d,]+)円")),
    ("通常料金（全日程・税込）", re.compile(r"通常料金\s*\d+日間\s*([\d,]+)円")),
    ("1日受講（税込）", re.compile(r"1日受講[^0-9]*?([\d,]+)円")),
    (
        "プライベートレッスン（15分・税込）",
        re.compile(r"プライベートレッスン[／/]?\s*(?:\d+分)?\s*([\d,]+)円"),
    ),
    ("第16・17回受講者割引（全日程・税込）", re.compile(r"受講者割引\s*([\d,]+)円")),
]


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    for label, pat in _PRICE_ROWS:
        m = pat.search(text)
        if not m:
            continue
        amount = parse.parse_amount(m.group(1))
        if amount is None:
            continue
        prices.append(Price(amount=amount, currency="JPY", label=label, includes=["tuition"]))
    return prices


# --- genres -------------------------------------------------------------------
#
# Ballet Class + Pointe class + Variation (= repertoire). No contemporary class is
# taught, so contemporary is not claimed.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet class", "バレエ")),
    ("pointe", ("pointe", "ポアント", "ポワント")),
    ("repertoire", ("variation", "ヴァリエーション", "レパートリー")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text.lower(), _GENRE_KEYWORDS, default=["classical"])


# --- teachers: founder + RBS guest + city pianist -----------------------------
#
# Three named roles, each "<JP name>（<English>）" (full- or half-width parens):
# the founder (David Makhateli), the special guest (特別講師 Valeri Hristov, RBS),
# and the per-city pianist (Pianist …). Only the named, verifiable roles are kept.

_MAKHATELI = re.compile(r"(デヴィッド・マッカテリ)（David Makhateli）")
_HRISTOV = re.compile(r"特別講師\s*(ヴァレリ・ヒリストフ)（Valeri Hristov）")
_PIANIST = re.compile(r"Pianist\s*([^()（]+?)\s*[（(]([^)）]+)[)）]")


def _teachers(text: str) -> list[Teacher]:
    teachers: list[Teacher] = []
    if _MAKHATELI.search(text):
        teachers.append(Teacher(name="David Makhateli", role="主催（D&D Art Productions 創設者）"))
    if _HRISTOV.search(text):
        teachers.append(Teacher(name="Valeri Hristov", role="特別講師（The Royal Ballet School）"))
    pm = _PIANIST.search(text)
    if pm:
        teachers.append(Teacher(name=parse.clean(pm.group(2)), role="ピアニスト"))
    return teachers


# --- scholarship / audition note (kept verbatim, not turned into requirements) -

_SCHOLARSHIP = re.compile(r"(ヨーロッパ名門バレエ学校への短期スカラシップ留学権[^。]*。)")


def _scholarship_note(text: str) -> str | None:
    m = _SCHOLARSHIP.search(text)
    return parse.clean(m.group(1)) if m else None
