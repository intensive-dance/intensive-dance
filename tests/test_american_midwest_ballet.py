"""Offline tests for the American Midwest Ballet summer scraper.

Inline `content.rendered` snippets mirror the real WP page structure: the program
cards, the June camps, the teen/adult range, the August two-week series with its
per-track pricing, and the two out-of-scope cards (Primary Dance creative movement,
Day of Dance) that must NOT be emitted.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import american_midwest_ballet as amb

# Trimmed but structurally faithful copy of the page's content.rendered.
RENDERED = """
<h1>2026 Summer Classes</h1>
<p><strong>June Primary Dance (Ages 3-5)</strong></p>
<h4>June Children&#8217;s programming</h4>
<p><strong>June Primary Dance</strong>: A three-week series in which movement,
music, and imagination unite for dancers ages 3-5.</p>
<p>Dates: Saturday, June 13, 2026 Saturday, June 20, 2026 Saturday, June 27, 2026</p>
<p>Cost: $36 for all three sessions</p>
<p>Registration deadline: June 1, 2026</p>
<p><strong>June Children's Summer Dance Camps</strong>: A magical combination of
storytelling and dance for dancers ages 6-9. Each themed camp starts with a ballet
class, followed by a snack, ballet-inspired craft, and studio performance.</p>
<p>9:45-11:45 am</p>
<p>Camps*: Saturday, June 13, 2026 &#8211; Firebird Saturday, June 20, 2026 &#8211;
Swan Lake Saturday, June 27, 2026 &#8211; Wizard of Oz</p>
<p>Cost: Single camp: $40 Three camps: $100</p>
<p>Registration deadline: June 1, 2026</p>
<h4>June Teen and Adult Summer Series</h4>
<p><strong>June Teen/Adult Summer Series</strong>: A four-week series of classes for
beginning through advanced teen and adult students.</p>
<p>4 weeks: June 9 &#8211; July 1, 2026</p>
<p>Adult Beginning Tap (ages 18+) Cost: $60 (4 total classes over 4 weeks)</p>
<p>Teen Beginning Ballet (ages 11+) Cost: $60 (4 total classes over 4 weeks)</p>
<p>Adult Int/Adv Ballet (ages 18+) Cost: $60 (4 total classes over 4 weeks)</p>
<p>These are a series, so dancers must register by June 1.</p>
<h4>August Summer Series 2026</h4>
<p>Week 1: August 17-20, 2026 Week 2: August 24-27, 2026</p>
<p>Child Ballet 1-2 (Ages 6-8) Academy 2-3 Ballet (Ages 10+) Academy 4-6
Contemporary (Ages 12+)</p>
<p>Pricing:</p>
<p>Creative Movement Series (ages 3-5) Cost: $60 (4 classes total over 2 weeks)</p>
<p>Child 1-2 Series (ages 6-8) Cost: $100 (8 classes total over 2 weeks)</p>
<p>Child 3/Academy 1 Series (ages 8-12) Cost: $120 (8 classes total over 2 weeks)</p>
<p>Academy 2-3 Series (ages 10+) Cost: $300 (16 classes total over 2 weeks)</p>
<p>Academy 4-6 Series (ages 12+) Cost: $300 (16 classes total over 2 weeks)</p>
<p>Adult Classes (ages 18+) Mon Beginning Ballet; $30 (2 classes total over 2 weeks)</p>
<h4>Day of Dance 2026</h4>
<p>Day of Dance is our annual celebration, with a variety of free classes! This
year's day of dance will be Saturday, August 15! Watch this page for registration.</p>
"""

TODAY = date(2026, 6, 1)


def _by_id(offerings):
    return {o.id.split("/")[1]: o for o in offerings}


def test_emits_three_ballet_programs_only():
    offerings = amb._build_offerings(RENDERED, TODAY)
    slugs = {o.id.split("/")[1] for o in offerings}
    assert slugs == {
        "june-childrens-dance-camps-2026",
        "june-teen-adult-summer-series-2026",
        "august-summer-series-2026",
    }
    # Primary Dance (creative movement, no ballet) and Day of Dance are dropped.


def test_childrens_camps():
    o = _by_id(amb._build_offerings(RENDERED, TODAY))["june-childrens-dance-camps-2026"]
    assert o.title == "June Children's Summer Dance Camps 2026"
    assert o.genres == ["classical"]
    assert o.age_range == {"min": 6, "max": 9}
    # Start is the first camp, NOT the June 1 registration deadline.
    assert o.schedule.start == date(2026, 6, 13)
    assert o.schedule.end == date(2026, 6, 27)
    assert {(p.amount, p.label) for p in o.prices} == {
        (40.0, "Single camp"),
        (100.0, "All three camps"),
    }
    assert o.application.deadline == date(2026, 6, 1)
    assert o.location is not None and o.location.city == "Council Bluffs"


def test_teen_adult_series():
    o = _by_id(amb._build_offerings(RENDERED, TODAY))["june-teen-adult-summer-series-2026"]
    assert o.genres == ["classical"]
    assert o.age_range == {"min": 11, "max": None}
    assert o.schedule.start == date(2026, 6, 9)
    assert o.schedule.end == date(2026, 7, 1)
    assert [p.amount for p in o.prices] == [60.0]
    # "register by June 1" carries no year — taken from the series year.
    assert o.application.deadline == date(2026, 6, 1)


def test_august_series_tracks_and_genres():
    o = _by_id(amb._build_offerings(RENDERED, TODAY))["august-summer-series-2026"]
    assert o.genres == ["classical", "contemporary"]
    assert o.age_range == {"min": 3, "max": None}
    assert o.schedule.start == date(2026, 8, 17)
    assert o.schedule.end == date(2026, 8, 27)
    # Ballet-containing tracks priced; non-ballet Creative Movement excluded.
    labels = {p.label: p.amount for p in o.prices}
    assert labels == {
        "Child 1-2 Series": 100.0,
        "Child 3/Academy 1 Series": 120.0,
        "Academy 2-3 Series": 300.0,
        "Academy 4-6 Series": 300.0,
        "Adult class": 30.0,
    }
    assert o.application.deadline is None
