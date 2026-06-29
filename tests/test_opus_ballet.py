"""Unit tests for the Opus Ballet Summer Campus scraper.

Pin the Italian elided date range, the edition note, the out-of-scope genre
drop, the open-topped age, the PDF-sourced €20 registration fee + venue, and the
fail-open raise. Inline HTML/PDF-text, no network.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import opus_ballet as o

_HTML = """
<html><body>
<h1>Summer Campus</h1>
<p>Dal 29 giugno all'11 luglio 2026</p>
<p>La XXVI edizione del SUMMER DANCE CAMPUS si terrà a Firenze dal 29 giugno
all'11 luglio e propone lezioni di danza classica, modern, contemporanea, hip hop,
e un programma junior con lezioni dai 7 ai 12 anni.</p>
</body></html>
"""

_PDF = (
    "CENTRO OPUSBALLET SSD a r.l. via Ugo Foscolo, 6 - 50124 Firenze "
    "SCHEDA DI ISCRIZIONE SUMMER CAMPUS 2026 QUOTA DI ISCRIZIONE € 20,00"
)


def test_date_range_with_elision():
    off = o._build_offering(_HTML, _PDF)
    assert (off.schedule.start, off.schedule.end) == (date(2026, 6, 29), date(2026, 7, 11))
    assert off.id == "opus-ballet/summer-campus-2026"


def test_edition_note_and_genres():
    off = o._build_offering(_HTML, _PDF)
    assert "XXVI edizione" in (off.schedule.notes or "")
    assert off.genres == ["classical", "contemporary"]  # hip hop dropped


def test_age_open_topped():
    off = o._build_offering(_HTML, _PDF)
    assert off.age_range == {"min": 7}  # adults → no upper bound


def test_pdf_registration_fee_and_venue():
    off = o._build_offering(_HTML, _PDF)
    assert len(off.prices) == 1
    assert off.prices[0].amount == 20
    assert off.prices[0].type == "registration"
    assert off.location is not None
    assert off.location.city == "Florence"
    assert "Ugo Foscolo" in (off.location.venue or "")


def test_no_pdf_means_no_price_no_venue():
    off = o._build_offering(_HTML, "")
    assert off.prices == []
    assert off.location is not None and off.location.venue is None


def test_raises_without_dates():
    with pytest.raises(ValueError):
        o._build_offering("<html><body><p>Prossimamente</p></body></html>", "")
