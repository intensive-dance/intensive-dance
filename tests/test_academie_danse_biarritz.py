"""Unit tests for the Académie Internationale de Danse de Biarritz scraper.

The site is WordPress; each detail page comes back as `content.rendered` HTML.
These pin the parsing offline: the year-less day-month date lines (year read off
the "… août 2026" headline), the age/level tiers (beginners excluded), the
curriculum genres, the public-tier price table, the Elementor-reordered faculty
roster (names then affiliations, paired positionally, pianists dropped), and the
end-to-end `_build_offering`. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import academie_danse_biarritz as b

# A faithful slice of the infos-pratiques page: the two year-less course-day lines
# and the price table (Carte | Pour tous | Grandes écoles | Professionnels).
_INFOS_HTML = """
<div>
  <p>Début des cours : dimanche 2 août</p>
  <p>Fin des cours : vendredi 7 août en fin d’après-midi</p>
  <p>Lieu du stage Lycée hôtelier Biarritz Atlantique 64200 Biarritz</p>
  <h3>Tarifs des cours 2026</h3>
  <table>
    <tr><th>Carte</th><th>Pour tous</th><th>Grandes écoles et Eurocité (1)</th><th>Professionnels (2)</th></tr>
    <tr><td>6 cours (1 cours/jour)</td><td>240 €</td><td>220 €</td><td>–</td></tr>
    <tr><td>12 cours (2 cours/jour)</td><td>380 €</td><td>340 €</td><td>–</td></tr>
    <tr><td>cours illimités</td><td>520 €</td><td>480 €</td><td>300 €</td></tr>
  </table>
</div>
"""

# The presentation page: the "août 2026" headline carries the year, plus the
# level/age tiers (beginners excluded) and the curriculum.
_PRESENTATION_HTML = """
<div>
  <p>Prochaine édition : du 2 au 7 août 2026</p>
  <p>Il n’y a pas de cours pour les débutants, un minimum de deux ans de danse est requis.</p>
  <p>Élémentaire : 9/10 ans Moyen : 11/12 ans Intermédiaire : 12/14 ans
     Avancé : 14/16 ans Supérieur : plus de 16 ans, pré-professionnel et professionnel</p>
  <p>cours de classique, une barre à terre, un cours spécifique pointes, un atelier
     chorégraphique Malandain, cours de répertoire, cours d’adage. Cours adultes amateurs.</p>
</div>
"""

# The équipe-pédagogique page as Elementor renders it: every <h4> name first,
# then the block of affiliation/text widgets (matching document order). Two
# teachers share "Opéra national de Paris"; pianists have no affiliation line.
_EQUIPE_HTML = """
<div class="elementor">
  <h2>Équipe pédagogique</h2>
  <h3>Professeurs</h3>
  <h4>Carole Arbo</h4>
  <h4>Eric Quilleré</h4>
  <h4>Delphine Moussin</h4>
  <h3>Ateliers</h3>
  <h4>Ione Miren Aguirre</h4>
  <h3>Pianistes</h3>
  <h4>Laurent Choukroun</h4>
  <div class="elementor-widget-text-editor"><p>Grâce à sa riche équipe pédagogique, l’Académie propose de nombreux courants représentés par les plus grandes écoles internationales du monde entier réunies ici chaque été.</p></div>
  <div class="elementor-widget-text-editor"><p>Opéra national de Paris</p></div>
  <div class="elementor-widget-text-editor"><p>Opéra National de Bordeaux</p></div>
  <div class="elementor-widget-text-editor"><p>Opéra national de Paris</p></div>
  <div class="elementor-widget-text-editor"><p>Ateliers</p></div>
  <div class="elementor-widget-text-editor"><p>Atelier Thierry Malandain</p></div>
  <div class="elementor-widget-text-editor"><p>Pianistes</p></div>
