"""RAD Japan — International Summer School (Tokyo, JP).

Run by RAD Japan, the Japan office of the **Royal Academy of Dance (RAD)**, the
UK syllabus/examinations body (London HQ). The summer school is hosted in Tokyo
and taught by RAD faculty flown in from London with an interpreter on every
class (外国人教師＋通訳つき) — so it's a foreign (British) brand's intensive run
in Japan; the RAD affiliation is carried on the organization + offering titles.

API FIRST: none. radjapan.org is a static, hand-authored Dreamweaver-template
site (`InstanceBegin template=…`) — the full text is in the markup, no JSON API
and no JS render. The page is served **EUC-JP** (its `<meta charset>` says so,
but the response Content-Type carries no charset), so we must decode the raw
bytes as EUC-JP ourselves — httpx would otherwise mis-decode it as UTF-8. Routed
through the fetch proxy because the host blocks the CI runner's datacenter IP on
a direct fetch (connection reset).

DISCOVERY: one page (`/summerschool.html`) describes the current edition — the
31st International Summer School (第31回, August 2026). It runs several student
courses that differ by age band, dates, fee and curriculum, plus a block of
Teachers' Courses (TC-1…TC-5). We emit **one Offering per student course** (per
the model's one-Offering-per-track rule — folding would lose the age/fee/genre
split):
  - Students' Course A (1 day)   — 幼児 年中〜年長,  ¥6,600  — classical.
  - Students' Course B (3 days)  — 小学1〜2年生,    ¥33,000 — classical + character.
  - Performance Course A (4 days)— 小学3〜5年生,    ¥57,200 — classical + character,
    a theatre demonstration (あうるすぽっと) on the final day.
  - Performance Course B (5 days)— 小学6年生〜20歳,  ¥78,540 — classical + repertoire
    + creative dance, theatre demonstration on the final day.
The **Teachers' Courses are out of scope** — RAD CPD for registered teachers
(対象：RAD登録教師), not student intensives — so they're dropped, not emitted.
The slug is year-stamped (from the title's edition stamp) so ids roll forward.

JAPANESE SOURCE: parsed language-agnostically. The per-course date lines carry no
year ("7月31日(金)〜8月4日(火)"), so the year is read from the headline edition
stamp ("２０２６年８月…第３１回" / full-width digits) and applied to every span and to
the application-open date. Ages are stated as **school grades / preschool years**,
not numbers — mapped to ages by the statutory April-entry schedule (小N年→6+(N-1),
preschool 年中→4 / 年長→5), with the explicit "20歳" upper bound on Course B kept
verbatim; the raw band stays in each schedule note. JPY ASCII amounts (税込 =
tax-incl). Source free text (titles, age bands, venue) is kept in Japanese, never
translated inline.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-06):
  - Four Offerings from one page (per-course split), distinct ageRange + price +
    dates + genres parsed from each course's own block.
  - EUC-JP byte decode (charset from the page's own meta, not the HTTP header).
  - Full-width-digit year resolution from a headline edition stamp ("第３１回").
  - JPY tax-inclusive tuition; character genre on the courses whose curriculum
    adds キャラクターダンス; contemporary (creative dance, クリエイティブダンス) +
    repertoire (レパートリー) on Course B only.
  - `application.opensAt` from the published reception-open date (受付開始); no
    audition/photo brief is stated (all courses are RAD-experience-optional,
    RAD経験不問), so requirements stay `[]` ("not stated").
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

BASE = "https://www.radjapan.org"
PAGE = f"{BASE}/summerschool.html"
# One shared application form for every course on the page.
APPLY_URL = "https://business.form-mailer.jp/fms/976f88fe330802"

ORG = Organization(
    name="Royal Academy of Dance Japan",
    slug="rad-japan-summer-school",
    country="JP",
    city="Tokyo",
)

# Main venue (kept faithfully in Japanese). The performance courses also use the
# あうるすぽっと theatre for the final-day demonstration.
VENUE_JA = "小林紀子バレエ・シアター TRAD目白スタジオ"


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE, follow_redirects=True)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    # Served EUC-JP with no charset in the HTTP header — decode the raw bytes by
    # the encoding the page's own <meta> declares (default euc-jp for this site).
    html = resp.content.decode(_charset(resp.content), errors="replace")
    return _build_offerings(html)


def _charset(raw: bytes) -> str:
    head = raw[:2048].decode("ascii", errors="ignore").lower()
    m = re.search(r"charset=[\"']?([\w-]+)", head)
    return m.group(1) if m else "euc-jp"


# --- per-course offerings -----------------------------------------------------
#
# Each student course is a `div.course_box` keyed by a stable id
# (studentscourse-a…-d). We read the title, age band, date span, fee and venue
# from that block's own lines so per-course facts never leak across.


class _Course:
    def __init__(self, course_id: str, key: str) -> None:
        self.course_id = course_id  # the page's div id
        self.key = key  # our offering-slug stem


_COURSES = [
    _Course("studentscourse-a", "students-course-a"),
    _Course("studentscourse-b", "students-course-b"),
    _Course("studentscourse-c", "performance-course-a"),
    _Course("studentscourse-d", "performance-course-b"),
]


def _build_offerings(html: str) -> list[Offering]:
    tree = HTMLParser(html)
    year = _year(tree)
    if year is None:
        return []  # no dated edition stamp parseable
    season = str(year)
    opens_at = _opens_at(tree, year)

    offerings: list[Offering] = []
    for course in _COURSES:
        box = tree.css_first(f"#{course.course_id}")
        if box is None:
            continue
        offering = _build_offering(course, box, season, year, opens_at)
        if offering is not None:
            offerings.append(offering)
    return offerings


def _build_offering(
    course: _Course,
    box,
    season: str,
    year: int,
    opens_at: date | None,
) -> Offering | None:
    block = parse.clean(box.text(separator=" "))
    start, end = _date_range(block, year)
    title = _title(box, season)
    return Offering(
        id=f"rad-japan-summer-school/{course.key}-{season}",
        source=Source(provider="rad-japan-summer-school", url=PAGE, scrapedAt=now_utc()),
        title=title,
        genres=_genres(block),
        ageRange=_age_range(block),
        organization=ORG,
        location=Location(venue=_venue(block), city="Tokyo", country="JP"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Asia/Tokyo",
            notes=_schedule_note(block),
        ),
        prices=_prices(block),
        application=Application(
            opensAt=opens_at,
            url=APPLY_URL,
        ),
    )


# --- title --------------------------------------------------------------------
#
# The heading's first letter sits in its own span, so the box text reads
# "P erformance Course B for 5 days" / "S tudents' Course A for 1day". We rebuild
# the English label (re-gluing the lead letter, normalising "1day" → "1 day") and
# stamp the RAD edition + season onto it.

_TITLE_EN = re.compile(
    r"([SP])\s*(tudents'|erformance)\s*Course\s*([AB])\s*for\s*(\d+)\s*days?",
    re.I,
)


def _title(box, season: str) -> str:
    text = parse.clean(box.text(separator=" "))
    m = _TITLE_EN.search(text)
    if m:
        label = f"{m.group(1)}{m.group(2)} Course {m.group(3).upper()}"
        days = int(m.group(4))
        unit = "day" if days == 1 else "days"
        return f"RAD International Summer School {season} — {label} ({days} {unit})"
    return f"RAD International Summer School {season}"


# --- year: full-width-digit headline stamp "２０２６年８月…第３１回" ------------------
#
# Per-course date lines are year-less, so the headline edition stamp anchors the
# whole page. Digits there are full-width (２０２６); normalise then read the year.


def _year(tree: HTMLParser) -> int | None:
    text = (tree.body.text(separator=" ") if tree.body else "").translate(
        parse.FULLWIDTH_DIGITS_TRANS
    )
    # "2026年8月、第31回インターナショナル・サマースクール" — year directly precedes 年.
    m = re.search(r"(20\d\d)\s*年\s*\d{1,2}\s*月[^。]*?サマースクール", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(20\d\d)\s*年[^。]*?第\s*\d+\s*回[^。]*?サマースクール", text)
    return int(m.group(1)) if m else None


# --- dates: year-less span "7月31日(金)〜8月4日(火)" ------------------------------
#
# Start/end day-months share the title's year; the wave dash 〜 (also ~, -, –)
# separates them, and the closing month may be omitted when it equals the start.

_RANGE = re.compile(
    r"(\d{1,2})月\s*(\d{1,2})日[^〜~\-–]*?[〜~\-–]\s*(?:(\d{1,2})月\s*)?(\d{1,2})日",
)
_SINGLE = re.compile(r"(\d{1,2})月\s*(\d{1,2})日")


def _date_range(block: str, year: int) -> tuple[date | None, date | None]:
    m = _RANGE.search(block)
    if m:
        smonth = int(m.group(1))
        emonth = int(m.group(3)) if m.group(3) else smonth
        return date(year, smonth, int(m.group(2))), date(year, emonth, int(m.group(4)))
    s = _SINGLE.search(block)  # a 1-day course states a single date
    if s:
        d = date(year, int(s.group(1)), int(s.group(2)))
        return d, d
    return None, None


def _schedule_note(block: str) -> str | None:
    # Keep this course's own 日程 line verbatim (it carries weekday + demo notes).
    m = re.search(r"日程\s*[：:]\s*([^：:]*?)(?:\s*会場|\s*受講料|$)", block)
    return parse.clean(m.group(1)) if m else None


# --- ages: school grades / preschool years ------------------------------------
#
# 対象 lines: "幼児 年中〜年長", "小学1〜2年生", "小学3〜5年生", "小学6年生〜20歳". The
# elementary band names the level once with a low〜high digit pair ("小学3〜5年生"),
# so the prefix sits only on the low grade. Mapped to ages by the April-entry
# schedule (mirrors tokyo_ballet_school): elementary 小N → 6+(N-1); the upper bound
# is the END of the top grade's year. An explicit numeric "N歳" upper bound
# (Course B's 20歳) is taken as-is; preschool 年中→4 / 年長→5.

# "小学3〜5年" / "小学6年" — low grade with optional high grade after the wave dash.
_GRADE_BAND = re.compile(r"小学\s*(\d)(?:\s*[〜~–\-]\s*(\d))?\s*年")
_AGE_NUM = re.compile(r"(\d{1,2})\s*歳")
_PRESCHOOL = {"年少": 3, "年中": 4, "年長": 5}


def _age_range(block: str) -> dict | None:
    m = _GRADE_BAND.search(block)
    if m:
        low_grade = int(m.group(1))
        high_grade = int(m.group(2)) if m.group(2) else low_grade
        low = parse.japanese_grade_to_age("小学", low_grade)
        num = _AGE_NUM.search(block)  # explicit upper age (e.g. "20歳") wins
        if num:
            return {"min": low, "max": int(num.group(1))}
        high = parse.japanese_grade_to_age("小学", high_grade) + 1  # end of the top grade's year
        return {"min": low, "max": high}
    presch = [v for k, v in _PRESCHOOL.items() if k in block]
    if presch:
        return {"min": min(presch), "max": max(presch) + 1}
    return None


# --- venue --------------------------------------------------------------------
#
# 会場 line names the studio (and あうるすぽっと theatre for performance courses).


def _venue(block: str) -> str:
    m = re.search(r"会場\s*[：:]\s*([^：:]*?)(?:\s*受講料|\s*定員|$)", block)
    return parse.clean(m.group(1)) if m else VENUE_JA


# --- prices: "78,540円（税込）" — JPY, tax-inclusive ----------------------------

_PRICE = re.compile(r"受講料\s*[：:]\s*([\d,]+)\s*円\s*(（税込）)?")


def _prices(block: str) -> list[Price]:
    m = _PRICE.search(block)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    label = "受講料（税込）" if m.group(2) else "受講料"
    return [Price(amount=amount, currency="JPY", label=label, includes=["tuition"])]


# --- genres: matched against THIS course's own curriculum block ----------------
#
# Curriculum keywords from each course's description: クラシックバレエ (classical),
# キャラクターダンス (character), レパートリー (repertoire), クリエイティブダンス
# (creative dance → contemporary).

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("クラシックバレエ", "クラシック", "バレエ")),
    ("character", ("キャラクターダンス", "キャラクター")),
    ("repertoire", ("レパートリー", "振付")),
    ("contemporary", ("クリエイティブダンス", "クリエイティブ")),
]


def _genres(block: str) -> list[Genre]:
    return parse.match_genres(block, _GENRE_KEYWORDS, default=["classical"])


# --- application opens-at: "2026年3月13日(金)12:00より受付開始" --------------------
#
# A published reception-open date (受付開始), not a deadline. Half-width digits
# here; the year is present but we still cross-check against the edition year.

_OPENS = re.compile(r"(20\d\d)\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日[^。]*?受付開始")


def _opens_at(tree: HTMLParser, year: int) -> date | None:
    text = (tree.body.text(separator=" ") if tree.body else "").translate(
        parse.FULLWIDTH_DIGITS_TRANS
    )
    m = _OPENS.search(text)
    if not m:
        return None
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
