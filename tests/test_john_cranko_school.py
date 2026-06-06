"""Unit tests for the John Cranko School Summer School scraper (German page)."""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import john_cranko_school as jcs


def test_date_range_german_span():
    text = "Montag, 1. Juni 2026 bis Samstag, 6. Juni 2026 Alter 12 - 19 Jahre"
    assert jcs._date_range(text) == (date(2026, 6, 1), date(2026, 6, 6))


def test_deadline():
    assert jcs._deadline("Einsendeschluss: Freitag, 08. Mai 2026") == date(2026, 5, 8)
    assert jcs._deadline("kein Datum hier") is None


def test_age_range():
    assert jcs._age_range("Alter 12 - 19 Jahre") == {"min": 12, "max": 19}


def test_genres_from_german_disciplines():
    text = (
        "Klassisches Ballett, Spitzenschuhe, Contemporary, Repertoire, Pas de deux, Spanischer Tanz"
    )
    assert jcs._genres(text) == ["classical", "contemporary", "repertoire", "character", "pointe"]


def test_requirements_cover_video_and_full_body_photo():
    # The page asks for a video AND a full-body photo in a leotard; both must be
    # emitted (the photo was previously dropped).
    offering = jcs._build_offering(
        "<html><body>Montag, 1. Juni 2026 bis Samstag, 6. Juni 2026</body></html>",
        date(2026, 1, 1),
    )
    assert offering is not None
    types = sorted(r.type for r in offering.application.requirements)
    assert types == ["photos", "video"]


def test_price_includes_performance():
    text = "Die Kosten für 6 Tage Unterricht und die Aufführung betragen insgesamt 650,00 €."
    (price,) = jcs._prices(text)
    assert (price.amount, price.currency, price.includes) == (
        650.0,
        "EUR",
        ["tuition", "performance"],
    )
