"""Unit tests for the IntoDance (Athens) scraper.

Offline: inline Elementor `content.rendered` snippets mirroring the live Events
page — each event is a self-contained section with one `hfe-infocard` (title), a
date `heading`, and `text-editor` (location). They pin the day-first date range
with a trailing year, the Athens location, the classical-default genre, the
out-of-scope drop (the Tokyo academy *audition*), and the year-less fallback.
No network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import intodance_athens as ida

# One in-scope event (Athens intensive) + one out-of-scope (Tokyo academy audition),
# each an Elementor section holding a single info-card, a date heading, and a
# location text-editor — the live page's shape.
EVENTS_HTML = """
<div class="elementor elementor-386">
  <section class="elementor-section" data-id="aaa">
    <div class="elementor-widget" data-widget_type="heading.default">
      <div class="elementor-widget-container">
        <h2 class="elementor-heading-title">29 June - 3 july 2026</h2>
      </div>
    </div>
    <div class="elementor-widget" data-widget_type="hfe-infocard.default">
      <div class="elementor-widget-container">
        <h3 class="hfe-info-card-title">Summer Intensive</h3>
        <p class="hfe-info-card-text">Train with INTERNATIONAL BALLET STARS</p>
      </div>
    </div>
    <div class="elementor-widget" data-widget_type="text-editor.default">
      <div class="elementor-widget-container"><p>Athens, Greece</p></div>
    </div>
  </section>
  <section class="elementor-section" data-id="bbb">
    <div class="elementor-widget" data-widget_type="heading.default">
      <div class="elementor-widget-container">
        <h2 class="elementor-heading-title">2026年　8月8日（土）</h2>
      </div>
    </div>
    <div class="elementor-widget" data-widget_type="hfe-infocard.default">
      <div class="elementor-widget-container">
        <h3 class="hfe-info-card-title">イタリア ミラノ バレエ学校 入学オーディション</h3>
        <p class="hfe-info-card-text">［ACCADEMIA UCRAINA DI BALLETTO MILANO］</p>
      </div>
    </div>
    <div class="elementor-widget" data-widget_type="text-editor.default">
      <div class="elementor-widget-container"><p>スタジオアーキタンツ 田町駅</p></div>
    </div>
  </section>
</div>
"""


def test_only_athens_intensive_is_emitted():
    offerings = ida._build_offerings(EVENTS_HTML, date(2026, 1, 1))
    # The Tokyo academy audition is dropped — only the Athens intensive remains.
    assert len(offerings) == 1
    assert offerings[0].id == "intodance-athens/summer-intensive-2026"


def test_offering_fields():
    [o] = ida._build_offerings(EVENTS_HTML, date(2026, 1, 1))
    assert o.title == "Summer Intensive 2026"
    assert o.genres == ["classical"]
    assert o.schedule.season == "2026"
    assert (o.schedule.start, o.schedule.end) == (date(2026, 6, 29), date(2026, 7, 3))
    assert o.schedule.timezone == "Europe/Athens"
    assert o.organization.slug == "intodance-athens"
    assert o.location is not None
    assert (o.location.city, o.location.country) == ("Athens", "GR")
    # Nothing about ages/prices/teachers/requirements is stated → kept empty, not invented.
    assert o.age_range is None
    assert o.prices == []
    assert o.teachers == []
    assert o.application.requirements == []
    assert o.application.url == "https://into-dance.com/events/"


def test_dates_day_first_range_with_trailing_year():
    assert ida._dates("29 June - 3 july 2026") == (date(2026, 6, 29), date(2026, 7, 3))
    assert ida._dates("14 - 18 July 2025") == (date(2025, 7, 14), date(2025, 7, 18))


def test_dates_without_year_returns_none():
    assert ida._dates("29 June - 3 July") == (None, None)


def test_genres_adds_contemporary_when_card_says_so():
    assert ida._genres("Summer Intensive classical and contemporary") == [
        "classical",
        "contemporary",
    ]
    assert ida._genres("Summer Intensive") == ["classical"]


def test_yearless_section_emits_unknown_season():
    html = """
    <div class="elementor">
      <section data-id="ccc">
        <div data-widget_type="heading.default">
          <div class="elementor-widget-container"><h2>Coming soon</h2></div>
        </div>
        <div data-widget_type="hfe-infocard.default">
          <div class="elementor-widget-container"><h3>Winter Intensive</h3></div>
        </div>
      </section>
    </div>
    """
    [o] = ida._build_offerings(html, date(2026, 1, 1))
    assert o.id == "intodance-athens/summer-intensive-unknown"
    assert o.title == "Winter Intensive"
    assert o.schedule.season == "unknown"
    assert (o.schedule.start, o.schedule.end) == (None, None)
    # No location text-editor → defaults to the org's Athens base.
    assert o.location is not None
    assert o.location.city == "Athens"
