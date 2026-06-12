from datetime import date

from intensive_dance.scrapers import ballettratten

# Trimmed but faithful to the live Teenager detail page (German, Joomla).
TEENAGER = """
<html><body>
<h1>Sommerintensivkurs 2026 - Teenager</h1>
<h2>Teenager (10 - 18 Jahre)</h2>
<p>13. - 17. Juli 2026 &nbsp; 15.00 - 18.00 Uhr</p>
<p>Im Sommer 2026 bieten wir einen Sommerintensivkurs für Jugendliche von
10 - 18 Jahren an. In diesen 5 Tagen wird intensives Balletttraining mit
zusätzlichen Einheiten für Spitzentechnik und Variationsunterricht stattfinden.
Teilnehmer/innen werden nach Alter und Niveau in verschiedenen Gruppen
unterrichtet.</p>
<ul>
<li>15.30 - 16.45 Uhr Klassisches Training</li>
<li>17.00 - 18.00 Uhr Spitze / Klassische Variation</li>
</ul>
<p>Kosten: € 320</p>
<p>Ballettinstitut Döbling, 1. Stock<br>1190 Wien, Billrothstr. 16</p>
<p>Anmeldung: esther.kainz@ballettratten.com</p>
<script>var x = "13. - 99. Dezember 2099";</script>
</body></html>
"""


def test_teenager_offering():
    offerings = ballettratten._build_offerings(TEENAGER)
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "ballettratten/sommerintensivkurs-teenager-2026"
    assert o.title == "Sommerintensivkurs – Teenager"
    assert o.schedule.start == date(2026, 7, 13)
    assert o.schedule.end == date(2026, 7, 17)
    assert o.schedule.season == "2026"
    assert o.age_range == {"min": 10, "max": 18}
    assert set(o.genres) == {"classical", "pointe", "repertoire"}
    assert o.location is not None
    assert o.location.venue == "Ballettinstitut Döbling"
    assert o.location.city == "Vienna"
    assert len(o.prices) == 1
    assert o.prices[0].amount == 320.0
    assert o.prices[0].currency == "EUR"
    assert o.application.status == "open"
    # email-only registration, no audition gate
    assert o.application.requirements == []


def test_script_date_not_picked():
    # The <script> tag's fake date must be stripped before date matching.
    offerings = ballettratten._build_offerings(TEENAGER)
    assert offerings[0].schedule.start == date(2026, 7, 13)


MISSING_DATE = """
<html><body>
<h2>Teenager (10 - 18 Jahre)</h2>
<p>Termin folgt in Kürze.</p>
<p>Kosten: € 320</p>
</body></html>
"""


def test_missing_date_fails_open():
    o = ballettratten._build_offerings(MISSING_DATE)[0]
    assert o.schedule.start is None
    assert o.schedule.end is None
    assert o.schedule.season == "2026"
    assert o.schedule.notes is None
    # age + price still extracted
    assert o.age_range == {"min": 10, "max": 18}
    assert o.prices[0].amount == 320.0
