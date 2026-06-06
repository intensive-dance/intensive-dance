"""The Tokyo Ballet School (東京バレエ学校), Tokyo (JP) — its 夏休み特別講習会.

The school of The Tokyo Ballet / NBS (公益財団法人日本舞台芸術振興会), Japan's
foremost touring company.

API FIRST: none. The site is a static, server-rendered template (Mobirise-style
HTML; the full text is in the markup, no JSON API and no JS render needed). The
current edition is a dated news/kodomo post — the "夏休み特別講習会2026" page,
reached from the news listing (`/news/`).

DISCOVERY: the page announces one short-term student intensive — the 夏休み特別
講習会 (Summer Special Workshop), a 4-day short course (4日間の短期集中講習会) at
the school's studios, with a guest teacher and one company-performance viewing
folded in. The source splits enrolment into three **classes** that differ only by
age band and gender (fee/dates/curriculum are shared), so this is **one Offering
for the edition with one `Session` per class** (the model's per-track split lives
in `Session`, which carries the `gender`/`ageRange` an Offering can't):
  - ガールズⅡ — 小学4年生～中学1年生の女子 (grade-4 elementary … grade-1 junior
    high, female).
  - ガールズⅠ — 中学2年生～高校3年生の女子 (grade-2 junior high … grade-3 high
    school, female); pointe required (クラスⅠ受講者はポワント必須).
  - ボーイズ — 小学5年生～高校3年生の男子 (grade-5 elementary … grade-3 high
    school, male).
The slug is year-stamped so the id rolls forward when a new edition is posted.

JAPANESE SOURCE: parsed language-agnostically. The course-date line carries no
year ("8月6日(木)、7日(金)、8日(土)、9日(日)"), so the year is read from the title's
"夏休み特別講習会<YYYY>" stamp and applied to the month/day span; the application
deadline ("◇お申込み締切： 7月20日(月祝)") inherits the same year. Ages are stated as
Japanese **school grades**, not numbers — mapped to ages by the statutory
April-entry schedule (小N年→age 6+N…7+N, 中N年→12+N…13+N, 高N年→15+N…16+N), with
the raw grade band kept verbatim in each session's `notes`. JPY ASCII amounts.
Source free text (title, grade bands, guest-teacher line) is kept faithfully in
Japanese, never translated inline.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-06):
  - One Offering, three `Session`s (per-class split) with distinct ageRange +
    gender (female/female/male); the Offering ageRange spans all classes.
  - Year-from-title date resolution (the date line is year-less); 4-day span.
  - JPY tuition (tax-inclusive, includes the Swan Lake viewing ticket) plus an
    optional private-lesson price.
  - `pointe` genre — ガールズⅠ requires pointe (ポワント必須); classical otherwise.
  - A defined-poses application requirement is NOT claimed: the public page states
    no audition/photo brief (entry is via a Peatix booking link), so requirements
    stay `[]` ("not stated"), the participation conditions kept as a note.
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

BASE = "https://www.thetokyoballetschool.com"
# The current edition's dated post (found from /news/). The path is the CMS's
# auto-slug for the 2026 announcement; it 404s into [] once retired.
PAGE = f"{BASE}/kodomo/-2025-1.html"

ORG = Organization(
    name="The Tokyo Ballet School",
    slug="tokyo-ballet-school",
    country="JP",
    city="Tokyo",
)

# The source title stem (kept faithfully in Japanese; not translated inline). The
# live title is "夏休み特別講習会<year>".
TITLE_STEM = "夏休み特別講習会"
VENUE_JA = "東京バレエ学校 スタジオ"

# Participation conditions, kept verbatim as an application note (no audition or
# photo brief is stated — entry is a Peatix booking).
_APPLY_NOTE = (
    "参加条件：バレエ歴3年以上であること／クラスⅠ受講者はポワント必須／4日間全ての"
    "プログラムに参加できること。各クラス先着20名限定。お申込みはPeatixより。"
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE, follow_redirects=True)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    offering = _build_offering(resp.text)
    return [offering] if offering is not None else []


def _build_offering(html: str) -> Offering | None:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""

    year = _year(text)
    if year is None:
        return None  # no dated edition parseable
    start, end = _date_range(text, year)
    if start is None:
        return None
    season = str(year)

    sessions = _sessions(text)
    return Offering(
        id=f"tokyo-ballet-school/summer-special-{season}",
        source=Source(provider="tokyo-ballet-school", url=PAGE, scrapedAt=now_utc()),
        title=f"{TITLE_STEM}{season}",
        genres=_genres(text),
        ageRange=_offering_age_range(sessions),
        organization=ORG,
        location=Location(venue=VENUE_JA, city="Tokyo", country="JP"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Asia/Tokyo",
            sessions=sessions,
            notes=_schedule_note(text),
        ),
        teachers=_teachers(text),
        prices=_prices(text),
        application=Application(
            deadline=_deadline(text, year),
            url=_apply_url(text),
            notes=_APPLY_NOTE,
        ),
    )


# --- year: read from the title stamp "夏休み特別講習会<YYYY>" ----------------------
#
# The course-date line gives no year, so the title's trailing year anchors the
# whole edition (and the deadline). Falls back to any "<YYYY>年の夏" mention.

_YEAR_TITLE = re.compile(TITLE_STEM + r"(\d{4})")
_YEAR_SEASON = re.compile(r"(\d{4})\s*年の夏")


def _year(text: str) -> int | None:
    m = _YEAR_TITLE.search(text) or _YEAR_SEASON.search(text)
    return int(m.group(1)) if m else None


# --- dates --------------------------------------------------------------------
#
# Course span as a comma-listed run of (year-less) days under one month:
# "8月6日(木)、7日(金)、8日(土)、9日(日)". The year comes from the title; the first
# and last days bound the span. Weekday parentheses are ignored.

_DATE_LINE = re.compile(r"(\d{1,2})月\s*(\d{1,2})日(?:[^月]*?[、,]\s*(\d{1,2})日)*", re.DOTALL)
_DAY = re.compile(r"(\d{1,2})日")


def _date_range(text: str, year: int) -> tuple[date | None, date | None]:
    m = _DATE_LINE.search(text)
    if not m:
        return None, None
    month = int(m.group(1))
    days = [int(d) for d in _DAY.findall(m.group(0))]
    return date(year, month, days[0]), date(year, month, days[-1])


# 「◇舞台鑑賞について 公演名：… 日時：8月8日(土) 15:00開演」 — a company-performance
# viewing folded into the course (its ticket is covered by the fee), anchored on
# the structured 舞台鑑賞 section (not the intro blurb) and kept verbatim as a note.
_VIEWING = re.compile(r"舞台鑑賞について\s*(公演名[：:][^◇※]*?開演)")


def _schedule_note(text: str) -> str | None:
    m = _VIEWING.search(text)
    if not m:
        return None
    return "舞台鑑賞：" + parse.clean(m.group(1))


# --- deadline: "◇お申込み締切： 7月20日(月祝)" — year inherited from the title -----

_DEADLINE = re.compile(r"締切[：:]\s*(\d{1,2})月\s*(\d{1,2})日")


def _deadline(text: str, year: int) -> date | None:
    m = _DEADLINE.search(text)
    return date(year, int(m.group(1)), int(m.group(2))) if m else None


# --- apply url: the Peatix booking link --------------------------------------

_APPLY = re.compile(r"https?://peatix\.com/event/\d+")


def _apply_url(text: str) -> str:
    m = _APPLY.search(text)
    return m.group(0) if m else PAGE


# --- classes → sessions -------------------------------------------------------
#
# Each class is a "【<name>】<grade band>の<gender>" run. Grade bands are mapped to
# ages by the statutory April-entry schedule; the raw band stays in `notes`.


class _Class:
    def __init__(self, key: str, name: str) -> None:
        self.key = key
        self.name = name


_CLASSES = [
    _Class("girls2", "ガールズⅡ"),
    _Class("girls1", "ガールズⅠ"),
    _Class("boys", "ボーイズ"),
]

# "【ガールズⅡ】小学4年生～中学1年生の女子" — the grade band + gender suffix; the band
# runs up to the next 【 or a section marker.
_CLASS_BAND = re.compile(r"【\s*{name}\s*】\s*([^【◇※]*?の(?:女子|男子))")
# School-grade tokens: 小学N年(生) / 中学N年(生) / 高校N年(生).
_GRADE = re.compile(r"(小学|中学|高校)\s*(\d)\s*年")


def _class_band(text: str, cls: _Class) -> str | None:
    m = re.search(_CLASS_BAND.pattern.format(name=re.escape(cls.name)), text)
    return parse.clean(m.group(1)) if m else None


def _band_age_range(band: str) -> dict | None:
    grades = _GRADE.findall(band)
    if not grades:
        return None
    low_level, low_grade = grades[0]
    high_level, high_grade = grades[-1]
    low = parse.japanese_grade_to_age(low_level, int(low_grade))
    # Upper bound is the END of the top grade's year (one year past its start age).
    high = parse.japanese_grade_to_age(high_level, int(high_grade)) + 1
    return {"min": low, "max": high}


def _band_gender(band: str):
    if "女子" in band:
        return "female"
    if "男子" in band:
        return "male"
    return "both"


def _sessions(text: str) -> list[Session]:
    sessions: list[Session] = []
    for cls in _CLASSES:
        band = _class_band(text, cls)
        if band is None:
            continue
        sessions.append(
            Session(
                label=cls.name,
                ageRange=_band_age_range(band),
                gender=_band_gender(band),
                notes=band,
            )
        )
    return sessions


def _offering_age_range(sessions: list[Session]) -> dict | None:
    bounds = [s.age_range for s in sessions if s.age_range]
    if not bounds:
        return None
    return {
        "min": min(b["min"] for b in bounds),
        "max": max(b["max"] for b in bounds),
    }


# --- prices: "51,000円（税込み）" per class (incl. the viewing ticket); the optional
# private lesson is "30分 6,000円（税込み）" -------------------------------------

_TUITION = re.compile(r"([\d,]+)\s*円\s*（税込み?）")
_PRIVATE = re.compile(r"プライベートレッスン[^】]*】\s*(\d+)\s*分\s*([\d,]+)\s*円")


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    seg = text
    cut = text.find("プライベートレッスン")
    if cut >= 0:
        seg = text[:cut]  # keep class tuition amounts out of the private-lesson block
    amounts = {parse.parse_amount(m) for m in _TUITION.findall(seg)}
    amounts.discard(None)
    if amounts:
        amount = max(a for a in amounts if a is not None)
        prices.append(
            Price(
                amount=amount,
                currency="JPY",
                label="受講料（4日間・税込）",
                includes=["tuition"],
                notes="東京バレエ団「はじめてのバレエ 白鳥の湖」鑑賞チケット費用を含む。",
            )
        )
    pm = _PRIVATE.search(text)
    if pm:
        pamount = parse.parse_amount(pm.group(2))
        if pamount is not None:
            prices.append(
                Price(
                    amount=pamount,
                    currency="JPY",
                    label=f"プライベートレッスン（{pm.group(1)}分・希望者のみ・税込）",
                    includes=["tuition"],
                )
            )
    return prices


# --- genres -------------------------------------------------------------------
#
# A classical short course; ガールズⅠ requires pointe (ポワント必須), so pointe is
# part of the program. No contemporary class is listed this edition.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("バレエ", "クラスレッスン")),
    ("pointe", ("ポワント", "ポアント")),
    ("contemporary", ("コンテンポラリー",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- teachers: the named guest teacher (ゲスト教師) ------------------------------
#
# "ゲスト教師：高田茜さん（英国ロイヤル・バレエ団 プリンシパル）" — only the named
# guest is recorded; "東京バレエ学校教師" (the school's own faculty) is an
# unattributable collective, left out rather than over-claimed.

_GUEST = re.compile(r"ゲスト教師[：:]\s*([^（(]+?)\s*[（(]([^）)]*)[）)]")


def _teachers(text: str) -> list[Teacher]:
    m = _GUEST.search(text)
    if not m:
        return []
    name = parse.clean(m.group(1)).rstrip("さん")
    affiliation = parse.clean(m.group(2))
    role = f"ゲスト教師（{affiliation}）" if affiliation else "ゲスト教師"
    return [Teacher(name=name, role=role)]
