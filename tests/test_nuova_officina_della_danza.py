from datetime import date

from intensive_dance.models import VideoReq
from intensive_dance.scrapers import nuova_officina_della_danza as nod

PAGE = """
Summer Intensive Program '26
JUNE 29 > JULY 17
Held in Turin from June 29 to July 17, you will engage with contemporary choreographers.
three ballet classes per week
Designed for dancers with strong contemporary technique toward a professional career.
ALL INCLUSIVE | 3 WEEKS
Early Bird Fee for applications submitted by December 31st:
€1.900,00 — Fee for 7 artists (excluding Emilie Leriche)
€2.040,00 — Fee for 8 artists (including Emilie Leriche)
Regular fee: € 2.300,00 (Registration fee included)
In case of late enrollment, the full remaining balance must be paid no later than June 15, 2026.
WEEK 1 | JUNE 29 > JULY 3
Full Week | Ben Behrends, Ella Rothschild
WEEK 2 | JULY 6 > JULY 10 -
Full Week | Ethan Colangelo, Anamaria Lucaciu, Greg Lau
WEEK 3 | JULY 13 > JULY 17
Full week| Noa Zuk, Bruno Guillore, Emilie Leriche
fill out the form by entering your CV and two separate links - only Vimeo or YouTube links
"""


def test_one_offering_span_and_sessions():
    offerings = nod._build_offerings(PAGE)
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "nuova-officina-della-danza/2026"
    assert o.title == "NOD Summer Intensive Program 2026"
    assert o.schedule.season == "summer"
    assert o.schedule.start == date(2026, 6, 29)
    assert o.schedule.end == date(2026, 7, 17)
    labels = [(s.label, s.start, s.end) for s in o.schedule.sessions]
    assert labels == [
        ("Week 1", date(2026, 6, 29), date(2026, 7, 3)),
        ("Week 2", date(2026, 7, 6), date(2026, 7, 10)),
        ("Week 3", date(2026, 7, 13), date(2026, 7, 17)),
    ]


def test_genres_level_location():
    o = nod._build_offerings(PAGE)[0]
    assert set(o.genres) == {"contemporary", "classical"}
    assert o.level == ["pre-professional"]
    assert o.location is not None
    assert o.location.city == "Turin" and o.location.country == "IT"


def test_eight_guest_artists_deduped():
    teachers = nod._build_offerings(PAGE)[0].teachers
    assert [t.name for t in teachers] == [
        "Ben Behrends",
        "Ella Rothschild",
        "Ethan Colangelo",
        "Anamaria Lucaciu",
        "Greg Lau",
        "Noa Zuk",
        "Bruno Guillore",
        "Emilie Leriche",
    ]
    assert all(t.role == "Guest artist" for t in teachers)


def test_three_week_price_tiers():
    prices = nod._build_offerings(PAGE)[0].prices
    assert [p.amount for p in prices] == [1900.0, 2040.0, 2300.0]
    assert all(p.currency == "EUR" and p.includes == ["tuition"] for p in prices)


def test_application_cv_and_video():
    app = nod._build_offerings(PAGE)[0].application
    assert app.status == "open"
    types = [r.type for r in app.requirements]
    assert types == ["cv", "video"]
    video = app.requirements[1]
    assert isinstance(video, VideoReq)
    assert video.specificity == "unspecific"


def test_no_week_headers_yields_nothing():
    assert nod._build_offerings("Some page with 2026 but no week headers.") == []
