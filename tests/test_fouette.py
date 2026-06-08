"""Unit tests for the Fouetté scraper (PL, Poznań — summer camp + winter intensive).

`_build_offerings` takes the WordPress `posts` payload (the dated recap blog
posts) and emits one Offering per camp/winter edition with a parseable date span.
These pin: the Polish in-body month range ("23–27 lutego", year from the publish
date) for a winter intensive; a numeric span baked into a summer post slug/title
("13-20.08.2021"); the founder/affiliation teacher; the ballet-core genre mapping
including pointe/repertoire; that a non-camp post (a spectacle) and a camp recap
with no parseable date are both skipped; and that one program/year emits once even
when several recaps mention it. Inline payloads, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import fouette


def _post(slug: str, day: str, title: str, body: str) -> dict:
    return {
        "slug": slug,
        "date": f"{day}T10:00:00",
        "link": f"https://fouette.pl/{slug}/",
        "title": {"rendered": title},
        "content": {"rendered": f"<p>{body}</p>"},
    }


# A winter-intensive recap: Polish in-body month range, year from the post date.
WINTER_2026 = _post(
    "taneczne-ferie-fouette-2",
    "2026-04-08",
    "Taneczne Ferie Fouetté",
    "W dniach 23–27 lutego odbył się Intensywny Zimowy Kurs. W programie: "
    "technika tańca klasycznego, taniec współczesny, taniec jazzowy, stretching, "
    "partnerowanie, repertuar, point.",
)

# A summer camp with a numeric span encoded in the slug/title.
SUMMER_2021 = _post(
    "13-20-08-2021-oboz-taneczny-fouette",
    "2021-08-20",
    "13-20.08.2021 Obóz Taneczny Fouetté",
    "Taniec klasyczny, taniec współczesny, stretching, trening motoryczny.",
)

# A camp recap with NO parseable date — must be skipped (we never invent one).
SUMMER_UNDATED = _post(
    "oboz-fouette-2025",
    "2025-08-09",
    "Obóz „Fouette” 2025",
    "Obóz „Fouetté” – Summer Dance Program 2025 rozpoczęty! Taniec klasyczny, "
    "taniec współczesny, stretching.",
)

# A non-camp post (a spectacle) — must not be treated as an edition at all.
SPECTACLE = _post(
    "coppelia-taneczny-spektakl",
    "2025-09-22",
    "Coppelia — taneczny spektakl 16 listopada",
    "Zapraszamy na spektakl baletowy Coppelia.",
)


def test_winter_intensive_polish_month_range():
    offerings = fouette._build_offerings([WINTER_2026])
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "fouette/winter-intensive-2026"
    assert o.title == "Fouetté Winter Intensive 2026"
    assert o.schedule.start == date(2026, 2, 23)
    assert o.schedule.end == date(2026, 2, 27)
    assert o.schedule.season == "2026"
    assert o.schedule.timezone == "Europe/Warsaw"
    # ballet core + winter extras, faithfully captured.
    assert set(o.genres) == {"classical", "contemporary", "repertoire", "pointe"}


def test_summer_camp_numeric_slug_span():
    offerings = fouette._build_offerings([SUMMER_2021])
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "fouette/summer-camp-2021"
    assert o.schedule.start == date(2021, 8, 13)
    assert o.schedule.end == date(2021, 8, 20)
    assert o.genres == ["classical", "contemporary"]


def test_cross_month_slug_span():
    post = _post(
        "14-08-24-08-2019-letni-oboz-fouette",
        "2019-08-14",
        "Letni Obóz Fouetté",
        "Taniec klasyczny i współczesny.",
    )
    o = fouette._build_offerings([post])[0]
    assert o.schedule.start == date(2019, 8, 14)
    assert o.schedule.end == date(2019, 8, 24)


def test_undated_and_nonedition_posts_skipped():
    offerings = fouette._build_offerings([SUMMER_UNDATED, SPECTACLE])
    assert offerings == []


def test_one_offering_per_program_year():
    # Two winter recaps for the same Feb 2026 edition collapse to one Offering.
    dup = _post(
        "taneczne-ferie-zimowe-coraz-blizej",
        "2026-02-01",
        "Taneczne ferie zimowe coraz bliżej",
        "Już 23–27 lutego rusza Intensywny Kurs Zimowy.",
    )
    offerings = fouette._build_offerings([WINTER_2026, dup])
    assert len(offerings) == 1
    assert offerings[0].id == "fouette/winter-intensive-2026"


def test_founder_teacher_and_affiliation():
    o = fouette._build_offerings([WINTER_2026])[0]
    assert len(o.teachers) == 1
    t = o.teachers[0]
    assert t.name == "Beata Książkiewicz"
    assert t.role == "Founder & Director"
    assert len(t.affiliations) == 1
    aff = t.affiliations[0]
    assert "Chopin" in aff.organization
    assert aff.current is True


def test_no_prices_or_ages_or_requirements_stated():
    o = fouette._build_offerings([WINTER_2026])[0]
    assert o.prices == []
    assert o.age_range is None
    assert o.application.requirements == []


def test_location_country_only():
    o = fouette._build_offerings([WINTER_2026])[0]
    assert o.location is not None
    assert o.location.country == "PL"
    assert o.location.city is None
    assert o.location.venue is None
