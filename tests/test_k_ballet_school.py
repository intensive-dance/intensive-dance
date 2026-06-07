"""Unit tests for the K-Ballet School scraper (summer + winter JP event pages).

These pin the parsing of both the Summer Intensive (夏期特別講習会) and Winter
Intensive (冬期特別講習会) pages: per-course block slicing (two different page
layouts), year-from-header date assembly, JPY fees, venue extraction, age ranges,
and course-scoped genres. Inline JP-shaped strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import k_ballet_school as k

# A trimmed page text mirroring the real DOM after `body.text()` + clean(): the
# header carries the year, each course <h3> opens a program block, and 申込方法
# follows the last course. Kept faithful to the source's Japanese wording.
PAGE_TEXT = (
    "Summer Intensive 2026 ［夏期特別講習会］ "
    "開催日程 2026. 8/2(日)～8/9(日) ＊8/5(水)は休講です "
    "サマーインテンシブ 開講コース プログラム内容 "
    "キッズ：年中～年長対象 楽しさを学ぶ3日間のコースです。 "
    "【日程】 8/2(日)～8/4(火) 3日間 "
    "【会場】 Kバレエ スクール 恵比寿 〒150-0013 東京都渋谷区恵比寿 "
    "【プログラム】 ストレッチ＆バー / ヴァリエーション "
    "【受講料】 34,000円(税込) スケジュールの詳細はこちら ＊キッズは… 申込はこちら "
    "ファウンデーション：小学1～3年生対象 クラシカルバレエクラスと男⼥別ヴァリエーション。 "
    "【日程】 Aコース：8/2(日)～8/4(火) Bコース：8/6(木)～8/9(日) Cコース：8/2(日)～8/9(日) ※8/5(水)は休講 "
    "【会場】 Kバレエ スクール 後楽園 〒112-0002 東京都文京区小石川 "
    "【プログラム】 クラシカルバレエクラス / ヴァリエーション "
    "【受講料】 Aコース：46,500円(税込) Bコース：62,000円(税込) Cコース：102,000円(税込) "
    "スケジュールの詳細はこちら ＊本コースは… 申込はこちら "
    "インターメディエイト：中学生以上対象 ⽬的に合わせた2つのコース。 "
    "【日程】 8/2(日)～8/9(日) ※8/5(水)は休講 "
    "【会場】 Kバレエ スクール 恵比寿 〒150-0013 東京都渋谷区恵比寿 "
    "【プログラム】 バレエクラス ヴァリエーション / レパートリー Girlsポワント コンテンポラリー "
    "パ・ド・ドゥ / マイム / ドラマ "
    "【受講料】 Aコースのみ：163,000円(税込) Aコース＋ソロアッセンブリー参加：200,000円(税込) "
    "Bコース＋ソロアッセンブリー参加：145,000円(税込) スケジュールの詳細はこちら 申込はこちら "
    "お申込方法 下記申込フォームよりお申し込みください。 蔵 健太 校長 ロイヤル・バレエ団に入団。"
)


def test_scrape_emits_one_offering_per_present_course():
    offerings = k._build_offerings(f"<html><body>{PAGE_TEXT}</body></html>")
    # Elementary is absent from this trimmed fixture; the other three are present,
    # each id ending in its course key + season.
    ids = {o.id for o in offerings}
    assert ids == {
        "k-ballet-school/summer-intensive-kids-2026",
        "k-ballet-school/summer-intensive-foundation-2026",
        "k-ballet-school/summer-intensive-intermediate-2026",
    }
    assert all(o.schedule.season == "2026" for o in offerings)


def test_age_range_maps_grade_bands():
    # Grade range, open-topped level, and kindergarten — mapped per the statutory
    # April-entry schedule (the upper bound is one past the top grade's start age).
    assert k._age_range("ファウンデーション：小学1～3年生対象") == {"min": 6, "max": 9}
    assert k._age_range("エレメンタリー：小学4～6年生対象") == {"min": 9, "max": 12}
    assert k._age_range("インターメディエイト：中学生以上対象") == {"min": 12, "max": None}
    assert k._age_range("キッズ：年中～年長対象") == {"min": 4, "max": 6}


def test_age_range_none_when_no_band():
    assert k._age_range("対象の記載なし") is None


def test_year_from_page_header():
    assert k._year("開催日程 2026. 8/2(日)～8/9(日)") == 2026
    assert k._year("no dated edition announced yet") is None


def test_date_range_spans_block_min_to_max():
    # Foundation lists A/B/C windows; the span brackets the earliest start and
    # latest end (full-width ～ separator, year taken from the header).
    block = "【日程】 Aコース：8/2(日)～8/4(火) Bコース：8/6(木)～8/9(日) Cコース：8/2(日)～8/9(日)"
    assert k._date_range(block, 2026) == (date(2026, 8, 2), date(2026, 8, 9))


def test_date_range_single_window():
    assert k._date_range("【日程】 8/2(日)～8/4(火) 3日間", 2026) == (
        date(2026, 8, 2),
        date(2026, 8, 4),
    )


def test_date_range_absent():
    assert k._date_range("no dates here", 2026) == (None, None)


def test_location_reads_per_course_venue():
    loc = k._location("【会場】 Kバレエ スクール 後楽園 〒112-0002 東京都文京区小石川")
    assert loc.venue == "Kバレエ スクール 後楽園"
    assert loc.city == "Tokyo"
    assert loc.country == "JP"


def test_prices_tax_inclusive_jpy_with_subcourse_labels():
    block = (
        "【受講料】 Aコース：46,500円(税込) Bコース：62,000円(税込) Cコース：102,000円(税込) "
        "スケジュールの詳細はこちら"
    )
    prices = k._prices(block)
    assert [(p.amount, p.currency) for p in prices] == [
        (46500.0, "JPY"),
        (62000.0, "JPY"),
        (102000.0, "JPY"),
    ]
    assert prices[0].label == "受講料 Aコース（税込）"
    assert all(p.includes == ["tuition"] for p in prices)


def test_solo_assembly_tier_carries_performance_include():
    block = (
        "【受講料】 Aコースのみ：163,000円(税込) "
        "Aコース＋ソロアッセンブリー参加：200,000円(税込) "
        "Bコース＋ソロアッセンブリー参加：145,000円(税込) スケジュールの詳細はこちら"
    )
    prices = k._prices(block)
    assert prices[0].includes == ["tuition"]
    assert prices[1].includes == ["tuition", "performance"]
    assert prices[2].includes == ["tuition", "performance"]


def test_prices_ignore_numbers_outside_fee_section():
    # A 円 amount in faculty prose must not leak in as a price.
    block = "【受講料】 34,000円(税込) スケジュールの詳細はこちら 蔵 健太 1995年に入学 9,999円のチケット"
    prices = k._prices(block)
    assert [p.amount for p in prices] == [34000.0]


def test_genres_scoped_to_course_block():
    # classical is always present; the discriminating genres attach only where the
    # course's own program lists them (contemporary stays off Kids/Foundation).
    kids = "ストレッチ＆バー / テクニック強化 / ヴァリエーション"
    assert k._genres(kids) == ["classical", "repertoire"]
    intermediate = (
        "バレエクラス ヴァリエーション / レパートリー Girlsポワント コンテンポラリー パ・ド・ドゥ"
    )
    assert k._genres(intermediate) == ["classical", "pointe", "repertoire", "contemporary"]


def test_genres_always_classical():
    assert k._genres("案内のみ") == ["classical"]


def test_dates_note_keeps_raw_window_text():
    block = "【日程】 8/2(日)～8/9(日) ※8/5(水)は休講 【会場】 Kバレエ スクール 吉祥寺"
    assert k._dates_note(block) == "8/2(日)～8/9(日) ※8/5(水)は休講"


# --- winter intensive tests --------------------------------------------------
#
# The winter page uses a table layout: "クラス {Name}" row keys, and plain field
# labels (コース日程 / 会場 / 対象学年 / 受講料) without 【】 brackets. The year
# lives in the "開催日程 2025." overview header; per-course blocks may show
# "2026.12/26" (data-entry error) which _date_range safely ignores.

WINTER_TEXT = (
    "Winter Intensive 2025 ［冬期特別講習会］ "
    "開催日程 2025. 12/26(金)～12/27(土) 2日間 インターメディエイトのみ、12/26(金)～12/29(月) 4日間 "
    "会場 Kバレエ スクール 各校 "
    "クラス キッズ コース日程 2日間 2026.12/26(金)～12/27(土) "
    "会場 Kバレエ スクール 武蔵小杉 〒211-0012 神奈川県川崎市 "
    "対象学年 年中・年長 外部生：バレエ経験1年以上の方 "
    "受講料 22,000円(税込) "
    "プログラム ストレッチ＆バー テクニック強化 ヴァリエーション "
    "クラス ファウンデーション コース日程 2日間 2026.12/26(金)～12/27(土) "
    "会場 Kバレエ スクール 武蔵小杉 〒211-0012 神奈川県川崎市 "
    "対象学年 小学1～3年生 "
    "受講料 25,000円(税込) "
    "プログラム クラシカルバレエクラス テクニッククラス "
    "クラス エレメンタリー コース日程 2日間 2026.12/26(金)～12/27(土) "
    "会場 Kバレエ アカデミー 〒112-0002 東京都文京区 "
    "対象学年 小学4～6年生 "
    "受講料 48,000円(税込) "
    "プログラム バーコーチング クラシカルバレエクラス テクニッククラス "
    "クラス インターメディエイト コース日程 4日間 2026.12/26(金)～12/29(月) "
    "会場 Kバレエ スクール 武蔵小杉 〒211-0012 神奈川県川崎市 "
    "対象学年 中学生以上 "
    "受講料 98,000円(税込) "
    "プログラム バーコーチング クラシカルバレエクラス コンテンポラリー パ・ド・ドゥ "
    "クラス内容紹介 お申込方法"
)


def test_winter_year_from_overview_header():
    # Year is read from "開催日程 2025." even though per-course rows show "2026."
    assert k._year(WINTER_TEXT) == 2025


def test_winter_course_block_slices_correctly():
    block = k._winter_course_block(WINTER_TEXT, k._COURSES_WINTER[0])
    assert block is not None
    assert "クラス キッズ" in block
    assert "クラス ファウンデーション" not in block


def test_winter_date_range_ignores_year_prefix():
    # The per-course rows show "2026.12/26(金)～12/27(土)"; _date_range should
    # ignore the "2026." prefix and use the year 2025 passed from the header.
    block = (
        "クラス キッズ コース日程 2日間 2026.12/26(金)～12/27(土) 会場 Kバレエ スクール 武蔵小杉"
    )
    assert k._date_range(block, 2025) == (date(2025, 12, 26), date(2025, 12, 27))


def test_winter_date_range_intermediate_four_days():
    block = "クラス インターメディエイト コース日程 4日間 2026.12/26(金)～12/29(月)"
    assert k._date_range(block, 2025) == (date(2025, 12, 26), date(2025, 12, 29))


def test_winter_location_musashikosugi():
    block = "会場 Kバレエ スクール 武蔵小杉 〒211-0012 神奈川県川崎市"
    loc = k._winter_location(block)
    assert loc.venue == "Kバレエ スクール 武蔵小杉"
    assert loc.country == "JP"


def test_winter_location_academy():
    block = "会場 Kバレエ アカデミー 〒112-0002 東京都文京区"
    loc = k._winter_location(block)
    assert loc.venue == "Kバレエ アカデミー"


def test_winter_age_range_from_対象学年():
    kids_block = "対象学年 年中・年長 外部生：バレエ経験1年以上の方"
    assert k._winter_age_range(kids_block) == {"min": 4, "max": 6}
    foundation_block = "対象学年 小学1～3年生 受講料"
    assert k._winter_age_range(foundation_block) == {"min": 6, "max": 9}
    intermediate_block = "対象学年 中学生以上 受講料"
    assert k._winter_age_range(intermediate_block) == {"min": 12, "max": None}


def test_winter_prices_single_fee():
    block = "受講料 22,000円(税込) プログラム"
    prices = k._winter_prices(block)
    assert len(prices) == 1
    assert prices[0].amount == 22000.0
    assert prices[0].currency == "JPY"
    assert prices[0].includes == ["tuition"]


def test_winter_genres_intermediate_has_contemporary():
    block = "プログラム バーコーチング クラシカルバレエクラス コンテンポラリー パ・ド・ドゥ"
    assert "contemporary" in k._genres(block)
    kids_block = "プログラム ストレッチ＆バー テクニック強化 ヴァリエーション"
    assert "contemporary" not in k._genres(kids_block)


def test_build_winter_offerings_four_courses():
    url = "https://www.k-ballet.co.jp/school/event/2025winterassembly.html"
    offerings = k._build_winter_offerings(f"<html><body>{WINTER_TEXT}</body></html>", url)
    assert len(offerings) == 4
    ids = {o.id for o in offerings}
    assert ids == {
        "k-ballet-school/winter-intensive-kids-2025",
        "k-ballet-school/winter-intensive-foundation-2025",
        "k-ballet-school/winter-intensive-elementary-2025",
        "k-ballet-school/winter-intensive-intermediate-2025",
    }
    # Verify season and basic date assembly
    for o in offerings:
        assert o.schedule.season == "2025"
    intermediate = next(o for o in offerings if "intermediate" in o.id)
    assert intermediate.schedule.end == date(2025, 12, 29)
    kids = next(o for o in offerings if "kids" in o.id)
    assert kids.schedule.end == date(2025, 12, 27)
    # Venue checks
    kids_loc = kids.location
    assert kids_loc is not None
    assert kids_loc.venue == "Kバレエ スクール 武蔵小杉"
    elem = next(o for o in offerings if "elementary" in o.id)
    elem_loc = elem.location
    assert elem_loc is not None
    assert elem_loc.venue == "Kバレエ アカデミー"


# --- URL discovery: picks the latest (max) when multiple editions are listed ---
#
# The /school/event/ listing can contain links for several past + current
# editions (e.g. 2024winterassembly before 2025winterassembly). _discover_url
# must pick the lexicographically greatest href so older editions don't shadow
# the current one.  We test the selection logic by calling the pure HTMLParser
# step in isolation, bypassing the network fetch.


def test_discover_url_picks_latest_of_multiple_matches():
    listing_html = (
        "<html><body>"
        "<a href='/school/event/2026summerintensive.html'>2026夏</a>"
        "<a href='/school/event/2024winterassembly.html'>2024冬</a>"
        "<a href='/school/event/2025summerintensive.html'>2025夏</a>"
        "<a href='/school/event/2025winterassembly.html'>2025冬</a>"
        "</body></html>"
    )
    assert (
        k._select_url(listing_html, "winterassembly")
        == f"{k.BASE}/school/event/2025winterassembly.html"
    )
