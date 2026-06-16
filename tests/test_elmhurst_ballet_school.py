"""Offline tests for the Elmhurst Ballet School Summer School scraper.

Inline HTML mirrors the `#collapse6` accordion panel structure (two `<h4>`
sub-programmes, `<strong>` labels, date/fee lines). No network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import Offering
from intensive_dance.scrapers.elmhurst_ballet_school import _build_offerings

# Faithful slice of the rendered "Summer School" accordion panel.
PANEL_HTML = """
<div id="collapse6">
  <p>Elmhurst’s Summer Schools offer young dancers an inspiring opportunity, with
     a focus on classical ballet and complementary styles.</p>

  <h4>Seniors -&nbsp;(Ages 14–18)</h4>
  <p><strong>New for 2026 - Two-week course option available</strong></p>
  <p><strong>Dates:</strong></p>
  <p>Week 1: Monday 10th – Saturday 15th August 2026 (Arrival: Sunday 9th August)</p>
  <p>Week 2: Monday 17th – Saturday 22nd August 2026 (Arrival: Sunday 16th August)</p>
  <p>Two-week course: Monday 10th – Saturday 22nd August 2026 (Arrival: Sunday 9th August)</p>
  <p>Training includes:</p>
  <p>Classical ballet technique</p>
  <p>Repertoire</p>
  <p>Pas de deux</p>
  <p>Pointe work</p>
  <p>Contemporary</p>
  <p>Jazz</p>
  <p><strong>Fees:</strong></p>
  <p>One Week:</p>
  <p>Residential: £940</p>
  <p>Non-residential: £670</p>
  <p>Two Weeks:</p>
  <p>Residential: £1680</p>
  <p>Non-residential: £1150</p>
  <p>A £50 non-refundable deposit, per week will be required once a place is offered.
     All fees include daily dance training, evening activities, and all food and drink.</p>

  <h4>Juniors -&nbsp;(Ages 10–13)</h4>
  <p><strong>Dates:</strong></p>
  <p>Tuesday 25th – Thursday 27th August 2026 (Arrival: Monday 24th August)</p>
  <p>This three-day programme introduces younger dancers, with a focus on classical
     ballet and repertoire from British Classics, alongside contemporary and jazz.</p>
  <p><strong>Fees:</strong></p>
  <p>Residential: £585.50</p>
  <p>Non-residential: £495.50</p>
  <p>A £50 non-refundable deposit will be required once a place is offered.</p>

  <p><strong>Applications are now closed, however please contact us to see if places
     are still available - summerschool@elmhurstdance.co.uk</strong></p>
</div>
"""


def _by_slug(html: str) -> dict[str, Offering]:
    return {o.id.split("/")[-1]: o for o in _build_offerings(html)}


def test_emits_both_summer_school_editions():
    offerings = _build_offerings(PANEL_HTML)
    assert {o.id for o in offerings} == {
        "elmhurst-ballet-school/senior-summer-school-2026",
        "elmhurst-ballet-school/junior-summer-school-2026",
    }
    for o in offerings:
        assert o.organization.country == "GB"
        assert o.location is not None and o.location.city == "Birmingham"
        assert o.application.status == "closed"
        assert o.application.notes is not None
        assert o.application.notes.startswith("Applications are now closed")
        assert o.application.requirements == []  # not stated on this page


def test_seniors_weeks_sessions_and_two_week_span():
    seniors = _by_slug(PANEL_HTML)["senior-summer-school-2026"]
    assert seniors.title == "Summer School (Seniors) 2026"
    assert seniors.age_range == {"min": 14, "max": 18}
    # Overall span = the two-week option; one Session per bookable week.
    assert seniors.schedule.start == date(2026, 8, 10)
    assert seniors.schedule.end == date(2026, 8, 22)
    labels = [(s.label, s.start, s.end) for s in seniors.schedule.sessions]
    assert labels == [
        ("Week 1", date(2026, 8, 10), date(2026, 8, 15)),
        ("Week 2", date(2026, 8, 17), date(2026, 8, 22)),
    ]
    assert seniors.genres == ["classical", "repertoire", "pointe", "contemporary"]


def test_seniors_fee_matrix_with_residential_includes():
    seniors = _by_slug(PANEL_HTML)["senior-summer-school-2026"]
    matrix = {(p.label, p.amount): sorted(p.includes) for p in seniors.prices}
    assert matrix == {
        ("One Week — Residential", 940.0): ["accommodation", "meals", "tuition"],
        ("One Week — Non-residential", 670.0): ["meals", "tuition"],
        ("Two Weeks — Residential", 1680.0): ["accommodation", "meals", "tuition"],
        ("Two Weeks — Non-residential", 1150.0): ["meals", "tuition"],
    }
    assert all(p.currency == "GBP" for p in seniors.prices)
    # The £50 deposit line must not become a price.
    assert 50.0 not in {p.amount for p in seniors.prices}


def test_juniors_single_edition_no_pointe():
    juniors = _by_slug(PANEL_HTML)["junior-summer-school-2026"]
    assert juniors.age_range == {"min": 10, "max": 13}
    assert juniors.schedule.start == date(2026, 8, 25)
    assert juniors.schedule.end == date(2026, 8, 27)
    assert juniors.schedule.sessions == []
    assert juniors.genres == ["classical", "repertoire", "contemporary"]
    assert {(p.label, p.amount) for p in juniors.prices} == {
        ("Residential", 585.5),
        ("Non-residential", 495.5),
    }


def test_missing_panel_yields_nothing():
    assert _build_offerings("<div id='collapse6'></div>") == []
    assert _build_offerings("<html><body>no panel</body></html>") == []
