"""Unit tests for the Norwegian National Ballet summer-course scraper.

These pin the prose parsing of the operaen.no article: the DD.MM.YY date range,
the bounded age range, curriculum-scoped genres, the NOK course fee (tuition +
meals, accommodation/travel excluded), the application deadline, and the
`specific` video requirement. They also pin the two discovery guards — the
heading must be the summer course, and an already-finished edition is dropped.
Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import norwegian_national_ballet as nnb

# Mirrors the real article body (EN), trimmed to the load-bearing sentences.
_TEXT = (
    "Norwegian National Ballet's Summer Course 2026 "
    "The course is aimed at classical ballet students and is suitable for dancers "
    "from 10 to 19 of all nationalities and will take place 22.06.26 – 27.06.26 in the "
    "Oslo Opera House The pupils will receive instruction in classical ballet, modern "
    "ballet, variations/repertoire, basic training as well as lectures with dancers. "
    "The course costs NOK 2600 and includes tuition, lunch, and fruit every day. "
    "Students must cover the costs of accommodation and travel during the summer course. "
    "The closing date for applications is: 23.02.2026 "
    "Please include a link to a short video that includes: Tendu & adagio exercise in "
    "centre Piroutte exercise Petit allegro exercise & grand allegro exercise. "
    "Applicants from Wilhelmsen Akademiet, KHIO og Ballettskolen do not need to send a "
    "video. Applicants will receive a response from us by 20.03.2026"
)


def _html(title: str = "Norwegian National Ballet's Summer Course 2026") -> str:
    return f"<html><body><h1>{title}</h1><div>{_TEXT}</div></body></html>"


def test_dates_two_digit_year():
    assert nnb._dates(_TEXT) == (date(2026, 6, 22), date(2026, 6, 27))


def test_age_range_bounded():
    assert nnb._age_range(_TEXT) == {"min": 10, "max": 19}


def test_genres_scoped_to_curriculum():
    assert nnb._genres(_TEXT) == ["classical", "contemporary", "repertoire"]


def test_prices_fee_includes_tuition_and_meals_only():
    (price,) = nnb._prices(_TEXT)
    assert price.amount == 2600.0
    assert price.currency == "NOK"
    assert price.includes == ["tuition", "meals"]  # accommodation/travel excluded


def test_deadline():
    assert nnb._deadline(_TEXT) == date(2026, 2, 23)


def test_video_requirement_is_specific():
    (req,) = nnb._requirements(_TEXT)
    assert req.type == "video"
    assert req.specificity == "specific"


def test_build_offering_happy_path():
    offering = nnb._build_offering(
        _html(), nnb.ARTICLE.format(base=nnb.BASE, year=2026), date(2026, 6, 1)
    )
    assert offering is not None
    assert offering.id == "norwegian-national-ballet/summer-course-2026"
    assert offering.schedule.season == "2026"
    assert offering.location is not None
    assert offering.location.venue == "Oslo Opera House"
    assert offering.application.url == "https://forms.office.com/e/tXASbXnU6t"


def test_non_summer_course_article_rejected():
    html = _html(title="Norwegian National Ballet's Autumn Gala 2026")
    assert nnb._build_offering(html, "https://x/", date(2026, 6, 1)) is None


def test_finished_edition_dropped():
    # end (27.06.26) < today → drop, even though the page still resolves.
    assert nnb._build_offering(_html(), "https://x/", date(2026, 7, 1)) is None
