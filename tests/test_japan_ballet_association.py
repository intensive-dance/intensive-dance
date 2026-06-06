"""Unit tests for the Japan Ballet Association — Summer Course scraper (JP page).

Source-shaped inline strings only — no network. The fixture mirrors the live
2026年度 サマー・コース announcement: a fully-dated course span ("2026年8月5日(水)
～8月9日(日)"), a 4泊5日 residential note, the Shiga Kogen venue, a JPY fee split
into tuition + accommodation (the latter bundling 1日3食 meals), three named guest
faculty with per-subject roles, a lesson list spanning several genres, a
Reiwa-era application window, and a Google Form apply link.
"""

from __future__ import annotations

from datetime import date

from selectolax.parser import HTMLParser

from intensive_dance.scrapers import japan_ballet_association as j

# A faithful, condensed slice of the live page (Japanese kept verbatim).
PAGE = (
    "Home > 講習会 > 2026年度 サマー・コース 開催のお知らせ "
    "2026年度 サマー・コース 開催のお知らせ 2026-03-23 講習会 お知らせ 告知中 本部 "
    "〈コース概要〉 "
    "開催期間：2026年8月5日(水)～8月9日(日) ＜4泊5日＞ "
    "開催場所：長野県志賀高原 ホテル一乃瀬 "
    "参加料：84,000円／1名 "
    "<内訳> 受講料:44,000円(税込)＋宿泊料:40,000円(税込) "
    "※宿泊費には1日3食の食事代が含まれます。 "
    "〈講師〉 "
    "フィオーナ・トンキン（クラシック・バレエ担当） "
    "マイレン・トレウバエフ（キャラクター＆ヒストリカル・ダンス担当） "
    "滝井 真樹子（コンテンポラリー担当） "
    "〈スタッフ〉 チーフ：多々納 みわ子 インストラクター：安藤 明代 ピアニスト：稲葉 智子 "
    "－レッスン内容－ "
    "基礎レッスン／バー＆センター・レッスン ポアント・レッスン ヒストリカルダンス "
    "キャラクター･ダンス コンテンポラリー・ダンスの基礎 "
    "※詳細は下記サマーコース参加要項をご確認ください。 "
    "【参加お申し込み方法】 下記リンク先もしくは参加要項記載のQRコードよりお申込みの上、"
    "所定の参加費用を下記口座へお振込みください。入金確認をもってお申込み確定といたします。 "
    "●お申込みは こちら "
    "●振込先口座：【三菱UFJ銀行 五反田支店 普通2624091 公益社団法人日本バレエ協会】 "
    "＜お申込み受付期間＞ 令和8年4月17日12：00～7月17日 "
    "※定員に達し次第、受付期間であってもお申込みを終了いたします。"
)


def _wrap_html(body_text: str, apply_href: str = "https://forms.gle/acRDx7p6czqoUjqm9") -> str:
    return (
        "<html><body><div>"
        + body_text.replace("こちら", f'<a href="{apply_href}">こちら</a>')
        + "</div></body></html>"
    )


def test_date_range_full_year_first_to_last_day():
    assert j._date_range(PAGE) == (date(2026, 8, 5), date(2026, 8, 9))


def test_date_range_handles_an_explicit_close_month():
    # A span that crosses into the next month must read the close month, not reuse August.
    text = "開催期間：2026年7月30日(水)～8月3日(日)"
    assert j._date_range(text) == (date(2026, 7, 30), date(2026, 8, 3))


def test_date_range_none_when_unparseable():
    assert j._date_range("開催場所：長野県志賀高原") == (None, None)


def test_schedule_note_is_the_nights_days_span():
    assert j._schedule_note(PAGE) == "4泊5日"


def test_apply_window_converts_reiwa_year():
    # 令和8 → 2026; opening date carries the era year, the close inherits it.
    opens_at, deadline = j._apply_window(PAGE)
    assert opens_at == date(2026, 4, 17)
    assert deadline == date(2026, 7, 17)


def test_apply_window_none_when_absent():
    assert j._apply_window("お申込みはこちら") == (None, None)


def test_apply_url_prefers_the_google_form_link():
    tree = HTMLParser(_wrap_html(PAGE))
    assert j._apply_url(tree) == "https://forms.gle/acRDx7p6czqoUjqm9"


def test_apply_url_falls_back_to_page_without_a_form_link():
    tree = HTMLParser("<html><body><a href='/other/'>x</a></body></html>")
    assert j._apply_url(tree) == j.PAGE


def test_prices_tuition_and_accommodation_with_meals():
    tuition, lodging = j._prices(PAGE)
    assert (tuition.amount, tuition.currency, tuition.includes) == (44000.0, "JPY", ["tuition"])
    assert "税込" in (tuition.label or "")
    assert lodging.amount == 40000.0
    # Accommodation bundles 1日3食 → meals rides along with accommodation.
    assert lodging.includes == ["accommodation", "meals"]
    assert lodging.notes is not None and "1日3食" in lodging.notes


def test_prices_accommodation_without_meals_drops_meals_include():
    text = "受講料:44,000円(税込)＋宿泊料:40,000円(税込)"  # no 1日3食 mention
    _, lodging = j._prices(text)
    assert lodging.includes == ["accommodation"]
    assert lodging.notes is None


def test_genres_matched_against_the_lesson_list():
    # 基礎/バー＆センター → classical, ポアント → pointe, ヒストリカル/キャラクター →
    # character, コンテンポラリー → contemporary.
    assert j._genres(PAGE) == ["classical", "pointe", "character", "contemporary"]


def test_teachers_named_faculty_with_roles_not_staff():
    teachers = j._teachers(PAGE)
    assert [t.name for t in teachers] == [
        "フィオーナ・トンキン",
        "マイレン・トレウバエフ",
        "滝井 真樹子",
    ]
    assert teachers[0].role == "クラシック・バレエ担当"
    # The 〈スタッフ〉 block (チーフ/インストラクター/ピアニスト) is not faculty.
    assert all("多々納" not in t.name for t in teachers)


def test_build_offering_full():
    offering = j._build_offering(_wrap_html(PAGE))
    assert offering is not None
    assert offering.id == "japan-ballet-association/summer-course-2026"
    assert offering.title == "2026年度 サマー・コース"
    assert offering.schedule.season == "2026"
    assert offering.schedule.start == date(2026, 8, 5)
    assert offering.schedule.end == date(2026, 8, 9)
    assert offering.schedule.timezone == "Asia/Tokyo"
    assert offering.schedule.notes == "4泊5日"
    assert offering.genres == ["classical", "pointe", "character", "contemporary"]
    # Ages are not stated on the public page — not invented.
    assert offering.age_range is None
    assert offering.location is not None
    assert offering.location.venue == "長野県志賀高原 ホテル一乃瀬"
    assert offering.location.country == "JP"
    assert len(offering.teachers) == 3
    assert len(offering.prices) == 2
    assert offering.application.opens_at == date(2026, 4, 17)
    assert offering.application.deadline == date(2026, 7, 17)
    assert offering.application.url == "https://forms.gle/acRDx7p6czqoUjqm9"
    # No audition/photo brief is stated → requirements unknown, not invented.
    assert offering.application.requirements == []


def test_build_offering_no_dated_edition():
    # A page without a parseable course span yields no offering.
    assert j._build_offering(_wrap_html("〈コース概要〉 開催場所：長野県志賀高原")) is None
