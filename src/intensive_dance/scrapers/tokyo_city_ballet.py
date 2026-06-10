"""Tokyo City Ballet (東京シティ・バレエ団) — its スペシャルワークショップ.

The company that runs the 全国バレエコンペティション ("National Ballet
Competition"); this scraper covers ONLY the **Special Workshop** bundled with it,
not the competition (competitions are out of scope — AGENTS.md).

API FIRST: none. The main school site (tokyocityballet.org) is static
server-rendered HTML but lists no workshop page — the workshop lives on the
company's own competition microsite (tokyocityballetcompetition.com), itself
plain server-rendered HTML (full text in the markup, no JSON API, no JS render).
The dedicated `workshop.html` page is the primary, authoritative source: its
structured 開催概要 ("overview") block carries the dated edition. The site mixes
in stale prose from prior editions (commented-out 中止 lines, July/August dates
from past years in admin notes), so we anchor strictly on the structured
overview/fee blocks (`<h3>開催日</h3>` etc.) and never the loose prose.

DISCOVERY: one dated edition — スペシャルワークショップ2026, a 5-day short course
(Aug 2–6 2026) at the company's 東京シティ・バレエ団スタジオ in Koto-ku, Tokyo (near
「大島」 station — 大島 is the station, not the studio's name).
The overview splits enrolment into four **class types** that differ by age band
and (for the Special class) fee/genre — Classical, the new Special "become
Swanilda" repertoire class, Pilates&Classical, and Contemporary. Fee/dates are
otherwise shared, so this is **one Offering for the edition with one `Session`
per class type** (the per-class age band lives in `Session`, which carries the
`ageRange` an Offering can't split). The slug is year-stamped so the id rolls
forward when a new edition is posted.

JAPANESE SOURCE: parsed language-agnostically. Dates are explicit
`YYYY年M月D日(曜)～M月D日(曜)` in the overview, so the year is read straight from the
range (no title-stamp inference needed). Ages are stated as Japanese **school
grades**, not numbers — mapped to ages by the statutory April-entry schedule
(小N年→age 6+N…7+N, 中N年→12+N…13+N, 高N年→15+N…16+N); an open-ended "小学3年生～"
keeps a null upper bound, and the raw grade band stays verbatim in each session's
`notes`. JPY ASCII amounts. Source free text (title, class names, grade bands,
the AD's role line) is kept faithfully in Japanese, never translated inline.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-06):
  - One Offering, four `Session`s (per class type) with distinct ageRange — an
    open-ended band ("小学3年生～" → {min: 8}) and bounded bands; the Offering
    ageRange spans all classes (lowest min, open upper since a class is open).
  - JPY tuition priced **per class** (¥5,000; the Special class ¥6,000),
    tax-inclusive, attached to the matching session.
  - `classical` + `pointe` genres (a ★ポワント強化 / pointe-reinforced classical
    class) + `repertoire` (the Swanilda variation) + `contemporary`; a Pilates
    class is noted but maps to no ballet genre and is not invented as one.
  - `application.status` = open with `opensAt` (受付開始 2026/4/24); NO deadline
    is stated — each class "fills then closes" (定員になり次第締め切り), a rolling
    cap, not a dated cut — so `deadline` stays None (not invented).
  - No audition/photo brief is stated (a sewn-on レオタード nametag is a dress
    rule, not an application requirement), so requirements stay `[]`.
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

BASE = "https://tokyocityballetcompetition.com"
# The dedicated workshop page (the school's main site has no workshop page; this
# microsite is the company's own primary source). 404s into [] once retired.
PAGE = f"{BASE}/workshop.html"

ORG = Organization(
    name="Tokyo City Ballet",
    slug="tokyo-city-ballet",
    country="JP",
    city="Tokyo",
)

# The source title stem (kept faithfully in Japanese; not translated inline). The
# live title is "スペシャルワークショップ<year>".
TITLE_STEM = "スペシャルワークショップ"
VENUE_JA = "東京シティ・バレエ団スタジオ"

# Registration is by an online form, then payment; entry closes per class as it
# fills (no dated deadline). Kept verbatim as an application note.
_APPLY_NOTE = (
    "受講お申し込みフォームよりお申し込み（各クラス定員になり次第締め切り）。受講料は"
    "クラスごと・税込で、お申し込みより1週間以内に銀行振込。お問い合わせは"
    "workshop@tokyocityballet.org。"
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

    sessions = _sessions(text)
    return Offering(
        id=f"tokyo-city-ballet/special-workshop-{season}",
        source=Source(provider="tokyo-city-ballet", url=PAGE, scrapedAt=now_utc()),
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
        ),
        teachers=_teachers(text),
        prices=_prices(text),
        application=Application(
            status="open" if "受付開始" in text or "お申し込み" in text else None,
            opensAt=_opens_at(text),
            url=PAGE,
            notes=_APPLY_NOTE,
        ),
    )


# --- dates: explicit "2026年8月2日(日)～8月6日(木)" in the 開催概要 overview --------
#
# The overview gives a full year + month/day on the opening bound and a bare
# month/day on the closing bound. We read the year straight from the range (no
# title-stamp inference needed); the closing month falls back to the opening
# month when the close repeats it bare.

_RANGE = re.compile(
    r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日[^～~\-–]*?[～~\-–]\s*(?:(\d{1,2})月\s*)?(\d{1,2})日",
)


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _RANGE.search(text)
    if not m:
        return None, None
    year = int(m.group(1))
    start_month = int(m.group(2))
    end_month = int(m.group(4)) if m.group(4) else start_month
    return date(year, start_month, int(m.group(3))), date(year, end_month, int(m.group(5)))


# --- registration open date: "申込期間：2026年4月24日（金）受付開始" --------------
#
# No dated *deadline* is stated — each class closes when its cap fills
# (定員になり次第締め切り) — so only the opens-at date is recorded.

_OPENS = re.compile(r"申込期間[：:]\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")


def _opens_at(text: str) -> date | None:
    m = _OPENS.search(text)
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


# --- class types → sessions ---------------------------------------------------
#
# The 対象年齢 ("target age") list in the overview names each class type and its
# grade band; the 受講料 ("tuition") list prices each by the same name. We join on
# the class-type name so per-class age/fee never leak across, and map grade bands
# to ages by the statutory April-entry schedule (raw band kept in `notes`).


class _ClassType:
    def __init__(self, key: str, name: str) -> None:
        self.key = key
        self.name = name


# Order/names match the overview's 対象年齢 list.
_CLASS_TYPES = [
    _ClassType("classical", "クラシック・クラス"),
    _ClassType("swanilda", "スペシャル・クラス～スワニルダになりきろう～"),
    _ClassType("pilates", "ピラティス＆クラシック・クラス"),
    _ClassType("contemporary", "コンテンポラリー・クラス"),
]

# School-grade tokens: 小学N年(生) / 中学N年(生) / 高校N年(生).
_GRADE = re.compile(r"(小学|中学|高校)\s*(\d)\s*年")
# An open-ended band ("…～" with no closing grade), e.g. "小学3年生～".
_OPEN_END = re.compile(r"年生?\s*[～~]\s*$")


def _class_band(text: str, ct: _ClassType) -> str | None:
    # The 対象年齢 list line: "・<name>　<grade band>". Capture up to the next list
    # bullet/marker OR the next overview field (会場/主催/タイム…) so the last item
    # (Contemporary, with no trailing "・") doesn't swallow the following section.
    pat = re.compile(
        r"・\s*" + re.escape(ct.name) + r"\s*([^・※]*?)(?=\s*[・※]|会場|主催|タイム|$)"
    )
    m = pat.search(text)
    return parse.clean(m.group(1)) if m else None


def _band_age_range(band: str) -> dict | None:
    grades = _GRADE.findall(band)
    if not grades:
        return None
    low_level, low_grade = grades[0]
    low = parse.japanese_grade_to_age(low_level, int(low_grade))
    if len(grades) == 1 and _OPEN_END.search(band):
        return {"min": low}  # "小学3年生～" — open-ended upper bound
    high_level, high_grade = grades[-1]
    # Upper bound is the END of the top grade's year (one year past its start age).
    high = parse.japanese_grade_to_age(high_level, int(high_grade)) + 1
    return {"min": low, "max": high}


def _sessions(text: str) -> list[Session]:
    sessions: list[Session] = []
    for ct in _CLASS_TYPES:
        band = _class_band(text, ct)
        if band is None:
            continue
        sessions.append(
            Session(
                label=ct.name,
                ageRange=_band_age_range(band),
                notes=band,
            )
        )
    return sessions


def _offering_age_range(sessions: list[Session]) -> dict | None:
    bounds = [s.age_range for s in sessions if s.age_range]
    if not bounds:
        return None
    out: dict = {"min": min(b["min"] for b in bounds)}
    # Open upper bound if ANY class is open-ended; otherwise the widest stated max.
    maxes = [b["max"] for b in bounds if "max" in b]
    if maxes and len(maxes) == len(bounds):
        out["max"] = max(maxes)
    return out


# --- prices: "<class name>：5,000円／1クラス（税込）" — JPY, per class, tax-incl. ---

_PRICE = re.compile(r"([\d,]+)\s*円／1クラス（税込）")


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    for ct in _CLASS_TYPES:
        m = re.search(re.escape(ct.name) + r"[：:]\s*([\d,]+)\s*円／1クラス（税込）", text)
        if not m:
            continue
        amount = parse.parse_amount(m.group(1))
        if amount is None:
            continue
        prices.append(
            Price(
                amount=amount,
                currency="JPY",
                label=f"{ct.name}（1クラス・税込）",
                includes=["tuition"],
            )
        )
    return prices


# --- genres -------------------------------------------------------------------
#
# Matched against the class menu, not loose prose. The course centres on classical
# class (with a ★ポワント強化 / pointe-reinforced class → pointe), adds a Swanilda
# repertoire variation (repertoire) and a contemporary class. A Pilates class is
# offered but isn't a ballet genre, so it maps to nothing rather than being faked.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("クラシック",)),
    ("pointe", ("ポワント", "ポアント", "トウシューズ")),
    ("repertoire", ("ヴァリエーション", "スワニルダ")),
    ("contemporary", ("コンテンポラリー",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- teachers: the named artistic director (芸術監督) ----------------------------
#
# The AD is named with her role in the profile block — "安達 悦子 Etsuko Adachi
# 東京シティ・バレエ団芸術監督／理事長". She is verifiable and leads the workshop; the
# wider profile roll mixes in prior editions' guests, so we record only the named
# AD with her stated role (parsed from the page, not hardcoded) rather than
# over-claim an unattributable roster (the call tokyo_ballet_school / Joffrey /
# ENBS also make).

_AD = re.compile(
    r"安達\s*悦子\s*(?:Etsuko\s*Adachi)?\s*(東京シティ・バレエ団[^<。\s]*(?:監督|理事)[^<。\s]*)"
)


def _teachers(text: str) -> list[Teacher]:
    m = _AD.search(text)
    if not m:
        return []
    return [Teacher(name="安達悦子", role=parse.clean(m.group(1)))]
