"""Unit tests for the Académie Internationale d'Été de Nice scraper.

Pin the French-language parsing of the one dance-stage page: the
"Du 27 juillet au 1 Aout 2026" banner (shared trailing year, accent-free "Aout"),
the three level tiers and their minimum-age open-top range, the genres scoped to
the inscription course list (so a teacher bio can't leak a genre), and the weekly
tuition / accommodation / meal prices. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import academie_ete_nice as nice

_DATE_BANNER = "Académie Internationale d'Été de Nice Du 27 juillet au 1 Aout 2026 Planning"


def test_date_range_shared_year_accentless_aout():
    assert nice._date_range(_DATE_BANNER) == (date(2026, 7, 27), date(2026, 8, 1))


def test_date_range_with_er_and_accents():
    # "1er août" — ordinal suffix + accented month should still parse.
    start, end = nice._date_range("Du 1er août au 8 août 2027")
    assert (start, end) == (date(2027, 8, 1), date(2027, 8, 8))


def test_date_range_absent():
    assert nice._date_range("no dated stage here") == (None, None)


def test_age_range_min_only_open_top():
    text = (
        "Élementaire (à partir de 8 ans) Moyen - Intermédiaire (à partir de 11 ans) "
        "Avancé-Pro (à partir de 14 ans). Ouvert aux enfants, adolescents et adultes."
    )
    assert nice._age_range(text) == {"min": 8}


def test_age_range_absent():
    assert nice._age_range("aucune limite d'âge indiquée") is None


def test_levels_three_tiers():
    text = "Élementaire (à partir de 8 ans) Moyen - Intermédiaire Avancé-Pro (à partir de 14 ans)"
    assert nice._levels(text) == ["beginner", "intermediate", "advanced"]


def test_genres_scoped_to_course_list():
    # The teacher-bio prose names contemporary choreographers, but the course
    # list (the curriculum) decides the genres.
    text = (
        "Il a dansé le répertoire néoclassique et contemporain de Balanchine et Forsythe. "
        "Choix des cours * Barre à terre Classique Technique pointes Technique garçons "
        "Répertoire / Pas de deux Atelier chorégraphique contemporain "
        "Sélectionne au moins 1 cours."
    )
    assert nice._genres(text) == ["classical", "pointe", "repertoire", "contemporary"]


def test_genres_default_classical():
    assert nice._genres("Choix des cours * Barre à terre Sélectionne au moins 1 cours.") == [
        "classical"
    ]


def test_prices_weekly_tiers_meals_accommodation():
    text = (
        "Tarifs À la semaine Illimité "
        "1 cours par jour (soit 6 cours) Frais pédagogique 200€ Adhésion 20€ 220€ "
        "2 cours par jour (soit 12 cours) Frais pédagogique 371€ Adhésion 20€ 391€ "
        "Cours illimités Frais pédagogique 635€ Adhésion 20€ 655€ "
        "Déjeuner à la cantine 79€ la semaine "
        "Tarif : 370€ la semaine, du dimanche au dimanche"
    )
    prices = nice._prices(text)
    by_amount = {p.amount: p for p in prices}
    assert by_amount[220.0].includes == ["tuition"]
    assert "1 cours par jour" in (by_amount[220.0].label or "")
    assert by_amount[655.0].includes == ["tuition"]
    assert by_amount[79.0].includes == ["meals"]
    assert by_amount[370.0].includes == ["accommodation", "meals"]
    assert all(p.currency == "EUR" for p in prices)


def test_prices_daily_pass_tiers():
    text = (
        "1 journée en illimité Frais pédagogique 100€ Adhésion 20€ 120€ "
        "2 journées en illimité Frais pédagogique 200€ Adhésion 20€ 220€ "
        "3 journées en illimité Frais pédagogique 300€ Adhésion 20€ 320€ "
        "4 journées en illimité Frais pédagogique 400€ Adhésion 20€ 420€ "
        "5 journées en illimité Frais pédagogique 500€ Adhésion 20€ 520€"
    )
    prices = nice._prices(text)
    day_passes = [p for p in prices if "Day pass" in (p.label or "")]
    assert len(day_passes) == 5
    amounts = [p.amount for p in day_passes]
    assert amounts == [120.0, 220.0, 320.0, 420.0, 520.0]
    assert all(p.includes == ["tuition"] for p in day_passes)
    assert all(p.currency == "EUR" for p in day_passes)
    # Labels should identify the number of days
    assert "1 day" in (day_passes[0].label or "")
    assert "5 day" in (day_passes[4].label or "")


def test_build_offering_end_to_end():
    html = (
        "<html><body>"
        "<h1>Stage de danse</h1>"
        "<p>Académie Internationale d'Été de Nice Du 27 juillet au 1 Aout 2026 Planning</p>"
        "<p>Élementaire (à partir de 8 ans) Avancé-Pro (à partir de 14 ans)</p>"
        "<p>Choix des cours * Classique Technique pointes Répertoire / Pas de deux "
        "Atelier chorégraphique contemporain Sélectionne au moins 1 cours.</p>"
        "<p>1 cours par jour (soit 6 cours) Frais pédagogique 200€ Adhésion 20€ 220€</p>"
        "</body></html>"
    )
    offering = nice._build_offering(html)
    assert offering is not None
    assert offering.id == "academie-ete-nice/summer-dance-stage-2026"
    assert offering.schedule.start == date(2026, 7, 27)
    assert offering.schedule.end == date(2026, 8, 1)
    assert offering.genres == ["classical", "pointe", "repertoire", "contemporary"]
    assert offering.age_range == {"min": 8}
    assert offering.location is not None
    assert offering.location.city == "Nice"
    assert offering.location.venue == "Conservatoire de Nice"
    assert {t.name for t in offering.teachers} == {
        "Charles Jude",
        "Stéphanie Roublot",
        "Monique Loudières",
        "Thomas Klein",
        "Igor Yebra",
    }


def test_build_offering_none_without_dates():
    assert nice._build_offering("<html><body><p>no dates</p></body></html>") is None
