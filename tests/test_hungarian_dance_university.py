from datetime import date

from intensive_dance.scrapers import hungarian_dance_university as hdu

# ISIBC (English) — mirrors the live program block; faculty bios deliberately
# mention "Modern" and "classical repertoire" to prove genre matching is scoped to
# the "course includes" clause, not the whole page.
_ISIBC = """
<html><body>
<h1>International Summer Intensive Ballet Course 2026</h1>
<p>Dates: 5&#8211;14 August 2026. The course includes: Classical ballet, Classical
repertoire, Pas de deux, Progressing Ballet Technique (PBT) Modern technique, Modern
repertoire. The age limit for the ISIBC 2026 Professional Program is 14&#8211;24 years.
Participation requirements: a minimum of 4 years of classical ballet training; for
female dancers, a minimum of 3 years of pointe work experience.</p>
<p>Application deadline / Payment deadline : June 10. 2026.</p>
<h3>ISIBC 2026 masters</h3>
<p>Anita Magyari danced Odette in Swan Lake and many roles in the classical
repertoire; she also performed Modern works at La Scala.</p>
</body></html>
"""

# Nyári Balett Stúdió (Hungarian) — closed cycle (LEZÁRULT) kept per keep-ended rule.
_NYARI = """
<html><body>
<h1>Nyári Balett Stúdió 2026</h1>
<p>Id&#337;pont: 2026. j&uacute;lius 27. &#8211; augusztus 2. a Magyar
T&aacute;ncm&#369;v&eacute;szeti Egyetemen. V&aacute;rjuk azon 11&#8211;14 &eacute;ves
(jelenleg 5&#8211;8. oszt&aacute;lyos) fiatalok jelentkez&eacute;s&eacute;t.</p>
<p>Jelentkez&eacute;si hat&aacute;rid&#337;: 2026.06.10. &#8211; LEZ&Aacute;RULT</p>
<p>A kurzuson oktat&oacute; mesterek: Klasszikus balett, k&eacute;pess&eacute;gfejleszt&eacute;s,
repertoire. Modernt&aacute;nc, improviz&aacute;ci&oacute;. Hip-hop.</p>
<p>Tov&aacute;bbi inform&aacute;ci&oacute;: kurzus@mte.eu</p>
</body></html>
"""


def test_isibc_core_fields():
    o = hdu._build_isibc(_ISIBC)
    assert o.id == "hungarian-dance-university/international-summer-intensive-ballet-course-2026"
    assert o.title == "International Summer Intensive Ballet Course 2026"
    assert o.schedule.start == date(2026, 8, 5)
    assert o.schedule.end == date(2026, 8, 14)
    assert o.schedule.season == "2026"
    assert o.age_range == {"min": 14, "max": 24}
    assert o.application.deadline == date(2026, 6, 10)
    assert o.level == ["pre-professional"]
    # Curriculum-scoped: classical + repertoire + contemporary (modern); pointe is a
    # prerequisite (not taught) so it is NOT a genre.
    assert set(o.genres) == {"classical", "repertoire", "contemporary"}
    assert "pointe" not in o.genres
    assert o.application.requirements == []
    assert o.prices == []


def test_nyari_core_fields_closed_cycle():
    o = hdu._build_nyari(_NYARI)
    assert o.id == "hungarian-dance-university/nyari-balett-studio-2026"
    assert o.title == "Nyári Balett Stúdió 2026"
    # Cross-month Hungarian span.
    assert o.schedule.start == date(2026, 7, 27)
    assert o.schedule.end == date(2026, 8, 2)
    assert o.age_range == {"min": 11, "max": 14}
    assert o.application.deadline == date(2026, 6, 10)
    assert o.application.status == "closed"
    # Hip-hop is out of scope and ignored; ballet genres remain.
    assert set(o.genres) == {"classical", "repertoire", "contemporary"}


def test_both_offerings_have_budapest_location():
    for o in (hdu._build_isibc(_ISIBC), hdu._build_nyari(_NYARI)):
        assert o.location is not None
        assert o.location.city == "Budapest"
        assert o.location.country == "HU"
        assert o.organization.slug == "hungarian-dance-university"
