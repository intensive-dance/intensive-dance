"""Offline unit tests for the Turku Dance Camp scraper.

Pin the happy-path HTML fixture (five WP `<details>` accordions — four groups +
one add-on), asserting the single Offering's dates, open-topped age, levels,
genres, four Sessions, seven labelled EUR prices (incl. the regression-prone
Lite sub-tier qualifier mapping), and the degraded-fixture ValueError.
No network.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import turku_dance_camp as m

_HAPPY = """
<html><body>
<h1>Turku Dance Camp</h1>
<p>Turku Dance Camp will take place from Sunday 26 to Friday 31 July 2026 in
Turku, Finland. The six-day intensive will finish with a performance at Sigyn
Hall and a dinner gala at Turku Castle.</p>
<details><summary>Standard</summary><p>The Standard Group is meant for all
motivated dancers aged 13 (b. 2013) and up, including adults. Included: Daily
classes of ballet, repertoire, contemporary and body conditioning. Price
400,00€</p></details>
<details><summary>Intensive</summary><p>Intensive Group is meant for all
motivated dancers aged 15 and up, including professionals and
pre-professionals. Price: 400,00€</p></details>
<details><summary>Lite</summary><p>a lighter option for all adults and young
dancers (born latest 2013). The Lite package includes one class of each per day
for the duration of five days, 26 to 30 July. Price: 240,00€ for all classes OR
180,00€ for only ballet or 150,00€ for only contemporary classes</p></details>
<details><summary>Children's course</summary><p>For future talents aged 10–12
(b. 2016–2014) we offer a course of ballet and repertoire. Price
220,00€</p></details>
<details><summary>Choreography workshop</summary><p>Top up your Standard,
Intensive or Lite camp package. 100,00€ for all classes or 30,00€ per class if
bought separately</p></details>
</body></html>
"""

_DEGRADED = "<html><body><h1>Turku Dance Camp</h1><p>See you next summer!</p></body></html>"


def _build() -> m.Offering:
    return m._build_offering(_HAPPY)


# -- camp-level assertions ---------------------------------------------------


def test_dates_and_id():
    off = _build()
    assert off.id == "turku-dance-camp/2026"
    assert off.title == "Turku Dance Camp 2026"
    assert (off.schedule.start, off.schedule.end) == (date(2026, 7, 26), date(2026, 7, 31))
    assert off.schedule.season == "2026"


def test_location():
    off = _build()
    assert off.location is not None
    assert off.location.city == "Turku"
    assert off.location.country == "FI"
    assert off.schedule.timezone == "Europe/Helsinki"


def test_age_open_topped():
    off = _build()
    assert off.age_range is not None
    assert off.age_range == {"min": 10}
    assert "max" not in off.age_range


def test_level_and_genres():
    off = _build()
    assert off.level == ["open", "pre-professional"]
    assert off.genres == ["classical", "contemporary", "repertoire"]


# -- sessions ----------------------------------------------------------------


def test_session_count_excludes_choreography():
    off = _build()
    assert len(off.schedule.sessions) == 4
    labels = [s.label for s in off.schedule.sessions]
    assert "Choreography workshop" not in labels


def test_session_age_ranges():
    off = _build()
    ages = {s.label: s.age_range for s in off.schedule.sessions}
    assert ages["Standard"] == {"min": 13}
    assert ages["Intensive"] == {"min": 15}
    assert ages["Lite"] is None
    assert ages["Children's course"] == {"min": 10, "max": 12}


# -- prices ------------------------------------------------------------------


def test_price_count():
    off = _build()
    assert len(off.prices) == 7


def test_standard_and_intensive_prices():
    off = _build()
    by_label = {p.label: p.amount for p in off.prices}
    assert by_label["Standard"] == 400.0
    assert by_label["Intensive"] == 400.0


def test_lite_qualifier_mapping():
    """The Lite sub-tier qualifier is the regression-prone parse — assert all three."""
    off = _build()
    by_label = {p.label: p.amount for p in off.prices}
    assert by_label["Lite — all classes"] == 240.0
    assert by_label["Lite — ballet only"] == 180.0
    assert by_label["Lite — contemporary only"] == 150.0


def test_children_and_addon_prices():
    off = _build()
    by_label = {p.label: p.amount for p in off.prices}
    assert by_label["Children's course"] == 220.0
    assert by_label["Choreography workshop (add-on)"] == 100.0


def test_all_prices_eur():
    off = _build()
    for p in off.prices:
        assert p.currency == "EUR"


# -- degraded ----------------------------------------------------------------


def test_raises_without_dates():
    with pytest.raises(ValueError):
        m._build_offering(_DEGRADED)