</div>
"""

_ETAUSSI_HTML = """
<div><p>Une démonstration publique des stagiaires aura lieu le mardi 4 août 2026
à 21h au théâtre de la Gare du Midi de Biarritz. Gratuit en entrée libre.</p></div>
"""


def test_date_range_yearless_lines_with_headline_year():
    infos = b._text(_INFOS_HTML)
    year_text = b._text(_PRESENTATION_HTML)
    assert b._date_range(infos, year_text) == (date(2026, 8, 2), date(2026, 8, 7))


def test_date_range_absent_without_year():
    # Day-month lines but no "<month> <year>" headline → no parseable edition.
    assert b._date_range("Début des cours : dimanche 2 août", "no year here") == (None, None)


def test_age_range_lower_bound_open_top():
    # Smallest tier age (9); top open because pre-pro/pro adults are welcome.
    assert b._age_range(b._text(_PRESENTATION_HTML)) == {"min": 9}


def test_levels_exclude_beginner():
    levels = b._levels(b._text(_PRESENTATION_HTML))
    assert "beginner" not in levels
    assert set(levels) == {"intermediate", "advanced", "pre-professional", "professional", "open"}


def test_genres():
    assert b._genres(b._text(_PRESENTATION_HTML)) == [
        "classical",
        "pointe",
        "repertoire",
        "contemporary",
    ]


def test_genres_default_classical():
    assert b._genres("aucune mention de cours ici") == ["classical"]


def test_prices_public_tier_with_reduced_note():
    prices = b._prices(_INFOS_HTML)
    assert [(p.amount, p.currency, p.includes) for p in prices] == [
        (240.0, "EUR", ["tuition"]),
        (380.0, "EUR", ["tuition"]),
        (520.0, "EUR", ["tuition"]),
    ]
    assert prices[0].label == "Carte « 6 cours (1 cours/jour) » (tarif plein)"
    assert prices[0].notes == "Reduced: grandes écoles/eurocités 220 €."
    # The illimités row carries the only professional tier.
    assert prices[2].notes == "Reduced: grandes écoles/eurocités 480 €; professionnels 300 €."


def test_teachers_pair_positionally_share_affiliation_drop_pianists():
    teachers = b._teachers(_EQUIPE_HTML)
    pairs = [(t.name, t.affiliations[0].organization) for t in teachers]
    assert pairs == [
        ("Carole Arbo", "Opéra national de Paris"),
        ("Eric Quilleré", "Opéra National de Bordeaux"),
        ("Delphine Moussin", "Opéra national de Paris"),  # shared affiliation kept
        ("Ione Miren Aguirre", "Atelier Thierry Malandain"),
    ]
    # The pianist (no affiliation line) is dropped — not dance faculty.
    assert "Laurent Choukroun" not in {t.name for t in teachers}


def test_schedule_note_demo():
    note = b._schedule_note(b._text(_ETAUSSI_HTML))
    assert note is not None
    assert "démonstration publique" in note
    assert "Gare du Midi" in note


def test_build_offering_end_to_end():
    pages = {
        "infos-pratiques": _INFOS_HTML,
        "presentation": _PRESENTATION_HTML,
        "equipe-pedagogique": _EQUIPE_HTML,
        "et-aussi": _ETAUSSI_HTML,
    }
    offering = b._build_offering(pages, date(2026, 6, 6))
    assert offering is not None
    assert offering.id == "academie-danse-biarritz/academy-2026"
    assert offering.title == "Académie Internationale de Danse de Biarritz 2026"
    assert offering.schedule.season == "2026"
    assert offering.schedule.start == date(2026, 8, 2)
    assert offering.schedule.end == date(2026, 8, 7)
    assert offering.location is not None
    assert offering.location.venue == "Lycée hôtelier Biarritz Atlantique"
    assert offering.location.country == "FR"
    assert len(offering.prices) == 3
    assert len(offering.teachers) == 4
    # Open enrolment: no audition requirements stated.
    assert offering.application.requirements == []
    assert offering.application.url == "https://biarritz-academie-danse.com/inscription/"


def test_build_offering_none_without_dates():
    assert b._build_offering({"presentation": "<p>aucune date</p>"}, date(2026, 6, 6)) is None
