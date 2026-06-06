"""Japan Ballet Association — Summer Course (公益社団法人日本バレエ協会 サマー・コース), JP.

The national peak body for ballet in Japan (公益社団法人日本バレエ協会) runs an
annual residential summer course at Shiga Kogen (Nagano).

API FIRST: WordPress, but unusable via REST. `GET /wp-json/wp/v2/posts/<id>` 200s
for the announcement post, yet its `content.rendered` is **empty** — the body is
built by a page-builder that renders nothing into REST (the ABT trap). The full
text is, however, present in the static server-rendered HTML of the announcement
page, so we parse that one page directly. The host is **HTTP-only** (HTTPS is
refused), so the fetch URL is `http://…`; a plain httpx fetch suffices (no proxy,
no JS render).

DISCOVERY: the page announces one dated short-term student intensive — the
2026年度 サマー・コース (2026 Summer Course), a 4-night/5-day residential course
(4泊5日) taught by a named guest faculty. It is a single course with one fee and
one set of dates (no per-track/per-class split), so we emit **one Offering**,
season-keyed from the parsed dates so the id rolls forward when a new edition is
posted.

JAPANESE SOURCE: parsed language-agnostically — the course span carries a full
year ("2026年8月5日(水)～8月9日(日)"), so the year is read straight from it; the
application window is stamped in the **Reiwa era** ("令和8年4月17日…～7月17日"), so
the era year is converted to the Gregorian year (令和N → 2018+N) before building
the open/deadline dates. JPY amounts are ASCII ("84,000円"). Source free text
(title, faculty names, raw date/fee notes) is kept faithfully in Japanese and is
never translated inline.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-06):
  - A single Offering with a 4泊5日 (4-night/5-day) residential span.
  - JPY prices (tax-inclusive): tuition (受講料) plus accommodation (宿泊料) that
    bundles 1日3食 (three meals a day) — two `Price`s, the second tagged
    accommodation + meals.
  - Multiple genres matched against the stated lesson list (基礎/バー＆センター →
    classical; ポアント → pointe; ヒストリカルダンス/キャラクター → character;
    コンテンポラリー → contemporary).
  - Named guest faculty with their per-subject role (担当), kept in Japanese.
  - Application window stamped in the Reiwa era → opensAt + deadline; the apply
    URL is the linked Google Form. Requirements are `[]` ("not stated") — the
    public page describes no audition/photo brief (entry is by form + bank
    transfer), with the participation terms kept as an application note.
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
    Teacher,
    now_utc,
)

BASE = "http://www.j-b-a.or.jp"  # HTTP only — the host refuses HTTPS.
PAGE = f"{BASE}/classes/2026summercours/"

ORG = Organization(
    name="Japan Ballet Association",
    slug="japan-ballet-association",
    country="JP",
    city="Tokyo",  # the association's seat; the course itself is held in Nagano.
)

# The source title stem (kept faithfully in Japanese; not translated inline). The
# live title is "<YYYY>年度 サマー・コース".
TITLE_STEM = "サマー・コース"
VENUE_JA = "長野県志賀高原 ホテル一乃瀬"

# Participation terms, kept verbatim as an application note (the public page states
# no audition/photo brief — entry is a Google Form plus a bank transfer, and a
# place is confirmed only once payment clears).
_APPLY_NOTE = (
    "お申込みはリンク先または参加要項記載のQRコードより。所定の参加費用を指定口座へ"
    "振込み、入金確認をもって申込み確定。定員に達し次第、受付期間中でも受付終了。"
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

    start, end = _date_range(text)
    if start is None or end is None:
        return None  # no dated edition parseable
    season = str(start.year)
    opens_at, deadline = _apply_window(text)

    return Offering(
        id=f"japan-ballet-association/summer-course-{season}",
        source=Source(provider="japan-ballet-association", url=PAGE, scrapedAt=now_utc()),
        title=f"{season}年度 {TITLE_STEM}",
        genres=_genres(text),
        ageRange=None,  # not stated on the public page.
        organization=ORG,
        location=Location(venue=VENUE_JA, city="山ノ内町", country="JP"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Asia/Tokyo",
            notes=_schedule_note(text),
        ),
        teachers=_teachers(text),
        prices=_prices(text),
        application=Application(
            opensAt=opens_at,
            deadline=deadline,
            url=_apply_url(tree),
            notes=_APPLY_NOTE,
        ),
    )


# --- dates --------------------------------------------------------------------
#
# Course span carries a full year on the opening bound, the closing bound bares
# its month+day: "2026年8月5日(水)～8月9日(日)". Japanese full-width "～" or ASCII
# "~/-" separates the two bounds; the weekday parentheses are ignored.

_RANGE = re.compile(
    r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日[^～~\-–]*?[～~\-–]\s*"
    r"(?:(\d{1,2})月\s*)?(\d{1,2})日",
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    year = int(m.group(1))
    start_month = int(m.group(2))
    end_month = int(m.group(4)) if m.group(4) else start_month
    return date(year, start_month, int(m.group(3))), date(year, end_month, int(m.group(5)))


# "＜4泊5日＞" — the nights/days span, kept verbatim as a schedule note.
_NIGHTS = re.compile(r"(\d+\s*泊\s*\d+\s*日)")


def _schedule_note(text: str) -> str | None:
    m = _NIGHTS.search(text)
    return parse.clean(m.group(1)) if m else None


# --- application window: stamped in the Reiwa era ----------------------------
#
# "＜お申込み受付期間＞ 令和8年4月17日12：00～7月17日" — the opening date carries the
# Reiwa year (令和N → 2018+N) and a full month/day; the closing bound bares its
# month/day and inherits the (converted) year. The closing date is the deadline.

_REIWA_BASE = 2018  # 令和1 == 2019.
_WINDOW = re.compile(
    r"受付期間[＞>]?\s*令和\s*(\d{1,2})\s*年\s*(\d{1,2})月\s*(\d{1,2})日"
    r"[^～~\-–]*?[～~\-–]\s*(?:(\d{1,2})月\s*)?(\d{1,2})日",
)


def _apply_window(text: str) -> tuple[date | None, date | None]:
    m = _WINDOW.search(text)
    if not m:
        return None, None
    year = _REIWA_BASE + int(m.group(1))
    open_month = int(m.group(2))
    close_month = int(m.group(4)) if m.group(4) else open_month
    opens_at = date(year, open_month, int(m.group(3)))
    deadline = date(year, close_month, int(m.group(5)))
    return opens_at, deadline


# --- apply url: the linked Google Form ----------------------------------------


def _apply_url(tree: HTMLParser) -> str:
    for a in tree.css("a"):
        href = a.attributes.get("href") or ""
        if "forms.gle" in href or "docs.google.com/forms" in href:
            return href
    return PAGE


# --- prices: "受講料:44,000円(税込)＋宿泊料:40,000円(税込)" -------------------------
#
# Tuition (受講料) and accommodation (宿泊料) are listed separately, both
# tax-inclusive (税込); the accommodation line bundles 1日3食 (three meals a day),
# so it carries meals as well as accommodation in `includes`.

_TUITION = re.compile(r"受講料\s*[:：]\s*([\d,]+)\s*円\s*(（税込）|\(税込\))?")
_LODGING = re.compile(r"宿泊料\s*[:：]\s*([\d,]+)\s*円\s*(（税込）|\(税込\))?")


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    tm = _TUITION.search(text)
    if tm:
        amount = parse.parse_amount(tm.group(1))
        if amount is not None:
            label = "受講料（税込）" if tm.group(2) else "受講料"
            prices.append(Price(amount=amount, currency="JPY", label=label, includes=["tuition"]))
    lm = _LODGING.search(text)
    if lm:
        amount = parse.parse_amount(lm.group(1))
        if amount is not None:
            label = "宿泊料（税込）" if lm.group(2) else "宿泊料"
            meals = "1日3食" in text or "３食" in text
            includes: list = ["accommodation", "meals"] if meals else ["accommodation"]
            notes = "宿泊費には1日3食の食事代が含まれます。" if meals else None
            prices.append(
                Price(amount=amount, currency="JPY", label=label, includes=includes, notes=notes)
            )
    return prices


# --- genres: matched against the stated lesson list (－レッスン内容－) --------------
#
# "基礎レッスン／バー＆センター・レッスン ポアント・レッスン ヒストリカルダンス
# キャラクター･ダンス コンテンポラリー・ダンスの基礎" — keyword-match the syllabus,
# not loose prose, so a genre is only claimed when a class teaches it.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("基礎レッスン", "バー", "センター", "クラシック")),
    ("pointe", ("ポアント", "ポワント")),
    ("character", ("キャラクター", "ヒストリカル")),
    ("contemporary", ("コンテンポラリー",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- teachers: the named guest faculty (〈講師〉), each with a per-subject 担当 ------
#
# "〈講師〉 フィオーナ・トンキン（クラシック・バレエ担当） マイレン・トレウバエフ（…
# 担当） 滝井 真樹子（…担当）" — name + a parenthesised subject role. Only the named
# 講師 are recorded; the 〈スタッフ〉 block (chief/instructors/pianist) is operational
# staff, left out. The faculty block runs from 〈講師〉 to the next 〈section〉.

_FACULTY_BLOCK = re.compile(r"〈\s*講師\s*〉(.*?)〈", re.DOTALL)
_FACULTY = re.compile(r"([^（()〈〉、,／/]+?)\s*[（(]\s*([^）)]*?)\s*[）)]")


def _teachers(text: str) -> list[Teacher]:
    bm = _FACULTY_BLOCK.search(text)
    if not bm:
        return []
    teachers: list[Teacher] = []
    seen: set[str] = set()
    for m in _FACULTY.finditer(bm.group(1)):
        name = parse.clean(m.group(1))
        role = parse.clean(m.group(2))
        if not name or name in seen:
            continue
        seen.add(name)
        teachers.append(Teacher(name=name, role=role or None))
    return teachers
