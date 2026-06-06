"""Unit tests for the RAD Japan International Summer School scraper.

Source-shaped inline HTML only — no network. The fixture mirrors the live page's
structure: a full-width-digit headline edition stamp ("２０２６年８月…第３１回"), a
reception-open line ("2026年3月13日(金)…受付開始"), and four `div.course_box`
sections keyed by id (studentscourse-a…-d) each carrying its own English heading
(lead letter in a separate span), age band, year-less date span, fee and venue.
The Teachers' Courses block is included to prove it is NOT emitted.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import rad_japan_summer_school as rad


def _course_box(cid: str, lead: str, rest: str, days: str, body: str) -> str:
    # The live heading splits the first letter into its own span ("P erformance").
    return (
        f'<div class="course_box" id="{cid}">'
        f'<span class="lsize"><span class="red">{lead}</span></span>'
        f'<span class="msize">{rest}</span><span>&nbsp;for {days}</span>'
        f"{body}"
        f'<div class="mousikomi-btn2"><a href="{rad.APPLY_URL}">申し込み</a></div>'
        f"</div>"
    )


PAGE = (
    "<html><body>"
    '<div class="ss_txt1">２０２６年８月、第３１回インターナショナル・サマースクールin東京開催！</div>'
    '<div><span class="msize">2026年3月13日(金)12:00より受付開始</span></div>'
    # Students' Course A — 1 day, preschool, classical only.
    + _course_box(
        "studentscourse-a",
        "S",
        "tudents' Course A",
        "1day",
        "<span>スチューデントコースA チルドレン1日コース</span>"
        "<ul><li>対象 ： 受講時 幼児 年中~年長 （RAD経験不問）</li>"
        "<li>日程 ： <strong>7月31日(金)</strong></li>"
        "<li>会場 ： TRAD目白B2F 小林紀子バレエ・シアタースタジオ<br>"
        "受講料 : <strong>6,600円</strong>（税込）</li>"
        "<li>定員 ： 20名</li>"
        '<p class="scap">クラシックバレエの基礎と楽しいステップを学びます。</p></ul>',
    )
    # Students' Course B — 3 days, 小学1~2年生, classical + character.
    + _course_box(
        "studentscourse-b",
        "S",
        "tudents' Course B",
        "3 days",
        "<span>スチューデントコースB 3日間コース</span>"
        "<ul><li>対象 ： 受講時 小学1~2年生 （RAD経験不問）</li>"
        "<li>日程 ： <strong>7月29日(水)~31日(金)</strong></li>"
        "<li>会場 ： TRAD目白B2F 小林紀子バレエ・シアタースタジオ<br>"
        "受講料 : <strong>33,000円</strong>（税込）</li>"
        "<li>定員 ： 60名</li>"
        '<p class="scap">毎日クラシックバレエとキャラクターダンスの2クラスを受講します。</p></ul>',
    )
    # Performance Course A — 4 days, 小学3~5年生, classical + character + theatre demo.
    + _course_box(
        "studentscourse-c",
        "P",
        "erformance Course A",
        "4 days",
        "<span>パフォーマンスコースA 4日間コース</span>"
        "<ul><li>対象 ： 受講時 小学3~5年生（RAD経験不問）</li>"
        "<li>日程 ： <strong>8月1日(土)~4日(火)</strong>"
        "※8月4日はデモンストレーションへの出演がございます。</li>"
        "<li>会場 ： TRAD目白B2F 小林紀子バレエ・シアタースタジオ ／あうるすぽっと<br>"
        "受講料 : <strong>57,200円</strong>（税込）</li>"
        "<li>定員 ： 60名</li>"
        '<p class="scap">毎日クラシックとキャラクターダンスを学び、最終日は劇場で踊ります。</p></ul>',
    )
    # Performance Course B — 5 days, 小学6年生~20歳, classical + repertoire + creative.
    + _course_box(
        "studentscourse-d",
        "P",
        "erformance Course B",
        "5 days",
        "<span>パフォーマンスコースB 5日間コース</span>"
        "<ul><li>対象 ： 受講時 小学6年生~20歳（RAD経験不問）</li>"
        "<li>日程 ： <strong>7月31日(金)~8月4日(火)</strong>"
        "※8月4日はデモンストレーションへの出演がございます。</li>"
        "<li>会場 ： TRAD目白B2F 小林紀子バレエ・シアタースタジオ ／あうるすぽっと<br>"
        "受講料 : <strong>78,540円</strong>（税込）</li>"
        "<li>定員 ： 60名</li>"
        '<p class="scap">クラシック、レパートリー、クリエイティブダンスの1日3クラスを学びます。</p></ul>',
    )
    # A Teachers' Course block (RAD登録教師 CPD) — must NOT be emitted.
    + '<div class="course_box" id="teacherscourse-1">'
    "<span>Teachers' Course 01 シルバースワンズ</span>"
    "<ul><li>対象 ： RAD登録教師限定</li>"
    "<li>日程 ： 7月29日(水)午前</li>"
    "<li>受講料 : 33,000円（税込・RADメンバー価格）</li></ul></div>"
    "</body></html>"
)


def test_charset_from_meta_then_default():
    assert (
        rad._charset(b'<meta http-equiv="Content-Type" content="text/html; charset=euc-jp">')
        == "euc-jp"
    )
    assert rad._charset(b"<html><head><title>x</title>") == "euc-jp"
    assert rad._charset(b'<meta charset="utf-8">') == "utf-8"


def test_year_from_fullwidth_headline_stamp():
    from selectolax.parser import HTMLParser

    assert rad._year(HTMLParser(PAGE)) == 2026


def test_year_absent_returns_none():
    from selectolax.parser import HTMLParser

    assert rad._year(HTMLParser("<html><body><div>サマースクール開催</div></body></html>")) is None


def test_opens_at_reception_date():
    from selectolax.parser import HTMLParser

    assert rad._opens_at(HTMLParser(PAGE), 2026) == date(2026, 3, 13)


def test_date_range_span_with_month_rollover():
    assert rad._date_range("日程 ： 7月31日(金)~8月4日(火)", 2026) == (
        date(2026, 7, 31),
        date(2026, 8, 4),
    )


def test_date_range_same_month():
    assert rad._date_range("日程 ： 7月29日(水)~31日(金)", 2026) == (
        date(2026, 7, 29),
        date(2026, 7, 31),
    )


def test_date_range_single_day():
    assert rad._date_range("日程 ： 7月31日(金)", 2026) == (date(2026, 7, 31), date(2026, 7, 31))


def test_age_range_elementary_band():
    # 小学3~5年生 — the level prefix is named once for the 3〜5 digit pair.
    assert rad._age_range("対象 ： 小学3~5年生") == {"min": 8, "max": 11}


def test_age_range_explicit_upper_age_wins():
    # 小学6年生~20歳 — the explicit 20歳 sets the upper bound.
    assert rad._age_range("対象 ： 小学6年生~20歳") == {"min": 11, "max": 20}


def test_age_range_preschool():
    assert rad._age_range("対象 ： 幼児 年中~年長") == {"min": 4, "max": 6}


def test_genres_per_course_block():
    assert rad._genres("クラシックバレエの基礎を学びます。") == ["classical"]
    assert rad._genres("クラシックとキャラクターダンスを学びます。") == ["classical", "character"]
    assert rad._genres("クラシック、レパートリー、クリエイティブダンス。") == [
        "classical",
        "repertoire",
        "contemporary",
    ]


def test_prices_jpy_tax_inclusive():
    (price,) = rad._prices("受講料 : 78,540円（税込）")
    assert (price.amount, price.currency, price.includes) == (78540.0, "JPY", ["tuition"])
    assert "税込" in (price.label or "")


def test_build_offerings_four_student_courses_only():
    offerings = rad._build_offerings(PAGE)
    assert len(offerings) == 4  # the Teachers' Course is dropped
    ids = [o.id for o in offerings]
    assert ids == [
        "rad-japan-summer-school/students-course-a-2026",
        "rad-japan-summer-school/students-course-b-2026",
        "rad-japan-summer-school/performance-course-a-2026",
        "rad-japan-summer-school/performance-course-b-2026",
    ]
    for o in offerings:
        assert o.schedule.season == "2026"
        assert o.schedule.timezone == "Asia/Tokyo"
        assert o.organization.slug == "rad-japan-summer-school"
        assert o.organization.country == "JP"
        assert o.location is not None and o.location.city == "Tokyo"
        assert o.application.opens_at == date(2026, 3, 13)
        assert o.application.url == rad.APPLY_URL
        assert o.application.requirements == []  # no audition/photo brief stated


def test_build_offerings_facts_per_course():
    a, b, pa, pb = rad._build_offerings(PAGE)

    assert a.title == "RAD International Summer School 2026 — Students' Course A (1 day)"
    assert a.age_range == {"min": 4, "max": 6}
    assert a.genres == ["classical"]
    assert a.prices[0].amount == 6600.0
    assert (a.schedule.start, a.schedule.end) == (date(2026, 7, 31), date(2026, 7, 31))

    assert b.title == "RAD International Summer School 2026 — Students' Course B (3 days)"
    assert b.genres == ["classical", "character"]
    assert b.prices[0].amount == 33000.0
    assert (b.schedule.start, b.schedule.end) == (date(2026, 7, 29), date(2026, 7, 31))

    assert pa.age_range == {"min": 8, "max": 11}
    assert pa.prices[0].amount == 57200.0
    assert (pa.schedule.start, pa.schedule.end) == (date(2026, 8, 1), date(2026, 8, 4))
    assert pa.location is not None and "あうるすぽっと" in (pa.location.venue or "")

    assert pb.age_range == {"min": 11, "max": 20}
    assert pb.genres == ["classical", "repertoire", "contemporary"]
    assert pb.prices[0].amount == 78540.0
    assert (pb.schedule.start, pb.schedule.end) == (date(2026, 7, 31), date(2026, 8, 4))


def test_build_offerings_no_dated_edition():
    no_year = (
        "<html><body><div>サマースクール</div>"
        + '<div class="course_box" id="studentscourse-a">x</div></body></html>'
    )
    assert rad._build_offerings(no_year) == []
