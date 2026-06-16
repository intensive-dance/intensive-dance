"""Offline tests for the Finland International Summer Ballet School scraper.

Inline fixtures mirror the live Wix pages (zero-width-spaced text, the edition
title, the four weekly date tokens, the curriculum/fee block) and the linked
Google-Doc schedule. No network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import finland_international_summer_ballet_school as f

# Home page: edition title + year, the four weekly session tokens, ld+json, the
# apply-form link, and the linked schedule doc. Zero-width spaces (​) are
# sprinkled in as Wix does, to prove they're stripped.
HOME_HTML = """
<html><head>
<title>Finland International Summer Ballet School | dance</title>
<script type="application/ld+json">{"@type":"LocalBusiness","name":"Finland International Summer Ballet School","address":{"addressCountry":"FI","addressLocality":"Helsinki"}}</script>
</head><body>
<h1>The 12th​ Finland 2026 International Summer Ballet​ School</h1>
<p>Helsinki</p>
<p>22-27.6 _ 29.6-4.7 _ 6-11.7 _ 13-18.7</p>
<a href="https://forms.gle/H9d2zfHPYTrTcxE46">Apply here till June 15</a>
<a href="https://docs.google.com/document/d/DOC123/edit?usp=sharing">Schedule / Tutors</a>
</body></html>
"""

# Course page: the structured curriculum list, the four levels with ages, the
# per-week fee range, and the accommodation/meals exclusion.
COURSE_HTML = """
<html><body>
<h2>About Dance Classes</h2>
<p>The Ballet Summer School Programme Helsinki includes education in:</p>
<p>Ballet Training / Master Class ( 20 classes of 90 minutes / 4 weeks )</p>
<p>Pointe / Variation / Repertoire Class ( 20 classes of 60 minutes / 4 weeks )</p>
<p>Character Dance ( 20 classes of 90 minutes / 4 weeks )</p>
<p>Contemporary/ jazz-dance ( 20 classes of 90 minutes / 4 weeks )</p>
<p>Final Public Presentation</p>
<p>There will be 4 levels of Summer Ballet School education:</p>
<p>Intermediate/ Youth - 9-12 years</p>
<p>Intermediate/Young students aged from 12-15+</p>
<p>Advanced /Professional/ Semi-professional students aged from 16-25+</p>
<p>Adult ballet classes - Open level</p>
<p>Classes will be given in English.</p>
<h3>Fees</h3>
<p>Summer Ballet School Fee for 1 week in Helsinki: 150-475 eur</p>
<p>Summer Ballet School Fee for 4 weeks: 600-1900 eur</p>
<p>The Fees need to be transferred before June 15th to the Ballet Summer School Bank Account.</p>
<p>The cost of accommodation and meals is not included in the Summer Ballet School Fees.</p>
</body></html>
"""

# The schedule doc's "Tutors:" block: weeks 3+4 share a single "6-18.7" header.
DOC_TEXT = """﻿Finland International Summer Ballet School 2026
Tutors:
22-27.6 Ballet/repertoire:  Ekaterina Petina (ex-Principal Dancer with the  Les Ballets de Monte-Carlo)
Character, ballet 9-12 y.o.: Taja Soiko  Adults ballet Mo-Fr
29.6-4.7 Ballet/repertoire: Alisa Gasemyr (Stockholm); SERGEI UPKIN  Adults ballet Mo-Fr
Character-dance 12+ y.o.: SERGEI UPKIN (ex-Principal Dancer with the Estonian National Ballet)
6-18.7 Ballet/repertoire: Chinara Alizade  (Principal Dancer of the Teatr Wielki - Polish National Opera)
Adults ballet Mo-Fr-  Rasmus Ahlgren  (Demi-soloist with the Estonian National Ballet)
SCHEDULE  22 - 27.6.2026
"""


def _build(home=HOME_HTML, course=COURSE_HTML, doc=DOC_TEXT):
    return f._build_offerings(home, course, doc)


def test_emits_one_offering_per_weekly_session():
    offs = _build()
    assert [o.schedule.start for o in offs] == [
        date(2026, 6, 22),
        date(2026, 6, 29),
        date(2026, 7, 6),
        date(2026, 7, 13),
    ]
    assert [o.schedule.end for o in offs] == [
        date(2026, 6, 27),
        date(2026, 7, 4),
        date(2026, 7, 11),
        date(2026, 7, 18),
    ]
    # Year-stamped, day-stamped slug under the provider.
    assert offs[0].id == "finland-international-summer-ballet-school/summer-2026-06-22"
    assert all(o.schedule.season == "2026" for o in offs)
    assert all(o.schedule.timezone == "Europe/Helsinki" for o in offs)


def test_month_crossing_title():
    offs = _build()
    assert "29 June – 4 July 2026" in offs[1].title
    assert "22–27 June 2026" in offs[0].title


def test_levels_and_session_age_bands():
    o = _build()[0]
    assert o.level == ["intermediate", "advanced", "open"]
    bands = [(s.age_range) for s in o.schedule.sessions]
    assert {"min": 9, "max": 12} in bands
    assert {"min": 12, "max": 15} in bands
    assert {"min": 16, "max": 25} in bands
    # The adult open-level block is open-ended (no age band).
    assert None in bands


def test_genres_from_curriculum_list():
    o = _build()[0]
    assert o.genres == ["classical", "pointe", "repertoire", "character", "contemporary"]


def test_prices_per_week_range_eur_tuition_only():
    o = _build()[0]
    assert [(p.amount, p.currency, p.label) for p in o.prices] == [
        (150.0, "EUR", "From (per week)"),
        (475.0, "EUR", "To (per week)"),
    ]
    # Accommodation/meals are NOT included — tuition only.
    assert all(p.includes == ["tuition"] for p in o.prices)


def test_location_and_organization():
    o = _build()[0]
    assert o.organization.slug == "finland-international-summer-ballet-school"
    assert o.organization.country == "FI"
    assert o.location is not None
    assert o.location.city == "Helsinki"
    assert "Leipätehdas" in (o.location.venue or "")


def test_application_window_and_form():
    o = _build()[0]
    assert o.application.deadline == date(2026, 6, 15)
    assert o.application.url == "https://forms.gle/H9d2zfHPYTrTcxE46"
    # The page states a payment deadline, not an application status — so status is
    # left unset (consumers derive closed-ness from deadline < today).
    assert o.application.status is None
    assert o.application.requirements == []  # not described publicly


def test_faculty_attributed_per_week():
    offs = _build()
    week1, week2, week3, week4 = offs

    assert [t.name for t in week1.teachers] == ["Ekaterina Petina"]
    assert week1.teachers[0].affiliations[0].organization == "Les Ballets de Monte-Carlo"
    assert week1.teachers[0].affiliations[0].role == "ex-Principal Dancer"

    # All-caps doc name normalized; the "(Stockholm)" place is not an affiliation.
    names2 = {t.name for t in week2.teachers}
    assert names2 == {"Alisa Gasemyr", "Sergei Upkin"}
    gasemyr = next(t for t in week2.teachers if t.name == "Alisa Gasemyr")
    assert gasemyr.affiliations == []
    upkin = next(t for t in week2.teachers if t.name == "Sergei Upkin")
    assert upkin.affiliations[0].organization == "Estonian National Ballet"

    # A single "6-18.7" header seeds both the 6.7 and 13.7 weeks with its tutors.
    for wk in (week3, week4):
        names = {t.name for t in wk.teachers}
        assert names == {"Chinara Alizade", "Rasmus Ahlgren"}


def test_fails_open_without_schedule_doc():
    offs = _build(doc="")
    assert len(offs) == 4
    assert all(o.teachers == [] for o in offs)


def test_missing_fee_block_yields_no_prices():
    course = COURSE_HTML.replace("Summer Ballet School Fee for 1 week in Helsinki: 150-475 eur", "")
    offs = _build(course=course)
    assert all(o.prices == [] for o in offs)


def test_no_edition_year_yields_nothing():
    offs = _build(home="<html><body><p>22-27.6</p></body></html>")
    assert offs == []
