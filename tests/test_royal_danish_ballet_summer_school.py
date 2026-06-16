"""Unit tests for the Royal Danish Ballet Summer School scraper (EN HTML)."""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import royal_danish_ballet_summer_school as rdb

# A trimmed slice of the live English page covering every field the scraper reads.
HTML = """
<html><body>
<h1>The Royal Danish Ballet Summer School</h1>
<p>The Royal Danish Theatre offer an intensive two-week summer course for young
dancers aged 12-21 in collaboration with Tanz Akademie Zürich.</p>
<p>The training includes: Ballet class, Repertoire, Bournonville, Contemporary.
The course is selective and all applicants must upload a link to an audition video.</p>
<p>Dates: 20 July – 1 August 2026</p>
<p>The entrance of the studios is at Tordenskjoldsgade 8, 1055 Copenhagen K.</p>
<p>The price for both weeks is DKK 12.500 incl. VAT.</p>
<p>Lunch served at the theatre: DKK 500 per week (all programmes)</p>
<p>The price is DKK 5.995 DKK per student per week (plus 150 DKK in administration fees).</p>
<p>The deadline for application is 20 March 2026.</p>
</body></html>
"""


def test_build_offering_full():
    o = rdb._build_offering(HTML)
    assert o is not None
    assert o.id == "royal-danish-ballet-summer-school/summer-school-2026"
    assert o.lifecycle == "scheduled"
    assert o.schedule.start == date(2026, 7, 20)
    assert o.schedule.end == date(2026, 8, 1)
    assert o.age_range == {"min": 12, "max": 21}
    # The page states a deadline, not a status — status stays unset.
    assert o.application.deadline == date(2026, 3, 20)
    assert o.application.status is None


def test_date_range_shared_year():
    # The year appears once, trailing — it applies to both day-month pairs.
    assert rdb._date_range("Dates: 20 July – 1 August 2026") == (
        date(2026, 7, 20),
        date(2026, 8, 1),
    )
    assert rdb._date_range("no dates here") == (None, None)


def test_genres_from_curriculum():
    text = "Ballet class, Repertoire, Bournonville, Contemporary, Pas de deux, Pilates"
    assert rdb._genres(text) == ["classical", "repertoire", "contemporary", "character"]


def test_prices_three_tiers():
    prices = rdb._prices(HTML)
    assert [(p.amount, p.currency, p.includes) for p in prices] == [
        (12500.0, "DKK", ["tuition"]),
        (500.0, "DKK", ["meals"]),
        (5995.0, "DKK", ["accommodation"]),
    ]


def test_deadline_parsed():
    assert rdb._deadline(HTML) == date(2026, 3, 20)


def test_requirements_video():
    (req,) = rdb._requirements(HTML)
    assert req.type == "video"
    assert req.specificity == "unspecific"
    assert rdb._requirements("nothing about applying here") == []
