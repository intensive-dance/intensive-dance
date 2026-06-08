"""Unit tests for the Młody Balet Polski (Summer Ballet Workshops) scraper.

Source-shaped inline HTML only — no network. The fixture mirrors the live
"Summer Ballet Workshops" announcement page: a Polish-genitive August date range
("10-21 sierpnia 2026"), two labelled age tracks ("Wiek 11-19" / "Wiek 6-10")
each with its own hours + Polish programme word list, and phone-only
registration (no fee stated).
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import mlody_balet_polski as m

# A faithful, condensed slice of the live article (Polish kept verbatim).
PAGE = """<!DOCTYPE html>
<html lang="pl"><head><title>Summer Ballet Workshops 10-21 sierpnia 2026 - Młody Balet Polski</title></head>
<body>
  <header><nav>Start Informacje Szkoła</nav></header>
  <main>
    <h1>Summer Ballet Workshops 10-21 sierpnia 2026</h1>
    <p>Letnie Warsztaty Baletowe 2026</p>
    <p>Termin 10-21 sierpnia ( 10 dni)</p>
    <p>Zajęcia od poniedziałku do piątku</p>
    <p>Wiek 11-19 godz. 9.00-15.00</p>
    <p>Program: Balet / Pointy/ Pilates/ Stretching/ Repertuar</p>
    <p>Wiek 6-10 godz. 15.00-17.00</p>
    <p>Program: Balet podstawy/ Gimnastyka</p>
    <p>Rejestracja telefoniczna: 696018760</p>
    <p>Ilość miejsc ograniczona.</p>
  </main>
  <footer>Copyright @ 2017 Młody Balet Polski</footer>
</body></html>"""

# Off-season: the announcement page is up but carries no dated edition.
PAGE_NO_DATES = """<!DOCTYPE html>
<html lang="pl"><head><title>Letnie Warsztaty - Młody Balet Polski</title></head>
<body><main>
  <h1>Letnie Warsztaty Baletowe</h1>
  <p>W drugiej połowie sierpnia organizujemy intensywne warsztaty. Szczegóły wkrótce.</p>
</main></body></html>"""


def test_date_range_polish_genitive_august():
    assert m._date_range(m._page_text(PAGE)) == (date(2026, 8, 10), date(2026, 8, 21))


def test_build_offering_core_fields():
    o = m._build_offering(PAGE, date(2026, 6, 8))
    assert o is not None
    assert o.id == "mlody-balet-polski/summer-intensive-2026"
    assert o.title == "Summer Ballet Workshops 2026"
    assert o.schedule.season == "2026"
    assert o.schedule.start == date(2026, 8, 10)
    assert o.schedule.end == date(2026, 8, 21)
    assert o.schedule.timezone == "Europe/Warsaw"
    assert o.organization.slug == "mlody-balet-polski"
    assert o.location is not None
    assert o.location.city == "Warszawa"
    assert o.location.country == "PL"


def test_two_age_sessions_keep_their_own_ages():
    o = m._build_offering(PAGE, date(2026, 6, 8))
    assert o is not None
    assert len(o.schedule.sessions) == 2
    ages = [s.age_range for s in o.schedule.sessions]
    assert {"min": 11, "max": 19} in ages
    assert {"min": 6, "max": 10} in ages
    # The combined ageRange spans both tracks.
    assert o.age_range == {"min": 6, "max": 19}
    # Each session keeps its own raw programme text.
    senior = next(s for s in o.schedule.sessions if s.age_range == {"min": 11, "max": 19})
    assert senior.notes is not None
    assert "Pointy" in senior.notes
    assert "Repertuar" in senior.notes


def test_genres_from_programme_words():
    o = m._build_offering(PAGE, date(2026, 6, 8))
    assert o is not None
    # Balet → classical, Pointy → pointe, Repertuar → repertoire. The programme
    # never lists contemporary/character, so those are not emitted.
    assert set(o.genres) == {"classical", "pointe", "repertoire"}


def test_no_price_when_registration_is_phone_only():
    o = m._build_offering(PAGE, date(2026, 6, 8))
    assert o is not None
    assert o.prices == []


def test_director_emitted_as_teacher():
    o = m._build_offering(PAGE, date(2026, 6, 8))
    assert o is not None
    assert [t.name for t in o.teachers] == ["Anna Davies"]
    assert o.teachers[0].role == "director"


def test_no_dated_edition_defers():
    assert m._build_offering(PAGE_NO_DATES, date(2026, 6, 8)) is None
