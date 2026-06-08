"""Unit tests for the Jiří Bubeníček Ballet Masterclasses scraper (Prague, CZ).

No network — all helpers are fed inline HTML/text snippets.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import PhotosReq, VideoReq
from intensive_dance.scrapers import bubenicek_masterclasses as bbm

# ---------------------------------------------------------------------------
# Inline HTML snippets — minimal but structurally representative.
# ---------------------------------------------------------------------------

_HOME_HTML = """
<html><body>
<h2>July 27 - August 8, 2026</h2>
<p>PRAGUE will be the place of our BUBENICEK BALLET MASTERCLASSES.
Over the course of 12 days, you will have the rare opportunity to
spend time with acclaimed dance teachers.
Ballet Class, Variations, Contemporary / Choreography Class, Repertoire.
</p>
</body></html>
"""

_HOME_HTML_NO_DATE = """
<html><body>
<p>Coming soon — dates TBC.</p>
</body></html>
"""

_TEAM_HTML = """
<html><body>
<h2>Jiří Bubeníček</h2><h2>Choreographer</h2>
<p>Former Principal Dancer with Semperoper Ballet and Hamburg Ballet.</p>
<h2>Sarah Lamb</h2><h2>PRINCIPAL DANCER</h2>
<p>PRINCIPAL AT THE ROYAL BALLET in London.</p>
<h2>Juliane Mathis</h2><h2>DANCER</h2>
<p>Former Coryphée Dancer at the Ballet de l'Opéra de Paris.</p>
<h2>Jean-Guillaume Bart</h2><h2>ÉTOILE</h2>
<p>TEACHER &amp; ETOILE AT THE OPERA NATIONAL DE PARIS.</p>
<h2>Arman Grigoryan</h2><h2>PRINCIPAL DANCER</h2>
<p>Zurich Ballet Principal.</p>
<h2>Nikos Kalivas</h2>
<p>Contemporary dance teacher.</p>
</body></html>
"""

_TEAM_HTML_PARTIAL = """
<html><body>
<h2>Jiří Bubeníček</h2><h2>Choreographer</h2>
<p>Founder of Les Ballets Bubeníček.</p>
</body></html>
"""

_FEE_HTML = """
<html><body>
<h2>TUITION FEE: 13 DAYS BUBENÍČEK BALLET MASTERCLASSES FOR 1.350 EUROS</h2>
<p>non-refundable deposit of 300€ must be made within 1 week. Full payment by July 1, 2026.</p>
</body></html>
"""

_FEE_HTML_NO_PRICE = """
<html><body>
<p>Tuition fee information coming soon.</p>
</body></html>
"""

_REGISTER_HTML = """
<html><body>
<p>Please note that all participants must be between the ages of 14 and 30.</p>
<p>Masterclasses are designed for advanced and professional level dancers.
This includes individuals who have completed at least one year of full-time training.</p>
<p>Please include a brief CV outlining your relevant experience, a headshot,
one photo in first arabesque, and one additional ballet photo.</p>
<p>Link to Classical Variation Video (Youtube) and Contemporary Variation video.</p>
</body></html>
"""


# ---------------------------------------------------------------------------
# _date_range
# ---------------------------------------------------------------------------


def test_date_range_cross_month():
    result = bbm._date_range("July 27 - August 8, 2026")
    assert result is not None
    start, end = result
    assert start == date(2026, 7, 27)
    assert end == date(2026, 8, 8)


def test_date_range_em_dash():
    result = bbm._date_range("July 27 – August 8, 2026")
    assert result is not None
    start, end = result
    assert start == date(2026, 7, 27)
    assert end == date(2026, 8, 8)


def test_date_range_absent():
    assert bbm._date_range("Dates TBC") is None


# ---------------------------------------------------------------------------
# _genres
# ---------------------------------------------------------------------------


def test_genres_classical_contemporary_repertoire():
    text = "Ballet Class, Variations, Contemporary / Choreography Class, Repertoire"
    genres = bbm._genres(text)
    assert "classical" in genres
    assert "contemporary" in genres
    assert "repertoire" in genres


def test_genres_default_when_empty():
    assert bbm._genres("") == ["classical"]


# ---------------------------------------------------------------------------
# _age_range
# ---------------------------------------------------------------------------


def test_age_range_between_syntax():
    assert bbm._age_range("participants must be between the ages of 14 and 30") == {
        "min": 14,
        "max": 30,
    }


def test_age_range_absent():
    assert bbm._age_range("no age information here") is None


# ---------------------------------------------------------------------------
# _level
# ---------------------------------------------------------------------------


def test_level_advanced_professional():
    text = "advanced and professional level dancers … full-time training"
    levels = bbm._level(text)
    assert "professional" in levels
    assert "pre-professional" in levels


def test_level_empty_when_not_mentioned():
    assert bbm._level("open to everyone") == []


# ---------------------------------------------------------------------------
# _teachers
# ---------------------------------------------------------------------------


def test_teachers_all_six():
    teachers = bbm._teachers(_TEAM_HTML)
    names = [t.name for t in teachers]
    assert "Jiří Bubeníček" in names
    assert "Sarah Lamb" in names
    assert "Juliane Mathis" in names
    assert "Jean-Guillaume Bart" in names
    assert "Arman Grigoryan" in names
    assert "Nikos Kalivas" in names


def test_teachers_affiliations_jiri():
    teachers = bbm._teachers(_TEAM_HTML)
    jiri = next(t for t in teachers if t.name == "Jiří Bubeníček")
    org_names = [a.organization for a in jiri.affiliations]
    assert "Les Ballets Bubeníček" in org_names
    assert "Semperoper Ballet" in org_names


def test_teachers_sarah_lamb_affiliation():
    teachers = bbm._teachers(_TEAM_HTML)
    sarah = next(t for t in teachers if t.name == "Sarah Lamb")
    assert sarah.affiliations[0].organization == "The Royal Ballet"


def test_teachers_partial_page():
    # Only Jiří appears — other names absent → only one teacher emitted.
    teachers = bbm._teachers(_TEAM_HTML_PARTIAL)
    assert len(teachers) == 1
    assert teachers[0].name == "Jiří Bubeníček"


def test_teachers_none_when_empty():
    assert bbm._teachers("<html><body></body></html>") == []


# ---------------------------------------------------------------------------
# _prices
# ---------------------------------------------------------------------------


def test_prices_1350_eur():
    prices = bbm._prices(bbm._text(_FEE_HTML))
    assert len(prices) == 1
    assert prices[0].amount == 1350.0
    assert prices[0].currency == "EUR"
    assert "tuition" in prices[0].includes


def test_prices_absent():
    assert bbm._prices("Tuition fee coming soon.") == []


# ---------------------------------------------------------------------------
# _apply_note
# ---------------------------------------------------------------------------


def test_apply_note_contains_deposit_info():
    note = bbm._apply_note(bbm._text(_FEE_HTML))
    assert note is not None
    low = (note or "").lower()
    assert "deposit" in low or "july" in low


# ---------------------------------------------------------------------------
# _requirements
# ---------------------------------------------------------------------------


def test_requirements_types():
    reqs = bbm._requirements(bbm._text(_REGISTER_HTML))
    types = [r.type for r in reqs]
    assert "cv" in types
    assert "headshot" in types
    assert "photos" in types
    assert "video" in types


def test_requirements_photo_poses():
    reqs = bbm._requirements(bbm._text(_REGISTER_HTML))
    photos = [r for r in reqs if isinstance(r, PhotosReq)]
    assert len(photos) == 1
    assert photos[0].specificity == "defined-poses"
    assert "first arabesque" in photos[0].poses


def test_requirements_two_video_reqs():
    reqs = bbm._requirements(bbm._text(_REGISTER_HTML))
    videos = [r for r in reqs if isinstance(r, VideoReq)]
    assert len(videos) == 2
    specificities = {v.specificity for v in videos}
    assert "specific" in specificities
    assert "unspecific" in specificities


# ---------------------------------------------------------------------------
# _build_offerings — integration
# ---------------------------------------------------------------------------


def test_build_offerings_happy_path():
    offerings = bbm._build_offerings(
        home_html=_HOME_HTML,
        team_html=_TEAM_HTML,
        fee_html=_FEE_HTML,
        register_html=_REGISTER_HTML,
        today=date(2026, 6, 8),
    )
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "bubenicek-masterclasses/masterclasses-2026"
    assert o.source.provider == "bubenicek-masterclasses"
    assert o.schedule.start == date(2026, 7, 27)
    assert o.schedule.end == date(2026, 8, 8)
    assert o.schedule.season == "2026"
    assert o.schedule.timezone == "Europe/Prague"
    assert o.organization.country == "CZ"
    assert o.organization.city == "Prague"
    assert o.location is not None
    assert o.location.country == "CZ"
    assert o.location.city == "Prague"
    assert "classical" in o.genres
    assert "pre-professional" in o.level
    assert o.age_range == {"min": 14, "max": 30}
    assert len(o.teachers) == 6
    assert len(o.prices) == 1
    assert o.prices[0].amount == 1350.0
    types = [r.type for r in o.application.requirements]
    assert "cv" in types
    assert "headshot" in types
    assert "photos" in types
    assert "video" in types


def test_build_offerings_no_date():
    result = bbm._build_offerings(
        home_html=_HOME_HTML_NO_DATE,
        team_html=_TEAM_HTML,
        fee_html=_FEE_HTML,
        register_html=_REGISTER_HTML,
        today=date(2026, 6, 8),
    )
    assert result == []


def test_build_offerings_no_price():
    offerings = bbm._build_offerings(
        home_html=_HOME_HTML,
        team_html=_TEAM_HTML,
        fee_html=_FEE_HTML_NO_PRICE,
        register_html=_REGISTER_HTML,
        today=date(2026, 6, 8),
    )
    assert len(offerings) == 1
    assert offerings[0].prices == []
