"""Unit tests for the Nuovo Balletto Classico summer-courses scraper.

Pin the Italian date range, the five-genre extraction, the open-topped age, the
deduped intensity-tier prices + residential package, the open status, and the
fail-open raise. Inline HTML (incl. a duplicated slider block), no network.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import nuovo_balletto_classico as n

# Mirrors the LayerSlider page: the pricing block appears twice (must dedupe).
_BLOCK = """
<p>Sono aperte le iscrizioni. Dal 29 giugno al 18 luglio 2026, corsi dai 10 anni in su.</p>
<p>Danza classica e punte. Repertorio e passo a due. Danza di carattere e contemporanea.</p>
<p>Percorso Base (1 lezione/giorno): € 140,00 Percorso Standard (2 lezioni/giorno): € 210,00
Percorso Full Immersion (6 lezioni/giorno): € 390,00</p>
<p>Il tutto al costo di appena 330 € a settimana, comprende il servizio pasti e trasporto.</p>
"""
_HTML = f"<html><body>{_BLOCK}{_BLOCK}</body></html>"


def test_date_range_and_id():
    off = n._build_offering(_HTML)
    assert (off.schedule.start, off.schedule.end) == (date(2026, 6, 29), date(2026, 7, 18))
    assert off.id == "nuovo-balletto-classico/corsi-estivi-2026"


def test_five_genres():
    off = n._build_offering(_HTML)
    assert off.genres == ["classical", "pointe", "repertoire", "character", "contemporary"]


def test_age_open_topped():
    assert n._build_offering(_HTML).age_range == {"min": 10}


def test_prices_deduped_with_residential():
    off = n._build_offering(_HTML)
    tuition = [p for p in off.prices if p.type == "tuition"]
    # 3 distinct tiers despite the block appearing twice.
    assert {p.amount for p in tuition} == {140, 210, 390}
    assert all(p.notes == "Per week." for p in tuition)
    res = [p for p in off.prices if "Residential" in (p.label or "")]
    assert len(res) == 1
    assert res[0].amount == 330
    assert set(res[0].includes) == {"accommodation", "meals"}


def test_status_open():
    assert n._build_offering(_HTML).application.status == "open"


def test_raises_without_dates():
    with pytest.raises(ValueError):
        n._build_offering("<html><body><p>In aggiornamento</p></body></html>")
