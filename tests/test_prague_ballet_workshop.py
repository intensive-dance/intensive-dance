from datetime import date

from intensive_dance.scrapers import prague_ballet_workshop as pbw

WORKSHOP = """
top of page
Workshop Summer
Our classical workshop contains:
10x ballet class
10x point shoes, man´s technique
10x repertoire class
10x contemporary class
10x pilates lesson
July 13th - 24th 2026
Our ballet workshop is specially created for students of ballet schools
and dance conservatories, aged 13-21 years old.
"""

PRICES = """
10 days intensive workshop
13.-17.july
20.-24.july
Workshop price:
1 week €850
2weeks € 1400
"""

APPLICATIONS = """
Submit your dance video: Attach a short dance video along with your application.
Age: 13 - 21 years (after consultation, older).
We look forward to receiving your applications!
"""

INSTRUCTORS = """
Workshop Summer
Daily Schedule Summer
Meet Our Instructors
Summer 2026
All our instructors were great dancers, working for different companies all around the world.
Ballet class, point shoes
& variation class, pilates
RICHARD D´ALTON
EX PRINCIPAL DANCER FROM ORLANDO BALLET
FREELANCE TEACHER AND CHOREOGRAPHER
MARIANA TORRES
CERTIFICATED PILATES INSTRUCTOR
Gianvito Attimonelli
EX SOLIST DANCER FROM
CZECH NATIONAL BALLET
BALLETMASTER
Contemporary
LUISA MARÍA ARIAS
DANCE TEACHER AND ASSISTANT OF NACHO DUATO
JAREK CEMEREK
RENOWNED CONTEMPORARY CHOREOGRAPHER, TEACHER AND DANCER
Partners:
©2025 Prague Ballet Workshop
"""

LOCATION = """
Beautiful studio in the city center
Address:
Budečská 35, Praha 2 - Vinohrady
View the Map
"""


def _build():
    return pbw._build_offerings(WORKSHOP, PRICES, APPLICATIONS, INSTRUCTORS, LOCATION)


def test_one_offering_dates_and_id():
    offerings = _build()
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "prague-ballet-workshop/2026"
    assert o.title == "Prague Summer Ballet Workshop 2026"
    assert o.schedule.season == "summer"
    assert o.schedule.start == date(2026, 7, 13)
    assert o.schedule.end == date(2026, 7, 24)


def test_genres_and_level_and_age():
    o = _build()[0]
    assert set(o.genres) == {"classical", "pointe", "repertoire", "contemporary"}
    assert o.level == ["pre-professional"]
    assert o.age_range == {"min": 13, "max": 21}


def test_prices_two_tiers_eur():
    prices = _build()[0].prices
    assert [(p.amount, p.label) for p in prices] == [(850.0, "1 week"), (1400.0, "2 weeks")]
    assert all(p.currency == "EUR" and p.includes == ["tuition"] for p in prices)


def test_application_video_unspecific_and_open():
    app = _build()[0].application
    assert app.status == "open"
    assert app.url.endswith("/kopie-applications-2")
    assert len(app.requirements) == 1
    req = app.requirements[0]
    assert req.type == "video"
    assert req.specificity == "unspecific"


def test_teachers_roster_names_only():
    names = [t.name for t in _build()[0].teachers]
    assert names == [
        "Richard D'Alton",
        "Mariana Torres",
        "Gianvito Attimonelli",
        "Luisa María Arias",
        "Jarek Cemerek",
    ]
    # credential/section lines and the company name are not mistaken for instructors
    assert "Czech National Ballet" not in names
    assert all(t.affiliations == [] for t in _build()[0].teachers)


def test_location_venue():
    loc = _build()[0].location
    assert loc is not None
    assert loc.city == "Prague" and loc.country == "CZ"
    assert loc.venue == "Budečská 35, Praha 2 - Vinohrady"


def test_no_dates_yields_no_offering():
    assert pbw._build_offerings("no dates here", PRICES, APPLICATIONS, INSTRUCTORS, LOCATION) == []
