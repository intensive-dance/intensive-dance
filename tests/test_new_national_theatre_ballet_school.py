"""Unit tests for the New National Theatre Ballet School scraper (Japanese page).

Source-shaped inline strings only — no network. The fixture mirrors the live
page's structure: a shared course-date line, two track sections ("Aクラス
〈13－14歳〉" / "Bクラス 〈15－18歳〉") each with its own age band, fee, schedule and
予定講師 roster, an application window with a 必着 deadline, and the page-wide
pose-photo requirement.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import PhotosReq
from intensive_dance.scrapers import new_national_theatre_ballet_school as nnt

# A faithful, condensed slice of the live page (Japanese kept verbatim).
PAGE = (
    "新国立劇場バレエ研修所「夏の特別バレエレッスン」のお知らせ "
    "プロをめざす13歳から18歳 （2027〈R9〉年4月1日時点） までの方々にむけたクラスです。 "
    "開催概要 "
    "日程 ：2026年8月20日（木）～22日（土）の３日間 "
    "会場 ：新国立劇場リハーサル室 "
    "主催 ：新国立劇場バレエ研修所 "
    "応募方法 【申込開始期間】2026年5月25日（月）～6月19日（金）必着 "
    "【ポーズ写真貼付用紙】 ポーズ写真貼付用紙をプリントアウトし、指定された要領で写真を貼付、提出してください。 "
    "対象年齢とクラス "
    "Aクラス 〈13－14歳〉 将来プロとしてバレエを踊る上で一番大切な基礎固めのクラスです。 "
    "3 日間 １クラス定員30名程度 【内 容】 クラスレッスン "
    "【受講料】 28,000円（税込） ※3日間の料金です "
    "【日程詳細 A1クラス】 ・8月20日（木）10:50-12:30 クラスレッスン ★タイムテーブル（A1クラス）（PDF） "
    "【A1クラス予定講師】*1 イルギス・ガリムーリン、西山裕子、八幡顕光 "
    "【日程詳細 A2クラス】 ・8月20日（木）13:30-15:10 クラスレッスン ★タイムテーブル（A2クラス）（PDF） "
    "【A2クラス予定講師】*1 本島美和、小嶋直也、イルギス・ガリムーリン "
    "Aクラス受講者のうち希望者は、ジュニアクラスの選考にご応募いただけます。 "
    "Bクラス 〈 15－18歳 〉 ステップアップするためのクラスです。コンテンポラリーダンスクラスも開講します。 "
    "3 日間 定員30名程度 【内 容】 クラスレッスンおよびコンテンポラリーダンス "
    "【受講料】 39,000円（税込） ※3日間の料金です "
    "【日程詳細】 ・8月20日（木）11:00-12:30 クラスレッスン／13:15-14:45 コンテンポラリーダンスクラス "
    "★タイムテーブル（Bクラス）（PDF） "
    "【予定講師】*1 クラスレッスン：小嶋直也、西山裕子、八幡顕光 コンテンポラリーダンス：新井美紀子 "
    "*1 予定講師は予告なく変更になる可能性がございます。 "
    "説明会概要 バレエ研修所の研修体系についてご説明します。 "
    "お問い合わせ／ 新国立劇場バレエ研修所"
)


def test_date_range_japanese_span():
    assert nnt._date_range(PAGE) == (date(2026, 8, 20), date(2026, 8, 22))


def test_date_range_absent():
    assert nnt._date_range("日程は未定です。") == (None, None)


def test_deadline_uses_window_close_must_arrive_by():
    # 必着 = must-arrive-by; the close day (6/19) inherits the year, its own month.
    assert nnt._deadline(PAGE) == date(2026, 6, 19)


def test_age_range_per_track_full_width_hyphen():
    a_block = nnt._track_block(PAGE, nnt._TRACKS[0])
    b_block = nnt._track_block(PAGE, nnt._TRACKS[1])
    assert a_block is not None and b_block is not None
    assert nnt._age_range(a_block) == {"min": 13, "max": 14}
    assert nnt._age_range(b_block) == {"min": 15, "max": 18}


def test_track_blocks_do_not_leak_fees():
    a_block = nnt._track_block(PAGE, nnt._TRACKS[0])
    b_block = nnt._track_block(PAGE, nnt._TRACKS[1])
    assert a_block is not None and b_block is not None
    assert "28,000" in a_block and "39,000" not in a_block
    assert "39,000" in b_block and "28,000" not in b_block


def test_prices_jpy_tax_inclusive():
    a_block = nnt._track_block(PAGE, nnt._TRACKS[0])
    assert a_block is not None
    (price,) = nnt._prices(a_block)
    assert (price.amount, price.currency, price.includes) == (28000.0, "JPY", ["tuition"])
    assert "税込" in (price.label or "")


def test_genres_contemporary_only_on_b_track():
    a_block = nnt._track_block(PAGE, nnt._TRACKS[0])
    b_block = nnt._track_block(PAGE, nnt._TRACKS[1])
    assert a_block is not None and b_block is not None
    assert nnt._genres(a_block) == ["classical"]
    assert nnt._genres(b_block) == ["classical", "contemporary"]


def test_teachers_merge_unique_across_rosters():
    a_block = nnt._track_block(PAGE, nnt._TRACKS[0])
    b_block = nnt._track_block(PAGE, nnt._TRACKS[1])
    assert a_block is not None and b_block is not None
    a_names = [t.name for t in nnt._teachers(a_block)]
    b_names = [t.name for t in nnt._teachers(b_block)]
    # A merges A1 + A2 rosters, deduping イルギス・ガリムーリン.
    assert a_names == ["イルギス・ガリムーリン", "西山裕子", "八幡顕光", "本島美和", "小嶋直也"]
    # B keeps the class-lesson names AND the contemporary teacher (label-stripped).
    assert b_names == ["小嶋直也", "西山裕子", "八幡顕光", "新井美紀子"]
    assert all(t.role == "予定講師（変更の可能性あり）" for t in nnt._teachers(a_block))


def test_dates_note_captures_both_a1_and_a2_sub_tracks():
    # The A class splits into A1 (morning 10:50-12:30) and A2 (afternoon 13:30-15:10).
    # Both 【日程詳細 …】 blocks must appear in the note so neither time-slot is lost.
    a_block = nnt._track_block(PAGE, nnt._TRACKS[0])
    assert a_block is not None
    note = nnt._dates_note(a_block)
    assert note is not None
    assert "10:50" in note  # A1 morning time
    assert "13:30" in note  # A2 afternoon time


def test_dates_note_b_track_single_block():
    # The B class has one schedule block; the note must still be populated.
    b_block = nnt._track_block(PAGE, nnt._TRACKS[1])
    assert b_block is not None
    note = nnt._dates_note(b_block)
    assert note is not None
    assert "11:00" in note


def test_page_requirements_defined_poses():
    (req,) = nnt._page_requirements(PAGE)
    assert isinstance(req, PhotosReq)
    assert req.specificity == "defined-poses"
    assert req.poses == []  # the pose names live in a PDF we don't invent


def test_build_offerings_two_tracks():
    offerings = nnt._build_offerings(_wrap_html(PAGE))
    assert len(offerings) == 2
    a, b = offerings
    assert a.id == "new-national-theatre-ballet-school/summer-special-a-2026"
    assert b.id == "new-national-theatre-ballet-school/summer-special-b-2026"
    for o in offerings:
        assert o.schedule.start == date(2026, 8, 20)
        assert o.schedule.end == date(2026, 8, 22)
        assert o.schedule.season == "2026"
        assert o.schedule.timezone == "Asia/Tokyo"
        assert o.location is not None
        assert o.location.venue == "新国立劇場リハーサル室"
        assert o.location.country == "JP"
        assert o.application.deadline == date(2026, 6, 19)
        assert o.application.url == nnt.APPLY_URL
        assert [r.type for r in o.application.requirements] == ["photos"]
    assert a.genres == ["classical"]
    assert b.genres == ["classical", "contemporary"]
    assert a.prices[0].amount == 28000.0
    assert b.prices[0].amount == 39000.0


def test_build_offerings_no_dated_edition():
    assert nnt._build_offerings(_wrap_html("日程は未定です。Aクラス 〈13－14歳〉")) == []


def _wrap_html(body_text: str) -> str:
    return f"<html><body><div>{body_text}</div></body></html>"
