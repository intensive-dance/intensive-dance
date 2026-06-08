"""Unit tests for the Nacho Duato Academy scraper (offline / no network)."""

from __future__ import annotations

from datetime import date

from intensive_dance.models import VideoReq
from intensive_dance.scrapers import nacho_duato_academy as nda

# ---- inline HTML snippet mirroring the WP content.rendered structure --------
# Divi shortcodes are left in (as the API returns them), the parser strips them.
# One division block each, fees section, and a PDF link with the edition year.

_HTML = """
<p>[et_pb_section fb_built=&#8221;1&#8243;]</p>
<h1 style="text-align: center;">NDA SUMMER INTENSIVE BALLET COURSE</h1>
<p style="text-align: center;"><strong>JUNE 22-JULY 4</strong></p>
<p>Nacho Duato Academy summer intensive is an exclusive opportunity to refine your
<strong>classical ballet technique</strong> through exceptional training and repertoire,
immerse yourself in the speed, musicality, and expressiveness of
<strong>Nacho Duato Repertoire</strong>, explore the company's signature works, and take
your first steps into <strong>Escuela Bolera</strong>—a vibrant Spanish dance style.</p>
<p>For more information
<a href="https://nachoduatoacademy.com/wp-content/uploads/2026/05/2026-Summer-Intensive-NDA.pdf">here</a>
you can find all the documentation.</p>
<p><span>The deadline to submit the material is <strong>June 1st</strong>.</span></p>
<h2>COURSE CONTENT AND SCHEDULE</h2>
<p><strong>NDA SUMMER INTENSIVE SENIOR</strong></p>
<p>9:30-11:00 Ballet Class</p>
<p>11:00-12:30 Classical Ballet Repertoire</p>
<p>12:30-14:00 Nacho Duato Repertoire</p>
<p>14:30-15:30 Escuela Bolera</p>
<p>15:30-17:00 Sonia Dawkins workshop</p>
<p><strong>NDA SUMMER INTENSIVE JUNIOR</strong></p>
<p>9:30-11:00 Ballet Class</p>
<p>11:10-12:30 Classical Ballet Repertoire</p>
<p>13.00-14:00 Escuela Bolera</p>
<p>14:00-15:15 Nacho Duato Repertoire</p>
<h2>FEES</h2>
<ul>
<li>ALL INCLUDED SUMMER INTENSIVE PACKAGE SENIOR (INCLUDES: all classes, lodging in individual
rooms for 14 nights, breakfast and dinner at the Student Experience): <strong>2500€</strong></li>
<li>Summer intensive SENIOR all classes (including Sonia Dawkins special guest workshop)
for one week: <strong>750€</strong></li>
<li>Summer intensive SENIOR 2 weeks (including special guest Sonia Dawkins workshop):
<strong>1400€</strong></li>
<li>Summer intensive Junior one week: <strong>450€</strong></li>
<li>Summer intensive Junior 2 weeks: <strong>800€</strong></li>
</ul>
<p>[/et_pb_section]</p>
"""

_MODIFIED = "2026-05-20T16:36:38"


# ---- date / year helpers -----------------------------------------------------


def test_infer_year_from_pdf_link():
    assert nda._infer_year(_HTML, _MODIFIED) == 2026


def test_infer_year_from_modified_when_no_pdf():
    html_no_pdf = "<p>JUNE 22-JULY 4</p>"
    assert nda._infer_year(html_no_pdf, "2026-03-01T00:00:00") == 2026


def test_parse_dates_cross_month():
    text = nda._extract_text(_HTML)
    start, end = nda._parse_dates(text, 2026)
    assert start == date(2026, 6, 22)
    assert end == date(2026, 7, 4)


def test_parse_dates_absent():
    start, end = nda._parse_dates("No dates here.", 2026)
    assert start is None
    assert end is None


# ---- deadline ----------------------------------------------------------------


def test_parse_deadline():
    text = nda._extract_text(_HTML)
    assert nda._parse_deadline(text, 2026) == date(2026, 6, 1)


def test_parse_deadline_absent():
    assert nda._parse_deadline("No deadline mentioned.", 2026) is None


