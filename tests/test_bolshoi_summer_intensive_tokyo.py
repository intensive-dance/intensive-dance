"""Unit tests for the Bolshoi Academy Tokyo Summer Intensive scraper.

Source-shaped inline strings only — no network. The fixture mirrors the live
bilingual (EN + JP) page: the audition-only intro, the "$125" registration fee,
the "AUGUST 17-22, 2026" date span, the two age groups ("09/13" / "14/19+"), the
class list, and the Bolshoi-faculty line.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import VideoReq
from intensive_dance.scrapers import bolshoi_summer_intensive_tokyo as bolshoi

# A faithful, condensed slice of the live page (JP kept verbatim).
PAGE = (
    "HOW TO JOIN OUR SUMMER INTENSIVE PROGRAMS: "
    "❗️OUR SUMMER PROGRAMS ARE BY AUDITION ONLY❗️ "
    "1) FILL OUT THE VIDEO AUDITION FORM OR AUDITION IN-PERSON "
    "2) PAY THE AUDITION FEE 3) SUBMIT YOUR VIDEO "
    "IF ACCEPTED, YOU WILL RECEIVE AN OFFICIAL ACCEPTANCE LETTER. "
    "Video auditions and applications are accepted ビデオオーディションと、サマーインテンシブの申込みは受付中です。 "
    "Registration Fee: $125 登録料：125ドル "
    "Upon Registration Non-Refundable 登録料は返金できません "
    "Bolshoi Academy Tokyo Summer Intensive 2024 "
    "AUGUST 17-22, 2026 2026 年 8 月 17 ～ 22 日 "
    "WITH FULL TIME TEACHERS OF THE BOLSHOI ACADEMY ボリショイバレエアカデミーの常勤教師による指導 "
    "Age groups 09/13 14/19+ "
    "Classes クラス "
    "Ballet Technique, Pointe, Repertoire, Character Dance, and Bolshoi stretch class "
    "バレエテクニック、ポアント、レパートリー、キャラクターダンス、ボリショイ式ストレッチ "
    "Get in touch russianballetinternational@gmail.com"
)


def test_date_range_english_span_with_year():
    assert bolshoi._date_range(PAGE) == (date(2026, 8, 17), date(2026, 8, 22))


def test_date_range_absent():
    assert bolshoi._date_range("Dates to be announced.") == (None, None)


def test_sessions_two_age_bands_open_ended_high():
    sessions = bolshoi._sessions(PAGE)
    assert [s.age_range for s in sessions] == [
        {"min": 9, "max": 13},
        {"min": 14},  # "19+" is open-ended → only a min bound
    ]
    assert [s.label for s in sessions] == ["Ages 9–13", "Ages 14–19+"]
    # Raw band token kept verbatim in notes.
    assert sessions[0].notes == "09/13" and sessions[1].notes == "14/19+"


def test_age_block_does_not_leak_fee_or_classes():
    block = bolshoi._age_block(PAGE)
    # The $125 fee and the class list sit outside the Age-groups block.
    assert "09/13" in block and "14/19+" in block
    assert "125" not in block and "Ballet Technique" not in block


def test_offering_age_range_spans_bands_open_upper():
    sessions = bolshoi._sessions(PAGE)
    # Lowest min across bands; no max because one band is open-ended.
    assert bolshoi._offering_age_range(sessions) == {"min": 9}


def test_prices_usd_registration_fee_not_tuition():
    (price,) = bolshoi._prices(PAGE)
    assert (price.amount, price.currency) == (125.0, "USD")
    assert price.includes == []  # a registration fee, not tuition
    assert "Non-refundable" in (price.notes or "")


def test_genres_from_class_list():
    assert bolshoi._genres(PAGE) == ["classical", "pointe", "repertoire", "character"]


def test_teachers_bolshoi_faculty_affiliation():
    (teacher,) = bolshoi._teachers(PAGE)
    assert teacher.name == "Bolshoi Ballet Academy faculty"
    (aff,) = teacher.affiliations
    assert aff.organization == "Bolshoi Ballet Academy"
    assert aff.slug == "bolshoi-ballet-academy"
    assert aff.current is True


def test_requirements_video_unspecific():
    (req,) = bolshoi._requirements(PAGE)
    assert isinstance(req, VideoReq)
    assert req.specificity == "unspecific"


def test_build_offering_full():
    offering = bolshoi._build_offering(_wrap_html(PAGE))
    assert offering is not None
    assert offering.id == "bolshoi-summer-intensive-tokyo/summer-intensive-2026"
    assert offering.title == "Bolshoi Academy Tokyo Summer Intensive 2026"
    assert offering.source.provider == "bolshoi-summer-intensive-tokyo"
    # The running org is the local host, not the Moscow academy.
    assert offering.organization.name == "Russian Ballet International"
    assert offering.organization.country == "JP"
    assert offering.schedule.start == date(2026, 8, 17)
    assert offering.schedule.end == date(2026, 8, 22)
    assert offering.schedule.season == "2026"
    assert offering.schedule.timezone == "Asia/Tokyo"
    assert len(offering.schedule.sessions) == 2
    assert offering.age_range == {"min": 9}
    assert offering.location is not None
    assert offering.location.city == "Tokyo"
    assert offering.location.country == "JP"
    assert offering.genres == ["classical", "pointe", "repertoire", "character"]
    assert [p.amount for p in offering.prices] == [125.0]
    assert [r.type for r in offering.application.requirements] == ["video"]
    assert "Bolshoi" in (offering.schedule.notes or "")


def test_build_offering_no_dated_edition():
    assert bolshoi._build_offering(_wrap_html("Dates to be announced. Age groups 09/13")) is None


def _wrap_html(body_text: str) -> str:
    return f"<html><body><div>{body_text}</div></body></html>"
