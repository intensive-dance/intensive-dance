"""Unit tests for the Yorkshire Ballet Seminars scraper (Wix, two pages).

These pin the parsing of the YBS summer-residential pages without network: the
four weekly dated editions read off the single editions heading (with the title
year applied and a New-Year wrap), the age band and curriculum genres drawn from
the homepage prose, and the Artistic Director byline (whose comma + singular
"Director" must skip the "Welcome New Artistic Director" heading and the
"previous Artistic Directors" prose). Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import yorkshire_ballet_seminars as ybs

# The editions live in one <h2>: "Summer Residential 2026 (per week) <dates>".
COURSES_HTML = """
<html><body>
  <h2>RESIDENTIAL COURSES</h2>
  <p>Spend a week immersed in dance. Each day pairs technique classes and
     repertoire sessions with personalised feedback from industry professionals.</p>
  <h2>Summer Residential 2026​
      (per week)
      July 12th - July 18th
      July 19th - July 25th
      July 26th - August 1st
      August 2nd - August 8th</h2>
  <h2>LOCATION</h2>
  <p>Ashville College, Green Lane, Harrogate HG2 9JP</p>
</body></html>
"""

# The homepage carries the canonical age band, the curriculum line, and the
# Artistic Director byline — alongside two decoys the regex must not catch.
HOME_TEXT = (
    "LEARN MORE Welcome New Artistic Director "
    "building on the outstanding work of previous Artistic Directors and "
    "strengthening pastoral care. Isabelle Brouwers, Artistic Director "
    "Yorkshire Ballet Seminars offers dance students ages 9 to 19 the opportunity "
    "to attend world class residential courses taught by internationally renowned "
    "dancers, with classical ballet, pointe work and contemporary classes. "
    "Patrons: Anya Sainsbury CBE, Sir Anthony Dowell CBE, Kevin O'Hare CBE."
)


def test_summer_editions_four_weeks():
    season, weeks = ybs._summer_editions(COURSES_HTML)
    assert season == "2026"
    assert weeks == [
        (date(2026, 7, 12), date(2026, 7, 18)),
        (date(2026, 7, 19), date(2026, 7, 25)),
        (date(2026, 7, 26), date(2026, 8, 1)),
        (date(2026, 8, 2), date(2026, 8, 8)),
    ]


def test_summer_editions_absent_returns_empty():
    # A page with no "Residential <year>" heading yields no editions (fail open).
    season, weeks = ybs._summer_editions("<html><body><h2>About Us</h2></body></html>")
    assert (season, weeks) == ("unknown", [])


def test_ranges_new_year_wrap():
    # An end month before the start month rolls the end into the next year
    # (e.g. an Easter-style course closing in early January).
    assert ybs._ranges("December 28th - January 3rd", 2026) == [
        (date(2026, 12, 28), date(2027, 1, 3)),
    ]


def test_age_range():
    assert ybs._age_range(HOME_TEXT) == {"min": 9, "max": 19}


def test_genres_from_combined_prose():
    genres = ybs._genres(
        "technique classes and repertoire sessions. "
        "classical ballet, pointe work and contemporary classes"
    )
    assert genres == ["classical", "pointe", "contemporary", "repertoire"]


def test_director_byline_picks_named_person():
    teachers = ybs._teachers(HOME_TEXT)
    assert len(teachers) == 1
    teacher = teachers[0]
    assert teacher.name == "Isabelle Brouwers"
    assert teacher.role == "Artistic Director"
    assert teacher.affiliations[0].organization == "Yorkshire Ballet Seminars"
    assert teacher.affiliations[0].current is True


def test_director_byline_skips_headings_and_plurals():
    # No named "<Name>, Artistic Director" byline → no teacher emitted; the bare
    # heading and the plural "Artistic Directors" must not match.
    assert ybs._teachers("Welcome New Artistic Director and previous Artistic Directors") == []


def test_build_offerings_end_to_end():
    offerings = ybs._build_offerings(COURSES_HTML, HOME_TEXT, date(2026, 6, 8))
    assert [o.id for o in offerings] == [
        "yorkshire-ballet-seminars/summer-2026-week-1",
        "yorkshire-ballet-seminars/summer-2026-week-2",
        "yorkshire-ballet-seminars/summer-2026-week-3",
        "yorkshire-ballet-seminars/summer-2026-week-4",
    ]
    first = offerings[0]
    assert first.title == "Summer Residential 2026 — Week 1 (12–18 July)"
    assert first.schedule.start == date(2026, 7, 12)
    assert first.schedule.end == date(2026, 7, 18)
    assert first.schedule.season == "2026"
    assert first.age_range == {"min": 9, "max": 19}
    assert first.genres == ["classical", "pointe", "contemporary", "repertoire"]
    assert first.organization.country == "GB"
    assert first.location is not None
    assert first.location.city == "Harrogate"
    assert first.application.url == "https://www.ybss.co.uk/summerapply"
    # Prices are not published in scrapeable markup → none invented.
    assert first.prices == []
    # A cross-month edition keeps the British two-month label.
    assert offerings[2].title == "Summer Residential 2026 — Week 3 (26 July – 1 August)"


def test_no_editions_yields_no_offerings():
    assert ybs._build_offerings("<html><body></body></html>", HOME_TEXT, date(2026, 6, 8)) == []
