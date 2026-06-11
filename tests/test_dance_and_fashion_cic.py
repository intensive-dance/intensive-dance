"""Offline tests for the Dance & Fashion CIC (TT Stage) scraper.

The real page is a long Italian Wix press round-up; the snippet keeps the current
edition paragraph plus a couple of stale press lines (a "15-27 luglio" excerpt) to
prove those don't get parsed as the dates.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import dance_and_fashion_cic as df

HTML = """
<html><head>
<meta name="description" content="Partecipa al TT Stage Ballet Summer intensive
2026 a Rapallo! Stage estivo di danza classica, punte, repertorio maschile e
femminile, pas de deux, danza di carattere, moderno per ballerini professionisti e
adulti amatoriali dall'Europa, USA, Russia, UK.">
</head><body>
<p>Dal 15 al 27 luglio si chiuder&#224; una stagione intensissima (vecchia
edizione, press).</p>
<p>Torniamo all'evento TTSTAGE Summer Course &amp; Ballet Gala, uno stage di danza
classica che si terr&#224; nella splendida citt&#224; di Rapallo da 20&#8203;
luglio 01 agosto 2026. Aperto a tutti i partecipanti di et&#224; dagli 11 anni in
su.</p>
<p>Il Ballet Gala per ballerini professionisti si terr&#224; il 01 agosto 2026.</p>
</body></html>
"""


def test_single_offering_current_edition():
    offerings = df._build_offering(HTML)
    assert offerings is not None
    o = offerings
    assert o.id == "dance-and-fashion-cic/summer-ballet-intensive-2026"
    assert o.title == "Summer Ballet Intensive TT Stage 2026"
    # The current edition span, not the stale "15-27 luglio" press line.
    assert o.schedule.start == date(2026, 7, 20)
    assert o.schedule.end == date(2026, 8, 1)


def test_genres_levels_ages():
    o = df._build_offering(HTML)
    assert o is not None
    assert o.genres == ["classical", "pointe", "repertoire", "character"]
    assert o.level == ["professional", "open"]
    assert o.age_range == {"min": 11, "max": None}
    # No fee / audition stated on the page.
    assert o.prices == []
    assert o.application.requirements == []
    assert o.location is not None and o.location.city == "Rapallo"


def test_no_date_yields_nothing():
    assert df._build_offering("<html><body><p>nessuna data</p></body></html>") is None
