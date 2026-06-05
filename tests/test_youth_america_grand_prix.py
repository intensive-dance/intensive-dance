"""Unit tests for the Youth America Grand Prix (YAGP) scraper.

These pin the parse of the embedded `javascript_array` stop blobs from the
international-schedule page: the stop markup is duplicated, so dedupe by name;
cross-month and same-month date ranges both resolve; only European competition
stops survive (US/Asia dropped by country, the German "Job Fair" dropped as a
non-competition); and the flat $125 USD registration fee + DanceCompGenie URL
land on every emitted Offering. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import youth_america_grand_prix as yagp


def _blob(name: str, the_date: str) -> str:
    return f'<script>var javascript_array = {{"name":"{name}","date":"{the_date}"}};</script>'


# Each stop's markup is duplicated on the real page; reproduce that here so the
# dedupe is exercised. A cross-month stop (Paris), a same-month stop (Barcelona),
# the German Job Fair, and an out-of-scope US stop, all inside a 2026-2027 page.
_HTML = (
    "<h1>YAGP 2026-2027 International Locations &amp; Dates</h1>"
    + _blob("PARIS, FRANCE", "October 29 - November 1, 2026")
    + _blob("PARIS, FRANCE", "October 29 - November 1, 2026")
    + _blob("BARCELONA, SPAIN", "December 1 - 6, 2026")
    + _blob("STUTTGART, GERMANY (JOB FAIR)", "February 13 - 14, 2027")
    + _blob("TAMPA, FLORIDA (FINALS)", "April 26 - May 2, 2027")
)

_TODAY = date(2026, 6, 5)


def test_emits_only_european_competition_stops():
    offerings = yagp._build_offerings(_HTML, _TODAY)
    ids = {o.id for o in offerings}
    assert ids == {
        "youth-america-grand-prix/paris-2026-27",
        "youth-america-grand-prix/barcelona-2026-27",
    }


def test_dedupes_repeated_stop_markup():
    offerings = yagp._build_offerings(_HTML, _TODAY)
    paris = [o for o in offerings if o.id.endswith("paris-2026-27")]
    assert len(paris) == 1


def test_cross_month_and_same_month_ranges():
    offerings = {o.id: o for o in yagp._build_offerings(_HTML, _TODAY)}
    paris = offerings["youth-america-grand-prix/paris-2026-27"]
    assert paris.schedule.start == date(2026, 10, 29)
    assert paris.schedule.end == date(2026, 11, 1)  # month carries to the end day
    barcelona = offerings["youth-america-grand-prix/barcelona-2026-27"]
    assert barcelona.schedule.start == date(2026, 12, 1)
    assert barcelona.schedule.end == date(2026, 12, 6)


def test_competition_fields_and_fee():
    paris = yagp._build_offerings(_HTML, _TODAY)[0]
    assert paris.kind == "competition"
    assert paris.title == "YAGP Paris, France"
    assert paris.schedule.season == "2026-27"
    assert paris.location is not None
    assert (paris.location.city, paris.location.country) == ("Paris", "FR")
    assert paris.location.venue is None  # the page gives no street venue
    assert [(p.amount, p.currency) for p in paris.prices] == [(125.0, "USD")]
    assert paris.application.status is None  # not exposed programmatically
    assert paris.application.url == yagp.REGISTRATION_URL


def test_drops_ended_cycle():
    html = _blob("PARIS, FRANCE", "October 29 - November 1, 2026")
    assert yagp._build_offerings(html, date(2026, 11, 2)) == []


def test_date_range_helper_handles_new_year_straddle():
    span = yagp._date_range("December 30 - January 2, 2027")
    assert span == (date(2026, 12, 30), date(2027, 1, 2))
