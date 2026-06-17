from datetime import date

from intensive_dance.scrapers import baletni_akademie_pollertova as bap

HOME = """
ČERVENEC A SRPEN 2026 - letní kurzy
Kurzy baletu v letních měsících - více informací, termíny a přihlášky
Letní soustředění pro děti
Letní soustředění pro mladší děti - 10.8.-14.8. 2026
Letní soustředění pro starší děti - 17.8.-21.8. 2026
Rušíte-li účast na akci (kurz, otevřená lekce, letní soustředění pro děti) ...
Na Poříčí 25, Praha 1, 110 00
"""


def test_emits_two_dated_editions():
    offerings = bap._build_offerings(HOME)
    assert len(offerings) == 2
    younger, older = offerings
    assert younger.id == "baletni-akademie-pollertova/younger-children-2026"
    assert younger.title == "Summer Intensive for Younger Children 2026"
    assert younger.schedule.start == date(2026, 8, 10)
    assert younger.schedule.end == date(2026, 8, 14)
    assert older.id == "baletni-akademie-pollertova/older-children-2026"
    assert older.schedule.start == date(2026, 8, 17)
    assert older.schedule.end == date(2026, 8, 21)


def test_genre_location_and_raw_notes():
    younger = bap._build_offerings(HOME)[0]
    assert younger.genres == ["classical"]
    assert younger.schedule.season == "summer"
    assert younger.location is not None
    assert younger.location.city == "Prague" and younger.location.country == "CZ"
    assert younger.location.venue == "Na Poříčí 25, Praha 1"
    assert "mladší" in (younger.schedule.notes or "")


def test_no_unstated_fields_invented():
    younger = bap._build_offerings(HOME)[0]
    assert younger.age_range is None
    assert younger.level == []
    assert younger.prices == []
    assert younger.teachers == []
    assert younger.application.status is None


def test_header_line_without_dates_is_skipped():
    # "Letní soustředění pro děti" (no date span) must not become an offering
    assert bap._build_offerings("Letní soustředění pro děti\n") == []
