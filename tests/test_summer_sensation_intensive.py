"""Unit tests for the DART Summer Sensation Intensive scraper (Wix, two pages).

These pin the regex parsing of the `/summer-intensive-berlin` page (three August
weeks with the source's year typo normalised, confirmed seven-teacher roster,
contemporary/repertoire genres, three EUR week tiers, CV + specific-video
requirements) and the `/summer-intensive-milan` page (three-day June intensive,
single price, three named teachers, CV + unspecific video, deadline). Inline
strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import CVReq, VideoReq
from intensive_dance.scrapers import summer_sensation_intensive as dart

# The roster names each live in their own <span> on the live (Wix) page, so the
# end-to-end fixture mirrors that — one span per teacher between the intro and the
# "WORKSHOP SCHEDULE" heading. A zero-width space (the Wix trap) is glued into a
# name and a price, and weeks 2 & 3 carry the source's "2025" typo.
_ZWSP = "​"
_HTML = (
    "<html><body>"
    "<span>Summer Sensation Intensive BERLIN</span>"
    "<span>The Summer Sensation Intensive DART Dance Company course will "
    "feature the following teachers:</span>"
    "<span>Olivier Coëffard</span>"
    "<span>Anton Valdbauer</span>"
    "<span>Quentin Roger</span>"
    f"<span>Kinga{_ZWSP} Varga</span>"
    "<span>Zoran Markovic</span>"
    "<span>Luis Martin Oya</span>"
    "<span>Alessandra La Bella</span>"
    "<span>WORKSHOP SCHEDULE</span>"
    "<p>FIRST WEEK: 3rd - 7th August 2026: Monday-Friday MATS EK REPERTOIRE "
    "SECOND WEEK: 10th - 14th August 2025: Monday-Friday JIŘÍ KYLIÁN REPERTOIRE "
    "THIRD WEEK: 17th - 21st August 2025: Monday-Friday "
    "DART DANCE COMPANY REPERTOIRE - Kinga Varga - Artistic Director/DART Dance Company "
    "ALEXANDER EKMAN REPERTOIRE contemporary dance "
    "To apply: Please send your CV a maximum five-minute improvisation video "
    "a maximum ten-minute ballet video uploaded on Youtube WITHOUT PASSWORD "
    "Prices: The prices are including the registration cost! "
    f"1 week - 595 Euros 2 weeks - 995 {_ZWSP}Euros 3 weeks - 1.395 Euros</p>"
    "</body></html>"
)
# The collapsed page text (what most helpers parse), zero-width chars stripped.
_PAGE = dart._collapse(dart._parse(_HTML))


def test_sessions_three_weeks_year_typo_normalised():
    sessions = dart._sessions(_PAGE)
    assert [(s.label, s.start, s.end) for s in sessions] == [
        ("Week 1", date(2026, 8, 3), date(2026, 8, 7)),
        ("Week 2", date(2026, 8, 10), date(2026, 8, 14)),  # source typed 2025
        ("Week 3", date(2026, 8, 17), date(2026, 8, 21)),  # source typed 2025
    ]


def test_schedule_note_flags_typo_only_when_present():
    note = dart._schedule_note(_PAGE, "2026")
    assert note is not None
    assert "2025" in note and "August 2026" in note
    # No typo → no note.
    clean = _PAGE.replace("August 2025", "August 2026")
    assert dart._schedule_note(clean, "2026") is None


def test_teachers_roster_with_director_role():
    spans = dart._spans(dart._parse(_HTML))
    teachers = dart._teachers(spans, _PAGE)
    assert [t.name for t in teachers] == [
        "Olivier Coëffard",
        "Anton Valdbauer",
        "Quentin Roger",
        "Kinga Varga",
        "Zoran Markovic",
        "Luis Martin Oya",
        "Alessandra La Bella",
    ]
    kinga = next(t for t in teachers if t.name == "Kinga Varga")
    assert kinga.role == "Artistic Director"
    assert all(t.role is None for t in teachers if t.name != "Kinga Varga")


def test_genres_contemporary_repertoire_no_classical():
    genres = dart._genres(_PAGE)
    assert "contemporary" in genres
    assert "repertoire" in genres
    assert "classical" not in genres  # ballet video is an entry req, not a class


def test_prices_three_week_tiers():
    prices = dart._prices(_PAGE)
    assert [(p.amount, p.currency, p.label, p.includes) for p in prices] == [
        (595.0, "EUR", "1 week", ["tuition"]),
        (995.0, "EUR", "2 weeks", ["tuition"]),
        (1395.0, "EUR", "3 weeks", ["tuition"]),
    ]
    assert all(p.notes == "Includes the registration cost." for p in prices)


def test_requirements_cv_and_specific_video():
    reqs = dart._requirements(_PAGE)
    assert isinstance(reqs[0], CVReq)
    assert isinstance(reqs[1], VideoReq)
    assert reqs[1].specificity == "specific"
    assert reqs[1].description is not None
    assert "petit allegro" in reqs[1].description


def test_requirements_absent_when_not_stated():
    assert dart._requirements("Train with the company this summer.") == []


def test_build_offering_end_to_end():
    offering = dart._build_offering(_HTML)
    assert offering is not None
    assert offering.id == "dart-dance-company/summer-sensation-intensive-2026"
    assert offering.title == "Summer Sensation Intensive Berlin 2026"
    assert offering.source.provider == "summer-sensation-intensive"
    assert offering.schedule.start == date(2026, 8, 3)
    assert offering.schedule.end == date(2026, 8, 21)
    assert offering.schedule.season == "2026"
    assert offering.location is not None
    assert offering.location.country == "DE"
    assert "Motzener" in (offering.location.venue or "")
    assert len(offering.teachers) == 7
    assert len(offering.prices) == 3
    assert offering.application.url is not None and "docs.google.com" in offering.application.url
    # Not stated on the page → left empty.
    assert offering.age_range is None
    assert offering.level == []


def test_build_offering_none_when_no_dates():
    html = "<html><body><p>The intensive returns next summer. Stay tuned.</p></body></html>"
    assert dart._build_offering(html) is None


# --- Milan page tests --------------------------------------------------------

# Minimal inline fixture mirroring the live /summer-intensive-milan page
# structure (Wix server-rendered, same zero-width-space trap).
_MILAN_HTML = (
    "<html><body>"
    "<p>ITALY SUMMER MASTER INTENSIVE 2026</p>"
    "<p>Join us for an extraordinary opportunity to challenge your limits. "
    "Under the guidance of Kinga Varga, participants will delve into the DART "
    "Dance Company REPERTOIRE. Clyde Emmanuel Archer will lead sessions on "
    "S-E-D SHARON EYAL contemporary repertoire, while Alessandra La Bella will "
    "introduce dancers to MARCO GOECKE's work.</p>"
    "<p>SCHEDULE 15th to 17th June 2026: contemporary and repertoire classes.</p>"
    "<p>Workshop price: 468 EUR</p>"
    "<p>TO APPLY: Please send your CV and a five-minute maximum improvisation "
    "video uploaded on YouTube NO PASSWORD to dartdanceworkshop@gmail.com</p>"
    "<p>APPLICATION DEADLINE: 13th of June 2026</p>"
    "<p>WORKSHOP ADDRESS: Day 1: TEATRO CARCANO, Corso di Porta Romana, 63, "
    "20122, Milan, Italy Day 2 &amp; 3: TEATRO ARCIMBOLDI, Viale dell'Innovazione "
    "20, 20126, Milan, Italy</p>"
    "</body></html>"
)
_MILAN_TEXT = dart._collapse(dart._parse(_MILAN_HTML))


def test_milan_dates_parse():
    start, end = dart._milan_dates(_MILAN_TEXT)
    assert start == date(2026, 6, 15)
    assert end == date(2026, 6, 17)


def test_milan_deadline_parse():
    assert dart._milan_deadline(_MILAN_TEXT) == date(2026, 6, 13)


def test_milan_prices_single_tier():
    prices = dart._milan_prices(_MILAN_TEXT)
    assert len(prices) == 1
    assert prices[0].amount == 468.0
    assert prices[0].currency == "EUR"
    assert prices[0].includes == ["tuition"]


def test_milan_teachers_three_names():
    teachers = dart._milan_teachers(_MILAN_TEXT)
    assert [t.name for t in teachers] == [
        "Kinga Varga",
        "Clyde Emmanuel Archer",
        "Alessandra La Bella",
    ]


def test_milan_requirements_cv_and_unspecific_video():
    reqs = dart._milan_requirements(_MILAN_TEXT)
    assert isinstance(reqs[0], CVReq)
    assert isinstance(reqs[1], VideoReq)
    assert reqs[1].specificity == "unspecific"


def test_build_milan_offering_end_to_end():
    offering = dart._build_milan_offering(_MILAN_HTML)
    assert offering is not None
    assert offering.id == "dart-dance-company/italy-summer-master-intensive-2026"
    assert offering.title == "Italy Summer Master Intensive Milan 2026"
    assert offering.source.provider == "summer-sensation-intensive"
    assert offering.schedule.start == date(2026, 6, 15)
    assert offering.schedule.end == date(2026, 6, 17)
    assert offering.schedule.season == "2026"
    assert offering.location is not None
    assert offering.location.city == "Milan"
    assert offering.location.country == "IT"
    assert len(offering.teachers) == 3
    assert len(offering.prices) == 1
    assert offering.application.deadline == date(2026, 6, 13)
    assert offering.age_range is None


def test_build_milan_offering_none_when_no_dates():
    html = "<html><body><p>Milan intensive — dates coming soon.</p></body></html>"
    assert dart._build_milan_offering(html) is None
