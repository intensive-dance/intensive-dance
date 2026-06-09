"""Unit tests for the NBA Ballet Company summer-school scraper (two JP sources).

Source-shaped inline strings only — no network. The fixtures mirror the live
edition: the company news post (carrying the title, target ages, curriculum and
the "YYYY.MM.DD" publish stamp that anchors the year) and the rendered Peatix
event body (the machine-readable 開催日時 / 会場+住所 / 対象 / 受講料 / per-day
カリキュラム). Year-less Peatix dates, the school-grade age band, the JPY
tax-inclusive fee and the Tokyo (Shinjuku) venue are exercised.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import nba_ballet_company as n

# A faithful, condensed slice of the live news post (Japanese kept verbatim). The
# publish stamp "2025.05.07" is the only year on the page; the article links out
# to the (image) PDF and the Peatix booking, and states the target band + the
# 4-day duration.
NEWS_HTML = (
    "<html><body><div>"
    "News お知らせ HOME 新着情報 NBA短期集中サマースクール 開催します！ "
    "NBA短期集中サマースクール 開催します！ 2025.05.07 "
    "ＮＢＡバレエ団主催 サマースクール バレエを総合的に学べるサマースクールを開催いたします。 "
    "クラスレッスンに加えてキャラクターダンス、コンテンポラリーダンス、ピラティス等 "
    "4日間で集中的に総合的に学ぶことができます。 対象：小学5年生~高校生まで "
    "【レッスンスケジュール・講師紹介】→ "
    "https://nbaballet.org/wp/wp-content/uploads/2025/05/20250501_summerschool.pdf "
    "【申込受付】→ https://peatix.com/event/4409752/view "
    "皆様のご参加をお待ちいたしております"
    "</div></body></html>"
)

# A faithful slice of the rendered Peatix event body (Markdown via the proxy). The
# date line is year-less; the venue address carries the Shinjuku prefecture+ward.
PEATIX_MD = (
    "# NBAバレエコンクール主催「短期集中サマースクール」 "
    "## Event description "
    "NBAバレエコンクール主催「短期集中サマースクール」開催！ ～NBA Ballet Competition Summer School～ "
    "【開催日時】 7/31（木） ～ 8/3（日） "
    "【会場】 芸能花伝舎 C1スタジオ 〒160-0023 東京都新宿区西新宿6-12-30 "
    "【対象】 小学5年生～高校生 "
    "【受講料】 80,000円（全4日間 税込) "
    "【カリキュラム】 "
    "7/31(木) クラスレッスン・女性向けレパートリー・コンテンポラリーダンス・ピラティス "
    "8/1(金) クラスレッスン・男性向けレパートリー・コンテンポラリーダンス・ピラティス "
    "8/2(土) クラスレッスン・キャラクターダンス・コンテンポラリーダンス・自習時間 "
    "8/3(日) クラスレッスン・キャラクターダンス・コンテンポラリーダンス（発表会）・修了式（ディプロマ授与） "
    "先着順とさせていただきますので、是非お早めにお申込みください。"
)


def test_year_read_from_news_publish_stamp():
    assert n._year("… 2025.05.07 ＮＢＡバレエ団主催 …") == 2025
    # No publish stamp anywhere → no resolvable year.
    assert n._year("ＮＢＡバレエ団主催 サマースクール") is None


def test_date_range_year_less_span_gets_news_year():
    assert n._date_range(PEATIX_MD, 2025) == (date(2025, 7, 31), date(2025, 8, 3))
    # Missing detail (proxy down) → no span.
    assert n._date_range("", 2025) == (None, None)


def test_ages_school_grade_band_to_numeric_range():
    band, rng = n._ages(PEATIX_MD)
    # 小学5 → age 10; 高校生 = through high school → end of 高3 = 18.
    assert rng == {"min": 10, "max": 18}
    assert band is not None and "小学5" in band and "高校" in band


def test_ages_falls_back_to_news_when_peatix_empty():
    # The news post states the same band ("小学5年生~高校生まで").
    band, rng = n._ages("対象：小学5年生~高校生まで クラスレッスンに加えてキャラクターダンス")
    assert rng == {"min": 10, "max": 18}


def test_location_venue_and_tokyo_city_from_address():
    loc = n._location(PEATIX_MD)
    assert loc.country == "JP"
    assert loc.city == "Tokyo"  # 東京都新宿区 → Tokyo
    assert loc.venue is not None and "芸能花伝舎" in loc.venue


def test_prices_single_tax_inclusive_jpy_fee():
    prices = n._prices(PEATIX_MD)
    assert len(prices) == 1
    p = prices[0]
    assert p.amount == 80000.0
    assert p.currency == "JPY"
    assert p.includes == ["tuition"]
    assert p.label is not None and "税込" in p.label


def test_genres_classical_repertoire_character_contemporary_no_pilates():
    # ピラティス is conditioning, not a ballet genre, so it must not appear.
    assert n._genres(PEATIX_MD) == [
        "classical",
        "repertoire",
        "character",
        "contemporary",
    ]


def test_teachers_five_named_with_affiliations():
    names = [t.name for t in n._TEACHERS]
    assert names == ["久保 紘一", "峰岸 千晶", "山田 佳歩", "砂原 伽音", "三崎 彩"]
    assert n._TEACHERS[0].role is not None and "芸術監督" in n._TEACHERS[0].role
    assert n._TEACHERS[1].role is not None and "バレエミストレス" in n._TEACHERS[1].role


def test_build_offering_full():
    offering = n._build_offering(NEWS_HTML, PEATIX_MD)
    assert offering is not None
    assert offering.id == "nba-ballet-company/summer-school-2025"
    assert offering.title == "NBA短期集中サマースクール2025"
    assert offering.organization.slug == "nba-ballet-company"
    assert offering.schedule.season == "2025"
    assert offering.schedule.start == date(2025, 7, 31)
    assert offering.schedule.end == date(2025, 8, 3)
    assert offering.schedule.timezone == "Asia/Tokyo"
    assert offering.schedule.notes is not None and "対象" in offering.schedule.notes
    assert offering.age_range == {"min": 10, "max": 18}
    assert offering.location is not None and offering.location.city == "Tokyo"
    assert {p.amount for p in offering.prices} == {80000.0}
    assert [t.name for t in offering.teachers] == [
        "久保 紘一",
        "峰岸 千晶",
        "山田 佳歩",
        "砂原 伽音",
        "三崎 彩",
    ]
    # First-come enrolment; no audition/photo brief is stated → requirements unknown.
    assert offering.application.requirements == []
    assert offering.application.url == n.PEATIX_URL
    assert offering.application.notes is not None and "先着順" in offering.application.notes


def test_build_offering_no_year_yields_nothing():
    # News body without a publish stamp → no resolvable year → no offering.
    no_year = "<html><body><div>NBA短期集中サマースクール 開催します！</div></body></html>"
    assert n._build_offering(no_year, PEATIX_MD) is None


def test_build_offering_no_detail_yields_nothing():
    # Year resolves from the news post, but the Peatix detail (dates) is missing.
    assert n._build_offering(NEWS_HTML, "") is None
