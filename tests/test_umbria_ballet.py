"""Offline tests for the Umbria Ballet (Legacy Master of Ballet) scraper.

Inline WPBakery-shaped `content.rendered` snippets mirror the real page. No network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import PhotosReq, VideoReq
from intensive_dance.scrapers import umbria_ballet as ub

INFO_RENDERED = """
[vc_row][vc_column][vc_column_text]
<p>Legacy Master of Ballet — Seconda Edizione. Dal 29 giugno al 4 luglio 2026, ad Assisi.</p>
[/vc_column_text]
<h2>LE LEZIONI</h2>
[vc_column_text]
<p>6 Lezioni al giorno per ogni livello<br />Tecnica classica<br />Tecnica maschile<br />
Lezioni di Punte<br />Lezioni di contemporaneo<br />Laboratorio coreografico<br />Yoga</p>
[/vc_column_text]
<h2>ISCRIZIONI</h2>
[vc_column_text]<p>Lo stage è a numero chiuso. Si può partecipare solo dopo avere superato la selezione foto/video.</p>[/vc_column_text]
<h2>DOCENTI</h2>
<h3 style="font-weight: bold;">Luca MASALA</h3>
[vc_column_text]<p>Classico<br />Tecnica<br />Variazioni</p>[/vc_column_text]
<h3>Julieta MARTÍNEZ</h3>
[vc_column_text]<p>Repertorio contemporaneo<br />Improvvisazione</p>[/vc_column_text]
<h2>PIANISTI</h2>
<h3>Massimiliano GRECO</h3>
[vc_column_text]<p>Pianista accompagnatore</p>[/vc_column_text]
[/vc_column][/vc_row]
"""

PAYMENT_TEXT = "Legacy Master of Ballet ITALY 850€ + 50,00€ Tariffa Paypal / PayPal Fees"


def test_core_fields():
    o = ub._build_offering(INFO_RENDERED, PAYMENT_TEXT)
    assert o.id == "umbria-ballet/legacy-master-of-ballet-2026"
    assert o.title == "Legacy Master of Ballet 2026"
    assert o.schedule.start == date(2026, 6, 29)
    assert o.schedule.end == date(2026, 7, 4)
    assert o.schedule.season == "2026"
    assert o.location is not None
    assert o.location.venue == "Resort Valle di Assisi"


def test_genres_scoped_to_lessons():
    o = ub._build_offering(INFO_RENDERED, PAYMENT_TEXT)
    # From "LE LEZIONI": classical (Tecnica classica), contemporary, pointe (Punte).
    # "Repertorio contemporaneo" sits only in a faculty label → repertoire NOT emitted.
    assert o.genres == ["classical", "contemporary", "pointe"]


def test_faculty_excludes_pianists():
    o = ub._build_offering(INFO_RENDERED, PAYMENT_TEXT)
    names = [t.name for t in o.teachers]
    assert "Luca MASALA" in names
    assert "Julieta MARTÍNEZ" in names
    assert "Massimiliano GRECO" not in names  # pianist accompanist dropped


def test_price_and_requirements():
    o = ub._build_offering(INFO_RENDERED, PAYMENT_TEXT)
    assert len(o.prices) == 1
    assert o.prices[0].amount == 850.0
    assert o.prices[0].currency == "EUR"
    assert o.prices[0].includes == ["tuition"]
    types = {type(r) for r in o.application.requirements}
    assert PhotosReq in types and VideoReq in types


def test_no_price_when_payment_missing():
    o = ub._build_offering(INFO_RENDERED, "")
    assert o.prices == []
