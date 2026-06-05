"""Unit tests for the Helsinki International Ballet Competition scraper.

These pin the parsing of the two `/en/competition/*` pages: the edition label
and headline date span, the three age divisions → sessions, the spanning age
range, classical+contemporary genres, the €100/€250 fees, the application
window → `closed` status with a `video`/`specific` requirement, and the
jury-President teacher. Also pins the "end date == today is NOT dropped" rule
and the past-edition drop. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import helsinki_international_ballet_competition as hibc

_INFO = (
    "Competition Information 28.5.–5.6.2026 The 10th Helsinki International Ballet "
    "Competition will be held at the Finnish National Opera and Ballet from May 28 "
    "to June 5, 2026. The competition program consists of both classical and "
    "contemporary repertoire. In Round I all competitors present classical "
    "variations and in Round II a contemporary piece. The application period for "
    "the competition is 1.11.2025–31.1.2026. Competition Categories HIBC 2026 has "
    "three divisions: Juniors (ages 15 to 18) Young Professionals (ages 19 to 21) "
    "Seniors (ages 22 to 25). Javier Torres, the Artistic Director of the Finnish "
    "National Ballet, is the President of the HIBC Jury."
)
_RULES = (
    "Competitors shall apply for the competition using the registration form on the "
    "website (www.ibchelsinki.fi) 1.11.2025– 31.1.2026. A dancer applying for the "
    "competition must perform alone in the video submitted for the video selection. "
    "The participation fee for the competition’s video qualification is 100€, which "
    "must be paid in connection with the registration. The participation fee for the "
    "competition is 250€, which is paid by the competitors who have been accepted "
    "from the video qualification."
)

# After the application window (and on/after the edition's end date).
_AFTER = date(2026, 6, 5)


def test_edition_title_and_dates():
    o = hibc._build_offering(_INFO, _RULES, _AFTER)
    assert o is not None
    assert o.title == "10th Helsinki International Ballet Competition"
    assert o.kind == "competition"
    assert o.schedule.start == date(2026, 5, 28)
    assert o.schedule.end == date(2026, 6, 5)
    assert o.schedule.season == "2026"


def test_sessions_are_the_three_divisions():
    sessions = hibc._sessions(_INFO)
    assert [(s.label, s.age_range) for s in sessions] == [
        ("Juniors", {"min": 15, "max": 18}),
        ("Young Professionals", {"min": 19, "max": 21}),
        ("Seniors", {"min": 22, "max": 25}),
    ]
    assert hibc._age_range(sessions) == {"min": 15, "max": 25}


def test_genres_classical_and_contemporary():
    assert set(hibc._genres(_INFO)) >= {"classical", "contemporary"}


def test_prices_two_fees():
    prices = hibc._prices(_RULES)
    amounts = {p.amount for p in prices}
    assert amounts == {100.0, 250.0}
    assert all(p.currency == "EUR" for p in prices)


def test_application_window_closed_with_video_requirement():
    app = hibc._application(_RULES, _AFTER)
    assert app.status == "closed"
    assert app.opens_at == date(2025, 11, 1)
    assert app.deadline == date(2026, 1, 31)
    assert len(app.requirements) == 1
    req = app.requirements[0]
    assert req.type == "video"
    assert getattr(req, "specificity") == "specific"


def test_application_open_during_window():
    app = hibc._application(_RULES, date(2025, 12, 1))
    assert app.status == "open"


def test_teacher_is_jury_president():
    teachers = hibc._teachers(_INFO)
    assert [t.name for t in teachers] == ["Javier Torres"]
    assert teachers[0].role == "Jury President"


def test_end_date_today_is_not_dropped():
    # past = end < today; today == end must still be emitted.
    o = hibc._build_offering(_INFO, _RULES, date(2026, 6, 5))
    assert o is not None


def test_past_edition_is_dropped():
    assert hibc._build_offering(_INFO, _RULES, date(2026, 6, 6)) is None
