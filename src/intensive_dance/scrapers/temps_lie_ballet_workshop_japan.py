"""Temps Lié Ballet Workshop Japan (日仏舞踊協会 タンリエ / Association le-temps-lié),
Tokyo + Osaka (JP).

The Franco-Japanese dance association "le-temps-lié" (タンリエ) runs an annual
summer ballet workshop in Japan with Paris Opéra / CNSMDP faculty — distinct from
its other public activity, which is **registration support** (登録サポート) for
*foreign* schools' auditions/summer schools (Paris Opéra, Cannes Rosella
Hightower, CNSMD Lyon …). Those agency-mediated listings are NOT this org's own
dated intensive and are deliberately ignored; only the self-run "タンリエバレエ
ワークショップ in Japan" edition is scraped.

API FIRST: none. The association's main site (`le-temps-lie.org`) is a Jimdo
build whose Info pages carry only the agency listings. The workshop itself lives
on the sister Jimdo site `paris-tokyo-ballet.com` ("WORKSHOP IN PARIS - TOKYO"),
whose `/summer-japan-2026/` page server-renders the full edition into the static
HTML (dates, venues, level/age bands, JPY fees, faculty all present), so a plain
fetch is enough — no JSON API, no JS render, no proxy needed
(verified live 2026-06-09).

DISCOVERY: the 2026 edition runs as **two separate city sessions** with distinct
dates, venues, currency-section and fees — Tokyo (東京バレエ学校 新館スタジオ,
8/25–27) and Osaka (K★バレエスタジオ, 8/12–13). They are genuinely different
editions of the same workshop, so we emit **one Offering per city** (folding would
lose the per-city dates/venue/price split). Each city's enrolment splits into
three **ballet levels** that share dates/venue/curriculum and differ only by age
band, so each level becomes one `Session` carrying its own band; the Offering
ageRange spans all levels (open-topped, since the 上級/プロ class is 16歳以上).
A guest **contemporary** class (希望者 / optional) and an optional private
variation lesson run alongside the ballet spine — folded into the Offering's
genres + notes, not split into extra Offerings.

JAPANESE SOURCE: parsed language-agnostically and kept faithfully (no inline
translation). Dates are explicit `2026年8月25日…` (year present on the page — no
title-stamp inference needed); a `str.translate` to ASCII guards against the
full-width digits these JP pages love even though this edition uses half-width.
Level age bands are stated as plain ages with a 目安 ("approximate") caveat —
"上級/プロ 16歳以上" (open top), "高等 14-16歳", "中級 12-13歳" — kept verbatim in
each session's notes. JPY amounts are tax-EXCLUSIVE (税別), flagged in the price
label.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-09):
  - Two Offerings from one page (per-city split), distinct dates/venue/prices;
    each with three ballet-level `Session`s — one open-topped (上級/プロ 16歳以上),
    so the Offering ageRange also keeps a null upper bound.
  - A per-city JPY price ladder (ballet 1/2/3-class bundles + contemporary
    bundles), tax-exclusive, plus a shared private-lesson fee (¥19,500/30min).
  - classical + contemporary genres (a guest contemporary class is actually
    taught) + pointe (高等以上はポワント持参) + repertoire (the private variation
    lesson). The genre table is matched against the program/class menu.
  - Named faculty with affiliations: Gil Isoart (Paris Opéra Ballet teacher /
    CNSMDP professor, ballet), Kenta Kojiri (contemporary, Tokyo), Yu Otagaki
    (contemporary, Osaka), and the named pianists.
  - Requirements stay `[]` ("not stated"): the workshop classes are 先着順
    (first-come, fills then closes — no dated deadline, a rolling cap). Only the
    OPTIONAL private lesson has a 5/31 cut-off and a video selection; that is kept
    verbatim in `application.notes`, not turned into a workshop entry requirement.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Affiliation,
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

BASE = "https://www.paris-tokyo-ballet.com"
# The workshop's own dedicated page (the association site only lists agency
# support). The slug year-stamps with the edition; 404s into [] once retired.
PAGE = f"{BASE}/summer-japan-2026/"

ORG = Organization(
    name="Association le-temps-lié (日仏舞踊協会 タンリエ)",
    slug="temps-lie-ballet-workshop-japan",
    country="JP",
)

# The source title stem (kept faithfully in Japanese; not translated inline). The
# live title is "タンリエバレエワークショップ in Japan <year>".
TITLE_STEM = "タンリエバレエワークショップ in Japan"

# Registration is by online form, first-come (先着順), each class closing when its
# cap fills — no dated deadline. The optional private lesson alone has a 5/31
# cut-off and a video selection. Kept verbatim as an application note.
_APPLY_NOTE = (
    "講習会の通常クラスは先着順で受付（募集人数になり次第締め切り）。"
    "プライベートレッスン（ヴァリエーション指導・希望者のみ）は先着順ではなく、"
    "申込後に動画を送付のうえ選考、申込締切は5月31日。お申込みは"
    "paris-tokyo-ballet.com のメールフォームより。"
)

# The explicit "now accepting applications" phrase; the optional み matches both
# the live spelling (お申込み受付中) and the compact お申込受付中.
_ACCEPTING = re.compile(r"お申込み?受付中")


class _City:
    def __init__(self, key: str, label_ja: str, city: str) -> None:
        self.key = key
        self.label_ja = label_ja  # the "東京"/"大阪" anchor used on the page
        self.city = city


_CITIES = [
    _City("tokyo", "東京", "Tokyo"),
    _City("osaka", "大阪", "Osaka"),
]


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
    body = tree.css_first("body")
    text = (parse.clean(body.text(separator=" ")) if body else "").translate(
        parse.FULLWIDTH_DIGITS_TRANS
    )

    year = _year(text)
    if year is None:
        return []  # no dated edition parseable

    teachers = _teachers(text)
    sessions = _sessions(text)
    offerings: list[Offering] = []
    for city in _CITIES:
        start, end = _date_range(text, city, year)
        if start is None or end is None:
            continue
        season = str(year)
        offerings.append(
            Offering(
                id=f"temps-lie-ballet-workshop-japan/summer-{city.key}-{season}",
                source=Source(
                    provider="temps-lie-ballet-workshop-japan", url=PAGE, scrapedAt=now_utc()
                ),
                title=f"{TITLE_STEM} {season}（{city.label_ja}）",
                genres=_genres(text, city),
                ageRange=_offering_age_range(sessions),
                organization=ORG,
                location=_location(text, city),
                schedule=Schedule(
                    season=season,
                    start=start,
                    end=end,
                    timezone="Asia/Tokyo",
                    sessions=sessions,
                ),
                teachers=_city_teachers(teachers, city),
                prices=_prices(text, city),
                application=Application(
                    # "open" only from the explicit "now accepting" phrase
                    # (お申込[み]受付中) — the optional み matches both the live
                    # spelling (お申込み受付中) and the compact form. The bare
                    # "お申込み" (the apply-here button label) is NOT a status
                    # signal — it stays present after a close, so it's not used.
                    status="open" if _ACCEPTING.search(text) else None,
                    url=f"{BASE}/apply-summer-japan-2026/",
                    notes=_APPLY_NOTE,
                ),
            )
        )
    return offerings


# --- year: explicit in the title "タンリエバレエワークショップ in Japan <YYYY>" --------

_YEAR = re.compile(re.escape("タンリエバレエワークショップ") + r"\s*in\s*Japan\s*(\d{4})")


def _year(text: str) -> int | None:
    m = _YEAR.search(text)
    return int(m.group(1)) if m else None


# --- dates --------------------------------------------------------------------
#
# Per-city overview lines, year present:
#   Tokyo "東京 ： 2026年8月25日-26日-27日 / 講習会" (hyphen-joined day run)
#   Osaka "大阪 ： 2026年8月12日と13日 / 講習会期間中…" ("と"-joined two days)
# We read the month + the first/last day of that city's run.

_TOKYO_DATES = re.compile(
    r"東京\s*[：:]\s*(\d{4})年\s*(\d{1,2})月\s*((?:\d{1,2}日[-、と〜~\s]*)+?)\s*/\s*講習会"
)
_OSAKA_DATES = re.compile(r"大阪\s*[：:]\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日と(\d{1,2})日")


def _date_range(text: str, city: _City, year: int) -> tuple[date | None, date | None]:
    if city.key == "tokyo":
        m = _TOKYO_DATES.search(text)
        if not m:
            return None, None
        month = int(m.group(2))
        days = [int(d) for d in re.findall(r"\d{1,2}", m.group(3))]
        if not days:
            return None, None
        return date(year, month, days[0]), date(year, month, days[-1])
    m = _OSAKA_DATES.search(text)
    if not m:
        return None, None
    month = int(m.group(2))
    return date(year, month, int(m.group(3))), date(year, month, int(m.group(4)))


# --- venue / location ---------------------------------------------------------
#
# The 開催地 block: "東京 ： <venue> / <address> ( http… )" then "大阪 ： <venue> /
# <address> ( https://k-ballet… )". We read the venue name (before the slash);
# the city is fixed per record.

_TOKYO_VENUE = re.compile(r"開催地\s*東京\s*[：:]\s*([^/(]+?)\s*/\s*[^(]+?\(\s*https")
_OSAKA_VENUE = re.compile(r"大阪\s*[：:]\s*([^/(]+?)\s*/\s*[^(]+?\(\s*https://k-ballet")


def _location(text: str, city: _City) -> Location:
    pat = _TOKYO_VENUE if city.key == "tokyo" else _OSAKA_VENUE
    m = pat.search(text)
    venue = parse.clean(m.group(1)) if m else None
    return Location(venue=venue, city=city.city, country="JP")


# --- ballet levels → sessions -------------------------------------------------
#
# One shared 対象年齢 block names the three ballet levels with their (目安 /
# approximate) age bands; both cities run the same three levels. Each level
# becomes a `Session` carrying its own band (raw band kept in notes). 上級/プロ is
# "16歳以上" — open-topped (null upper bound).

_LEVELS: list[tuple[str, re.Pattern[str]]] = [
    ("上級/プロ クラス", re.compile(r"上級/プロ\s*クラス\s*[：:]\s*(\d{1,2})歳以上")),
    ("高等クラス", re.compile(r"高等クラス\s*[：:]\s*(\d{1,2})-(\d{1,2})歳")),
    ("中級クラス", re.compile(r"中級クラス\s*[：:]\s*(\d{1,2})-(\d{1,2})歳")),
]


def _sessions(text: str) -> list[Session]:
    sessions: list[Session] = []
    for label, pat in _LEVELS:
        m = pat.search(text)
        if not m:
            continue
        if len(m.groups()) == 1:  # "16歳以上" — open-ended upper bound
            band = {"min": int(m.group(1)), "max": None}
            note = f"{label}：{m.group(1)}歳以上（目安）"
        else:
            band = {"min": int(m.group(1)), "max": int(m.group(2))}
            note = f"{label}：{m.group(1)}-{m.group(2)}歳（目安）"
        sessions.append(Session(label=label, ageRange=band, notes=note))
    return sessions


def _offering_age_range(sessions: list[Session]) -> dict | None:
    bounds = [s.age_range for s in sessions if s.age_range]
    if not bounds:
        return None
    maxes = [b.get("max") for b in bounds]
    # Open upper bound if ANY level is open-ended (上級/プロ = 16+).
    overall_max = None if any(m is None for m in maxes) else max(m for m in maxes if m is not None)
    return {"min": min(b["min"] for b in bounds), "max": overall_max}


# --- prices: the per-city JPY ladder, tax-EXCLUSIVE (税別) ----------------------
#
# Each city has its own "[<city>] 受講費用" block listing ballet (Tokyo labels it
# "バレエクラスレッスン", Osaka "クラスレッスン") and contemporary bundles by class
# count, e.g. "… 3回 ¥ 34,500 (税別) / 3クラス". We slice the block for the city so
# Tokyo/Osaka fees never cross, then read each "<N>回 ¥<amt>" row. A shared
# private-lesson fee follows in "[プライベートレッスン] 受講費用".

_PRICE_ROW = re.compile(
    r"(バレエ\s*クラスレッスン|クラスレッスン|コンテンポラリーレッスン)\s*(\d)\s*回\s*¥?\s*([\d,]+)\s*\(税別\)"
)
_PRIVATE_ROW = re.compile(r"プライベートレッスン[^¥]*?¥?\s*([\d,]+)\s*\(税別\)\s*/\s*(\d+)\s*min")


def _price_block(text: str, city: _City) -> str:
    header = f"[{city.label_ja}] 受講費用"
    start = text.find(header)
    if start < 0:
        return ""
    end = text.find("[プライベートレッスン] 受講費用", start)
    # Tokyo block ends where the Osaka block begins; Osaka ends at the private block.
    if city.key == "tokyo":
        osaka = text.find("[大阪] 受講費用", start)
        if osaka >= 0:
            end = osaka
    return text[start:end] if end >= 0 else text[start:]


def _kind_label(raw: str) -> str:
    return "コンテンポラリー" if "コンテンポラリー" in raw else "バレエ"


def _prices(text: str, city: _City) -> list[Price]:
    prices: list[Price] = []
    seen: set[tuple[str, int]] = set()
    block = _price_block(text, city)
    for m in _PRICE_ROW.finditer(block):
        kind = _kind_label(m.group(1))
        count = int(m.group(2))
        amount = parse.parse_amount(m.group(3))
        if amount is None or (kind, count) in seen:
            continue
        seen.add((kind, count))
        prices.append(
            Price(
                amount=amount,
                currency="JPY",
                label=f"{kind}クラスレッスン {count}回（税別）",
                includes=["tuition"],
            )
        )
    # Shared private-lesson fee (東京・大阪共通) — append to each city's ladder.
    pm = _PRIVATE_ROW.search(text)
    if pm:
        pamount = parse.parse_amount(pm.group(1))
        if pamount is not None:
            prices.append(
                Price(
                    amount=pamount,
                    currency="JPY",
                    label=f"プライベートレッスン（{pm.group(2)}分・希望者のみ・税別）",
                    includes=["tuition"],
                )
            )
    return prices


# --- genres -------------------------------------------------------------------
#
# Matched against the class menu. Ballet class is the spine (classical); a guest
# contemporary class is actually taught (contemporary); 高等以上はポワント持参
# (pointe); the private lesson is variation coaching (repertoire). Both cities run
# the same menu, so the genre set is the same per city.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("バレエクラス", "クラスレッスン", "バレエ")),
    ("contemporary", ("コンテンポラリー",)),
    ("pointe", ("ポワント", "ポアント")),
    ("repertoire", ("ヴァリエーション",)),
]


def _genres(text: str, city: _City) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- teachers: the named guest faculty + pianists -----------------------------
#
# Three named guest teachers, each "<JP name> <English name>" with a role/
# affiliation line, plus the named pianists. Isoart teaches ballet in both
# cities; Kojiri the Tokyo contemporary; Otagaki the Osaka contemporary — so the
# contemporary teacher is filtered per city.

_ISOART = re.compile(r"ジル・?\s*イゾアール\s*Gil\s*Isoart")
_KOJIRI = re.compile(r"小尻\s*健太\s*Kenta\s*Kojiri")
_OTAGAKI = re.compile(r"太田垣悠\s*Yu\s*Otagaki")
# "ピアニスト： 名前（所属）名前（所属）…" up to the next section header.
_PIANISTS = re.compile(r"ピアニスト[：:]\s*(.+?)\s*開催各クラスの詳細")
_PIANIST = re.compile(r"([^（）()]+?)\s*[（(]([^）)]+)[)）]")


def _teachers(text: str) -> list[Teacher]:
    teachers: list[Teacher] = []
    if _ISOART.search(text):
        teachers.append(
            Teacher(
                name="Gil Isoart",
                role="バレエクラス講師（東京・大阪）",
                affiliations=[
                    Affiliation(organization="Paris Opéra Ballet", role="教師", current=True),
                    Affiliation(
                        organization="Conservatoire national supérieur de musique et de "
                        "danse de Paris (CNSMDP)",
                        role="教授",
                        current=True,
                    ),
                ],
            )
        )
    if _KOJIRI.search(text):
        teachers.append(
            Teacher(
                name="Kenta Kojiri",
                role="コンテンポラリークラス講師（東京）",
                affiliations=[Affiliation(organization="ダンサー・振付家")],
            )
        )
    if _OTAGAKI.search(text):
        teachers.append(
            Teacher(
                name="Yu Otagaki",
                role="コンテンポラリークラス講師（大阪）",
                affiliations=[
                    Affiliation(organization="元リヨン・オペラ座バレエ団／ジュネーヴ歌劇場バレエ")
                ],
            )
        )
    teachers.extend(_pianists(text))
    return teachers


def _pianists(text: str) -> list[Teacher]:
    m = _PIANISTS.search(text)
    if not m:
        return []
    out: list[Teacher] = []
    for pm in _PIANIST.finditer(m.group(1)):
        name = parse.clean(pm.group(1))
        affiliation = parse.clean(pm.group(2))
        if not name:
            continue
        out.append(
            Teacher(
                name=name,
                role="ピアニスト",
                affiliations=[Affiliation(organization=affiliation)] if affiliation else [],
            )
        )
    return out


def _city_teachers(teachers: list[Teacher], city: _City) -> list[Teacher]:
    # Keep Isoart + pianists (both cities); the contemporary teacher is city-bound.
    other_city = "大阪" if city.key == "tokyo" else "東京"
    return [t for t in teachers if f"（{other_city}）" not in (t.role or "")]
