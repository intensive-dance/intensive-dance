"""Unit tests for the Nationaltheater Mannheim scraper (single-page HTML)."""

from __future__ import annotations

from datetime import date

from intensive_dance.models import VideoReq
from intensive_dance.scrapers import nationaltheater_mannheim as ntm

# ---------------------------------------------------------------------------
# Inline HTML snippet — mirrors the English INFORMATION block structure and
# the AUDITION PROCEDURE section from the real page (verified 2026-06-08).
# ---------------------------------------------------------------------------

_INFO_HTML = """
<html><body>
<div class="richtext" lang="en">
<ul>
<li><strong>Dates:</strong><br>Monday, July 13th – Sunday, July 19th 2026</li>
<li><strong>Location:</strong><br>Mannheim, Germany</li>
<li><strong>Registration opens:</strong><br>January 4th 2026, at 10.00 AM</li>
<li><strong>Registration closes:</strong><br>February 28th 2026, at 10.00 AM
(Please note: registration may close earlier once maximum number of applications is reached.)</li>
<li><strong>Announcement of selected participants:</strong><br>March 1st till March 30th 2026</li>
<li><strong>Tuition fee:</strong><br>€ 650,00 (including daily lunch, excluding accommodation)</li>
</ul>
<strong>+++ Application is closed +++</strong>
</div>
<div class="richtext" lang="en">
<strong>AUDITION PROCEDURE</strong>
We are excited that you would like to audition!
<strong>1. Audition requirements</strong>
To sign up, please send us an E-Mail with the following information:
<ul>
<li>attach a recent headshot so we can put a face to your name.</li>
<li>Share one video link (YouTube or Vimeo)</li>
<li>Include a Showreel (stage or studio) and 1 minute of improvisation.</li>
<li>Your video should be no longer than 3 minutes. Improvisation unedited, and danced to original music.</li>
</ul>
</div>
<div class="richtext" lang="en">
We are excited to announce the very first NTM Tanz Summer Intensive taking place from
July 13th to July 19th 2026! A unique opportunity for 25 professional dancers (ages 18+, X/M/F)
from around the world to experience a week of professional training, artistic exploration,
and creative exchange.
Under the guidance of Stephan Thoss, our company dancers, rehearsal directors,
and choreographers.
Every day will start with a technical class, alternating between contemporary, ballet,
and improvisation.
All participants will take part of a new creation led by: Luis Tena Torres and Albert Galindo,
dancers and choreographers with international experience.
</div>
</body></html>
"""

# Edge case: no dates in page → should return empty list.
_NO_DATES_HTML = """
<html><body>
<div class="richtext" lang="en">
Summer Intensive coming soon — dates to be announced.
ages 18+ professional dancers
€ 650,00
headshot and video link required
</div>
</body></html>
"""

# Edge case: application open (registration not yet closed).
_OPEN_HTML = """
<html><body>
<div class="richtext" lang="en">
Monday, July 13th – Sunday, July 19th 2026
Registration opens: January 4th 2026
ages 18+
€ 650,00
headshot and video link required
</div>
</body></html>
"""


def test_date_range_cross_month_ordinal():
    # Page uses "July 13th – Sunday, July 19th 2026".
    assert ntm._date_range("Monday, July 13th – Sunday, July 19th 2026") == (
        date(2026, 7, 13),
        date(2026, 7, 19),
    )


def test_date_range_absent():
    assert ntm._date_range("no dated edition yet announced") == (None, None)


def test_age_range_open_top():
    # "ages 18+" → min 18, max None (open-ended upper bound).
    result = ntm._age_range("25 professional dancers (ages 18+, X/M/F)")
    assert result is not None
    assert result["min"] == 18
    assert result["max"] is None


def test_age_range_absent():
    assert ntm._age_range("no age stated here") is None


def test_genres_classical_and_contemporary():
    text = "alternating between contemporary, ballet, and improvisation"
    genres = ntm._genres(text)
    assert "classical" in genres
    assert "contemporary" in genres


