"""K-Ballet School (Kバレエ スクール), Tokyo (JP) — its Summer Intensive and
Winter Intensive (夏期特別講習会 / 冬期特別講習会).

API FIRST: none. The K-Ballet site (Apache, no public JSON API) serves its event
pages as plain server-rendered HTML under `/school/event/`; the current editions'
full text — dates, venues, courses, fees, faculty — is in the static markup, no JS
render needed. Summer lives at `/school/event/<year>summerintensive.html`; winter
at `/school/event/<year>winterassembly.html`. Both are discovered by scanning
the `/school/event/` listing for the relevant URL-keyword patterns.

DISCOVERY: each intensive announces the same four age-banded courses, each at its
own venue, with its own dates and fee schedule — one Offering per course (per the
model's one-Offering-per-track rule — folding would lose the date/venue/fee/genre
split):
  - キッズ (Kids) — preschool 〈年中・年長〉.
  - ファウンデーション (Foundation) — primary grades 1–3.
  - エレメンタリー (Elementary) — primary grades 4–6.
  - インターメディエイト (Intermediate) — junior-high and up.
The slug is year-stamped; "summer" and "winter" are separate slug stems so the
eight Offerings never collide.

JAPANESE SOURCE: parsed language-agnostically. Summer: per-course `【日程】` blocks,
`【会場】` venue label, `【受講料】` fee section, year from `開催日程 YYYY.` header.
Winter: a table-layout page — `クラス {Name}` / `コース日程` / `会場` / `受講料` field
labels (without `【】` brackets). In both cases the year lives in the
`開催日程 YYYY.` page header and the M/D ranges in per-course blocks; the
`_date_range` regex `M/D(曜)` safely ignores the
YYYY. prefix in the winter course-detail rows (verified: the 2025 winter page
has `会場 2026.12/26(金)～12/27(土)` in detail rows but `開催日程 2025.` in the
overview — a data-entry error; we read the year from the overview, not the rows).
Source free text is kept faithfully in Japanese.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-06 summer; 2025-12 winter via
archived page):
  - Eight Offerings total (four summer + four winter), distinct venue + prices.
  - JPY prices (税込), several per course (A/B/C sub-courses, optional Solo
    Assembly performance fee).
  - Two page-layout modes: summer (`【label】` blocks) vs winter (plain label rows).
  - Contemporary genre on Intermediate only (both seasons).
  - Grade-banded age ranges via the statutory April-entry schedule.

Discovery strategy: the `/school/event/` listing is scanned for links whose href
contains the keyword "summerintensive" or "winterassembly"; the most recently
listed matching link is used. If discovery finds no winter URL, we fall back to
the explicit latest-known URL rather than silently dropping the edition.
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
LISTING_URL = f"{BASE}/school/event/"
PAGE_SUMMER = f"{BASE}/school/event/2026summerintensive.html"
# Latest-known winter URL used as a fallback if discovery fails (IDR-24: keep past
# editions; the listing may lag behind newly posted pages).
PAGE_WINTER_FALLBACK = f"{BASE}/school/event/2025winterassembly.html"
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

# Source titles (kept faithfully in Japanese; not translated inline).
TITLE_SUMMER_JA = "サマーインテンシブ（夏期特別講習会）"
TITLE_WINTER_JA = "ウインター インテンシブ（冬期特別講習会）"


class _Course:
    def __init__(self, key: str, heading: str, label: str) -> None:
        self.key = key
        self.heading = heading  # the <h3> program-block heading to slice on
        self.label = label  # the cohort label kept in the title (faithful JA)


# Order matches the summer page; `heading` is the program-detail <h3> text we
# slice on for the summer layout (【日程】 / 【会場】 / 【受講料】 blocks).
_COURSES_SUMMER = [
    _Course("kids", "キッズ：年中～年長対象", "キッズ〈年中・年長〉"),
    _Course(
        "foundation", "ファウンデーション：小学1～3年生対象", "ファウンデーション〈小学1～3年生〉"
    ),
    _Course("elementary", "エレメンタリー：小学4～6年生対象", "エレメンタリー〈小学4～6年生〉"),
    _Course(
        "intermediate", "インターメディエイト：中学生以上対象", "インターメディエイト〈中学生以上〉"
    ),
]

# Winter page uses a table layout; course blocks are keyed on "クラス {Name}".
# The heading field here is the クラス-row label; label is the title label.
_COURSES_WINTER = [
    _Course("kids", "クラス キッズ", "キッズ〈年中・年長〉"),
    _Course("foundation", "クラス ファウンデーション", "ファウンデーション〈小学1～3年生〉"),
    _Course("elementary", "クラス エレメンタリー", "エレメンタリー〈小学4～6年生〉"),
    _Course("intermediate", "クラス インターメディエイト", "インターメディエイト〈中学生以上〉"),
]

# The program-detail section ends here (the 申込方法 / faculty bios follow).
_BLOCKS_END = "お申込方法"
# Winter: after the last course block comes the course-description section.
_WINTER_BLOCKS_END = "クラス内容紹介"


def scrape(client: httpx.Client) -> list[Offering]:
    offerings: list[Offering] = []

    resp_summer = client.get(PAGE_SUMMER, follow_redirects=True)
    if resp_summer.status_code != 404:
        resp_summer.raise_for_status()
        offerings.extend(_build_offerings(resp_summer.text))

    winter_url = _discover_url(client, "winterassembly") or PAGE_WINTER_FALLBACK
    resp_winter = client.get(winter_url, follow_redirects=True)
    if resp_winter.status_code != 404:
        resp_winter.raise_for_status()
        offerings.extend(_build_winter_offerings(resp_winter.text, winter_url))

    return offerings


def _discover_url(client: httpx.Client, keyword: str) -> str | None:
    """Scan the /school/event/ listing for the latest link whose href contains `keyword`.

    The listing may contain multiple editions (e.g. 2024winterassembly before 2025winterassembly).
    We collect all matches and return the lexicographically greatest href — year-prefixed URLs
    sort correctly by year, so max() picks the most recently announced edition.
    """
    resp = client.get(LISTING_URL, follow_redirects=True)
    if not resp.is_success:
        return None
    return _select_url(resp.text, keyword)


def _select_url(listing_html: str, keyword: str) -> str | None:
    tree = HTMLParser(listing_html)
    matches: list[str] = []
    for a in tree.css("a[href]"):
        href = a.attributes.get("href", "") or ""
        if keyword in href:
            matches.append(href if href.startswith("http") else f"{BASE}{href}")
    return max(matches) if matches else None


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
    for course in _COURSES_SUMMER:
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
        source=Source(provider="k-ballet-school", url=PAGE_SUMMER, scrapedAt=now_utc()),
        title=f"{TITLE_SUMMER_JA} {course.label} {season}",
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


# --- winter intensive ---------------------------------------------------------
#
# The winter page uses a table/grid layout instead of the summer's 【label】 block
# style. Course blocks are keyed on "クラス {Name}" rows, and fields are labelled
# with plain text (コース日程 / 会場 / 対象学年 / 受講料) without 【】 brackets.
#
# The 2025 winter page also contains a data-entry error: the detail rows show
# e.g. "2026.12/26(金)～12/27(土)" while the overview header reads "2025. 12/26".
# The year is correctly read from the overview header; the _date_range regex
# (matching (\d{1,2})/(\d{1,2})) safely ignores the "2026." prefix in those rows.


def _build_winter_offerings(html: str, url: str) -> list[Offering]:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    year = _year(text)
    if year is None:
        return []
    season = str(year)

    offerings: list[Offering] = []
    for course in _COURSES_WINTER:
        block = _winter_course_block(text, course)
        if block is None:
            continue
        start, end = _date_range(block, year)
        if start is None and end is None:
            continue
        age = _winter_age_range(block)
        offerings.append(
            Offering(
                id=f"k-ballet-school/winter-intensive-{course.key}-{season}",
                source=Source(provider="k-ballet-school", url=url, scrapedAt=now_utc()),
                title=f"{TITLE_WINTER_JA} {course.label} {season}",
                genres=_genres(block),
                ageRange=age,
                organization=ORG,
                location=_winter_location(block),
                schedule=Schedule(
                    season=season,
                    start=start,
                    end=end,
                    timezone="Asia/Tokyo",
                ),
                prices=_winter_prices(block),
                application=Application(url=APPLY_URL),
            )
        )
    return offerings


def _winter_course_block(text: str, course: _Course) -> str | None:
    """Slice from this course's "クラス {Name}" row to the next course row."""
    start = text.find(course.heading)
    if start < 0:
        return None
    end = len(text)
    for other in _COURSES_WINTER:
        pos = text.find(other.heading, start + len(course.heading))
        if 0 <= pos < end:
            end = pos
    end_marker = text.find(_WINTER_BLOCKS_END, start)
    if 0 <= end_marker < end:
        end = end_marker
    return text[start:end]


