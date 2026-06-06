"""Unit tests for The Tokyo Ballet School scraper (Japanese page).

Source-shaped inline strings only — no network. The fixture mirrors the live
夏休み特別講習会2026 page: a year-less course-date run ("8月6日(木)、…、9日(日)") with
the year only in the title, three classes split by school-grade band + gender,
a folded-in performance viewing, JPY tuition + an optional private-lesson price,
a guest-teacher line, a Peatix booking link, and the application deadline.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import tokyo_ballet_school as t

# A faithful, condensed slice of the live page (Japanese kept verbatim).
PAGE = (
    "【参加者募集！】夏休み特別講習会2026 東京バレエ学校 夏休み特別講習会2026 "
    "～東京バレエ学校がおおくりする4日間の短期集中講習会！～ "
    "2026年の夏は、ゲスト教師に高田茜さん（英国ロイヤル・バレエ団 プリンシパル）を迎え、"
    "舞台芸術を学ぶ時間として東京バレエ団「はじめての白鳥の湖」の鑑賞の機会も！ "
    "◇日程：8月6日(木)、7日(金)、8日(土)、9日(日) "
    "◇場所：東京バレエ学校 スタジオ "
    "◇講師： ゲスト教師：高田茜さん（英国ロイヤル・バレエ団 プリンシパル） 東京バレエ学校教師 "
    "◇クラス： 【ガールズⅡ】小学4年生～中学1年生の女子 【ガールズⅠ】中学2年生～高校3年生の女子 "
    "【ボーイズ】小学5年生～高校3年生の男子 "
    "◇参加条件 ・バレエ歴3年以上であること ・クラスⅠ受講者はポワント必須 "
    "・4日間全てのプログラムに参加できること "
    "◇舞台鑑賞について 公演名：東京バレエ団「はじめてのバレエ白鳥の湖」 日時：8月8日(土) 15:00開演 "
    "◇受講料： 【ガールズⅡ】51,000円（税込み） 【ガールズⅠ】51,000円（税込み） "
    "【ボーイズ】51,000（税込み） "
    "※東京バレエ団「はじめてのバレエ 白鳥の湖」鑑賞チケット費用も含まれています。 "
    "【プライベートレッスン（※希望者のみ）】 30分 6,000円（税込み） "
    "※各クラス先着20名限定とさせていただきますので、お早めにお申込みください。 "
    "◇お申込み： 以下のURLよりお進みください！ https://peatix.com/event/4993363 "
    "◇お申込み締切： 7月20日(月祝) 23:59"
)


def test_year_from_title_stamp():
    assert t._year(PAGE) == 2026
    # The date line is year-less; absent any year stamp we can't resolve it.
    assert t._year("◇日程：8月6日(木)、9日(日)") is None


def test_date_range_year_from_title_first_to_last_day():
    assert t._date_range(PAGE, 2026) == (date(2026, 8, 6), date(2026, 8, 9))


def test_deadline_inherits_title_year():
    assert t._deadline(PAGE, 2026) == date(2026, 7, 20)


def test_apply_url_is_peatix_link():
    assert t._apply_url(PAGE) == "https://peatix.com/event/4993363"


def test_schedule_note_is_the_structured_viewing_not_the_intro_blurb():
    note = t._schedule_note(PAGE)
    assert note is not None
    assert "8月8日(土) 15:00開演" in note
    assert "機会も" not in note  # must not capture the intro blurb


def test_sessions_per_class_grade_age_and_gender():
    sessions = t._sessions(PAGE)
    assert [s.label for s in sessions] == ["ガールズⅡ", "ガールズⅠ", "ボーイズ"]
    g2, g1, boys = sessions
    # 小4(=9)…中1(=12, +1 end-of-year → 13), female.
    assert g2.age_range == {"min": 9, "max": 13}
    assert g2.gender == "female"
    # 中2(=13)…高3(=17, +1 → 18), female; pointe required.
    assert g1.age_range == {"min": 13, "max": 18}
    assert g1.gender == "female"
    # 小5(=10)…高3(=18), male.
    assert boys.age_range == {"min": 10, "max": 18}
    assert boys.gender == "male"
    # Raw grade band kept verbatim.
    assert g2.notes == "小学4年生～中学1年生の女子"


def test_offering_age_range_spans_all_classes():
    sessions = t._sessions(PAGE)
    assert t._offering_age_range(sessions) == {"min": 9, "max": 18}


def test_prices_class_tuition_and_optional_private_lesson():
    prices = t._prices(PAGE)
    tuition, private = prices
    assert (tuition.amount, tuition.currency, tuition.includes) == (51000.0, "JPY", ["tuition"])
    assert "税込" in (tuition.label or "")
    assert tuition.notes is not None and "白鳥の湖" in tuition.notes
    # The private-lesson amount (6,000) must not be mistaken for a class fee.
    assert private.amount == 6000.0
    assert "プライベートレッスン" in (private.label or "")


def test_genres_classical_with_pointe_no_contemporary():
    # ガールズⅠ requires pointe; the 2026 guest is classical (no contemporary class).
    assert t._genres(PAGE) == ["classical", "pointe"]


def test_teachers_named_guest_only():
    (teacher,) = t._teachers(PAGE)
    assert teacher.name == "高田茜"
    assert teacher.role is not None and "英国ロイヤル・バレエ団" in teacher.role


def test_build_offering_full():
    offering = t._build_offering(_wrap_html(PAGE))
    assert offering is not None
    assert offering.id == "tokyo-ballet-school/summer-special-2026"
    assert offering.title == "夏休み特別講習会2026"
    assert offering.schedule.season == "2026"
    assert offering.schedule.start == date(2026, 8, 6)
    assert offering.schedule.end == date(2026, 8, 9)
    assert offering.schedule.timezone == "Asia/Tokyo"
    assert len(offering.schedule.sessions) == 3
    assert offering.age_range == {"min": 9, "max": 18}
    assert offering.location is not None
    assert offering.location.venue == "東京バレエ学校 スタジオ"
    assert offering.location.country == "JP"
    assert offering.application.deadline == date(2026, 7, 20)
    assert offering.application.url == "https://peatix.com/event/4993363"
    # No audition/photo brief is stated → requirements unknown, not invented.
    assert offering.application.requirements == []


def test_build_offering_no_dated_edition():
    # A page with no year stamp anywhere yields no offering.
    assert (
        t._build_offering(_wrap_html("◇日程：8月6日(木)、9日(日) 【ガールズⅡ】小学4年生の女子"))
        is None
    )


def _wrap_html(body_text: str) -> str:
    return f"<html><body><div>{body_text}</div></body></html>"
