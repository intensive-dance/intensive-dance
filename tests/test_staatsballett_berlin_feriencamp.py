"""Offline tests for the Staatsballett Berlin holiday-intensive scraper.

Inline HTML mirrors the TYPO3 detail pages (visually-hidden timeblock spans +
German description). No network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import staatsballett_berlin_feriencamp as sb

FERIENCAMP_HTML = """
<html><body>
<h1>Feriencamp</h1>
<label class="ni-timeblock-link"><span class="visually-hidden">Montag, 19. Oktober 2026 9:30</span></label>
<label class="ni-timeblock-link"><span class="visually-hidden">Dienstag, 30. März 2027 9:25</span></label>
<p>In diesem fünftägigen Feriencamp lernen Kinder und Jugendliche zwischen 12 und 16 Jahren,
die bereits Vorkenntnisse von mindestens fünf Jahren im Ballett mitbringen, die Spielarten des
Tanzes kennen. Der Vormittag ist dem klassischen Tanz vorbehalten ... Am Nachmittag lernen die
Teilnehmer*innen zeitgenössische Bewegungssprachen kennen. Der Kurs findet an allen Tagen von
9:30 - 16:00 Uhr in den Ballettsälen des Staatsballetts Berlin in der Staatsoper Unter den Linden
statt und kostet 200 Euro pro Person (exkl. Verpflegung).</p>
<div>Zurück zum Seitenanfang</div>
<footer>Ballettsäle Impressum 999 Euro Newsletter</footer>
</body></html>
"""

SPITZE_HTML = """
<html><body>
<h1>Ferienangebot</h1>
<label class="ni-timeblock-link"><span class="visually-hidden">Donnerstag, 9. Juli 2026 10:00</span></label>
<p>Ferienkurs "Spitze auf Spitze" für alle zwischen 14 und 20. Du tanzt bereits auf Spitze ...
Der Kurs richtet sich an Balletttänzer*innen zwischen 14 und 20 Jahren, die bereits Vorkenntnisse
im Spitzentanz mitbringen und über eigene Spitzenschuhe verfügen. Der Kurs findet am 9. und 10.
Juli sowie am 13. und 14. Juli, jeweils von 10:00 – 13:45 Uhr in den Sälen des Staatsballetts
Berlin in der Deutschen Oper statt und kostet 100 Euro pro Person.</p>
<div>Zurück zum Seitenanfang</div>
</body></html>
"""


def test_feriencamp_two_editions():
    offerings = sb._feriencamp(FERIENCAMP_HTML)
    assert [o.id for o in offerings] == [
        "staatsballett-berlin-feriencamp/feriencamp-2026",
        "staatsballett-berlin-feriencamp/feriencamp-2027",
    ]
    o2026, o2027 = offerings
    # five-day camp: end = start + 4
    assert o2026.schedule.start == date(2026, 10, 19)
    assert o2026.schedule.end == date(2026, 10, 23)
    assert o2027.schedule.start == date(2027, 3, 30)
    assert o2027.schedule.end == date(2027, 4, 3)
    assert o2026.age_range == {"min": 12, "max": 16}
    assert o2026.genres == ["classical", "contemporary"]
    # the 999 Euro in the footer (after "Zurück zum Seitenanfang") is excluded
    assert len(o2026.prices) == 1
    assert o2026.prices[0].amount == 200.0
    # a participation prerequisite is not an audition requirement
    assert o2026.application.requirements == []


def test_spitze_non_consecutive_span():
    o = sb._spitze(SPITZE_HTML)
    assert o.id == "staatsballett-berlin-feriencamp/spitze-auf-spitze-2026"
    assert o.schedule.start == date(2026, 7, 9)
    assert o.schedule.end == date(2026, 7, 14)
    assert o.age_range == {"min": 14, "max": 20}
    assert o.genres == ["classical", "pointe"]
    assert o.prices[0].amount == 100.0
    assert o.location is not None
    assert o.location.venue == "Deutsche Oper Berlin"
