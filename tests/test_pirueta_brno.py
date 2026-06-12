from __future__ import annotations

from intensive_dance.scrapers.pirueta_brno import _build_offerings

# Trimmed from the live /portfolio/soustredeni/ page (WordPress, custom UA).
HTML = """
<html><body>
<h1>Letní baletní soustředění</h1>
<p>Na letní prázdniny 2026 nabízíme rodičům možnost přihlásit své dítě na 26.
ročník Letního baletního soustředění. Určeno pro děti ve věku 6 – 17 let
s baletní průpravou. Účastnit se mohou i žáci jiných škol a tanečních studií.</p>
<p><span style="font-family: verdana,geneva;"><strong>Termín konání: </strong>27.7. – 2.8.2026</span></p>
<p><span style="font-family: verdana,geneva;"><strong>Místo konání: </strong>
<a href="https://www.parkhotelmozolov.cz/">ParkHOTEL MOZOLOV ***</a>&nbsp; Nadějkov – Mozolov 7.</span></p>
<p><span style="font-family: verdana,geneva;"><strong>Cena:</strong>&nbsp; 9.580,- zahrnuje pobyt
s ubytováním 7 dní (6 nocí) s plnou penzí a celodenní program s výukou baletu,
materiál na výrobu rekvizit, soutěžní ceny, pronájem prostor a vybavení.</span></p>
<p><span style="font-family: verdana,geneva;"><strong>Program:</strong> výuka baletu,
tvorba a prezentace choreografií, výroba rekvizit, sportovní hry a soutěže.</span></p>
<p><span style="font-family: verdana,geneva;">Pokud Vás naše nabídka zaujala,
<strong>nejpozději do 31.3.2026</strong>&nbsp;
<a href="https://pirueta.cz/prihlasky/vyuka-pro-deti/objednavka-soustredeni/">vyplňte přihlášku</a>.</span></p>
</body></html>
"""

# Edge: no dates / no price stated yet (a not-yet-announced edition).
HTML_BARE = """
<html><body>
<h1>Letní baletní soustředění</h1>
<p>Připravujeme další ročník Letního baletního soustředění s výukou baletu.</p>
</body></html>
"""


def test_happy():
    offers = _build_offerings(HTML)
    assert len(offers) == 1
    o = offers[0]
    assert o.id == "pirueta-brno/letni-baletni-soustredeni-2026"
    assert o.title == "Letní baletní soustředění"
    assert o.genres == ["classical"]

    assert o.age_range == {"min": 6, "max": 17}

    assert o.schedule.start is not None and o.schedule.end is not None
    assert o.schedule.start.isoformat() == "2026-07-27"
    assert o.schedule.end.isoformat() == "2026-08-02"
    assert o.schedule.season == "2026"
    assert o.schedule.timezone == "Europe/Prague"

    assert len(o.prices) == 1
    price = o.prices[0]
    assert price.amount == 9580.0
    assert price.currency == "CZK"
    assert "accommodation" in price.includes and "tuition" in price.includes

    assert o.location is not None
    assert o.location.venue == "ParkHOTEL MOZOLOV"
    assert o.location.city == "Nadějkov"

    assert o.application.deadline is not None
    assert o.application.deadline.isoformat() == "2026-03-31"
    assert o.application.url is not None
    assert o.application.url.endswith("/objednavka-soustredeni/")
    assert o.application.requirements == []
    assert o.application.status is None


def test_bare_edition_emits_open_fields():
    offers = _build_offerings(HTML_BARE)
    assert len(offers) == 1
    o = offers[0]
    assert o.schedule.start is None and o.schedule.end is None
    assert o.schedule.season == "2026"
    assert o.prices == []
    assert o.age_range is None
    assert o.application.deadline is None
    # The programme still names ballet, so the genre survives.
    assert o.genres == ["classical"]
