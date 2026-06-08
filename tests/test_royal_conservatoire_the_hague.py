"""Unit tests for the Royal Conservatoire The Hague scraper (two-page HTML + ld+json)."""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import royal_conservatoire_the_hague as rc


# Minimal ld+json page that mirrors the real site structure.
_MAIN_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebPage",
   "description":"The Dance Intensive is a six day programme ( 24-29th August 2026 ), for dance students from 12-25 years old, aimed at presenting a concise version of our school curriculum with prominent teachers.",
   "headline":"International Dance Intensive",
   "url":"https://www.koncon.nl/en/dance-intensive"}
]}
</script>
</head><body>International Dance Intensive</body></html>
"""

# Registration sub-page text mirroring the key sections.
_REG_HTML = """
<html><body>
<p>All applications must be received before July 1st, 2026.</p>
<p>Video link (YouTube only): 6-minute maximum, ballet + contemporary class material (centre work; no barre)</p>
<p>Advanced &amp; Pre-professional Dance Intensive course fee: € 550</p>
<p>Royal Conservatoire student fee: € 350</p>
<p>Applicants must be dancers or choreographers with an advanced, pre-professional or professional level between the ages of 12 and 25 years old.</p>
</body></html>
"""

# Edge case: no dated edition announced yet (description has no date range).
_MAIN_HTML_NO_DATE = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebPage",
   "description":"The Dance Intensive is an annual programme for dance students.",
   "headline":"International Dance Intensive",
   "url":"https://www.koncon.nl/en/dance-intensive"}
]}
</script>
</head><body>International Dance Intensive</body></html>
"""

# Edge case: ld+json missing entirely (returns empty offerings).
_MAIN_HTML_NO_LD = "<html><body>Some page content without ld+json</body></html>"


def test_parse_dates_standard():
    assert rc._parse_dates("24-29th August 2026") == (date(2026, 8, 24), date(2026, 8, 29))


def test_parse_dates_both_ordinals():
    assert rc._parse_dates("24th-29th August 2026") == (date(2026, 8, 24), date(2026, 8, 29))


def test_parse_dates_absent():
    assert rc._parse_dates("no dates here") == (None, None)


def test_parse_age_range():
    assert rc._parse_age_range("dance students from 12-25 years old") == {"min": 12, "max": 25}


def test_parse_age_range_absent():
    assert rc._parse_age_range("no age stated") is None


def test_parse_level():
    text = "advanced, pre-professional or professional level"
    levels = rc._parse_level(text)
    assert "advanced" in levels
    assert "pre-professional" in levels
    assert "professional" in levels


def test_parse_level_absent():
    assert rc._parse_level("no level information here") == []


def test_parse_prices():
    text = (
        "Advanced & Pre-professional Dance Intensive course fee:  € 550 "
        "Royal Conservatoire student fee:  € 350"
    )
    prices = rc._parse_prices(text)
    assert len(prices) == 2
    amounts = {p.label: p.amount for p in prices if p.label is not None}
    assert amounts.get("Advanced & Pre-professional Dance Intensive course fee") == 550.0
    assert amounts.get("Royal Conservatoire student fee") == 350.0
    assert all(p.currency == "EUR" for p in prices)
    assert all("tuition" in p.includes for p in prices)


def test_parse_prices_absent():
    assert rc._parse_prices("No fees mentioned here.") == []


def test_parse_deadline():
    text = "All applications must be received before July 1st, 2026."
    assert rc._parse_deadline(text) == date(2026, 7, 1)


def test_parse_deadline_absent():
    assert rc._parse_deadline("No deadline information.") is None


def test_parse_requirements_video():
    text = "Video link (YouTube only): 6-minute maximum, ballet + contemporary"
    reqs = rc._parse_requirements(text)
    assert len(reqs) == 1
    assert reqs[0].type == "video"
    assert reqs[0].specificity == "specific"


def test_parse_requirements_absent():
    assert rc._parse_requirements("No requirements stated.") == []


def test_ld_description_extracts_from_webpage_node():
    desc = rc._ld_description(_MAIN_HTML)
    assert "24-29th August 2026" in desc
    assert "12-25 years old" in desc


def test_ld_description_absent():
    assert rc._ld_description(_MAIN_HTML_NO_LD) == ""


def test_build_offerings_happy_path():
    offerings = rc._build_offerings(_MAIN_HTML, _REG_HTML, date.today())
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "royal-conservatoire-the-hague/international-dance-intensive-2026"
    assert o.title == "International Dance Intensive 2026"
    assert o.schedule.start == date(2026, 8, 24)
    assert o.schedule.end == date(2026, 8, 29)
    assert o.schedule.season == "2026"
    assert o.schedule.timezone == "Europe/Amsterdam"
    assert "classical" in o.genres
    assert "contemporary" in o.genres
    assert o.age_range == {"min": 12, "max": 25}
    assert o.organization.slug == "royal-conservatoire-the-hague"
    assert o.organization.country == "NL"
    assert o.location is not None
    assert o.location.city == "The Hague"
    assert o.location.country == "NL"
    assert len(o.prices) == 2
    assert o.application.deadline == date(2026, 7, 1)
    assert len(o.application.requirements) == 1
    assert o.application.requirements[0].type == "video"


def test_build_offerings_no_date_returns_empty():
    # If the description contains no date range, no offering is emitted.
    offerings = rc._build_offerings(_MAIN_HTML_NO_DATE, _REG_HTML, date.today())
    assert offerings == []


def test_build_offerings_no_ld_returns_empty():
    offerings = rc._build_offerings(_MAIN_HTML_NO_LD, "", date.today())
    assert offerings == []


def test_dates_note():
    note = rc._dates_note("The programme runs 24-29th August 2026 in The Hague.")
    assert note is not None
    assert "24" in note
    assert "August" in note
    assert "2026" in note
