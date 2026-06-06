"""Unit tests for the D&D Masterclass Japan scraper (Japanese, two city pages).

Source-shaped inline strings only — no network. The fixtures mirror the live
18th-edition Tokyo and Osaka pages: full-width-digit, year-less course-date lines
with an extra open-day line, two age groups (12–15 / 16+ open-ended), the JPY
price ladder (all 税込), the founder + RBS-guest + city-pianist faculty, and the
year carried only by the application-deadline rows.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import dd_masterclass_japan as d

# A faithful, condensed slice of the live Tokyo page (full-width digits kept, as
# the live page serves them; Japanese kept verbatim).
TOKYO = (
    "ホーム 18th TOKYO TOKYO 今回で18回目を迎えるマスタークラスは、東京・大阪の二都市開催となります。 "
    "主催デイヴィット・マッカテリの母校、The Royal Ballet Schoolよりヴァレリ・ヒリストフ先生を招集し開催！ "
    "伝統あるThe Royal Ballet Schoolのクラスをこの夏は日本で受講してみませんか？ "
    "ヨーロッパ名門バレエ学校への短期スカラシップ留学権、国際コンクール参加権、 "
    "就職活動を目指す方にはバレエ団合同オーディションである グランドオーディション参加権 "
    "などの様々なチャンスを皆さんにお届けいたします。 "
    "Teachers デヴィッド・マッカテリ（David Makhateli） 英国ロイヤルバレエ団プリンシパル。「D&D ArtProductions」の創設者。 "
    "特別講師 ヴァレリ・ヒリストフ（Valeri Hristov） The Royal Ballet Schoolのアーティスティック・ティーチャー。 "
    "Pianist 江藤 勝己 (Katsumi Etoh) クラシックバレエを学ぶ。 "
    "Schedule Group A １２歳から１５歳（4年以上のバレエ経験者） Group B １６歳から "
    "※Group Aは通訳付きクラス。 "
    "７月２４日（金）から２６日（日） Group A 14:00 - 15:30 Ballet Class /15:40 - 16:55 Variation, Pointe class "
    "①プライベートレッスン 17:00 - 18:00 Group B 18:10 - 19:40 Ballet Class/ 19:50 - 21:05 Variation, Pointe class "
    "②プライベートレッスン 21:10 - 22:10 ７月２７日（月） Group A 10:00 - 11:45 Open day (warm up class and Variation) "
    "Group B 12:00 - 13:45 Open day "
    "Prices 早割料金 4日間 92,000円 2026年6月20日申請分まで 通常料金 4日間 97,000円 2026年7月10日申請分まで "
    "通常料金 １日受講（オーディション不可） 30,000円 通常料金 プライベートレッスン／15分 15,000円 スタジオ代金込み "
    "特別料金 第16回及び17回マスタークラス受講者割引 87,000円 2026年6月20日申請分まで ※ 全て税込価格です。 "
    "Location Studio H （アッシュ） 住所：〒150-0013 東京都渋谷区恵比寿2-17-22 最寄り駅： JR恵比寿駅から徒歩約8～10分"
)

# Osaka mirrors the same template — different dates, venue, fees and pianist.
OSAKA = (
    "ホーム 18th OSAKA OSAKA 今回で18回目を迎えるマスタークラスは、東京・大阪の二都市開催となります。 "
    "ヨーロッパ名門バレエ学校への短期スカラシップ留学権、国際コンクール参加権、 "
    "就職活動を目指す方にはバレエ団合同オーディションである グランドオーディション参加権 "
    "などの様々なチャンスを皆さんにお届けいたします。 "
    "Teachers デヴィッド・マッカテリ（David Makhateli） 「D&D ArtProductions」の創設者。 "
    "特別講師 ヴァレリ・ヒリストフ（Valeri Hristov） The Royal Ballet Schoolのアーティスティック・ティーチャー。 "
    "Pianist 山本 規子 (Noriko Yamamoto) 武蔵野音楽大学卒業。 "
    "Schedule Group A １２歳から１５歳（4年以上のバレエ経験者） Group B １６歳から "
    "７月２８日（火）から２９日（水） Group A 14:00 - 15:30 Ballet Class /15:40 - 16:55 Variation, Pointe class "
    "①プライベートレッスン 17:00 - 18:00 Group B 18:10 - 19:40 Ballet Class/ 19:50 - 21:05 Variation, Pointe class "
    "②プライベートレッスン 21:10 - 22:10 ７月３０日（木） Group A 10:00 - 11:45 Open day (warm up class and Variation) "
    "Prices 早割料金 ３日間 67,000円 2026年6月20日申請分まで 通常料金 ３日間 72,000円 2026年7月10日申請分まで "
    "通常料金 １日受講 30,000円 オーディション参加不可 通常料金 プライベートレッスン 15,000円 スタジオ代金込み "
    "特別料金 第1６回及び17回マスタークラス受講者割引 62,000円 2026年6月20日申請分まで ※ 全て税込価格です。 "
    "Location Garage Art Space 住所：〒577-0045 大阪府東大阪市西堤本通３丁目６−２３ →大阪市営地下鉄・高井田駅 徒歩１０分"
)


def _fw(text: str) -> str:
    # The builder normalizes full-width digits up front; the unit-helper tests
    # call helpers directly, so we normalize the fixture the same way here.
    return text.translate(d._FW)


def test_year_read_from_deadline_rows_not_the_dateline():
    assert d._year(_fw(TOKYO)) == 2026
    # The date line itself is year-less; with no deadline year, we can't resolve.
    assert d._year(_fw("７月２４日（金）から２６日（日）")) is None


def test_date_range_open_day_extends_past_the_kara_close():
    # Tokyo span closes at 26日 but the open day (27日) is the real end.
    assert d._date_range(_fw(TOKYO), 2026) == (date(2026, 7, 24), date(2026, 7, 27))
    assert d._date_range(_fw(OSAKA), 2026) == (date(2026, 7, 28), date(2026, 7, 30))


def test_deadline_is_the_earliest_application_cutoff():
    assert d._deadline(_fw(TOKYO), 2026) == date(2026, 6, 20)


def test_sessions_two_groups_group_b_open_ended():
    sessions = d._sessions(_fw(TOKYO))
    assert [s.label for s in sessions] == ["Group A", "Group B"]
    a, b = sessions
    assert a.age_range == {"min": 12, "max": 15}
    assert b.age_range == {"min": 16, "max": None}  # 16歳から = open-ended
    assert a.notes is not None and "4年以上" in a.notes


def test_offering_age_range_open_ended_when_a_group_is():
    sessions = d._sessions(_fw(TOKYO))
    assert d._offering_age_range(sessions) == {"min": 12, "max": None}


def test_prices_full_ladder_all_tax_inclusive():
    prices = d._prices(_fw(TOKYO))
    by_amount = {p.amount for p in prices}
    assert by_amount == {92000.0, 97000.0, 30000.0, 15000.0, 87000.0}
    assert all(p.currency == "JPY" for p in prices)
    assert all(p.includes == ["tuition"] for p in prices)


def test_private_lesson_price_not_eaten_by_minutes_token():
    # Osaka writes "プライベートレッスン 15,000円" (no "／15分"); the 15 must NOT be
    # mistaken for a minutes count that swallows the amount's leading digits.
    private = [p for p in d._prices(_fw(OSAKA)) if "プライベート" in (p.label or "")]
    assert [p.amount for p in private] == [15000.0]


def test_genres_classical_pointe_repertoire_no_contemporary():
    assert d._genres(_fw(TOKYO)) == ["classical", "pointe", "repertoire"]


def test_teachers_founder_guest_and_city_pianist():
    teachers = d._teachers(_fw(TOKYO))
    names = [t.name for t in teachers]
    assert names == ["David Makhateli", "Valeri Hristov", "Katsumi Etoh"]
    hristov = teachers[1]
    assert hristov.role is not None and "Royal Ballet School" in hristov.role
    # Osaka carries a different pianist.
    assert d._teachers(_fw(OSAKA))[2].name == "Noriko Yamamoto"


def test_location_venue_and_city_per_page():
    tokyo = d._location(_fw(TOKYO), d._CITIES[0])
    assert tokyo.city == "Tokyo" and tokyo.country == "JP"
    assert tokyo.venue is not None and "Studio H" in tokyo.venue
    osaka = d._location(_fw(OSAKA), d._CITIES[1])
    assert osaka.city == "Osaka"
    assert osaka.venue == "Garage Art Space"


def test_build_offering_tokyo_full():
    offering = d._build_offering(_wrap_html(TOKYO), d._CITIES[0])
    assert offering is not None
    assert offering.id == "dd-masterclass-japan/18th-tokyo-2026"
    assert offering.title == "18th D&D Masterclass 東京 2026"
    assert offering.schedule.season == "2026"
    assert offering.schedule.start == date(2026, 7, 24)
    assert offering.schedule.end == date(2026, 7, 27)
    assert offering.schedule.timezone == "Asia/Tokyo"
    assert len(offering.schedule.sessions) == 2
    assert offering.age_range == {"min": 12, "max": None}
    assert offering.location is not None and offering.location.country == "JP"
    assert offering.application.deadline == date(2026, 6, 20)
    assert offering.application.url == d._CITIES[0].page
    # The masterclass doubles as a scholarship/audition route, but no entry photo/
    # video brief is stated → requirements unknown, not invented.
    assert offering.application.requirements == []
    assert offering.application.notes is not None and "スカラシップ" in offering.application.notes


def test_build_offering_osaka_distinct_edition():
    offering = d._build_offering(_wrap_html(OSAKA), d._CITIES[1])
    assert offering is not None
    assert offering.id == "dd-masterclass-japan/18th-osaka-2026"
    assert offering.schedule.start == date(2026, 7, 28)
    assert offering.schedule.end == date(2026, 7, 30)
    assert {p.amount for p in offering.prices} == {67000.0, 72000.0, 30000.0, 15000.0, 62000.0}


def test_build_offering_no_dated_edition():
    # No deadline-year stamp anywhere → no resolvable year → no offering.
    assert (
        d._build_offering(
            _wrap_html("Group A １２歳から１５歳 ７月２４日（金）から２６日（日）"), d._CITIES[0]
        )
        is None
    )


def _wrap_html(body_text: str) -> str:
    return f"<html><body><div>{body_text}</div></body></html>"
