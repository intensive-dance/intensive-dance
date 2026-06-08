"""Unit tests for the Akademia Sztuki Baletowej scraper (Summer Dance Project).

The body is Polish in every render, so these pin the language-agnostic parse:
two dated sessions from a Polish "od … do …" announcement (one cross-month, one
single-month span), the PLN residential fee, the technique-keyed genres, the
"places limited" selectivity note, and that the full build emits one Offering per
session with the pinned faculty + affiliations. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import akademia_sztuki_baletowej as asb

# Trimmed but faithful to the live `/warsztaty/` page body (Polish prose).
PAGE = (
    "<p>OTWIERAMY ZAPISY NA OGÓLNOPOLSKIE LETNIE WARSZTATY AKADEMII SZTUKI "
    "BALETOWEJ GOŁUŃ 2026 &#8222;SUMMER DANCE PROJECT 2026&#8221;</p>"
    "<p>Zapraszamy na coroczne ogólnopolskie letnie warsztaty tańca i baletu "
    "w przepięknym Hotelu Gołuń. Warsztaty będą prowadzone w dwóch terminach: "
    "od 27 czerwca do 05 lipca 2026 roku oraz od 22 do 31 sierpnia 2026 roku "
    "przez wybitnych pedagogów i pierwszych solistów w technikach : taniec "
    "klasyczny, technika point, taniec współczesny, repertuar, partnerowanie "
    "(technika dolna i górna), stretching/pilates.</p>"
    "<p>Koszt warsztatów 3200zł. Wyśmienite cztery posiłki dziennie "
    "(szwedzki stół). Gościem specjalnym tego roku będzie Guido Marni. "
    "Ilość miejsc ograniczona!</p>"
)


def test_sessions_two_spans_cross_and_single_month():
    spans = asb._sessions(asb._plain_text(PAGE))
    assert spans == [
        (date(2026, 6, 27), date(2026, 7, 5)),
        (date(2026, 8, 22), date(2026, 8, 31)),
    ]


def test_sessions_deduped():
    text = "od 27 czerwca do 05 lipca 2026 ... od 27 czerwca do 05 lipca 2026 roku"
    assert asb._sessions(text) == [(date(2026, 6, 27), date(2026, 7, 5))]


def test_prices_pln_residential_full_board():
    (price,) = asb._prices(asb._plain_text(PAGE))
    assert price.amount == 3200.0
    assert price.currency == "PLN"
    assert set(price.includes) == {"tuition", "accommodation", "meals"}


def test_prices_absent_when_no_fee():
    assert asb._prices("Brak informacji o cenie.") == []


def test_genres_from_technique_list():
    genres = asb._genres(asb._plain_text(PAGE))
    assert genres == ["classical", "pointe", "contemporary", "repertoire"]


def test_genres_default_classical():
    assert asb._genres("warsztaty baletowe") == ["classical"]


def test_application_note_limited_places():
    assert asb._application_notes(asb._plain_text(PAGE)) == "Places are limited."
    assert asb._application_notes("Zapraszamy wszystkich.") is None


def test_build_offerings_full():
    offerings = asb._build_offerings(PAGE, date(2026, 1, 1))
    assert len(offerings) == 2

    first = offerings[0]
    assert first.id == "akademia-sztuki-baletowej/summer-dance-project-golun-2026-06-27"
    assert first.title == "Summer Dance Project — Gołuń 2026"
    assert first.schedule.season == "2026"
    assert first.schedule.start == date(2026, 6, 27)
    assert first.schedule.end == date(2026, 7, 5)
    assert first.schedule.timezone == "Europe/Warsaw"

    assert first.location is not None
    assert first.location.venue == "Hotel Gołuń"
    assert first.location.country == "PL"

    assert first.organization.slug == "akademia-sztuki-baletowej"
    assert first.application.deadline is None  # the 2025 deadline typo is not committed
    assert first.application.requirements == []  # nothing stated

    names = {t.name for t in first.teachers}
    assert "Guido Marni" in names
    assert "Jacek Walasik" in names

    guest = next(t for t in first.teachers if t.name == "Guido Marni")
    assert guest.role == "guest"
    assert {a.organization for a in guest.affiliations} == {
        "Teatro alla Scala",
        "National Ballet of Canada",
        "Semperoper Dresden",
    }

    second = offerings[1]
    assert second.schedule.start == date(2026, 8, 22)
    assert second.schedule.end == date(2026, 8, 31)
