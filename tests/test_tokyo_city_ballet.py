"""Unit tests for the Tokyo City Ballet Special Workshop scraper (Japanese page).

Source-shaped inline strings only — no network. The fixture mirrors the live
`workshop.html` 開催概要 ("overview") + 受講料 ("tuition") blocks: an explicit dated
span ("2026年8月2日(日)～8月6日(木)"), four class types in the 対象年齢 list each with
a school-grade band (one open-ended "小学3年生～", one bounded), per-class JPY fees
(¥5,000; the Special class ¥6,000), the registration-open date ("申込期間：
2026年4月24日（金）受付開始"), and the AD's profile/role line. No audition/photo brief
is stated.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import tokyo_city_ballet as t

# A faithful, condensed slice of the live page (Japanese kept verbatim). The
# 対象年齢 list and 受講料 list each name the four class types; the scraper joins
# them by name.
PAGE = (
    "東京シティ・バレエ団 presents スペシャルワークショップ2026 "
    "国内外で活躍する教師によるスペシャルワークショップ。 "
    "今回は、定評のあるクラシック・クラスのほか、ピラティス・クラス、コンテンポラリー・クラスを開催します。 "
    "新登場のスペシャル・クラス～スワニルダになりきろう～もあります。 "
    "開催概要 "
    "開催日 2026年8月2日(日)～8月6日(木) "
    "対象年齢 小学3年生～ "
    "※各クラスの詳細な対象年齢は、タイムスケジュールでご確認ください。 "
    "・クラシック・クラス　小学3年生～ "
    "・スペシャル・クラス～スワニルダになりきろう～　小学3年生～中学3年生 "
    "・ピラティス＆クラシック・クラス　中学1年生～ "
    "・コンテンポラリー・クラス　小学3年生～ "
    "会場 東京シティ・バレエ団スタジオ（都営新宿線「大島」駅徒歩15分） "
    "〒136－0073　東京都江東区北砂4丁目40−17 2F TEL：03-6666-0390 "
    "主催 公益財団法人 東京シティ・バレエ団 "
    "タイムテーブル・受講料 8月2日 (日) 8月3日 (月) 8月4日 (火) 8月5日 (水) 8月6日 (木) "
    "クラシック・クラス 10:00〜11:45 志賀育恵（小学3年生～中学1年生） "
    "クラシック・クラス ★ポワント強化 12:15〜14:00 志賀育恵（中学生～高校生） "
    "コンテンポラリー・クラス 14:30〜16:00 五島茉佑子（小学3年生以上） "
    "スペシャル・クラス～スワニルダになりきろう～ 14:30〜16:00 庄田紬香（小学3年生～中学3年生） "
    "申込期間：2026年4月24日（金）受付開始（各クラス定員になり次第締め切り） "
    "受講料 "
    "クラシック・クラス：5,000円／1クラス（税込） "
    "スペシャル・クラス～スワニルダになりきろう～：6,000円／1クラス（税込） "
    "・『コッペリア』第1幕より スワニルダのヴァリエーション（講師：庄田絢香） "
    "ピラティス＆クラシック・クラス：5,000円／1クラス（税込） "
    "コンテンポラリー・クラス：5,000円／1クラス（税込） "
    "講師プロフィール 安達 悦子 Etsuko Adachi 東京シティ・バレエ団芸術監督／理事長 "
)


def test_date_range_explicit_year_span():
    # The closing bound repeats the opening month bare ("…～8月6日").
    assert t._date_range(PAGE) == (date(2026, 8, 2), date(2026, 8, 6))


def test_date_range_absent():
    assert t._date_range("開催日は未定です。") == (None, None)


def test_opens_at_registration_date():
    assert t._opens_at(PAGE) == date(2026, 4, 24)
    # No window stated → no opens-at.
    assert t._opens_at("お申し込みは後日。") is None


def test_sessions_per_class_type_grade_age_bands():
    sessions = t._sessions(PAGE)
    assert [s.label for s in sessions] == [
        "クラシック・クラス",
        "スペシャル・クラス～スワニルダになりきろう～",
        "ピラティス＆クラシック・クラス",
        "コンテンポラリー・クラス",
    ]
    classical, swanilda, pilates, contemporary = sessions
    # 小学3年生～ → open-ended upper bound (8, no max).
    assert classical.age_range == {"min": 8}
    assert classical.notes == "小学3年生～"
    # 小学3年生(8) … 中学3年生(14, +1 end-of-year → 15).
    assert swanilda.age_range == {"min": 8, "max": 15}
    # 中学1年生～ → open from 12.
    assert pilates.age_range == {"min": 12}
    # The last list item must NOT swallow the following 会場 section.
    assert contemporary.age_range == {"min": 8}
    assert contemporary.notes == "小学3年生～"


def test_offering_age_range_open_upper_when_any_class_open():
    sessions = t._sessions(PAGE)
    # Lowest min across classes; upper stays open because some classes are open.
    assert t._offering_age_range(sessions) == {"min": 8}


def test_offering_age_range_bounded_when_all_classes_bounded():
    # If every class is bounded, the Offering takes the widest stated max.
    from intensive_dance.models import Session

    bounded = [
        Session(label="a", ageRange={"min": 8, "max": 13}),
        Session(label="b", ageRange={"min": 10, "max": 15}),
    ]
    assert t._offering_age_range(bounded) == {"min": 8, "max": 15}


def test_prices_per_class_jpy_tax_inclusive_deduped():
    prices = t._prices(PAGE)
    amounts = sorted(p.amount for p in prices)
    # ¥5,000 (shared by classical/pilates/contemporary) + ¥6,000 (Special) — deduped.
    assert amounts == [5000.0, 6000.0]
    for p in prices:
        assert p.currency == "JPY"
        assert p.includes == ["tuition"]
        assert "税込" in (p.label or "")


def test_genres_classical_pointe_repertoire_contemporary():
    # ★ポワント強化 → pointe; スワニルダのヴァリエーション → repertoire; plus contemporary.
    assert t._genres(PAGE) == ["classical", "pointe", "repertoire", "contemporary"]


def test_teachers_named_artistic_director_only():
    (teacher,) = t._teachers(PAGE)
    assert teacher.name == "安達悦子"
    assert teacher.role is not None and "芸術監督" in teacher.role


def test_build_offering_full():
    offering = t._build_offering(_wrap_html(PAGE))
    assert offering is not None
    assert offering.id == "tokyo-city-ballet/special-workshop-2026"
    assert offering.title == "スペシャルワークショップ2026"
    assert offering.schedule.season == "2026"
    assert offering.schedule.start == date(2026, 8, 2)
    assert offering.schedule.end == date(2026, 8, 6)
    assert offering.schedule.timezone == "Asia/Tokyo"
    assert len(offering.schedule.sessions) == 4
    assert offering.age_range == {"min": 8}
    assert offering.location is not None
    assert offering.location.venue == "東京シティ・バレエ団 大島スタジオ"
    assert offering.location.country == "JP"
    # Registration opened; no dated deadline (classes fill then close).
    assert offering.application.status == "open"
    assert offering.application.opens_at == date(2026, 4, 24)
    assert offering.application.deadline is None
    # No audition/photo brief is stated → requirements unknown, not invented.
    assert offering.application.requirements == []


def test_build_offering_no_dated_edition():
    # A page with no parseable date span yields no offering.
    assert t._build_offering(_wrap_html("スペシャルワークショップ 開催日は未定です。")) is None


def _wrap_html(body_text: str) -> str:
    return f"<html><body><div>{body_text}</div></body></html>"
