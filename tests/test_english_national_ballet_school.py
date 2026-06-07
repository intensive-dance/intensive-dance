"""Unit tests for the English National Ballet School Summer Intensives scraper."""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import english_national_ballet_school as enbs

# A trimmed-down stand-in for the page's plain text: three course markers, each
# with its own date range / age / level, then the shared fees + guidance block
# whose "RAD intermediate level" must not leak into Course Three.
SAMPLE = (
    "Summer Intensives "
    "COURSE ONE - High Technique & Artistry Monday 20 July – Friday 31 July 2026 "
    "classical ballet through in-depth repertoire studies Age: 14-17 "
    "Level: At least intermediate or RAD equivalent. "
    "ENBS Faculty Sebnem Onal, Ibrahim Onal, Senri Kou, Michael Berkin, Nicola Simpson "
    "Guest Teachers Principal Dancer and Actress Constance Devarnay and "
    "Elmhurst Ballet School's Joshua Barwick. "
    "Dates Monday 20 July – Friday 31 July 2026. Apply for Course One "
    "COURSE TWO - Bournonville and Ashton Monday 3 August – Saturday 15 August 2026 "
    "Week One: Bournonville Train with exceptional artists including Olivier and Evening "
    "Standard Award winner Peter Schaufuss, Knight of Denmark & Founder of English National "
    "ballet School and, Dinna Bjørn, a leading world authority on the female Bournonville style. "
    "Week Two: Ashton Work with leading Ashton specialists including Samara Downs, "
    "Principal Dancer with Birmingham Royal Ballet. "
    "repertoire and mime, the interplay of music and character that define his ballets Age: 14-18 "
    "Level: At least Intermediate or RAD equivalent. Apply for Course Two "
    "COURSE THREE-Pre-Professional & Professional Ballet Intensive "
    "Monday 20 July - Friday 31 July 2026 pointe work and variations Age: 18 to 23 "
    "Apply for Course Three "
    "All Summer Intensive Course Information Fees "
    "A non-refundable application fee of £30 must be paid. Each Intensive Course is £1250. "
    "Placements are open to students at RAD intermediate level. "
    "Applications are now open."
)


REGION = SAMPLE[: SAMPLE.index("All Summer Intensive Course Information")]


def _course(numeral: str) -> tuple[str, str, str]:
    return next(c for c in enbs._courses(REGION) if c[0] == numeral)


def test_courses_split_into_three_with_titles():
    numerals = [c[0] for c in enbs._courses(REGION)]
    assert numerals == ["1", "2", "3"]
    assert _course("1")[1] == "High Technique & Artistry"
    assert _course("3")[1] == "Pre-Professional & Professional Ballet Intensive"


def test_date_range_shares_year_across_endpoints():
    assert enbs._date_range(_course("1")[2]) == (date(2026, 7, 20), date(2026, 7, 31))
    assert enbs._date_range(_course("2")[2]) == (date(2026, 8, 3), date(2026, 8, 15))


def test_age_range_handles_dash_and_to():
    assert enbs._age_range(_course("1")[2]) == {"min": 14, "max": 17}
    assert enbs._age_range(_course("3")[2]) == {"min": 18, "max": 23}


def test_levels_per_course():
    assert enbs._levels(_course("1")[2]) == ["intermediate"]
    assert enbs._levels(_course("3")[2]) == ["pre-professional", "professional"]


def test_shared_block_does_not_leak_intermediate_into_course_three():
    # "RAD intermediate level" lives past the shared marker, so Course Three —
    # an 18-23 pre-pro/professional course — must not pick up "intermediate".
    assert "intermediate" not in enbs._levels(_course("3")[2])


def test_genres_ignore_prose_word_character():
    # Course Two mentions "music and character"; that's not character *dance*.
    assert enbs._genres(_course("2")[2]) == ["classical", "repertoire"]
    assert enbs._genres(_course("3")[2]) == ["classical", "pointe"]


def test_prices_course_and_application_fee():
    course, app = enbs._prices(SAMPLE)
    assert (course.amount, course.currency, course.includes) == (1250.0, "GBP", ["tuition"])
    assert (app.amount, app.currency) == (30.0, "GBP")


def test_build_offering_keeps_cycle_as_scheduled():
    # Per IDR-24 the scraper no longer date-drops; offerings stay `scheduled`
    # and past/cancelled handling is left to the model.
    offering = enbs._build_offering(_course("1"), SAMPLE)
    assert offering.id == "english-national-ballet-school/summer-intensive-2026-course-1"
    assert offering.lifecycle == "scheduled"
    assert offering.application.status == "open"


def test_teachers_course_one_enbs_faculty():
    teachers = enbs._teachers("1", _course("1")[2])
    names = [t.name for t in teachers]
    assert "Sebnem Onal" in names
    assert "Ibrahim Onal" in names
    assert "Senri Kou" in names
    assert "Michael Berkin" in names
    assert "Nicola Simpson" in names
    faculty = [t for t in teachers if t.role == "Faculty"]
    assert len(faculty) == 5
    assert all(
        any(a.organization == "English National Ballet School" for a in t.affiliations)
        for t in faculty
    )


def test_teachers_course_one_guest_teachers():
    teachers = enbs._teachers("1", _course("1")[2])
    guest_names = {t.name for t in teachers if t.role == "Guest Teacher"}
    assert "Constance Devarnay" in guest_names
    assert "Joshua Barwick" in guest_names
    barwick = next(t for t in teachers if t.name == "Joshua Barwick")
    assert any(a.organization == "Elmhurst Ballet School" for a in barwick.affiliations)


def test_teachers_course_two_bournonville_and_ashton():
    teachers = enbs._teachers("2", _course("2")[2])
    names = [t.name for t in teachers]
    assert "Peter Schaufuss" in names
    assert "Dinna Bjørn" in names
    assert "Samara Downs" in names
    samara = next(t for t in teachers if t.name == "Samara Downs")
    assert any(a.organization == "Birmingham Royal Ballet" for a in samara.affiliations)
    assert "Week Two" in (samara.role or "")


def test_teachers_course_three_empty():
    assert enbs._teachers("3", _course("3")[2]) == []
