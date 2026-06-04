"""Unit tests for the Russian Masters Ballet scraper's HTML-shaped parsing.

RMB is the project's first pure-HTML scrape (Bitrix, no API), so these pin the
judgement calls a hash check can't catch: track→level mapping, age/date/money
parsing, prose-section slicing, and — the headline feature — pulling named
teachers with their institutional affiliations out of run-together markup.
Inline strings/HTML snippets, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import russian_masters_ballet as rmb


# --- levels (from the track name) ---------------------------------------------


def test_levels_from_track_name():
    assert rmb._levels("Professional") == ["professional"]
    assert rmb._levels("Professional (3 weeks)") == ["professional"]
    assert rmb._levels("Pre-Professional") == ["pre-professional"]
    assert rmb._levels("Open Professional") == ["professional", "open"]
    assert rmb._levels("Observation") == []


# --- ages ---------------------------------------------------------------------


def test_age_range_yo_and_years_old():
    assert rmb._age_range("students 12-19 y.o. specializing in classical dance") == {"min": 12, "max": 19}
    assert rmb._age_range("students 10-18 years old with prior knowledge") == {"min": 10, "max": 18}


def test_age_range_spans_multiple_ranges():
    # Madrid states two bands; we keep the outer envelope.
    assert rmb._age_range("11-18 y.o. For the Package - 12-18 y.o.") == {"min": 11, "max": 18}


def test_age_range_none_when_absent():
    assert rmb._age_range("classical ballet professionals") is None


# --- dates --------------------------------------------------------------------


def test_dates_short_shared_month_range():
    assert rmb._dates("3 weeks: 5 - 26 July", 2026) == (date(2026, 7, 5), date(2026, 7, 26))


def test_dates_cross_month_range_inherits_year():
    assert rmb._dates("3 weeks: 28 June - 19 July", 2026) == (date(2026, 6, 28), date(2026, 7, 19))


def test_dates_picks_earliest_start_latest_end():
    text = "1 week: 5 - 12 July 2 weeks: 12 - 26 July 3 weeks: 5 - 26 July"
    assert rmb._dates(text, 2026) == (date(2026, 7, 5), date(2026, 7, 26))


def test_dates_uses_trailing_year_token():
    assert rmb._dates("26 December - 30 December, 2026", None) == (date(2026, 12, 26), date(2026, 12, 30))


def test_dates_wrap_across_new_year():
    # A winter cycle's January tail belongs to the following year.
    assert rmb._dates("26 December - 04 January", 2026) == (date(2026, 12, 26), date(2027, 1, 4))


def test_dates_none_without_day_month():
    assert rmb._dates("1, 2 or 3 weeks", 2026) == (None, None)


# --- money & prices -----------------------------------------------------------


def test_prices_euro_per_line():
    fee = "1 week: 5 - 12 July - 550 €\n2 weeks: 12 - 26 July - 950 €"
    assert [(p.amount, p.currency, p.label) for p in rmb._prices(fee)] == [
        (550.0, "EUR", "1 week: 5 - 12 July"),
        (950.0, "EUR", "2 weeks: 12 - 26 July"),
    ]


def test_prices_cny_with_thousands_separator():
    fee = "Early Bird price - 12,800 CNY\nRegular price - 15,800 CNY"
    assert [(p.amount, p.currency, p.label) for p in rmb._prices(fee)] == [
        (12800.0, "CNY", "Early Bird price"),
        (15800.0, "CNY", "Regular price"),
    ]


def test_prices_includes_tuition():
    (price,) = rmb._prices("3 weeks: 1950 €")
    assert price.includes == ["tuition"]


# --- prose section slicing ----------------------------------------------------


def test_section_slices_between_labels():
    body = "TEACHERS\nJane Doe\nPROGRAM FEE\n3 weeks: 1950 €\nOFFICIAL ACCOMMODATION\nhostel"
    assert rmb._section(body, "PROGRAM FEE") == "3 weeks: 1950 €"


def test_section_missing_label_is_empty():
    assert rmb._section("AIMED AT students", "PROGRAM FEE") == ""


# --- genres -------------------------------------------------------------------


def test_genres_from_program_text():
    body = "Ballet Classes Points / Male technique Classical Repertoire Character Pas de Deux Contemporary"
    assert rmb._genres(body) == ["classical", "contemporary", "character", "repertoire", "pointe"]


# --- teachers & affiliations --------------------------------------------------

from selectolax.parser import HTMLParser  # noqa: E402


def _article(html: str):
    return HTMLParser(f"<div>{html}</div>").css_first("div")


def test_teachers_split_despite_runtogether_markup():
    # The first names are nested in wrapper spans with no separator text between
    # the name and the next anchor — a sibling walk overruns; document order doesn't.
    html = (
        "<b>TEACHERS</b><br>"
        "<span><a href='/faculty/teachers/yulia/'><b><u>Yuliya Kasenkova</u></b></a>"
        "<span> - current teacher of Vaganova Academy<br>"
        "<a href='/faculty/teachers/alexey/'><b><u>Alexey Ilyin</u></b></a> - current teacher of Vaganova Academy<br>"
        "</span></span>"
    )
    teachers = rmb._teachers(_article(html))
    assert [t.name for t in teachers] == ["Yuliya Kasenkova", "Alexey Ilyin"]
    # Yuliya's affiliation is just her own — not bled from the next teacher.
    (aff,) = teachers[0].affiliations
    assert (aff.organization, aff.role, aff.current) == ("Vaganova Ballet Academy", "teacher", True)


def test_teacher_former_affiliation_is_not_current():
    html = (
        "<a href='/faculty/teachers/anton/'><b><u>Anton Valdbauer</u></b></a>"
        " - contemporary choreographer, ex soloist of the Royal Swedish Ballet<br>"
    )
    (teacher,) = rmb._teachers(_article(html))
    (aff,) = teacher.affiliations
    assert (aff.organization, aff.role, aff.current) == ("Royal Swedish Ballet", "soloist", False)


def test_teacher_guest_link_does_not_capture_a_teacher():
    # Guests link under /faculty/artists/ (or /guests/), not /faculty/teachers/.
    html = "<a href='/faculty/artists/svetlana/'><b><u>Svetlana Bednenko</u></b></a> - ex dancer<br>"
    assert rmb._teachers(_article(html)) == []


def test_teacher_multiple_institutions_kept_org_only():
    html = (
        "<a href='/faculty/teachers/larissa/'><b><u>Larissa Lezhnina</u></b></a>"
        " - principal tutor at Dutch National Ballet, former soloist at Mariinsky, "
        "Vaganova Academy licensed teacher<br>"
    )
    (teacher,) = rmb._teachers(_article(html))
    orgs = [a.organization for a in teacher.affiliations]
    assert orgs == ["Vaganova Ballet Academy", "Mariinsky Theatre", "Dutch National Ballet"]
    # Role/currency aren't attributed when several institutions are named.
    assert all(a.role is None and a.current is None for a in teacher.affiliations)
