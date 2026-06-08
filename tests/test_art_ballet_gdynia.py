"""Unit tests for the ART Ballet — ART Ballet Camp (Gdynia) scraper.

The site is Polish-only, so these pin the language-agnostic parse of the static
`/warsztaty` HTML: two dated single-month session spans ("7-16 lipca 2026" /
"15-22 sierpnia 2026"), the technique-keyed genres (classical/repertoire/
contemporary, with stretching/pilates excluded), the limited-places +
competition-prep notes, and the fail-open path (no fees/ages/faculty published →
empty/null). Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import art_ballet_gdynia as ab

# Trimmed but faithful to the live `/warsztaty` page body (Polish prose, the
# emoji bullets and the per-line <div> shapes the real page uses).
PAGE = (
    "<body>"
    "<h2>Warsztaty- LATO 2026</h2>"
    "<div>Wyjątkowe Warsztaty Baletowe dla Twojego Dziecka! 🩰</div>"
    "<div>📅 Terminy:</div>"
    "<div>➡️7-16 lipca 2026</div>"
    "<div>➡️15-22 sierpnia 2026</div>"
    "<div>📍 Miejsce: Hotel Gołuń, Wdzydzki Park Krajobrazowy</div>"
    "<div>✅ Lekcje tańca klasycznego – profesjonalna kadra pedagogiczna.</div>"
    "<div>✅ Praca nad repertuarem – nauka wariacji baletowych.</div>"
    "<div>✅ Stretching i pilates – dla lepszej kondycji i elastyczności.</div>"
    "<div>✅ Taniec współczesny – rozwój umiejętności ruchowych.</div>"
    "<div>✅ Przygotowanie do nowego sezonu konkursowego.</div>"
    "<div>⚠ Liczba miejsc ograniczona! Zapisy trwają!</div>"
    "</body>"
)


def test_sessions_two_single_month_spans():
    spans = ab._sessions(ab._plain_text(PAGE))
    assert spans == [
        (date(2026, 7, 7), date(2026, 7, 16)),
        (date(2026, 8, 15), date(2026, 8, 22)),
    ]


def test_sessions_deduped():
    text = "7-16 lipca 2026 ... 7-16 lipca 2026 roku"
    assert ab._sessions(text) == [(date(2026, 7, 7), date(2026, 7, 16))]


def test_sessions_absent_when_no_dates():
    assert ab._sessions("Brak terminów.") == []


def test_genres_from_class_list_excludes_stretching():
    genres = ab._genres(ab._plain_text(PAGE))
    assert genres == ["classical", "repertoire", "contemporary"]


def test_genres_default_classical():
    assert ab._genres("warsztaty baletowe") == ["classical"]


def test_application_notes_limited_and_competition():
    note = ab._application_notes(ab._plain_text(PAGE))
    assert note == ("Places are limited. Includes preparation for the new competition season.")


def test_application_notes_absent():
    assert ab._application_notes("Zapraszamy wszystkich.") is None


def test_build_offerings_full():
    offerings = ab._build_offerings(PAGE, date(2026, 1, 1))
    assert len(offerings) == 2

    first = offerings[0]
    assert first.id == "art-ballet-gdynia/camp-golun-2026-07-07"
    assert first.title == "ART Ballet Camp — Gołuń 2026"
    assert first.schedule.season == "2026"
    assert first.schedule.start == date(2026, 7, 7)
    assert first.schedule.end == date(2026, 7, 16)
    assert first.schedule.timezone == "Europe/Warsaw"

    assert first.location is not None
    assert first.location.venue == "Hotel Gołuń"
    assert first.location.country == "PL"

    assert first.organization.slug == "art-ballet-gdynia"
    assert first.genres == ["classical", "repertoire", "contemporary"]

    # Fail-open: nothing published for these on the page.
    assert first.prices == []
    assert first.age_range is None
    assert first.teachers == []
    assert first.application.requirements == []
    assert first.application.deadline is None

    second = offerings[1]
    assert second.id == "art-ballet-gdynia/camp-golun-2026-08-15"
    assert second.schedule.start == date(2026, 8, 15)
    assert second.schedule.end == date(2026, 8, 22)
