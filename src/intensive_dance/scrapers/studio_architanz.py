"""Studio ARCHITANZ (スタジオアーキタンツ), Tokyo (JP) — its guest-school
short-term-study workshop-audition (ワークショップ・オーディション).

ARCHITANZ is a Tokyo (Tamachi/Mita) studio that runs year-round drop-in open
classes with a rotating cast of international guest teachers, plus a separate
ATP (ARCHITANZ Training Program) full-time program on its own subdomain. Neither
of those is in scope: the open classes are ongoing drop-ins (not a dated
edition), and ATP is a long-term Ausbildung. What IS in scope is the studio's
recurring **short-term-study workshop-audition** — a discrete, dated multi-day
workshop where a visiting ballet *school* (e.g. The School of the Hamburg Ballet
+ English National Ballet School) teaches class/repertoire and screens dancers
for a short-term study (短期留学) placement.

API FIRST: plain WordPress. `a-tanz.com/wp-json/` is 200 with clean
`content.rendered` post bodies (no JS render, no proxy). The studio has no custom
post type for workshops; the editions live as ordinary `posts` tagged
"ワークショップ・オーディション". We fetch those via the REST search endpoint and parse
the 【…】-delimited overview blocks (日時/対象年齢/受講料/会場/講師/申込み締切) in the
body — no HTML page scrape. (verified live 2026-06-09)

DISCOVERY: one Offering per dated school workshop-audition edition. We keep only
the **school short-term-study** workshops (the body must mention 短期留学 +
バレエ学校/スクール) and drop pure professional-company auditions (e.g. Dortmund
Ballet's company audition), which aren't student intensives. The body splits
enrolment by purpose, not by curriculum: an **audition-track** band (per-school,
15–18) and a **workshop-only** band (14–18) over the same dates/fee/classes — so
this is one Offering with one `Session` per track (the per-track age band lives
on `Session`); the Offering ageRange spans both. Ended editions are kept (the
register never date-filters); the slug is year-stamped so a new edition rolls the
id forward. When no qualifying edition is posted the scraper yields [].

JAPANESE SOURCE: parsed language-agnostically and kept faithfully (no inline
translation). Dates are explicit "2025年8月4日（月）、5日（火）" so the year is read
straight from the line. Ages are plain numbers with a half/full-width dash
("15歳-18歳", "14-18歳"). JPY amounts are tax-inclusive (税込). Full-width digits
are normalized up front.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-09):
  - One Offering from a WP post body, two `Session`s (audition / workshop-only)
    with distinct ageRange; the Offering ageRange spans both.
  - A comma-listed, same-month multi-day date span read straight from the 日時 line.
  - JPY price ladder: workshop tuition + an optional audition-screening fee,
    tax-inclusive.
  - classical (バレエクラス) + repertoire (レパートリークラス, Demis Volpi works) +
    pointe (ポアントシューズ required in the dress code); no contemporary class taught.
  - Named guest faculty with affiliation (the visiting ballet-master, parsed from
    the 講師 block) — the studio's own staff are not over-claimed.
  - `application.deadline` from 申込み締切; `application.url` = the Google Form.
    The workshop doubles as an in-person audition (no photo/video brief is
    stated), so requirements stay `[]`; the audition/short-study flow is a note.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from intensive_dance import parse, wp
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

BASE = "https://a-tanz.com"
# The studio's WordPress REST posts; editions are tagged ワークショップ・オーディション.
# We search the body rather than guess a slug, then keep the in-scope school
# short-term-study workshops and pick the most recent.
SEARCH = "ワークショップ・オーディション"
POSTS = f"{BASE}/wp-json/wp/v2/posts"

ORG = Organization(
    name="Studio ARCHITANZ",
    slug="studio-architanz",
    country="JP",
    city="Tokyo",
)

VENUE_DEFAULT = "スタジオアーキタンツ"

# A school short-term-study workshop must speak of 短期留学 (short-term study) AND a
# ballet *school* — this excludes pro-company auditions (e.g. Dortmund Ballet's
# company audition), which are not student intensives. The defining marker is the
# structured per-school audition age band ("<school>：N歳-M歳") in the 対象年齢 block:
# it's absent from both pro-company auditions AND from the studio's drop-in
# promo classes that merely *cross-reference* the workshop (¥3,000 pay-at-door,
# 事前のお申込みは不要 = no application) — both of which we must skip.
_AUDITION_BAND = re.compile(
    r"(?:バレエ学校|バレエスクール|スクール)\s*[：:]\s*\d{1,2}\s*歳?\s*[-–~〜]\s*\d{1,2}\s*歳"
)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(
        POSTS,
        params={"search": SEARCH, "per_page": 20, "_fields": "id,link,date,title,content"},
        follow_redirects=True,
    )
    resp.raise_for_status()
    posts = resp.json()
    if not isinstance(posts, list):
        return []
    edition = _pick_edition(posts)
    if edition is None:
        return []
    offering = _build_offering(edition["content"]["rendered"], edition["link"])
    return [offering] if offering is not None else []


def _is_school_workshop(rendered: str) -> bool:
    text = wp.plain_text(rendered)
    return "短期留学" in text and bool(_AUDITION_BAND.search(text))


def _pick_edition(posts: list[dict]) -> dict | None:
    # The API returns posts newest-first, so the first qualifying school
    # short-term-study workshop is the current edition.
    for post in posts:
        rendered = post.get("content", {}).get("rendered", "")
        if rendered and _is_school_workshop(rendered):
            return post
    return None


def _build_offering(rendered: str, url: str) -> Offering | None:
    text = wp.plain_text(rendered).translate(parse.FULLWIDTH_DIGITS_TRANS)

    start, end = _date_range(text)
    if start is None or end is None:
        return None  # no dated edition parseable

    season = str(start.year)
    schools = _schools(text)
    sessions = _sessions(text)
    return Offering(
        id=f"studio-architanz/school-workshop-{season}",
        source=Source(provider="studio-architanz", url=url, scrapedAt=now_utc()),
        title=_title(schools, season),
        genres=_genres(_program_text(text)),
        ageRange=_offering_age_range(sessions),
        organization=ORG,
        location=Location(venue=_venue(text), city="Tokyo", country="JP"),
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
            deadline=_deadline(text),
            url=_apply_url(text) or url,
            notes=_apply_note(schools),
        ),
    )


# --- title: name the visiting school(s) + year, kept in Japanese ---------------
#
# The CMS post title is wrapped in 【受付中】-style banners, so we assemble a
# faithful Japanese title from the detected schools instead.


def _title(schools: list[str], season: str) -> str:
    head = "・".join(schools) + " " if schools else ""
    return f"{head}ワークショップ・オーディション {season}"


# --- schools: the visiting ballet school(s) screening for short-term study ------
#
# Named in the intro and again in the per-school 対象年齢 list. A small known map
# keeps the canonical Japanese name; we only record those actually present.

_SCHOOLS: list[tuple[str, str]] = [
    ("ハンブルク・バレエ学校", "ハンブルク・バレエ学校"),
    ("イングリッシュ・ナショナル・バレエスクール", "イングリッシュ・ナショナル・バレエスクール"),
    ("カナダ・ナショナル・バレエスクール", "カナダ・ナショナル・バレエスクール"),
    ("カナダ・ナショナル・バレエ・スクール", "カナダ・ナショナル・バレエスクール"),
    ("パルッカ", "パルッカ・シューレ・ドレスデン"),
]


def _schools(text: str) -> list[str]:
    out: list[str] = []
    for needle, canonical in _SCHOOLS:
        if needle in text and canonical not in out:
            out.append(canonical)
    return out


# --- dates: "2025年8月4日（月）、5日（火）" — explicit year, same-month day list -------
#
# The 日時 line gives a full year+month on the first day and bare days after, each
# with a weekday marker "（火）" that contains a 月/日 of its own — so we anchor on the
# year+month, then read every "<N>日（曜）" day token in the window up to the next 【
# section. First and last day bound the span (weekday parens ignored).

_DATE_HEAD = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")
_DAY_TOKEN = re.compile(r"(\d{1,2})日\s*（[月火水木金土日祝・]+）")


def _date_range(text: str) -> tuple[date | None, date | None]:
    m = _DATE_HEAD.search(text)
    if not m:
        return None, None
    year, month = int(m.group(1)), int(m.group(2))
    first_day = int(m.group(3))
    # Bound the window to this 日時 entry (stop at the next 【…】 section).
    window = text[m.start() : text.find("】", m.end()) if "】" in text[m.end() :] else m.end() + 60]
    days = [int(d) for d in _DAY_TOKEN.findall(window)] or [first_day]
    if first_day not in days:
        days.insert(0, first_day)
    return date(year, month, min(days)), date(year, month, max(days))


# --- deadline: "【申込み締切】 2025年8月1日（金）23:59" ---------------------------------

_DEADLINE = re.compile(r"締切】?\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")


def _deadline(text: str) -> date | None:
    m = _DEADLINE.search(text)
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


# --- apply url: the Google Form booking link ----------------------------------

_FORM = re.compile(r"https?://forms\.gle/\S+")


def _apply_url(text: str) -> str | None:
    m = _FORM.search(text)
    return m.group(0).rstrip(".,)") if m else None


# --- tracks → sessions --------------------------------------------------------
#
# The 対象年齢 block splits enrolment by purpose: an audition-screen track (per
# school, each "・<school>：15歳-18歳") and a workshop-only track ("14-18歳"). Both
# share dates/fee/classes, so each becomes a `Session` carrying its own age band;
# the raw band text stays in `notes`. School names carry internal "・", so we anchor
# each per-school band on the *known* school name (from `_SCHOOLS`) rather than a
# generic capture that the internal "・" would split.

_BAND = r"\s*[：:]\s*(\d{1,2})\s*歳?\s*[-–~〜]\s*(\d{1,2})\s*歳"
_WORKSHOP_BAND = re.compile(
    r"(?:オーディション審査をご希望されない|ワークショップとしての参加)[^【]*?"
    r"(\d{1,2})\s*歳?\s*[-–~〜]\s*(\d{1,2})\s*歳"
)


def _sessions(text: str) -> list[Session]:
    sessions: list[Session] = []
    seen: set[str] = set()
    for source_name, canonical in _SCHOOLS:
        m = re.search(re.escape(source_name) + _BAND, text)
        if not m or canonical in seen:
            continue
        seen.add(canonical)
        lo, hi = int(m.group(1)), int(m.group(2))
        sessions.append(
            Session(
                label=f"オーディション審査（{canonical}）",
                ageRange={"min": lo, "max": hi},
                notes=f"短期留学オーディション審査：{canonical} {lo}歳-{hi}歳",
            )
        )
    w = _WORKSHOP_BAND.search(text)
    if w:
        lo, hi = int(w.group(1)), int(w.group(2))
        sessions.append(
            Session(
                label="ワークショップのみ",
                ageRange={"min": lo, "max": hi},
                notes=f"ワークショップとしての参加（審査なし）：{lo}-{hi}歳",
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


# --- venue: "【会場】 スタジオアーキタンツ 01スタジオ" -----------------------------

_VENUE = re.compile(r"会場】?\s*(スタジオアーキタンツ[^【※\n]*)")


def _venue(text: str) -> str:
    m = _VENUE.search(text)
    return parse.clean(m.group(1)) if m else VENUE_DEFAULT


# --- prices: workshop tuition + optional audition-screening fee, tax-incl ------
#
# "■ 2日間通し（全4クラス）：28,000円（税込）" and "■ オーディション審査料：7,000円（税込）".

_TUITION = re.compile(r"([^■\n：:]*?通し[^：:]*?)[：:]\s*([\d,]+)\s*円\s*（税込）")
_AUDITION_FEE = re.compile(r"オーディション審査料\s*[：:]\s*([\d,]+)\s*円\s*（税込）")


def _prices(text: str) -> list[Price]:
    prices: list[Price] = []
    tm = _TUITION.search(text)
    if tm:
        amount = parse.parse_amount(tm.group(2))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="JPY",
                    label=parse.clean(tm.group(1)) + "（税込）",
                    includes=["tuition"],
                )
            )
    am = _AUDITION_FEE.search(text)
    if am:
        amount = parse.parse_amount(am.group(1))
        if amount is not None:
            prices.append(
                Price(
                    amount=amount,
                    currency="JPY",
                    label="オーディション審査料（希望者のみ・税込）",
                    includes=["tuition"],
                )
            )
    return prices


# --- genres -------------------------------------------------------------------
#
# A classical workshop: バレエクラス (classical) + レパートリークラス (repertoire);
# the dress code requires ポアントシューズ (pointe). No contemporary class is taught
# here — so genres are matched only on the *program* body, NOT the 【学校情報】
# school-profile blurb (which describes e.g. Hamburg's school teaching "クラシック
# バレエとコンテンポラリーダンス" — about the school's curriculum, not this workshop).

# Everything from the 【学校情報】 (school profile) marker on is provider blurb, not
# this workshop's class menu; cut it before genre keyword-matching.
_SCHOOL_INFO = "学校情報】"


def _program_text(text: str) -> str:
    cut = text.find(_SCHOOL_INFO)
    return text[:cut] if cut >= 0 else text


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("バレエクラス", "クラシック")),
    ("repertoire", ("レパートリー", "ヴァリエーション")),
    ("pointe", ("ポアント", "ポワント")),
    ("contemporary", ("コンテンポラリー",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- teachers: the named visiting ballet-master (講師) --------------------------
#
# "【講師】 Damiano Pettenella / ダミアーノ・ペッテネッラ ハンブルク・バレエ団 主任バレエ
# マスター". We keep the Latin name with the stated role/affiliation (the line
# after the JP name, up to the bio). The studio's own staff are an unattributable
# collective, left out rather than over-claimed.

_TEACHER = re.compile(
    r"講師】?\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.\s]+?)\s*[/／]\s*[^\s]+?\s+"
    r"([^【\n]*?(?:バレエマスター|監督|教師|講師|ディレクター))"
)
_AFFIL = re.compile(r"(.+?(?:バレエ団|劇場|カンパニー|学校|スクール))")


def _teachers(text: str) -> list[Teacher]:
    m = _TEACHER.search(text)
    if not m:
        return []
    name = parse.clean(m.group(1))
    role = parse.clean(m.group(2))
    affiliations: list[Affiliation] = []
    am = _AFFIL.match(role)
    if am:
        affiliations.append(Affiliation(organization=parse.clean(am.group(1)), current=True))
    return [Teacher(name=name, role=role, affiliations=affiliations)]


# --- application note: the audition / short-term-study flow, kept verbatim ------


def _apply_note(schools: list[str]) -> str:
    school_phrase = "・".join(schools) if schools else "招聘校"
    return (
        f"ワークショップ・オーディションは{school_phrase}への短期留学（および年間留学の最終審査）"
        "を兼ねる対面審査。合格者は最終審査への参加資格を得る。ワークショップのみの参加も可。"
        "お申し込みはGoogleフォームより、定員になり次第締め切り。"
    )