# Winter venue: "会場 Kバレエ スクール 武蔵小杉 〒..." or "会場 Kバレエ アカデミー 〒..."
_WINTER_VENUE = re.compile(r"会場\s+(Kバレエ\s+\S+(?:\s+\S+)??)(?:\s+〒|\s+\d{3})")


def _winter_location(block: str) -> Location:
    m = _WINTER_VENUE.search(block)
    venue = parse.clean(m.group(1)) if m else None
    return Location(venue=venue, city="Tokyo", country="JP")


# Winter age range: "対象学年 年中・年長" / "対象学年 小学1～3年生" / "対象学年 中学生以上"
_WINTER_AGE_LABEL = re.compile(r"対象学年\s+([^\s外内部]+)")


def _winter_age_range(block: str) -> dict | None:
    m = _WINTER_AGE_LABEL.search(block)
    return _age_range(m.group(1)) if m else None


# Winter price: plain "受講料 22,000円(税込)" (no 【受講料】 bracket)
_WINTER_FEE = re.compile(r"受講料\s+([\d,]+)\s*円\s*[（(]税込[)）]")


def _winter_prices(block: str) -> list[Price]:
    m = _WINTER_FEE.search(block)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    return [Price(amount=amount, currency="JPY", label="受講料（税込）", includes=["tuition"])]


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
    for other in _COURSES_SUMMER:
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
