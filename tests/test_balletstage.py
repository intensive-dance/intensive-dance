"""Unit tests for the BalletStage Summer Intensive scraper (single Wix page).

These pin the regex parsing of the one Summer Intensive page: the two-week date
range (shared trailing month+year), the four participant groups → per-group
sessions and the union age band, the EUR price tiers with their `includes` and
de-duplication of the repeated camp options, the curriculum genres, the
registration status and application deadline, and the fixed audition-form
requirement set (video link + portrait + arabesque). Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import HeadshotReq, PhotosReq, VideoReq
from intensive_dance.scrapers import balletstage as bs

# A compact slice mirroring the live page's structure (groups + prices + terms).
_PAGE_TEXT = (
    "Summer Intensive MasterClass 13 - 25 July 2026 Ljubljana - Slovenia Registrations Open "
    "Classical dance lesson, Pointe technique (Girls), Repertoire, Wave in Motion contemporary "
    "Participant Groups: "
    "Group A 10-13 years old | No Pointe Shoes or 1 year on Pointe "
    "Group B 13-14 years old | More than 2 years on Pointe "
    "Group C 15-17 years old | More than 4 years on Pointe "
    "Group D 18-30 years old | More than 8 years on Pointe "
    "Ballet Shop Apply Now "
    "Admission Prices & Terms "
    "1 Week MasterClass Admission Includes Daily Lunches Euro 1370 including applicable taxes "
    "2 Weeks MasterClass Admission Includes Daily Lunches Euro 2370 including applicable taxes "
    "1 Week Camp and MasterClass Admission Includes Accommodation & Meals "
    "Euro 1960 including applicable taxes "
    "Olga Smirnova Class (For participants without general masterclass admission) "
    "Euro 200 per day (From 21-24 July) "
    "Participants who are professional, semi-professional, or have completed at least one year "
    "of full-time training for a career in dance and are 10 years or older are eligible to apply. "
    "The deadline for applications is 20th June 2026 ."
)


def test_date_range_shared_month_year():
    assert bs._date_range("Summer Intensive MasterClass 13 - 25 July 2026 Ljubljana") == (
        date(2026, 7, 13),
        date(2026, 7, 25),
    )


def test_date_range_absent():
    assert bs._date_range("no dated edition announced yet") == (None, None)


def test_sessions_one_per_group_with_age_and_note():
    sessions = bs._sessions(_PAGE_TEXT, date(2026, 7, 13), date(2026, 7, 25))
    labels = [s.label for s in sessions]
    assert labels == ["Group A", "Group B", "Group C", "Group D"]
    group_a = sessions[0]
    assert group_a.age_range == {"min": 10, "max": 13}
    assert group_a.notes is not None and "No Pointe Shoes" in group_a.notes
    group_d = sessions[3]
    assert group_d.age_range == {"min": 18, "max": 30}
    assert all(s.start == date(2026, 7, 13) and s.end == date(2026, 7, 25) for s in sessions)


def test_age_range_is_union_of_groups():
    assert bs._age_range(_PAGE_TEXT) == {"min": 10, "max": 30}


def test_age_range_absent():
    assert bs._age_range("a two-week summer programme") is None


def test_level_pre_professional_from_eligibility():
    assert bs._level(_PAGE_TEXT) == ["pre-professional"]


def test_prices_tiers_includes_and_perday():
    prices = bs._prices(_PAGE_TEXT)
    by_amount = {p.amount: p for p in prices}
    assert by_amount[1370.0].includes == ["tuition", "meals"]
    assert by_amount[1370.0].currency == "EUR"
    assert by_amount[1960.0].includes == ["tuition", "accommodation", "meals"]
    assert by_amount[200.0].label == "Olga Smirnova class (per day)"


def test_prices_dedupe_repeated_camp_option():
    # The Summer-Camp section repeats the same camp option verbatim; emit it once.
    text = (
        "1 Week Camp and MasterClass Admission Includes Accommodation & Meals "
        "Euro 1960 including applicable taxes "
        "1 Week Camp and MasterClass Admission Includes Accommodation & Meals "
        "Euro 1960 including applicable taxes"
    )
    prices = bs._prices(text)
    assert [p.amount for p in prices] == [1960.0]


def test_genres_from_curriculum():
    assert bs._genres(_PAGE_TEXT) == ["classical", "pointe", "repertoire", "contemporary"]


def test_status_open():
    assert bs._status("13 - 25 July 2026 Ljubljana - Slovenia Registrations Open") == "open"


def test_status_closed():
    assert bs._status("Winter MasterClass Closed 16 - 21 February 2026") == "closed"


def test_status_none_when_unstated():
    assert bs._status("13 - 25 July 2026") is None


def test_deadline():
    assert bs._deadline(_PAGE_TEXT) == date(2026, 6, 20)


def test_deadline_absent():
    assert bs._deadline("apply soon, places are limited") is None


def test_requirements_video_portrait_arabesque():
    reqs = bs._requirements()
    assert {r.type for r in reqs} == {"video", "headshot", "photos"}

    video = next(r for r in reqs if isinstance(r, VideoReq))
    assert video.specificity == "specific"
    assert "variation" in (video.description or "")

    assert any(isinstance(r, HeadshotReq) for r in reqs)

    photos = next(r for r in reqs if isinstance(r, PhotosReq))
    assert photos.specificity == "defined-poses"
    assert photos.poses == ["arabesque"]


def test_build_offering_end_to_end():
    offering = bs._build_offering(f"<html><body>{_PAGE_TEXT}</body></html>")
    assert offering is not None
    assert offering.id == "balletstage/summer-intensive-2026"
    assert offering.title == "Summer Intensive MasterClass 2026"
    assert offering.schedule.start == date(2026, 7, 13)
    assert offering.schedule.end == date(2026, 7, 25)
    assert offering.location is not None
    assert offering.location.city == "Ljubljana"
    assert offering.location.country == "SI"
    assert offering.application.deadline == date(2026, 6, 20)
    assert offering.application.status == "open"
    assert len(offering.schedule.sessions) == 4


def test_build_offering_returns_none_without_dates():
    assert bs._build_offering("<html><body>no dates here</body></html>") is None
