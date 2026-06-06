"""Unit tests for the Académie Theilaïa scraper (WordPress / WPBakery page).

These pin the parsing of the Theilaïa "Stage International" page: the French
date range read from the page title ("du 13 au 17 juillet 2026"), the edition
stamp, the open-from-9 age band, the five level bands, the three EUR fee tiers
with their `includes`, the curriculum genres, and the registration opening date.
Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import academie_theilaia as t

_TITLE = "THEILAÏA – 24e Stage International du 13 au 17 juillet 2026"

# A trimmed but faithful slice of the rendered page text (post shortcode/CSS strip).
_TEXT = (
    "Cours ouverts aux Enfants dès 9 ans, Amateurs, Pré-professionnels, "
    "Professionnels, Adultes Répartition des cours sur 5 niveaux Élémentaire "
    "(9-11 ans), Intermédiaire (12-13 ans), Avancé (14-15 ans), Supérieur "
    "(à partir de 16 ans) et Adulte 4 à 6 cours par jour en fonction du niveau "
    "Tarif réduit 2026 appliqué pour toute inscription avant le 30 mars 2026 "
    "Tarifs 2026 ►Forfait tarif réduit 525 € prolongé possibilité de paiement "
    "►Carte de 4 cours adulte en soirée 150 € ►Hébergement en internat "
    "surveillé en pension complète 525 € "
    "Inscription au stage – à partir du lundi 12 janvier 2026 "
    "THEILAÏA offers classes including : Classical Ballet, Repertory, "
    "Pas de deux, Character Dance, Baroque Dance and Floor Barre."
)


def test_date_range_from_french_title():
    assert t._date_range(_TITLE) == (date(2026, 7, 13), date(2026, 7, 17))


def test_date_range_absent():
    assert t._date_range("THEILAÏA – Stage International") == (None, None)


def test_edition_label():
    assert t._edition_label(_TITLE) == "24e edition"
    assert t._edition_label("Stage International juillet 2026") is None


def test_age_range_open_from_nine():
    # Open from 9 with no upper bound (adults are included).
    assert t._age_range(_TEXT) == {"min": 9}


def test_age_range_absent():
    assert t._age_range("no age stated here") is None


def test_levels_all_five_bands():
    assert t._levels(_TEXT) == [
        "beginner",
        "intermediate",
        "advanced",
        "pre-professional",
        "professional",
        "open",
    ]


def test_prices_three_tiers_with_includes():
    prices = t._prices(_TEXT)
    assert [(p.amount, p.currency, p.includes, p.label) for p in prices] == [
        (525.0, "EUR", ["tuition"], "Forfait (4 à 6 cours par jour) — tarif réduit"),
        (150.0, "EUR", ["tuition"], "Carte de 4 cours adulte en soirée"),
        (
            525.0,
            "EUR",
            ["accommodation", "meals"],
            "Hébergement en internat surveillé (pension complète)",
        ),
    ]
    # The forfait carries the reduced-rate deadline as a note.
    assert "30 mars 2026" in (prices[0].notes or "")


def test_prices_absent():
    assert t._prices("no fees published") == []


def test_genres_from_curriculum():
    assert t._genres(_TEXT) == ["classical", "repertoire", "character"]


def test_genres_default_classical():
    assert t._genres("no curriculum keywords here") == ["classical"]


def test_opens_at_french_date():
    assert t._opens_at(_TEXT) == date(2026, 1, 12)


def test_opens_at_absent():
    assert t._opens_at("registration details to follow") is None


def test_application_status_open_after_opening():
    app = t._application(_TEXT, "https://www.academie-ballet.fr/x/")
    # Opening (12 Jan 2026) is in the past, so registration is open.
    assert app.status == "open"
    assert app.opens_at == date(2026, 1, 12)
    assert app.url == "https://www.academie-ballet.fr/x/"
    assert app.requirements == []  # open enrolment, no audition described


def test_build_offering_full():
    rendered = (
        "[vc_row][vc_column_text]"
        "<style>.foo{color:#000}</style>"
        f"<p>{_TEXT}</p>"
        "[/vc_column_text][/vc_row]"
    )
    offering = t._build_offering(_TITLE, rendered, "https://www.academie-ballet.fr/x/")
    assert offering is not None
    assert offering.id == "academie-theilaia/stage-international-2026"
    assert offering.title == "Theilaïa — Stage International 2026 (24e edition)"
    assert offering.schedule.start == date(2026, 7, 13)
    assert offering.schedule.end == date(2026, 7, 17)
    assert offering.schedule.season == "2026"
    assert offering.organization.slug == "academie-theilaia"
    assert offering.location is not None
    assert offering.location.city == "Lyon"
    assert offering.location.country == "FR"
    assert "CNSMD" in (offering.location.venue or "")
    assert offering.genres == ["classical", "repertoire", "character"]
    assert offering.age_range == {"min": 9}
    assert [p.amount for p in offering.prices] == [525.0, 150.0, 525.0]


def test_build_offering_no_dates_returns_none():
    # No parseable dated edition in the title → don't fabricate an Offering.
    rendered = "[vc_row][vc_column_text]<p>Stage info à venir.</p>[/vc_column_text][/vc_row]"
    assert t._build_offering("THEILAÏA – Stage International", rendered, "https://x/") is None
