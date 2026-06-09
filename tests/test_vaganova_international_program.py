"""Unit tests for the Vaganova International Program scraper (single static page).

These pin the regex parsing of the one summer-intensive home page — the year-less
ordinal date span (year lifted from the "Summer 2026" stamp), the three level
bands → age range + training levels, the USD tuition / registration / room-and-
board prices, the curriculum-driven genres, the closed-registration status and
the video-audition requirement. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import VideoReq
from intensive_dance.scrapers import vaganova_international_program as vip

# A trimmed slice of the live home page text covering every field the scraper reads.
HTML = """
<html><head><title>Vaganova International Program — Summer 2026</title></head>
<body>
<p>Summer 26 • UNLV • Las Vegas</p>
<h1>Vaganova International Program</h1>
<h2>Dates</h2>
<p>Summer 2026 — Las Vegas, Nevada</p>
<p><strong>Program dates:</strong> June 22nd to July 3rd rehearsals Gala day on July 3rd</p>
<h2>Levels &amp; Placement</h2>
<p>VIP serves dancers ages 9–19, divided into the following levels:</p>
<ul>
  <li><strong>Level 1:</strong> Ages 9–11</li>
  <li><strong>Level 2:</strong> Ages 12–14</li>
  <li><strong>Level 3:</strong> Ages 15–19</li>
</ul>
<h2>Curriculum Includes</h2>
<ul>
  <li>Daily Ballet Technique</li>
  <li>Pointe / Male Technique</li>
  <li>Classical Repertoire</li>
  <li>Variations Coaching</li>
  <li>Contemporary Technique &amp; Repertoire</li>
</ul>
<h2>Tuition &amp; Fees</h2>
<p>Program Tuition: 2000</p>
<p>Registration Fee: 150 (non refundable)</p>
<h2>Room Options &amp; Pricing</h2>
<p>Private Room + Meals (12 nights): $1,600</p>
<p>Shared Room + Meals (12 nights): $1,150</p>
<h2>Registration</h2>
<p>Due to high demand, all registrations closed. Please register here for Wait list.</p>
<p>all student registering now are automatically placed on the wait list</p>
</body></html>
"""


def test_build_offering_happy_path():
    offering = vip._build_offering(HTML)
    assert offering is not None
    assert offering.id == "vaganova-international-program/summer-intensive-2026"
    assert offering.schedule.start == date(2026, 6, 22)
    assert offering.schedule.end == date(2026, 7, 3)
    assert offering.schedule.season == "2026"
    assert offering.location is not None
    assert offering.location.city == "Las Vegas"
    assert offering.location.country == "US"
    assert offering.age_range == {"min": 9, "max": 19}


def test_dates_ordinal_with_external_year():
    assert vip._dates("Program dates: June 22nd to July 3rd", 2026) == (
        date(2026, 6, 22),
        date(2026, 7, 3),
    )


def test_dates_none_without_year():
    # Year must come from the "Summer 20xx" stamp; absent it, no dated edition.
    assert vip._dates("June 22nd to July 3rd", None) == (None, None)


def test_year_from_summer_stamp():
    assert vip._year("Summer 2026 — Las Vegas, Nevada") == 2026
    assert vip._year("no year stated") is None


def test_age_range_spans_level_bands():
    text = "Level 1: Ages 9–11 Level 2: Ages 12-14 Level 3: Ages 15–19"
    assert vip._age_range(text) == {"min": 9, "max": 19}


def test_age_range_absent():
    assert vip._age_range("a focused summer intensive") is None


def test_levels_mapped_from_bands():
    text = "Level 1: Ages 9–11 Level 2: Ages 12–14 Level 3: Ages 15–19"
    assert vip._levels(text) == ["beginner", "intermediate", "pre-professional"]


def test_genres_from_curriculum():
    text = "Daily Ballet Technique Pointe / Male Technique Classical Repertoire Variations Contemporary"
    assert vip._genres(text) == ["classical", "pointe", "repertoire", "contemporary"]


def test_prices_tuition_registration_and_board():
    text = (
        "Program Tuition: 2000 Registration Fee: 150 (non refundable) "
        "Private Room + Meals (12 nights): $1,600 Shared Room + Meals (12 nights): $1,150"
    )
    prices = vip._prices(text)
    by_label = {p.label: p for p in prices}
    assert by_label["Program Tuition"].amount == 2000.0
    assert by_label["Program Tuition"].includes == ["tuition"]
    assert by_label["Registration Fee"].amount == 150.0
    assert by_label["Registration Fee"].includes == []
    assert by_label["Private Room + Meals"].amount == 1600.0
    assert by_label["Private Room + Meals"].includes == ["accommodation", "meals"]
    assert by_label["Shared Room + Meals"].amount == 1150.0
    assert all(p.currency == "USD" for p in prices)


def test_status_closed_on_waitlist():
    assert vip._status("Due to high demand, all registrations closed. Wait list.") == "closed"


def test_status_none_when_unstated():
    assert vip._status("Program dates: June 22nd to July 3rd") is None


def test_requirements_video_audition():
    reqs = vip._requirements("Please register here for Wait list registration.")
    assert len(reqs) == 1
    assert isinstance(reqs[0], VideoReq)
    assert reqs[0].specificity == "unspecific"


def test_teachers_named_with_affiliations():
    offering = vip._build_offering(HTML)
    assert offering is not None
    names = [t.name for t in offering.teachers]
    assert "Alexei Moskalenko" in names
    assert "Natalia Bashkatova" in names
    # every named teacher carries at least one affiliation
    assert all(t.affiliations for t in offering.teachers)


def test_no_dated_edition_returns_none():
    assert vip._build_offering("<html><body><p>Coming soon.</p></body></html>") is None