def test_genres_default_when_no_keywords():
    # Fallback default includes both classical and contemporary.
    genres = ntm._genres("no genre hints here")
    assert "classical" in genres
    assert "contemporary" in genres


def test_levels_professional():
    text = "25 professional dancers (ages 18+, X/M/F)"
    assert "professional" in ntm._levels(text)


def test_levels_empty_when_no_keywords():
    assert ntm._levels("some generic text about training") == []


def test_prices_eur_european_notation():
    # "€ 650,00 (including daily lunch, excluding accommodation)"
    prices = ntm._prices("Tuition fee: € 650,00 (including daily lunch, excluding accommodation)")
    assert len(prices) == 1
    p = prices[0]
    assert p.amount == 650.0
    assert p.currency == "EUR"
    assert "tuition" in p.includes
    assert "meals" in p.includes


def test_prices_absent_when_no_fee():
    assert ntm._prices("no fee information here") == []


def test_app_status_closed():
    assert ntm._app_status("+++ Application is closed +++") == "closed"


def test_app_status_none_when_not_stated():
    assert ntm._app_status("some generic text") is None


def test_deadline_february():
    text = "Registration closes: February 28th 2026, at 10.00 AM"
    assert ntm._deadline(text) == date(2026, 2, 28)


def test_deadline_absent():
    assert ntm._deadline("no deadline mentioned here") is None


def test_requirements_headshot_and_video():
    text = "attach a recent headshot — Share one video link (YouTube or Vimeo) Showreel"
    reqs = ntm._requirements(text)
    types = [r.type for r in reqs]
    assert "headshot" in types
    assert "video" in types
    video = next(r for r in reqs if r.type == "video")
    assert isinstance(video, VideoReq)
    assert video.specificity == "specific"


def test_requirements_empty_when_no_hints():
    # No headshot or video keyword → empty list (unknown/not stated).
    assert ntm._requirements("send an email to register") == []


def test_teachers_all_named():
    text = (
        "Under the guidance of Stephan Thoss, rehearsal directors. "
        "New creation led by Luis Tena Torres and Albert Galindo."
    )
    teachers = ntm._teachers(text)
    names = [t.name for t in teachers]
    assert "Stephan Thoss" in names
    assert "Luis Tena Torres" in names
    assert "Albert Galindo" in names
    thoss = next(t for t in teachers if t.name == "Stephan Thoss")
    assert thoss.role is not None
    assert "Artistic Director" in thoss.role


def test_teachers_empty_when_no_names():
    assert ntm._teachers("no named teachers here") == []


def test_build_offerings_happy_path():
    offerings = ntm._build_offerings(_INFO_HTML, date(2026, 6, 8))
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "nationaltheater-mannheim/summer-intensive-2026"
    assert o.title == "NTM Tanz Summer Intensive 2026"
    assert o.schedule.start == date(2026, 7, 13)
    assert o.schedule.end == date(2026, 7, 19)
    assert o.schedule.season == "2026"
    assert o.schedule.timezone == "Europe/Berlin"
    assert o.organization.slug == "nationaltheater-mannheim"
    assert o.organization.country == "DE"
    assert o.location is not None
    assert o.location.city == "Mannheim"
    assert o.location.country == "DE"
    assert o.application.status == "closed"
    assert o.application.deadline == date(2026, 2, 28)
    # Requirements: headshot + video
    req_types = [r.type for r in o.application.requirements]
    assert "headshot" in req_types
    assert "video" in req_types
    # Price
    assert len(o.prices) == 1
    assert o.prices[0].amount == 650.0
    assert o.prices[0].currency == "EUR"
    # Teachers
    names = [t.name for t in o.teachers]
    assert "Stephan Thoss" in names
    # Age range: 18+ open-topped
    assert o.age_range is not None
    assert o.age_range["min"] == 18
    assert o.age_range["max"] is None
    # Level
    assert "professional" in o.level
    # Genres
    assert "classical" in o.genres
    assert "contemporary" in o.genres


def test_build_offerings_no_dates_returns_empty():
    offerings = ntm._build_offerings(_NO_DATES_HTML, date(2026, 6, 8))
    assert offerings == []
