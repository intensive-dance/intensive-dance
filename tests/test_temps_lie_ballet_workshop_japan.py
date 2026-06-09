"""Unit tests for the Temps Lié Ballet Workshop Japan scraper (Japanese, one page,
two city Offerings).

Source-shaped inline strings only — no network. The fixture mirrors the live
`/summer-japan-2026/` page: the year-stamped title, the per-city overview date
lines (Tokyo hyphen-joined "25日-26日-27日", Osaka "12日と13日"), the 開催地 venue
block, the shared three-level age band (上級/プロ open-topped), the per-city JPY
tax-EXCLUSIVE price ladders sliced by "[東京]/[大阪] 受講費用" headers, a shared
private-lesson fee, and the named guest faculty (ballet teacher in both cities,
contemporary teacher per city) + pianists.
"""

from __future__ import annotations

from datetime import date

from intensive_dance import parse
from intensive_dance.scrapers import temps_lie_ballet_workshop_japan as t

# A faithful, condensed slice of the live page (Japanese kept verbatim; the
# builder normalizes full-width digits up front, so the fixture uses ASCII —
# `_fw` mirrors that for helper-level tests).
PAGE = (
    "STAGE DE DANSE A PARIS - TOKYO HOME Summer Japan 2026 "
    "タンリエバレエワークショップ in Japan 2026 開催決定 "
    "パリオペラ座バレエ団 教師 ジル・イゾアール ダンサー・振付家 小尻健太 (東京) "
    "コンテンポラリーダンス講師 太田垣悠 (大阪) "
    "2026年8月25-26-27日 ：東京講習会 2026年8月28日：イゾアール個人レッスン "
    "2026年8月12日〜13日： 大阪講習会＆イゾアール個人レッスン "
    "開催日時 東京 ： 2026年8月25日-26日-27日 / 講習会 2026年8月28日 / プライベートレッスンのみ "
    "大阪 ： 2026年8月12日と13日 / 講習会期間中にプライベートレッスンを行います "
    "開催地 東京 ： 東京バレエ学校 新館内 スタジオ / 東京都目黒区目黒4-25-4 "
    "( https://thetokyoballetschool.com ) "
    "大阪 ： K★バレエスタジオ / 大阪市中央区内本町1-2-15 谷四スクエアビル3F "
    "( https://k-ballet-studio.com ) "
    "プログラム 【バレエクラスレッスン】講師：ジル・イゾアール "
    "[クラス・対象年齢] (年齢は目安です) - 上級/プロ クラス ： 16歳以上 - 高等クラス : 14-16歳 "
    "- 中級クラス : 12-13歳 *大人から始められた方向けのクラスではございません "
    "＊高等クラス以上につきましては、ポワントを履く可能性もありますのでポワントをご持参ください。 "
    "ジル・イゾアールによる個人レッスン ＊ヴァリエーション指導となります "
    "スペシャルゲスト講師 ジル・イゾアール Gil Isoart パリ・オペラ座バレエ団 教師 "
    "パリ国立高等コンセルバトワール 教授 フランス、ニース出身。 "
    "小尻 健太 Kenta Kojiri ダンサー・振付家 （コンテンポラリークラス 担当 / 東京） "
    "太田垣悠 Yu Otagaki コンテンポラリーダンス講師 (コンテンポラリークラス 担当 / 大阪） "
    "リヨン国立高等コンセルヴァトワールを首席で卒業。 "
    "ピアニスト： 榎本真弓（昭和音楽大学 講師 / バレエピアニスト） "
    "圓井晶子（新国立劇場バレエ団 バレエピアニスト） "
    "辻徳子（パリオペラ座バレエ団・パリ国立高等コンセルバトワール 正バレエピアニスト） "
    "開催各クラスの詳細は、以下をご覧ください "
    "[東京] 受講費用 全レベル共通 / バレエクラスレッスン 3回 ¥ 34,500 (税別) / 3クラス "
    "全レベル共通 / バレエクラスレッスン 2回 ¥ 25,000 (税別) / 2クラス "
    "全レベル共通 / バレエクラスレッスン 1回 ¥ 13,500 (税別) / 1クラス "
    "全レベル共通 / コンテンポラリーレッスン 3回 ¥ 22,500 (税別) / 3クラス "
    "全レベル共通 / コンテンポラリーレッスン 2回 ¥ 16,500 (税別) / 2クラス "
    "全レベル共通 / コンテンポラリーレッスン 1回 ¥ 9,000 (税別) / 1クラス "
    "[大阪] 受講費用 全レベル共通 / クラスレッスン 2回 ¥ 23,000 (税別) / 2クラス "
    "全レベル共通 / クラスレッスン 1回 ¥ 13,000 (税別) / 1クラス "
    "全レベル共通 / コンテンポラリーレッスン 2回 ¥ 10,000 (税別) / 2クラス "
    "全レベル共通 / コンテンポラリーレッスン 1回 ¥ 5,750 (税別) / 1クラス "
    "[プライベートレッスン] 受講費用 (東京・大阪共通） "
    "プライベートレッスン / スタジオ代・通訳アシスタント代込み ¥ 19,500 (税別) / 30min "
    "お申込受付中 講習会参加者は先着順で受付いたします プライベートレッスンのみ、お申込みを5月31日まで"
)


def _fw(text: str) -> str:
    # The builder normalizes full-width digits up front; helper-level tests call
    # helpers directly, so the fixture is normalized the same way here.
    return text.translate(parse.FULLWIDTH_DIGITS_TRANS)


def _wrap_html(body_text: str) -> str:
    return f"<html><body><div>{body_text}</div></body></html>"


