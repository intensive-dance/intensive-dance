"""Unit tests for the Ballet Summer Course Budapest scraper.

The front page lists each group (level) with its age band inline in the "Details"
link and the course date span ("held from 27 July 2026 to 8 August 2026"); each
group's fee lives on its own page. These pin: the shared date range, one Offering
per group, the age-band variants (numeric, open-topped "from 16", and the
"no age limit" amateurs that carry no bounds), the per-group EUR fees (and that
the amount-first children "extra class" fee is *not* picked up as tuition), level
inference, and faculty + affiliations. Inline HTML, no network.
"""

from __future__ import annotations

from datetime import date

from selectolax.parser import HTMLParser

from intensive_dance.scrapers import ballet_summer_course_budapest as bsc

# A trimmed front page: the date line, three group "Details" links covering the
# three age-band shapes, and a two-teacher roster with affiliations.
HOME_HTML = """
<html><body>
<p>Welcome to our 12 th international summer ballet course in 2026! This year our
course will be held from 27 July 2026 to 8 August 2026.</p>
<p>
<a href="https://balletsummercoursebudapest.com/about-our-groups/professional-young-group/">Professional young group (from 13 to 15 age) &gt;&gt; Details</a>
<a href="https://balletsummercoursebudapest.com/about-our-groups/professional-junior-group-between-13-and-15-years-of-age/">Professional group. (from 16 years of age) &gt;&gt; Details</a>
<a href="https://balletsummercoursebudapest.com/about-our-groups/advanced-amateur-group-from-the-age-of-15/">Amateur advanced level group. (no age limit) &gt;&gt; Details</a>
<a href="https://balletsummercoursebudapest.com/about-our-groups/">About our groups</a>
</p>
<h3>Our teachers</h3>
<h4><a href="https://balletsummercoursebudapest.com/vdovicheva-tatjana-en/">Vdovicheva Tatjana</a></h4>
<p>Since 2009 Member of the Hungarian State Opera House and since 2013 Hungarian Dance Academy ballet master. Graduated in Russian Perm Ballet Institute.</p>
<h4><a href="https://balletsummercoursebudapest.com/diana-kosyreva/">Kosyreva Diana</a></h4>
<p>Soloist with the Hungarian National Ballet since 2018. Graduated from GITIS in 2020.</p>
<p>Ballet summer course includes: Classical ballet, pointe work, variation, character dance, modern.</p>
</body></html>
"""

GROUP_HTML = {
    "https://balletsummercoursebudapest.com/about-our-groups/professional-young-group/": (
        "<html><body><nav>Fees Location</nav>"
        "<div>Fees 1 week: 450 € 2 weeks: 750 € Shedule Every day 4 lessons</div>"
        "</body></html>"
    ),
    "https://balletsummercoursebudapest.com/about-our-groups/professional-junior-group-between-13-and-15-years-of-age/": (
        "<html><body><div>Fees 1 week: 450 € 2 weeks: 750 €</div></body></html>"
    ),
    "https://balletsummercoursebudapest.com/about-our-groups/advanced-amateur-group-from-the-age-of-15/": (
        "<html><body><div>Fees 1 week: 350 € 2 weeks: 600 €</div></body></html>"
    ),
}


def build():
    return bsc._build_offerings(HOME_HTML, GROUP_HTML, date(2026, 6, 9))


def test_one_offering_per_group():
    offs = build()
    assert len(offs) == 3
    assert [o.id for o in offs] == sorted(o.id for o in offs)


def test_shared_date_range():
    o = build()[0]
    assert o.schedule.start == date(2026, 7, 27)
    assert o.schedule.end == date(2026, 8, 8)
    assert o.schedule.season == "2026"
    assert o.schedule.timezone == "Europe/Budapest"


def test_age_numeric_band():
    (young,) = [o for o in build() if "professional-young-group-2026" in o.id]
    assert young.age_range == {"min": 13, "max": 15}
    assert young.level == ["professional"]


def test_age_open_topped_from_sixteen():
    (pro,) = [o for o in build() if "professional-junior-group" in o.id]
    assert pro.age_range == {"min": 16}
    assert pro.level == ["professional"]


def test_amateur_no_age_limit_has_no_bounds():
    (adv,) = [o for o in build() if "advanced-amateur" in o.id]
    assert adv.age_range is None
    assert set(adv.level) == {"advanced", "open"}


def test_prices_per_group_in_eur():
    (adv,) = [o for o in build() if "advanced-amateur" in o.id]
    assert [(p.amount, p.currency, p.label) for p in adv.prices] == [
        (350.0, "EUR", "1 week"),
        (600.0, "EUR", "2 weeks"),
    ]
    assert all(p.includes == ["tuition"] for p in adv.prices)


def test_extra_class_fee_not_counted_as_tuition():
    # The children "extra class" fee is written amount-first → must not be read.
    text = "Fees 1 week: 300 € 2 week: 450 € Extra class 80 € for 1 week 145 € for 2 weeks"
    amounts = [p.amount for p in bsc._prices(text)]
    assert amounts == [300.0, 450.0]


def test_genres_shared():
    o = build()[0]
    assert o.genres == ["classical", "pointe", "repertoire", "character", "contemporary"]


def test_location_and_org():
    o = build()[0]
    assert o.location is not None
    assert o.location.city == "Budapest"
    assert o.location.country == "HU"
    assert o.organization.slug == "ballet-summer-course-budapest"


def test_requirements_empty_open_enrolment():
    o = build()[0]
    assert o.application.requirements == []


def test_teachers_with_affiliations():
    o = build()[0]
    by_name = {t.name: t for t in o.teachers}
    assert "Vdovicheva Tatjana" in by_name
    orgs = {a.organization for a in by_name["Vdovicheva Tatjana"].affiliations}
    assert "Hungarian State Opera" in orgs
    assert "Perm Ballet" in orgs
    diana = by_name["Kosyreva Diana"]
    orgs2 = {a.organization for a in diana.affiliations}
    assert "Hungarian National Ballet" in orgs2
    assert "GITIS (Russian Institute of Theatre Arts)" in orgs2


def test_dates_helper():
    assert bsc._dates("held from 27 July 2026 to 8 August 2026") == (
        date(2026, 7, 27),
        date(2026, 8, 8),
    )


def test_groups_helper_drops_index_link():
    groups = bsc._groups(HTMLParser(HOME_HTML))
    # Three "Details" groups; the bare "About our groups" index is dropped.
    assert len(groups) == 3
    names = [name for name, _age, _url in groups]
    assert "Professional young group" in names
    assert "About our groups" not in names
