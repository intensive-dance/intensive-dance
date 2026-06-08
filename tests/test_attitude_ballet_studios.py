"""Unit tests for the Attitude Ballet Studios (Vienna Ballet Intensive) scraper.

One Elementor-built page → one Offering. These pin the date range (shared
trailing month+year), the open-ended 12+ age band, curriculum-driven genres,
the two EUR tuition tiers (parsed through the split `<sup>€</sup><span>` markup
that yields "€ 1350"), the professional/pre-professional levels, the photo+video
requirement pair, and the curated faculty roster gated on page presence. Inline
strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import PhotosReq, VideoReq
from intensive_dance.scrapers import attitude_ballet_studios as abs_

# A trimmed shape of the live page: zero-width chars sprinkled in, the price
# block with € split into a <sup> so text extraction yields "€ 1350" / "€ 750".
HAPPY_HTML = """
<html><body>
<h3>Registrations are​ OPEN for Vienna International Ballet Intensive 2026!
Ballet professionals and pre-professionals are welcome!</h3>
<p>The Ballet Workshop will be carried out in 2 weeks of ballet intensive.
13 - 25 July 2026</p>
<h4>Students 12+ years old are required to make an application for registering.</h4>
<h6>ARTISTIC DIRECTOR</h6><h2>Laura Cristinoiu</h2>
<h6>SPECIAL MASTER BALLET TEACHER</h6><h2>Liudmila Konovalova</h2>
<h6>Special Guest Master Teacher</h6><h2>Roman Lazik</h2>
<h2>Natalya Kusch</h2><h2>Annkathrin Dehn</h2>
<h2>Alexandra Inculet</h2><h2>Robert Gabdullin</h2>
<h3>Máire Elizabeth New</h3>
<p>Standard Rate (From 1 March 2026): 2 Weeks (Full Program): €1,350 1 Week: €750</p>
<p>A non-refundable deposit of €200 is required upon acceptance.</p>
<div class="price"><sup>€</sup><span>1350</span></div>
<div class="price"><sup>€</sup><span>750</span></div>
<h4>Timetable</h4><h4>Monday to Friday, 10:00 to 16:30</h4>
<h5>Ballet Study Class</h5><h5>Variations</h5><h5>Pointes</h5>
<h5>Modern and Contemporary</h5><h5>Character Dance</h5>
<h5>Neoclassical Choreography</h5><h5>Final Presentation</h5>
<p>The Intensive ends with a final presentation. Signed certificates will be handed out.</p>
<form><label>Upload Ballet Pose Photo *</label><label>Link to video *</label></form>
<p>Exceptions to registration can be made for 11-year-old children.</p>
</body></html>
"""

# Edge: an as-yet-undated future edition with no parseable date range.
NO_DATE_HTML = "<html><body><h3>Vienna Ballet Intensive — dates coming soon</h3></body></html>"


def test_build_offering_happy_path():
    o = abs_._build_offering(HAPPY_HTML)
    assert o is not None
    assert o.id == "attitude-ballet-studios/vienna-ballet-intensive-2026"
    assert o.title == "Vienna Ballet Intensive 2026"
    assert o.schedule.start == date(2026, 7, 13)
    assert o.schedule.end == date(2026, 7, 25)
    assert o.schedule.season == "2026"
    assert o.location is not None
    assert o.location.city == "Vienna"
    assert o.location.country == "AT"


def test_build_offering_no_date_returns_none():
    assert abs_._build_offering(NO_DATE_HTML) is None


def test_date_range_shared_month_year():
    assert abs_._date_range("13 - 25 July 2026") == (date(2026, 7, 13), date(2026, 7, 25))


def test_date_range_absent():
    assert abs_._date_range("dates coming soon") == (None, None)


def test_age_range_open_ended_min_only():
    assert abs_._age_range("Students 12+ years old are welcome") == {"min": 12}


def test_age_range_absent():
    assert abs_._age_range("a two-week summer programme") is None


def test_levels_professional_and_pre():
    assert abs_._levels("Ballet professionals and pre-professionals are welcome") == [
        "pre-professional",
        "professional",
    ]


def test_genres_from_curriculum():
    text = (
        "Ballet Study Class Variations Pointes Modern and Contemporary "
        "Character Dance Neoclassical Choreography"
    )
    assert abs_._genres(text) == [
        "classical",
        "pointe",
        "repertoire",
        "contemporary",
        "character",
        "neoclassical",
    ]


def test_prices_two_tiers_eur():
    text = "2 Weeks (Full Program): €1,350 1 Week: €750 deposit of €200"
    prices = abs_._prices(text)
    assert [(p.amount, p.currency, p.label) for p in prices] == [
        (1350.0, "EUR", "2 weeks (full program)"),
        (750.0, "EUR", "1 week"),
    ]
    assert prices[0].includes == ["tuition"]
    assert prices[0].notes is not None and "€200" in prices[0].notes


def test_prices_split_sup_symbol_form():
    # Text extraction of <sup>€</sup><span>1350</span> yields "€ 1350" / "€ 750".
    text = "2 Weeks (Full Program): € 1350 1 Week: € 750"
    assert [p.amount for p in abs_._prices(text)] == [1350.0, 750.0]


def test_status_open():
    assert (
        abs_._status("Registrations are OPEN for Vienna International Ballet Intensive") == "open"
    )


def test_status_closed():
    assert abs_._status("Registrations are closed") == "closed"


def test_status_none_when_unstated():
    assert abs_._status("13 - 25 July 2026") is None


def test_requirements_photo_and_video():
    text = (
        "Upload Ballet Pose Photo * ... Please submit a video link featuring a classical variation"
    )
    reqs = abs_._requirements(text)
    assert isinstance(reqs[0], PhotosReq) and reqs[0].specificity == "freeform"
    assert isinstance(reqs[1], VideoReq) and reqs[1].specificity == "unspecific"


def test_requirements_absent():
    assert abs_._requirements("apply on this page") == []


def test_teachers_curated_roster():
    o = abs_._build_offering(HAPPY_HTML)
    assert o is not None
    names = [t.name for t in o.teachers]
    assert names == [
        "Laura Cristinoiu",
        "Liudmila Konovalova",
        "Roman Lazik",
        "Natalya Kusch",
        "Annkathrin Dehn",
        "Alexandra Inculet",
        "Robert Gabdullin",
        "Máire Elizabeth New",
    ]
    konova = next(t for t in o.teachers if t.name == "Liudmila Konovalova")
    assert konova.affiliations[0].organization == "Wiener Staatsballett"
    assert konova.affiliations[0].current is True


def test_teachers_drop_absent_names():
    # A page missing the guest roster only keeps the names actually present.
    html = "<html><body><p>13 - 25 July 2026</p><h2>Laura Cristinoiu</h2></body></html>"
    o = abs_._build_offering(html)
    assert o is not None
    assert [t.name for t in o.teachers] == ["Laura Cristinoiu"]


def test_schedule_note_final_presentation():
    o = abs_._build_offering(HAPPY_HTML)
    assert o is not None
    assert o.schedule.sessions[0].notes is not None
    assert "final presentation" in o.schedule.sessions[0].notes.lower()