def test_year_read_from_title_stamp():
    assert t._year(_fw(PAGE)) == 2026
    assert t._year(_fw("no edition here")) is None


def test_date_range_per_city():
    tokyo = t._date_range(_fw(PAGE), t._CITIES[0], 2026)
    osaka = t._date_range(_fw(PAGE), t._CITIES[1], 2026)
    # Tokyo: hyphen-joined "25日-26日-27日" → first and last day of the run.
    assert tokyo == (date(2026, 8, 25), date(2026, 8, 27))
    # Osaka: "12日と13日".
    assert osaka == (date(2026, 8, 12), date(2026, 8, 13))


def test_sessions_three_levels_top_open_ended():
    sessions = t._sessions(_fw(PAGE))
    assert [s.label for s in sessions] == ["上級/プロ クラス", "高等クラス", "中級クラス"]
    top, mid, low = sessions
    assert top.age_range == {"min": 16, "max": None}  # 16歳以上 = open-topped
    assert mid.age_range == {"min": 14, "max": 16}
    assert low.age_range == {"min": 12, "max": 13}
    assert low.notes is not None and "目安" in low.notes


def test_offering_age_range_open_ended_because_top_class_is():
    sessions = t._sessions(_fw(PAGE))
    assert t._offering_age_range(sessions) == {"min": 12, "max": None}


def test_location_venue_and_city_per_record():
    tokyo = t._location(_fw(PAGE), t._CITIES[0])
    assert tokyo.city == "Tokyo" and tokyo.country == "JP"
    assert tokyo.venue == "東京バレエ学校 新館内 スタジオ"
    osaka = t._location(_fw(PAGE), t._CITIES[1])
    assert osaka.city == "Osaka"
    assert osaka.venue == "K★バレエスタジオ"


def test_prices_per_city_do_not_cross():
    tokyo = {p.amount for p in t._prices(_fw(PAGE), t._CITIES[0])}
    osaka = {p.amount for p in t._prices(_fw(PAGE), t._CITIES[1])}
    # Tokyo ballet 3/2/1 + contemporary 3/2/1 + shared private fee.
    assert tokyo == {34500.0, 25000.0, 13500.0, 22500.0, 16500.0, 9000.0, 19500.0}
    # Osaka has a different (cheaper) ladder; the Tokyo 34,500 must NOT leak in.
    assert osaka == {23000.0, 13000.0, 10000.0, 5750.0, 19500.0}
    assert 34500.0 not in osaka


def test_prices_currency_and_includes():
    prices = t._prices(_fw(PAGE), t._CITIES[0])
    assert all(p.currency == "JPY" for p in prices)
    assert all(p.includes == ["tuition"] for p in prices)
    # Tax-exclusive flagged in the label.
    assert all("税別" in (p.label or "") for p in prices)


def test_genres_classical_contemporary_pointe_repertoire():
    assert t._genres(_fw(PAGE), t._CITIES[0]) == [
        "classical",
        "contemporary",
        "pointe",
        "repertoire",
    ]


def test_teachers_ballet_in_both_cities_contemporary_per_city():
    tokyo = t._city_teachers(t._teachers(_fw(PAGE)), t._CITIES[0])
    osaka = t._city_teachers(t._teachers(_fw(PAGE)), t._CITIES[1])
    tnames = [x.name for x in tokyo]
    onames = [x.name for x in osaka]
    # Isoart teaches both cities; Kojiri only Tokyo, Otagaki only Osaka.
    assert "Gil Isoart" in tnames and "Gil Isoart" in onames
    assert "Kenta Kojiri" in tnames and "Kenta Kojiri" not in onames
    assert "Yu Otagaki" in onames and "Yu Otagaki" not in tnames
    # The pianists appear in both.
    assert "榎本真弓" in tnames and "榎本真弓" in onames


def test_isoart_affiliations_captured():
    isoart = next(x for x in t._teachers(_fw(PAGE)) if x.name == "Gil Isoart")
    orgs = [a.organization for a in isoart.affiliations]
    assert "Paris Opéra Ballet" in orgs
    assert any("CNSMDP" in o for o in orgs)
    assert all(a.current for a in isoart.affiliations)


def test_build_offerings_two_cities():
    offerings = t._build_offerings(_wrap_html(PAGE))
    ids = sorted(o.id for o in offerings)
    assert ids == [
        "temps-lie-ballet-workshop-japan/summer-osaka-2026",
        "temps-lie-ballet-workshop-japan/summer-tokyo-2026",
    ]
    tokyo = next(o for o in offerings if o.id.endswith("tokyo-2026"))
    assert tokyo.title == "タンリエバレエワークショップ in Japan 2026（東京）"
    assert tokyo.schedule.season == "2026"
    assert tokyo.schedule.start == date(2026, 8, 25)
    assert tokyo.schedule.end == date(2026, 8, 27)
    assert tokyo.schedule.timezone == "Asia/Tokyo"
    assert len(tokyo.schedule.sessions) == 3
    assert tokyo.age_range == {"min": 12, "max": None}
    assert tokyo.location is not None and tokyo.location.country == "JP"
    assert tokyo.organization.slug == "temps-lie-ballet-workshop-japan"
    # First-come, fills then closes → no dated deadline; status open; no requirements.
    assert tokyo.application.status == "open"
    assert tokyo.application.deadline is None
    assert tokyo.application.requirements == []
    assert tokyo.application.notes is not None and "先着順" in tokyo.application.notes


def test_build_offerings_no_dated_edition():
    # No title-stamp year anywhere → no resolvable edition → nothing emitted.
    assert t._build_offerings(_wrap_html("バレエワークショップ 開催地 東京")) == []