# ---- prices ------------------------------------------------------------------


def test_prices_senior_all_tiers():
    text = nda._extract_text(_HTML)
    prices = nda._parse_prices_senior(text)
    amounts = {p.label: p.amount for p in prices}
    # All-inclusive package
    assert amounts["All-inclusive Senior (2 weeks)"] == 2500.0
    # 1-week and 2-week tuition
    assert amounts["Senior — 1 week (all classes)"] == 750.0
    assert amounts["Senior — 2 weeks (all classes)"] == 1400.0
    # All prices in EUR
    assert all(p.currency == "EUR" for p in prices)


def test_prices_senior_all_inclusive_includes():
    text = nda._extract_text(_HTML)
    prices = nda._parse_prices_senior(text)
    ai = next(p for p in prices if p.label and "All-inclusive" in p.label)
    assert "tuition" in ai.includes
    assert "accommodation" in ai.includes
    assert "meals" in ai.includes


def test_prices_junior_both_tiers():
    text = nda._extract_text(_HTML)
    prices = nda._parse_prices_junior(text)
    amounts = {p.label: p.amount for p in prices}
    assert amounts["Junior — 1 week"] == 450.0
    assert amounts["Junior — 2 weeks"] == 800.0


def test_prices_absent_when_no_fees():
    assert nda._parse_prices_senior("No fees here.") == []
    assert nda._parse_prices_junior("No fees here.") == []


# ---- genres ------------------------------------------------------------------


def test_genres_from_content():
    text = nda._extract_text(_HTML)
    genres = nda._genres(text)
    assert "classical" in genres
    assert "contemporary" in genres  # Nacho Duato Repertoire → contemporary
    assert "character" in genres  # Escuela Bolera → character


# ---- full build_offerings ----------------------------------------------------


def test_build_offerings_returns_two_offerings():
    offerings = nda._build_offerings(_HTML, _MODIFIED)
    assert len(offerings) == 2
    ids = [o.id for o in offerings]
    assert "nacho-duato-academy/summer-intensive-senior-2026" in ids
    assert "nacho-duato-academy/summer-intensive-junior-2026" in ids


def test_build_offerings_dates():
    offerings = nda._build_offerings(_HTML, _MODIFIED)
    for o in offerings:
        assert o.schedule.start == date(2026, 6, 22)
        assert o.schedule.end == date(2026, 7, 4)
        assert o.schedule.season == "2026"


def test_build_offerings_deadline():
    offerings = nda._build_offerings(_HTML, _MODIFIED)
    for o in offerings:
        assert o.application.deadline == date(2026, 6, 1)


def test_build_offerings_requirements_are_video_specific():
    offerings = nda._build_offerings(_HTML, _MODIFIED)
    for o in offerings:
        reqs = o.application.requirements
        assert len(reqs) == 1
        req = reqs[0]
        assert isinstance(req, VideoReq)
        assert req.specificity == "specific"
        assert req.description is not None
        assert "adage" in req.description.lower()


def test_build_offerings_location():
    offerings = nda._build_offerings(_HTML, _MODIFIED)
    for o in offerings:
        assert o.location is not None
        assert o.location.city == "Madrid"
        assert o.location.country == "ES"


def test_build_offerings_senior_has_more_prices():
    offerings = nda._build_offerings(_HTML, _MODIFIED)
    senior = next(o for o in offerings if "senior" in o.id)
    junior = next(o for o in offerings if "junior" in o.id)
    # Senior has 3 tiers (all-inclusive, 1wk, 2wks); junior has 2 (1wk, 2wks)
    assert len(senior.prices) == 3
    assert len(junior.prices) == 2


def test_build_offerings_no_dates_returns_empty():
    html_no_dates = "<p>No dates announced yet.</p>"
    assert nda._build_offerings(html_no_dates, "2026-01-01T00:00:00") == []


def test_build_offerings_organisation():
    offerings = nda._build_offerings(_HTML, _MODIFIED)
    for o in offerings:
        assert o.organization.name == "Nacho Duato Academy"
        assert o.organization.country == "ES"
        assert o.organization.city == "Madrid"
