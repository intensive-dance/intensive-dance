"""NBA Ballet Company (一般財団法人NBAバレエ団), Tokyo (JP) — its 短期集中サマースクール.

The short-term intensive summer school ("短期集中サマースクール" / "NBA Ballet
Competition Summer School") run by NBA Ballet Company (Tokorozawa, Saitama) under
its competition arm (NBAバレエコンクール主催). The dated edition is held at a Tokyo
venue (芸能花伝舎, Nishi-Shinjuku).

API FIRST: none usable. nbaballet.org runs on WordPress but the host (XServer)
403s `/wp-json/`, and the edition's structured detail (dates, venue, fee,
per-day curriculum) does not live in scrapeable HTML on the company site — the
news announcement (`/news/news-9616/`) only carries the title, the target ages,
the "4日間" duration and links out to (a) an **image-only PDF** schedule and (b)
a **Peatix** event page. So two text-bearing sources are combined:
  - the company **news post** — the canonical announcement; gives the edition
    **year** (from its "YYYY.MM.DD" publish stamp), the target-age band, the
    curriculum keywords and the Peatix link. A plain fetch works.
  - the **Peatix event page** — the machine-readable edition detail (開催日時 /
    会場+住所 / 対象 / 受講料 / per-day カリキュラム). Its body is JS-rendered and
    Peatix 502s the datacenter IP on a direct fetch, so it's pulled through the
    fetch proxy with `render=1` (Markdown via Readability) — documented because
    that's the one proxy-dependent hop.
The faculty are only on the image PDF (no text layer), so the five named teachers
for this edition are carried as verified constants (names + NBA/affiliation roles
read off the PDF), not parsed — see `_TEACHERS`.

DISCOVERY: one short-term student intensive — a 4-day comprehensive summer school
(クラスレッスン + レパートリー/ヴァリエーション + キャラクターダンス + コンテンポラリー
ダンス + ピラティス, closing with a 発表会 and a 修了式/ディプロマ授与). It is one
cohort (小学5年生〜高校生, both genders); the only per-day split is which
レパートリー is taught (女性向け on day 1, 男性向け on day 2), which is not a
distinct enrolment track — so this is **one Offering, no per-class Session split**
(unlike tokyo_ballet_school, where classes differ by age/gender). The slug is
year-stamped so the id rolls forward when a new edition is posted.

JAPANESE SOURCE: parsed language-agnostically. The Peatix course-date line carries
no year ("7/31（木） ～ 8/3（日）"), so the year is read from the news post's publish
stamp ("2025.05.07") and applied to the month/day span. Ages are stated as
**school grades** ("小学5年生〜高校生"), mapped to ages by the statutory April-entry
schedule (小5 → 10, 高校 upper = end of 高3 → 18); the raw band is kept verbatim in
the schedule note. JPY ASCII amount, tax-inclusive (税込). Free text (title, age
band, faculty) is kept faithfully in Japanese, never translated inline.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-09):
  - Two text-bearing sources combined (year from the news post, edition detail
    from the Peatix render); year-from-publish-stamp date resolution.
  - School-grade age band (小5 → 高校) mapped to a numeric ageRange, raw band in
    the schedule note.
  - JPY tax-inclusive tuition (the single 80,000円 all-four-days fee).
  - classical + repertoire + character + contemporary genres parsed from the
    per-day curriculum (ピラティス is conditioning, not a ballet genre — not
    claimed); five named faculty with NBA / external affiliations.
  - First-come enrolment (先着順) kept as an application note; no audition/photo
    brief is stated, so requirements stay `[]` ("not stated"). Kept after the
    cycle has ended (IDR-24): a past edition stays in the store.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.fetch import PROXY_PARAMS_HEADER
from intensive_dance.models import (
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://nbaballet.org"
# The current edition's announcement (found from /news/). 404s once retired.
NEWS_URL = f"{BASE}/news/news-9616/"
# The edition's Peatix event page — the machine-readable detail block. JS-rendered
# and IP-blocked on a direct fetch, so it's pulled through the proxy's render tier.
PEATIX_URL = "https://peatix.com/event/4409752/view"
_PEATIX_PARAMS = "render=1&wait=8000&format=md"

ORG = Organization(
    name="NBA Ballet Company",
    slug="nba-ballet-company",
    country="JP",
    city="Tokorozawa",  # the company's home (Saitama); the school is held in Tokyo
)

TITLE_JA = "短期集中サマースクール"
VENUE_JA = "芸能花伝舎 C1スタジオ"

# First-come enrolment, kept verbatim as an application note (no audition/photo
# brief is stated — entry is a Peatix booking).
_APPLY_NOTE = "先着順。お申込みはPeatixより。"

# Faculty are only on the image-only schedule PDF (no text layer), so the named
# teachers for this edition are carried as verified constants (read off the PDF,
# 2026-06-09), each with the role/affiliation the PDF states.
_TEACHERS = [
    Teacher(name="久保 紘一", role="講師（NBAバレエ団 芸術監督）"),
    Teacher(name="峰岸 千晶", role="講師（NBAバレエ団 バレエミストレス）"),
    Teacher(name="山田 佳歩", role="講師（NBAバレエ団 プリンシパル）"),
    Teacher(name="砂原 伽音", role="講師（舞踊家）"),
    Teacher(name="三崎 彩", role="講師（演者・指導者・振付家）"),
]


def scrape(client: httpx.Client) -> list[Offering]:
    news = client.get(NEWS_URL)
    if news.status_code == 404:
        return []
    news.raise_for_status()
    peatix = client.get(PEATIX_URL, headers={PROXY_PARAMS_HEADER: _PEATIX_PARAMS})
    peatix_text = peatix.text if peatix.status_code == 200 else ""
    offering = _build_offering(news.text, peatix_text)
    return [offering] if offering is not None else []


def _build_offering(news_html: str, peatix_md: str) -> Offering | None:
    tree = HTMLParser(news_html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    news_text = parse.clean(tree.body.text(separator=" ")) if tree.body else ""
    detail = parse.clean(peatix_md)

    year = _year(news_text)
    if year is None:
        return None  # no dated edition resolvable
    start, end = _date_range(detail, year)
    if start is None:
        return None
    season = str(year)

    age_band, age_range = _ages(detail or news_text)
    return Offering(
        id=f"nba-ballet-company/summer-school-{season}",
        source=Source(provider="nba-ballet-company", url=NEWS_URL, scrapedAt=now_utc()),
        title=f"NBA{TITLE_JA}{season}",
        genres=_genres(detail or news_text),
        ageRange=age_range,
        organization=ORG,
        location=_location(detail),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Asia/Tokyo",
            notes=_schedule_note(age_band),
        ),
        teachers=list(_TEACHERS),
        prices=_prices(detail),
        application=Application(url=PEATIX_URL, notes=_APPLY_NOTE),
    )


# --- year: read from the news post's publish stamp "2025.05.07" ----------------
#
# The Peatix course-date line is year-less, so the announcement's own publish
# date anchors the edition (and the day/month span).

_YEAR_STAMP = re.compile(r"(20\d\d)\.\d{1,2}\.\d{1,2}")


def _year(news_text: str) -> int | None:
    m = _YEAR_STAMP.search(news_text)
    return int(m.group(1)) if m else None


# --- dates: year-less span "7/31（木） ～ 8/3（日）" ------------------------------
#
# Slash-month/day with a wave-dash separator (〜/～/~/-). The closing month is
# stated separately ("8/3"); the year comes from the news post.

_RANGE = re.compile(
    r"(\d{1,2})/(\d{1,2})\s*[（(][^)）]*[)）]?\s*[〜～~\-–]\s*(\d{1,2})/(\d{1,2})",
)


def _date_range(detail: str, year: int) -> tuple[date | None, date | None]:
    m = _RANGE.search(detail)
    if not m:
        return None, None
    m1, d1, m2, d2 = (int(g) for g in m.groups())
    return date(year, m1, d1), date(year, m2, d2)


# --- venue / city: "芸能花伝舎 C1スタジオ 〒160-0023 東京都新宿区西新宿6-12-30" -------
#
# The 会場 line names the studio; the address's prefecture+ward token gives the
# city (東京都新宿区 → Tokyo). The school is held in Tokyo even though the company
# is based in Tokorozawa (Saitama).

_CITY = re.compile(r"〒[\d－\-]+\s*([^ ]+?[都道府県])([^ \d]+?[市区町村])")


def _location(detail: str) -> Location:
    venue = VENUE_JA if VENUE_JA[:4] in detail else None
    m = _CITY.search(detail)
    city = "Tokyo" if m and m.group(1) == "東京都" else None
    return Location(venue=venue, city=city, country="JP")


# --- ages: school grades "小学5年生〜高校生" ------------------------------------
#
# Lower bound is the start age of 小学5 (= 10) by the April-entry schedule; the
# upper bound is the END of high school (高3 → 18), since "高校生" is an open
# "through high school" band rather than a specific grade. The raw band is kept
# verbatim in the schedule note.

_BAND = re.compile(r"小学\s*(\d)\s*年生?\s*[〜～~\-–]\s*(高校生?|中学\s*\d\s*年生?)")
_HIGH_SCHOOL_END_AGE = 18  # end of 高校3年 by the April-entry schedule


def _ages(text: str) -> tuple[str | None, dict | None]:
    m = _BAND.search(text)
    if not m:
        return None, None
    low = parse.japanese_grade_to_age("小学", int(m.group(1)))
    high_token = m.group(2)
    if "高校" in high_token:
        high = _HIGH_SCHOOL_END_AGE
    else:  # explicit 中学N年 upper bound
        gm = re.search(r"中学\s*(\d)", high_token)
        high = parse.japanese_grade_to_age("中学", int(gm.group(1))) + 1 if gm else None
    band = parse.clean(m.group(0))
    return band, {"min": low, "max": high}


def _schedule_note(age_band: str | None) -> str | None:
    return f"対象：{age_band}" if age_band else None


# --- prices: "80,000円（全4日間 税込)" — JPY, tax-inclusive ----------------------

_FEE = re.compile(r"([\d,]+)\s*円\s*[（(]([^）)]*)[)）]")


def _prices(detail: str) -> list[Price]:
    m = _FEE.search(detail)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    return [
        Price(
            amount=amount,
            currency="JPY",
            label=f"受講料（{parse.clean(m.group(2))}）",
            includes=["tuition"],
        )
    ]


# --- genres: matched against the per-day curriculum ----------------------------
#
# クラスレッスン (classical), レパートリー/ヴァリエーション (repertoire),
# キャラクターダンス (character), コンテンポラリーダンス (contemporary). ピラティス is
# body conditioning, not a ballet genre, so it isn't claimed.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("クラスレッスン", "クラシック", "バレエ")),
    ("repertoire", ("レパートリー", "ヴァリエーション", "バリエーション")),
    ("character", ("キャラクターダンス", "キャラクター")),
    ("contemporary", ("コンテンポラリーダンス", "コンテンポラリー")),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])
