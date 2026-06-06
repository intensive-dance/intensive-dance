"""Unit tests for the Revolve Dance Festival (Bucharest) scraper.

The page is a single Brizy-built programme page read as text and sliced on the
group headings. These tests feed inline HTML mirroring that structure and pin:
one Offering per track, the multi-genre matching (no force-classical on the
contemporary special groups), per-week + package prices on Senior Pro, the
audition-fee / Paquita add-on being excluded from tuition, age bands, default
festival dates inherited by the graded groups, and the shared guest roster.
No network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import revolve_dance_bucharest as rev

# A trimmed but structurally faithful copy of the live page: the enrolment intro
# (carrying the festival span), the graded groups, the two-week Senior Pro track,
# the two repertory special groups, and the guest-teacher roster.
SAMPLE_HTML = """
<html><body>
<p>Enrollment for Revolve Dance – Summer Intensive 2026 is open to all students,
aged 9 to 20+. This year, the summer courses will take place in two locations:
August 10 – 23 in Bucharest. August 23 – Stars Gala at the Bucharest National Opera.</p>

<h3>CHILDREN group</h3>
<p>09 - 11 years - girls and boys ( Completed by January 1, 2026 ) 5 hours/day x 13 days
+ gala including alternately: stretching/floor-barre, classical ballet technique,
repertoire/dance of character, contemporary. 1090 €</p>

<h3>JUNIOR group</h3>
<p>12 - 14 years - girls and boys 5 hours x 13 days: technique, classical ballet
pointes/ repertoire, character dance, contemporary. 1090 €</p>

<h3>JUNIOR PRO group</h3>
<p>13 - 15 years - girls and boys 6 hours x 13 days: technique, classical ballet
points / repertoire, boys class, character dance, contemporary/neo-classical. 1190 €</p>

<h3>SENIOR group</h3>
<p>16 - 20 years - girls and boys 6 hours x 13 days: technique, boys class, repertoire,
pas de deux/duet, character dance, contemporary/neo-classical. 1190 €</p>

<h3>NEW! SENIOR PRO Group</h3>
<p>18 - 25 years old, girls and boys (Completed by January 1, 2026)
Week 1, August 10-15: 700 euros: minimum 6 hours/day x 6 days, ballet technique,
boys' class, ensemble repertoire, pas de deux/duet, neo classic/ contemporary.
Week 2, August 17-23: 800 euros : ballet technique, neo classic, contemporary.
If you want to get involved in the "suite Paquita", you have to pay a separate fee of
150 euros . For both weeks, you can make a total package of 1300 euros.</p>

<h3>PARTICIPATION TO STARS GALA CHOREOGRAPHY “PAQUITA”</h3>
<p>* the casting will be organized during the first week of workshop. 150 €</p>

<h3>SPECIAL GROUP “Nacho Duato”</h3>
<p>only Senior &amp; Senior Pro. A special choreography will be studied and will be
presented at the Stars Gala on August 23, 2026. Schedule: August 17-23; Age: 18 - 25 years.
50 euro - fee for audition. This course can also be taken separately. 200 €</p>

<h3>SPECIAL GROUP “Maurice Bejart”</h3>
<p>The group will be limited to students for Senior Pro by audition.
Schedule: August 17-23; Age: 18 – 25 years. 17-22 august – daily courses x 2h.
50 euro - fee for audition. 200 €</p>

