from datetime import date

from intensive_dance.scrapers import scuola_hamlyn as ham


def _post(title: str, content: str = "", link: str = "https://www.scuolahamlyn.com/x/"):
    return {"title": {"rendered": title}, "content": {"rendered": content}, "link": link}


POSTS = [
    _post(
        "Summer Course dal 24 al 29 Agosto 2026",
        "<p><strong>Alessandro Borghesani</strong> Solista</p>"
        "<p><strong>Irene van Dijk</strong> Solista</p>"
        "<p><strong>Elisa Corsini</strong> Co-direttrice</p>",
    ),
    _post("SUMMER COURSE 22/27 AGOSTO 2022", ""),
    _post("8 Febbraio 2020 AUDIZIONE-STAGE JOFFREY BALLET SCHOOL SUMMER COURSE", ""),
    _post("CORSO DI FORMAZIONE INSEGNANTI", ""),
]


def test_emits_one_offering_per_summer_course_edition():
    offerings = ham._build_offerings(POSTS)
    ids = {o.id for o in offerings}
    assert ids == {"scuola-hamlyn/2026", "scuola-hamlyn/2022"}


def test_audition_and_unrelated_posts_excluded():
    offerings = ham._build_offerings(POSTS)
    # the audition-for-another-school post and the teacher-training post are not editions
    assert all("joffrey" not in o.id.lower() for o in offerings)
    assert len(offerings) == 2


def test_dates_parse_both_title_formats():
    by_id = {o.id: o for o in ham._build_offerings(POSTS)}
    assert by_id["scuola-hamlyn/2026"].schedule.start == date(2026, 8, 24)
    assert by_id["scuola-hamlyn/2026"].schedule.end == date(2026, 8, 29)
    assert by_id["scuola-hamlyn/2022"].schedule.start == date(2022, 8, 22)
    assert by_id["scuola-hamlyn/2022"].schedule.end == date(2022, 8, 27)


def test_genre_location_and_faculty():
    o = next(o for o in ham._build_offerings(POSTS) if o.id == "scuola-hamlyn/2026")
    assert o.genres == ["classical"]
    assert o.location is not None and o.location.city == "Florence"
    assert [t.name for t in o.teachers] == [
        "Alessandro Borghesani",
        "Irene van Dijk",
        "Elisa Corsini",
    ]


def test_edition_without_faculty_has_empty_teachers():
    o = next(o for o in ham._build_offerings(POSTS) if o.id == "scuola-hamlyn/2022")
    assert o.teachers == []
