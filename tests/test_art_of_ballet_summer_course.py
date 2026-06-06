"""Unit tests for the ART of – Ballet Summer Course scraper (Zürich + Madrid).

These pin the regex parsing of the static PHP pages: the landing-page date range
(one trailing year, ordinal suffixes), the minimum-age floor, the venue, the
two-tier Complete Course fee (standard tier only, in the edition's currency), the
deadline, the Education-Plan curriculum genres, the photo audition requirements
with their named full-body poses, and the per-city faculty roster (HTML entities
decoded). Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import HeadshotReq, PhotosReq
from intensive_dance.scrapers import art_of_ballet_summer_course as art


def test_date_range_zurich():
    assert art._date_range("ZURICH SUMMER 3rd - 15th August 2026 WINTER") == (
        date(2026, 8, 3),
        date(2026, 8, 15),
    )


def test_date_range_madrid():
    assert art._date_range("BALLET SUMMER COURSE 13th - 25th July 2026 Train in Madrid") == (
        date(2026, 7, 13),
        date(2026, 7, 25),
    )


def test_date_range_absent():
    assert art._date_range("Winter Coming soon!") == (None, None)


def test_age_range_floor_only():
    text = "The minimum age to take part in our Summer or Winter Course in Zurich is 10 years."
    assert art._age_range(text) == {"min": 10}


def test_age_range_madrid():
    assert art._age_range("The minimum age … is 14 years .") == {"min": 14}


def test_age_range_absent():
    assert art._age_range("no stated age floor") is None


def test_venue_zurich():
    text = "Course location TANZWERK 101 Pfingstweidstrasse 101, 8005 Zürich, Switzerland"
    assert art._venue(text) == "TANZWERK 101"


def test_venue_madrid_quoted_name():
    text = (
        'Course location Conservatorio Superior de Danza "María de Ávila" '
        "Calle del General Ricardos 177, 28025 Madrid, Spain"
    )
    assert art._venue(text) == 'Conservatorio Superior de Danza "María de Ávila"'


def test_prices_standard_tier_only_in_currency():
    # The page lists the Complete Course first, then a discounted professional tier;
    # only the first week/two-week pair (the standard fee) is emitted.
    text = (
        "COURSE OPTIONS COMPLETE COURSE One week: 700 CHF Two weeks: 1200 CHF "
        "PROFESSIONAL DANCERS Complete Course One week: 500 CHF Two weeks: 850 CHF "
        "PERSONAL COACHING One 30 min. class: 60 CHF"
    )
    prices = art._prices(text, "CHF")
    assert [(p.amount, p.currency, p.label, p.includes) for p in prices] == [
        (700.0, "CHF", "Complete Course — one week", ["tuition"]),
        (1200.0, "CHF", "Complete Course — two weeks", ["tuition"]),
    ]


def test_prices_madrid_euro():
    text = "COMPLETE COURSE One week: 700 Euro Two weeks: 1200 Euro"
    prices = art._prices(text, "EUR")
    assert [(p.amount, p.currency) for p in prices] == [(700.0, "EUR"), (1200.0, "EUR")]


def test_deadline_madrid():
    assert art._deadline("Application Deadline: July 3rd, 2026") == date(2026, 7, 3)


def test_deadline_zurich_summer_specific():
    text = (
        "Application deadline for ART of - Ballet Winter Course Zurich is December 20th, 2025. "
        "Application deadline for ART of - Ballet Summer Course Zurich is July 28th, 2026."
    )
    assert art._deadline(text) == date(2026, 7, 28)


def test_deadline_absent():
    assert art._deadline("no deadline here") is None


def test_genres_from_education_plan():
    text = (
        "WILLIAM FORSYTHE IMPROVISATION TECHNOLOGIES CLASSICAL BALLET POINTE CLASSES "
        "REPERTOIRE CLASSES Classical and neo -classical repertoire classes. "
        "MEN AND WOMEN TECHNIQUE"
    )
    assert art._genres(text) == [
        "classical",
        "pointe",
        "repertoire",
        "neoclassical",
        "contemporary",
    ]


def test_genres_default_classical():
    assert art._genres("an unstructured blurb with no curriculum headings") == ["classical"]


def test_requirements_photo_audition_with_named_poses():
    text = (
        "Send us your filled in application form along with two full body shots in a dance "
        "position in dance attire (example: 1st arabesque 90°, sauté - 2nd feet position) "
        "and your portrait picture."
    )
    reqs = art._requirements(text)
    assert {r.type for r in reqs} == {"headshot", "photos"}
    assert any(isinstance(r, HeadshotReq) for r in reqs)
    photos = next(r for r in reqs if isinstance(r, PhotosReq))
    assert photos.specificity == "defined-poses"
    assert photos.poses == ["1st arabesque 90°", "sauté - 2nd feet position"]


def test_requirements_empty_when_unstated():
    assert art._requirements("no audition material described") == []


_TEACHERS_HTML = (
    "<p><strong>LEANNE BENJAMIN</strong></p>"
    "<p><em><strong>Former Artistic Director of Queensland Ballet "
    "&amp; Former Principal Dancer of the Royal Ballet&nbsp;</strong></em></p>"
    "<p>Long bio paragraph that is not a role line.</p>"
    "<p><strong>OLEG KLYMYUK</strong></p>"
    "<p><em><strong>Ballet Teacher &amp; Director of ART of</strong></em></p>"
)


def test_teachers_parsed_with_decoded_entities():
    teachers = art._teachers(_TEACHERS_HTML)
    assert [(t.name, t.role) for t in teachers] == [
        (
            "Leanne Benjamin",
            "Former Artistic Director of Queensland Ballet & Former Principal Dancer of the Royal Ballet",
        ),
        ("Oleg Klymyuk", "Ballet Teacher & Director of ART of"),
    ]


def test_teachers_empty_when_no_blocks():
    assert art._teachers("<p>just some prose, no teacher blocks</p>") == []


def test_build_offering_zurich_end_to_end():
    landing = "ZURICH SUMMER 3rd - 15th August 2026"
    general = (
        "Course location TANZWERK 101 Pfingstweidstrasse 101, 8005 Zürich, Switzerland "
        "The minimum age to take part in our Summer or Winter Course in Zurich is 10 years. "
        "Application deadline for ART of - Ballet Summer Course Zurich is July 28th, 2026. "
        "COMPLETE COURSE One week: 700 CHF Two weeks: 1200 CHF "
        "two full body shots in a dance position in dance attire "
        "(example: 1st arabesque 90°, sauté - 2nd feet position) and your portrait picture."
    )
    education = "CLASSICAL BALLET POINTE CLASSES REPERTOIRE CLASSES WILLIAM FORSYTHE IMPROVISATION"
    teachers_html = _TEACHERS_HTML

    edition = next(e for e in art._EDITIONS if e.key == "zurich")
    offering = art._build_offering(edition, landing, general, education, teachers_html)
    assert offering is not None
    assert offering.id == "art-of-zurich/zurich-summer-course-2026"
    assert offering.title == "ART of – Ballet Summer Course Zürich 2026"
    assert offering.schedule.start == date(2026, 8, 3)
    assert offering.schedule.end == date(2026, 8, 15)
    assert offering.location is not None
    assert offering.location.venue == "TANZWERK 101"
    assert offering.location.city == "Zürich"
    assert offering.location.country == "CH"
    assert offering.age_range == {"min": 10}
    assert [p.currency for p in offering.prices] == ["CHF", "CHF"]
    assert offering.application.deadline == date(2026, 7, 28)
    assert offering.teachers[0].name == "Leanne Benjamin"


def test_build_offering_skipped_without_dates():
    edition = next(e for e in art._EDITIONS if e.key == "madrid")
    assert art._build_offering(edition, "Winter Coming soon!", "", "", "") is None