<h4>Guest teachers</h4>
<p>Nacho Duato — International choreographer.
Ivan Liška — Director Bayerisches Junior Ballett München and Heinz-Bosl-Stiftung.
Nina Ivanovich — Professor at the Vaganova Ballet Academy.
Andrey Ivanov — Eifman Dance Academy; former Principal at Mariinskii.
Anne-Cécile Morelle — Former soloist for Maurice Béjart.
Domenico Levré — Répétiteur of the Béjart Ballet Lausanne.</p>
</body></html>
"""


def _by_slug(offerings):
    return {o.id.split("/", 1)[1]: o for o in offerings}


def test_emits_one_offering_per_track():
    offs = rev._build_offerings(SAMPLE_HTML)
    slugs = {o.id.split("/", 1)[1] for o in offs}
    assert slugs == {
        "children-2026",
        "junior-2026",
        "junior-pro-2026",
        "senior-2026",
        "senior-pro-2026",
        "special-nacho-duato-2026",
        "special-maurice-bejart-2026",
    }


def test_graded_group_inherits_festival_dates():
    children = _by_slug(rev._build_offerings(SAMPLE_HTML))["children-2026"]
    assert children.schedule.start == date(2026, 8, 10)
    assert children.schedule.end == date(2026, 8, 23)
    assert children.age_range == {"min": 9, "max": 11}
    assert children.level == []


def test_children_is_multi_genre_not_just_classical():
    children = _by_slug(rev._build_offerings(SAMPLE_HTML))["children-2026"]
    assert children.genres == ["classical", "contemporary", "character", "repertoire"]


def test_junior_has_pointe():
    junior = _by_slug(rev._build_offerings(SAMPLE_HTML))["junior-2026"]
    assert "pointe" in junior.genres


def test_pro_tracks_marked_pre_professional():
    by = _by_slug(rev._build_offerings(SAMPLE_HTML))
    assert by["junior-pro-2026"].level == ["pre-professional"]
    assert by["senior-pro-2026"].level == ["pre-professional"]


def test_senior_pro_per_week_and_package_prices():
    senior_pro = _by_slug(rev._build_offerings(SAMPLE_HTML))["senior-pro-2026"]
    priced = {p.label: p.amount for p in senior_pro.prices}
    assert priced == {"Week 1": 700.0, "Week 2": 800.0, "Both weeks (package)": 1300.0}
    # The Paquita "separate fee of 150 euros" is an add-on, never tuition.
    assert 150.0 not in {p.amount for p in senior_pro.prices}
    assert all(p.currency == "EUR" for p in senior_pro.prices)


def test_senior_pro_sessions():
    senior_pro = _by_slug(rev._build_offerings(SAMPLE_HTML))["senior-pro-2026"]
    spans = [(s.label, s.start, s.end) for s in senior_pro.schedule.sessions]
    assert spans == [
        ("Week 1", date(2026, 8, 10), date(2026, 8, 15)),
        ("Week 2", date(2026, 8, 17), date(2026, 8, 23)),
    ]


def test_graded_group_single_tuition_excludes_audition_fee():
    senior = _by_slug(rev._build_offerings(SAMPLE_HTML))["senior-2026"]
    assert [(p.amount, p.label) for p in senior.prices] == [(1190.0, None)]


def test_special_groups_genre_from_choreographer_curriculum():
    by = _by_slug(rev._build_offerings(SAMPLE_HTML))
    duato = by["special-nacho-duato-2026"]
    bejart = by["special-maurice-bejart-2026"]
    # Duato = contemporary repertory; Béjart = neoclassical repertory. Never
    # force-defaulted to classical.
    assert "contemporary" in duato.genres and "classical" not in duato.genres
    assert "neoclassical" in bejart.genres and "classical" not in bejart.genres
    # Special groups run the second week only and have a single 200 € tuition.
    assert duato.schedule.start == date(2026, 8, 17)
    assert duato.schedule.end == date(2026, 8, 23)
    assert [(p.amount, p.label) for p in duato.prices] == [(200.0, None)]


def test_special_group_age_and_level():
    bejart = _by_slug(rev._build_offerings(SAMPLE_HTML))["special-maurice-bejart-2026"]
    assert bejart.age_range == {"min": 18, "max": 25}
    assert bejart.level == ["pre-professional"]


def test_requirements_video_plus_two_photos():
    children = _by_slug(rev._build_offerings(SAMPLE_HTML))["children-2026"]
    reqs = children.application.requirements
    types = {r.type for r in reqs}
    assert types == {"video", "photos"}
    video = next(r for r in reqs if r.type == "video")
    photos = next(r for r in reqs if r.type == "photos")
    assert video.specificity == "unspecific"
    assert photos.specificity == "freeform"


def test_shared_guest_roster_with_affiliations():
    children = _by_slug(rev._build_offerings(SAMPLE_HTML))["children-2026"]
    names = {t.name for t in children.teachers}
    assert {"Nacho Duato", "Ivan Liška", "Nina Ivanovich", "Domenico Levré"} <= names
    nina = next(t for t in children.teachers if t.name == "Nina Ivanovich")
    assert any(a.slug == "vaganova-ballet-academy" for a in nina.affiliations)


def test_no_faculty_section_means_no_teachers():
    # If the faculty block is gone, don't bake in a stale roster.
    html = SAMPLE_HTML.replace("Guest teachers", "Other content")
    offs = rev._build_offerings(html)
    assert all(o.teachers == [] for o in offs)


def test_titles_and_org():
    children = _by_slug(rev._build_offerings(SAMPLE_HTML))["children-2026"]
    assert children.title == "Summer Intensive 2026 — Children (9–11)"
    assert children.organization.slug == "revolve-dance-bucharest"
    assert children.organization.country == "RO"
    assert children.location is not None
    assert children.location.city == "Bucharest"
