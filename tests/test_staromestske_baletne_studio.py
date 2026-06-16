from __future__ import annotations

from intensive_dance.scrapers.staromestske_baletne_studio import _build_offerings

# Trimmed from the live article: a younger dance camp (out of scope) BEFORE the
# youth school, and the English camp AFTER it — to prove the block slicing keeps
# only the youth course's dates/ages/prices.
HTML = """
<html><body>
<h3><strong>Letný tanečný tábor so Staromestským baletným štúdiom</strong></h3>
<p><strong>Školská 14</strong><br>
<strong>Termín a čas:</strong> 6. 7. – 10. 7. 2026 / 8.00 - 16:00</p>
<p><strong>Vek:</strong> pre deti 8 - 11 rokov<br>
Okrem tanečných lekcií baletu a moderného tanca bude program doplnený workshopom herectva.<br>
<strong>Cena:</strong> 160 € / 144 € pre obyvateľstvo Starého mesta (v cene sú zahrnuté obedy)</p>

<h3><strong>Letná škola tanca pre mládež 12 – 18 rokov</strong></h3>
<p><strong>Termín a čas: </strong> 17. - 21. 8. 2026 /  9:00 - 15:30<br>
Každý deň lekcia: Telohra a súčasný tanec, moderný tanec a tanečná variácia, balet.
Jedno poobedie pozeranie tanečného videa.<br>
Skúsenosť s tancom alebo s iným pohybom je pre LTŠ mládež vítaná a potrebná.<br>
<strong>Cena:</strong> 160 € / 144 € pre obyvateľstvo Starého mesta (v cene sú zahrnuté obedy)<br>
<strong>Prihlasovanie</strong>:
<a href="https://forms.cloud.microsoft/e/FcLx0FdfvU">Prihláška dieťaťa na letnú školu tanca pre mládež</a></p>

<h3>Letný denný tábor English Summer Day Camp</h3>
<p>Tábor je určený deťom vo veku 7 – 12 rokov.<br>
6. – 10. 7. 2026<br>
<strong>Vstupné:</strong> 230 € / 210 € pre obyvateľstvo Starého Mesta</p>
</body></html>
"""

# Edge: the youth block is missing entirely (e.g. only the recreational camps
# published) → nothing emitted.
HTML_NO_YOUTH = """
<html><body>
<h3><strong>Letný tanečný tábor so Staromestským baletným štúdiom</strong></h3>
<p><strong>Termín a čas:</strong> 6. 7. – 10. 7. 2026<br>
<strong>Vek:</strong> pre deti 8 - 11 rokov</p>
</body></html>
"""


def test_emits_only_youth_school():
    offers = _build_offerings(HTML)
    assert len(offers) == 1
    o = offers[0]
    assert o.id == "staromestske-baletne-studio/letna-skola-tanca-mladez-2026"
    assert o.title == "Letná škola tanca pre mládež"

    # Dates/ages come from the youth block, NOT the younger camp above it.
    assert o.age_range == {"min": 12, "max": 18}
    assert o.schedule.start is not None and o.schedule.end is not None
    assert o.schedule.start.isoformat() == "2026-08-17"
    assert o.schedule.end.isoformat() == "2026-08-21"
    assert o.schedule.season == "2026"
    assert o.schedule.timezone == "Europe/Bratislava"

    assert set(o.genres) == {"classical", "contemporary", "repertoire"}

    assert len(o.prices) == 2
    standard, resident = o.prices
    assert standard.amount == 160.0 and standard.currency == "EUR"
    assert "meals" in standard.includes and "tuition" in standard.includes
    assert standard.label is None
    assert resident.amount == 144.0
    assert resident.label == "Obyvatelia Starého Mesta"

    assert o.location is not None
    assert o.location.city == "Bratislava"
    assert o.application.url == "https://forms.cloud.microsoft/e/FcLx0FdfvU"
    assert o.application.requirements == []
    assert o.application.status is None


def test_no_youth_block_emits_nothing():
    assert _build_offerings(HTML_NO_YOUTH) == []
