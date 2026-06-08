"""Offline tests for the NDT Summer Intensive scraper.

All tests feed inline HTML/text to the pure parsing helpers — no network calls.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers.ndt_summer_intensive import (
    _age_range,
    _application_dates,
    _build_offerings,
    _course_dates,
    _genres,
    _prices,
)

# ---------------------------------------------------------------------------
# Minimal info-page HTML containing all key facts for 2026
# ---------------------------------------------------------------------------
_INFO_HTML = """\
<!DOCTYPE html>
<html>
<head><title>NDT Summer Intensive</title></head>
<body>
<h1>NDT Summer Intensive</h1>
<p>27 July - 8 August 2026</p>
<p>GROW AND DEVELOP ALL ASPECTS OF YOUR DANCE TALENT</p>
<p>Take part in a professional training programme during our annual NDT Summer
Intensive as one of 60 young dancers from all over the world. In two intensive
weeks, these young professionals – ages 16 to 25 (X/M/F) – will work together
with our dancers, rehearsers and choreographers.</p>
<ul>
  <li>NDT Summer Intensive 2026 takes place from Monday 27 July – Saturday
      8 August in The Hague (The Netherlands);</li>
  <li>The course tuition is €1500,- (including VAT, excluding accommodation costs).</li>
  <li>Optional accommodation at The Social Hub is available for €1150,-
      (including VAT and city taxes).</li>
  <li>We are no longer accepting audition applications for NDT Summer Intensive 2026</li>
</ul>
<p>NDT Summer Intensive is specially created for (pre)professional ballet and/or
contemporary trained dancers aged 16 – 25 years old (X/F/M).</p>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Minimal audition-procedure page HTML
# ---------------------------------------------------------------------------
_AUDITION_HTML = """\
<!DOCTYPE html>
<html>
<body>
<h1>Audition procedure NDT Summer Intensive 2026</h1>
<h2>Important dates</h2>
<p>12 January 2026  Application opens at 10 AM (Amsterdam local time)</p>
<p>9 February 2026  Application closes at 5 PM (Amsterdam local time)</p>
<p>8 April 2026  Announcement of results</p>
<p>27 July 2026  Start NDT Summer Intensive 2026</p>
<p>8 August 2026  End NDT Summer Intensive 2026</p>
<p>Maximum duration 6 minutes. The video should not contain pointe work.</p>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Edge-case: no year on the info page → no offering emitted
# ---------------------------------------------------------------------------
_NO_DATE_HTML = """\
<!DOCTYPE html>
<html>
<body>
<h1>NDT Summer Intensive</h1>
<p>Dates to be announced.</p>
<p>The course tuition is €1500,-.</p>
</body>
</html>
"""

_TODAY = date(2026, 6, 8)


def test_happy_path_emits_one_offering():
    offerings = _build_offerings(_INFO_HTML, _AUDITION_HTML, _TODAY)
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "ndt-summer-intensive/2026"
    assert o.title == "NDT Summer Intensive 2026"


def test_schedule():
    offerings = _build_offerings(_INFO_HTML, _AUDITION_HTML, _TODAY)
    o = offerings[0]
    assert o.schedule.start == date(2026, 7, 27)
    assert o.schedule.end == date(2026, 8, 8)
    assert o.schedule.season == "2026"
    assert o.schedule.timezone == "Europe/Amsterdam"


def test_age_range():
    offerings = _build_offerings(_INFO_HTML, _AUDITION_HTML, _TODAY)
    o = offerings[0]
    assert o.age_range is not None
    assert o.age_range["min"] == 16
    assert o.age_range["max"] == 25


def test_genres_contemporary():
    offerings = _build_offerings(_INFO_HTML, _AUDITION_HTML, _TODAY)
    o = offerings[0]
    assert "contemporary" in o.genres


def test_prices():
    offerings = _build_offerings(_INFO_HTML, _AUDITION_HTML, _TODAY)
    o = offerings[0]
    assert len(o.prices) == 2  # noqa: PLR2004
    tuition = next(p for p in o.prices if "tuition" in p.includes)
    assert tuition.amount == 1500.0  # noqa: PLR2004
    assert tuition.currency == "EUR"
    accom = next(p for p in o.prices if "accommodation" in p.includes)
    assert accom.amount == 1150.0  # noqa: PLR2004


def test_application_dates():
    offerings = _build_offerings(_INFO_HTML, _AUDITION_HTML, _TODAY)
    o = offerings[0]
    assert o.application.opens_at == date(2026, 1, 12)
    assert o.application.deadline == date(2026, 2, 9)


def test_application_status_closed_after_deadline():
    # Scraping after deadline → status=closed
    offerings = _build_offerings(_INFO_HTML, _AUDITION_HTML, date(2026, 3, 1))
    o = offerings[0]
    assert o.application.status == "closed"


def test_video_requirement():
    offerings = _build_offerings(_INFO_HTML, _AUDITION_HTML, _TODAY)
    o = offerings[0]
    reqs = o.application.requirements
    assert len(reqs) == 1
    req = reqs[0]
    assert req.type == "video"
    assert req.specificity == "specific"
    assert req.description is not None
    assert "6 minutes" in req.description


def test_no_date_emits_nothing():
    """If the info page has no dated edition, no Offering is emitted."""
    offerings = _build_offerings(_NO_DATE_HTML, "", _TODAY)
    assert offerings == []


def test_location():
    offerings = _build_offerings(_INFO_HTML, _AUDITION_HTML, _TODAY)
    o = offerings[0]
    assert o.location is not None
    assert o.location.city == "The Hague"
    assert o.location.country == "NL"


# ---------------------------------------------------------------------------
# Unit tests for individual helpers
# ---------------------------------------------------------------------------


def test_course_dates_cross_month():
    start, end = _course_dates("27 July - 8 August 2026")
    assert start == date(2026, 7, 27)
    assert end == date(2026, 8, 8)


def test_course_dates_dash_variant():
    start, end = _course_dates("Monday 27 July – Saturday 8 August 2026")
    assert start == date(2026, 7, 27)
    assert end == date(2026, 8, 8)


def test_age_range_helper():
    result = _age_range("dancers aged 16 – 25 years old")
    assert result == {"min": 16, "max": 25}


def test_age_range_none():
    assert _age_range("no ages mentioned") is None


def test_genres_defaults_to_contemporary():
    genres = _genres("A unique contemporary dance experience.")
    assert genres == ["contemporary"]


def test_genres_no_classical_from_mere_mention():
    # "ballet" should not add classical if the source doesn't say "classical ballet"
    genres = _genres("(pre)professional ballet and/or contemporary trained dancers")
    assert "contemporary" in genres
    assert "classical" not in genres


def test_prices_tuition_only():
    """When the accommodation amount is garbled, only the tuition is returned."""
    text = "The course tuition is €1500,- (including VAT)."
    prices = _prices(text)
    assert len(prices) == 1
    assert prices[0].amount == 1500.0  # noqa: PLR2004
    assert "tuition" in prices[0].includes


def test_application_dates_helper():
    text = "12 January 2026 Application opens at 10 AM\n9 February 2026 Application closes at 5 PM"
    opens, deadline = _application_dates(text)
    assert opens == date(2026, 1, 12)
    assert deadline == date(2026, 2, 9)
