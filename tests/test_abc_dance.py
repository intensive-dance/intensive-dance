"""Offline tests for the abcDance (Wiener Neustadt) summer Tanzcamp scraper.

The camp dates live as text in the Jimdo registration form's checkbox labels
("CAMP 1 (20.-24. Juli 2026; 5-15 Jahre)") — never in the schedule images. These
inline snippets mirror that form plus the separate `programm` page that carries
the "Anmeldungsdeadline:" line, covering the same-month range, the cross-month
Aug→Sep range, the shared age band, and the deadline-vs-loose-date trap.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import abc_dance

# Faithful copy of the Tanz-Camp registration form's checkbox group.
FORM_HTML = """
<html><body>
<nav>Home Workshops 2026 Contemporary Dance Ballett</nav>
<h1>Anmeldung sommer Tanzcamp 2026</h1>
<div class="cc-m-form-view-element">
  <label><div>Camp auswählen</div></label>
  <div class="cc-m-form-element-input">
    <div><label>
      <input type="checkbox" name="mc" value="CAMP 1 (20.-24. Juli 2026; 5-15 Jahre)"/>
      <span>CAMP 1 (20.-24. Juli 2026; 5-15 Jahre)</span>
    </label></div>
    <div><label>
      <input type="checkbox" name="mc" value="CAMP 2 (27.-31. Juli 2026; 5-15 Jahre)"/>
      <span>CAMP 2 (27.-31. Juli 2026; 5-15 Jahre)</span>
    </label></div>
    <div><label>
      <input type="checkbox" name="mc" value="CAMP 3 (30. August-5. September 2026; 5-15 Jahre)"/>
      <span>CAMP 3 (30. August-5. September 2026; 5-15 Jahre)</span>
    </label></div>
  </div>
</div>
</body></html>
"""

# The programm page only carries the deadline as text (the rest is images).
PROGRAMM_HTML = """
<html><body>
<h1>Programm Sommer 2026</h1>
<p>Sommer 2026 Anmeldungsdeadline: 4. Juli 2026</p>
</body></html>
"""


def test_three_camps_with_dates_and_ages() -> None:
    offerings = abc_dance._build_offerings(FORM_HTML, PROGRAMM_HTML, date(2026, 6, 1))
    assert len(offerings) == 3

    ids = [o.id for o in offerings]
    assert ids == [
        "abc-dance/sommer-tanzcamp-1-2026",
        "abc-dance/sommer-tanzcamp-2-2026",
        "abc-dance/sommer-tanzcamp-3-2026",
    ]

    c1, c2, c3 = offerings
    # Same-month spans.
    assert c1.schedule.start == date(2026, 7, 20)
    assert c1.schedule.end == date(2026, 7, 24)
    assert c2.schedule.start == date(2026, 7, 27)
    assert c2.schedule.end == date(2026, 7, 31)
    # Cross-month span, year stated once at the end.
    assert c3.schedule.start == date(2026, 8, 30)
    assert c3.schedule.end == date(2026, 9, 5)

    for o in offerings:
        assert o.age_range == {"min": 5, "max": 15}
        assert o.genres == ["classical"]  # no per-camp genre in text → ballet default
        assert o.schedule.timezone == "Europe/Vienna"
        assert o.schedule.season == "2026"
        assert o.application.deadline == date(2026, 7, 4)  # the labelled deadline, not "24. Juli"
        assert [r.type for r in o.application.requirements] == ["none"]
        assert o.location is not None
        assert o.location.city == "Wiener Neustadt"
        assert o.location.country == "AT"


def test_deadline_missing_when_programm_absent() -> None:
    offerings = abc_dance._build_offerings(FORM_HTML, "", date(2026, 6, 1))
    assert len(offerings) == 3
    assert all(o.application.deadline is None for o in offerings)


def test_no_camps_yields_nothing() -> None:
    # A form variant with no camp checkboxes (e.g. before the editions are published).
    empty = "<html><body><h1>Anmeldung</h1><p>Bald verfügbar.</p></body></html>"
    assert abc_dance._build_offerings(empty, PROGRAMM_HTML, date(2026, 6, 1)) == []
