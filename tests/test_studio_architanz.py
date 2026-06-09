"""Unit tests for the Studio ARCHITANZ scraper (Japanese WP post body).

Source-shaped inline rendered HTML only — no network. The fixtures mirror the
live workshop-audition post: the two-school short-term-study workshop (Hamburg
Ballet School + English National Ballet School, Aug 4-5 2025), and a pure
professional-company audition (Dortmund Ballet) that must be rejected as
out-of-scope by the school-workshop filter.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import studio_architanz as a

# A faithful, condensed slice of the live Hamburg/ENBS workshop-audition post body
# (rendered HTML as the WP REST API returns it; Japanese kept verbatim).
HAMBURG_ENBS = (
    "<p><strong>ハンブルク・バレエ学校</strong></p>"
    "<p><strong>イングリッシュ・ナショナル・バレエスクール</strong></p>"
    "<p>2校によるワークショップ・オーディションをアーキタンツにて開催します。</p>"
    "<p>ハンブルク・バレエ学校およびイングリッシュ・ナショナル・バレエスクールへの"
    "<strong>短期留学</strong>に向けてワークショップ・オーディションを開催いたします。</p>"
    "<p>本ワークショップ・オーディションでは、ハンブルク・バレエ団のバレエマスターである"
    "ダミアーノ・ペッテネッラ氏が来日。バレエクラスおよび同バレエ団芸術監督デミス・ヴォルピ氏による"
    "レパートリークラスを指導いたします。</p>"
    "<p><strong>【日時】</strong></p>"
    "<p><strong>2025年8月4日（月）、5日（火）</strong></p>"
    "<p>8月4日（月） 15:15-16:45 バレエクラス / 17:00-18:30 レパートリークラス</p>"
    "<p>【対象年齢】</p>"
    "<p>■短期留学に向けたオーディション審査をご希望される場合</p>"
    "<p>・ハンブルク・バレエ学校：15歳-18歳</p>"
    "<p>・イングリッシュ・ナショナル・バレエスクール：15歳-18歳</p>"
    "<p>■ワークショップとしての参加の場合（オーディション審査をご希望されない場合）</p>"
    "<p>14-18歳</p>"
    "<p>【受講料】</p>"
    "<p>■ 2日間通し（全4クラス）：28,000円（税込）</p>"
    "<p>■ オーディション審査料：7,000円（税込）</p>"
    "<p>【会場】スタジオアーキタンツ　01スタジオ</p>"
    "<p>【定員】50名程度（先着順）</p>"
    "<p>【服装・持ち物】女性：無地レオタード、ピンクタイツ、バレエシューズ、ポアントシューズ。"
    "男女共通：名前の入ったゼッケンを各自でご用意ください。</p>"
    "<p>【お申込み】https://forms.gle/ryut5F8wUJQTtz3VA</p>"
    "<p>【申込み締切】2025年8月1日（金）23:59</p>"
    "<p>【講師】Damiano Pettenella / ダミアーノ・ペッテネッラ ハンブルク・バレエ団 主任バレエマスター "
    "ミラノ・スカラ座バレエ学校にて学び、2000年に卒業後、ミラノ・スカラ座バレエ団に入団。</p>"
    # The 学校情報 blurb describes the SCHOOL's curriculum ("classical ballet AND
    # contemporary dance") — about the school, not this workshop. It must NOT leak a
    # contemporary genre into the offering.
    "<p>==========【学校情報】ハンブルク・バレエ学校｜The School of the Hamburg Ballett "
    "クラシックバレエとコンテンポラリーダンスを、それぞれ専門的に学びながら高いレベルで融合させる"
    "独自のカリキュラムが特徴です。</p>"
)

# A pure professional-company audition — names a Ballett-TEAM (company), no 短期留学
# study placement, no school. Must be rejected by the school-workshop filter.
DORTMUND_COMPANY = (
    "<p>ドルトムントバレエ団／ジュニアカンパニー ワークショップ・オーディション 2025</p>"
    "<p>2025年2月1日（土）・2日（日）に、ドルトムントバレエ団およびジュニアカンパニーの"
    "オーディションをアーキタンツにて開催します。海外カンパニーのオーディションを日本で受けられます。</p>"
    "<p>【申込期限】2025年1月29日（木）必着</p>"
)


def _build():
    return a._build_offering(HAMBURG_ENBS, "https://a-tanz.com/ballet/2025/06/15151738")


def test_filter_accepts_school_workshop():
    assert a._is_school_workshop(HAMBURG_ENBS) is True


def test_filter_rejects_company_audition():
    assert a._is_school_workshop(DORTMUND_COMPANY) is False


def test_pick_edition_skips_company_picks_school():
    posts = [
        {"content": {"rendered": DORTMUND_COMPANY}, "link": "x"},
        {"content": {"rendered": HAMBURG_ENBS}, "link": "y"},
    ]
    picked = a._pick_edition(posts)
    assert picked is not None
    assert picked["link"] == "y"


def test_pick_edition_returns_none_when_no_school_workshop():
    posts = [{"content": {"rendered": DORTMUND_COMPANY}, "link": "x"}]
    assert a._pick_edition(posts) is None


def test_offering_identity_and_dates():
    o = _build()
    assert o is not None
    assert o.id == "studio-architanz/school-workshop-2025"
    assert o.schedule.season == "2025"
    assert o.schedule.start == date(2025, 8, 4)
    assert o.schedule.end == date(2025, 8, 5)
    assert o.schedule.timezone == "Asia/Tokyo"
    # Title names both visiting schools.
    assert "ハンブルク・バレエ学校" in o.title
    assert "イングリッシュ・ナショナル・バレエスクール" in o.title
    assert "2025" in o.title


def test_location():
    o = _build()
    assert o is not None
    assert o.location is not None
    assert o.location.city == "Tokyo"
    assert o.location.country == "JP"
    assert o.location.venue is not None
    assert "スタジオアーキタンツ" in o.location.venue


def test_sessions_split_audition_and_workshop_tracks():
    o = _build()
    assert o is not None
    labels = [s.label for s in o.schedule.sessions]
    # Two per-school audition tracks + one workshop-only track.
    assert any(label is not None and "ハンブルク" in label for label in labels)
    assert any(label is not None and "イングリッシュ" in label for label in labels)
    assert "ワークショップのみ" in labels

    audition = next(
        s for s in o.schedule.sessions if s.label == "オーディション審査（ハンブルク・バレエ学校）"
    )
    assert audition.age_range == {"min": 15, "max": 18}
    workshop = next(s for s in o.schedule.sessions if s.label == "ワークショップのみ")
    assert workshop.age_range == {"min": 14, "max": 18}


def test_offering_age_range_spans_all_tracks():
    o = _build()
    assert o is not None
    assert o.age_range == {"min": 14, "max": 18}


def test_prices_tuition_and_audition_fee():
    o = _build()
    assert o is not None
    amounts = {p.amount for p in o.prices}
    assert 28000.0 in amounts
    assert 7000.0 in amounts
    for p in o.prices:
        assert p.currency == "JPY"
        assert p.includes == ["tuition"]


def test_genres():
    o = _build()
    assert o is not None
    assert "classical" in o.genres
    assert "repertoire" in o.genres
    assert "pointe" in o.genres
    assert "contemporary" not in o.genres


def test_teachers():
    o = _build()
    assert o is not None
    assert len(o.teachers) == 1
    t = o.teachers[0]
    assert t.name == "Damiano Pettenella"
    assert t.role is not None and "バレエマスター" in t.role
    assert any("ハンブルク・バレエ団" in af.organization for af in t.affiliations)


def test_application_deadline_url_and_no_requirements():
    o = _build()
    assert o is not None
    assert o.application.deadline == date(2025, 8, 1)
    assert o.application.url == "https://forms.gle/ryut5F8wUJQTtz3VA"
    # Workshop doubles as an in-person audition; no photo/video brief stated.
    assert o.application.requirements == []
    assert o.application.notes is not None and "短期留学" in o.application.notes


def test_no_dates_yields_none():
    body = "<p>ハンブルク・バレエ学校 短期留学 ワークショップ・オーディション。日程は後日発表。</p>"
    assert a._build_offering(body, "u") is None
