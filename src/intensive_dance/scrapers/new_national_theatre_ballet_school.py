"""New National Theatre Ballet School (新国立劇場バレエ研修所), Tokyo (JP).

API FIRST: none. The New National Theatre (NNT) site serves its training news
on plain server-rendered HTML pages under `/ballet/training/news/` — the full
text is in the static markup, no JSON API and no JS render needed. The current
edition lives at a dated `detail/<id>.html` news page found from the listing.

DISCOVERY: the page announces one short-term student intensive — the "夏の特別
バレエレッスン / Summer Special Ballet Lessons", a 3-day course taught by the
school's faculty (研修所講師) at the NNT rehearsal studios that feeds the NNT
Ballet company. The source splits it into two tracks with distinct ages, fees
and curriculum, so we emit **one Offering per track** (per the model's
one-Offering-per-track rule — folding would lose the age/fee/genre split):
  - A class 〈13–14〉 — fundamentals, class lessons only, ¥28,000.
  - B class 〈15–18〉 — class lessons + a contemporary dance class, ¥39,000.
The slug is year-stamped so the id rolls forward when a new edition is posted.

JAPANESE SOURCE: parsed language-agnostically — numeric `YYYY年M月D日` dates
(also handling the Japanese era stamp "(2027〈R9〉年4月1日時点)" that anchors the
ages), full-width-hyphen age bands (13－14 / 15－18), and ASCII ¥ amounts. Source
free text (title, faculty names, raw date/fee notes) is kept faithfully in
Japanese, never translated inline.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-06):
  - Two Offerings from one page (per-track split), distinct ageRange + prices.
  - JPY prices (tuition, tax-inclusive), full-width-digit "3-day" note.
  - A defined-poses PhotosReq: applicants submit a "ポーズ写真貼付用紙" (pose-photo
    attachment form) with photos taken in a specified manner — the pose names
    live in a PDF form we can't reliably extract, so we record the requirement
    type faithfully without inventing the pose list.
  - Contemporary genre on the B track only (its curriculum adds コンテンポラリー
    ダンス); the A track stays classical, matched against the per-track block.
  - Application window stamped as a deadline (必着 = must-arrive-by date).
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
    PhotosReq,
    Price,
    Requirement,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.nntt.jac.go.jp"
# The current edition's dated news-detail page (found from /ballet/training/news/).
PAGE = f"{BASE}/ballet/training/news/detail/27_031194.html"
APPLY_URL = "https://nntt.form.kintoneapp.com/public/summerschool2026"

ORG = Organization(
    name="New National Theatre Ballet School",
    slug="new-national-theatre-ballet-school",
    country="JP",
    city="Tokyo",
)

# The source title (kept faithfully in Japanese; not translated inline).
TITLE_JA = "夏の特別バレエレッスン"
VENUE_JA = "新国立劇場リハーサル室"


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

    start, end = _date_range(text)
    anchor = start or end
    if anchor is None:
        return []  # no dated edition parseable
    season = str(anchor.year)
    deadline = _deadline(text)
    # The pose-photo requirement is stated once for the whole page (not per track).
    requirements = _page_requirements(text)

    offerings: list[Offering] = []
    for track in _TRACKS:
        block = _track_block(text, track)
        if block is None:
            continue
        offerings.append(_build_offering(track, block, season, start, end, deadline, requirements))
    return offerings


def _build_offering(
    track: _Track,
    block: str,
    season: str,
    start: date | None,
    end: date | None,
    deadline: date | None,
    requirements: list[Requirement],
) -> Offering:
    return Offering(
        id=f"new-national-theatre-ballet-school/summer-special-{track.key}-{season}",
        source=Source(provider="new-national-theatre-ballet-school", url=PAGE, scrapedAt=now_utc()),
        title=f"{TITLE_JA} {track.label} {season}",
        genres=_genres(block),
        ageRange=_age_range(block),
        organization=ORG,
        location=Location(venue=VENUE_JA, city="Tokyo", country="JP"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Asia/Tokyo",
            notes=_dates_note(block),
        ),
        teachers=_teachers(block),
        prices=_prices(block),
        application=Application(
            deadline=deadline,
            url=APPLY_URL,
            requirements=list(requirements),
        ),
    )


# --- track split --------------------------------------------------------------
#
# The page lists the two tracks under the section headings "Aクラス 〈13－14歳〉" and
# "Bクラス 〈15－18歳〉", then a "説明会概要" (info-session) section. We anchor each
# track on its `〈age〉` heading (so the timetable label "（Bクラス）" doesn't get
# mistaken for the section start) and slice from one heading to the next, so
# per-track ages/fees/genres/faculty never leak across.

# Section heading anchored on the age band, e.g. "Aクラス 〈13－14歳〉" — the angle
# bracket may sit either side of a space and the band uses a 全角/半角 hyphen.
_HEADING = re.compile(r"([AB])クラス\s*〈\s*\d{1,2}\s*[－–\-]\s*\d{1,2}\s*歳")
# Where a track section ends (the next track heading is handled separately).
_SECTION_END = "説明会概要"


class _Track:
    def __init__(self, key: str, label: str, letter: str) -> None:
        self.key = key
        self.label = label
        self.letter = letter


_TRACKS = [
    _Track("a", "Aクラス", "A"),
    _Track("b", "Bクラス", "B"),
]


def _track_block(text: str, track: _Track) -> str | None:
    bounds = [m.start() for m in _HEADING.finditer(text)]
    letters = [m.group(1) for m in _HEADING.finditer(text)]
    if track.letter not in letters:
        return None
    i = letters.index(track.letter)
    start = bounds[i]
    end = bounds[i + 1] if i + 1 < len(bounds) else len(text)
    section_end = text.find(_SECTION_END, start)
    if 0 <= section_end < end:
        end = section_end
    return text[start:end]


# --- dates --------------------------------------------------------------------
#
# Course span: "2026年8月20日（木）～22日（土）" — a shared year/month, the closing
# day given bare. Japanese full-width "～" or ASCII "~/-" separates the two days.

_RANGE = re.compile(
    r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日[^～~\-–]*?[～~\-–]\s*(\d{1,2})日",
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    year, month, d1, d2 = (int(g) for g in m.groups())
    return date(year, month, d1), date(year, month, d2)


def _dates_note(block: str) -> str | None:
    # Keep per-day schedule lines from ALL 【日程詳細…】 blocks in this track.
    # The A class splits into A1 (morning) and A2 (afternoon) sub-tracks, each
    # with its own block; a single-match regex silently drops A2. We concatenate
    # all blocks so both time-slots are preserved.
    parts = [m.group(1) for m in re.finditer(r"【日程詳細[^】]*】\s*([^【]+)", block)]
    combined = " ".join(parse.clean(p) for p in parts if p.strip())
    return combined if combined else None


# 申込開始期間】2026年5月25日（月）～6月19日（金）必着 — the closing 必着 date is the
# must-arrive-by deadline (year/month from the window's opening date).
_DEADLINE = re.compile(
    r"申込開始期間】\s*(\d{4})年\s*(\d{1,2})月\s*\d{1,2}日[^～~\-–]*?"
    r"[～~\-–]\s*(?:(\d{1,2})月\s*)?(\d{1,2})日[^必]*?必着",
)


def _deadline(text: str) -> date | None:
    m = _DEADLINE.search(text)
    if not m:
        return None
    year = int(m.group(1))
    open_month = int(m.group(2))
    close_month = int(m.group(3)) if m.group(3) else open_month
    return date(year, close_month, int(m.group(4)))


# --- ages: full-width-hyphen band "〈13－14歳〉" / "〈15－18歳〉" ------------------

_AGE = re.compile(r"(\d{1,2})\s*[－–\-]\s*(\d{1,2})\s*歳")


def _age_range(block: str) -> dict | None:
    return parse.extract_age_range(block, _AGE)


# --- prices: "28,000円（税込）" — JPY, tax-inclusive (税込) ----------------------

_PRICE = re.compile(r"受講料】\s*([\d,]+)\s*円(（税込）)?")


def _prices(block: str) -> list[Price]:
    m = _PRICE.search(block)
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None:
        return []
    label = "受講料（3日間・税込）" if m.group(2) else "受講料（3日間）"
    return [Price(amount=amount, currency="JPY", label=label, includes=["tuition"])]


# --- genres: matched against THIS track's curriculum block --------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("クラスレッスン", "バレエ")),
    ("contemporary", ("コンテンポラリー",)),
]


def _genres(block: str) -> list[Genre]:
    return parse.match_genres(block, _GENRE_KEYWORDS, default=["classical"])


# --- teachers: the per-track 予定講師 roster (provisional) ----------------------
#
# "【予定講師】*1 クラスレッスン：小嶋直也、…" — names are 全角-comma separated. A
# track can list more than one roster (the A track splits A1/A2), so we merge the
# unique names across every 予定講師 block. The *1 footnote says they may change
# without notice, so the role records that.

_FACULTY = re.compile(r"予定講師】\s*\*?1?\s*([^【]+)")
# Trailing prose after the last name (the A track runs straight into "Aクラス受講
# 者のうち…"); cut the roster at the first such non-name run.
_FACULTY_TAIL = re.compile(r"(Aクラス受講者|※|予定講師は|\*1)")


# A roster may be prefixed by curriculum labels ("クラスレッスン：…", then mid-line
# "… コンテンポラリーダンス：…"). Drop every "<label>：" run so only names remain.
_FACULTY_LABEL = re.compile(r"\S*[：:]")


def _teachers(block: str) -> list[Teacher]:
    seen: set[str] = set()
    teachers: list[Teacher] = []
    for m in _FACULTY.finditer(block):
        raw = _FACULTY_TAIL.split(m.group(1), maxsplit=1)[0]
        raw = _FACULTY_LABEL.sub("、", raw)  # turn label runs into separators
        for chunk in re.split(r"[、,\s]+", raw):
            chunk = parse.clean(chunk)
            if not chunk or chunk.startswith("*") or "予定講師" in chunk:
                continue
            if chunk in seen:
                continue
            seen.add(chunk)
            teachers.append(Teacher(name=chunk, role="予定講師（変更の可能性あり）"))
    return teachers


# --- requirements: a defined-poses pose-photo submission ----------------------


def _page_requirements(text: str) -> list[Requirement]:
    """The pose-photo requirement is stated once on the page, not per track.

    Applicants submit a "ポーズ写真貼付用紙" (pose-photo attachment form) with photos
    taken in a specified manner. The exact poses live in a PDF form we can't
    reliably extract, so we record the defined-poses type faithfully without
    inventing the pose list.
    """
    reqs: list[Requirement] = []
    if "ポーズ写真" in text:
        reqs.append(
            PhotosReq(
                specificity="defined-poses",
                notes=(
                    "応募には「ポーズ写真貼付用紙」に指定の要領で撮影したポーズ写真を貼付して提出"
                    "（具体的なポーズは応募要項PDFに記載）。"
                ),
            )
        )
    return reqs
