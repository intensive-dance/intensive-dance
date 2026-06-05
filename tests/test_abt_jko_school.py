"""Unit tests for the ABT JKO School Summer Intensives scraper.

ABT is an HTML scrape of one page whose three sites live in an `.accordion-wrap`
of `.accordion-item`s, each carrying an Age Group · Cost · Location · Housing
table. These pin the judgement calls a hash check can't catch: the cross-month
date range, the multi-fee Cost cell, the venue/city split out of the address
lines, level/genre keyword mapping, and the audition→video requirement. Inline
HTML snippets, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import abt_jko_school as abt

# Two sites: New York (one Tuition fee, names a guest teacher) and Florida (three
# fees, on-campus housing). Enough to exercise every parsing branch end to end.
_HTML = """
<div class="accordion-wrap">
  <div class="accordion-item">
    <div class="accordion-item-title">New York Summer Intensive</div>
    <div class="accordion-item-content"><div class="accordion-item-content-text">
      <p>Five weeks geared toward advanced dancers, trained with ABT's National
      Training Curriculum. Hosts guest teachers including ABT Artistic Director
      Susan Jaffe and other ABT Directors of Repertoire.</p>
      <p><strong>Dates:</strong> June 22 &#8211; July 24, 2026</p>
      <table><tbody>
        <tr><td><strong>Age Group</strong></td><td><strong>Cost</strong></td>
            <td><strong>Location</strong></td><td><strong>Housing</strong></td></tr>
        <tr>
          <td><p>12-20</p></td>
          <td>Tuition:<p>$4,350 USD</p></td>
          <td><p>American Ballet Theatre</p><p>890 Broadway, 3rd Floor</p>
              <p>New York, NY 10003</p><p>(212) 477-3030 ext. 3416</p></td>
          <td><em>Supervised housing is not available in New York.</em></td>
        </tr>
      </tbody></table>
    </div></div>
  </div>
  <div class="accordion-item">
    <div class="accordion-item-title">Florida Summer Intensive</div>
    <div class="accordion-item-content"><div class="accordion-item-content-text">
      <p>A three-week intensive refining technique for intermediate and advanced
      dancers, taught by renowned ABT faculty.</p>
      <p><strong>Dates:</strong> July 13 &#8211; July 31, 2026</p>
      <table><tbody>
        <tr><td><strong>Age Group</strong></td><td><strong>Cost</strong></td>
            <td><strong>Location</strong></td><td><strong>Housing</strong></td></tr>
        <tr>
          <td><p>12-18</p></td>
          <td>Tuition:<p>$2,775 USD</p>Day Student Fee:<p>$1,000 USD</p>
              Room and Board:<p>$3,000 USD</p></td>
          <td><p>University of South Florida</p><p>School of Theatre and Dance</p>
              <p>Tampa, FL 33620</p></td>
          <td>Housing is available.</td>
        </tr>
      </tbody></table>
    </div></div>
  </div>
</div>
<p>Dancers may audition in person at one of the sites on our National Audition
Tour or submit a video audition. Online pre-registration will open on
November 1, 2025.</p>
"""


# --- dates --------------------------------------------------------------------


def test_dates_cross_month_range():
    assert abt._dates("Dates: June 22 – July 24, 2026") == (date(2026, 6, 22), date(2026, 7, 24))


def test_dates_same_month_range():
    assert abt._dates("July 13 – July 31, 2026") == (date(2026, 7, 13), date(2026, 7, 31))


def test_dates_absent():
    assert abt._dates("no dated edition yet") == (None, None)


# --- ages ---------------------------------------------------------------------


def test_age_range():
    assert abt._age_range("12-20") == {"min": 12, "max": 20}
    assert abt._age_range("12-18") == {"min": 12, "max": 18}


def test_age_range_absent():
    assert abt._age_range("advanced dancers") is None


# --- levels & genres ----------------------------------------------------------


def test_levels_from_prose():
    assert abt._levels("geared toward advanced dancers") == ["advanced"]
    assert abt._levels("for intermediate and advanced dancers") == ["intermediate", "advanced"]


def test_genres_default_and_repertoire():
    assert abt._genres("classical ballet technique") == ["classical"]
    assert abt._genres("ballet technique and ABT repertory") == ["classical", "repertoire"]


# --- prices -------------------------------------------------------------------


def test_prices_single_tuition():
    (price,) = abt._prices("Tuition: $4,350 USD")
    assert (price.amount, price.currency, price.label, price.includes) == (
        4350.0,
        "USD",
        "Tuition",
        ["tuition"],
    )


def test_prices_multiple_with_room_and_board():
    prices = abt._prices(
        "Tuition: $2,775 USD Day Student Fee: $1,000 USD Room and Board: $3,000 USD"
    )
    assert [(p.label, p.amount, p.includes) for p in prices] == [
        ("Tuition", 2775.0, ["tuition"]),
        ("Day Student Fee", 1000.0, []),
        ("Room and Board", 3000.0, ["accommodation", "meals"]),
    ]


# --- opens_at & requirements --------------------------------------------------


def test_opens_at():
    assert abt._opens_at("pre-registration will open on November 1, 2025.") == date(2025, 11, 1)


def test_opens_at_absent():
    assert abt._opens_at("auditions are by acceptance only") is None


def test_requirements_video_when_audition_stated():
    (req,) = abt._requirements("Dancers may submit a video audition.")
    assert (req.type, req.specificity) == ("video", "unspecific")


def test_requirements_none_when_silent():
    assert abt._requirements("Classes are held Monday to Friday.") == []


# --- end-to-end over the accordion structure ----------------------------------


def test_build_offerings_splits_sites():
    offerings = abt._build_offerings(_HTML, date(2026, 1, 1))
    assert [o.id for o in offerings] == [
        "abt-jko-school/new-york-2026",
        "abt-jko-school/florida-2026",
    ]


def test_build_offerings_new_york_fields():
    ny = abt._build_offerings(_HTML, date(2026, 1, 1))[0]
    assert ny.schedule.start == date(2026, 6, 22)
    assert ny.schedule.end == date(2026, 7, 24)
    assert ny.schedule.timezone == "America/New_York"
    assert ny.age_range == {"min": 12, "max": 20}
    assert ny.level == ["advanced"]
    assert ny.location is not None
    assert ny.location.venue == "American Ballet Theatre"
    assert ny.location.city == "New York"
    assert [p.amount for p in ny.prices] == [4350.0]
    assert ny.application.opens_at == date(2025, 11, 1)
    assert ny.application.requirements[0].type == "video"


def test_build_offerings_florida_venue_city_and_fees():
    fl = abt._build_offerings(_HTML, date(2026, 1, 1))[1]
    assert fl.location is not None
    assert fl.location.venue == "University of South Florida"
    assert fl.location.city == "Tampa"
    assert [p.label for p in fl.prices] == ["Tuition", "Day Student Fee", "Room and Board"]
    assert fl.level == ["intermediate", "advanced"]


def test_build_offerings_names_guest_teacher():
    ny = abt._build_offerings(_HTML, date(2026, 1, 1))[0]
    (teacher,) = ny.teachers
    assert teacher.name == "Susan Jaffe"
    assert teacher.affiliations[0].organization == "American Ballet Theatre"
    # Florida cites only unnamed "ABT faculty" → no teachers.
    assert abt._build_offerings(_HTML, date(2026, 1, 1))[1].teachers == []
