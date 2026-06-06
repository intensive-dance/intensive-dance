"""K-Ballet School (Kバレエ スクール), Tokyo (JP) — its Summer Intensive (夏期特別講習会).

API FIRST: none. The K-Ballet site (Apache, no public JSON API) serves its event
pages as plain server-rendered HTML under `/school/event/`; the current edition's
full text — dates, venues, courses, fees, faculty — is in the static markup, no JS
render needed. The dated edition lives at `/school/event/<year>summerintensive.html`,
found from the `/school/event/` listing.

DISCOVERY: the page announces one short-term student intensive — the school's
annual "Summer Intensive 〈夏期特別講習会〉", run by K-Ballet School (the open school
of K-Ballet Tokyo; founder Tetsuya Kumakawa, ex-Royal Ballet principal). The
source splits it into **four age-banded courses**, each at its own venue, with
its own dates and fee schedule, so we emit **one Offering per course** (per the
model's one-Offering-per-track rule — folding would lose the date/venue/fee/genre
split):
  - キッズ (Kids) — preschool 〈年中・年長〉, Ebisu, a 3-day course.
  - ファウンデーション (Foundation) — primary grades 1–3, Korakuen; A/B/C sub-courses
    span different parts of the week.
  - エレメンタリー (Elementary) — primary grades 4–6, Kichijoji; A (comprehensive) /
    B (solo) sub-courses, with an optional Solo Assembly performance fee.
  - インターメディエイト (Intermediate) — junior-high and up, Ebisu; A/B sub-courses,
    the A curriculum adding contemporary, pas de deux, mime and drama.
The slug is year-stamped so the id rolls forward when a new edition is posted.

JAPANESE SOURCE: parsed language-agnostically. Per-course `【日程】` lines give the
span as `M/D(曜)～M/D(曜)` with the **year only in the page-level header**
(`開催日程 2026. 8/2(日)～8/9(日)`); we read the year there and the earliest start /
latest end across each block's ranges (Foundation lists A/B/C windows, so the span
brackets them). Fees are ASCII `34,000円(税込)` (tax-inclusive). Source free text
(course title, grade band, faculty names, raw date/fee notes) is kept faithfully
in Japanese, never translated inline.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-06):
  - Four Offerings from one page (per-course split), distinct venue + prices.
  - JPY prices (tax-inclusive 税込), several per course — the A/B/C sub-courses and
    the optional Solo-Assembly performance fee carry a `performance` include.
  - Year-from-header / day-month-from-block date assembly, full-width `～` ranges,
    a mid-week 休講 (no-class day) kept as a schedule note.
  - Contemporary genre on the Intermediate course only (its A curriculum adds
    コンテンポラリー), matched against that course's own program block; the others
    stay classical.
  - Grade-banded cohorts the source states as Japanese school grades, mapped to
    `ageRange` by the statutory April-entry schedule (AGENTS.md), the same as the
    sibling JP scrapers. The raw band stays verbatim in the title label. Three
    band shapes: 小学N～M年生 (grade range), 中学生以上 (open-topped), and 年中～年長
    (kindergarten — named, not graded, so mapped locally not via the shared helper).
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
    Source,
    now_utc,
)

BASE = "https://www.k-ballet.co.jp"
PAGE = f"{BASE}/school/event/2026summerintensive.html"
# Application is by an external Google Form linked from the page ("申込はこちら").
APPLY_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLScUXFlBN7rd6TJCXwTgZBj88TNZNGrQojJKzT3KUjpa05WnQQ/viewform"
)

ORG = Organization(
    name="K-Ballet School",
    slug="k-ballet-school",
    country="JP",
    city="Tokyo",
)

# The source title (kept faithfully in Japanese; not translated inline).
TITLE_JA = "サマーインテンシブ（夏期特別講習会）"


class _Course:
    def __init__(self, key: str, heading: str, label: str) -> None:
        self.key = key
        self.heading = heading  # the <h3> program-block heading to slice on
        self.label = label  # the cohort label kept in the title (faithful JA)


# Order matches the page; `heading` is the program-detail <h3> text we slice on.
_COURSES = [
    _Course("kids", "キッズ：年中～年長対象", "キッズ〈年中・年長〉"),
    _Course(
        "foundation", "ファウンデーション：小学1～3年生対象", "ファウンデーション〈小学1～3年生〉"
    ),
    _Course("elementary", "エレメンタリー：小学4～6年生対象", "エレメンタリー〈小学4～6年生〉"),
    _Course(
        "intermediate", "インターメディエイト：中学生以上対象", "インターメディエイト〈中学生以上〉"
    ),
]

# The program-detail section ends here (the 申込方法 / faculty bios follow).
_BLOCKS_END = "お申込方法"


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE, follow_redirects=True)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return _build_offerings(resp.text)


def _build_offerings(html: str) -> list[Offering]:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    year = _year(text)
    if year is None:
        return []  # no dated edition parseable
    season = str(year)

    offerings: list[Offering] = []
    for course in _COURSES:
        block = _course_block(text, course)
        if block is None:
            continue
        start, end = _date_range(block, year)
        if start is None and end is None:
            continue
        offerings.append(_build_offering(course, block, season, start, end))
    return offerings


def _build_offering(
    course: _Course,
    block: str,
    season: str,
    start: date | None,
    end: date | None,
) -> Offering:
    return Offering(
        id=f"k-ballet-school/summer-intensive-{course.key}-{season}",
        source=Source(provider="k-ballet-school", url=PAGE, scrapedAt=now_utc()),
        title=f"{TITLE_JA} {course.label} {season}",
        genres=_genres(block),
        ageRange=_age_range(course.heading),
        organization=ORG,
        location=_location(block),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Asia/Tokyo",
            notes=_dates_note(block),
        ),
        prices=_prices(block),
        application=Application(url=APPLY_URL),
    )


# --- course split -------------------------------------------------------------
#
# The program detail lists each course under its own <h3>, e.g. "キッズ：年中～年長
# 対象", in page order. We slice from one heading to the next (and the last to the
# 申込方法 section) so a course's own dates/venue/fees/genres never leak across.


def _course_block(text: str, course: _Course) -> str | None:
    start = text.find(course.heading)
    if start < 0:
        return None
    # End at the next course heading, or the post-course 申込方法 section.
    end = len(text)
    for other in _COURSES:
        pos = text.find(other.heading, start + len(course.heading))
        if 0 <= pos < end:
            end = pos
    apply_pos = text.find(_BLOCKS_END, start)
    if 0 <= apply_pos < end:
        end = apply_pos
    return text[start:end]


# --- ages: grade bands → numeric range ----------------------------------------
#
# Each course states a Japanese school-grade band, mapped to ages by the
# statutory April-entry schedule (AGENTS.md), the upper bound being the end of
# the top grade's year (one past its start age). Three shapes appear:
#   "小学1～3年生" / "小学4～6年生" — level + grade range (shared 小/中 helper)
#   "中学生以上"                    — level, open-topped (min only)
#   "年中～年長"                    — kindergarten (年少/年中/年長), named not graded
# Kindergarten levels don't fit the (level, grade) helper, so they map locally.
_KINDERGARTEN_AGES = {"年少": 3, "年中": 4, "年長": 5}
_GRADE_BAND = re.compile(r"(小学|中学|高校)\s*(\d)(?:\s*[～~\-–]\s*(\d))?")
_LEVEL_PLUS = re.compile(r"(小学|中学|高校)生?\s*以上")
_KINDER_BAND = re.compile(r"(年少|年中|年長)(?:\s*[～~\-–・]\s*(年少|年中|年長))?")


def _age_range(band: str) -> dict | None:
    if m := _GRADE_BAND.search(band):
        level, low_grade, high_grade = m.group(1), int(m.group(2)), m.group(3)
        low = parse.japanese_grade_to_age(level, low_grade)
        top = int(high_grade) if high_grade else low_grade
        return {"min": low, "max": parse.japanese_grade_to_age(level, top) + 1}
    if m := _LEVEL_PLUS.search(band):
        return {"min": parse.japanese_grade_to_age(m.group(1), 1), "max": None}
    if m := _KINDER_BAND.search(band):
        low = _KINDERGARTEN_AGES[m.group(1)]
        high = _KINDERGARTEN_AGES[m.group(2)] if m.group(2) else low
        return {"min": low, "max": high + 1}
    return None


# --- dates --------------------------------------------------------------------
#
# Per-course spans are written `M/D(曜)～M/D(曜)` with NO year — the year lives only
# in the page header ("開催日程 2026. 8/2(日)～8/9(日)"). We read the year there, then
# take the earliest start and latest end across the block's ranges (Foundation
# lists A/B/C windows; the course span brackets them all). A mid-week 休講 day is
# not removed — it's a no-class day inside the span, kept as a schedule note.

_YEAR = re.compile(r"開催日程\s*(\d{4})\s*[.．]")
# "8/2(日)～8/9(日)" / "8/6(木)～8/9(日)" — full-width or ASCII tilde/dash separator.
_RANGE = re.compile(r"(\d{1,2})/(\d{1,2})\s*\([^)]*\)\s*[～~\-–]\s*(\d{1,2})/(\d{1,2})")


def _year(text: str) -> int | None:
    m = _YEAR.search(text)
    return int(m.group(1)) if m else None


def _date_range(block: str, year: int) -> tuple[date | None, date | None]:
    starts: list[date] = []
    ends: list[date] = []
    for m in _RANGE.finditer(block):
        m1, d1, m2, d2 = (int(g) for g in m.groups())
        starts.append(date(year, m1, d1))
        ends.append(date(year, m2, d2))
    if not starts:
        return None, None
    return min(starts), max(ends)


def _dates_note(block: str) -> str | None:
    # Keep this course's own raw 【日程】 line (A/B/C windows, the 休講 caveat, …).
    m = re.search(r"【日程】\s*([^【]+?)\s*【会場】", block)
    return parse.clean(m.group(1)) if m else None


# --- location: the per-course venue line "【会場】 Kバレエ スクール 恵比寿 …" ---------

_VENUE = re.compile(r"【会場】\s*(Kバレエ スクール\s*\S+)")


def _location(block: str) -> Location:
    m = _VENUE.search(block)
    venue = parse.clean(m.group(1)) if m else None
    return Location(venue=venue, city="Tokyo", country="JP")


# --- prices: "34,000円(税込)" — JPY, tax-inclusive (税込) -------------------------
#
# A course lists several fees: A/B/C sub-courses and (Elementary/Intermediate) an
# optional "+ソロアッセンブリー参加" (Solo Assembly performance) tier. We keep each as
# its own Price, labelled with the source's own sub-course text, and tag the
# Solo-Assembly tiers with a `performance` include.

_FEE = re.compile(r"([^\s：:【】]*[：:])?\s*([\d,]+)\s*円\s*(（税込）|\(税込\))")


def _prices(block: str) -> list[Price]:
    # Read fees only from the 【受講料】 section so teacher-bio numbers don't leak in.
    m = re.search(r"【受講料】\s*(.+?)(?:スケジュール|【|申込|＊|$)", block)
    fee_text = m.group(1) if m else block
    prices: list[Price] = []
    for fm in _FEE.finditer(fee_text):
        amount = parse.parse_amount(fm.group(2))
        if amount is None:
            continue
        sub = parse.clean(fm.group(1) or "").rstrip("：:")
        label = f"受講料 {sub}（税込）" if sub else "受講料（税込）"
        includes: list = ["tuition"]
        if "ソロアッセンブリー" in (sub or ""):
            includes.append("performance")
        prices.append(Price(amount=amount, currency="JPY", label=label, includes=includes))
    return prices


# --- genres: matched against THIS course's program block -----------------------
#
# Every course is fundamentally a ballet course (its program lists バレエクラス /
# ストレッチ＆バー), so `classical` is always present. The discriminating genres are
# scoped to the course block so the Intermediate course's コンテンポラリー doesn't
# leak onto Kids/Foundation, and pointe (ポワント) / repertoire (レパートリー・
# ヴァリエーション) only attach where that course's curriculum lists them.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("pointe", ("ポワント",)),
    ("repertoire", ("ヴァリエーション", "レパートリー")),
    ("contemporary", ("コンテンポラリー",)),
]


def _genres(block: str) -> list[Genre]:
    extra = parse.match_genres(block, _GENRE_KEYWORDS)
    return ["classical", *extra]
