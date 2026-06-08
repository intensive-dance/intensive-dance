"""Unit tests for the Les Ballets de Pologne scraper (summer ballet workshop).

The body is Polish in every render, so these pin the language-agnostic parse:
two dated 2023 editions (one single-month span "3-9 lipca", one cross-month
"28 sierpnia - 2 września"), the default classical genre, the "places limited"
selectivity note, and the fail-open full build (no invented price/age/level/
faculty). Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import les_ballets_de_pologne as lbp

# Trimmed but faithful to the live `/warsztaty-wakacyjne/` page body (Polish prose).
PAGE = (
    "<body><main><h2>Warsztaty wakacyjne</h2>"
    "<p>Kochani! Powtarzamy naszą edycję warsztatów baletowych! Tym razem "
    "widzimy się w dniach 3-9 lipca 2023!</p>"
    "<p>Zapraszamy na warsztaty baletowe w wakacje! 28 sierpnia - 2 września 2023</p>"
    "<p><strong>INFORMACJE OGÓLNE</strong></p>"
    "<p>Zapisy: obowiązują zapisy mailowe na lesballetsdepologne@gmail.com. "
    "Limit miejsc: w każdej grupie obowiązuje limit 12 osób. "
    "Strój na warsztatach jest dowolny.</p></main></body>"
)


def test_editions_single_and_cross_month():
    spans = lbp._editions(lbp._plain_text(PAGE))
    assert spans == [
        (date(2023, 7, 3), date(2023, 7, 9)),
        (date(2023, 8, 28), date(2023, 9, 2)),
    ]


def test_editions_deduped():
    text = "3-9 lipca 2023 ... powtarzamy 3-9 lipca 2023"
    assert lbp._editions(text) == [(date(2023, 7, 3), date(2023, 7, 9))]


def test_editions_none_when_undated():
    assert lbp._editions("Warsztaty wakacyjne — terminy wkrótce!") == []


def test_genres_default_classical():
    assert lbp._genres("warsztaty baletowe w wakacje") == ["classical"]


def test_genres_pointe_when_named():
    assert lbp._genres("balet i pointy / praca na puentach") == ["classical", "pointe"]


def test_application_note_group_limit():
    text = lbp._plain_text(PAGE)
    assert lbp._application_notes(text) == "Places limited to 12 per group."
    assert lbp._application_notes("Zapisy mailowe, bez limitu.") is None


def test_build_offerings_full():
    offerings = lbp._build_offerings(PAGE, date(2023, 1, 1))
    assert len(offerings) == 2

    first = offerings[0]
    assert first.id == "les-ballets-de-pologne/warsztaty-wakacyjne-2023-07-03"
    assert first.title == "Summer ballet workshop 2023"
    assert first.genres == ["classical"]
    assert first.schedule.season == "2023"
    assert first.schedule.start == date(2023, 7, 3)
    assert first.schedule.end == date(2023, 7, 9)
    assert first.schedule.timezone == "Europe/Warsaw"

    assert first.location is not None
    assert first.location.city == "Warszawa"
    assert first.location.country == "PL"

    assert first.organization.slug == "les-ballets-de-pologne"
    # Fail-open: the page states no price/age/level/faculty for the workshop.
    assert first.prices == []
    assert first.age_range is None
    assert first.level == []
    assert first.teachers == []
    assert first.application.requirements == []  # email-only signup, nothing stated
    assert first.application.notes == "Places limited to 12 per group."

    second = offerings[1]
    assert second.id == "les-ballets-de-pologne/warsztaty-wakacyjne-2023-08-28"
    assert second.schedule.start == date(2023, 8, 28)
    assert second.schedule.end == date(2023, 9, 2)
